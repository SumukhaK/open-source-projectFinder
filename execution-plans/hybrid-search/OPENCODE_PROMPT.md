# Copy-ready session prompt

Use with the DeepSeek model already selected in OpenCode. Replace TASK_ID with one task ID, for example T03. Paste the matching task file too if the tool cannot read repository files. Do not paste secrets.

```text
Implement exactly TASK_ID from execution-plans/hybrid-search/TRACKER.md.

Read AGENTS.md, execution-plans/hybrid-search/README.md, REQUEST.md,
ARCHITECTURE.md, EXECUTION_GUIDE.md, REVIEW_CHECKLIST.md and the linked task.
Read the current code/callers/tests/fixtures/settings/CI before editing. Follow
the portable Ponytail rules: smallest complete readable solution, existing
helpers and standard library first, no speculative features or refactors.
Do not assume Codex plugins are installed in OpenCode or change billing/models.

Verify dependencies are merged into main and required policy decisions have
recorded approval. Preserve unrelated dirty work. Fetch origin/main and create
the task's named codex/ branch FROM origin/main; record the base SHA. Work only
there. If blocked, document the exact prerequisite; do not bypass it.

For each behavioral change write a meaningful test FIRST, run it to an expected
assertion failure (RED), then implement minimum code (GREEN), refactor and run
affected existing tests/lint/type checks. Record actual commands and results.
Mocks cannot establish real Milvus, GPU or restore success. Docs-only work uses
static checks. Keep security/coverage/CI gates unchanged and secrets ignored.

Use the task's acceptance criteria and explicit non-goals. Both healthy sources
serve the app's normal hybrid search. Archive-only cutoff/license/corpus rules
must not remove valid live-only results. Preserve legacy behavior and privacy.

Update relevant docs and tracker to Awaiting review, with evidence. Inspect the
staged diff, commit task files, push this branch and raise one PR against main.
Return PR URL, exact head SHA, RED/GREEN/check evidence and remaining limits.
Then STOP AND WAIT FOR REVIEW. Do not self-accept, create a review marker, merge,
change security exceptions or begin another task. For requested changes update
the same PR, rerun affected checks and wait for review of its new exact head.
Only an independent trusted review with passing required checks can mark the
task accepted; only its merge into main unblocks dependent tasks.
```
