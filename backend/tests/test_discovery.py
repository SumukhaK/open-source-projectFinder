import json
import time

import httpx
import pytest
from app.core.config import Settings
from app.core.store import digest
from app.main import create_app
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

REPO = {
    "id": 1,
    "name": "compass",
    "full_name": "octocat/compass",
    "private": False,
    "owner": {
        "login": "octocat",
        "avatar_url": "https://avatars.githubusercontent.com/u/1",
    },
    "description": "Find projects",
    "stargazers_count": 42,
    "language": "Python",
    "html_url": "https://github.com/octocat/compass",
    "default_branch": "main",
}


@pytest.fixture
def discovery(tmp_path, request):
    calls = []
    responses = {}

    def remote(request):
        calls.append(request)
        path = request.url.path
        if path in responses:
            return responses[path]
        if path == "/search/repositories":
            return httpx.Response(
                200,
                json={"items": [REPO], "total_count": 1, "incomplete_results": False},
            )
        if path.endswith("/languages"):
            return httpx.Response(200, json={"Python": 90, "Shell": 10})
        if path.endswith("/releases"):
            return httpx.Response(
                200,
                json=[
                    {
                        "tag_name": "v1",
                        "name": "First",
                        "published_at": "2026-01-01",
                        "html_url": "https://github.com/octocat/compass/releases/tag/v1",
                    }
                ],
            )
        if path.endswith("/readme"):
            return httpx.Response(200, text="# Compass\nFind projects")
        if path.endswith("/contributors"):
            return httpx.Response(
                200,
                json=[
                    {
                        "login": "octocat",
                        "avatar_url": "https://avatars.githubusercontent.com/u/1",
                        "contributions": 8,
                    }
                ],
            )
        return httpx.Response(200, json=REPO)

    key = Fernet.generate_key()
    cipher = Fernet(key)
    settings = Settings(
        _env_file=None,
        database_path=str(tmp_path / "db"),
        token_encryption_key=key.decode(),
        discovery_rate_limit=100,
        search_page_size=20,
        **getattr(request, "param", {}),
    )
    app = create_app(settings, httpx.MockTransport(remote), sleep=lambda _: None)
    with app.state.store.connect() as db:
        for uid in (1, 2):
            db.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?)",
                (
                    uid,
                    f"user{uid}",
                    "",
                    cipher.encrypt(
                        json.dumps({"access_token": "upstream"}).encode()
                    ).decode(),
                ),
            )
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                (digest(f"session{uid}"), uid, time.time() + 1000),
            )
    with TestClient(app) as client:
        yield client, app, calls, responses


HEADERS = {"Authorization": "Bearer session1"}


def test_favourites_are_persistent_idempotent_and_per_user(discovery):
    client, app, _, _ = discovery
    assert client.put("/favourites/octocat/compass", headers=HEADERS).status_code == 200
    assert client.put("/favourites/octocat/compass", headers=HEADERS).status_code == 200
    assert len(client.get("/favourites", headers=HEADERS).json()["items"]) == 1
    assert (
        client.get("/favourites", headers={"Authorization": "Bearer session2"}).json()[
            "items"
        ]
        == []
    )
    with app.state.store.connect() as db:
        assert db.execute("SELECT count(*) FROM favourites").fetchone()[0] == 1
    assert (
        client.delete("/favourites/octocat/compass", headers=HEADERS).status_code == 204
    )
    assert (
        client.delete("/favourites/octocat/compass", headers=HEADERS).status_code == 204
    )
    assert client.get("/favourites", headers=HEADERS).json()["items"] == []


def test_details_sections_and_optional_missing_content(discovery):
    client, _, _, responses = discovery
    details = client.get("/projects/octocat/compass", headers=HEADERS)
    assert details.status_code == 200
    assert details.json()["readme"].startswith("# Compass")
    assert details.json()["languages"]["Python"] == 90
    assert details.json()["contributors"][0]["login"] == "octocat"
    for suffix in ("readme", "releases", "contributors", "languages"):
        responses[f"/repos/octocat/compass/{suffix}"] = httpx.Response(404)
    empty = client.get("/projects/octocat/compass", headers=HEADERS).json()
    assert empty["readme"] == "" and empty["releases"] == []
    assert empty["contributors"] == [] and empty["languages"] == {}


def test_private_missing_and_provider_rate_limits_never_become_empty_results(discovery):
    client, _, calls, responses = discovery
    responses["/repos/octocat/compass"] = httpx.Response(
        200, json={**REPO, "private": True}
    )
    assert client.get("/projects/octocat/compass", headers=HEADERS).status_code == 404
    assert client.put("/favourites/octocat/compass", headers=HEADERS).status_code == 404
    assert client.get("/projects/octocat/bad..name", headers=HEADERS).status_code == 422


@pytest.mark.parametrize("sort", ["stars", "forks", "updated"])
def test_sort_parameter(discovery, sort):
    client, _, calls, _ = discovery
    response = client.post(
        "/projects/search",
        headers=HEADERS,
        json={"idea": "python web framework", "sort": sort, "order": "asc"},
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].url.params["sort"] == sort
    assert response.json()["sort"] == sort


@pytest.mark.parametrize("order", ["desc", "asc"])
def test_order_parameter(discovery, order):
    client, _, calls, _ = discovery
    response = client.post(
        "/projects/search",
        headers=HEADERS,
        json={"idea": "python web framework", "sort": "stars", "order": order},
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].url.params["order"] == order
    assert response.json()["order"] == order


def test_sorting_defaults_to_descending_order(discovery):
    client, _, calls, _ = discovery
    response = client.post(
        "/projects/search",
        headers=HEADERS,
        json={"idea": "python web framework", "sort": "stars"},
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].url.params.get("order", "desc") == "desc"
    assert response.json()["order"] == "desc"


@pytest.mark.parametrize("order", [None, "desc", "asc"])
def test_best_match_omits_upstream_sort_and_order(discovery, order):
    client, _, calls, _ = discovery
    body = {"idea": "python web framework"}
    if order is not None:
        body["order"] = order
    response = client.post("/projects/search", headers=HEADERS, json=body)
    assert response.status_code == 200
    assert len(calls) == 1
    assert "sort" not in calls[0].url.params
    assert "order" not in calls[0].url.params
    assert response.json()["sort"] == "relevance"
    assert response.json()["order"] == "desc"


def test_null_page_size_and_sort_use_effective_defaults(discovery):
    client, app, calls, _ = discovery
    app.state.settings.search_page_size = 7
    response = client.post(
        "/projects/search",
        headers=HEADERS,
        json={"idea": "python web framework", "per_page": None, "sort": None},
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].url.params["per_page"] == "7"
    assert "sort" not in calls[0].url.params
    assert "order" not in calls[0].url.params
    assert response.json()["per_page"] == 7
    assert response.json()["sort"] == "relevance"
    assert response.json()["order"] == "desc"


@pytest.mark.parametrize("per_page", [1, 10, 100])
def test_per_page_parameter(discovery, per_page):
    client, _, calls, _ = discovery
    response = client.post(
        "/projects/search",
        headers=HEADERS,
        json={"idea": "python web framework", "per_page": per_page},
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].url.params["per_page"] == str(per_page)
    assert response.json()["per_page"] == per_page


@pytest.mark.parametrize("configured_size", [7, 20, 50])
def test_omitted_per_page_uses_configured_default(discovery, configured_size):
    client, app, calls, _ = discovery
    app.state.settings.search_page_size = configured_size
    response = client.post(
        "/projects/search", headers=HEADERS, json={"idea": "python web framework"}
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].url.params["per_page"] == str(configured_size)
    assert response.json()["per_page"] == configured_size


def test_explicit_per_page_overrides_configured_default(discovery):
    client, app, calls, _ = discovery
    app.state.settings.search_page_size = 7
    response = client.post(
        "/projects/search",
        headers=HEADERS,
        json={"idea": "python web framework", "per_page": 25},
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].url.params["per_page"] == "25"
    assert response.json()["per_page"] == 25


@pytest.mark.parametrize(
    "invalid",
    [
        {"per_page": 0},
        {"per_page": 101},
        {"page": 0},
        {"page": -1},
        {"page": 51},
        {"sort": "invalid"},
        {"order": "invalid"},
    ],
)
def test_invalid_search_parameters_never_call_github(discovery, invalid):
    client, _, calls, _ = discovery
    response = client.post(
        "/projects/search",
        headers=HEADERS,
        json={"idea": "python web framework", **invalid},
    )
    assert response.status_code == 422
    assert response.json()["detail"]
    assert calls == []


@pytest.mark.parametrize(
    ("page", "per_page"), [(1, 1), (50, 1), (50, 20), (10, 100), (34, 30)]
)
def test_search_accepts_pages_starting_inside_result_window(discovery, page, per_page):
    client, _, calls, _ = discovery
    response = client.post(
        "/projects/search",
        headers=HEADERS,
        json={"idea": "python web framework", "page": page, "per_page": per_page},
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].url.params["page"] == str(page)
    assert calls[0].url.params["per_page"] == str(per_page)
    assert response.json()["page"] == page
    assert response.json()["per_page"] == per_page


@pytest.mark.parametrize(("page", "per_page"), [(11, 100), (35, 30), (50, 100)])
def test_search_rejects_pages_outside_result_window(discovery, page, per_page):
    client, _, calls, _ = discovery
    response = client.post(
        "/projects/search",
        headers=HEADERS,
        json={"idea": "python web framework", "page": page, "per_page": per_page},
    )
    assert response.status_code == 422
    assert response.json()["detail"]
    assert calls == []


@pytest.mark.parametrize(("page", "status"), [(20, 200), (21, 422)])
def test_result_window_uses_configured_page_size_when_omitted(discovery, page, status):
    client, app, calls, _ = discovery
    app.state.settings.search_page_size = 50
    response = client.post(
        "/projects/search",
        headers=HEADERS,
        json={"idea": "python web framework", "page": page},
    )
    assert response.status_code == status
    if status == 200:
        assert len(calls) == 1
        assert calls[0].url.params["per_page"] == "50"
        assert response.json()["per_page"] == 50
    else:
        assert calls == []


@pytest.mark.parametrize("length", [255, 256, 257])
@pytest.mark.parametrize("joined", [False, True], ids=["single-word", "joined-words"])
def test_query_length_enforcement(discovery, length, joined):
    client, _, calls, _ = discovery
    keywords = "p" * (length - 2) + " q" if joined else "p" * length
    assert len(keywords) == length
    response = client.post("/projects/search", headers=HEADERS, json={"idea": keywords})
    if length > 256:
        assert response.status_code == 422
        assert "256" in response.json()["detail"]
        assert calls == []
    else:
        assert response.status_code == 200
        assert len(calls) == 1
        assert calls[0].url.params["q"] == (
            keywords + " in:name,description,readme is:public archived:false"
        )
        assert len(calls[0].url.params["q"]) > 256


@pytest.mark.parametrize("idea", ["", "   ", "x", "the and using", "..."])
def test_empty_or_nonmeaningful_idea_never_calls_github(discovery, idea):
    client, _, calls, _ = discovery
    response = client.post("/projects/search", headers=HEADERS, json={"idea": idea})
    assert response.status_code == 422
    assert calls == []


@pytest.mark.parametrize(("length", "status"), [(1000, 200), (1001, 422)])
def test_raw_idea_length_boundary_is_separate_from_keyword_limit(
    discovery, length, status
):
    client, _, calls, _ = discovery
    prefix = "python web framework django flask fastapi "
    idea = prefix + "z" * (length - len(prefix))
    assert len(idea) == length
    response = client.post("/projects/search", headers=HEADERS, json={"idea": idea})
    assert response.status_code == status
    if status == 200:
        assert len(calls) == 1
        assert calls[0].url.params["q"] == (
            "python web framework django flask fastapi"
            " in:name,description,readme is:public archived:false"
        )
    else:
        assert calls == []


def test_search_with_all_new_parameters(discovery):
    client, _, calls, _ = discovery
    response = client.post(
        "/projects/search",
        headers=HEADERS,
        json={
            "idea": "python web framework",
            "per_page": 25,
            "sort": "stars",
            "order": "asc",
            "page": 2,
        },
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].url.path == "/search/repositories"
    assert dict(calls[0].url.params) == {
        "q": "python web framework in:name,description,readme is:public archived:false",
        "per_page": "25",
        "sort": "stars",
        "order": "asc",
        "page": "2",
    }
    body = response.json()
    assert body["per_page"] == 25
    assert body["sort"] == "stars"
    assert body["order"] == "asc"
    assert body["page"] == 2


def test_search_default_response_shape_and_size_are_unchanged(discovery):
    client, _, calls, _ = discovery
    response = client.post(
        "/projects/search", headers=HEADERS, json={"idea": "python web framework"}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "items",
        "total",
        "incomplete",
        "page",
        "per_page",
        "sort",
        "order",
        "source",
    }
    assert body["page"] == 1
    assert body["per_page"] == 20
    assert body["sort"] == "relevance"
    assert body["order"] == "desc"
    assert body["source"] == "github_keywords"
    assert calls[0].url.params["per_page"] == "20"


def test_search_preserves_incomplete_flag_and_result_metadata(discovery):
    client, _, _, responses = discovery
    responses["/search/repositories"] = httpx.Response(
        200, json={"items": [REPO], "total_count": 1200, "incomplete_results": True}
    )
    response = client.post(
        "/projects/search",
        headers=HEADERS,
        json={
            "idea": "python web framework",
            "per_page": 10,
            "page": 3,
            "sort": "forks",
            "order": "asc",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1200
    assert body["incomplete"] is True
    assert body["source"] == "github_keywords"
    assert body["page"] == 3
    assert body["per_page"] == 10
    assert body["sort"] == "forks"
    assert body["order"] == "asc"
    assert [item["full_name"] for item in body["items"]] == ["octocat/compass"]


def test_search_accepts_full_page_larger_than_general_provider_budget(discovery):
    client, app, calls, responses = discovery
    items = [
        {**REPO, "id": index, "provider_metadata": "x" * 5400} for index in range(100)
    ]
    upstream = httpx.Response(
        200, json={"items": items, "total_count": 100, "incomplete_results": False}
    )
    assert app.state.settings.max_github_response < len(upstream.content) < 1048576
    responses["/search/repositories"] = upstream
    response = client.post(
        "/projects/search",
        headers=HEADERS,
        json={"idea": "python web framework", "per_page": 100},
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].url.params["per_page"] == "100"
    assert len(response.json()["items"]) == 100


@pytest.mark.parametrize(
    "discovery", [{"max_github_search_response": 1024}], indirect=True
)
def test_search_rejects_response_over_configured_search_budget(discovery):
    client, _, _, responses = discovery
    responses["/search/repositories"] = httpx.Response(
        200,
        json={
            "items": [{**REPO, "provider_metadata": "x" * 1100}],
            "total_count": 1,
            "incomplete_results": False,
        },
    )
    response = client.post(
        "/projects/search", headers=HEADERS, json={"idea": "python web framework"}
    )
    assert response.status_code == 503
    assert "items" not in response.json()


def test_search_empty_success_is_not_a_provider_failure(discovery):
    client, _, _, responses = discovery
    responses["/search/repositories"] = httpx.Response(
        200, json={"items": [], "total_count": 0, "incomplete_results": False}
    )
    response = client.post(
        "/projects/search", headers=HEADERS, json={"idea": "python web framework"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["incomplete"] is False


def test_search_omits_nonpublic_items_from_provider_response(discovery):
    client, _, _, responses = discovery
    private = {**REPO, "id": 2, "private": True}
    unspecified = {**REPO, "id": 3}
    del unspecified["private"]
    responses["/search/repositories"] = httpx.Response(
        200,
        json={
            "items": [REPO, private, unspecified],
            "total_count": 3,
            "incomplete_results": False,
        },
    )
    response = client.post(
        "/projects/search", headers=HEADERS, json={"idea": "python web framework"}
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [1]


@pytest.mark.parametrize(
    "upstream",
    [
        httpx.Response(429, headers={"Retry-After": "120"}),
        httpx.Response(
            403, headers={"Retry-After": "120", "X-RateLimit-Remaining": "0"}
        ),
        httpx.Response(503),
    ],
    ids=["rate-limited-429", "rate-limited-403", "unavailable"],
)
def test_search_provider_failures_are_not_empty_successes(discovery, upstream):
    client, _, _, responses = discovery
    responses["/search/repositories"] = upstream
    response = client.post(
        "/projects/search", headers=HEADERS, json={"idea": "python web framework"}
    )
    assert response.status_code == 503
    assert response.json()["detail"]
    assert "items" not in response.json()


@pytest.mark.parametrize("session", ["missing", "invalid", "expired"])
def test_search_requires_a_valid_app_session(discovery, session):
    client, app, calls, _ = discovery
    headers = HEADERS
    if session == "missing":
        headers = {}
    elif session == "invalid":
        headers = {"Authorization": "Bearer invalid-session"}
    else:
        with app.state.store.connect() as db:
            db.execute(
                "UPDATE sessions SET expires = 0 WHERE key = ?", (digest("session1"),)
            )
    response = client.post(
        "/projects/search", headers=headers, json={"idea": "python web framework"}
    )
    assert response.status_code == 401
    assert calls == []


def test_discovery_throttle_and_request_body_limit(discovery):
    client, app, calls, _ = discovery
    app.state.settings.discovery_rate_limit = 1
    assert client.get("/favourites", headers=HEADERS).status_code == 200
    assert client.get("/favourites", headers=HEADERS).status_code == 429
    app.state.settings.discovery_rate_limit = 100
    response = client.post("/projects/search", headers=HEADERS, content=b"x" * 5000)
    assert response.status_code == 413
    assert calls == []


def test_search_throttling_prevents_another_provider_request(discovery):
    client, app, calls, _ = discovery
    app.state.settings.discovery_rate_limit = 1
    body = {"idea": "python web framework"}
    assert (
        client.post("/projects/search", headers=HEADERS, json=body).status_code == 200
    )
    response = client.post("/projects/search", headers=HEADERS, json=body)
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert len(calls) == 1


def test_favourite_limit_missing_repository_and_provider_failure(discovery):
    client, app, _, responses = discovery
    app.state.settings.max_favourites = 1
    assert client.put("/favourites/octocat/compass", headers=HEADERS).status_code == 200
    responses["/repos/octocat/another"] = httpx.Response(
        200, json={**REPO, "full_name": "octocat/another"}
    )
    assert client.put("/favourites/octocat/another", headers=HEADERS).status_code == 409
    responses["/repos/octocat/compass"] = httpx.Response(404)
    assert client.get("/projects/octocat/compass", headers=HEADERS).status_code == 404
    responses["/repos/octocat/compass"] = httpx.Response(503)
    assert client.get("/projects/octocat/compass", headers=HEADERS).status_code == 503
    app.state.settings.token_encryption_key = ""
    second = create_app(
        Settings(_env_file=None, database_path=app.state.settings.database_path)
    )
    with TestClient(second) as no_cipher:
        assert (
            no_cipher.get("/projects/octocat/compass", headers=HEADERS).status_code
            == 503
        )


@pytest.mark.parametrize("page", [None, 1], ids=["idea-only", "idea-and-page"])
def test_basic_search_backward_compatibility(discovery, page):
    client, _, calls, _ = discovery
    body = {
        "idea": "  I want to build a Python web-app with Fast_API, Django, Flask, SQLite and Redis  "
    }
    if page is not None:
        body["page"] = page
    response = client.post("/projects/search", headers=HEADERS, json=body)
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].url.params["q"] == (
        "python web-app fast_api django flask sqlite"
        " in:name,description,readme is:public archived:false"
    )
    assert calls[0].url.params["per_page"] == "20"
    assert calls[0].url.params["page"] == "1"
    json_data = response.json()
    assert json_data["items"] == [
        {
            "id": 1,
            "name": "compass",
            "full_name": "octocat/compass",
            "owner": "octocat",
            "avatar_url": "https://avatars.githubusercontent.com/u/1",
            "description": "Find projects",
            "stars": 42,
            "language": "Python",
            "url": "https://github.com/octocat/compass",
        }
    ]
    assert json_data["total"] == 1
    assert json_data["incomplete"] is False
    assert json_data["page"] == 1
    assert json_data["source"] == "github_keywords"


@pytest.mark.parametrize(
    ("idea", "keywords"),
    [
        ("कार्य सूची साझा करना", "कार्य सूची साझा करना"),
        ("开源 项目 搜索", "开源 项目 搜索"),
        ("Café recipe planner", "café recipe planner"),
    ],
    ids=["devanagari", "cjk", "accented-latin"],
)
def test_search_keeps_non_ascii_keywords_intact(discovery, idea, keywords):
    client, _, calls, _ = discovery
    response = client.post("/projects/search", headers=HEADERS, json={"idea": idea})
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].url.params["q"] == (
        keywords + " in:name,description,readme is:public archived:false"
    )


@pytest.mark.parametrize(
    ("upstream", "retry_after"),
    [
        (httpx.Response(429, headers={"Retry-After": "120"}), "120"),
        (httpx.Response(429), "60"),
        (httpx.Response(503), None),
    ],
    ids=["retry-after", "no-timing-headers", "unavailable"],
)
def test_provider_rate_limits_tell_the_client_when_to_retry(
    discovery, upstream, retry_after
):
    client, _, _, responses = discovery
    responses["/search/repositories"] = upstream
    response = client.post(
        "/projects/search", headers=HEADERS, json={"idea": "python web framework"}
    )
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == retry_after


def test_provider_rate_limit_reset_becomes_retry_after(discovery):
    client, _, _, responses = discovery
    responses["/search/repositories"] = httpx.Response(
        403,
        headers={
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + 90),
        },
    )
    response = client.post(
        "/projects/search", headers=HEADERS, json={"idea": "python web framework"}
    )
    assert response.status_code == 503
    assert 80 <= int(response.headers["Retry-After"]) <= 91


def test_chunked_request_bodies_are_limited_and_otherwise_delivered(discovery):
    client, _, calls, _ = discovery

    def chunks(*parts):
        yield from parts

    response = client.post(
        "/projects/search",
        headers={**HEADERS, "Content-Type": "application/json"},
        content=chunks(b'{"idea": "python ', b'web framework"}'),
    )
    assert response.status_code == 200
    assert calls[0].url.params["q"].startswith("python web framework ")
    response = client.post(
        "/projects/search", headers=HEADERS, content=chunks(b"x" * 3000, b"x" * 3000)
    )
    assert response.status_code == 413
    assert len(calls) == 1
