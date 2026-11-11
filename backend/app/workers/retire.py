"""T20's daily privacy/removal sweep (D4), a manual local operator command.

Order follows D4: finish purging content that is already suppressed, then
re-check every known repository by numeric ID (private/deleted/archived/
blocked first-class suppressions, then licence, then 365-day expiry, which only
purges), then re-check suppressed IDs so a repository that is public and
eligible again is lifted. Credential, quota and 5xx failures stop the sweep
without removing anything; a broad 403 is never treated as a removal signal.
"""

from __future__ import annotations

from datetime import timedelta

from app.integrations.archive_github import (
    ArchiveAuthenticationError,
    ArchiveForbidden,
    ArchiveGitHubError,
    ArchiveRateLimited,
    ArchiveRequestError,
    ArchiveUnavailable,
    RepositoryIdentityMismatch,
    RepositoryNotFound,
    RepositoryNotPublic,
)
from app.services.archive_retirement import (
    STICKY_REASONS,
    PurgeAborted,
    SuppressionLedger,
    compact_runs,
    lift,
    purge_repository,
    reapply,
    suppress,
    sweep_unreferenced_files,
)
from app.services.archive_runs import WriterBusy, publication_writer
from app.workers.archive import (
    ELIGIBILITY_DAYS,
    IneligibleRepository,
    check_eligibility,
)

_SUPPRESS = {
    "not_public": "not_public",
    "archived": "archived",
    "license_missing": "licence",
    "license_not_allowed": "licence",
}
# Not unsafe: content is purged but nothing is suppressed, so a repository
# that becomes eligible again can return through an ordinary ingest.
_PURGE_ONLY = frozenset({"stale", "fork"})


# Each pair reads the next window after the saved cursor, then wraps around.
_KNOWN = (
    "SELECT r.repo_id, r.active_revision FROM archive_repositories AS r "
    "WHERE NOT EXISTS (SELECT 1 FROM archive_suppressions AS s "
    "WHERE s.repo_id=r.repo_id) AND r.repo_id > ? ORDER BY r.repo_id LIMIT ?",
    "SELECT r.repo_id, r.active_revision FROM archive_repositories AS r "
    "WHERE NOT EXISTS (SELECT 1 FROM archive_suppressions AS s "
    "WHERE s.repo_id=r.repo_id) AND r.repo_id <= ? ORDER BY r.repo_id LIMIT ?",
)
_SUPPRESSED = (
    "SELECT repo_id, reason FROM archive_suppressions WHERE observed_at < ? "
    "AND repo_id > ? ORDER BY repo_id LIMIT ?",
    "SELECT repo_id, reason FROM archive_suppressions WHERE observed_at < ? "
    "AND repo_id <= ? ORDER BY repo_id LIMIT ?",
)


def _rotation(connect, name, queries, limit, params):
    """Return up to ``limit`` rows after the saved cursor, wrapping once."""
    with connect() as db:
        row = db.execute(
            "SELECT cursor FROM archive_sweep_state WHERE name=?", (name,)
        ).fetchone()
        cursor = row[0] if row else 0
        rows = db.execute(queries[0], (*params, cursor, limit)).fetchall()
        if len(rows) < limit:
            rows += db.execute(
                queries[1], (*params, cursor, limit - len(rows))
            ).fetchall()
    return rows


def _advance(connect, name, repo_id):
    with connect(write=True) as db:
        db.execute(
            "INSERT INTO archive_sweep_state(name, cursor) VALUES(?, ?) "
            "ON CONFLICT(name) DO UPDATE SET cursor=excluded.cursor",
            (name, repo_id),
        )


class _Stop(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def sweep(runtime, *, now, limit=1000, remove_ids=()):
    """Run one bounded sweep and return a content-free summary."""
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError("--limit must be an integer from 1 through 10000")
    connect, at = runtime.connect, now.timestamp()
    ledger = SuppressionLedger.for_catalogue(connect)
    summary = {
        "reapplied": reapply(connect, ledger),
        "removed": 0,
        "suppressed": {},
        "purged": 0,
        "expired": 0,
        "lifted": 0,
        "checked": 0,
        "issues": 0,
        "stop_reason": "finished",
    }
    for repo_id in remove_ids:
        suppress(connect, ledger, repo_id, "operator", at)
        summary["removed"] += 1
    try:
        _purge_suppressed(runtime, summary)
        _check_known(runtime, ledger, now, limit, summary)
        _recheck_suppressed(runtime, ledger, now, limit, summary)
        # Retention takes the writer lock and a fenced lease, so it never runs
        # while a refresh/backfill owns a live lease and could reuse a file.
        with publication_writer(connect):
            summary["files"] = sweep_unreferenced_files(connect, runtime.content, at)
            summary["runs"] = compact_runs(connect, at)
    except _Stop as stop:
        summary["stop_reason"] = stop.reason
    except WriterBusy:
        summary["stop_reason"] = "busy"
    return summary


def _purge_suppressed(runtime, summary):
    with runtime.connect() as db:
        repo_ids = [
            row[0]
            for row in db.execute(
                "SELECT r.repo_id FROM archive_repositories AS r JOIN "
                "archive_suppressions AS s USING(repo_id) ORDER BY r.repo_id"
            )
        ]
    for repo_id in repo_ids:
        _purge(runtime, repo_id, summary)


def _purge(runtime, repo_id, summary, **guard):
    try:
        purge_repository(
            runtime.connect, runtime.vectors, runtime.content, repo_id, **guard
        )
    except WriterBusy:
        # Another writer owns a live lease; serving is already blocked by the
        # suppression row, so stop and let the next sweep finish the purge.
        raise _Stop("busy") from None
    except PurgeAborted:
        summary["issues"] += 1
        return
    summary["purged"] += 1


def _fetch(runtime, repo_id):
    """Return metadata, a suppression reason, or None for a non-decisive error."""
    try:
        return runtime.reader.fetch_metadata_by_id(repo_id).metadata
    except RepositoryNotPublic:
        return "not_public"
    except RepositoryNotFound:
        # Ambiguous (private, transferred or deleted): hidden, never "deleted".
        return "not_found"
    except RepositoryIdentityMismatch:
        return "identity_mismatch"
    except ArchiveAuthenticationError:
        raise _Stop("credential") from None
    except (ArchiveRateLimited, ArchiveUnavailable):
        raise _Stop("rate_limit") from None
    except ArchiveForbidden:
        # A broad 403 can be a token/scope problem; never remove on it.
        raise _Stop("forbidden") from None
    except ArchiveRequestError as error:
        if getattr(error.response, "status", None) == 451:
            return "blocked"
        return None
    except ArchiveGitHubError:
        return None


def _check_known(runtime, ledger, now, limit, summary):
    cutoff = now - timedelta(days=ELIGIBILITY_DAYS)
    allowlist = runtime.settings.archive_license_allowlist
    rows = _rotation(runtime.connect, "known", _KNOWN, limit, ())
    for repo_id, active in rows:
        _advance(runtime.connect, "known", repo_id)
        summary["checked"] += 1
        result = _fetch(runtime, repo_id)
        if result is None:
            summary["issues"] += 1
            continue
        if isinstance(result, str):
            _suppress_and_purge(runtime, ledger, repo_id, result, now, summary)
            continue
        try:
            check_eligibility(result, allowlist, cutoff)
        except IneligibleRepository as error:
            if error.reason in _SUPPRESS:
                reason = _SUPPRESS[error.reason]
                _suppress_and_purge(runtime, ledger, repo_id, reason, now, summary)
            elif error.reason in _PURGE_ONLY:
                summary["expired"] += 1
                _purge(runtime, repo_id, summary, expect_active=active)
            else:
                summary["issues"] += 1


def _suppress_and_purge(runtime, ledger, repo_id, reason, now, summary):
    suppress(runtime.connect, ledger, repo_id, reason, now.timestamp())
    summary["suppressed"][reason] = summary["suppressed"].get(reason, 0) + 1
    _purge(runtime, repo_id, summary)


def _recheck_suppressed(runtime, ledger, now, limit, summary):
    cutoff = now - timedelta(days=ELIGIBILITY_DAYS)
    # Decisions made earlier in this sweep are not re-checked at once.
    rows = _rotation(
        runtime.connect, "suppressed", _SUPPRESSED, limit, (now.timestamp(),)
    )
    for repo_id, reason in rows:
        _advance(runtime.connect, "suppressed", repo_id)
        if reason in STICKY_REASONS:
            continue
        result = _fetch(runtime, repo_id)
        if result is None or isinstance(result, str):
            continue
        try:
            check_eligibility(
                result, runtime.settings.archive_license_allowlist, cutoff
            )
        except IneligibleRepository:
            continue
        # Public and eligible again under a valid credential: allow it back.
        lift(runtime.connect, ledger, repo_id, now.timestamp())
        summary["lifted"] += 1
