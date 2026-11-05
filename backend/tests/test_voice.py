import asyncio
import io
import json
import logging
import time
import wave

import httpx
import pytest
from app.core.config import Settings
from app.core.store import digest
from app.main import create_app
from fastapi.testclient import TestClient


def clip(seconds=1, rate=16000):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x01\x00" * int(rate * seconds))
    return stream.getvalue()


@pytest.fixture
def voice(tmp_path):
    settings = Settings(
        _env_file=None, database_path=str(tmp_path / "auth.db"), deepgram_api_key=""
    )
    app = create_app(settings)

    def unexpected_network(request):
        pytest.fail("Test must explicitly configure a fake provider")

    app.state.voice_transport = httpx.MockTransport(unexpected_network)
    with app.state.store.connect() as db:
        db.execute("INSERT INTO users VALUES (1, 'tester', '', '')")
        db.execute(
            "INSERT INTO sessions VALUES (?, 1, ?)",
            (digest("voice-session"), time.time() + 1000),
        )
    with TestClient(app) as client:
        client.headers.update(
            {"Authorization": "Bearer voice-session", "Content-Type": "audio/wav"}
        )
        yield client, app, settings


def test_missing_key_is_typed_unavailable(voice):
    client, _, _ = voice
    response = client.post("/v1/voice/transcribe", content=clip())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "VOICE_UNAVAILABLE"
    assert response.json()["detail"]["retryable"] is True
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("token", ["", "Bearer invalid"])
def test_authentication_precedes_audio_processing(voice, token):
    client, _, _ = voice
    response = client.post(
        "/v1/voice/transcribe", content=b"invalid", headers={"Authorization": token}
    )
    assert response.status_code == 401


def provider_response(text="find python projects"):
    return {
        "results": {"channels": [{"alternatives": [{"transcript": text}]}]},
    }


def enable(voice, handler):
    # The route uses the real HTTP adapter; only the provider network is fake.
    from pydantic import SecretStr

    client, app, settings = voice
    settings.deepgram_api_key = SecretStr("fake-deepgram-secret")
    app.state.voice_transport = httpx.MockTransport(handler)
    return client, app, settings


def test_transcription_is_ephemeral_and_logs_only_measurements(voice, caplog):
    audio = clip()
    calls = []

    def remote(request):
        calls.append(request)
        return httpx.Response(200, json=provider_response("private spoken idea"))

    client, app, settings = enable(voice, remote)
    with caplog.at_level(logging.INFO, logger="reporadar.voice"):
        response = client.post("/v1/voice/transcribe", content=audio)
    assert response.status_code == 200
    assert response.json()["transcript"] == "private spoken idea"
    assert response.json()["duration_seconds"] == 1
    assert response.json()["latency_ms"] >= 0
    assert len(calls) == 1
    assert calls[0].url.host == "api.deepgram.com"
    assert calls[0].url.params["mip_opt_out"] == "true"
    assert calls[0].headers["authorization"] == "Token fake-deepgram-secret"
    assert calls[0].content == audio
    records = [
        json.loads(r.message) for r in caplog.records if r.name == "reporadar.voice"
    ]
    assert len(records) == 1
    assert set(records[0]) == {"bytes", "duration_seconds", "latency_ms"}
    assert "private spoken idea" not in caplog.text
    assert "fake-deepgram-secret" not in caplog.text
    assert "fake-deepgram-secret" not in repr(settings)
    with app.state.store.connect() as db:
        dump = "\n".join(db.iterdump())
    assert "private spoken idea" not in dump
    assert "fake-deepgram-secret" not in dump


@pytest.mark.parametrize(
    "audio,status,code",
    [
        (b"", 400, "VOICE_INVALID_AUDIO"),
        (b"not a wav", 400, "VOICE_INVALID_AUDIO"),
        (clip()[:-2], 400, "VOICE_INVALID_AUDIO"),
        (clip(30.001), 413, "VOICE_TOO_LONG"),
        (b"a" * (4 * 1024 * 1024 + 1), 413, "VOICE_TOO_LARGE"),
    ],
    ids=["empty", "invalid", "truncated", "too-long", "too-large"],
)
def test_invalid_audio_never_reaches_provider(voice, audio, status, code):
    calls = []
    client, _, _ = enable(voice, lambda r: calls.append(r))
    response = client.post("/v1/voice/transcribe", content=audio)
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert response.json()["detail"]["retryable"] is False
    assert not calls


def test_inclusive_duration_boundary_and_chunked_upload(voice):
    client, _, _ = enable(
        voice, lambda r: httpx.Response(200, json=provider_response())
    )
    audio = clip(30)
    response = client.post(
        "/v1/voice/transcribe", content=iter([audio[:100], audio[100:]])
    )
    assert response.status_code == 200
    assert response.json()["duration_seconds"] == 30


def test_wrong_media_type(voice):
    client, _, _ = enable(voice, lambda r: pytest.fail("must not call Deepgram"))
    response = client.post(
        "/v1/voice/transcribe",
        content=clip(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 415


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
def test_provider_errors_are_sanitized_retryable(voice, status, caplog):
    client, _, _ = enable(
        voice, lambda r: httpx.Response(status, text="private spoken idea secret")
    )
    response = client.post("/v1/voice/transcribe", content=clip())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "VOICE_UNAVAILABLE"
    assert response.json()["detail"]["retryable"] is True
    assert "private spoken idea" not in response.text + caplog.text


def test_provider_timeout_is_typed(voice):
    def remote(request):
        raise httpx.ReadTimeout("secret provider error")

    client, _, _ = enable(voice, remote)
    response = client.post("/v1/voice/transcribe", content=clip())
    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "VOICE_TIMEOUT"
    assert response.json()["detail"]["retryable"] is True
    assert "secret" not in response.text


@pytest.mark.parametrize(
    "body",
    [b"no json", b"{}", b"null", b"a" * 65537],
    ids=["non-json", "missing", "null", "oversized"],
)
def test_invalid_provider_response_is_bounded_and_sanitized(voice, body):
    client, _, _ = enable(voice, lambda r: httpx.Response(200, content=body))
    response = client.post("/v1/voice/transcribe", content=clip())
    assert response.status_code == 503
    assert response.json()["detail"]["retryable"] is True


@pytest.mark.parametrize("text", ["", "   ", "x" * 1001, 123])
def test_unusable_transcript_does_not_feed_search(voice, text):
    client, _, _ = enable(
        voice, lambda r: httpx.Response(200, json=provider_response(text))
    )
    response = client.post("/v1/voice/transcribe", content=clip())
    assert response.status_code in (422, 503)
    assert response.json()["detail"]["code"] in ("VOICE_NO_SPEECH", "VOICE_UNAVAILABLE")


def test_voice_uses_existing_request_throttle(voice):
    client, _, settings = voice
    settings.discovery_rate_limit = 1
    client.post("/v1/voice/transcribe", content=clip())
    response = client.post("/v1/voice/transcribe", content=clip())
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "VOICE_RATE_LIMITED"
    assert response.json()["detail"]["retryable"] is True


def test_deadline_and_cancellation_release_capacity(voice):
    _, app, settings = enable(voice, lambda r: None)
    settings.voice_max_concurrent = 1
    settings.voice_timeout = 0.05

    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()

        async def remote(request):
            entered.set()
            await release.wait()
            return httpx.Response(200, json=provider_response())

        app.state.voice_transport = httpx.MockTransport(remote)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={
                "Authorization": "Bearer voice-session",
                "Content-Type": "audio/wav",
            },
        ) as client:
            first = asyncio.create_task(
                client.post("/v1/voice/transcribe", content=clip())
            )
            await entered.wait()
            busy = await client.post("/v1/voice/transcribe", content=clip())
            assert busy.status_code == 503
            assert busy.json()["detail"]["code"] == "VOICE_BUSY"
            expired = await first
            assert expired.status_code == 504
            assert expired.json()["detail"]["code"] == "VOICE_TIMEOUT"
            settings.voice_timeout = 5
            entered.clear()
            pending = asyncio.create_task(
                client.post("/v1/voice/transcribe", content=clip())
            )
            await entered.wait()
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            release.set()
            resumed = await client.post("/v1/voice/transcribe", content=clip())
            assert resumed.status_code == 200

    asyncio.run(scenario())


def test_unknown_length_body_cannot_bypass_byte_limit(voice):
    client, _, settings = enable(voice, lambda r: pytest.fail("must not send audio"))
    settings.voice_max_bytes = 100
    response = client.post("/v1/voice/transcribe", content=iter([b"a" * 70, b"b" * 70]))
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "VOICE_TOO_LARGE"


def test_extra_audio_after_wav_is_not_forwarded(voice):
    seen = []

    def remote(request):
        seen.append(request.content)
        return httpx.Response(200, json=provider_response())

    client, _, _ = enable(voice, remote)
    response = client.post("/v1/voice/transcribe", content=clip() + clip(30))
    assert response.status_code == 200
    assert seen == [clip()]


@pytest.mark.parametrize("status", [301, 302, 307])
def test_provider_redirect_is_not_followed(voice, status):
    calls = []

    def remote(request):
        calls.append(request.url.host)
        return httpx.Response(status, headers={"Location": "https://other.example"})

    client, _, _ = enable(voice, remote)
    response = client.post("/v1/voice/transcribe", content=clip())
    assert response.status_code == 503
    assert calls == ["api.deepgram.com"]
