"""Authenticated grounded summary of the current search's first page.

The client sends only result identities. Name, description and licence come
from the page this account was just served, so a client cannot inject
repository text. The provider stream is collected and validated before the
first response byte, so an ungrounded or late summary is never shown.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.integrations.llm import (
    LlmError,
    LlmTimeout,
    summary_is_grounded,
    summary_messages,
)

logger = logging.getLogger("reporadar.summary")

MAX_RESULTS = 10
_CHUNK_CHARS = 120
_FULL_NAME = r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$"
FullName = Annotated[str, Field(min_length=3, max_length=200, pattern=_FULL_NAME)]


class SummaryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_names: list[FullName] = Field(default_factory=list, max_length=MAX_RESULTS)


class SummaryPages:
    """Bounded, account-scoped metadata for the last first page served."""

    def __init__(self, *, ttl, max_accounts, now=time.monotonic):
        self._ttl = ttl
        self._max_accounts = max_accounts
        self._now = now
        self._pages = {}

    def remember(self, account, items):
        self._purge()
        # Re-insert so a re-remembered account becomes the newest entry.
        self._pages.pop(account, None)
        self._pages[account] = (
            self._now() + self._ttl,
            [
                {
                    "name": item.get("name"),
                    "full_name": item["full_name"],
                    "description": item.get("description") or "",
                    "license": item.get("license"),
                }
                for item in items
                if isinstance(item.get("full_name"), str) and item["full_name"]
            ],
        )
        while len(self._pages) > self._max_accounts:
            self._pages.pop(next(iter(self._pages)))

    def resolve(self, account, full_names):
        self._purge()
        entry = self._pages.get(account)
        if entry is None:
            return []
        wanted = {name.casefold() for name in full_names}
        return [item for item in entry[1] if item["full_name"].casefold() in wanted]

    def _purge(self):
        now = self._now()
        expired = [
            account for account, (expires, _) in self._pages.items() if expires <= now
        ]
        for account in expired:
            self._pages.pop(account, None)


def _event(name, data):
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def _response(chunks, reason, *, count=0):
    def body():
        for chunk in chunks:
            yield _event("summary", {"text": chunk})
        if reason is None:
            yield _event("done", {"grounded": True, "results": count})
        else:
            yield _event("done", {"grounded": False, "reason": reason})

    return StreamingResponse(body(), media_type="text/event-stream")


def _pieces(text):
    return [
        text[index : index + _CHUNK_CHARS]
        for index in range(0, len(text), _CHUNK_CHARS)
    ]


async def _collect(client, results, deadline):
    chunks = []
    async with asyncio.timeout(deadline):
        async for chunk in client.stream(summary_messages(results)):
            chunks.append(chunk)
    return "".join(chunks)


def _log(profile, model, results, chars, reason, started):
    logger.info(
        json.dumps(
            {
                "event": "summary",
                "profile": profile,
                "model": model,
                "result_count": results,
                "summary_chars": chars,
                "reason": reason,
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
        )
    )


def summary_router(settings, current, pages):
    router = APIRouter()
    in_flight = 0

    @router.post("/v1/projects/search/summary")
    async def summary(body: SummaryBody, request: Request):
        nonlocal in_flight
        user = current(request)
        started = time.monotonic()
        results = pages.resolve(user["github_id"], body.full_names)
        client = getattr(request.app.state, "llm_client", None)
        profile = getattr(client, "profile_name", settings.llm_active_profile or None)
        model = getattr(client, "model", None)
        reason = None
        if not results:
            reason = "no_results"
        elif (
            not settings.llm_active_profile
            or client is None
            or not getattr(request.app.state, "llm_available", False)
        ):
            reason = "unavailable"
        if reason is not None:
            _log(profile, model, len(results), 0, reason, started)
            return _response((), reason)
        if in_flight >= settings.summary_max_concurrent:
            _log(profile, model, len(results), 0, "busy", started)
            return _response((), "busy")
        in_flight += 1
        try:
            text = (await _collect(client, results, settings.summary_deadline)).strip()
        except (TimeoutError, LlmTimeout):
            reason = "timeout"
        except LlmError:
            reason = "unavailable"
        else:
            if not text:
                reason = "empty"
            elif not summary_is_grounded(text, results):
                reason = "ungrounded"
        finally:
            in_flight -= 1
        if reason is not None:
            _log(profile, model, len(results), 0, reason, started)
            return _response((), reason)
        _log(profile, model, len(results), len(text), "ok", started)
        return _response(_pieces(text), None, count=len(results))

    return router
