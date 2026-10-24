# Execution rules for OpenCode

This folder is a portable execution contract. The user's selected DeepSeek model executes **one task per PR**. Codex skill names are provenance, not proof those plugins exist in OpenCode. These instructions carry over the useful rules from Ponytail, incremental planning, API design, source-driven development, TDD and code review. Read the repository's current AGENTS.md as well. Do not install plugins or change model/provider/billing settings to start a task.

## Start a task safely

1. Read README, REQUEST, ARCHITECTURE, this guide, TRACKER and the chosen task. Inspect current callers, tests, fixtures, settings, exports and CI before editing. Resolve any mismatch against merged main; a draft task's proposed path is not an existing interface.
2. Verify prerequisite PRs are actually merged into main. An accepted checkbox alone is insufficient. Resolve only decisions the task depends on; record other blockers and continue independent work.
3. Inspect git status. Preserve unrelated work; never reset, stash, clean or cherry-pick someone else's changes. If the checkout is dirty, use a clean approved worktree or report the isolation needed. Do not overwrite an existing branch.
4. Fetch origin main, then cut the task's named `codex/` branch **from origin/main**, not another feature branch. Example for a clean checkout: `git fetch origin main`, then `git switch -c codex/hybrid-t03-catalogue origin/main`. Record base SHA. Do not create another GitHub repository.
5. Run the relevant baseline checks; distinguish inherited failures from your changes. Do not hide either. Read official docs for changed APIs and pin a compatible runtime/library set when needed. Capture source links/version, not copied outdated examples.

## Tests first, minimum implementation second

Write a meaningful test for the next observable behavior, run it and save its expected assertion failure (RED). A syntax error, missing dependency, network outage or broken test setup is not behavioral RED. Then write the smallest readable implementation (GREEN), run the same test, refactor only the touched logic and rerun affected existing tests. Repeat for distinct behaviors within this task; do not implement future tasks first. Prefer fixed clocks, fake HTTP transports and explicit fixtures over real GitHub/model/network calls in unit tests.

Keep the repository's layers and naming. Reuse current helpers where their guarantees fit; use the standard library before a dependency. No generic repository framework, configurable search engine, plugin registry, speculative interface, service locator, unrelated rename or formatting sweep. Add a shared abstraction only for real callers in this task. Keep short functions and ordinary typed data; explain non-obvious safety decisions in one-line comments. A documented bounded shortcut uses `shortcut: <limit>, <when to upgrade>`; it cannot excuse security, data-loss, validation or accessibility gaps.

Aim for about 1-5 production files per slice plus meaningful tests and required docs. If the actual scope is larger, propose a split in the tracker and wait for plan review instead of hiding a large feature in one PR. Documentation/config-only tasks use relevant static validation and inspection, not fake application tests. Test the boundary where the requirement can fail; a mock-only test cannot prove Milvus, CUDA, HTTP integration or recovery works.

## Non-negotiable product and safety rules

- A normal new search invokes both healthy sources. The full idea goes to the local model; keyword extraction is only for GitHub. Results are a union, deduplicated by GitHub numeric ID. Collapse archive chunks before app-level RRF (equal weights, k=60). No raw-score addition or percentage-similarity claims.
- The 365-day cutoff, archive membership, license-content policy and pilot cap apply to the archive branch. Valid live-only and older live results survive. Shared explicit filters are applied consistently using typed allowlisted values, never raw search/filter expressions.
- Preserve legacy `/projects/search` behavior as actually merged. `/v1/projects/search` is the sole new app search flow: idea 2-1000 characters, page_size 1-50 (initial default 20), cursor, typed language/license filters, relevance ranking. No mode/source selector. Do not silently add advanced GitHub operators to the legacy endpoint.
- A failed/incomplete/unsupported source with verified hits is a degraded success; with zero verified hits it is `503 SEARCH_INCOMPLETE`. Only two completed successful empty sources justify definitive no matches. A declared curated archive is coverage, not a retrieval failure. A missing index/model is not an empty archive.
- Authenticate search/status and retain existing request/quota protections. No public ingestion admin API. Never use end-user OAuth credentials for background ingestion. Never expose worker tokens, raw provider errors, file paths or README payloads in status/logs.
- Do not persist raw ideas, transcripts or query embeddings. Cursor snapshots hold bounded IDs/ranks/source status for five minutes, account/query/filter/model/ranking bound; new source recovery requires a fresh search. Keep cached mobile results/account privacy and offline consent behavior intact.
- Numeric ID must match every fresh metadata/redirect response. Old owner/name reuse cannot authorize old content. Archive results must have a current eligible active revision and bounded public validation; failures cannot be bypassed to fill a page.
- SQLite/catalogue + private bounded raw files are the archive; Milvus is rebuildable. There is no cross-store transaction. Stage vectors before SQL activation, postfilter pending/old revisions and reconcile retries. Keep auth DB separate. Check the worker's linked SQLite WAL fix before enabling WAL.
- Bound input bytes, parse work, token counts, chunks, concurrency, queues, retries, top-K, disk and VRAM. Keep blocking CPU/clients off the async event loop and propagate deadlines. No executing repository code, cloning, following README links, downloading images or trusting model remote code.
- Keep services private/authenticated; secrets stay in central settings/environment and ignored files. No security exceptions, CI exclusions, weaker thresholds, skipped required jobs or paid services merely to pass a task. Never run `npm audit fix --force` or blind cross-major overrides.

## Verification commands

Use the repository's supported Python environment; `python` below means that environment (the archive runtime is WSL/Linux, not proof from Windows). From repository root, choose focused tests first:

```text
python -m pytest backend/tests/test_<area>.py scripts/tests/test_<area>.py
ruff check backend scripts
ruff format --check backend scripts
python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:reports/backend-coverage.json
python scripts/quality.py coverage reports/backend-coverage.json
bandit -r backend/app
```

Replace test placeholders with real touched tests; omit nonexistent/unaffected suites. Create ignored reports/ when needed. The backend policy requires combined coverage >=90%, branches >=80%; do not lower it or game coverage. Pin new dependencies using the existing requirements/lock process and audit their complete resolved tree.

For mobile changes, from mobile/:

```text
npm ci
npm run typecheck
npm run lint
npm test -- --runTestsByPath tests/<area>.test.tsx
npm run test:coverage
```

Use npm.cmd in PowerShell if needed. Run npm ci only in your isolated checkout. Reuse CI's E2E environment (`RUN_AUTH_E2E=1`, `PYTHON_EXECUTABLE` pointing at the selected Python) and export checks when mobile integration/config changes. Exact commands/coverage thresholds are defined by current `.github/workflows/quality.yml`, `.ci/quality-policy.json` and mobile package scripts; re-read them rather than copying this handbook forever.

For lock changes, capture `pip-audit --strict --no-deps --disable-pip -r backend/requirements.lock.txt -f json -o reports/python-audit.json` and `npm audit --package-lock-only --json` in mobile/, then apply `scripts/quality.py pip/npm` to those reports. Findings exit 1 is not a scanner execution error; do not swallow error exits or omit reports. For docs-only work check local links, identifiers/dependency order, fenced blocks, diagram XML/themes and `git diff --check`. Required remote CI still runs; documentation does not bypass it.

Record command, platform/version, date, exit code and the behavior the result proves. Keep artifacts/logs ignored and sanitized. Run real Milvus/WSL/GPU integration where the task requires it; mark unavailable checks blocked instead of manufacturing a pass. Do not repeatedly run the full suite if nothing changed after a valid pass.

## PR, review and completion

Update affected root requirements/scope/README/tracker only for actual changes; keep planned capabilities labeled planned. Put task evidence in the PR template in REVIEW_CHECKLIST. Stage explicit task files, inspect staged diff and secrets, commit clearly, push your task branch and open one PR targeting main. Add the task ID, base/head SHA, RED/GREEN evidence, focused/full checks, source/version decisions, migrations/rollback and material limits. Set the tracker row to Awaiting review with the PR URL; do not mark accepted yourself. Stop and wait for review. Do not merge, approve yourself or automatically start the next task.

If review requests changes, address them on this branch, rerun affected checks and request a fresh review of the new head. Never leave known important findings open and mark done. The human/trusted reviewer verifies the exact current head and all repository checks/rules before acceptance or merge. The reviewed-merge workflow, when available on main, belongs to that reviewer; the implementing model must not forge its marker or dispatch it as self-approval.

The tracker checkbox means review acceptance, not implementation claimed. A later task depends on the predecessor being **merged into main**. A post-review implementation commit invalidates acceptance. Do not amend the implementation PR merely to tick its own accepted checkbox: the review is authoritative, and a separately reviewed documentation sync (or the next authorized task PR) records the accepted/merged SHA. This avoids invalidating the very review being recorded.
