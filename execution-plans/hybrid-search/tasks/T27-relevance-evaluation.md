# T27: Evaluate relevance on a human-judged query set

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t27-relevance-evaluation` |
| Prerequisites, merged into main | [T26](T26-hybrid-integration.md) |
| Intended scope | small offline evaluation script/data/runbook + tests |

Read first: ARCHITECTURE evaluation goals; approved T00 thresholds; actual ranking/coverage/model versions. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T27 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t27-relevance-evaluation FROM origin/main; record base SHA.
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

Prepare at least50 diverse human-judged ideas across languages, rare/common topics and no-match cases with provenance/licensing-safe fixtures. Freeze a corpus/snapshot and compare keyword-only, archive-only and hybrid offline evaluation runs (not public product modes). Measure nDCG@10 and Recall@20 within a disclosed judged pool, source contributions and failure cases. Record judgments/uncertainty and tuning decisions.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: hand-computed metric examples, ties/empty pools and invalid/missing judgments. GREEN: reproducible evaluation outputs at pinned model/ranking/corpus versions; human judges, not the implementing model, approve labels.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

At least50 reviewed labels and a fair frozen baseline comparison exist. Recall is explicitly judged-pool recall, not global GitHub recall. Improvements/latency tradeoffs and failure examples meet recorded acceptance thresholds or remain blocked.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No fabricated ground truth, LLM-only labels accepted as human review, storing real user query logs, overfitting the test set or declaring similarity from star counts.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
