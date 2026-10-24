# T29: Close rollout readiness and recovery documentation

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t29-rollout-readiness` |
| Prerequisites, merged into main | [T28](T28-capacity.md) |
| Intended scope | root docs/handbook tracker + final verification evidence |

Read first: All accepted review records/merged SHAs; runtime/status outputs; current README/REQUIREMENTS/SCOPE/PROJECT_TRACKER and diagram styling. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T29 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t29-rollout-readiness FROM origin/main; record base SHA.
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

Verify each predecessor is merged/accepted with current evidence and no unresolved important finding. Update actual tools/versions, architecture source+both themes, setup/start/stop/refresh/retry/backup/restore/disable runbooks, availability/coverage/privacy limits and root docs. Record real last-success, selected profile, quality/capacity outcomes and dependency audit. Provide a concrete rollout recommendation; deployment/host activation only within explicit operator authorization.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

Validate links/diagrams/tracker evidence, run affected final regression/security/integration checks, and rehearse documented recovery without deleting live data. No behavioral RED is needed for docs alone; any code fix discovered gets its own test-first task/PR.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Every completion claim maps to an exact review/check/real runtime artifact. All required current checks pass; schedule/backup/GPU limitations remain visible if not satisfied. The reviewer can operate and recover the pilot using docs alone.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No blanket complete checkbox for pending tasks, fabricated green CI, stale dependency exceptions, automatic launch or confusing this handbook publication with implementation completion.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
