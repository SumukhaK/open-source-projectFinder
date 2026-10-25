# T01: Prove local Milvus CPU/GPU feasibility

Status: Merged (PR #15, `7f94e2f`); CPU and GPU 1k proofs passed. Host/archive capacity and the worker SQLite WAL prerequisite for T03 remain open. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t01-milvus-feasibility` |
| Prerequisites, merged into main | [T00](T00-readiness.md) |
| Intended scope | infra/milvus + bounded integration probe |

Read first: ARCHITECTURE sections 3-4; current infra conventions, requirements and official versioned Milvus/NVIDIA/WSL documentation. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T01 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t01-milvus-feasibility FROM origin/main; record base SHA.
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

Choose and pin a compatible Milvus/SDK/runtime set. Add minimal private/authenticated Compose profiles and a runbook. Before implementation write a bounded probe for build/load/search/filter/upsert/delete using a synthetic 1k sample; run CPU baseline and actual GPU profile on WSL. Check linked SQLite WAL fix, disk and RAM/VRAM peaks. Record exact index/metric/device/driver versions and a bounded resource budget.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: the integration probe exposes the absent/unusable deployment or unsupported operation, labeled as environment failure rather than behavioral unit RED. Add assertion tests for any nontrivial probe/config validation. GREEN requires an actual server result; CPU cannot satisfy GPU proof.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Pinned CPU profile passes real operations; GPU evidence either passes the same checks with measured device use or is explicitly blocked pending an approved CPU-only change. No unsafe public bind/default credentials; measured rebuild/steady memory and SQLite runtime evidence are recorded.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No Linux display driver install inside WSL, automatic host memory/disk/driver changes, unbounded image downloads, GPU embedding competition or claims that pool limits cap total VRAM.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
