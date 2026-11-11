"""T20 suppression, purge and retention: fake GitHub/model/Milvus, real SQL."""

import json
import os
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest
from app.core.config import ARCHIVE_BACKFILL_LICENSES
from app.integrations.archive_github import (
    ArchiveAuthenticationError,
    ArchiveForbidden,
    ArchiveRateLimited,
    ArchiveRequestError,
    ArchiveUnavailable,
    RepositoryNotFound,
    RepositoryNotPublic,
)
from app.integrations.milvus import MilvusUnavailable
from app.services import archive_retirement as retirement
from app.services.archive_publication import filter_active_hits, load_active_chunks
from app.services.archive_runs import RunStore
from app.workers import archive as worker
from app.workers.retire import sweep
from test_archive_worker import (
    NOW,
    REPO_ID,
    FakeMilvus,
    harness,
    make_settings,
    make_snapshot,
)


class SweepReader:
    """Answers metadata-by-ID with a snapshot or a configured error."""

    def __init__(self, snapshot, outcome=None):
        self.snapshot = snapshot
        self.outcome = outcome
        self.requested = []

    def fetch_metadata_by_id(self, repo_id):
        self.requested.append(repo_id)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        snapshot = self.outcome or self.snapshot
        return SimpleNamespace(metadata=snapshot.metadata)


class FlakyMilvus(FakeMilvus):
    def __init__(self, settings, failures=1):
        super().__init__(settings)
        self.failures = failures

    def delete(self, chunk_ids):
        if self.failures:
            self.failures -= 1
            raise MilvusUnavailable("synthetic delete failure")
        super().delete(chunk_ids)


def published(tmp_path, *, milvus=None, **snapshot):
    settings = make_settings(
        tmp_path, archive_license_allowlist=list(ARCHIVE_BACKFILL_LICENSES)
    )
    state = harness(
        tmp_path, make_snapshot(**snapshot), settings=settings, milvus=milvus
    )
    result = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert result["result"] == "published"
    state.revision = result["revision"]
    return state


def run_sweep(state, outcome=None, **kwargs):
    reader = SweepReader(make_snapshot(), outcome)
    runtime = replace(state.runtime, reader=reader)
    return sweep(runtime, now=NOW, **kwargs), reader


def hits(state):
    return [
        {"repo_id": REPO_ID, "revision": state.revision, "chunk_id": chunk_id}
        for chunk_id in state.vectors.rows
    ] or [{"repo_id": REPO_ID, "revision": state.revision, "chunk_id": "x" * 64}]


def catalogue_counts(state):
    with state.connect() as db:
        return {
            table: db.execute(
                f"SELECT count(*) FROM {table} WHERE repo_id=?", (REPO_ID,)
            ).fetchone()[0]
            for table in ("archive_repositories", "archive_documents", "archive_chunks")
        }


def content_files(state):
    root = state.runtime.content.root
    return sorted(p for p in root.rglob("*") if p.is_file())


def ledger(state):
    return retirement.SuppressionLedger.for_catalogue(state.connect)


def assert_purged(state):
    assert catalogue_counts(state) == {
        "archive_repositories": 0,
        "archive_documents": 0,
        "archive_chunks": 0,
    }
    assert state.vectors.rows == {}
    assert content_files(state) == []


def test_public_to_private_suppresses_then_purges_everything(tmp_path):
    state = published(tmp_path)
    assert state.vectors.rows and content_files(state)

    summary, _ = run_sweep(state, RepositoryNotPublic("private now"))

    assert summary["suppressed"] == {"not_public": 1}
    assert summary["purged"] == 1
    assert_purged(state)
    assert ledger(state).current()[REPO_ID][0] == "not_public"
    with state.connect() as db:
        assert filter_active_hits(db, hits(state)) == []


def test_archived_repository_is_suppressed_and_purged(tmp_path):
    state = published(tmp_path)

    summary, _ = run_sweep(state, make_snapshot(archived=True))

    assert summary["suppressed"] == {"archived": 1}
    assert_purged(state)


def test_repo_404_is_ambiguous_not_found_never_deleted(tmp_path):
    state = published(tmp_path)

    summary, _ = run_sweep(state, RepositoryNotFound("404 is not deletion"))

    assert summary["suppressed"] == {"not_found": 1}
    assert ledger(state).current()[REPO_ID][0] == "not_found"
    assert_purged(state)


def test_missing_readme_with_public_metadata_keeps_the_repository(tmp_path):
    state = published(tmp_path, missing_readme=True)
    before = catalogue_counts(state)

    summary, _ = run_sweep(state, make_snapshot(missing_readme=True))

    assert summary["suppressed"] == {}
    assert summary["purged"] == 0
    assert catalogue_counts(state) == before


def test_licence_change_suppresses_as_licence(tmp_path):
    state = published(tmp_path)

    summary, _ = run_sweep(state, make_snapshot(license_spdx="GPL-3.0"))

    assert summary["suppressed"] == {"licence": 1}
    assert_purged(state)


@pytest.mark.parametrize(
    ("days", "purged"),
    [(364, False), (366, True)],
)
def test_cutoff_boundary_purges_without_suppressing(tmp_path, days, purged):
    state = published(tmp_path)

    summary, _ = run_sweep(state, make_snapshot(pushed_at=NOW - timedelta(days=days)))

    assert summary["suppressed"] == {}
    assert summary["expired"] == (1 if purged else 0)
    assert ledger(state).current() == {}
    if purged:
        assert_purged(state)
    else:
        assert catalogue_counts(state)["archive_chunks"] > 0


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ArchiveAuthenticationError("token expired"), "credential"),
        (ArchiveRateLimited("quota"), "rate_limit"),
        (ArchiveUnavailable("502"), "rate_limit"),
        (ArchiveForbidden("broad 403"), "forbidden"),
    ],
)
def test_credential_quota_5xx_and_403_never_wipe_the_catalogue(tmp_path, error, reason):
    state = published(tmp_path)
    before = (catalogue_counts(state), dict(state.vectors.rows), content_files(state))

    summary, _ = run_sweep(state, error)

    assert summary["stop_reason"] == reason
    assert summary["purged"] == 0
    assert (
        catalogue_counts(state),
        dict(state.vectors.rows),
        content_files(state),
    ) == before
    assert ledger(state).current() == {}


def test_451_is_a_blocked_suppression(tmp_path):
    state = published(tmp_path)
    blocked = ArchiveRequestError("legal block", response=SimpleNamespace(status=451))

    summary, _ = run_sweep(state, blocked)

    assert summary["suppressed"] == {"blocked": 1}
    assert_purged(state)


def test_partial_cleanup_never_serves_and_a_repeated_purge_finishes(tmp_path):
    settings = make_settings(
        tmp_path, archive_license_allowlist=list(ARCHIVE_BACKFILL_LICENSES)
    )
    state = published(tmp_path, milvus=FlakyMilvus(settings, failures=1))
    retirement.suppress(state.connect, ledger(state), REPO_ID, "not_public", 1.0)

    with pytest.raises(MilvusUnavailable):
        retirement.purge_repository(
            state.connect, state.vectors, state.runtime.content, REPO_ID
        )
    with state.connect() as db:
        assert filter_active_hits(db, hits(state)) == []
        assert load_active_chunks(db, REPO_ID) == ()

    first = retirement.purge_repository(
        state.connect, state.vectors, state.runtime.content, REPO_ID
    )
    again = retirement.purge_repository(
        state.connect, state.vectors, state.runtime.content, REPO_ID
    )

    assert first.documents == 1 and first.vectors > 0
    assert (again.documents, again.vectors, again.files) == (0, 0, 0)
    assert_purged(state)


def test_purge_removes_vectors_of_every_retained_revision(tmp_path):
    state = published(tmp_path)
    old_vectors = set(state.vectors.rows)
    state.runtime.reader.snapshot = make_snapshot(readme_text="# Compass\n\nNew text.")
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert old_vectors - set(state.vectors.rows) == old_vectors  # reconciled
    retirement.suppress(state.connect, ledger(state), REPO_ID, "operator", 1.0)

    retirement.purge_repository(
        state.connect, state.vectors, state.runtime.content, REPO_ID
    )

    assert state.vectors.rows == {}
    with state.connect() as db:
        stages = {
            row[0]
            for row in db.execute(
                "SELECT stage FROM archive_tasks WHERE repo_id=?", (REPO_ID,)
            )
        }
    assert stages == {"cleanup"}


def test_shared_content_files_survive_and_stale_files_are_swept(tmp_path):
    state = published(tmp_path)
    with state.connect() as db:
        raw_path = db.execute(
            "SELECT raw_path FROM archive_documents WHERE repo_id=?", (REPO_ID,)
        ).fetchone()[0]
    other = REPO_ID + 1
    with state.connect(write=True) as db:
        db.execute(
            "INSERT INTO archive_repositories(repo_id, full_name) VALUES(?, 'acme/twin')",
            (other,),
        )
        db.execute(
            "INSERT INTO archive_documents(repo_id, revision, raw_path, state) "
            "VALUES(?, ?, ?, 'pending')",
            (other, "b" * 64, raw_path),
        )
    stale = state.runtime.content.root / "raw" / "ab" / ("ab" + "0" * 62)
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b"orphan")
    fresh = state.runtime.content.root / "raw" / "cd" / ("cd" + "0" * 62)
    fresh.parent.mkdir(parents=True, exist_ok=True)
    fresh.write_bytes(b"recent")
    old = NOW.timestamp() - 31 * 86400
    os.utime(stale, (old, old))
    os.utime(fresh, (NOW.timestamp(), NOW.timestamp()))
    retirement.suppress(state.connect, ledger(state), REPO_ID, "not_public", 1.0)

    retirement.purge_repository(
        state.connect, state.vectors, state.runtime.content, REPO_ID
    )
    swept = retirement.sweep_unreferenced_files(
        state.connect, state.runtime.content, NOW.timestamp()
    )

    root = state.runtime.content.root
    assert (root / raw_path).exists()
    assert not stale.exists() and fresh.exists()
    assert swept == 1


def test_purge_then_republish_keeps_the_generation_high_water_mark(tmp_path):
    state = published(tmp_path)
    retired = set(state.vectors.rows)
    expired = make_snapshot(pushed_at=NOW - timedelta(days=400))
    run_sweep(state, expired)
    assert_purged(state)

    state.runtime.reader.snapshot = make_snapshot()
    again = worker.ingest_one(state.runtime, REPO_ID, now=NOW)

    assert again["result"] == "published"
    with state.connect() as db:
        generation = db.execute(
            "SELECT generation FROM archive_documents WHERE repo_id=?", (REPO_ID,)
        ).fetchone()[0]
    assert generation > 1
    assert set(state.vectors.rows).isdisjoint(retired)


def test_stale_purge_decision_cannot_remove_a_newer_safe_revision(tmp_path):
    state = published(tmp_path)
    old_revision = state.revision
    state.runtime.reader.snapshot = make_snapshot(readme_text="# Compass\n\nNewer.")
    newer = worker.ingest_one(state.runtime, REPO_ID, now=NOW)

    with pytest.raises(retirement.PurgeAborted):
        retirement.purge_repository(
            state.connect,
            state.vectors,
            state.runtime.content,
            REPO_ID,
            expect_active=old_revision,
        )
    with pytest.raises(retirement.PurgeAborted):
        retirement.purge_repository(
            state.connect, state.vectors, state.runtime.content, REPO_ID
        )
    with state.connect() as db:
        assert len(load_active_chunks(db, REPO_ID)) > 0
        assert (
            db.execute(
                "SELECT active_revision FROM archive_repositories WHERE repo_id=?",
                (REPO_ID,),
            ).fetchone()[0]
            == newer["revision"]
        )


def test_ledger_survives_restart_and_is_reapplied_to_a_restored_catalogue(tmp_path):
    state = published(tmp_path)
    run_sweep(state, RepositoryNotPublic("private"))
    with state.connect(write=True) as db:
        # Simulate restoring an older catalogue that predates the decision.
        db.execute("DELETE FROM archive_suppressions")

    reopened = retirement.SuppressionLedger(ledger(state).path)
    assert reopened.current()[REPO_ID][0] == "not_public"
    assert retirement.reapply(state.connect, reopened) == (1, 0)
    with state.connect() as db:
        assert (
            db.execute(
                "SELECT reason FROM archive_suppressions WHERE repo_id=?", (REPO_ID,)
            ).fetchone()[0]
            == "not_public"
        )


def test_ledger_is_content_free_and_private(tmp_path):
    state = published(tmp_path)
    run_sweep(state, RepositoryNotPublic("private"))

    path = ledger(state).path
    lines = path.read_text(encoding="ascii").splitlines()
    assert [set(json.loads(line)) for line in lines] == [
        {"v", "repo_id", "action", "reason", "at"}
    ]
    text = path.read_text(encoding="ascii")
    assert "acme" not in text and "Compass" not in text
    assert path.parent != state.runtime.content.root
    if os.name == "posix":
        assert path.stat().st_mode & 0o077 == 0


def test_torn_final_ledger_line_is_ignored(tmp_path):
    path = tmp_path / retirement.LEDGER_NAME
    ledger_file = retirement.SuppressionLedger(path)
    ledger_file.append(7, "suppress", "not_found", 1.0)
    with open(path, "a", encoding="ascii") as handle:
        handle.write('{"v": 1, "repo_id": 8, "act')

    assert ledger_file.current() == {7: ("not_found", 1.0)}


def test_suppressed_repository_is_lifted_when_public_again(tmp_path):
    state = published(tmp_path)
    run_sweep(state, RepositoryNotFound("gone for now"))

    later = replace(state.runtime, reader=SweepReader(make_snapshot()))
    summary = sweep(later, now=NOW + timedelta(days=1))

    assert summary["lifted"] == 1
    assert ledger(state).current() == {}
    with state.connect() as db:
        assert (
            db.execute("SELECT count(*) FROM archive_suppressions").fetchone()[0] == 0
        )


def test_operator_removal_is_never_lifted_automatically(tmp_path):
    state = published(tmp_path)
    summary, _ = run_sweep(state, make_snapshot(), remove_ids=(REPO_ID,))
    assert summary["removed"] == 1
    assert_purged(state)

    later = replace(state.runtime, reader=SweepReader(make_snapshot()))
    again = sweep(later, now=NOW + timedelta(days=1))

    assert again["lifted"] == 0
    assert ledger(state).current()[REPO_ID][0] == "operator"


def test_ingest_refuses_a_suppressed_repository(tmp_path):
    state = published(tmp_path)
    retirement.suppress(state.connect, ledger(state), REPO_ID, "operator", 1.0)

    with pytest.raises(worker.IneligibleRepository) as error:
        worker.ingest_one(state.runtime, REPO_ID, now=NOW)

    assert error.value.reason == "suppressed"


def test_repeated_suppression_does_not_grow_the_ledger(tmp_path):
    state = published(tmp_path)
    for _ in range(3):
        retirement.suppress(state.connect, ledger(state), REPO_ID, "not_public", 1.0)

    assert len(ledger(state).path.read_text(encoding="ascii").splitlines()) == 1


def test_run_compaction_preserves_max_fence_and_tombstones(tmp_path):
    state = published(tmp_path)
    state.runtime.reader.snapshot = make_snapshot(readme_text="# Compass\n\nTwo.")
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    store = RunStore(state.connect, clock=lambda: NOW.timestamp())
    with state.connect(write=True) as db:
        db.execute("UPDATE archive_runs SET heartbeat_at=0, expires_at=0")
        old_max = db.execute("SELECT MAX(fence) FROM archive_runs").fetchone()[0]
        db.execute(
            "INSERT INTO archive_runs(kind, due_period, fence, heartbeat_at) "
            "VALUES('backfill', 'pilot', 0, 0)"
        )
        tasks = db.execute(
            "SELECT count(*) FROM archive_tasks WHERE repo_id=?", (REPO_ID,)
        ).fetchone()[0]

    removed = retirement.compact_runs(state.connect, NOW.timestamp())

    with state.connect() as db:
        assert (
            db.execute("SELECT MAX(fence) FROM archive_runs").fetchone()[0] == old_max
        )
        kinds = [row[0] for row in db.execute("SELECT kind FROM archive_runs")]
        assert "backfill" in kinds
        assert (
            db.execute(
                "SELECT count(*) FROM archive_tasks WHERE repo_id=?", (REPO_ID,)
            ).fetchone()[0]
            == tasks
        )
    run_id = store.create_run("refresh", NOW)
    lease = store.claim(run_id, "next-owner")
    assert removed >= 1
    assert lease.fence > old_max


def test_sweep_refuses_a_non_d2_allowlist_before_any_request(
    tmp_path, monkeypatch, capsys
):
    settings = make_settings(tmp_path, archive_license_allowlist=[])
    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(
        worker,
        "build_runtime",
        lambda _: pytest.fail("retire built a runtime with a non-D2 allowlist"),
    )

    code = worker.main(["retire"])

    assert code == 1
    assert "approved backfill policy" in capsys.readouterr().out


def test_eligibility_suppression_reaches_the_ledger(tmp_path):
    from app.services.eligibility import EligibilityService

    state = published(tmp_path)
    service = EligibilityService(state.connect, None, state.settings, now=lambda: NOW)

    service._suppress(REPO_ID, "not_public", NOW)
    service._suppress(REPO_ID, "archived", NOW)

    assert ledger(state).current()[REPO_ID][0] == "not_public"


def stale_orphan(state):
    path = state.runtime.content.root / "raw" / "ef" / ("ef" + "0" * 62)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"unreferenced")
    old = NOW.timestamp() - 31 * 86400
    os.utime(path, (old, old))
    return path


def live_refresh_lease(state):
    store = RunStore(state.connect)
    run_id = store.create_run("refresh", NOW)
    return store.claim(run_id, "live-refresh")


def test_live_writer_lease_makes_file_sweep_and_compaction_wait(tmp_path):
    state = published(tmp_path)
    orphan = stale_orphan(state)
    live_refresh_lease(state)
    with state.connect() as db:
        runs = {row[0] for row in db.execute("SELECT run_id FROM archive_runs")}

    summary, _ = run_sweep(state, make_snapshot())

    assert summary["stop_reason"] == "busy"
    assert orphan.exists()
    with state.connect() as db:
        # Nothing compacted (a refused writer attempt may add an unused row).
        assert runs <= {row[0] for row in db.execute("SELECT run_id FROM archive_runs")}


def test_writer_busy_during_a_purge_returns_a_busy_summary(tmp_path):
    state = published(tmp_path)
    live_refresh_lease(state)

    summary, _ = run_sweep(state, RepositoryNotPublic("private"))

    assert summary["stop_reason"] == "busy"
    assert summary["suppressed"] == {"not_public": 1}
    with state.connect() as db:
        # T10 serving excludes suppressed IDs, so it is hidden before the purge.
        assert (
            db.execute(
                "SELECT reason FROM archive_suppressions WHERE repo_id=?", (REPO_ID,)
            ).fetchone()[0]
            == "not_public"
        )


def add_refresh_run(db, due, *, completed, state):
    run_id = db.execute(
        "INSERT INTO archive_runs(kind, due_period, completed, heartbeat_at) "
        "VALUES('refresh', ?, ?, 0)",
        (due, int(completed)),
    ).lastrowid
    db.execute(
        "INSERT INTO archive_backfill_state(run_id, state_json) VALUES(?, ?)",
        (run_id, json.dumps(state)),
    )
    return run_id


def test_compaction_keeps_the_latest_completed_and_latest_refresh_runs(tmp_path):
    state = published(tmp_path)
    with state.connect(write=True) as db:
        oldest = add_refresh_run(
            db, "2025-12-06T22:00:00+00:00", completed=True, state={"sweep_index": 4}
        )
        completed = add_refresh_run(
            db, "2026-01-03T22:00:00+00:00", completed=True, state={"sweep_index": 5}
        )
        latest = add_refresh_run(
            db, "2026-02-07T22:00:00+00:00", completed=False, state={"sweep_start": 5}
        )
        db.execute("UPDATE archive_runs SET heartbeat_at=0, expires_at=0")

    retirement.compact_runs(state.connect, NOW.timestamp())

    with state.connect() as db:
        kept = {row[0] for row in db.execute("SELECT run_id FROM archive_runs")}
        states = {
            row[0] for row in db.execute("SELECT run_id FROM archive_backfill_state")
        }
    assert {completed, latest} <= kept and {completed, latest} <= states
    assert oldest not in kept


def add_known(state, *repo_ids):
    with state.connect(write=True) as db:
        db.executemany(
            "INSERT INTO archive_repositories(repo_id, full_name) VALUES(?, ?)",
            [(repo_id, f"acme/r{repo_id}") for repo_id in repo_ids],
        )


def test_known_repository_checks_rotate_beyond_the_limit(tmp_path):
    state = published(tmp_path)
    add_known(state, 1, 2, 3, 4)
    seen = []

    for day in range(3):
        reader = SweepReader(make_snapshot())
        runtime = replace(state.runtime, reader=reader)
        sweep(runtime, now=NOW + timedelta(days=day), limit=2)
        seen.append(reader.requested)

    assert seen == [[1, 2], [3, 4], [REPO_ID, 1]]


def test_suppressed_rechecks_rotate_beyond_the_limit(tmp_path):
    state = published(tmp_path)
    for repo_id in (11, 12, 13):
        retirement.suppress(state.connect, ledger(state), repo_id, "not_found", 1.0)
    seen = []

    for day in range(3):
        reader = SweepReader(make_snapshot(), RepositoryNotFound("still gone"))
        runtime = replace(state.runtime, reader=reader)
        sweep(runtime, now=NOW + timedelta(days=day), limit=1)
        seen.append(
            [repo_id for repo_id in reader.requested if repo_id in (11, 12, 13)]
        )

    assert seen == [[11], [12], [13]]
