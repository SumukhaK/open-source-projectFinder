# T18 bounded resumable backfill

Status: Phase A implementation in progress. Phase B has not been authorized and no real GitHub request, model load, Docker/Milvus start or application closure was performed.

## Scope and safety

Base: `d6927f4ea8fe18ead3fcff2927ebe4ed62583faf`. Verified prerequisites: T09 `7766744`, T16 `539d02e`, T17 `ca191fc`. Migration 5 is additive and creates the backfill outcome ledger, durable page records and run state; migrations 1–4 are unchanged. The manual command is capped at 1,000 distinct candidate IDs and enforces the approved D2 SPDX list. Its JSON-lines log records only partition queries, search counts, completeness, pages and numeric IDs.

## RED / GREEN

RED: `backend/tests/test_archive_backfill.py` initially failed because `app.workers.backfill` did not exist (19 failures). The tests cover every T18 checkpoint crash/restart boundary, cap, quota/disk/queue/partition/byte bounds, 429 and secondary limits, incomplete search, duplicate IDs, invalid credentials, licence skips and the per-partition log.

GREEN: `E:/OpenSourceProjectFinder-t01/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_archive_backfill.py backend/tests/test_backfill_io.py -q` — 27 passed (Windows fake-only SQL/HTTP/model/Milvus fixtures; no external services).

Full WSL WAL-fixed verification: `/home/sumukha/reporadar-worker-venv/bin/python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-fail-under=90 -q` — 859 passed, 2 skipped, 95.95% combined coverage (Python 3.11.17, SQLite 3.53.1). Ruff check/format and Bandit passed. Native `git diff --check` passed; WSL cannot run Git in this Windows-created worktree because its `.git` worktree pointer contains a Windows path.

After merging `origin/main` as `4f66fcf`, the Windows regression command passed: 797 passed, 65 skipped, 94.16% combined coverage (Python 3.11.9 / SQLite 3.45.1). A final WSL repeat was unavailable because WSL returned `HCS_E_NO_SYSTEM_RESOURCES`; no WSL setting or application was changed. Required Linux CI remains the final current-head platform check.

## Review fixes (2026-10-31)

Exact-head review of `780c41d` requested five fixes. All are addressed in
`backfill.py`, `archive.py` and their tests; Phase B remains blocked.

1. **Transient vs terminal failures.** `_ingest` lets `LeaseLost` propagate
   (never marking the repository), keeps the credential and rate-limit
   re-raises, marks only a deterministic `IngestError` as `failed`, and treats
   every other exception (embedding/model, Milvus, disk, bugs) as a run stop:
   the repository stays `pending`, `stop_reason` is `dependency`, the lease is
   released without completing the run, and coverage is `partial`. `run` also
   reports `incomplete` when unfinished repositories remain, and completion
   requires no `pending` or `failed` repository.
2. **Cap applies only to new admissions.** `_page` checks the cap only when the
   repository has no row for this run, so a `pending` repository is resumed even
   when `_admitted >= cap`.
3. **Durable accounting.** Cumulative `bytes` and per-bucket `requests` are
   merged into `archive_backfill_state` after every response, loaded at run
   start, enforced against the cumulative byte limit, and reported cumulatively.
   `_save_state` merges instead of replacing, so clearing `retry_at` preserves
   accounting.
4. **Quota stops persist `retry_at`.** The headroom stop writes the retry time
   to `archive_backfill_state`, so an early re-run returns `rate_limit` with
   zero HTTP requests until the reset time.
5. **Allowlist and malformed headers.** `backfill_license_policy_ok` compares
   the allowlist as a set with no duplicates (order-insensitive), and
   `after_response` parses `x-ratelimit-*` in a guarded block. A malformed or
   missing reset value becomes a conservative quota stop with
   `retry_at = now + 60`, so the lease is released rather than leaked.

RED: the eight new tests were run against the previous implementation
(`8 failed, 20 deselected`): a transient embedding failure still reported
`finished`; `LeaseLost` did not propagate; the cap-th pending repository was
lost on resume; accounting restarted at zero; the crossed byte limit reported
`finished`; the quota stop did not persist `retry_at`; malformed headers raised
`ValueError`; and `backfill_license_policy_ok` did not exist.

GREEN: `python -m pytest backend/tests/test_archive_backfill.py -q` — 28
passed. The requested affected suite (`test_archive_backfill`,
`test_backfill_io`, `test_archive_runs`, `test_archive_store`,
`test_archive_worker`) — 92 passed, 57 skipped. Full `backend/tests
scripts/tests` with coverage — 805 passed, 65 skipped; gate 94.1% combined /
91.6% branches. Ruff check/format, Bandit (0 findings) and `git diff --check`
clean. Windows, Python 3.11.9, fake HTTP/model/Milvus; no external service.

## Re-review fixes

The re-review of `62bd75f` found one blocking issue: per-repository GitHub
outcomes that subclass `ArchiveGitHubError` were still treated as an
infrastructure outage, so one deleted or blocked repository stopped every
resume at `dependency` and later repositories were never reached. `_ingest`
now classifies them terminally:

- `RepositoryNotFound` -> `skipped` / `not_found`
- `RepositoryIdentityMismatch` -> `skipped` / `identity_mismatch`
- `ArchiveForbidden` and 451 (`ArchiveRequestError`) -> `skipped` / `forbidden`
- `ArchiveProtocolError`, `BlobNotFound`, `BlobIdentityMismatch` and other
  per-repository request errors -> `failed` / `failed`

Each saves the outcome and checkpoints `outcome_saved`. Credential,
rate-limit, unavailable and `LeaseLost` still propagate; the generic
`except Exception` still leaves the repository pending and stops with
`dependency`.

RED: the new tests against the previous implementation — `5 failed, 28
deselected`: 404, identity mismatch, 403, 451 and a malformed metadata
response all ended `dependency` instead of reaching repo 2.

GREEN: `test_archive_backfill.py` — 33 passed; the requested affected suite —
97 passed, 57 skipped; full `backend/tests scripts/tests` with coverage — 810
passed, 65 skipped; gate 94.1% combined / 91.6% branches. Ruff check/format,
Bandit (0 findings) and `git diff --check` clean.

## Operator and rollback notes

The command exits cleanly with its persisted retry time rather than sleeping through a long limit. Re-run the same command after that time; it resumes the same durable manual pilot. Reverting migration 5 code must not be followed by opening the catalogue with old code, because old code correctly refuses a newer schema. The real pilot is blocked until the owner replies exactly `T18 real run approved`.

A repository recorded as `failed` (a deterministic data-specific or per-repository protocol failure) keeps the run `incomplete` and the command exits 1 on every later invocation until an operator reviews or removes that outcome; the run is intentionally not released as completed. `skipped` outcomes (`not_found`, `identity_mismatch`, `forbidden`) do not block completion.
