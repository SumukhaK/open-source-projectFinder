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
- React Native versus another React-based mobile delivery model; supported platforms.
- AI, embedding, and speech providers; hosting and budget constraints.
- Corpus selection and whether to index metadata, README content, documentation, or source code.
- Ingestion cadence, scale targets, retention, storage beyond vectors, and GitHub API budget.
- Similarity criteria, ranking, result explanations, latency targets, and measurable relevance evaluation.
- Authentication, voice and text privacy, retention, accessibility, and deployment requirements.

This document records initial requirements, not a finalized implementation contract. No multi-agent architecture is currently required.
