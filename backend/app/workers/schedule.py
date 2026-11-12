"""T23: run the scheduled archive jobs once, and report their status.

Windows Task Scheduler starts ``python -m app.workers.schedule run weekly`` or
``run daily`` inside WSL (templates in ``infra/scheduler``). Nothing here
schedules itself or stays running. D7 times, both fixed in UTC because
Asia/Kolkata has no daylight saving:

- weekly: Saturday 22:00 UTC = Sunday 03:30 IST: ``refresh``, then ``backup``.
- daily: 16:30 UTC = 22:00 IST: ``retire``.

The weekly period is the same boundary ``refresh`` already uses, so a
scheduled, catch-up or manual launch in one week resumes the same run. A
private file lock lets only one scheduled job run at a time. Each step's JSON
summary is reduced to allowlisted counts, timings and IDs and appended to a
private log beside the catalogue; ``status`` reads only that log.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404 - fixed argument list, no shell
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from app.workers.refresh import due_boundary

JOBS = {"weekly": ("refresh", "backup"), "daily": ("retire",)}
PERIODS = {"weekly": timedelta(days=7), "daily": timedelta(days=1)}
DAILY_HOUR, DAILY_MINUTE = 16, 30  # 22:00 Asia/Kolkata
TIMEOUTS = {"refresh": 6 * 3600, "backup": 3600, "retire": 2 * 3600}
LOG_NAME = "schedule-log.jsonl"
LOCK_NAME = "schedule.lock"
LOG_KEEP = 400  # about a year of daily and weekly records

COMPLETE = {"finished", "exported", "verified"}
PARTIAL = {"cap", "quota", "rate_limit"}
# Only counts, timings, stop reasons and version IDs reach the log.
KEPT = {
    "result",
    "stop_reason",
    "coverage",
    "run_id",
    "known_ids",
    "discovered",
    "repositories",
    "published",
    "unchanged",
    "failed",
    "pending",
    "skipped",
    "bytes",
    "requests",
    "retry_at",
    "cap",
    "admitted",
    "unread_partitions",
    "last_attempt_at",
    "last_complete_at",
    "last_completed_boundary",
    "reapplied",
    "removed",
    "suppressed",
    "purged",
    "expired",
    "lifted",
    "checked",
    "issues",
    "files",
    "runs",
    "expiry",
    "snapshot",
    "schema_version",
    "error",
    "timings_ms",
}
MAX_TEXT = 200


def _check(job, now):
    if job not in JOBS:
        raise ValueError(f"job must be one of {sorted(JOBS)}")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("schedule time must be timezone-aware")


def last_due(job, now):
    """The scheduled instant of the period that contains ``now``."""
    _check(job, now)
    if job == "weekly":
        return due_boundary(now)
    moment = now.astimezone(timezone.utc)
    due = moment.replace(hour=DAILY_HOUR, minute=DAILY_MINUTE, second=0, microsecond=0)
    return due if due <= moment else due - PERIODS["daily"]


def next_due(job, now):
    return last_due(job, now) + PERIODS[job]


def _iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def _value(value):
    if value is None or type(value) in (bool, int, float):
        return True
    return isinstance(value, str) and len(value) <= MAX_TEXT


def _sanitize(summary):
    kept = {}
    for key in KEPT & summary.keys():
        value = summary[key]
        if isinstance(value, dict):
            value = {
                str(k)[:64]: v
                for k, v in value.items()
                if _value(v) and not isinstance(v, str)
            }
        elif not _value(value):
            continue
        kept[key] = value
    return kept


def _summary(stdout):
    """The archive CLI prints one JSON line; anything else is unreadable."""
    lines = (stdout or "").strip().splitlines()
    try:
        summary = json.loads(lines[-1]) if lines else None
    except json.JSONDecodeError:
        summary = None
    return summary if isinstance(summary, dict) else {"result": "unreadable"}


def _state(code, summary):
    result = summary.get("result")
    if code == 0 and result in COMPLETE:
        return "complete"
    if code == 0 and result in PARTIAL:
        return "partial"
    return "failed"


def _run_step(step, runner):
    command = [sys.executable, "-m", "app.workers.archive", step]
    try:
        done = runner(
            command,
            capture_output=True,
            text=True,
            timeout=TIMEOUTS[step],
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, {"result": "timeout"}
    except OSError:
        return None, {"result": "failed", "error": "could not start the worker"}
    return done.returncode, _sanitize(_summary(done.stdout))


@contextmanager
def _single_instance(directory):
    import fcntl  # POSIX only: the worker runs in WSL

    fd = os.open(directory / LOCK_NAME, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


def _append(directory, record):
    path = directory / LOG_NAME
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(record, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if len(lines) > LOG_KEEP:
        temporary = directory / (LOG_NAME + ".tmp")
        fd = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.writelines(lines[-LOG_KEEP:])
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)


def run_job(job, directory, *, runner=subprocess.run, clock=time.time):
    """Run one job's steps in order; return 0 only if every step exited 0."""
    launched = clock()
    due = last_due(job, datetime.fromtimestamp(launched, timezone.utc))
    base = {"job": job, "due_period": due.isoformat(), "launched_at": _iso(launched)}
    with _single_instance(directory) as acquired:
        if not acquired:
            _append(
                directory,
                {
                    **base,
                    "step": "launch",
                    "started_at": _iso(launched),
                    "finished_at": _iso(launched),
                    "exit_code": None,
                    "result": "overlap",
                    "state": "failed",
                },
            )
            return 1
        status = 0
        # Backup runs even after a failed refresh: the export is consistent on
        # its own and keeps the D5 7-day copies current.
        for step in JOBS[job]:
            started = clock()
            code, summary = _run_step(step, runner)
            state = _state(code, summary)
            _append(
                directory,
                {
                    **summary,
                    **base,
                    "step": step,
                    "started_at": _iso(started),
                    "finished_at": _iso(clock()),
                    "exit_code": code,
                    "state": state,
                },
            )
            if code != 0:
                status = 1
        return status


def _records(directory):
    try:
        text = (directory / LOG_NAME).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    rows = []
    for row in text.splitlines():
        try:
            record = json.loads(row)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("job") in JOBS:
            rows.append(record)
    return rows


def _step_status(rows):
    latest = rows[-1] if rows else {}
    success = [row for row in rows if row.get("state") == "complete"]
    return {
        "last_attempt_at": latest.get("finished_at"),
        "last_state": latest.get("state"),
        "last_success_at": success[-1].get("finished_at") if success else None,
        "result": latest.get("result"),
        "stop_reason": latest.get("stop_reason"),
        "retry_at": latest.get("retry_at"),
        "error": latest.get("error"),
    }


def _job_state(rows):
    if not rows:
        return None
    launch = rows[-1].get("launched_at")
    states = {row.get("state") for row in rows if row.get("launched_at") == launch}
    for state in ("failed", "partial", "complete"):
        if state in states:
            return state
    return "failed"


def status(directory, now):
    """Content-free view of each job: last attempt, success, partial, next due."""
    records = _records(directory)
    jobs = {}
    for job, steps in JOBS.items():
        due = last_due(job, now)
        rows = [row for row in records if row["job"] == job]
        attempted = any(row.get("due_period") == due.isoformat() for row in rows)
        jobs[job] = {
            "current_due": due.isoformat(),
            "missed": not attempted,
            "next_due": next_due(job, now).isoformat() if attempted else "now",
            "last_state": _job_state(rows),
            "steps": {
                step: _step_status([row for row in rows if row.get("step") == step])
                for step in steps
            },
        }
    return {"now": now.astimezone(timezone.utc).isoformat(), "jobs": jobs}


def _directory():
    from app.core.config import Settings

    return Settings().archive_database_path.expanduser().resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m app.workers.schedule",
        description="Run one scheduled archive job, or show job status",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run one job now (used by the scheduler)")
    run.add_argument("job", choices=sorted(JOBS))
    commands.add_parser("status", help="Show last success, partial and next due")
    args = parser.parse_args(argv)

    directory = _directory()
    if args.command == "run":
        return run_job(args.job, directory)
    print(json.dumps(status(directory, datetime.now(timezone.utc)), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
