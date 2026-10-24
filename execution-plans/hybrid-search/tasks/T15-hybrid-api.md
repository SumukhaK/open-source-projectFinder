# T15: Expose authenticated versioned hybrid search and status

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t15-hybrid-api` |
| Prerequisites, merged into main | [T14](T14-fused-cursors.md) |
| Intended scope | backend/app/api/archive.py + app factory/tests |

Read first: main.py, existing auth/current session guards/request limits; legacy endpoint tests; ARCHITECTURE API shapes. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T15 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t15-hybrid-api FROM origin/main; record base SHA.
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

Add POST /v1/projects/search with idea 2-1000 chars, page_size 1-50 default20, cursor and bounded typed language/license filters; both sources mandatory by default. Inject service through app factory. Return existing card fields plus source/degraded/freshness/cursor/ranking fields and nullable total. Add authenticated sanitized GET /v1/archive/status; distinguish uninitialized/unknown lifecycle status until T17/T19 supply it.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: session/rate guards, invalid bounds/filter/cursor, legacy unchanged, both empty, partial hits, partial zero SEARCH_INCOMPLETE, expired cursor and sanitized status. GREEN: HTTP contract tests assert semantic results/provenance, not only status codes.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

No mode/source parameter or publicly reachable worker controls. Errors are typed/sanitized and status does not leak secrets/paths/raw exceptions. Existing legacy/details/favourites tests pass and client timeout budget is respected.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No fake last-success data before lifecycle implementation, destructive API migrations, generated similarity percentages or authentication bypass for status.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
