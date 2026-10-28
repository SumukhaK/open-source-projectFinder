"""Bounded, offline preparation of repository content for later ingestion."""

import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass
from math import ceil

from app.core.config import (
    ARCHIVE_CHUNK_TOKENS,
    ARCHIVE_MARKDOWN_MAX_NESTING,
    ARCHIVE_MAX_CHUNKS,
    ARCHIVE_METADATA_MAX_BYTES,
    ARCHIVE_PARSE_MAX_CHARS,
    ARCHIVE_README_MAX_BYTES,
    ARCHIVE_TITLE_TOKENS,
    ARCHIVE_TOKEN_PROBE_CHARS,
    MILVUS_TEXT_BYTES,
)
from app.services.embeddings import PREFIXES, EmbeddingAdapter, EmbeddingError
from markdown_it import MarkdownIt

NORMALIZER_VERSION = "markdown-v1"
CHUNKER_VERSION = "sections-v1"
_NAVIGATION = {"contents", "table of contents", "navigation"}


@dataclass(frozen=True)
class PreparedChunk:
    chunk_id: str
    ordinal: int
    section: str
    text: str
    token_count: int
    text_hash: str


@dataclass(frozen=True)
class PreparedRepository:
    repo_id: int
    semantic_hash: str
    normalizer_version: str
    chunker_version: str
    model_revision: str
    readme_status: str
    omissions: tuple[str, ...]
    chunks: tuple[PreparedChunk, ...]


def prepare_repository(
    metadata: dict,
    readme: bytes | None,
    *,
    adapter: EmbeddingAdapter,
    source_truncated: bool = False,
) -> PreparedRepository:
    """Return inert passages; the caller later embeds them with kind='passage'.

    Reuse a loaded T02 adapter. Its counter includes special tokens and performs
    no truncation; this function adds the same passage prefix when counting.
    """
    if type(source_truncated) is not bool:
        raise ValueError("source_truncated must be a boolean")
    adapter.manifest.validate()
    repo_id, name, overview = _metadata(metadata)
    sections, status, omissions = _readme(readme)
    if source_truncated:
        omissions.append("source_truncated")
    semantic_hash = _hash(
        [
            name,
            overview,
            sections,
            status,
            omissions,
            NORMALIZER_VERSION,
            CHUNKER_VERSION,
            asdict(adapter.manifest),
            PREFIXES["passage"],
            ARCHIVE_README_MAX_BYTES,
            ARCHIVE_PARSE_MAX_CHARS,
            ARCHIVE_CHUNK_TOKENS,
            ARCHIVE_MAX_CHUNKS,
            ARCHIVE_TITLE_TOKENS,
            ARCHIVE_TOKEN_PROBE_CHARS,
            ARCHIVE_MARKDOWN_MAX_NESTING,
            MILVUS_TEXT_BYTES["section"],
        ]
    )

    def count(text):
        return _count(adapter, text)

    short_name = _fit(name, lambda text: count(text) <= ARCHIVE_TITLE_TOKENS)
    if short_name != name:
        omissions.append("title_tokens")
    chunks = []
    for section_index, (section, body) in enumerate(
        [("Overview", overview), *sections]
    ):
        short_section = _fit(
            section,
            lambda text: (
                count(text) <= ARCHIVE_TITLE_TOKENS
                and len(text.encode("utf-8")) <= MILVUS_TEXT_BYTES["section"]
            ),
        )
        if short_section != section:
            omissions.append("title_tokens")
        title = f"Repository: {short_name}\nSection: {short_section}"
        while True:
            if len(chunks) == ARCHIVE_MAX_CHUNKS:
                omissions.append("chunk_limit")
                break

            def fits(text):
                return count(text.strip()) <= ARCHIVE_CHUNK_TOKENS and count(
                    PREFIXES["passage"] + _passage(title, text)
                ) <= min(512, adapter.manifest.max_tokens)

            piece = _fit(body, fits)
            if len(piece) < len(body) and not body[len(piece)].isspace():
                for boundary in range(len(piece) - 1, ceil(len(piece) * 0.8) - 1, -1):
                    if piece[boundary].isspace():
                        piece = piece[:boundary]
                        break
            if (body and not piece) or not fits(piece):
                raise EmbeddingError("token budget cannot hold a repository passage")
            text = _passage(title, piece)
            ordinal = len(chunks)
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chunks.append(
                PreparedChunk(
                    _hash([repo_id, semantic_hash, ordinal, text_hash]),
                    ordinal,
                    short_section,
                    text,
                    count(PREFIXES["passage"] + text),
                    text_hash,
                )
            )
            body = body[len(piece) :].lstrip()
            if section_index == 0:
                if body:
                    omissions.append("overview_tokens")
                break
            if not body:
                break
        if "chunk_limit" in omissions:
            break
    return PreparedRepository(
        repo_id,
        semantic_hash,
        NORMALIZER_VERSION,
        CHUNKER_VERSION,
        adapter.manifest.revision,
        status,
        tuple(sorted(set(omissions))),
        tuple(chunks),
    )


def _passage(title, body):
    return title + ("\n\n" + body.strip() if body.strip() else "")


def _count(adapter, text):
    try:
        counts = list(adapter.encoder.count_tokens([text]))
    except Exception:
        raise EmbeddingError("archive tokenizer failed") from None
    if len(counts) != 1 or type(counts[0]) is not int or counts[0] < 1:
        raise EmbeddingError("archive tokenizer returned invalid counts")
    return counts[0]


def _fit(text, fits):
    # Bounded probes; each returned candidate is checked, even for non-monotonic tokenization.
    low, high = 0, min(len(text), ARCHIVE_TOKEN_PROBE_CHARS)
    while low < high:
        middle = (low + high + 1) // 2
        if fits(text[:middle]):
            low = middle
        else:
            high = middle - 1
    return text[:low]


def _hash(values):
    encoded = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def _metadata(metadata):
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    repo_id = metadata.get("id")
    if type(repo_id) is not int or not 0 < repo_id < 2**63:
        raise ValueError("metadata needs a positive numeric repository ID")
    fields = [metadata.get(key) for key in ("full_name", "description", "language")]
    topics = metadata.get("topics")
    if topics is None:
        topics = []
    if not isinstance(topics, list) or len(topics) > 100:
        raise ValueError("metadata topics must be a bounded list")
    size = 0
    for value in [*fields, *topics]:
        if value is None:
            continue
        if not isinstance(value, str) or len(value) > ARCHIVE_METADATA_MAX_BYTES:
            raise ValueError("metadata text must be bounded strings")
        if _binary_text(value):
            raise ValueError("metadata must not contain binary controls")
        size += len(value.encode("utf-8"))
    if size > ARCHIVE_METADATA_MAX_BYTES or any(not isinstance(t, str) for t in topics):
        raise ValueError("metadata exceeds its byte/type budget")
    name, description, language = [_normalize(value or "") for value in fields]
    if not name:
        raise ValueError("metadata full_name is required")
    parts = []
    for label, value in (
        ("Description", description),
        (
            "Topics",
            ", ".join(sorted({_normalize(topic) for topic in topics if topic.strip()})),
        ),
        ("Language", language),
    ):
        if value:
            parts.append(f"{label}: {value}")
    return repo_id, name, "\n".join(parts)


def _readme(raw):
    if raw is None:
        return [], "missing", []
    if not isinstance(raw, bytes):
        raise ValueError("README must be decoded bytes or None")
    if len(raw) > ARCHIVE_README_MAX_BYTES:
        return [], "too_large", ["readme_bytes"]
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], "invalid", []
    if _binary_text(text):
        return [], "invalid", []
    if not text.strip():
        return [], "empty", []
    omissions = ["parse_chars"] if len(text) > ARCHIVE_PARSE_MAX_CHARS else []
    return _sections(text[:ARCHIVE_PARSE_MAX_CHARS]), "present", omissions


def _binary_text(text):
    return any(
        unicodedata.category(char) == "Cc" and char not in "\t\r\n" for char in text
    )


def _sections(text):
    # Parse HTML as tokens to discard; never render it or resolve any asset.
    tokens = MarkdownIt(
        "commonmark", {"html": True, "maxNesting": ARCHIVE_MARKDOWN_MAX_NESTING}
    ).parse(text)
    sections, paragraphs = [], []
    title = "README"
    for index, token in enumerate(tokens):
        if token.type == "inline":
            content = _inline_text(token.children or [])
            if index and tokens[index - 1].type == "heading_open":
                sections.append((title, "\n\n".join(paragraphs)))
                title, paragraphs = content or "README", []
            elif content:
                paragraphs.append(content)
        elif token.type in {"fence", "code_block"}:
            paragraphs.append(_normalize(token.content))
    sections.append((title, "\n\n".join(paragraphs)))
    seen, useful = set(), []
    for title, content in sections:
        if content and title.casefold() not in _NAVIGATION and content not in seen:
            useful.append((title, content))
            seen.add(content)
    return useful


def _inline_text(tokens):
    if any(token.type == "html_inline" for token in tokens):
        return ""
    parts, anchor = [], False
    for token in tokens:
        if token.type == "link_open":
            anchor = (token.attrGet("href") or "").startswith("#")
        elif token.type == "link_close":
            anchor = False
        elif not anchor and token.type in {"text", "code_inline"}:
            parts.append(token.content)
        elif token.type in {"softbreak", "hardbreak"}:
            parts.append(" ")
    return _normalize("".join(parts))
