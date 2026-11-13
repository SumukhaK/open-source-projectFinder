"""Test-only uvicorn entry point for the opt-in T26 hybrid lane.

The process serves the real FastAPI app with the real archive catalogue and
real Milvus collection, while GitHub traffic is a deterministic MockTransport.
It is never imported by the application or the default test suite.
"""

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import uvicorn
from app.core.config import Settings
from app.integrations.archive_github import ArchiveGitHubReader
from app.integrations.github import GitHubProvider
from app.main import create_app
from app.services.hybrid_runtime import HybridRuntime
from hybrid_e2e_fixtures import FixtureEmbeddings, FixtureTransport
from hybrid_e2e_support import milvus_token
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware


def build(config):
    settings = Settings(
        _env_file=None, milvus_token=milvus_token(), **config["settings"]
    )
    transport = httpx.MockTransport(FixtureTransport(private_ids=config["private_ids"]))
    provider = GitHubProvider(
        settings.github_client_id,
        settings.github_client_secret,
        settings.github_callback_url,
        transport,
        lambda _: None,
        settings,
    )
    reader = ArchiveGitHubReader(
        token="fixture-archive-token",
        transport=transport,
        settings=settings,
        sleep=lambda _: None,
    )
    runtime = HybridRuntime(
        settings,
        provider=provider,
        archive_reader=reader,
        embeddings=FixtureEmbeddings(),
    )
    app = create_app(settings, transport, sleep=lambda _: None, hybrid=runtime)

    # The production crash boundary redacts tracebacks, so this test-only
    # process prints the real one. The middleware is appended last to run
    # inside that boundary and must never be part of the application.
    async def traceback_surface(request, call_next):
        try:
            return await call_next(request)
        except Exception:
            traceback.print_exc()
            raise

    app.user_middleware.append(
        Middleware(BaseHTTPMiddleware, dispatch=traceback_surface)
    )
    return app


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as handle:
        config = json.load(handle)
    uvicorn.run(
        build(config),
        host="127.0.0.1",
        port=int(config["port"]),
        log_level="warning",
    )
