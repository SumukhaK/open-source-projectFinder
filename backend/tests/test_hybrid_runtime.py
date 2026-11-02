"""T15: lazy hybrid runtime and T10 later-page revalidation adapter."""

import json
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from app.core.archive_store import MIGRATIONS
from app.core.config import Settings
from app.integrations.archive_github import RepositoryNotFound
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
    assert reader.calls == [(1, "owner/repo-1"), (3, "owner/repo-3")]


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


def connect_to(path):
    @contextmanager
    def connect(*, write=False):
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    return connect


def test_archive_counts_distinguish_uninitialized_from_recorded_runs(tmp_path):
    path = tmp_path / "catalogue.sqlite3"
    with sqlite3.connect(path) as db:
        for migration in MIGRATIONS:
            for statement in migration:
                db.execute(statement)

    counts = archive_counts(connect_to(path))
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
    counts = archive_counts(connect_to(path))
    assert counts["latest_run"] == {
        "kind": "weekly",
        "due_period": "2026-10-24T00:00:00+00:00",
        "completed": True,
    }


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
