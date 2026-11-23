import sqlite3
from pathlib import Path

import pytest
from app.core.config import Settings
from app.workers import state_sync
from pydantic import SecretStr


class FakeHub:
    """In-memory stand-in for the subset of HfApi the sync uses."""

    def __init__(self, files=None, fail_download=False):
        self.files = dict(files or {})
        self.uploads = []
        self.fail_download = fail_download

    def file_exists(self, repo_id, filename, *, repo_type):
        assert repo_type == "dataset"
        return filename in self.files

    def hf_hub_download(self, repo_id, filename, *, repo_type, local_dir):
        assert repo_type == "dataset"
        if self.fail_download:
            raise OSError("network down")
        target = Path(local_dir) / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.files[filename])
        return str(target)

    def upload_file(
        self, *, path_or_fileobj, path_in_repo, repo_id, repo_type, commit_message
    ):
        assert repo_type == "dataset"
        data = Path(path_or_fileobj).read_bytes()
        self.files[path_in_repo] = data
        self.uploads.append((repo_id, path_in_repo))


def make_db(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
        db.executemany("INSERT INTO t VALUES (?)", [(r,) for r in rows])
    return path


def read_rows(path):
    with sqlite3.connect(path) as db:
        return [r[0] for r in db.execute("SELECT v FROM t ORDER BY v")]


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        database_path=str(tmp_path / "data" / "auth.sqlite3"),
        archive_database_path=tmp_path / "data" / "archive" / "catalogue.sqlite3",
        archive_content_path=tmp_path / "data" / "archive" / "content",
        state_sync_repo="owner/reporadar-state",
        state_sync_token=SecretStr("hf_test"),
    )


def db_bytes(tmp_path, name, rows):
    return make_db(tmp_path / "remote" / name, rows).read_bytes()


def test_restore_downloads_auth_and_catalogue_when_missing(settings, tmp_path):
    hub = FakeHub(
        {
            "auth.sqlite3": db_bytes(tmp_path, "a.sqlite3", ["alice"]),
            "catalogue.sqlite3": db_bytes(tmp_path, "c.sqlite3", ["repo"]),
        }
    )

    restored = state_sync.restore(settings, hub)

    assert restored == ["auth.sqlite3", "catalogue.sqlite3"]
    assert read_rows(settings.database_path) == ["alice"]
    assert read_rows(settings.archive_database_path) == ["repo"]


def test_restore_never_overwrites_local_files(settings, tmp_path):
    make_db(Path(settings.database_path), ["local"])
    hub = FakeHub({"auth.sqlite3": db_bytes(tmp_path, "a.sqlite3", ["remote"])})

    assert state_sync.restore(settings, hub) == []
    assert read_rows(settings.database_path) == ["local"]


def test_restore_skips_files_the_dataset_does_not_hold(settings):
    assert state_sync.restore(settings, FakeHub()) == []
    assert not Path(settings.database_path).exists()


def test_restore_fails_closed_when_download_fails(settings, tmp_path):
    hub = FakeHub(
        {"auth.sqlite3": db_bytes(tmp_path, "a.sqlite3", ["x"])}, fail_download=True
    )

    with pytest.raises(OSError):
        state_sync.restore(settings, hub)
    assert not Path(settings.database_path).exists()


def test_restore_is_a_no_op_without_a_repo(tmp_path):
    settings = Settings(_env_file=None, database_path=str(tmp_path / "auth.sqlite3"))
    hub = FakeHub({"auth.sqlite3": b"ignored"})

    assert state_sync.restore(settings, hub) == []


def test_snapshot_uploads_a_consistent_copy_only_when_changed(settings, tmp_path):
    make_db(Path(settings.database_path), ["alice"])
    hub = FakeHub()

    digest = state_sync.snapshot(settings, hub, last_digest=None)
    assert hub.uploads == [("owner/reporadar-state", "auth.sqlite3")]
    copy = tmp_path / "copy.sqlite3"
    copy.write_bytes(hub.files["auth.sqlite3"])
    assert read_rows(copy) == ["alice"]

    assert state_sync.snapshot(settings, hub, last_digest=digest) == digest
    assert len(hub.uploads) == 1

    make_db(Path(settings.database_path), ["bob"])
    assert state_sync.snapshot(settings, hub, last_digest=digest) != digest
    assert len(hub.uploads) == 2


def test_snapshot_never_uploads_the_catalogue(settings, tmp_path):
    make_db(Path(settings.database_path), ["alice"])
    make_db(Path(settings.archive_database_path), ["repo"])
    hub = FakeHub()

    state_sync.snapshot(settings, hub, last_digest=None)

    assert [path for _, path in hub.uploads] == ["auth.sqlite3"]


def test_snapshot_waits_for_a_database(settings):
    hub = FakeHub()

    assert state_sync.snapshot(settings, hub, last_digest=None) is None
    assert hub.uploads == []


def test_interval_is_bounded():
    with pytest.raises(ValueError):
        Settings(_env_file=None, state_sync_interval_seconds=5)


class FailingHub(FakeHub):
    def upload_file(self, **kwargs):
        raise OSError("hub down")


def test_run_keeps_going_after_a_failed_upload(settings, capsys):
    make_db(Path(settings.database_path), ["alice"])
    waits = []

    state_sync.run(settings, FailingHub(), sleep=waits.append, rounds=2)

    assert waits == [300, 300]
    out = capsys.readouterr().out
    assert out.count('"ok": false') == 2
    assert "hf_test" not in out


def test_main_is_disabled_without_a_repo(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("STATE_SYNC_REPO", raising=False)

    assert state_sync.main(["restore"]) == 0
    assert "state_sync_disabled" in capsys.readouterr().out


def test_main_restore_exits_non_zero_on_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STATE_SYNC_REPO", "owner/reporadar-state")
    monkeypatch.setenv("STATE_SYNC_TOKEN", "hf_secret_value")
    make_db(tmp_path / "remote.sqlite3", ["x"])
    hub = FakeHub(
        {"auth.sqlite3": (tmp_path / "remote.sqlite3").read_bytes()},
        fail_download=True,
    )
    monkeypatch.setattr(state_sync, "_hub", lambda settings: hub)

    assert state_sync.main(["restore"]) == 1
    out = capsys.readouterr().out
    assert "state_sync_restore_failed" in out
    assert "hf_secret_value" not in out


def test_main_restore_succeeds(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STATE_SYNC_REPO", "owner/reporadar-state")
    monkeypatch.setattr(state_sync, "_hub", lambda settings: FakeHub())

    assert state_sync.main(["restore"]) == 0
    assert '"restored": []' in capsys.readouterr().out
