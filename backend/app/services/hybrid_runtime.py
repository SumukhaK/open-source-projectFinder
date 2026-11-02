"""Lazy hybrid serving stack and the T10 later-page revalidation adapter.

Nothing here connects to Milvus, loads the embedding model or opens the archive
catalogue at import time. A missing or broken optional component makes the v1
route return a typed "unavailable" error while the legacy API keeps serving.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from threading import RLock

from app.core.archive_store import ArchiveStore
from app.core.config import Settings
from app.integrations.archive_github import ArchiveGitHubError, ArchiveGitHubReader
from app.services.eligibility import EligibilityService
from app.services.embeddings import EmbeddingAdapter, EmbeddingError, ModelManifest
from app.services.fused_cursor import HybridPager
from app.services.hybrid_search import BoundedExecutor, HybridSearchService
from app.services.keyword_candidates import GitHubKeywordCandidates
from app.services.rank_fusion import RANKING_VERSION

logger = logging.getLogger("reporadar.hybrid")


class HybridUnavailable(RuntimeError):
    """A required serving component is missing; the v1 route cannot search."""


@dataclass(frozen=True)
class HybridTarget:
    pager: HybridPager
    generation: str
    executor: BoundedExecutor


class FusedRevalidator:
    """Adapt fused cards to T10 ``EligibilityService.check`` input.

    Archived cards become T07 hit identities so T10 re-reads their active
    revision and fresh metadata. Live-only cards are re-read through the same
    public reader; stored snapshot metadata is never reused as the check.
    Anything that cannot be freshly verified is dropped (fail closed).
    """

    def __init__(self, eligibility, reader):
        self.eligibility = eligibility
        self.reader = reader

    def __call__(self, candidates):
        hits = []
        live = {}
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
            metadata = self._fresh(candidate)
            if metadata is not None:
                live[candidate.repo_id] = metadata
        checked = self.eligibility.check(hits, live=live)
        kept = {metadata.get("id") for metadata in checked.live}
        kept.update(evidence.hit["repo_id"] for evidence in checked.archive)
        return [candidate for candidate in candidates if candidate.repo_id in kept]

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


def archive_counts(connect):
    """Read bounded catalogue counts and the latest run without exposing paths."""
    with connect() as db:
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

    def __init__(self, settings: Settings, *, provider):
        self.settings = settings
        self.provider = provider
        self._lock = RLock()
        self._store = None
        self._target = None

    def target(self):
        with self._lock:
            if self._target is None:
                self._target = self._build()
            return self._target

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
            counts = archive_counts(self._archive_store().connect)
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

    def _archive_store(self):
        with self._lock:
            if self._store is None:
                self._store = ArchiveStore(self.settings)
            return self._store

    def _build(self):
        key = self.settings.hybrid_cursor_signing_key.get_secret_value()
        if len(key) < 32:
            raise HybridUnavailable("hybrid search is not configured")
        try:
            embeddings = EmbeddingAdapter.load()
        except EmbeddingError:
            raise HybridUnavailable("hybrid search is not configured") from None
        manifest = embeddings.manifest
        # Imported here so app boot never imports the Milvus SDK.
        from app.integrations.milvus import (
            MilvusAdapter,
            MilvusContractError,
            MilvusUnavailable,
        )

        try:
            vectors = MilvusAdapter.connect(self.settings, manifest)
        except (MilvusContractError, MilvusUnavailable):
            raise HybridUnavailable("hybrid search is unavailable") from None
        try:
            store = self._archive_store()
            reader = ArchiveGitHubReader(settings=self.settings)
        except (ArchiveGitHubError, OSError, RuntimeError):
            vectors.close()
            raise HybridUnavailable("hybrid search is unavailable") from None
        eligibility = EligibilityService(store.connect, reader, self.settings)
        service = HybridSearchService(
            self.settings,
            GitHubKeywordCandidates(self.provider, self.settings),
            embeddings,
            vectors,
            eligibility,
        )
        pager = HybridPager(
            service,
            self.settings,
            revalidate=FusedRevalidator(eligibility, reader),
        )
        return HybridTarget(
            pager=pager,
            generation=f"{manifest.revision}:{RANKING_VERSION}",
            executor=service.executor,
        )
