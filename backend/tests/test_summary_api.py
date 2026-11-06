"""V2a: authenticated, grounded summary of the current first page."""

import asyncio
import json
import logging
import time
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
from app.api.summary import SummaryPages
from app.core.config import Settings
from app.core.store import digest
from app.integrations.llm import LlmClient, LlmProviderError
from app.main import create_app
from app.services.hybrid_search import BoundedExecutor
from app.services.rank_fusion import FusedCandidate, SourceHealth
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

KEY = "k" * 40
GENERATION = "a" * 40 + ":rrf-v1"
HEADERS = {"Authorization": "Bearer session1"}
IDEA = "an offline first app for sharing community tools"
SUMMARY_PATH = "/v1/projects/search/summary"


def metadata(repo_id, **changes):
    data = {
        "id": repo_id,
        "name": f"repo-{repo_id}",
        "full_name": f"owner/repo-{repo_id}",
        "owner": {"login": "owner", "avatar_url": ""},
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


def card(rank, repo_id, **changes):
    return FusedCandidate(
        rank=rank,
        repo_id=repo_id,
        metadata=metadata(repo_id, **changes),
        sources=("github",),
        rrf_score=1 / (60 + rank),
        license="MIT",
        license_conflict=False,
        archive=None,
    )


class FakePager:
    def __init__(self, cards):
        self.cards = tuple(cards)

    async def first_page(self, token, idea, **kwargs):
        return SimpleNamespace(
            items=self.cards,
            next_cursor=None,
            has_more=False,
            status="ok",
            github=SourceHealth("ok"),
            archive=SourceHealth("ok"),
        )


class FakeRuntime:
    def __init__(self, cards):
        self.pager = FakePager(cards)
        self.generation = GENERATION
        self.executor = BoundedExecutor(2, 4)
        self.revalidator = None

    def target(self):
        return SimpleNamespace(
            pager=self.pager,
            generation=self.generation,
            executor=self.executor,
            revalidator=self.revalidator,
        )

    def status(self):
        return {
            "state": "uninitialized",
            "coverage": "unknown",
            "archive_as_of": None,
        }


class FakeLlm:
    """Fake provider that still uses the real client log line."""

    def __init__(self, chunks=("Try owner/repo-1.",), *, error=None, delay=0):
        self.resolved = SimpleNamespace(
            name="fake", model="fake-model", provider="ollama"
        )
        self.chunks = list(chunks)
        self.error = error
        self.delay = delay
        self.messages = []
        self.complete_error = None
        self.calls = 0
        self.entered = None
        self.release = None

    @property
    def profile_name(self):
        return self.resolved.name

    @property
    def model(self):
        return self.resolved.model

    async def complete(self, messages, **kwargs):
        if self.complete_error is not None:
            raise self.complete_error
        return "ok"

    async def stream(self, messages, **kwargs):
        started = time.monotonic()
        self.messages.append(messages)
        self.calls += 1
        try:
            if self.error is not None:
                raise self.error
            if self.entered is not None:
                self.entered.set()
            if self.release is not None:
                await self.release.wait()
            if self.delay:
                await asyncio.sleep(self.delay)
            for chunk in self.chunks:
                yield chunk
        finally:
            LlmClient._log(self, started, messages, stream=True)


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not predicate():
        time.sleep(0.01)
    return bool(predicate())


def events(body):
    parsed = []
    for block in body.strip().split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name is not None:
            parsed.append((name, data))
    return parsed


def summary_text(body):
    return "".join(data["text"] for name, data in events(body) if name == "summary")


@pytest.fixture
def serve(tmp_path):
    created = []

    @contextmanager
    def run(cards=None, *, llm=None, **changes):
        key = Fernet.generate_key()
        changes.setdefault("token_encryption_key", key.decode())
        changes.setdefault("database_path", str(tmp_path / f"db-{len(created)}"))
        changes.setdefault("hybrid_cursor_signing_key", KEY)
        changes.setdefault("discovery_rate_limit", 100)
        created.append(changes["database_path"])
        settings = Settings(_env_file=None, **changes)
        runtime = FakeRuntime(cards or [card(1, 1), card(2, 2)])
        app = create_app(
            settings,
            httpx.MockTransport(lambda request: httpx.Response(200, json={})),
            sleep=lambda _: None,
            hybrid=runtime,
            llm=llm,
        )
        cipher = Fernet(settings.token_encryption_key.encode())
        with app.state.store.connect() as db:
            db.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?)",
                (
                    1,
                    "user1",
                    "",
                    cipher.encrypt(json.dumps({"access_token": "t"}).encode()).decode(),
                ),
            )
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                (digest("session1"), 1, time.time() + 1000),
            )
        try:
            with TestClient(app) as client:
                yield client, app
        finally:
            runtime.executor.close()

    return run


def search(client):
    return client.post("/v1/projects/search", headers=HEADERS, json={"idea": IDEA})


def test_summary_requires_a_session(serve):
    fake = FakeLlm()
    with serve(llm=fake, llm_active_profile="ollama") as (client, _):
        assert (
            client.post(SUMMARY_PATH, json={"full_names": ["owner/repo-1"]}).status_code
            == 401
        )
        assert (
            client.post(
                SUMMARY_PATH,
                headers={"Authorization": "Bearer nope"},
                json={"full_names": ["owner/repo-1"]},
            ).status_code
            == 401
        )
    assert fake.messages == []


def test_summary_rejects_repository_text_from_the_client(serve):
    fake = FakeLlm()
    with serve(llm=fake, llm_active_profile="ollama") as (client, _):
        response = client.post(
            SUMMARY_PATH,
            headers=HEADERS,
            json={
                "full_names": ["owner/repo-1"],
                "description": "forged repository text",
            },
        )
    assert response.status_code == 422
    assert fake.messages == []


def test_summary_rejects_more_than_ten_identities(serve):
    fake = FakeLlm()
    with serve(llm=fake, llm_active_profile="ollama") as (client, _):
        response = client.post(
            SUMMARY_PATH,
            headers=HEADERS,
            json={"full_names": [f"owner/repo-{index}" for index in range(11)]},
        )
    assert response.status_code == 422
    assert fake.messages == []


def test_summary_ignores_forged_full_names(serve):
    fake = FakeLlm(chunks=("Use owner/repo-1.",))
    with serve(llm=fake, llm_active_profile="ollama") as (client, app):
        assert wait_until(lambda: app.state.llm_available is True)
        assert search(client).status_code == 200
        response = client.post(
            SUMMARY_PATH,
            headers=HEADERS,
            json={
                "full_names": ["owner/repo-1", "evil/backdoor", "owner/repo-2"],
            },
        )
    assert response.status_code == 200
    prompt = json.dumps(fake.messages[-1])
    assert "owner/repo-1" in prompt
    assert "owner/repo-2" in prompt
    assert "evil/backdoor" not in prompt
    assert "forged" not in prompt
    assert events(response.text)[-1] == ("done", {"grounded": True, "results": 2})


def test_summary_rejects_an_ungrounded_reply(serve):
    fake = FakeLlm(chunks=("Try evil/backdoor instead.",))
    with serve(llm=fake, llm_active_profile="ollama") as (client, app):
        assert wait_until(lambda: app.state.llm_available is True)
        assert search(client).status_code == 200
        response = client.post(
            SUMMARY_PATH, headers=HEADERS, json={"full_names": ["owner/repo-1"]}
        )
    assert response.status_code == 200
    assert summary_text(response.text) == ""
    assert events(response.text) == [
        ("done", {"grounded": False, "reason": "ungrounded"})
    ]


def test_summary_deadline_returns_no_summary(serve):
    fake = FakeLlm(chunks=("late",), delay=5)
    with serve(llm=fake, llm_active_profile="ollama", summary_deadline=0.1) as (
        client,
        app,
    ):
        assert wait_until(lambda: app.state.llm_available is True)
        assert search(client).status_code == 200
        started = time.monotonic()
        response = client.post(
            SUMMARY_PATH, headers=HEADERS, json={"full_names": ["owner/repo-1"]}
        )
        elapsed = time.monotonic() - started
    assert response.status_code == 200
    assert elapsed < 2
    assert events(response.text) == [("done", {"grounded": False, "reason": "timeout"})]


def test_provider_down_returns_no_summary_while_search_works(serve):
    fake = FakeLlm()
    fake.complete_error = LlmProviderError("down", status=503, retryable=True)
    with serve(llm=fake, llm_active_profile="ollama") as (client, app):
        assert wait_until(
            lambda: app.state.llm_probe is not None and app.state.llm_probe.done()
        )
        assert app.state.llm_available is False
        assert search(client).status_code == 200
        response = client.post(
            SUMMARY_PATH, headers=HEADERS, json={"full_names": ["owner/repo-1"]}
        )
    assert response.status_code == 200
    assert events(response.text) == [
        ("done", {"grounded": False, "reason": "unavailable"})
    ]


def test_stream_failure_returns_no_summary(serve):
    fake = FakeLlm(error=LlmProviderError("down", status=503, retryable=True))
    with serve(llm=fake, llm_active_profile="ollama") as (client, app):
        assert wait_until(lambda: app.state.llm_available is True)
        assert search(client).status_code == 200
        response = client.post(
            SUMMARY_PATH, headers=HEADERS, json={"full_names": ["owner/repo-1"]}
        )
    assert response.status_code == 200
    assert events(response.text) == [
        ("done", {"grounded": False, "reason": "unavailable"})
    ]


def test_no_active_profile_returns_no_summary(serve):
    with serve(llm=None) as (client, _):
        assert search(client).status_code == 200
        response = client.post(
            SUMMARY_PATH, headers=HEADERS, json={"full_names": ["owner/repo-1"]}
        )
    assert response.status_code == 200
    assert events(response.text) == [
        ("done", {"grounded": False, "reason": "unavailable"})
    ]


def test_summary_requires_an_active_profile_even_with_a_client(serve):
    fake = FakeLlm()
    with serve(llm=fake) as (client, _):
        assert search(client).status_code == 200
        response = client.post(
            SUMMARY_PATH, headers=HEADERS, json={"full_names": ["owner/repo-1"]}
        )
    assert response.status_code == 200
    assert events(response.text) == [
        ("done", {"grounded": False, "reason": "unavailable"})
    ]
    assert fake.messages == []


def test_summary_before_any_search_returns_no_summary(serve):
    fake = FakeLlm()
    with serve(llm=fake, llm_active_profile="ollama") as (client, app):
        assert wait_until(lambda: app.state.llm_available is True)
        response = client.post(
            SUMMARY_PATH, headers=HEADERS, json={"full_names": ["owner/repo-1"]}
        )
    assert response.status_code == 200
    assert events(response.text) == [
        ("done", {"grounded": False, "reason": "no_results"})
    ]
    assert fake.messages == []


def test_summary_logs_counts_only(serve, caplog):
    caplog.set_level(logging.INFO)
    text = "A grounded summary about owner/repo-1."
    fake = FakeLlm(chunks=(text,))
    with serve(llm=fake, llm_active_profile="ollama") as (client, app):
        assert wait_until(lambda: app.state.llm_available is True)
        assert search(client).status_code == 200
        response = client.post(
            SUMMARY_PATH, headers=HEADERS, json={"full_names": ["owner/repo-1"]}
        )
        assert response.status_code == 200
    assert IDEA not in caplog.text
    assert text not in caplog.text
    assert "summary_chars" in caplog.text
    assert "duration_ms" in caplog.text


def test_remember_moves_a_repeated_account_to_the_newest_position():
    pages = SummaryPages(ttl=60, max_accounts=2, now=lambda: 0.0)

    def item(full_name):
        return {
            "name": full_name.split("/")[1],
            "full_name": full_name,
            "description": "",
            "license": None,
        }

    pages.remember("A", [item("a/one")])
    pages.remember("B", [item("b/two")])
    pages.remember("A", [item("a/three")])
    pages.remember("C", [item("c/four")])

    assert [entry["full_name"] for entry in pages.resolve("A", ["a/three"])] == [
        "a/three"
    ]
    assert pages.resolve("B", ["b/two"]) == []
    assert [entry["full_name"] for entry in pages.resolve("C", ["c/four"])] == [
        "c/four"
    ]


def test_busy_summary_returns_immediately_without_a_second_provider_call(serve):
    fake = FakeLlm(chunks=("Use owner/repo-1.",))
    with serve(llm=fake, llm_active_profile="ollama") as (client, app):
        assert wait_until(lambda: app.state.llm_available is True)
        assert search(client).status_code == 200

        async def scenario():
            fake.entered = asyncio.Event()
            fake.release = asyncio.Event()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                headers=HEADERS,
            ) as async_client:
                first = asyncio.create_task(
                    async_client.post(
                        SUMMARY_PATH, json={"full_names": ["owner/repo-1"]}
                    )
                )
                await asyncio.wait_for(fake.entered.wait(), timeout=2)
                try:
                    busy = await asyncio.wait_for(
                        async_client.post(
                            SUMMARY_PATH, json={"full_names": ["owner/repo-1"]}
                        ),
                        timeout=1,
                    )
                except TimeoutError:
                    fake.release.set()
                    pytest.fail("the second summary waited instead of returning busy")
                assert events(busy.text) == [
                    ("done", {"grounded": False, "reason": "busy"})
                ]
                assert fake.calls == 1
                fake.release.set()
                done = await first
            assert fake.calls == 1
            assert events(done.text)[-1] == ("done", {"grounded": True, "results": 1})

        asyncio.run(scenario())


def test_cancelled_summary_releases_the_slot(serve):
    fake = FakeLlm(chunks=("Use owner/repo-1.",))
    with serve(llm=fake, llm_active_profile="ollama") as (client, app):
        assert wait_until(lambda: app.state.llm_available is True)
        assert search(client).status_code == 200

        async def scenario():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                headers=HEADERS,
            ) as async_client:
                fake.entered = asyncio.Event()
                fake.release = asyncio.Event()
                cancelled = asyncio.create_task(
                    async_client.post(
                        SUMMARY_PATH, json={"full_names": ["owner/repo-1"]}
                    )
                )
                await asyncio.wait_for(fake.entered.wait(), timeout=2)
                cancelled.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await cancelled

                fake.entered = asyncio.Event()
                fake.release = asyncio.Event()
                second = asyncio.create_task(
                    async_client.post(
                        SUMMARY_PATH, json={"full_names": ["owner/repo-1"]}
                    )
                )
                await asyncio.wait_for(fake.entered.wait(), timeout=2)
                try:
                    busy = await asyncio.wait_for(
                        async_client.post(
                            SUMMARY_PATH, json={"full_names": ["owner/repo-1"]}
                        ),
                        timeout=1,
                    )
                except TimeoutError:
                    fake.release.set()
                    pytest.fail("cancellation did not release the summary slot")
                assert events(busy.text) == [
                    ("done", {"grounded": False, "reason": "busy"})
                ]
                fake.release.set()
                done = await second
            assert events(done.text)[-1] == ("done", {"grounded": True, "results": 1})
            assert fake.calls == 2

        asyncio.run(scenario())
