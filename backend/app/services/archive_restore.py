"""T22 restore of a T21 backup into quarantine, then explicit activation.

``restore_to_quarantine`` never touches the live archive. It restores one
restic snapshot into a private ``restore-quarantine`` folder beside the
catalogue, checks the manifest (every hash, completeness, schema, model),
reapplies the *current* suppression ledger, purges suppressed and expired
repositories inside the quarantine and, when the ledger cannot be trusted,
re-checks every remaining repository by numeric ID on GitHub. Only a run that
finishes all of that writes a ``ready`` verdict; any other outcome deletes the
restored plaintext and reports why.

``activate`` is a separate operator step. Under the live writer lock it
reapplies decisions made since the restore, rebuilds and reads back every
active vector, and only then swaps the quarantine in. The previous live
archive is moved aside, never deleted, so a failed or regretted activation is
a rename away from rollback.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import stat
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from app.core.config import MILVUS_TEXT_BYTES
from app.integrations.milvus import VectorChunk
from app.services.archive_backup import (
    MANIFEST_NAME,
    MANIFEST_VERSION,
    BackupError,
    Restic,
    _catalogue_path,
    _check_destination,
    _device,
    _referenced,
    _remove_stale_plaintext,
    _sha256,
)
from app.services.archive_content import ArchiveContentStore
from app.services.archive_publication import _batches, load_active_chunks
from app.services.archive_retirement import (
    LEDGER_NAME,
    LedgerError,
    SuppressionLedger,
    purge_repository,
    reapply,
)
from app.services.archive_runs import publication_writer
from app.services.embeddings import ModelManifest

QUARANTINE = "restore-quarantine"
VERDICT_NAME = "verdict.json"
_CONTENT_PATH = re.compile(r"(raw|normalized)/[0-9a-f]{2}/[0-9a-f]{64}")


class RestoreRefused(BackupError):
    """The restore cannot be trusted or activated; the live archive is unchanged."""


class _NoVectors:
    """Quarantine purges must never touch the live Milvus collection.

    Vectors are rebuilt from the reconciled catalogue on activation instead.
    """

    def __init__(self, settings):
        self.settings = settings

    def delete(self, chunk_ids):
        return len(chunk_ids)


def _private_tree(root):
    """Make a restored tree private (0700/0600) and refuse links or odd files."""
    for current, dirs, files in os.walk(root):
        os.chmod(current, 0o700)
        for name in dirs + files:
            info = os.lstat(os.path.join(current, name))
            if stat.S_ISLNK(info.st_mode):
                raise RestoreRefused("restored snapshot contains a symbolic link")
            if name in files:
                if not stat.S_ISREG(info.st_mode):
                    raise RestoreRefused("restored snapshot contains a special file")
                os.chmod(os.path.join(current, name), 0o600)


def _remove(path):
    if os.path.islink(path) or os.path.isfile(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


def _quarantine_settings(settings, quarantine):
    return settings.model_copy(
        update={
            "archive_database_path": quarantine / "catalogue.sqlite3",
            "archive_content_path": quarantine / "content",
        }
    )


def _open_with_store(settings):
    from app.core.archive_store import ArchiveStore

    # ArchiveStore migrates an older schema and refuses a newer one.
    return ArchiveStore(settings).connect


def _check_manifest(root, current_model):
    """Return the manifest after checking it against the restored files."""
    try:
        manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
        catalogue, files = manifest["catalogue"], manifest["files"]
        model, schema = manifest["model"], manifest["schema_version"]
        expected = {entry["path"]: entry for entry in files}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RestoreRefused("backup manifest is missing or malformed") from error
    if manifest.get("version") != MANIFEST_VERSION or type(schema) is not int:
        raise RestoreRefused("backup manifest version is not supported")
    if model != asdict(current_model):
        raise RestoreRefused("backup model does not match the pinned model")
    copy = root / "catalogue.sqlite3"
    if not copy.is_file() or _sha256(copy) != catalogue.get("sha256"):
        raise RestoreRefused("restored catalogue does not match the manifest")
    if copy.stat().st_size != catalogue.get("bytes"):
        raise RestoreRefused("restored catalogue does not match the manifest")
    present = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if not path.is_dir()
    }
    wanted = {"catalogue.sqlite3", MANIFEST_NAME} | {
        "content/" + path for path in expected
    }
    if any(Path(name).name == LEDGER_NAME for name in present):
        raise RestoreRefused("restored snapshot contains the suppression ledger")
    if present != wanted:
        raise RestoreRefused("restored snapshot is incomplete or has extra files")
    for path, entry in expected.items():
        target = root / "content" / path
        if (
            not _CONTENT_PATH.fullmatch(path)
            or _sha256(target) != entry.get("sha256")
            or target.stat().st_size != entry.get("bytes")
        ):
            raise RestoreRefused("restored content does not match the manifest")
    return manifest


def _check_catalogue(connect, manifest, model):
    with connect() as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RestoreRefused("restored catalogue failed its integrity check")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RestoreRefused("restored catalogue has broken references")
        listed = {entry["path"] for entry in manifest["files"]}
        if {path for path, _ in _referenced(db)} - listed:
            raise RestoreRefused("restored catalogue references unlisted files")
        if db.execute(
            "SELECT 1 FROM archive_documents WHERE model_revision IS NOT NULL "
            "AND model_revision<>? LIMIT 1",
            (model.revision,),
        ).fetchone():
            raise RestoreRefused("restored documents use another model revision")
        if db.execute(
            "SELECT 1 FROM archive_repositories WHERE "
            "json_extract(metadata_json, '$.id') IS NOT NULL "
            "AND json_extract(metadata_json, '$.id') IS NOT repo_id LIMIT 1"
        ).fetchone():
            raise RestoreRefused("restored repository identities do not match")
    with connect(write=True) as db:
        # Backup-era leases are history, never a live writer in quarantine.
        db.execute(
            "UPDATE archive_runs SET owner=NULL, expires_at=NULL "
            "WHERE expires_at IS NOT NULL"
        )


def ledger_state(ledger, live_connect):
    """Return ("trusted" | "missing" | "stale", decisions to enforce).

    Trusted means a private, parseable ledger that holds every suppression the
    live catalogue currently enforces. A ledger that cannot be read safely is
    refused outright: decisions could not be recorded or replayed.
    """
    with live_connect() as db:
        live = {
            row[0]: (row[1], row[2])
            for row in db.execute(
                "SELECT repo_id, reason, observed_at FROM archive_suppressions"
            )
        }
    try:
        info = ledger.path.lstat()
    except FileNotFoundError:
        return "missing", live
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or (os.name == "posix" and info.st_mode & 0o077)
    ):
        raise RestoreRefused("suppression ledger is unsafe; repair it first")
    try:
        current = ledger.current()
    except (LedgerError, OSError, UnicodeDecodeError) as error:
        raise RestoreRefused("suppression ledger is unreadable; repair it") from error
    if any(current.get(repo_id, (None,))[0] != row[0] for repo_id, row in live.items()):
        # The live catalogue enforces decisions the ledger lost: enforce both.
        return "stale", {**current, **live}
    return "trusted", current


def _apply_ledger(connect, ledger, trust, current):
    if trust == "trusted":
        return reapply(connect, ledger)
    # Untrusted: add every known decision but never lift a backup-era one.
    added = 0
    with connect(write=True) as db:
        for repo_id, (reason, at) in current.items():
            added += db.execute(
                "INSERT INTO archive_suppressions(repo_id, reason, observed_at) "
                "VALUES(?, ?, ?) ON CONFLICT(repo_id) DO UPDATE SET "
                "reason=excluded.reason, observed_at=excluded.observed_at "
                "WHERE reason<>excluded.reason",
                (repo_id, reason, at),
            ).rowcount
    return added, 0


def _purge_offline(runtime, now, summary):
    """Purge suppressed repositories, then any whose stored facts fail policy."""
    from app.workers.archive import (
        ELIGIBILITY_DAYS,
        IneligibleRepository,
        check_eligibility,
        load_cached_repository,
    )

    with runtime.connect() as db:
        suppressed = [
            row[0]
            for row in db.execute(
                "SELECT r.repo_id FROM archive_repositories AS r JOIN "
                "archive_suppressions AS s USING(repo_id) ORDER BY r.repo_id"
            )
        ]
        active = db.execute(
            "SELECT r.repo_id, r.active_revision FROM archive_repositories AS r "
            "WHERE r.active_revision IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "
            "archive_suppressions AS s WHERE s.repo_id=r.repo_id) ORDER BY r.repo_id"
        ).fetchall()
    for repo_id in suppressed:
        purge_repository(runtime.connect, runtime.vectors, runtime.content, repo_id)
        summary["purged"] += 1
    cutoff = now - timedelta(days=ELIGIBILITY_DAYS)
    for repo_id, revision in active:
        cached = load_cached_repository(runtime.connect, runtime.content, repo_id)
        try:
            if cached is None:
                raise IneligibleRepository("unverifiable", "stored facts unusable")
            check_eligibility(
                cached.metadata, runtime.settings.archive_license_allowlist, cutoff
            )
        except IneligibleRepository:
            # Backup-era facts are not authoritative: purge only, no ledger
            # entry, so an eligible repository can return through an ingest.
            purge_repository(
                runtime.connect,
                runtime.vectors,
                runtime.content,
                repo_id,
                expect_active=revision,
            )
            summary["expired"] += 1


def _recheck(runtime, ledger, now, summary):
    """Re-check every remaining repository by numeric ID (T20 sweep rules)."""
    from app.workers import retire

    with runtime.connect() as db:
        total = db.execute("SELECT count(*) FROM archive_repositories").fetchone()[0]
    if total == 0:
        return
    sweep = {"checked": 0, "issues": 0, "suppressed": {}, "purged": 0, "expired": 0}
    try:
        retire._check_known(runtime, ledger, now, total, sweep)
    except retire._Stop as stop:
        raise RestoreRefused(
            f"GitHub re-check stopped ({stop.reason}); retry the restore later"
        ) from None
    summary["rechecked"] = sweep["checked"]
    summary["suppressed"] = sweep["suppressed"]
    summary["purged"] += sweep["purged"]
    summary["expired"] += sweep["expired"]
    if sweep["issues"] or sweep["checked"] < total:
        raise RestoreRefused("GitHub re-check was incomplete; retry the restore later")


def _checkpoint(path):
    db = sqlite3.connect(path)
    try:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.execute("PRAGMA journal_mode=DELETE")
    finally:
        db.close()


def _tree_bytes(paths):
    total = 0
    for path in paths:
        if path.is_file():
            total += path.stat().st_size
        elif path.is_dir():
            total += sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return total


def restore_to_quarantine(
    connect,
    content,
    settings,
    *,
    now,
    snapshot="latest",
    reader=None,
    restic=None,
    open_catalogue=_open_with_store,
    device=_device,
    disk_free=None,
):
    """Restore one snapshot into quarantine and return a content-free verdict.

    The live writer lock is held throughout, so nothing publishes or purges
    meanwhile and two restores can never share a quarantine.
    """
    restic = restic or Restic.from_settings(settings)
    catalogue = _catalogue_path(connect)
    _check_destination(settings, catalogue, content.root, restic, device)
    model = ModelManifest.load()
    ledger = SuppressionLedger(catalogue.parent / LEDGER_NAME)
    with publication_writer(connect):
        _remove_stale_plaintext(catalogue.parent)
        quarantine = catalogue.parent / QUARANTINE
        _remove(quarantine)
        # shortcut: assume the backup is about the size of the live archive;
        # read the manifest size first if archives grow past the D1 pilot.
        needed = _tree_bytes([catalogue, Path(content.root)])
        free = (disk_free or (lambda: shutil.disk_usage(catalogue.parent).free))()
        if free - needed < settings.archive_min_free_bytes:
            raise RestoreRefused("not enough free disk to restore into quarantine")
        quarantine.mkdir(mode=0o700)
        try:
            return _restore(
                connect,
                settings,
                quarantine,
                restic,
                snapshot,
                model,
                ledger,
                reader,
                open_catalogue,
                now,
            )
        except BaseException:
            # Nothing half-checked is kept: restored plaintext goes on failure.
            _remove(quarantine)
            raise


def _restore(
    live_connect,
    settings,
    quarantine,
    restic,
    snapshot,
    model,
    ledger,
    reader,
    open_catalogue,
    now,
):
    raw = quarantine / "snapshot"
    raw.mkdir(mode=0o700)
    restic.restore(snapshot, raw)
    manifests = list(raw.rglob(MANIFEST_NAME))
    if len(manifests) != 1:
        raise RestoreRefused("restored snapshot has no single manifest")
    root = manifests[0].parent
    _private_tree(raw)
    manifest = _check_manifest(root, model)
    if manifest["schema_version"] > _code_schema():
        raise RestoreRefused("backup schema is newer than this code")
    os.replace(root / "catalogue.sqlite3", quarantine / "catalogue.sqlite3")
    if (root / "content").is_dir():
        os.replace(root / "content", quarantine / "content")
    else:
        (quarantine / "content").mkdir(mode=0o700)
    shutil.rmtree(raw)

    local = _quarantine_settings(settings, quarantine)
    try:
        connect = open_catalogue(local)
    except (RuntimeError, sqlite3.DatabaseError) as error:
        raise RestoreRefused(
            "restored file is not a usable archive catalogue"
        ) from error
    _check_catalogue(connect, manifest, model)
    trust, current = ledger_state(ledger, live_connect)
    added, removed = _apply_ledger(connect, ledger, trust, current)
    runtime = SimpleNamespace(
        connect=connect,
        content=ArchiveContentStore(local),
        vectors=_NoVectors(settings),
        reader=reader,
        settings=settings,
    )
    summary = {
        "ledger": trust,
        "reapplied": [added, removed],
        "purged": 0,
        "expired": 0,
        "rechecked": 0,
    }
    _purge_offline(runtime, now, summary)
    if trust != "trusted":
        # D5: without a trustworthy ledger, only current GitHub state can
        # clear a restored repository for serving.
        if reader is None:
            raise RestoreRefused("the ledger is not trusted and GitHub is unavailable")
        _recheck(runtime, ledger, now, summary)
    with connect() as db:
        serving = sum(
            1
            for (repo_id,) in db.execute(
                "SELECT repo_id FROM archive_repositories "
                "WHERE active_revision IS NOT NULL"
            ).fetchall()
            if load_active_chunks(db, repo_id)
        )
    _checkpoint(quarantine / "catalogue.sqlite3")
    verdict = {
        "ready": True,
        "snapshot": snapshot,
        "backup_created_at": manifest.get("created_at"),
        "restored_at": now.isoformat(),
        "schema_version": manifest["schema_version"],
        "model_revision": model.revision,
        "catalogue_sha256": _sha256(quarantine / "catalogue.sqlite3"),
        "repositories": serving,
        **summary,
    }
    _write_private(quarantine / VERDICT_NAME, json.dumps(verdict, sort_keys=True))
    return {"result": "quarantined", **verdict}


def _code_schema():
    from app.core.archive_store import MIGRATIONS

    return len(MIGRATIONS)


def _write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


def _load_verdict(quarantine):
    try:
        verdict = json.loads((quarantine / VERDICT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RestoreRefused("no ready quarantine; run restore first") from error
    if verdict.get("ready") is not True:
        raise RestoreRefused("the quarantine is not ready")
    if _sha256(quarantine / "catalogue.sqlite3") != verdict.get("catalogue_sha256"):
        raise RestoreRefused("the quarantine changed after its verdict; restore again")
    return verdict


def _vector_rows(db, repo_id, chunks, model):
    from app.workers.archive import _bounded, _pushed_at

    stored = json.loads(
        db.execute(
            "SELECT metadata_json FROM archive_repositories WHERE repo_id=?",
            (repo_id,),
        ).fetchone()[0]
    )
    language = _bounded(stored.get("language") or "", MILVUS_TEXT_BYTES["language"])
    licence = _bounded(stored.get("license_spdx") or "", MILVUS_TEXT_BYTES["license"])
    pushed = int(_pushed_at(stored.get("pushed_at")).timestamp())
    return [
        (
            chunk,
            dict(
                chunk_id=chunk.chunk_id,
                repo_id=repo_id,
                revision=chunk.revision,
                model_revision=model.revision,
                language=language,
                license=licence,
                pushed_at=pushed,
                ordinal=chunk.ordinal,
                section=chunk.section,
                snippet=_bounded(chunk.text, MILVUS_TEXT_BYTES["snippet"]),
            ),
        )
        for chunk in chunks
    ]


def _rebuild_vectors(connect, vectors, adapter, model):
    """Upsert and strongly read back every active chunk of the quarantine."""
    if adapter.manifest != model:
        raise RestoreRefused("the loaded model does not match the pinned model")
    with connect() as db:
        repo_ids = [
            row[0]
            for row in db.execute(
                "SELECT repo_id FROM archive_repositories "
                "WHERE active_revision IS NOT NULL ORDER BY repo_id"
            )
        ]
        work = []
        for repo_id in repo_ids:
            chunks = load_active_chunks(db, repo_id)
            if chunks:
                work.append(_vector_rows(db, repo_id, chunks, model))
    batch = vectors.settings.milvus_batch_size
    written = set()
    for rows in work:
        embedded = adapter.embed([chunk.text for chunk, _ in rows], kind="passage")
        if len(embedded) != len(rows):
            raise RestoreRefused("the model returned the wrong number of vectors")
        records = tuple(
            VectorChunk(**fields, vector=vector)
            for (_, fields), vector in zip(rows, embedded, strict=True)
        )
        for part in _batches(records, batch):
            vectors.upsert(part)
        for part in _batches(records, batch):
            if not vectors.ready(part):
                raise RestoreRefused("rebuilt vectors are not readable; retry")
        written.update(record.chunk_id for record in records)
    return written


def _swap(catalogue, content_root, quarantine, now):
    """Move the live archive aside and the quarantine in; undo on failure."""
    previous = catalogue.parent / f"restore-previous-{now:%Y%m%dT%H%M%SZ}"
    previous.mkdir(mode=0o700)
    moves = [
        (Path(str(catalogue) + suffix), previous / (catalogue.name + suffix))
        for suffix in ("", "-wal", "-shm")
        if Path(str(catalogue) + suffix).exists()
    ]
    moves.append((content_root, previous / "content"))
    moves += [
        (quarantine / "catalogue.sqlite3", catalogue),
        (quarantine / "content", content_root),
    ]
    done = []
    try:
        for source, target in moves:
            os.rename(source, target)
            done.append((source, target))
    except OSError as error:
        for source, target in reversed(done):
            os.rename(target, source)
        raise RestoreRefused(
            "could not swap the quarantine in; nothing changed"
        ) from error
    return previous


def activate(
    connect,
    content,
    settings,
    *,
    now,
    vectors,
    adapter,
    open_catalogue=_open_with_store,
):
    """Swap a ready quarantine in after rebuilding and checking its vectors.

    Requires the API to be stopped; restarting it afterwards clears its
    process-local visibility cache and pagination snapshots.
    """
    catalogue = _catalogue_path(connect)
    quarantine = catalogue.parent / QUARANTINE
    content_root = Path(content.root)
    model = ModelManifest.load()
    ledger = SuppressionLedger(catalogue.parent / LEDGER_NAME)
    if _device(content_root.parent) != _device(catalogue.parent):
        raise RestoreRefused("the content folder must share the catalogue's volume")
    with publication_writer(connect):
        verdict = _load_verdict(quarantine)
        if verdict.get("model_revision") != model.revision:
            raise RestoreRefused("the quarantine was checked under another model")
        local = _quarantine_settings(settings, quarantine)
        restored = open_catalogue(local)
        # Decisions made since the restore apply before anything can serve.
        trust, current = ledger_state(ledger, connect)
        added, removed = _apply_ledger(restored, ledger, trust, current)
        runtime = SimpleNamespace(
            connect=restored,
            content=ArchiveContentStore(local),
            vectors=_NoVectors(settings),
            settings=settings,
        )
        summary = {"purged": 0, "expired": 0}
        _purge_offline(runtime, now, summary)
        written = _rebuild_vectors(restored, vectors, adapter, model)
        with connect() as db:
            live_chunks = {
                row[0] for row in db.execute("SELECT chunk_id FROM archive_chunks")
            }
        _checkpoint(quarantine / "catalogue.sqlite3")
        previous = _swap(catalogue, content_root, quarantine, now)
        _remove(quarantine)
        orphans = sorted(live_chunks - written)
        result = {
            "result": "activated",
            "snapshot": verdict.get("snapshot"),
            "repositories": verdict.get("repositories"),
            "reapplied": [added, removed],
            "purged": summary["purged"],
            "expired": summary["expired"],
            "vectors": len(written),
            "previous": previous.name,
            "orphan_vectors": "done",
            "next": "restart the API, then run retire",
        }
        try:
            for part in _batches(tuple(orphans), vectors.settings.milvus_batch_size):
                vectors.delete(part)
        except Exception:
            # Serving already ignores chunks outside the active set.
            result["orphan_vectors"] = "failed"
        return result
