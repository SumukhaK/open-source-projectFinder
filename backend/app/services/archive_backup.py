"""T21 consistent, encrypted, expiring archive backups through restic (D5/D6).

An export takes the writer lock (so no publication, purge or retention runs
meanwhile), copies the catalogue with SQLite's backup API (committed WAL state
included), copies exactly the content files the copied catalogue references
after verifying their hashes, and writes a manifest. restic then encrypts that
staging tree into an owner-provided repository; only a successful restic
snapshot counts as a completed backup. The private plaintext staging tree is
always deleted. The current suppression ledger is never included (T20/T22).

The application never reads the restic password: restic opens the configured
password file itself. The repository is never created here; the operator
initialises it once on the approved external drive.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess  # nosec B404 - fixed argument list, no shell
import uuid
from dataclasses import asdict
from pathlib import Path

from app.core.config import ARCHIVE_BACKFILL_LICENSES
from app.services.archive_retirement import LEDGER_NAME
from app.services.archive_runs import publication_writer
from app.services.embeddings import ModelManifest

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1
RETENTION = "7d"  # D5: encrypted backups are kept at most 7 days
TAG = "reporadar-archive"
RESTIC_TIMEOUT_SECONDS = 3600


class BackupError(Exception):
    """A sanitized backup failure; never contains secrets or file contents."""


class Restic:
    """Minimal restic runner; arguments are fixed lists, never a shell."""

    def __init__(self, binary, repository, password_file, *, run=subprocess.run):
        self.binary, self.repository, self.password_file = (
            binary,
            repository,
            password_file,
        )
        self._run = run

    @classmethod
    def from_settings(cls, settings):
        return cls(
            settings.archive_backup_restic,
            settings.archive_backup_repository,
            settings.archive_backup_password_file,
        )

    def _call(self, *args, cwd=None):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("RESTIC_")
        }
        env["RESTIC_REPOSITORY"] = self.repository
        env["RESTIC_PASSWORD_FILE"] = self.password_file
        try:
            result = self._run(  # nosec B603 - fixed argv, configured binary
                [self.binary, *args],
                env=env,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=RESTIC_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BackupError(f"restic {args[0]} could not run") from error
        if result.returncode != 0:
            # restic output is not echoed: keep errors free of paths/secrets.
            raise BackupError(f"restic {args[0]} failed (exit {result.returncode})")
        return result.stdout

    def initialised(self):
        try:
            self._call("cat", "config")
        except BackupError:
            return False
        return True

    def backup(self, staging):
        output = self._call(
            "backup", "--json", "--tag", TAG, "--host", "reporadar", ".", cwd=staging
        )
        for line in reversed(output.splitlines()):
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get("message_type") == "summary" and message.get("snapshot_id"):
                return message["snapshot_id"]
        raise BackupError("restic backup reported no snapshot")

    def forget_expired(self):
        self._call("forget", "--tag", TAG, "--keep-within", RETENTION, "--prune")

    def restore_latest(self, target):
        self._call("restore", "latest", "--tag", TAG, "--target", str(target))

    def check(self):
        self._call("check")


def _catalogue_path(connect):
    with connect() as db:
        path = db.execute("PRAGMA database_list").fetchone()[2]
    if not path:
        raise BackupError("backups require a file-backed catalogue")
    return Path(path)


def _check_destination(settings, catalogue, restic, device):
    if (
        not settings.archive_backup_repository
        or not settings.archive_backup_password_file
    ):
        raise BackupError("backup repository and password file must be configured")
    secret = Path(settings.archive_backup_password_file)
    try:
        info = secret.lstat()
    except OSError as error:
        raise BackupError("backup password file is missing") from error
    if not stat.S_ISREG(info.st_mode):
        raise BackupError("backup password file must be a regular file")
    if os.name == "posix" and info.st_mode & 0o077:
        raise BackupError("backup password file must be private (0600)")
    repository = Path(settings.archive_backup_repository)
    if not repository.is_dir():
        # Never created here: only the owner-approved drive may hold backups.
        raise BackupError("backup repository does not exist; initialise it first")
    if device(repository) == device(catalogue.parent):
        raise BackupError(
            "backup repository is on the catalogue's volume; use the external drive"
        )
    if not restic.initialised():
        raise BackupError("backup repository is not an initialised restic repository")


def _device(path):
    return os.stat(path).st_dev


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _referenced(db):
    return sorted(
        {
            (path, sha256)
            for row in db.execute(
                "SELECT raw_path, raw_sha256, normalized_path, normalized_sha256 "
                "FROM archive_documents"
            )
            for path, sha256 in ((row[0], row[1]), (row[2], row[3]))
            if path is not None
        }
    )


def export_backup(
    connect, content, settings, *, now, restic=None, disk_free=None, device=_device
):
    """Create one encrypted restic snapshot and expire old ones; return a summary."""
    restic = restic or Restic.from_settings(settings)
    catalogue = _catalogue_path(connect)
    _check_destination(settings, catalogue, restic, device)
    staging = catalogue.parent / f"backup-staging-{uuid.uuid4().hex}"
    staging.mkdir(mode=0o700)
    try:
        with publication_writer(connect):
            with connect() as db:
                referenced = _referenced(db)
            needed = sum(
                os.path.getsize(content.root / path)
                for path, _ in referenced
                if (content.root / path).is_file()
            ) + sum(
                os.path.getsize(path)
                for path in (catalogue, Path(str(catalogue) + "-wal"))
                if path.exists()
            )
            free = (disk_free or (lambda: shutil.disk_usage(staging).free))()
            if free - needed < settings.archive_min_free_bytes:
                raise BackupError("not enough free disk to stage the backup")
            copy = staging / "catalogue.sqlite3"
            target = sqlite3.connect(copy)
            try:
                # The backup API copies a consistent snapshot, WAL included.
                with connect() as db:
                    db.backup(target)
                files = []
                for path, sha256 in _referenced(target):
                    data = content.read(path, sha256)  # verifies the hash
                    destination = staging / "content" / path
                    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    destination.write_bytes(data)
                    files.append({"path": path, "sha256": sha256, "bytes": len(data)})
                version = target.execute("PRAGMA user_version").fetchone()[0]
            finally:
                target.close()
        manifest = {
            "version": MANIFEST_VERSION,
            "created_at": now.isoformat(),
            "schema_version": version,
            "catalogue": {"sha256": _sha256(copy), "bytes": copy.stat().st_size},
            "files": files,
            "model": asdict(ModelManifest.load()),
            "policy": {
                "licence_allowlist": sorted(ARCHIVE_BACKFILL_LICENSES),
                "retention": RETENTION,
                "suppression_ledger": "excluded; reapply the current ledger on restore",
            },
        }
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8"
        )
        if (staging / LEDGER_NAME).exists():
            raise BackupError("the suppression ledger must never enter a backup")
        snapshot = restic.backup(staging)
        restic.forget_expired()
        return {
            "result": "exported",
            "snapshot": snapshot,
            "files": len(files),
            "bytes": manifest["catalogue"]["bytes"] + sum(f["bytes"] for f in files),
            "schema_version": version,
        }
    finally:
        # Never keep plaintext: the staging tree goes on success and failure.
        shutil.rmtree(staging, ignore_errors=True)


def verify_backup(settings, scratch_parent, *, restic=None):
    """Restore the latest snapshot privately and check every manifest hash."""
    restic = restic or Restic.from_settings(settings)
    target = Path(scratch_parent) / f"backup-verify-{uuid.uuid4().hex}"
    target.mkdir(mode=0o700)
    try:
        restic.check()
        restic.restore_latest(target)
        manifests = list(target.rglob(MANIFEST_NAME))
        if len(manifests) != 1:
            raise BackupError("restored snapshot has no single manifest")
        root = manifests[0].parent
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        if _sha256(root / "catalogue.sqlite3") != manifest["catalogue"]["sha256"]:
            raise BackupError("restored catalogue hash does not match the manifest")
        for entry in manifest["files"]:
            if _sha256(root / "content" / entry["path"]) != entry["sha256"]:
                raise BackupError("restored content hash does not match the manifest")
        if any(path.name == LEDGER_NAME for path in target.rglob("*")):
            raise BackupError("restored snapshot contains the suppression ledger")
        return {
            "result": "verified",
            "files": len(manifest["files"]),
            "schema_version": manifest["schema_version"],
        }
    finally:
        shutil.rmtree(target, ignore_errors=True)
