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
