"""Worker-only crash-safe publication and bounded restart reconciliation.

SQLite and Milvus share no transaction. A revision is staged as pending chunk
rows, every vector is upserted with stable IDs and strongly read back, and only
then does one short SQL transaction publish the revision and move the
repository's active pointer. Superseded rows are retired by ``reconcile`` only
after their vectors are deleted, so a crash can leave extra rows but never an
untracked vector.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.core.config import ARCHIVE_MAX_CHUNKS, ARCHIVE_RECONCILE_DOCUMENTS
from app.integrations.milvus import VectorChunk
from app.services.archive_index import PreparedChunk, PreparedRepository

_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_BATCH = 64


class PublicationError(Exception):
    """Publication cannot proceed; the active revision is unchanged."""


class PublicationContractError(PublicationError):
    """The prepared revision and vectors do not match the catalogue contract."""


class PublicationIncomplete(PublicationError):
    """Vectors were written but the complete expected set is not readable."""


@dataclass(frozen=True)
class ActiveChunk:
    chunk_id: str
    repo_id: int
    revision: str
    ordinal: int
    section: str
    text: str
    text_sha256: str | None
    token_count: int


@dataclass(frozen=True)
class PublicationResult:
    repo_id: int
    revision: str
    chunks: int
    previous: str | None


@dataclass(frozen=True)
class ReconcileResult:
    documents: int
    vectors: int
    pending_documents: int


def _validate_prepared(prepared):
    if not isinstance(prepared, PreparedRepository):
        raise PublicationContractError("prepared must be a PreparedRepository")
    if type(prepared.repo_id) is not int or prepared.repo_id <= 0:
        raise PublicationContractError("repository id must be a positive integer")
    if not isinstance(prepared.semantic_hash, str) or not _SHA256.fullmatch(
        prepared.semantic_hash
    ):
        raise PublicationContractError("revision must be a lowercase SHA-256")
    if not isinstance(prepared.model_revision, str) or not prepared.model_revision:
        raise PublicationContractError("model revision must be text")
    chunks = prepared.chunks
    if not isinstance(chunks, tuple) or not 1 <= len(chunks) <= ARCHIVE_MAX_CHUNKS:
        raise PublicationContractError(
            "revision must contain between 1 and ARCHIVE_MAX_CHUNKS chunks"
        )
    seen = set()
    for ordinal, chunk in enumerate(chunks):
        if not isinstance(chunk, PreparedChunk):
            raise PublicationContractError(
                "prepared chunks must be PreparedChunk records"
            )
        if chunk.ordinal != ordinal:
            raise PublicationContractError(
                "chunk ordinals must be contiguous from zero in order"
            )
        if not isinstance(chunk.chunk_id, str) or not _SHA256.fullmatch(chunk.chunk_id):
            raise PublicationContractError("chunk identity must be a lowercase SHA-256")
        if chunk.chunk_id in seen:
            raise PublicationContractError("chunk identities must be unique")
        seen.add(chunk.chunk_id)
        if not isinstance(chunk.text, str) or not chunk.text:
            raise PublicationContractError("chunk text must be non-empty text")
        if not isinstance(chunk.section, str):
            raise PublicationContractError("chunk section must be text")
        if type(chunk.token_count) is not int or chunk.token_count <= 0:
            raise PublicationContractError("chunk token count must be positive")
        if chunk.text_hash != hashlib.sha256(chunk.text.encode("utf-8")).hexdigest():
            raise PublicationContractError("chunk text hash does not match its text")
    return chunks


def _vector_chunks(prepared, chunks):
    if not isinstance(chunks, tuple) or len(chunks) != len(prepared.chunks):
        raise PublicationContractError("vector set must match the prepared chunks")
    expected = {chunk.chunk_id: chunk for chunk in prepared.chunks}
    seen = set()
    for chunk in chunks:
        if not isinstance(chunk, VectorChunk):
            raise PublicationContractError("vectors must be VectorChunk records")
        if chunk.chunk_id in seen:
            raise PublicationContractError("vector identities must be unique")
        seen.add(chunk.chunk_id)
        source = expected.get(chunk.chunk_id)
        if source is None:
            raise PublicationContractError("vector does not belong to the revision")
        if chunk.repo_id != prepared.repo_id:
            raise PublicationContractError("vector belongs to another repository")
        if chunk.revision != prepared.semantic_hash:
            raise PublicationContractError("vector belongs to another revision")
        if chunk.model_revision != prepared.model_revision:
            raise PublicationContractError("vector model revision does not match")
        if chunk.ordinal != source.ordinal:
            raise PublicationContractError("vector ordinal does not match")
        if chunk.section != source.section:
            raise PublicationContractError("vector section does not match")
    return tuple(sorted(chunks, key=lambda chunk: chunk.ordinal))


def _batch_size(vectors):
    settings = getattr(vectors, "settings", None)
    size = getattr(settings, "milvus_batch_size", None)
    if type(size) is not int or not 1 <= size <= _MAX_BATCH:
        raise PublicationContractError(
            "vector batch size must be within the Milvus limit"
        )
    return size


def _batches(items, size):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _stage(connect, prepared):
    with connect(write=True) as db:
        row = db.execute(
            "SELECT state, model_revision FROM archive_documents "
            "WHERE repo_id=? AND revision=?",
            (prepared.repo_id, prepared.semantic_hash),
        ).fetchone()
        if row is None:
            raise PublicationContractError(
                "pending revision must be persisted before publication"
            )
        if row[1] != prepared.model_revision:
            raise PublicationContractError(
                "catalogue model revision does not match the prepared revision"
            )
        state = row[0]
        if state == "superseded":
            raise PublicationContractError("superseded revisions cannot be republished")
        if state == "published":
            active = db.execute(
                "SELECT active_revision FROM archive_repositories WHERE repo_id=?",
                (prepared.repo_id,),
            ).fetchone()
            if active is None or active[0] != prepared.semantic_hash:
                raise PublicationContractError(
                    "published revision is not the active revision"
                )
        for chunk in prepared.chunks:
            db.execute(
                "INSERT INTO archive_chunks (chunk_id, repo_id, revision, ordinal, "
                "section, text, text_sha256, token_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                (
                    chunk.chunk_id,
                    prepared.repo_id,
                    prepared.semantic_hash,
                    chunk.ordinal,
                    chunk.section,
                    chunk.text,
                    chunk.text_hash,
                    chunk.token_count,
                ),
            )
        rows = db.execute(
            "SELECT chunk_id, ordinal, section, text, text_sha256, token_count "
            "FROM archive_chunks WHERE repo_id=? AND revision=? ORDER BY ordinal",
            (prepared.repo_id, prepared.semantic_hash),
        ).fetchall()
        expected = tuple(
            (
                chunk.chunk_id,
                chunk.ordinal,
                chunk.section,
                chunk.text,
                chunk.text_hash,
                chunk.token_count,
            )
            for chunk in prepared.chunks
        )
        if tuple(tuple(row) for row in rows) != expected:
            raise PublicationContractError(
                "catalogue chunks do not match the prepared revision"
            )


def _activate(connect, prepared):
    with connect(write=True) as db:
        row = db.execute(
            "SELECT state FROM archive_documents WHERE repo_id=? AND revision=?",
            (prepared.repo_id, prepared.semantic_hash),
        ).fetchone()
        if row is None:
            raise PublicationContractError("revision disappeared before activation")
        if row[0] == "superseded":
            raise PublicationContractError("revision was superseded before activation")
        rows = db.execute(
            "SELECT chunk_id FROM archive_chunks WHERE repo_id=? AND revision=? "
            "ORDER BY ordinal",
            (prepared.repo_id, prepared.semantic_hash),
        ).fetchall()
        if tuple(row[0] for row in rows) != tuple(
            chunk.chunk_id for chunk in prepared.chunks
        ):
            raise PublicationIncomplete("catalogue chunks changed during publication")
        db.execute(
            "UPDATE archive_chunks SET vector_state='written' "
            "WHERE repo_id=? AND revision=?",
            (prepared.repo_id, prepared.semantic_hash),
        )
        active = db.execute(
            "SELECT active_revision FROM archive_repositories WHERE repo_id=?",
            (prepared.repo_id,),
        ).fetchone()
        if active is None:
            raise PublicationContractError("repository disappeared during publication")
        previous = active[0]
        if row[0] == "published" and previous not in (None, prepared.semantic_hash):
            raise PublicationContractError(
                "published revision is not the active revision"
            )
        if previous not in (None, prepared.semantic_hash):
            db.execute(
                "UPDATE archive_documents SET state='superseded' "
                "WHERE repo_id=? AND revision=? AND state='published'",
                (prepared.repo_id, previous),
            )
        db.execute(
            "UPDATE archive_documents SET state='published' "
            "WHERE repo_id=? AND revision=?",
            (prepared.repo_id, prepared.semantic_hash),
        )
        db.execute(
            "UPDATE archive_repositories SET active_revision=? WHERE repo_id=?",
            (prepared.semantic_hash, prepared.repo_id),
        )
        return previous


def publish_revision(connect, vectors, *, prepared, chunks):
    """Stage, write and verify one revision, then atomically activate it.

    ``connect`` is the archive catalogue's ``connect(write=...)`` factory and
    ``vectors`` is the T07 adapter. Retryable adapter failures propagate with
    the revision still pending; callers replay the same prepared revision.
    """
    _validate_prepared(prepared)
    vector_chunks = _vector_chunks(prepared, chunks)
    batch_size = _batch_size(vectors)

    _stage(connect, prepared)
    for batch in _batches(vector_chunks, batch_size):
        vectors.upsert(batch)
    for batch in _batches(vector_chunks, batch_size):
        if not vectors.ready(batch):
            raise PublicationIncomplete("the complete vector set is not readable")

    previous = _activate(connect, prepared)
    return PublicationResult(
        prepared.repo_id, prepared.semantic_hash, len(vector_chunks), previous
    )


def reconcile(connect, vectors, *, limit=ARCHIVE_RECONCILE_DOCUMENTS):
    """Retire bounded superseded work and report pending publications.

    Vectors are deleted before their catalogue rows. Pending revisions are
    reported but never activated or removed; their publisher replays them.
    """
    if type(limit) is not int or not 1 <= limit <= ARCHIVE_RECONCILE_DOCUMENTS:
        raise PublicationContractError("reconcile limit must be within its bound")
    batch_size = _batch_size(vectors)
    with connect() as db:
        documents = db.execute(
            "SELECT d.repo_id, d.revision FROM archive_documents AS d "
            "JOIN archive_repositories AS r ON r.repo_id = d.repo_id "
            "WHERE d.state = 'superseded' "
            "AND (r.active_revision IS NULL OR r.active_revision <> d.revision) "
            "ORDER BY d.repo_id, d.revision LIMIT ?",
            (limit,),
        ).fetchall()
        pending = db.execute(
            "SELECT count(*) FROM archive_documents WHERE state='pending'"
        ).fetchone()[0]
    retired_documents = 0
    retired_vectors = 0
    for repo_id, revision in documents:
        with connect() as db:
            chunk_ids = tuple(
                row[0]
                for row in db.execute(
                    "SELECT chunk_id FROM archive_chunks "
                    "WHERE repo_id=? AND revision=? ORDER BY ordinal",
                    (repo_id, revision),
                )
            )
        for batch in _batches(chunk_ids, batch_size):
            vectors.delete(batch)
            retired_vectors += len(batch)
        with connect(write=True) as db:
            row = db.execute(
                "SELECT state FROM archive_documents WHERE repo_id=? AND revision=?",
                (repo_id, revision),
            ).fetchone()
            if row is None or row[0] != "superseded":
                continue
            active = db.execute(
                "SELECT active_revision FROM archive_repositories WHERE repo_id=?",
                (repo_id,),
            ).fetchone()
            if active is None or active[0] == revision:
                continue
            db.execute(
                "DELETE FROM archive_documents WHERE repo_id=? AND revision=? "
                "AND state='superseded'",
                (repo_id, revision),
            )
            retired_documents += 1
    return ReconcileResult(retired_documents, retired_vectors, pending)


def load_active_chunks(db, repo_id):
    """Return the complete published, vector-ready active chunk set.

    The caller owns the read transaction. An incomplete, pending or gapped set
    is treated as empty so search never exposes a partial revision.
    """
    if type(repo_id) is not int or repo_id <= 0:
        raise PublicationContractError("repository id must be a positive integer")
    rows = db.execute(
        "SELECT c.chunk_id, c.repo_id, c.revision, c.ordinal, c.section, c.text, "
        "c.text_sha256, c.token_count, c.vector_state "
        "FROM archive_repositories AS r "
        "JOIN archive_documents AS d "
        "ON d.repo_id = r.repo_id AND d.revision = r.active_revision "
        "JOIN archive_chunks AS c "
        "ON c.repo_id = d.repo_id AND c.revision = d.revision "
        "WHERE r.repo_id = ? AND d.state = 'published' "
        "ORDER BY c.ordinal",
        (repo_id,),
    ).fetchall()
    if not rows or len(rows) > ARCHIVE_MAX_CHUNKS:
        return ()
    if [row[3] for row in rows] != list(range(len(rows))):
        return ()
    if any(row[8] != "written" for row in rows):
        return ()
    return tuple(
        ActiveChunk(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7])
        for row in rows
    )
