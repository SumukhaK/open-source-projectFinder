# T08: Publish revisions with crash-safe reconciliation

Status: Merged via [PR #30](https://github.com/SumukhaK/open-source-projectFinder/pull/30) as `952f7e2` (2026-10-28). Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t08-publication` |
| Prerequisites, merged into main | [T06](T06-raw-content.md), [T07](T07-milvus-adapter.md) |
| Intended scope | archive_index publication + catalogue/vector tests |

Read first: T03/T06/T07 implementation; ARCHITECTURE crash-safe publication rules. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T08 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t08-publication FROM origin/main; record base SHA.
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

Persist pending revisions/chunks, write deterministic vectors, verify the full expected set readable and then atomically activate the SQL revision. Retire old chunks only after safe activation; reconcile pending/orphan work on restart. Search exposes only eligible current SQL revisions. Keep the previous safe revision when an attempted update fails.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: kill/failure before files, mid-vector batch, after vectors/before activation, after activation/before cleanup; replay and shrinking chunk sets. GREEN: no pending/partial revision becomes visible and retries create no duplicate IDs.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

A failure-injection test exercises each store boundary. Active revision never references an incomplete vector set; orphan cleanup is repeatable and bounded. A real Milvus reconciliation check complements unit tests.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No distributed-transaction claim, SQL activation before vector verification, deleting the old safe revision on a failed update or skipping active-revision filtering.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
