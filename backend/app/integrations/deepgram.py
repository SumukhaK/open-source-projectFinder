"""Bounded, transient pre-recorded transcription; no SDK or provider error text."""

import json
import math

import httpx


class VoiceUnavailable(Exception):
    pass


async def transcribe(audio, settings, *, content_type="audio/wav", transport=None):
    async with httpx.AsyncClient(
        transport=transport, timeout=settings.voice_timeout, follow_redirects=False
    ) as client:
        async with client.stream(
            "POST",
            "https://api.deepgram.com/v1/listen",
            params={"model": settings.deepgram_model, "mip_opt_out": "true"},
            headers={
                "Authorization": "Token "
                + settings.deepgram_api_key.get_secret_value(),
                "Content-Type": content_type,
                "Accept-Encoding": "identity",
            },
            content=audio,
        ) as response:
            if (
                response.status_code != 200
                or response.headers.get("content-encoding", "identity") != "identity"
            ):
                raise VoiceUnavailable
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                body.extend(chunk)
                if len(body) > 65536:
                    raise VoiceUnavailable
    try:
        data = json.loads(body)
        duration = None
        if content_type != "audio/wav":
            duration = data["metadata"]["duration"]
            if (
                type(duration) not in (int, float)
                or not math.isfinite(duration)
                or duration <= 0
            ):
                raise VoiceUnavailable
        text = data["results"]["channels"][0]["alternatives"][0]["transcript"]
        if not isinstance(text, str) or len(text) > 1000:
            raise VoiceUnavailable
        return text.strip(), duration
    except (ValueError, TypeError, KeyError, IndexError):
        raise VoiceUnavailable from None
