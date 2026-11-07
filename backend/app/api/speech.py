"""Speak only account-bound validated summaries; no content in logs."""

import asyncio
import json
import logging
import time

import httpx
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from app.api.voice import error
from app.integrations.deepgram import VoiceUnavailable, speech_audio

logger = logging.getLogger("reporadar.speech")


class SpeechResponse(StreamingResponse):
    """Close the provider and release the slot even on client cancellation.

    Starlette iterates the body but does not close it, so the wrapper owns
    cleanup and the byte count used by the log line.
    """

    def __init__(self, stream, first, deadline, finish):
        super().__init__(stream, media_type="audio/mpeg")
        self.stream, self.first, self.deadline, self.finish = (
            stream,
            first,
            deadline,
            finish,
        )
        self.size = 0

    async def stream_response(self, send):
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self.raw_headers,
            }
        )
        try:
            async with asyncio.timeout_at(self.deadline):
                await send(
                    {
                        "type": "http.response.body",
                        "body": self.first,
                        "more_body": True,
                    }
                )
                self.size += len(self.first)
                async for chunk in self.stream:
                    await send(
                        {"type": "http.response.body", "body": chunk, "more_body": True}
                    )
                    self.size += len(chunk)
        except (TimeoutError, VoiceUnavailable, httpx.HTTPError):
            # Headers have been sent: close partial audio, never append JSON or retry.
            pass
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                await self.stream.aclose()
            finally:
                self.finish(self.size)


def speech_router(settings, current, summaries):
    router = APIRouter()
    in_flight = 0

    @router.get("/v1/voice/speech/{summary_id}")
    async def speech(summary_id: str, request: Request):
        nonlocal in_flight
        try:
            account = current(request)["github_id"]
        except HTTPException:
            raise error(401, "VOICE_AUTH_REQUIRED", "Sign in to use voice.") from None
        text = summaries.resolve(account, summary_id)
        if text is None:
            raise error(404, "speech_not_found", "Summary is unavailable.")
        if not settings.deepgram_api_key.get_secret_value().strip():
            raise error(
                503, "speech_unavailable", "Speech is unavailable.", retryable=True
            )
        if in_flight >= settings.speech_max_concurrent:
            raise error(
                503, "speech_busy", "Speech is busy. Try again.", retryable=True
            )
        in_flight += 1
        started = time.monotonic()
        deadline = asyncio.get_running_loop().time() + settings.speech_deadline
        stream = speech_audio(
            text,
            settings,
            transport=getattr(request.app.state, "speech_transport", None),
        )

        def finish(size):
            nonlocal in_flight
            in_flight -= 1
            logger.info(
                json.dumps(
                    {
                        "bytes": size,
                        "latency_ms": round((time.monotonic() - started) * 1000, 2),
                    }
                )
            )

        try:
            async with asyncio.timeout_at(deadline):
                first = await anext(stream)
        except BaseException as failure:
            try:
                await stream.aclose()
            finally:
                finish(0)
            if isinstance(
                failure,
                (StopAsyncIteration, TimeoutError, VoiceUnavailable, httpx.HTTPError),
            ):
                raise error(
                    503, "speech_unavailable", "Speech is unavailable.", retryable=True
                ) from None
            raise
        return SpeechResponse(stream, first, deadline, finish)

    return router
