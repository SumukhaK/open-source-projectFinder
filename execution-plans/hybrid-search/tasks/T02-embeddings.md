# T02: Pin a CPU embedding adapter and manifest

Status: Awaiting review; CPU adapter, manifest, tests and benchmark passed. Review/merge evidence belongs in [TRACKER](../TRACKER.md) and [T02_EVIDENCE](../T02_EVIDENCE.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t02-embeddings` |
| Prerequisites, merged into main | [T01](T01-milvus-feasibility.md) |
| Intended scope | backend/app/services/embeddings.py + dependencies + tests |

Read first: ARCHITECTURE section 7; Settings; existing dependency/lock process; model publisher card and Sentence Transformers documentation. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T02 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t02-embeddings FROM origin/main; record base SHA.
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

Implement the smallest CPU adapter for intfloat/multilingual-e5-small using an immutable safe-weight revision, matching tokenizer, normalized 384-dimensional vectors, query:/passage: prefixes and explicit 512-token enforcement. Keep model loading warmed/bounded and injectable for tests. Record compatible dependency pins and the model manifest; benchmark a small approved sample.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: incorrect prefixes, overflow after prefix, invalid/NaN/wrong-dimension vectors and manifest mismatch are rejected; tests use a deterministic fixture encoder. GREEN: real local model smoke checks both query and passage dimensions/norms without remote model code.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Both paths share the immutable manifest and full idea input within its documented token budget. Real CPU startup/throughput/memory evidence exists separately from mocks. Unit checks do not download models; dependencies and safe-weight provenance are pinned/audited.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No paid embedding API, LLM paraphrasing, GPU model loading, query persistence or generic model-provider framework. Do not silently claim a 1000-character idea always fits 512 tokens.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
