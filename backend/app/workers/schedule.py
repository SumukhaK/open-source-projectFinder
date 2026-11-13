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
import re
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
# After a missed window both tasks start together at logon; the second waits
# for the first instead of being lost until its next trigger. Task Scheduler's
# ExecutionTimeLimit covers this wait plus the job's own step timeouts.
LOCK_WAIT = 150 * 60
LOCK_POLL = 30

# Steps that need the local Milvus stack; backup does not.
MILVUS_STEPS = {"refresh", "retire"}
MILVUS_POLL = 10
STACK_COMMAND_TIMEOUT = 300

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
    "milvus_started",
    "docker_started",
    "milvus_ready_s",
}
MAX_TEXT = 200
# CLI errors are already sanitized; this is a second guard so a future message
# carrying a path, URL or token-like string never reaches the log.
UNSAFE_ERROR = re.compile(r"[/\\]|://|[A-Za-z0-9_\-]{32,}")


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
        elif key == "error" and isinstance(value, str) and UNSAFE_ERROR.search(value):
            value = "error withheld from the log"
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
def _single_instance(directory, clock, sleep):
    """Yield the seconds waited for the lock, or None after LOCK_WAIT."""
    import fcntl  # POSIX only: the worker runs in WSL

    fd = os.open(directory / LOCK_NAME, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        start = clock()
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if clock() - start >= LOCK_WAIT:
                    yield None
                    return
                sleep(LOCK_POLL)
        yield round(clock() - start)
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


def _milvus_ready(settings):
    """True when Milvus answers and the configured collection is loaded."""
    from app.integrations.milvus import MilvusAdapter
    from app.services.embeddings import ModelManifest

    adapter = None
    try:
        adapter = MilvusAdapter.connect(settings, ModelManifest.load())
        adapter.verify_collection()
        return True
    except Exception:  # any failure just means "not ready yet"
        return False
    finally:
        if adapter is not None:
            try:
                adapter.close()
            except Exception:  # nosec B110 - closing a probe client is best effort
                pass


def _diagnostic(code, stderr):
    """Exit code plus the last stderr line, only if it carries no path or token."""
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    text = f"exit {code}"
    if lines and not UNSAFE_ERROR.search(lines[-1]):
        text += ": " + lines[-1]
    return text[:MAX_TEXT]


class MilvusStack:
    """Bring Docker/Milvus up for the steps that need it; stop only what we started.

    Commands are fixed argument lists from settings, run without a shell. Their
    output is never logged; the log gets fixed messages, flags and seconds.
    """

    def __init__(self, settings, *, runner, clock, sleep, probe):
        self.settings = settings
        self.runner, self.clock, self.sleep, self.probe = runner, clock, sleep, probe
        self.ready = None  # None until a step that needs Milvus asks for it
        self.started = False
        self.docker_started = False
        self.detail = None

    def _command(self, command, timeout):
        """Run one stack command; on failure keep a short sanitized diagnostic."""
        self.detail = None
        try:
            done = self.runner(
                command, capture_output=True, text=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired:
            self.detail = f"timed out after {timeout} s"
            return False
        except OSError:
            self.detail = "could not run"
            return False
        if done.returncode != 0:
            self.detail = _diagnostic(done.returncode, done.stderr)
        return done.returncode == 0

    def _failed(self, message, detail):
        return f"{message} ({detail})"[:MAX_TEXT] if detail else message

    def _docker_running(self):
        status = self.settings.archive_schedule_docker_status
        return bool(status) and self._command(status, STACK_COMMAND_TIMEOUT)

    def _ensure_docker(self, start, limit):
        """Start Docker Desktop first if its status says it is down.

        Return an error, or None when Docker is (or was already) running. Runs
        before any compose command: the Windows docker CLI auto-starts Desktop
        as a side effect, and an "up" that races that startup fails. A Desktop
        that was already running is never marked as ours, so never stopped.
        """
        settings = self.settings
        if not settings.archive_schedule_docker_start:
            return None
        if not settings.archive_schedule_docker_status:
            return "Docker start needs a status command"
        if self._docker_running():
            return None
        if not self._command(
            settings.archive_schedule_docker_start, STACK_COMMAND_TIMEOUT
        ):
            return self._failed("Docker start command failed", self.detail)
        # We started Desktop, so we stop it again even if the engine never answers.
        self.docker_started = True
        # "desktop start" can return before the engine answers.
        while not self._docker_running():
            if self.clock() - start >= limit:
                return f"Docker was not ready within {limit} s"
            self.sleep(MILVUS_POLL)
        return None

    def ensure(self):
        settings = self.settings
        start = self.clock()
        limit = settings.archive_schedule_milvus_ready_seconds
        record = {"step": "milvus", "milvus_started": False, "docker_started": False}
        error = None
        if self.probe():
            self.ready = True
        elif not settings.archive_schedule_milvus_up:
            error = "Milvus is not ready and no start command is configured"
        else:
            error = self._ensure_docker(start, limit)
            if error is None:
                self.started = True  # a failed "up" may still leave containers
                if not self._command(settings.archive_schedule_milvus_up, limit):
                    error = self._failed("Milvus start command failed", self.detail)
            if error is None:
                while not self.probe():
                    if self.clock() - start >= limit:
                        error = f"Milvus was not ready within {limit} s"
                        break
                    self.sleep(MILVUS_POLL)
                else:
                    self.ready = True
        self.ready = bool(self.ready)
        record.update(
            milvus_started=self.started,
            docker_started=self.docker_started,
            milvus_ready_s=round(self.clock() - start),
            result="ready" if self.ready else "failed",
            state="complete" if self.ready else "failed",
            started_at=_iso(start),
            finished_at=_iso(self.clock()),
        )
        if error:
            record["error"] = error
        return record

    def stop(self):
        """Undo only what ensure() started; None when there was nothing to stop."""
        if not (self.started or self.docker_started):
            return None
        start = self.clock()
        errors = []
        down = self.settings.archive_schedule_milvus_down
        if self.started and down and not self._command(down, STACK_COMMAND_TIMEOUT):
            errors.append(self._failed("Milvus stop command failed", self.detail))
        docker_stop = self.settings.archive_schedule_docker_stop
        if (
            self.docker_started
            and docker_stop
            and not self._command(docker_stop, STACK_COMMAND_TIMEOUT)
        ):
            errors.append(self._failed("Docker stop command failed", self.detail))
        record = {
            "step": "milvus_stop",
            "result": "failed" if errors else "stopped",
            "state": "failed" if errors else "complete",
            "started_at": _iso(start),
            "finished_at": _iso(self.clock()),
        }
        if errors:
            record["error"] = "; ".join(errors)[:MAX_TEXT]
        return record


def run_job(
    job,
    directory,
    *,
    settings=None,
    runner=subprocess.run,
    clock=time.time,
    sleep=time.sleep,
    probe=None,
):
    """Run one job's steps in order; return 0 only if every step exited 0.

    With ``settings``, the Milvus stack is checked (and started if configured)
    before the first step that needs it and stopped at the end if this run
    started it. Without settings the steps run as-is.
    """
    launched = clock()
    due = last_due(job, datetime.fromtimestamp(launched, timezone.utc))
    base = {"job": job, "due_period": due.isoformat(), "launched_at": _iso(launched)}
    with _single_instance(directory, clock, sleep) as waited:
        if waited is None:
            _append(
                directory,
                {
                    **base,
                    "step": "launch",
                    "started_at": _iso(launched),
                    "finished_at": _iso(clock()),
                    "exit_code": None,
                    "result": "overlap",
                    "state": "failed",
                },
            )
            return 1
        status = 0
        stack = None
        if settings is not None:
            stack = MilvusStack(
                settings,
                runner=runner,
                clock=clock,
                sleep=sleep,
                probe=probe or (lambda: _milvus_ready(settings)),
            )
        try:
            # Backup runs even after a failed refresh or an unavailable Milvus:
            # the export is consistent on its own and keeps the D5 copies current.
            for step in JOBS[job]:
                started = clock()
                if stack is not None and step in MILVUS_STEPS:
                    if stack.ready is None:
                        record = stack.ensure()
                        _append(directory, {**base, "exit_code": None, **record})
                        if not stack.ready:
                            status = 1
                    if not stack.ready:
                        _append(
                            directory,
                            {
                                **base,
                                "step": step,
                                "started_at": _iso(started),
                                "finished_at": _iso(clock()),
                                "exit_code": None,
                                "result": "milvus_unavailable",
                                "state": "failed",
                                "waited_s": waited,
                            },
                        )
                        continue
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
                        "waited_s": waited,
                    },
                )
                if code != 0:
                    status = 1
        finally:
            record = stack.stop() if stack is not None else None
            if record is not None:
                _append(directory, {**base, "exit_code": None, **record})
                if record["state"] != "complete":
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


def _milvus_status(rows):
    start = [row for row in rows if row.get("step") == "milvus"]
    stop = [row for row in rows if row.get("step") == "milvus_stop"]
    latest = start[-1] if start else {}
    return {
        "last_check_at": latest.get("finished_at"),
        "result": latest.get("result"),
        "milvus_started": latest.get("milvus_started"),
        "milvus_ready_s": latest.get("milvus_ready_s"),
        "error": latest.get("error"),
        "last_stop": (stop[-1].get("result") if stop else None),
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
        # An overlap-only launch ran no step, so it does not count as attempted.
        attempted = any(
            row.get("due_period") == due.isoformat() and row.get("step") in steps
            for row in rows
        )
        jobs[job] = {
            "current_due": due.isoformat(),
            "missed": not attempted,
            "next_due": next_due(job, now).isoformat() if attempted else "now",
            "last_state": _job_state(rows),
            "steps": {
                step: _step_status([row for row in rows if row.get("step") == step])
                for step in steps
            },
            "milvus": _milvus_status(rows),
        }
    return {"now": now.astimezone(timezone.utc).isoformat(), "jobs": jobs}


def _settings():
    from app.core.config import Settings

    return Settings()


def _directory(settings=None):
    settings = settings or _settings()
    return settings.archive_database_path.expanduser().resolve().parent


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

    if args.command == "run":
        settings = _settings()
        return run_job(args.job, _directory(settings), settings=settings)
    directory = _directory()
    print(json.dumps(status(directory, datetime.now(timezone.utc)), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
