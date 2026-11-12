# T22 restore into quarantine and reapply suppression

Status: **Awaiting review.** Implemented by Claude on the owner's instruction (2026-11-12). It needs an independent review before merge. **No real restore has run yet** (see Limits).

In plain terms: `restore` unpacks a backup into a private quarantine folder, checks every hash, the schema and the model, applies today's "do not store" decisions, deletes anything that is suppressed or too old, and, if today's ledger cannot be trusted, re-checks every repository on GitHub. Only then is the quarantine marked ready. `restore --activate` is a separate step: it rebuilds the vectors, reads them back, and only then swaps the restored archive in, keeping the previous one aside.

- Branch: `claude/project-thread-tjty1z` (the session's assigned branch; the plan names `codex/hybrid-t22-restore`)
- Base: `37d056f` (`origin/main`: T21 merged as `5622403`, CLI fix `37d056f`)
- Prerequisites: T21 merged into main. D5 (7-day backups, reapply the current ledger on restore) and D6 (restic) approved 2026-10-29; D6 destination change approved 2026-11-11.

## Scope delivered

Production files: 3.
- New `services/archive_restore.py`: `restore_to_quarantine`, `activate`, `ledger_state`.
- `services/archive_backup.py`: `Restic.restore(snapshot, target)` with a validated snapshot ID (`latest` or hex); `restore_latest` now uses it.
- `workers/archive.py`: `restore [--snapshot ID] [--activate]`, behind the same D2 allowlist gate as `retire`; `quarantined`/`activated` exit 0; `orphan_vectors: failed` exits 1.

Reused rather than rewritten: T21's destination checks, lock and stale-plaintext cleanup; T20's `reapply`, `purge_repository` and the sweep's numeric-ID check (`retire._check_known`); T09's `check_eligibility` and `load_cached_repository`; T08's `load_active_chunks`; `ArchiveStore` for migration and newer-schema refusal.

### `restore` (never touches the live archive)
Under the live writer lock (nothing publishes, purges or backs up meanwhile):
1. T21 destination checks; free-disk check (live archive size plus `ARCHIVE_MIN_FREE_BYTES`, a documented shortcut).
2. Replace any previous `restore-quarantine/`; `restic restore <snapshot>` into it; make the tree 0700/0600 and refuse links or special files.
3. Manifest: one manifest, version 1, catalogue and every file match SHA-256 and size, the tree holds exactly what is listed, content paths are content-addressed, no ledger, model equals the pinned manifest, schema not newer than the code.
4. Catalogue (opened with `ArchiveStore`, which migrates an older schema): integrity check, foreign keys, every referenced file listed, every document's model revision pinned, stored IDs match their rows; backup-era writer leases cleared.
5. Ledger: **trusted** (private, parseable, holds every live suppression) is reapplied exactly. **Missing** or **stale** adds the ledger's and the live catalogue's decisions without lifting any. **Unsafe or unreadable** is refused.
6. Purge inside the quarantine (never Milvus): suppressed repositories, then those whose stored facts fail the archive policy.
7. Missing/stale ledger only: re-check every remaining repository by numeric ID with the T20 rules; new suppressions go to the live ledger. A stop or any inconclusive answer refuses.
8. Checkpoint the catalogue and write `verdict.json` with `ready: true` and its hash. Any failure deletes the quarantine.

### `restore --activate` (API stopped)
Under the live writer lock: require a ready verdict and an unchanged catalogue hash and model; reapply decisions made since the restore and purge again; embed every active chunk, upsert and strongly read back; move the live catalogue (+WAL/SHM) and content to `restore-previous-<UTC>/`, rename the quarantine in (rolled back on a failed rename); then delete vectors of chunks the replaced archive had and the restored one lacks.

Stale caches and cursors: the API's visibility cache (at most 900 s, fresh GitHub reads only) and pagination snapshots (5 minutes) are process-local. Activation requires the API to be stopped, and restarting it clears both. Neither can resurrect suppressed content: the restored catalogue's suppressions are a superset of the live ones, and serving still requires an active revision in the catalogue.

## RED evidence (mutation, Linux, Python 3.13.18, SQLite 3.53.1, 2026-11-12)

The tests were written alongside the code, so RED is shown by removing each safeguard from the finished code, running `pytest backend/tests/test_archive_restore.py`, and restoring the code:

| Safeguard removed | Result | Failing tests |
| --- | --- | --- |
| no ledger reapply at restore | 2 failed, 37 passed | test_private_then_purge_then_older_backup_cannot_resurrect, test_stale_ledger_enforces_live_suppressions_and_rechecks |
| no GitHub recheck for an untrusted ledger | 5 failed, 34 passed | test_github_unavailable_keeps_nothing_and_leaves_live_untouched, test_inconclusive_github_answer_keeps_it_quarantined, test_missing_ledger_requires_a_recheck_by_numeric_id, test_missing_ledger_with_a_public_repository_is_ready_after_recheck |
| GitHub stop ignored | 1 failed, 38 passed | test_github_unavailable_keeps_nothing_and_leaves_live_untouched |
| incomplete recheck accepted | 1 failed, 38 passed | test_inconclusive_github_answer_keeps_it_quarantined |
| manifest not checked | 8 failed, 31 passed | test_corrupt_incomplete_or_mismatched_backup_is_refused |
| live suppressions not merged for a stale ledger | 1 failed, 38 passed | test_stale_ledger_enforces_live_suppressions_and_rechecks |
| no offline expiry | 1 failed, 38 passed | test_expired_repository_is_purged_in_quarantine |
| activation skips the ledger | 1 failed, 38 passed | test_activation_reapplies_decisions_made_after_the_restore |
| swap before the vector rebuild | 7 failed, 32 passed | test_activation_reapplies_decisions_made_after_the_restore, test_failed_orphan_cleanup_is_reported, test_failed_vector_rebuild_leaves_the_live_archive_untouched, test_loaded_model_must_match_to_rebuild, test_orphan_vectors_of_the_replaced_archive_are_deleted, test_private_then_purge_then_older_backup_cannot_resurrect, test_round_trip_restores_the_archive_and_rebuilds_its_vectors |
| verdict hash not checked | 1 failed, 38 passed | test_changed_quarantine_cannot_be_activated |
| loaded model not checked | 1 failed, 38 passed | test_loaded_model_must_match_to_rebuild |
| orphan vectors kept | 2 failed, 37 passed | test_failed_orphan_cleanup_is_reported, test_orphan_vectors_of_the_replaced_archive_are_deleted |
| document model not checked | 1 failed, 38 passed | test_corrupt_incomplete_or_mismatched_backup_is_refused |

Required RED list covered: private then purge then older backup (`test_private_then_purge_then_older_backup_cannot_resurrect`), missing/stale ledger, corrupt/incomplete manifest (15 cases: content/catalogue hash, missing/extra/unlisted file, symlink, no/malformed manifest, version, ledger inside, model, document model, newer schema, identity, not a catalogue), model mismatch (manifest, documents, loaded model), stale cursor/cache (process restart, above), GitHub unavailable (stop, inconclusive answer, no reader).

## GREEN

Linux container, Python 3.13.18 (CI uses 3.11), SQLite 3.53.1, 2026-11-12:
- `pytest backend/tests/test_archive_restore.py`: **39 passed**.
- `pytest backend/tests scripts/tests --cov=backend/app --cov-branch`: **1285 passed, 3 skipped** (restic not installed, POSIX/Windows-only skips); `scripts/quality.py coverage`: 93.3% combined, 90.3% branches, exit 0. `archive_restore.py` alone: 94%.
- `ruff check backend scripts`, `ruff format --check backend scripts`: clean. `bandit -r backend/app`: no issues. `git diff --check`: clean.

## Limits

- **No real restic restore has run.** The fake restic copies the captured staging tree. The real round trip should run on the WSL worker against a throwaway repository (as T21's `test_real_restic_round_trip` does), then one owner-approved restore of the real Drive repository into quarantine (D6's single restore check). The real repository has not been touched.
- **No real activation** against Milvus and the E5 model; the vector rebuild is tested with the fake Milvus and the tiny encoder.
- Activation cannot detect a running API; stopping it is an operator step, documented in the backend README.
- The restored catalogue replaces the live tombstone history. This is safe because activation holds the operation lock (no Milvus IO in flight) and deletes the replaced archive's orphan vectors; a later ingest may reuse a generation the replaced archive had used.
- A trusted-ledger restore does not call GitHub; per-request public validation still applies when serving, and the next `retire` sweep re-checks every repository.

## Operator and rollback notes

- Rollback is a code revert: no migration. A regretted activation is undone by renaming `restore-previous-*` back (API stopped), then running `retire`.
- Delete `restore-previous-*` once satisfied: the T20 sweep does not look inside it.
- Never serve or open a backup in place; always go through `restore`.
