import os
import sqlite3
import stat
from pathlib import Path

import pytest
from app.core import archive_store
from app.core.config import Settings
from app.core.store import Store
from pydantic import ValidationError

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Archive catalogue requires a private POSIX filesystem"
)


def settings_for(tmp_path, **overrides):
    return Settings(
        _env_file=None,
        database_path=str(tmp_path / "auth.sqlite3"),
        **{
            "archive_database_path": tmp_path / "private/catalogue.sqlite3",
            **overrides,
        },
    )


def test_archive_settings_are_central_and_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_BUSY_TIMEOUT_MS", "1200")
    settings = settings_for(tmp_path)
    assert (
        getattr(settings, "archive_database_path", None)
        == tmp_path / "private/catalogue.sqlite3"
    )
    assert getattr(settings, "archive_busy_timeout_ms", None) == 1200
    for timeout in (0, 30001):
        with pytest.raises(ValidationError):
            settings_for(tmp_path, archive_busy_timeout_ms=timeout)


@pytest.mark.parametrize("path", ["", ":memory:", "file:archive?mode=memory"])
def test_archive_rejects_non_file_paths(tmp_path, path):
    with pytest.raises(ValidationError):
        settings_for(tmp_path, archive_database_path=path)


def test_archive_paths_cannot_alias_auth_or_each_other(tmp_path):
    auth = tmp_path / "auth.sqlite3"
    for path in (auth, auth.parent / "unused/../auth.sqlite3"):
        with pytest.raises(ValidationError):
            settings_for(tmp_path, archive_database_path=path)
    with pytest.raises(ValidationError):
        settings_for(
            tmp_path, archive_content_path=tmp_path / "private/catalogue.sqlite3"
        )


def test_archive_rejects_hardlink_to_auth(tmp_path):
    auth = tmp_path / "auth.sqlite3"
    auth.write_bytes(b"protected auth data")
    alias = tmp_path / "alias.sqlite3"
    os.link(auth, alias)
    with pytest.raises(ValidationError):
        settings_for(tmp_path, archive_database_path=alias)
    assert auth.read_bytes() == b"protected auth data"


@pytest.fixture
def catalogue(tmp_path):
    return archive_store.ArchiveStore(settings_for(tmp_path))


def add_repository(db, repo_id=101, name="owner/project"):
    db.execute(
        "INSERT INTO archive_repositories (repo_id, full_name) VALUES (?, ?)",
        (repo_id, name),
    )


def add_document(db, revision="rev-one", repo_id=101):
    db.execute(
        "INSERT INTO archive_documents (repo_id, revision) VALUES (?, ?)",
        (repo_id, revision),
    )


def test_migration_is_idempotent_and_preserves_stable_ids(tmp_path):
    settings = settings_for(tmp_path)
    store = archive_store.ArchiveStore(settings)
    with store.connect() as db:
        assert {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        } == {"archive_repositories", "archive_documents", "archive_chunks"}
    with store.connect(write=True) as db:
        add_repository(db)
        add_document(db)
        db.execute(
            "INSERT INTO archive_chunks (chunk_id, repo_id, revision, ordinal, text, token_count) VALUES ('101:rev-one:0', 101, 'rev-one', 0, 'Synthetic README', 3)"
        )
    store.migrate()
    reopened = archive_store.ArchiveStore(settings)
    with reopened.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert db.execute(
            "SELECT repo_id, full_name FROM archive_repositories"
        ).fetchall()[0][:] == (101, "owner/project")
        assert db.execute("SELECT chunk_id, text FROM archive_chunks").fetchone()[
            :
        ] == ("101:rev-one:0", "Synthetic README")
        assert {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        } == {"archive_repositories", "archive_documents", "archive_chunks"}


def test_auth_database_is_untouched(tmp_path):
    settings = settings_for(tmp_path)
    auth = Store(settings.database_path)
    with auth.connect() as db:
        db.execute("INSERT INTO users (github_id, login) VALUES (7, 'protected-user')")
    before = Path(settings.database_path).read_bytes()
    archive_store.ArchiveStore(settings)
    assert Path(settings.database_path).read_bytes() == before
    with auth.connect() as db:
        assert db.execute("SELECT login FROM users").fetchone()[0] == "protected-user"
        assert not db.execute(
            "SELECT name FROM sqlite_schema WHERE name LIKE 'archive_%'"
        ).fetchall()


def test_transaction_rolls_back_all_writes(catalogue):
    with pytest.raises(RuntimeError, match="abort"):
        with catalogue.connect(write=True) as db:
            add_repository(db)
            add_document(db)
            raise RuntimeError("abort")
    with catalogue.connect() as db:
        assert (
            db.execute("SELECT count(*) FROM archive_repositories").fetchone()[0] == 0
        )
        assert db.execute("SELECT count(*) FROM archive_documents").fetchone()[0] == 0
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute("SELECT 1")


def test_revision_states_and_active_pointer_persist(catalogue):
    with catalogue.connect(write=True) as db:
        add_repository(db)
        add_document(db)
        add_document(db, "rev-two")
        db.execute(
            "UPDATE archive_documents SET state='published' WHERE revision='rev-one'"
        )
        db.execute(
            "UPDATE archive_repositories SET active_revision='rev-one' WHERE repo_id=101"
        )
    with catalogue.connect() as db:
        assert (
            db.execute("SELECT active_revision FROM archive_repositories").fetchone()[0]
            == "rev-one"
        )
        assert [
            row[:]
            for row in db.execute(
                "SELECT revision, state FROM archive_documents ORDER BY revision"
            )
        ] == [("rev-one", "published"), ("rev-two", "pending")]


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO archive_repositories (repo_id, full_name) VALUES (101, 'duplicate')",
        "INSERT INTO archive_repositories (repo_id, full_name) VALUES (0, 'invalid')",
        "INSERT INTO archive_repositories (repo_id, full_name) VALUES ('not-an-id', 'invalid')",
        "INSERT INTO archive_documents (repo_id, revision) VALUES (999, 'orphan')",
        "INSERT INTO archive_documents (repo_id, revision) VALUES (101, 'rev-one')",
        "UPDATE archive_documents SET state='invented'",
        "UPDATE archive_repositories SET active_revision='missing' WHERE repo_id=101",
        "INSERT INTO archive_chunks (chunk_id, repo_id, revision, ordinal, text, token_count) VALUES ('orphan', 101, 'missing', 0, 'text', 1)",
        "INSERT INTO archive_chunks (chunk_id, repo_id, revision, ordinal, text, token_count) VALUES ('invalid', 101, 'rev-one', -1, 'text', 1)",
        "INSERT INTO archive_chunks (chunk_id, repo_id, revision, ordinal, text, token_count) VALUES ('invalid', 101, 'rev-one', 0, 'text', 0)",
    ],
)
def test_constraints_reject_invalid_identity_or_relationship(catalogue, sql):
    with catalogue.connect(write=True) as db:
        add_repository(db)
        add_document(db)
    with pytest.raises(sqlite3.IntegrityError):
        with catalogue.connect(write=True) as db:
            db.execute(sql)
    with catalogue.connect() as db:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM archive_documents").fetchone()[0] == 1


def test_chunk_ids_and_ordinals_are_unique(catalogue):
    sql = "INSERT INTO archive_chunks (chunk_id, repo_id, revision, ordinal, text, token_count) VALUES (?, 101, 'rev-one', ?, 'text', 1)"
    with catalogue.connect(write=True) as db:
        add_repository(db)
        add_document(db)
        db.execute(sql, ("chunk-one", 0))
    for key, ordinal in (("chunk-one", 1), ("other-key", 0)):
        with pytest.raises(sqlite3.IntegrityError):
            with catalogue.connect(write=True) as db:
                db.execute(sql, (key, ordinal))


def test_active_revision_cannot_belong_to_another_repository(catalogue):
    with catalogue.connect(write=True) as db:
        add_repository(db)
        add_repository(db, 202, "other/project")
        add_document(db, "other-revision", 202)
    with pytest.raises(sqlite3.IntegrityError):
        with catalogue.connect(write=True) as db:
            db.execute(
                "UPDATE archive_repositories SET active_revision='other-revision' WHERE repo_id=101"
            )


def test_private_directory_and_file_modes(catalogue):
    assert stat.S_IMODE(catalogue.path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(catalogue.path.stat().st_mode) == 0o600


def test_existing_shared_directory_is_rejected_without_chmod(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o755)
    with pytest.raises(PermissionError):
        archive_store.ArchiveStore(settings_for(tmp_path))
    assert stat.S_IMODE(directory.stat().st_mode) == 0o755
    assert not (directory / "catalogue.sqlite3").exists()


def test_unpatched_runtime_is_rejected_before_any_file_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version", "3.46.1")
    with pytest.raises(RuntimeError, match="WAL"):
        archive_store.ArchiveStore(settings_for(tmp_path))
    assert not (tmp_path / "private").exists()


def test_existing_catalogue_also_refuses_unpatched_connections(catalogue, monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version", "3.46.1")
    with pytest.raises(RuntimeError, match="WAL"):
        with catalogue.connect():
            pytest.fail("Unsafe connection yielded")


def test_unknown_database_is_not_migrated(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = directory / "catalogue.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unrelated (value TEXT)")
        db.execute("INSERT INTO unrelated VALUES ('keep me')")
    path.chmod(0o600)
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="catalogue"):
        archive_store.ArchiveStore(settings_for(tmp_path))
    assert path.read_bytes() == before


def test_future_schema_version_is_refused_without_changes(catalogue, tmp_path):
    with catalogue.connect(write=True) as db:
        db.execute("PRAGMA user_version=99")
    before = catalogue.path.read_bytes()
    with pytest.raises(RuntimeError, match="version"):
        archive_store.ArchiveStore(settings_for(tmp_path))
    assert catalogue.path.read_bytes() == before


def test_real_wal_reader_snapshot_writer_commit_checkpoint_and_reopen(catalogue):
    print(f"Linked SQLite: {sqlite3.sqlite_version}")
    with catalogue.connect(write=True) as db:
        add_repository(db)
    with catalogue.connect() as reader:
        assert reader.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert (
            reader.execute("SELECT count(*) FROM archive_repositories").fetchone()[0]
            == 1
        )
        with catalogue.connect(write=True) as writer:
            add_repository(writer, 202, "other/project")
        assert (
            reader.execute("SELECT count(*) FROM archive_repositories").fetchone()[0]
            == 1
        )
    with catalogue.connect() as reader:
        assert (
            reader.execute("SELECT count(*) FROM archive_repositories").fetchone()[0]
            == 2
        )
    with sqlite3.connect(catalogue.path) as db:
        assert db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() == (0, 0, 0)
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    reopened = archive_store.ArchiveStore(settings_for(catalogue.path.parents[1]))
    with reopened.connect() as db:
        assert (
            db.execute("SELECT count(*) FROM archive_repositories").fetchone()[0] == 2
        )


def test_migration_failure_rolls_back_ddl_and_version(tmp_path, monkeypatch):
    broken = archive_store.MIGRATIONS + (
        ("CREATE TABLE should_rollback (value TEXT)", "invalid SQL"),
    )
    monkeypatch.setattr(archive_store, "MIGRATIONS", broken)
    with pytest.raises(sqlite3.OperationalError):
        archive_store.ArchiveStore(settings_for(tmp_path))
    with sqlite3.connect(tmp_path / "private/catalogue.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0
        assert db.execute("PRAGMA application_id").fetchone()[0] == 0
        assert db.execute("SELECT name FROM sqlite_schema").fetchall() == []
    monkeypatch.undo()
    store = archive_store.ArchiveStore(settings_for(tmp_path))
    with store.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1


def test_private_file_and_wal_sidecars_and_bounded_lock_wait(catalogue):
    with catalogue.connect(write=True) as db:
        add_repository(db)
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        for suffix in ("-wal", "-shm"):
            assert (
                stat.S_IMODE(Path(str(catalogue.path) + suffix).stat().st_mode) == 0o600
            )
    catalogue.path.chmod(0o644)
    with pytest.raises(PermissionError):
        with catalogue.connect():
            pytest.fail("Shared database accepted")


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE archive_repositories SET metadata_json='invalid json'",
        "UPDATE archive_repositories SET metadata_json='[]'",
        "UPDATE archive_chunks SET vector_state='invented'",
    ],
)
def test_metadata_and_vector_state_constraints(catalogue, sql):
    with catalogue.connect(write=True) as db:
        add_repository(db)
        add_document(db)
        db.execute(
            "INSERT INTO archive_chunks (chunk_id, repo_id, revision, ordinal, text, token_count) VALUES ('chunk', 101, 'rev-one', 0, 'text', 1)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        with catalogue.connect(write=True) as db:
            db.execute(sql)


def test_deleting_revision_removes_its_chunks(catalogue):
    with catalogue.connect(write=True) as db:
        add_repository(db)
        add_document(db)
        db.execute(
            "INSERT INTO archive_chunks (chunk_id, repo_id, revision, ordinal, text, token_count) VALUES ('chunk', 101, 'rev-one', 0, 'text', 1)"
        )
    with catalogue.connect(write=True) as db:
        db.execute(
            "DELETE FROM archive_documents WHERE repo_id=101 AND revision='rev-one'"
        )
    with catalogue.connect() as db:
        assert db.execute("SELECT count(*) FROM archive_chunks").fetchone()[0] == 0


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_archive_sidecars_cannot_overwrite_auth_database(tmp_path, suffix):
    archive = tmp_path / "private/catalogue.sqlite3"
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_path=str(archive) + suffix,
            archive_database_path=archive,
        )


@pytest.mark.parametrize("name", [".", "/"])
def test_archive_database_requires_a_filename(tmp_path, name):
    with pytest.raises(ValidationError):
        settings_for(tmp_path, archive_database_path=name)
