"""Authenticated, memory-only PCM WAV upload with a verified duration limit."""

import asyncio
import io
import json
import logging
import time
import wave

import httpx
from fastapi import APIRouter, HTTPException, Request
from starlette.requests import ClientDisconnect

from app.integrations.deepgram import VoiceUnavailable, transcribe

logger = logging.getLogger("reporadar.voice")


def error(status, code, message, *, retryable=False):
    return HTTPException(
        status, {"code": code, "message": message, "retryable": retryable}
    )


def pcm_clip(body, settings):
    try:
        with wave.open(io.BytesIO(body), "rb") as audio:
            channels, width, rate, frames, compression, _ = audio.getparams()
            if (
                channels not in (1, 2)
                or width != 2
                or not 8000 <= rate <= 48000
                or compression != "NONE"
                or frames == 0
            ):
                raise ValueError
            duration = frames / rate
            if duration > settings.voice_max_seconds:
                raise error(413, "VOICE_TOO_LONG", "Record at most 30 seconds.")
            pcm = audio.readframes(frames)
            if len(pcm) != frames * channels * width:
                raise ValueError
        # Send only verified frames, excluding arbitrary metadata/extra data chunks.
        output = io.BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setnchannels(channels)
            audio.setsampwidth(width)
            audio.setframerate(rate)
            audio.writeframes(pcm)
        return output.getvalue(), duration
    except (wave.Error, EOFError, ValueError, OSError):
        raise error(
            400, "VOICE_INVALID_AUDIO", "Send a valid PCM WAV recording."
        ) from None


def voice_router(settings, current):
    router = APIRouter()
    in_flight = 0

    @router.post("/v1/voice/transcribe")
    async def upload(request: Request):
        nonlocal in_flight
        try:
            current(request)
        except HTTPException:
            raise error(401, "VOICE_AUTH_REQUIRED", "Sign in to use voice.") from None
        if not settings.deepgram_api_key.get_secret_value().strip():
            raise error(
                503,
                "VOICE_UNAVAILABLE",
                "Voice is unavailable. Type your idea.",
                retryable=True,
            )
        if (
            request.headers.get("content-type", "").split(";", 1)[0].lower()
            != "audio/wav"
        ):
            raise error(415, "VOICE_UNSUPPORTED_AUDIO", "Send PCM WAV audio.")
        if in_flight >= settings.voice_max_concurrent:
            raise error(503, "VOICE_BUSY", "Voice is busy. Try again.", retryable=True)
        in_flight += 1
        start = time.monotonic()
        body = bytearray()
        duration = 0
        try:
            # Covers slow uploads and total provider time, not just socket inactivity.
            async with asyncio.timeout(settings.voice_timeout):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > settings.voice_max_bytes:
                        raise error(413, "VOICE_TOO_LARGE", "Recording is too large.")
                    body.extend(chunk)
                audio, duration = pcm_clip(body, settings)
                text = await transcribe(
                    audio,
                    settings,
                    transport=getattr(request.app.state, "voice_transport", None),
                )
                if len(text) < 2:
                    raise error(
                        422,
                        "VOICE_NO_SPEECH",
                        "Try again or type your idea.",
                        retryable=True,
                    )
                return {
                    "transcript": text,
                    "duration_seconds": duration,
                    "latency_ms": round((time.monotonic() - start) * 1000, 2),
                }
        except (TimeoutError, httpx.TimeoutException):
            raise error(
                504, "VOICE_TIMEOUT", "Voice timed out. Try again.", retryable=True
            ) from None
        except (VoiceUnavailable, httpx.HTTPError):
            raise error(
                503,
                "VOICE_UNAVAILABLE",
                "Voice is unavailable. Type your idea.",
                retryable=True,
            ) from None
        except ClientDisconnect:
            raise error(
                400, "VOICE_UPLOAD_INTERRUPTED", "Recording upload was interrupted."
            ) from None
        finally:
            in_flight -= 1
            logger.info(
                json.dumps(
                    {
                        "bytes": len(body),
                        "duration_seconds": duration,
                        "latency_ms": round((time.monotonic() - start) * 1000, 2),
                    }
                )
            )

    return router
