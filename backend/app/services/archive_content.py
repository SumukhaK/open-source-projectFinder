"""Private content-addressed archive files and atomic revision persistence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.core.config import ARCHIVE_CONTENT_MAX_BYTES, ARCHIVE_METADATA_MAX_BYTES
from app.integrations.archive_github import ReadmeDocument, RepositoryMetadata
from app.services.archive_index import PreparedRepository

CONTENT_FORMAT_VERSION = "prepared-v1"
_KINDS = frozenset({"raw", "normalized"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")


class ContentError(Exception):
    pass


class ContentPathError(ContentError):
    pass


class ContentIdentityError(ContentError):
    pass


class ContentTooLarge(ContentError):
    pass


class ContentWriteError(ContentError):
    pass


class RevisionConflict(ContentError):
    pass


class RevisionIdentityError(ContentError):
    pass


@dataclass(frozen=True)
class ContentFile:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class StoredRevision:
    repo_id: int
    revision: str
    raw_path: str | None
    raw_sha256: str | None
    raw_bytes: int | None
    normalized_path: str
    normalized_sha256: str
    normalized_bytes: int
    replayed: bool


class ArchiveContentStore:
    """Content-addressed files confined to one private directory."""

    def __init__(self, settings):
        configured = Path(settings.archive_content_path).expanduser()
        if configured.is_symlink():
            raise ContentPathError("archive content root must not be a symlink")
        self.root = configured.resolve()
        self._prepare_root()

    def _prepare_root(self):
        if os.path.lexists(self.root):
            info = self.root.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise ContentPathError("archive content root must be a directory")
        else:
            self.root.mkdir(mode=0o700, parents=True)
        if os.name == "posix" and stat.S_IMODE(self.root.stat().st_mode) & 0o077:
            raise PermissionError("Archive content directory must be private (0700)")

    def path_for(self, kind, sha256):
        if kind not in _KINDS:
            raise ContentPathError("content kind must be raw or normalized")
        if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
            raise ContentPathError("content digest must be a lowercase SHA-256")
        return f"{kind}/{sha256[:2]}/{sha256}"

    def _target(self, relative):
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise ContentPathError("content path must be a relative POSIX path")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
            raise ContentPathError("content path escapes the private root")
        target = self.root.joinpath(*pure.parts)
        current = self.root
        for part in pure.parts:
            current = current / part
            if os.path.lexists(current) and stat.S_ISLNK(current.lstat().st_mode):
                raise ContentPathError("content path must not contain symlinks")
        resolved = target.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise ContentPathError("content path escapes the private root")
        return target

    def _prepare_parent(self, target):
        current = self.root
        for part in target.parent.relative_to(self.root).parts:
            current = current / part
            if not os.path.lexists(current):
                try:
                    current.mkdir(mode=0o700)
                except FileExistsError:
                    pass
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise ContentPathError("content directory must be a real directory")
            if os.name == "posix" and stat.S_IMODE(info.st_mode) & 0o077:
                raise PermissionError(
                    "Archive content directory must be private (0700)"
                )

    def _verify(self, target, digest, size):
        info = target.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ContentPathError("content path must be a regular file")
        if os.name == "posix" and stat.S_IMODE(info.st_mode) & 0o077:
            raise PermissionError("Archive content file must be private (0600)")
        if info.st_size != size:
            raise ContentIdentityError("existing content has the wrong size")
        try:
            data = target.read_bytes()
        except OSError as error:
            raise ContentIdentityError("existing content cannot be read") from error
        if hashlib.sha256(data).hexdigest() != digest:
            raise ContentIdentityError("existing content does not match its digest")

    def _write_atomic(self, target, data):
        temporary = None
        try:
            descriptor, temporary = tempfile.mkstemp(
                dir=target.parent, prefix=".tmp-", suffix=".part"
            )
            try:
                handle = os.fdopen(descriptor, "wb")
            except Exception:
                os.close(descriptor)
                raise
            with handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            temporary = None
            if os.name == "posix":
                self._sync_directory(target.parent)
        except OSError as error:
            raise ContentWriteError(
                "archive content could not be written atomically"
            ) from error
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    @staticmethod
    def _sync_directory(directory):
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def ensure(self, kind, data):
        return self._ensure(kind, data)[0]

    def _ensure(self, kind, data):
        if not isinstance(data, bytes):
            raise ContentError("content must be bytes")
        if len(data) > ARCHIVE_CONTENT_MAX_BYTES:
            raise ContentTooLarge("content exceeds the archive storage bound")
        digest = hashlib.sha256(data).hexdigest()
        relative = self.path_for(kind, digest)
        target = self._target(relative)
        if os.path.lexists(target):
            self._verify(target, digest, len(data))
            return ContentFile(relative, digest, len(data)), False
        self._prepare_parent(target)
        self._write_atomic(target, data)
        return ContentFile(relative, digest, len(data)), True

    def read(self, path, expected_sha256):
        if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(
            expected_sha256
        ):
            raise ContentPathError("expected digest must be a lowercase SHA-256")
        target = self._target(path)
        if not os.path.lexists(target):
            raise FileNotFoundError(target)
        info = target.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ContentPathError("content path must be a regular file")
        if os.name == "posix" and stat.S_IMODE(info.st_mode) & 0o077:
            raise PermissionError("Archive content file must be private (0600)")
        data = target.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ContentIdentityError("content does not match its expected digest")
        return data


def persist_revision(
    db,
    content,
    *,
    metadata,
    prepared,
    readme,
    raw=None,
    source_ref=None,
    source_truncated=False,
    expected_repo_id=None,
):
    """Write files first, then insert a pending catalogue revision atomically.

    The caller owns the SQL transaction and must pass an open write transaction
    (``ArchiveStore.connect(write=True)``). A replay with identical provenance
    is idempotent and repairs missing content files; any difference is refused.
    """
    if not isinstance(content, ArchiveContentStore):
        raise TypeError("content must be an ArchiveContentStore")
    if not isinstance(metadata, RepositoryMetadata):
        raise TypeError("metadata must be RepositoryMetadata")
    if not isinstance(prepared, PreparedRepository):
        raise TypeError("prepared must be PreparedRepository")
    if readme is not None and not isinstance(readme, ReadmeDocument):
        raise TypeError("readme must be ReadmeDocument or None")
    if type(source_truncated) is not bool:
        raise RevisionIdentityError("source_truncated must be a boolean")
    if not db.in_transaction:
        raise RuntimeError("persist_revision requires an open write transaction")
    if db.execute("PRAGMA user_version").fetchone()[0] < 2:
        raise RuntimeError("archive catalogue must be migrated before persistence")

    repo_id = metadata.repo_id
    if type(repo_id) is not int or repo_id <= 0:
        raise RevisionIdentityError("repository id must be a positive integer")
    if expected_repo_id is not None and (
        type(expected_repo_id) is not int or expected_repo_id <= 0
    ):
        raise RevisionIdentityError("expected repository id must be a positive integer")
    if expected_repo_id is not None and expected_repo_id != repo_id:
        raise RevisionIdentityError("repository id does not match the expected id")
    if prepared.repo_id != repo_id:
        raise RevisionIdentityError("prepared content belongs to another repository")
    if readme is not None and readme.repo_id != repo_id:
        raise RevisionIdentityError("README belongs to another repository")

    revision = prepared.semantic_hash
    if not isinstance(revision, str) or not _SHA256.fullmatch(revision):
        raise RevisionIdentityError("revision must be a lowercase SHA-256")
    for name, value in (
        ("normalizer_version", prepared.normalizer_version),
        ("chunker_version", prepared.chunker_version),
        ("model_revision", prepared.model_revision),
    ):
        if not isinstance(value, str) or not value or len(value) > 128:
            raise RevisionIdentityError(f"{name} must be bounded text")
    if not isinstance(metadata.full_name, str) or not metadata.full_name.strip():
        raise RevisionIdentityError("repository full name is required")

    if source_ref is not None and (
        not isinstance(source_ref, str) or not _SHA1.fullmatch(source_ref)
    ):
        raise RevisionIdentityError(
            "source_ref must be a 40-character commit SHA or None"
        )
    blob_sha = readme.blob_sha if readme is not None else None
    if readme is not None and blob_sha is None:
        raise RevisionIdentityError("README must include a file blob SHA")
    if blob_sha is not None and (
        not isinstance(blob_sha, str) or not _SHA1.fullmatch(blob_sha)
    ):
        raise RevisionIdentityError(
            "blob_sha must be a 40-character file blob SHA or None"
        )

    source = readme.response if readme is not None else metadata.response
    endpoint = source.url
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > 2048:
        raise RevisionIdentityError("source endpoint must be bounded text")
    for name, value in (
        ("etag", source.etag),
        ("last_modified", source.last_modified),
    ):
        if value is not None and (not isinstance(value, str) or len(value) > 512):
            raise RevisionIdentityError(f"{name} must be bounded text or None")

    if raw is None and readme is not None and readme.text is not None:
        raw = readme.text.encode("utf-8")
    if raw is not None:
        if not isinstance(raw, bytes):
            raise RevisionIdentityError("raw content must be bytes or None")
        if len(raw) > ARCHIVE_CONTENT_MAX_BYTES:
            raise ContentTooLarge("raw content exceeds the archive storage bound")
        if readme is not None and readme.text is not None:
            if raw != readme.text.encode("utf-8"):
                raise RevisionIdentityError(
                    "raw content does not match the README text"
                )
        if blob_sha is not None and _git_blob_sha(raw) != blob_sha:
            raise RevisionIdentityError(
                "raw content does not match the README blob SHA"
            )

    normalized = _normalized_bytes(prepared)
    if len(normalized) > ARCHIVE_CONTENT_MAX_BYTES:
        raise ContentTooLarge("normalized content exceeds the archive storage bound")
    metadata_json = _metadata_json(metadata)
    if len(metadata_json.encode("utf-8")) > ARCHIVE_METADATA_MAX_BYTES:
        raise RevisionIdentityError("repository metadata exceeds its byte budget")

    raw_sha = hashlib.sha256(raw).hexdigest() if raw is not None else None
    raw_path = content.path_for("raw", raw_sha) if raw is not None else None
    normalized_sha = hashlib.sha256(normalized).hexdigest()
    normalized_path = content.path_for("normalized", normalized_sha)
    raw_bytes = len(raw) if raw is not None else None
    truncated = int(source_truncated)
    expected = (
        raw_path,
        raw_sha,
        normalized_path,
        normalized_sha,
        prepared.model_revision,
        prepared.normalizer_version,
        prepared.chunker_version,
        endpoint,
        source_ref,
        blob_sha,
        source.etag,
        source.last_modified,
        raw_bytes,
        truncated,
    )
    existing = db.execute(
        "SELECT raw_path, raw_sha256, normalized_path, normalized_sha256, "
        "model_revision, normalizer_version, chunker_version, source_endpoint, "
        "source_ref, blob_sha, etag, last_modified, raw_bytes, truncated "
        "FROM archive_documents WHERE repo_id=? AND revision=?",
        (repo_id, revision),
    ).fetchone()
    if existing is not None:
        if tuple(existing) != expected:
            raise RevisionConflict(
                "revision already exists with different content or provenance"
            )
        if raw is not None:
            content.ensure("raw", raw)
        content.ensure("normalized", normalized)
        return StoredRevision(
            repo_id,
            revision,
            raw_path,
            raw_sha,
            raw_bytes,
            normalized_path,
            normalized_sha,
            len(normalized),
            True,
        )

    created = []
    try:
        if raw is not None:
            _, made = content._ensure("raw", raw)
            if made:
                created.append(raw_path)
        _, made = content._ensure("normalized", normalized)
        if made:
            created.append(normalized_path)
        db.execute(
            "INSERT INTO archive_repositories (repo_id, full_name, metadata_json) "
            "VALUES (?, ?, ?) ON CONFLICT(repo_id) DO NOTHING",
            (repo_id, metadata.full_name, metadata_json),
        )
        db.execute(
            "INSERT INTO archive_documents ("
            "repo_id, revision, raw_path, raw_sha256, normalized_path, "
            "normalized_sha256, model_revision, normalizer_version, "
            "chunker_version, source_endpoint, source_ref, blob_sha, etag, "
            "last_modified, raw_bytes, truncated"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                repo_id,
                revision,
                raw_path,
                raw_sha,
                normalized_path,
                normalized_sha,
                prepared.model_revision,
                prepared.normalizer_version,
                prepared.chunker_version,
                endpoint,
                source_ref,
                blob_sha,
                source.etag,
                source.last_modified,
                raw_bytes,
                truncated,
            ),
        )
    except Exception:
        for path in created:
            try:
                (content.root / path).unlink()
            except FileNotFoundError:
                pass
        raise
    return StoredRevision(
        repo_id,
        revision,
        raw_path,
        raw_sha,
        raw_bytes,
        normalized_path,
        normalized_sha,
        len(normalized),
        False,
    )


def _normalized_bytes(prepared):
    payload = {
        "format": CONTENT_FORMAT_VERSION,
        "repo_id": prepared.repo_id,
        "semantic_hash": prepared.semantic_hash,
        "normalizer_version": prepared.normalizer_version,
        "chunker_version": prepared.chunker_version,
        "model_revision": prepared.model_revision,
        "readme_status": prepared.readme_status,
        "omissions": list(prepared.omissions),
        "chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "ordinal": chunk.ordinal,
                "section": chunk.section,
                "text": chunk.text,
                "token_count": chunk.token_count,
                "text_hash": chunk.text_hash,
            }
            for chunk in prepared.chunks
        ],
    }
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _metadata_json(metadata):
    payload = {
        "default_branch": metadata.default_branch,
        "visibility": metadata.visibility,
        "archived": metadata.archived,
        "fork": metadata.fork,
        "license_spdx": metadata.license_spdx,
        "pushed_at": metadata.pushed_at,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _git_blob_sha(data):
    return hashlib.sha1(
        b"blob %d\0" % len(data) + data, usedforsecurity=False
    ).hexdigest()
