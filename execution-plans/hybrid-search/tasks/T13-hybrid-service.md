# T13: Orchestrate concurrent bounded hybrid retrieval

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t13-hybrid-service` |
| Prerequisites, merged into main | [T02](T02-embeddings.md), [T07](T07-milvus-adapter.md), [T10](T10-visibility.md), [T11](T11-keyword-candidates.md), [T12](T12-rank-fusion.md) |
| Intended scope | backend/app/services/discovery.py orchestration + tests |

Read first: App factory/injection and request limits; current HTTP/Milvus timeout semantics; ARCHITECTURE deadlines/failure table. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T13 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t13-hybrid-service FROM origin/main; record base SHA.
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

Invoke both healthy sources concurrently: full idea CPU embedding/Milvus and bounded GitHub keywords. Start at 200 Milvus chunks with bounded repository overfetch up to the supported ceiling (at most 1000), then validate/collapse/fuse. Carry remaining deadline through admission/clients/validation, initial overall budget 8s. Keep CPU/blocking clients off the event loop and cap outstanding work including timed-out jobs. Map one typed licence filter to both sources: the GitHub licence keyword for T11 (`mit`) and the SPDX ID for the Milvus/catalogue filter (`MIT`), from a single explicit mapping table; reject unmappable values before either source runs. Keep T11's reporting of a GitHub 422 (rejected query) as source status `failed`/`unavailable`; it degrades the request rather than failing it.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: a fused card with `license_conflict` shows the live licence and no archive snippet; the archive status passed to T12 fusion reflects the real Milvus/T10 outcome (failed, incomplete, ok). A licence filter selects the same licence on both sources (`mit` ↔ `MIT`, `apache-2.0` ↔ `Apache-2.0`) and an unmappable value is rejected with no source call; a GitHub 422 yields `failed`/`unavailable` live status with archive results still served. Prove concurrent start with barriers, one slow/failing/unsupported/incomplete branch with and without verified hits, both empty, missing index vs empty, validation failure, disconnect and overload. GREEN: timed-out/disconnected requests cannot grow an unbounded background thread/queue backlog.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Two healthy sources are actually invoked. Only complete-empty+complete-empty returns definitive empty; partial verified hits are degraded, partial zero is SEARCH_INCOMPLETE. Bounded cancellation/admission and source-health propagation have tests; no raw idea is persisted/logged. Licence filters are mapped from one table to GitHub keyword and SPDX forms and select the same set on both sources; a GitHub 422 is reported as `failed`/`unavailable` (accepted 2026-10-29), not an endpoint error. T12 follow-ups (2026-10-30): `license_conflict` cards drop the archive snippet and show the live licence; `archive_status` is derived from the actual archive outcome.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No public source selector, sequential eight-second waits per branch, unbounded asyncio.to_thread spawning or claiming CPU cancellation kills already running native work.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
