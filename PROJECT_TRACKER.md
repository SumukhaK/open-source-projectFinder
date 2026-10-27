# Project Tracker

## Dependency security remediation and PR delivery - 2026-10-24

User request (verbatim): "merge both the pr s to main then"

Plan: retain useful search PR #10; fix inherited Python advisories and verify a scoped Expo CLI Zod 4 migration with tests first on a separate main-based branch. Preserve security/coverage/review gates and unrelated workspace work. Review and merge the remediation PR only after local checks and exact-head CI pass, then update/review/merge PRs #10 and #11 against current main.

Dependency delivery complete: [PR #12](https://github.com/SumukhaK/open-source-projectFinder/pull/12) merged as be74b1a3b5f3a583787f1d40d62b627881bca005 after independent review of 163e77deb6542d5adc128ed8a49dcf5d543d7388 and passing [CI 40083752223](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40083752223). The bounded-array regression failed with 1,001 issues before the scoped Zod upgrade and passes with one rejection afterward; actual Expo plugin/output/MCP schema compatibility tests pass. Verification: 32 backend/policy tests (93.7% combined coverage, 87.5% branches), 29 mobile unit tests plus the real-HTTP auth E2E, lint/type/format/Bandit, deterministic asset generation and Android/iOS/web exports passed. Python audit reports no known vulnerabilities; npm passes the unchanged policy with only the pre-existing node-forge exception. No new exceptions were added. Native-device and authenticated live-GitHub search checks remain outside this tooling change.

## Current state
Core idea received on 2026-10-02. Project name: RepoRadar. Repository: SumukhaK/open-source-projectFinder (private initially). Confirmed stack: Python FastAPI, React mobile client, Milvus, GitHub Search API. Detailed brainstorming remains pending.

## Workflow preparation
- [x] Read Karpathy guidelines and extract additional reusable engineering instructions.
- [x] Create AGENTS.md.
- [x] Preserve the initial workflow prompt below.
- [x] Receive the project-specific prompt (recorded below). Brainstorming continues feature by feature; detailed requests are recorded in each feature section.
- [x] Extract technical requirements, scope, decisions, and unresolved questions (REQUIREMENTS.md, SCOPE.md and the feature sections below).
- [x] Define feature phases, dependencies, acceptance criteria, and verification checks for each delivered feature and the hybrid-search handbook.
- [x] Create README.md with planned architecture and selected tools, REQUIREMENTS.md, and SCOPE.md.
- [x] Establish the GitHub repository identity and initialize the repository.
- [ ] Implement features through TDD, feature branches, pull requests, review, and merge (ongoing; PRs #1-#13 delivered this way).

## Feature phase tracking
Populate after project scope is established. For each feature record phase, status (planned / in progress / in review / blocked / complete), dependencies, acceptance criteria, tests and results, branch, PR, and documentation updates. Record blockers and unresolved questions explicitly.

## Initial workflow prompt (verbatim)

```text
here are some common instruction i use every time i build a project with AI. read them most of them are inspired from karpathy-guidelines u already inherited, so add whats missed out. once im done brainstorming project  idea end to end i shall give you project specific prompt instructions.

 you act like a a senior software architect, go through this prompt and extract whats suitable for agent.md from them and add them there and take rest of the informations as project requirements and implementation guidelines. once done reading, analyse it deeply, plan the project and features to implement in each phases of the project and record them in a md file in project folder and update them as we accomplish implemntation of each phases. record this initial prompt as well in that tracker md. update the project readme with a high level of architecture diagram of what we are planning to do and update the same readme with short details as we implement each phase succesfully. Think and analyse before acting, read the existing code before making edits or updates. if there s a bug, read the code, understand and then plan before fixing it. fixing one bug should not break existing and working parts of the project. Create a remote repo in my github with a readme file and push code feature by feature by creating branches and merge them once its reviewed by you. In project readme, keep high level architecure diagram, project s brief descrption, tools and libraries used. Create a separate readme for project requirement in techincal terms and a separate readme for explaining the project and its scope to non technical people, another tracker file where you mention the planned phases of this multi agent system and put tracker with them to mark it for update as we continue to execute the project.

use TDD, write unit tests before writing actaul code. divide tasks into features and write code accordingly and push them to git with approriate commmit messages. each feature should first open a PR in git. Review the code and merge if its fine, if it changes the status to "Request changes" act on them accordingly. also the code should be simple, human readable and human understandable format. do not assume anything, do not make up anything. ask if confused. keep all the api keys and sensitive data in env and do not push them. keep all configurations related settings in one file and at one place.
```

## Project-specific prompt
```text
feel free to create a remote git repo with the name "open-source-projectFinder" or come up with some cool nickname for the project and use it as github project. we are going to build an AI driven backend and a front end mobile app in react for it as a client. our ultimate goal is to let user share their project idea using voice or text using app, backend will go through github public repo s to see if similiar idea is already implemented. we are going to use milvus vector db to store massive data we download from git periodically and also use github search api to give hybrid search advantage to our users. this is the core idea, details i will share later, use this to plan folder structures withinh the laptop file system and git repo and add a project level readme, figure out a catchy name and push the empty project repo to github. we will stick with python fast api s for backend
```

## Preliminary phases (revise after brainstorming)

| Phase | Features | Status | Verification |
| --- | --- | --- | --- |
| 0 | Repository, folder scaffold, architecture and scope documents | Complete | Diff reviewed; secret exclusions verified; pushed scaffold PR #1; GitGuardian check passed |
| 1 | Finalize requirements, API contract, providers and evaluation criteria | In progress | Hybrid contract proposed in execution-plans/hybrid-search; T00 merged; eight operator decisions (D1-D8) still pending |
| 2 | Text idea submission and GitHub search baseline | Backend complete; mobile pending | Backend keyword search, details and favourites merged (#9, #10, plus fixes below); mobile discovery UI unmerged |
| 3 | Periodic ingestion, embeddings and Milvus index | In progress: T01 Milvus feasibility and T02 CPU embeddings merged; T03 catalogue awaiting review with fixed worker SQLite 3.53.1; T04-T09, T16-T23 planned | Repeatable ingestion, deduplication, updates and retrieval checks |
| 4 | Hybrid retrieval, ranking and AI similarity explanations | Planned (T10-T15, T27) | Agreed relevance evaluation, provenance and failure handling |
| 5 | Mobile text discovery flow | Planned (blocked on unmerged mobile foundation; T24-T26) | Client tests and end-to-end submission/results verification |
| 6 | Voice submission and transcription | Planned | Voice-to-search flow and privacy/error behavior verification |
| 7 | Scale validation and deployment readiness | Planned | Agreed performance, reliability and deployment checks |

These phases are provisional. The mobile foundation and authentication now have installed dependencies and application code. React Native with Expo is now selected for the mobile branding foundation. Future feature entries must record branches, PRs, test results and documentation changes.


## Phase 0 review record
Branch: chore/project-scaffold. PR: https://github.com/SumukhaK/open-source-projectFinder/pull/1. Reviewed documentation and directory boundaries; no application tests apply to this documentation-only scaffold. Verified environment files are ignored and no runtime secrets are tracked. Merge follows final whitespace validation and remote checks.

## Branding decision - 2026-10-02

User selection: Bracket Navigator. Saved the chosen concept board and documented the blue/navy direction, dark/light modes, and platform-specific launch/icon requirements in docs/BRANDING.md. Branch: docs/bracket-navigator-brand. Decision and reference preservation complete; production exports and mobile integration remain part of the mobile phase. Verification: reviewed concept and documentation, confirmed reference file exists, and checked diff whitespace. No application tests apply to this asset/documentation update.

User follow-up: 'and use app icon bracket navigator as loading animation throughout the app'. Added the shared loading requirement to technical requirements and branding guidance. Proposed motion: stationary brackets with a gently moving needle; final timing and reusable mobile component remain pending. PR: https://github.com/SumukhaK/open-source-projectFinder/pull/2.

## Mobile branding implementation - 2026-10-02

User authorization: "go ahead and build it and push it to git. open PR, review it yourself and then merge".
Architecture follow-up: "use Bulletproof React  architecture guide on the app side".

Branch: feat/mobile-branding. Scope: mobile foundation only; search and voice functionality remain pending.

- [x] Adapt Bulletproof React structure for React Native and Expo.
- [x] Write theme and loader tests before implementation; confirm missing modules fail the initial test run.
- [x] Implement shared vector geometry and generate iOS light/dark/tinted and Android adaptive/monochrome exports.
- [x] Configure native themed splash and minimal iOS launch background without artificial delay.
- [x] Implement saved appearance settings and accessible loader with Reduce Motion and cleanup.
- [x] Add a working branding preview screen and screen interaction test.
- [x] Run tests (8 passing), typecheck, lint, Expo diagnostics (21/21), and iOS/Android/web bundle exports.
- [x] Inspect the browser preview at phone width; theme switching and loader toggle work.
- [x] Complete final checks after accessibility review correction; open and review PR #3.
- Delivery PR: https://github.com/SumukhaK/open-source-projectFinder/pull/3 (merge status tracked on GitHub).
- [ ] Validate native release launch screens, icons and accessibility on physical iOS/Android devices.

No backend endpoints, artificial searches or voice permissions were introduced. Native builds need signing and store identifiers to be configured later. The npm audit reports 13 inherited Expo tooling advisories (9 moderate, 4 high), rooted in uuid and node-forge. A current patched node-forge release was unavailable at inspection; the suggested forced Expo downgrade would break SDK compatibility. Dependency findings are recorded as outstanding rather than claiming a clean audit.

Final review: corrected radio checked-state accessibility, centralized on-accent colors, and removed generated SVG whitespace. Confirmed 8 passing tests, clean type/lint checks, and successful cross-platform exports. Browser validation confirms restored appearance and checked state after reload. No unresolved code-review findings; native device checks and dependency advisories remain recorded above.

## Architecture diagram readability - 2026-10-02

User requested a minimal background-matched diagram and asked for an issue only if its five-minute closure was guaranteed to earn a GitHub achievement. Badge eligibility could not be guaranteed. The user subsequently requested issue opening and closing anyway; opened issue #5 and linked its fix to PR #4.

Replaced the README diagram presentation with neutral light/dark SVG variants, preserving the same logical architecture and its editable Mermaid source. Added future styling guidance to AGENTS.md and docs/DIAGRAMS.md. Validation: XML parsing, review of flow and labels, visual inspection of both theme variants, and diff whitespace checks. No runtime behavior changes or application tests are needed.

## GitHub authentication - 2026-10-02

Original request: "okay then, plan this from end to end. start implementing back end first and always run the tests before and after implemntation for confirmations, implement rate limiter and incremental time retries to keep it safe from attacks. once back end implementation is done plan a simple ui page and implement front end , unit tests first agan. and finally test it end to end"

Branch: feat/github-auth. Existing mobile baseline: 8 tests pass. Backend has no existing executable tests.

- [x] Backend TDD: OAuth state and PKCE, expiring one-use handoff, identity upsert, encrypted GitHub credentials, hashed revocable app sessions.
- [x] Persistent per-IP rate limits, bounded incremental retry on safe GitHub identity reads, explicit failures and provider timeouts.
- [x] Backend integration tests cover successful signup/login/logout, replay, expiry, bad proof and throttling before mobile work.
- [x] Mobile TDD: single GitHub sign-in page, browser authorization, secure native session persistence, session restore and logout, branded pending/error states.
- [x] Cross-layer automated flow and mobile checks; live GitHub and physical-device validation require OAuth registration/development builds.
- [x] Documentation and self-review; PR #6 opened. Remote check/merge status is recorded on the linked PR.

Authentication uses no private-repository permission. GitHub credentials stay encrypted on the server; the mobile receives a separate RepoRadar session. SQLite is the initial persistent store on one deployment host; distributed deployment needs shared database/rate-limit infrastructure. Authorization-code exchanges are never blindly retried because the code may already be consumed; safe identity reads retry transient errors with bounded exponential delay and jitter. Rate limiting reduces abuse but is not a substitute for infrastructure DDoS protection.

Verification: backend tests fail before implementation, then 11 pass; existing mobile baseline 8 pass, new auth tests fail before implementation, then 18 mobile tests pass including the real HTTP UI/backend/SQLite flow. Typecheck passes after correcting a test enum type. Added backend lint/format checks and cross-layer CI. Self-review preserves appearance controls, enforces callback/authorization destinations and tests atomic consumption/persistent limits. Live GitHub and physical-device verification remain pending credentials/native builds. Provider refresh remains a search-phase responsibility; app sessions expire no later than reported provider expiry.

Final checks: 11 backend tests and 18 mobile tests pass, including cross-layer HTTP. Typecheck and lint pass; Android/iOS/web exports succeed. User confirmed OAuth app is not yet registered; live GitHub authorization remains pending setup. UI plan: branded heading, one GitHub action, accessible pending/error status, saved appearance controls, and a simple signed-in account/sign-out page.

Review correction: a failing regression test reproduced early retries for GitHub 429 responses with no timing headers. Corrected the policy to fail immediately, respecting GitHub's minimum wait; centralized provider retry/timeout and body-size settings. Backend tests now total 11 passing. Expo diagnostics: 21/21 checks pass. Browser review confirms readable branded dark-theme login and working appearance controls. User registered the OAuth app in Firefox. Verified backend/.env loads both locally entered OAuth credentials, a valid encryption key and correct callback/allowlist; no secret values displayed or tracked.

Delivery: https://github.com/SumukhaK/open-source-projectFinder/pull/6. Self-review found no unresolved implementation findings after the retry regression correction. CI gates the merge; live OAuth browser/native device validation remains separate from the simulated-provider automated flow.

## Quality pipeline phase - 2026-10-02

Original request: "okay i just mentioned the stack i knew, u check whats standard for the tech stack we are using and use open source free tools to implement them, no api key insertions or paid tools. plan it and implement it as next phase before we move forward"

Branch: chore/quality-pipeline. Scope: strengthen validation and review-controlled delivery before product features. No manually configured API keys or paid scanner services. GitHub Actions uses its built-in short-lived token only for checkout and explicitly dispatched reviewed merges. Hosted runner usage remains subject to the account's included quota; no paid plan changes.

1. Measure existing backend/mobile tests and coverage; choose realistic explicit gates.
2. Add free Python/TypeScript SAST, dependency auditing with reviewed expiring exceptions, and full-history secret scanning. Fail scanner/tool errors.
3. Consolidate CI into parallel jobs with an always-running final quality gate, bounded timeouts, pinned tooling and concise report artifacts.
4. Add safe local crash capture/recovery and regression tests; no external telemetry service or credentials.
5. Add a manually dispatched merge workflow that verifies my recorded review against the exact PR head and successful CI; reject stale reviews, drafts, foreign branches and failures.
6. Verify scanners reject deliberately unsafe disposable fixtures, test policy failures, run all checks before/after, open PR, self-review and merge only when green.

- [x] Baseline and gates
- [x] Security and dependency checks
- [x] Crash handling and tests
- [x] CI and reviewed merge workflow
- [x] Local/remote verification and pipeline delivery (PR #7); guarded merge integration exercise tracked below

A coverage percentage alone does not prove correctness. Native release builds and centralized runtime crash aggregation remain deployment-phase work; this phase must not invent hosting, credentials or signing configuration.

User cost/reasoning preference: "one more suggestion, when u think please switch to as high efforts as possible and while implemnting u can switch back to lower efforts"; "within the allowed limits of my subsciption, dont pile up usage bill". Saved reusable preferences in AGENTS.md; no paid services, plan upgrades or extra model runs.

Baseline 11 backend/18 mobile tests passed. New merge/audit/crash/table-boundary tests failed before implementation. Local verification now passes 19 backend/policy and 27 mobile tests, approximately 92.4% backend combined coverage / 85.5% branches and 95.3% mobile statements / 82.3% branches. Patched cryptography, UUID and isolated build tools; no Python dependency findings remain. One node-forge tooling advisory is accepted exactly until 2026-11-01, not silently ignored. All recommended TypeScript security rules remain enabled. Negative fixtures confirm scanners reject unsafe patterns and redact synthetic secrets. All remote checks passed on PR #7 and the reviewed implementation was merged. Evidence: https://github.com/SumukhaK/open-source-projectFinder/actions/runs/36991276218. This documentation PR exercises the default-branch reviewed-merge workflow; its live result is recorded in GitHub Actions and the PR merge status, rather than asserted before execution.


## Discovery pages and APIs - 2026-10-02

Original request: "homepage of mobile app will have 2 options at bottom navigation bar one is called home, which will have floating action button that opens a text field for user to input their project idea or on long click of fab it starts listening for user's voice input. it will listen as long as user press and hold the button. and once we have data from backend home page will be populated with the list of data we got or show an meage saying no matching projects found.
second tab is named profile, when user clicks it takes them to something like a setting screen, where at the top it will have user's logged in github s dp (if we can fetch it from github api) and their username below it, then we will have favourite option in which we will show list of repo s user listed as favourite in our app. user seraches for repo via text or voice based description in home page and they can heart repos if it intrests them, we show them here. they can uncheck to remove it from the fav list.
whether user clicks on a project from home page search result or clicks on favourite project, we will have peoject details screen where it shows project title and below it author/authors names and to its right number ofd stars it has below it the banner image of the project, after the banner About , releases, languages and then load the project readme, show contributors at the bottom. this is vague idea, use proper design tools, well define spacing between the items think it like a senior designer and come up with page designs which is neat, minimal, intutive and informative. feel free to design and implement the back end apis that supports these pages as well."

User confirmed: live GitHub search first, Milvus ingestion/semantic search next.

- [x] Backend: authenticated public-only search/details, per-user persisted favourites, validation/rate limiting and bounded provider reads; failing tests first.
- [ ] Mobile: Home/Profile navigation, search composer/results/empty/error states, favourites and details; tests first, safe README presentation.
- [ ] Voice: native speech recognition, hold/release/permission races/background cleanup; editable transcript, no audio persistence or paid transcription keys.
- [ ] Design verification: actual mobile-sized light/dark browser previews, safe areas, 48-point controls, spacing/type hierarchy, accessible labels; native device limitations recorded.
- [ ] Delivery: full quality gates, self-review and feature PR merges.

Design: 8-point spacing grid; 20-point screen padding; 16-point card padding; 16-point body/24 line height; 28-point page headings; 56-point FAB above bottom safe area. Owner is displayed as maintainer, not an invented author list. Missing banner uses branded repository preview, optional GitHub sections have explicit empty states. Search is keyword-based and is not described as AI similarity until Milvus is implemented. Native speech requires development builds; platform services may process speech according to device settings.

Scope update: user requested UI and frontend/backend GitHub API integration only; search feature tests, relevance validation and live search execution are deferred. Favourites, details and safety tests remain in scope.

Backend validation: 32 Python tests pass; 93.7% combined coverage and 87.5% branches, clean Bandit and Ruff. Tests cover favourites isolation/idempotency/limits, optional detail omissions, invalid/private/missing repos, request limits and provider failure/retry behavior. Search-specific feature tests and live search were deliberately not run.

## Standalone GitHub search improvements - 2026-10-13

Original review request (verbatim):

```text
okay, now based on the plan, verify the test cases written by the cline. analyse, think, read beofre making any changes
```

Authorization to change the tests (verbatim):

```text
sure, start changing as u propsed
```

Continuation (verbatim):

```text
continue from where u left off
```

Scope: strengthen the Phase 1 search tests before reviewing or changing the endpoint implementation. Preserve the existing favourites/details tests, restore the deleted discovery protection test, and leave unrelated backend/mobile work intact. Branch: `improved-search-endpoint`. Semantic search and combining retrieval results remain separate planned work.

| Phase / feature | Status | Dependencies and verification criteria |
| --- | --- | --- |
| Phase 1: test contract and regression coverage | Complete (RED verified locally) | Assertions cover actual outbound GitHub parameters, effective metadata, configured defaults, exact input/query boundaries, valid/invalid pagination, public scope, authentication, throttling, body limits and provider failures. Reviewed the test diff, confirmed mutation detection and recorded the current endpoint failures below. No endpoint or delivery phase is marked complete. |
| Phase 1: endpoint implementation review and corrections | Complete (verified locally) | Corrected configured defaults, sorting, query/pagination validation and search response limits. All 94 backend/policy tests, coverage gates, Ruff and Bandit pass. |
| Phase 1: PR review and delivery | Blocked (dependency audit); [PR #10](https://github.com/SumukhaK/open-source-projectFinder/pull/10) remains open | Only this feature is committed. Independent backend review found no blocking findings. Required CI rejects two tooling advisories without available fixes; the user chose to keep the gate unchanged and leave the PR open. No merge workflow was dispatched. |
| Phase 2: qualifiers and quoted phrases | Planned | Decide the explicit advanced-query input contract and conflicts with mandatory public scope before adding tests or implementation. Preserve ordinary idea normalization. |
| Phase 3: Boolean expressions | Planned | Depends on Phase 2. Preserve expression meaning, enforce GitHub's operator budget and public-only policy. |

Phase 1 decisions and acceptance criteria:
- Existing `idea` normalization, public-only/unarchived qualifiers and the six-keyword adapter remain unchanged. Keep existing response fields and verify supplied pagination/sorting metadata values.
- Optional `per_page` accepts 1-100; omission uses central `Settings.search_page_size`, whose existing default is 20. Explicit values override the configured default.
- Supported explicit sorts are `stars`, `forks` and `updated`. Omission means best match and omits upstream `sort` and `order`; an order supplied without a sort is accepted but has no upstream effect. Sorting uses `desc` by default and forwards explicit `asc`/`desc`.
- Preserve the existing page range 1-50. Additionally reject pages whose starting offset is at least 1,000, using the effective page size; a partial final page starting below 1,000 remains valid.
- Validate 255/256/257 characters of retained keyword text, including spaces, separately from the raw idea's 1,000-character maximum. Qualifiers do not count against the keyword limit. Reject invalid input before calling GitHub; do not silently truncate keywords.
- Provider failure is an error, not an empty successful result. Preserve GitHub's incomplete-result flag and defensively omit nonpublic items.

Baseline verification: the reviewed discovery file had 13 passing tests and one failure caused by an undefined variable in the forwarding test; Ruff reported four errors. In-memory mutations showed that the old feature tests survived disabled length validation, ignored page size/sort/order and incorrect metadata. Verification results after the test changes will be recorded below. No live GitHub search, implementation approval, PR or merge is claimed at this stage.

Changes: repaired parameter inspection with HTTPX's `URL.params`, replaced permissive status-only checks with contract assertions and independent parameterized cases, removed redundant direct Pydantic checks, restored discovery throttling/body-limit coverage and added search-specific authentication/failure/public-scope checks. Default descending order may be omitted upstream because GitHub already defaults to `desc`; an empty parameter is not equivalent to omission.

Final verification: `python -m pytest backend/tests scripts/tests -q --tb=short` with a unique ignored workspace temporary directory reported **79 passed, 12 failed, one pre-existing Starlette/httpx deprecation warning** in 33.20 seconds. The discovery file accounts for 64 cases: 52 passed and 12 failed; all other backend/policy tests passed. No cases were skipped or marked as expected failures. All failures were assertions against current endpoint behavior, rather than broken test code:

- Five sorting cases expose empty upstream `sort`/`order` parameters or missing effective descending order.
- Two configured-default cases expose the hardcoded page size of 20.
- Three explicit pagination cases expose missing rejection of page offsets at or beyond 1,000.
- Two combined configuration/pagination cases expose the same defects when the page size is omitted.

The tests detected all five targeted in-memory mutations (disabled query length validation, ignored page size, ignored sort, ignored order, incorrect response metadata), after each corresponding unmodified baseline passed. `ruff check backend/app backend/tests`, Ruff format checks on those paths and `git diff --check` passed. The existing endpoint source hash remained unchanged (`985B8307B144790C3B691068AF03D125507502A54D5A3B2D9FF5AA7371E1392C`). Existing favourites/details checks were preserved, and the restored protection checks passed. Documentation distinguishes this verified RED stage from a completed endpoint. Live GitHub, advanced query phases and mobile checks were not run; there is no PR, merge or implementation approval for this work yet.

### Backend implementation and delivery authorization

User request (verbatim):

```text
now first review the backend code written as per the specs agreed , then plan for changes necessary, re write the code wherever necessary , run the tests and then raise a PR, review it and then merge it
```

Review findings:
1. Hardcoded `Idea.per_page=20` bypasses the configured default used by existing clients.
2. `sort="relevance"` is an invalid default under the model's own validator. Passing `None` values to HTTPX serializes empty query parameters; descending order is also sent empty, and order is forwarded without a sort.
3. Page validation is independent of the effective page size and permits requests outside GitHub's 1,000-result window.
4. Overlong keywords are truncated immediately before rejection, and the error misleadingly asks for keywords instead of describing the length limit.
5. The general 512 KiB provider response limit can reject ordinary 100-result pages. A single public GitHub `fastapi` search returned 100 items in 568,754 bytes, above the current 524,288-byte limit. No provider credentials or repository payloads were printed or saved.

Correction plan, in order:
- Add failing regressions for effective order metadata, clear query-limit errors, optional null controls and full/oversized search-response payloads. Preserve the previously verified 12 failing cases.
- Represent unset page size and sort explicitly with valid optional types; enumerate accepted sort/order values. Omitted or null page size uses the configured default; omitted or null sort means best match. Best match reports effective descending order even when an ignored ascending order was supplied.
- Validate the starting offset with the effective page size, reject overlong retained keyword text without truncation, and build provider parameters with sorting keys only when a sort is active.
- Add centralized `max_github_search_response` (default 1 MiB, configurable 1 KiB-2 MiB) and pass that budget explicitly through the existing provider read interface. Retain the general 512 KiB default for other GitHub reads and the existing timeout/retry behavior.
- Run the full backend/policy tests with coverage, the coverage gate, tracked-file Ruff checks and Bandit. Review the scoped diff and stage only search source/tests and their documentation; exclude unrelated mobile work and untracked scratch scripts.
- Push the existing `improved-search-endpoint` feature branch, open the PR, attach it to this task, review its exact commit and address findings. Record the repository's exact-head review marker only after review, wait for all required quality checks, and use the reviewed-merge workflow without bypassing protections.

Dependencies and limits: no new library, credentials, paid service or schema migration is needed. Main was verified at `2237c7e5241a698258a28952150194b943d616b0`; an active `protect-main` ruleset and the reviewed-merge workflow apply. Advanced-query parsing, semantic search and mobile work remain outside this feature. Architecture components are unchanged, so no diagram update is required.

Implementation verification: the additional regressions produced **50 passed and 17 failed** discovery cases before the correction, then **67 passed** afterward. The full backend/policy suite reports **94 passed**, with **97.0% combined coverage and 93.0% branch coverage**, passing the repository's coverage gate. Tracked Python files pass Ruff lint and formatting, backend application code passes Bandit, and the staged Gitleaks scan finds no leaks. The existing Starlette/httpx deprecation warning remains. The test HTTP provider exercises the real application/session/store path; the public payload-size check does not establish a live authenticated application search or native-device validation. [PR #10](https://github.com/SumukhaK/open-source-projectFinder/pull/10) is the delivery record; exact-head review, required CI and the reviewed-merge result are recorded there and in GitHub Actions rather than asserted before execution.

CI blocker: [run 38425124561](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/38425124561) passed backend, mobile/E2E/platform exports and secret checks, but the dependency audit rejected newly reviewed advisories for [braces 3.0.3 / GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) and [sprintf-js 1.0.3 / GHSA-hp3w-g68c-fv3c](https://github.com/advisories/GHSA-hp3w-g68c-fv3c). GitHub's advisory database lists no patched releases, and npm's latest releases are still affected (3.0.3 and 1.1.3). The committed lock traces braces through Jest and Expo/React Native Metro file matching, and sprintf-js through Jest coverage configuration's js-yaml/argparse path. These advisories remain unresolved; no vulnerable package is described as patched.

Delivery decision: automatic approval review rejected committing/pushing proposed short-lived exact-version exceptions because explicit authorization to weaken the dependency gate was absent. The user then chose, verbatim: **"Keep the gate unchanged; leave PR open (Recommended)"**. The uncommitted exception proposal was removed. Scanner execution, policy, thresholds and mobile dependencies remain unchanged. PR #10 stays open without merging; resolving the advisories compatibly, passing required CI and reviewing the resulting exact head are prerequisites to any future merge. Unrelated local mobile work is preserved.



## Hybrid search execution handbook - 2026-10-24

Original request (verbatim):

```text
now , we will be using deepseek flash v4 available on open code to implemnt this plan, so what u should do is dicide this plan into smaller executable plans, write anothe detailed doc that invloves prompt for execution that explains what to do, what counts as acceptable right solution, what not to do, include a tracker option to mark each tasks as done when its accepted via code review.  include this instruction in each task, deepseek shouldcut a branch from main, execute plan there, raise PR and wait for review. TDD approach for coding so tests first then actaul code. use ponytail and other coding plugins to plan the task with detaile instruction, so codes are minimal, human readable and underestandable, follow lint and other coding discipline. add all these docs on main branch under a newly created folder and push it on main repo as well
```

Scope: publish the existing proposed hybrid/archive architecture plus portable OpenCode execution prompts in [execution-plans/hybrid-search](execution-plans/hybrid-search/README.md). No archive implementation, provider/model configuration, model download or scheduler activation is included. Confirmed requirements and earlier project prompts are retained in [REQUEST](execution-plans/hybrid-search/REQUEST.md); policy recommendations remain pending explicit decisions.

| Phase / feature | Status | Verification / acceptance |
| --- | --- | --- |
| Handbook authoring | Complete; merged as `2e4a9ff` via PR #11 (reviewed head `5cba2a4`, [CI 40084144348](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40084144348)) | Static checks passed for 37 Markdown files, 30 required task workflows, 289 local links/anchors, dependency ordering and both diagram themes. Independent review found one missing T17 dependency on T08 publication; it was added to the task and tracker. [PR #11](https://github.com/SumukhaK/open-source-projectFinder/pull/11) and its current-head review/checks are authoritative for publication status. |
| T00 readiness | Complete (accepted and merged as `6dc4233`) | [PR #13](https://github.com/SumukhaK/open-source-projectFinder/pull/13) on base `2e4a9ff353de7a137c49fff0c99bea1765a357a2`; exact-head review of `b535011` and [CI 40086438932](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40086438932) passed. The rest of this cell is the original delivery note: [READINESS](execution-plans/hybrid-search/READINESS.md) records the fresh dependency audits, merged #10/#12/#11 prerequisites, unmerged mobile foundation, eight pending operator decisions and the task readiness/blocker matrix. Exact-head review and CI are pending; the implementer has not accepted or merged. |
| T01-T29 implementation | T01-T05 merged; T06 awaiting review; T07-T29 not started | [Task tracker](execution-plans/hybrid-search/TRACKER.md) is authoritative for per-task status, full reviewed SHA/review/CI evidence and merged SHA. Only review acceptance checks a task done; dependents require merge into main. |

Main baseline was 2237c7e5241a698258a28952150194b943d616b0. Search PR #10 and the local discovery mobile foundation were not merged during authoring. Fresh dependency policy evaluation on 2026-10-24 blocked main's mobile lock on zod 3.25.76 / GHSA-mrhx-c7xc-m3w5; the earlier braces/sprintf advisories were withdrawn, not patched here. The first handbook CI run additionally blocked the unchanged Python lock on six advisories across certifi, filelock, opentelemetry-api and setuptools; backend/mobile quality and secrets passed at that earlier head. See the dated evidence in REQUEST.md; later-head checks remain required. The handbook preserves current gates and requires rechecking prerequisite/security state. No unrelated workspace changes are included.

### Delivery update - 2026-10-24

[PR #10](https://github.com/SumukhaK/open-source-projectFinder/pull/10) was retained because it adds backend search controls/validation and contract tests absent from the documentation-only PR #11. It merged as 1e681ae5fe1bb309e793c225aa0513335d95ba15 after independent review of 3b80dad4fefb6ee5e8008ffbbe9217b22b501e2e and passing [CI 40083939979](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40083939979). A fresh 94-test run with the patched dependency environment passed, at 97.0% combined and 93.0% branch coverage. Both #12 and #10 used the reviewed-merge workflow with exact-head markers and passing current checks; no restrictions were bypassed.

The October 13 security/delivery paragraphs above are historical and superseded by this update: the braces/sprintf advisories were withdrawn, and the current Python/Zod blockers were fixed in #12 with no new exceptions. The prior node-forge tooling exception still expires on 2026-11-01. PR #11 now includes the actual delivered prerequisite code from main and updated readiness notes; its own exact-head review/checks and merge status remain authoritative in GitHub. T00-T29 implementation remains not started; the unrelated local mobile foundation remains unmerged and untouched.

### T00 readiness delivery - 2026-10-24

[T00 PR #13](https://github.com/SumukhaK/open-source-projectFinder/pull/13) is a documentation-only readiness slice on base `2e4a9ff353de7a137c49fff0c99bea1765a357a2`. It records the current legacy keyword-search contract, the merged #10/#12/#11 prerequisites, and the still-unmerged mobile discovery foundation (no origin branch or PR; the local uncommitted WIP was not copied). Fresh audits: the Python lock has 59 dependencies and 0 known vulnerabilities; the npm lock has 4 high audit entries with one direct `node-forge 1.4.0` advisory `GHSA-86w9-cpqp-85rv`, covered only by the existing exception expiring 2026-11-01. Local checks: 94 backend tests passed, 97.0% combined / 93.0% branches, ruff/format/Bandit clean, 302 relative links/anchors resolved, and diff/secret checks clean. All eight policy decisions remain pending operator approval with blocking task IDs in [READINESS](execution-plans/hybrid-search/READINESS.md). No runtime, ingestion, scheduler, credential, gate or mobile change was made. At the time of that note T00 was not yet accepted; it has since been accepted and merged as `6dc4233` (see the hybrid [TRACKER](execution-plans/hybrid-search/TRACKER.md) change log). T01 is now prerequisite-ready.

## Documentation drift and discovery hardening - 2026-10-24

User request (verbatim):

```text
cut a branch from main and work on fixing issues to watch 2,3,4. im aware od first issue, we will deal with it later. also PR#13 is merged, so update ur graph and knowldge accoringly
```

Scope: the architect review's issues 2-4. Issue 1 (node-forge exception expiring 2026-11-01) is deliberately deferred by the user. Branch `claude/optimistic-franklin-06iy1f`, recut from main `6dc4233`.

| Feature | Status | Verification |
| --- | --- | --- |
| 2. Documentation drift | Complete (merged in PR #14) | backend README no longer calls search planned; invalid Latin-1 byte in README replaced with UTF-8 `·`; PR #11 and T00/PR #13 merges recorded here and in the hybrid TRACKER/READINESS with review/CI evidence; stale phase table and workflow checkboxes updated with evidence |
| 3. Unmerged mobile path in the plan | Complete (merged in PR #14) | ARCHITECTURE/README of the handbook now label `mobile/src/features/discovery/...` as a local uncommitted workspace file and point at prerequisite P2; T24-T26 remain blocked. The mobile foundation itself cannot be delivered from this checkout because it exists only on the operator's machine. |
| 4a. Non-ASCII ideas | Complete (merged in PR #14) | Keywords keep letters, digits and combining marks of any script. RED: Devanagari and CJK ideas returned 422 and `CafÃ©` became `caf`; GREEN after the change. Existing ASCII normalization tests unchanged. |
| 4b. Per-user GitHub quota | Complete (merged in PR #14) (mitigation) | Using each user's own token is kept by design. Rate-limited discovery reads now return 503 with `Retry-After` (GitHub's Retry-After/reset, or 60 s when GitHub gives no timing headers). RED: header missing; GREEN after the change. |
| 4c. Private `request._body` | Complete (merged in PR #14) | Replaced by a public-ASGI `BodyLimit` middleware that buffers up to `max_auth_body`, returns 413 and replays the body; it runs inside `protection`, so throttling still comes first. Chunked-body and direct ASGI tests cover delivery, oversize, disconnect and replay; real uvicorn smoke test returned 200 for a chunked login start and 413 for a 5,000-byte chunked body. |
| 4d. Per-request SQLite pruning / single host | Not changed | Already documented as single-host; a shared PostgreSQL/Redis limiter belongs to the deployment phase. Rewriting the pruning without a measured problem would be speculative. |

Verification (Linux, Python 3.13 scratch venv from `backend/requirements.lock.txt`; CI uses 3.11): `ruff check`/`ruff format --check backend scripts` clean; `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch` 104 passed (was 94); `scripts/quality.py coverage` 97.2% combined / 93.5% branches; Bandit clean. Mobile code is unchanged and its suite was not run locally; PR CI runs mobile and E2E checks. No dependency, gate or exception change.

Delivery: [PR #14](https://github.com/SumukhaK/open-source-projectFinder/pull/14) passed exact-head review of `df6db41` and [CI 40088092750](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40088092750), and merged through the reviewed-merge workflow as `3fe8016` on 2026-10-24.


## T01 Milvus feasibility continuation - 2026-10-24

User request (verbatim): "awesome, please proceed"

Resume only T01 from the supplied DeepSeek handoff. The existing clean branch was fast-forwarded from 6dc4233 to current main 3fe801661d63e0b147f611f39f35f2f07a79e184 before changes, preserving the newer search fixes and T00 review record. Original checkout/mobile WIP is untouched.

Initial implementation plan (historical; now awaiting review): write failing behavior tests, then a bounded synthetic 1k-vector probe and private authenticated CPU/GPU Compose profiles. Verify official version/config sources, real operations and resource use independently for CPU/GPU; document SQLite/memory/runtime limits honestly. Run relevant checks/audits, update tracker to Awaiting review, open one PR and stop. Do not start T02, merge, approve policy decisions or change host memory/driver settings. Live tests depend on safe available resources; missing evidence remains blocked.

Verification/handoff: **Awaiting review, not accepted**. Real Milvus 2.6.26 / PyMilvus 2.6.17 CPU proof passed twice on 1,000 synthetic normalized vectors with HNSW/IP, scalar filtering, upsert/delete and owned-collection cleanup. Default/missing REST credentials are rejected. The real GPU 1k proof now also passes twice on operator-installed 617.42 with GPU_CAGRA/IP, clearing the earlier 551.61 startup failure. Host/archive and rebuild capacity remain untested; WSL SQLite 3.46.1 fails the WAL gate for T03, not T01 review. No CPU-only approval is inferred. See [T01 evidence](execution-plans/hybrid-search/T01_EVIDENCE.md) and [runbook](infra/milvus/README.md).

Implementation checks (2026-10-25, before this docs sync): 138 backend/policy/probe tests pass (96.8% combined coverage / 92.4% branches); Ruff/format/Bandit/pip-check pass; 69 locked Python dependencies audit clean, npm passes the unchanged policy with the existing node-forge exception only. Static validation covers 44 Markdown files and 335 links/anchors, diagram XML, conflict/fence checks and unchecked T01 acceptance. New behavior regressions were observed failing before their fixes. No local mobile rerun solely for this probe; required remote CI remains authoritative. The probe now requires Finished/all 1,000 rows indexed/zero pending rows after review exposed the default small-segment flat-scan risk; two corrected live CPU runs passed. Test containers were stopped without deleting volumes and the task-started Docker Desktop was stopped to release RAM; pre-existing WSL settings and unrelated applications/workspace files remain unchanged. [PR #15](https://github.com/SumukhaK/open-source-projectFinder/pull/15) is open and awaiting review; no T02 work or merge. The user explicitly instructed that the PR remain unmerged.


T01 documentation sync — 2026-10-25: update only the seven requested Markdown files with the existing [GPU execution results](https://github.com/SumukhaK/open-source-projectFinder/pull/15#issuecomment-6396209833), preserving the tested code at `20d7a84`. Plan/verification: check archived JSON/CSV hashes and exact measured values, clarify CPU/GPU timing limits and the separate T03 WAL prerequisite, run 138 tests/Ruff/format/link/diff/staged-secret checks, push one documentation commit, await new-head Quality pipeline and only then mark the PR ready for review. No code/tests/Compose/limits/dependencies/CI/security or host changes. Acceptance stays unchecked; no merge, approval marker or T02 work. The live PR head and full new SHA/CI link are maintained in the PR description because a commit cannot embed its own hash.

Documentation-sync verification (2026-10-25): `python -m pytest backend/tests scripts/tests -q` passed 138 tests; `ruff check backend scripts` and `ruff format --check backend scripts` passed. Local link/fence/diagram and diff checks pass. Staged-secret/private-value inspection passed; exactly seven Markdown files are staged, with no raw evidence or environment files. New-head CI remains required before ready-for-review delivery; live GPU measurements above are from the unchanged tested code, not a new hardware run.

## T02 CPU embedding adapter - 2026-10-25

User request (verbatim): "PR merged. well done. now Read execution-plans/hybrid-search/OPENCODE_PROMPT.md, replace TASK_ID with T02, and execute only that task. Read all referenced documents, follow its instructions, raise a PR, then stop and wait for review."

Resume only T02 in a separate worktree at `E:\OpenSourceProjectFinder-t02`, cut from `origin/main` `7f94e2f5c8b0e68905dba367c584b4f74d98c175` (T01 merged via PR #15). The original checkout and mobile work were untouched. Plan: pin the model revision and safe-weight hashes; add a CPU-only adapter with injectable loading, explicit 512-token enforcement after prefixing, normalized 384-dimensional output validation and bounded batches; write behavioral RED tests with a deterministic fake encoder; implement the minimum GREEN; run a real local CPU smoke/benchmark; audit the optional dependency tree; update docs/tracker; open one PR and stop.

Verification/handoff: **Awaiting review, not accepted.** The adapter is `backend/app/services/embeddings.py`; the immutable manifest is `backend/app/services/embedding_model.json` for `intfloat/multilingual-e5-small` revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, 384 dimensions, 512 tokens, MIT, `model.safetensors` SHA-256 `1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477`, `tokenizer.json` SHA-256 `0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39`. Query/passage prefixes are `query: ` and `passage: `; inputs that already carry a prefix are rejected. The optional CPU lock is `backend/requirements.embeddings.lock.txt` (42 packages, `torch==2.14.1+cpu`); the main CI lock is unchanged. Real Windows CPU smoke passed with verified cached hashes: 3 query and 12 passage vectors, all 384-dimensional and norm 1.0; warm-cache load 5.013 s; about 99.7 query vectors/s and 171.4 passage vectors/s; peak RSS 1224.1 MB. Focused RED was 16 failed/3 passed; GREEN is 22 focused and 160 total tests, 97.8% combined coverage / 95.5% branches. Ruff/format/Bandit/pip-check and both dependency audits (69 main + 42 embedding packages, 0 known findings) passed. [T02 evidence](execution-plans/hybrid-search/T02_EVIDENCE.md) and the [tracker](execution-plans/hybrid-search/TRACKER.md) are authoritative for the live PR/head; PR [#16](https://github.com/SumukhaK/open-source-projectFinder/pull/16) carries the exact head.

Initial implementation limits: the first real evidence was a small Windows warm-cache sample. Linux execution is now measured in the follow-up below; relevance quality, sustained concurrency and archive capacity remain untested. Unit tests use a fake encoder and never download a model. The adapter rejects over-budget input rather than truncating and does not claim a 1,000-character idea always fits 512 tokens. The API does not import the adapter yet; no query/embedding persistence, paid API, GPU model load or generic provider framework is included. The optional stack is not installed by the main CI lock, so a separate operator environment is required. No self-acceptance, merge or T03 work.


### T02 review follow-up recovery — 2026-10-25

Resume the interrupted follow-up on PR #16 from reviewed head86457ec, retaining OpenCode's seven matching uncommitted files. Scope: enforce cached snapshot/safetensors and both manifest hashes on the real CPU load path; explicit setup only for downloads; distinguish UnsupportedInput from model faults; prove the unchanged CPU lock and real offline smoke on WSL; fail closed on audit-pin rewrite drift. No API wiring, Milvus/T01 edits, T03/T13 implementation, policy exception, approval marker or merge.

Recovery baseline:28 existing focused tests pass and Ruff is clean. Linux venv `/home/sumukha/t02-venv-linux` already contains all42 pinned embedding packages; cached weights/tokenizer exist but supporting model configuration is absent. Plan: add failing regressions for model-fault classification and bounded explicit setup, make minimum fixes, complete Linux setup/offline smoke, run full coverage/static/audits and review, then push the same branch and await new-head CI. Record inherited verification separately from newly observed RED/GREEN; T02 remains Awaiting review.

Follow-up verification:44 focused /182 total offline tests pass; embeddings.py100% line/branch coverage, total98.0% combined/95.7% branches. Newly observed behavioral RED was11+3+2 failures before the corresponding fixes. The unchanged42-package CPU lock installed in Ubuntu26.04.1 /Python3.14.4; final explicit setup and HF_HUB_OFFLINE=1 smoke exit0, both hashes verified. Warm-cache load2.837s, query86.96vectors/s, passage153.65vectors/s, peak RSS1015.4MiB on the synthetic sample. The initial Linux cache-filter failure was fixed with a regression. Ruff/format/Bandit and both audits pass; four audit-guard fixtures fail closed as required. [T02 evidence](execution-plans/hybrid-search/T02_EVIDENCE.md) records commands, historical versus recovered results and limitations. Push the same PR #16 branch and await exact-head CI/review; no merge, acceptance checkbox, review marker or next task.

## Tracker sync for T01 and T02 - 2026-10-25

User request (verbatim):

```text
update the tracker
```

Scope: documentation only. Record the completed reviews and merges of T01 and T02 and refresh status lines that still described them as awaiting review. No code, tests, configuration, dependencies or CI changed.

- **T01** ([PR #15](https://github.com/SumukhaK/open-source-projectFinder/pull/15)): exact-head review of `403ec8f5b0f60c9daa40e8df92c700d1dcc21abe` ([review 5642730753](https://github.com/SumukhaK/open-source-projectFinder/pull/15#pullrequestreview-5642730753)), [CI 40184328241](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40184328241) passed, merged as `7f94e2f` on 2026-10-25. The sections above that say "awaiting review" or "remain unmerged" are the historical delivery notes. Open: host/archive and rebuild capacity; a WAL-fixed worker SQLite (3.51.3+, or the fixed 3.50.7/3.44.6 branches) before T03 uses WAL; the WSL runtime read `3.46.1 False`.
- **T02** ([PR #16](https://github.com/SumukhaK/open-source-projectFinder/pull/16)): first review of `86457ec` raised four non-blocking notes, all fixed on the same PR; final exact-head review of `c1a5b5ea540ba794fa025c2602393b2641207424` ([review 5643007484](https://github.com/SumukhaK/open-source-projectFinder/pull/16#pullrequestreview-5643007484)), [CI 40189393293](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40189393293) passed, merged as `e400076` on 2026-10-25. Open: API wiring and UnsupportedInput mapping (T13), relevance and capacity.
- Unchanged blockers: policy decisions D1-D8 and prerequisites P1-P3 in [READINESS](execution-plans/hybrid-search/READINESS.md); the node-forge 1.4.0 dependency exception expires 2026-11-01.


## T03 isolated archive catalogue - 2026-10-25

User request (verbatim):

```text
now Read execution-plans/hybrid-search/OPENCODE_PROMPT.md, replace TASK_ID with T03, and execute only that task. Read all referenced documents, follow its instructions, raise a PR, then stop and wait for review.

Start from the latest origin/main (at or after 487cc52, which records T01/T02 as merged).

Runtime for real WAL evidence: WSL venv /home/sumukha/reporadar-worker-venv
(Python 3.11.17, SQLite 3.53.1, wal_is_fixed True, verified 2026-10-25).
Run the T03 catalogue tests and the WAL-enable path with that interpreter in WSL,
and record its sqlite3.sqlite_version in the T03 evidence. Keep the code check that
refuses WAL on an unpatched runtime (e.g. system 3.46.1) and test that refusal.
Do not modify the system Python/SQLite or this venv's interpreter.

A version gate already exists as scripts/milvus_probe.py::wal_is_fixed. Do not keep two
copies: if the catalogue needs it in backend/app, move it there with its tests and make the
probe import it, keeping the probe's behaviour and tests unchanged.

WSL needs about 6-7 GB of free RAM to start; if it fails with HCS_E_NO_SYSTEM_RESOURCES,
stop and tell me rather than changing .wslconfig or closing my applications.

If CI fails only because the node-forge exception expired (after 2026-11-01), report it;
do not edit the exception or weaken any gate.
```

Base: `487cc52c54c6b03e553f183a1e5764fd50c77899`; branch `codex/hybrid-t03-catalogue`. T00/T01/T02 are merged. Scope is synthetic/offline catalogue work; no pending corpus/retention/scheduling policy is activated.

| Slice | Status | Acceptance / verification |
| --- | --- | --- |
| Shared runtime gate and bounded central settings | Awaiting review | One WAL gate, refusal before DB creation, separate auth/archive paths |
| Catalogue v1 migration and transactions | Awaiting review | Repeat migrations/reopen preserve IDs, constraints reject invalid relationships, rollback is atomic |
| WSL evidence and handoff | Awaiting review | Real WAL reader/writer/checkpoint on SQLite 3.53.1; regressions, coverage, lint/security, PR awaiting review |

Non-goals: no ingestion, raw-file writer, vector publication, durable jobs, API/mobile changes or system/runtime modifications. Architecture flow is unchanged; existing planned diagrams remain accurate.

Verification: 222 tests pass in WSL Python 3.11.17 / SQLite 3.53.1; 97.8% combined / 95.3% branch coverage passes unchanged gates; Ruff lint/format and Bandit pass. Real catalogue WAL snapshots, commits, truncate checkpoint, reopen and integrity pass; system SQLite 3.46.1 fails the shared gate. Detailed RED/GREEN commands and rollback are in [T03 evidence](execution-plans/hybrid-search/T03_EVIDENCE.md). PR/current-head CI and independent trusted acceptance remain GitHub evidence; task is not accepted or merged.

T03 handoff: [PR #18](https://github.com/SumukhaK/open-source-projectFinder/pull/18), Awaiting review. Independent trusted acceptance and required current-head CI remain pending; no merge or next-task execution.


### T03 CI runtime review follow-up - 2026-10-25

User request (verbatim):

```text
Address the "Changes requested" review on PR #18 (T03, branch codex/hybrid-t03-catalogue,
reviewed head 46ff60f). Work on the SAME branch and PR; do not start T04.

Blocking fix: CI Backend quality fails (run 40195929309: 5 failed, 23 errors) because
actions/setup-python's Python 3.11.17 links an unpatched SQLite, so ArchiveStore correctly
refuses it. Make CI run the backend job on a WAL-fixed runtime, like the worker venv:
- In .github/workflows/quality.yml backend job, provision a pinned CPython 3.11
  python-build-standalone interpreter (e.g. via a pinned uv release with checksum
  verification, or an action pinned by full commit SHA) whose sqlite3.sqlite_version
  passes app.core.sqlite_runtime.wal_is_fixed. Install backend/requirements.lock.txt into
  it and run the existing ruff/pytest/coverage/quality.py/Bandit steps with it.
- Add a step that prints Python + sqlite3.sqlite_version and exits 1 unless
  wal_is_fixed(...) is True.
- Keep job permissions read-only, timeouts, caching and the quality gate unchanged.
  Do not weaken any gate, add exceptions or change dependency pins.
- Do NOT skip/xfail archive tests on unpatched runtimes and do NOT monkeypatch
  sqlite3.sqlite_version in the shared catalogue fixture. Keep the existing refusal tests.
Non-blocking (include if small): add pytest.mark.skipif(os.name != "posix") to the archive
store tests with a clear reason (platform restriction only; CI is Linux); note in
backend/README.md that the catalogue must live on a Linux-native path, not /mnt/c or /mnt/e.
Future schema changes go in migration 2+, never by editing migration 1.

Verify: reproduce the CI failure first (run the suite under a Python with SQLite < 3.51.3,
e.g. the system /usr/bin/python3 in a throwaway venv, expect the same RuntimeErrors), then
show the new CI-equivalent runtime passing: full pytest with coverage gate, ruff, Bandit.
Update T03_EVIDENCE.md with the CI interpreter/SQLite version and the new CI run link.
Push to the same PR, wait for CI, report the new head SHA and run link, then STOP for review.
NEVER merge, approve, write a review marker, or start another task.
```

Plan on the same branch/PR: (1) reproduce the 28 WAL refusals with the unchanged suite on an isolated system-SQLite venv; (2) pin the worker-family CPython archive by release, version and SHA-256 in the backend job, keeping the existing pip cache and checks, and add an explicit shared WAL gate step; (3) run the workflow steps locally with that archive, update evidence/operator migration notes and await all required CI before review handoff. No catalogue schema or dependency changes. Status: In progress; baseline head `46ff60f2acece4c7aa4c45fb7918b41da6444784`.

Progress as of 2026-10-26: phases 1 and 2 verified. The unchanged suite on actual SQLite 3.46.1 reproduced 5 failures and 23 errors; all nine backend workflow commands then passed using the checksum-verified standalone CPython 3.11.17 / SQLite 3.53.1 (222 tests, 97.8% combined / 95.3% branch coverage, Ruff and Bandit). The POSIX-only marker skips 40 catalogue tests on native Windows while all 8 shared gate tests pass; Linux skips none. All existing workflow steps, permissions, timeouts, caching, dependency locks, schema and safety gates remain unchanged. Phase 3: local verification and documentation complete; [CI run 40260379712](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40260379712) passed all five jobs at implementation head `4b8bebec510a92dab57619dae44eb60610de2037`, confirming the same runtime and coverage in GitHub. This documentation-only follow-up still requires current-head CI. Status: Awaiting trusted review, not accepted or merged. See [T03 evidence](execution-plans/hybrid-search/T03_EVIDENCE.md#ci-runtime-review-follow-up---2026-10-2526).


## T04 requested review fixes - 2026-10-26

User request (verbatim):

```text
Address the "Changes requested" review on PR #19 (T04, branch codex/hybrid-t04-archive-http,
reviewed head 2593688). Work on the SAME branch/PR; do not start T05 or other tasks.
TDD: for each item write the failing test first, record RED, then fix (GREEN).

1. 5xx Retry-After: in ArchiveGitHubReader._get, a 5xx with a short retry_at must wait
   max(backoff, retry_at - now), capped by archive_github_retry_max_wait (longer waits keep
   raising ArchiveUnavailable with retry_at). Test: 503 + Retry-After: 4 then 200 -> recorded
   sleep >= 4.
2. Secondary rate limit: a 403 whose JSON "message" mentions a (secondary) rate limit and has
   no Retry-After/X-RateLimit headers must be ArchiveRateLimited with retry_at = now + 60s via
   the existing _wait_or_raise. Plain 403 stays ArchiveForbidden; non-JSON 403 bodies must not
   crash. Tests for all three.
3. Content-verified blob identity: after base64 decoding, require
   hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest() == blob_sha
   for inline README content and for fetch_blob. Mismatch -> ReadmeInvalid / BlobIdentityMismatch.
   Skip only for README encoding "none" (no content). Update fixtures to use real git blob SHAs;
   add tests: correct hash accepted, one changed byte rejected (both paths).
Optional: note in T04_EVIDENCE.md that decoded-byte limits are enforced per decoded chunk, so a
single compressed network chunk may transiently inflate before the cap (GitHub-only origin).

Verify on Linux with the CI runtime if possible (WSL venv /home/sumukha/reporadar-worker-venv),
else Windows + rely on CI: full pytest + coverage gate, ruff check/format, bandit, git diff --check.
Update T04_EVIDENCE.md (RED/GREEN for these fixes) and the PR description (new head, CI link).
Push to the same PR, wait for CI, report the new head SHA, then STOP for review.
NEVER merge, approve, write a review marker, change dependencies/CI gates, or start another task.
```

Scope: only `archive_github.py`, its tests, backend README, evidence and this tracker. Reuse `_backoff`, `_wait_or_raise` and bounded JSON parsing; preserve OAuth, cache/redirect/size behavior and all dependencies/gates. Worktree `E:/OpenSourceProjectFinder-t04`, branch `codex/hybrid-t04-archive-http`, reviewed base `2593688c4baf4e75e7c92a8c7551f94f9c20e3bb`. Existing focused baseline: 128 passed on Windows Python 3.11.9. WSL stopped with 1.74 GiB free RAM; use allowed Windows checks plus required Linux CI without closing apps or changing system settings.

Plan: (1) RED/GREEN short 5xx retry delay and cap; (2) RED/GREEN secondary-rate-limit classification with safe plain/non-JSON fallbacks; (3) RED/GREEN byte-verified blob identity on README/blob paths and realistic fixtures; (4) full regression, unchanged coverage/lint/security checks, evidence, same-PR push and exact-head CI. Status: In progress. No merge, acceptance marker or later task work.

Progress: phases 1-3 verified with separate RED/GREEN runs, including malformed 403 parser edges. Phase 4 local verification passed: 147 focused tests; 329 full-suite tests with 40 existing Windows POSIX skips; 94.0% combined / 91.2% branch coverage; Ruff check/format and Bandit clean. Backend README and [T04 evidence](execution-plans/hybrid-search/T04_EVIDENCE.md#requested-review-fixes---2026-10-26) record behavior and the per-decoded-chunk memory limit. Status: Awaiting exact-head Linux CI and trusted review on PR #19; no acceptance, approval or merge.

## T05 deterministic content preparation - 2026-10-26

User request (verbatim):

```text
PR merged. well done. now Read execution-plans/hybrid-search/OPENCODE_PROMPT.md, replace TASK_ID with T05, and execute only that task. Read all referenced documents, follow its instructions, raise a PR, then stop and wait for review.
```

Base `origin/main`: `776bf654551fd0466386c6bc008df6ae606b0dcb`. Branch: `codex/hybrid-t05-chunking`. T02 / PR #16 (`e4000764c97b3648ec0b08fe42989ee8d2e56463`) is an ancestor of this base; T03 / PR #18 is now merged. T04 is not a T05 dependency. No pending policy decision is activated by synthetic/offline preparation.

| Phase | Status | Verification criteria |
| --- | --- | --- |
| Read boundaries and baseline | Verified | Existing Windows suite: 182 pass, 40 existing POSIX-only catalogue skips; no failures |
| Normalize bounded metadata and Markdown | In progress | Behavioral RED/GREEN for Unicode, code fences, HTML/images/navigation, malformed/binary/oversized/absent README and repeated sections |
| Bound chunks and stable versioned identity | Planned | Metadata overview + selected sections; real tokenizer counts including prefix/title/special tokens <=512, content <=400, <=8 chunks, explicit omissions, stable IDs and semantic changes without star-count churn |
| Review and handoff | Planned | Full suite/coverage, Ruff/Bandit, real pinned-tokenizer smoke, required CI, one PR; await trusted review |

Scope: new `archive_index.py`, central hard bounds in `config.py`, explicit direct declaration of the already-locked Markdown parser, tests and documentation. Existing embedding adapter/counting and manifest are reused; no new tokenizer loader, dependency upgrade, schema, file writer, API, worker or vector publication.

Rulings: use zero overlap (within the task's <=50 bound) to avoid repeated content; chunker version records this policy. Drop raw-HTML blocks/HTML-bearing paragraphs rather than render them; retain ordinary Markdown prose/code as inert text. Reject an oversized or binary README to a metadata-only document with an explicit status; bound parser input separately and record clipping. Metadata inputs have a strict byte/type budget; invalid metadata fails before parsing. Preparation uses the loaded T02 adapter's actual tokenizer counts, with fake counters only in unit tests and a separate real-tokenizer check. These choices trade some coverage for bounded local work and require relevance evaluation in T27, not additional T05 features.

T05 implementation verification: 53 preparation tests pass; final Windows full suite 235 passed / 40 existing POSIX catalogue skips. Coverage 92.4% combined / 89.2% branches passes unchanged gates (new module 100%); Ruff and Bandit pass. Real hash-verified E5 tokenizer smoke passes seven synthetic cases offline (all <=400 content / <=512 final tokens, <=8 chunks, repeat deterministic), re-run on 2026-10-26 with the same result. No WSL start due to 3 GiB available RAM; Linux tests remain required CI. Algorithm/metadata bounds and exact operator contract: [T05 evidence](execution-plans/hybrid-search/T05_EVIDENCE.md). Status: Awaiting review; fresh author-independent preflight and PR CI pending, no acceptance.

## T05 word-boundary review follow-up - 2026-10-26

User request (verbatim):

```text
Follow-up on PR #20 (T05, branch codex/hybrid-t05-chunking, reviewed head bdd021c). Same branch/PR.
TDD: failing test first, then fix.
In backend/app/services/archive_index.py, after _fit returns a piece that ends mid-word (next
char is not whitespace) and a whitespace boundary exists within the last 20% of the piece, cut at
that whitespace instead; otherwise keep the hard cut (CJK, long URLs/tokens). Re-check fits() on the
adjusted piece. Tests: a long English section never splits a word; a no-whitespace section still
chunks within budget. Keep CHUNKER_VERSION "sections-v1" (nothing has been ingested yet) and note
the boundary rule in T05_EVIDENCE.md. Run full pytest + coverage gate, ruff, bandit; push, wait for
CI, report the new head SHA, then STOP. Never merge, approve or write a review marker.
```

Scope: body chunk selection in `archive_index.py`, its existing tests, backend README, T05 evidence and this tracker. Keep title fitting, tokenizer/prefix budgets, normalization, hard-cut fallback, chunk cap, version, dependencies and gates unchanged. The only caller is the offline preparation entry point; there is no ingested data or migration. Work on existing branch/PR #20 from clean reviewed head `bdd021cb76973ec3bab49d77d09e9ef8899231e9`.

Plan: (1) record RED for English word preservation and adjusted-piece budget validation, with bounded hard-cut/20% boundary controls; (2) retreat to the nearest qualifying whitespace after `_fit`, retaining the existing `fits()` check; (3) full tests/coverage, Ruff, Bandit, offline pinned-tokenizer smoke if available, documentation and exact-head CI on the same PR. Status: In progress; no acceptance, review marker, merge or later task. WSL is stopped with 4.34 GiB available RAM, below the prior startup target; use Windows checks plus Linux CI without changing applications or machine settings.

Expanded user request (verbatim; supersedes the earlier sequence):

```text
Follow-up on PR #20 (T05, branch codex/hybrid-t05-chunking, reviewed head bdd021c). Work on the SAME
branch/PR; do not start T06 or any other task.

STEP 1: Bring in main (T04 merged as d2354e9).
- git fetch origin && git merge origin/main into codex/hybrid-t05-chunking with a MERGE COMMIT.
  No rebase, amend or force-push.
- Resolve conflicts by keeping both sides:
  * backend/app/core/config.py: keep ALL ARCHIVE_GITHUB_* settings/validators from T04 AND all T05
    README/parse/metadata/token/chunk constants. Don't change any value from either side.
  * PROJECT_TRACKER.md: keep both the T04 and T05 sections, in chronological order.
  * execution-plans/hybrid-search/TRACKER.md: keep the T03 row exactly as on this branch, and keep any
    T04 text from main.
  * backend/README.md: keep both the archive reader (T04) and chunking (T05) sections.
- Run the full suite right after the merge, before any other edit. Everything must pass, including
  the T04 tests.

STEP 2: Word-boundary fix (TDD: write the failing test first and record RED, then GREEN).
- In backend/app/services/archive_index.py, _fit may return a piece that ends mid-word (the next
  character is not whitespace). When that happens and a whitespace boundary exists within the last
  20% of the piece, cut at that whitespace instead. Otherwise keep the hard cut (CJK, long
  URLs/tokens). Re-check fits() on the adjusted piece. The next chunk must start after the skipped
  whitespace: no leading spaces, no lost or duplicated characters.
- Tests:
  (a) a long English section never splits a word across chunks;
  (b) a section with no whitespace still chunks within the 400/512 token budget;
  (c) re-joining all chunk texts reproduces the section's words in order.
- Keep CHUNKER_VERSION "sections-v1" (nothing has been ingested yet). Document the boundary rule in
  T05_EVIDENCE.md.

STEP 3: T04 tracker sync (docs only).
In execution-plans/hybrid-search/TRACKER.md, mark T04 Merged with:
  - review: https://github.com/SumukhaK/open-source-projectFinder/pull/19#pullrequestreview-5649001232
    (accepted on head 1ada43a36382baa7c790f0c829a810b5f4a0c590)
  - CI: https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40289498384
  - merge commit: d2354e9 (PR #19)
Match the format of the existing T01-T03 rows. Leave T05 un-accepted: it is still under review.

STEP 4: Verify, push, stop.
- Linux with the CI runtime if WSL has RAM (venv /home/sumukha/reporadar-worker-venv, Python 3.11.17 /
  SQLite 3.53.1). Otherwise use Windows and rely on Linux CI.
- Run: python -m pytest backend/tests scripts/tests with the unchanged coverage gate, ruff check,
  ruff format --check, bandit -r backend/app, git diff --check.
- Update T05_EVIDENCE.md (merge result plus RED/GREEN for the boundary fix) and the PR description
  (new head SHA, CI link, note that main d2354e9 is merged in).
- Push to the same PR, wait for CI to go green on the new head, report the new head SHA, then STOP.

NEVER: merge, approve, or write a review marker; change dependencies, lockfiles, workflows, CI gates or
security exceptions; touch the system Python/SQLite or the worker venv interpreter; start another task.
```

Revised phases: (1) merge latest main with both sides preserved and immediately run the full suite; (2) RED/GREEN the boundary fix; (3) sync only T04's completed review/merge evidence while keeping T03 unchanged and T05 unaccepted; (4) full verification, evidence, same-PR push and exact-head CI. Phase 1 verified: merge commit `e7579f3` has reviewed T05 and main `d2354e95b47d8cf4d2d668d09d937e26669c0ed1` as parents. Immediate combined suite: 382 passed, 40 existing Windows POSIX skips, 94.9% combined / 92.9% branch coverage. T04 tests pass unchanged; no application edit preceded this run. Phases 2-4 in progress.

Follow-up progress: phases 1-3 verified. The boundary tests recorded 3 expected failures before implementation; 105 preparation/embedding tests now pass. Final combined Windows suite: 390 passed with 40 existing POSIX skips; 94.9% combined / 93.0% branch coverage; Ruff, Bandit and offline pinned-tokenizer checks passed. T04 tracker sync records its accepted head, review, CI and merge; T03 remains unchanged and T05 unaccepted. Phase 4 local verification complete; same-PR push and exact-head CI pending. See [T05 follow-up evidence](execution-plans/hybrid-search/T05_EVIDENCE.md#main-merge-and-word-boundary-review-follow-up---2026-10-26).


## Tracker sync for T04 and T05 - 2026-10-26

User request (verbatim):

```text
merge and then update the tracker and project readme
```

Scope: documentation only. PR #20 was merged by the reviewed-merge workflow on its exact reviewed head before this sync. This records the T05 merge in the task tracker and refreshes README status lines that still described T04 as not started and T05 as awaiting review. T04's tracker row and history were already synced inside PR #20. No code, tests, configuration, dependencies or CI changed.

- **T04** ([PR #19](https://github.com/SumukhaK/open-source-projectFinder/pull/19)): exact-head acceptance of `1ada43a36382baa7c790f0c829a810b5f4a0c590` ([review 5649001232](https://github.com/SumukhaK/open-source-projectFinder/pull/19#pullrequestreview-5649001232)), [CI 40289498384](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40289498384) passed, merged as `d2354e9` on 2026-10-26. Open: worker wiring (T09/T18) and live GitHub calls.
- **T05** ([PR #20](https://github.com/SumukhaK/open-source-projectFinder/pull/20)): exact-head acceptance of `99c9c1711e8fa2decb1384871e144b7a3adc5e18` ([review 5652759721](https://github.com/SumukhaK/open-source-projectFinder/pull/20#pullrequestreview-5652759721)), [CI 40330742961](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40330742961) passed, merged as `adfd0f8` on 2026-10-26. Open: inline-HTML paragraphs are dropped whole (revisit in T27 relevance evaluation); `CHUNKER_VERSION` must be bumped for any later boundary change once content is ingested.
- Unchanged blockers: policy decisions D1-D8 and prerequisites P1-P3 in [READINESS](execution-plans/hybrid-search/READINESS.md); the node-forge 1.4.0 dependency exception expires 2026-11-01, after which every PR's dependency audit fails until it is resolved.


## Tracker sync for T06 - 2026-10-27

User request (verbatim):

```text
merge and update the docs
```

Scope: documentation only. PR #22 was merged by the reviewed-merge workflow on its exact reviewed head before this sync. This records the T06 merge in the task tracker and task file, corrects stale status lines in the T00, T04 and T05 task files, and changes the README, REQUIREMENTS, SCOPE and backend README status from awaiting review to merged. No code, tests, configuration, dependencies or CI changed.

- **T06** ([PR #22](https://github.com/SumukhaK/open-source-projectFinder/pull/22)): the first review of `b2ae30e` requested separating fetch observation from content identity and refusing raw bytes without a README; both were fixed on the same PR. Exact-head acceptance of `41e5548933a514f800b7964e1a6eb759cac44952` ([review 5662649788](https://github.com/SumukhaK/open-source-projectFinder/pull/22#pullrequestreview-5662649788)), [CI 40455506122](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40455506122) passed, merged as `c73c457` on 2026-10-27. The catalogue is now at schema v2.
- Open: `archive_repositories.full_name`/`metadata_json` keep first-seen values (T10/T19 own refreshing them); unreferenced content files left after a caller rollback are cleaned up by T08.
- Next unblocked: T07 (Milvus adapter) and T16 (discovery planning); T08 needs T07. Unchanged blockers: D1-D8 and P1-P3 in [READINESS](execution-plans/hybrid-search/READINESS.md); the node-forge 1.4.0 dependency exception expires 2026-11-01.
