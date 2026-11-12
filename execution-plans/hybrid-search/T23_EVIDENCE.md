# T23 weekly host scheduling and operator status

Status: **Merged** as `9667ea5` ([PR #105](https://github.com/SumukhaK/open-source-projectFinder/pull/105)), after an independent Claude review (changes requested at `b7b73d7`, approved at `f7d09a6`). Both tasks are registered on the laptop **disabled**; one real daily run passed through Task Scheduler (see "Real Windows evidence"). Enabling the schedule needs the owner's separate approval.

In plain terms: two Windows Task Scheduler templates start the archive worker in WSL. Every Sunday at 03:30 India time it runs the weekly refresh and then the encrypted backup; every evening at 22:00 it runs the privacy/removal sweep. If the laptop was off, the job runs when it is next on. Only one job runs at a time. `status` shows what last succeeded, what was partial, and when the next run is due. The templates import switched off; switching them on needs the owner's OK.

- Branch: `claude/project-thread-0r6boc` (the session's assigned branch, in place of the handbook's `codex/hybrid-t23-host-schedule`)
- Base: `5bd2046` (`origin/main`, T22 merged as PR #102)
- Prerequisites merged into main: T19 (`43f5db9`), T20 (`a454b98`), T22 (`5bd2046`). D7 approved: daily sweep about 22:00 and full refresh Sunday 03:30 Asia/Kolkata, missed runs catch up.

## Scope delivered

Production files: 3.
- New `backend/app/workers/schedule.py`: `run weekly|daily` and `status`.
- New `infra/scheduler/reporadar-archive-weekly.xml` and `reporadar-archive-daily.xml` (Task Scheduler templates, `Enabled=false`).

Docs: `infra/scheduler/README.md` (runbook), `backend/README.md`, this file, tracker.

Behaviour:
- **Periods.** Weekly = `refresh.due_boundary` (Saturday 22:00 UTC = Sunday 03:30 IST), so scheduler, catch-up and manual runs in one week share one `refresh` run. Daily = 16:30 UTC (22:00 IST). Both fixed in UTC; Asia/Kolkata has no DST. `retire` needs no durable run of its own: it is idempotent, and the daily period is recorded only in the job log.
- **Steps.** Weekly runs `refresh` then `backup`; daily runs `retire`. Each is `python -m app.workers.archive <step>` with its defaults, so `refresh` keeps `--cap 0` (D1). Backup still runs after a failed refresh (it is a consistent export on its own); the job exits 1 if any step exited non-zero. Per-step timeouts: refresh 6 h, backup 1 h, retire 2 h; Task Scheduler's limits are 10 h / 5 h (step timeouts plus the 2.5 h lock wait).
- **One instance.** Task Scheduler `IgnoreNew` per task, plus a private `schedule.lock` (`flock`, non-blocking) beside the catalogue across both tasks. A second launch (both tasks firing at logon after a missed window) waits for the lock, polling every 30 s for up to 2.5 h, then runs and logs `waited_s`; only after that wait does it run nothing, log `overlap` and exit 1. The archive writer lease is unchanged and still guards manual commands.
- **Catch-up.** `StartWhenAvailable=true`, `WakeToRun=false`, runs only while the owner is signed in (`InteractiveToken`, least privilege, no stored password), not stopped on battery.
- **Status and log.** Each step's JSON summary is reduced to an allowlist of counts, timings, stop reasons, run/snapshot IDs and short sanitized errors, then appended (fsynced) to `schedule-log.jsonl` (0600, last 400 lines). Non-JSON output is logged only as `unreadable`; stderr is never logged. `status` reads only this log and prints, per job, `current_due`, `missed`, `next_due` (`"now"` when missed), `last_state` (`complete`/`partial`/`failed` for the last launch), and per step the last attempt/state/result/success, `stop_reason`, `retry_at`, `error`.

## RED (Linux, Python 3.13.18, SQLite 3.53.1, 2026-11-12)

Tests written first against a stub whose functions raised `NotImplementedError`:
`python -m pytest tests/test_archive_schedule.py -q` (from `backend/`) → **18 failed**, exit 1. Covered: IST week boundary (03:29 vs 03:30 Sunday, Monday/Saturday catch-up stays in the same week, equality with `refresh.due_boundary`), IST daily boundary (21:59/22:00, after midnight), naive time and unknown job rejected, refresh→backup order and allowlisted log, failed refresh still backs up, timeout and unreadable output, overlapping launch runs nothing, scheduled and catch-up launches record one period, bounded log, status for missed/partial/last success/next due, CLI.

Mutation check after GREEN (each defect reintroduced, then reverted); every one failed the suite:

| Defect | Result |
| --- | --- |
| no lock | 1 failed |
| no allowlist (whole summary logged) | 1 failed |
| daily at 22:00 UTC instead of IST | 4 failed |
| weekly ignores the input time zone | 2 failed |
| stop after a failed refresh (no backup) | 2 failed |
| unbounded log | 1 failed |
| never reports a missed period | 2 failed |
| world-readable log | 1 failed |

## GREEN (same platform)

- `python -m pytest tests/test_archive_schedule.py -q` → 20 passed (two coverage tests added after the first GREEN: worker that cannot start, bad JSON, CLI `run`).
- `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:reports/backend-coverage.json` → 1,326 passed, 3 skipped.
- `python scripts/quality.py coverage reports/backend-coverage.json` → 93.4% combined / 90.3% branches (gate 90/80).
- `ruff check backend scripts` passed; `ruff format --check backend scripts` clean; `bandit -r backend/app` 0 findings; `git diff --check` clean. Both XML templates parse.
- Secret inspection of the diff: no tokens, passwords or private paths beyond the already-documented worker interpreter path.

## Review fixes (2026-11-12)

The independent review of `b7b73d7` requested one blocking change. After a missed window, both tasks start at logon (`StartWhenAvailable`). The loser logged `overlap`, exited 1 and was never relaunched, so the weekly refresh and backup could be lost for a week. Fixes:
- **Blocking: bounded lock wait.** `run_job` now polls the lock every 30 s for up to `LOCK_WAIT` (2.5 h) and runs once it is free. It logs `overlap` only on timeout. The Task Scheduler limits were raised to 10 h weekly and 5 h daily to cover the wait.
- `status` counts a period as attempted only if a real step ran, so an overlap-only launch leaves it `missed`.
- `error` gets a second guard: a value containing a path separator, a URL or a token-like run of 32 or more characters is replaced by `error withheld from the log`.

RED: the 7 new tests were run against the reviewed `schedule.py` and failed, exit 1. The failing tests were: wait then run, overlap only after the bounded wait, overlap-only not attempted, and 4 withheld-error cases. GREEN: `tests/test_archive_schedule.py` passed 27; full suite 1,333 passed / 3 skipped, coverage 93.4% / 90.4%; ruff, format, bandit and `git diff --check` clean.

## Real Windows evidence (2026-11-12)

Run by the reviewing Claude session on the owner's laptop with the owner's approval, from a worker clone at `f7d09a6`:
- Both templates registered under `\RepoRadar\`; both showed **Disabled**.
- `archive-daily` was enabled, started and disabled again at once, so it ran through the real Task Scheduler -> `wsl.exe` -> `schedule run daily` path: **LastTaskResult 0** in 3 min 9 s. Both tasks ended Disabled. `archive-weekly` has never run.
- Log line: `state: complete`, `result: finished`, `due_period 2026-11-11T16:30:00+00:00` (the 22:00 IST boundary), `waited_s: 0`, `checked: 204`, `purged: 2`, `issues: 0`; counts and timings only.
- `status`: daily complete with `next_due` 16:30Z; weekly `missed: true` (never run, as expected).
- Live catalogue: 206 -> 204 repositories, 1,157 -> 1,141 chunks; 2 `archived` suppressions reapplied from the ledger; the ledger did not grow.
- `schedule-log.jsonl`, `schedule.lock` and the ledger are all 0600.

**Operator note:** the registered tasks point at `/home/sumukha/reporadar-t23-worker`, which was checked out at the PR branch. Switch that checkout to `main` (now containing `9667ea5`) before anyone enables the tasks.

## Not run

- The weekly job (`refresh` + `backup`) has not run through Task Scheduler; the tasks were not left enabled.

## Limits

- A sleeping, switched-off or signed-out laptop does not run the jobs; they catch up when Windows is next up and the owner is signed in.
- The jobs do not start Docker Desktop or the GPU Milvus stack. `refresh` and `retire` fail with a sanitized error if Milvus is down; `backup` does not need it. Keeping Milvus running for the 22:00 daily sweep costs host RAM (T18 saw `vmmem` at the 6 GB cap); the owner may prefer to start Milvus only for the weekly window, which would leave the daily sweep failing on other days. This needs an owner decision before enabling.
- With `--cap 0`, every weekly refresh ends `partial` (`cap`) by design.
- A launch still locked out after 2.5 h (for example, the daily sweep behind a refresh that runs longer than that) logs `overlap` and stays `missed` until its next trigger or a manual rerun.
- `status` reflects only scheduled (or `schedule run`) launches, not commands run directly with `app.workers.archive`.
- Trigger times are local; the runbook checks the Windows time zone is India Standard Time. The run identity is UTC-pinned either way.

## Operator and rollback notes

See [infra/scheduler/README.md](../../infra/scheduler/README.md) for import, dry run, enable/disable, status, retry and credentials. No migration. Rollback: `Unregister-ScheduledTask` both tasks and revert the code; `schedule-log.jsonl` and `schedule.lock` can be deleted.

## Follow-up: the jobs start and stop Milvus (2026-11-12)

On the owner's decision (the laptop normally keeps Docker Desktop and Milvus stopped to save RAM), `schedule run` now manages the stack for the steps that need it (`refresh`, `retire`; not `backup`):
- It first checks Milvus: connect and `verify_collection`, which also loads the collection. If Milvus is ready, the job uses it and leaves it running.
- Otherwise it runs `ARCHIVE_SCHEDULE_MILVUS_UP`. If that fails (inside WSL the `docker` CLI is missing or fails while Docker Desktop is stopped), it runs `ARCHIVE_SCHEDULE_DOCKER_START` and retries `up` once. It then polls every 10 s up to `ARCHIVE_SCHEDULE_MILVUS_READY_SECONDS` (default 300).
- If Milvus never becomes ready, the Milvus steps are logged `milvus_unavailable` and skipped, `backup` still runs, and the job exits 1.
- At the end it runs `..._MILVUS_DOWN` only if it ran `up`, and `..._DOCKER_STOP` only if it started Desktop. A failed stop fails the job.
- The log gets `milvus` / `milvus_stop` lines with `milvus_started`, `docker_started`, `milvus_ready_s` and fixed error messages; command output is never captured into it. `status` shows the last check per job.
- Settings validation: each command is a JSON argument list with an absolute program path first, at most 32 bounded arguments, run without a shell. `-v`, `--volumes` and `--rmi` are refused, so a stop can never delete the Milvus volumes. Empty (the default) means check only, never start.

Production files: `backend/app/workers/schedule.py`, `backend/app/core/config.py`. Also changed: the `backend/.env.example` placeholders and the runbook section "Starting and stopping Milvus".

Tests are fakes only: a fake runner, probe, clock and sleep, plus `Settings` validation. They cover:
- Milvus already healthy (left running);
- stopped Milvus started, waited for and stopped after the whole job;
- Docker CLI failure, then Desktop start, then retry, then both stopped;
- never ready (refresh skipped, backup run, Milvus stopped, exit 1);
- Docker start failure;
- no start command configured (nothing started or stopped);
- failed stop fails the job;
- the status `milvus` block;
- the probe returning False on a Milvus error;
- unsafe commands rejected.

Mutation check: 8 defects were each reintroduced and each failed the suite. They were: stopping when Milvus was healthy at start, no Docker fallback, running refresh without Milvus, skipping backup after a Milvus failure, never stopping what was started, skipping the health probe, allowing `down -v`, and allowing a PATH lookup. `tests/test_archive_schedule.py`: 41 passed; full suite 1,347 passed / 3 skipped, coverage 93.4% / 90.4%; ruff, format, bandit and `git diff --check` clean.

Not run: Docker Desktop start from WSL (`docker.exe desktop start`, Desktop 4.37+) and the real compose up/down through Task Scheduler. The reviewer will check them on the laptop. Both tasks stay Disabled.
