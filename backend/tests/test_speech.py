import asyncio
import json
import logging
import time

import httpx
import pytest
from app.core.store import digest
from test_summary_api import HEADERS, SUMMARY_PATH, FakeLlm, events, search, wait_until
from test_summary_api import serve as serve

TEXT = "Try owner/repo-1 for community tools."
PATH = "/v1/voice/speech/"


def issue(client, app):
    assert wait_until(lambda: app.state.llm_available)
    assert search(client).status_code == 200
    result = client.post(
        SUMMARY_PATH, headers=HEADERS, json={"full_names": ["owner/repo-1"]}
    )
    done = events(result.text)[-1][1]
    assert done["grounded"] is True
    assert isinstance(done.get("summary_id"), str)
    assert len(done["summary_id"]) >= 22
    return done["summary_id"]


class Audio(httpx.AsyncByteStream):
    def __init__(self, chunks=(b"mp3-one", b"mp3-two"), stall=False):
        self.chunks, self.stall, self.closed = chunks, stall, False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
        if self.stall:
            await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


def test_validated_id_streams_exact_text_without_sensitive_logs(serve, caplog):
    audio, calls = Audio(), []

    def provider(request):
        calls.append(request)
        return httpx.Response(200, headers={"content-type": "audio/mpeg"}, stream=audio)

    with serve(
        llm=FakeLlm(chunks=(TEXT,)),
        llm_active_profile="ollama",
        deepgram_api_key="fake-secret",
    ) as (client, app):
        app.state.speech_transport = httpx.MockTransport(provider)
        with caplog.at_level(logging.INFO, logger="reporadar"):
            identity = issue(client, app)
            response = client.get(PATH + identity, headers=HEADERS)
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"
        assert response.headers["cache-control"] == "no-store"
        assert response.content == b"mp3-onemp3-two"
    assert audio.closed
    assert len(calls) == 1
    request = calls[0]
    assert json.loads(request.content) == {"text": TEXT}
    assert request.url.path == "/v1/speak"
    assert request.url.params["encoding"] == "mp3"
    assert request.url.params["model"] == "aura-2-thalia-en"
    assert request.headers["authorization"] == "Token fake-secret"
    logs = " ".join(
        record.message
        for record in caplog.records
        if record.name.startswith("reporadar")
    )
    for secret in (TEXT, identity, "fake-secret", "mp3-one"):
        assert secret not in logs
    assert '"bytes"' in logs


@pytest.mark.parametrize("chunks", [("Use unknown/evil.",), ("",)])
def test_no_id_for_rejected_summary(serve, chunks):
    with serve(llm=FakeLlm(chunks=chunks), llm_active_profile="ollama") as (
        client,
        app,
    ):
        assert wait_until(lambda: app.state.llm_available)
        search(client)
        done = events(
            client.post(
                SUMMARY_PATH, headers=HEADERS, json={"full_names": ["owner/repo-1"]}
            ).text
        )[-1][1]
        assert done["grounded"] is False
        assert "summary_id" not in done


@pytest.mark.parametrize("kind", ["unknown", "expired", "other account"])
def test_ids_are_account_bound_and_expire(serve, kind):
    with serve(llm=FakeLlm(chunks=(TEXT,)), llm_active_profile="ollama") as (
        client,
        app,
    ):
        identity = issue(client, app)
        headers = HEADERS
        if kind == "unknown":
            identity = "unknown"
        elif kind == "expired":
            app.state.speech_summaries._now = lambda: time.monotonic() + 301
        else:
            with app.state.store.connect() as db:
                db.execute("INSERT INTO users VALUES (2, 'other', '', '')")
                db.execute(
                    "INSERT INTO sessions VALUES (?, 2, ?)",
                    (digest("other"), time.time() + 1000),
                )
            headers = {"Authorization": "Bearer other"}
        response = client.get(PATH + identity, headers=headers)
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "speech_not_found"


@pytest.mark.parametrize(
    "kind", ["missing key", "provider error", "empty audio", "first byte deadline"]
)
def test_preflight_failure_is_typed_503(serve, kind):
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(
            500 if kind == "provider error" else 200,
            headers={"content-type": "audio/mpeg"},
            stream=Audio((), stall=kind == "first byte deadline"),
        )

    with serve(
        llm=FakeLlm(chunks=(TEXT,)),
        llm_active_profile="ollama",
        deepgram_api_key="" if kind == "missing key" else "fake",
    ) as (client, app):
        app.state.settings.speech_deadline = 0.05
        app.state.speech_transport = httpx.MockTransport(provider)
        response = client.get(PATH + issue(client, app), headers=HEADERS)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "speech_unavailable"
        assert response.json()["detail"]["retryable"] is True
    assert len(calls) == (0 if kind == "missing key" else 1)


@pytest.mark.parametrize("kind", ["bytes", "deadline"])
def test_stream_bounds_close_provider(serve, kind):
    audio = Audio((b"123", b"456")) if kind == "bytes" else Audio((b"123",), stall=True)
    with serve(
        llm=FakeLlm(chunks=(TEXT,)),
        llm_active_profile="ollama",
        deepgram_api_key="fake",
    ) as (client, app):
        app.state.settings.speech_deadline = 0.05
        app.state.settings.speech_max_bytes = 4
        app.state.speech_transport = httpx.MockTransport(
            lambda _: httpx.Response(
                200, headers={"content-type": "audio/mpeg"}, stream=audio
            )
        )
        response = client.get(PATH + issue(client, app), headers=HEADERS)
        assert response.status_code == 200
        assert response.content == b"123"
        assert audio.closed


def test_concurrency_is_reserved_before_provider_call(serve):
    with serve(
        llm=FakeLlm(chunks=(TEXT,)),
        llm_active_profile="ollama",
        deepgram_api_key="fake",
    ) as (client, app):
        identity = issue(client, app)

        async def run():
            entered, release = asyncio.Event(), asyncio.Event()
            calls = []

            async def provider(request):
                calls.append(request)
                entered.set()
                await release.wait()
                return httpx.Response(
                    200, headers={"content-type": "audio/mpeg"}, content=b"audio"
                )

            app.state.speech_transport = httpx.MockTransport(provider)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as remote:
                first = asyncio.create_task(
                    remote.get(PATH + identity, headers=HEADERS)
                )
                await asyncio.wait_for(entered.wait(), 2)
                second = await remote.get(PATH + identity, headers=HEADERS)
                release.set()
                assert (await first).status_code == 200
                assert second.status_code == 503
                assert second.json()["detail"]["code"] == "speech_busy"
                assert second.json()["detail"]["retryable"] is True
                assert len(calls) == 1

        asyncio.run(run())


def test_speech_session_and_shared_throttle(serve):
    with serve(discovery_rate_limit=1) as (client, _):
        assert client.get(PATH + "unknown").status_code == 401
        response = client.get(PATH + "unknown", headers=HEADERS)
        assert response.status_code == 429
        assert response.json()["detail"]["code"] == "VOICE_RATE_LIMITED"


def test_summary_cache_bounds_lru_and_exact_expiry():
    from app.api.summary import ValidatedSummaries

    now = [0.0]
    cache = ValidatedSummaries(3, 2, now=lambda: now[0])
    first = cache.issue(1, "first")
    second = cache.issue(1, "second")
    third = cache.issue(1, "third")
    assert cache.resolve(1, first) is None
    other = cache.issue(2, "other")
    assert cache.resolve(1, second) == "second"
    cache.issue(3, "new")
    assert cache.resolve(1, third) is None
    assert cache.resolve(2, other) == "other"
    now[0] = 299.999
    assert cache.resolve(1, second) == "second"
    now[0] = 300
    assert cache.resolve(1, second) is None
    assert not cache._entries


@pytest.mark.parametrize(
    "changes",
    [
        {"speech_deadline": 0},
        {"speech_deadline": 121},
        {"speech_max_bytes": 0},
        {"speech_max_bytes": 16777217},
        {"speech_max_concurrent": 0},
        {"speech_max_concurrent": 5},
        {"deepgram_tts_model": ""},
        {"deepgram_tts_model": "x" * 101},
    ],
)
def test_speech_settings_are_bounded(changes):
    from app.core.config import Settings
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **changes)


def test_cancelled_stream_closes_provider_and_releases_concurrency(serve):
    with serve(
        llm=FakeLlm(chunks=(TEXT,)),
        llm_active_profile="ollama",
        deepgram_api_key="fake",
    ) as (client, app):
        identity = issue(client, app)

        async def run():
            entered = asyncio.Event()

            class HeldAudio(Audio):
                async def __aiter__(self):
                    yield b"first"
                    entered.set()
                    await asyncio.Event().wait()

            audio = HeldAudio()
            app.state.speech_transport = httpx.MockTransport(
                lambda _: httpx.Response(
                    200, headers={"content-type": "audio/mpeg"}, stream=audio
                )
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as remote:
                first = asyncio.create_task(
                    remote.get(PATH + identity, headers=HEADERS)
                )
                await asyncio.wait_for(entered.wait(), 2)
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
                assert audio.closed
                app.state.speech_transport = httpx.MockTransport(
                    lambda _: httpx.Response(
                        200, headers={"content-type": "audio/mpeg"}, content=b"new"
                    )
                )
                response = await remote.get(PATH + identity, headers=HEADERS)
                assert response.status_code == 200

        asyncio.run(run())
