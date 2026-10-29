# RepoRadar

Turn a project idea into a search for existing open-source implementations.

RepoRadar is a planned AI-driven discovery service with a React-based mobile client and a Python FastAPI backend. Users describe an idea by text or voice; the backend combines semantic retrieval from Milvus with GitHub public repository search to find similar projects.

**Status (2026-10-27):**

- **Implemented:** mobile branding and GitHub-only signup/login (Expo / React Native + FastAPI); authenticated public GitHub keyword search with page-size/sort controls, repository details and account-specific favourites.
- **Hybrid-search foundations merged:** local Milvus runs on the development laptop's CPU and GPU (T01), and a pinned CPU embedding model turns text into vectors (T02). Neither is connected to search yet.
- **Archive building blocks merged:** a separate private SQLite archive catalogue (T03), a worker-only bounded GitHub reader that verifies repository identity and Git blob hashes (T04), deterministic metadata/README chunking within the real tokenizer limits (T05), a private content-addressed store that saves raw and prepared content with its provenance atomically (T06), and a deterministic planner that splits a rolling year of GitHub search into partitions below the 1,000-result cap (T16). None is wired into ingestion, search or auth yet. See the [T03](execution-plans/hybrid-search/T03_EVIDENCE.md), [T04](execution-plans/hybrid-search/T04_EVIDENCE.md) and [T05](execution-plans/hybrid-search/T05_EVIDENCE.md) and [T06](execution-plans/hybrid-search/T06_EVIDENCE.md) evidence.
- **Planned:** repository ingestion into Milvus, semantic and hybrid matching, the mobile discovery screens and voice input.
- **Single-repository ingestion merged (T09):** an operator command fetches one approved repository by its numeric ID, checks eligibility and licence, chunks and embeds its README, and publishes it to Milvus crash-safely; re-running on unchanged content does no embedding work. Verified live on one owner-approved repository (fastapi/typer, MIT). No bulk crawling, and nothing else may be ingested until the licence (D2) and serving (D4) policies are decided. See [T09 evidence](execution-plans/hybrid-search/T09_EVIDENCE.md).
- **Source eligibility merged (T10):** checks that keep stale or unsafe archive evidence away from valid live results; not yet wired into search, and production use waits on the visibility policy (D4). See [T10 evidence](execution-plans/hybrid-search/T10_EVIDENCE.md).
- **Crash-safe publication merged (T08):** revisions are staged, their vectors written and verified, then activated in one short transaction; failed or abandoned updates never replace the serving revision, and search hits are limited to the active revision. Not yet wired into ingestion or search. See [T08 evidence](execution-plans/hybrid-search/T08_EVIDENCE.md).
- **Vector store adapter merged (T07):** a bounded Milvus collection adapter, verified on the local GPU with synthetic vectors. It is not connected to ingestion or search. See [T07 evidence](execution-plans/hybrid-search/T07_EVIDENCE.md).
- **Still to validate:** live GitHub OAuth and native-device checks.

Standalone GitHub search controls are implemented: configurable page size, sorting, validated query/pagination limits and bounded search responses. Tests preserve existing parsing, authentication and public-only scope. Review, CI and delivery evidence: [PR #10](https://github.com/SumukhaK/open-source-projectFinder/pull/10) and [the tracker](PROJECT_TRACKER.md). Advanced qualifiers, Boolean expressions and semantic search remain planned.

The CPU embedding adapter is implemented in `backend/app/services/embeddings.py` with a pinned `intfloat/multilingual-e5-small` revision and manifest. It produces normalized 384-dimensional query/passage vectors, adds the E5 prefixes, enforces the 512-token limit after prefixing, and loads only safe weights on CPU with remote model code disabled. It is not connected to an API route yet. Unit tests use a deterministic fake encoder and never download a model; the real local CPU smoke/benchmark and dependency evidence are in [T02 evidence](execution-plans/hybrid-search/T02_EVIDENCE.md). The optional CPU lock is separate from the main backend lock.

## Planned architecture

![RepoRadar planned architecture](docs/architecture-light.svg#gh-light-mode-only)
![RepoRadar planned architecture](docs/architecture-dark.svg#gh-dark-mode-only)

[Editable Mermaid source](docs/architecture.mmd) · [Diagram styling](docs/DIAGRAMS.md)

The backend and ingestion worker share integration code and one central backend configuration module. Provider choices, corpus boundaries, ingestion cadence, and ranking strategy remain open.

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
| Language model, voice transcription | Pending | Select after requirements |
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
scripts/           # Quality gates, reviewed merge, Milvus probe, embedding smoke check
AGENTS.md          # Engineering workflow
REQUIREMENTS.md    # Technical requirements
SCOPE.md           # Plain-language scope
PROJECT_TRACKER.md # Phases, decisions, original prompts
```

## Development

See [backend setup and checks](backend/README.md) and [mobile setup and checks](mobile/README.md) to run the implemented client. Keep secrets in ignored environment files, use a central configuration module, and develop each feature through tests, a feature branch, a pull request, review, and merge.

## Phase progress

- Phase 0: initial folder scaffold and documentation prepared.
- Mobile branding: implemented vector icon assets, themed launch configuration, saved appearance preferences, and accessible shared loading animation.
- GitHub authentication: implemented OAuth/PKCE, encrypted credentials, revocable sessions, rate limiting, mobile sign-in and automated cross-layer tests.
- Quality pipeline: free open-source validation, explicit coverage/security gates and review-controlled delivery.
- Backend discovery: public GitHub search/details and account-specific favourites, with verified keyword search controls and limits.
- Discovery hardening: non-ASCII ideas are searchable, GitHub rate limits return `Retry-After`, and request-size limits use a public ASGI middleware.
- Hybrid search handbook: T00 readiness (PR #13), T01 Milvus CPU/GPU feasibility (PR #15), T02 CPU embedding adapter (PR #16), T03 archive catalogue (PR #18), T04 bounded archive GitHub reads (PR #19) and T05 content preparation (PR #20) T06 raw content/provenance (PR #22) and T16 discovery partition planning (PR #24) and T07 Milvus collection adapter (PR #28) and T08 crash-safe publication (PR #30) and T10 source eligibility (PR #32) and T09 single-repository ingestion (PR #34) merged; corpus capacity and the other tasks up to T29 remain planned.
- Semantic search, ingestion, mobile discovery and voice: planned; advanced search syntax needs an explicit input contract.

See [technical requirements](REQUIREMENTS.md), [plain-language scope](SCOPE.md), and [project tracker](PROJECT_TRACKER.md).

## Visual direction

**Bracket Navigator** is the selected icon and splash concept: rounded code brackets around a blue compass needle, with a navy dark theme and cool off-white light theme. See [branding guidance and concept board](docs/BRANDING.md). Native icon exports, theme settings, and the shared loader are implemented; release-device validation remains pending.

## Quality and delivery

![Quality pipeline](docs/quality-pipeline-light.svg#gh-light-mode-only)
![Quality pipeline](docs/quality-pipeline-dark.svg#gh-dark-mode-only)

[Editable pipeline diagram](docs/quality-pipeline.mmd)

The free-tool pipeline runs pytest/Jest with coverage gates, Ruff/ESLint/TypeScript, Bandit and TypeScript security rules, dependency auditing, redacted full-history secret scans and platform bundle exports. A reviewed merge must match the exact reviewed commit and have successful CI. No manually configured scanner keys or paid services. See [quality pipeline, local commands and limitations](docs/QUALITY_PIPELINE.md).

Sanitized local crash events and a mobile retry screen are implemented; production crash aggregation and deployment remain planned. One narrow, expiring dependency audit exception remains (deepmerge 4.3.1, low severity, build/test tooling only, expires 2026-12-31); node-forge was updated to the patched 1.4.2.

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
| T11-T15, T17-T29 | Not started | Require their task-specific merged prerequisites and policy approvals |

Still open: archive and rebuild capacity on the 16 GB development laptop, the six remaining policy decisions (corpus cap, retention, backups and others; licence policy D2 and visibility D4 were approved 2026-10-29) and the unmerged mobile discovery foundation. Search quality is not measured until T27.
