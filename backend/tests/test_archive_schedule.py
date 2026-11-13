"""T23 scheduled archive jobs: due periods, one instance, sanitized status."""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from app.core.config import Settings
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


def test_cli_run_uses_the_catalogue_directory_and_settings(tmp_path, monkeypatch):
    calls = []
    marker = object()
    monkeypatch.setattr(schedule, "_settings", lambda: marker)
    monkeypatch.setattr(schedule, "_directory", lambda settings=None: tmp_path)
    monkeypatch.setattr(
        schedule,
        "run_job",
        lambda job, directory, settings: calls.append((job, directory, settings)) or 1,
    )
    assert schedule.main(["run", "daily"]) == 1
    assert calls == [("daily", tmp_path, marker)]


# --- Milvus stack ------------------------------------------------------------

UP = ("/usr/bin/docker", "compose", "--profile", "gpu", "up", "-d", "--wait")
DOWN = ("/usr/bin/docker", "compose", "--profile", "gpu", "down")
DOCKER_START = ("/mnt/c/docker/docker.exe", "desktop", "start")
DOCKER_STOP = ("/mnt/c/docker/docker.exe", "desktop", "stop")
DOCKER_STATUS = ("/mnt/c/docker/docker.exe", "info")


def stack_settings(**overrides):
    values = {
        "archive_schedule_milvus_up": list(UP),
        "archive_schedule_milvus_down": list(DOWN),
        "archive_schedule_docker_start": list(DOCKER_START),
        "archive_schedule_docker_stop": list(DOCKER_STOP),
        "archive_schedule_docker_status": list(DOCKER_STATUS),
        "archive_schedule_milvus_ready_seconds": 300,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class StackRunner:
    """Archive steps by name; stack commands by argument list (default exit 0)."""

    def __init__(self, steps, commands=None):
        self.steps = steps
        self.commands = {tuple(k): list(v) for k, v in (commands or {}).items()}
        self.calls = []

    def __call__(self, command, **kwargs):
        assert "shell" not in kwargs
        if command[1:3] == ["-m", "app.workers.archive"]:
            self.calls.append(command[3])
            code, stdout = self.steps[command[3]]
            return subprocess.CompletedProcess(command, code, stdout, "")
        self.calls.append(" ".join(command[1:]))
        outcomes = self.commands.get(tuple(command), [])
        outcome = outcomes.pop(0) if outcomes else 0
        if isinstance(outcome, Exception):
            raise outcome
        code, stderr = outcome if isinstance(outcome, tuple) else (outcome, "")
        return subprocess.CompletedProcess(command, code, "secret output", stderr)


def probe_after(ready_on_call):
    calls = []

    def probe():
        calls.append(1)
        return len(calls) >= ready_on_call

    return probe


def sleeping(clock):
    def sleep(seconds):
        clock.now += seconds

    return sleep


WEEKLY_STEPS = {
    "refresh": (0, line(result="cap", coverage="partial")),
    "backup": (0, line(result="exported", snapshot="a")),
}


@posix_only
def test_healthy_milvus_is_used_and_left_running(tmp_path):
    clock = Clock(WEEKLY_DUE)
    runner = StackRunner(WEEKLY_STEPS)
    code = schedule.run_job(
        "weekly",
        tmp_path,
        settings=stack_settings(),
        runner=runner,
        clock=clock,
        sleep=sleeping(clock),
        probe=lambda: True,
    )
    assert code == 0
    assert runner.calls == ["refresh", "backup"]
    milvus, refresh, backup = records(tmp_path)
    assert milvus["step"] == "milvus" and milvus["result"] == "ready"
    assert milvus["milvus_started"] is False and milvus["milvus_ready_s"] <= 1


@posix_only
def test_stopped_milvus_is_started_waited_for_and_stopped_again(tmp_path):
    clock = Clock(WEEKLY_DUE)
    runner = StackRunner(WEEKLY_STEPS)
    code = schedule.run_job(
        "weekly",
        tmp_path,
        settings=stack_settings(),
        runner=runner,
        clock=clock,
        sleep=sleeping(clock),
        probe=probe_after(4),
    )
    assert code == 0
    up, down = " ".join(UP[1:]), " ".join(DOWN[1:])
    # Milvus comes up before refresh and goes down only after the whole job.
    # Docker was already running (status 0), so only Milvus is started.
    status = " ".join(DOCKER_STATUS[1:])
    assert runner.calls == [status, up, "refresh", "backup", down]
    milvus, refresh, backup, stop = records(tmp_path)
    assert milvus["milvus_started"] is True and milvus["docker_started"] is False
    assert milvus["milvus_ready_s"] >= 2 * schedule.MILVUS_POLL
    assert stop["step"] == "milvus_stop" and stop["result"] == "stopped"
    assert "secret output" not in (tmp_path / schedule.LOG_NAME).read_text()


@posix_only
def test_stopped_docker_desktop_is_started_and_ready_before_the_first_up(tmp_path):
    # The Windows docker CLI auto-starts Desktop as a side effect, so an "up"
    # run while Desktop is down races its startup. Start and wait first.
    clock = Clock(DAILY_DUE)
    runner = StackRunner(
        {"retire": (0, line(result="finished"))},
        {UP: [0], DOCKER_STATUS: [1, 1, 0]},
    )
    code = schedule.run_job(
        "daily",
        tmp_path,
        settings=stack_settings(),
        runner=runner,
        clock=clock,
        sleep=sleeping(clock),
        probe=probe_after(2),
    )
    assert code == 0
    up = " ".join(UP[1:])
    status = " ".join(DOCKER_STATUS[1:])
    # Down before the start, polled until the engine answers, then one "up".
    assert runner.calls == [
        status,
        " ".join(DOCKER_START[1:]),
        status,
        status,
        up,
        "retire",
        " ".join(DOWN[1:]),
        " ".join(DOCKER_STOP[1:]),
    ]
    milvus, retire, stop = records(tmp_path)
    assert milvus["docker_started"] is True and milvus["milvus_started"] is True
    assert retire["state"] == "complete" and stop["result"] == "stopped"
    assert runner.calls.count(up) == 1


@posix_only
def test_milvus_never_ready_skips_refresh_but_backs_up_and_stops(tmp_path):
    clock = Clock(WEEKLY_DUE)
    runner = StackRunner(WEEKLY_STEPS)
    code = schedule.run_job(
        "weekly",
        tmp_path,
        settings=stack_settings(),
        runner=runner,
        clock=clock,
        sleep=sleeping(clock),
        probe=lambda: False,
    )
    assert code == 1
    assert "refresh" not in runner.calls and "backup" in runner.calls
    assert runner.calls[-1] == " ".join(DOWN[1:])
    milvus, refresh, backup, stop = records(tmp_path)
    assert milvus["state"] == "failed"
    assert milvus["error"] == "Milvus was not ready within 300 s"
    assert milvus["milvus_ready_s"] >= 300
    assert refresh["result"] == "milvus_unavailable" and refresh["state"] == "failed"
    assert backup["state"] == "complete"
    assert stop["result"] == "stopped"


@posix_only
def test_docker_start_failure_is_logged_and_retire_skipped(tmp_path):
    clock = Clock(DAILY_DUE)
    runner = StackRunner(
        {"retire": (0, line(result="finished"))},
        {
            UP: [1],
            DOCKER_STATUS: [1],
            DOCKER_START: [subprocess.TimeoutExpired(["x"], 1)],
        },
    )
    code = schedule.run_job(
        "daily",
        tmp_path,
        settings=stack_settings(),
        runner=runner,
        clock=clock,
        sleep=sleeping(clock),
        probe=lambda: False,
    )
    assert code == 1
    assert "retire" not in runner.calls
    milvus, retire, *rest = records(tmp_path)
    stop = rest[0] if rest else None
    assert milvus["error"] == "Docker start command failed (timed out after 300 s)"
    # A start that failed is not "ours": Desktop is never stopped for it.
    assert milvus["docker_started"] is False
    assert " ".join(DOCKER_STOP[1:]) not in runner.calls
    assert retire["result"] == "milvus_unavailable"
    # Neither Desktop nor Milvus was started, so nothing is stopped.
    assert " ".join(UP[1:]) not in runner.calls
    assert stop is None


@posix_only
def test_no_start_command_fails_without_starting_or_stopping(tmp_path):
    clock = Clock(DAILY_DUE)
    runner = StackRunner({"retire": (0, line(result="finished"))})
    settings = stack_settings(
        archive_schedule_milvus_up=[], archive_schedule_docker_start=[]
    )
    code = schedule.run_job(
        "daily",
        tmp_path,
        settings=settings,
        runner=runner,
        clock=clock,
        sleep=sleeping(clock),
        probe=lambda: False,
    )
    assert code == 1
    assert runner.calls == []
    milvus, retire = records(tmp_path)
    assert milvus["error"] == "Milvus is not ready and no start command is configured"
    assert milvus["milvus_started"] is False


@posix_only
def test_failed_stop_fails_the_job(tmp_path):
    clock = Clock(DAILY_DUE)
    runner = StackRunner({"retire": (0, line(result="finished"))}, {DOWN: [1]})
    code = schedule.run_job(
        "daily",
        tmp_path,
        settings=stack_settings(),
        runner=runner,
        clock=clock,
        sleep=sleeping(clock),
        probe=probe_after(2),
    )
    assert code == 1
    stop = records(tmp_path)[-1]
    assert (
        stop["state"] == "failed"
        and stop["error"] == "Milvus stop command failed (exit 1)"
    )


def test_status_reports_the_last_milvus_check(tmp_path):
    write_log(
        tmp_path,
        entry(
            "daily",
            "milvus",
            DAILY_DUE,
            DAILY_DUE,
            "complete",
            result="ready",
            milvus_started=True,
            milvus_ready_s=42,
        ),
        entry("daily", "retire", DAILY_DUE, DAILY_DUE, "complete"),
        entry(
            "daily", "milvus_stop", DAILY_DUE, DAILY_DUE, "complete", result="stopped"
        ),
    )
    daily = schedule.status(tmp_path, DAILY_DUE + timedelta(hours=1))["jobs"]["daily"]
    assert daily["milvus"]["milvus_started"] is True
    assert daily["milvus"]["milvus_ready_s"] == 42
    assert daily["milvus"]["last_stop"] == "stopped"
    assert daily["last_state"] == "complete"


def test_probe_reports_not_ready_on_any_milvus_error(monkeypatch):
    from app.integrations import milvus

    def refuse(settings, manifest):
        raise milvus.MilvusUnavailable("Could not connect to local Milvus")

    monkeypatch.setattr(milvus.MilvusAdapter, "connect", refuse)
    assert schedule._milvus_ready(SimpleNamespace()) is False


@pytest.mark.parametrize(
    "command",
    [
        ["docker", "compose", "up"],
        ["/usr/bin/docker", "compose", "down", "-v"],
        ["/usr/bin/docker", "compose", "down", "--volumes"],
        ["/usr/bin/docker", ""],
    ],
)
def test_settings_reject_unsafe_schedule_commands(command):
    with pytest.raises(ValueError):
        Settings(archive_schedule_milvus_down=command)


def test_settings_accept_fixed_schedule_commands():
    settings = Settings(
        archive_schedule_milvus_up=UP, archive_schedule_milvus_down=DOWN
    )
    assert settings.archive_schedule_milvus_up == list(UP)
    assert Settings().archive_schedule_milvus_up == []


@posix_only
def test_running_docker_desktop_is_never_started_or_stopped(tmp_path):
    # Desktop was already up (status 0) but compose up failed: the job must not
    # "start" Desktop (a no-op) and then stop the owner's running Desktop.
    clock = Clock(DAILY_DUE)
    runner = StackRunner(
        {"retire": (0, line(result="finished"))}, {UP: [1], DOCKER_STATUS: [0]}
    )
    code = schedule.run_job(
        "daily",
        tmp_path,
        settings=stack_settings(),
        runner=runner,
        clock=clock,
        sleep=sleeping(clock),
        probe=lambda: False,
    )
    assert code == 1
    assert " ".join(DOCKER_START[1:]) not in runner.calls
    assert " ".join(DOCKER_STOP[1:]) not in runner.calls
    milvus, retire, stop = records(tmp_path)
    assert milvus["docker_started"] is False
    assert milvus["error"] == "Milvus start command failed (exit 1)"


@posix_only
def test_docker_is_not_started_without_a_status_command(tmp_path):
    clock = Clock(DAILY_DUE)
    runner = StackRunner({"retire": (0, line(result="finished"))}, {UP: [1]})
    code = schedule.run_job(
        "daily",
        tmp_path,
        settings=stack_settings(archive_schedule_docker_status=[]),
        runner=runner,
        clock=clock,
        sleep=sleeping(clock),
        probe=lambda: False,
    )
    assert code == 1
    assert " ".join(DOCKER_START[1:]) not in runner.calls
    assert " ".join(DOCKER_STOP[1:]) not in runner.calls
    assert records(tmp_path)[0]["error"] == "Docker start needs a status command"


@posix_only
def test_docker_that_never_answers_is_stopped_after_the_bound(tmp_path):
    clock = Clock(DAILY_DUE)
    runner = StackRunner(
        {"retire": (0, line(result="finished"))}, {UP: [1], DOCKER_STATUS: [1] * 100}
    )
    code = schedule.run_job(
        "daily",
        tmp_path,
        settings=stack_settings(),
        runner=runner,
        clock=clock,
        sleep=sleeping(clock),
        probe=lambda: False,
    )
    assert code == 1
    milvus = records(tmp_path)[0]
    assert milvus["error"] == "Docker was not ready within 300 s"
    assert milvus["docker_started"] is True
    assert runner.calls[-1] == " ".join(DOCKER_STOP[1:])


@pytest.mark.parametrize(
    "field", ["archive_schedule_docker_start", "archive_schedule_docker_stop"]
)
def test_settings_require_a_docker_status_command(field):
    with pytest.raises(ValueError):
        Settings(**{field: list(DOCKER_START)})
    Settings(
        **{
            field: list(DOCKER_START),
            "archive_schedule_docker_status": list(DOCKER_STATUS),
        }
    )


def run_daily_with_failed_up(tmp_path, stderr):
    clock = Clock(DAILY_DUE)
    runner = StackRunner(
        {"retire": (0, line(result="finished"))},
        {UP: [(1, stderr)], DOCKER_STATUS: [0]},
    )
    schedule.run_job(
        "daily",
        tmp_path,
        settings=stack_settings(),
        runner=runner,
        clock=clock,
        sleep=sleeping(clock),
        probe=lambda: False,
    )
    return records(tmp_path)[0]["error"]


@posix_only
def test_failed_stack_command_logs_exit_code_and_last_safe_stderr_line(tmp_path):
    stderr = (
        "Container reporadar-t01-etcd-1  Started\n"
        "Error response from daemon: could not select device driver with capabilities: [[gpu]]\n"
    )
    error = run_daily_with_failed_up(tmp_path, stderr)
    assert error == (
        "Milvus start command failed (exit 1: Error response from daemon: "
        "could not select device driver with capabilities: [[gpu]])"
    )
    assert "etcd" not in error


@posix_only
@pytest.mark.parametrize(
    "last_line",
    [
        "open E:\\OpenSourceProjectFinder-t01\\infra\\milvus\\.env: denied",
        "pull access denied for milvusdb/milvus",
        "token ghp_abcdefghijklmnopqrstuvwxyz0123456789 rejected",
    ],
)
def test_failed_stack_command_withholds_unsafe_stderr(tmp_path, last_line):
    error = run_daily_with_failed_up(tmp_path, "starting\n" + last_line + "\n")
    assert error == "Milvus start command failed (exit 1)"


def test_diagnostic_is_bounded():
    text = schedule._diagnostic(125, "x " * 500)
    assert text.startswith("exit 125: ") and len(text) <= schedule.MAX_TEXT
