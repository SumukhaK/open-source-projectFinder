"""Concurrent, deadline-bounded orchestration of the two hybrid sources.

The service is internal: it owns no HTTP route or cursor. T15 exposes it and
T14 adds pagination. Blocking CPU/HTTP/Milvus/SQLite work always runs in a
bounded executor so the event loop stays responsive and timed-out jobs cannot
grow an unbounded backlog.
"""

from __future__ import annotations

import asyncio
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from threading import BoundedSemaphore, Lock

from app.core.config import Settings
from app.integrations.milvus import (
    MilvusContractError,
    MilvusOperationError,
    MilvusUnavailable,
    ScalarFilters,
)
from app.services.eligibility import ArchiveEvidence, EligibilityResult
from app.services.embeddings import EmbeddingError, UnsupportedInput
from app.services.keyword_candidates import KeywordCandidate, KeywordCandidates
from app.services.keyword_query import CandidateFilters
from app.services.rank_fusion import FusedResults, SourceHealth, fuse_candidates

logger = logging.getLogger("reporadar.hybrid")

# A live source that finishes just after archive retrieval can still supply
# fresh metadata, but a slow live source must never starve archive validation.
_LIVE_METADATA_GRACE = 0.05


class BusyError(RuntimeError):
    """The bounded executor has no free slot for more work."""


class DeadlineExceeded(TimeoutError):
    """The overall hybrid-search deadline cannot fund another blocking call."""


@dataclass(frozen=True)
class LicenseSelection:
    github: str
    spdx: str


# One table maps a single typed value to the two source-specific spellings.
LICENSE_FILTERS = {
    "mit": LicenseSelection("mit", "MIT"),
    "apache-2.0": LicenseSelection("apache-2.0", "Apache-2.0"),
}


def license_selection(value):
    """Map one typed licence value to both source filters, or reject it."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Unsupported license filter")
    try:
        return LICENSE_FILTERS[value.strip().casefold()]
    except KeyError:
        raise ValueError("Unsupported license filter") from None


@dataclass(frozen=True)
class HybridSearchResult:
    fused: FusedResults
    status: str
    archive_reason: str | None = None


@dataclass(frozen=True)
class _ArchiveOutcome:
    evidence: tuple[ArchiveEvidence, ...] = ()
    status: str = "ok"
    reason: str | None = None


class BoundedExecutor:
    """Run blocking work in a bounded pool without queueing past the cap.

    A timed-out or disconnected caller keeps its slot until the worker really
    finishes. That is deliberate: it caps abandoned native work instead of
    pretending cancellation stops it.
    """

    def __init__(self, max_workers: int, max_outstanding: int):
        if max_workers < 1 or max_outstanding < 1:
            raise ValueError("Executor limits must be positive")
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="hybrid"
        )
        self._slots = BoundedSemaphore(max_outstanding)
        self._lock = Lock()
        self._active = 0
        self._closed = False

    @property
    def outstanding(self):
        with self._lock:
            return self._active

    async def run(self, work, *, timeout):
        if self._closed:
            raise BusyError("executor is closed")
        if timeout is None or timeout <= 0:
            raise DeadlineExceeded("deadline exhausted")
        if not self._slots.acquire(blocking=False):
            raise BusyError("executor is at capacity")
        with self._lock:
            self._active += 1
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def deliver(result=None, error=None):
            if future.cancelled():
                return
            if error is not None:
                future.set_exception(error)
            else:
                future.set_result(result)

        def finish(result, error):
            # Free the slot before waking the caller so a completed run never
            # observes phantom outstanding work.
            with self._lock:
                self._active -= 1
            self._slots.release()
            try:
                loop.call_soon_threadsafe(deliver, result, error)
            except RuntimeError:
                pass

        def task():
            try:
                result = work()
            except BaseException as error:
                finish(None, error)
            else:
                finish(result, None)

        try:
            pending = self._pool.submit(task)
        except RuntimeError:
            with self._lock:
                self._active -= 1
            self._slots.release()
            raise BusyError("executor is closed") from None
        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError:
            self._reclaim_queued(pending)
            if future.cancelled():
                raise DeadlineExceeded("deadline exhausted") from None
            raise
        except asyncio.CancelledError:
            self._reclaim_queued(pending)
            raise

    def _reclaim_queued(self, pending):
        # A job that never started will not call finish(); reclaim its slot.
        # A running job cannot be cancelled here and keeps its slot until it
        # really finishes, which caps abandoned native work.
        if pending.cancel():
            with self._lock:
                self._active -= 1
            self._slots.release()

    def close(self):
        if self._closed:
            return
        self._closed = True
        # Let already-admitted work finish so its slot is released normally.
        self._pool.shutdown(wait=False)


class HybridSearchService:
    """Invoke live GitHub and the archive concurrently under one deadline."""

    def __init__(
        self,
        settings: Settings,
        github,
        embeddings,
        vectors,
        eligibility,
        *,
        executor=None,
    ):
        self.settings = settings
        self.github = github
        self.embeddings = embeddings
        self.vectors = vectors
        self.eligibility = eligibility
        self.executor = executor or BoundedExecutor(
            settings.hybrid_search_max_workers,
            settings.hybrid_search_max_outstanding,
        )
        self._owns_executor = executor is None
        self._admission = asyncio.Semaphore(settings.hybrid_search_max_concurrent)

    async def search(self, token, idea, *, language=None, license=None):
        selection = license_selection(license)
        filters = CandidateFilters(
            language=language, license=selection.github if selection else None
        )
        archive_filters = ScalarFilters(
            language=language, license=selection.spdx if selection else None
        )
        loop = asyncio.get_running_loop()
        started = loop.time()
        deadline = started + self.settings.hybrid_search_budget
        if not await self._admit(deadline):
            return self._busy_result(loop, started)
        live_task = archive_task = None
        try:
            live_task = asyncio.create_task(self._live(token, idea, filters, deadline))
            archive_task = asyncio.create_task(
                self._archive(idea, archive_filters, deadline, live_task)
            )
            github_result, archive_outcome = await asyncio.gather(
                live_task, archive_task
            )
        except asyncio.CancelledError:
            for task in (live_task, archive_task):
                if task is not None and not task.done():
                    task.cancel()
            raise
        finally:
            self._admission.release()

        fused = fuse_candidates(
            github_result,
            archive_outcome.evidence,
            archive_status=archive_outcome.status,
        )
        fused = replace(
            fused,
            archive=SourceHealth(archive_outcome.status, archive_outcome.reason),
        )
        fused = _without_conflicting_snippets(fused)
        status = _overall_status(
            github_result.status, archive_outcome.status, fused.candidates
        )
        logger.info(
            "hybrid search status=%s github_status=%s archive_status=%s "
            "candidates=%d duration_ms=%d",
            status,
            github_result.status,
            archive_outcome.status,
            len(fused.candidates),
            int((loop.time() - started) * 1000),
        )
        return HybridSearchResult(fused, status, archive_outcome.reason)

    def close(self):
        if self._owns_executor:
            self.executor.close()

    async def _admit(self, deadline):
        if not self._admission.locked():
            await self._admission.acquire()
            return True
        remaining = deadline - asyncio.get_running_loop().time()
        timeout = min(max(remaining, 0), self.settings.hybrid_search_admission_timeout)
        if timeout <= 0:
            return False
        try:
            await asyncio.wait_for(self._admission.acquire(), timeout)
            return True
        except TimeoutError:
            return False

    def _busy_result(self, loop, started):
        fused = fuse_candidates(
            KeywordCandidates(status="failed", reason="busy"),
            (),
            archive_status="failed",
        )
        fused = replace(fused, archive=SourceHealth("failed", "busy"))
        logger.info(
            "hybrid search status=busy duration_ms=%d",
            int((loop.time() - started) * 1000),
        )
        return HybridSearchResult(fused, "busy", "busy")

    async def _live(self, token, idea, filters, deadline):
        try:
            result = await self.executor.run(
                lambda: self.github.search(token, idea, filters),
                timeout=_call_timeout(deadline, self.settings.github_timeout),
            )
        except DeadlineExceeded:
            return KeywordCandidates(status="failed", reason="timeout")
        except BusyError:
            return KeywordCandidates(status="failed", reason="busy")
        except Exception:
            return KeywordCandidates(status="failed", reason="unavailable")
        if not isinstance(result, KeywordCandidates):
            return KeywordCandidates(status="failed", reason="invalid_response")
        return result

    async def _archive(self, idea, filters, deadline, live_task):
        try:
            embedded = await self.executor.run(
                lambda: self.embeddings.embed([idea], kind="query"),
                timeout=_remaining(deadline),
            )
        except UnsupportedInput:
            return _ArchiveOutcome(status="failed", reason="query_not_supported")
        except DeadlineExceeded:
            return _ArchiveOutcome(status="failed", reason="timeout")
        except BusyError:
            return _ArchiveOutcome(status="failed", reason="busy")
        except EmbeddingError:
            return _ArchiveOutcome(status="failed", reason="embedding_failed")
        except Exception:
            return _ArchiveOutcome(status="failed", reason="unavailable")
        vector = _embedding_vector(embedded)
        if vector is None:
            return _ArchiveOutcome(status="failed", reason="invalid_response")

        limit = self.settings.hybrid_archive_initial_limit
        ceiling = self.settings.hybrid_archive_max_limit
        target = self.settings.hybrid_archive_target_repositories
        rows = []
        exhausted = False
        while True:
            try:
                page = await self.executor.run(
                    lambda: self.vectors.search(vector, limit=limit, filters=filters),
                    timeout=_call_timeout(deadline, self.settings.milvus_timeout),
                )
            except DeadlineExceeded:
                return _ArchiveOutcome(status="failed", reason="timeout")
            except BusyError:
                return _ArchiveOutcome(status="failed", reason="busy")
            except MilvusOperationError:
                return _ArchiveOutcome(status="failed", reason="operation_failed")
            except MilvusUnavailable:
                return _ArchiveOutcome(status="failed", reason="unavailable")
            except MilvusContractError:
                return _ArchiveOutcome(status="failed", reason="index_incompatible")
            except Exception:
                return _ArchiveOutcome(status="failed", reason="unavailable")
            if not isinstance(page, list) or any(
                not isinstance(row, dict) for row in page
            ):
                return _ArchiveOutcome(status="failed", reason="invalid_response")
            # A larger search already contains the previous top-k, so replace
            # rather than accumulate overlapping pages.
            rows = page
            if len(_distinct_repositories(rows)) >= target:
                break
            if len(page) < limit:
                break
            if limit >= ceiling:
                exhausted = True
                break
            limit = min(limit * 2, ceiling)

        hits = _dedupe_hits(rows)
        if not hits:
            return _ArchiveOutcome()
        live_metadata = await self._live_metadata(live_task, deadline)
        try:
            checked = await self.executor.run(
                lambda: self.eligibility.check(hits, live=live_metadata),
                timeout=_call_timeout(deadline, self.settings.archive_github_timeout),
            )
        except DeadlineExceeded:
            return _ArchiveOutcome(status="failed", reason="timeout")
        except BusyError:
            return _ArchiveOutcome(status="failed", reason="busy")
        except Exception:
            return _ArchiveOutcome(status="failed", reason="validation_failed")
        if not isinstance(checked, EligibilityResult):
            return _ArchiveOutcome(status="failed", reason="invalid_response")
        if checked.issues and not checked.archive:
            return _ArchiveOutcome(status="failed", reason="validation_failed")
        if exhausted:
            return _ArchiveOutcome(checked.archive, "incomplete", "overfetch_exhausted")
        if checked.issues:
            return _ArchiveOutcome(checked.archive, "incomplete", "validation_failed")
        # No issues and no evidence means every hit was definitively dropped
        # (archived, private, suppressed, stale or no longer catalogued). That is
        # a complete answer, not an unverified one.
        return _ArchiveOutcome(checked.archive, "ok", None)

    async def _live_metadata(self, task, deadline):
        if task is None:
            return None
        if not task.done():
            grace = min(_remaining(deadline), _LIVE_METADATA_GRACE)
            if grace > 0:
                await asyncio.wait({task}, timeout=grace)
        if not task.done() or task.cancelled():
            return None
        try:
            result = task.result()
        except Exception:
            return None
        if not isinstance(result, KeywordCandidates) or result.status not in (
            "ok",
            "incomplete",
        ):
            return None
        return {
            candidate.repo_id: candidate.metadata
            for candidate in result.candidates
            if isinstance(candidate, KeywordCandidate)
        }


def _remaining(deadline):
    return deadline - asyncio.get_running_loop().time()


def _call_timeout(deadline, setting):
    return min(_remaining(deadline), setting)


def _embedding_vector(value):
    if not isinstance(value, (list, tuple)) or len(value) != 1:
        return None
    vector = value[0]
    if not isinstance(vector, (list, tuple)) or not vector:
        return None
    if any(
        type(component) not in (int, float) or not math.isfinite(component)
        for component in vector
    ):
        return None
    return tuple(float(component) for component in vector)


def _distinct_repositories(rows):
    return {
        row["repo_id"]
        for row in rows
        if type(row.get("repo_id")) is int and row["repo_id"] > 0
    }


def _dedupe_hits(rows):
    seen = set()
    unique = []
    for row in rows:
        chunk_id = row.get("chunk_id")
        if isinstance(chunk_id, str):
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
        unique.append(row)
    return unique


def _without_conflicting_snippets(fused):
    if not any(card.license_conflict for card in fused.candidates):
        return fused
    return replace(
        fused,
        candidates=tuple(
            replace(card, archive=None) if card.license_conflict else card
            for card in fused.candidates
        ),
    )


def _overall_status(github_status, archive_status, candidates):
    if candidates:
        return "ok" if github_status == "ok" and archive_status == "ok" else "degraded"
    if github_status == "ok" and archive_status == "ok":
        return "empty"
    return "incomplete"
