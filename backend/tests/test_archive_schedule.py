"""T23 scheduled archive jobs: due periods, one instance, sanitized status."""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

import pytest
from app.workers import schedule
from app.workers.refresh import due_boundary

IST = timezone(timedelta(hours=5, minutes=30))
# Sunday 2026-11-15 03:30 Asia/Kolkata is Saturday 2026-11-14 22:00 UTC (D7).
WEEKLY_DUE = datetime(2026, 11, 14, 22, 0, tzinfo=timezone.utc)
# Thursday 2026-11-12 22:00 Asia/Kolkata is 16:30 UTC (D7 daily sweep).
DAILY_DUE = datetime(2026, 11, 12, 16, 30, tzinfo=timezone.utc)

posix_only = pytest.mark.skipif(os.name != "posix", reason="worker runs in WSL")


# --- due periods -------------------------------------------------------------


@pytest.mark.parametrize(
    ("local", "expected"),
    [
        # One minute before Sunday 03:30 IST still belongs to last week.
        (datetime(2026, 11, 15, 3, 29, tzinfo=IST), WEEKLY_DUE - timedelta(days=7)),
        (datetime(2026, 11, 15, 3, 30, tzinfo=IST), WEEKLY_DUE),
        # A Monday or Saturday catch-up launch resumes the same week.
        (datetime(2026, 11, 16, 9, 0, tzinfo=IST), WEEKLY_DUE),
        (datetime(2026, 11, 22, 3, 29, tzinfo=IST), WEEKLY_DUE),
    ],
)
def test_weekly_due_is_sunday_0330_kolkata_and_matches_refresh(local, expected):
    assert schedule.last_due("weekly", local) == expected
    # The scheduler and a manual refresh must pin the same run identity.
    assert schedule.last_due("weekly", local) == due_boundary(local)
    assert schedule.next_due("weekly", local) == expected + timedelta(days=7)


@pytest.mark.parametrize(
    ("local", "expected"),
    [
        (datetime(2026, 11, 12, 21, 59, tzinfo=IST), DAILY_DUE - timedelta(days=1)),
        (datetime(2026, 11, 12, 22, 0, tzinfo=IST), DAILY_DUE),
        # After midnight IST the previous evening's sweep is still current.
        (datetime(2026, 11, 13, 0, 30, tzinfo=IST), DAILY_DUE),
    ],
)
def test_daily_due_is_2200_kolkata(local, expected):
    assert schedule.last_due("daily", local) == expected
    assert schedule.next_due("daily", local) == expected + timedelta(days=1)


def test_due_rejects_naive_time_and_unknown_job():
    with pytest.raises(ValueError):
        schedule.last_due("weekly", datetime(2026, 11, 15, 3, 30))
    with pytest.raises(ValueError):
        schedule.last_due("hourly", WEEKLY_DUE)


# --- running a job -----------------------------------------------------------


class FakeRunner:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        outcome = self.outcomes[command[3]]
        if isinstance(outcome, Exception):
            raise outcome
        code, stdout = outcome
        return subprocess.CompletedProcess(command, code, stdout, "")


def line(**summary):
    return json.dumps(summary) + "\n"


class Clock:
    def __init__(self, start):
        self.now = start.timestamp()

    def __call__(self):
        self.now += 1
        return self.now


def records(directory):
    path = directory / schedule.LOG_NAME
    return [json.loads(row) for row in path.read_text().splitlines()]


@posix_only
def test_weekly_runs_refresh_then_backup_and_logs_only_counts(tmp_path):
    runner = FakeRunner(
        {
            "refresh": (
                0,
                line(
                    result="cap",
                    stop_reason="cap",
                    coverage="partial",
                    published=3,
                    skipped={"license": 2},
                    requests={"search": 0, "rest": 9},
                    readme="# secret README text",
                    idea="user idea",
                    timings_ms={"total": 12},
                ),
            ),
            "backup": (0, line(result="exported", snapshot="7265e6f5", files=405)),
        }
    )
    code = schedule.run_job("weekly", tmp_path, runner=runner, clock=Clock(WEEKLY_DUE))

    assert code == 0
    commands = [call[0][3:] for call in runner.calls]
    assert commands == [["refresh"], ["backup"]]
    assert all(call[0][1:3] == ["-m", "app.workers.archive"] for call in runner.calls)
    assert all(call[1]["timeout"] > 0 for call in runner.calls)
    refresh, backup = records(tmp_path)
    assert refresh["job"] == backup["job"] == "weekly"
    assert refresh["due_period"] == WEEKLY_DUE.isoformat()
    assert refresh["step"] == "refresh" and refresh["exit_code"] == 0
    assert refresh["state"] == "partial"
    assert refresh["published"] == 3 and refresh["skipped"] == {"license": 2}
    assert "readme" not in refresh and "idea" not in refresh
    assert backup["state"] == "complete" and backup["snapshot"] == "7265e6f5"
    assert (tmp_path / schedule.LOG_NAME).stat().st_mode & 0o777 == 0o600


@posix_only
def test_failed_refresh_still_backs_up_and_job_fails(tmp_path):
    runner = FakeRunner(
        {
            "refresh": (1, line(result="failed", error="Milvus is unreachable")),
            "backup": (0, line(result="exported", snapshot="abc")),
        }
    )
    assert (
        schedule.run_job("weekly", tmp_path, runner=runner, clock=Clock(WEEKLY_DUE))
        == 1
    )
    refresh, backup = records(tmp_path)
    assert refresh["state"] == "failed" and refresh["error"] == "Milvus is unreachable"
    assert backup["state"] == "complete"


@posix_only
def test_timeout_and_unreadable_output_are_failures(tmp_path):
    runner = FakeRunner(
        {
            "refresh": subprocess.TimeoutExpired(["x"], 1),
            "backup": (1, "Traceback: /home/user/private/path\n"),
        }
    )
    assert (
        schedule.run_job("weekly", tmp_path, runner=runner, clock=Clock(WEEKLY_DUE))
        == 1
    )
    refresh, backup = records(tmp_path)
    assert refresh["result"] == "timeout" and refresh["state"] == "failed"
    assert refresh["exit_code"] is None
    assert backup["result"] == "unreadable" and backup["state"] == "failed"
    assert "private" not in json.dumps(backup)


def hold_lock(directory):
    import fcntl

    fd = os.open(directory / schedule.LOCK_NAME, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


@posix_only
def test_second_launch_waits_for_the_first_then_runs(tmp_path):
    # Both tasks fire at logon after a missed window: the weekly job must not
    # be lost because the daily one holds the lock.
    fd = hold_lock(tmp_path)
    clock = Clock(WEEKLY_DUE + timedelta(days=1))
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        clock.now += seconds
        if len(sleeps) == 3:
            os.close(fd)  # the first job finishes

    runner = FakeRunner(
        {
            "refresh": (0, line(result="cap", coverage="partial")),
            "backup": (0, line(result="exported", snapshot="a")),
        }
    )
    code = schedule.run_job("weekly", tmp_path, runner=runner, clock=clock, sleep=sleep)
    assert code == 0
    assert [call[0][3] for call in runner.calls] == ["refresh", "backup"]
    assert sleeps == [schedule.LOCK_POLL] * 3
    refresh, backup = records(tmp_path)
    assert refresh["waited_s"] >= 3 * schedule.LOCK_POLL
    assert refresh["due_period"] == WEEKLY_DUE.isoformat()


@posix_only
def test_overlap_is_logged_only_after_the_bounded_wait(tmp_path):
    fd = hold_lock(tmp_path)
    clock = Clock(DAILY_DUE)

    def sleep(seconds):
        clock.now += seconds

    runner = FakeRunner({"retire": (0, line(result="finished"))})
    try:
        code = schedule.run_job(
            "daily", tmp_path, runner=runner, clock=clock, sleep=sleep
        )
    finally:
        os.close(fd)
    assert code == 1
    assert runner.calls == []
    (record,) = records(tmp_path)
    assert record["result"] == "overlap" and record["state"] == "failed"
    assert clock.now - DAILY_DUE.timestamp() >= schedule.LOCK_WAIT
    # Once the first instance exits, the next launch runs normally.
    assert (
        schedule.run_job("daily", tmp_path, runner=runner, clock=Clock(DAILY_DUE)) == 0
    )
    # An overlap-only period is not an attempt; the retry above is.
    assert (
        schedule.status(tmp_path, DAILY_DUE + timedelta(hours=1))["jobs"]["daily"][
            "missed"
        ]
        is False
    )


def test_status_does_not_count_overlap_only_as_attempted(tmp_path):
    write_log(
        tmp_path,
        entry("daily", "launch", DAILY_DUE, DAILY_DUE, "failed", result="overlap"),
    )
    daily = schedule.status(tmp_path, DAILY_DUE + timedelta(hours=1))["jobs"]["daily"]
    assert daily["missed"] is True and daily["next_due"] == "now"
    assert daily["last_state"] == "failed"


@pytest.mark.parametrize(
    "error",
    [
        "cannot open /home/someone/private/catalogue.sqlite3",
        "failed at https://example.invalid/x",
        "bad token ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "C:\\Users\\someone\\file",
    ],
)
def test_error_with_path_url_or_token_is_withheld(error):
    kept = schedule._sanitize({"result": "failed", "error": error})
    assert kept["error"] == "error withheld from the log"


def test_plain_sanitized_error_is_kept():
    kept = schedule._sanitize({"result": "failed", "error": "Milvus is unreachable"})
    assert kept["error"] == "Milvus is unreachable"


@posix_only
def test_scheduled_and_catch_up_launches_record_one_period(tmp_path):
    runner = FakeRunner(
        {
            "refresh": (0, line(result="rate_limit", coverage="partial", retry_at=1.0)),
            "backup": (0, line(result="exported", snapshot="a")),
        }
    )
    schedule.run_job("weekly", tmp_path, runner=runner, clock=Clock(WEEKLY_DUE))
    monday = WEEKLY_DUE + timedelta(days=1, hours=5)
    schedule.run_job("weekly", tmp_path, runner=runner, clock=Clock(monday))
    periods = {record["due_period"] for record in records(tmp_path)}
    assert periods == {WEEKLY_DUE.isoformat()}


@posix_only
def test_log_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule, "LOG_KEEP", 3)
    runner = FakeRunner({"retire": (0, line(result="finished"))})
    for day in range(5):
        start = DAILY_DUE + timedelta(days=day)
        schedule.run_job("daily", tmp_path, runner=runner, clock=Clock(start))
    kept = records(tmp_path)
    assert len(kept) == 3
    assert kept[-1]["due_period"] == (DAILY_DUE + timedelta(days=4)).isoformat()


# --- status ------------------------------------------------------------------


def write_log(directory, *rows):
    path = directory / schedule.LOG_NAME
    path.write_text("".join(json.dumps(row) + "\n" for row in rows) + "not json\n")


def entry(job, step, due, at, state, **extra):
    return {
        "job": job,
        "step": step,
        "due_period": due.isoformat(),
        "started_at": at.isoformat(),
        "finished_at": at.isoformat(),
        "launched_at": at.isoformat(),
        "state": state,
        **extra,
    }


def test_status_with_no_runs_reports_every_job_missed(tmp_path):
    now = WEEKLY_DUE + timedelta(hours=1)
    report = schedule.status(tmp_path, now)
    weekly = report["jobs"]["weekly"]
    assert weekly["current_due"] == WEEKLY_DUE.isoformat()
    assert weekly["missed"] is True
    assert weekly["next_due"] == "now"
    assert weekly["last_state"] is None
    assert weekly["steps"]["refresh"]["last_success_at"] is None


def test_status_shows_partial_last_success_and_next_due(tmp_path):
    earlier = WEEKLY_DUE - timedelta(days=7)
    write_log(
        tmp_path,
        entry("weekly", "refresh", earlier, earlier, "complete"),
        entry("weekly", "backup", earlier, earlier, "complete"),
        entry(
            "weekly",
            "refresh",
            WEEKLY_DUE,
            WEEKLY_DUE,
            "partial",
            stop_reason="rate_limit",
            retry_at=99.0,
        ),
        entry("weekly", "backup", WEEKLY_DUE, WEEKLY_DUE, "complete", snapshot="s2"),
        entry("daily", "retire", DAILY_DUE, DAILY_DUE, "failed", error="busy"),
    )
    now = WEEKLY_DUE + timedelta(hours=2)
    report = schedule.status(tmp_path, now)

    weekly = report["jobs"]["weekly"]
    assert weekly["missed"] is False
    assert weekly["last_state"] == "partial"
    assert weekly["next_due"] == (WEEKLY_DUE + timedelta(days=7)).isoformat()
    refresh = weekly["steps"]["refresh"]
    assert refresh["last_state"] == "partial"
    assert refresh["stop_reason"] == "rate_limit" and refresh["retry_at"] == 99.0
    assert refresh["last_success_at"] == earlier.isoformat()
    assert weekly["steps"]["backup"]["last_success_at"] == WEEKLY_DUE.isoformat()

    daily = report["jobs"]["daily"]
    # The sweep that failed on 12 Nov is stale by the 14th: today's is missed.
    assert daily["missed"] is True and daily["next_due"] == "now"
    assert daily["last_state"] == "failed"


def test_cli_status_prints_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(schedule, "_directory", lambda: tmp_path)
    assert schedule.main(["status"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert set(report["jobs"]) == {"weekly", "daily"}


def test_cli_rejects_unknown_job():
    with pytest.raises(SystemExit):
        schedule.main(["run", "hourly"])


@posix_only
def test_worker_that_cannot_start_or_prints_bad_json_fails(tmp_path):
    runner = FakeRunner(
        {"refresh": OSError("no such file"), "backup": (0, "{not json\n")}
    )
    assert (
        schedule.run_job("weekly", tmp_path, runner=runner, clock=Clock(WEEKLY_DUE))
        == 1
    )
    refresh, backup = records(tmp_path)
    assert refresh["error"] == "could not start the worker"
    assert "no such file" not in json.dumps(refresh)
    assert backup["result"] == "unreadable" and backup["state"] == "failed"


def test_cli_run_uses_the_catalogue_directory(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(schedule, "_directory", lambda: tmp_path)
    monkeypatch.setattr(
        schedule, "run_job", lambda job, directory: calls.append((job, directory)) or 1
    )
    assert schedule.main(["run", "daily"]) == 1
    assert calls == [("daily", tmp_path)]
