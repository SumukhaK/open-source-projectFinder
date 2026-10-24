# Technical Requirements

## Confirmed core
- Provide a React-based mobile client for submitting project ideas as text or voice.
- Provide an AI-driven Python FastAPI backend.
- Search public GitHub repositories for similar implementations.
- Periodically ingest repository data and index it in Milvus for semantic search at substantial scale.
- Combine Milvus retrieval with GitHub Search API results for hybrid discovery.
- Return repository matches to the mobile client.

## Proposed boundaries
- Keep HTTP handling, search orchestration, external integrations, and ingestion scheduling separate.
- Run periodic ingestion as a worker separate from API request handling.
- Centralize backend configuration in backend/app/core; keep sensitive values in environment variables.
- Preserve repository provenance and ingestion timestamps; define update, deletion, deduplication, and retry behavior during detailed design.
- Treat embedding-model selection, versioning, index schema, and ranking as explicit design decisions.

## Decisions still required
- React Native with Expo selected and implemented for the branding foundation; supported release OS versions remain to be specified.
- AI, embedding, and speech providers; hosting and budget constraints.
- Corpus selection and whether to index metadata, README content, documentation, or source code.
- Ingestion cadence, scale targets, retention, storage beyond vectors, and GitHub API budget.
- Similarity criteria, ranking, result explanations, latency targets, and measurable relevance evaluation.
- Voice and text privacy, retention, accessibility and deployment requirements. GitHub-only authentication is confirmed below.

This document records initial requirements, not a finalized implementation contract. No multi-agent architecture is currently required.

## Confirmed visual requirements

- Use Bracket Navigator for the app icon and as the shared animated in-app loading indicator.
- Support dark and light appearances and system appearance preference.
- Loading indicators must respect Reduce Motion and expose accessible loading status.
- Detailed animation, export, and platform rules are recorded in docs/BRANDING.md.

## Mobile architecture

Follow Bulletproof React feature-based organization, adapted for Expo / React Native: compose at the app layer, keep feature-specific code in features, and share independent components, hooks, libraries and centralized configuration.

## GitHub-only authentication

- One signup/login action after launch; valid sessions skip sign-in.
- GitHub OAuth without private-repository permission; stable GitHub ID identifies accounts.
- Separate app sessions; encrypted GitHub credentials backend-side for future user-scoped search.
- State, provider/app PKCE, expiring one-use handoff, revocation and secure native storage.
- Persistent IP quotas, bounded safe retries, provider timeouts and payload limits.
- Backend tests before implementation, mobile tests before implementation, automated real-HTTP cross-layer verification.
- Live GitHub/device checks require OAuth registration and native development builds. See docs/AUTHENTICATION.md.

## Quality phase requirements

- Free open-source tools; no manually supplied scanner keys, paid subscriptions or plan/budget upgrades.
- Unit/integration/E2E tests, measurable coverage gates, lint/type/format checks, SAST, dependency auditing and redacted full-history secret scanning.
- Failed/skipped/cancelled jobs and scanner errors must fail the quality gate. Exceptions must be exact and expiring.
- Agent self-review of the exact head is mandatory before a workflow-controlled merge; repository restrictions must still apply.
- Sanitized local crash capture and retry, with centralized/native crash reporting deferred until deployment is defined.
- Bounded/cached jobs and minimal report retention; hosted runner quotas are not unlimited.

Discovery API integration now exposes account-scoped app favourites and GitHub public repository details. Standalone keyword search controls and their contract tests are implemented and verified locally. Review, CI and delivery evidence is recorded in [PR #10](https://github.com/SumukhaK/open-source-projectFinder/pull/10). Milvus semantic matching remains planned. Optional details must be omitted when GitHub supplies no data.

## Standalone GitHub search improvements

- Preserve ordinary `idea` normalization, the existing response fields and public-only/unarchived repository scope. Keyword extraction keeps letters, digits and combining marks of any script, so non-ASCII ideas are searchable instead of rejected or split mid-word.
- Optional `per_page` accepts 1-100 and falls back to centralized `Settings.search_page_size` when omitted or null. Explicit sorts are `stars`, `forks` and `updated`; omitted or null sort uses best match. Sorting uses `desc` by default or explicit `asc`; an order supplied without a sort has no upstream effect. Response metadata reports the effective page size and sorting, including descending best match.
- Preserve pages 1-50 and reject a page whose starting offset, calculated with the effective page size, is at least 1,000. Allow a partial final page starting within that window.
- Retained keyword text, including spaces but excluding qualifiers, must fit the 256-character limit. Validate raw idea length separately at 1,000 characters. Reject invalid requests before provider calls and preserve explicit provider failures and incomplete-result metadata.
- Search reads use a separate centralized 1 MiB response budget, configurable between 1 KiB and 2 MiB, while other GitHub reads keep the 512 KiB default. Reject over-budget responses and preserve bounded timeouts/retries. Provider rate limits return 503 with `Retry-After` when GitHub supplies (or requires) a wait.
- Verify actual outbound parameters and response values, configured defaults, exact boundaries, compatibility, authentication, throttling, body limits, defensive public filtering and search response budgets. Delivery requires the full backend suite, coverage gates, review of the exact PR commit and all required repository checks.
- Advanced qualifiers/quoted phrases and Boolean expressions are later phases requiring an explicit input contract. Semantic search and combining retrieval results remain separate planned work.

T01 feasibility uses pinned Milvus2.6.26 / PyMilvus2.6.17 and 1k synthetic384-dimensional normalized vectors. CPU operations passed; GPU driver compatibility, supported host capacity and a WAL-fixed worker SQLite remain prerequisites. See [evidence](execution-plans/hybrid-search/T01_EVIDENCE.md).
