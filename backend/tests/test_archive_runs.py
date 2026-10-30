"""Durable worker state: fake time, real transactions, no network or sleeps."""

import importlib.util
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from app.core.archive_store import APPLICATION_ID, MIGRATIONS, ArchiveStore
from app.core.config import Settings
from app.services.archive_partitions import plan_root, split_partition

DUE = datetime(2026, 10, 29, 22, tzinfo=timezone(timedelta(hours=5, minutes=30)))


class Clock:
    def __init__(self):
        self.now = DUE.timestamp()

    def __call__(self):
        return self.now


@pytest.fixture(params=["plain", "wal"])
def catalogue(request, tmp_path):
    if request.param == "wal":
        if os.name != "posix":
            pytest.skip("Real archive WAL requires a private POSIX filesystem")
        store = ArchiveStore(
            Settings(
                _env_file=None,
                database_path=str(tmp_path / "auth.db"),
                archive_database_path=tmp_path / "private/archive.db",
            )
        )
        return store.connect
    path = tmp_path / "archive.db"
    with sqlite3.connect(path) as db:
        for migration in MIGRATIONS:
            for statement in migration:
                db.execute(statement)

    @contextmanager
    def connect(*, write=False):
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            with db:
                yield db
        finally:
            db.close()

    return connect


def api():
    assert importlib.util.find_spec("app.services.archive_runs") is not None, (
        "T17 durable runs are not implemented"
    )
    from app.services import archive_runs

    return archive_runs


def test_same_due_period_has_one_run_and_one_writer(catalogue):
    runs = api()
    clock = Clock()
    one = runs.RunStore(catalogue, clock=clock)
    two = runs.RunStore(catalogue, clock=clock)
    run = one.create_run("privacy", DUE)
    assert two.create_run("privacy", DUE.astimezone(timezone.utc)) == run
    other = two.create_run("refresh", DUE)
    lease = one.claim(run, "first", ttl=30)
    for candidate in (run, other):
        with pytest.raises(runs.WriterBusy):
            two.claim(candidate, "second", ttl=30)
    one.release(lease)
    assert two.claim(other, "second", ttl=30).fence > lease.fence


def test_heartbeat_expiry_takeover_rejects_stale_writer(catalogue):
    runs = api()
    clock = Clock()
    store = runs.RunStore(catalogue, clock=clock)
    run = store.create_run("refresh", DUE)
    old = store.claim(run, "old", ttl=30)
    clock.now += 20
    store.heartbeat(old, ttl=30)
    clock.now += 10
    with pytest.raises(runs.WriterBusy):
        store.claim(run, "new", ttl=30)
    clock.now += 20
    new = store.claim(run, "new", ttl=30)
    assert new.fence > old.fence
    for action in (
        lambda: store.heartbeat(old),
        lambda: store.release(old),
        lambda: store.add_partition(old, plan_root(DUE)),
    ):
        with pytest.raises(runs.LeaseLost):
            action()
    with catalogue() as db:
        runs.check_lease(db, new)


def test_restart_mid_page_preserves_stage_and_completed_intervals(catalogue):
    runs = api()
    clock = Clock()
    store = runs.RunStore(catalogue, clock=clock)
    run = store.create_run("refresh", DUE)
    lease = store.claim(run, "old", ttl=30)
    first, second = split_partition(
        plan_root(DUE), reported_count=900, incomplete=False
    ).children
    for partition in (first, second):
        store.add_partition(lease, partition)
    store.checkpoint(lease, first.key, page=3, stage="fetch", last_repo_id=101)
    store.checkpoint(lease, second.key, page=2, stage="done", completed=True)
    clock.now += 30
    restarted = runs.RunStore(catalogue, clock=clock)
    new = restarted.claim(run, "new", ttl=30)
    saved = restarted.task(run, first.key)
    assert saved["page"] == 3 and saved["stage"] == "fetch"
    assert saved["last_repo_id"] == 101
    assert restarted.partition(run, first.key) == first
    assert restarted.completed_partitions(run) == (second,)
    restarted.checkpoint(new, first.key, page=4, stage="done", completed=True)
    assert set(restarted.completed_partitions(run)) == {first, second}
    with pytest.raises(ValueError, match="completed"):
        restarted.checkpoint(new, second.key, page=1, stage="fetch")


def test_retry_after_survives_process_lifetime(catalogue):
    runs = api()
    clock = Clock()
    store = runs.RunStore(catalogue, clock=clock)
    run = store.create_run("refresh", DUE)
    lease = store.claim(run, "old", ttl=30)
    partition = plan_root(DUE)
    store.add_partition(lease, partition)
    retry_at = clock.now + 86400
    store.defer(lease, partition.key, retry_at=retry_at)
    clock.now += 31
    restarted = runs.RunStore(catalogue, clock=clock)
    new = restarted.claim(run, "new", ttl=30)
    assert restarted.task(run, partition.key)["retry_count"] == 1
    assert restarted.task(run, partition.key)["retry_at"] == retry_at
    with pytest.raises(runs.RetryNotDue):
        restarted.checkpoint(new, partition.key, page=2, stage="fetch")
    assert restarted.completed_partitions(run) == ()
    clock.now = retry_at
    new = restarted.claim(run, "later", ttl=30)
    restarted.checkpoint(new, partition.key, page=2, stage="done", completed=True)
    assert restarted.completed_partitions(run) == (partition,)


def test_partial_checkpoint_rolls_back_without_losing_completed_work(catalogue):
    runs = api()
    store = runs.RunStore(catalogue, clock=Clock())
    lease = store.claim(store.create_run("refresh", DUE), "worker")
    first, second = split_partition(
        plan_root(DUE), reported_count=900, incomplete=False
    ).children
    for partition in (first, second):
        store.add_partition(lease, partition)
    store.checkpoint(lease, first.key, page=2, stage="done", completed=True)
    with catalogue(write=True) as db:
        db.execute(
            "CREATE TRIGGER fail_completion BEFORE UPDATE ON archive_partitions "
            "WHEN NEW.state='completed' BEGIN SELECT RAISE(ABORT,'injected'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        store.checkpoint(lease, second.key, page=4, stage="done", completed=True)
    saved = store.task(lease.run_id, second.key)
    assert saved["page"] == 1 and saved["stage"] == "discover"
    assert store.completed_partitions(lease.run_id) == (first,)


@pytest.mark.skipif(os.name != "posix", reason="Real archive WAL requires POSIX")
def test_migration_four_replays_on_existing_v3(tmp_path):
    settings = Settings(
        _env_file=None,
        database_path=str(tmp_path / "auth.db"),
        archive_database_path=tmp_path / "private/archive.db",
    )
    settings.archive_database_path.parent.mkdir(mode=0o700)
    with sqlite3.connect(settings.archive_database_path) as db:
        for migration in MIGRATIONS[:3]:
            for statement in migration:
                db.execute(statement)
        db.execute(f"PRAGMA application_id={APPLICATION_ID}")
        db.execute("PRAGMA user_version=3")
        db.execute("INSERT INTO archive_suppressions VALUES(99,'not_found',1)")
        db.execute(
            "INSERT INTO archive_repositories(repo_id,full_name) VALUES(42,'a/b')"
        )
    settings.archive_database_path.chmod(0o600)
    store = ArchiveStore(settings)
    store.migrate()
    with store.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4
        assert (
            db.execute("SELECT repo_id FROM archive_repositories").fetchone()[0] == 42
        )
        assert (
            db.execute("SELECT repo_id FROM archive_suppressions").fetchone()[0] == 99
        )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_parent_cannot_claim_coverage_before_children_finish(catalogue):
    runs = api()
    store = runs.RunStore(catalogue, clock=Clock())
    lease = store.claim(store.create_run("refresh", DUE), "worker")
    parent = plan_root(DUE)
    children = split_partition(parent, reported_count=900, incomplete=False).children
    store.add_partition(lease, parent)
    store.add_split(
        lease, split_partition(parent, reported_count=900, incomplete=False)
    )
    with pytest.raises(ValueError, match="children"):
        store.checkpoint(lease, parent.key, page=1, stage="done", completed=True)
    assert store.completed_partitions(lease.run_id) == ()
    for child in children:
        store.checkpoint(lease, child.key, page=2, stage="done", completed=True)
    store.checkpoint(lease, parent.key, page=1, stage="done", completed=True)
    with pytest.raises(ValueError, match="completed"):
        store.add_split(
            lease, split_partition(parent, reported_count=900, incomplete=False)
        )


def test_completed_run_cannot_be_reclaimed_or_extended(catalogue):
    runs = api()
    store = runs.RunStore(catalogue, clock=Clock())
    run = store.create_run("refresh", DUE)
    lease = store.claim(run, "worker")
    partition = plan_root(DUE)
    store.add_partition(lease, partition)
    store.add_partition(lease, partition)
    with pytest.raises(ValueError, match="incomplete"):
        store.release(lease, completed=True)
    store.checkpoint(lease, partition.key, page=1, stage="done", completed=True)
    store.release(lease, completed=True)
    assert store.create_run("refresh", DUE) == run
    with pytest.raises(ValueError, match="completed"):
        store.claim(run, "again")
    with pytest.raises(runs.LeaseLost):
        store.add_partition(lease, partition)


def test_old_run_cannot_revive_after_clock_moves_backwards(catalogue):
    runs = api()
    clock = Clock()
    store = runs.RunStore(catalogue, clock=clock)
    old = store.claim(store.create_run("refresh", DUE), "old", ttl=10)
    clock.now += 10
    new = store.claim(store.create_run("privacy", DUE), "new", ttl=10)
    clock.now -= 10
    with catalogue() as db:
        with pytest.raises(runs.LeaseLost):
            runs.check_lease(db, old)
        runs.check_lease(db, new)


@pytest.mark.parametrize("bad", [0, -1, 3601, True, 1.5])
def test_invalid_lease_duration_is_rejected(catalogue, bad):
    store = api().RunStore(catalogue, clock=Clock())
    run = store.create_run("refresh", DUE)
    with pytest.raises(ValueError):
        store.claim(run, "worker", ttl=bad)


def test_invalid_inputs_do_not_change_checkpoint(catalogue):
    runs = api()
    store = runs.RunStore(catalogue, clock=Clock())
    with pytest.raises(ValueError):
        store.create_run("", DUE)
    with pytest.raises(ValueError):
        store.create_run("refresh", DUE.replace(tzinfo=None))
    with pytest.raises(ValueError):
        store.claim(999, "worker")
    lease = store.claim(store.create_run("refresh", DUE), "worker")
    partition = plan_root(DUE)
    with pytest.raises(TypeError):
        store.add_partition(lease, {})
    with pytest.raises(ValueError):
        store.add_split(lease, {})
    store.add_partition(lease, partition)
    for kwargs in (
        {"page": 0},
        {"page": 11},
        {"page": True},
        {"stage": ""},
        {"last_repo_id": -1},
        {"completed": 1},
    ):
        args = {"page": 2, "stage": "fetch", **kwargs}
        with pytest.raises(ValueError):
            store.checkpoint(lease, partition.key, **args)
    for retry_at in (-1, float("nan"), float("inf"), True, lease.clock()):
        with pytest.raises(ValueError):
            store.defer(lease, partition.key, retry_at=retry_at)
    with pytest.raises(ValueError):
        store.release(lease, completed=1)
    with pytest.raises(ValueError):
        store.partition(lease.run_id, "missing")
    with pytest.raises(ValueError):
        store.task(lease.run_id, "missing")
    assert store.task(lease.run_id, partition.key)["page"] == 1
    assert store.task(lease.run_id, partition.key)["retry_count"] == 0


def test_split_registration_is_atomic_and_cannot_hide_a_missing_sibling(catalogue):
    runs = api()
    store = runs.RunStore(catalogue, clock=Clock())
    lease = store.claim(store.create_run("refresh", DUE), "worker")
    parent = plan_root(DUE)
    split = split_partition(parent, reported_count=900, incomplete=False)
    store.add_partition(lease, parent)
    assert hasattr(store, "add_split"), "split registration must be atomic"
    with catalogue(write=True) as db:
        db.execute(
            "CREATE TRIGGER fail_child BEFORE INSERT ON archive_partitions "
            "WHEN NEW.partition_key='" + split.children[1].key + "' "
            "BEGIN SELECT RAISE(ABORT,'injected'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        store.add_split(lease, split)
    with catalogue() as db:
        assert db.execute("SELECT count(*) FROM archive_partitions").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM archive_tasks").fetchone()[0] == 1
    with catalogue(write=True) as db:
        db.execute("DROP TRIGGER fail_child")
    store.add_split(lease, split)
    store.add_split(lease, split)
    store.checkpoint(lease, split.children[0].key, page=1, stage="done", completed=True)
    with pytest.raises(ValueError, match="children"):
        store.checkpoint(lease, parent.key, page=1, stage="done", completed=True)
    assert store.completed_partitions(lease.run_id) == (split.children[0],)
