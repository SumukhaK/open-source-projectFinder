import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager, suppress
from urllib.parse import urlencode

from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from app.api.archive import archive_router
from app.api.summary import SummaryPages, summary_router
from app.api.voice import voice_router
from app.core.config import Settings
from app.core.store import Store, digest
from app.discovery import credentials, discovery_router
from app.integrations.github import GitHubProvider, ProviderError
from app.integrations.llm import (
    LlmConfigurationError,
    build_client,
    probe_profile,
)
from app.services.hybrid_runtime import HybridRuntime


def challenge(verifier):
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )


class StartRequest(BaseModel):
    challenge: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    redirect_uri: str = Field(max_length=500)


class SessionRequest(BaseModel):
    code: str = Field(min_length=32, max_length=128)
    verifier: str = Field(pattern=r"^[A-Za-z0-9._~-]{43,128}$")


DISCOVERY_PATHS = ("/projects/", "/favourites")
ARCHIVE_PATHS = ("/v1/projects/", "/v1/archive/")
GUARDED_PATHS = DISCOVERY_PATHS + ARCHIVE_PATHS


class BodyLimit:
    """Buffer limited request bodies, including chunked ones, then replay them."""

    def __init__(self, app, paths, settings):
        self.app, self.paths, self.settings = app, paths, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(self.paths):
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return None
            body.extend(message.get("body", b""))
            if len(body) > self.settings.max_auth_body:
                response = JSONResponse({"detail": "Request too large"}, 413)
                return await response(scope, receive, send)
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay():
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        return await self.app(scope, replay, send)


def create_app(
    settings=None, transport=None, sleep=time.sleep, *, hybrid=None, llm=None
):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.llm_available = False
        app.state.llm_client = None
        app.state.llm_probe = None
        client = llm
        if client is None and settings.llm_active_profile:
            try:
                client = build_client(settings)
            except LlmConfigurationError as error:
                logging.getLogger("reporadar.llm").error(
                    json.dumps(
                        {
                            "event": "llm_unavailable",
                            "profile": settings.llm_active_profile,
                            "error": type(error).__name__,
                        }
                    )
                )
        app.state.llm_client = client
        if client is not None:

            async def run_probe():
                app.state.llm_available = await probe_profile(
                    client, client.profile_name, client.model
                )

            # Summaries are background: the probe must never delay a request.
            app.state.llm_probe = asyncio.create_task(run_probe())
        try:
            yield
        finally:
            probe = app.state.llm_probe
            if probe is not None and not probe.done():
                probe.cancel()
                with suppress(asyncio.CancelledError):
                    await probe

    app = FastAPI(title="RepoRadar API", lifespan=lifespan)
    store = Store(settings.database_path)
    app.state.settings, app.state.store = settings, store
    provider = GitHubProvider(
        settings.github_client_id,
        settings.github_client_secret,
        settings.github_callback_url,
        transport,
        sleep,
        settings,
    )
    hybrid = hybrid or HybridRuntime(settings, provider=provider)
    pages = SummaryPages(
        ttl=settings.hybrid_cursor_ttl_seconds,
        max_accounts=settings.hybrid_cursor_cache_size,
    )
    cipher = (
        Fernet(settings.token_encryption_key.encode())
        if settings.token_encryption_key
        else None
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Added before protection, so it runs inside it: throttling is checked first.
    app.add_middleware(BodyLimit, paths=("/auth/",) + GUARDED_PATHS, settings=settings)

    @app.middleware("http")
    async def protection(request, call_next):
        discovery = request.url.path.startswith(DISCOVERY_PATHS)
        archive = request.url.path.startswith(ARCHIVE_PATHS)
        voice = request.url.path == "/v1/voice/transcribe"
        if request.url.path.startswith("/auth/") or discovery or archive or voice:
            # Trust the actual connection, not user-supplied forwarding headers.
            ip = request.client.host if request.client else "unknown"
            guarded = discovery or archive or voice
            retry = store.throttle(
                digest(("discovery:" if guarded else "auth:") + ip),
                settings.discovery_rate_limit if guarded else settings.rate_limit,
                settings.rate_window,
            )
            if retry:
                detail = (
                    {
                        "code": "VOICE_RATE_LIMITED",
                        "message": "Too many requests. Try again later.",
                        "retryable": True,
                    }
                    if voice
                    else "Too many requests. Try again later."
                )
                return JSONResponse(
                    {"detail": detail},
                    429,
                    headers={"Retry-After": str(retry), "Cache-Control": "no-store"},
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.middleware("http")
    async def crash_reporting(request, call_next):
        try:
            return await call_next(request)
        except Exception as error:  # deliberate outer crash-redaction boundary
            # Do not log exception messages, request bodies, URLs, headers or tokens.
            logging.getLogger("reporadar.crashes").error(
                json.dumps(
                    {
                        "event": "backend_unhandled_exception",
                        "route": getattr(request.scope.get("route"), "path", "unknown"),
                        "error_type": type(error).__name__,
                    }
                )
            )
            return JSONResponse(
                {"detail": "An unexpected error occurred"},
                500,
                headers={"Cache-Control": "no-store"},
            )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        if request.url.path.startswith(ARCHIVE_PATHS):
            # Typed and value-free: never echo the submitted idea or filters.
            fields = [
                ".".join(
                    str(part)
                    for part in detail.get("loc", ())
                    if isinstance(part, (str, int))
                )[:120]
                for detail in error.errors()
            ]
            return JSONResponse(
                {
                    "detail": {
                        "code": "INVALID_REQUEST",
                        "message": "Check the search request.",
                        "retryable": False,
                        "fields": fields[:8],
                    }
                },
                422,
            )
        return JSONResponse({"detail": jsonable_encoder(error.errors())}, 422)

    def configured():
        if (
            not settings.github_client_id
            or not settings.github_client_secret
            or cipher is None
        ):
            raise HTTPException(503, "GitHub sign-in is not configured")

    def current(request):
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer ") or len(authorization) > 256:
            raise HTTPException(401, "Sign in required")
        token = authorization[7:]
        with store.connect() as db:
            row = db.execute(
                "SELECT users.github_id, login, avatar_url FROM sessions JOIN users USING (github_id) WHERE sessions.key = ? AND sessions.expires > ?",
                (digest(token), time.time()),
            ).fetchone()
        if not row:
            raise HTTPException(401, "Session expired. Sign in again.")
        return dict(row)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/auth/github/start")
    def start(body: StartRequest):
        configured()
        if body.redirect_uri not in settings.allowed_redirects:
            raise HTTPException(400, "Invalid callback destination")
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with store.connect() as db:
            db.execute(
                "INSERT INTO transactions VALUES (?, ?, ?, ?, ?)",
                (
                    digest(state),
                    cipher.encrypt(verifier.encode()).decode(),
                    body.challenge,
                    body.redirect_uri,
                    time.time() + settings.transaction_ttl,
                ),
            )
        query = urlencode(
            {
                "client_id": settings.github_client_id,
                "redirect_uri": settings.github_callback_url,
                "state": state,
                "code_challenge": challenge(verifier),
                "code_challenge_method": "S256",
            }
        )
        return {
            "authorization_url": "https://github.com/login/oauth/authorize?" + query,
            "state": state,
        }

    @app.get("/auth/github/callback")
    def callback(state: str = "", code: str = "", error: str = ""):
        configured()
        if len(state) > 128 or len(code) > 512:
            raise HTTPException(400, "Invalid authorization response")
        transaction = store.consume("transactions", state)
        if not transaction:
            raise HTTPException(400, "Invalid or expired login. Start again.")
        destination = transaction["redirect"]
        if error:
            return RedirectResponse(
                destination
                + "?"
                + urlencode({"error": "access_denied", "state": state}),
                303,
            )
        if not code:
            raise HTTPException(400, "Missing authorization code")
        try:
            credentials = provider.exchange(
                code, cipher.decrypt(transaction["verifier"].encode()).decode()
            )
            user = provider.user(credentials["access_token"])
        except ProviderError:
            return RedirectResponse(
                destination
                + "?"
                + urlencode({"error": "provider_unavailable", "state": state}),
                303,
            )
        expires_in = credentials.get("expires_in")
        ttl = settings.session_ttl
        if expires_in is not None:
            if type(expires_in) is not int or expires_in <= 60:
                return RedirectResponse(
                    destination
                    + "?"
                    + urlencode({"error": "provider_unavailable", "state": state}),
                    303,
                )
            ttl = min(ttl, expires_in - 60)
        code = secrets.token_urlsafe(32)
        # Save only required identity and encrypted provider credentials, including refresh token if issued.
        encrypted = cipher.encrypt(json.dumps(credentials).encode()).decode()
        with store.connect() as db:
            db.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?) ON CONFLICT(github_id) DO UPDATE SET login=excluded.login, avatar_url=excluded.avatar_url, credentials=excluded.credentials",
                (user["id"], user["login"], user.get("avatar_url", ""), encrypted),
            )
            db.execute(
                "INSERT INTO handoffs VALUES (?, ?, ?, ?, ?)",
                (
                    digest(code),
                    user["id"],
                    transaction["challenge"],
                    time.time() + settings.handoff_ttl,
                    ttl,
                ),
            )
        return RedirectResponse(
            destination + "?" + urlencode({"code": code, "state": state}), 303
        )

    @app.post("/auth/session")
    def session(body: SessionRequest):
        handoff = store.consume("handoffs", body.code)
        if not handoff or not hmac.compare_digest(
            challenge(body.verifier), handoff["challenge"]
        ):
            raise HTTPException(400, "Invalid or expired login. Start again.")
        token = secrets.token_urlsafe(32)
        expires = time.time() + handoff["session_ttl"]
        with store.connect() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                (digest(token), handoff["github_id"], expires),
            )
            user = dict(
                db.execute(
                    "SELECT github_id, login, avatar_url FROM users WHERE github_id = ?",
                    (handoff["github_id"],),
                ).fetchone()
            )
        return {"token": token, "expires_at": expires, "user": user}

    @app.get("/auth/me")
    def me(request: Request):
        return current(request)

    @app.post("/auth/logout", status_code=204)
    def logout(request: Request):
        current(request)
        with store.connect() as db:
            db.execute(
                "DELETE FROM sessions WHERE key = ?",
                (digest(request.headers["Authorization"][7:]),),
            )
        return Response(status_code=204)

    app.include_router(discovery_router(store, provider, cipher, current, settings))
    app.include_router(voice_router(settings, current))
    app.include_router(
        archive_router(
            settings, current, credentials(store, cipher, current), hybrid, pages
        )
    )
    app.include_router(summary_router(settings, current, pages))
    return app
