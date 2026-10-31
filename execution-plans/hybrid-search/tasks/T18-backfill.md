# T18: Run a bounded resumable backfill

Status: In progress — Phase A (fake-only) merged as `aa5db53` (2026-10-31) from [PR #47](https://github.com/SumukhaK/open-source-projectFinder/pull/47); Phase B real run pending the owner's explicit "T18 real run approved". Not accepted until Phase B evidence, including the T16 per-partition real-search log, is reviewed. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t18-backfill` |
| Prerequisites, merged into main | [T09](T09-one-repository.md), [T16](T16-discovery-partitions.md), [T17](T17-durable-runs.md) |
| Intended scope | worker CLI bootstrap/resume + tests |

Read first: T00 approved policy/cap and T01 measured resources; discovery/lease/acquisition/publication implementations. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T18 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t18-backfill FROM origin/main; record base SHA.
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

Wire serial paced discovery and per-repository ingestion with durable checkpoints and independent REST/search budgets. Enforce approved 1k sample then 10k pilot limits, byte/disk/queue bounds and ~20% quota headroom based on actual headers. Capture language/activity/star distribution, deferred/unresolved partitions and truthful curated coverage. Pause long waits to retry-at and stop on credential failure.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: crash/restart at each checkpoint, cap/quota/disk stop, 429/secondary limits, incomplete discovery, duplicate IDs and invalid credential. GREEN: a bounded approved real sample resumes without duplication or lost work; unit runs use fake HTTP/model.

Carried over from T16: the partition planner has never run against real GitHub search (no P1 credential at T16 time). The first approved real run must log, per partition, the query, reported `total_count`, `incomplete_results`, pages read, IDs returned and the split/unresolved decision, and record whether the `…Z` time-range and `stars:` qualifiers behaved as documented. Missing this log blocks T18 acceptance.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Backfill can be interrupted/resumed and reports exact counts/gaps/bytes/requests. No full-year completeness claim follows from a capped or moving-index crawl. Resource budgets respect measured feasibility, not raw-vector arithmetic.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No unapproved bulk fetch, token rotation to evade limits, unlimited parallel fetches or 10k expansion before 1k evidence/approval.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
