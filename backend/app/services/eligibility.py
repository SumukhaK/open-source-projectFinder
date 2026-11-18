"""Source-specific checks, isolated from API serving until D4 is approved."""

import json
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Event, Lock

from app.core.config import ARCHIVE_VISIBILITY_CACHE_SIZE
from app.integrations.archive_github import (
    ArchiveAuthenticationError,
    ArchiveGitHubError,
    ArchiveRateLimited,
    ArchiveUnavailable,
    RepositoryIdentityMismatch,
    RepositoryNotFound,
    RepositoryNotPublic,
)
from app.services.archive_publication import filter_active_hits
from app.services.archive_retirement import SuppressionLedger, suppress
from app.services.live_scope import live_eligible

VISIBILITY_CHECK_CONCURRENCY = 4


@dataclass(frozen=True)
class ArchiveEvidence:
    hit: dict
    metadata: dict


@dataclass(frozen=True)
class EligibilityIssue:
    repo_id: int
    code: str


@dataclass(frozen=True)
class EligibilityResult:
    live: tuple[dict, ...]
    archive: tuple[ArchiveEvidence, ...]
    issues: tuple[EligibilityIssue, ...] = ()
    deferred: tuple[ArchiveEvidence, ...] = ()

    @property
    def incomplete(self):
        return bool(self.issues)


@dataclass(frozen=True)
class _Candidate:
    """One catalogue candidate with its best hit and stored card fields."""

    hit: dict
    full_name: str
    metadata: dict


def _cached_copy(metadata):
    """Copy a cached record so a caller cannot mutate the shared nested dicts."""
    copy = dict(metadata)
    for key in ("owner", "license"):
        value = copy.get(key)
        if isinstance(value, dict):
            copy[key] = dict(value)
    return copy


def _within_window(value, now):
    if not isinstance(value, str):
        return False
    try:
        pushed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return pushed.tzinfo is not None and now - timedelta(days=365) <= pushed <= now


def _catalogue_metadata(candidate):
    """Build a public card from catalogue fields without a GitHub call.

    Deferred candidates are never shown before a later page re-verifies them,
    so these fields only have to satisfy the same live-card shape. Name, owner,
    visibility and archive state come from the catalogue, not the display card.
    """
    full_name = candidate.full_name
    owner, _, name = full_name.partition("/")
    metadata = candidate.metadata
    stars = metadata.get("stargazers_count")
    language = metadata.get("language")
    license_spdx = metadata.get("license_spdx")
    return {
        "id": candidate.hit["repo_id"],
        "name": name or full_name,
        "full_name": full_name,
        "owner": {"login": owner or full_name, "avatar_url": ""},
        "description": metadata.get("description"),
        "stargazers_count": stars if type(stars) is int and stars >= 0 else 0,
        "language": language if isinstance(language, str) else None,
        "license": (
            {"spdx_id": license_spdx}
            if isinstance(license_spdx, str) and license_spdx
            else None
        ),
        "private": False,
        "archived": False,
        "visibility": "public",
        "pushed_at": metadata.get("pushed_at"),
    }


class _Flight:
    """One in-flight GitHub visibility call that concurrent checks share."""

    def __init__(self):
        self.done = Event()
        self.body = None
        self.checked = None
        self.error = None


class EligibilityService:
    """Pass bounded raw live metadata keyed by expected numeric ID per request.

    `connect` is ArchiveStore.connect; `reader` is a dedicated T04 public-read
    reader. No HTTP is performed in a catalogue transaction. Suppression is
    sticky: later tasks must explicitly reconcile it before serving again.
    """

    def __init__(self, connect, reader, settings, *, now=None):
        self.connect = connect
        self.reader = reader
        self.settings = settings
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._cache = OrderedDict()
        self._flights = {}
        self._lock = Lock()

    def _suppress(self, repo_id, reason, now):
        with self.connect() as db:
            known = db.execute(
                "SELECT 1 FROM archive_suppressions WHERE repo_id=?", (repo_id,)
            ).fetchone()
        if known is None:
            # T20: the first decision also goes to the content-free ledger so
            # a restored backup can reapply it; later reasons stay sticky here.
            suppress(
                self.connect,
                SuppressionLedger.for_catalogue(self.connect),
                repo_id,
                reason,
                now.timestamp(),
            )
        with self._lock:
            self._cache.pop(repo_id, None)

    def _cached_locked(self, repo_id, now):
        cached = self._cache.get(repo_id)
        if cached:
            checked, metadata = cached
            if (
                0
                <= (now - checked).total_seconds()
                < self.settings.archive_visibility_ttl_seconds
            ):
                return _cached_copy(metadata), checked
            self._cache.pop(repo_id)
        return None

    def _cached(self, repo_id, now):
        with self._lock:
            return self._cached_locked(repo_id, now)

    def _flight_timeout(self):
        """Upper bound on one fetch, derived from the reader's own retries."""
        attempts = self.settings.archive_github_attempts
        return (
            attempts * self.settings.archive_github_timeout
            + (attempts - 1) * self.settings.archive_github_retry_max_wait
        )

    def _fetch_metadata(self, repo_id, name, checked):
        """Fetch one repository, sharing an in-flight call with other checks.

        A search that hit its deadline leaves its check running in a worker
        thread; the next search must reuse that call, not repeat it (T28).
        Returns ``(metadata, checked)`` using the leader's start time.
        """
        with self._lock:
            hit = self._cached_locked(repo_id, checked)
            if hit is not None:
                return hit
            flight = self._flights.get(repo_id)
            leader = flight is None
            if leader:
                flight = self._flights[repo_id] = _Flight()
        if not leader:
            # A stalled leader must not pin a search open indefinitely.
            if not flight.done.wait(self._flight_timeout()):
                raise ArchiveUnavailable("in-flight visibility check did not finish")
            if flight.error is not None:
                raise flight.error
            return json.loads(flight.body), flight.checked
        try:
            result = self.reader.fetch_metadata(repo_id, name)
            metadata = json.loads(result.response.body)
            if live_eligible(repo_id, metadata):
                self._remember(repo_id, metadata, checked)
            flight.body, flight.checked = result.response.body, checked
            return metadata, checked
        except BaseException as error:
            flight.error = error
            raise
        finally:
            with self._lock:
                self._flights.pop(repo_id, None)
            flight.done.set()

    def _prefetch(self, pending, fetched, errors):
        """Fetch uncached metadata concurrently, at most the fixed bound at once.

        ``pending`` holds ``(repo_id, full_name, checked)`` in candidate order.
        Returns the repository whose credential was rejected, if any, so the
        caller can return without waiting for the other fetches.
        """
        rejected = None
        pool = ThreadPoolExecutor(
            max_workers=min(VISIBILITY_CHECK_CONCURRENCY, len(pending)),
            thread_name_prefix="visibility-check",
        )
        try:
            futures = {
                pool.submit(self._fetch_metadata, repo_id, full_name, checked): (
                    repo_id,
                    checked,
                )
                for repo_id, full_name, checked in pending
            }
            for future in as_completed(futures):
                repo_id, checked = futures[future]
                try:
                    fetched[repo_id] = future.result()
                except ArchiveAuthenticationError as error:
                    errors[repo_id] = error
                    rejected = repo_id
                    break
                except Exception as error:  # re-raised in candidate order
                    errors[repo_id] = error
        finally:
            # Never wait for a fetch that is still running; the caller may
            # already have a definitive credential failure.
            pool.shutdown(wait=False, cancel_futures=True)
        return rejected

    def _remember(self, repo_id, metadata, now):
        # Store a bounded public card subset plus the validation fields, never
        # provider response bodies, README text or arbitrary URLs.
        owner = metadata.get("owner")
        license_data = metadata.get("license")
        cached = {
            "id": metadata.get("id"),
            "name": metadata.get("name"),
            "full_name": metadata.get("full_name"),
            "owner": (
                {
                    "login": owner.get("login"),
                    "avatar_url": owner.get("avatar_url", ""),
                }
                if isinstance(owner, dict)
                else None
            ),
            "description": metadata.get("description"),
            "stargazers_count": metadata.get("stargazers_count"),
            "language": metadata.get("language"),
            "license": (
                {"spdx_id": license_data.get("spdx_id")}
                if isinstance(license_data, dict)
                else None
            ),
            "private": metadata.get("private"),
            "archived": metadata.get("archived"),
            "pushed_at": metadata.get("pushed_at"),
        }
        cached["visibility"] = metadata.get("visibility", "public")
        with self._lock:
            self._cache[repo_id] = (now, cached)
            self._cache.move_to_end(repo_id)
            while len(self._cache) > ARCHIVE_VISIBILITY_CACHE_SIZE:
                self._cache.popitem(last=False)

    def _candidates(self, hits, now):
        with self.connect() as db:
            active = filter_active_hits(db, hits)
            records = {}
            for hit in active:
                repo_id = hit["repo_id"]
                if repo_id in records:
                    continue
                row = db.execute(
                    "SELECT full_name, metadata_json FROM archive_repositories AS r "
                    "WHERE repo_id=? AND NOT EXISTS (SELECT 1 FROM "
                    "archive_suppressions AS s WHERE s.repo_id=r.repo_id)",
                    (repo_id,),
                ).fetchone()
                if row:
                    metadata = json.loads(row[1])
                    if _within_window(metadata.get("pushed_at"), now):
                        records[repo_id] = _Candidate(hit, row[0], metadata)
        return [hit for hit in active if hit["repo_id"] in records], records

    def check(self, archive_hits, *, live=None, archive_only_limit=None):
        now = self.now().astimezone(timezone.utc)
        current = {
            repo_id: dict(metadata)
            for repo_id, metadata in (live or {}).items()
            if live_eligible(repo_id, metadata)
        }
        for repo_id, metadata in (live or {}).items():
            if (
                type(repo_id) is not int
                or not 0 < repo_id < 2**63
                or not isinstance(metadata, dict)
            ):
                continue
            if type(metadata.get("id")) is int and metadata["id"] != repo_id:
                self._suppress(repo_id, "identity_mismatch", now)
            elif metadata.get("id") == repo_id:
                if metadata.get("private") is True or metadata.get("visibility") in (
                    "private",
                    "internal",
                ):
                    self._suppress(repo_id, "not_public", now)
                elif metadata.get("archived") is True:
                    self._suppress(repo_id, "archived", now)
        candidates, records = self._candidates(archive_hits, now)
        verified = {}
        validated_at = {}
        issues = []

        # Resolve cache hits in candidate order and queue the rest. The fetches
        # run concurrently, but suppressions, issues and cache writes below are
        # still applied in the original candidate order. ``archive_only_limit``
        # spends GitHub calls only on uncached, archive-only candidates: cache
        # hits and live overlaps are free, and candidates past the budget are
        # deferred for a later page to verify.
        cached = {}
        pending = []
        deferred = {}
        budget = archive_only_limit
        for repo_id, record in records.items():
            if repo_id in current:
                continue
            if live is not None and repo_id in live:
                # Malformed or ineligible live metadata never falls back to a
                # cached public record and never spends an HTTP call.
                continue
            checked = self.now()
            hit = self._cached(repo_id, checked)
            if hit is not None:
                cached[repo_id] = hit
                continue
            if budget is not None:
                if budget <= 0:
                    deferred[repo_id] = record
                    continue
                budget -= 1
            pending.append((repo_id, record.full_name, checked))

        fetched = {}
        errors = {}
        if pending:
            rejected = self._prefetch(pending, fetched, errors)
            if rejected is not None:
                return EligibilityResult(
                    tuple(current.values()),
                    (),
                    (EligibilityIssue(rejected, "credential_invalid"),),
                )

        for repo_id in records:
            if repo_id in deferred:
                # Deferred candidates are re-verified by a later page; this
                # call neither verifies nor reports them.
                continue
            metadata = current.get(repo_id)
            checked = now
            if live is not None and repo_id in live and metadata is None:
                with self._lock:
                    self._cache.pop(repo_id, None)
                issues.append(EligibilityIssue(repo_id, "validation_failed"))
                continue
            if metadata is None:
                error = errors.get(repo_id)
                if error is not None:
                    if isinstance(
                        error,
                        (
                            RepositoryNotFound,
                            RepositoryNotPublic,
                            RepositoryIdentityMismatch,
                        ),
                    ):
                        reason = {
                            RepositoryNotFound: "not_found",
                            RepositoryNotPublic: "not_public",
                            RepositoryIdentityMismatch: "identity_mismatch",
                        }[type(error)]
                        self._suppress(repo_id, reason, now)
                        continue
                    if isinstance(error, ArchiveGitHubError):
                        code = (
                            "rate_limited"
                            if isinstance(error, ArchiveRateLimited)
                            else "unavailable"
                            if isinstance(error, ArchiveUnavailable)
                            else "validation_failed"
                        )
                        issues.append(EligibilityIssue(repo_id, code))
                        continue
                    raise error
                if repo_id in fetched:
                    metadata, checked = fetched[repo_id]
                else:
                    metadata, checked = cached[repo_id]
            if metadata.get("archived") is True:
                self._suppress(repo_id, "archived", now)
                continue
            if metadata.get("private") is True:
                self._suppress(repo_id, "not_public", now)
                continue
            if not live_eligible(repo_id, metadata):
                issues.append(EligibilityIssue(repo_id, "validation_failed"))
                continue
            # A cache hit must not slide its original validation time forward.
            if repo_id in current:
                self._remember(repo_id, metadata, now)
            if _within_window(metadata.get("pushed_at"), now):
                verified[repo_id] = metadata
                validated_at[repo_id] = checked
        candidates, still_active = self._candidates(candidates, now)
        finished = self.now()
        for repo_id, checked in validated_at.items():
            if (
                not 0
                <= (finished - checked).total_seconds()
                < self.settings.archive_visibility_ttl_seconds
            ):
                verified.pop(repo_id)
                issues.append(EligibilityIssue(repo_id, "validation_expired"))
        return EligibilityResult(
            tuple(current.values()),
            tuple(
                ArchiveEvidence(hit, dict(verified[hit["repo_id"]]))
                for hit in candidates
                if hit["repo_id"] in verified
            ),
            tuple(issues),
            tuple(
                ArchiveEvidence(record.hit, _catalogue_metadata(record))
                for repo_id, record in deferred.items()
                if repo_id in still_active
            ),
        )
