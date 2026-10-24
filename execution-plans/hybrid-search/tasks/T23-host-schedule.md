# T23: Prepare weekly host scheduling and operator status

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t23-host-schedule` |
| Prerequisites, merged into main | [T19](T19-weekly-refresh.md), [T20](T20-retirement.md), [T22](T22-restore.md) |
| Intended scope | host scheduler templates/runbook + focused tests |

Read first: Approved schedule; actual WSL path/runtime and lease/status commands; Windows Task Scheduler/systemd documentation. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T23 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t23-host-schedule FROM origin/main; record base SHA.
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

Provide the minimal Windows Task Scheduler -> WSL worker invocation/template for the approved weekly time (proposal Sunday03:30 Asia/Kolkata), missed-run catch-up and no overlapping instance. Pin due-period keys so manual/scheduled/restarted attempts resume one run. Document enable/disable/status/retry and credential handling. Do not install/activate host tasks without explicit operator activation approval; retain truthful manual operation until then.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: timezone/week boundary, duplicate/missed period and overlapping launch in any nontrivial period calculation. GREEN: bounded manual launch and approved scheduler dry-run demonstrate correct command/exit/lease behavior; actual scheduling stays pending if activation is not approved.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Actual last-success/partial/next-due status is visible and sanitized. Sleeping/offline laptop limits are stated. One host scheduler only; logs contain counts/timings/version IDs, not ideas/tokens/README.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No automation service/plugin reminder instead of app scheduling, implicit OS task installation, always-running in-process scheduler or promise a sleeping laptop refreshes weekly.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
