# T19 weekly refresh

Status: **T19a awaiting review.** This PR delivers only the T17 follow-up safe generation protocol. The T19b manual `refresh` worker command (known-ID reconciliation, recent discovery, rotating full-window sweep, conditional reads and status) is deliberately not started.

- Branch: `codex/hybrid-t19-weekly-refresh`
- Base: `7fec65a322cecac587ec8722eb1774155e191c76` (`origin/main`, T18 Phase B evidence)
- PR: [#83](https://github.com/SumukhaK/open-source-projectFinder/pull/83) (open, not merged)
- Verified tree: merge commit `e56bd441ae5f08d8c428171c9518afeb1d9c959c` (merges `origin/main` `d90fab154c8b8ddd38bbfd29e4cf5f5578dd12f0`, PR #82). The full-suite, coverage, ruff and bandit results below were re-run on that merged tree.
- Worktree: `E:\OpenSourceProjectFinder-t19` (the unrelated dirty main checkout was not used)

## Scope delivered (T19a only)

- Chunk IDs now carry a per-publication generation. `persist_revision` reuses the generation of an existing document row or allocates `max(generation over that repository's documents and tasks) + 1`; `archive_index.with_generation` salts the chunk identity hash only for generations above 1.
- Generation 1 keeps the original unsalted IDs. Existing catalogues, active revisions and pending replays therefore remain valid without re-embedding or rewriting vectors.
- After T17 cleanup retires revision A, a later A→B→A refresh allocates a new generation for A. Its chunk IDs are disjoint from the retired set, so a late Milvus delete for the old IDs cannot remove the new vectors.
- `archive_publication._stage` still quarantines same-generation reuse after a `cleanup` tombstone. It allows only a strictly newer generation and verifies that the prepared chunk identities match the document generation. `_activate` also requires the staged task generation to match the document.
- `archive_tasks.generation` records the generation of a cleanup tombstone. Reconcile keeps the tombstone, as before.
- Migration 6 is additive: it appends `generation INTEGER NOT NULL DEFAULT 1 CHECK (generation >= 1)` to `archive_documents` and `archive_tasks`. Existing rows become generation 1. Previous code refuses schema 6 exactly as it refuses any newer version.
- No scheduler, refresh command, GitHub request, Milvus start, model load, token rotation or parallel worker was added.

## RED / GREEN evidence

Platform: WSL, `/home/sumukha/reporadar-worker-venv/bin/python`, Python 3.11.17, SQLite 3.53.1. Fake HTTP, fake model and fake Milvus only.

RED (before implementation):

```sh
cd /mnt/e/OpenSourceProjectFinder-t19
/home/sumukha/reporadar-worker-venv/bin/python -m pytest backend/tests/test_archive_worker.py -q --no-header -k readme_revert_after_retirement
# exit 1: 1 failed. sqlite3.OperationalError: no such column: generation
```

The same worker test exercises the complete A→B→A path: publish A, publish B, reconcile retires A (document deleted, `cleanup` tombstone retained), then republish A. It asserts the active revision returns to A, the new chunk IDs are disjoint from the retired IDs, the new document generation is greater than 1, and the task stage is `published`.

RED for the migration contract:

```sh
/home/sumukha/reporadar-worker-venv/bin/python -m pytest backend/tests/test_archive_store.py -q --no-header -k "v5_catalogue or previous_code_refuses"
# exit 1: v5 catalogue stayed at user_version 5; previous code did not refuse the v6 schema
```

GREEN (focused archive suites):

```sh
/home/sumukha/reporadar-worker-venv/bin/python -m pytest \
  backend/tests/test_archive_worker.py backend/tests/test_archive_store.py \
  backend/tests/test_archive_content.py backend/tests/test_archive_publication.py \
  backend/tests/test_archive_fencing.py backend/tests/test_archive_index.py \
  backend/tests/test_archive_runs.py -q --no-header
# exit 0: 305 passed
```

GREEN (all archive, backfill and hybrid-runtime suites):

```sh
/home/sumukha/reporadar-worker-venv/bin/python -m pytest \
  backend/tests/test_archive_*.py backend/tests/test_backfill_io.py \
  backend/tests/test_hybrid_runtime.py -q --no-header
# exit 0: 580 passed, 1 skipped
```

## Full verification

| Check | Command | Result |
| --- | --- | --- |
| Full backend + scripts suite with coverage | `/home/sumukha/reporadar-worker-venv/bin/python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=term-missing --cov-report=json:reports/backend-coverage.json --cov-report=xml:reports/backend-coverage.xml --junitxml=reports/backend-tests.xml -q --no-header` | exit 0: `1145 passed, 2 skipped` |
| Coverage gate | `/home/sumukha/reporadar-worker-venv/bin/python scripts/quality.py coverage reports/backend-coverage.json` | exit 0: `94.5% combined; 91.6% branches` (gate: 90% combined, 80% branches) |
| Ruff check | `/home/sumukha/reporadar-worker-venv/bin/python -m ruff check backend scripts` | exit 0: `All checks passed!` |
| Ruff format | `/home/sumukha/reporadar-worker-venv/bin/python -m ruff format --check backend scripts` | exit 0: `76 files already formatted` |
| Bandit | `/home/sumukha/reporadar-worker-venv/bin/python -m bandit -r backend/app -f json -o reports/bandit.json` | exit 0: 0 findings |
| Whitespace check | native Windows `git diff --check` | exit 0 |

Changed production files: `backend/app/core/archive_store.py`, `backend/app/services/archive_index.py`, `backend/app/services/archive_content.py`, `backend/app/services/archive_publication.py`, `backend/app/workers/archive.py` (five files). Tests and documentation are additional.

## Migration compatibility evidence

- `test_existing_v5_catalogue_upgrades_to_v6_with_generation_defaults` builds a v5 catalogue, inserts a repository and document, then opens it with the new code. It asserts `user_version = 6`, `generation = 1` for the existing document, and the new `archive_tasks.generation` column.
- `test_previous_code_refuses_the_v6_generation_schema` monkeypatches the migration tuple back to the five v5 migrations and confirms the old code refuses a v6 catalogue with `Archive catalogue schema version is newer than this code`, leaving the file bytes unchanged.
- `test_migration_is_idempotent_and_preserves_stable_ids`, the v1→current upgrade test, the failed-migration rollback test and the existing future-schema refusal test all pass at schema 6.
- The real production migration was not run on the owner's laptop in this task. The migration is exercised by the SQLite catalogue tests on the WSL worker runtime; no real catalogue was opened, copied or changed.

## Operator and rollback notes

- Deploy the new worker code with the existing private catalogue. `ArchiveStore` applies migration 6 automatically on the first worker connection; stop other catalogue consumers first and take a consistent SQLite backup as for earlier migrations.
- Migration 6 is forward-only. Reverting only the code after migration makes the older code refuse schema 6, so keep the new code or restore a pre-upgrade consistent snapshot. Do not edit migration 1, delete the catalogue or move a live WAL database to bypass the version check.
- Generation 1 rows are unchanged. No content file or vector rewrite is required for existing revisions.
- If a republish is interrupted, retry the same numeric repository ID. The persisted document row keeps its allocated generation, so the replay is idempotent. A same-generation `cleanup` tombstone still refuses reuse; investigate and complete reconciliation before forcing anything.
- No real refresh run, Docker/Milvus start, model load or GitHub request was performed. The reviewer runs any real refresh on the laptop.

## Limits and deferred work

- T19b is not implemented: there is no `refresh` command, no known-ID reconciliation loop, no recent-discovery boundary, no rotating full-window sweep, no conditional ETag/If-None-Match reuse, no metadata-only star update, no removed-README handling and no last-attempt/last-complete status. Those remain the next PR.
- A returning revision is re-embedded in T19a because its semantic hash changed from the intervening revision. Content-aware reuse and zero-embedding 304 handling belong to T19b.
- The `WriterBusy` misleading “Archive storage failed” message from the T18 real run is unchanged (T30 item); T19a does not share that refresh path.
- `stars:` band splits remain fake-tested only; no real GitHub coverage is claimed.
