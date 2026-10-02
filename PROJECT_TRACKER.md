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
- [ ] Local/remote verification and delivery

A coverage percentage alone does not prove correctness. Native release builds and centralized runtime crash aggregation remain deployment-phase work; this phase must not invent hosting, credentials or signing configuration.

User cost/reasoning preference: "one more suggestion, when u think please switch to as high efforts as possible and while implemnting u can switch back to lower efforts"; "within the allowed limits of my subsciption, dont pile up usage bill". Saved reusable preferences in AGENTS.md; no paid services, plan upgrades or extra model runs.

Baseline 11 backend/18 mobile tests passed. New merge/audit/crash/table-boundary tests failed before implementation. Local verification now passes 19 backend/policy and 27 mobile tests, approximately 92.4% backend combined coverage / 85.5% branches and 95.3% mobile statements / 82.3% branches. Patched cryptography, UUID and isolated build tools; no Python dependency findings remain. One node-forge tooling advisory is accepted exactly until 2026-11-01, not silently ignored. All recommended TypeScript security rules remain enabled. Negative fixtures confirm scanners reject unsafe patterns and redact synthetic secrets. CI/actual reviewed-merge delivery validation remains pending.
