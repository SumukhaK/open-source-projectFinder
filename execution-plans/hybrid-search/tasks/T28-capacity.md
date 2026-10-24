# T28: Measure capacity and foreground fairness before expansion

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t28-capacity` |
| Prerequisites, merged into main | [T23](T23-host-schedule.md), [T26](T26-hybrid-integration.md), [T27](T27-relevance-evaluation.md) |
| Intended scope | bounded benchmark/runbook + focused assertions |

Read first: T01 resource envelope; real model/worker/service; corpus distribution/coverage; latency hypotheses and quality results. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T28 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t28-capacity FROM origin/main; record base SHA.
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

Measure 1k then approved10k corpus at stated chunks/concurrency, CPU embedding throughput, foreground hybrid p50/p95 and total memory/VRAM/disk including rebuilds/backups. Test refresh concurrent with user search and bounded quota/CPU admission. Compare CPU vs GPU empirically; set measured central limits and document approved expansion gates for25k/50k without activating them.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: any new limiter/control has failing boundary/fairness tests first. GREEN: bounded real load run includes timeout/queue behavior, VRAM pressure and halt-before-disk-exhaustion. Preserve units, versions and raw sanitized measurements.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

No OOM/sustained swapping or starved foreground requests at approved limits. Proposed warm semantic p95<2s/hybrid p95<5s are measured hypotheses, not guaranteed until approved. If targets fail, stop expansion and report a revised cap/limitation for approval.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No automatically growing corpus, unbounded soak tests, estimating total VRAM from vectors alone, hiding GPU fallback or paid infrastructure purchase.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
