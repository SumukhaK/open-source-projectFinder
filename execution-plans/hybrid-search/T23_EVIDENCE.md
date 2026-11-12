# T23 weekly host scheduling and operator status

Status: **Awaiting review.** Implemented by Claude on the owner's instruction (2026-11-12). It needs an independent review before merge. **No scheduled task has been imported or enabled, and no real scheduled run has happened**; see "Not run".

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
- **Steps.** Weekly runs `refresh` then `backup`; daily runs `retire`. Each is `python -m app.workers.archive <step>` with its defaults, so `refresh` keeps `--cap 0` (D1). Backup still runs after a failed refresh (it is a consistent export on its own); the job exits 1 if any step exited non-zero. Per-step timeouts: refresh 6 h, backup 1 h, retire 2 h; Task Scheduler's limits are 8 h / 3 h.
- **One instance.** Task Scheduler `IgnoreNew` per task, plus a private `schedule.lock` (`flock`, non-blocking) beside the catalogue across both tasks. An overlapping launch runs nothing, logs `overlap` and exits 1. The archive writer lease is unchanged and still guards manual commands.
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

## Not run

- **No Windows import, dry run or enable.** This session has no Windows host. The templates were checked as XML only, not by Task Scheduler. The handbook's GREEN step (a bounded manual launch and a scheduler dry run on the laptop) is pending and needs the owner: import disabled, run the dry-run command from the runbook, read `status`, then decide on enabling.
- No real refresh, retire or backup was run by the scheduler. The archive commands themselves are unchanged.

## Limits

- A sleeping, switched-off or signed-out laptop does not run the jobs; they catch up when Windows is next up and the owner is signed in.
- The jobs do not start Docker Desktop or the GPU Milvus stack. `refresh` and `retire` fail with a sanitized error if Milvus is down; `backup` does not need it. Keeping Milvus running for the 22:00 daily sweep costs host RAM (T18 saw `vmmem` at the 6 GB cap); the owner may prefer to start Milvus only for the weekly window, which would leave the daily sweep failing on other days. This needs an owner decision before enabling.
- With `--cap 0`, every weekly refresh ends `partial` (`cap`) by design.
- `status` reflects only scheduled (or `schedule run`) launches, not commands run directly with `app.workers.archive`.
- Trigger times are local; the runbook checks the Windows time zone is India Standard Time. The run identity is UTC-pinned either way.

## Operator and rollback notes

See [infra/scheduler/README.md](../../infra/scheduler/README.md) for import, dry run, enable/disable, status, retry and credentials. No migration. Rollback: `Unregister-ScheduledTask` both tasks and revert the code; `schedule-log.jsonl` and `schedule.lock` can be deleted.
