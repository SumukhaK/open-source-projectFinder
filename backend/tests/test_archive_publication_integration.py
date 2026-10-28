"""Opt-in real Milvus proof for publication and bounded retirement."""

import hashlib
import os
import sqlite3
import uuid
from contextlib import contextmanager

import pytest
from app.core import archive_store
from app.core.config import Settings
from app.integrations.milvus import MilvusAdapter, VectorChunk
from app.services.archive_index import PreparedChunk, PreparedRepository
from app.services.archive_publication import (
    ReconcileResult,
    load_active_chunks,
    publish_revision,
    reconcile,
)
from app.services.embeddings import ModelManifest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MILVUS_INTEGRATION") != "1",
    reason="Opt-in synthetic proof needs the private pinned Milvus server",
)

REPO_ID = 9001


def make_prepared(revision, count):
    chunks = tuple(
        PreparedChunk(
            chunk_id=hashlib.sha256(f"{revision}:{ordinal}".encode()).hexdigest(),
            ordinal=ordinal,
            section=f"Section {ordinal}",
            text=f"passage text {ordinal}",
            token_count=ordinal + 2,
            text_hash=hashlib.sha256(f"passage text {ordinal}".encode()).hexdigest(),
        )
        for ordinal in range(count)
    )
    return PreparedRepository(
        repo_id=REPO_ID,
        semantic_hash=revision,
        normalizer_version="markdown-v1",
        chunker_version="sections-v1",
        model_revision=ModelManifest.load().revision,
        readme_status="present",
        omissions=(),
        chunks=chunks,
    )


def make_vectors(prepared):
    vectors = []
    for chunk in prepared.chunks:
        values = [0.0] * 384
        values[chunk.ordinal] = 1.0
        vectors.append(
            VectorChunk(
                chunk_id=chunk.chunk_id,
                repo_id=prepared.repo_id,
                revision=prepared.semantic_hash,
                model_revision=prepared.model_revision,
                language="Python",
                license="MIT",
                pushed_at=1_700_000_000,
                ordinal=chunk.ordinal,
                section=chunk.section,
                snippet=chunk.text,
                vector=tuple(values),
            )
        )
    return tuple(vectors)


def create_catalogue(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    for migration in archive_store.MIGRATIONS:
        for statement in migration:
            db.execute(statement)
    db.execute(f"PRAGMA user_version={len(archive_store.MIGRATIONS)}")
    db.commit()
    db.close()


def seed_document(path, prepared):
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute(
        "INSERT INTO archive_repositories (repo_id, full_name) VALUES (?, ?) "
        "ON CONFLICT(repo_id) DO NOTHING",
        (prepared.repo_id, "acme/compass"),
    )
    db.execute(
        "INSERT INTO archive_documents (repo_id, revision, state, model_revision, "
        "normalizer_version, chunker_version) VALUES (?, ?, 'pending', ?, ?, ?)",
        (
            prepared.repo_id,
            prepared.semantic_hash,
            prepared.model_revision,
            prepared.normalizer_version,
            prepared.chunker_version,
        ),
    )
    db.commit()
    db.close()


@contextmanager
def connect(path, write=False):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
    try:
        with db:
            yield db
    finally:
        db.close()


def test_real_publication_and_bounded_reconciliation(tmp_path):
    name = "reporadar_t08_" + uuid.uuid4().hex
    settings = Settings(_env_file=None, milvus_collection=name, milvus_timeout=30)
    adapter = MilvusAdapter.connect(settings, ModelManifest.load())
    client = adapter.client
    owned = not client.has_collection(name, timeout=30)
    path = tmp_path / "catalogue.sqlite3"
    create_catalogue(path)

    def open_db(write=False):
        return connect(path, write=write)

    try:
        assert owned, "Never reuse an existing collection for the disposable proof"
        adapter.ensure_collection()

        first = make_prepared("a" * 64, 3)
        seed_document(path, first)
        published = publish_revision(
            open_db, adapter, prepared=first, chunks=make_vectors(first)
        )
        assert published.chunks == 3
        assert adapter.ready(make_vectors(first))
        with open_db() as db:
            assert [chunk.chunk_id for chunk in load_active_chunks(db, REPO_ID)] == [
                chunk.chunk_id for chunk in first.chunks
            ]

        second = make_prepared("b" * 64, 1)
        seed_document(path, second)
        published = publish_revision(
            open_db, adapter, prepared=second, chunks=make_vectors(second)
        )
        assert published.previous == first.semantic_hash
        assert adapter.ready(make_vectors(first))
        with open_db() as db:
            assert [chunk.revision for chunk in load_active_chunks(db, REPO_ID)] == [
                second.semantic_hash
            ]

        cleaned = reconcile(open_db, adapter)
        assert cleaned == ReconcileResult(1, 3, 0)
        assert not adapter.ready(make_vectors(first))
        assert adapter.ready(make_vectors(second))
        with open_db() as db:
            assert [chunk.revision for chunk in load_active_chunks(db, REPO_ID)] == [
                second.semantic_hash
            ]
        assert reconcile(open_db, adapter) == ReconcileResult(0, 0, 0)
    finally:
        if owned:
            client.drop_collection(name, timeout=30)
        adapter.close()
