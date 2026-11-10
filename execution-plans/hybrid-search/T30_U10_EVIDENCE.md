# T30 U10: cursor/digest domain separation

Date: 2026-11-10. Status: awaiting review; not accepted or merged.
Branch: `codex/hybrid-t30-u10-digest-separation`.
Base main: `d90fab154c8b8ddd38bbfd29e4cf5f5578dd12f0`.
Isolated worktree: `E:/OpenSourceProjectFinder-u10`.
The owner explicitly pulled U10 forward before T29; U11 waits for U10's merge.

## Defect and change

Reproduced on current main: `CursorCodec.digest(data)` produced the same HMAC
as signing the identical cursor body. Substituting that digest as the signature
was accepted. This proves missing domain separation, not an end-to-end account
bypass: the pager retains its binding and snapshot checks.

Reviewed T14 evidence and [PR #49](https://github.com/SumukhaK/open-source-projectFinder/pull/49)
(merged as `5d1b404ff8a0ea650a5f411c3d60d88f8d697c5d`). Its body records
review fixes; GitHub returned no formal review or inline review entries. T30 U10
records the deferred separation issue.

Only the shared digest calculation changes: HMAC-SHA256 over `b"digest:" + data`.
Cursor signing continues over the base64url body, whose alphabet cannot contain
the colon in that prefix. The domains cannot overlap. Both idea and filter callers
use the corrected helper. No configuration, dependency, API or storage changes.
Runtime and route callers were inspected but need no edits. No worker, archive
publication/content/index, Milvus or T19 files changed.

## RED and GREEN

Windows, Python 3.11.9 / SQLite 3.45.1, 2026-11-10. Commands ran from the worktree
with `PYTHONPATH=backend`, using the existing
`E:/OpenSourceProjectFinder/backend/.venv/Scripts/python.exe` (shown as `python`).

- RED, before production edits:
  `python -m pytest backend/tests/test_fused_cursor.py -q -k "separate_from_cursor_signature or cannot_authenticate"`
  -> **2 failed, 59 deselected**. Equality assertion failed; substituting a digest
  signature did not raise `CursorInvalid`.
- GREEN/regression:
  `python -m pytest backend/tests/test_fused_cursor.py backend/tests/test_archive_api.py backend/tests/test_hybrid_search.py -q`
  -> **126 passed**. Covers digest stability, separation, substitution rejection,
  round trips, tampering, expiry and account/filter binding. The privacy test also
  captures DEBUG logs and asserts the raw idea is absent from logs, cursor payload
  and stored snapshot.
- `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:reports/backend-coverage.json`
  -> **1080 passed, 65 skipped**, 82.69 s.
- `python scripts/quality.py coverage reports/backend-coverage.json`
  -> **93.3% combined, 90.1% branches**, unchanged gate passed.
- `python -m ruff check backend scripts` -> passed.
- `python -m ruff format --check backend scripts` -> 76 files already formatted.
- `python -m bandit -r backend/app -q` -> passed, no findings.
- `git diff --check` -> passed.

One existing Starlette/httpx deprecation warning. No dependencies or gates changed.

## Operations and limits

A rollout or rollback may invalidate in-flight cursor bindings (five-minute TTL).
Restart the search for a fresh first page; no persistent data migration or deletion
is needed. In-memory snapshots are already lost on process restart.

Fakes only; no real application provider calls, models, Docker, WSL or emulator.
The 65 Windows platform/runtime skips remain; Linux WAL-backed store paths were
not run locally. CI supplies Linux verification. No device/server performance
claim. No other T30 item was implemented. U11 must wait for U10 to merge.
