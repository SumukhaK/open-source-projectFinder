"""T15: authenticated hybrid v1 search and sanitized archive status."""

import asyncio
import json
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
from app.core.config import Settings
from app.core.store import digest
from app.main import create_app
from app.services.eligibility import ArchiveEvidence, EligibilityResult
from app.services.fused_cursor import HybridPager
from app.services.hybrid_runtime import FusedRevalidator, HybridRuntime
from app.services.hybrid_search import BoundedExecutor, HybridSearchResult
from app.services.rank_fusion import (
    ArchiveCard,
    FusedCandidate,
    FusedResults,
    SourceHealth,
)
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

KEY = "k" * 40
GENERATION = "a" * 40 + ":keyword-first-v1"
HEADERS = {"Authorization": "Bearer session1"}
OTHER_HEADERS = {"Authorization": "Bearer session2"}
IDEA = "an offline first app for sharing community tools"

REPO = {
    "id": 1,
    "name": "compass",
    "full_name": "octocat/compass",
    "private": False,
    "owner": {
        "login": "octocat",
        "avatar_url": "https://avatars.githubusercontent.com/u/1",
    },
    "description": "Find projects",
    "stargazers_count": 42,
    "language": "Python",
    "html_url": "https://github.com/octocat/compass",
    "default_branch": "main",
}


def metadata(repo_id, **changes):
    data = {
        "id": repo_id,
        "name": f"repo-{repo_id}",
        "full_name": f"owner/repo-{repo_id}",
        "owner": {
            "login": "owner",
            "avatar_url": "https://avatars.githubusercontent.com/u/1",
        },
        "description": f"Project {repo_id}",
        "stargazers_count": repo_id,
        "language": "Python",
        "private": False,
        "archived": False,
        "visibility": "public",
        "pushed_at": "2026-10-01T00:00:00Z",
        "license": {"spdx_id": "MIT"},
    }
    data.update(changes)
    return data


def card(
    rank,
    repo_id,
    *,
    sources=("github",),
    archive=None,
    license_value="MIT",
    license_conflict=False,
    **changes,
):
    return FusedCandidate(
        rank=rank,
        repo_id=repo_id,
        metadata=metadata(repo_id, **changes),
        sources=sources,
        rrf_score=1 / (60 + rank),
        license=license_value,
        license_conflict=license_conflict,
        archive=archive,
    )


def archive_card(rank, repo_id, *, section="Features", snippet="A bounded snippet"):
    return card(
        rank,
        repo_id,
        sources=("archive",),
        archive=ArchiveCard(
            snippet=snippet,
            section=section,
            revision=f"revision-{repo_id}",
            chunk_id=f"chunk-{repo_id}",
        ),
    )


def result(cards, *, status="ok", github=None, archive=None):
    return HybridSearchResult(
        FusedResults(
            tuple(cards),
            github or SourceHealth("ok"),
            archive or SourceHealth("ok"),
        ),
        status,
    )


class FakeService:
    def __init__(self, value):
        self.value = value
        self.calls = []
        self.loop_thread = None

    async def search(self, token, idea, *, language=None, license=None):
        self.loop_thread = threading.get_ident()
        self.calls.append(
            {"token": token, "idea": idea, "language": language, "license": license}
        )
        return self.value


class FakeRuntime:
    def __init__(
        self,
        pager,
        *,
        generation=GENERATION,
        status=None,
        executor=None,
        revalidator=None,
    ):
        self.pager = pager
        self.generation = generation
        self.executor = executor or BoundedExecutor(2, 4)
        self.revalidator = revalidator
        self.status_data = status or {
            "state": "uninitialized",
            "coverage": "unknown",
            "archive_as_of": None,
        }

    def target(self):
        return SimpleNamespace(
            pager=self.pager,
            generation=self.generation,
            executor=self.executor,
            revalidator=self.revalidator,
        )

    def status(self):
        return dict(self.status_data)


def pager(service, *, now=None, revalidate=None, **changes):
    settings = Settings(_env_file=None, hybrid_cursor_signing_key=KEY, **changes)
    return HybridPager(
        service,
        settings,
        now=now or (lambda: 1000.0),
        revalidate=revalidate or (lambda candidates: [item for item in candidates]),
    )


@pytest.fixture
def serve(tmp_path):
    created = []

    def remote(request):
        if request.url.path == "/search/repositories":
            return httpx.Response(
                200,
                json={"items": [REPO], "total_count": 1, "incomplete_results": False},
            )
        return httpx.Response(200, json=REPO)

    @contextmanager
    def run(runtime, **changes):
        key = Fernet.generate_key()
        changes.setdefault("token_encryption_key", key.decode())
        changes.setdefault("database_path", str(tmp_path / f"db-{len(created)}"))
        changes.setdefault("hybrid_cursor_signing_key", KEY)
        changes.setdefault("discovery_rate_limit", 100)
        created.append(changes["database_path"])
        settings = Settings(_env_file=None, **changes)
        app = create_app(
            settings,
            httpx.MockTransport(remote),
            sleep=lambda _: None,
            hybrid=runtime,
        )
        cipher = Fernet(settings.token_encryption_key.encode())
        with app.state.store.connect() as db:
            for uid in (1, 2):
                db.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?)",
                    (
                        uid,
                        f"user{uid}",
                        "",
                        cipher.encrypt(
                            json.dumps({"access_token": "upstream"}).encode()
                        ).decode(),
                    ),
                )
                db.execute(
                    "INSERT INTO sessions VALUES (?, ?, ?)",
                    (digest(f"session{uid}"), uid, time.time() + 1000),
                )
        try:
            with TestClient(app) as client:
                yield client, app
        finally:
            executor = getattr(runtime, "executor", None)
            if executor is not None:
                executor.close()

    return run


def test_search_requires_a_session(serve):
    service = FakeService(result([card(1, 101)]))
    with serve(FakeRuntime(pager(service))) as (client, _):
        assert (
            client.post("/v1/projects/search", json={"idea": IDEA}).status_code == 401
        )
        assert (
            client.post(
                "/v1/projects/search",
                headers={"Authorization": "Bearer nope"},
                json={"idea": IDEA},
            ).status_code
            == 401
        )
        assert service.calls == []


def test_search_shares_the_legacy_rate_limit(serve):
    service = FakeService(result([card(1, 101)]))
    with serve(FakeRuntime(pager(service)), discovery_rate_limit=1) as (client, _):
        first = client.post("/v1/projects/search", headers=HEADERS, json={"idea": IDEA})
        second = client.post(
            "/v1/projects/search", headers=HEADERS, json={"idea": IDEA}
        )
        assert first.status_code == 200
        assert second.status_code == 429
        assert second.headers["Retry-After"]
        assert len(service.calls) == 1


def strings(payload):
    if isinstance(payload, str):
        yield payload
    elif isinstance(payload, dict):
        for value in payload.values():
            yield from strings(value)
    elif isinstance(payload, list):
        for value in payload:
            yield from strings(value)


@pytest.mark.parametrize(
    "body, code",
    [
        ({"idea": "a"}, "INVALID_REQUEST"),
        ({"idea": "x" * 1001}, "INVALID_REQUEST"),
        ({"idea": "   "}, "INVALID_REQUEST"),
        ({"idea": IDEA, "page_size": 0}, "INVALID_REQUEST"),
        ({"idea": IDEA, "page_size": 51}, "INVALID_REQUEST"),
        ({"idea": IDEA, "cursor": "c" * 2049}, "INVALID_REQUEST"),
        ({"idea": IDEA, "mode": "archive"}, "INVALID_REQUEST"),
        ({"idea": IDEA, "filters": {"language": 'python" OR 1'}}, "UNSUPPORTED_FILTER"),
        ({"idea": IDEA, "filters": {"license": "GPL-3.0"}}, "UNSUPPORTED_FILTER"),
    ],
)
def test_invalid_requests_are_typed_and_do_not_echo_the_idea(serve, body, code):
    service = FakeService(result([card(1, 101)]))
    with serve(FakeRuntime(pager(service))) as (client, _):
        response = client.post("/v1/projects/search", headers=HEADERS, json=body)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == code
        assert response.json()["detail"]["retryable"] is False
        idea = body.get("idea", "").strip()
        if idea:
            assert idea not in set(strings(response.json()))
        assert service.calls == []


def test_supported_filters_are_canonicalized_for_both_sources(serve):
    service = FakeService(result([card(1, 101)]))
    with serve(FakeRuntime(pager(service))) as (client, _):
        response = client.post(
            "/v1/projects/search",
            headers=HEADERS,
            json={
                "idea": IDEA,
                "filters": {"language": "C++", "license": "Apache-2.0"},
            },
        )
        assert response.status_code == 200
        assert service.calls[0]["language"] == "C++"
        assert service.calls[0]["license"] == "apache-2.0"


def test_first_page_returns_semantic_cards_and_provenance(serve):
    both = card(
        1,
        101,
        sources=("github", "archive"),
        archive=ArchiveCard("Feature snippet", "Features", "revision-101", "chunk-101"),
    )
    archive_only = archive_card(2, 102, section="Usage", snippet="Usage snippet")
    service = FakeService(result([both, archive_only]))
    with serve(FakeRuntime(pager(service))) as (client, _):
        response = client.post(
            "/v1/projects/search", headers=HEADERS, json={"idea": IDEA}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] is None
        assert body["degraded"] is False
        assert body["ranking_version"] == "keyword-first-v1"
        assert body["generation"] == GENERATION
        assert body["next_cursor"] is None and body["has_more"] is False
        assert body["sources"]["github"]["status"] == "ok"
        assert body["sources"]["archive"]["status"] == "ok"
        assert body["archive_as_of"] is None

        first, second = body["items"]
        assert first["id"] == 101
        assert first["full_name"] == "owner/repo-101"
        assert first["owner"] == "owner"
        assert first["url"] == "https://github.com/owner/repo-101"
        assert first["stars"] == 101
        assert first["sources"] == ["github", "archive"]
        assert first["freshness"] == "live+archive"
        assert first["matched_section"] == "Features"
        assert first["snippet"] == "Feature snippet"
        assert first["license"] == "MIT"
        assert first["rank"] == 1
        assert 0 < first["rrf_score"] < 1

        assert second["sources"] == ["archive"]
        assert second["freshness"] == "archive"
        assert second["matched_section"] == "Usage"
        assert "similarity" not in json.dumps(body).lower()
        assert "percent" not in json.dumps(body).lower()


def test_license_conflict_serves_the_live_license_without_archive_text(serve):
    conflicted = card(
        1,
        101,
        sources=("github", "archive"),
        archive=None,
        license_value="MIT",
        license_conflict=True,
    )
    service = FakeService(result([conflicted]))
    with serve(FakeRuntime(pager(service))) as (client, _):
        response = client.post(
            "/v1/projects/search", headers=HEADERS, json={"idea": IDEA}
        )
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["license"] == "MIT"
        assert item["license_conflict"] is True
        assert item["snippet"] is None
        assert item["matched_section"] is None


def test_degraded_partial_hits_are_served_with_source_health(serve):
    cards = [archive_card(1, 102)]
    service = FakeService(
        result(
            cards,
            status="degraded",
            github=SourceHealth("failed", "timeout"),
        )
    )
    with serve(FakeRuntime(pager(service))) as (client, _):
        response = client.post(
            "/v1/projects/search", headers=HEADERS, json={"idea": IDEA}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["degraded"] is True
        assert body["sources"]["github"] == {
            "status": "failed",
            "incomplete": True,
            "reason": "timeout",
            "retry_after": None,
        }
        assert [item["id"] for item in body["items"]] == [102]


def test_partial_zero_is_a_typed_incomplete_error(serve):
    service = FakeService(
        result((), status="incomplete", github=SourceHealth("failed", "busy"))
    )
    with serve(FakeRuntime(pager(service))) as (client, _):
        response = client.post(
            "/v1/projects/search", headers=HEADERS, json={"idea": IDEA}
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "SEARCH_INCOMPLETE"
        assert response.json()["detail"]["retryable"] is True


def test_busy_is_a_typed_retryable_error(serve):
    service = FakeService(result((), status="busy"))
    with serve(FakeRuntime(pager(service))) as (client, _):
        response = client.post(
            "/v1/projects/search", headers=HEADERS, json={"idea": IDEA}
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "SEARCH_BUSY"
        assert response.json()["detail"]["retryable"] is True


def test_empty_search_is_a_successful_empty_page(serve):
    service = FakeService(result(()))
    with serve(FakeRuntime(pager(service))) as (client, _):
        response = client.post(
            "/v1/projects/search", headers=HEADERS, json={"idea": IDEA}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] is None
        assert body["degraded"] is False
        assert body["next_cursor"] is None


class FakeEligibility:
    def __init__(self, active):
        self.active = set(active)
        self.calls = []
        self.thread = None

    def check(self, archive_hits, *, live=None):
        self.thread = threading.get_ident()
        self.calls.append((archive_hits, live))
        kept_live = tuple(
            value
            for repo_id, value in (live or {}).items()
            if repo_id in self.active and value.get("private") is False
        )
        evidence = tuple(
            ArchiveEvidence(hit, metadata(hit["repo_id"]))
            for hit in archive_hits
            if hit["repo_id"] in self.active
        )
        return EligibilityResult(kept_live, evidence, ())


class FakeReader:
    def __init__(self, fresh):
        self.fresh = fresh
        self.calls = []

    def fetch_metadata(self, repo_id, full_name):
        self.calls.append((repo_id, full_name))
        return SimpleNamespace(
            response=SimpleNamespace(body=json.dumps(self.fresh[repo_id]))
        )


def test_later_pages_revalidate_fresh_visibility_off_the_event_loop(serve):
    cards = [
        card(1, 101),
        card(2, 102),
        card(3, 103),
        archive_card(4, 104),
    ]
    service = FakeService(result(cards))
    eligibility = FakeEligibility({104})
    reader = FakeReader({103: metadata(103, private=True)})
    revalidator = FusedRevalidator(eligibility, reader)
    with serve(
        FakeRuntime(pager(service, revalidate=revalidator)),
        hybrid_search_budget=2,
    ) as (client, _):
        first = client.post(
            "/v1/projects/search",
            headers=HEADERS,
            json={"idea": IDEA, "page_size": 2},
        )
        assert first.status_code == 200
        assert [item["id"] for item in first.json()["items"]] == [101, 102]
        cursor = first.json()["next_cursor"]
        assert cursor

        second = client.post(
            "/v1/projects/search",
            headers=HEADERS,
            json={"idea": IDEA, "page_size": 2, "cursor": cursor},
        )
        assert second.status_code == 200
        assert second.json()["generation"] == first.json()["generation"]
        assert [item["id"] for item in second.json()["items"]] == [104]

    hits, live = eligibility.calls[0]
    assert [hit["repo_id"] for hit in hits] == [104]
    assert hits[0]["revision"] == "revision-104"
    assert hits[0]["chunk_id"] == "chunk-104"
    assert reader.calls == [(103, "owner/repo-103")]
    assert live[103]["private"] is True
    assert eligibility.thread != service.loop_thread


def test_later_page_revalidation_is_bounded_by_the_request_deadline(serve):
    cards = [card(1, 101), card(2, 102)]

    class SlowEligibility(FakeEligibility):
        def check(self, archive_hits, *, live=None):
            time.sleep(0.5)
            return super().check(archive_hits, live=live)

    service = FakeService(result(cards))
    eligibility = SlowEligibility({101, 102})
    reader = FakeReader({102: metadata(102)})
    revalidator = FusedRevalidator(eligibility, reader)
    with serve(
        FakeRuntime(pager(service, revalidate=revalidator)),
        hybrid_search_budget=0.2,
    ) as (client, _):
        first = client.post(
            "/v1/projects/search",
            headers=HEADERS,
            json={"idea": IDEA, "page_size": 1},
        )
        assert first.status_code == 200
        second = client.post(
            "/v1/projects/search",
            headers=HEADERS,
            json={
                "idea": IDEA,
                "page_size": 1,
                "cursor": first.json()["next_cursor"],
            },
        )
        assert second.status_code == 503
        assert second.json()["detail"]["code"] == "SEARCH_TIMEOUT"
        assert second.json()["detail"]["retryable"] is True


def test_later_page_stops_at_the_deadline_and_serves_a_short_page(serve):
    cards = [card(rank, rank) for rank in range(1, 21)]

    class SlowReader:
        def __init__(self):
            self.calls = []

        def fetch_metadata(self, repo_id, full_name):
            self.calls.append(repo_id)
            time.sleep(1)
            return SimpleNamespace(
                response=SimpleNamespace(body=json.dumps(metadata(repo_id)))
            )

    service = FakeService(result(cards))
    revalidator = FusedRevalidator(FakeEligibility(set(range(1, 21))), SlowReader())
    runtime = FakeRuntime(
        pager(service, revalidate=revalidator), revalidator=revalidator
    )
    with serve(runtime, hybrid_search_budget=0.6) as (client, _):
        first = client.post(
            "/v1/projects/search",
            headers=HEADERS,
            json={"idea": IDEA, "page_size": 1},
        )
        assert first.status_code == 200
        started = time.monotonic()
        second = client.post(
            "/v1/projects/search",
            headers=HEADERS,
            json={
                "idea": IDEA,
                "page_size": 20,
                "cursor": first.json()["next_cursor"],
            },
        )
        elapsed = time.monotonic() - started
        assert second.status_code == 200
        assert len(second.json()["items"]) < 19
        assert elapsed < 0.6


def test_a_slow_first_build_returns_retryable_unavailable_within_the_bound(serve):
    class SlowRuntime:
        def __init__(self):
            self.calls = 0

        def target(self):
            self.calls += 1
            time.sleep(1)
            return SimpleNamespace(pager=None, generation=GENERATION, executor=None)

        def status(self):
            return {}

    runtime = SlowRuntime()
    with serve(runtime, hybrid_build_wait_seconds=0.1) as (client, _):
        started = time.monotonic()
        response = client.post(
            "/v1/projects/search", headers=HEADERS, json={"idea": IDEA}
        )
        elapsed = time.monotonic() - started
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "SEARCH_UNAVAILABLE"
        assert response.json()["detail"]["retryable"] is True
        assert elapsed < 0.4


def test_expired_cursor_restarts_the_search(serve):
    clock = [1000.0]
    service = FakeService(result([card(1, 101), card(2, 102)]))
    with serve(FakeRuntime(pager(service, now=lambda: clock[0]))) as (client, _):
        first = client.post(
            "/v1/projects/search",
            headers=HEADERS,
            json={"idea": IDEA, "page_size": 1},
        )
        clock[0] += 301
        second = client.post(
            "/v1/projects/search",
            headers=HEADERS,
            json={
                "idea": IDEA,
                "page_size": 1,
                "cursor": first.json()["next_cursor"],
            },
        )
        assert second.status_code == 410
        assert second.json()["detail"]["code"] == "CURSOR_EXPIRED"


def test_tampered_and_cross_account_cursors_are_rejected(serve):
    service = FakeService(result([card(1, 101), card(2, 102)]))
    with serve(FakeRuntime(pager(service))) as (client, _):
        first = client.post(
            "/v1/projects/search",
            headers=HEADERS,
            json={"idea": IDEA, "page_size": 1},
        )
        cursor = first.json()["next_cursor"]
        # Change a middle base64url character: the last character can carry
        # only padding bits, so editing it may decode to the same bytes.
        index = len(cursor) // 2
        while not cursor[index].isalnum():
            index += 1
        swap = "A" if cursor[index] != "A" else "B"
        tampered = cursor[:index] + swap + cursor[index + 1 :]
        rejected = client.post(
            "/v1/projects/search",
            headers=HEADERS,
            json={"idea": IDEA, "page_size": 1, "cursor": tampered},
        )
        assert rejected.status_code == 400
        assert rejected.json()["detail"]["code"] == "CURSOR_INVALID"

        foreign = client.post(
            "/v1/projects/search",
            headers=OTHER_HEADERS,
            json={"idea": IDEA, "page_size": 1, "cursor": cursor},
        )
        assert foreign.status_code == 400
        assert foreign.json()["detail"]["code"] == "CURSOR_INVALID"


def test_cursor_is_bound_to_the_resubmitted_idea_and_filters(serve):
    service = FakeService(result([card(1, 101), card(2, 102)]))
    with serve(FakeRuntime(pager(service))) as (client, _):
        first = client.post(
            "/v1/projects/search",
            headers=HEADERS,
            json={
                "idea": IDEA,
                "page_size": 1,
                "filters": {"language": "Python"},
            },
        )
        cursor = first.json()["next_cursor"]
        for body in (
            {"idea": IDEA + " please", "page_size": 1, "cursor": cursor},
            {
                "idea": IDEA,
                "page_size": 1,
                "cursor": cursor,
                "filters": {"language": "Rust"},
            },
        ):
            response = client.post("/v1/projects/search", headers=HEADERS, json=body)
            assert response.status_code == 400
            assert response.json()["detail"]["code"] == "CURSOR_INVALID"
        assert len(service.calls) == 1


def test_legacy_search_is_unchanged(serve):
    service = FakeService(result([card(1, 101)]))
    with serve(FakeRuntime(pager(service))) as (client, _):
        response = client.post(
            "/projects/search",
            headers=HEADERS,
            json={"idea": "python web framework"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "github_keywords"
        assert body["items"][0]["full_name"] == "octocat/compass"
        assert service.calls == []


def test_unconfigured_signing_key_keeps_the_app_bootable(serve):
    with serve(None, hybrid_cursor_signing_key="") as (client, _):
        assert client.get("/health").status_code == 200
        unavailable = client.post(
            "/v1/projects/search", headers=HEADERS, json={"idea": IDEA}
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["detail"]["code"] == "SEARCH_UNAVAILABLE"
        legacy = client.post(
            "/projects/search",
            headers=HEADERS,
            json={"idea": "python web framework"},
        )
        assert legacy.status_code == 200


def test_status_requires_auth_and_returns_the_sanitized_runtime_view(serve):
    service = FakeService(result(()))
    status = {
        "state": "uninitialized",
        "search_configured": False,
        "collection": "repo_chunks_e5small_v1",
        "profile": "gpu",
        "model_revision": None,
        "ranking_version": "keyword-first-v1",
        "generation": None,
        "coverage": "unknown",
        "archive_as_of": None,
        "repositories": None,
        "published_documents": None,
        "chunks": None,
        "latest_run": None,
    }
    with serve(FakeRuntime(pager(service), status=status)) as (client, _):
        assert client.get("/v1/archive/status").status_code == 401
        response = client.get("/v1/archive/status", headers=HEADERS)
        assert response.status_code == 200
        assert response.json() == status
        assert "path" not in response.text.lower()
        assert "token" not in response.text.lower()


def test_concurrent_cold_build_requests_return_starting_before_build_finishes(
    serve, monkeypatch
):
    runtime = HybridRuntime(Settings(_env_file=None), provider=None)
    entered, release = threading.Event(), threading.Event()
    target = FakeRuntime(pager(FakeService(result([card(1, 101)])))).target()
    target.archive_online = True
    builds = []

    def build():
        builds.append(1)
        entered.set()
        assert release.wait(10), "test must release the builder"
        return target

    monkeypatch.setattr(runtime, "_build", build)

    async def requests(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def search():
                return await client.post(
                    "/v1/projects/search", headers=HEADERS, json={"idea": IDEA}
                )

            builder = asyncio.create_task(search())
            waiters = []
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                waiters = [asyncio.create_task(search()) for _ in range(8)]
                done, pending = await asyncio.wait(waiters, timeout=2)
                assert not pending, (
                    "waiters must return before the 5-second build timeout"
                )
                for task in done:
                    response = task.result()
                    assert response.status_code == 503
                    assert response.json()["detail"] == {
                        "code": "SEARCH_UNAVAILABLE",
                        "message": "Search is starting. Try again shortly.",
                        "retryable": True,
                    }
                    assert "Retry-After" not in response.headers
                assert builds == [1]
                assert not builder.done()
            finally:
                release.set()
                await asyncio.gather(builder, *waiters)
            assert (await search()).status_code == 200
            assert builds == [1]

    try:
        with serve(runtime, hybrid_build_wait_seconds=5) as (_, app):
            asyncio.run(requests(app))
    finally:
        release.set()
        target.executor.close()
