# T19 weekly refresh

Status: **T19b awaiting review.** T19a (safe generation protocol) is merged as `393726f` (PR #83). T19b adds the manual `refresh` worker command: known-ID reconciliation, recent discovery, a rotating full-window sweep, conditional reads, metadata-only scalar updates and real attempt/complete status.

- Branch: `codex/hybrid-t19b-refresh`
- Base: `9065f660da3b4182b5086644e9e81e0db6ec4f0f` (`origin/main`, T19a merge). Main then advanced to `71c02edd` (T30 U10, PR #85); the branch was rebased onto it with only the tracker history resolved, and the full verification below was re-run on the rebased tree.
- PR: [#87](https://github.com/SumukhaK/open-source-projectFinder/pull/87) (open, not merged)
- Worktree: `E:\OpenSourceProjectFinder-t19b` (the unrelated dirty main checkout was not used)

## T19b scope delivered

- `backend/app/workers/refresh.py` adds one manual `Refresh` run and `python -m app.workers.archive refresh [--sweep-buckets N] [--cap N]`. The run identity is the most recent Saturday 22:00 UTC boundary, so a stopped or partial run resumes in place; running the same boundary again after completion is idempotent.
- Known IDs: every row in `archive_repositories` is reconciled by numeric ID every run, even without a new push.
- Recent discovery: search covers `[last completed boundary - 48h, due]`; the first run falls back to `[due - 7 days - 48h, due]`.
- Sweep: one 28-day bucket of the rolling `[due - 365 days, due]` window per run (default), with `--sweep-buckets` 1-14. The bucket index advances only when the run finishes; the next week's run retries the bucket of a capped or partial run, so no coverage is skipped (see review fixes).
- New admissions: `--cap` 0-1000 (default 0) bounds repositories not yet in the catalogue; known IDs are always reconciled (see review fixes).
- Conditional reads: `load_cached_repository` rebuilds ETag/Last-Modified state only from metadata written as `payload_version: 2`. A 304 metadata/README response reuses the stored body; a README 304 never fetches the blob. Legacy or inconsistent metadata falls back to a full read and is upgraded on the next unchanged pass.
- Metadata-only changes: `upsert_repository_metadata` updates `full_name`, description, topics, language, stars, `pushed_at`, licence/visibility flags and validators in place. Stars or other non-semantic scalar changes make no embedding calls; a model/chunker/semantic change still re-embeds.
- Removed README: a 404 after verified metadata publishes the metadata-only overview and retires the old README chunks through the existing safe publication/reconcile path.
- Superseded revisions: `RevisionSuperseded` is a typed `PublicationContractError`. A refresh catches it, runs one bounded `reconcile`, retries the repository once, and otherwise leaves the row `pending` with reason `superseded` and stops the run `incomplete`/partial. It never reports the run as a `dependency` failure for this case.
- Generation-1 guard (T19a review U19): `with_generation` always recomputes chunk identities, including generation 1, so staging salted chunks against a generation-1 document raises `PublicationContractError`.
- Status: the JSON summary exposes `last_attempt_at`, `last_complete_at`, `last_completed_boundary`, `coverage` (`complete`/`partial`), `stop_reason`, known/discovered/repository counts, published/unchanged/failed/pending counts, skipped reasons, bytes and request buckets. A resumed run retries repositories left `failed` by an earlier attempt; a completed boundary is not re-run.
- No scheduler in Uvicorn, no `pushed_at`-only content hash, no whole-corpus re-embedding, no search-absence deletion, no token rotation, no parallel workers, no real GitHub/Milvus/model/Docker run and no new migration.

## T19b RED evidence

Platform: WSL, `/home/sumukha/reporadar-worker-venv/bin/python`, Python 3.11.17, SQLite 3.53.1. Fake HTTP, fake model and fake Milvus only.

1. Generation-1 guard. Temporarily restoring the old `if generation == 1: return prepared` short-circuit:

```sh
cd /mnt/e/OpenSourceProjectFinder-t19b
/home/sumukha/reporadar-worker-venv/bin/python -m pytest \
  backend/tests/test_archive_publication.py -q -k staging_rejects_chunks_salted
# exit 1: Failed: DID NOT RAISE PublicationContractError
```

After restoring the recompute, the same selection passed (5 passed with the superseded tests).

2. Superseded retry. Temporarily removing the `except RevisionSuperseded` branch:

```sh
/home/sumukha/reporadar-worker-venv/bin/python -m pytest \
  backend/tests/test_archive_refresh.py -q -k superseded
# exit 1: 2 failed; stop_reason was "dependency" instead of "finished"/"incomplete"
```

After restoring the branch, both tests pass.

3. Resume/idempotency. Before the failed-row retry and completed-run guard:

```sh
/home/sumukha/reporadar-worker-venv/bin/python -m pytest \
  backend/tests/test_archive_refresh.py -q -k "resume_retries or idempotent"
# exit 1: test_resume_retries... failed (the failed row was not retried);
# test_second_manual_run... raised ValueError: run is missing or completed
```

After the fixes, both pass.

## T19b GREEN and full verification

Platform: WSL, `/home/sumukha/reporadar-worker-venv/bin/python`, Python 3.11.17, SQLite 3.53.1. Fake HTTP, fake model and fake Milvus only. The WSL VM initially refused to start with `ERROR_NO_SYSTEM_RESOURCES` (T30 U18); verification used a temporary 1 GB WSL memory limit, and the owner's 6 GB/2 GB config was restored afterwards.

| Check | Command | Result |
| --- | --- | --- |
| Focused archive suites | `python -m pytest backend/tests/test_archive_refresh.py backend/tests/test_archive_worker.py backend/tests/test_archive_content.py backend/tests/test_archive_publication.py backend/tests/test_archive_index.py backend/tests/test_archive_backfill.py -q` | exit 0: `276 passed` |
| Full backend suite | `python -m pytest backend/tests -q` | exit 0: `1134 passed, 2 skipped` |
| Full backend + scripts suite with coverage | `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:reports/backend-coverage.json -q` | exit 0: `1171 passed, 2 skipped` |
| Coverage gate | `python scripts/quality.py coverage reports/backend-coverage.json` | exit 0: `93.3% combined; 90.2% branches` (gate: 90% combined, 80% branches) |
| Ruff check | `python -m ruff check backend scripts` | exit 0: `All checks passed!` |
| Ruff format | `python -m ruff format --check backend scripts` | exit 0: `78 files already formatted` |
| Bandit | `python -m bandit -r backend/app -f json -o reports/bandit.json` | exit 0: 0 findings |
| Whitespace check | native Windows `git diff --check` | exit 0 |
| Windows cross-check | full backend suite on the available Python 3.11.9 / SQLite 3.45.1 venv | exit 0: `1069 passed, 67 skipped` (not the required worker runtime; the WSL result above is authoritative) |

Changed production files: `backend/app/services/archive_content.py`, `backend/app/services/archive_index.py`, `backend/app/services/archive_publication.py`, `backend/app/workers/archive.py` and `backend/app/workers/refresh.py` (five files). Tests and documentation are additional.

## T19b review fixes (2026-11-11)

Claude's review of PR #87 at `d2147352` requested three blockers: an uncapped admission of new repositories, an in-memory discovery walk that restarted from the root after every quota stop, and a missing licence-policy gate on `refresh`. OpenCode started the fixes in this worktree and stopped before finishing or committing them. **Claude completed the fixes** on the owner's instruction (2026-11-11), keeping OpenCode's work, and committed them as `3de2941`. `origin/main` `47525dc` was then merged in (no rebase or force-push).

- **Admission cap.** `refresh --cap N` (0-1000, default 0) admits at most N repositories that are not already in `archive_repositories`. Known IDs are always reconciled and never count. The count is stored in the run state in the same SQLite transaction as the claim, so a resume can never exceed the cap. A cap stop is `partial`, advances no watermark and leaves the boundary resumable. `--cap 0` reconciles known IDs, makes no search requests and stops with `cap`, so a skipped discovery is never recorded as a finished boundary. The summary reports `cap`, `admitted` and `unread_partitions`.
- **Durable discovery.** Recent discovery and each sweep bucket walk the T16/T17 `archive_partitions`/`archive_tasks`/`archive_backfill_pages` checkpoints with `archive_backfill_partition_limit`, as `backfill.py` does. IDs are ingested page by page. A page saved before a stop is reused on resume, so no search is repeated. Split parents are promoted through `finish_completed_parents`, a module function extracted unchanged from `Backfill` and shared by both workers, so a finished refresh can release a run that contains splits.
- **Sweep rotation.** The next run starts after the latest finished run's index, or retries the `sweep_start` bucket of an unfinished run.
- **Licence gate.** `refresh` checks `backfill_license_policy_ok` (exactly the D2 list) before building a runtime, as `backfill` does.
- **Retry comment.** A `failed` row is retried on every resume, not once; the docstring now says so.

RED (mutation, Windows Python 3.11.9, 2026-11-11). Each defect was restored in the fixed code, its test run, and the code restored:

| Defect restored | Test | Result |
| --- | --- | --- |
| Saved page reused without its record (OpenCode WIP crash) | `test_resume_reuses_a_saved_page_that_needs_a_split` | 1 failed: `UnboundLocalError: ... 'record'` |
| Admission count not persisted (in-memory counter) | `test_cap_holds_across_a_resume_without_repeating_searches`, `test_cap_admits_exactly_cap_new_repositories` | 2 failed: `'finished' == 'cap'` |
| Off-by-one, admits cap-1 (OpenCode WIP) | `test_cap_admits_exactly_cap_new_repositories` | 1 failed: `assert 1 == 2` |
| Sweep index advanced on a cap stop (OpenCode WIP) | `test_cap_admits_exactly_cap_new_repositories` | 1 failed: `'sweep_index' not in {...}` |
| Refresh licence gate removed (PR head) | `test_refresh_refuses_a_non_d2_allowlist_before_any_request` | 1 failed: runtime built with a non-D2 allowlist |
| Split parents never promoted | `test_resume_reuses_a_saved_page_that_needs_a_split` | 1 failed: `ValueError: run still has incomplete partitions` |

New tests also cover `--cap 0` (known IDs reconciled, zero search requests) and the next week's run retrying the capped bucket. Existing refresh tests that are not about the cap now pass an explicit `refresh_cap=CAP`.

GREEN (Windows, Python 3.11.9 / SQLite 3.45.1, after merging `47525dc`):

- `python -m pytest backend/tests/test_archive_refresh.py backend/tests/test_archive_backfill.py -q` → 62 passed; refresh alone 29 passed.
- `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:reports/backend-coverage.json` → **1112 passed, 67 skipped**.
- `python scripts/quality.py coverage reports/backend-coverage.json` → 92.5% combined / 89.3% branches (gate 90/80).
- `ruff check backend scripts` passed; `ruff format --check` 78 files already formatted; `bandit -r backend/app -q` no findings; `git diff --check` clean.

The WSL worker venv was unavailable: WSL refused to start with `Wsl/Service/CreateVm/HCS/ERROR_NO_SYSTEM_RESOURCES` at about 3.9 GB free host RAM (T30 U18). `.wslconfig` was not changed. The 67 Windows skips are the WAL-backed/Linux-only paths; the required Linux CI run on this PR is the authoritative check for them. Fakes only: no GitHub, Milvus, model, Docker or WSL run.

## T19b operator and rollback notes

- Run from `backend/` with the WSL worker interpreter, private `ARCHIVE_GITHUB_TOKEN`/`MILVUS_TOKEN` and `HF_HUB_OFFLINE=1`:

```sh
/home/sumukha/reporadar-worker-venv/bin/python -m app.workers.archive refresh --sweep-buckets 1 --cap 0
```

- `--cap 0` (default) reconciles known IDs only and stops with `cap`. Any `--cap` above 0 admits new repositories and needs the owner's explicit approval under D1; a 10k pilot is not approved.

- The command is manual only; no scheduler or API route starts it. A second invocation at the same due boundary resumes the same run. A completed boundary returns the stored summary instead of reprocessing.
- `coverage: "partial"` with `stop_reason` (`cap`, `quota`, `rate_limit`, `bytes`, `disk`, `credential`, `dependency`, `partition`, `incomplete`) means the run is unfinished. `last_completed_boundary` and the sweep index advance only on `finished`; retry later with the same command. `retry_at` is a Unix timestamp from the server's reset header or a bounded fallback.
- Rollback: revert the worker code; there is no migration. Refresh rows/state live in the existing additive T17/T18 tables, and `payload_version: 2` metadata is an additive JSON object. Older code ignores the extra metadata keys and never uses the conditional-read path. Do not delete catalogue/vector rows to force a refresh; retry by numeric ID or leave the boundary incomplete.
- No real refresh was run in this task. A real run needs the private catalogue, GPU Milvus, the cached E5 snapshot, the dedicated worker credential and owner approval; inspect the JSON summary and `archive_runs`/`archive_backfill_repositories` before accepting coverage.

## T19b limits and deferred work

- Conditional 304/ETag reuse, README removal, star-only updates and the sweep boundaries are fake-tested. No real GitHub request, Milvus write, model load or full refresh was performed.
- The refresh does not delete stale, private, deleted, suppressed or expired repositories from the catalogue; T20 owns retention/removal. A known ID that becomes ineligible is reported as `skipped` and remains until that task.
- The summary is operator JSON, not an API/status route. T23 owns host scheduling and operator status.
- `payload_version: 2` stores selected scalar fields, not the full GitHub payload. A legacy v1 row pays one full read and is upgraded; a corrupt/inconsistent row is treated the same way.
- No parallel workers, token rotation, `pushed_at`-only hash, search-absence deletion or whole-corpus re-embedding was added. Schema version remains 6.
- (Resolved) CI at `615dec1`: Backend quality, Mobile quality and E2E, Secret scan and GitGuardian passed. Dependency audit and the aggregate Quality gate failed on four npm advisories for node-forge 1.4.2 (GHSA-6889-vf6x-f3g5, GHSA-w4xr-hqv8-ch44, GHSA-6cv4-p8m7-4r25, GHSA-j8rw-jp99-435v). This diff changes no JavaScript: `mobile/package-lock.json`, `.ci/quality-policy.json`, `scripts/quality.py` and `.github/workflows/quality.yml` are identical to `origin/main`, which was green on 2026-11-10, so the advisory data changed after that run. No exception was added and no gate was lowered; it needs an owner decision (dependency bump or a narrow dated exception) and is not part of T19b. Resolved by PR #88 (node-forge 1.4.3, merged as `47525dc`), which is merged into this branch.

## T19a (merged as `393726f`)

### T19a scope delivered

- Chunk IDs now carry a per-publication generation. `persist_revision` reuses the generation of an existing document row or allocates `max(generation over that repository's documents and tasks) + 1`; `archive_index.with_generation` salts the chunk identity hash only for generations above 1.
- Generation 1 keeps the original unsalted IDs. Existing catalogues, active revisions and pending replays therefore remain valid without re-embedding or rewriting vectors.
- After T17 cleanup retires revision A, a later A→B→A refresh allocates a new generation for A. Its chunk IDs are disjoint from the retired set, so a late Milvus delete for the old IDs cannot remove the new vectors.
- `archive_publication._stage` still quarantines same-generation reuse after a `cleanup` tombstone. It allows only a strictly newer generation and verifies that the prepared chunk identities match the document generation. `_activate` also requires the staged task generation to match the document.
- `archive_tasks.generation` records the generation of a cleanup tombstone. Reconcile keeps the tombstone, as before.
- Migration 6 is additive: it appends `generation INTEGER NOT NULL DEFAULT 1 CHECK (generation >= 1)` to `archive_documents` and `archive_tasks`. Existing rows become generation 1. Previous code refuses schema 6 exactly as it refuses any newer version.
- No scheduler, refresh command, GitHub request, Milvus start, model load, token rotation or parallel worker was added.

### T19a RED / GREEN evidence

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

### T19a full verification

| Check | Command | Result |
| --- | --- | --- |
| Full backend + scripts suite with coverage | `/home/sumukha/reporadar-worker-venv/bin/python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=term-missing --cov-report=json:reports/backend-coverage.json --cov-report=xml:reports/backend-coverage.xml --junitxml=reports/backend-tests.xml -q --no-header` | exit 0: `1145 passed, 2 skipped` |
| Coverage gate | `/home/sumukha/reporadar-worker-venv/bin/python scripts/quality.py coverage reports/backend-coverage.json` | exit 0: `94.5% combined; 91.6% branches` (gate: 90% combined, 80% branches) |
| Ruff check | `/home/sumukha/reporadar-worker-venv/bin/python -m ruff check backend scripts` | exit 0: `All checks passed!` |
| Ruff format | `/home/sumukha/reporadar-worker-venv/bin/python -m ruff format --check backend scripts` | exit 0: `76 files already formatted` |
| Bandit | `/home/sumukha/reporadar-worker-venv/bin/python -m bandit -r backend/app -f json -o reports/bandit.json` | exit 0: 0 findings |
| Whitespace check | native Windows `git diff --check` | exit 0 |

Changed production files: `backend/app/core/archive_store.py`, `backend/app/services/archive_index.py`, `backend/app/services/archive_content.py`, `backend/app/services/archive_publication.py`, `backend/app/workers/archive.py` (five files). Tests and documentation are additional.

Required GitHub CI passed on the pushed branch at `2f1c1986cbaf2c369cf9f90a63ab8cf5c41d797b` ([CI 42780740297](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/42780740297)): Backend quality, Quality gate, Mobile quality and E2E, Dependency audit, Secret scan and GitGuardian all passed. The commit after it is documentation-only.

### T19a migration compatibility evidence

- `test_existing_v5_catalogue_upgrades_to_v6_with_generation_defaults` builds a v5 catalogue, inserts a repository and document, then opens it with the new code. It asserts `user_version = 6`, `generation = 1` for the existing document, and the new `archive_tasks.generation` column.
- `test_previous_code_refuses_the_v6_generation_schema` monkeypatches the migration tuple back to the five v5 migrations and confirms the old code refuses a v6 catalogue with `Archive catalogue schema version is newer than this code`, leaving the file bytes unchanged.
- `test_migration_is_idempotent_and_preserves_stable_ids`, the v1→current upgrade test, the failed-migration rollback test and the existing future-schema refusal test all pass at schema 6.
- The real production migration was not run on the owner's laptop in this task. The migration is exercised by the SQLite catalogue tests on the WSL worker runtime; no real catalogue was opened, copied or changed.

### T19a operator and rollback notes

- Deploy the new worker code with the existing private catalogue. `ArchiveStore` applies migration 6 automatically on the first worker connection; stop other catalogue consumers first and take a consistent SQLite backup as for earlier migrations.
- Migration 6 is forward-only. Reverting only the code after migration makes the older code refuse schema 6, so keep the new code or restore a pre-upgrade consistent snapshot. Do not edit migration 1, delete the catalogue or move a live WAL database to bypass the version check.
- Generation 1 rows are unchanged. No content file or vector rewrite is required for existing revisions.
- If a republish is interrupted, retry the same numeric repository ID. The persisted document row keeps its allocated generation, so the replay is idempotent. A same-generation `cleanup` tombstone still refuses reuse; investigate and complete reconciliation before forcing anything.
- No real refresh run, Docker/Milvus start, model load or GitHub request was performed. The reviewer runs any real refresh on the laptop.

### T19a limits and deferred work

- T19b (this PR) adds the `refresh` command, known-ID reconciliation, recent discovery, the rotating sweep, conditional reads, metadata-only star updates, removed-README handling and attempt/complete status. The T19a statements below describe the earlier PR only.
- A returning A→B→A revision still re-embeds because its semantic hash changed from the intervening revision. T19b adds zero-embedding reuse for unchanged 304 responses; it does not reuse vectors across different semantic revisions.
- The `WriterBusy` misleading “Archive storage failed” message from the T18 real run is unchanged (T30 item); the refresh path uses the same run/lease store.
- `stars:` band splits remain fake-tested only; no real GitHub coverage is claimed.
