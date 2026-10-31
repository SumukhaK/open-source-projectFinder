"""T09: ingest exactly one approved public repository end to end.

The operator names a numeric GitHub repository ID; this module resolves the
verified metadata by that ID, refuses ineligible repositories, reuses unchanged
semantic content, and otherwise embeds, publishes and reconciles one revision.
It is a local operator command, never an API endpoint or a scheduler.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.archive_store import ArchiveStore
from app.core.config import ARCHIVE_BACKFILL_LICENSES, MILVUS_TEXT_BYTES, Settings
from app.integrations.archive_github import (
    ArchiveGitHubError,
    ArchiveGitHubReader,
    RepositoryMetadata,
)
from app.integrations.milvus import (
    MilvusAdapter,
    MilvusContractError,
    MilvusOperationError,
    MilvusUnavailable,
    VectorChunk,
)
from app.services.archive_content import (
    ArchiveContentStore,
    ContentError,
    persist_revision,
)
from app.services.archive_index import PreparedRepository, prepare_repository
from app.services.archive_publication import (
    PublicationError,
    load_active_chunks,
    publish_revision,
    reconcile,
)
from app.services.archive_runs import check_lease
from app.services.embeddings import EmbeddingAdapter, EmbeddingError
from pydantic import ValidationError
from pydantic_settings import SettingsError

ELIGIBILITY_DAYS = 365


class IngestError(Exception):
    """A sanitized, actionable failure that is safe to print."""


class IneligibleRepository(IngestError):
    """The repository does not meet the approved archive policy."""

    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class IngestRuntime:
    settings: Settings
    reader: ArchiveGitHubReader
    adapter: EmbeddingAdapter
    vectors: MilvusAdapter
    content: ArchiveContentStore
    connect: Callable


def _safe_error(error):
    if isinstance(error, EmbeddingError):
        return (
            "preflight: pinned embedding model unavailable; verify the offline E5 cache"
        )
    if isinstance(error, MilvusContractError):
        return "preflight: verify the pinned 2.6 family, collection and index contract"
    if isinstance(error, (MilvusUnavailable, MilvusOperationError)):
        return "preflight: Could not connect or operate Milvus; check the local service"
    if isinstance(error, ArchiveGitHubError):
        return (
            "GitHub acquisition failed; verify worker credentials, identity and quota"
        )
    if isinstance(error, PublicationError):
        return "Publication incomplete; retry the same numeric repository ID"
    return "Archive storage failed; check private paths, free disk and WAL-fixed SQLite"


def build_runtime(settings):
    """Run every preflight check, then return the wired runtime."""
    try:
        return _build_runtime(settings)
    except IngestError:
        raise
    except (
        ArchiveGitHubError,
        ContentError,
        EmbeddingError,
        MilvusUnavailable,
        MilvusOperationError,
        MilvusContractError,
        RuntimeError,
        OSError,
    ) as error:
        raise IngestError(_safe_error(error)) from None


def _build_runtime(settings):
    if not settings.archive_github_token.strip():
        raise IngestError(
            "ARCHIVE_GITHUB_TOKEN is not configured; a public-read worker token is required"
        )
    if not settings.archive_license_allowlist:
        raise IngestError(
            "ARCHIVE_LICENSE_ALLOWLIST is empty; approve a licence policy first"
        )
    content = ArchiveContentStore(settings)
    _check_disk(content.root, settings.archive_min_free_bytes)
    store = ArchiveStore(settings)
    _check_disk(settings.archive_database_path.parent, settings.archive_min_free_bytes)
    adapter = EmbeddingAdapter.load(batch_size=settings.milvus_batch_size, warm=False)
    vectors = MilvusAdapter.connect(settings, adapter.manifest)
    try:
        # Verifies the 2.6 server, collection/index contract and loaded state.
        vectors.ensure_collection()
    except Exception:
        vectors.close()
        raise
    reader = ArchiveGitHubReader(settings=settings)
    return IngestRuntime(settings, reader, adapter, vectors, content, store.connect)


def _check_disk(path, minimum):
    free = shutil.disk_usage(path).free
    if free < minimum:
        raise IngestError(
            f"free disk {free} bytes is below ARCHIVE_MIN_FREE_BYTES={minimum}"
        )


def ingest_one(runtime, repo_id, *, now=None, lease=None, progress=None):
    """Acquire, prepare, persist and publish one repository; return a summary."""
    if type(repo_id) is not int or not 0 < repo_id < 2**63:
        raise IngestError("repository id must be a positive integer")
    if lease is not None:
        with runtime.connect() as db:
            check_lease(db, lease)
    report = progress or (lambda stage, facts: None)
    cutoff = _utc(now) - timedelta(days=ELIGIBILITY_DAYS)
    timings = {}
    started = time.perf_counter()

    step = time.perf_counter()
    metadata = runtime.reader.fetch_metadata_by_id(repo_id).metadata
    if metadata is None or metadata.repo_id != repo_id:
        raise IngestError("numeric repository identity did not match")
    timings["acquire"] = _elapsed(step)

    pushed_at = check_eligibility(
        metadata, runtime.settings.archive_license_allowlist, cutoff
    )
    payload = _metadata_payload(metadata)
    report(
        "eligible",
        {
            "license": metadata.license_spdx,
            "language": _bounded(payload.get("language") or "Unknown", 128),
            "pushed_at": pushed_at.timestamp(),
            "stars": payload.get("stargazers_count", 0),
        },
    )

    step = time.perf_counter()
    readme = runtime.reader.fetch_readme(metadata).readme
    raw, readme = _readme_bytes(runtime.reader, metadata, readme)
    confirmed = runtime.reader.fetch_metadata_by_id(repo_id).metadata
    if (
        confirmed is None
        or confirmed.repo_id != repo_id
        or confirmed.full_name != metadata.full_name
    ):
        raise IngestError("repository moved during acquisition; retry by numeric ID")
    check_eligibility(confirmed, runtime.settings.archive_license_allowlist, cutoff)
    prepared = prepare_repository(payload, raw, adapter=runtime.adapter)
    timings["prepare"] = _elapsed(step)

    summary = {
        "repo_id": repo_id,
        "revision": prepared.semantic_hash,
        "chunks": len(prepared.chunks),
        "readme": prepared.readme_status,
    }
    report(
        "prepared", {"revision": prepared.semantic_hash, "chunks": len(prepared.chunks)}
    )
    if _active_revision(runtime.connect, repo_id) == prepared.semantic_hash:
        timings["total"] = _elapsed(started)
        return {
            **summary,
            "result": "unchanged",
            "embedded_chunks": 0,
            "embedding_calls": 0,
            "vectors_written": 0,
            "timings_ms": timings,
        }

    step = time.perf_counter()
    with runtime.connect(write=True) as db:
        if lease is not None:
            check_lease(db, lease)
        persist_revision(
            db,
            runtime.content,
            metadata=metadata,
            prepared=prepared,
            readme=readme,
            raw=raw,
        )
    timings["persist"] = _elapsed(step)
    report("persisted", {})

    step = time.perf_counter()
    embedded = runtime.adapter.embed(
        [chunk.text for chunk in prepared.chunks], kind="passage"
    )
    timings["embed"] = _elapsed(step)
    report("embedded", {})
    chunks = _vector_chunks(prepared, embedded, metadata, pushed_at, payload)

    step = time.perf_counter()
    published = publish_revision(
        runtime.connect, runtime.vectors, prepared=prepared, chunks=chunks, lease=lease
    )
    timings["publish"] = _elapsed(step)
    report("published", {"revision": prepared.semantic_hash})

    step = time.perf_counter()
    try:
        retired = reconcile(runtime.connect, runtime.vectors, lease=lease)
        reconcile_summary = {
            "documents": retired.documents,
            "vectors": retired.vectors,
            "pending": retired.pending_documents,
        }
    except (MilvusUnavailable, MilvusOperationError):
        # The new revision is already active; leftover superseded vectors are safe.
        reconcile_summary = {"deferred": True}
    timings["reconcile"] = _elapsed(step)
    timings["total"] = _elapsed(started)

    return {
        **summary,
        "result": "published",
        "embedded_chunks": len(embedded),
        "embedding_calls": 1,
        "vectors_written": published.chunks,
        "reconcile": reconcile_summary,
        "timings_ms": timings,
    }


def check_eligibility(metadata, allowlist, cutoff):
    """Return the parsed pushed time or raise a typed policy refusal."""
    if not isinstance(metadata, RepositoryMetadata):
        raise IngestError("acquisition returned invalid metadata")
    if metadata.visibility != "public":
        raise IneligibleRepository("not_public", "repository is not public")
    if metadata.archived:
        raise IneligibleRepository("archived", "repository is archived")
    if metadata.fork:
        raise IneligibleRepository("fork", "repository is a fork")
    pushed_at = _pushed_at(metadata.pushed_at)
    if pushed_at < cutoff:
        raise IneligibleRepository(
            "stale",
            f"repository was not pushed within the rolling {ELIGIBILITY_DAYS}-day window",
        )
    if not metadata.license_spdx:
        raise IneligibleRepository("license_missing", "repository has no SPDX license")
    allowed = {entry.strip().lower() for entry in allowlist}
    if metadata.license_spdx.lower() not in allowed:
        raise IneligibleRepository(
            "license_not_allowed",
            "repository license is not in ARCHIVE_LICENSE_ALLOWLIST",
        )
    return pushed_at


def _pushed_at(value):
    if not isinstance(value, str) or not value.strip():
        raise IneligibleRepository(
            "pushed_at_missing", "repository pushed_at is missing"
        )
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as error:
        raise IneligibleRepository(
            "pushed_at_invalid", "repository pushed_at is not ISO 8601"
        ) from error
    if moment.tzinfo is None:
        raise IneligibleRepository(
            "pushed_at_invalid", "repository pushed_at must include a timezone"
        )
    return moment.astimezone(timezone.utc)


def _utc(now):
    moment = now or datetime.now(timezone.utc)
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise IngestError("cutoff time must be timezone-aware")
    return moment.astimezone(timezone.utc)


def _readme_bytes(reader, metadata, readme):
    if readme is None:
        return None, None
    if readme.text is not None:
        return readme.text.encode("utf-8"), readme
    result = reader.fetch_blob(metadata, readme.blob_sha)
    if result.blob is None:
        raise IngestError("README content is unavailable")
    return result.blob.data, readme


def _metadata_payload(metadata):
    try:
        payload = json.loads(metadata.response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IngestError("repository metadata payload is not valid JSON") from error
    if not isinstance(payload, dict) or payload.get("id") != metadata.repo_id:
        raise IngestError(
            "repository metadata payload does not match the verified repository id"
        )
    return payload


def _vector_chunks(
    prepared: PreparedRepository, embedded, metadata, pushed_at, payload
):
    if len(embedded) != len(prepared.chunks):
        raise IngestError("embedding model returned the wrong number of vectors")
    language = _bounded(payload.get("language") or "", MILVUS_TEXT_BYTES["language"])
    license_spdx = _bounded(metadata.license_spdx or "", MILVUS_TEXT_BYTES["license"])
    moment = int(pushed_at.timestamp())
    return tuple(
        VectorChunk(
            chunk_id=chunk.chunk_id,
            repo_id=prepared.repo_id,
            revision=prepared.semantic_hash,
            model_revision=prepared.model_revision,
            language=language,
            license=license_spdx,
            pushed_at=moment,
            ordinal=chunk.ordinal,
            section=chunk.section,
            snippet=_bounded(chunk.text, MILVUS_TEXT_BYTES["snippet"]),
            vector=vector,
        )
        for chunk, vector in zip(prepared.chunks, embedded, strict=True)
    )


def _bounded(value, limit):
    if not isinstance(value, str):
        raise IngestError("chunk metadata must be text")
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


def _active_revision(connect, repo_id):
    with connect() as db:
        chunks = load_active_chunks(db, repo_id)
    return chunks[0].revision if chunks else None


def _elapsed(start):
    return round((time.perf_counter() - start) * 1000, 3)


def _positive_id(value):
    if not value.isascii() or not value.isdigit() or not 0 < int(value) < 2**63:
        raise argparse.ArgumentTypeError("--repo-id must be a positive integer")
    return int(value)


def _backfill_cap(value):
    if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 1000:
        raise argparse.ArgumentTypeError("--cap must be an integer from 1 through 1000")
    return int(value)


def backfill_license_policy_ok(settings):
    """The approved SPDX set, order-insensitive and without duplicates."""
    values = settings.archive_license_allowlist
    return len(values) == len(set(values)) and set(values) == set(
        ARCHIVE_BACKFILL_LICENSES
    )


def _failure(repo_id, message, started, *, result="failed"):
    return {
        "result": result,
        "repo_id": repo_id,
        "error": message,
        "timings_ms": {"total": _elapsed(started)},
    }


def _invalid_fields(error):
    fields = sorted({str(item["loc"][0]) for item in error.errors() if item.get("loc")})
    return ", ".join(fields) or "unknown field"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m app.workers.archive",
        description="Local archive ingestion worker (one repository at a time)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser(
        "ingest", help="Ingest one approved public repository by numeric id"
    )
    ingest.add_argument("--repo-id", type=_positive_id, required=True)
    backfill = commands.add_parser(
        "backfill", help="Resume the bounded local archive pilot"
    )
    backfill.add_argument("--cap", type=_backfill_cap, default=1000)
    args = parser.parse_args(argv)

    started = time.perf_counter()
    runtime = None
    try:
        settings = Settings()
        if args.command == "backfill":
            if not backfill_license_policy_ok(settings):
                raise IngestError(
                    "ARCHIVE_LICENSE_ALLOWLIST must equal the approved backfill policy"
                )
            runtime = build_runtime(settings)
            from app.workers.backfill import Backfill

            summary = Backfill(runtime, clock=time.time).run(cap=args.cap)
        else:
            runtime = build_runtime(settings)
            summary = ingest_one(runtime, args.repo_id)
    except ValidationError as error:
        summary = _failure(
            getattr(args, "repo_id", None),
            "invalid settings: " + _invalid_fields(error),
            started,
        )
    except SettingsError:
        summary = _failure(
            getattr(args, "repo_id", None),
            "invalid settings: check JSON arrays in environment configuration",
            started,
        )
    except IneligibleRepository as error:
        summary = _failure(
            getattr(args, "repo_id", None), str(error), started, result="refused"
        )
        summary["reason"] = error.reason
    except IngestError as error:
        summary = _failure(getattr(args, "repo_id", None), str(error), started)
    except (
        ArchiveGitHubError,
        EmbeddingError,
        ContentError,
        PublicationError,
        MilvusUnavailable,
        MilvusOperationError,
        MilvusContractError,
        ValueError,
        RuntimeError,
        OSError,
    ) as error:
        summary = _failure(getattr(args, "repo_id", None), _safe_error(error), started)
    except Exception as error:  # never print a traceback or provider payload
        summary = _failure(
            getattr(args, "repo_id", None),
            f"unexpected {type(error).__name__}",
            started,
        )
    finally:
        if runtime is not None:
            try:
                runtime.vectors.close()
            except Exception:
                summary = _failure(
                    getattr(args, "repo_id", None),
                    "Milvus cleanup failed; check the local service",
                    started,
                )

    if "timings_ms" not in summary:
        summary["result"] = summary["stop_reason"]
        summary["repo_id"] = None
        summary["timings_ms"] = {"total": _elapsed(started)}
    summary["timings_ms"]["total"] = _elapsed(started)
    print(json.dumps(summary, sort_keys=True))
    return (
        0
        if summary["result"]
        in ("published", "unchanged", "finished", "cap", "quota", "rate_limit")
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
