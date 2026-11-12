# T21 consistent encrypted backup exports

Status: **Awaiting review.** Implemented by Claude on the owner's instruction (2026-11-11). It needs an independent review before merge. **The real export to the approved destination has not run yet**; see "Real export: pending owner steps".

In plain terms: `backup` makes one encrypted copy of our local archive (the catalogue and its README files) with restic, and `backup --verify` proves that copy can be opened and matches. Copies older than 7 days are deleted on each run. The "do not store" ledger is deliberately left out, so a restore always uses the current one.

- Branch: `codex/hybrid-t21-backup`
- Base: `68d1f19` (`origin/main`, T20 merged as `a454b98`)
- Worktree: `E:\OpenSourceProjectFinder-t21` (the unrelated dirty main checkout was not used)

## Decisions and tool identity

- D5: encrypted backups are kept at most 7 days; a restore reapplies the current ledger. D6: restic.
- **Owner-approved D6 change (2026-11-11):** the destination is a subfolder of the owner's Google Drive for desktop sync folder on `D:` (for example `D:\<drive-sync-folder>\RepoRadar-backup`). The owner signed in and chose the folder. This replaces the offline external drive with an encrypted, off-site sync folder. restic encrypts everything before Drive syncs it. Caveats:
  - Drive Trash keeps deleted pack files for 30 days, so the 7-day expiry is fully effective only once the Trash empties.
  - A synced folder can propagate ransomware; Drive version history mitigates this.
  - The Google account is not recorded anywhere, and nothing else in that folder was read or listed.
- restic was installed by the owner (administrator, `winget install --exact --id restic.restic --scope Machine`, winget-verified installer hash). Recorded identity:
  - `restic version`: `restic 0.19.1 compiled with go1.26.4 on windows/amd64`
  - `C:\Program Files\WinGet\Links\restic.exe` is a symbolic link to `C:\Program Files\WinGet\Packages\restic.restic_Microsoft.Winget.Source_8wekyb3d8bbwe\restic_0.19.1_windows_amd64.exe`
  - SHA-256 (of the resolved target): `b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830`
- Password handling: the application only receives a path (`ARCHIVE_BACKUP_PASSWORD_FILE`). restic opens it via `RESTIC_PASSWORD_FILE`; any inherited `RESTIC_*` variable (for example `RESTIC_PASSWORD`) is stripped from restic's environment. No Claude session reads or prints the real password. The tests generate throwaway passwords in pytest temp folders only.

## Scope delivered

Production files: 3.
- `core/config.py`: `ARCHIVE_BACKUP_REPOSITORY`, `ARCHIVE_BACKUP_PASSWORD_FILE`, `ARCHIVE_BACKUP_RESTIC` (paths only).
- New `services/archive_backup.py`.
- `workers/archive.py`: the `backup [--verify]` CLI. `BackupError` produces a sanitized failure and exit 1; `exported`/`verified` exit 0.

**Export**, in order:
1. Check the destination:
   - repository and password file configured;
   - password file a regular, private (0600 on POSIX) file;
   - repository outside the catalogue/content tree and already existing (never created);
   - on a different volume from the catalogue;
   - an initialised restic repository.
2. Create a private staging folder beside the catalogue.
3. Under `publication_writer` (writer lock plus fenced lease):
   - check free disk (staging bytes plus `ARCHIVE_MIN_FREE_BYTES`);
   - copy the catalogue with SQLite's backup API;
   - copy every content file the copy references, through `ArchiveContentStore.read`, which verifies each SHA-256.
4. Write `manifest.json`: catalogue SHA-256/bytes, each file's path/SHA-256/bytes, the model manifest and the policy (D2 allowlist, `7d`, "ledger excluded"). Refuse if the ledger is somehow present.
5. Run `restic backup --json --tag reporadar-archive --host reporadar .`, then `restic forget --tag reporadar-archive --keep-within 7d --prune`.
6. Always delete the staging folder.

**Verify:** `restic check`, then restore `latest` into a private temporary folder, compare the catalogue and every file with the manifest hashes, refuse if the ledger appears, and delete the restore.

## RED evidence (mutation, Windows Python 3.11.9, 2026-11-11)

The tests were written alongside the code, so RED is shown by restoring each defect into the finished code, running its tests, and restoring the code:

| Defect restored | Result |
| --- | --- |
| No writer lock during the copy | 2 failed: `DID NOT RAISE WriterBusy` (live lease; publication/purge during copy) |
| Live DB file copied instead of the backup API | committed-WAL test failed: `None == ('acme/wal',)` |
| Ledger copied into the backup | manifest-only test failed (`suppression-ledger.jsonl` present) |
| Plaintext staging kept | 3 failed (failed encryption, interruption, missing file) |
| No disk check | disk-limit test failed: `DID NOT RAISE BackupError` |
| Expiry runs even when encryption fails | failed-encryption test failed: `1 == 0` forgets |
| Retention widened to 30 days | 2 failed: `'30d' == '7d'` |
| Inherited `RESTIC_*` variables leak | argument test failed (`RESTIC_PASSWORD` passed through) |
| restic stderr echoed in errors | error test failed (output included in the message) |
| Same-volume repository accepted | refusal test failed |
| Uninitialised repository accepted | refusal test failed |
| Missing repository created silently | refusal test failed |
| Repository inside the catalogue/content tree accepted | 2 failed |

Required RED list covered:
- concurrent publication/purge (live lease, and a writer attempt during the copy);
- missing referenced file;
- disk-full;
- failed encryption;
- interrupted export (KeyboardInterrupt during the copy);
- expiry (fixed `forget` arguments);
- ledger excluded;
- WAL-committed rows present in the snapshot;
- destination refusals (same volume, uninitialised, missing, unconfigured, missing password file, inside the archive tree);
- non-private password file (POSIX only, skipped on Windows).

## GREEN

Windows, Python 3.11.9:
- `pytest backend/tests/test_archive_backup.py`: **18 passed, 1 skipped** (the POSIX permission test).
- That count includes `test_real_restic_round_trip_is_encrypted_and_verifiable`. It ran against the installed restic 0.19.1 with a temporary repository and a throwaway password in the pytest temp folder: `restic init`, export, `verify_backup` (`restic check`, restore, every hash matched). It also asserted that neither the README text nor the repository name appears in plaintext anywhere in the repository files.
- The full Windows suite, ruff, format, bandit (no findings) and `git diff --check` results are in the PR description. The required Linux CI run is authoritative; restic is not installed on CI, so the real round-trip test is skipped there.

## Review fixes (2026-11-11)

An independent review of `3256d62` requested one blocking fix and one optional one. Both are fixed on this branch, with no rebase.

1. **Plaintext left by a killed run (blocking).** `backup-staging-*` and `backup-verify-*` were removed only in `finally`, so a hard kill, power loss or WSL shutdown could leave a plaintext copy of the catalogue and READMEs indefinitely, outside T20's purge.
   - `export_backup` and the CLI's `verify_backup` now hold the writer lock for the whole run. Before creating their own folder, they delete any leftover `backup-staging-<32 hex>` / `backup-verify-<32 hex>` entry directly in that folder.
   - Only those exact names are touched. A symlink is removed as a link and never followed. Nothing outside that parent is touched.
   - Holding the lock for the whole run also means one backup run can never delete another live run's staging. Ingest, refresh and purge wait while a backup runs, which takes seconds at the current archive size.
2. **Expiry failure after a snapshot (optional).** If `restic forget --prune` fails after a successful snapshot, the summary now reports `result: "exported"` with the snapshot ID and `expiry: "failed"`, and the CLI exits 1. A successful run reports `expiry: "done"`.

RED before the fixes (`pytest backend/tests/test_archive_backup.py -k "killed_run or failed_expiry"`): 3 failed.
- The export left both stale trees in place (`assert not True`).
- `verify_backup` had no catalogue lock or cleanup (`unexpected keyword argument 'connect'`).
- A failed `forget` raised instead of reporting the snapshot.

GREEN: `test_archive_backup.py` 21 passed, 1 skipped (the POSIX permission test), including the real restic round trip.

## Real export (2026-11-12)

On the owner's explicit instruction ("cant u do these urself, please go ahead and do it"), Claude did the setup inside WSL. The owner keeps the password in their own password manager; no Claude session read, printed or copied it.

- **Linux restic:** the official `restic_0.19.1_linux_amd64.bz2` from the v0.19.1 GitHub release, checked against the release's `SHA256SUMS` (`sha256sum -c`: OK), decompressed with Python's `bz2` and installed to `/home/sumukha/.local/bin/restic` (0755, no sudo). `restic version`: `restic 0.19.1 compiled with go1.26.4 on linux/amd64`. SHA-256 of the installed binary: `20d4142678d0d95ec11a4759def1b73fd9190abc9ca19e4b62d067c0b387e639`.
- **Password file:** `/home/sumukha/.config/reporadar/restic-password`, written straight from `/dev/urandom` (32 random bytes, base64) with `umask 077`. The directory is 0700. Checked by `stat` only: `-rw------- 45 bytes`. Its contents were never read or printed. The owner copies it into their password manager themselves.
- **Repository:** `restic init` at `/mnt/d/<drive-sync-folder>/RepoRadar-backup` (the owner's Google Drive for desktop sync folder) created repository `29f37fd072`. The ignored `backend/.env` of the worker checkout holds only paths: catalogue, content, repository, password file, restic binary.
- **First `backup`:** snapshot `896c6682`, 3.608 MiB of data. The command then crashed while printing its result (`KeyError: 'stop_reason'`, fixed below). The snapshot itself was complete, and no `backup-staging-*` folder was left.
- **`backup --verify`**, after the fix: `{"result": "verified", "files": 405, "schema_version": 7}`, exit 0, about 4.3 s (restic check, private restore, every hash matched, ledger absent).
- **Second `backup`:** `{"result": "exported", "expiry": "done", "files": 405, "bytes": 3697878, "schema_version": 7, "snapshot": "7265e6f5..."}`, exit 0, about 4.8 s. There are 2 snapshots; both are within the 7-day window, so expiry kept them.
- **Destination contents:** only restic's layout (`config`, `data/`, `index/`, `keys/`, `locks/`, `snapshots/`), 10 files, 1.8 MB on disk. A byte search found neither a repository name from the catalogue nor an SQLite header, so nothing is stored in plaintext. No plaintext staging or verify folder remains beside the catalogue.

### Bug found by the real run: CLI result for backup summaries

`main()` treated every summary without `timings_ms` as a worker run and read `summary["stop_reason"]`. Backup summaries carry `result` instead, so a successful `backup` or `backup --verify` crashed after finishing its work. Fix: keep an existing `result` and fall back to `stop_reason`.
- RED: `test_backup_cli_prints_its_result_and_exits_zero[backup|verify]` failed with `KeyError: 'stop_reason'`.
- GREEN: both pass. The archive worker, backfill, refresh, retirement and backup suites give 159 passed, 1 skipped, plus 1 known Windows-only baseline failure that is unrelated.

## Real export: original plan


The catalogue lives on WSL's Linux filesystem and the destination is `D:`. The simplest safe route, proposed to the owner and **not done**:
1. Install Linux restic inside WSL (needs owner approval).
2. The owner creates a private password file inside WSL with a command that writes random bytes without echoing them (`umask 077`). The owner copies it into their password manager. No Claude session reads it.
3. The owner runs `restic init` once for `/mnt/d/<drive-sync-folder>/RepoRadar-backup`.
4. Set `ARCHIVE_BACKUP_REPOSITORY` and `ARCHIVE_BACKUP_PASSWORD_FILE` in the ignored `.env`, run `backup`, then `backup --verify` once (D6's single restore check).

The alternative, Windows restic reading a staged snapshot via `\\wsl$`, adds a cross-OS path hop. Neither the real repository nor the password file exists yet.

## Operator and rollback notes

- Rollback is a code revert: no migration, and backups never touch the live catalogue.
- If the password file is lost, the backups cannot be opened. Keep a copy in a password manager.
- Backups are never served or opened in place. A restore must go through T22's quarantine, which reapplies the current ledger first.
- Expiry happens only when `backup` runs. Under the Drive destination, deleted pack files stay in Drive Trash for up to 30 days.

## Limits

- No real export to the approved destination has run (pending owner steps above).
- A same-laptop copy is not disaster recovery; the Drive sync is the off-site copy.
- No scheduling (T23) and no restore quarantine (T22).
- restic is not installed in CI, so the real round trip runs only where restic exists.
