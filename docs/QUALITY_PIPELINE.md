# Quality pipeline

This phase uses free open-source tools, with no manually supplied API keys or paid scanner subscriptions. GitHub Actions is the existing runner platform; private-repository runner minutes/storage are subject to the account's included allowance, not unlimited free compute. No billing settings, paid plans or spending limits were changed. Local commands remain usable without hosted runners.

## Checks

| Gate | Tools / behavior |
| --- | --- |
| Backend correctness | pytest unit/integration tests, real HTTP cross-layer flow |
| Mobile correctness | Jest and React Native Testing Library, secure-storage/startup/error regressions |
| Coverage | pytest-cov / coverage.py and Jest; thresholds in `.ci/quality-policy.json` |
| Python quality and SAST | Ruff lint/format and Bandit application scan |
| TypeScript quality and SAST | TypeScript, ESLint and eslint-plugin-security; all recommended security rules fail the build |
| Dependencies | pip-audit on the fully pinned Python lock and npm audit on the JavaScript lock; scanner errors fail closed |
| Secrets | Pinned Gitleaks CLI, full Git history, redacted output; downloaded executable verified against committed SHA-256 |
| Build consistency | Regenerate branding assets and reject drift; export Android/iOS/web bundles |
| Merge | Exact-head self-review plus latest successful quality workflow, verified by default-branch merge automation |

Application coverage gates: backend 90% combined statement/branch coverage and 80% branch coverage; mobile 90% statements/functions, 80% branches and 95% lines. The auth API has its own 85% statement/function, 75% branch and 95% line gate. Jest subtracts files with dedicated thresholds from its global threshold calculation. Coverage includes all application source; build/test scripts and native generated code are outside application percentage gates. Pipeline policies have separate positive/negative tests. Percentages supplement meaningful behavior tests, not replace review.

## Dependency decisions

Upgraded cryptography to patched 50.0.2 and isolated pip/setuptools to patched locked releases. A UUID 11.1.1 override removes the previous UUID advisory while retaining CommonJS support; verified unit tests, Expo diagnostics, asset generation and platform exports after the override.

No dependency exceptions remain. The former node-forge 1.4.0 / GHSA-86w9-cpqp-85rv exception (Expo CLI code-signing tooling, never in the shipped JS client) was removed on 2026-10-29 after node-forge 1.4.1 (published 2026-10-27, which fixes that advisory and four further high-severity advisories affecting ≤1.4.0) was adopted inside Expo's existing `^1.3.3` range; no Expo change or override was needed. The gate still fails on any new finding and on any expired exception, so a future exception must be exact (ecosystem, package, version, advisory), justified and expiring. A passing gate means no known advisory in the audited locks, not a vulnerability-free dependency tree.

## Workflow behavior and cost controls

`.github/workflows/quality.yml` replaces the duplicate backend/mobile workflows. Backend, mobile, dependencies and secrets run in parallel; an always-running **Quality gate** fails if any job failed, was skipped or cancelled. There are no path filters that could leave a required check permanently pending. Read-only job permissions, checkout without persisted credentials, immutable action revisions, dependency caches, job timeouts, cancellation of superseded runs and seven-day report retention bound unnecessary work. No automatic periodic scans, signing jobs, deployments or extra model runs were added.

GitHub's built-in token is automatic and short-lived; no OAuth client secret or other local `.env` value is passed into CI. Reports contain test/coverage/scan results only. Secret findings are redacted. No application code is uploaded to an external scanner service.

## Review-controlled merge

I review the current diff and tests, fix findings and record a GitHub review comment containing:

```text
<!-- reporadar-review:FULL_40_CHARACTER_HEAD_SHA -->
```

Only after that review, dispatch:

```sh
gh workflow run reviewed-merge.yml --ref main -f pr_number=NUMBER -f reviewed_sha=FULL_SHA
```

The workflow checks out trusted `main`, not the PR. It accepts only an open, non-draft, same-repository PR targeting main; the submitted SHA must still be the head. The dispatching user's review comment must refer to that commit, and the latest run of this repository's quality workflow for that PR/head must have succeeded. It uses a minimally scoped automatic GitHub token and `gh pr merge --match-head-commit` without admin bypass. New commits invalidate review. Failed/cancelled/latest-pending runs cannot be substituted with an older green result. Outstanding formal requested changes also block merging. Shell commands never interpolate PR titles/bodies.

This comment records the user's authorized agent self-review; it is not an independent GitHub approval. Existing branch protections and repository rules still apply. Required-check protection depends on the account/repository feature availability and is not silently claimed. The workflow guards our automated merge path; it does not prevent repository administrators from using other paths. Do not grant additional permissions or upgrade plans to bypass a restriction.

## Crash capture

Mobile render failures show a themed, accessible retry screen and emit only a fixed local `mobile_render_crash` event. Retrying remounts providers and restores the secure session. FastAPI catches unhandled request failures before response headers and emits a sanitized event with the declared route template and exception class; responses stay generic. Neither reporter includes exception messages, inputs, query strings, headers or tokens. Tests verify redaction and recovery.

This is local crash detection and recovery, not centralized telemetry. It does not capture OS/native crashes, process startup failures, asynchronous event-handler failures or streaming failures after response start. Production aggregation, native diagnostics, consent and retention belong to the deployment phase; no paid service, hosted collector or DSN/API key was introduced.

## Local verification

From repository root, use `backend/.venv` Python (or an activated equivalent):

```sh
python -m pip install -r backend/requirements.lock.txt
ruff check backend scripts
ruff format --check backend scripts
python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:backend/coverage.json
python scripts/quality.py coverage backend/coverage.json
bandit -r backend/app
pip-audit --strict --no-deps --disable-pip -r backend/requirements.lock.txt -f json -o backend/pip-audit.json
python scripts/quality.py pip backend/pip-audit.json
python scripts/install_gitleaks.py
```

Use `.ci/bin/gitleaks` (`gitleaks.exe` on Windows) with `git --redact --no-banner .`. For staged changes use `git --staged --redact --no-banner .`. Do not scan the ignored local `.env` into a report artifact.

From `mobile`, run `npm ci`, `npm run typecheck`, `npm run lint`, and `RUN_AUTH_E2E=1 PYTHON_EXECUTABLE=python npm run test:coverage` on Unix. PowerShell: set the equivalent process environment variables, run the command, then remove them. Default E2E Python is backend/.venv; setting PYTHON_EXECUTABLE is needed when CI uses a global isolated runner interpreter. `npm audit --package-lock-only --json` may exit 1 for findings; save the report, then use `python scripts/quality.py npm REPORT` from repository root. Do not suppress network/tool errors with `|| true`.

## Validation evidence

Baseline: 11 backend tests, 18 mobile tests; backend approximately 92% combined coverage, mobile 82% statements. Added regression/policy tests fail before implementation. Final local runs: 19 backend/policy tests and 27 mobile tests, including real HTTP E2E; backend approximately 92.4% combined / 85.5% branches and mobile 95.3% statements / 82.3% branches. Negative disposable fixtures prove Gitleaks rejects/redacts a synthetic credential, Bandit rejects unsafe Python deserialization and ESLint rejects dynamic evaluation. Policy tests reject expired/unrelated exceptions, scanner errors, low coverage, foreign/draft/stale PRs, incorrect review authors and failed latest CI.

## Tool references

- [Bandit](https://bandit.readthedocs.io/)
- [pip-audit](https://github.com/pypa/pip-audit)
- [Gitleaks CLI](https://github.com/gitleaks/gitleaks)
- [ESLint security rules](https://github.com/eslint-community/eslint-plugin-security)
- [Jest coverage](https://jestjs.io/docs/configuration#coveragethreshold-object)
