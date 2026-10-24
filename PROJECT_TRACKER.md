# Project Tracker

## Current state
Core idea received on 2026-10-02. Project name: RepoRadar. Repository: SumukhaK/open-source-projectFinder (private initially). Confirmed stack: Python FastAPI, React mobile client, Milvus, GitHub Search API. Detailed brainstorming remains pending.

## Workflow preparation
- [x] Read Karpathy guidelines and extract additional reusable engineering instructions.
- [x] Create AGENTS.md.
- [x] Preserve the initial workflow prompt below.
- [ ] Complete end-to-end project brainstorming and receive the project-specific prompt.
- [ ] Extract technical requirements, scope, decisions, and unresolved questions.
- [ ] Define feature phases, dependencies, acceptance criteria, and verification checks.
- [x] Create README.md with planned architecture and selected tools, REQUIREMENTS.md, and SCOPE.md.
- [x] Establish the GitHub repository identity and initialize the repository.
- [ ] Implement features through TDD, feature branches, pull requests, review, and merge.

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
| 1 | Finalize requirements, API contract, providers and evaluation criteria | Planned | Agreed acceptance criteria and recorded decisions |
| 2 | Text idea submission and GitHub search baseline | Planned | Unit tests first, API integration checks, relevant results |
| 3 | Periodic ingestion, embeddings and Milvus index | Planned | Repeatable ingestion, deduplication, updates and retrieval checks |
| 4 | Hybrid retrieval, ranking and AI similarity explanations | Planned | Agreed relevance evaluation, provenance and failure handling |
| 5 | Mobile text discovery flow | Planned | Client tests and end-to-end submission/results verification |
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


## Hybrid search execution handbook - 2026-10-24

Original request (verbatim):

```text
now , we will be using deepseek flash v4 available on open code to implemnt this plan, so what u should do is dicide this plan into smaller executable plans, write anothe detailed doc that invloves prompt for execution that explains what to do, what counts as acceptable right solution, what not to do, include a tracker option to mark each tasks as done when its accepted via code review.  include this instruction in each task, deepseek shouldcut a branch from main, execute plan there, raise PR and wait for review. TDD approach for coding so tests first then actaul code. use ponytail and other coding plugins to plan the task with detaile instruction, so codes are minimal, human readable and underestandable, follow lint and other coding discipline. add all these docs on main branch under a newly created folder and push it on main repo as well
```

Scope: publish the existing proposed hybrid/archive architecture plus portable OpenCode execution prompts in [execution-plans/hybrid-search](execution-plans/hybrid-search/README.md). No archive implementation, provider/model configuration, model download or scheduler activation is included. Confirmed requirements and earlier project prompts are retained in [REQUEST](execution-plans/hybrid-search/REQUEST.md); policy recommendations remain pending explicit decisions.

| Phase / feature | Status | Verification / acceptance |
| --- | --- | --- |
| Handbook authoring | Authored in PR #11; awaiting final exact-head review/checks and publication | Static checks passed for 37 Markdown files, 30 required task workflows, 286 local links/anchors, dependency ordering and both diagram themes. Independent review found one missing T17 dependency on T08 publication; it was added to the task and tracker. [PR #11](https://github.com/SumukhaK/open-source-projectFinder/pull/11) and its current-head review/checks are authoritative for publication status. |
| T00-T29 implementation | Not started | [Task tracker](execution-plans/hybrid-search/TRACKER.md) is authoritative for per-task status, full reviewed SHA/review/CI evidence and merged SHA. Only review acceptance checks a task done; dependents require merge into main. |

Main baseline was 2237c7e5241a698258a28952150194b943d616b0. Search PR #10 and the local discovery mobile foundation were not merged during authoring. Fresh dependency policy evaluation on 2026-10-24 blocked main's mobile lock on zod 3.25.76 / GHSA-mrhx-c7xc-m3w5; the earlier braces/sprintf advisories were withdrawn, not patched here. The handbook preserves current gates and requires rechecking prerequisite/security state. No unrelated workspace changes are included.
