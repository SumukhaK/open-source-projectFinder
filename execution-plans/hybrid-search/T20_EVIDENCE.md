# T20 suppression and retirement

In plain terms: T20 cleans **our own local copy** of repository data, never anything on GitHub. When an archived repository becomes unsafe, our stored copy is removed: its README files on the laptop, its catalogue rows and its Milvus vectors. Unsafe means private, gone (404), archived, legally blocked, licence no longer allowed, or removed on the owner's request. Expired content (no push in 365 days) is removed the same way. It is hidden from search first, unsafe repositories are remembered on a content-free "do not store" list kept outside backups, and favourites and offline backups are not touched.

Status: **Awaiting review.** Implemented by Claude on the owner's instruction (2026-11-11), relayed through the project thread. It needs an independent review before merge.

- Branch: `codex/hybrid-t20-retirement`
- Base: `18b8632a137ce27079bb06869117a4c87ae1a7d9` (`origin/main`; T10 `ab2582d` and T19 `393726f`/`43f5db9` merged)
- Worktree: `E:\OpenSourceProjectFinder-t20` (the unrelated dirty main checkout was not used)
- Fakes only: no GitHub, Milvus, model, Docker or real catalogue run. No backup tool was installed and no backup destination was created.

## Scope delivered

Production files: 5 (`archive_store.py`, new `services/archive_retirement.py`, new `workers/retire.py`, `workers/archive.py`, `services/eligibility.py`).

- **Migration 7** rebuilds `archive_suppressions` (SQLite cannot alter a CHECK) with reasons `not_public`, `archived`, `not_found`, `identity_mismatch`, `licence`, `blocked` and `operator`, copying existing rows. Previous code refuses schema 7.
- **Logical suppression first.** `suppress()` appends to the ledger, then upserts the catalogue row, which T10 serving already filters on. Repeating the same decision is a no-op, so per-request serving checks don't grow the ledger. `EligibilityService._suppress` now goes through it, so serving-time suppressions reach the ledger too. `ingest_one` refuses a suppressed repository (`IneligibleRepository("suppressed")`).
- **Content-free ledger outside backups.** `suppression-ledger.jsonl` sits beside the catalogue file actually in use (resolved from `PRAGMA database_list`, not a guessed path). It is append-only, `O_APPEND`, fsynced on every write, a private regular file (0600, no symlink or hard link) and ASCII JSON. Each line holds only `v`, `repo_id`, `action`, `reason` and `at`. A torn final line is ignored; any other malformed line fails closed. `reapply()` makes the catalogue match the current ledger. It runs at the start of every sweep (repairing a crash between the ledger append and the catalogue write), and T22 can use it after a restore.
- **Bounded, idempotent purge.** It runs under `publication_writer` (the OS writer lock plus a fenced lease):
  1. In one write transaction: re-check the decision (still suppressed, or the active revision is unchanged for a non-suppression purge), clear the active revision, and upsert cleanup tombstones keeping `MAX(generation)`.
  2. Delete vectors in batches.
  3. Unlink content files no other repository's document references.
  4. Delete document, chunk and repository rows.

  A failure at any step leaves the repository unserved and the next call finishes the job.
- **Daily sweep** (`retire`, D4 order):
  1. Finish purging already-suppressed repositories.
  2. Re-check known repositories by numeric ID. Not-public, 404 (`not_found`, ambiguous, never "deleted"), identity mismatch, archived and 451 (`blocked`) are suppressed and purged. A licence missing or not on the D2 list is suppressed as `licence` and purged. Past the 365-day window, or a fork, is purged without suppression. An unparseable `pushed_at` or a protocol error is only counted as an issue.
  3. Re-check suppressed IDs not decided in this sweep and lift those that are public and eligible again, except `operator`.

  Credential failure, quota/5xx and a broad 403 stop the sweep with nothing removed. `--remove-repo-id` records an `operator` suppression (D4(3)). The sweep refuses to start unless the allowlist is exactly D2.
- **Retention (D3).** `sweep_unreferenced_files` deletes content files no document references once they're older than 30 days; this covers superseded revisions, whose rows T08 reconcile already deletes, and any file a crashed purge left. `compact_runs` deletes content-free run history older than 90 days. It keeps the run holding `MAX(fence)` and every backfill run (its admission cap lives in the run), skips live leases, and re-points repository tombstones to the kept run, so no generation high-water mark is lost.

## RED evidence

The tests were written alongside the implementation, so RED is shown by mutation. Each defect below was put back into the finished code, its test run with `python -m pytest backend/tests/test_archive_retirement.py -k <test>` (Windows, Python 3.11.9, 2026-11-11), and the code restored:

| Defect restored | Result |
| --- | --- |
| Purge drops tombstones (generation high-water mark lost) | `test_purge_then_republish...` failed: `assert 1 > 1` (generation 1 reused) |
| No stale-decision guard | `test_stale_purge_decision...` failed: `DID NOT RAISE PurgeAborted` |
| Serving not stopped before vector deletes | `test_partial_cleanup_never_serves...` failed: the active hit was still served |
| Shared content files deleted | `test_shared_content_files_survive...` failed |
| Compaction may delete the `MAX(fence)` run | `test_run_compaction...` failed: `assert 0 == 4` |
| Broad 403 treated as a removal | `test_credential_quota_5xx_and_403...[forbidden]` failed |
| Credential failure treated as `not_found` | `...[credential]` failed |
| 404 recorded as `not_public` (ambiguity lost) | `test_repo_404_is_ambiguous...` failed |
| Expired content suppressed instead of purge-only | `test_cutoff_boundary...[366-True]` failed |
| Suppressed IDs never lifted | `test_suppressed_repository_is_lifted...` failed: `assert 0 == 1` |
| Ingest ignores suppression | `test_ingest_refuses...` failed: `DID NOT RAISE` |
| Retire runs without the D2 gate | `test_sweep_refuses_a_non_d2_allowlist...` failed |
| Ledger not written (catalogue only) | ledger restart and eligibility tests failed: `KeyError` |
| Repeated suppression grows the ledger | `test_repeated_suppression...` failed: `assert 3 == 1` |
| Migration 7 absent | `test_licence_change...` failed (the `licence` reason was rejected) |

The required RED list is covered: public-to-private, archive/cutoff boundary (364 vs 366 days), missing README vs repository 404, credential outage (plus quota, 5xx and 403), repeated purge, old vectors (every retained revision), stale file references (shared files kept, unreferenced old files swept), purge then republish (generation > 1, IDs disjoint from the retired set), and the ledger surviving a restart (a new ledger instance plus `reapply` onto a catalogue whose suppression rows were deleted, simulating a restore).

New migration tests in `test_archive_store.py`: v6→v7 keeps suppression rows and accepts the new reasons while rejecting others, and previous code refuses v7. Four existing store/run tests that hard-coded `user_version == 6` now compare against `len(MIGRATIONS)`. The `test_archive_content.py` fixture commits after building the catalogue, because migration 7's row copy opens an implicit transaction there.

## GREEN and full verification

| Check | Platform | Result |
| --- | --- | --- |
| `pytest backend/tests/test_archive_retirement.py` | Windows 3.11.9 | 27 passed |
| Affected suites (retirement, store, runs, content, worker, eligibility, backfill, refresh, publication) | WSL Python 3.11.17 / SQLite 3.53.1 | 371 passed, 0 skipped |
| `pytest backend/tests scripts/tests --cov=backend/app --cov-branch` | WSL | **1206 passed, 2 skipped** |
| `scripts/quality.py coverage` | WSL | 93.2% combined / 90.2% branches (gate 90/80) |
| `ruff check` / `ruff format --check` | WSL | passed / 81 files formatted |
| `bandit -r backend/app` | Windows and WSL | no findings, no `nosec` |
| `git diff --check` | Windows | clean |

Windows baseline: the full Windows suite has 4 failures unrelated to T20 (`test_archive_reader_requires_its_own_credential`, `test_worker_settings_refuse_bad_limits_and_have_no_implicit_licences`, `test_favourite_limit_missing_repository_and_provider_failure`, `test_workers_ai_profile_fails_closed_without_credentials`). They fail identically on unmodified `origin/main` code with the same command and interpreter, and pass in WSL, so they are an environment artefact of this Windows host.

## Operator and rollback notes

```sh
/home/sumukha/reporadar-worker-venv/bin/python -m app.workers.archive retire --limit 1000
/home/sumukha/reporadar-worker-venv/bin/python -m app.workers.archive retire --remove-repo-id 123
```

- Manual only. D7's daily ~22:00 Asia/Kolkata schedule is T23's job.
- `stop_reason`:
  - `finished`: the sweep completed.
  - `credential`, `rate_limit`, `forbidden`: stopped with nothing removed; fix the cause and rerun.
- `issues` counts aborted purges and non-decisive responses.
- Each phase reads at most `--limit` repositories, so one sweep makes at most twice that many metadata requests.
- The sweep builds the normal worker runtime (embedding adapter and Milvus), because purges delete vectors.
- **Migration 7 is forward-only.** Take a consistent SQLite backup first. Reverting only the code makes older code refuse schema 7; restore the pre-upgrade snapshot instead.
- **Purges are not reversible.** A purged repository returns only through a new ingest after its suppression is lifted. Do not delete or edit `suppression-ledger.jsonl`. It is the authority T21/T22 must keep outside backups and reapply on restore.
- **Backups are not erased.** A purge does not remove content already in an offline backup. D5 limits backups to 7 days, and a restore must reapply the current ledger before use.

## Limits and deferred work

- No real sweep has run. GitHub responses, Milvus deletes and file I/O are exercised with fakes and real SQLite only.
- Not owned by T20:
  - Scheduling and the operator status route belong to T23.
  - Backup exclusion of the ledger belongs to T21.
  - Restore-time reapplication belongs to T22.
- Repositories already pending in a refresh or backfill run may still be attempted. Ingest refuses them as `suppressed`, and serving never shows them, because suppression is checked before ingest and filtered at serving.
- **Narrow race:** an ingest that passed its suppression check just before a new suppression can still publish. Serving stays blocked by the suppression row, and the next sweep purges it again.
- `sweep_unreferenced_files` walks the content directory on each call (marked `shortcut:` in code). That is acceptable up to the D1 10k pilot; index files by age if the corpus grows.
- The ledger is append-only, with no compaction yet. Each line is about 90 bytes, and a decision is appended only when it changes.
