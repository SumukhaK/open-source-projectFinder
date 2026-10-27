# RepoRadar backend

## Dependency security maintenance

The Python lock pins the published security fixes in certifi 2026.10.19, filelock 4.2.1, opentelemetry-api 1.45.1 and setuptools 84.1.0. Regenerate it from the tested isolated environment; do not upgrade the whole dependency tree to resolve one advisory.

Mobile scopes a Zod 4.6.6 override to Expo CLI while that CLI declares Zod 3. Regression tests resolve the CLI's actual validator and exercise its plugin metadata/output and MCP command schemas. They prove bounded oversized arrays reject before parsing every element; this does not claim unbounded arrays have a universal memory cap. Recheck the override and those compatibility tests on Expo upgrades, and remove it when the upstream dependency supports a patched version directly. No new audit exception or weaker gate is part of this fix. The existing node-forge 1.4.0 exception still requires review before its 2026-11-01 expiry.

Primary sources: [certifi advisory](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2), [filelock release](https://github.com/tox-dev/filelock/releases/tag/4.2.1), [OpenTelemetry advisory](https://github.com/open-telemetry/opentelemetry-python/security/advisories/GHSA-xcq7-p3pf-p88h), [setuptools advisory](https://github.com/advisories/GHSA-xmj3-9gf7-h52w), [Zod advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) and [Zod 3 maintenance discussion](https://github.com/colinhacks/zod/issues/6653).

FastAPI GitHub signup/login, persistent rate limits, encrypted provider credentials and revocable app sessions, plus authenticated public GitHub keyword search, repository details and app-local favourites. A CPU embedding adapter and manifest are implemented but not yet wired into search; semantic (Milvus) search and repository ingestion remain planned.

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

## CPU embeddings (optional)

The T02 adapter is `app/services/embeddings.py`; its immutable manifest is `app/services/embedding_model.json`. It pins `intfloat/multilingual-e5-small` at revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, produces normalized 384-dimensional vectors, adds `query: ` / `passage: ` prefixes, rejects caller prefixes and inputs over 512 tokens after prefixing, and loads safe weights on CPU with `trust_remote_code=False`. It is not imported by an API route yet.

Loading is offline-only. The adapter resolves the cached snapshot with `local_files_only=True`, verifies the manifest SHA-256 values for `model.safetensors` and `tokenizer.json`, then loads from that verified path with `use_safetensors=True`. Serving and worker processes must use `HF_HUB_OFFLINE=1` so a request cannot trigger a model download; set it after the explicit setup step below.

The embedding stack is intentionally separate from `requirements.lock.txt` so the main CI lock does not install PyTorch. In a Python 3.11+ environment, install once:

```sh
python -m pip install -r requirements.embeddings.lock.txt
```

Then perform the explicit one-time download with network access:

```sh
env -u HF_HUB_OFFLINE python ../scripts/embeddings_smoke.py --download --repeats 3
```

For serving/worker processes and the offline smoke run:

```sh
export HF_HUB_OFFLINE=1
python ../scripts/embeddings_smoke.py --repeats 3
```

The setup downloads only the pinned safetensors weights and model/tokenizer support files, excluding alternate pickle/export weights. After setup, the smoke command is offline-only and fails with a clear setup message if the pinned snapshot is missing. The smoke command verifies both cached hashes and prints CPU dimensions, norms, timings and memory as JSON. Unit tests use fake encoders and do not download models. Input rejections use `UnsupportedInput`; model/cache/manifest faults use `EmbeddingError`. T13 must map unsupported input to semantic `query_not_supported` while retaining live GitHub results; no API wiring is included here. Do not persist user ideas or embeddings. See [T02 evidence](../execution-plans/hybrid-search/T02_EVIDENCE.md).

## Configuration and storage

All backend settings live in `app/core/config.py`. `DATABASE_PATH` defaults to ignored `data/auth.sqlite3`. SQLite transactions make single-use handoffs and rate counts atomic across processes on one host. This is not a distributed rate limiter; migrate to shared PostgreSQL/Redis before multiple deployment hosts. Rate limits default to 20 auth requests per connection IP per 60 seconds, configurable through `RATE_LIMIT`/`RATE_WINDOW`. NAT users share this quota. Authentication and discovery request bodies, including chunked bodies, are capped at 4096 bytes (`MAX_AUTH_BODY`) by a small ASGI middleware that runs after throttling.

Authentication can run locally without credentials for health checks; login then returns 503. An invalid configured encryption key fails startup. No production credentials or fake provider are included. The GitHub simulator exists only under tests.

## Archive catalogue (T03, merged)

`app/core/archive_store.py` provides an opt-in catalogue, independent of auth. It is not constructed by the app factory and creates no database during ordinary API startup. It uses only standard-library `sqlite3`; no ORM or new dependency is installed. `ARCHIVE_DATABASE_PATH` and `ARCHIVE_CONTENT_PATH` must be separate from auth, including auth/archive journal sidecars and hardlink aliases. `ARCHIVE_BUSY_TIMEOUT_MS` defaults to 5000 (1-30000 allowed).

Run with a WAL-patched interpreter on a Linux-native WSL filesystem, never `/mnt/c`, `/mnt/e`, a network share or simultaneous Windows/Linux access. The verified local worker is `/home/sumukha/reporadar-worker-venv/bin/python` (Python 3.11.17, SQLite 3.53.1). Native Windows archive opening is refused; auth remains supported as before. The shared `app/core/sqlite_runtime.py::wal_is_fixed` checks the linked SQLite on every catalogue connection before opening/creating a file. It accepts 3.51.3+ and the documented 3.50.7/3.44.6 backport families; 3.46.1 is refused. Do not override the gate or replace system libraries.

The `.env.example` archive paths are relative to the working directory. If the checkout is under `/mnt/c` or `/mnt/e`, set absolute Linux-native archive paths as below before initializing it. Backend CI downloads the pinned CPython 3.11.17 standalone build from release `20261021`, verifies its SHA-256, and fails before testing unless its linked SQLite passes the same gate. The existing pip cache remains enabled. Archive tests skip only non-POSIX platforms; an unpatched SQLite on Linux fails rather than skipping tests.

From the checkout's `backend/` directory in WSL, an operator can initialize an empty catalogue explicitly:

```sh
export ARCHIVE_DATABASE_PATH="$HOME/.local/share/reporadar/archive/catalogue.sqlite3"
export ARCHIVE_CONTENT_PATH="$HOME/.local/share/reporadar/archive/content"
/home/sumukha/reporadar-worker-venv/bin/python -c 'from app.core.config import Settings; from app.core.archive_store import ArchiveStore; ArchiveStore(Settings()); print("Archive catalogue v1 ready")'
```

New catalogue directories are 0700; database/WAL/SHM files are 0600. Shared existing directories/files are refused without changing their permissions. Choose a new private directory instead of changing a shared parent. The content path is reserved configuration only: T03 creates no raw-content directory/files.

`ArchiveStore(Settings()).connect(write=True)` yields a short `BEGIN IMMEDIATE` write transaction; `connect()` yields a deferred transaction with a stable reader snapshot. Both commit on success, roll back on error and close the connection. Keep network calls, parsing, embedding and user work outside these contexts. Readers must also use the patched runtime. The lock wait is bounded by the configured timeout; a lock error must not trigger a reset.

Schema v1 has only `archive_repositories`, `archive_documents` and `archive_chunks`, with numeric repository IDs, unique revisions/chunk ordinals, foreign keys and pending/published/superseded document states. Repository metadata is an object-shaped JSON column; document provenance/hash/version fields remain nullable until acquisition supplies them. Renames update `full_name` for the same ID; names are deliberately not unique because an old name may be reused by a different repository. Active revision references are constrained to the same repository. T08 must enforce publication readiness before switching that pointer; T03 does not claim SQL/Milvus atomic publication.

Migrations are ordered in `MIGRATIONS`, use transactional individual statements (not implicitly committing `executescript`) and advance `PRAGMA user_version` only atomically. `PRAGMA application_id` identifies this catalogue. Repeated initialization preserves records; unknown databases and future schema versions are refused without migration. A failed first migration rolls back every table and version marker and can be retried. There is no destructive reset or downgrade command.

Future schema changes must append migration 2 or later; never edit migration 1 after delivery. Existing catalogues must upgrade through the same versioned path as new installations.

Rollback: stop catalogue consumers and revert the T03 code; the existing API continues using its unchanged auth DB. Preserve the catalogue and any WAL/SHM together. Before a future upgrade, take a consistent snapshot using SQLite's backup API rather than copying a live main DB file alone. T21 owns encrypted backup/restore tooling. Never point the catalogue at auth, delete the database to bypass a migration error, or move a live WAL database between filesystems.

Evidence and reproducible tests: [T03 evidence](../execution-plans/hybrid-search/T03_EVIDENCE.md). Ingestion, raw-file writes, vector publication, queues, APIs and scheduling are later tasks.

## Archive GitHub reads (T04, merged)

`app/integrations/archive_github.py` is a worker-only reader. It is not imported by the API app and does not change the OAuth provider in `app/integrations/github.py`. It requires a dedicated `ARCHIVE_GITHUB_TOKEN` with public-read access; never configure an end-user OAuth token or reuse `GITHUB_CLIENT_SECRET`. The reader refuses to start without its own token and never logs it or forwards it to another origin.

`ARCHIVE_GITHUB_API_URL` must be an HTTPS origin (default `https://api.github.com`). Redirects are followed only within that origin, with `ARCHIVE_GITHUB_MAX_REDIRECTS` (default 3, 0-5). `ARCHIVE_GITHUB_TIMEOUT` defaults to 10 seconds (greater than 0, up to 30), `ARCHIVE_GITHUB_ATTEMPTS` to 3 (1-5), `ARCHIVE_GITHUB_METADATA_BYTES` to 512 KiB (1 KiB-2 MiB), `ARCHIVE_GITHUB_README_BYTES` to 256 KiB (1 KiB-1 MiB) and `ARCHIVE_GITHUB_RETRY_MAX_WAIT` to 5 seconds (greater than 0, up to 60).

The reader fetches repository metadata, verifies the returned numeric ID against the expected ID (including redirects), rejects non-public metadata and then fetches `/readme`. A metadata 404 is ambiguous (private, transferred, inaccessible or deleted) and raises `RepositoryNotFound`; it is not proof of deletion. After verified metadata, a README 404 means `readme_missing=True`. README JSON/base64 is decoded with strict size, padding and UTF-8 checks, and the decoded bytes must match the Git blob SHA retained as provenance. `fetch_blob` accepts only a 40-character file blob SHA and uses `/git/blobs/{sha}`, never a branch or commit ref, and verifies the decoded bytes against that SHA. If the README has no inline content, the caller can fetch that immutable blob separately.

Responses are typed with status, URL, headers, body, request ID, ETag, Last-Modified, retry-at and encoded/decoded byte counts. Bodies are streamed with encoded/decoded limits checked per decoded chunk before accumulation; a single compressed network chunk can transiently inflate before the cap is checked. Conditional `304` responses return the supplied cached metadata/README/blob only when it matches the expected repository ID/blob SHA; otherwise `CacheMiss` or a request error is raised. Long rate-limit waits (429, or 403 with exhausted quota or a rate-limit message) and long 5xx `Retry-After` values become `retry_at` values instead of sleeps. A headerless rate-limit `403` defaults to a 60-second retry time; plain or malformed `403` bodies remain `ArchiveForbidden`. Short 5xx waits honor the larger of provider delay and exponential backoff, capped by the configured wait limit. `401` stops the run; bounded 5xx and network failures are retried.

The reader does not crawl links, clone repositories, download arbitrary URLs or fetch submodules. It is not wired into an API route or worker yet; persistence, scheduling and ingestion are later tasks. Evidence: [T04 evidence](../execution-plans/hybrid-search/T04_EVIDENCE.md).

## Content preparation (T05, merged)

`app/services/archive_index.py::prepare_repository` prepares already-fetched metadata and decoded README bytes in memory. Reuse a loaded T02 `EmbeddingAdapter`; preparation only calls its real tokenizer counter, never vector inference. No model download, repository request, file write or database operation occurs here.

```python
from app.services.archive_index import prepare_repository

prepared = prepare_repository(
    {
        "id": 42,
        "full_name": "example/compass",
        "description": "Offline maps",
        "topics": ["maps"],
        "language": "Python",
    },
    b"# Features\nShared route planning.",
    adapter=adapter,  # the existing, loaded T02 adapter
    source_truncated=False,
)
# A later ingestion task embeds [chunk.text for chunk in prepared.chunks]
# with kind="passage"; text does not already contain the E5 prefix.
```

Metadata gets a strict 16 KiB budget. README input is capped at 256 KiB; at most 65,536 decoded characters are parsed with the already-locked `markdown-it-py==4.2.0`. HTML-bearing prose, images and navigation are discarded; ordinary Markdown/code becomes inert text. Output starts with an overview and continues through README sections in source order, at most eight chunks with zero overlap. Actual content counts are at most 400 tokens and final prefixed/titled counts at most 512. If a body chunk would end mid-word, it retreats to the nearest whitespace within the final 20% of the fitted piece, then rechecks both token budgets. Without a nearby boundary, it keeps the hard cut for CJK and long URLs/tokens. The next piece starts after whitespace; words remain in source order. `CHUNKER_VERSION` remains `sections-v1` because no content has been ingested. Bounds live in `core/config.py` and are part of the versioned format, not environment switches.

Inspect `readme_status` and `omissions`; metadata-only, parser-clipped and chunk-capped output must not be represented as a complete README. `semantic_hash` includes normalized semantic metadata/content, model identity and preparation versions, but not stars. Chunk keys also bind numeric repository ID and ordinal. `text_hash` is the UTF-8 SHA-256 of unprefixed chunk text; embedding reuse additionally requires the same model/preparation contract. Future rule changes need a new normalizer/chunker version and regenerated content. T08 owns obsolete-vector cleanup/publication; this function does not perform either.

Rollback is a code revert with no schema/data migration. Render output as plain text, never as trusted HTML. See [T05 evidence](../execution-plans/hybrid-search/T05_EVIDENCE.md) for tests, real-tokenizer verification, explicit clipping tradeoffs and remaining integration limits.

## Raw content and provenance (T06, merged)

`app/services/archive_content.py::persist_revision` writes bounded raw/normalized files and one `pending` catalogue revision in the same caller-owned write transaction. It requires `ArchiveStore.connect(write=True)` and schema v2. It does not call GitHub, embed text, write `archive_chunks`, publish a revision or use Milvus; T08/T09 own those steps.

```python
from app.core.archive_store import ArchiveStore
from app.services.archive_content import ArchiveContentStore, persist_revision

content = ArchiveContentStore(settings)
with ArchiveStore(settings).connect(write=True) as db:
    stored = persist_revision(
        db,
        content,
        metadata=repository_metadata,  # T04 RepositoryMetadata
        prepared=prepared,  # T05 PreparedRepository
        readme=readme_document,  # T04 ReadmeDocument, or None when absent
        source_ref=resolved_commit_sha,  # optional 40-hex commit SHA
        source_truncated=False,
    )
# stored.revision == prepared.semantic_hash; state is "pending"
```

Files live under `ARCHIVE_CONTENT_PATH` as `<kind>/<sha256[:2]>/<sha256>` for `raw` and `normalized`. Raw is the exact decoded README UTF-8 bytes. Normalized is canonical JSON (`prepared-v1`) with repository ID, semantic hash, normalizer/chunker/model versions, README status, omission flags and chunk text/hashes. `ARCHIVE_CONTENT_MAX_BYTES` is a defensive 1 MiB per-file bound; acquisition and preparation keep their smaller limits. No user query, idea, transcript, embedding or token is stored.

Schema v2 appends `normalized_path`, `source_endpoint`, `source_ref`, `blob_sha`, `etag`, `last_modified`, `raw_bytes` and `truncated` to `archive_documents`. Existing v1 rows keep NULL provenance and `truncated = 0`. `blob_sha` is the Git file blob SHA; `source_ref` is a separate optional resolved commit SHA. Do not use a branch name in either field.

The store rejects traversal, absolute paths, symlinked components/targets and non-regular targets. On POSIX, new roots/shards are 0700 and files 0600; shared existing permissions are refused without repair. Writes use an exclusive temporary file in the target shard, flush/fsync and atomic replace. Files are written before the document insert; if the insert fails, newly created files are removed. An identical replay is idempotent, creates no duplicate row/file and repairs a missing file; differing content or provenance raises `RevisionConflict` and is not overwritten. Reads verify the expected SHA-256.

Rollback: migration 2 is forward-only. Reverting only the T06 code after upgrade makes the T03 version check refuse the newer schema, so stop consumers and restore a pre-upgrade consistent snapshot, or keep the T06 code. Do not edit migration 1 or delete the catalogue to bypass a migration error. Content files are immutable; remove only unreferenced files after confirming no document points at them. See [T06 evidence](../execution-plans/hybrid-search/T06_EVIDENCE.md) for tests, the local Windows limitation and Linux-CI coverage of POSIX permission/symlink and upgrade cases.

## Local vector collection adapter (T07, awaiting review)

`app/integrations/milvus.py` provides synchronous `MilvusAdapter`, `VectorChunk` and `ScalarFilters`. Nothing imports it from API startup. Create it explicitly with `MilvusAdapter.connect(Settings(), ModelManifest.load())`, then call `ensure_collection()` from the worker setup path; close the client in `finally`. Keep blocking SDK calls outside an async request loop. T13 owns request admission/cancellation and the total hybrid deadline.

Use the already-pinned `pymilvus==2.6.17` and Milvus 2.6.26 from [the local runbook](../infra/milvus/README.md). Settings are `MILVUS_URI` (explicit HTTP 127.0.0.1 port), `MILVUS_TOKEN` (non-default `user:password`, at least 16 password characters), `MILVUS_PROFILE` (`gpu` default, or explicitly `cpu`), `MILVUS_COLLECTION` (`repo_chunks_e5small_v1`), `MILVUS_TIMEOUT` (10 seconds, >0 to 30), `MILVUS_BUILD_TIMEOUT` (120 seconds, >0 to 120), and `MILVUS_BATCH_SIZE` (64, 1-64). Secrets belong only in ignored environment files. Ordinary auth/search startup still needs no Milvus credentials/server.

The generation fingerprint covers the complete T02 manifest, query/passage prefixes, normalized IP, schema version and scalar bounds. Collection description and every row carry that identity. Setup checks exact fields, dimensions, primary key, Strong consistency and disabled dynamic fields before creating a missing vector index or loading. An existing mismatch is refused without repair/drop. GPU_CAGRA and HNSW use IP; only the selected collection is loaded. A configured alias is rejected by checking the canonical collection name, so an old alias cannot silently direct writes/search to another generation. Alias switching and a durable activation record belong to T08; T07 never changes an alias.

`upsert(chunks)` accepts a nonempty list/tuple of at most the configured batch size, rejects duplicate IDs within a batch, and checks the returned count and IDs. Repeating the same deterministic keys updates the same records. There is no automatic adapter replay after an uncertain or partial write: retry the complete stable-ID batch, then use `ready(chunks)` to compare all expected metadata and vectors under Strong consistency. A missing/old/mismatched row yields false; an unavailable/unloaded index raises an error. Readiness is not SQL activation or proof that growing rows have finished indexing. `delete(chunk_ids)` accepts bounded explicit SHA256 keys only; it cannot execute a caller-supplied delete expression.

Rows contain `chunk_id`, `repo_id`, SHA256 content `revision`, `model_revision`, derived `generation`, `language`, `license`, Unix-seconds `pushed_at`, ordinal 0-7, `section`, bounded `snippet` and `vector`. The caller supplies the snippet (max 2048 UTF-8 bytes); full chunk text stays in the catalogue. Section is at most 512 bytes and language/license at most 128 each. Oversized values are rejected, never silently clipped. Unit-normalized finite vectors must have exactly 384 components.

`search(vector, limit=200, filters=ScalarFilters(...))` accepts 1-1000 hits and only language/license strings, a nonnegative Unix-seconds `pushed_after`, and a positive numeric `repo_id`. Values go through Milvus filter parameters, never expression interpolation. It returns bounded chunk metadata and raw IP scores, without vectors. Scores are not probabilities. No implicit rolling cutoff, visibility/license policy, active-revision filtering or repository-level ranking is applied here; later services must enforce those before serving results. The query vector is transient and never written.

Each operation passes the remaining configured budget to SDK calls; the adapter adds no retry loop and rejects responses arriving after its deadline. The pinned synchronous SDK has its own finite retries and can overshoot an operation budget during an in-flight call/backoff. This is not a hard cancellation guarantee; a late write may have committed, so reconcile/retry the same IDs. Retryable transport/timeouts/rate limits become `MilvusUnavailable`; other SDK errors become sanitized `MilvusOperationError`; input/schema mismatches become `MilvusContractError`. SDK loggers used by this synchronous path suppress raw diagnostics process-wide once the adapter is initialized; preserve private server logs separately when diagnosing failures.

Real synthetic verification (after starting exactly one profile with private credentials):

```powershell
$env:PYTHONPATH = 'backend'
$env:RUN_MILVUS_INTEGRATION = '1'
$env:MILVUS_PROFILE = 'gpu'
# Set MILVUS_URI/MILVUS_TOKEN privately using infra/milvus/README.md.
python -m pytest backend/tests/test_milvus_integration.py -q -s
Remove-Item Env:MILVUS_TOKEN,Env:RUN_MILVUS_INTEGRATION
```

Run from the repo root; Linux uses the equivalent exports and the supported worker interpreter. This opt-in test creates a unique `reporadar_t07_*` collection and synthetic alias, drops only its own resources, and never resets a configured archive. It proves all 1000 rows indexed, Strong read-back, max top-K, parameter filters (including quote injection), repeat/update/delete and alias rejection. It does not ingest user ideas or GitHub content. See [T07 evidence](../execution-plans/hybrid-search/T07_EVIDENCE.md) for exact versions, resource samples and limits.

Rollback: stop consumers and revert T07; auth and existing keyword search are unaffected. No SQL migration or alias activation occurs. Preserve real collection data; never delete a collection to repair a generation mismatch. A future model/schema change requires a newly named collection and T08's validated activation, not modifying the existing collection in place.

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
| `idea` | 2-1,000 characters; letters, digits and combining marks of any script form keywords (underscores and hyphens kept, other characters separate words); retained keywords must fit 256 characters, excluding the fixed qualifiers |
| `page` | 1-50, default 1; starting offset must be below 1,000 using the effective page size |
| `per_page` | 1-100; omission or null uses `Settings.search_page_size`, default 20 |
| `sort` | `stars`, `forks`, `updated`; omission or null uses best match and omits upstream sorting parameters |
| `order` | `desc` or `asc`, default `desc`; ignored without an explicit sort |

Existing response fields are preserved; `per_page`, `sort` and `order` report effective values. Best match is represented as `sort: "relevance", order: "desc"`. Invalid input and pages return 422 before calling GitHub; an overlong keyword query is rejected without truncation. Search responses have a separate configurable `MAX_GITHUB_SEARCH_RESPONSE` budget of 1 MiB (1 KiB-2 MiB allowed); other GitHub reads retain the general 512 KiB default. Oversized provider responses remain explicit errors. When GitHub rate-limits a discovery read beyond the bounded retry budget, the 503 response carries `Retry-After` with GitHub's requested wait (60 seconds when GitHub gives no timing headers); other provider failures carry none. Searches use the signed-in user's own GitHub token, so GitHub's per-user search quota applies. Limits, timeouts and retries are centralized in Settings.

Contract tests use real API/session/storage/provider code with a mocked HTTP transport. A single direct public GitHub search verified that an ordinary 100-item payload exceeded the old general budget; this does not validate the application's live OAuth search flow or semantic relevance. Source: [GitHub Search API](https://docs.github.com/en/rest/search/search).
