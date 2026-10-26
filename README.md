# RepoRadar

Turn a project idea into a search for existing open-source implementations.

RepoRadar is a planned AI-driven discovery service with a React-based mobile client and a Python FastAPI backend. Users describe an idea by text or voice; the backend combines semantic retrieval from Milvus with GitHub public repository search to find similar projects.

**Status (2026-10-26):**

- **Implemented:** mobile branding and GitHub-only signup/login (Expo / React Native + FastAPI); authenticated public GitHub keyword search with page-size/sort controls, repository details and account-specific favourites.
- **Hybrid-search foundations merged:** local Milvus runs on the development laptop's CPU and GPU (T01), and a pinned CPU embedding model turns text into vectors (T02). Neither is connected to search yet.
- **Catalogue merged:** T03 adds a separate private SQLite archive catalogue; it is opt-in and does not alter search or auth. See [T03 evidence](execution-plans/hybrid-search/T03_EVIDENCE.md).
- **Awaiting review:** T05 prepares bounded metadata/README passages with stable hashes and actual tokenizer limits; it does not ingest or publish content. See [T05 evidence](execution-plans/hybrid-search/T05_EVIDENCE.md).
- **Planned:** repository ingestion into Milvus, semantic and hybrid matching, the mobile discovery screens and voice input.
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
- Hybrid search handbook: T00 readiness (PR #13), T01 Milvus CPU/GPU feasibility (PR #15) and T02 CPU embedding adapter (PR #16) merged; T03 catalogue is awaiting review with the worker WAL gate proven on SQLite 3.53.1; corpus capacity and T04-T29 remain planned.
- Semantic search, ingestion, mobile discovery and voice: planned; advanced search syntax needs an explicit input contract.

See [technical requirements](REQUIREMENTS.md), [plain-language scope](SCOPE.md), and [project tracker](PROJECT_TRACKER.md).

## Visual direction

**Bracket Navigator** is the selected icon and splash concept: rounded code brackets around a blue compass needle, with a navy dark theme and cool off-white light theme. See [branding guidance and concept board](docs/BRANDING.md). Native icon exports, theme settings, and the shared loader are implemented; release-device validation remains pending.

## Quality and delivery

![Quality pipeline](docs/quality-pipeline-light.svg#gh-light-mode-only)
![Quality pipeline](docs/quality-pipeline-dark.svg#gh-dark-mode-only)

[Editable pipeline diagram](docs/quality-pipeline.mmd)

The free-tool pipeline runs pytest/Jest with coverage gates, Ruff/ESLint/TypeScript, Bandit and TypeScript security rules, dependency auditing, redacted full-history secret scans and platform bundle exports. A reviewed merge must match the exact reviewed commit and have successful CI. No manually configured scanner keys or paid services. See [quality pipeline, local commands and limitations](docs/QUALITY_PIPELINE.md).

Sanitized local crash events and a mobile retry screen are implemented; production crash aggregation and deployment remain planned. One narrowly scoped Expo CLI dependency exception expires on 2026-11-01.

## Planned hybrid search implementation

The [OpenCode execution handbook](execution-plans/hybrid-search/README.md) contains the proposed Milvus archive/hybrid design, 30 small task prompts, tests-first acceptance criteria and a review-controlled [task tracker](execution-plans/hybrid-search/TRACKER.md). Each task uses a fresh main-based branch, a PR and exact-head review before merge.

| Task | Status | Result |
| --- | --- | --- |
| T00 readiness | Merged (PR #13) | Prerequisites, audits and the decision/blocker matrix recorded in [READINESS](execution-plans/hybrid-search/READINESS.md) |
| T01 Milvus feasibility | Merged (PR #15) | 1,000-vector CPU and GPU proofs pass on the development laptop; GPU peak 196 MiB of 4 GB; no meaningful speed gain at this size ([evidence](execution-plans/hybrid-search/T01_EVIDENCE.md), [runbook](infra/milvus/README.md)) |
| T02 CPU embeddings | Merged (PR #16) | Hash-verified offline model loading on Windows and WSL; about 87–100 queries/s and about 1 GiB RAM on CPU ([evidence](execution-plans/hybrid-search/T02_EVIDENCE.md)) |
| T03 catalogue | Merged (PR #18) | Isolated SQLite v1 migrations; real WAL proof on worker SQLite 3.53.1; auth unchanged ([evidence](execution-plans/hybrid-search/T03_EVIDENCE.md)) |
| T05 content preparation | Awaiting review | Bounded Markdown/metadata passages, versioned identity and tokenizer budgets ([evidence](execution-plans/hybrid-search/T05_EVIDENCE.md)) |
| T04, T06-T29 | Not started | Require their task-specific merged prerequisites and policy approvals |

Still open: archive and rebuild capacity on the 16 GB development laptop, the eight policy decisions (corpus cap, licences, retention and others) and the unmerged mobile discovery foundation. Search quality is not measured until T27.
