# T17: Persist runs, checkpoints and fenced worker leases

Status: Merged (`ca191fc`, 2026-10-30) after exact-head acceptance of `3c1c1d9`. Implementation and verification: [T17 evidence](../T17_EVIDENCE.md). Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t17-durable-runs` |
| Prerequisites, merged into main | [T03](T03-catalogue.md), [T08](T08-publication.md), [T16](T16-discovery-partitions.md) |
| Intended scope | archive_store run/task/partition migrations + tests |

Read first: Existing archive migrations, T08 publication/activation/cleanup code and pure partition outputs; ARCHITECTURE run/task schema and lease requirements. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T17 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t17-durable-runs FROM origin/main; record base SHA.
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

Add only now-needed runs/tasks/partitions and due-period uniqueness. Persist page/stage checkpoints, retries and lease heartbeat/expiry with monotonically increasing fences. Reject stale owners at catalogue publication/activation boundaries; fence-aware integration must serialize activation and cleanup safely. Keep transactions short with one active writer.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: two workers same period, expiry/takeover, stale writer after takeover, restart mid-page, retry-after beyond process lifetime and partial checkpoint rollback. GREEN: no duplicate run/activation or lost completed interval; migrations replay safely.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

A killed/restarted process resumes durable work without assuming its old lease is valid. Even if an old vector write finishes, it cannot activate, delete current data or make stale candidates visible. Coverage watermarks advance only completed partitions.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No Redis/Celery, long network calls inside SQL transactions, full-database lock held for embeddings or lease timestamps without fencing.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
