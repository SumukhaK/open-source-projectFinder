"""Source-specific checks, isolated from API serving until D4 is approved."""

import json
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock

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

    @property
    def incomplete(self):
        return bool(self.issues)


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

    def _metadata(self, repo_id, name, now):
        with self._lock:
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
        result = self.reader.fetch_metadata(repo_id, name)
        metadata = json.loads(result.response.body)
        if live_eligible(repo_id, metadata):
            self._remember(repo_id, metadata, now)
        return metadata, now

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
            names = {}
            for repo_id in {hit["repo_id"] for hit in active}:
                row = db.execute(
                    "SELECT full_name, metadata_json FROM archive_repositories AS r "
                    "WHERE repo_id=? AND NOT EXISTS (SELECT 1 FROM "
                    "archive_suppressions AS s WHERE s.repo_id=r.repo_id)",
                    (repo_id,),
                ).fetchone()
                if row and _within_window(json.loads(row[1]).get("pushed_at"), now):
                    names[repo_id] = row[0]
        return [hit for hit in active if hit["repo_id"] in names], names

    def check(self, archive_hits, *, live=None):
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
        candidates, names = self._candidates(archive_hits, now)
        verified = {}
        validated_at = {}
        issues = []
        for repo_id, full_name in names.items():
            metadata = current.get(repo_id)
            checked = now
            if live is not None and repo_id in live and metadata is None:
                with self._lock:
                    self._cache.pop(repo_id, None)
                issues.append(EligibilityIssue(repo_id, "validation_failed"))
                continue
            if metadata is None:
                try:
                    metadata, checked = self._metadata(repo_id, full_name, self.now())
                except (
                    RepositoryNotFound,
                    RepositoryNotPublic,
                    RepositoryIdentityMismatch,
                ) as error:
                    reason = {
                        RepositoryNotFound: "not_found",
                        RepositoryNotPublic: "not_public",
                        RepositoryIdentityMismatch: "identity_mismatch",
                    }[type(error)]
                    self._suppress(repo_id, reason, now)
                    continue
                except ArchiveAuthenticationError:
                    return EligibilityResult(
                        tuple(current.values()),
                        (),
                        (EligibilityIssue(repo_id, "credential_invalid"),),
                    )
                except ArchiveGitHubError as error:
                    code = (
                        "rate_limited"
                        if isinstance(error, ArchiveRateLimited)
                        else "unavailable"
                        if isinstance(error, ArchiveUnavailable)
                        else "validation_failed"
                    )
                    issues.append(EligibilityIssue(repo_id, code))
                    continue
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
        candidates, _ = self._candidates(candidates, now)
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
        )
