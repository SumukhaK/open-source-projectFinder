import httpx
import pytest
from app.integrations.github import GitHubProvider, ProviderError


def test_read_retries_incrementally_but_auth_errors_do_not():
    waits = []
    statuses = [503, 502, 200]

    def response(request):
        status = statuses.pop(0)
        return httpx.Response(status, json={"id": 1, "login": "user"})

    provider = GitHubProvider(
        "id",
        "secret",
        "https://example.test/callback",
        httpx.MockTransport(response),
        waits.append,
    )
    assert provider.user("token")["id"] == 1
    assert len(waits) == 2 and waits[1] > waits[0]
    statuses[:] = [401]
    with pytest.raises(ProviderError):
        provider.user("token")
    assert len(waits) == 2


def test_retry_after_over_budget_and_code_exchange_are_not_retried():
    calls = []

    def response(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})

    provider = GitHubProvider(
        "id",
        "secret",
        "https://example.test/callback",
        httpx.MockTransport(response),
        lambda _: pytest.fail("must not wait"),
    )
    with pytest.raises(ProviderError):
        provider.user("token")
    assert len(calls) == 1
    with pytest.raises(ProviderError):
        provider.exchange("code", "verifier")
    assert len(calls) == 2


def test_exhausted_retries_and_invalid_token_response():
    calls, waits = [], []

    def response(request):
        calls.append(request)
        if request.url.path.endswith("access_token"):
            return httpx.Response(200, json={"error": "bad_verification_code"})
        return httpx.Response(503)

    provider = GitHubProvider(
        "id",
        "secret",
        "https://example.test/callback",
        httpx.MockTransport(response),
        waits.append,
    )
    with pytest.raises(ProviderError):
        provider.user("token")
    assert len(calls) == 3 and len(waits) == 2
    with pytest.raises(ProviderError):
        provider.exchange("code", "verifier")
    assert len(calls) == 4


def test_rate_limit_without_retry_headers_does_not_retry_early():
    calls = []

    def response(request):
        calls.append(request)
        return httpx.Response(429)

    provider = GitHubProvider(
        "id",
        "secret",
        "https://example.test/callback",
        httpx.MockTransport(response),
        lambda _: pytest.fail("must not retry before GitHub's minimum wait"),
    )
    with pytest.raises(ProviderError):
        provider.user("token")
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"id": "bad"}),
        httpx.Response(200, text="not-json"),
        httpx.Response(404),
        httpx.Response(200, text="x" * 524289),
    ],
)
def test_provider_rejects_invalid_missing_and_oversized_identity(response):
    provider = GitHubProvider(
        "id",
        "secret",
        "https://example.test/callback",
        httpx.MockTransport(lambda _: response),
        lambda _: None,
    )
    with pytest.raises(ProviderError):
        provider.user("token")


@pytest.mark.parametrize(
    "headers",
    [
        {"Retry-After": "bad"},
        {"Retry-After": "Thu, 01 Jan 2099 00:00:00 GMT"},
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "99999999999"},
    ],
)
def test_provider_respects_unusable_or_distant_retry_headers(headers):
    provider = GitHubProvider(
        "id",
        "secret",
        "https://example.test/callback",
        httpx.MockTransport(lambda _: httpx.Response(403, headers=headers)),
        lambda _: pytest.fail("must not retry"),
    )
    with pytest.raises(ProviderError):
        provider.user("token")


def test_provider_network_failure_is_bounded():
    def response(request):
        raise httpx.ConnectError("offline", request=request)

    waits = []
    provider = GitHubProvider(
        "id",
        "secret",
        "https://example.test/callback",
        httpx.MockTransport(response),
        waits.append,
    )
    with pytest.raises(ProviderError):
        provider.user("token")
    assert len(waits) == 2
