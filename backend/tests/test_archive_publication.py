import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from app.core import archive_store
from app.integrations.milvus import MilvusUnavailable, VectorChunk
from app.services.archive_index import PreparedChunk, PreparedRepository
from app.services.archive_publication import (
    PublicationContractError,
    PublicationIncomplete,
    PublicationResult,
    ReconcileResult,
    filter_active_hits,
    load_active_chunks,
    publish_revision,
    reconcile,
)

REPO_ID = 42
MODEL_REVISION = "c" * 40
VECTOR = [0.01] * 384


def make_chunk_id(revision, ordinal):
    return hashlib.sha256(f"{revision}:{ordinal}".encode()).hexdigest()


def make_prepared(count=3, *, revision="a" * 64, repo_id=REPO_ID):
    chunks = tuple(
        PreparedChunk(
            chunk_id=make_chunk_id(revision, ordinal),
            ordinal=ordinal,
            section=f"Section {ordinal}",
            text=f"passage text {ordinal}",
            token_count=ordinal + 2,
            text_hash=hashlib.sha256(f"passage text {ordinal}".encode()).hexdigest(),
        )
        for ordinal in range(count)
    )
    return PreparedRepository(
        repo_id=repo_id,
        semantic_hash=revision,
        normalizer_version="markdown-v1",
        chunker_version="sections-v1",
        model_revision=MODEL_REVISION,
        readme_status="present",
        omissions=(),
        chunks=chunks,
    )


def make_vectors(prepared):
    return tuple(
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
            vector=VECTOR,
        )
        for chunk in prepared.chunks
    )


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "catalogue.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=ON")
    for migration in archive_store.MIGRATIONS:
        for statement in migration:
            connection.execute(statement)
    connection.execute(f"PRAGMA user_version={len(archive_store.MIGRATIONS)}")
    connection.commit()
    connection.close()
    return path


@pytest.fixture
def connect(db_path):
    @contextmanager
    def open_db(write=False):
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            with db:
                yield db
        finally:
            db.close()

    return open_db


def seed_document(db_path, prepared, *, state="pending"):
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute(
        "INSERT INTO archive_repositories (repo_id, full_name) VALUES (?, ?) "
        "ON CONFLICT(repo_id) DO NOTHING",
        (prepared.repo_id, "acme/compass"),
    )
    db.execute(
        "INSERT INTO archive_documents (repo_id, revision, state, model_revision, "
        "normalizer_version, chunker_version) VALUES (?, ?, ?, ?, ?, ?)",
        (
            prepared.repo_id,
            prepared.semantic_hash,
            state,
            prepared.model_revision,
            prepared.normalizer_version,
            prepared.chunker_version,
        ),
    )
    db.commit()
    db.close()


def stage_pending_chunks(db_path, prepared, *, written=False):
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA foreign_keys=ON")
    for chunk in prepared.chunks:
        db.execute(
            "INSERT INTO archive_chunks (chunk_id, repo_id, revision, ordinal, "
            "section, text, text_sha256, token_count, vector_state) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                chunk.chunk_id,
                prepared.repo_id,
                prepared.semantic_hash,
                chunk.ordinal,
                chunk.section,
                chunk.text,
                chunk.text_hash,
                chunk.token_count,
                "written" if written else "pending",
            ),
        )
    db.commit()
    db.close()


class CountingDB:
    def __init__(self, db):
        self.db = db
        self.queries = 0

    def execute(self, *args, **kwargs):
        self.queries += 1
        return self.db.execute(*args, **kwargs)


class FakeVectors:
    def __init__(
        self,
        *,
        batch_size=2,
        ready=True,
        fail_upsert_batch=None,
        fail_delete_batch=None,
        inspect_upsert=None,
        inspect_delete=None,
    ):
        self.settings = SimpleNamespace(milvus_batch_size=batch_size)
        self.ready_result = ready
        self.fail_upsert_batch = fail_upsert_batch
        self.fail_delete_batch = fail_delete_batch
        self.inspect_upsert = inspect_upsert
        self.inspect_delete = inspect_delete
        self.upserts = []
        self.readies = []
        self.deletes = []
        self.upsert_attempts = 0
        self.delete_attempts = 0

    def upsert(self, chunks):
        attempt = self.upsert_attempts
        self.upsert_attempts += 1
        if self.fail_upsert_batch == attempt:
            raise MilvusUnavailable("synthetic upsert failure")
        if self.inspect_upsert is not None:
            self.inspect_upsert()
        self.upserts.append(tuple(chunk.chunk_id for chunk in chunks))
        return len(chunks)

    def ready(self, chunks):
        self.readies.append(tuple(chunk.chunk_id for chunk in chunks))
        return self.ready_result

    def delete(self, chunk_ids):
        attempt = self.delete_attempts
        self.delete_attempts += 1
        if self.fail_delete_batch == attempt:
            raise MilvusUnavailable("synthetic delete failure")
        if self.inspect_delete is not None:
            self.inspect_delete()
        self.deletes.append(tuple(chunk_ids))
        return len(chunk_ids)


def test_publish_stages_pending_chunks_before_writing_vectors(connect, db_path):
    prepared = make_prepared()
    seed_document(db_path, prepared)
    observed = []

    def inspect_upsert():
        with connect() as db:
            observed.append(
                (
                    db.execute("SELECT state FROM archive_documents").fetchone()[0],
                    db.execute(
                        "SELECT active_revision FROM archive_repositories"
                    ).fetchone()[0],
                    [
                        row[0]
                        for row in db.execute(
                            "SELECT vector_state FROM archive_chunks ORDER BY ordinal"
                        )
                    ],
                    load_active_chunks(db, REPO_ID),
                )
            )

    vectors = FakeVectors(inspect_upsert=inspect_upsert)
    result = publish_revision(
        connect, vectors, prepared=prepared, chunks=make_vectors(prepared)
    )

    assert result == PublicationResult(REPO_ID, prepared.semantic_hash, 3, None)
    assert observed
    assert all(
        state == "pending"
        and active is None
        and states == ["pending"] * 3
        and not visible
        for state, active, states, visible in observed
    )
    assert vectors.upserts == [
        (prepared.chunks[0].chunk_id, prepared.chunks[1].chunk_id),
        (prepared.chunks[2].chunk_id,),
    ]
    assert vectors.readies == vectors.upserts
    with connect() as db:
        assert (
            db.execute("SELECT state FROM archive_documents").fetchone()[0]
            == "published"
        )
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == prepared.semantic_hash
        )
        assert [
            row[0]
            for row in db.execute(
                "SELECT vector_state FROM archive_chunks ORDER BY ordinal"
            )
        ] == ["written"] * 3
        assert [chunk.chunk_id for chunk in load_active_chunks(db, REPO_ID)] == [
            chunk.chunk_id for chunk in prepared.chunks
        ]


def test_publish_rejects_missing_pending_document_without_writes(connect, db_path):
    prepared = make_prepared()
    vectors = FakeVectors()

    with pytest.raises(PublicationContractError):
        publish_revision(
            connect, vectors, prepared=prepared, chunks=make_vectors(prepared)
        )

    assert vectors.upserts == []
    with connect() as db:
        assert db.execute("SELECT count(*) FROM archive_documents").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM archive_chunks").fetchone()[0] == 0


def test_mid_batch_failure_keeps_previous_revision_and_retry_is_idempotent(
    connect, db_path
):
    first = make_prepared(revision="a" * 64)
    seed_document(db_path, first)
    publish_revision(connect, FakeVectors(), prepared=first, chunks=make_vectors(first))

    second = make_prepared(revision="b" * 64)
    seed_document(db_path, second)
    broken = FakeVectors(fail_upsert_batch=1)
    with pytest.raises(MilvusUnavailable):
        publish_revision(connect, broken, prepared=second, chunks=make_vectors(second))

    with connect() as db:
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == first.semantic_hash
        )
        assert (
            db.execute(
                "SELECT state FROM archive_documents WHERE revision=?",
                (second.semantic_hash,),
            ).fetchone()[0]
            == "pending"
        )
        assert [
            row[0]
            for row in db.execute(
                "SELECT vector_state FROM archive_chunks WHERE revision=? "
                "ORDER BY ordinal",
                (second.semantic_hash,),
            )
        ] == ["pending"] * 3
        assert [chunk.revision for chunk in load_active_chunks(db, REPO_ID)] == [
            first.semantic_hash
        ] * 3

    healthy = FakeVectors()
    result = publish_revision(
        connect, healthy, prepared=second, chunks=make_vectors(second)
    )

    assert result.previous == first.semantic_hash
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM archive_chunks WHERE revision=?",
                (second.semantic_hash,),
            ).fetchone()[0]
            == 3
        )
        assert [chunk.revision for chunk in load_active_chunks(db, REPO_ID)] == [
            second.semantic_hash
        ] * 3
    attempted = {chunk_id for batch in broken.upserts for chunk_id in batch}
    assert attempted <= {chunk.chunk_id for chunk in second.chunks}
    assert len({chunk_id for batch in healthy.upserts for chunk_id in batch}) == len(
        second.chunks
    )


def test_unreadable_vectors_never_activate(connect, db_path):
    prepared = make_prepared()
    seed_document(db_path, prepared)
    vectors = FakeVectors(ready=False)

    with pytest.raises(PublicationIncomplete):
        publish_revision(
            connect, vectors, prepared=prepared, chunks=make_vectors(prepared)
        )

    with connect() as db:
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            is None
        )
        assert (
            db.execute("SELECT state FROM archive_documents").fetchone()[0] == "pending"
        )
        assert [
            row[0]
            for row in db.execute(
                "SELECT vector_state FROM archive_chunks ORDER BY ordinal"
            )
        ] == ["pending"] * 3
        assert load_active_chunks(db, REPO_ID) == ()


def test_activation_failure_after_vectors_keeps_revision_pending(connect, db_path):
    first = make_prepared(revision="a" * 64)
    seed_document(db_path, first)
    publish_revision(connect, FakeVectors(), prepared=first, chunks=make_vectors(first))

    second = make_prepared(revision="b" * 64)
    seed_document(db_path, second)
    writes = 0

    @contextmanager
    def failing_connect(write=False):
        nonlocal writes
        if write:
            writes += 1
            if writes == 2:
                raise sqlite3.OperationalError("synthetic activation failure")
        with connect(write=write) as db:
            yield db

    vectors = FakeVectors()
    with pytest.raises(sqlite3.OperationalError):
        publish_revision(
            failing_connect, vectors, prepared=second, chunks=make_vectors(second)
        )

    assert vectors.upserts
    with connect() as db:
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == first.semantic_hash
        )
        assert (
            db.execute(
                "SELECT state FROM archive_documents WHERE revision=?",
                (second.semantic_hash,),
            ).fetchone()[0]
            == "pending"
        )
        assert [chunk.revision for chunk in load_active_chunks(db, REPO_ID)] == [
            first.semantic_hash
        ] * 3

    result = publish_revision(
        connect, FakeVectors(), prepared=second, chunks=make_vectors(second)
    )
    assert result.previous == first.semantic_hash


def test_activation_keeps_superseded_vectors_until_reconcile(connect, db_path):
    first = make_prepared(count=3, revision="a" * 64)
    second = make_prepared(count=1, revision="b" * 64)
    seed_document(db_path, first)
    publish_revision(connect, FakeVectors(), prepared=first, chunks=make_vectors(first))
    seed_document(db_path, second)

    vectors = FakeVectors()
    result = publish_revision(
        connect, vectors, prepared=second, chunks=make_vectors(second)
    )

    assert result.previous == first.semantic_hash
    assert vectors.deletes == []
    with connect() as db:
        assert [chunk.revision for chunk in load_active_chunks(db, REPO_ID)] == [
            second.semantic_hash
        ]
        assert (
            db.execute(
                "SELECT state FROM archive_documents WHERE revision=?",
                (first.semantic_hash,),
            ).fetchone()[0]
            == "superseded"
        )
        assert (
            db.execute(
                "SELECT count(*) FROM archive_chunks WHERE revision=?",
                (first.semantic_hash,),
            ).fetchone()[0]
            == 3
        )

    observed = []

    def inspect_delete():
        with connect() as db:
            observed.append(
                db.execute(
                    "SELECT count(*) FROM archive_chunks WHERE revision=?",
                    (first.semantic_hash,),
                ).fetchone()[0]
            )

    vectors.inspect_delete = inspect_delete
    cleaned = reconcile(connect, vectors)

    assert cleaned == ReconcileResult(1, 3, 0)
    assert observed == [3, 3]
    assert vectors.deletes == [
        (first.chunks[0].chunk_id, first.chunks[1].chunk_id),
        (first.chunks[2].chunk_id,),
    ]
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM archive_documents WHERE revision=?",
                (first.semantic_hash,),
            ).fetchone()[0]
            == 0
        )
        assert [chunk.revision for chunk in load_active_chunks(db, REPO_ID)] == [
            second.semantic_hash
        ]
    assert reconcile(connect, vectors) == ReconcileResult(0, 0, 0)


def test_reconcile_is_bounded_and_never_activates_pending(connect, db_path):
    superseded = [
        make_prepared(count=1, revision=revision)
        for revision in ("a" * 64, "b" * 64, "c" * 64)
    ]
    pending = [
        make_prepared(count=1, revision=revision) for revision in ("d" * 64, "e" * 64)
    ]
    for prepared in superseded:
        seed_document(db_path, prepared, state="superseded")
    for prepared in pending:
        seed_document(db_path, prepared)

    first = reconcile(connect, FakeVectors(), limit=2)
    assert first == ReconcileResult(2, 0, 2)
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM archive_documents WHERE state='superseded'"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT count(*) FROM archive_documents WHERE state='pending'"
            ).fetchone()[0]
            == 2
        )
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            is None
        )

    second = reconcile(connect, FakeVectors(), limit=2)
    assert second == ReconcileResult(1, 0, 2)
    assert reconcile(connect, FakeVectors()) == ReconcileResult(0, 0, 2)


def test_reconcile_retries_partial_vector_deletion_before_removing_rows(
    connect, db_path
):
    first = make_prepared(count=3, revision="a" * 64)
    second = make_prepared(count=1, revision="b" * 64)
    seed_document(db_path, first)
    publish_revision(connect, FakeVectors(), prepared=first, chunks=make_vectors(first))
    seed_document(db_path, second)
    publish_revision(
        connect, FakeVectors(), prepared=second, chunks=make_vectors(second)
    )

    broken = FakeVectors(fail_delete_batch=1)
    with pytest.raises(MilvusUnavailable):
        reconcile(connect, broken)

    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM archive_documents WHERE revision=?",
                (first.semantic_hash,),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT count(*) FROM archive_chunks WHERE revision=?",
                (first.semantic_hash,),
            ).fetchone()[0]
            == 3
        )

    cleaned = reconcile(connect, FakeVectors())
    assert cleaned == ReconcileResult(1, 3, 0)
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM archive_documents WHERE revision=?",
                (first.semantic_hash,),
            ).fetchone()[0]
            == 0
        )
        assert [chunk.revision for chunk in load_active_chunks(db, REPO_ID)] == [
            second.semantic_hash
        ]


def test_load_active_chunks_fails_closed_for_pending_partial_or_gapped_sets(
    connect, db_path
):
    prepared = make_prepared(count=3)
    seed_document(db_path, prepared)
    publish_revision(
        connect, FakeVectors(), prepared=prepared, chunks=make_vectors(prepared)
    )

    with connect(write=True) as db:
        db.execute(
            "UPDATE archive_chunks SET vector_state='pending' WHERE chunk_id=?",
            (prepared.chunks[1].chunk_id,),
        )
    with connect() as db:
        assert load_active_chunks(db, REPO_ID) == ()

    with connect(write=True) as db:
        db.execute("UPDATE archive_chunks SET vector_state='written'")
        db.execute(
            "DELETE FROM archive_chunks WHERE chunk_id=?",
            (prepared.chunks[1].chunk_id,),
        )
    with connect() as db:
        assert load_active_chunks(db, REPO_ID) == ()

    pending = make_prepared(count=1, revision="d" * 64)
    seed_document(db_path, pending)
    with connect(write=True) as db:
        db.execute(
            "UPDATE archive_repositories SET active_revision=?",
            (pending.semantic_hash,),
        )
    with connect() as db:
        assert load_active_chunks(db, REPO_ID) == ()


def test_replay_of_active_revision_is_idempotent(connect, db_path):
    prepared = make_prepared()
    seed_document(db_path, prepared)
    publish_revision(
        connect, FakeVectors(), prepared=prepared, chunks=make_vectors(prepared)
    )

    vectors = FakeVectors()
    result = publish_revision(
        connect, vectors, prepared=prepared, chunks=make_vectors(prepared)
    )

    assert result == PublicationResult(
        REPO_ID, prepared.semantic_hash, 3, prepared.semantic_hash
    )
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM archive_chunks WHERE revision=?",
                (prepared.semantic_hash,),
            ).fetchone()[0]
            == 3
        )
        assert [
            row[0]
            for row in db.execute(
                "SELECT vector_state FROM archive_chunks ORDER BY ordinal"
            )
        ] == ["written"] * 3
    assert len({chunk_id for batch in vectors.upserts for chunk_id in batch}) == len(
        prepared.chunks
    )


def test_superseded_revision_cannot_be_reactivated(connect, db_path):
    first = make_prepared(revision="a" * 64)
    second = make_prepared(revision="b" * 64)
    seed_document(db_path, first)
    publish_revision(connect, FakeVectors(), prepared=first, chunks=make_vectors(first))
    seed_document(db_path, second)
    publish_revision(
        connect, FakeVectors(), prepared=second, chunks=make_vectors(second)
    )

    with pytest.raises(PublicationContractError):
        publish_revision(
            connect, FakeVectors(), prepared=first, chunks=make_vectors(first)
        )

    with connect() as db:
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == second.semantic_hash
        )


def test_published_revision_must_still_be_active(connect, db_path):
    prepared = make_prepared()
    seed_document(db_path, prepared, state="published")

    with pytest.raises(PublicationContractError):
        publish_revision(
            connect, FakeVectors(), prepared=prepared, chunks=make_vectors(prepared)
        )


def test_staging_rejects_a_document_from_another_model_revision(connect, db_path):
    prepared = make_prepared()
    seed_document(db_path, prepared)
    with connect(write=True) as db:
        db.execute(
            "UPDATE archive_documents SET model_revision=? "
            "WHERE repo_id=? AND revision=?",
            ("d" * 40, prepared.repo_id, prepared.semantic_hash),
        )

    with pytest.raises(PublicationContractError):
        publish_revision(
            connect, FakeVectors(), prepared=prepared, chunks=make_vectors(prepared)
        )


def test_staging_refuses_extra_catalogue_chunks(connect, db_path):
    prepared = make_prepared()
    seed_document(db_path, prepared)
    with connect(write=True) as db:
        db.execute(
            "INSERT INTO archive_chunks (chunk_id, repo_id, revision, ordinal, "
            "section, text, text_sha256, token_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "f" * 64,
                REPO_ID,
                prepared.semantic_hash,
                3,
                "Section 3",
                "extra",
                hashlib.sha256(b"extra").hexdigest(),
                2,
            ),
        )

    with pytest.raises(PublicationContractError):
        publish_revision(
            connect, FakeVectors(), prepared=prepared, chunks=make_vectors(prepared)
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda prepared: object(),
        lambda prepared: replace(prepared, chunks=()),
        lambda prepared: replace(prepared, semantic_hash="A" * 64),
        lambda prepared: replace(prepared, repo_id=0),
        lambda prepared: replace(prepared, model_revision=""),
        lambda prepared: replace(prepared, chunks=(object(),)),
        lambda prepared: replace(
            prepared, chunks=(replace(prepared.chunks[0], text=""),)
        ),
        lambda prepared: replace(
            prepared, chunks=(replace(prepared.chunks[0], section=None),)
        ),
        lambda prepared: replace(prepared, chunks=make_prepared(count=9).chunks),
        lambda prepared: replace(
            prepared,
            chunks=(prepared.chunks[0], replace(prepared.chunks[1], ordinal=0)),
        ),
        lambda prepared: replace(
            prepared,
            chunks=(prepared.chunks[0], replace(prepared.chunks[1], ordinal=3)),
        ),
        lambda prepared: replace(
            prepared,
            chunks=(
                prepared.chunks[0],
                replace(prepared.chunks[1], text_hash="0" * 64),
                prepared.chunks[2],
            ),
        ),
        lambda prepared: replace(
            prepared,
            chunks=(
                prepared.chunks[0],
                replace(prepared.chunks[1], token_count=0),
                prepared.chunks[2],
            ),
        ),
        lambda prepared: replace(
            prepared,
            chunks=(
                prepared.chunks[0],
                replace(prepared.chunks[1], chunk_id="not-a-hash"),
                prepared.chunks[2],
            ),
        ),
        lambda prepared: replace(
            prepared,
            chunks=(
                prepared.chunks[0],
                replace(prepared.chunks[1], chunk_id=prepared.chunks[0].chunk_id),
                prepared.chunks[2],
            ),
        ),
    ],
)
def test_publish_rejects_invalid_prepared_contract(connect, db_path, mutation):
    prepared = make_prepared()
    seed_document(db_path, prepared)
    vectors = FakeVectors()

    with pytest.raises(PublicationContractError):
        publish_revision(
            connect,
            vectors,
            prepared=mutation(prepared),
            chunks=make_vectors(prepared),
        )

    assert vectors.upserts == []


@pytest.mark.parametrize(
    "mutation",
    [
        lambda prepared, chunks: chunks[:-1],
        lambda prepared, chunks: (replace(chunks[0], revision="f" * 64), *chunks[1:]),
        lambda prepared, chunks: (replace(chunks[0], repo_id=REPO_ID + 1), *chunks[1:]),
        lambda prepared, chunks: (
            replace(chunks[0], model_revision="d" * 40),
            *chunks[1:],
        ),
        lambda prepared, chunks: (replace(chunks[0], ordinal=1), *chunks[1:]),
        lambda prepared, chunks: (replace(chunks[0], section="Other"), *chunks[1:]),
        lambda prepared, chunks: (replace(chunks[0], chunk_id="e" * 64), *chunks[1:]),
        lambda prepared, chunks: (chunks[0], chunks[0], chunks[2]),
        lambda prepared, chunks: (object(), chunks[1], chunks[2]),
        lambda prepared, chunks: [*chunks],
    ],
)
def test_publish_rejects_mismatched_vectors_without_writing(connect, db_path, mutation):
    prepared = make_prepared()
    seed_document(db_path, prepared)
    vectors = FakeVectors()

    with pytest.raises(PublicationContractError):
        publish_revision(
            connect,
            vectors,
            prepared=prepared,
            chunks=mutation(prepared, make_vectors(prepared)),
        )

    assert vectors.upserts == []
    with connect() as db:
        assert db.execute("SELECT count(*) FROM archive_chunks").fetchone()[0] == 0
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            is None
        )


def test_publish_rejects_invalid_batch_size_before_staging(connect, db_path):
    prepared = make_prepared()
    seed_document(db_path, prepared)

    with pytest.raises(PublicationContractError):
        publish_revision(
            connect,
            FakeVectors(batch_size=0),
            prepared=prepared,
            chunks=make_vectors(prepared),
        )

    with connect() as db:
        assert db.execute("SELECT count(*) FROM archive_chunks").fetchone()[0] == 0


@pytest.mark.parametrize("limit", [0, 101, True, "1"])
def test_reconcile_rejects_unbounded_limits(connect, limit):
    with pytest.raises(PublicationContractError):
        reconcile(connect, FakeVectors(), limit=limit)


@pytest.mark.parametrize("repo_id", [0, -1, True, "42"])
def test_load_active_chunks_rejects_invalid_repository_ids(connect, repo_id):
    with pytest.raises(PublicationContractError):
        with connect() as db:
            load_active_chunks(db, repo_id)


def test_activation_refuses_a_revision_removed_after_vectors(connect, db_path):
    prepared = make_prepared()
    seed_document(db_path, prepared)
    writes = 0

    @contextmanager
    def racing_connect(write=False):
        nonlocal writes
        if write:
            writes += 1
            if writes == 2:
                with connect(write=True) as db:
                    db.execute(
                        "DELETE FROM archive_documents WHERE repo_id=? AND revision=?",
                        (prepared.repo_id, prepared.semantic_hash),
                    )
        with connect(write=write) as db:
            yield db

    with pytest.raises(PublicationContractError):
        publish_revision(
            racing_connect,
            FakeVectors(),
            prepared=prepared,
            chunks=make_vectors(prepared),
        )


def test_activation_refuses_a_revision_superseded_after_vectors(connect, db_path):
    prepared = make_prepared()
    seed_document(db_path, prepared)
    writes = 0

    @contextmanager
    def racing_connect(write=False):
        nonlocal writes
        if write:
            writes += 1
            if writes == 2:
                with connect(write=True) as db:
                    db.execute(
                        "UPDATE archive_documents SET state='superseded' "
                        "WHERE repo_id=? AND revision=?",
                        (prepared.repo_id, prepared.semantic_hash),
                    )
        with connect(write=write) as db:
            yield db

    with pytest.raises(PublicationContractError):
        publish_revision(
            racing_connect,
            FakeVectors(),
            prepared=prepared,
            chunks=make_vectors(prepared),
        )


def test_activation_refuses_published_revision_that_is_not_active(connect, db_path):
    active = make_prepared(revision="a" * 64)
    seed_document(db_path, active)
    publish_revision(
        connect, FakeVectors(), prepared=active, chunks=make_vectors(active)
    )

    candidate = make_prepared(revision="b" * 64)
    seed_document(db_path, candidate)
    writes = 0

    @contextmanager
    def racing_connect(write=False):
        nonlocal writes
        if write:
            writes += 1
            if writes == 2:
                with connect(write=True) as db:
                    db.execute(
                        "UPDATE archive_documents SET state='published' "
                        "WHERE repo_id=? AND revision=?",
                        (candidate.repo_id, candidate.semantic_hash),
                    )
        with connect(write=write) as db:
            yield db

    with pytest.raises(PublicationContractError):
        publish_revision(
            racing_connect,
            FakeVectors(),
            prepared=candidate,
            chunks=make_vectors(candidate),
        )

    with connect() as db:
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == active.semantic_hash
        )


def test_activation_refuses_a_changed_catalogue_chunk_set(connect, db_path):
    prepared = make_prepared()
    seed_document(db_path, prepared)
    writes = 0

    @contextmanager
    def racing_connect(write=False):
        nonlocal writes
        if write:
            writes += 1
            if writes == 2:
                with connect(write=True) as db:
                    db.execute(
                        "DELETE FROM archive_chunks WHERE chunk_id=?",
                        (prepared.chunks[1].chunk_id,),
                    )
        with connect(write=write) as db:
            yield db

    with pytest.raises(PublicationIncomplete):
        publish_revision(
            racing_connect,
            FakeVectors(),
            prepared=prepared,
            chunks=make_vectors(prepared),
        )


def test_reconcile_skips_a_document_that_is_no_longer_superseded(connect, db_path):
    first = make_prepared(count=1, revision="a" * 64)
    second = make_prepared(count=1, revision="b" * 64)
    seed_document(db_path, first)
    publish_revision(connect, FakeVectors(), prepared=first, chunks=make_vectors(first))
    seed_document(db_path, second)
    publish_revision(
        connect, FakeVectors(), prepared=second, chunks=make_vectors(second)
    )

    writes = 0

    @contextmanager
    def racing_connect(write=False):
        nonlocal writes
        if write:
            writes += 1
            if writes == 1:
                with connect(write=True) as db:
                    db.execute(
                        "UPDATE archive_documents SET state='pending' "
                        "WHERE repo_id=? AND revision=?",
                        (first.repo_id, first.semantic_hash),
                    )
        with connect(write=write) as db:
            yield db

    assert reconcile(racing_connect, FakeVectors()) == ReconcileResult(0, 1, 0)
    with connect() as db:
        assert (
            db.execute(
                "SELECT state FROM archive_documents WHERE revision=?",
                (first.semantic_hash,),
            ).fetchone()[0]
            == "pending"
        )


def test_reconcile_skips_a_document_that_became_active(connect, db_path):
    first = make_prepared(count=1, revision="a" * 64)
    second = make_prepared(count=1, revision="b" * 64)
    seed_document(db_path, first)
    publish_revision(connect, FakeVectors(), prepared=first, chunks=make_vectors(first))
    seed_document(db_path, second)
    publish_revision(
        connect, FakeVectors(), prepared=second, chunks=make_vectors(second)
    )

    writes = 0

    @contextmanager
    def racing_connect(write=False):
        nonlocal writes
        if write:
            writes += 1
            if writes == 1:
                with connect(write=True) as db:
                    db.execute(
                        "UPDATE archive_repositories SET active_revision=? "
                        "WHERE repo_id=?",
                        (first.semantic_hash, first.repo_id),
                    )
        with connect(write=write) as db:
            yield db

    assert reconcile(racing_connect, FakeVectors()) == ReconcileResult(0, 1, 0)
    with connect() as db:
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == first.semantic_hash
        )


def test_activation_supersedes_other_pending_revisions(connect, db_path):
    first = make_prepared(count=2, revision="a" * 64)
    seed_document(db_path, first)
    publish_revision(connect, FakeVectors(), prepared=first, chunks=make_vectors(first))

    abandoned = make_prepared(count=2, revision="b" * 64)
    seed_document(db_path, abandoned)
    writes = 0

    @contextmanager
    def failing_connect(write=False):
        nonlocal writes
        if write:
            writes += 1
            if writes == 2:
                raise sqlite3.OperationalError("synthetic activation failure")
        with connect(write=write) as db:
            yield db

    with pytest.raises(sqlite3.OperationalError):
        publish_revision(
            failing_connect,
            FakeVectors(),
            prepared=abandoned,
            chunks=make_vectors(abandoned),
        )

    current = make_prepared(count=2, revision="c" * 64)
    seed_document(db_path, current)
    publish_revision(
        connect, FakeVectors(), prepared=current, chunks=make_vectors(current)
    )

    other = make_prepared(count=1, revision="d" * 64, repo_id=REPO_ID + 1)
    seed_document(db_path, other)

    with connect() as db:
        states = dict(
            db.execute("SELECT revision, state FROM archive_documents").fetchall()
        )
        assert states[abandoned.semantic_hash] == "superseded"
        assert states[other.semantic_hash] == "pending"
        assert states[current.semantic_hash] == "published"
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == current.semantic_hash
        )

    replay = FakeVectors()
    with pytest.raises(PublicationContractError):
        publish_revision(
            connect, replay, prepared=abandoned, chunks=make_vectors(abandoned)
        )
    assert replay.upserts == []

    observed = []
    abandoned_ids = tuple(chunk.chunk_id for chunk in abandoned.chunks)
    placeholders = ",".join("?" * len(abandoned_ids))

    def inspect_delete():
        with connect() as db:
            observed.append(
                db.execute(
                    f"SELECT count(*) FROM archive_chunks WHERE chunk_id IN ({placeholders})",
                    abandoned_ids,
                ).fetchone()[0]
            )

    vectors = FakeVectors(inspect_delete=inspect_delete)
    cleaned = reconcile(connect, vectors)

    assert cleaned == ReconcileResult(2, 4, 1)
    assert observed == [2, 2]
    assert vectors.deletes == [
        (first.chunks[0].chunk_id, first.chunks[1].chunk_id),
        (abandoned.chunks[0].chunk_id, abandoned.chunks[1].chunk_id),
    ]
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM archive_documents WHERE revision=?",
                (abandoned.semantic_hash,),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM archive_chunks WHERE revision=?",
                (abandoned.semantic_hash,),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == current.semantic_hash
        )
        assert (
            db.execute(
                "SELECT state FROM archive_documents WHERE revision=?",
                (other.semantic_hash,),
            ).fetchone()[0]
            == "pending"
        )

    with pytest.raises(PublicationContractError):
        publish_revision(
            connect, FakeVectors(), prepared=abandoned, chunks=make_vectors(abandoned)
        )


def test_filter_active_hits_keeps_only_active_published_written_chunks(
    connect, db_path
):
    old = make_prepared(count=2, revision="a" * 64)
    seed_document(db_path, old)
    publish_revision(connect, FakeVectors(), prepared=old, chunks=make_vectors(old))

    active = make_prepared(count=2, revision="b" * 64)
    seed_document(db_path, active)
    publish_revision(
        connect, FakeVectors(), prepared=active, chunks=make_vectors(active)
    )

    pending = make_prepared(count=1, revision="c" * 64)
    seed_document(db_path, pending)
    stage_pending_chunks(db_path, pending, written=True)

    def hit(prepared, ordinal, **changes):
        return {
            "repo_id": prepared.repo_id,
            "revision": prepared.semantic_hash,
            "chunk_id": prepared.chunks[ordinal].chunk_id,
            "score": 0.5,
            **changes,
        }

    unknown_repo = make_prepared(count=1, revision="d" * 64, repo_id=REPO_ID + 1)
    candidates = [
        hit(old, 0),
        hit(pending, 0),
        hit(active, 0),
        {"repo_id": REPO_ID, "revision": active.semantic_hash},
        {**hit(active, 1), "repo_id": str(REPO_ID)},
        {**hit(active, 1), "repo_id": True},
        hit(active, 1, score=0.9),
        {**hit(active, 0), "chunk_id": "f" * 64},
        hit(unknown_repo, 0),
        "not-a-hit",
    ]

    with connect() as db:
        counter = CountingDB(db)
        assert filter_active_hits(counter, candidates) == [
            candidates[2],
            candidates[6],
        ]
        assert counter.queries == 2
        assert filter_active_hits(counter, []) == []
        assert counter.queries == 2
