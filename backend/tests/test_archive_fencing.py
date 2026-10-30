"""Lease loss during vector operations must never authorize catalogue changes."""

import pytest
from app.services.archive_publication import (
    _activate,
    filter_active_hits,
    publish_revision,
    reconcile,
)
from app.services.archive_runs import LeaseLost, RunStore, WriterBusy
from test_archive_publication import (
    REPO_ID,
    FakeVectors,
    make_prepared,
    make_vectors,
    seed_document,
)
from test_archive_publication import (
    connect as connect,
)
from test_archive_publication import (
    db_path as db_path,
)
from test_archive_runs import DUE, Clock


def test_unfenced_t09_cannot_bypass_an_active_writer(connect, db_path):
    store = RunStore(connect, clock=Clock())
    # Use current real time for this particular compatibility boundary.
    import time

    store.clock = time.time
    lease = store.claim(store.create_run("refresh", DUE), "worker")
    prepared = make_prepared()
    seed_document(db_path, prepared)
    vectors = FakeVectors()
    with pytest.raises(WriterBusy):
        publish_revision(
            connect, vectors, prepared=prepared, chunks=make_vectors(prepared)
        )
    assert vectors.upserts == []
    store.release(lease)
    publish_revision(connect, vectors, prepared=prepared, chunks=make_vectors(prepared))


def test_late_vector_write_cannot_activate_after_takeover(connect, db_path):
    current = make_prepared(count=1, revision="c" * 64)
    old = make_prepared(count=1, revision="a" * 64)
    new = make_prepared(count=1, revision="b" * 64)
    seed_document(db_path, current)
    publish_revision(
        connect, FakeVectors(), prepared=current, chunks=make_vectors(current)
    )
    for prepared in (old, new):
        seed_document(db_path, prepared)
    clock = Clock()
    store = RunStore(connect, clock=clock)
    run = store.create_run("refresh", DUE)
    stale = store.claim(run, "old", ttl=10)
    taken = []

    def takeover():
        clock.now += 10
        taken.append(store.claim(run, "new", ttl=30))
        with pytest.raises(WriterBusy):
            publish_revision(
                connect,
                FakeVectors(),
                prepared=new,
                chunks=make_vectors(new),
                lease=taken[0],
            )

    vectors = FakeVectors(inspect_upsert=takeover)
    with pytest.raises(LeaseLost):
        publish_revision(
            connect, vectors, prepared=old, chunks=make_vectors(old), lease=stale
        )
    assert len(vectors.upserts) == 1
    with connect() as db:
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == current.semantic_hash
        )
        assert (
            filter_active_hits(
                db,
                [
                    {
                        "repo_id": REPO_ID,
                        "revision": old.semantic_hash,
                        "chunk_id": old.chunks[0].chunk_id,
                    }
                ],
            )
            == []
        )
    with pytest.raises(LeaseLost):
        _activate(connect, old, lease=stale)
    publish_revision(
        connect, FakeVectors(), prepared=new, chunks=make_vectors(new), lease=taken[0]
    )
    with connect() as db:
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == new.semantic_hash
        )
        assert (
            db.execute(
                "SELECT count(*) FROM archive_documents WHERE state='published'"
            ).fetchone()[0]
            == 1
        )


def test_stale_cleanup_is_rejected_before_vector_deletion(connect, db_path):
    clock = Clock()
    store = RunStore(connect, clock=clock)
    run = store.create_run("refresh", DUE)
    old = store.claim(run, "old", ttl=10)
    clock.now += 10
    store.claim(run, "new")
    vectors = FakeVectors()
    with pytest.raises(LeaseLost):
        reconcile(connect, vectors, lease=old)
    assert vectors.deletes == []


def test_cleanup_in_flight_blocks_activation_and_fences_catalogue_delete(
    connect, db_path
):
    old = make_prepared(count=1)
    current = make_prepared(count=1, revision="b" * 64)
    for prepared in (old, current):
        seed_document(db_path, prepared)
        publish_revision(
            connect, FakeVectors(), prepared=prepared, chunks=make_vectors(prepared)
        )
    clock = Clock()
    store = RunStore(connect, clock=clock)
    run = store.create_run("refresh", DUE)
    stale = store.claim(run, "old", ttl=10)
    taken = []

    def takeover():
        clock.now += 10
        taken.append(store.claim(run, "new", ttl=30))
        with pytest.raises(WriterBusy):
            publish_revision(
                connect,
                FakeVectors(),
                prepared=current,
                chunks=make_vectors(current),
                lease=taken[0],
            )

    vectors = FakeVectors(inspect_delete=takeover)
    with pytest.raises(LeaseLost):
        reconcile(connect, vectors, lease=stale)
    assert vectors.deletes == [(old.chunks[0].chunk_id,)]
    with connect() as db:
        assert db.execute("SELECT count(*) FROM archive_documents").fetchone()[0] == 2
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == current.semantic_hash
        )
    assert reconcile(connect, FakeVectors(), lease=taken[0]).documents == 1


def _hold_operation_lock(path, channel):
    import sqlite3
    from contextlib import contextmanager

    from app.services.archive_runs import _operation_lock

    @contextmanager
    def connect():
        db = sqlite3.connect(path)
        try:
            yield db
        finally:
            db.close()

    with _operation_lock(connect):
        channel.send("locked")
        channel.recv()


def test_operation_lock_serializes_processes_and_releases_on_exit(connect, db_path):
    import multiprocessing

    from app.services.archive_runs import _operation_lock

    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=_hold_operation_lock, args=(str(db_path), child))
    process.start()
    try:
        assert parent.poll(15), "child did not acquire the operation lock"
        assert parent.recv() == "locked"
        with pytest.raises(WriterBusy):
            with _operation_lock(connect):
                pytest.fail("two vector operations acquired the same lock")
        parent.send("release")
        process.join(15)
        assert process.exitcode == 0
        with _operation_lock(connect):
            pass
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
        parent.close()
        child.close()


def test_temporary_lease_cannot_activate_after_its_expiry(
    connect, db_path, monkeypatch
):
    from app.services import archive_runs

    clock = Clock()
    factory = archive_runs.RunStore
    monkeypatch.setattr(archive_runs, "RunStore", lambda db: factory(db, clock=clock))
    prepared = make_prepared(count=1)
    seed_document(db_path, prepared)

    def expire():
        clock.now += 3601

    with pytest.raises(LeaseLost):
        publish_revision(
            connect,
            FakeVectors(inspect_upsert=expire),
            prepared=prepared,
            chunks=make_vectors(prepared),
        )
    with connect() as db:
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            is None
        )
    publish_revision(
        connect, FakeVectors(), prepared=prepared, chunks=make_vectors(prepared)
    )


def test_ambiguous_delete_prevents_reusing_ids_targeted_by_a_late_rpc(connect, db_path):
    from app.integrations.milvus import MilvusUnavailable
    from app.services.archive_publication import PublicationIncomplete

    old = make_prepared(count=1)
    current = make_prepared(count=1, revision="b" * 64)
    for prepared in (old, current):
        seed_document(db_path, prepared)
        publish_revision(
            connect, FakeVectors(), prepared=prepared, chunks=make_vectors(prepared)
        )
    # The server may still apply the first delete after the caller times out.
    with pytest.raises(MilvusUnavailable):
        reconcile(connect, FakeVectors(fail_delete_batch=0))
    assert reconcile(connect, FakeVectors()).documents == 1
    seed_document(db_path, old)
    vectors = FakeVectors()
    with pytest.raises(PublicationIncomplete, match="quarantined"):
        publish_revision(connect, vectors, prepared=old, chunks=make_vectors(old))
    assert vectors.upserts == []
    with connect() as db:
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == current.semantic_hash
        )


@pytest.mark.parametrize("already_active", [False, True])
def test_late_upsert_can_only_replay_identical_vector_payload(
    connect, db_path, already_active
):
    from dataclasses import replace

    from app.integrations.milvus import MilvusUnavailable
    from app.services.archive_publication import PublicationIncomplete

    prepared = make_prepared(count=1)
    seed_document(db_path, prepared)
    original = make_vectors(prepared)
    if already_active:
        publish_revision(connect, FakeVectors(), prepared=prepared, chunks=original)
    with pytest.raises(MilvusUnavailable):
        publish_revision(
            connect,
            FakeVectors(fail_upsert_batch=0),
            prepared=prepared,
            chunks=original,
        )
    changed = (
        replace(original[0], license="Apache-2.0", pushed_at=original[0].pushed_at + 1),
    )
    vectors = FakeVectors()
    with pytest.raises(PublicationIncomplete, match="payload"):
        publish_revision(connect, vectors, prepared=prepared, chunks=changed)
    assert vectors.upserts == []
    # A late write of the original bytes is harmless to an identical replay.
    publish_revision(connect, FakeVectors(), prepared=prepared, chunks=original)
    with connect() as db:
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == prepared.semantic_hash
        )


def test_uncertain_upsert_stays_quarantined_after_cleanup(connect, db_path):
    from app.integrations.milvus import MilvusUnavailable
    from app.services.archive_publication import PublicationIncomplete

    old = make_prepared(count=1)
    newer = make_prepared(count=1, revision="b" * 64)
    seed_document(db_path, old)
    with pytest.raises(MilvusUnavailable):
        publish_revision(
            connect,
            FakeVectors(fail_upsert_batch=0),
            prepared=old,
            chunks=make_vectors(old),
        )
    publish_revision(connect, FakeVectors(), prepared=old, chunks=make_vectors(old))
    seed_document(db_path, newer)
    publish_revision(connect, FakeVectors(), prepared=newer, chunks=make_vectors(newer))
    reconcile(connect, FakeVectors())
    seed_document(db_path, old)
    with pytest.raises(PublicationIncomplete, match="quarantined"):
        publish_revision(connect, FakeVectors(), prepared=old, chunks=make_vectors(old))


def test_activation_requires_the_staged_payload_even_with_current_lease(
    connect, db_path
):
    from app.services.archive_publication import PublicationIncomplete

    prepared = make_prepared(count=1)
    seed_document(db_path, prepared)
    store = RunStore(connect, clock=Clock())
    lease = store.claim(store.create_run("refresh", DUE), "worker")
    with pytest.raises(PublicationIncomplete, match="staged vector payload"):
        _activate(connect, prepared, lease=lease)
    with connect() as db:
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            is None
        )


def test_successful_cleanup_also_prevents_retired_id_reuse(connect, db_path):
    from app.services.archive_publication import PublicationIncomplete

    old = make_prepared(count=1)
    current = make_prepared(count=1, revision="b" * 64)
    for prepared in (old, current):
        seed_document(db_path, prepared)
        publish_revision(
            connect, FakeVectors(), prepared=prepared, chunks=make_vectors(prepared)
        )
    reconcile(connect, FakeVectors())
    seed_document(db_path, old)
    with pytest.raises(PublicationIncomplete, match="quarantined"):
        publish_revision(connect, FakeVectors(), prepared=old, chunks=make_vectors(old))
