# T26: Verify the cross-layer hybrid path over real HTTP

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t26-hybrid-integration` |
| Prerequisites, merged into main | [T09](T09-one-repository.md), [T15](T15-hybrid-api.md), [T22](T22-restore.md), [T25](T25-mobile-results.md) |
| Intended scope | focused integration harness/tests and CI entry point |

Read first: Existing auth E2E setup; real Milvus CPU profile; mobile adapter/backend contract; T01/T02 hardware/model evidence. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T26 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t26-hybrid-integration FROM origin/main; record base SHA.
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

Add the smallest repeatable integration lane using real FastAPI HTTP and real CPU Milvus with fake upstream GitHub transport and deterministic fixture embeddings. Keep this separate from live model/GPU claims. Exercise archive ingestion/publication, authenticated mobile request, union/dedup/ranking/pages and private suppression/restart. Integrate as a bounded free CI/manual lane with explicit runtime requirements.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: assertion-level cross-layer regressions (wrong endpoint/provenance/pages, private record leakage, incomplete-empty mislabel). GREEN: actual HTTP/server/store assertions pass; fixture cleanup is confined to test resources and cannot delete operator data.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

A real adapter-to-HTTP-to-Milvus path is demonstrated, not a route test mocking the discovery service. Shared auth/legacy/mobile tests remain green. If hosted CI cannot run the service affordably, require evidenced local integration before review instead of skipping it silently.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No live GitHub credentials/model downloads in deterministic CI, arbitrary test volume deletion, GPU-pass claim from CPU CI or unlimited runner minutes.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
