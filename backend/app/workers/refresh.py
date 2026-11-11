"""T19b's manual weekly refresh: known IDs, recent discovery and a sweep.

The refresh is a local operator command, never an API scheduler. One run is
identified by the most recent Saturday 22:00 UTC boundary and resumes in place.
It reconciles every known repository, discovers new repositories from the last
completed boundary minus a 48-hour overlap, and sweeps one rotating 28-day
slice of the rolling 365-day window. Conditional reads reuse cached bodies, so
unchanged content makes no embedding calls.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timedelta, timezone

from app.integrations.archive_github import (
    ArchiveAuthenticationError,
    ArchiveForbidden,
    ArchiveProtocolError,
    ArchiveRateLimited,
    ArchiveRequestError,
    ArchiveUnavailable,
    BlobIdentityMismatch,
    BlobNotFound,
    RepositoryIdentityMismatch,
    RepositoryNotFound,
    RepositoryNotPublic,
)
from app.integrations.milvus import MilvusOperationError, MilvusUnavailable
from app.services.archive_partitions import (
    DiscoveryPartition,
    needs_split,
    split_partition,
)
from app.services.archive_publication import RevisionSuperseded, reconcile
from app.services.archive_runs import LeaseLost, RunStore
from app.workers.archive import (
    IneligibleRepository,
    IngestError,
    ingest_one,
    load_cached_repository,
)

RECENT_OVERLAP = timedelta(hours=48)
SWEEP_DAYS = 28
SWEEP_BUCKETS = 14
_WEEK = timedelta(days=7)


def due_boundary(now):
    """Return the most recent Saturday 22:00 UTC instant at or before ``now``."""
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("refresh time must be timezone-aware")
    moment = now.astimezone(timezone.utc)
    days_since_saturday = (moment.weekday() - 5) % 7
    boundary = (moment - timedelta(days=days_since_saturday)).replace(
        hour=22, minute=0, second=0, microsecond=0
    )
    if boundary > moment:
        boundary -= _WEEK
    return boundary


class Refresh:
    """One manual weekly refresh, resumable by its stable due boundary."""

    def __init__(self, runtime, *, clock, disk_free=None):
        self.runtime = runtime
        self.clock = clock
        self.disk_free = disk_free or self._free_disk
        self.store = RunStore(runtime.connect, clock=clock)
        self.requests = {"search": 0, "rest": 0}
        self.bytes = 0
        self.known_ids = 0
        self.discovered = set()
        self._run_id = None
        self._lease = None
        self._stop = None
        self._retry_at = None

    def _free_disk(self):
        return min(
            shutil.disk_usage(self.runtime.settings.archive_database_path.parent).free,
            shutil.disk_usage(self.runtime.content.root).free,
        )

    def run(self, *, sweep_buckets=1):
        if type(sweep_buckets) is not int or not 1 <= sweep_buckets <= SWEEP_BUCKETS:
            raise ValueError(
                f"--sweep-buckets must be an integer from 1 through {SWEEP_BUCKETS}"
            )
        due = due_boundary(datetime.fromtimestamp(self.clock(), timezone.utc))
        run_id = self.store.create_run("refresh", due)
        self._run_id, self._stop, self._retry_at = run_id, None, None
        state = self._state(run_id)
        self.bytes = int(state.get("bytes") or 0)
        self.known_ids = self._count_repositories()
        self.discovered = set()
        saved = state.get("requests") or {}
        self.requests = {
            "search": int(saved.get("search") or 0),
            "rest": int(saved.get("rest") or 0),
        }
        with self.runtime.connect() as db:
            already_done = db.execute(
                "SELECT completed FROM archive_runs WHERE run_id=?", (run_id,)
            ).fetchone()[0]
        if already_done:
            return self._summary(run_id, "finished", None, due, sweep_buckets)
        retry_at = state.get("retry_at")
        if retry_at and retry_at > self.clock():
            return self._summary(run_id, "rate_limit", retry_at, due, sweep_buckets)
        if retry_at:
            self._save_state(run_id, {"retry_at": None})
        if self.bytes > self.runtime.settings.archive_backfill_byte_limit:
            return self._summary(run_id, "bytes", None, due, sweep_buckets)

        lease = self.store.claim(run_id, uuid.uuid4().hex)
        self._lease = lease
        reader = self.runtime.reader
        reader.observer = self
        self._save_state(run_id, {"last_attempt_at": self.clock()})
        try:
            index = self._sweep_index(run_id, state)
            previous = self._previous_boundary(run_id, due)
            self._known_ids(run_id, lease, due)
            if not self._stop:
                recent = DiscoveryPartition(previous - RECENT_OVERLAP, due)
                self._discover_and_ingest(run_id, lease, recent, due)
            for offset in range(sweep_buckets):
                if self._stop:
                    break
                bucket = self._sweep_bucket(due, index + offset)
                self._discover_and_ingest(run_id, lease, bucket, due)
            if not self._stop and self._unresolved(run_id):
                self._stop = "incomplete"
            completed = not self._stop
            if completed:
                self._save_state(
                    run_id,
                    {
                        "last_complete_at": self.clock(),
                        "last_completed_boundary": due.isoformat(),
                        "sweep_index": (index + sweep_buckets) % SWEEP_BUCKETS,
                    },
                )
            self.store.release(lease, completed=completed)
            return self._summary(
                run_id,
                "finished" if completed else (self._stop or "incomplete"),
                self._retry_at,
                due,
                sweep_buckets,
            )
        except ArchiveAuthenticationError:
            self._stop = "credential"
            self.store.release(lease)
            return self._summary(run_id, "credential", None, due, sweep_buckets)
        except (ArchiveRateLimited, ArchiveUnavailable) as error:
            retry = self._retry_at or (
                error.retry_at.timestamp()
                if error.retry_at is not None
                else self.clock() + 60
            )
            self._save_state(run_id, {"retry_at": retry})
            self.store.release(lease)
            return self._summary(
                run_id, self._stop or "rate_limit", retry, due, sweep_buckets
            )
        finally:
            reader.observer = None

    # The reader calls these around every actual HTTP request. They use server
    # headers, never guessed quotas, and preserve independent buckets.
    def before_request(self, path):
        if self._stop:
            raise ArchiveUnavailable("refresh budget reached")
        self.store.heartbeat(self._lease)
        if self.disk_free() < self.runtime.settings.archive_min_free_bytes:
            self._stop = "disk"
            raise ArchiveUnavailable("disk bound reached")
        bucket = "search" if path == "/search/repositories" else "rest"
        self.requests[bucket] += 1

    def after_response(self, response):
        self.bytes += response.encoded_bytes
        state = {"bytes": self.bytes, "requests": dict(self.requests)}
        if self.bytes > self.runtime.settings.archive_backfill_byte_limit:
            self._stop = "bytes"
        remaining = response.headers.get("x-ratelimit-remaining")
        limit = response.headers.get("x-ratelimit-limit")
        reset = response.headers.get("x-ratelimit-reset")
        if remaining is not None and limit is not None:
            try:
                low = int(remaining) <= max(1, int(limit) // 5)
                retry_at = float(reset) if reset is not None else self.clock() + 60
                if not retry_at > self.clock():
                    retry_at = self.clock() + 60
            except (TypeError, ValueError):
                low, retry_at = True, self.clock() + 60
            if low:
                self._stop = "quota"
                self._retry_at = retry_at
                state["retry_at"] = retry_at
        self._save_state(self._run_id, state)

    def _known_ids(self, run_id, lease, due):
        with self.runtime.connect() as db:
            repo_ids = [
                row[0]
                for row in db.execute(
                    "SELECT repo_id FROM archive_repositories ORDER BY repo_id"
                )
            ]
        for repo_id in repo_ids:
            if self._stop:
                return
            if self._claim_repo(run_id, repo_id):
                self._ingest_repo(run_id, lease, repo_id, boundary=due)

    def _discover_and_ingest(self, run_id, lease, partition, due):
        for repo_id in self._discover(partition):
            if self._stop:
                return
            if self._claim_repo(run_id, repo_id):
                self._ingest_repo(run_id, lease, repo_id, boundary=due)

    def _discover(self, partition):
        ids, seen = [], set()
        self._walk(partition, ids, seen)
        self.discovered.update(ids)
        return ids

    def _count_repositories(self):
        with self.runtime.connect() as db:
            return db.execute("SELECT count(*) FROM archive_repositories").fetchone()[0]

    def _walk(self, partition, ids, seen):
        if self._stop:
            return
        result = self.runtime.reader.search_repositories(partition.query, page=1)
        if needs_split(result.total_count, result.incomplete):
            split = split_partition(
                partition,
                reported_count=result.total_count,
                incomplete=result.incomplete,
            )
            if split.unresolved:
                self._stop = "partition"
                return
            for child in split.children:
                if self._stop:
                    return
                self._walk(child, ids, seen)
            return
        page = 1
        while True:
            for repo_id in result.ids:
                if repo_id not in seen:
                    seen.add(repo_id)
                    ids.append(repo_id)
            if len(result.ids) < 100 or page >= 10 or page * 100 >= result.total_count:
                return
            page += 1
            result = self.runtime.reader.search_repositories(partition.query, page=page)

    def _ingest_repo(self, run_id, lease, repo_id, *, boundary):
        for attempt in range(2):
            cached = load_cached_repository(
                self.runtime.connect, self.runtime.content, repo_id
            )
            try:
                result = ingest_one(
                    self.runtime,
                    repo_id,
                    now=boundary,
                    lease=lease,
                    cached=cached,
                )
            except RevisionSuperseded:
                if attempt == 0 and self._reconcile(lease):
                    continue
                self._outcome(run_id, repo_id, "pending", "superseded")
                if attempt:
                    self._stop = "incomplete"
                return
            except IneligibleRepository as error:
                reason = (
                    "licence" if error.reason.startswith("license") else error.reason
                )
                if reason == "not_public":
                    reason = "private"
                self._outcome(run_id, repo_id, "skipped", reason)
                return
            except RepositoryNotPublic:
                self._outcome(run_id, repo_id, "skipped", "private")
                return
            except RepositoryNotFound:
                self._outcome(run_id, repo_id, "skipped", "not_found")
                return
            except RepositoryIdentityMismatch:
                self._outcome(run_id, repo_id, "skipped", "identity_mismatch")
                return
            except ArchiveForbidden:
                self._outcome(run_id, repo_id, "skipped", "forbidden")
                return
            except ArchiveRequestError as error:
                status = getattr(error.response, "status", None)
                if status == 451:
                    self._outcome(run_id, repo_id, "skipped", "forbidden")
                else:
                    self._outcome(run_id, repo_id, "failed", "failed")
                return
            except (ArchiveProtocolError, BlobNotFound, BlobIdentityMismatch):
                self._outcome(run_id, repo_id, "failed", "failed")
                return
            except IngestError:
                self._outcome(run_id, repo_id, "failed", "failed")
                return
            except ArchiveAuthenticationError:
                raise
            except (ArchiveRateLimited, ArchiveUnavailable):
                raise
            except LeaseLost:
                raise
            except Exception:
                # Model, Milvus, disk and other infrastructure failures are
                # resumable. Leave the repository pending and stop this run.
                self._stop = "dependency"
                return
            self._outcome(run_id, repo_id, result["result"], None)
            return

    def _reconcile(self, lease):
        try:
            reconcile(self.runtime.connect, self.runtime.vectors, lease=lease)
            return True
        except (MilvusUnavailable, MilvusOperationError):
            self._stop = "incomplete"
            return False

    def _claim_repo(self, run_id, repo_id):
        with self.runtime.connect(write=True) as db:
            db.execute(
                "INSERT INTO archive_backfill_repositories(run_id,repo_id,status) "
                "VALUES(?,?, 'pending') ON CONFLICT DO NOTHING",
                (run_id, repo_id),
            )
            status = db.execute(
                "SELECT status FROM archive_backfill_repositories "
                "WHERE run_id=? AND repo_id=?",
                (run_id, repo_id),
            ).fetchone()[0]
            if status == "failed":
                # A resumed run retries transient failures once more.
                db.execute(
                    "UPDATE archive_backfill_repositories SET status='pending',reason=NULL "
                    "WHERE run_id=? AND repo_id=?",
                    (run_id, repo_id),
                )
                return True
            return status == "pending"

    def _outcome(self, run_id, repo_id, status, reason):
        with self.runtime.connect(write=True) as db:
            db.execute(
                "UPDATE archive_backfill_repositories SET status=?,reason=? "
                "WHERE run_id=? AND repo_id=?",
                (status, reason, run_id, repo_id),
            )

    def _unresolved(self, run_id):
        with self.runtime.connect() as db:
            return (
                db.execute(
                    "SELECT 1 FROM archive_backfill_repositories WHERE run_id=? "
                    "AND status IN ('pending','failed') LIMIT 1",
                    (run_id,),
                ).fetchone()
                is not None
            )

    def _previous_boundary(self, run_id, due):
        with self.runtime.connect() as db:
            row = db.execute(
                "SELECT due_period FROM archive_runs WHERE kind='refresh' "
                "AND completed=1 AND run_id<>? ORDER BY due_period DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        if row is not None:
            try:
                return datetime.fromisoformat(row[0])
            except ValueError:
                pass
        return due - _WEEK

    def _sweep_index(self, run_id, state):
        if "sweep_index" in state:
            return int(state["sweep_index"]) % SWEEP_BUCKETS
        with self.runtime.connect() as db:
            row = db.execute(
                "SELECT s.state_json FROM archive_runs AS r "
                "JOIN archive_backfill_state AS s USING(run_id) "
                "WHERE r.kind='refresh' AND r.run_id<>? "
                "ORDER BY r.due_period DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        if row is not None:
            try:
                return int(json.loads(row[0]).get("sweep_index") or 0) % SWEEP_BUCKETS
            except (TypeError, ValueError, json.JSONDecodeError):
                return 0
        return 0

    @staticmethod
    def _sweep_bucket(due, index):
        index %= SWEEP_BUCKETS
        start = due - timedelta(days=365) + timedelta(days=SWEEP_DAYS * index)
        end = min(start + timedelta(days=SWEEP_DAYS), due)
        return DiscoveryPartition(start, end)

    def _state(self, run_id):
        with self.runtime.connect(write=True) as db:
            db.execute(
                "INSERT INTO archive_backfill_state(run_id,state_json) "
                "VALUES(?, '{}') ON CONFLICT DO NOTHING",
                (run_id,),
            )
            return json.loads(
                db.execute(
                    "SELECT state_json FROM archive_backfill_state WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
            )

    def _save_state(self, run_id, state):
        current = self._state(run_id)
        current.update(state)
        with self.runtime.connect(write=True) as db:
            db.execute(
                "UPDATE archive_backfill_state SET state_json=? WHERE run_id=?",
                (json.dumps(current, sort_keys=True), run_id),
            )

    def _summary(self, run_id, stop_reason, retry_at, due, sweep_buckets):
        with self.runtime.connect() as db:
            rows = db.execute(
                "SELECT status,reason FROM archive_backfill_repositories "
                "WHERE run_id=?",
                (run_id,),
            ).fetchall()
            status = self._status(db)
        counts = {
            "published": 0,
            "unchanged": 0,
            "failed": 0,
            "pending": 0,
        }
        skipped = {}
        for row in rows:
            if row["status"] == "skipped":
                skipped[row["reason"]] = skipped.get(row["reason"], 0) + 1
            elif row["status"] in counts:
                counts[row["status"]] += 1
        return {
            "run_id": run_id,
            "due_period": due.isoformat(),
            "known_ids": self.known_ids,
            "discovered": len(self.discovered),
            "repositories": len(rows),
            **counts,
            "skipped": skipped,
            "bytes": self.bytes,
            "requests": self.requests,
            "retry_at": retry_at,
            "stop_reason": stop_reason,
            "coverage": "complete" if stop_reason == "finished" else "partial",
            "sweep_buckets": sweep_buckets,
            **status,
        }

    @staticmethod
    def _status(db):
        rows = db.execute(
            "SELECT r.due_period, r.completed, s.state_json "
            "FROM archive_runs AS r LEFT JOIN archive_backfill_state AS s "
            "USING(run_id) WHERE r.kind='refresh'"
        ).fetchall()
        attempt = None
        complete = None
        boundary = None
        for row in rows:
            try:
                state = json.loads(row["state_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                state = {}
            value = state.get("last_attempt_at")
            if type(value) in (int, float) and (attempt is None or value > attempt):
                attempt = value
            if row["completed"]:
                value = state.get("last_complete_at")
                if type(value) in (int, float) and (
                    complete is None or value > complete
                ):
                    complete = value
                if boundary is None or row["due_period"] > boundary:
                    boundary = row["due_period"]
        return {
            "last_attempt_at": _iso(attempt),
            "last_complete_at": _iso(complete),
            "last_completed_boundary": boundary,
        }


def _iso(value):
    if value is None:
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat()
