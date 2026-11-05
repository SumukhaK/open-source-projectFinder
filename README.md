# RepoRadar

Turn a project idea into a search for existing open-source implementations.

P3 adds Home/Profile navigation for signed-in users: search remains on Home; Profile contains favourites, appearance, privacy information and sign-out. See [verification and limits](execution-plans/voice-assistant/P3_EVIDENCE.md). Review is pending.

RepoRadar is a planned AI-driven discovery service with a React-based mobile client and a Python FastAPI backend. Users describe an idea by text or by holding to talk; the backend combines semantic retrieval from Milvus with GitHub public repository search to find similar projects, and (planned) a small LLM summarises the results, which can be read aloud.

## Planned architecture

![RepoRadar planned architecture](docs/architecture-light.svg#gh-light-mode-only)
![RepoRadar planned architecture](docs/architecture-dark.svg#gh-dark-mode-only)

[Editable Mermaid source](docs/architecture.mmd) · [Diagram styling](docs/DIAGRAMS.md)

The backend and ingestion worker share integration code and one central backend configuration module. Dashed boxes are planned by the [voice assistant plan](execution-plans/voice-assistant/README.md); see [voice assistant architecture](docs/VOICE_ASSISTANT_ARCHITECTURE.md).

## Implemented authentication

![RepoRadar authentication](docs/authentication-light.svg#gh-light-mode-only)
![RepoRadar authentication](docs/authentication-dark.svg#gh-dark-mode-only)

[Authentication flow and security](docs/AUTHENTICATION.md) · [Editable source](docs/authentication.mmd)

GitHub credentials stay encrypted on the backend; the app uses a separate revocable session. Persistent rate limits and bounded provider retries are implemented.

## Tools

| Component | Technology | Decision |
| --- | --- | --- |
| Backend API | Python, FastAPI | Confirmed |
| Mobile client | React ecosystem | React Native with Expo implemented |
| Semantic index | Milvus 2.6.26 standalone (etcd + MinIO) via Docker Compose, PyMilvus 2.6.17 | Pinned; local CPU (HNSW) and GPU (GPU_CAGRA) feasibility proven in T01; archive not built yet |
| Live repository retrieval | GitHub Search API | Confirmed |
| Embeddings | `intfloat/multilingual-e5-small` (pinned revision, 384-d) with `sentence-transformers` and CPU-only PyTorch | T02 adapter, manifest and hash-verified offline loading merged; not yet wired into search |
| Archive catalogue | Standard-library SQLite, separate private Linux database and versioned migrations | T03 merged; real WAL evidence on SQLite 3.53.1; no ingestion yet |
| Archive GitHub reads | HTTPX with a dedicated worker token, bounded streaming and conditional requests | T04 merged; not yet called by a worker |
| Content preparation | `markdown-it-py` 4.2.0 (AST read only, never rendered) and the pinned E5 tokenizer | T05 merged; at most 8 chunks of ≤400 content / ≤512 final tokens |
| Local runtime | WSL2 (Ubuntu) + Docker Desktop on Windows; NVIDIA driver 617.42 for the GPU profile | Used for Milvus and the embedding smoke checks |
| Speech to text, text to speech | Deepgram, called only from the backend | Approved 2026-11-05 (VD1); not implemented |
| Language model | OpenAI-compatible client over switchable profiles: Ollama locally, then Cloudflare Workers AI open models up to about 30B; no frontier model | Approved 2026-11-05 (VD2); not implemented |
| Tests | Unit and integration tests with TDD | pytest, Jest / React Native Testing Library |

## Repository layout

```text
backend/
  app/
    api/           # HTTP endpoints
    main.py        # Authentication HTTP API and app factory
    core/          # Configuration and transactional SQLite store
    services/      # Idea processing, retrieval, ranking
    integrations/  # GitHub, Milvus, AI provider adapters
    workers/       # Periodic ingestion
  tests/
    unit/
    integration/
mobile/
  src/             # React mobile client
  tests/
infra/
  milvus/          # Pinned local Milvus CPU/GPU Compose profiles and runbook (T01)
docs/              # Detailed design documents
execution-plans/
  hybrid-search/   # Hybrid search handbook, task prompts, tracker and evidence
  voice-assistant/ # Voice and LLM summary plan, task prompts and tracker
scripts/           # Quality gates, reviewed merge, Milvus probe, embedding smoke check
AGENTS.md          # Engineering workflow
REQUIREMENTS.md    # Technical requirements
SCOPE.md           # Plain-language scope
PROJECT_TRACKER.md # Phases, decisions, original prompts
```

## Development

See [backend setup and checks](backend/README.md) and [mobile setup and checks](mobile/README.md) to run the implemented client. Keep secrets in ignored environment files, use a central configuration module, and develop each feature through tests, a feature branch, a pull request, review, and merge.

See [technical requirements](REQUIREMENTS.md), [plain-language scope](SCOPE.md), and [project tracker](PROJECT_TRACKER.md).

## Visual direction

**Bracket Navigator** is the selected icon and splash concept: rounded code brackets around a blue compass needle, with a navy dark theme and cool off-white light theme. See [branding guidance and concept board](docs/BRANDING.md). Native icon exports, theme settings, and the shared loader are implemented; release-device validation remains pending.

## Quality and delivery

![Quality pipeline](docs/quality-pipeline-light.svg#gh-light-mode-only)
![Quality pipeline](docs/quality-pipeline-dark.svg#gh-dark-mode-only)

[Editable pipeline diagram](docs/quality-pipeline.mmd)

The free-tool pipeline runs pytest/Jest with coverage gates, Ruff/ESLint/TypeScript, Bandit and TypeScript security rules, dependency auditing, redacted full-history secret scans and platform bundle exports. A reviewed merge must match the exact reviewed commit and have successful CI. No manually configured scanner keys or paid services. See [quality pipeline, local commands and limitations](docs/QUALITY_PIPELINE.md).

Sanitized local crash events and a mobile retry screen are implemented; production crash aggregation and deployment remain planned. One narrow, expiring dependency audit exception remains (deepmerge 4.3.1, low severity, build/test tooling only, expires 2026-12-31); node-forge was updated to the patched 1.4.2.

## Planned voice assistant

The user holds to talk, the backend transcribes the clip with Deepgram, and the editable transcript runs the existing hybrid search. The result list shows first. A small LLM then writes a summary of only those results, and Deepgram can read it aloud if voice output is on. The LLM never changes the list, and any voice or LLM failure falls back to plain text search. Models are settings profiles (Ollama first, then Workers AI) and change only after evals. A Home/Profile bottom bar comes first (P3); "Read summaries aloud" lives in Profile › Voice and is on for voice searches only. See the [architecture](docs/VOICE_ASSISTANT_ARCHITECTURE.md), the [UX](docs/VOICE_UX.md) and the [plan and tracker](execution-plans/voice-assistant/README.md) (P3, V0-V4, not started).

## Planned hybrid search implementation

The [OpenCode execution handbook](execution-plans/hybrid-search/README.md) contains the proposed Milvus archive/hybrid design, 30 small task prompts, tests-first acceptance criteria and a review-controlled [task tracker](execution-plans/hybrid-search/TRACKER.md). Each task uses a fresh main-based branch, a PR and exact-head review before merge.

| Task | Status | Result |
| --- | --- | --- |
| T00 readiness | Merged (PR #13) | Prerequisites, audits and the decision/blocker matrix recorded in [READINESS](execution-plans/hybrid-search/READINESS.md) |
| T01 Milvus feasibility | Merged (PR #15) | 1,000-vector CPU and GPU proofs pass on the development laptop; GPU peak 196 MiB of 4 GB; no meaningful speed gain at this size ([evidence](execution-plans/hybrid-search/T01_EVIDENCE.md), [runbook](infra/milvus/README.md)) |
| T02 CPU embeddings | Merged (PR #16) | Hash-verified offline model loading on Windows and WSL; about 87–100 queries/s and about 1 GiB RAM on CPU ([evidence](execution-plans/hybrid-search/T02_EVIDENCE.md)) |
| T03 catalogue | Merged (PR #18) | Isolated SQLite v1 migrations; real WAL proof on worker SQLite 3.53.1; auth unchanged ([evidence](execution-plans/hybrid-search/T03_EVIDENCE.md)) |
| T04 archive GitHub reads | Merged (PR #19) | Worker-only bounded reader; numeric repository identity, Git blob SHA content checks, `Retry-After` and secondary rate limits honoured ([evidence](execution-plans/hybrid-search/T04_EVIDENCE.md)) |
| T05 content preparation | Merged (PR #20) | Bounded Markdown/metadata passages cut at word boundaries, versioned identity and tokenizer budgets ([evidence](execution-plans/hybrid-search/T05_EVIDENCE.md)) |
| T06 raw content and provenance | Merged (PR #22) | Private content-addressed raw/normalized files, schema v2 provenance and atomic revision persistence; unchanged content replays refresh fetch details instead of conflicting; no ingestion or publication ([evidence](execution-plans/hybrid-search/T06_EVIDENCE.md)) |
| T16 discovery partitions | Merged (PR #24) | Rolling-year pushed window split pushed → created → stars under 750 results per query; stable keys and a selection record whose coverage is never labelled complete ([evidence](execution-plans/hybrid-search/T16_EVIDENCE.md)) |
| T07 Milvus collection adapter | Merged (PR #28) | Generation-safe collection with fail-closed schema/index checks, bounded upsert/read-back/search/delete and parameterised filters; live GPU_CAGRA proof at 1k synthetic vectors, peak 203 MiB VRAM ([evidence](execution-plans/hybrid-search/T07_EVIDENCE.md)) |
| T08 crash-safe publication | Merged (PR #30) | Stage → write and read back vectors → activate in one transaction; activation supersedes older pending attempts; bounded reconcile deletes vectors before rows; `filter_active_hits` limits search to the active revision ([evidence](execution-plans/hybrid-search/T08_EVIDENCE.md)) |
| T10 source eligibility | Merged (PR #32) | Live results need only an exact numeric ID and public, unarchived status; archive evidence also needs the active T08 revision, a 365-day push window, a fresh ID-bound check (≤15 min) and no sticky suppression; outages return incomplete, 401 purges nothing. Serving gated by D4 ([evidence](execution-plans/hybrid-search/T10_EVIDENCE.md)) |
| T09 single-repository ingestion | Merged (PR #34) | `python -m app.workers.archive ingest --repo-id N`: numeric-ID fetch, fail-closed preflight, licence allowlist (empty by default), unchanged replay with zero embeds, T06 → E5 → T07 → T08 publish and reconcile. Live pilot: fastapi/typer (MIT) published 8 chunks, replay 0 embeds, 8/8 active hits; no GPU-capacity claim ([evidence](execution-plans/hybrid-search/T09_EVIDENCE.md)) |
| T11 keyword candidates | Merged (PR #38) | Shared bounded keyword compiler; internal 100-candidate live GitHub source with `ok`/`incomplete`/`query_not_supported`/`failed` status; typed language/licence filters; legacy search contract unchanged ([evidence](execution-plans/hybrid-search/T11_EVIDENCE.md)) |
| T12 rank fusion | Merged (PR #42) | One pure helper over the T10/T11 types: archive chunk collapse to the best chunk per repository, 100-repository source caps, equal-weight RRF (k=60) ordered by score then best source rank then ID, live-wins metadata, SPDX licence comparison, preserved source health and a null `total` ([evidence](execution-plans/hybrid-search/T12_EVIDENCE.md)) |
| T17 durable runs | Merged (PR #40) | Additive migration 4: unique due-period runs, T16 partition checkpoints, persisted retries, heartbeat/expiry leases with increasing fences checked at publication/activation/cleanup, and a private lock serializing vector IO; T09 takes a temporary lease automatically ([evidence](execution-plans/hybrid-search/T17_EVIDENCE.md)) |
| T13 hybrid orchestration | Merged (PR #45) | One internal service starts live GitHub and the archive concurrently under an 8-second deadline, bounds blocking work and outstanding jobs, derives real archive status, maps one licence table to both sources and applies the T12 conflict rule; no route or cursor ([evidence](execution-plans/hybrid-search/T13_EVIDENCE.md)) |
| T14 fused snapshot cursors | Merged (PR #49) | One internal pager stores at most 200 fused cards for 300 s (256 snapshots total, 8 per account) and pages them with an opaque HMAC-SHA256 cursor bound to account, keyed HMAC-SHA256 idea/filter digests, model/ranking generation, expiry and offset; later pages never re-query either source and call the required revalidator on their own window; no route ([evidence](execution-plans/hybrid-search/T14_EVIDENCE.md)) |
| T18 bounded backfill | Phase A merged (PR #47); Phase B pending approval | Manual serial `backfill --cap 1000` worker: additive migration 5, durable pages/outcomes, cap/disk/queue/partition/byte bounds, header-driven ~20% quota headroom with persisted `retry_at`, credential stop, terminal per-repo outcomes, curated/partial coverage only; fake-only so far ([evidence](execution-plans/hybrid-search/T18_EVIDENCE.md)) |
| T15 hybrid API | Merged (PR #51) | Authenticated `POST /v1/projects/search` and sanitized `GET /v1/archive/status`: 2-1000 character idea, 1-50 page size, typed language/licence filters, both sources, T14 paging with the remaining deadline, T10 later-page revalidation with a bounded TTL cache and bounded concurrency, short pages at the deadline, provenance/degraded state, nullable `total`, typed errors, read-only status, lazy Milvus/model/archive construction with model reuse and a bounded build wait, and first-page source health repeated on later pages ([evidence](execution-plans/hybrid-search/T15_EVIDENCE.md)) |
| T24 mobile hybrid contract | Merged (PR #55) | The single mobile transport calls `POST /v1/projects/search` with strict zod request/response/error schemas, cursor paging (`has_more`/`next_cursor`), typed error states, licence/freshness/snippet on cards, and a versioned results cache that drops legacy snapshots, keeps favourites and never stores the idea or cursor. Mobile search now needs the full hybrid backend; see [operator steps and rollback](execution-plans/hybrid-search/T24_EVIDENCE.md) |
| T25 mobile results | Merged (PR #58) | One combined result list with truthful partial/empty states, Try again, a stale banner on cached results and pull to refresh on Home results ([evidence](execution-plans/hybrid-search/T25_EVIDENCE.md)) |
| T19-T23, T26-T29 | Not started | Require their task-specific merged prerequisites and policy approvals |
| T30 upkeep | Not started; backlog open | Collects non-blocking review notes (currently U1-U12 and U15; U13 and U14 closed) and runs after T29 ([task](execution-plans/hybrid-search/tasks/T30-upkeep.md)) |

Still open: archive and rebuild capacity on the 16 GB development laptop, the D8 quality numbers (set after T27; all eight policy decisions D1-D8 were approved 2026-10-29). The mobile discovery foundation, T24 and T25 are merged; T26 still needs T22. Search quality is not measured until T27.
