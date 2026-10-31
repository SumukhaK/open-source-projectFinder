"""T18's deliberately serial, resumable 1,000-repository backfill worker."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.integrations.archive_github import (
    ArchiveAuthenticationError,
    ArchiveRateLimited,
    ArchiveUnavailable,
    RepositoryNotPublic,
)
from app.services.archive_partitions import needs_split, plan_root, split_partition
from app.services.archive_runs import RunStore
from app.workers.archive import IneligibleRepository, ingest_one

_PERIOD = datetime(1970, 1, 1, tzinfo=timezone.utc)


class Backfill:
    """One manual pilot is identified by a stable due period and resumes in place."""

    def __init__(self, runtime, *, clock, disk_free=None, checkpoint=None):
        self.runtime = runtime
        self.clock = clock
        self.disk_free = disk_free or self._free_disk
        self.checkpoint = checkpoint or (lambda stage: None)
        self.store = RunStore(runtime.connect, clock=clock)
        self.requests = {"search": 0, "rest": 0}
        self.bytes = 0
        self._stop = None
        self._retry_at = None

    def _free_disk(self):
        return min(
            shutil.disk_usage(self.runtime.settings.archive_database_path.parent).free,
            shutil.disk_usage(self.runtime.content.root).free,
        )

    def run(self, *, cap):
        if type(cap) is not int or not 1 <= cap <= 1000:
            raise ValueError("--cap must be an integer from 1 through 1000")
        run_id = self.store.create_run("backfill", _PERIOD)
        state = self._state(run_id)
        if state.get("retry_at", 0) > self.clock():
            return self._summary(run_id, "rate_limit", state["retry_at"])
        if state.get("retry_at"):
            self._save_state(run_id, {})
        lease = self.store.claim(run_id, uuid.uuid4().hex)
        reader, self.runtime.reader.observer = self.runtime.reader, self
        try:
            self._ensure_root(run_id, lease)
            while not self._stop:
                task = self._next_task(run_id)
                if task is None:
                    if self._finish_completed_parents(run_id, lease):
                        continue
                    break
                self._page(run_id, lease, task, cap)
            complete = not self._stop and not self._pending(run_id)
            self.store.release(lease, completed=complete)
            return self._summary(run_id, self._stop or "finished", self._retry_at)
        except ArchiveAuthenticationError:
            self._stop = "credential"
            self.store.release(lease)
            return self._summary(run_id, "credential", None)
        except (ArchiveRateLimited, ArchiveUnavailable) as error:
            if self._stop:
                self.store.release(lease)
                return self._summary(run_id, self._stop, self._retry_at)
            retry = error.retry_at.timestamp() if error.retry_at else self.clock() + 60
            self._defer(lease, self._current_key, retry)
            return self._summary(run_id, "rate_limit", retry)
        finally:
            reader.observer = None

    # The reader calls these around every actual HTTP request.  They deliberately
    # use server headers, never guessed quotas, and preserve independent buckets.
    def before_request(self, path):
        if self._stop:
            raise ArchiveUnavailable("backfill budget reached")
        self.store.heartbeat(self._lease)
        if self.disk_free() < self.runtime.settings.archive_min_free_bytes:
            self._stop = "disk"
            raise ArchiveUnavailable("disk bound reached")
        bucket = "search" if path == "/search/repositories" else "rest"
        self.requests[bucket] += 1

    def after_response(self, response):
        self.bytes += response.encoded_bytes
        if self.bytes > self.runtime.settings.archive_backfill_byte_limit:
            self._stop = "bytes"
        remaining = response.headers.get("x-ratelimit-remaining")
        limit = response.headers.get("x-ratelimit-limit")
        reset = response.headers.get("x-ratelimit-reset")
        if remaining and limit and reset and int(remaining) <= max(1, int(limit) // 5):
            self._stop = "quota"
            self._retry_at = float(reset)

    def _ensure_root(self, run_id, lease):
        with self.runtime.connect() as db:
            exists = db.execute(
                "SELECT 1 FROM archive_partitions WHERE run_id=?", (run_id,)
            ).fetchone()
        if not exists:
            self.store.add_partition(
                lease, plan_root(datetime.fromtimestamp(self.clock(), timezone.utc))
            )

    def _next_task(self, run_id):
        with self.runtime.connect() as db:
            row = db.execute(
                "SELECT p.partition_key,p.record,t.page,t.stage FROM archive_partitions p "
                "JOIN archive_tasks t USING(run_id,partition_key) "
                "WHERE p.run_id=? AND p.state='pending' AND (t.retry_at IS NULL OR t.retry_at<=?) "
                "AND t.stage NOT IN ('split','unresolved') ORDER BY p.partition_key LIMIT 1",
                (run_id, self.clock()),
            ).fetchone()
        if row is None:
            return None
        from app.services.archive_partitions import DiscoveryPartition

        return (
            row["partition_key"],
            DiscoveryPartition.from_record(json.loads(row["record"])),
            row["page"],
        )

    def _page(self, run_id, lease, task, cap):
        key, partition, page = task
        self._lease, self._current_key = lease, key
        if self.disk_free() < self.runtime.settings.archive_min_free_bytes:
            self._stop = "disk"
            return
        result = self.runtime.reader.search_repositories(partition.query, page=page)
        record = {
            "query": partition.query,
            "total_count": result.total_count,
            "incomplete_results": result.incomplete,
            "pages_read": page,
            "ids_returned": list(result.ids),
            "decision": "page",
        }
        with self.runtime.connect(write=True) as db:
            db.execute(
                "INSERT OR REPLACE INTO archive_backfill_pages VALUES(?,?,?,?)",
                (run_id, key, page, json.dumps(record, sort_keys=True)),
            )
        self.checkpoint("page_saved")
        if needs_split(result.total_count, result.incomplete):
            split = split_partition(
                partition,
                reported_count=result.total_count,
                incomplete=result.incomplete,
            )
            record["decision"] = split.reason or "split"
            self._replace_page(run_id, key, page, record)
            if split.unresolved:
                self.store.checkpoint(lease, key, page=page, stage="unresolved")
                self._stop = "partition"
                return
            if (
                self._partition_count(run_id) + len(split.children)
                > self.runtime.settings.archive_backfill_partition_limit
            ):
                record["decision"] = "unresolved"
                self._replace_page(run_id, key, page, record)
                self.store.checkpoint(lease, key, page=page, stage="unresolved")
                self._stop = "partition"
                return
            self.store.add_split(lease, split)
            self.store.checkpoint(lease, key, page=page, stage="split")
            return
        if len(result.ids) > self.runtime.settings.archive_backfill_queue_limit:
            self._stop = "queue"
            return
        for repo_id in result.ids:
            if self._admitted(run_id) >= cap:
                self._stop = "cap"
                return
            if not self._claim_repo(run_id, repo_id):
                continue
            self._ingest(run_id, lease, repo_id)
            if self._stop:
                return
        done = len(result.ids) < 100 or page >= 10 or page * 100 >= result.total_count
        self.store.checkpoint(
            lease, key, page=min(10, page + 1), stage="page_finished", completed=done
        )
        self.checkpoint("page_finished")

    def _ingest(self, run_id, lease, repo_id):
        def progress(stage, facts):
            if stage in ("eligible", "published"):
                with self.runtime.connect(write=True) as db:
                    row = db.execute(
                        "SELECT facts_json FROM archive_backfill_repositories WHERE run_id=? AND repo_id=?",
                        (run_id, repo_id),
                    ).fetchone()
                    saved = {**json.loads(row[0]), **facts}
                    if stage == "published":
                        saved["published"] = True
                    db.execute(
                        "UPDATE archive_backfill_repositories SET facts_json=? WHERE run_id=? AND repo_id=?",
                        (json.dumps(saved, sort_keys=True), run_id, repo_id),
                    )
            self.checkpoint(stage)

        try:
            result = ingest_one(
                self.runtime,
                repo_id,
                now=datetime.fromtimestamp(self.clock(), timezone.utc),
                lease=lease,
                progress=progress,
            )
            status = result["result"]
            if status == "unchanged" and self._was_published(run_id, repo_id):
                status = "published"
            self._outcome(run_id, repo_id, status, None)
            self.checkpoint("outcome_saved")
        except IneligibleRepository as error:
            reason = "licence" if error.reason.startswith("license") else error.reason
            if reason == "not_public":
                reason = "private"
            self._outcome(
                run_id,
                repo_id,
                "skipped",
                reason,
            )
            self.checkpoint("outcome_saved")
        except RepositoryNotPublic:
            self._outcome(run_id, repo_id, "skipped", "private")
            self.checkpoint("outcome_saved")
        except ArchiveAuthenticationError:
            raise
        except (ArchiveRateLimited, ArchiveUnavailable):
            raise
        except Exception:
            self._outcome(run_id, repo_id, "failed", "failed")

    def _claim_repo(self, run_id, repo_id):
        with self.runtime.connect(write=True) as db:
            db.execute(
                "INSERT INTO archive_backfill_repositories(run_id,repo_id,status) VALUES(?,?, 'pending') ON CONFLICT DO NOTHING",
                (run_id, repo_id),
            )
            return (
                db.execute(
                    "SELECT status FROM archive_backfill_repositories WHERE run_id=? AND repo_id=?",
                    (run_id, repo_id),
                ).fetchone()[0]
                == "pending"
            )

    def _outcome(self, run_id, repo_id, status, reason):
        with self.runtime.connect(write=True) as db:
            db.execute(
                "UPDATE archive_backfill_repositories SET status=?,reason=? WHERE run_id=? AND repo_id=?",
                (status, reason, run_id, repo_id),
            )

    def _was_published(self, run_id, repo_id):
        with self.runtime.connect() as db:
            row = db.execute(
                "SELECT facts_json FROM archive_backfill_repositories WHERE run_id=? AND repo_id=?",
                (run_id, repo_id),
            ).fetchone()
        return bool(row and json.loads(row[0]).get("published"))

    def _admitted(self, run_id):
        with self.runtime.connect() as db:
            return db.execute(
                "SELECT count(*) FROM archive_backfill_repositories WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]

    def _partition_count(self, run_id):
        with self.runtime.connect() as db:
            return db.execute(
                "SELECT count(*) FROM archive_partitions WHERE run_id=?", (run_id,)
            ).fetchone()[0]

    def _pending(self, run_id):
        with self.runtime.connect() as db:
            return (
                db.execute(
                    "SELECT 1 FROM archive_partitions WHERE run_id=? AND state='pending'",
                    (run_id,),
                ).fetchone()
                is not None
            )

    def _finish_completed_parents(self, run_id, lease):
        """Only promote a split parent after every durable child is complete."""
        with self.runtime.connect() as db:
            rows = db.execute(
                "SELECT t.partition_key,t.page FROM archive_tasks t "
                "WHERE t.run_id=? AND t.stage='split'",
                (run_id,),
            ).fetchall()
            ready = [
                row
                for row in rows
                if not db.execute(
                    "SELECT 1 FROM archive_partitions WHERE run_id=? "
                    "AND json_extract(record,'$.parent_key')=? AND state<>'completed'",
                    (run_id, row["partition_key"]),
                ).fetchone()
            ]
        for row in ready:
            self.store.checkpoint(
                lease,
                row["partition_key"],
                page=row["page"],
                stage="completed",
                completed=True,
            )
        return bool(ready)

    def _defer(self, lease, key, retry):
        self._retry_at = retry
        self._save_state(lease.run_id, {"retry_at": retry})
        self.store.defer(lease, key, retry_at=retry)
        self.store.release(lease)

    def _state(self, run_id):
        with self.runtime.connect(write=True) as db:
            db.execute(
                "INSERT INTO archive_backfill_state(run_id,state_json) VALUES(?, '{}') ON CONFLICT DO NOTHING",
                (run_id,),
            )
            return json.loads(
                db.execute(
                    "SELECT state_json FROM archive_backfill_state WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
            )

    def _save_state(self, run_id, state):
        with self.runtime.connect(write=True) as db:
            db.execute(
                "UPDATE archive_backfill_state SET state_json=? WHERE run_id=?",
                (json.dumps(state), run_id),
            )

    def _replace_page(self, run_id, key, page, record):
        with self.runtime.connect(write=True) as db:
            db.execute(
                "UPDATE archive_backfill_pages SET record_json=? WHERE run_id=? AND partition_key=? AND page=?",
                (json.dumps(record, sort_keys=True), run_id, key, page),
            )

    def _summary(self, run_id, stop_reason, retry_at=None):
        self._write_log(run_id)
        with self.runtime.connect() as db:
            rows = db.execute(
                "SELECT status,reason,facts_json FROM archive_backfill_repositories WHERE run_id=?",
                (run_id,),
            ).fetchall()
            unresolved = db.execute(
                "SELECT count(*) FROM archive_tasks WHERE run_id=? AND stage='unresolved'",
                (run_id,),
            ).fetchone()[0]
            deferred = db.execute(
                "SELECT count(*) FROM archive_tasks WHERE run_id=? AND retry_at IS NOT NULL",
                (run_id,),
            ).fetchone()[0]
        counts = {"published": 0, "unchanged": 0, "failed": 0, "eligible": 0}
        skipped, language, stars = {}, {}, {}
        activity = {"30d": 0, "31d-180d": 0, "181d-365d": 0}
        for row in rows:
            if row["status"] in counts:
                counts[row["status"]] += 1
            if row["status"] in ("published", "unchanged"):
                counts["eligible"] += 1
                facts = json.loads(row["facts_json"])
                name = facts.get("language") or "Unknown"
                language[name] = language.get(name, 0) + 1
                age = self.clock() - facts.get("pushed_at", self.clock())
                band = (
                    "30d"
                    if age <= 30 * 86400
                    else "31d-180d"
                    if age <= 180 * 86400
                    else "181d-365d"
                )
                activity[band] += 1
                value = facts.get("stars", 0)
                star_band = (
                    "0"
                    if value == 0
                    else "1-10"
                    if value <= 10
                    else "11-100"
                    if value <= 100
                    else "101+"
                )
                stars[star_band] = stars.get(star_band, 0) + 1
            if row["status"] == "skipped":
                skipped[row["reason"]] = skipped.get(row["reason"], 0) + 1
        return {
            "run_id": run_id,
            "discovered": self._admitted(run_id),
            **counts,
            "skipped": skipped,
            "bytes": self.bytes,
            "requests": self.requests,
            "retry_at": retry_at,
            "stop_reason": stop_reason,
            "unresolved_partitions": unresolved,
            "deferred_partitions": deferred,
            "coverage": "partial"
            if stop_reason in ("disk", "queue", "partition", "bytes") or unresolved
            else "curated",
            "distribution": {
                "language": language,
                "activity": activity,
                "stars": stars,
            },
        }

    def _write_log(self, run_id):
        with self.runtime.connect() as db:
            rows = db.execute(
                "SELECT record_json FROM archive_backfill_pages WHERE run_id=? ORDER BY partition_key,page",
                (run_id,),
            ).fetchall()
        path = (
            Path(self.runtime.settings.archive_database_path).parent
            / f"backfill-{run_id}.jsonl"
        )
        path.write_text(
            "".join(
                json.dumps(json.loads(row[0]), sort_keys=True) + "\n" for row in rows
            ),
            encoding="utf-8",
        )
