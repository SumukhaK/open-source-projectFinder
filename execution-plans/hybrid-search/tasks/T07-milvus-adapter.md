# T07: Implement the minimal Milvus collection adapter

Status: Awaiting review. Implementation and real GPU evidence are in [T07_EVIDENCE](../T07_EVIDENCE.md); review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t07-milvus-adapter` |
| Prerequisites, merged into main | [T01](T01-milvus-feasibility.md), [T02](T02-embeddings.md), [T03](T03-catalogue.md) |
| Intended scope | backend/app/integrations/milvus.py + tests |

Read first: T01 compatibility evidence; model manifest; ARCHITECTURE collection schema; versioned pymilvus docs. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T07 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t07-milvus-adapter FROM origin/main; record base SHA.
Use Ponytail discipline: minimum complete, human-readable code, existing patterns
and standard library first, no speculative abstractions or unrelated changes.
For behavior, write and RUN meaningful failing tests FIRST (RED), implement the
minimum code (GREEN), then refactor and run affected tests/lint/type/security checks.
Documentation-only changes use relevant static checks; do not invent behavioral RED.
Implement only the scope and acceptance criteria below. Do not lower CI gates,
add security exceptions or claim unrun real-server/hardware checks passed.
Update relevant docs and tracker to Awaiting review with actual evidence.
Commit explicit task files, push this branch, and RAISE ONE PR AGAINST main.
Return PR URL, full head SHA and verification/limits; STOP AND WAIT FOR REVIEW.
Do not self-accept, write a review marker, merge or start the next task.
Address review changes on this PR, rerun affected checks and await fresh head review.
```

## Work and boundaries

Create only the selected generation collection with stable chunk PK, repo_id, revision/model fields, bounded snippet and 384-dimensional vector. Implement bounded upsert/readiness/search/delete and typed allowlisted scalar filters. Fail clearly on generation/dimension/metric mismatch; keep large raw data outside Milvus. Support the measured CPU/GPU profile rather than automatic opaque fallback.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: wrong dimensions/manifest, malformed filter, retryable failures, duplicate upsert, partial batch and stale collection alias. GREEN: a real selected Milvus server proves round-trip vectors/filter/update/delete; isolated unit fixtures cover boundaries.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Normalized inner-product metric matches both profiles. Model generation cannot silently mix; dynamic fields are disabled. Supported top-K/consistency and activation evidence are recorded for the exact server/SDK pair.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No second vector database, raw user filter interpolation, Milvus-native fusion of external GitHub results or fake GPU claims from mocked clients.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
