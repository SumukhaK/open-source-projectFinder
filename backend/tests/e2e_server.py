"""Test-only GitHub simulator; never deployed or enabled in the application."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import uvicorn
from app.core.config import Settings
from app.main import create_app
from cryptography.fernet import Fernet


def provider(request):
    if request.url.path.endswith("access_token"):
        return httpx.Response(200, json={"access_token": "test-provider-token"})
    return httpx.Response(200, json={"id": 123, "login": "octocat", "avatar_url": ""})


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        settings = Settings(
            github_client_id="fixture",
            github_client_secret="fixture",
            token_encryption_key=Fernet.generate_key().decode(),
            database_path=str(Path(directory) / "auth.db"),
            rate_limit=100,
        )
        app = create_app(settings, httpx.MockTransport(provider), sleep=lambda _: None)
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=int(sys.argv[1]),
            access_log=False,
            log_level="error",
        )
