# RepoRadar

Turn a project idea into a search for existing open-source implementations.

RepoRadar is a planned AI-driven discovery service with a React-based mobile client and a Python FastAPI backend. Users describe an idea by text or voice; the backend combines semantic retrieval from Milvus with GitHub public repository search to find similar projects.

**Status:** mobile branding and GitHub-only signup/login implemented with Expo / React Native and FastAPI. Public GitHub search/details and account-specific favourites are connected. Standalone search controls are implemented and tested; repository ingestion, semantic matching and voice remain planned. Live OAuth and native device validation remain required.

Standalone GitHub search controls are implemented: configurable page size, sorting, validated query/pagination limits and bounded search responses. Tests preserve existing parsing, authentication and public-only scope. Review, CI and delivery evidence: [PR #10](https://github.com/SumukhaK/open-source-projectFinder/pull/10) and [the tracker](PROJECT_TRACKER.md). Advanced qualifiers, Boolean expressions and semantic search remain planned.

## Planned architecture

![RepoRadar planned architecture](docs/architecture-light.svg#gh-light-mode-only)
![RepoRadar planned architecture](docs/architecture-dark.svg#gh-dark-mode-only)

[Editable Mermaid source](docs/architecture.mmd) Â· [Diagram styling](docs/DIAGRAMS.md)

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
| Semantic index | Milvus | Confirmed |
| Live repository retrieval | GitHub Search API | Confirmed |
| Embeddings, language model, voice transcription | Pending | Select after requirements |
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
infra/             # Deployment and local service configuration
docs/              # Detailed design documents
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
- Search, ingestion, and voice implementation: pending further brainstorming and requirements.

See [technical requirements](REQUIREMENTS.md), [plain-language scope](SCOPE.md), and [project tracker](PROJECT_TRACKER.md).

## Visual direction

**Bracket Navigator** is the selected icon and splash concept: rounded code brackets around a blue compass needle, with a navy dark theme and cool off-white light theme. See [branding guidance and concept board](docs/BRANDING.md). Native icon exports, theme settings, and the shared loader are implemented; release-device validation remains pending.

## Quality and delivery

![Quality pipeline](docs/quality-pipeline-light.svg#gh-light-mode-only)
![Quality pipeline](docs/quality-pipeline-dark.svg#gh-dark-mode-only)

[Editable pipeline diagram](docs/quality-pipeline.mmd)

The free-tool pipeline runs pytest/Jest with coverage gates, Ruff/ESLint/TypeScript, Bandit and TypeScript security rules, dependency auditing, redacted full-history secret scans and platform bundle exports. A reviewed merge must match the exact reviewed commit and have successful CI. No manually configured scanner keys or paid services. See [quality pipeline, local commands and limitations](docs/QUALITY_PIPELINE.md).

Sanitized local crash events and a mobile retry screen are implemented; production crash aggregation and deployment remain planned. One narrowly scoped Expo CLI dependency exception expires on 2026-11-01.
