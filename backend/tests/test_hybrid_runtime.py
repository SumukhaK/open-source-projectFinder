"""T15: lazy hybrid runtime and T10 later-page revalidation adapter."""

import json
import sqlite3
import time
from threading import Lock
from types import SimpleNamespace

import pytest
from app.core.archive_store import APPLICATION_ID, MIGRATIONS
from app.core.config import Settings
from app.integrations.archive_github import RepositoryNotFound
from app.integrations.milvus import MilvusUnavailable
from app.services.eligibility import ArchiveEvidence, EligibilityResult
from app.services.hybrid_runtime import (
    FusedRevalidator,
    HybridRuntime,
    HybridUnavailable,
    archive_counts,
)
from app.services.rank_fusion import ArchiveCard, FusedCandidate


def metadata(repo_id, **changes):
    data = {
        "id": repo_id,
        "full_name": f"owner/repo-{repo_id}",
        "private": False,
        "archived": False,
        "visibility": "public",
        "pushed_at": "2026-10-01T00:00:00Z",
    }
    data.update(changes)
    return data


def candidate(repo_id, *, archive=None, **changes):
    return FusedCandidate(
        rank=1,
        repo_id=repo_id,
        metadata=metadata(repo_id, **changes),
        sources=("archive",) if archive else ("github",),
        rrf_score=0.01,
        license="MIT",
        license_conflict=False,
        archive=archive,
    )


class FakeEligibility:
    def __init__(self, active):
        self.active = set(active)
        self.calls = []

    def check(self, archive_hits, *, live=None):
        self.calls.append((archive_hits, live))
        kept = tuple(
            value
            for repo_id, value in (live or {}).items()
            if repo_id in self.active and value.get("private") is False
        )
        evidence = tuple(
            ArchiveEvidence(hit, metadata(hit["repo_id"]))
            for hit in archive_hits
            if hit["repo_id"] in self.active
        )
        return EligibilityResult(kept, evidence, ())


class FakeReader:
    def __init__(self, fresh=None, error=None):
        self.fresh = fresh or {}
        self.error = error
        self.calls = []

    def fetch_metadata(self, repo_id, full_name):
        self.calls.append((repo_id, full_name))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            response=SimpleNamespace(body=json.dumps(self.fresh[repo_id]))
        )


def test_revalidator_keeps_only_freshly_verified_repositories():
    archive = ArchiveCard("snippet", "Features", "revision-2", "chunk-2")
    cards = [
        candidate(1, private=True),
        candidate(2, archive=archive),
        candidate(3),
    ]
    eligibility = FakeEligibility({2, 3})
    reader = FakeReader({1: metadata(1, private=True), 3: metadata(3)})

    kept = FusedRevalidator(eligibility, reader)(cards)

    assert [item.repo_id for item in kept] == [2, 3]
    hits, live = eligibility.calls[0]
    assert hits == [{"repo_id": 2, "revision": "revision-2", "chunk_id": "chunk-2"}]
    assert live == {1: metadata(1, private=True), 3: metadata(3)}
    assert set(reader.calls) == {(1, "owner/repo-1"), (3, "owner/repo-3")}


def test_revalidator_fails_closed_when_a_fresh_read_fails():
    cards = [candidate(1), candidate(2)]
    eligibility = FakeEligibility({1, 2})
    reader = FakeReader(error=RepositoryNotFound("gone"))

    kept = FusedRevalidator(eligibility, reader)(cards)

    assert kept == []
    hits, live = eligibility.calls[0]
    assert hits == [] and live == {}


def test_revalidator_drops_cards_without_a_usable_name():
    cards = [candidate(1, full_name=None)]
    eligibility = FakeEligibility({1})
    reader = FakeReader()

    kept = FusedRevalidator(eligibility, reader)(cards)

    assert kept == []
    assert reader.calls == []


def test_revalidator_serves_a_warm_cache_without_http():
    cards = [candidate(repo_id) for repo_id in range(1, 21)]
    eligibility = FakeEligibility(set(range(1, 21)))
    reader = FakeReader({repo_id: metadata(repo_id) for repo_id in range(1, 21)})
    revalidator = FusedRevalidator(eligibility, reader)

    assert [item.repo_id for item in revalidator(cards)] == list(range(1, 21))
    reader.calls.clear()

    class Exploding:
        def fetch_metadata(self, repo_id, full_name):
            raise AssertionError("a warm cache must not perform HTTP")

    revalidator.reader = Exploding()
    assert [item.repo_id for item in revalidator(cards)] == list(range(1, 21))


def test_revalidator_stops_at_the_deadline_and_drops_unverified_cards():
    cards = [candidate(repo_id) for repo_id in range(1, 21)]

    class SlowReader:
        def __init__(self):
            self.calls = []

        def fetch_metadata(self, repo_id, full_name):
            self.calls.append(repo_id)
            time.sleep(0.5)
            return SimpleNamespace(
                response=SimpleNamespace(body=json.dumps(metadata(repo_id)))
            )

    revalidator = FusedRevalidator(
        FakeEligibility(set(range(1, 21))), SlowReader(), max_workers=4
    )
    revalidator.begin(time.monotonic() + 0.15)
    started = time.monotonic()
    kept = revalidator(cards)
    elapsed = time.monotonic() - started

    assert elapsed < 0.4
    assert kept == []


def test_revalidator_bounds_concurrent_fresh_reads():
    cards = [candidate(repo_id) for repo_id in range(1, 21)]
    active = 0
    peak = 0
    guard = Lock()

    class Reader:
        def fetch_metadata(self, repo_id, full_name):
            nonlocal active, peak
            with guard:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with guard:
                active -= 1
            return SimpleNamespace(
                response=SimpleNamespace(body=json.dumps(metadata(repo_id)))
            )

    revalidator = FusedRevalidator(
        FakeEligibility(set(range(1, 21))), Reader(), max_workers=4
    )

    assert len(revalidator(cards)) == 20
    assert 1 < peak <= 4


def test_revalidator_drops_a_repository_that_became_private_without_caching_it():
    cards = [candidate(7)]
    eligibility = FakeEligibility({7})
    reader = FakeReader({7: metadata(7, private=True)})
    revalidator = FusedRevalidator(eligibility, reader)

    assert revalidator(cards) == []
    assert revalidator(cards) == []
    assert reader.calls == [(7, "owner/repo-7"), (7, "owner/repo-7")]


def test_revalidator_cache_expires_at_its_absolute_deadline():
    clock = [0.0]
    cards = [candidate(7)]
    reader = FakeReader({7: metadata(7)})
    revalidator = FusedRevalidator(
        FakeEligibility({7}),
        reader,
        settings=Settings(_env_file=None, archive_visibility_ttl_seconds=900),
        now=lambda: clock[0],
    )

    assert [item.repo_id for item in revalidator(cards)] == [7]
    reader.calls.clear()
    assert [item.repo_id for item in revalidator(cards)] == [7]
    assert reader.calls == []

    clock[0] = 901.0
    assert [item.repo_id for item in revalidator(cards)] == [7]
    assert reader.calls == [(7, "owner/repo-7")]


def catalogue(path, *, repositories=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        for migration in MIGRATIONS:
            for statement in migration:
                db.execute(statement)
        db.execute(f"PRAGMA application_id={APPLICATION_ID}")
        db.execute(f"PRAGMA user_version={len(MIGRATIONS)}")
        for repo_id in range(1, repositories + 1):
            db.execute(
                "INSERT INTO archive_repositories(repo_id, full_name) VALUES (?, ?)",
                (repo_id, f"owner/repo-{repo_id}"),
            )
    return path


def test_archive_counts_distinguish_uninitialized_from_recorded_runs(tmp_path):
    path = catalogue(tmp_path / "catalogue.sqlite3")

    counts = archive_counts(path)
    assert counts == {
        "repositories": 0,
        "published_documents": 0,
        "chunks": 0,
        "latest_run": None,
    }

    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO archive_runs(kind, due_period, completed) "
            "VALUES ('weekly', '2026-10-24T00:00:00+00:00', 1)"
        )
    counts = archive_counts(path)
    assert counts["latest_run"] == {
        "kind": "weekly",
        "due_period": "2026-10-24T00:00:00+00:00",
        "completed": True,
    }


def test_archive_counts_opens_the_catalogue_read_only(tmp_path):
    path = tmp_path / "missing" / "catalogue.sqlite3"

    with pytest.raises(sqlite3.OperationalError):
        archive_counts(path)
    assert not path.exists()
    assert not path.parent.exists()


def test_archive_counts_rejects_an_unexpected_schema(tmp_path):
    path = tmp_path / "catalogue.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE archive_repositories (repo_id INTEGER)")

    with pytest.raises(RuntimeError):
        archive_counts(path)


def test_runtime_status_leaves_a_missing_catalogue_absent(tmp_path):
    archive = tmp_path / "archive" / "catalogue.sqlite3"
    settings = Settings(
        _env_file=None,
        database_path=str(tmp_path / "auth.sqlite3"),
        archive_database_path=archive,
        archive_content_path=tmp_path / "archive" / "content",
    )

    status = HybridRuntime(settings, provider=None).status()

    assert status["state"] == "unknown"
    assert status["repositories"] is None
    assert status["published_documents"] is None
    assert status["chunks"] is None
    assert status["latest_run"] is None
    assert not archive.exists()
    assert not archive.parent.exists()


def test_runtime_status_reads_an_initialized_catalogue_without_migrating(tmp_path):
    archive = tmp_path / "archive" / "catalogue.sqlite3"
    catalogue(archive, repositories=2)
    settings = Settings(
        _env_file=None,
        database_path=str(tmp_path / "auth.sqlite3"),
        archive_database_path=archive,
        archive_content_path=tmp_path / "archive" / "content",
    )

    status = HybridRuntime(settings, provider=None).status()

    assert status["state"] == "initialized"
    assert status["repositories"] == 2
    assert status["published_documents"] == 0
    assert status["chunks"] == 0


def test_runtime_status_is_sanitized_and_never_invents_a_last_success(tmp_path):
    settings = Settings(
        _env_file=None,
        database_path=str(tmp_path / "auth.sqlite3"),
        archive_database_path=tmp_path / "archive" / "catalogue.sqlite3",
        archive_content_path=tmp_path / "archive" / "content",
    )
    status = HybridRuntime(settings, provider=None).status()

    assert status["state"] in {"unknown", "uninitialized"}
    assert status["coverage"] == "unknown"
    assert status["archive_as_of"] is None
    assert status["latest_run"] is None
    assert status["ranking_version"] == "rrf-v1"
    assert status["search_configured"] is False
    assert status["generation"] is None
    rendered = json.dumps(status)
    assert str(tmp_path) not in rendered
    assert "sqlite" not in rendered.lower()
    assert "error" not in rendered.lower()


def test_runtime_checks_the_signing_key_before_loading_the_model(monkeypatch):
    settings = Settings(_env_file=None, hybrid_cursor_signing_key="")

    def fail():
        raise AssertionError("model must not load without a signing key")

    monkeypatch.setattr(
        "app.services.hybrid_runtime.ModelManifest.load",
        classmethod(lambda cls: fail()),
    )
    runtime = HybridRuntime(settings, provider=None)
    with pytest.raises(HybridUnavailable):
        runtime.target()


class FakeStore:
    def connect(self):
        raise AssertionError("live-only searches never open the catalogue")


class FakeArchiveReader:
    def __init__(self, settings=None):
        self.settings = settings


def runtime_with(monkeypatch, *, load, connect, clock=None, retry=30):
    settings = Settings(
        _env_file=None,
        hybrid_cursor_signing_key="k" * 40,
        hybrid_build_retry_seconds=retry,
    )
    monkeypatch.setattr(
        "app.services.hybrid_runtime.EmbeddingAdapter.load",
        classmethod(lambda cls: load()),
    )
    monkeypatch.setattr(
        "app.integrations.milvus.MilvusAdapter.connect",
        classmethod(connect),
    )
    monkeypatch.setattr(
        "app.services.hybrid_runtime.ArchiveGitHubReader", FakeArchiveReader
    )
    monkeypatch.setattr(
        "app.services.hybrid_runtime.ModelManifest.load",
        classmethod(lambda cls: SimpleNamespace(revision="m" * 40)),
    )
    runtime = HybridRuntime(
        settings,
        provider=None,
        now=(lambda: clock[0]) if clock is not None else None,
    )
    monkeypatch.setattr(runtime, "_archive_store", lambda: FakeStore())
    return runtime


def loaded_model(loads):
    def load():
        loads.append(1)
        return SimpleNamespace(manifest=SimpleNamespace(revision="a" * 40))

    return load


def milvus_down(connects):
    def connect(cls, settings, manifest):
        connects.append(1)
        raise MilvusUnavailable("milvus is down")

    return connect


def test_runtime_serves_live_only_when_milvus_is_down(monkeypatch):
    loads, connects = [], []
    runtime = runtime_with(
        monkeypatch, load=loaded_model(loads), connect=milvus_down(connects)
    )

    target = runtime.target()

    assert target.archive_online is False
    assert target.generation == f"{'a' * 40}:rrf-v1"
    assert target.revalidator is not None
    assert len(loads) == 1 and len(connects) == 1


def test_runtime_serves_live_only_when_the_model_cannot_load(monkeypatch):
    from app.services.embeddings import EmbeddingError

    def load():
        raise EmbeddingError("model files are missing")

    def connect(cls, settings, manifest):
        raise AssertionError("Milvus is not contacted without a model")

    runtime = runtime_with(monkeypatch, load=load, connect=connect)

    target = runtime.target()

    assert target.archive_online is False
    # The manifest still names the pinned revision even without weights.
    assert target.generation == f"{'m' * 40}:rrf-v1"


def test_live_only_target_reports_the_archive_as_failed(monkeypatch):
    import asyncio

    from app.services.hybrid_runtime import ArchiveOffline, _OfflineArchive

    offline = _OfflineArchive()
    with pytest.raises(ArchiveOffline):
        offline.embed(["idea"], kind="query")
    with pytest.raises(ArchiveOffline):
        offline.search([0.0], limit=10, filters=None)

    runtime = runtime_with(monkeypatch, load=loaded_model([]), connect=milvus_down([]))
    target = runtime.target()
    service = target.pager.service

    async def archive_only():
        live = asyncio.get_running_loop().create_future()
        live.set_result(None)
        deadline = asyncio.get_running_loop().time() + 5
        return await service._archive("task manager", None, deadline, live)

    outcome = asyncio.run(archive_only())
    assert outcome.status == "failed"
    assert outcome.reason == "unavailable"
    service.close()
    target.executor.close()


def test_runtime_reuses_the_live_only_target_until_the_backoff_ends(monkeypatch):
    clock = [0.0]
    loads, connects = [], []
    runtime = runtime_with(
        monkeypatch,
        load=loaded_model(loads),
        connect=milvus_down(connects),
        clock=clock,
    )

    first = runtime.target()
    clock[0] = 10.0
    assert runtime.target() is first
    assert len(connects) == 1

    clock[0] = 31.0
    second = runtime.target()
    assert second is not first
    assert second.archive_online is False
    assert len(connects) == 2
    # The model is loaded once and reused across retries.
    assert len(loads) == 1
    # Both builds share one executor, so swapping targets strands no threads.
    assert second.executor is first.executor


def test_runtime_switches_to_the_full_stack_when_milvus_recovers(monkeypatch):
    clock = [0.0]
    state = {"up": False}
    vectors = SimpleNamespace(close=lambda: None)

    def connect(cls, settings, manifest):
        if not state["up"]:
            raise MilvusUnavailable("milvus is down")
        return vectors

    runtime = runtime_with(
        monkeypatch, load=loaded_model([]), connect=connect, clock=clock
    )
    assert runtime.target().archive_online is False

    state["up"] = True
    clock[0] = 31.0
    full = runtime.target()

    assert full.archive_online is True
    assert full.pager.service.vectors is vectors
    clock[0] = 1000.0
    assert runtime.target() is full


def test_runtime_keeps_serving_live_only_while_another_request_rebuilds(monkeypatch):
    clock = [0.0]
    connects = []
    runtime = runtime_with(
        monkeypatch,
        load=loaded_model([]),
        connect=milvus_down(connects),
        clock=clock,
    )
    first = runtime.target()
    clock[0] = 31.0

    runtime._build_lock.acquire()
    try:
        assert runtime.target() is first
    finally:
        runtime._build_lock.release()
    assert len(connects) == 1


def test_runtime_still_refuses_without_the_archive_reader(monkeypatch):
    from app.integrations.archive_github import ArchiveCredentialError

    def no_reader(settings=None):
        raise ArchiveCredentialError("worker token missing")

    loads = []
    runtime = runtime_with(
        monkeypatch, load=loaded_model(loads), connect=milvus_down([])
    )
    monkeypatch.setattr("app.services.hybrid_runtime.ArchiveGitHubReader", no_reader)

    with pytest.raises(HybridUnavailable):
        runtime.target()
    # A configuration failure is cached; no model load is attempted.
    with pytest.raises(HybridUnavailable):
        runtime.target()
    assert loads == []
