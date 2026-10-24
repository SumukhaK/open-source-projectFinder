# T10: Validate source-specific eligibility and public identity

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t10-visibility` |
| Prerequisites, merged into main | [T04](T04-archive-http.md), [T08](T08-publication.md) |
| Intended scope | discovery eligibility helpers/catalogue + tests |

Read first: ARCHITECTURE per-source eligibility; numeric identity and existing public details validation; approved T00 freshness policy. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T10 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t10-visibility FROM origin/main; record base SHA.
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

Implement small reusable serving checks for archive eligibility/current revision and live public/unarchived candidates. Archive cutoff is rolling UTC pushed_at; live eligibility has no automatic archive cutoff/membership/license-content gate. Require expected numeric ID on fresh validation/cache; use matching live public metadata once per request. Archive-only candidates need approved short-lived verification; suppress uncertain content and return structured incomplete status.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: exactly-at/over cutoff, older-created but recently-pushed, rename/old-name reuse, archived/private/404, stale/expired validation and GitHub outage. GREEN: valid older live-only hits remain; invalid archive evidence cannot attach to them.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Public checks are ID-bound with bounded TTL and no redundant check for a matching live hit. Invalid credentials do not purge the whole catalogue. A suppressed candidate cannot be resurrected by stale vector/cache data.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No global combined-list archive postfilter, weekly-only visibility guarantee, owner/name identity authorization or unapproved fail-open stale content.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
