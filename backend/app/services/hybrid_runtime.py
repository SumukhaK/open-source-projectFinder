"""Lazy hybrid serving stack and the T10 later-page revalidation adapter.

Nothing here connects to Milvus, loads the embedding model or opens the archive
catalogue at import time. A missing signing key or archive reader makes the v1
route return a typed "unavailable" error while the legacy API keeps serving. A
model or Milvus outage instead serves live GitHub results with the archive
source reported as failed, and the full stack is retried after the backoff.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, RLock, local

from app.core.archive_store import APPLICATION_ID, MIGRATIONS, ArchiveStore
from app.core.config import ARCHIVE_VISIBILITY_CACHE_SIZE, Settings
from app.integrations.archive_github import ArchiveGitHubError, ArchiveGitHubReader
from app.services.eligibility import EligibilityService
from app.services.embeddings import EmbeddingAdapter, EmbeddingError, ModelManifest
from app.services.fused_cursor import HybridPager
from app.services.hybrid_search import BoundedExecutor, HybridSearchService
from app.services.keyword_candidates import GitHubKeywordCandidates
from app.services.live_scope import live_eligible
from app.services.rank_fusion import RANKING_VERSION

logger = logging.getLogger("reporadar.hybrid")

# Leave the bounded executor enough room to return a short page instead of
# turning a slow live revalidation into a request timeout.
_DEADLINE_MARGIN_SECONDS = 0.1


class HybridUnavailable(RuntimeError):
    """A required serving component is missing; the v1 route cannot search."""


class ArchiveOffline(RuntimeError):
    """The model or Milvus could not be prepared for this build."""


class _OfflineArchive:
    """Stand-in for the model and vector store while either is unavailable.

    The hybrid service maps any failure here to an archive source of
    ``failed``/``unavailable``, so the live GitHub source still serves.
    """

    def embed(self, texts, *, kind):
        raise ArchiveOffline("archive search is offline")

    def search(self, vector, *, limit, filters):
        raise ArchiveOffline("archive search is offline")

    def close(self):
        return None


@dataclass(frozen=True)
class HybridTarget:
    pager: HybridPager
    generation: str
    executor: BoundedExecutor
    revalidator: FusedRevalidator | None = None
    archive_online: bool = True


class FusedRevalidator:
    """Adapt fused cards to T10 ``EligibilityService.check`` input.

    Archived cards become T07 hit identities so T10 re-reads their active
    revision and fresh metadata. Live-only cards are re-read through the same
    public reader; stored snapshot metadata is never reused as the check.
    Successful public reads are cached by numeric repository ID for at most the
    T10 visibility TTL so a warm later page performs no HTTP. Anything that
    cannot be freshly verified is dropped (fail closed).

    ``begin(deadline)`` installs the request's remaining deadline for the
    current thread; misses are fetched with bounded concurrency and only the
    completed, verified cards are passed on, so a short page is served instead
    of blocking until the executor times out.
    """

    def __init__(
        self,
        eligibility,
        reader,
        *,
        settings=None,
        now=None,
        max_workers=4,
    ):
        self.eligibility = eligibility
        self.reader = reader
        self._ttl = (
            settings.archive_visibility_ttl_seconds if settings is not None else 900
        )
        self._max_workers = max(1, int(max_workers))
        self._now = now or time.monotonic
        self._cache = OrderedDict()
        self._lock = Lock()
        self._deadline = local()

    def begin(self, deadline):
        """Set this thread's request deadline (``time.monotonic`` clock)."""
        self._deadline.value = deadline

    def end(self):
        self._deadline.value = None

    def __call__(self, candidates):
        hits = []
        live = {}
        misses = []
        for candidate in candidates:
            if candidate.archive is not None:
                hits.append(
                    {
                        "repo_id": candidate.repo_id,
                        "revision": candidate.archive.revision,
                        "chunk_id": candidate.archive.chunk_id,
                    }
                )
                continue
            cached = self._cached(candidate.repo_id)
            if cached is not None:
                live[candidate.repo_id] = cached
            else:
                misses.append(candidate)
        if misses:
            live.update(self._fetch(misses))
        checked = self.eligibility.check(hits, live=live)
        kept = {metadata.get("id") for metadata in checked.live}
        kept.update(evidence.hit["repo_id"] for evidence in checked.archive)
        for candidate in candidates:
            if candidate.archive is None and candidate.repo_id not in kept:
                self._forget(candidate.repo_id)
        return [candidate for candidate in candidates if candidate.repo_id in kept]

    def _remaining(self):
        deadline = getattr(self._deadline, "value", None)
        if deadline is None:
            return None
        return max(0.0, deadline - self._now() - _DEADLINE_MARGIN_SECONDS)

    def _cached(self, repo_id):
        now = self._now()
        with self._lock:
            entry = self._cache.get(repo_id)
            if entry is None:
                return None
            expires_at, metadata = entry
            if expires_at <= now:
                self._cache.pop(repo_id, None)
                return None
            self._cache.move_to_end(repo_id)
            return dict(metadata)

    def _remember(self, repo_id, metadata):
        if not live_eligible(repo_id, metadata):
            return
        cached = {
            key: metadata.get(key)
            for key in ("id", "full_name", "private", "archived", "pushed_at")
        }
        cached["visibility"] = metadata.get("visibility", "public")
        expires_at = self._now() + self._ttl
        with self._lock:
            self._cache[repo_id] = (expires_at, cached)
            self._cache.move_to_end(repo_id)
            while len(self._cache) > ARCHIVE_VISIBILITY_CACHE_SIZE:
                self._cache.popitem(last=False)

    def _forget(self, repo_id):
        with self._lock:
            self._cache.pop(repo_id, None)

    def _fetch(self, candidates):
        remaining = self._remaining()
        if remaining is not None and remaining <= 0:
            return {}
        workers = max(1, min(self._max_workers, len(candidates)))
        pool = ThreadPoolExecutor(max_workers=workers)
        futures = {
            pool.submit(self._fresh, candidate): candidate for candidate in candidates
        }
        fetched = {}
        try:
            try:
                for future in as_completed(futures, timeout=remaining):
                    candidate = futures[future]
                    try:
                        metadata = future.result()
                    except Exception:
                        metadata = None
                    if metadata is not None:
                        fetched[candidate.repo_id] = metadata
                        self._remember(candidate.repo_id, metadata)
            except TimeoutError:
                pass
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return fetched

    def _fresh(self, candidate):
        full_name = candidate.metadata.get("full_name")
        if not isinstance(full_name, str) or not full_name:
            return None
        try:
            result = self.reader.fetch_metadata(candidate.repo_id, full_name)
            metadata = json.loads(result.response.body)
        except (ArchiveGitHubError, TypeError, ValueError):
            return None
        return metadata if isinstance(metadata, dict) else None


def archive_counts(path):
    """Read bounded catalogue counts through a read-only SQLite URI.

    The status view must never create, migrate or lock the catalogue. A
    missing file, an unreadable file or an unexpected schema raises; the
    caller turns that into ``state: "unknown"`` with null counts.
    """
    location = Path(path).expanduser().resolve()
    db = sqlite3.connect(f"{location.as_uri()}?mode=ro", uri=True)
    try:
        identity = db.execute("PRAGMA application_id").fetchone()[0]
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if identity != APPLICATION_ID or version != len(MIGRATIONS):
            raise RuntimeError("archive catalogue schema is not readable")
        repositories = db.execute(
            "SELECT count(*) FROM archive_repositories"
        ).fetchone()[0]
        published = db.execute(
            "SELECT count(*) FROM archive_documents WHERE state='published'"
        ).fetchone()[0]
        chunks = db.execute("SELECT count(*) FROM archive_chunks").fetchone()[0]
        run = db.execute(
            "SELECT kind, due_period, completed FROM archive_runs "
            "ORDER BY run_id DESC LIMIT 1"
        ).fetchone()
    finally:
        db.close()
    return {
        "repositories": repositories,
        "published_documents": published,
        "chunks": chunks,
        "latest_run": (
            None
            if run is None
            else {
                "kind": run[0],
                "due_period": run[1],
                "completed": bool(run[2]),
            }
        ),
    }


class HybridRuntime:
    """Build the hybrid stack on first use; never at import or app boot."""

    def __init__(self, settings: Settings, *, provider, now=None):
        self.settings = settings
        self.provider = provider
        self._lock = RLock()
        self._build_lock = Lock()
        self._store = None
        self._embeddings = None
        self._target = None
        self._fallback = None
        self._fallback_until = 0.0
        self._executor = None
        self._failure_until = 0.0
        self._now = now or time.monotonic

    def target(self):
        with self._lock:
            if self._target is not None:
                return self._target
            fallback = self._fallback
            if fallback is not None and self._now() < self._fallback_until:
                return fallback
            if fallback is None and self._now() < self._failure_until:
                raise HybridUnavailable("hybrid search is unavailable")
        # Never hold a pool worker waiting for another request's build.
        if not self._build_lock.acquire(blocking=False):
            if fallback is not None:
                return fallback
            raise TimeoutError("hybrid search is starting")
        try:
            with self._lock:
                if self._target is not None:
                    return self._target
                if self._fallback is not None and self._fallback is not fallback:
                    return self._fallback
                if self._fallback is None and self._now() < self._failure_until:
                    raise HybridUnavailable("hybrid search is unavailable")
            try:
                target = self._build()
            except HybridUnavailable:
                self._remember_failure()
                raise
            except Exception as error:
                self._remember_failure()
                logger.info(
                    json.dumps(
                        {
                            "event": "hybrid_build_failed",
                            "error_type": type(error).__name__,
                        }
                    )
                )
                raise HybridUnavailable("hybrid search is unavailable") from None
            with self._lock:
                if target.archive_online:
                    self._target = target
                    self._fallback = None
                else:
                    self._fallback = target
                    self._fallback_until = (
                        self._now() + self.settings.hybrid_build_retry_seconds
                    )
                self._failure_until = 0.0
                return target
        finally:
            self._build_lock.release()

    def status(self):
        """Sanitized lifecycle facts; no paths, exception text or fake success."""
        configured = bool(self.settings.hybrid_cursor_signing_key.get_secret_value())
        status = {
            "state": "unknown",
            "search_configured": configured,
            "collection": self.settings.milvus_collection,
            "profile": self.settings.milvus_profile,
            "model_revision": None,
            "ranking_version": RANKING_VERSION,
            "generation": None,
            "coverage": "unknown",
            "archive_as_of": None,
            "repositories": None,
            "published_documents": None,
            "chunks": None,
            "latest_run": None,
        }
        try:
            manifest = ModelManifest.load()
        except EmbeddingError:
            manifest = None
        if manifest is not None:
            status["model_revision"] = manifest.revision
            if configured:
                status["generation"] = f"{manifest.revision}:{RANKING_VERSION}"
        try:
            counts = archive_counts(self.settings.archive_database_path)
        except Exception as error:  # status must stay a sanitized read-only view
            logger.info(
                json.dumps(
                    {
                        "event": "archive_status_unavailable",
                        "error_type": type(error).__name__,
                    }
                )
            )
            return status
        status.update(counts)
        status["state"] = (
            "uninitialized" if counts["repositories"] == 0 else "initialized"
        )
        return status

    def _remember_failure(self):
        with self._lock:
            self._fallback = None
            self._failure_until = self._now() + self.settings.hybrid_build_retry_seconds

    def _archive_store(self):
        with self._lock:
            if self._store is None:
                self._store = ArchiveStore(self.settings)
            return self._store

    def _load_embeddings(self):
        # Keep a successful model load across Milvus/archive failures: reloading
        # the model per request is the expensive part of a failed build.
        with self._lock:
            if self._embeddings is not None:
                return self._embeddings
        try:
            embeddings = EmbeddingAdapter.load()
        except EmbeddingError:
            raise HybridUnavailable("hybrid search is not configured") from None
        with self._lock:
            if self._embeddings is None:
                self._embeddings = embeddings
            return self._embeddings

    def _shared_executor(self):
        # One executor for every build, so swapping a live-only target for the
        # full stack never strands worker threads.
        with self._lock:
            if self._executor is None:
                self._executor = BoundedExecutor(
                    self.settings.hybrid_search_max_workers,
                    self.settings.hybrid_search_max_outstanding,
                )
            return self._executor

    def _archive_components(self):
        """Return ``(embeddings, vectors, revision)`` or raise ArchiveOffline."""
        try:
            embeddings = self._load_embeddings()
        except HybridUnavailable:
            raise ArchiveOffline("model") from None
        manifest = embeddings.manifest
        try:
            # Imported here so app boot never imports the Milvus SDK.
            from app.integrations.milvus import (
                MilvusAdapter,
                MilvusContractError,
                MilvusUnavailable,
            )
        except ImportError:
            raise ArchiveOffline("milvus") from None
        try:
            vectors = MilvusAdapter.connect(self.settings, manifest)
        except (MilvusContractError, MilvusUnavailable):
            raise ArchiveOffline("milvus") from None
        return embeddings, vectors, manifest.revision

    def _manifest_revision(self):
        with self._lock:
            if self._embeddings is not None:
                return self._embeddings.manifest.revision
        try:
            return ModelManifest.load().revision
        except EmbeddingError:
            return "unavailable"

    def _build(self):
        key = self.settings.hybrid_cursor_signing_key.get_secret_value()
        if len(key) < 32:
            raise HybridUnavailable("hybrid search is not configured")
        try:
            store = self._archive_store()
            reader = ArchiveGitHubReader(settings=self.settings)
        except (ArchiveGitHubError, OSError, RuntimeError):
            raise HybridUnavailable("hybrid search is unavailable") from None
        try:
            embeddings, vectors, revision = self._archive_components()
            archive_online = True
        except ArchiveOffline as offline:
            logger.info(
                json.dumps(
                    {"event": "hybrid_archive_offline", "component": str(offline)}
                )
            )
            embeddings = vectors = _OfflineArchive()
            revision = self._manifest_revision()
            archive_online = False
        eligibility = EligibilityService(store.connect, reader, self.settings)
        revalidator = FusedRevalidator(eligibility, reader, settings=self.settings)
        service = HybridSearchService(
            self.settings,
            GitHubKeywordCandidates(self.provider, self.settings),
            embeddings,
            vectors,
            eligibility,
            executor=self._shared_executor(),
        )
        pager = HybridPager(
            service,
            self.settings,
            revalidate=revalidator,
        )
        return HybridTarget(
            pager=pager,
            generation=f"{revision}:{RANKING_VERSION}",
            executor=service.executor,
            revalidator=revalidator,
            archive_online=archive_online,
        )
