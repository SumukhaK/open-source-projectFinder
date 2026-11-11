"""T21 encrypted backups: fake and real restic, real SQLite and content files."""

import json
import os
import secrets
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.services import archive_backup as backup
from app.services.archive_retirement import LEDGER_NAME, SuppressionLedger
from app.services.archive_runs import RunStore, WriterBusy, publication_writer
from app.workers import archive as worker
from test_archive_worker import NOW, REPO_ID, harness, make_settings

PASSWORD_ENV = "RESTIC_PASSWORD"


class FakeRestic:
    """Records what restic would encrypt; never runs a process."""

    def __init__(self, *, initialised=True, fail_backup=False):
        self._initialised = initialised
        self.fail_backup = fail_backup
        self.snapshots = []
        self.forgets = 0

    def initialised(self):
        return self._initialised

    def backup(self, staging):
        if self.fail_backup:
            raise backup.BackupError("restic backup failed (exit 1)")
        copy = Path(staging).parent / f"captured-{len(self.snapshots)}"
        shutil.copytree(staging, copy)
        self.snapshots.append(copy)
        return f"snap{len(self.snapshots)}"

    def forget_expired(self):
        self.forgets += 1


def configured(tmp_path, **overrides):
    repository = tmp_path / "external-drive" / "repo"
    repository.mkdir(parents=True)
    password = tmp_path / "keys" / "restic-password"
    password.parent.mkdir()
    password.write_text(secrets.token_urlsafe(32), encoding="ascii")
    if os.name == "posix":
        password.chmod(0o600)
    laptop = tmp_path / "laptop"
    laptop.mkdir()
    settings = make_settings(
        tmp_path,
        archive_database_path=laptop / "catalogue.sqlite3",
        archive_content_path=laptop / "content",
        archive_backup_repository=str(repository),
        archive_backup_password_file=str(password),
        **overrides,
    )
    state = harness(tmp_path, settings=settings)
    assert worker.ingest_one(state.runtime, REPO_ID, now=NOW)["result"] == "published"
    return state


def distinct(path):
    # The test tree lives on one volume; pretend the "drive" is separate.
    return "external" if "external-drive" in str(path) else "laptop"


def export(state, restic, **kwargs):
    kwargs.setdefault("device", distinct)
    return backup.export_backup(
        state.connect,
        state.runtime.content,
        state.settings,
        now=NOW,
        restic=restic,
        **kwargs,
    )


def staging_dirs(state):
    return list(state.settings.archive_database_path.parent.glob("backup-staging-*"))


def sha256(path):
    return backup._sha256(path)


def test_export_contains_catalogue_referenced_files_and_manifest_only(tmp_path):
    state = configured(tmp_path)
    ledger = SuppressionLedger.for_catalogue(state.connect)
    ledger.append(999, "suppress", "not_found", 1.0)
    restic = FakeRestic()

    summary = export(state, restic)

    assert summary["result"] == "exported" and summary["snapshot"] == "snap1"
    assert restic.forgets == 1
    tree = restic.snapshots[0]
    names = {
        path.relative_to(tree).as_posix() for path in tree.rglob("*") if path.is_file()
    }
    manifest = json.loads((tree / backup.MANIFEST_NAME).read_text(encoding="utf-8"))
    files = {"content/" + entry["path"] for entry in manifest["files"]}
    assert names == {"catalogue.sqlite3", backup.MANIFEST_NAME} | files
    assert files and LEDGER_NAME not in {Path(name).name for name in names}
    assert manifest["catalogue"]["sha256"] == sha256(tree / "catalogue.sqlite3")
    for entry in manifest["files"]:
        assert sha256(tree / "content" / entry["path"]) == entry["sha256"]
    assert manifest["policy"]["retention"] == "7d"
    assert manifest["model"]["dimensions"] == 384
    assert staging_dirs(state) == []


def test_snapshot_includes_committed_wal_rows(tmp_path):
    state = configured(tmp_path)
    path = state.settings.archive_database_path
    writer = sqlite3.connect(path)
    assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute(
        "INSERT INTO archive_repositories(repo_id, full_name) VALUES(77, 'acme/wal')"
    )
    writer.commit()
    assert Path(str(path) + "-wal").stat().st_size > 0
    restic = FakeRestic()
    try:
        export(state, restic)
    finally:
        writer.close()

    copy = sqlite3.connect(restic.snapshots[0] / "catalogue.sqlite3")
    try:
        assert copy.execute(
            "SELECT full_name FROM archive_repositories WHERE repo_id=77"
        ).fetchone() == ("acme/wal",)
    finally:
        copy.close()


def test_live_writer_lease_blocks_the_export(tmp_path):
    state = configured(tmp_path)
    store = RunStore(state.connect)
    store.claim(store.create_run("refresh", NOW), "live-refresh")
    restic = FakeRestic()

    with pytest.raises(WriterBusy):
        export(state, restic)

    assert restic.snapshots == [] and staging_dirs(state) == []


def test_publication_or_purge_cannot_run_while_files_are_copied(tmp_path):
    state = configured(tmp_path)
    original = state.runtime.content.read
    blocked = []

    def read(path, sha256):
        with pytest.raises(WriterBusy):
            with publication_writer(state.connect):
                pass
        blocked.append(path)
        return original(path, sha256)

    state.runtime.content.read = read
    export(state, FakeRestic())

    assert blocked


def test_missing_referenced_file_fails_without_a_snapshot(tmp_path):
    state = configured(tmp_path)
    with state.connect() as db:
        raw = db.execute("SELECT raw_path FROM archive_documents").fetchone()[0]
    (state.runtime.content.root / raw).unlink()
    restic = FakeRestic()

    with pytest.raises(Exception, match="(?i)content|missing|exist|found"):
        export(state, restic)

    assert restic.snapshots == [] and staging_dirs(state) == []


def test_disk_limit_refuses_before_staging_anything(tmp_path):
    state = configured(tmp_path)
    restic = FakeRestic()

    with pytest.raises(backup.BackupError, match="free disk"):
        export(state, restic, disk_free=lambda: 0)

    assert restic.snapshots == [] and staging_dirs(state) == []


def test_failed_encryption_leaves_no_plaintext_and_no_expiry(tmp_path):
    state = configured(tmp_path)
    restic = FakeRestic(fail_backup=True)

    with pytest.raises(backup.BackupError, match="restic backup failed"):
        export(state, restic)

    assert restic.forgets == 0 and staging_dirs(state) == []


def test_interrupted_export_removes_the_staging_tree(tmp_path):
    state = configured(tmp_path)

    def interrupted(path, sha256):
        raise KeyboardInterrupt

    state.runtime.content.read = interrupted
    restic = FakeRestic()
    with pytest.raises(KeyboardInterrupt):
        export(state, restic)

    assert restic.snapshots == [] and staging_dirs(state) == []


def test_restic_gets_fixed_arguments_and_only_a_password_file(monkeypatch):
    calls = []
    monkeypatch.setenv(PASSWORD_ENV, "must-not-leak")

    def run(argv, **kwargs):
        calls.append((argv, kwargs["env"]))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    restic = backup.Restic("restic", "/drive/repo", "/keys/pw", run=run)
    restic.forget_expired()

    argv, env = calls[0]
    assert argv == [
        "restic",
        "forget",
        "--tag",
        backup.TAG,
        "--keep-within",
        "7d",
        "--prune",
    ]
    assert env["RESTIC_REPOSITORY"] == "/drive/repo"
    assert env["RESTIC_PASSWORD_FILE"] == "/keys/pw"
    assert PASSWORD_ENV not in env


def test_restic_errors_never_echo_its_output():
    def run(argv, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="secret /path detail")

    with pytest.raises(backup.BackupError) as error:
        backup.Restic("restic", "r", "p", run=run).check()

    assert str(error.value) == "restic check failed (exit 1)"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("same_volume", "catalogue's volume"),
        ("uninitialised", "not an initialised"),
        ("missing_repository", "does not exist"),
        ("unconfigured", "must be configured"),
        ("missing_password", "password file is missing"),
    ],
)
def test_destination_refusals(tmp_path, change, message):
    state = configured(tmp_path)
    restic = FakeRestic(initialised=change != "uninitialised")
    device = (lambda path: "same") if change == "same_volume" else distinct
    settings = state.settings
    if change == "missing_repository":
        shutil.rmtree(settings.archive_backup_repository)
    elif change == "unconfigured":
        settings = settings.model_copy(update={"archive_backup_repository": ""})
    elif change == "missing_password":
        Path(settings.archive_backup_password_file).unlink()

    with pytest.raises(backup.BackupError, match=message):
        backup.export_backup(
            state.connect,
            state.runtime.content,
            settings,
            now=NOW,
            restic=restic,
            device=device,
        )

    assert restic.snapshots == []
    assert Path(settings.archive_backup_repository or "x").exists() == (
        change not in ("missing_repository", "unconfigured")
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
def test_non_private_password_file_is_refused(tmp_path):
    state = configured(tmp_path)
    Path(state.settings.archive_backup_password_file).chmod(0o644)

    with pytest.raises(backup.BackupError, match="private"):
        export(state, FakeRestic())


def restic_binary():
    found = shutil.which("restic")
    winget = Path(r"C:\Program Files\WinGet\Links\restic.exe")
    return found or (str(winget) if winget.exists() else None)


@pytest.mark.skipif(restic_binary() is None, reason="restic is not installed")
def test_real_restic_round_trip_is_encrypted_and_verifiable(tmp_path):
    state = configured(tmp_path)
    settings = state.settings.model_copy(
        update={"archive_backup_restic": restic_binary()}
    )
    restic = backup.Restic.from_settings(settings)
    restic._call("init")

    summary = backup.export_backup(
        state.connect,
        state.runtime.content,
        settings,
        now=NOW,
        restic=restic,
        device=distinct,
    )
    verified = backup.verify_backup(settings, tmp_path, restic=restic)

    assert summary["result"] == "exported"
    assert verified == {
        "result": "verified",
        "files": summary["files"],
        "schema_version": summary["schema_version"],
    }
    stored = b"".join(
        path.read_bytes()
        for path in Path(settings.archive_backup_repository).rglob("*")
        if path.is_file()
    )
    assert b"Offline maps for hikers" not in stored
    assert b"acme/compass" not in stored
    assert staging_dirs(state) == []


@pytest.mark.parametrize("inside", ["catalogue", "content"])
def test_repository_inside_the_archive_tree_is_refused(tmp_path, inside):
    state = configured(tmp_path)
    root = (
        state.settings.archive_database_path.parent
        if inside == "catalogue"
        else state.runtime.content.root
    )
    repository = root / "backup-repo"
    repository.mkdir()
    settings = state.settings.model_copy(
        update={"archive_backup_repository": str(repository)}
    )
    restic = FakeRestic()

    with pytest.raises(backup.BackupError, match="outside the archive tree"):
        backup.export_backup(
            state.connect,
            state.runtime.content,
            settings,
            now=NOW,
            restic=restic,
            device=lambda path: str(path),
        )

    assert restic.snapshots == []
