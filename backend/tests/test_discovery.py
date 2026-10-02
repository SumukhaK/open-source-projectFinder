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
def discovery(tmp_path):
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


def test_discovery_throttle_and_request_body_limit(discovery):
    client, app, _, _ = discovery
    app.state.settings.discovery_rate_limit = 1
    assert client.get("/favourites", headers=HEADERS).status_code == 200
    assert client.get("/favourites", headers=HEADERS).status_code == 429
    app.state.settings.discovery_rate_limit = 100
    assert (
        client.post(
            "/projects/search", headers=HEADERS, content=b"x" * 5000
        ).status_code
        == 413
    )


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
