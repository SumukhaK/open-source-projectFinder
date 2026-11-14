"""Focused unit proof that the hybrid runtime accepts injected dependencies."""

from __future__ import annotations

from types import SimpleNamespace

from app.core.config import Settings
from app.services.hybrid_runtime import HybridRuntime


class FakeReader:
    pass


class FakeEmbeddings:
    manifest = SimpleNamespace(revision="a" * 40)

    def embed(self, texts, *, kind):  # pragma: no cover - never called
        raise AssertionError("injected embeddings must not be replaced")


def test_injected_reader_and_embeddings_are_used_by_the_build(monkeypatch):
    settings = Settings(
        _env_file=None,
        hybrid_cursor_signing_key="k" * 32,
        archive_github_token="fixture-archive-token",
    )
    reader = FakeReader()
    embeddings = FakeEmbeddings()
    runtime = HybridRuntime(
        settings,
        provider=object(),
        archive_reader=reader,
        embeddings=embeddings,
    )
    store = SimpleNamespace(connect=lambda **_: None)
    vectors = object()
    monkeypatch.setattr(runtime, "_archive_store", lambda: store)
    monkeypatch.setattr(
        runtime, "_archive_components", lambda: (embeddings, vectors, "a" * 40)
    )

    assert runtime._load_embeddings() is embeddings
    target = runtime._build()

    assert target.revalidator.reader is reader
    assert target.pager.service.embeddings is embeddings
    assert target.pager.service.vectors is vectors
    assert target.generation == "a" * 40 + ":keyword-first-v1"
