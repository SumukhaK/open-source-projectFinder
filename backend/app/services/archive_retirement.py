"""T20 suppression ledger, bounded purge and retention for the archive.

Suppression is logical first: a row in ``archive_suppressions`` stops serving
immediately (T10 filters on it). The same decision is appended to a
content-free JSON-lines ledger kept next to, but outside, the catalogue file,
so a restored historical backup can have the *current* decisions reapplied
(T22). Physical cleanup (vectors, raw/normalized files, catalogue rows) is
bounded and idempotent and can be retried after any partial failure.

Purging keeps every ``archive_tasks`` cleanup tombstone, so the per-repository
generation high-water mark used by T19a survives and a returning repository
never reuses generation-1 chunk IDs.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from app.services.archive_publication import _batch_size, _batches
from app.services.archive_runs import check_lease, publication_writer

LEDGER_NAME = "suppression-ledger.jsonl"
LEDGER_VERSION = 1
SUPPRESSION_REASONS = frozenset(
    {
        "not_public",
        "archived",
        "not_found",
        "identity_mismatch",
        "licence",
        "blocked",
        "operator",
    }
)
# Only the owner can undo an operator removal; every other reason is lifted
# when a fresh ID-bound check shows the repository is eligible again.
STICKY_REASONS = frozenset({"operator"})
SUPERSEDED_FILE_DAYS = 30  # D3: superseded/raw content
RUN_HISTORY_DAYS = 90  # D3: content-free run history
_DAY = 86400
# Default purge guard: the repository must still be suppressed.
SUPPRESSED = object()


class LedgerError(Exception):
    """The suppression ledger is missing, unsafe or malformed."""


class PurgeAborted(Exception):
    """The purge decision is stale; nothing was removed."""


@dataclass(frozen=True)
class PurgeResult:
    repo_id: int
    documents: int
    vectors: int
    files: int


class SuppressionLedger:
    """Append-only, fsynced, content-free record of suppress/lift decisions.

    Each line holds only a repository ID, action, reason, time and format
    version: never names, README text, metadata or credentials.
    """

    def __init__(self, path):
        self.path = Path(path)

    @classmethod
    def for_catalogue(cls, connect):
        """The ledger beside the catalogue file actually in use.

        It is a separate file, so a SQLite backup of the catalogue never
        carries (or rolls back) the current suppression decisions.
        """
        with connect() as db:
            path = db.execute("PRAGMA database_list").fetchone()[2]
        if not path:
            raise LedgerError("the suppression ledger requires a file-backed catalogue")
        return cls(Path(path).parent / LEDGER_NAME)

    def append(self, repo_id, action, reason, at):
        if type(repo_id) is not int or not 0 < repo_id < 2**63:
            raise LedgerError("ledger repository id must be a positive integer")
        if action not in ("suppress", "lift"):
            raise LedgerError("ledger action must be suppress or lift")
        if action == "suppress" and reason not in SUPPRESSION_REASONS:
            raise LedgerError("ledger reason is not an approved suppression reason")
        line = json.dumps(
            {
                "v": LEDGER_VERSION,
                "repo_id": repo_id,
                "action": action,
                "reason": reason if action == "suppress" else None,
                "at": float(at),
            },
            sort_keys=True,
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise LedgerError("suppression ledger must be a private regular file")
            if os.name == "posix" and info.st_mode & 0o077:
                raise LedgerError("suppression ledger must be private (0600)")
            os.write(fd, (line + "\n").encode("ascii"))
            os.fsync(fd)
        finally:
            os.close(fd)

    def current(self):
        """Return ``{repo_id: (reason, at)}`` for IDs whose last action is suppress."""
        if not self.path.exists():
            return {}
        state = {}
        with open(self.path, encoding="ascii") as handle:
            for number, line in enumerate(handle, 1):
                if not line.endswith("\n"):
                    # A torn final append never committed; ignore only that line.
                    break
                try:
                    entry = json.loads(line)
                    repo_id, action = entry["repo_id"], entry["action"]
                except (ValueError, KeyError, TypeError) as error:
                    raise LedgerError(f"ledger line {number} is malformed") from error
                if entry.get("v") != LEDGER_VERSION or type(repo_id) is not int:
                    raise LedgerError(f"ledger line {number} is malformed")
                if action == "suppress" and entry.get("reason") in SUPPRESSION_REASONS:
                    state[repo_id] = (entry["reason"], float(entry["at"]))
                elif action == "lift":
                    state.pop(repo_id, None)
                else:
                    raise LedgerError(f"ledger line {number} is malformed")
        return state


def suppress(connect, ledger, repo_id, reason, at):
    """Record a suppression durably, then stop serving it immediately.

    Repeating an existing decision is a no-op, so per-request serving checks
    do not grow the ledger.
    """
    with connect() as db:
        row = db.execute(
            "SELECT reason FROM archive_suppressions WHERE repo_id=?", (repo_id,)
        ).fetchone()
    if row is not None and row[0] == reason:
        return
    ledger.append(repo_id, "suppress", reason, at)
    with connect(write=True) as db:
        db.execute(
            "INSERT INTO archive_suppressions (repo_id, reason, observed_at) "
            "VALUES (?, ?, ?) ON CONFLICT(repo_id) DO UPDATE SET "
            "reason=excluded.reason, observed_at=excluded.observed_at",
            (repo_id, reason, at),
        )


def lift(connect, ledger, repo_id, at):
    """Allow a repository again; its content returns only through a new ingest."""
    ledger.append(repo_id, "lift", None, at)
    with connect(write=True) as db:
        db.execute("DELETE FROM archive_suppressions WHERE repo_id=?", (repo_id,))


def reapply(connect, ledger):
    """Make the catalogue's suppression rows match the current ledger.

    Used after a crash between the ledger append and the catalogue write, and
    by T22 after restoring an older catalogue. Returns (added, removed).
    """
    current = ledger.current()
    with connect(write=True) as db:
        rows = {
            row[0]: row[1]
            for row in db.execute("SELECT repo_id, reason FROM archive_suppressions")
        }
        added = 0
        for repo_id, (reason, at) in current.items():
            if rows.get(repo_id) != reason:
                db.execute(
                    "INSERT INTO archive_suppressions (repo_id, reason, observed_at) "
                    "VALUES (?, ?, ?) ON CONFLICT(repo_id) DO UPDATE SET "
                    "reason=excluded.reason, observed_at=excluded.observed_at",
                    (repo_id, reason, at),
                )
                added += 1
        removed = [repo_id for repo_id in rows if repo_id not in current]
        db.executemany(
            "DELETE FROM archive_suppressions WHERE repo_id=?",
            [(repo_id,) for repo_id in removed],
        )
    return added, len(removed)


def purge_repository(
    connect, vectors, content, repo_id, *, expect_active=SUPPRESSED, lease=None
):
    """Remove every revision, vector, file and metadata row of one repository.

    Order makes partial failure safe and retryable: serving stops first
    (active revision cleared, tombstones recorded), then vectors, then files,
    then catalogue rows. By default the repository must still be suppressed
    (a lifted suppression aborts). A non-suppression purge (expired or
    otherwise ineligible) passes the active revision its decision saw, so a
    newer publication since then aborts it instead of removing safe content.
    """
    with publication_writer(connect, lease) as active_lease:
        with connect(write=True) as db:
            check_lease(db, active_lease)
            repo = db.execute(
                "SELECT active_revision FROM archive_repositories WHERE repo_id=?",
                (repo_id,),
            ).fetchone()
            suppressed = db.execute(
                "SELECT 1 FROM archive_suppressions WHERE repo_id=?", (repo_id,)
            ).fetchone()
            if expect_active is SUPPRESSED and suppressed is None:
                raise PurgeAborted("repository is no longer suppressed")
            if expect_active is not SUPPRESSED and (
                repo is None or repo[0] != expect_active
            ):
                raise PurgeAborted("active revision changed since the purge decision")
            documents = db.execute(
                "SELECT revision, generation, raw_path, normalized_path "
                "FROM archive_documents WHERE repo_id=?",
                (repo_id,),
            ).fetchall()
            if repo is not None:
                db.execute(
                    "UPDATE archive_repositories SET active_revision=NULL WHERE repo_id=?",
                    (repo_id,),
                )
            chunk_ids = tuple(
                row[0]
                for row in db.execute(
                    "SELECT chunk_id FROM archive_chunks WHERE repo_id=? "
                    "ORDER BY revision, ordinal",
                    (repo_id,),
                )
            )
            # Persist before remote deletion: a timeout does not cancel server
            # work, and the tombstone keeps the generation high-water mark.
            db.executemany(
                "INSERT INTO archive_tasks(run_id,repo_id,revision,stage,generation) "
                "VALUES(?,?,?,'cleanup',?) ON CONFLICT(repo_id,revision) DO UPDATE SET "
                "stage='cleanup', generation=MAX(generation, excluded.generation)",
                [(active_lease.run_id, repo_id, row[0], row[1]) for row in documents],
            )
        for batch in _batches(chunk_ids, _batch_size(vectors)):
            with connect() as db:
                check_lease(db, active_lease)
            vectors.delete(batch)
        paths = {
            path
            for row in documents
            for path in (row[2], row[3])
            if isinstance(path, str)
        }
        with connect() as db:
            shared = {
                path
                for path in paths
                if db.execute(
                    "SELECT 1 FROM archive_documents WHERE repo_id<>? "
                    "AND (raw_path=? OR normalized_path=?) LIMIT 1",
                    (repo_id, path, path),
                ).fetchone()
            }
        files = sum(_remove(content, path) for path in sorted(paths - shared))
        with connect(write=True) as db:
            check_lease(db, active_lease)
            db.execute("DELETE FROM archive_documents WHERE repo_id=?", (repo_id,))
            db.execute("DELETE FROM archive_repositories WHERE repo_id=?", (repo_id,))
    return PurgeResult(repo_id, len(documents), len(chunk_ids), files)


def _remove(content, relative):
    target = content._target(relative)
    try:
        target.unlink()
    except FileNotFoundError:
        return 0
    return 1


def sweep_unreferenced_files(connect, content, now, *, limit=1000):
    """Delete content files no document references and older than 30 days.

    Superseded revisions lose their catalogue rows promptly (T08 reconcile),
    which leaves their content-addressed files behind; this applies the D3
    period to them and to any file a crashed purge left. Bounded per call.
    """
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError("file sweep limit must be from 1 through 10000")
    with connect() as db:
        referenced = {
            path
            for row in db.execute(
                "SELECT raw_path, normalized_path FROM archive_documents"
            )
            for path in row
            if path is not None
        }
    cutoff = now - SUPERSEDED_FILE_DAYS * _DAY
    removed = 0
    for kind in ("raw", "normalized"):
        base = content.root / kind
        if not base.is_dir():
            continue
        # shortcut: full directory walk per call; index files by age if the
        # corpus grows past the D1 10k pilot.
        for path in sorted(base.glob("*/*")):
            relative = path.relative_to(content.root).as_posix()
            if relative in referenced or not path.is_file() or path.is_symlink():
                continue
            if path.stat().st_mtime >= cutoff:
                continue
            removed += _remove(content, relative)
            if removed >= limit:
                return removed
    return removed


_RUN_DELETES = (
    "DELETE FROM archive_backfill_pages WHERE run_id=?",
    "DELETE FROM archive_backfill_repositories WHERE run_id=?",
    "DELETE FROM archive_backfill_state WHERE run_id=?",
    "DELETE FROM archive_tasks WHERE run_id=?",
    "DELETE FROM archive_partitions WHERE run_id=?",
    "DELETE FROM archive_runs WHERE run_id=?",
)


def compact_runs(connect, now):
    """Delete content-free run history older than 90 days.

    Keeps the run holding the catalogue-wide MAX(fence) so fences never go
    backwards, backfill runs (their admission cap lives in the run), and the
    latest refresh run plus the latest completed one (T19b reads its boundary
    and sweep rotation from them); skips live leases; and re-points repository
    tombstones to the kept run so no generation high-water mark is lost.
    """
    cutoff = now - RUN_HISTORY_DAYS * _DAY
    with connect(write=True) as db:
        keep = db.execute(
            "SELECT run_id FROM archive_runs ORDER BY fence DESC, run_id DESC LIMIT 1"
        ).fetchone()
        if keep is None:
            return 0
        runs = [
            row[0]
            for row in db.execute(
                "SELECT run_id FROM archive_runs WHERE run_id<>? AND kind<>'backfill' "
                "AND COALESCE(heartbeat_at, 0) < ? "
                "AND (expires_at IS NULL OR expires_at <= ?) "
                "AND run_id NOT IN (SELECT run_id FROM archive_runs "
                "WHERE kind='refresh' ORDER BY due_period DESC LIMIT 1) "
                "AND run_id NOT IN (SELECT run_id FROM archive_runs "
                "WHERE kind='refresh' AND completed=1 "
                "ORDER BY due_period DESC LIMIT 1)",
                (keep[0], cutoff, now),
            )
        ]
        for run_id in runs:
            db.execute(
                "UPDATE archive_tasks SET run_id=? WHERE run_id=? AND repo_id IS NOT NULL",
                (keep[0], run_id),
            )
            for statement in _RUN_DELETES:
                db.execute(statement, (run_id,))
        return len(runs)
