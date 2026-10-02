import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from app.core.config import Settings
from app.main import create_app
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

VERIFIER = "a" * 43
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
    .decode()
    .rstrip("=")
)


@pytest.fixture
def setup(tmp_path):
    calls = []

    def provider(request):
        calls.append(request)
        if request.url.path.endswith("access_token"):
            return httpx.Response(
                200, json={"access_token": "provider-secret", "token_type": "bearer"}
            )
        return httpx.Response(
            200,
            json={
                "id": 123,
                "login": "octocat",
                "avatar_url": "https://github.com/avatar.png",
            },
        )

    settings = Settings(
        github_client_id="test-id",
        github_client_secret="test-secret",
        token_encryption_key=Fernet.generate_key().decode(),
        database_path=str(tmp_path / "auth.db"),
        rate_limit=100,
    )
    app = create_app(settings, httpx.MockTransport(provider), sleep=lambda _: None)
    with TestClient(app) as client:
        yield client, app, calls


def begin(client):
    response = client.post(
        "/auth/github/start",
        json={"challenge": CHALLENGE, "redirect_uri": "reporadar://auth/callback"},
    )
    assert response.status_code == 200
    data = response.json()
    query = parse_qs(urlparse(data["authorization_url"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert "scope" not in query
    return data["state"]


def handoff(client, state):
    response = client.get(
        "/auth/github/callback",
        params={"state": state, "code": "github-code"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return parse_qs(urlparse(response.headers["location"]).query)["code"][0]


def login(client):
    code = handoff(client, begin(client))
    response = client.post("/auth/session", json={"code": code, "verifier": VERIFIER})
    assert response.status_code == 200
    return response.json(), code


def test_signup_restore_logout_and_encrypted_credentials(setup):
    client, app, _calls = setup
    session, code = login(client)
    headers = {"Authorization": "Bearer " + session["token"]}
    assert session["user"]["github_id"] == 123
    assert client.get("/auth/me", headers=headers).json()["login"] == "octocat"
    assert (
        client.post(
            "/auth/session", json={"code": code, "verifier": VERIFIER}
        ).status_code
        == 400
    )
    from pathlib import Path

    raw = Path(app.state.settings.database_path).read_bytes()
    assert b"provider-secret" not in raw
    assert session["token"].encode() not in raw
    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401
    again, _ = login(client)
    assert again["user"]["github_id"] == 123


def test_state_replay_bad_proof_and_redirect_validation(setup):
    client, _, calls = setup
    assert (
        client.post(
            "/auth/github/start",
            json={"challenge": CHALLENGE, "redirect_uri": "https://evil.example"},
        ).status_code
        == 400
    )
    assert (
        client.get(
            "/auth/github/callback", params={"state": "invalid", "code": "x"}
        ).status_code
        == 400
    )
    assert not calls
    state = begin(client)
    code = handoff(client, state)
    assert (
        client.get(
            "/auth/github/callback", params={"state": state, "code": "x"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/auth/session", json={"code": code, "verifier": "b" * 43}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/auth/session", json={"code": code, "verifier": VERIFIER}
        ).status_code
        == 400
    )


def test_expired_state_and_session(setup):
    client, app, _ = setup
    state = begin(client)
    with app.state.store.connect() as db:
        db.execute("UPDATE transactions SET expires = 0")
    assert (
        client.get(
            "/auth/github/callback", params={"state": state, "code": "x"}
        ).status_code
        == 400
    )
    session, _ = login(client)
    with app.state.store.connect() as db:
        db.execute("UPDATE sessions SET expires = 0")
    assert (
        client.get(
            "/auth/me", headers={"Authorization": "Bearer " + session["token"]}
        ).status_code
        == 401
    )


def test_rate_limiter_persists_and_ignores_spoofed_forwarding(setup):
    client, app, _ = setup
    app.state.settings.rate_limit = 2
    for _ in range(2):
        assert (
            client.post(
                "/auth/github/start",
                json={
                    "challenge": CHALLENGE,
                    "redirect_uri": "reporadar://auth/callback",
                },
            ).status_code
            == 200
        )
    response = client.post(
        "/auth/github/start", json={}, headers={"X-Forwarded-For": "1.2.3.4"}
    )
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 60


def test_denial_and_missing_configuration(setup):
    client, app, _calls = setup
    state = begin(client)
    response = client.get(
        "/auth/github/callback",
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )
    assert "error=access_denied" in response.headers["location"]
    assert not _calls
    app.state.settings.github_client_secret = ""
    assert (
        client.post(
            "/auth/github/start",
            json={"challenge": CHALLENGE, "redirect_uri": "reporadar://auth/callback"},
        ).status_code
        == 503
    )


def test_expired_handoff_payload_limits_and_security_headers(setup):
    client, app, _ = setup
    code = handoff(client, begin(client))
    with app.state.store.connect() as db:
        db.execute("UPDATE handoffs SET expires = 0")
    assert (
        client.post(
            "/auth/session", json={"code": code, "verifier": VERIFIER}
        ).status_code
        == 400
    )
    response = client.post("/auth/github/start", content="x" * 4097)
    assert response.status_code == 413
    response = client.get("/health")
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get("/auth/me").status_code == 401


def test_store_rate_limits_survive_reopening_and_consumption_is_atomic(setup):
    from concurrent.futures import ThreadPoolExecutor

    from app.core.store import Store

    client, app, _ = setup
    store = Store(app.state.settings.database_path)
    assert store.throttle("persistent-key", 1, 60) is None
    reopened = Store(app.state.settings.database_path)
    assert reopened.throttle("persistent-key", 1, 60) is not None
    state = begin(client)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _: store.consume("transactions", state), range(2))
        )
    assert sum(result is not None for result in results) == 1


def test_one_use_store_rejects_non_allowlisted_tables(setup):
    _, app, _ = setup
    with pytest.raises(ValueError, match="Unknown one-use table"):
        app.state.store.consume("users", "unused")
