"""CPU-only embedding adapter for the pinned multilingual E5 model.

The manifest and this module are the only contract later search code needs.
`sentence-transformers` is imported lazily, so the API and unit tests run
without the optional embedding stack installed.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

MANIFEST_PATH = Path(__file__).with_name("embedding_model.json")
PREFIXES = {"query": "query: ", "passage": "passage: "}
MAX_BATCH_SIZE = 64
_CALLER_PREFIXES = ("query:", "passage:")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EmbeddingError(ValueError):
    """The input or the model output does not match the pinned contract."""


@dataclass(frozen=True)
class ModelManifest:
    name: str
    revision: str
    dimensions: int
    max_tokens: int
    license: str
    weights_file: str
    weights_sha256: str
    tokenizer_file: str
    tokenizer_sha256: str

    @classmethod
    def load(cls, path: Path = MANIFEST_PATH) -> ModelManifest:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise EmbeddingError(f"cannot read embedding manifest: {error}") from error
        if not isinstance(data, dict):
            raise EmbeddingError("embedding manifest must be an object")
        weights = data.get("weights")
        tokenizer = data.get("tokenizer")
        if not isinstance(weights, dict) or not isinstance(tokenizer, dict):
            raise EmbeddingError(
                "embedding manifest needs weights and tokenizer objects"
            )
        manifest = cls(
            name=_text(data, "name"),
            revision=_text(data, "revision"),
            dimensions=_positive_int(data, "dimensions"),
            max_tokens=_positive_int(data, "max_tokens"),
            license=_text(data, "license"),
            weights_file=_text(weights, "file"),
            weights_sha256=_text(weights, "sha256"),
            tokenizer_file=_text(tokenizer, "file"),
            tokenizer_sha256=_text(tokenizer, "sha256"),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise EmbeddingError(
                "embedding manifest field 'name' must be a non-empty string"
            )
        if not isinstance(self.license, str) or not self.license.strip():
            raise EmbeddingError(
                "embedding manifest field 'license' must be a non-empty string"
            )
        if not isinstance(self.revision, str) or not _REVISION.fullmatch(self.revision):
            raise EmbeddingError("embedding revision must be a 40-character commit SHA")
        if _unsafe_filename(self.weights_file) or not self.weights_file.endswith(
            ".safetensors"
        ):
            raise EmbeddingError(
                "embedding weights must be a local .safetensors filename"
            )
        if not _is_sha256(self.weights_sha256):
            raise EmbeddingError(
                "embedding weights sha256 must be 64 lowercase hex characters"
            )
        if _unsafe_filename(self.tokenizer_file):
            raise EmbeddingError("embedding tokenizer must be a local filename")
        if not _is_sha256(self.tokenizer_sha256):
            raise EmbeddingError(
                "embedding tokenizer sha256 must be 64 lowercase hex characters"
            )
        if not _is_positive_int(self.dimensions):
            raise EmbeddingError("embedding dimensions must be a positive integer")
        if not _is_positive_int(self.max_tokens):
            raise EmbeddingError("embedding max_tokens must be a positive integer")


class TextEncoder(Protocol):
    max_seq_length: int

    def get_embedding_dimension(self) -> int | None: ...

    def count_tokens(self, texts: Sequence[str]) -> Sequence[int]: ...

    def encode(
        self, texts: Sequence[str], *, batch_size: int
    ) -> Sequence[Sequence[float]]: ...


class EmbeddingAdapter:
    def __init__(
        self,
        manifest: ModelManifest,
        encoder: TextEncoder,
        *,
        batch_size: int = 16,
    ) -> None:
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or not 1 <= batch_size <= MAX_BATCH_SIZE
        ):
            raise EmbeddingError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
        self.manifest = manifest
        self.encoder = encoder
        self.batch_size = batch_size
        self._check_encoder()

    def _check_encoder(self) -> None:
        if self.encoder.max_seq_length != self.manifest.max_tokens:
            raise EmbeddingError(
                f"encoder max sequence length {self.encoder.max_seq_length} "
                f"does not match manifest {self.manifest.max_tokens}"
            )
        dimension = self.encoder.get_embedding_dimension()
        if dimension != self.manifest.dimensions:
            raise EmbeddingError(
                f"encoder returns {dimension} dimensions, "
                f"manifest pins {self.manifest.dimensions}"
            )

    @classmethod
    def load(
        cls,
        *,
        manifest_path: Path = MANIFEST_PATH,
        encoder_factory: Callable[[ModelManifest], TextEncoder] | None = None,
        batch_size: int = 16,
        warm: bool = True,
    ) -> EmbeddingAdapter:
        manifest = ModelManifest.load(manifest_path)
        factory = encoder_factory or _sentence_transformer_encoder
        adapter = cls(manifest, factory(manifest), batch_size=batch_size)
        if warm:
            adapter.embed(["warm up"], kind="query")
        return adapter

    def embed(
        self, texts: Sequence[str], *, kind: Literal["query", "passage"]
    ) -> list[tuple[float, ...]]:
        if kind not in PREFIXES:
            raise EmbeddingError(f"kind must be one of {sorted(PREFIXES)}")
        if isinstance(texts, str):
            raise EmbeddingError(
                "texts must be a sequence of text, not a single string"
            )
        prepared = [self._prepare(text, kind) for text in texts]
        if not prepared:
            return []

        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(prepared), self.batch_size):
            chunk = prepared[start : start + self.batch_size]
            counts = list(self.encoder.count_tokens(chunk))
            if len(counts) != len(chunk):
                raise EmbeddingError(
                    "tokenizer returned the wrong number of token counts"
                )
            for count in counts:
                if (
                    isinstance(count, bool)
                    or not isinstance(count, int)
                    or count > self.manifest.max_tokens
                ):
                    raise EmbeddingError(
                        f"text needs {count} tokens; "
                        f"the limit is {self.manifest.max_tokens}"
                    )
            rows = list(self.encoder.encode(chunk, batch_size=len(chunk)))
            if len(rows) != len(chunk):
                raise EmbeddingError("encoder returned the wrong number of vectors")
            vectors.extend(self._vector(row) for row in rows)
        return vectors

    def _prepare(self, text: str, kind: str) -> str:
        if not isinstance(text, str):
            raise EmbeddingError("embedding input must be text")
        text = text.strip()
        if not text:
            raise EmbeddingError("embedding input must not be empty")
        if text.lower().startswith(_CALLER_PREFIXES):
            raise EmbeddingError(
                "omit the E5 prefix; the adapter adds query: or passage:"
            )
        return PREFIXES[kind] + text

    def _vector(self, row: Sequence[float]) -> tuple[float, ...]:
        try:
            values = tuple(float(value) for value in row)
        except (TypeError, ValueError) as error:
            raise EmbeddingError("encoder returned a non-numeric vector") from error
        if len(values) != self.manifest.dimensions:
            raise EmbeddingError(
                f"encoder returned {len(values)} dimensions; "
                f"expected {self.manifest.dimensions}"
            )
        if not all(math.isfinite(value) for value in values):
            raise EmbeddingError("encoder returned a non-finite vector")
        norm = math.sqrt(math.fsum(value * value for value in values))
        if norm == 0:
            raise EmbeddingError("encoder returned a zero vector")
        # Normalize here as well as in the model call so the contract survives encoder changes.
        return tuple(value / norm for value in values)


class _SentenceTransformerEncoder:
    """Lazy wrapper so only this class imports the optional dependency."""

    def __init__(self, manifest: ModelManifest) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise EmbeddingError(
                "install backend/requirements.embeddings.txt to use embeddings"
            ) from error
        self._model = SentenceTransformer(
            manifest.name,
            revision=manifest.revision,
            device="cpu",
            trust_remote_code=False,
        )
        self._model.max_seq_length = manifest.max_tokens
        if self._model.tokenizer is None:
            raise EmbeddingError("pinned model has no tokenizer")
        self._tokenizer = self._model.tokenizer

    @property
    def max_seq_length(self) -> int:
        return self._model.max_seq_length

    def get_embedding_dimension(self) -> int | None:
        return self._model.get_embedding_dimension()

    def count_tokens(self, texts: Sequence[str]) -> list[int]:
        encoded = self._tokenizer(
            list(texts), add_special_tokens=True, truncation=False
        )
        return [len(ids) for ids in encoded["input_ids"]]

    def encode(
        self, texts: Sequence[str], *, batch_size: int
    ) -> Sequence[Sequence[float]]:
        return self._model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )


def _sentence_transformer_encoder(
    manifest: ModelManifest,
) -> _SentenceTransformerEncoder:
    return _SentenceTransformerEncoder(manifest)


def _text(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EmbeddingError(
            f"embedding manifest field {key!r} must be a non-empty string"
        )
    return value.strip()


def _positive_int(data: dict, key: str) -> int:
    value = data.get(key)
    if not _is_positive_int(value):
        raise EmbeddingError(
            f"embedding manifest field {key!r} must be a positive integer"
        )
    return value


def _is_positive_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _unsafe_filename(value: object) -> bool:
    return (
        not isinstance(value, str)
        or not value
        or "/" in value
        or "\\" in value
        or value in {".", ".."}
    )
