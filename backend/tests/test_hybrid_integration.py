"""Opt-in T26 proof of the archive -> Milvus -> FastAPI -> HTTP hybrid path.

Run only with ``RUN_HYBRID_INTEGRATION=1`` against the CPU Milvus stack and a
private ``MILVUS_TOKEN``. The default suite skips this module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
import pytest
from app.core.archive_store import ArchiveStore
from app.integrations.archive_github import ArchiveGitHubReader
from app.integrations.milvus import MilvusAdapter, ScalarFilters
from app.services.archive_content import ArchiveContentStore
from app.services.embeddings import ModelManifest
from app.workers.archive import IngestRuntime, ingest_one
from hybrid_e2e_fixtures import (
    ARCHIVE_IDS,
    EXPECTED_ORDER,
    EXPECTED_SOURCES,
    INCOMPLETE_IDEA,
    INCOMPLETE_LANGUAGE,
    NORMAL_IDEA,
    QUERY_VECTOR,
    SPECS,
    FixtureEmbeddings,
    FixtureTransport,
)
from hybrid_e2e_support import (
    ServerProcess,
    assert_temp_root,
    build_settings,
    drop_owned_collection,
    login,
    new_collection_name,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_HYBRID_INTEGRATION") != "1",
    reason="Opt-in cross-layer lane needs the CPU Milvus stack",
)

KEY_BY_ID = {spec.repo_id: key for key, spec in SPECS.items()}
RRF_EXPECTED = {
    "B": 1 / 61 + 1 / 62,
    "A": 1 / 64 + 1 / 61,
    "D": 1 / 63 + 1 / 64,
    "G": 1 / 62,
    "C": 1 / 63,
    "E": 1 / 65,
    "F": 1 / 66,
}


@dataclass(frozen=True)
class Lane:
    root: object
    collection: str
    settings: object
    server: ServerProcess
    client: httpx.Client
    token: str

    def search(self, idea=NORMAL_IDEA, *, page_size=20, cursor=None, filters=None):
        body = {"idea": idea, "page_size": page_size}
        if cursor is not None:
            body["cursor"] = cursor
        if filters is not None:
            body["filters"] = filters
        return self.client.post(
            "/v1/projects/search",
            json=body,
            headers={"Authorization": f"Bearer {self.token}"},
        )


def keys(body):
    return [KEY_BY_ID[item["id"]] for item in body["items"]]


@pytest.fixture(scope="session")
def lane(tmp_path_factory):
    root = assert_temp_root(tmp_path_factory.mktemp("hybrid-t26"))
    collection = new_collection_name()
    settings = build_settings(root, collection)
    manifest = ModelManifest.load()
    vectors = MilvusAdapter.connect(settings, manifest)
    vectors.ensure_collection()
    try:
        try:
            content = ArchiveContentStore(settings)
            store = ArchiveStore(settings)
            transport = httpx.MockTransport(FixtureTransport())
            reader = ArchiveGitHubReader(
                token="fixture-archive-token",
                transport=transport,
                settings=settings,
                sleep=lambda _: None,
            )
            runtime = IngestRuntime(
                settings,
                reader,
                FixtureEmbeddings(),
                vectors,
                content,
                store.connect,
            )
            for repo_id in ARCHIVE_IDS:
                summary = ingest_one(runtime, repo_id)
                assert summary["result"] == "published", summary
        finally:
            vectors.close()
        with ServerProcess(root=root, collection=collection) as server:
            with httpx.Client(base_url=server.base_url, timeout=60) as client:
                token = login(client, server.base_url)
                yield Lane(root, collection, settings, server, client, token)
    finally:
        # Drop the owned collection even when ingestion or the server fails to
        # start, so a broken run cannot leak a Milvus collection.
        cleanup = MilvusAdapter.connect(settings, manifest)
        try:
            drop_owned_collection(cleanup.client, collection)
        finally:
            cleanup.close()


def test_mobile_adapter_contract(lane):
    response = lane.search()
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "items",
        "next_cursor",
        "has_more",
        "total",
        "degraded",
        "sources",
        "archive_as_of",
        "ranking_version",
        "generation",
    }
    assert body["total"] is None
    assert body["next_cursor"] is None
    assert body["has_more"] is False
    assert body["degraded"] is False
    assert body["archive_as_of"] is None
    assert body["ranking_version"] == "rrf-v1"
    assert isinstance(body["generation"], str) and body["generation"]
    assert set(body["sources"]) == {"github", "archive"}
    for health in body["sources"].values():
        assert set(health) >= {"status", "incomplete", "reason", "retry_after"}
        assert isinstance(health["status"], str)
        assert isinstance(health["incomplete"], bool)
    assert body["sources"]["archive"]["coverage"] == "unknown"
    assert body["sources"]["github"]["status"] == "ok"
    assert body["sources"]["archive"]["status"] == "ok"
    item_keys = {
        "id",
        "name",
        "full_name",
        "owner",
        "avatar_url",
        "description",
        "stars",
        "language",
        "url",
        "license",
        "sources",
        "license_conflict",
        "matched_section",
        "snippet",
        "freshness",
        "rank",
        "rrf_score",
    }
    assert body["items"]
    for item in body["items"]:
        assert set(item) == item_keys
        assert isinstance(item["id"], int)
        assert isinstance(item["stars"], int)
        assert item["language"] is None or isinstance(item["language"], str)
        assert isinstance(item["license_conflict"], bool)
        assert item["freshness"] in {"live", "archive", "live+archive"}
        assert isinstance(item["rank"], int)
        assert isinstance(item["rrf_score"], float)
        assert isinstance(item["sources"], list)
        assert set(item["sources"]) <= {"github", "archive"}


def test_union_and_provenance(lane):
    response = lane.search()
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["items"]]
    assert len(ids) == len(set(ids)), "a repository appears twice"
    assert keys(body) == list(EXPECTED_ORDER)
    for item in body["items"]:
        key = KEY_BY_ID[item["id"]]
        assert tuple(item["sources"]) == EXPECTED_SOURCES[key]
        if "archive" in item["sources"]:
            assert item["matched_section"] is not None
            assert item["snippet"]
        else:
            assert item["matched_section"] is None
            assert item["snippet"] is None
        expected_freshness = (
            "live+archive"
            if len(item["sources"]) == 2
            else "live"
            if item["sources"] == ["github"]
            else "archive"
        )
        assert item["freshness"] == expected_freshness


def test_known_fused_ranking_order(lane):
    response = lane.search()
    assert response.status_code == 200
    body = response.json()
    assert keys(body) == list(EXPECTED_ORDER)
    assert [item["rank"] for item in body["items"]] == list(range(1, 8))
    scores = [item["rrf_score"] for item in body["items"]]
    assert scores == sorted(scores, reverse=True)
    for item in body["items"]:
        key = KEY_BY_ID[item["id"]]
        assert item["rrf_score"] == pytest.approx(RRF_EXPECTED[key], rel=1e-12)


def test_fused_cursor_paging_has_no_repeats_or_gaps(lane):
    first = lane.search(page_size=2)
    assert first.status_code == 200
    body = first.json()
    collected = list(body["items"])
    seen_cursors = set()
    pages = [keys(body)]
    cursor = body["next_cursor"]
    assert body["has_more"] is True and cursor
    while cursor is not None:
        assert cursor not in seen_cursors
        seen_cursors.add(cursor)
        page = lane.search(page_size=2, cursor=cursor)
        assert page.status_code == 200
        body = page.json()
        pages.append(keys(body))
        collected.extend(body["items"])
        cursor = body["next_cursor"]
        assert body["has_more"] is (cursor is not None)
    assert pages == [["B", "A"], ["D", "G"], ["C", "E"], ["F"]]
    assert keys({"items": collected}) == list(EXPECTED_ORDER)
    ids = [item["id"] for item in collected]
    assert len(ids) == len(set(ids))
    assert [item["rank"] for item in collected] == list(range(1, 8))
    assert len(pages[-1]) == 1
    assert body["next_cursor"] is None
    assert body["has_more"] is False


def test_incomplete_source_is_never_labelled_empty(lane):
    degraded = lane.search(INCOMPLETE_IDEA)
    assert degraded.status_code == 200
    body = degraded.json()
    assert body["items"], "verified archive hits must still be served"
    assert body["degraded"] is True
    assert body["sources"]["github"]["status"] == "incomplete"
    assert body["sources"]["github"]["incomplete"] is True
    assert body["sources"]["archive"]["status"] == "ok"

    incomplete = lane.search(INCOMPLETE_IDEA, filters={"language": INCOMPLETE_LANGUAGE})
    assert incomplete.status_code == 503
    detail = incomplete.json()["detail"]
    assert detail["code"] == "SEARCH_INCOMPLETE"
    assert detail["retryable"] is True


def test_private_repository_is_suppressed_and_stays_gone(lane):
    public = lane.search()
    assert public.status_code == 200
    assert "D" in keys(public.json())

    private_id = SPECS["D"].repo_id
    for attempt in ("first-private-server", "restart"):
        with ServerProcess(
            root=lane.root, collection=lane.collection, private_ids=(private_id,)
        ) as server:
            with httpx.Client(base_url=server.base_url, timeout=60) as client:
                token = login(client, server.base_url)
                response = client.post(
                    "/v1/projects/search",
                    json={"idea": NORMAL_IDEA, "page_size": 20},
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert response.status_code == 200, response.text
            body = response.json()
            assert "D" not in keys(body), attempt
            assert body["sources"]["archive"]["status"] == "ok"
            assert body["sources"]["github"]["status"] == "ok"

    store = ArchiveStore(lane.settings)
    with store.connect() as db:
        suppressed = db.execute(
            "SELECT reason FROM archive_suppressions WHERE repo_id=?", (private_id,)
        ).fetchone()
    assert suppressed is not None and suppressed["reason"] == "not_public"

    vectors = MilvusAdapter.connect(lane.settings, ModelManifest.load())
    try:
        remaining = vectors.search(
            QUERY_VECTOR, limit=50, filters=ScalarFilters(repo_id=private_id)
        )
    finally:
        vectors.close()
    assert remaining, "suppression must not delete the archived vectors"
