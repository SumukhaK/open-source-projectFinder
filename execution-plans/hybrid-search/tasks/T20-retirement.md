# T20: Suppress and retire unsafe or expired archive content

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t20-retirement` |
| Prerequisites, merged into main | [T10](T10-visibility.md), [T19](T19-weekly-refresh.md) |
| Intended scope | archive purge/suppression lifecycle + tests |

Read first: Approved retention/license policy; visibility and revision filtering; ARCHITECTURE retirement and private-content rules. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T20 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t20-retirement FROM origin/main; record base SHA.
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

Implement immediate logical suppression for known private/inaccessible/archived/license-ineligible/expired records, followed by bounded idempotent vector/raw/normalized/snippet cleanup. Maintain a durable content-free suppression ledger outside historical backups for restore reapplication. Keep ambiguous missing/private vs confirmed deletion distinct and retry with valid identity. Superseded/raw/run retention uses approved periods; favourites remain separate user data.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: public-to-private, archive/cutoff boundary, missing README vs repo404, credential outage, repeated purge, old vectors and stale file references. GREEN: suppressed content never serves during partial cleanup and ledger survives restart.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Confirmed unsafe live content overrides ordinary superseded retention. Ledger retains only necessary ID/reason/time/version, not README/user text or credentials. Quota/5xx/expired token does not wipe the catalogue; cleanup cannot remove a current safe revision by stale task.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No immediate-erasure claim for offline backups, deleting favourites to purge vectors or permanent deletion inferred from a missing search page.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
