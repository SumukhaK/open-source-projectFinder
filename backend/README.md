# RepoRadar backend

FastAPI GitHub signup/login, persistent rate limits, encrypted provider credentials and revocable app sessions. Search and ingestion remain planned.

## Setup

Use Python 3.11. From this directory:

```sh
python -m venv .venv
# Activate .venv using the command for your shell.
python -m pip install -r requirements.lock.txt
```

Copy `.env.example` to the ignored `.env`. Register a GitHub OAuth app with your backend URL as its authorization callback (locally `http://localhost:8000/auth/github/callback`). Set `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` locally. Generate a Fernet key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and save it as `TOKEN_ENCRYPTION_KEY`. Keep this key stable, private and backed up: changing it prevents decryption of stored provider credentials. Never paste secrets into issues or chat.

Run:

```sh
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
python -m pytest tests -q
ruff check .
ruff format --check .
```

Configure HTTPS and a reachable callback for device testing/deployment. Bind to the required interface deliberately. Behind a proxy, allow only explicitly trusted proxy addresses; never accept arbitrary forwarded client IPs. Disable/redact auth query strings in proxy logs as well. Put a body-size limit and request timeout at the ingress. Use deployment filesystem permissions to protect `.env` and the database directory.

## Configuration and storage

All backend settings live in `app/core/config.py`. `DATABASE_PATH` defaults to ignored `data/auth.sqlite3`. SQLite transactions make single-use handoffs and rate counts atomic across processes on one host. This is not a distributed rate limiter; migrate to shared PostgreSQL/Redis before multiple deployment hosts. Rate limits default to 20 auth requests per connection IP per 60 seconds, configurable through `RATE_LIMIT`/`RATE_WINDOW`. NAT users share this quota. Authentication bodies are capped at 4096 bytes.

Authentication can run locally without credentials for health checks; login then returns 503. An invalid configured encryption key fails startup. No production credentials or fake provider are included. The GitHub simulator exists only under tests.

## API

- `POST /auth/github/start`: app PKCE challenge and exact allowlisted return URI; returns GitHub authorization URL and state.
- `GET /auth/github/callback`: consumes state, exchanges GitHub code and verifies identity; redirects with a 60-second, single-use handoff bound to the app's PKCE proof.
- `POST /auth/session`: exchanges handoff/proof for a separate RepoRadar session and account.
- `GET /auth/me`: account for a valid Bearer RepoRadar session.
- `POST /auth/logout`: revokes the current session.

See [authentication design](../docs/AUTHENTICATION.md). Do not use GitHub access tokens as app Bearer tokens.

## Quality pipeline

The lock includes patched cryptography and pinned free test/security tools. pytest-cov enforces the application coverage policy through scripts/quality.py; Ruff and Bandit check code. pip-audit scans the pinned dependency graph. Unhandled request crashes emit only a sanitized event, declared route template and exception class, without private error/request data. See [quality pipeline](../docs/QUALITY_PIPELINE.md) for local commands, coverage gates and limits of local crash capture.

## Discovery integration
Authenticated endpoints: `POST /projects/search` accepts `{idea, page}` and optional `per_page`, `sort` and `order`; `GET /projects/{owner}/{name}` assembles public repository metadata, up to three releases, languages, README and twelve contributors. `GET /favourites`, `PUT /favourites/{owner}/{name}` and `DELETE /favourites/{owner}/{name}` persist app-local favourites per GitHub identity. Saving a favourite does not star it on GitHub.

The standalone keyword search controls are implemented and verified by contract tests. Ordinary ideas retain the existing six-keyword normalization and public-only/unarchived repository scope. Missing GitHub sections return empty collections so the UI can omit them. Provider errors remain explicit errors rather than zero results. Favourite cards are saved snapshots; details fetch current public data. Milvus semantic matching, advanced query syntax and relevance evaluation remain planned.

| Search field | Accepted values and default |
| --- | --- |
| `idea` | 2-1,000 characters; retained keywords must fit 256 characters, excluding the fixed qualifiers |
| `page` | 1-50, default 1; starting offset must be below 1,000 using the effective page size |
| `per_page` | 1-100; omission or null uses `Settings.search_page_size`, default 20 |
| `sort` | `stars`, `forks`, `updated`; omission or null uses best match and omits upstream sorting parameters |
| `order` | `desc` or `asc`, default `desc`; ignored without an explicit sort |

Existing response fields are preserved; `per_page`, `sort` and `order` report effective values. Best match is represented as `sort: "relevance", order: "desc"`. Invalid input and pages return 422 before calling GitHub; an overlong keyword query is rejected without truncation. Search responses have a separate configurable `MAX_GITHUB_SEARCH_RESPONSE` budget of 1 MiB (1 KiB-2 MiB allowed); other GitHub reads retain the general 512 KiB default. Oversized provider responses remain explicit errors. Limits, timeouts and retries are centralized in Settings.

Contract tests use real API/session/storage/provider code with a mocked HTTP transport. A single direct public GitHub search verified that an ordinary 100-item payload exceeded the old general budget; this does not validate the application's live OAuth search flow or semantic relevance. Source: [GitHub Search API](https://docs.github.com/en/rest/search/search).
