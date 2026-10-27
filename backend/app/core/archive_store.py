"""Private, separately migrated archive catalogue; no ingestion or vector writes."""

import os
import sqlite3
from contextlib import contextmanager

from .config import Settings
from .sqlite_runtime import wal_is_fixed

APPLICATION_ID = 0x52524143  # RRAC, distinct from the authentication database.
MIGRATIONS = (
    (
        """CREATE TABLE archive_repositories (
            repo_id INTEGER PRIMARY KEY CHECK (repo_id > 0),
            full_name TEXT NOT NULL CHECK (length(trim(full_name)) > 0),
            metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (
                CASE WHEN json_valid(metadata_json)
                     THEN json_type(metadata_json) = 'object' ELSE 0 END),
            active_revision TEXT,
            FOREIGN KEY (repo_id, active_revision)
                REFERENCES archive_documents (repo_id, revision)
                DEFERRABLE INITIALLY DEFERRED
        ) STRICT""",
        """CREATE TABLE archive_documents (
            repo_id INTEGER NOT NULL REFERENCES archive_repositories (repo_id),
            revision TEXT NOT NULL CHECK (length(revision) > 0),
            state TEXT NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending', 'published', 'superseded')),
            raw_path TEXT,
            raw_sha256 TEXT,
            normalized_sha256 TEXT,
            model_revision TEXT,
            normalizer_version TEXT,
            chunker_version TEXT,
            PRIMARY KEY (repo_id, revision)
        ) STRICT""",
        """CREATE TABLE archive_chunks (
            chunk_id TEXT PRIMARY KEY CHECK (length(chunk_id) > 0),
            repo_id INTEGER NOT NULL,
            revision TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
            section TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL CHECK (length(text) > 0),
            text_sha256 TEXT,
            token_count INTEGER NOT NULL CHECK (token_count > 0),
            vector_state TEXT NOT NULL DEFAULT 'pending'
                CHECK (vector_state IN ('pending', 'written')),
            UNIQUE (repo_id, revision, ordinal),
            FOREIGN KEY (repo_id, revision)
                REFERENCES archive_documents (repo_id, revision) ON DELETE CASCADE
        ) STRICT""",
    ),
    (
        "ALTER TABLE archive_documents ADD COLUMN normalized_path TEXT",
        """ALTER TABLE archive_documents ADD COLUMN source_endpoint TEXT CHECK (
            source_endpoint IS NULL OR length(trim(source_endpoint)) > 0)""",
        """ALTER TABLE archive_documents ADD COLUMN source_ref TEXT CHECK (
            source_ref IS NULL OR (length(source_ref) = 40
                AND source_ref NOT GLOB '*[^0-9a-f]*'))""",
        """ALTER TABLE archive_documents ADD COLUMN blob_sha TEXT CHECK (
            blob_sha IS NULL OR (length(blob_sha) = 40
                AND blob_sha NOT GLOB '*[^0-9a-f]*'))""",
        "ALTER TABLE archive_documents ADD COLUMN etag TEXT",
        "ALTER TABLE archive_documents ADD COLUMN last_modified TEXT",
        """ALTER TABLE archive_documents ADD COLUMN raw_bytes INTEGER CHECK (
            raw_bytes IS NULL OR raw_bytes >= 0)""",
        """ALTER TABLE archive_documents ADD COLUMN truncated INTEGER NOT NULL
            DEFAULT 0 CHECK (truncated IN (0, 1))""",
    ),
)


class ArchiveStore:
    def __init__(self, settings: Settings):
        settings.separate_archive_paths()
        self.path = settings.archive_database_path.expanduser().resolve()
        self.timeout = settings.archive_busy_timeout_ms / 1000
        self.migrate()

    def _private_file(self):
        if os.name != "posix":
            raise RuntimeError("Archive catalogue requires a private Linux filesystem")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.parent.stat().st_mode & 0o077:
            raise PermissionError("Archive catalogue directory must be private (0700)")
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        info = self.path.stat()
        if info.st_mode & 0o077 or info.st_nlink != 1:
            raise PermissionError(
                "Archive catalogue file must be private (0600), without hardlinks"
            )

    @staticmethod
    def _version(db):
        identity = db.execute("PRAGMA application_id").fetchone()[0]
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > len(MIGRATIONS):
            raise RuntimeError(
                "Archive catalogue schema version is newer than this code"
            )
        if identity != APPLICATION_ID:
            empty = not db.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone()
            if identity != 0 or version != 0 or not empty:
                raise RuntimeError(
                    "Refusing to migrate a database that is not an archive catalogue"
                )
        return version

    @contextmanager
    def connect(self, *, write=False):
        # Check every process/connection, including databases already persisted in WAL mode.
        if not wal_is_fixed(sqlite3.sqlite_version):
            raise RuntimeError(
                "Archive WAL requires a linked SQLite with the WAL-reset fix"
            )
        self._private_file()
        db = sqlite3.connect(self.path, timeout=self.timeout)
        db.row_factory = sqlite3.Row
        try:
            self._version(db)
            db.execute("PRAGMA foreign_keys=ON")
            if db.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
                raise RuntimeError("Archive catalogue could not enable WAL")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            with db:
                yield db
        finally:
            db.close()

    def migrate(self):
        with self.connect(write=True) as db:
            version = self._version(db)
            for index in range(version, len(MIGRATIONS)):
                # executescript would implicitly commit, losing atomic DDL rollback.
                for statement in MIGRATIONS[index]:
                    db.execute(statement)
                db.execute(f"PRAGMA user_version={index + 1}")
            db.execute(f"PRAGMA application_id={APPLICATION_ID}")
