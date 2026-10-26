# T03: Add the isolated archive catalogue

Status: Merged via PR #18 (`776bf654`, 2026-10-26). Implementation and real WSL verification: [T03 evidence](../T03_EVIDENCE.md). Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t03-catalogue` |
| Prerequisites, merged into main | [T00](T00-readiness.md), [T01](T01-milvus-feasibility.md) |
| Intended scope | backend/app/core/config.py and archive_store.py + migrations/tests |

Read first: core/config.py; core/store.py; ARCHITECTURE schema/publication sections; SQLite backup/WAL documentation. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T03 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t03-catalogue FROM origin/main; record base SHA.
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

Add central bounded archive settings and the initial repository/document/chunk catalogue in a separate private database. Use numeric repository IDs, revision states, short transactions and versioned migrations. Reuse plain sqlite3 patterns. Verify the linked runtime includes the WAL-reset fix before enabling WAL; keep auth migrations untouched. Add only tables used now; durable run/task tables belong to T17.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: migration idempotence, restart persistence, uniqueness/foreign-key constraints, transaction rollback and rejected unpatched WAL runtime. GREEN: tests prove auth data is untouched and separate catalogue paths/permissions work.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

A clean install and repeated migration preserve data and stable IDs. Pending/active revision state is expressible without starting external services. Invalid settings fail clearly and no secret is logged.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No resetting existing databases, auth-store merge, generic ORM, speculative tables, hard-coded environment reads or enabling WAL based solely on Python version.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
