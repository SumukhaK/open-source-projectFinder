# T18 bounded resumable backfill

Status: Phase A implementation in progress. Phase B has not been authorized and no real GitHub request, model load, Docker/Milvus start or application closure was performed.

## Scope and safety

Base: `d6927f4ea8fe18ead3fcff2927ebe4ed62583faf`. Verified prerequisites: T09 `7766744`, T16 `539d02e`, T17 `ca191fc`. Migration 5 is additive and creates the backfill outcome ledger, durable page records and run state; migrations 1–4 are unchanged. The manual command is capped at 1,000 distinct candidate IDs and enforces the approved D2 SPDX list. Its JSON-lines log records only partition queries, search counts, completeness, pages and numeric IDs.

## RED / GREEN

RED: `backend/tests/test_archive_backfill.py` initially failed because `app.workers.backfill` did not exist (19 failures). The tests cover every T18 checkpoint crash/restart boundary, cap, quota/disk/queue/partition/byte bounds, 429 and secondary limits, incomplete search, duplicate IDs, invalid credentials, licence skips and the per-partition log.

GREEN: `E:/OpenSourceProjectFinder-t01/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_archive_backfill.py backend/tests/test_backfill_io.py -q` — 27 passed (Windows fake-only SQL/HTTP/model/Milvus fixtures; no external services).

Full WSL WAL-fixed verification: `/home/sumukha/reporadar-worker-venv/bin/python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-fail-under=90 -q` — 859 passed, 2 skipped, 95.95% combined coverage (Python 3.11.17, SQLite 3.53.1). Ruff check/format and Bandit passed. Native `git diff --check` passed; WSL cannot run Git in this Windows-created worktree because its `.git` worktree pointer contains a Windows path.

## Operator and rollback notes

The command exits cleanly with its persisted retry time rather than sleeping through a long limit. Re-run the same command after that time; it resumes the same durable manual pilot. Reverting migration 5 code must not be followed by opening the catalogue with old code, because old code correctly refuses a newer schema. The real pilot is blocked until the owner replies exactly `T18 real run approved`.
