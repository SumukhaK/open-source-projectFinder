# Acceptance and review record

Reviewer: read the task, its dependencies and current diff against main, not just the implementation's summary. Inspect connected callers and tests. Review the **exact current PR head**; record the full 40-character SHA and evidence link. Only trusted review acceptance with required passing checks can check the tracker row. Only merge unblocks dependents. No autonomous acceptance by the implementing DeepSeek session.

- The task stays within scope and has no unmerged dependency, unapproved policy choice or hidden prerequisite. Code uses existing patterns, small readable functions and central configuration; every new abstraction/library is justified by actual use.
- Behavioral RED is an expected assertion failure for the requirement, followed by GREEN and relevant regression checks. Fixtures cover failure and trust boundaries. Assertions prove outcomes rather than mirroring internals. Integration/hardware claims have corresponding real evidence.
- Check source-specific eligibility, union/dedup/RRF, model/token limits, identity/visibility, cursor isolation, source-failure empties, authenticated boundaries, bounded concurrency and data recovery where touched. No secrets/raw ideas in artifacts or logs.
- Migrations/backfill/publication/cleanup are resumable, bounded and reversible where possible; backup/restore evidence includes suppression reapplication. No feature shipped based on mocks alone.
- Non-blocking notes: if a named later task owns a note, add it to that task's RED list/acceptance criteria and to the "Verify closed" list in [T30](tasks/T30-upkeep.md); otherwise add it to T30's backlog at the post-merge tracker sync, with its source PR, problem and intended change.
- All current quality/security/coverage checks pass at that SHA. Inherited failures remain blockers; do not silently waive them. All important findings are fixed and rechecked. Record limits and explicit unavailable checks.

PR body template:

```text
Task: Txx — title
Base main SHA:
Current head SHA:
Prerequisite merged PRs/SHAs:
Approved decisions and authoritative API/version sources:

Problem and resulting behavior:
Scope/files and non-goals:
RED: command, expected assertion failure, date/platform
GREEN: command, result, date/platform
Regression/lint/type/security/integration checks: command + actual outcome
Real hardware/server evidence, or the precise blocking limitation:
Migration/data/rollback and operator actions:
Known limitations and follow-up (do not silently mark complete):

Review state: Awaiting review. Implementer has not accepted or merged this task.
```

Reviewer evidence template (post after review, not as a promise):

```text
Task and PR URL:
Reviewed head SHA:
Review verdict: Accepted / Changes requested / Blocked
Findings and resolutions:
Required CI run/check evidence at this SHA:
Manual/integration evidence and remaining limitations:
Reviewer identity/date and review permalink:
Merged main SHA (when merged):
```

After review, sync the tracker using a separately reviewed documentation change or the next authorized task PR; no extra implementation commit just to accept itself. Record an actual GitHub review permalink, not an invented approver or a local statement of approval. If the current repository permits a reviewed self-review workflow, a separately authorized reviewer/operator must still perform it; these implementation prompts intentionally stop at PR handoff.
