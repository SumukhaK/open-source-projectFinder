import errno
import hashlib
import json
import os
import sqlite3
import stat
from dataclasses import replace

import pytest
from app.core import archive_store
from app.core.config import ARCHIVE_CONTENT_MAX_BYTES, Settings
from app.integrations.archive_github import (
    ArchiveResponse,
    ReadmeDocument,
    RepositoryMetadata,
)
from app.services.archive_content import (
    ArchiveContentStore,
    ContentError,
    ContentIdentityError,
    ContentPathError,
    ContentTooLarge,
    ContentWriteError,
    RevisionConflict,
    RevisionIdentityError,
    persist_revision,
)
from app.services.archive_index import prepare_repository
from app.services.embeddings import EmbeddingAdapter, ModelManifest

README_TEXT = "# Project\n\nA bounded archive tool.\n"
BLOB_SHA = hashlib.sha1(
    b"blob %d\0" % len(README_TEXT.encode("utf-8")) + README_TEXT.encode("utf-8"),
    usedforsecurity=False,
).hexdigest()
COMMIT_SHA = "b" * 40


def git_blob_sha(text):
    encoded = text.encode("utf-8")
    return hashlib.sha1(
        b"blob %d\0" % len(encoded) + encoded, usedforsecurity=False
    ).hexdigest()


class CharacterEncoder:
    max_seq_length = 512

    def get_embedding_dimension(self):
        return 384

    def count_tokens(self, texts):
        return [len(text) + 2 for text in texts]

    def encode(self, texts, *, batch_size):
        raise AssertionError("Persistence must not embed content")


@pytest.fixture
def adapter():
    return EmbeddingAdapter(ModelManifest.load(), CharacterEncoder())


def settings_for(tmp_path, content_path=None):
    return Settings(
        _env_file=None,
        database_path=str(tmp_path / "auth.sqlite3"),
        archive_database_path=tmp_path / "private/catalogue.sqlite3",
        archive_content_path=content_path or tmp_path / "private/content",
    )


@pytest.fixture
def content(tmp_path):
    return ArchiveContentStore(settings_for(tmp_path))


@pytest.fixture
def db(tmp_path):
    connection = sqlite3.connect(tmp_path / "catalogue.sqlite3")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    for migration in archive_store.MIGRATIONS:
        for statement in migration:
            connection.execute(statement)
    connection.execute(f"PRAGMA user_version={len(archive_store.MIGRATIONS)}")
    connection.execute(f"PRAGMA application_id={archive_store.APPLICATION_ID}")
    yield connection
    connection.close()


def response(url, *, etag=None, last_modified=None):
    return ArchiveResponse(
        status=200,
        url=url,
        headers={},
        body=b"{}",
        request_id="req-archive",
        etag=etag,
        last_modified=last_modified,
        retry_at=None,
        encoded_bytes=2,
        decoded_bytes=2,
    )


def metadata_for(repo_id=101, full_name="owner/project"):
    return RepositoryMetadata(
        repo_id=repo_id,
        full_name=full_name,
        default_branch="main",
        visibility="public",
        archived=False,
        fork=False,
        license_spdx="MIT",
        pushed_at="2026-10-26T00:00:00Z",
        response=response(
            f"https://api.github.com/repos/{full_name}",
            etag='"metadata-etag"',
            last_modified="Mon, 26 Oct 2026 11:00:00 GMT",
        ),
    )


def readme_for(text=README_TEXT, repo_id=101, blob_sha=BLOB_SHA):
    return ReadmeDocument(
        repo_id=repo_id,
        path="README.md",
        blob_sha=blob_sha,
        text=text,
        size=len(text.encode("utf-8")),
        inline=True,
        response=response(
            "https://api.github.com/repos/owner/project/readme",
            etag='"readme-etag"',
            last_modified="Mon, 26 Oct 2026 12:00:00 GMT",
        ),
    )


def prepared_for(adapter, repo_id=101, full_name="owner/project", readme=README_TEXT):
    raw = readme.encode("utf-8") if readme is not None else None
    return prepare_repository(
        {
            "id": repo_id,
            "full_name": full_name,
            "description": "Offline maps",
            "topics": ["maps"],
            "language": "Python",
        },
        raw,
        adapter=adapter,
    )


def persist(db, content, *, metadata, prepared, readme, **kwargs):
    db.execute("BEGIN IMMEDIATE")
    try:
        stored = persist_revision(
            db,
            content,
            metadata=metadata,
            prepared=prepared,
            readme=readme,
            **kwargs,
        )
    except Exception:
        db.rollback()
        raise
    db.commit()
    return stored


def content_files(root):
    return sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    )


def document_row(db, repo_id=101):
    return db.execute(
        "SELECT * FROM archive_documents WHERE repo_id=?", (repo_id,)
    ).fetchone()


def test_persists_provenance_hashes_and_preparation_versions(
    tmp_path, db, content, adapter
):
    prepared = prepared_for(adapter)
    readme = readme_for()
    stored = persist(
        db,
        content,
        metadata=metadata_for(),
        prepared=prepared,
        readme=readme,
        source_ref=COMMIT_SHA,
        source_truncated=True,
    )

    raw = README_TEXT.encode("utf-8")
    row = document_row(db)
    assert stored.replayed is False
    assert stored.revision == prepared.semantic_hash
    assert row["state"] == "pending"
    assert row["raw_path"] == stored.raw_path
    assert row["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert row["normalized_path"] == stored.normalized_path
    assert row["normalized_sha256"] == stored.normalized_sha256
    assert row["normalizer_version"] == prepared.normalizer_version
    assert row["chunker_version"] == prepared.chunker_version
    assert row["model_revision"] == prepared.model_revision
    assert row["source_endpoint"] == readme.response.url
    assert row["source_ref"] == COMMIT_SHA
    assert row["blob_sha"] == BLOB_SHA
    assert row["source_ref"] != row["blob_sha"]
    assert row["etag"] == '"readme-etag"'
    assert row["last_modified"] == "Mon, 26 Oct 2026 12:00:00 GMT"
    assert row["raw_bytes"] == len(raw)
    assert row["truncated"] == 1
    assert (content.root / row["raw_path"]).read_bytes() == raw
    assert (content.root / row["normalized_path"]).read_bytes() == (
        content.read(row["normalized_path"], row["normalized_sha256"])
    )
    metadata_json = json.loads(
        db.execute("SELECT metadata_json FROM archive_repositories").fetchone()[0]
    )
    assert metadata_json["visibility"] == "public"
    assert "token" not in json.dumps(metadata_json).lower()


def test_absent_readme_persists_normalized_content_with_metadata_provenance(
    tmp_path, db, content, adapter
):
    prepared = prepared_for(adapter, readme=None)
    metadata = metadata_for()
    stored = persist(
        db,
        content,
        metadata=metadata,
        prepared=prepared,
        readme=None,
    )

    row = document_row(db)
    assert stored.raw_path is None
    assert row["raw_path"] is None
    assert row["raw_sha256"] is None
    assert row["raw_bytes"] is None
    assert row["blob_sha"] is None
    assert row["source_endpoint"] == metadata.response.url
    assert row["etag"] == '"metadata-etag"'
    assert row["last_modified"] == "Mon, 26 Oct 2026 11:00:00 GMT"
    assert row["truncated"] == 0
    payload = json.loads(content.read(row["normalized_path"], row["normalized_sha256"]))
    assert payload["readme_status"] == "missing"
    assert [chunk["text"] for chunk in payload["chunks"]] == [
        chunk.text for chunk in prepared.chunks
    ]


def test_duplicate_replay_deduplicates_and_repairs_a_missing_file(
    tmp_path, db, content, adapter
):
    prepared = prepared_for(adapter)
    metadata = metadata_for()
    readme = readme_for()
    first = persist(db, content, metadata=metadata, prepared=prepared, readme=readme)
    files = content_files(content.root)
    assert len(files) == 2

    replay = persist(db, content, metadata=metadata, prepared=prepared, readme=readme)
    assert replay.replayed is True
    assert replay.normalized_path == first.normalized_path
    assert content_files(content.root) == files
    assert db.execute("SELECT count(*) FROM archive_documents").fetchone()[0] == 1

    (content.root / first.normalized_path).unlink()
    repaired = persist(db, content, metadata=metadata, prepared=prepared, readme=readme)
    assert repaired.replayed is True
    assert content_files(content.root) == files
    assert (content.root / first.normalized_path).is_file()


def test_conflicting_replay_is_rejected_without_overwriting(db, content, adapter):
    prepared = prepared_for(adapter)
    metadata = metadata_for()
    readme = readme_for()
    stored = persist(db, content, metadata=metadata, prepared=prepared, readme=readme)
    before = content_files(content.root)
    conflicting = replace(prepared, model_revision="other-model-revision")

    with pytest.raises(RevisionConflict):
        persist(
            db,
            content,
            metadata=metadata,
            prepared=conflicting,
            readme=readme,
        )

    row = document_row(db)
    assert row["model_revision"] == prepared.model_revision
    assert row["normalized_path"] == stored.normalized_path
    assert content_files(content.root) == before


def test_replay_updates_readme_observation_provenance(db, content, adapter):
    prepared = prepared_for(adapter)
    metadata = metadata_for()
    readme = readme_for()
    stored = persist(db, content, metadata=metadata, prepared=prepared, readme=readme)
    files = content_files(content.root)

    updated = replace(
        readme,
        response=replace(
            readme.response,
            etag='"new-readme-etag"',
            last_modified="Tue, 27 Oct 2026 10:00:00 GMT",
        ),
    )
    replay = persist(db, content, metadata=metadata, prepared=prepared, readme=updated)

    row = document_row(db)
    assert replay.replayed is True
    assert replay.normalized_path == stored.normalized_path
    assert row["etag"] == '"new-readme-etag"'
    assert row["last_modified"] == "Tue, 27 Oct 2026 10:00:00 GMT"
    assert row["source_endpoint"] == readme.response.url
    assert row["source_ref"] is None
    assert db.execute("SELECT count(*) FROM archive_documents").fetchone()[0] == 1
    assert content_files(content.root) == files


def test_replay_updates_metadata_observation_provenance_without_readme(
    db, content, adapter
):
    prepared = prepared_for(adapter, readme=None)
    metadata = metadata_for()
    stored = persist(db, content, metadata=metadata, prepared=prepared, readme=None)

    updated = replace(
        metadata,
        response=replace(
            metadata.response,
            etag='"new-metadata-etag"',
            last_modified="Tue, 27 Oct 2026 11:00:00 GMT",
        ),
    )
    replay = persist(db, content, metadata=updated, prepared=prepared, readme=None)

    row = document_row(db)
    assert replay.replayed is True
    assert replay.normalized_path == stored.normalized_path
    assert row["etag"] == '"new-metadata-etag"'
    assert row["last_modified"] == "Tue, 27 Oct 2026 11:00:00 GMT"
    assert row["source_endpoint"] == metadata.response.url
    assert row["source_ref"] is None


def test_replay_updates_source_ref_observation_provenance(db, content, adapter):
    prepared = prepared_for(adapter)
    metadata = metadata_for()
    readme = readme_for()
    persist(
        db,
        content,
        metadata=metadata,
        prepared=prepared,
        readme=readme,
        source_ref=COMMIT_SHA,
    )

    new_ref = "c" * 40
    replay = persist(
        db,
        content,
        metadata=metadata,
        prepared=prepared,
        readme=readme,
        source_ref=new_ref,
    )

    row = document_row(db)
    assert replay.replayed is True
    assert row["source_ref"] == new_ref
    assert row["blob_sha"] == BLOB_SHA


def test_replay_updates_endpoint_observation_provenance_after_rename(
    db, content, adapter
):
    prepared = prepared_for(adapter)
    metadata = metadata_for()
    readme = readme_for()
    persist(db, content, metadata=metadata, prepared=prepared, readme=readme)

    renamed_url = "https://api.github.com/repos/new-owner/new-name/readme"
    renamed = replace(
        readme,
        response=replace(readme.response, url=renamed_url),
    )
    renamed_metadata = replace(
        metadata,
        full_name="new-owner/new-name",
        response=replace(
            metadata.response,
            url="https://api.github.com/repos/new-owner/new-name",
        ),
    )
    replay = persist(
        db,
        content,
        metadata=renamed_metadata,
        prepared=prepared,
        readme=renamed,
    )

    row = document_row(db)
    assert replay.replayed is True
    assert row["source_endpoint"] == renamed_url
    assert row["etag"] == readme.response.etag
    assert db.execute("SELECT count(*) FROM archive_documents").fetchone()[0] == 1


def test_replay_rejects_a_different_blob_sha_under_the_same_revision(
    db, content, adapter
):
    prepared = prepared_for(adapter)
    metadata = metadata_for()
    readme = readme_for()
    stored = persist(db, content, metadata=metadata, prepared=prepared, readme=readme)

    changed_text = "# Project\n\nDifferent bytes.\n"
    changed = replace(
        readme,
        text=changed_text,
        size=len(changed_text.encode("utf-8")),
        blob_sha=git_blob_sha(changed_text),
    )
    with pytest.raises(RevisionConflict):
        persist(db, content, metadata=metadata, prepared=prepared, readme=changed)

    row = document_row(db)
    assert row["blob_sha"] == BLOB_SHA
    assert row["raw_path"] == stored.raw_path


def test_replay_rejects_different_normalized_content_under_the_same_revision(
    db, content, adapter
):
    prepared = prepared_for(adapter)
    metadata = metadata_for()
    readme = readme_for()
    stored = persist(db, content, metadata=metadata, prepared=prepared, readme=readme)
    before = content_files(content.root)

    with pytest.raises(RevisionConflict):
        persist(
            db,
            content,
            metadata=metadata,
            prepared=replace(prepared, omissions=("chunk_limit",)),
            readme=readme,
        )

    row = document_row(db)
    assert row["normalized_path"] == stored.normalized_path
    assert content_files(content.root) == before


def test_raw_content_without_readme_is_rejected(db, content, adapter):
    with pytest.raises(RevisionIdentityError):
        persist(
            db,
            content,
            metadata=metadata_for(),
            prepared=prepared_for(adapter, readme=None),
            readme=None,
            raw=b"orphan raw bytes",
        )

    assert document_row(db) is None
    assert content_files(content.root) == []


@pytest.mark.parametrize(
    "change",
    [
        {"prepared_id": 202},
        {"readme_id": 202},
        {"expected_id": 303},
    ],
)
def test_mismatched_repository_identity_is_rejected(db, content, adapter, change):
    prepared = prepared_for(adapter, repo_id=change.get("prepared_id", 101))
    readme = readme_for(repo_id=change.get("readme_id", 101))

    with pytest.raises(RevisionIdentityError):
        persist(
            db,
            content,
            metadata=metadata_for(),
            prepared=prepared,
            readme=readme,
            expected_repo_id=change.get("expected_id"),
        )

    assert document_row(db) is None
    assert content_files(content.root) == []


@pytest.mark.parametrize("bad", ["main", "A" * 40, "a" * 39, "a" * 41])
def test_blob_and_resolved_commit_shas_are_strictly_validated(
    db, content, adapter, bad
):
    prepared = prepared_for(adapter)
    with pytest.raises(RevisionIdentityError):
        persist(
            db,
            content,
            metadata=metadata_for(),
            prepared=prepared,
            readme=readme_for(blob_sha=bad),
        )
    with pytest.raises(RevisionIdentityError):
        persist(
            db,
            content,
            metadata=metadata_for(),
            prepared=prepared,
            readme=readme_for(),
            source_ref=bad,
        )
    assert document_row(db) is None
    assert content_files(content.root) == []


def test_persist_requires_an_open_write_transaction(db, content, adapter):
    with pytest.raises(RuntimeError, match="transaction"):
        persist_revision(
            db,
            content,
            metadata=metadata_for(),
            prepared=prepared_for(adapter),
            readme=readme_for(),
        )
    assert document_row(db) is None
    assert content_files(content.root) == []


def test_raw_content_over_the_storage_bound_is_refused(db, content, adapter):
    with pytest.raises(ContentTooLarge):
        persist(
            db,
            content,
            metadata=metadata_for(),
            prepared=prepared_for(adapter),
            readme=readme_for(),
            raw=b"x" * (ARCHIVE_CONTENT_MAX_BYTES + 1),
        )
    assert document_row(db) is None
    assert content_files(content.root) == []


@pytest.mark.parametrize(
    "path",
    ["../escape", "/etc/passwd", "raw/../../escape", "raw/aa/../escape"],
)
def test_content_reads_reject_traversal_and_absolute_paths(content, path):
    with pytest.raises(ContentPathError):
        content.read(path, "0" * 64)


@pytest.mark.parametrize(
    "kind,sha",
    [
        ("../raw", "0" * 64),
        ("raw", "../" + "0" * 64),
        ("raw", "0" * 63),
        ("raw", "g" * 64),
    ],
)
def test_content_paths_reject_invalid_kind_or_digest(content, kind, sha):
    with pytest.raises(ContentPathError):
        content.path_for(kind, sha)


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions only")
def test_existing_shared_content_directory_is_rejected(tmp_path):
    root = tmp_path / "private/content"
    root.mkdir(parents=True, mode=0o755)
    root.chmod(0o755)

    with pytest.raises(PermissionError):
        ArchiveContentStore(settings_for(tmp_path))

    assert stat.S_IMODE(root.stat().st_mode) == 0o755


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions only")
def test_content_files_and_shard_directories_are_private(content):
    stored = content.ensure("raw", b"private bytes")
    target = content.root / stored.path

    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions only")
def test_shared_existing_content_file_is_not_accepted(content):
    stored = content.ensure("raw", b"private bytes")
    (content.root / stored.path).chmod(0o644)

    with pytest.raises(PermissionError):
        content.ensure("raw", b"private bytes")


@pytest.mark.skipif(os.name != "posix", reason="symlink escape is POSIX-specific")
def test_symlinked_content_root_is_rejected(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "private/content"
    link.parent.mkdir(parents=True)
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(ContentPathError):
        ArchiveContentStore(settings_for(tmp_path))


@pytest.mark.skipif(os.name != "posix", reason="symlink escape is POSIX-specific")
def test_symlinked_directory_escape_is_rejected(content, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (content.root / "raw").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ContentPathError):
        content.ensure("raw", b"private bytes")

    assert list(outside.iterdir()) == []


@pytest.mark.skipif(os.name != "posix", reason="symlink escape is POSIX-specific")
def test_symlinked_target_escape_is_rejected(content, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret"
    secret.write_bytes(b"keep me")
    digest = hashlib.sha256(b"private bytes").hexdigest()
    relative = content.path_for("raw", digest)
    target = content.root / relative
    target.parent.mkdir(parents=True)
    target.symlink_to(secret)

    with pytest.raises(ContentPathError):
        content.ensure("raw", b"private bytes")

    assert secret.read_bytes() == b"keep me"


def test_interrupted_replace_leaves_no_target_or_temporary_file(content, monkeypatch):
    def fail_replace(*args, **kwargs):
        raise OSError(errno.ENOSPC, "disk full")

    monkeypatch.setattr("app.services.archive_content.os.replace", fail_replace)

    with pytest.raises(ContentWriteError):
        content.ensure("raw", b"private bytes")

    assert content_files(content.root) == []


def test_disk_full_during_fsync_removes_the_temporary_file(content, monkeypatch):
    def fail_fsync(*args, **kwargs):
        raise OSError(errno.ENOSPC, "disk full")

    monkeypatch.setattr("app.services.archive_content.os.fsync", fail_fsync)

    with pytest.raises(ContentWriteError):
        content.ensure("normalized", b"private bytes")

    assert content_files(content.root) == []


def test_existing_content_with_the_wrong_hash_is_not_overwritten(content):
    data = b"private bytes"
    digest = hashlib.sha256(data).hexdigest()
    target = content.root / content.path_for("raw", digest)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"corrupt")
    target.chmod(0o600)

    with pytest.raises(ContentIdentityError):
        content.ensure("raw", data)

    assert target.read_bytes() == b"corrupt"


def test_recovery_read_rejects_tampered_content(db, content, adapter):
    persist(
        db,
        content,
        metadata=metadata_for(),
        prepared=prepared_for(adapter),
        readme=readme_for(),
    )
    row = document_row(db)
    (content.root / row["normalized_path"]).write_bytes(b"tampered")

    with pytest.raises(ContentIdentityError):
        content.read(row["normalized_path"], row["normalized_sha256"])


def test_database_failure_removes_new_files_and_leaves_no_reference(
    db, content, adapter
):
    db.execute(
        "CREATE TRIGGER reject_documents BEFORE INSERT ON archive_documents "
        "BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END"
    )

    with pytest.raises(sqlite3.IntegrityError, match="simulated write failure"):
        persist(
            db,
            content,
            metadata=metadata_for(),
            prepared=prepared_for(adapter),
            readme=readme_for(),
        )

    assert db.execute("SELECT count(*) FROM archive_repositories").fetchone()[0] == 0
    assert document_row(db) is None
    assert content_files(content.root) == []


def test_recovery_reads_normalized_content_without_github_or_milvus(
    db, content, adapter
):
    prepared = prepared_for(adapter)
    persist(
        db,
        content,
        metadata=metadata_for(),
        prepared=prepared,
        readme=readme_for(),
    )
    row = document_row(db)
    payload = json.loads(content.read(row["normalized_path"], row["normalized_sha256"]))

    assert payload["format"] == "prepared-v1"
    assert payload["repo_id"] == 101
    assert payload["semantic_hash"] == prepared.semantic_hash
    assert payload["normalizer_version"] == prepared.normalizer_version
    assert payload["chunker_version"] == prepared.chunker_version
    assert payload["model_revision"] == prepared.model_revision
    assert [
        (chunk["chunk_id"], chunk["text"], chunk["text_hash"])
        for chunk in payload["chunks"]
    ] == [(chunk.chunk_id, chunk.text, chunk.text_hash) for chunk in prepared.chunks]


def test_content_store_rejects_non_bytes_and_oversized_data(content):
    with pytest.raises(ContentError):
        content.ensure("raw", "text")
    with pytest.raises(ContentTooLarge):
        content.ensure("raw", b"x" * (ARCHIVE_CONTENT_MAX_BYTES + 1))

    assert content_files(content.root) == []


def test_content_root_must_be_a_directory(tmp_path):
    path = tmp_path / "private/content"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a directory")

    with pytest.raises(ContentPathError):
        ArchiveContentStore(settings_for(tmp_path))


def test_content_read_requires_a_valid_digest_and_existing_file(content):
    with pytest.raises(ContentPathError):
        content.read("raw/aa/" + "0" * 64, "bad")
    with pytest.raises(FileNotFoundError):
        content.read("raw/aa/" + "0" * 64, "0" * 64)


@pytest.mark.parametrize("path", ["", "raw\\aa\\x"])
def test_content_read_rejects_non_posix_paths(content, path):
    with pytest.raises(ContentPathError):
        content.read(path, "0" * 64)


def test_existing_content_with_the_wrong_size_is_not_overwritten(content):
    data = b"private bytes"
    digest = hashlib.sha256(data).hexdigest()
    target = content.root / content.path_for("raw", digest)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"short")
    target.chmod(0o600)

    with pytest.raises(ContentIdentityError):
        content.ensure("raw", data)

    assert target.read_bytes() == b"short"


def test_existing_file_where_a_shard_directory_belongs_is_rejected(content):
    (content.root / "raw").write_bytes(b"not a directory")

    with pytest.raises(ContentPathError):
        content.ensure("raw", b"private bytes")


@pytest.mark.parametrize(
    "change",
    [
        {"semantic_hash": "not-a-hash"},
        {"normalizer_version": ""},
        {"chunker_version": ""},
        {"model_revision": ""},
    ],
)
def test_persist_rejects_invalid_revision_or_versions(db, content, adapter, change):
    with pytest.raises(RevisionIdentityError):
        persist(
            db,
            content,
            metadata=metadata_for(),
            prepared=replace(prepared_for(adapter), **change),
            readme=readme_for(),
        )

    assert document_row(db) is None
    assert content_files(content.root) == []


def test_persist_rejects_invalid_source_metadata(db, content, adapter):
    prepared = prepared_for(adapter)
    base = metadata_for()
    readme = readme_for()
    invalid = [
        (replace(base, full_name=" "), readme),
        (base, replace(readme, response=replace(readme.response, url=""))),
        (base, replace(readme, response=replace(readme.response, etag=123))),
        (
            base,
            replace(
                readme,
                response=replace(readme.response, last_modified="x" * 513),
            ),
        ),
    ]
    for metadata, source in invalid:
        with pytest.raises(RevisionIdentityError):
            persist(
                db,
                content,
                metadata=metadata,
                prepared=prepared,
                readme=source,
            )

    assert document_row(db) is None
    assert content_files(content.root) == []


def test_persist_rejects_non_boolean_truncation_and_bad_expected_id(
    db, content, adapter
):
    prepared = prepared_for(adapter)
    for kwargs in ({"source_truncated": 1}, {"expected_repo_id": True}):
        with pytest.raises(RevisionIdentityError):
            persist(
                db,
                content,
                metadata=metadata_for(),
                prepared=prepared,
                readme=readme_for(),
                **kwargs,
            )

    assert document_row(db) is None
    assert content_files(content.root) == []


def test_persist_rejects_a_readme_without_a_blob_sha(db, content, adapter):
    with pytest.raises(RevisionIdentityError):
        persist(
            db,
            content,
            metadata=metadata_for(),
            prepared=prepared_for(adapter),
            readme=replace(readme_for(), blob_sha=None),
        )

    assert document_row(db) is None
    assert content_files(content.root) == []


def test_persist_rejects_non_bytes_and_mismatched_raw_content(db, content, adapter):
    prepared = prepared_for(adapter)
    with pytest.raises(RevisionIdentityError):
        persist(
            db,
            content,
            metadata=metadata_for(),
            prepared=prepared,
            readme=readme_for(),
            raw="text",
        )
    with pytest.raises(RevisionIdentityError):
        persist(
            db,
            content,
            metadata=metadata_for(),
            prepared=prepared,
            readme=readme_for(),
            raw=b"different",
        )
    blob_readme = replace(readme_for(), text=None)
    with pytest.raises(RevisionIdentityError):
        persist(
            db,
            content,
            metadata=metadata_for(),
            prepared=prepared,
            readme=blob_readme,
            raw=b"different",
        )

    assert document_row(db) is None
    assert content_files(content.root) == []


def test_persist_rejects_oversized_repository_metadata(db, content, adapter):
    with pytest.raises(RevisionIdentityError):
        persist(
            db,
            content,
            metadata=replace(metadata_for(), pushed_at="x" * 20000),
            prepared=prepared_for(adapter),
            readme=readme_for(),
        )

    assert document_row(db) is None
    assert content_files(content.root) == []


def test_persist_refuses_an_unmigrated_catalogue(tmp_path, content, adapter):
    connection = sqlite3.connect(tmp_path / "v1.sqlite3")
    connection.execute("PRAGMA foreign_keys=ON")
    for statement in archive_store.MIGRATIONS[0]:
        connection.execute(statement)
    connection.execute("PRAGMA user_version=1")
    connection.execute(f"PRAGMA application_id={archive_store.APPLICATION_ID}")
    connection.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(RuntimeError, match="migrated"):
            persist_revision(
                connection,
                content,
                metadata=metadata_for(),
                prepared=prepared_for(adapter),
                readme=readme_for(),
            )
    finally:
        connection.rollback()
        connection.close()

    assert content_files(content.root) == []


def test_migration_two_upgrades_a_v1_catalogue_without_data_loss(tmp_path):
    connection = sqlite3.connect(tmp_path / "catalogue.sqlite3")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    for statement in archive_store.MIGRATIONS[0]:
        connection.execute(statement)
    connection.execute("PRAGMA user_version=1")
    connection.execute(f"PRAGMA application_id={archive_store.APPLICATION_ID}")
    connection.execute(
        "INSERT INTO archive_repositories (repo_id, full_name) VALUES (101, 'owner/project')"
    )
    connection.execute(
        "INSERT INTO archive_documents (repo_id, revision) VALUES (101, 'rev-one')"
    )

    for statement in archive_store.MIGRATIONS[1]:
        connection.execute(statement)
    connection.execute("PRAGMA user_version=2")

    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(archive_documents)")
    }
    assert {
        "normalized_path",
        "source_endpoint",
        "source_ref",
        "blob_sha",
        "etag",
        "last_modified",
        "raw_bytes",
        "truncated",
    } <= columns
    row = connection.execute(
        "SELECT * FROM archive_documents WHERE repo_id=101 AND revision='rev-one'"
    ).fetchone()
    assert row["state"] == "pending"
    assert row["normalized_path"] is None
    assert row["source_ref"] is None
    assert row["blob_sha"] is None
    assert row["raw_bytes"] is None
    assert row["truncated"] == 0
    connection.close()
