# T11: Adapt GitHub candidates without breaking legacy search

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t11-keyword-candidates` |
| Prerequisites, merged into main | [T00](T00-readiness.md), [T10](T10-visibility.md) |
| Intended scope | existing discovery query/provider helpers + tests |

Read first: Actually merged legacy search/tests (PR #10 prerequisite); provider.read callers; current GitHub Search API documentation. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T11 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t11-keyword-candidates FROM origin/main; record base SHA.
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

Reuse the existing bounded keyword logic where practical for up to 100 live candidates, preserving legacy idea/page/per_page/sort/order/total behavior exactly as merged. Return candidate ranks plus incomplete/source status to the new internal pipeline. Translate only supported typed shared filters. A valid idea that cannot compile a safe keyword query marks this source query_not_supported without issuing a qualifiers-only broad search.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: unchanged legacy contract and default response sizes; long/stop-word/Unicode/operator-like input; incomplete_results; provider limit/error; typed filter escaping. GREEN: semantic input is not truncated to legacy keywords and unsupported compilation does not become endpoint-wide 422.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Existing legacy regression tests remain green. Live source retains its public/unarchived scope and does not inherit 365-day/pilot gates. Per-source status distinguishes completed-empty from unsupported/incomplete.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

Do not implement additional Cline operator phases or change legacy defaults here. Do not guess PR #10 is merged or cherry-pick its dirty branch to satisfy this dependency.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
