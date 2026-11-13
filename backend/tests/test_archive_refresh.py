"""Offline T19b refresh tests: fake HTTP/model/Milvus, real SQL."""

import importlib.util
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from app.core.config import ARCHIVE_BACKFILL_LICENSES
from app.integrations.archive_github import ArchiveGitHubReader
from app.integrations.milvus import MilvusUnavailable
from app.services.embeddings import EmbeddingAdapter, ModelManifest
from app.workers import archive as worker
from app.workers.refresh import Refresh
from test_archive_github import readme_payload, repo_payload
from test_archive_publication import FakeVectors
from test_archive_worker import (
    NOW,
    REPO_ID,
    CountingAdapter,
    TinyEncoder,
    harness,
    make_settings,
)

README_A = "# Compass\n\nOffline maps for hikers.\n"
README_B = "# Compass\n\nNow with route planning.\n"
DUE = datetime(2026, 10, 24, 22, 0, tzinfo=timezone.utc)
PREVIOUS = DUE - timedelta(days=7)
# Tests that are not about the admission cap allow every fake discovery.
CAP = 1000


def api():
    assert importlib.util.find_spec("app.workers.refresh") is not None, (
        "T19b refresh worker missing"
    )
    from app.workers.refresh import Refresh

    return Refresh


class FakeGitHub:
    def __init__(self):
        self.repos = {}
        self.readmes = {}
        self.metadata_etags = {}
        self.readme_etags = {}
        self.requests = []
        self.search_ids = []
        self.dense_queries = set()
        self.quota_remaining = None

    def add(self, repo_id=REPO_ID, *, full_name=None, readme=README_A, **overrides):
        full_name = full_name or f"owner/r{repo_id}"
        payload = repo_payload(
            repo_id,
            full_name,
            **{
                "description": "Offline maps",
                "topics": ["maps", "offline"],
                "language": "Python",
                "stargazers_count": 1,
                **overrides,
            },
        )
        self.repos[repo_id] = payload
        self.readmes[repo_id] = readme
        self.metadata_etags[repo_id] = f'"m{repo_id}-1"'
        self.readme_etags[repo_id] = f'"r{repo_id}-1"'

    def change_metadata(self, repo_id=REPO_ID, **overrides):
        self.repos[repo_id].update(overrides)
        self.metadata_etags[repo_id] = self.metadata_etags[repo_id] + "-next"

    def change_readme(self, repo_id=REPO_ID, text=README_A):
        self.readmes[repo_id] = text
        self.readme_etags[repo_id] = self.readme_etags[repo_id] + "-next"

    def rename(self, repo_id, full_name):
        self.repos[repo_id]["full_name"] = full_name

    def handle(self, request):
        self.requests.append(request)
        remaining = 4000 if self.quota_remaining is None else self.quota_remaining
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(int(NOW.timestamp() + 3600)),
        }
        path = request.url.path
        if path == "/search/repositories":
            page = int(request.url.params.get("page", "1"))
            ids = self.search_ids if page == 1 else []
            return httpx.Response(
                200,
                json={
                    "total_count": 1000
                    if request.url.params["q"] in self.dense_queries
                    else len(self.search_ids),
                    "incomplete_results": False,
                    "items": [{"id": repo_id} for repo_id in ids],
                },
                headers=headers,
            )
        if path.startswith("/repositories/"):
            repo_id = int(path.rsplit("/", 1)[1])
            payload = self.repos.get(repo_id)
            if payload is None:
                return httpx.Response(404, json={}, headers=headers)
            etag = self.metadata_etags[repo_id]
            if request.headers.get("if-none-match") == etag:
                return httpx.Response(304, headers={**headers, "ETag": etag})
            return httpx.Response(200, json=payload, headers={**headers, "ETag": etag})
        if path.endswith("/readme"):
            full_name = path.split("/repos/", 1)[1].rsplit("/", 1)[0]
            repo_id = next(
                (
                    key
                    for key, value in self.repos.items()
                    if value["full_name"] == full_name
                ),
                None,
            )
            if repo_id is None or self.readmes.get(repo_id) is None:
                return httpx.Response(404, json={}, headers=headers)
            etag = self.readme_etags[repo_id]
            if request.headers.get("if-none-match") == etag:
                return httpx.Response(304, headers={**headers, "ETag": etag})
            return httpx.Response(
                200,
                json=readme_payload(self.readmes[repo_id]),
                headers={**headers, "ETag": etag},
            )
        raise AssertionError(f"unexpected archive path {path}")


class FailingDeletes(FakeVectors):
    def delete(self, chunk_ids):
        self.delete_attempts += 1
        raise MilvusUnavailable("synthetic delete failure")


def setup(tmp_path, github=None, *, vectors=None):
    github = github or FakeGitHub()
    vectors = vectors or FakeVectors()
    config = make_settings(
        tmp_path, archive_license_allowlist=list(ARCHIVE_BACKFILL_LICENSES)
    )
    state = harness(tmp_path, settings=config, milvus=vectors)
    reader = ArchiveGitHubReader(
        settings=config,
        transport=httpx.MockTransport(github.handle),
        now=lambda: NOW,
        sleep=lambda _: pytest.fail("unexpected sleep"),
    )
    runtime = replace(state.runtime, reader=reader)
    return SimpleNamespace(
        runtime=runtime,
        github=github,
        state=state,
        connect=runtime.connect,
        adapter=state.adapter,
        vectors=vectors,
    )


def seed_completed_run(connect, *, due=PREVIOUS, state=None):
    with connect(write=True) as db:
        run_id = db.execute(
            "INSERT INTO archive_runs(kind,due_period,completed) VALUES('refresh',?,1)",
            (due.isoformat(),),
        ).lastrowid
        if state is not None:
            db.execute(
                "INSERT INTO archive_backfill_state(run_id,state_json) VALUES(?,?)",
                (run_id, json.dumps(state)),
            )
    return run_id


def search_queries(github):
    return [
        request.url.params["q"]
        for request in github.requests
        if request.url.path == "/search/repositories"
    ]


def stored_metadata(connect, repo_id=REPO_ID):
    with connect() as db:
        return json.loads(
            db.execute(
                "SELECT metadata_json FROM archive_repositories WHERE repo_id=?",
                (repo_id,),
            ).fetchone()[0]
        )


def active_revision(connect, repo_id=REPO_ID):
    with connect() as db:
        return db.execute(
            "SELECT active_revision FROM archive_repositories WHERE repo_id=?",
            (repo_id,),
        ).fetchone()[0]


def test_legacy_metadata_row_is_not_trusted_for_conditional_reads(tmp_path):
    github = FakeGitHub()
    github.add()
    state = setup(tmp_path, github)
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    with state.connect(write=True) as db:
        db.execute(
            "UPDATE archive_repositories SET metadata_json=? WHERE repo_id=?",
            (json.dumps({"default_branch": "main"}), REPO_ID),
        )

    assert (
        worker.load_cached_repository(state.connect, state.runtime.content, REPO_ID)
        is None
    )

    result = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert result["unchanged"] == 1
    assert stored_metadata(state.connect)["payload_version"] == 2


def test_known_repository_unchanged_304_makes_no_embedding_calls(tmp_path):
    github = FakeGitHub()
    github.add()
    state = setup(tmp_path, github)
    first = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert first["result"] == "published"
    calls, upserts = state.adapter.calls, len(state.vectors.upserts)

    result = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert result["stop_reason"] == "finished"
    assert result["coverage"] == "complete"
    assert result["unchanged"] == 1
    assert result["known_ids"] == 1
    assert result["discovered"] == 0
    assert result["repositories"] == 1
    assert state.adapter.calls == calls
    assert len(state.vectors.upserts) == upserts
    assert any(request.headers.get("if-none-match") for request in github.requests)
    assert result["last_attempt_at"] is not None
    assert result["last_complete_at"] is not None
    assert result["last_completed_boundary"] == DUE.isoformat()


def test_stars_only_metadata_change_updates_scalars_without_embedding(tmp_path):
    github = FakeGitHub()
    github.add(stargazers_count=1)
    state = setup(tmp_path, github)
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    calls = state.adapter.calls
    github.change_metadata(stargazers_count=99)

    result = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert result["unchanged"] == 1
    assert state.adapter.calls == calls
    assert stored_metadata(state.connect)["stargazers_count"] == 99


def test_changed_description_and_topics_reembeds_but_reuses_cached_readme(tmp_path):
    github = FakeGitHub()
    github.add()
    state = setup(tmp_path, github)
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    calls = state.adapter.calls
    before = len(github.requests)
    github.change_metadata(description="Different maps", topics=["new"])

    result = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert result["published"] == 1
    assert state.adapter.calls == calls + 1
    assert not any(
        "/git/blobs/" in request.url.path for request in github.requests[before:]
    )


def test_removed_readme_publishes_metadata_only_and_retires_old_chunks(tmp_path):
    github = FakeGitHub()
    github.add()
    state = setup(tmp_path, github)
    first = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    old_revision = first["revision"]
    old_chunks = {chunk_id for batch in state.vectors.upserts for chunk_id in batch}
    github.readmes[REPO_ID] = None

    result = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert result["published"] == 1
    with state.connect() as db:
        active = db.execute(
            "SELECT active_revision FROM archive_repositories WHERE repo_id=?",
            (REPO_ID,),
        ).fetchone()[0]
        assert active != old_revision
        assert (
            db.execute(
                "SELECT 1 FROM archive_documents WHERE repo_id=? AND revision=?",
                (REPO_ID, old_revision),
            ).fetchone()
            is None
        )
        text = db.execute(
            "SELECT text FROM archive_chunks WHERE repo_id=? AND revision=? "
            "AND ordinal=0",
            (REPO_ID, active),
        ).fetchone()[0]
    assert text.startswith("Repository:")
    deleted = {chunk_id for batch in state.vectors.deletes for chunk_id in batch}
    assert old_chunks <= deleted


def test_rename_updates_the_catalogue_and_republishes(tmp_path):
    github = FakeGitHub()
    github.add()
    state = setup(tmp_path, github)
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    github.rename(REPO_ID, "new/name")
    github.change_metadata()

    result = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert result["published"] == 1
    with state.connect() as db:
        assert (
            db.execute(
                "SELECT full_name FROM archive_repositories WHERE repo_id=?",
                (REPO_ID,),
            ).fetchone()[0]
            == "new/name"
        )


def test_model_change_reembeds_even_when_metadata_and_readme_are_unchanged(tmp_path):
    github = FakeGitHub()
    github.add()
    state = setup(tmp_path, github)
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    changed = replace(ModelManifest.load(), revision="d" * 40)
    adapter = CountingAdapter(EmbeddingAdapter(changed, TinyEncoder(), batch_size=4))
    runtime = replace(state.runtime, adapter=adapter)

    result = api()(runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert result["published"] == 1
    assert adapter.calls == 1
    with state.connect() as db:
        assert (
            db.execute(
                "SELECT model_revision FROM archive_documents "
                "WHERE repo_id=? AND state='published'",
                (REPO_ID,),
            ).fetchone()[0]
            == changed.revision
        )


def test_readme_revert_republishes_after_cleanup_with_a_new_generation(tmp_path):
    github = FakeGitHub()
    github.add(readme=README_A)
    state = setup(tmp_path, github)
    a = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    a_chunks = {chunk_id for batch in state.vectors.upserts for chunk_id in batch}
    github.change_readme(text=README_B)
    assert worker.ingest_one(state.runtime, REPO_ID, now=NOW)["result"] == "published"
    with state.connect() as db:
        assert (
            db.execute(
                "SELECT 1 FROM archive_documents WHERE repo_id=? AND revision=?",
                (REPO_ID, a["revision"]),
            ).fetchone()
            is None
        )

    github.change_readme(text=README_A)
    result = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert result["stop_reason"] == "finished"
    assert result["published"] == 1
    assert active_revision(state.connect) == a["revision"]
    with state.connect() as db:
        generation = db.execute(
            "SELECT generation FROM archive_documents WHERE repo_id=? AND revision=?",
            (REPO_ID, a["revision"]),
        ).fetchone()[0]
    assert generation > 1
    new_chunks = {chunk_id for batch in state.vectors.upserts for chunk_id in batch}
    assert new_chunks - a_chunks


def test_superseded_row_is_reconciled_and_retried_before_failing(tmp_path):
    github = FakeGitHub()
    github.add(readme=README_A)
    vectors = FakeVectors(fail_delete_batch=0)
    state = setup(tmp_path, github, vectors=vectors)
    a = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    github.change_readme(text=README_B)
    assert worker.ingest_one(state.runtime, REPO_ID, now=NOW)["result"] == "published"
    with state.connect() as db:
        assert (
            db.execute(
                "SELECT state FROM archive_documents WHERE repo_id=? AND revision=?",
                (REPO_ID, a["revision"]),
            ).fetchone()[0]
            == "superseded"
        )
    vectors.fail_delete_batch = None
    github.change_readme(text=README_A)

    result = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert result["stop_reason"] == "finished"
    assert result["published"] == 1
    assert active_revision(state.connect) == a["revision"]


def test_superseded_reconcile_failure_is_partial_not_dependency(tmp_path):
    github = FakeGitHub()
    github.add(readme=README_A)
    state = setup(tmp_path, github, vectors=FailingDeletes())
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    github.change_readme(text=README_B)
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    github.change_readme(text=README_A)

    result = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert result["stop_reason"] == "incomplete"
    assert result["coverage"] == "partial"
    assert result["pending"] == 1
    assert result["last_completed_boundary"] is None
    with state.connect() as db:
        row = db.execute(
            "SELECT status,reason FROM archive_backfill_repositories WHERE run_id=?",
            (result["run_id"],),
        ).fetchone()
    assert row["status"] == "pending" and row["reason"] == "superseded"


def test_recent_discovery_starts_at_the_last_completed_boundary_minus_48h(tmp_path):
    github = FakeGitHub()
    state = setup(tmp_path, github)
    seed_completed_run(state.connect)
    github.search_ids = [9001]
    github.add(9001, full_name="owner/new")

    result = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    recent_from = PREVIOUS - timedelta(hours=48)
    expected = (
        f"pushed:{recent_from.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        f"..{DUE.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )
    assert any(expected in query for query in search_queries(github))
    assert result["discovered"] == 1
    assert result["repositories"] == 1
    assert result["published"] == 1


def test_sweep_rotates_through_full_window_buckets(tmp_path):
    github = FakeGitHub()
    state = setup(tmp_path, github)
    seed_completed_run(state.connect, state={"sweep_index": 3})

    result = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    start = DUE - timedelta(days=365) + timedelta(days=28 * 3)
    end = start + timedelta(days=28)
    expected = (
        f"pushed:{start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        f"..{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )
    assert any(expected in query for query in search_queries(github))
    with state.connect() as db:
        saved = json.loads(
            db.execute(
                "SELECT state_json FROM archive_backfill_state WHERE run_id=?",
                (result["run_id"],),
            ).fetchone()[0]
        )
    assert saved["sweep_index"] == 4


def test_quota_pause_is_partial_and_does_not_advance_watermarks(tmp_path):
    github = FakeGitHub()
    github.add()
    state = setup(tmp_path, github)
    seed_completed_run(
        state.connect,
        state={"last_complete_at": NOW.timestamp() - 3600, "sweep_index": 0},
    )
    github.quota_remaining = 0

    result = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert result["stop_reason"] == "quota"
    assert result["coverage"] == "partial"
    assert result["last_completed_boundary"] == PREVIOUS.isoformat()
    assert result["last_attempt_at"] is not None
    with state.connect() as db:
        assert (
            db.execute(
                "SELECT completed FROM archive_runs WHERE run_id=?",
                (result["run_id"],),
            ).fetchone()[0]
            == 0
        )

    github.quota_remaining = None
    clock = [NOW.timestamp() + 7200]
    resumed = api()(state.runtime, clock=lambda: clock[0]).run(refresh_cap=CAP)

    assert resumed["stop_reason"] == "finished"
    assert resumed["last_completed_boundary"] == DUE.isoformat()


def test_resume_retries_a_repository_that_failed_earlier(tmp_path, monkeypatch):
    github = FakeGitHub()
    github.add()
    state = setup(tmp_path, github)
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    from app.workers import refresh as refresh_module

    real = refresh_module.ingest_one
    failures = [1]

    def flaky(*args, **kwargs):
        if failures:
            failures.pop()
            raise worker.IngestError("synthetic transient failure")
        return real(*args, **kwargs)

    monkeypatch.setattr(refresh_module, "ingest_one", flaky)
    first = refresh_module.Refresh(state.runtime, clock=lambda: NOW.timestamp()).run(
        refresh_cap=CAP
    )
    assert first["failed"] == 1
    assert first["stop_reason"] == "incomplete"
    assert first["coverage"] == "partial"
    assert first["last_completed_boundary"] is None

    second = refresh_module.Refresh(state.runtime, clock=lambda: NOW.timestamp()).run(
        refresh_cap=CAP
    )

    assert second["run_id"] == first["run_id"]
    assert second["unchanged"] == 1
    assert second["failed"] == 0
    assert second["stop_reason"] == "finished"
    assert second["coverage"] == "complete"


def test_second_manual_run_for_the_same_boundary_is_idempotent(tmp_path):
    github = FakeGitHub()
    github.add()
    state = setup(tmp_path, github)
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)

    first = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)
    second = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert second["run_id"] == first["run_id"]
    assert second["stop_reason"] == "finished"
    assert second["last_completed_boundary"] == first["last_completed_boundary"]


def test_ineligible_known_repository_is_skipped_not_failed(tmp_path):
    github = FakeGitHub()
    github.add()
    state = setup(tmp_path, github)
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    github.change_metadata(archived=True)

    result = api()(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert result["skipped"] == {"archived": 1}
    assert result["failed"] == 0
    assert result["stop_reason"] == "finished"


@pytest.mark.parametrize(
    "moment,expected",
    [
        (
            datetime(2026, 10, 24, 21, 59, tzinfo=timezone.utc),
            datetime(2026, 10, 17, 22, 0, tzinfo=timezone.utc),
        ),
        (
            datetime(2026, 10, 24, 22, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 24, 22, 0, tzinfo=timezone.utc),
        ),
        (
            datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 24, 22, 0, tzinfo=timezone.utc),
        ),
    ],
)
def test_due_boundary_is_the_most_recent_saturday_2200_utc(moment, expected):
    from app.workers.refresh import due_boundary

    assert due_boundary(moment) == expected


@pytest.mark.parametrize("value", [0, 15, True, 1.5])
def test_invalid_sweep_bucket_count_is_rejected(tmp_path, value):
    state = setup(tmp_path)
    with pytest.raises(ValueError):
        api()(state.runtime, clock=lambda: NOW.timestamp()).run(sweep_buckets=value)


def test_quota_stop_mid_walk_resumes_from_next_unread_partition(tmp_path):
    """A quota stop mid-discovery followed by a resume continues from the next
    unread partition and repeats none of the earlier searches. This exercises
    the durable checkpointing that mirrors backfill.py's partition/task/page
    checkpoints."""
    github = FakeGitHub()
    # Create many repos across multiple pushed-time windows so splitting occurs
    base_repo_id = 1000
    for i in range(50):
        rid = base_repo_id + i
        github.add(rid, full_name=f"owner/repo{rid}")
        github.search_ids.append(rid)
    state = setup(tmp_path, github)
    seed_completed_run(state.connect, state={"sweep_index": 0})

    # First run: quota exhausted after a few search requests
    github.quota_remaining = 2  # triggers quota stop (2 <= 1000 threshold)
    result = Refresh(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)

    assert result["stop_reason"] == "quota"
    assert result["coverage"] == "partial"
    first_search_queries = [
        q for q in github.requests if q.url.path == "/search/repositories"
    ]
    # Quota stop fires after the first search response with remaining=2
    assert len(first_search_queries) >= 1
    first_query = first_search_queries[0].url.params["q"]

    # Resume: should continue from next unread partition, not restart
    github.quota_remaining = None
    clock = [NOW.timestamp() + 7200]
    resumed = Refresh(state.runtime, clock=lambda: clock[0]).run(refresh_cap=CAP)

    assert resumed["stop_reason"] == "finished"
    assert resumed["coverage"] == "complete"
    assert resumed["run_id"] == result["run_id"]  # same run

    # Verify no search query was repeated
    all_search_queries = [
        q for q in github.requests if q.url.path == "/search/repositories"
    ]
    assert len(all_search_queries) > 1
    seen = set()
    for q in all_search_queries:
        query = q.url.params["q"]
        assert query not in seen, f"duplicate search query: {query}"
        seen.add(query)
    # The original query should not appear again
    assert first_query not in [q.url.params["q"] for q in all_search_queries[1:]]


def add_new_repositories(github, count, first=5000):
    for repo_id in range(first, first + count):
        github.add(repo_id)
        github.search_ids.append(repo_id)
    return list(range(first, first + count))


def run_state(connect, run_id):
    with connect() as db:
        return json.loads(
            db.execute(
                "SELECT state_json FROM archive_backfill_state WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]
        )


def test_cap_admits_exactly_cap_new_repositories(tmp_path):
    github = FakeGitHub()
    new_ids = add_new_repositories(github, 5)
    state = setup(tmp_path, github)
    seed_completed_run(state.connect, state={"sweep_index": 2})

    result = Refresh(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=2)

    assert result["stop_reason"] == "cap"
    assert result["coverage"] == "partial"
    assert result["admitted"] == 2
    assert result["published"] == 2
    with state.connect() as db:
        stored = {
            row[0] for row in db.execute("SELECT repo_id FROM archive_repositories")
        }
    assert stored == set(new_ids[:2])
    saved = run_state(state.connect, result["run_id"])
    assert "sweep_index" not in saved
    assert "last_completed_boundary" not in saved
    assert result["last_completed_boundary"] == PREVIOUS.isoformat()

    # The next week's run retries the capped bucket instead of skipping it.
    next_week = NOW.timestamp() + 7 * 86400
    later = Refresh(state.runtime, clock=lambda: next_week).run(refresh_cap=2)
    assert run_state(state.connect, later["run_id"])["sweep_start"] == 2


def test_cap_holds_across_a_resume_without_repeating_searches(tmp_path):
    github = FakeGitHub()
    add_new_repositories(github, 5)
    state = setup(tmp_path, github)
    seed_completed_run(state.connect)
    first = Refresh(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=2)
    searches = len(search_queries(github))

    second = Refresh(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=2)

    assert first["run_id"] == second["run_id"]
    assert second["stop_reason"] == "cap"
    assert second["admitted"] == 2
    assert second["published"] == 2
    assert len(search_queries(github)) == searches


def test_cap_zero_reconciles_known_ids_without_searching(tmp_path):
    github = FakeGitHub()
    github.add()
    add_new_repositories(github, 3)
    state = setup(tmp_path, github)
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    github.requests.clear()

    result = Refresh(state.runtime, clock=lambda: NOW.timestamp()).run()

    assert result["stop_reason"] == "cap"
    assert result["coverage"] == "partial"
    assert result["unchanged"] == 1
    assert result["admitted"] == 0
    assert search_queries(github) == []


def test_resume_reuses_a_saved_page_that_needs_a_split(tmp_path, monkeypatch):
    from app.services.archive_partitions import DiscoveryPartition
    from app.services.archive_runs import RunStore

    github = FakeGitHub()
    state = setup(tmp_path, github)
    seed_completed_run(state.connect)
    root = DiscoveryPartition(PREVIOUS - timedelta(hours=48), DUE).query
    github.dense_queries.add(root)
    original = RunStore.add_split
    calls = []

    def crash_once(self, lease, split):
        calls.append(split)
        if len(calls) == 1:
            raise RuntimeError("synthetic kill after the page was saved")
        return original(self, lease, split)

    monkeypatch.setattr(RunStore, "add_split", crash_once)
    with pytest.raises(RuntimeError):
        Refresh(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=CAP)
    assert search_queries(github).count(root) == 1

    later = NOW.timestamp() + 3600
    resumed = Refresh(state.runtime, clock=lambda: later).run(refresh_cap=CAP)

    assert resumed["stop_reason"] == "finished"
    assert search_queries(github).count(root) == 1
    assert len(calls) == 2


def test_refresh_refuses_a_non_d2_allowlist_before_any_request(
    tmp_path, monkeypatch, capsys
):
    settings = make_settings(tmp_path, archive_license_allowlist=["MIT"])
    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(
        worker,
        "build_runtime",
        lambda _: pytest.fail("refresh built a runtime with a non-D2 allowlist"),
    )

    code = worker.main(["refresh", "--cap", "10"])

    assert code == 1
    assert "approved backfill policy" in capsys.readouterr().out


def test_chunker_v2_refresh_reembeds_once_then_is_unchanged(tmp_path, monkeypatch):
    from app.services import archive_index

    github = FakeGitHub()
    github.add()
    state = setup(tmp_path, github)
    with monkeypatch.context() as old:
        old.setattr(archive_index, "CHUNKER_VERSION", "sections-v1")
        first = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert first["result"] == "published"
    previous_revision = active_revision(state.connect)
    calls = state.adapter.calls

    refreshed = Refresh(state.runtime, clock=lambda: NOW.timestamp()).run(refresh_cap=0)

    assert refreshed["published"] == 1
    assert state.adapter.calls == calls + 1
    assert active_revision(state.connect) != previous_revision
    with state.connect() as db:
        assert (
            db.execute(
                "SELECT chunker_version FROM archive_documents WHERE state='published'"
            ).fetchone()[0]
            == "sections-v2"
        )
    calls = state.adapter.calls
    upserts = len(state.vectors.upserts)
    next_week = (NOW + timedelta(days=7)).timestamp()
    replay = Refresh(state.runtime, clock=lambda: next_week).run(refresh_cap=0)
    assert replay["unchanged"] == 1
    assert replay["published"] == 0
    assert state.adapter.calls == calls
    assert len(state.vectors.upserts) == upserts
