"""T22 restore into quarantine: fake restic/GitHub/Milvus, real SQLite and files."""

import json
import os
import shutil
import sqlite3
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.archive_store import APPLICATION_ID
from app.integrations.archive_github import (
    ArchiveRequestError,
    ArchiveUnavailable,
    RepositoryNotPublic,
)
from app.services import archive_restore as restore
from app.services.archive_backup import MANIFEST_NAME, _sha256
from app.services.archive_publication import load_active_chunks
from app.services.archive_retirement import LEDGER_NAME, SuppressionLedger
from app.workers import archive as worker
from app.workers.retire import sweep
from test_archive_backup import FakeRestic, configured, distinct, export
from test_archive_retirement import SweepReader
from test_archive_worker import NOW, REPO_ID, make_snapshot


class RestoringRestic(FakeRestic):
    """Restores a captured staging tree under an absolute-looking path."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.restored = []

    def restore(self, snapshot, target):
        self.restored.append(snapshot)
        tree = self.snapshots[-1 if snapshot == "latest" else int(snapshot[4:]) - 1]
        shutil.copytree(
            tree, Path(target) / "home" / "worker" / "backup-staging", symlinks=True
        )


def reader(outcome=None):
    return SweepReader(make_snapshot(), outcome)


def run_restore(state, restic, *, outcome=None, now=NOW, github=True, **kwargs):
    return restore.restore_to_quarantine(
        state.connect,
        state.runtime.content,
        state.settings,
        now=now,
        restic=restic,
        reader=reader(outcome) if github else None,
        device=distinct,
        **kwargs,
    )


def run_activate(state, **kwargs):
    kwargs.setdefault("adapter", state.adapter)
    return restore.activate(
        state.connect,
        state.runtime.content,
        state.settings,
        now=NOW,
        vectors=state.vectors,
        **kwargs,
    )


def make_private(state):
    """Live GitHub says private: the T20 sweep suppresses and purges."""
    runtime = replace(state.runtime, reader=reader(RepositoryNotPublic("gone")))
    summary = sweep(runtime, now=NOW)
    assert summary["suppressed"] == {"not_public": 1} and summary["purged"] == 1


def quarantine(state):
    return state.settings.archive_database_path.parent / restore.QUARANTINE


ARCHIVE_TABLES = (
    "archive_repositories",
    "archive_documents",
    "archive_chunks",
    "archive_suppressions",
    "archive_tasks",
)


def live_snapshot(state):
    """Archive rows (not writer-lease bookkeeping) and every content file."""
    root = state.runtime.content.root
    files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    with state.connect() as db:
        rows = {
            table: sorted(tuple(row) for row in db.execute(f"SELECT * FROM {table}"))
            for table in ARCHIVE_TABLES
        }
    return rows, files, dict(state.vectors.rows)


def repositories(connect):
    with connect() as db:
        return [
            row[0] for row in db.execute("SELECT repo_id FROM archive_repositories")
        ]


def ledger(state):
    return SuppressionLedger.for_catalogue(state.connect)


def backed_up(tmp_path):
    state = configured(tmp_path)
    with state.connect(write=True) as db:
        # The fixture catalogue skips ArchiveStore; real ones carry this ID.
        db.execute(f"PRAGMA application_id={APPLICATION_ID}")
    restic = RestoringRestic()
    export(state, restic)
    return state, restic


def test_private_then_purge_then_older_backup_cannot_resurrect(tmp_path):
    state, restic = backed_up(tmp_path)
    make_private(state)

    verdict = run_restore(state, restic)

    assert verdict["result"] == "quarantined" and verdict["ready"] is True
    assert verdict["ledger"] == "trusted"
    assert verdict["purged"] == 1 and verdict["repositories"] == 0
    content = quarantine(state) / "content"
    assert [p for p in content.rglob("*") if p.is_file()] == []

    summary = run_activate(state)

    assert summary["result"] == "activated" and summary["vectors"] == 0
    assert repositories(state.connect) == []
    assert state.vectors.rows == {}
    with state.connect() as db:
        assert (
            db.execute(
                "SELECT reason FROM archive_suppressions WHERE repo_id=?", (REPO_ID,)
            ).fetchone()[0]
            == "not_public"
        )
    assert not quarantine(state).exists()
    assert ledger(state).current()[REPO_ID][0] == "not_public"


def test_round_trip_restores_the_archive_and_rebuilds_its_vectors(tmp_path):
    state, restic = backed_up(tmp_path)
    before = dict(state.vectors.rows)
    state.vectors.rows.clear()

    verdict = run_restore(state, restic, snapshot="snap1")
    summary = run_activate(state)

    assert verdict["repositories"] == 1 and restic.restored == ["snap1"]
    assert summary["vectors"] == len(before) and summary["orphan_vectors"] == "done"
    assert set(state.vectors.rows) == set(before)
    with state.connect() as db:
        assert len(load_active_chunks(db, REPO_ID)) == len(before)
    previous = state.settings.archive_database_path.parent / summary["previous"]
    assert (previous / "catalogue.sqlite3").is_file()
    assert (previous / "content").is_dir()
    mode = state.settings.archive_database_path.stat().st_mode
    assert os.name != "posix" or mode & 0o077 == 0


def test_restore_never_touches_the_live_archive(tmp_path):
    state, restic = backed_up(tmp_path)
    make_private(state)
    before = live_snapshot(state)

    run_restore(state, restic)

    assert live_snapshot(state) == before


def test_missing_ledger_requires_a_recheck_by_numeric_id(tmp_path):
    state, restic = backed_up(tmp_path)
    assert not (state.settings.archive_database_path.parent / LEDGER_NAME).exists()

    verdict = run_restore(state, restic, outcome=RepositoryNotPublic("gone"))

    assert verdict["ledger"] == "missing"
    assert verdict["rechecked"] == 1 and verdict["suppressed"] == {"not_public": 1}
    assert verdict["repositories"] == 0
    assert ledger(state).current()[REPO_ID][0] == "not_public"


def test_missing_ledger_with_a_public_repository_is_ready_after_recheck(tmp_path):
    state, restic = backed_up(tmp_path)

    verdict = run_restore(state, restic)

    assert verdict["ledger"] == "missing" and verdict["rechecked"] == 1
    assert verdict["repositories"] == 1


@pytest.mark.parametrize("github", [True, False])
def test_github_unavailable_keeps_nothing_and_leaves_live_untouched(tmp_path, github):
    state, restic = backed_up(tmp_path)
    before = live_snapshot(state)

    with pytest.raises(restore.RestoreRefused):
        run_restore(state, restic, outcome=ArchiveUnavailable("down"), github=github)

    assert not quarantine(state).exists()
    assert live_snapshot(state) == before
    with pytest.raises(restore.RestoreRefused, match="no ready quarantine"):
        run_activate(state)


def test_inconclusive_github_answer_keeps_it_quarantined(tmp_path):
    state, restic = backed_up(tmp_path)
    inconclusive = ArchiveRequestError("odd", response=SimpleNamespace(status=422))

    with pytest.raises(restore.RestoreRefused, match="incomplete"):
        run_restore(state, restic, outcome=inconclusive)

    assert not quarantine(state).exists()


def test_stale_ledger_enforces_live_suppressions_and_rechecks(tmp_path):
    state, restic = backed_up(tmp_path)
    SuppressionLedger.for_catalogue(state.connect).append(
        999, "suppress", "archived", 1.0
    )
    with state.connect(write=True) as db:
        # The live catalogue enforces a decision the ledger lost.
        db.execute(
            "INSERT INTO archive_suppressions VALUES(?, 'operator', 2.0)", (REPO_ID,)
        )

    verdict = run_restore(state, restic)

    assert verdict["ledger"] == "stale"
    assert verdict["purged"] == 1 and verdict["repositories"] == 0


@pytest.mark.parametrize("problem", ["malformed", "shared"])
def test_unreadable_or_unsafe_ledger_is_refused(tmp_path, problem):
    state, restic = backed_up(tmp_path)
    path = state.settings.archive_database_path.parent / LEDGER_NAME
    path.write_text("not json\n" if problem == "malformed" else "", "ascii")
    path.chmod(0o600 if problem == "malformed" else 0o644)
    if problem == "shared" and os.name != "posix":
        pytest.skip("POSIX permissions only")

    with pytest.raises(restore.RestoreRefused, match="ledger"):
        run_restore(state, restic)

    assert not quarantine(state).exists()


def rewrite_manifest(tree, change):
    path = tree / MANIFEST_NAME
    manifest = json.loads(path.read_text("utf-8"))
    change(manifest)
    path.write_text(json.dumps(manifest), "utf-8")


def first_file(tree):
    return next(p for p in (tree / "content").rglob("*") if p.is_file())


def model_change(tree):
    copy = tree / "catalogue.sqlite3"
    db = sqlite3.connect(copy)
    db.execute("UPDATE archive_documents SET model_revision=?", ("f" * 40,))
    db.commit()
    db.close()

    def fix(manifest):
        manifest["catalogue"] = {"sha256": _sha256(copy), "bytes": copy.stat().st_size}

    rewrite_manifest(tree, fix)


def identity_change(tree):
    copy = tree / "catalogue.sqlite3"
    db = sqlite3.connect(copy)
    db.execute(
        "UPDATE archive_repositories SET metadata_json=json_set(metadata_json, '$.id', 7)"
    )
    db.commit()
    db.close()
    rewrite_manifest(
        tree,
        lambda m: m.update(
            catalogue={"sha256": _sha256(copy), "bytes": copy.stat().st_size}
        ),
    )


def unlisted_file(tree):
    victim = first_file(tree)
    relative = victim.relative_to(tree / "content").as_posix()
    victim.unlink()
    rewrite_manifest(
        tree,
        lambda m: m.update(files=[f for f in m["files"] if f["path"] != relative]),
    )


def not_a_catalogue(tree):
    copy = tree / "catalogue.sqlite3"
    copy.write_bytes(b"plain text, not SQLite")
    rewrite_manifest(
        tree,
        lambda m: m.update(
            catalogue={"sha256": _sha256(copy), "bytes": copy.stat().st_size}
        ),
    )


CORRUPTIONS = {
    "symlink": lambda t: (t / "content" / "link").symlink_to(t / MANIFEST_NAME),
    "malformed manifest": lambda t: (t / MANIFEST_NAME).write_text("{", "utf-8"),
    "identity": identity_change,
    "unlisted file": unlisted_file,
    "not a catalogue": not_a_catalogue,
    "content hash": lambda t: first_file(t).write_bytes(b"tampered"),
    "missing file": lambda t: first_file(t).unlink(),
    "extra file": lambda t: (t / "content" / "extra").write_text("x", "utf-8"),
    "no manifest": lambda t: (t / MANIFEST_NAME).unlink(),
    "ledger inside": lambda t: (t / LEDGER_NAME).write_text("", "utf-8"),
    "catalogue hash": lambda t: (t / "catalogue.sqlite3").write_bytes(b"x"),
    "manifest version": lambda t: rewrite_manifest(t, lambda m: m.update(version=9)),
    "manifest model": lambda t: rewrite_manifest(
        t, lambda m: m["model"].update(revision="0" * 40)
    ),
    "newer schema": lambda t: rewrite_manifest(
        t, lambda m: m.update(schema_version=99)
    ),
    "document model": model_change,
}


@pytest.mark.parametrize("corruption", sorted(CORRUPTIONS))
def test_corrupt_incomplete_or_mismatched_backup_is_refused(tmp_path, corruption):
    state, restic = backed_up(tmp_path)
    CORRUPTIONS[corruption](restic.snapshots[-1])
    before = live_snapshot(state)

    with pytest.raises(restore.RestoreRefused):
        run_restore(state, restic)

    assert not quarantine(state).exists()
    assert live_snapshot(state) == before


def test_expired_repository_is_purged_in_quarantine(tmp_path):
    state, restic = backed_up(tmp_path)
    later = NOW + timedelta(days=400)
    ledger(state).append(999, "suppress", "archived", 1.0)

    verdict = run_restore(state, restic, now=later)

    assert verdict["expired"] == 1 and verdict["repositories"] == 0


def test_activation_reapplies_decisions_made_after_the_restore(tmp_path):
    state, restic = backed_up(tmp_path)
    ledger(state).append(999, "suppress", "archived", 1.0)
    assert run_restore(state, restic)["repositories"] == 1
    make_private(state)

    summary = run_activate(state)

    assert summary["purged"] == 1 and summary["vectors"] == 0
    assert repositories(state.connect) == []
    assert state.vectors.rows == {}


def test_failed_vector_rebuild_leaves_the_live_archive_untouched(tmp_path):
    state, restic = backed_up(tmp_path)
    ledger(state).append(999, "suppress", "archived", 1.0)
    run_restore(state, restic)
    state.vectors.ready = lambda chunks: False
    before = live_snapshot(state)

    with pytest.raises(restore.RestoreRefused, match="not readable"):
        run_activate(state)

    assert live_snapshot(state) == before
    assert (quarantine(state) / restore.VERDICT_NAME).is_file()


def test_changed_quarantine_cannot_be_activated(tmp_path):
    state, restic = backed_up(tmp_path)
    ledger(state).append(999, "suppress", "archived", 1.0)
    run_restore(state, restic)
    with open(quarantine(state) / "catalogue.sqlite3", "ab") as handle:
        handle.write(b"\0")
    before = live_snapshot(state)

    with pytest.raises(restore.RestoreRefused, match="changed"):
        run_activate(state)

    assert live_snapshot(state) == before


def test_loaded_model_must_match_to_rebuild(tmp_path):
    state, restic = backed_up(tmp_path)
    ledger(state).append(999, "suppress", "archived", 1.0)
    run_restore(state, restic)
    other = SimpleNamespace(manifest=None, embed=state.adapter.embed)
    before = live_snapshot(state)

    with pytest.raises(restore.RestoreRefused, match="model"):
        run_activate(state, adapter=other)

    assert live_snapshot(state) == before


def test_orphan_vectors_of_the_replaced_archive_are_deleted(tmp_path):
    state, restic = backed_up(tmp_path)
    ledger(state).append(999, "suppress", "archived", 1.0)
    run_restore(state, restic)
    with state.connect(write=True) as db:
        # A chunk the live archive gained after the backup.
        revision = db.execute("SELECT revision FROM archive_documents").fetchone()[0]
        db.execute(
            "INSERT INTO archive_chunks(chunk_id, repo_id, revision, ordinal, text, "
            "token_count) VALUES(?, ?, ?, 99, 'newer', 3)",
            ("e" * 64, REPO_ID, revision),
        )

    summary = run_activate(state)

    assert ("e" * 64,) in state.vectors.deletes
    assert summary["orphan_vectors"] == "done"


def test_low_disk_refuses_before_restoring(tmp_path):
    state, restic = backed_up(tmp_path)

    with pytest.raises(restore.RestoreRefused, match="disk"):
        run_restore(state, restic, disk_free=lambda: 0)

    assert restic.restored == [] and not quarantine(state).exists()


def test_failed_swap_is_rolled_back(tmp_path, monkeypatch):
    state, restic = backed_up(tmp_path)
    ledger(state).append(999, "suppress", "archived", 1.0)
    run_restore(state, restic)
    before = live_snapshot(state)
    real = os.rename
    calls = []

    def flaky(source, target):
        calls.append(source)
        if len(calls) == 3:
            raise OSError("synthetic rename failure")
        real(source, target)

    monkeypatch.setattr(restore.os, "rename", flaky)
    with pytest.raises(restore.RestoreRefused, match="nothing changed"):
        run_activate(state)
    monkeypatch.setattr(restore.os, "rename", real)

    assert live_snapshot(state)[:2] == before[:2]


def test_failed_orphan_cleanup_is_reported(tmp_path):
    state, restic = backed_up(tmp_path)
    ledger(state).append(999, "suppress", "archived", 1.0)
    run_restore(state, restic)
    make_private(state)

    def broken(chunk_ids):
        raise OSError("synthetic delete failure")

    with state.connect(write=True) as db:
        db.execute(
            "INSERT INTO archive_repositories(repo_id, full_name) VALUES(5, 'a/b')"
        )
        db.execute(
            "INSERT INTO archive_documents(repo_id, revision) VALUES(5, ?)", ("d" * 64,)
        )
        db.execute(
            "INSERT INTO archive_chunks(chunk_id, repo_id, revision, ordinal, text, "
            "token_count) VALUES(?, 5, ?, 0, 'x', 3)",
            ("e" * 64, "d" * 64),
        )
    state.vectors.delete = broken

    summary = run_activate(state)

    assert summary["result"] == "activated" and summary["orphan_vectors"] == "failed"


def test_a_new_restore_replaces_an_unused_quarantine(tmp_path):
    state, restic = backed_up(tmp_path)
    ledger(state).append(999, "suppress", "archived", 1.0)
    run_restore(state, restic)
    (quarantine(state) / "leftover").write_text("old", "utf-8")

    run_restore(state, restic)

    assert not (quarantine(state) / "leftover").exists()


@pytest.mark.parametrize(
    ("argv", "name", "result"),
    [
        (["restore"], "restore_to_quarantine", "quarantined"),
        (["restore", "--activate"], "activate", "activated"),
    ],
)
def test_restore_cli_prints_its_result(
    tmp_path, monkeypatch, capsys, argv, name, result
):
    from test_archive_worker import make_settings

    settings = make_settings(
        tmp_path,
        archive_license_allowlist=list(worker.ARCHIVE_BACKFILL_LICENSES),
    )
    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(restore, name, lambda *a, **k: {"result": result})
    runtime = SimpleNamespace(
        connect=None,
        content=None,
        vectors=SimpleNamespace(close=lambda: None),
        adapter=None,
    )
    monkeypatch.setattr(worker, "build_runtime", lambda _: runtime)
    monkeypatch.setattr(worker, "ArchiveStore", lambda _: SimpleNamespace(connect=None))
    monkeypatch.setattr(worker, "ArchiveContentStore", lambda _: None)
    monkeypatch.setattr(worker, "ArchiveGitHubReader", lambda **_: None)

    code = worker.main(argv)

    assert code == 0
    assert json.loads(capsys.readouterr().out)["result"] == result


def test_restore_cli_refuses_a_non_d2_allowlist(tmp_path, monkeypatch, capsys):
    from test_archive_worker import make_settings

    monkeypatch.setattr(worker, "Settings", lambda: make_settings(tmp_path))

    assert worker.main(["restore"]) == 1
    assert "ALLOWLIST" in json.loads(capsys.readouterr().out)["error"]


def make_legacy(tree):
    """Rewrite the backup as T18-era rows: no payload_version, id or language."""
    copy = tree / "catalogue.sqlite3"
    db = sqlite3.connect(copy)
    for repo_id, text in db.execute(
        "SELECT repo_id, metadata_json FROM archive_repositories"
    ).fetchall():
        stored = json.loads(text)
        legacy = {
            key: stored[key]
            for key in (
                "default_branch",
                "visibility",
                "archived",
                "fork",
                "license_spdx",
                "pushed_at",
            )
        }
        db.execute(
            "UPDATE archive_repositories SET metadata_json=? WHERE repo_id=?",
            (json.dumps(legacy), repo_id),
        )
    db.commit()
    db.close()
    rewrite_manifest(
        tree,
        lambda m: m.update(
            catalogue={"sha256": _sha256(copy), "bytes": copy.stat().st_size}
        ),
    )


@pytest.mark.parametrize("trusted", [False, True])
def test_legacy_metadata_is_rechecked_not_dropped(tmp_path, trusted):
    state, restic = backed_up(tmp_path)
    make_legacy(restic.snapshots[-1])
    if trusted:
        ledger(state).append(999, "suppress", "archived", 1.0)

    verdict = run_restore(state, restic)

    assert verdict["repositories"] == 1 and verdict["expired"] == 0
    assert verdict["rechecked"] == 1
    path = quarantine(state) / "catalogue.sqlite3"
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        stored = json.loads(
            db.execute("SELECT metadata_json FROM archive_repositories").fetchone()[0]
        )
    assert stored["payload_version"] == 2 and stored["language"] == "Python"

    summary = run_activate(state)

    assert summary["vectors"] > 0
    assert {row.language for row in state.vectors.rows.values()} == {"Python"}


def test_legacy_metadata_without_github_stays_quarantined(tmp_path):
    state, restic = backed_up(tmp_path)
    make_legacy(restic.snapshots[-1])
    ledger(state).append(999, "suppress", "archived", 1.0)

    with pytest.raises(restore.RestoreRefused, match="GitHub"):
        run_restore(state, restic, github=False)


def test_restore_that_removes_everything_offline_is_flagged(tmp_path):
    state, restic = backed_up(tmp_path)
    ledger(state).append(999, "suppress", "archived", 1.0)

    verdict = run_restore(state, restic, now=NOW + timedelta(days=400))

    assert verdict["repositories"] == 0 and "warning" in verdict
