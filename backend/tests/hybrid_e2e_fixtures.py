"""Deterministic fixtures for the opt-in T26 cross-layer hybrid lane.

Nothing here downloads a model, contacts GitHub or writes outside the caller's
temporary directory. The real archive worker, Milvus adapter, FastAPI app and
uvicorn server are driven with these fixed inputs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from app.services.embeddings import ModelManifest

# The two source orders are fixed so the RRF result is fully known.
KEYWORD_ORDER = ("B", "G", "D", "A")
ARCHIVE_ORDER = ("A", "B", "C", "D", "E", "F")
EXPECTED_ORDER = ("B", "A", "D", "G", "C", "E", "F")
EXPECTED_SOURCES = {
    "B": ("github", "archive"),
    "A": ("github", "archive"),
    "D": ("github", "archive"),
    "G": ("github",),
    "C": ("archive",),
    "E": ("archive",),
    "F": ("archive",),
}

NORMAL_IDEA = "fixture archive planner"
INCOMPLETE_IDEA = "incomplete fixture query"
INCOMPLETE_LANGUAGE = "Rust"
QUERY_VECTOR = (1.0,) + (0.0,) * 383


@dataclass(frozen=True)
class RepoSpec:
    key: str
    repo_id: int
    full_name: str
    description: str
    stars: int
    weight: float
    language: str = "Python"
    license: str = "MIT"


SPECS = {
    "A": RepoSpec("A", 910001, "fixture/repo-a", "Archive alpha planner", 410, 0.95),
    "B": RepoSpec("B", 910002, "fixture/repo-b", "Archive beta planner", 420, 0.90),
    "C": RepoSpec("C", 910003, "fixture/repo-c", "Archive gamma planner", 430, 0.85),
    "D": RepoSpec("D", 910004, "fixture/repo-d", "Archive delta planner", 440, 0.80),
    "E": RepoSpec("E", 910005, "fixture/repo-e", "Archive epsilon planner", 450, 0.75),
    "F": RepoSpec("F", 910006, "fixture/repo-f", "Archive zeta planner", 460, 0.70),
    # G is only returned by the live keyword source and is never ingested.
    "G": RepoSpec("G", 910007, "fixture/repo-g", "Live omega planner", 470, 0.0),
}
BY_ID = {spec.repo_id: spec for spec in SPECS.values()}
BY_FULL_NAME = {spec.full_name: spec for spec in SPECS.values()}
ARCHIVE_IDS = tuple(SPECS[key].repo_id for key in ARCHIVE_ORDER)

README_TEMPLATE = "# Fixture {key}\n\nrepo-key-{key} deterministic archive passage.\n"


def repo_vector(weight: float) -> tuple[float, ...]:
    """A unit vector whose inner product with QUERY_VECTOR is ``weight``."""
    vector = [0.0] * 384
    vector[0] = weight
    vector[1] = math.sqrt(max(0.0, 1.0 - weight * weight))
    return tuple(vector)


VECTORS = {key: repo_vector(spec.weight) for key, spec in SPECS.items()}


def readme_bytes(key: str) -> bytes:
    return README_TEMPLATE.format(key=key).encode("utf-8")


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        b"blob %d\0" % len(data) + data, usedforsecurity=False
    ).hexdigest()


def metadata(key: str, *, private: bool = False) -> dict:
    spec = SPECS[key]
    return {
        "id": spec.repo_id,
        "name": spec.full_name.split("/")[1],
        "full_name": spec.full_name,
        "private": private,
        "visibility": "private" if private else "public",
        "archived": False,
        "fork": False,
        "default_branch": "main",
        "description": spec.description,
        "language": spec.language,
        "license": {"spdx_id": spec.license},
        "pushed_at": "2026-10-01T00:00:00Z",
        "stargazers_count": spec.stars,
        "owner": {"login": "fixture", "avatar_url": ""},
        "topics": ["fixture", key.lower()],
    }


class FixtureEmbeddings:
    """Deterministic stand-in for the pinned E5 adapter.

    It exposes the same ``manifest`` and ``encoder.count_tokens`` surface the
    real archive pipeline uses, so ingestion exercises the real preparation
    code without downloading model weights.
    """

    def __init__(self):
        self.manifest = ModelManifest.load()
        self.encoder = _FixtureEncoder()

    def embed(self, texts, *, kind):
        if kind == "query":
            return tuple(QUERY_VECTOR for _ in texts)
        if kind == "passage":
            return tuple(self._passage(text) for text in texts)
        raise ValueError("fixture embeddings only support query and passage")

    @staticmethod
    def _passage(text):
        for full_name, spec in BY_FULL_NAME.items():
            if full_name in text:
                return VECTORS[spec.key]
        raise ValueError("fixture passage has no repository identity")


class _FixtureEncoder:
    max_seq_length = 512

    def get_embedding_dimension(self):
        return 384

    def count_tokens(self, texts):
        return [max(1, len(text.split())) for text in texts]

    def encode(self, texts, *, batch_size):  # pragma: no cover - never called
        raise AssertionError("fixture encoder must not run model inference")


def _response(payload, status=200):
    return httpx.Response(status, content=json.dumps(payload).encode("utf-8"))


class FixtureTransport:
    """One MockTransport handler for OAuth, keyword search and archive reads."""

    def __init__(self, *, private_ids=()):
        self.private_ids = frozenset(int(value) for value in private_ids)

    def __call__(self, request):
        path = urlsplit(str(request.url)).path
        if path == "/login/oauth/access_token":
            return _response({"access_token": "fixture-provider-token"})
        if path == "/user":
            return _response({"id": 123, "login": "octocat", "avatar_url": ""})
        if path == "/search/repositories":
            return _response(self._search(request))
        if path.startswith("/repositories/"):
            return self._metadata_by_id(path)
        if path.startswith("/repos/"):
            return self._repository_path(path)
        return _response({"message": "not found"}, status=404)

    def _search(self, request):
        query = request.url.params.get("q", "")
        if "incomplete" in query:
            return {"total_count": 0, "incomplete_results": True, "items": []}
        items = [
            metadata(key, private=SPECS[key].repo_id in self.private_ids)
            for key in KEYWORD_ORDER
        ]
        return {
            "total_count": len(items),
            "incomplete_results": False,
            "items": items,
        }

    def _metadata_by_id(self, path):
        try:
            repo_id = int(path.rsplit("/", 1)[1])
        except ValueError:
            return _response({"message": "not found"}, status=404)
        spec = BY_ID.get(repo_id)
        if spec is None:
            return _response({"message": "not found"}, status=404)
        return _response(metadata(spec.key, private=repo_id in self.private_ids))

    def _repository_path(self, path):
        parts = path.split("/")
        if len(parts) < 4 or parts[1] != "repos":
            return _response({"message": "not found"}, status=404)
        full_name = parts[2] + "/" + parts[3]
        spec = BY_FULL_NAME.get(full_name)
        if spec is None:
            return _response({"message": "not found"}, status=404)
        if len(parts) >= 5 and parts[4] == "readme":
            data = readme_bytes(spec.key)
            return _response(
                {
                    "type": "file",
                    "path": "README.md",
                    "sha": blob_sha(data),
                    "size": len(data),
                    "encoding": "base64",
                    "content": base64.b64encode(data).decode("ascii"),
                }
            )
        return _response(metadata(spec.key, private=spec.repo_id in self.private_ids))
