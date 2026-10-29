import httpx
import pytest
from app.core.config import Settings
from app.integrations.github import GitHubProvider, ProviderError
from app.services.keyword_candidates import GitHubKeywordCandidates
from app.services.keyword_query import (
    GITHUB_SCOPE,
    CandidateFilters,
    compile_keyword_query,
)

REPO = {
    "id": 1,
    "name": "compass",
    "full_name": "octocat/compass",
    "private": False,
    "archived": False,
    "visibility": "public",
    "owner": {"login": "octocat"},
    "description": "Find projects",
    "stargazers_count": 42,
    "language": "Python",
    "pushed_at": "2010-01-01T00:00:00Z",
    "license": {"spdx_id": "GPL-3.0"},
}


class FakeProvider:
    def __init__(self, data=None, error=None):
        self.data, self.error, self.calls = data, error, []

    def read(self, token, path, **kwargs):
        self.calls.append({"token": token, "path": path, **kwargs})
        if self.error:
            raise self.error
        return self.data


def source(provider, **settings):
    return GitHubKeywordCandidates(provider, Settings(_env_file=None, **settings))


def test_live_candidates_are_ranked_and_keep_public_scope():
    second = {**REPO, "id": 2, "full_name": "octocat/other"}
    private = {**REPO, "id": 3, "private": True}
    archived = {**REPO, "id": 4, "archived": True}
    internal = {**REPO, "id": 5, "visibility": "internal"}
    missing_archived = {**REPO, "id": 6}
    del missing_archived["archived"]
    provider = FakeProvider(
        {
            "items": [REPO, private, archived, internal, missing_archived, second],
            "total_count": 6,
            "incomplete_results": False,
        }
    )

    result = source(provider).search("token", "offline first notes")

    assert result.status == "ok"
    assert result.incomplete is False
    assert result.completed is True
    assert [(candidate.rank, candidate.repo_id) for candidate in result.candidates] == [
        (1, 1),
        (2, 2),
    ]
    # Older and copyleft live repositories remain eligible; only the archive has
    # the rolling cutoff and licence-content policy.
    assert result.candidates[0].metadata["pushed_at"] == "2010-01-01T00:00:00Z"
    assert result.candidates[0].metadata["license"]["spdx_id"] == "GPL-3.0"
    assert provider.calls == [
        {
            "token": "token",
            "path": "/search/repositories",
            "params": {
                "q": f"offline first notes {GITHUB_SCOPE}",
                "per_page": 100,
                "page": 1,
            },
            "max_response_bytes": 1048576,
        }
    ]


def test_candidate_source_requests_and_returns_at_most_100():
    provider = FakeProvider(
        {
            "items": [{**REPO, "id": index} for index in range(1, 131)],
            "total_count": 130,
            "incomplete_results": False,
        }
    )

    result = source(provider).search("token", "offline notes")

    assert len(result.candidates) == 100
    assert result.candidates[-1].rank == 100
    assert provider.calls[0]["params"]["per_page"] == 100


def test_incomplete_results_are_retained_and_flagged():
    provider = FakeProvider(
        {"items": [REPO], "total_count": 1200, "incomplete_results": True}
    )

    result = source(provider).search("token", "offline notes")

    assert result.status == "incomplete"
    assert result.incomplete is True
    assert result.completed is False
    assert [candidate.repo_id for candidate in result.candidates] == [1]


def test_completed_empty_is_not_unsupported_or_incomplete():
    provider = FakeProvider(
        {"items": [], "total_count": 0, "incomplete_results": False}
    )

    result = source(provider).search("token", "offline notes")

    assert result.status == "ok"
    assert result.candidates == ()
    assert result.incomplete is False
    assert result.completed is True


@pytest.mark.parametrize(
    ("idea", "reason"), [("the and using", "empty"), ("p" * 300, "too_long")]
)
def test_unusable_keyword_query_is_not_sent_as_a_broad_search(idea, reason):
    provider = FakeProvider({"items": [REPO], "total_count": 1})

    result = source(provider).search("token", idea)

    assert result.status == "query_not_supported"
    assert result.reason == reason
    assert result.candidates == ()
    assert result.completed is False
    assert provider.calls == []


def test_long_semantic_idea_uses_only_the_bounded_keyword_adapter():
    prefix = "python web framework django flask fastapi "
    idea = prefix + "z" * (1000 - len(prefix))
    assert len(idea) == 1000
    provider = FakeProvider({"items": [REPO], "total_count": 1})

    result = source(provider).search("token", idea)

    assert result.status == "ok"
    assert provider.calls[0]["params"]["q"] == (
        f"python web framework django flask fastapi {GITHUB_SCOPE}"
    )
    # The candidate source only derives a GitHub query; the caller keeps the
    # original idea for the semantic branch and this result never stores it.
    assert idea.startswith(prefix)


@pytest.mark.parametrize(
    ("idea", "keywords"),
    [
        ("Café 日本語", "café 日本語"),
        (
            "python OR is:private user:evil archived:true",
            "python or private user evil archived",
        ),
    ],
)
def test_keyword_text_keeps_scripts_and_cannot_inject_qualifiers(idea, keywords):
    provider = FakeProvider({"items": [REPO], "total_count": 1})

    source(provider).search("token", idea)

    query = provider.calls[0]["params"]["q"]
    assert query == f"{keywords} {GITHUB_SCOPE}"
    assert "is:private" not in query
    assert "user:evil" not in query
    assert "archived:true" not in query


@pytest.mark.parametrize(
    ("error", "reason", "retry_after"),
    [
        (ProviderError(retry_after=120), "rate_limited", 120),
        (ProviderError(), "unavailable", None),
    ],
)
def test_provider_failures_become_source_status(error, reason, retry_after):
    provider = FakeProvider(error=error)

    result = source(provider).search("token", "offline notes")

    assert result.status == "failed"
    assert result.reason == reason
    assert result.retry_after == retry_after
    assert result.candidates == ()
    assert result.completed is False


def test_oversized_provider_response_becomes_failed_status():
    def response(request):
        return httpx.Response(
            200,
            json={
                "items": [{**REPO, "padding": "x" * 2000}],
                "total_count": 1,
                "incomplete_results": False,
            },
        )

    settings = Settings(_env_file=None, max_github_search_response=1024)
    provider = GitHubProvider(
        "id",
        "secret",
        "https://example.test/callback",
        httpx.MockTransport(response),
        lambda _: None,
        settings,
    )

    result = GitHubKeywordCandidates(provider, settings).search(
        "token", "offline notes"
    )

    assert result.status == "failed"
    assert result.reason == "unavailable"
    assert result.candidates == ()


def test_malformed_provider_payload_is_not_a_completed_empty_result():
    provider = FakeProvider({"items": "not-a-list"})

    result = source(provider).search("token", "offline notes")

    assert result.status == "failed"
    assert result.reason == "invalid_response"
    assert result.candidates == ()
    assert result.completed is False


def test_supported_typed_filters_are_translated():
    provider = FakeProvider({"items": [REPO], "total_count": 1})

    source(provider).search(
        "token",
        "offline notes",
        CandidateFilters(language="TypeScript", license="apache-2.0"),
    )

    assert provider.calls[0]["params"]["q"] == (
        f"offline notes {GITHUB_SCOPE} language:TypeScript license:apache-2.0"
    )


@pytest.mark.parametrize(
    ("filters", "qualifiers"),
    [
        (CandidateFilters(language="Jupyter Notebook"), 'language:"Jupyter Notebook"'),
        (CandidateFilters(license="MIT OR 0BSD"), 'license:"MIT OR 0BSD"'),
    ],
)
def test_multi_word_filter_values_are_quoted(filters, qualifiers):
    provider = FakeProvider({"items": [REPO], "total_count": 1})

    source(provider).search("token", "offline notes", filters)

    assert provider.calls[0]["params"]["q"] == (
        f"offline notes {GITHUB_SCOPE} {qualifiers}"
    )


@pytest.mark.parametrize(
    "value",
    [
        "Python is:private",
        'Python" OR "x',
        "Python\nuser:evil",
        "Python\\is:private",
        "",
    ],
)
def test_unsafe_filter_values_are_rejected_before_the_provider(value):
    provider = FakeProvider({"items": [REPO], "total_count": 1})

    with pytest.raises(ValueError):
        source(provider).search(
            "token", "offline notes", CandidateFilters(language=value)
        )

    assert provider.calls == []


@pytest.mark.parametrize(
    ("idea", "query"),
    [
        (
            "  I want to build a Python web-app with Fast_API, Django, Flask, "
            "SQLite and Redis  ",
            "python web-app fast_api django flask sqlite",
        ),
        ("python web framework", "python web framework"),
        ("Café 日本語", "café 日本語"),
        ("p" * 256, "p" * 256),
    ],
)
def test_keyword_compiler_preserves_the_legacy_contract(idea, query):
    assert compile_keyword_query(idea) == (query, None)


@pytest.mark.parametrize(
    ("idea", "problem"),
    [("the and using", "empty"), ("p" * 257, "too_long")],
)
def test_keyword_compiler_reports_legacy_problems(idea, problem):
    assert compile_keyword_query(idea) == (None, problem)
