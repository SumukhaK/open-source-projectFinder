"""OpenAI-compatible LLM client, versioned prompts and grounding checks.

Both Ollama and Cloudflare Workers AI speak the OpenAI chat-completions
protocol, so switching provider is a settings change. This module is not
imported by a route in V0. Logs carry profile, model, counts and durations
only; prompts, ideas, transcripts and replies are never logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx
from app.core.config import LlmProfile, Settings

logger = logging.getLogger("reporadar.llm")

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
PROMPTS = {
    "query_tidy_v1": PROMPT_DIR / "query_tidy_v1.txt",
    "summary_grounded_v1": PROMPT_DIR / "summary_grounded_v1.txt",
}
QUERY_PROMPT_VERSION = "query_tidy_v1"
SUMMARY_PROMPT_VERSION = "summary_grounded_v1"
_REPOSITORY = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\b")


class LlmError(Exception):
    """Base class for typed LLM failures."""


class LlmConfigurationError(LlmError):
    pass


class LlmTimeout(LlmError):
    pass


class LlmProviderError(LlmError):
    def __init__(self, message, *, status=None, retryable=False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class LlmProtocolError(LlmError):
    pass


@dataclass(frozen=True)
class ResolvedProfile:
    name: str
    provider: str
    base_url: str
    model: str
    api_key: str
    connect_timeout: float
    first_token_timeout: float
    total_timeout: float
    max_output_tokens: int
    temperature: float
    context_limit: int
    streaming: bool


def resolve_profile(settings: Settings) -> ResolvedProfile:
    """Resolve the active profile and its server-side key reference."""
    name = settings.llm_active_profile
    if not name:
        raise LlmConfigurationError("No active LLM profile is configured")
    profile: LlmProfile | None = settings.llm_profiles.get(name)
    if profile is None:
        raise LlmConfigurationError(f"Unknown LLM profile: {name}")
    base_url = profile.base_url
    if "{account_id}" in base_url:
        account = settings.workers_ai_account_id.strip()
        if not account:
            raise LlmConfigurationError(
                "WORKERS_AI_ACCOUNT_ID is required for the workers_ai profile"
            )
        base_url = base_url.replace("{account_id}", account)
    api_key = ""
    if profile.api_key_env:
        if profile.api_key_env == "WORKERS_AI_API_TOKEN":
            api_key = settings.workers_ai_api_token.get_secret_value()
        else:
            api_key = os.environ.get(profile.api_key_env, "")
        if not api_key:
            raise LlmConfigurationError(
                f"{profile.api_key_env} is required for the {name} profile"
            )
    return ResolvedProfile(
        name=name,
        provider=profile.provider,
        base_url=base_url,
        model=profile.model,
        api_key=api_key,
        connect_timeout=profile.connect_timeout,
        first_token_timeout=profile.first_token_timeout,
        total_timeout=profile.total_timeout,
        max_output_tokens=profile.max_output_tokens,
        temperature=profile.temperature,
        context_limit=profile.context_limit,
        streaming=profile.streaming,
    )


def build_client(settings: Settings) -> "LlmClient":
    return LlmClient(resolve_profile(settings))


class LlmClient:
    def __init__(self, resolved: ResolvedProfile, transport=None):
        self.resolved = resolved
        self.transport = transport

    @property
    def profile_name(self):
        return self.resolved.name

    @property
    def model(self):
        return self.resolved.model

    def _url(self):
        return f"{self.resolved.base_url}/chat/completions"

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.resolved.api_key:
            headers["Authorization"] = f"Bearer {self.resolved.api_key}"
        return headers

    def _timeout(self):
        # Deadlines come from asyncio.timeout so a slow body cannot outlive the
        # profile; httpx's own read timeout is disabled to avoid double limits.
        return httpx.Timeout(
            connect=self.resolved.connect_timeout,
            read=None,
            write=self.resolved.connect_timeout,
            pool=self.resolved.connect_timeout,
        )

    def _payload(self, messages, stream, max_tokens, temperature):
        self._check_messages(messages)
        limit = self.resolved.max_output_tokens
        if max_tokens is not None:
            limit = min(max_tokens, limit)
        return {
            "model": self.resolved.model,
            "messages": list(messages),
            "stream": stream,
            "max_tokens": limit,
            "temperature": (
                self.resolved.temperature if temperature is None else temperature
            ),
        }

    def _check_messages(self, messages):
        if not isinstance(messages, Sequence) or not messages:
            raise LlmProtocolError("LLM messages must be a non-empty list")
        chars = 0
        for message in messages:
            if (
                not isinstance(message, Mapping)
                or not isinstance(message.get("role"), str)
                or not isinstance(message.get("content"), str)
            ):
                raise LlmProtocolError("LLM messages need a role and content")
            chars += len(message["content"])
        if chars // 4 > self.resolved.context_limit:
            raise LlmProtocolError("LLM prompt exceeds the profile context limit")

    @staticmethod
    def _raise_for_status(response):
        if response.status_code < 400:
            return
        retryable = response.status_code == 429 or response.status_code >= 500
        raise LlmProviderError(
            f"LLM provider returned HTTP {response.status_code}",
            status=response.status_code,
            retryable=retryable,
        )

    @staticmethod
    def _json(response):
        try:
            data = response.json()
        except ValueError as error:
            raise LlmProtocolError("LLM response was not JSON") from error
        if not isinstance(data, dict):
            raise LlmProtocolError("LLM response must be an object")
        return data

    @staticmethod
    def _message_content(data):
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LlmProtocolError("LLM response has no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LlmProtocolError("LLM response has no message content")
        return content

    async def complete(self, messages, *, max_tokens=None, temperature=None):
        payload = self._payload(messages, False, max_tokens, temperature)
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.resolved.total_timeout):
                async with httpx.AsyncClient(
                    transport=self.transport, timeout=self._timeout()
                ) as client:
                    response = await client.post(
                        self._url(), json=payload, headers=self._headers()
                    )
                    self._raise_for_status(response)
                    data = self._json(response)
        except TimeoutError as error:
            raise LlmTimeout("LLM request timed out") from error
        except httpx.HTTPError as error:
            raise LlmProviderError("LLM transport failed", retryable=True) from error
        finally:
            self._log(started, messages, stream=False)
        return self._message_content(data)

    async def stream(
        self, messages, *, max_tokens=None, temperature=None
    ) -> AsyncIterator[str]:
        payload = self._payload(messages, True, max_tokens, temperature)
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.resolved.total_timeout):
                async with httpx.AsyncClient(
                    transport=self.transport, timeout=self._timeout()
                ) as client:
                    async with client.stream(
                        "POST", self._url(), json=payload, headers=self._headers()
                    ) as response:
                        self._raise_for_status(response)
                        lines = response.aiter_lines()
                        line = await self._first_line(lines)
                        while line is not None:
                            if line.strip() == "data: [DONE]":
                                return
                            chunk = self._sse_content(line)
                            if chunk:
                                yield chunk
                            line = await anext(lines, None)
        except TimeoutError as error:
            raise LlmTimeout("LLM stream timed out") from error
        except httpx.HTTPError as error:
            raise LlmProviderError("LLM transport failed", retryable=True) from error
        finally:
            self._log(started, messages, stream=True)

    async def _first_line(self, lines):
        async with asyncio.timeout(self.resolved.first_token_timeout):
            async for line in lines:
                if line.strip():
                    return line
        return None

    @staticmethod
    def _sse_content(line):
        if not line.startswith("data:"):
            return None
        raw = line[5:].strip()
        if not raw or raw == "[DONE]":
            return None
        try:
            data = json.loads(raw)
        except ValueError as error:
            raise LlmProtocolError("LLM stream chunk was not JSON") from error
        if not isinstance(data, dict):
            raise LlmProtocolError("LLM stream chunk must be an object")
        if "error" in data:
            raise LlmProtocolError("LLM stream reported an error")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
        content = delta.get("content") if isinstance(delta, dict) else None
        return content if isinstance(content, str) else None

    def _log(self, started, messages, *, stream):
        logger.info(
            json.dumps(
                {
                    "event": "llm_request",
                    "profile": self.resolved.name,
                    "model": self.resolved.model,
                    "stream": stream,
                    "message_count": len(messages),
                    "prompt_chars": sum(len(m["content"]) for m in messages),
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            )
        )


def load_prompt(version: str) -> str:
    path = PROMPTS.get(version)
    if path is None:
        raise LlmConfigurationError(f"Unknown prompt version: {version}")
    return path.read_text(encoding="utf-8")


def query_messages(idea: str):
    return [
        {"role": "system", "content": load_prompt(QUERY_PROMPT_VERSION)},
        {"role": "user", "content": idea},
    ]


def summary_messages(results):
    bounded = [
        {
            "name": result.get("name"),
            "full_name": result.get("full_name"),
            "description": (result.get("description") or "")[:300],
            "license": result.get("license"),
        }
        for result in list(results)[:10]
    ]
    return [
        {"role": "system", "content": load_prompt(SUMMARY_PROMPT_VERSION)},
        {
            "role": "user",
            "content": json.dumps({"results": bounded}, ensure_ascii=False),
        },
    ]


def parse_tidy(text: str) -> str:
    try:
        data = json.loads(text)
    except ValueError as error:
        raise LlmProtocolError("Tidy response was not JSON") from error
    query = data.get("query") if isinstance(data, dict) else None
    if not isinstance(query, str):
        raise LlmProtocolError("Tidy response needs a query string")
    query = query.strip()
    if not 2 <= len(query) <= 200:
        raise LlmProtocolError("Tidy query is outside the allowed length")
    return query


def summary_is_grounded(summary: str, results) -> bool:
    allowed = set()
    for result in results:
        for key in ("name", "full_name"):
            value = result.get(key)
            if isinstance(value, str) and value:
                allowed.add(value.casefold())
    return all(token.casefold() in allowed for token in _REPOSITORY.findall(summary))


async def probe_profile(client, profile_name: str, model: str) -> bool:
    """One tiny call at startup; failure marks summaries unavailable only."""
    try:
        await client.complete([{"role": "user", "content": "ping"}], max_tokens=1)
        return True
    except LlmError as error:
        logger.error(
            json.dumps(
                {
                    "event": "llm_unavailable",
                    "profile": profile_name,
                    "model": model,
                    "error": type(error).__name__,
                }
            )
        )
        return False
