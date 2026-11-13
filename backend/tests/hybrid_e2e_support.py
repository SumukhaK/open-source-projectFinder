"""Safety guards, settings and process helpers for the opt-in T26 lane."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from app.core.config import Settings

COLLECTION_PATTERN = re.compile(r"^reporadar_t26_[0-9a-f]{32}$")
PILOT_ROOT = Path("/home/sumukha/reporadar-t18-pilot")


def new_collection_name():
    return "reporadar_t26_" + uuid.uuid4().hex


def assert_owned_collection(name):
    if not isinstance(name, str) or not COLLECTION_PATTERN.fullmatch(name):
        raise ValueError("refusing to touch a collection not created by this lane")
    return name


def assert_temp_root(path):
    """Reject any cleanup target that is not a fresh directory below temp."""
    resolved = Path(path).expanduser().resolve()
    if resolved == PILOT_ROOT or PILOT_ROOT in resolved.parents:
        raise ValueError("refusing to clean the pilot catalogue")
    temp = Path(tempfile.gettempdir()).resolve()
    if resolved == temp or temp not in resolved.parents:
        raise ValueError("cleanup requires a directory below the system temp root")
    return resolved


def drop_owned_collection(client, name):
    assert_owned_collection(name)
    if client.has_collection(name):
        client.drop_collection(name)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _fernet_key(seed):
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


def settings_kwargs(root, collection):
    """Serializable settings shared by the test process and the server."""
    root = Path(root)
    return {
        "github_client_id": "fixture",
        "github_client_secret": "fixture",
        "token_encryption_key": _fernet_key(collection),
        "database_path": str(root / "auth.sqlite3"),
        "archive_database_path": str(root / "archive-db" / "catalogue.sqlite3"),
        "archive_content_path": str(root / "archive-content"),
        "archive_github_token": "fixture-archive-token",
        "archive_license_allowlist": ["MIT"],
        "archive_min_free_bytes": 0,
        "archive_github_timeout": 5,
        "milvus_profile": "cpu",
        "milvus_collection": collection,
        "milvus_timeout": 30,
        "milvus_build_timeout": 120,
        "hybrid_cursor_signing_key": hashlib.sha256(
            (collection + ":cursor").encode("utf-8")
        ).hexdigest(),
        "hybrid_build_wait_seconds": 5,
        "hybrid_search_budget": 20,
        "rate_limit": 10000,
        "discovery_rate_limit": 10000,
        "allowed_redirects": ["reporadar://auth/callback"],
    }


def milvus_token():
    token = os.environ.get("MILVUS_TOKEN", "")
    if not token:
        raise RuntimeError("MILVUS_TOKEN is required for the T26 hybrid lane")
    return token


def build_settings(root, collection):
    return Settings(
        _env_file=None,
        milvus_token=milvus_token(),
        **settings_kwargs(root, collection),
    )


def wait_health(base_url, *, timeout=60, log_path=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(base_url + "/health", timeout=1)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    detail = ""
    if log_path is not None and Path(log_path).exists():
        detail = Path(log_path).read_text(encoding="utf-8", errors="replace")[-4000:]
    raise RuntimeError(f"server did not become healthy\n{detail}")


def login(client, base_url):
    """Run the real PKCE fake-OAuth flow and return a bearer token."""
    verifier = base64.urlsafe_b64encode(os.urandom(48)).rstrip(b"=").decode("ascii")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    started = client.post(
        base_url + "/auth/github/start",
        json={"challenge": challenge, "redirect_uri": "reporadar://auth/callback"},
    )
    started.raise_for_status()
    state = started.json()["state"]
    callback = client.get(
        base_url + "/auth/github/callback",
        params={"state": state, "code": "test-code"},
        follow_redirects=False,
    )
    if callback.status_code != 303:
        raise RuntimeError("fake OAuth callback did not redirect")
    code = parse_qs(urlsplit(callback.headers["location"]).query)["code"][0]
    session = client.post(
        base_url + "/auth/session", json={"code": code, "verifier": verifier}
    )
    session.raise_for_status()
    return session.json()["token"]


class ServerProcess:
    """Run the real FastAPI app under uvicorn against the shared fixture stack."""

    def __init__(self, *, root, collection, private_ids=()):
        self.root = Path(root)
        self.collection = collection
        self.private_ids = tuple(sorted(int(value) for value in private_ids))
        self.port = free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.log_path = self.root / f"server-{self.port}.log"
        self.process = None
        self._log = None

    def __enter__(self):
        config = {
            "settings": settings_kwargs(self.root, self.collection),
            "private_ids": list(self.private_ids),
            "port": self.port,
        }
        config_path = self.root / f"server-{self.port}.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        script = Path(__file__).with_name("hybrid_e2e_server.py")
        self._log = self.log_path.open("wb")
        self.process = subprocess.Popen(
            [sys.executable, str(script), str(config_path)],
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=self._log,
            stderr=subprocess.STDOUT,
            env=dict(os.environ),
        )
        try:
            wait_health(self.base_url, log_path=self.log_path)
        except Exception:
            self.stop()
            raise
        return self

    def stop(self):
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        if self._log is not None:
            self._log.close()
            self._log = None
        self.process = None

    def __exit__(self, exc_type, exc, traceback):
        self.stop()
        return False
