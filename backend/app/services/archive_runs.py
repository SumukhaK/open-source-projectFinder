"""Durable discovery checkpoints and one fenced writer per local catalogue."""

import json
import math
import os
import stat
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.config import ARCHIVE_LEASE_MAX_SECONDS, ARCHIVE_LEASE_SECONDS

from .archive_partitions import DiscoveryPartition, PartitionSplit, split_partition


class WriterBusy(RuntimeError):
    pass


class LeaseLost(RuntimeError):
    pass


class RetryNotDue(RuntimeError):
    pass


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise ValueError(f"{name} must be nonempty text of at most 64 characters")
    return value


def _seconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("time must be a finite nonnegative number")
    return value


def _ttl(value):
    if type(value) is not int or not 1 <= value <= ARCHIVE_LEASE_MAX_SECONDS:
        raise ValueError("lease TTL must be 1..3600 seconds")
    return value


@dataclass(frozen=True)
class Lease:
    run_id: int
    owner: str
    fence: int
    clock: object = field(default=time.time, repr=False, compare=False)


def check_lease(db, lease):
    """Check in the same transaction as the protected catalogue mutation."""
    if not isinstance(lease, Lease):
        raise LeaseLost("a writer lease is required")
    row = db.execute(
        "SELECT owner, fence, expires_at FROM archive_runs WHERE run_id=?",
        (lease.run_id,),
    ).fetchone()
    if (
        row is None
        or row[0] != lease.owner
        or row[1] != lease.fence
        or row[2] is None
        or row[2] <= _seconds(lease.clock())
    ):
        raise LeaseLost(
            "writer lease expired or was replaced; reacquire before resuming"
        )


class RunStore:
    def __init__(self, connect, *, clock=time.time):
        self.connect = connect
        self.clock = clock

    def create_run(self, kind, due_at):
        """The scheduled instant, not the catch-up launch time, identifies a run."""
        _text(kind, "kind")
        if not isinstance(due_at, datetime) or due_at.utcoffset() is None:
            raise ValueError("due_at must be timezone aware")
        return self._create(kind, due_at.astimezone(timezone.utc).isoformat())

    def _create(self, kind, period):
        with self.connect(write=True) as db:
            db.execute(
                "INSERT INTO archive_runs(kind,due_period) VALUES (?,?) "
                "ON CONFLICT(kind,due_period) DO NOTHING",
                (kind, period),
            )
            return db.execute(
                "SELECT run_id FROM archive_runs WHERE kind=? AND due_period=?",
                (kind, period),
            ).fetchone()[0]

    def claim(self, run_id, owner, *, ttl=ARCHIVE_LEASE_SECONDS):
        _text(owner, "owner")
        now = _seconds(self.clock())
        expiry = now + _ttl(ttl)
        with self.connect(write=True) as db:
            row = db.execute(
                "SELECT completed FROM archive_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None or row[0]:
                raise ValueError("run is missing or completed")
            if db.execute(
                "SELECT 1 FROM archive_runs WHERE expires_at>?", (now,)
            ).fetchone():
                raise WriterBusy("another catalogue writer owns a live lease")
            db.execute(
                "UPDATE archive_runs SET owner=NULL,expires_at=NULL WHERE expires_at IS NOT NULL"
            )
            # Retain run rows: MAX is the durable catalogue-wide fencing sequence.
            fence = db.execute(
                "SELECT COALESCE(MAX(fence),0)+1 FROM archive_runs"
            ).fetchone()[0]
            db.execute(
                "UPDATE archive_runs SET owner=?,fence=?,heartbeat_at=?,expires_at=? "
                "WHERE run_id=?",
                (owner, fence, now, expiry, run_id),
            )
        return Lease(run_id, owner, fence, self.clock)

    def heartbeat(self, lease, *, ttl=ARCHIVE_LEASE_SECONDS):
        duration = _ttl(ttl)
        with self.connect(write=True) as db:
            check_lease(db, lease)
            now = _seconds(self.clock())
            db.execute(
                "UPDATE archive_runs SET heartbeat_at=?,expires_at=? WHERE run_id=?",
                (now, now + duration, lease.run_id),
            )

    def release(self, lease, *, completed=False):
        if type(completed) is not bool:
            raise ValueError("completed must be boolean")
        with self.connect(write=True) as db:
            check_lease(db, lease)
            if (
                completed
                and db.execute(
                    "SELECT 1 FROM archive_partitions WHERE run_id=? AND state<>'completed'",
                    (lease.run_id,),
                ).fetchone()
            ):
                raise ValueError("run still has incomplete partitions")
            db.execute(
                "UPDATE archive_runs SET owner=NULL,expires_at=NULL,completed=? WHERE run_id=?",
                (int(completed), lease.run_id),
            )

    def add_partition(self, lease, partition):
        if not isinstance(partition, DiscoveryPartition):
            raise TypeError("partition must be a DiscoveryPartition")
        with self.connect(write=True) as db:
            check_lease(db, lease)
            self._insert_partition(db, lease.run_id, partition)

    def add_split(self, lease, split):
        if (
            not isinstance(split, PartitionSplit)
            or split.parent is None
            or not split.children
        ):
            raise ValueError("a resolved partition split is required")
        expected = split_partition(
            split.parent, reported_count=0, incomplete=True, max_depth=split.max_depth
        )
        if split != expected:
            raise ValueError("split must contain the complete T16 child set")
        with self.connect(write=True) as db:
            self._pending(db, lease, split.parent.key)
            for child in split.children:
                self._insert_partition(db, lease.run_id, child, split.parent.key)

    @staticmethod
    def _insert_partition(db, run_id, partition, parent_key=None):
        record = json.dumps(partition.as_record(parent_key), sort_keys=True)
        db.execute(
            "INSERT INTO archive_partitions(run_id,partition_key,record) VALUES(?,?,?) "
            "ON CONFLICT DO NOTHING",
            (run_id, partition.key, record),
        )
        saved = db.execute(
            "SELECT record FROM archive_partitions WHERE run_id=? AND partition_key=?",
            (run_id, partition.key),
        ).fetchone()[0]
        if saved != record:
            raise ValueError("partition record conflicts with its persisted identity")
        db.execute(
            "INSERT INTO archive_tasks(run_id,partition_key) VALUES(?,?) "
            "ON CONFLICT DO NOTHING",
            (run_id, partition.key),
        )

    def partition(self, run_id, key):
        with self.connect() as db:
            row = db.execute(
                "SELECT record FROM archive_partitions WHERE run_id=? AND partition_key=?",
                (run_id, key),
            ).fetchone()
            if row is None:
                raise ValueError("partition is missing")
            return DiscoveryPartition.from_record(json.loads(row[0]))

    def task(self, run_id, key):
        with self.connect() as db:
            return dict(self._task(db, run_id, key))

    @staticmethod
    def _task(db, run_id, key):
        row = db.execute(
            "SELECT t.*, p.state FROM archive_tasks t JOIN archive_partitions p "
            "USING(run_id,partition_key) WHERE run_id=? AND partition_key=?",
            (run_id, key),
        ).fetchone()
        if row is None:
            raise ValueError("partition task is missing")
        return row

    def _pending(self, db, lease, key):
        check_lease(db, lease)
        row = self._task(db, lease.run_id, key)
        if row["state"] == "completed":
            raise ValueError("completed partitions cannot be reopened")
        if row["retry_at"] is not None and row["retry_at"] > lease.clock():
            raise RetryNotDue("partition retry is not due")
        return row

    def checkpoint(
        self, lease, key, *, page, stage, last_repo_id=None, completed=False
    ):
        _text(stage, "stage")
        if type(page) is not int or not 1 <= page <= 10:
            raise ValueError("page must be 1..10")
        if last_repo_id is not None and (
            type(last_repo_id) is not int or last_repo_id <= 0
        ):
            raise ValueError("repository ID must be positive")
        if type(completed) is not bool:
            raise ValueError("completed must be boolean")
        with self.connect(write=True) as db:
            self._pending(db, lease, key)
            if (
                completed
                and db.execute(
                    "SELECT 1 FROM archive_partitions WHERE run_id=? "
                    "AND json_extract(record,'$.parent_key')=? AND state<>'completed'",
                    (lease.run_id, key),
                ).fetchone()
            ):
                raise ValueError("partition has incomplete children")
            db.execute(
                "UPDATE archive_tasks SET page=?,stage=?,last_repo_id=?,retry_at=NULL "
                "WHERE run_id=? AND partition_key=?",
                (page, stage, last_repo_id, lease.run_id, key),
            )
            if completed:
                db.execute(
                    "UPDATE archive_partitions SET state='completed' WHERE run_id=? AND partition_key=?",
                    (lease.run_id, key),
                )

    def defer(self, lease, key, *, retry_at):
        _seconds(retry_at)
        with self.connect(write=True) as db:
            self._pending(db, lease, key)
            if retry_at <= lease.clock():
                raise ValueError("retry_at must be in the future")
            db.execute(
                "UPDATE archive_tasks SET retry_count=retry_count+1,retry_at=? "
                "WHERE run_id=? AND partition_key=?",
                (retry_at, lease.run_id, key),
            )

    def completed_partitions(self, run_id):
        """Typed completed intervals retain gaps and secondary-range restrictions."""
        with self.connect() as db:
            return tuple(
                DiscoveryPartition.from_record(json.loads(row[0]))
                for row in db.execute(
                    "SELECT record FROM archive_partitions WHERE run_id=? AND state='completed' "
                    "ORDER BY partition_key",
                    (run_id,),
                )
            )


@contextmanager
def _operation_lock(connect):
    # A lease cannot cancel in-flight Milvus IO. This OS lock serializes those
    # calls across takeover, without holding a SQLite transaction over IO.
    with connect() as db:
        path = db.execute("PRAGMA database_list").fetchone()[2]
    if not path:
        raise ValueError("writer operations require a file-backed catalogue")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path + ".writer.lock", flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PermissionError("writer lock must be a private regular file")
        if os.name == "posix":
            import fcntl

            if info.st_mode & 0o077:
                raise PermissionError("writer lock must be private (0600)")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise WriterBusy(
                    "another vector operation is still in flight"
                ) from error
        else:
            # Windows supports the SQL unit fixtures; production remains POSIX.
            import msvcrt

            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise WriterBusy(
                    "another vector operation is still in flight"
                ) from error
        yield
    finally:
        os.close(fd)


@contextmanager
def publication_writer(connect, lease=None):
    """Use a durable fence, including for the existing single-repository CLI."""
    with _operation_lock(connect):
        temporary = lease is None
        store = RunStore(connect)
        if temporary:
            owner = uuid.uuid4().hex
            run_id = store._create("manual", owner)
            lease = store.claim(run_id, owner)
        with connect() as db:
            check_lease(db, lease)
        try:
            yield lease
        finally:
            if temporary:
                try:
                    store.release(lease, completed=True)
                except LeaseLost:
                    # Never release a successor's lease or hide the original failure.
                    pass
