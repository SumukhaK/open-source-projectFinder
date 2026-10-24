# T24: Migrate mobile transport and cache types to hybrid v1

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t24-mobile-contract` |
| Prerequisites, merged into main | [T00](T00-readiness.md), [T15](T15-hybrid-api.md) |
| Intended scope | existing discovery API/types/storage + tests |

Read first: Actually merged mobile discovery API/cache/offline tests; auth API error and account storage conventions; v1 contract. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T24 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t24-mobile-contract FROM origin/main; record base SHA.
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

Switch the existing single app search adapter to POST /v1/projects/search; add typed combined cards/provenance/degraded/freshness/cursor/error fields with page_size<=50. Keep legacy server endpoint available. Version account-scoped cached-result schemas safely; invalidate incompatible old search snapshots without erasing unrelated favourites/consented drafts. Cursor expiry restarts search explicitly.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: request/response contract, source notices, SEARCH_INCOMPLETE vs empty, cursor expiry, logout/account switch and old cache migration. GREEN: API/storage fixtures prove no raw query history/query embedding persistence and existing offline consent behavior passes.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Main must already contain the reviewed discovery/mobile foundation; otherwise record the prerequisite instead of recreating it here. No new source/mode selector or direct Milvus access. Existing request timeout and privacy contracts remain intact.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No whole mobile UI rewrite, deleting unrelated user data, treating all 503s as no matches or shipping worker credentials in app config.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
