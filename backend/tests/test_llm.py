import asyncio
import json
import logging
import time
from types import SimpleNamespace

import httpx
import pytest
from app.core.config import Settings
from app.core.store import digest
from app.integrations.llm import (
    QUERY_PROMPT_VERSION,
    SUMMARY_PROMPT_VERSION,
    LlmClient,
    LlmConfigurationError,
    LlmProtocolError,
    LlmProviderError,
    LlmTimeout,
    load_prompt,
    parse_tidy,
    query_messages,
    resolve_profile,
    summary_is_grounded,
    summary_messages,
)
from app.main import create_app
from app.services.rank_fusion import SourceHealth
from cryptography.fernet import Fernet
from pydantic import ValidationError


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=5))


EMPTY_PAGE = SimpleNamespace(
    items=(),
    next_cursor=None,
    has_more=False,
    status="ok",
    github=SourceHealth("ok"),
    archive=SourceHealth("ok"),
)


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not predicate():
        time.sleep(0.01)
    return bool(predicate())


def settings(**overrides):
    return Settings(_env_file=None, **overrides)


def ollama_settings(**overrides):
    return settings(llm_active_profile="ollama", **overrides)


def timeout_settings(*, first_token=5, total=5):
    return settings(
        llm_active_profile="fast",
        llm_profiles={
            "fast": {
                "provider": "ollama",
                "base_url": "http://127.0.0.1:11434/v1",
                "model": "fast-model",
                "first_token_timeout": first_token,
                "total_timeout": total,
            }
        },
    )


def workers_ai_settings(**overrides):
    return settings(
        llm_active_profile="workers_ai",
        workers_ai_account_id="account-123",
        workers_ai_api_token="token-456",
        **overrides,
    )


def ok_transport(content="ok"):
    def handler(request):
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}]}
        )

    return httpx.MockTransport(handler)


def stream_transport(*chunks):
    body = "".join(
        f"data: {json.dumps({'choices': [{'delta': {'content': chunk}}]})}\n\n"
        for chunk in chunks
    )
    body += "data: [DONE]\n\n"

    def handler(request):
        return httpx.Response(200, text=body)

    return httpx.MockTransport(handler)


class SlowBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        await asyncio.sleep(0.5)
        yield b'data: {"choices":[{"delta":{"content":"late"}}]}\n\n'


class TwoChunkSlowBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
        await asyncio.sleep(0.3)
        yield b'data: {"choices":[{"delta":{"content":"second"}}]}\n\n'
        yield b"data: [DONE]\n\n"


class SlowTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        await asyncio.sleep(0.5)
        return httpx.Response(200, json={"choices": [{"message": {"content": "late"}}]})


# --- profile configuration -------------------------------------------------


def test_active_profile_must_name_a_configured_profile():
    with pytest.raises(ValidationError, match="active LLM profile"):
        settings(llm_active_profile="missing")


def test_profiles_require_provider_model_and_ordered_timeouts():
    with pytest.raises(ValidationError):
        settings(
            llm_profiles={
                "p": {
                    "provider": "ollama",
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": "",
                }
            }
        )
    with pytest.raises(ValidationError):
        settings(
            llm_profiles={
                "p": {
                    "provider": "frontier",
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": "m",
                }
            }
        )
    with pytest.raises(ValidationError):
        settings(
            llm_profiles={
                "p": {
                    "provider": "ollama",
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": "m",
                    "first_token_timeout": 30,
                    "total_timeout": 5,
                }
            }
        )


def test_profile_names_are_bounded_and_non_empty():
    with pytest.raises(ValidationError):
        settings(llm_profiles={})
    with pytest.raises(ValidationError):
        settings(
            llm_profiles={
                "Bad Name": {
                    "provider": "ollama",
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": "m",
                }
            }
        )


def test_workers_ai_profile_substitutes_account_and_key():
    resolved = resolve_profile(workers_ai_settings())
    assert resolved.base_url == (
        "https://api.cloudflare.com/client/v4/accounts/account-123/ai/v1"
    )
    assert resolved.api_key == "token-456"
    assert resolved.model == workers_ai_settings().llm_profiles["workers_ai"].model


def test_workers_ai_profile_fails_closed_without_credentials():
    with pytest.raises(LlmConfigurationError, match="WORKERS_AI_ACCOUNT_ID"):
        resolve_profile(settings(llm_active_profile="workers_ai"))
    with pytest.raises(LlmConfigurationError, match="WORKERS_AI_API_TOKEN"):
        resolve_profile(
            settings(
                llm_active_profile="workers_ai", workers_ai_account_id="account-123"
            )
        )


def test_disabled_profile_is_not_resolved():
    with pytest.raises(LlmConfigurationError):
        resolve_profile(settings())


# --- client contract -------------------------------------------------------


def test_complete_returns_the_message_content():
    client = LlmClient(
        resolve_profile(ollama_settings()), transport=ok_transport("hello")
    )
    assert run(client.complete([{"role": "user", "content": "ping"}])) == "hello"


def test_stream_yields_delta_chunks():
    client = LlmClient(
        resolve_profile(ollama_settings()),
        transport=stream_transport("Hello", " world"),
    )

    async def collect():
        return [
            chunk
            async for chunk in client.stream([{"role": "user", "content": "ping"}])
        ]

    assert run(collect()) == ["Hello", " world"]


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(429, True), (500, True), (401, False), (400, False)],
)
def test_provider_errors_are_typed_and_retryable(status, retryable):
    transport = httpx.MockTransport(lambda request: httpx.Response(status))
    client = LlmClient(resolve_profile(ollama_settings()), transport=transport)
    with pytest.raises(LlmProviderError) as caught:
        run(client.complete([{"role": "user", "content": "ping"}]))
    assert caught.value.status == status
    assert caught.value.retryable is retryable


def test_malformed_responses_are_protocol_errors():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"choices": []})
    )
    client = LlmClient(resolve_profile(ollama_settings()), transport=transport)
    with pytest.raises(LlmProtocolError):
        run(client.complete([{"role": "user", "content": "ping"}]))


def test_first_token_timeout_is_reported_as_llm_timeout():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, stream=SlowBody())
    )
    client = LlmClient(
        resolve_profile(timeout_settings(first_token=0.05, total=5)),
        transport=transport,
    )

    async def collect():
        return [
            chunk
            async for chunk in client.stream([{"role": "user", "content": "ping"}])
        ]

    with pytest.raises(LlmTimeout):
        run(collect())


def test_total_timeout_is_reported_as_llm_timeout():
    client = LlmClient(
        resolve_profile(timeout_settings(first_token=0.05, total=0.05)),
        transport=SlowTransport(),
    )
    with pytest.raises(LlmTimeout):
        run(client.complete([{"role": "user", "content": "ping"}]))


def test_consumer_sleeping_past_the_deadline_gets_llm_timeout_and_is_not_cancelled():
    """No timeout scope may stay open across a yield.

    ``complete(m)`` is fine here: the consumer reads the first chunk, keeps the
    generator open, sleeps past the total deadline, and only its next ``anext``
    may raise ``LlmTimeout``. The consumer must not be cancelled.
    """
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, stream=TwoChunkSlowBody())
    )
    client = LlmClient(
        resolve_profile(timeout_settings(first_token=0.05, total=0.05)),
        transport=transport,
    )

    async def scenario():
        gen = client.stream([{"role": "user", "content": "ping"}])
        assert await anext(gen) == "first"
        try:
            await asyncio.sleep(0.3)
        except asyncio.CancelledError:  # a scope left open across the yield
            raise AssertionError("consumer was cancelled between chunks") from None
        with pytest.raises(LlmTimeout):
            await anext(gen)
        assert not asyncio.current_task().cancelled()

    run(scenario())


def test_logs_carry_metadata_but_never_message_text(caplog):
    caplog.set_level(logging.DEBUG, logger="reporadar.llm")
    client = LlmClient(resolve_profile(ollama_settings()), transport=ok_transport())
    run(client.complete([{"role": "user", "content": "secret quantum banana idea"}]))
    assert "secret quantum banana idea" not in caplog.text
    assert "ollama" in caplog.text


def test_contract_passes_for_each_profile():
    for name in ("ollama", "workers_ai"):
        active = workers_ai_settings() if name == "workers_ai" else ollama_settings()
        client = LlmClient(resolve_profile(active), transport=ok_transport())
        assert run(client.complete([{"role": "user", "content": "ping"}])) == "ok"


# --- prompts and grounding -------------------------------------------------


def test_prompt_files_are_versioned_and_non_empty():
    assert load_prompt(QUERY_PROMPT_VERSION).strip()
    assert load_prompt(SUMMARY_PROMPT_VERSION).strip()
    with pytest.raises(LlmConfigurationError):
        load_prompt("missing")


def test_query_prompt_keeps_the_idea_and_summary_prompt_keeps_results():
    messages = query_messages("a local budget tool")
    assert messages[0]["role"] == "system"
    assert "a local budget tool" in messages[1]["content"]

    results = [
        {
            "name": "compass",
            "full_name": "octocat/compass",
            "description": "Find projects",
            "license": "MIT",
        }
    ]
    summary = summary_messages(results)
    assert summary[0]["role"] == "system"
    assert "octocat/compass" in summary[1]["content"]


def test_parse_tidy_accepts_only_a_bounded_json_query():
    assert parse_tidy('{"query": "budget tracker"}') == "budget tracker"
    with pytest.raises(LlmProtocolError):
        parse_tidy("budget tracker")
    with pytest.raises(LlmProtocolError):
        parse_tidy('{"query": ""}')
    with pytest.raises(LlmProtocolError):
        parse_tidy('{"query": "x" * 500}')


def test_parse_tidy_matches_the_prompt_limit_of_120_characters():
    assert parse_tidy(json.dumps({"query": "x" * 120})) == "x" * 120
    with pytest.raises(LlmProtocolError):
        parse_tidy(json.dumps({"query": "x" * 121}))


def test_query_prompt_bounds_the_query_to_120_characters():
    text = load_prompt(QUERY_PROMPT_VERSION)
    assert "120" in text
    assert "200" not in text


def test_non_workers_api_key_env_is_rejected():
    with pytest.raises(LlmConfigurationError, match="api_key_env"):
        resolve_profile(
            settings(
                llm_active_profile="generic",
                llm_profiles={
                    "generic": {
                        "provider": "ollama",
                        "base_url": "http://127.0.0.1:11434/v1",
                        "model": "m",
                        "api_key_env": "OTHER_KEY",
                    }
                },
            )
        )


def test_grounding_rejects_repositories_outside_the_result_list():
    results = [
        {
            "name": "compass",
            "full_name": "octocat/compass",
            "description": "",
            "license": "MIT",
        }
    ]
    assert summary_is_grounded("Try octocat/compass for this.", results)
    assert not summary_is_grounded("Try evil/backdoor instead.", results)


# --- startup ---------------------------------------------------------------


class FailingClient:
    profile_name = "fake"
    model = "fake-model"

    async def complete(self, messages, **kwargs):
        raise LlmProviderError("down", status=503, retryable=True)


class HealthyClient:
    profile_name = "fake"
    model = "fake-model"

    async def complete(self, messages, **kwargs):
        return "ok"


class NeverClient:
    """A probe that never resolves, like a hung provider connection."""

    profile_name = "fake"
    model = "fake-model"

    async def complete(self, messages, **kwargs):
        await asyncio.Event().wait()


def frozen_runtime():
    """Smallest fake hybrid runtime so a plain search route can be served."""

    class Pager:
        async def first_page(self, *args, **kwargs):
            return EMPTY_PAGE

    return SimpleNamespace(
        target=lambda: SimpleNamespace(
            pager=Pager(),
            generation="gen",
            revalidator=None,
            executor=None,
        ),
        status=lambda: {
            "state": "uninitialized",
            "coverage": "unknown",
            "archive_as_of": None,
        },
    )


def authenticated_app(app, key, tmp_path):
    cipher = Fernet(key.encode())
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
    return app


def test_startup_failure_marks_summaries_unavailable_without_breaking_search(
    tmp_path, caplog
):
    caplog.set_level(logging.ERROR, logger="reporadar.llm")
    app = create_app(
        settings(database_path=str(tmp_path / "auth.sqlite3")), llm=FailingClient()
    )
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert wait_until(lambda: app.state.llm_probe.done())
        assert app.state.llm_available is False
    assert "llm_unavailable" in caplog.text
    assert "fake-model" in caplog.text


def test_startup_success_marks_summaries_available(tmp_path):
    app = create_app(
        settings(database_path=str(tmp_path / "auth.sqlite3")), llm=HealthyClient()
    )
    from fastapi.testclient import TestClient

    with TestClient(app):
        assert wait_until(lambda: app.state.llm_available is True)


def test_slow_probe_does_not_delay_search_and_is_cancelled_on_shutdown(tmp_path):
    from httpx import ASGITransport

    key = Fernet.generate_key().decode()
    app = authenticated_app(
        create_app(
            settings(
                database_path=str(tmp_path / "auth.sqlite3"),
                token_encryption_key=key,
            ),
            hybrid=frozen_runtime(),
            llm=NeverClient(),
        ),
        key,
        tmp_path,
    )

    async def scenario():
        async with app.router.lifespan_context(app):
            assert app.state.llm_available is False
            started = time.monotonic()
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as http:
                response = await http.post(
                    "/v1/projects/search",
                    headers={"Authorization": "Bearer session1"},
                    json={"idea": "a small budget tool"},
                )
            assert response.status_code == 200, response.text
            assert time.monotonic() - started < 2
            assert app.state.llm_available is False
        assert app.state.llm_probe is not None
        assert app.state.llm_probe.cancelled()

    run(scenario())


def test_no_model_name_is_hard_coded_outside_config():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    configured = set()
    for profile in settings().llm_profiles.values():
        configured.add(profile.model)
    for path in root.rglob("*.py"):
        if path.name == "config.py":
            continue
        text = path.read_text(encoding="utf-8")
        for model in configured:
            assert model not in text, f"{model} hard-coded in {path}"
