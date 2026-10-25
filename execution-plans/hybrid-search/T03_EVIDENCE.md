# T03 catalogue evidence - 2026-10-25

Status: **Awaiting review** in [PR #18](https://github.com/SumukhaK/open-source-projectFinder/pull/18), not accepted or merged. This is T03 only. The PR's current full head SHA and required CI run are authoritative in GitHub; this file cannot embed its own commit SHA.

## Scope and prerequisites

- Branch: `codex/hybrid-t03-catalogue`, cut from latest `origin/main` at `487cc52c54c6b03e553f183a1e5764fd50c77899`.
- Verified merged prerequisites: T00/PR #13 (`6dc4233797bc00d2b71fb2c0311574dc55bd5763`) and T01/PR #15 (`7f94e2f5c8b0e68905dba367c584b4f74d98c175`) are ancestors of the base. T02/PR #16 is also merged as `e4000764c97b3648ec0b08fe42989ee8d2e56463`.
- Four production files: central `config.py`, new `archive_store.py`, new shared `sqlite_runtime.py`, and `scripts/milvus_probe.py` importing that gate. No auth store/migration, API route, dependency lock, CI gate or security exception changes.
- Only three catalogue tables: repositories, document revisions and chunks. Numeric IDs remain stable across names/restarts; full names need not be unique. Metadata uses an object-shaped JSON column rather than adding unconsumed policy/cache columns. No run/task/lease/partition tables.
- Pending/published/superseded documents and a same-repository active pointer are representable. T08 will implement readiness checks and SQL/Milvus publication; setting a SQL pointer here is not evidence that vectors exist. Chunk keys are persisted/unique; deterministic key generation belongs to the later chunk/publication tasks.
- Ruling: add only path/lock settings used by this slice; corpus caps, credentials, retention, scheduling and model/vector settings remain with their owning tasks. No pending product policy is activated.
- Ruling: refuse non-POSIX opening and non-private existing directories/files instead of changing operator permissions or trying to infer Windows ACL protection. New files/directories are 0600/0700. This archive remains a single Linux-host component.
- Ruling: the existing WAL version function and eight version cases moved verbatim to backend core/tests. The probe re-exports the imported function for existing imports; its remaining tests and CPU/GPU logic are unchanged. Direct script invocation from another directory is checked without loading the SDK.

## Runtime and real WAL result

All catalogue tests and WAL-enable evidence used the existing WSL interpreter `/home/sumukha/reporadar-worker-venv/bin/python`: **Python 3.11.17**, **`sqlite3.sqlite_version == "3.53.1"`**, `wal_is_fixed == True`. Platform: Ubuntu WSL2, kernel `6.18.54.1-microsoft-standard-WSL2`, x86_64. Database fixtures live under Linux `/tmp`, not the Windows-mounted checkout. No system Python/SQLite, venv interpreter, applications, WSL settings, driver or Docker state was changed.

A disposable database exercised the actual `ArchiveStore(Settings(...))` initialization/connection/migration path. Results:

```json
{
  "python": "3.11.17",
  "sqlite3.sqlite_version": "3.53.1",
  "wal_is_fixed": true,
  "journal_mode": "wal",
  "busy_timeout_ms": 1200,
  "reader_before": 1,
  "reader_during_writer_commit": 1,
  "reader_new_transaction": 2,
  "truncate_checkpoint": [0, 0, 0],
  "integrity_check": "ok",
  "reopened_ids": [101, 202],
  "schema_version": 1,
  "foreign_key_check": [],
  "directory_mode": "0700",
  "database_wal_shm_modes": "0600",
  "auth_database_created": false,
  "temporary_database_removed": true
}
```

The system `/usr/bin/python3` was queried read-only: Python 3.14.4 links SQLite **3.46.1** and the same shared `wal_is_fixed` returns **False**. Unit tests substitute this version and assert the catalogue refuses both new initialization (before creating even a directory) and connections to an already-WAL catalogue. No alternate gate, bypass or Python-version inference exists.

Reproduce the real catalogue WAL test from repository root using the worker interpreter:

```sh
PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 /home/sumukha/reporadar-worker-venv/bin/python -B -m pytest backend/tests/test_archive_store.py -q -s -k real_wal -p no:cacheprovider --basetemp /tmp/reporadar-t03-wal-verification
```

The test prints the linked SQLite version and exercises reader snapshot -> concurrent writer commit -> new transaction -> truncate checkpoint -> integrity check -> reopen. It uses only synthetic records. The separate one-off JSON above additionally records file modes, timeout, auth non-creation and cleanup. Local raw logs are ignored under `reports/t03/`.

## TDD and verification

Commands below run from the isolated repository root in WSL; `python` and `ruff` mean `/home/sumukha/reporadar-worker-venv/bin/python` and its adjacent `ruff`. All results are dated 2026-10-25. Pytest commands use `PYTHONDONTWRITEBYTECODE=1`, `HF_HUB_OFFLINE=1`, `-p no:cacheprovider`, and a fresh Linux `/tmp/reporadar-t03-*` basetemp.

| Step | Command / assertions | Actual result |
| --- | --- | --- |
| Baseline | `python -B -m pytest backend/tests scripts/tests -q` | Exit 0, 182 passed in 6.61s; one inherited Starlette/httpx deprecation warning |
| RED settings | `python -B -m pytest backend/tests/test_archive_store.py -q` | Exit 1, 6 expected failures: missing central path/timeout, invalid file paths accepted, auth aliases/hardlinks accepted |
| RED catalogue | `python -B -m pytest backend/tests/test_archive_store.py -q -k 'migration_is_idempotent or private_directory or unpatched or unknown_database or existing_shared'` against the interface-only skeleton | Exit 1, 6 expected assertion failures: empty schema, non-private modes and missing refusals. The earlier broader skeleton run also encountered missing-table errors; those are not claimed as assertion-based RED. |
| GREEN initial catalogue | `python -B -m pytest backend/tests/test_archive_store.py backend/tests/test_sqlite_runtime.py scripts/tests/test_milvus_probe.py -q` | Exit 0, 63 passed |
| Additional RED path safety | `python -B -m pytest backend/tests/test_archive_store.py -q -k 'sidecars_cannot_overwrite or requires_a_filename'` | Exit 1, 5 expected failures: archive sidecar/auth overlap and directory-only DB paths accepted |
| GREEN focused | Same three focused test files | Exit 0, 74 passed in 2.32s |
| Full regression/coverage | `python -B -m pytest backend/tests scripts/tests -q --cov=backend/app --cov-branch --cov-report=term-missing --cov-report=json:reports/t03/backend-coverage.json` | Exit 0, **222 passed** in 14.00s; same inherited warning |
| Coverage policy | `python scripts/quality.py coverage reports/t03/backend-coverage.json` | Exit 0, **97.8% combined / 95.3% branches**; required 90/80 unchanged |
| Lint | `ruff check backend scripts --no-cache` | Exit 0, all checks passed |
| Format | `ruff format --check backend scripts --no-cache` | Exit 0, 26 files already formatted |
| SAST | `bandit -r backend/app -q -f json -o reports/t03/bandit.json` | Exit 0, no findings |

Coverage includes catalogue migration/reopen, transaction rollback/connection closing, migration DDL rollback and retry, uniqueness/foreign keys, cross-repository revision rejection, metadata/vector state constraints, chunk cascade, private files/sidecars, unknown/future database rejection, auth byte preservation, unpatched runtime refusal and the real WAL path. Catalogue combined coverage is 95%; central settings and the shared gate are 100%. Unit tests do not simulate a real disk-full/power-loss event.

The final fresh-context reviewer could not run because its model usage limit was reached. No paid upgrade, retry or model change was made. An author review of the complete diff and connected callers found and corrected the path-sidecar alias bug (with RED/GREEN) and documentation UTF-8/status drift. This is not independent trusted acceptance; that review remains required on the final PR head.

No dependencies were added or changed. Required remote CI still audits both Python locks and npm, tests the mobile client/E2E, and scans secrets. The existing node-forge exception remains unchanged and expires 2026-11-01; any resulting gate failure must be reported, not waived. Local mobile/export, fresh dependency audits and full-history secret scanning are delegated to that unchanged required CI, not claimed as local passes.

## Migration, compatibility and rollback

See [backend operator instructions](../../backend/README.md#archive-catalogue-t03-awaiting-review). Explicit opt-in initialization creates a new private catalogue; normal auth/API startup stays unchanged. `PRAGMA application_id` identifies this DB and `PRAGMA user_version` advances with atomic DDL. Repeated migration/reopen preserves IDs/content. Unknown schemas and future versions fail closed. A failed initial migration leaves no partial tables/version markers and can be retried; no reset/downgrade path exists.

On rollback, stop any catalogue consumer, revert the code and retain the catalogue plus any WAL/SHM. Auth data requires no migration or rollback. Use SQLite's backup API for a live snapshot; copying only a live main DB may omit committed WAL data. Encryption, suppression-aware restore, raw files and retention are later tasks; this slice implements none of those policies.

Official sources checked: [SQLite WAL and WAL-reset fix](https://www.sqlite.org/wal.html#walreset), [SQLite backup API](https://www.sqlite.org/backup.html), [Python 3.11 transaction control](https://docs.python.org/3.11/library/sqlite3.html#transaction-control). Existing documented release thresholds were preserved rather than inventing a second safety check.

## Handoff limits

No real GitHub data, models, Milvus operations, public serving, scheduled worker, paid service, next task, system-library changes, PR acceptance or merge. Disk/power-failure and sustained concurrency/load are not certified by these synthetic tests. T04 and other dependent tasks must wait for trusted exact-head acceptance, passing required checks and merge into main. The private runtime is local evidence; deployment/CI runtimes must independently satisfy the same linked-SQLite gate.
