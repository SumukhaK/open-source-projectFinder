# T12: Fuse repository candidates deterministically

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t12-rank-fusion` |
| Prerequisites, merged into main | [T10](T10-visibility.md), [T11](T11-keyword-candidates.md) |
| Intended scope | backend/app/services/discovery.py pure fusion helpers + tests |

Read first: ARCHITECTURE ranking/provenance and eligibility; actual candidate types from T10/T11. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T12 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t12-rank-fusion FROM origin/main; record base SHA.
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

Collapse archive chunks to one ranked repository before equal-weight app-level RRF, k=60. Fuse the source union by numeric ID with deterministic source-rank/ID tie breaks. Current live metadata wins card conflicts; archive snippets/provenance remain only if eligible/current. Preserve source health and nullable total; cap each source to 100 repositories. Compare and report licences by SPDX ID (GitHub items carry `license.spdx_id`), never by the GitHub filter keyword.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: GitHub-only/archive-only/common IDs, many chunks for one repo, equal scores, metadata conflicts, invalid archive evidence and repeated input order. GREEN: one deterministic card per ID and no invalid source attribution.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Hand-computed RRF fixtures agree with ranks. No source needs membership in the other; older valid live results survive. Source totals are not added and scores are never presented as match probabilities. A repository present in both sources gets one licence value, as an SPDX ID; a case or keyword-vs-SPDX mismatch (`mit` vs `MIT`) is not treated as a conflict and has a test.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No raw cosine-plus-rank arithmetic, generated descriptions, popularity reranking or configurable ranker framework.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
