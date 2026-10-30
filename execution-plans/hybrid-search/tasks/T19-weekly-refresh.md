# T19: Refresh weekly with content-aware change detection

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t19-weekly-refresh` |
| Prerequisites, merged into main | [T10](T10-visibility.md), [T17](T17-durable-runs.md), [T18](T18-backfill.md) |
| Intended scope | worker refresh/reconcile service + tests |

Read first: ARCHITECTURE weekly lifecycle and HTTP validator/hash rules; run/lease/publication code. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T19 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t19-weekly-refresh FROM origin/main; record base SHA.
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

Add manual refresh/resume for all selected known IDs plus recent discovery from last completed boundary minus48h and a rotating full-window sweep. Conditional metadata/README reads reuse valid cached bodies. Re-embed only changed semantic inputs/model/chunker; update scalar metadata without embedding stars. Remove obsolete README chunks via safe publication. Populate real last-attempt/last-complete status and keep partial runs explicit.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: README revert A→B→A after A was retired by T17 cleanup (must republish safely, not stay on B or report `failed`), 304 unchanged, changed description/topics with unchanged README, metadata-only stars, removed README, rename, model change, overlap gap, partial run and quota pause. GREEN: unchanged content makes zero embedding calls; failures never advance unfinished coverage watermarks.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Known IDs are reconciled even without new pushes. Date cutoff/selection remain source-specific. Status exposes actual success/partial/failure with no fabricated seven-day SLA, credentials or raw ideas. T17 follow-up (2026-10-30): a safe generation protocol (for example generation-salted chunk IDs) lets a repository return to previously retired content without reusing IDs a late Milvus delete could still target; the A→B→A regression passes.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No scheduler inside Uvicorn, pushed_at-only content hash, whole-corpus re-embedding each week or search-page absence treated as deletion.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
