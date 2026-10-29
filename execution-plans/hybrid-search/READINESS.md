# T00 readiness and policy decisions

Status: **Accepted and merged** via [PR #13](https://github.com/SumukhaK/open-source-projectFinder/pull/13) (`6dc4233`, 2026-10-24); acceptance evidence is in [TRACKER](TRACKER.md). The decisions and prerequisites below remain open unless the tracker or REQUEST records otherwise. This is a documentation/prerequisites slice. It implements no archive, hybrid, mobile, ingestion, scheduler, credential or quality-gate change. Review/merge evidence belongs in [TRACKER](TRACKER.md).

| Control | Value |
| --- | --- |
| Task | [T00: Readiness and policy decisions](tasks/T00-readiness.md) |
| Branch | `codex/hybrid-t00-readiness` |
| Base `origin/main` | `2e4a9ff353de7a137c49fff0c99bea1765a357a2` (2026-10-24) |
| Scope | Readiness record, prerequisite verification, dependency re-audit, decision owners/blockers, operator handoff |
| Non-goals | No implementation, model download, live ingestion, service/schedule, mobile change, gate change or invented approval |

## 1. Baseline and prerequisites

Inspected 2026-10-24 after `git fetch origin --prune`. The base is the current `origin/main` head.

| Prerequisite | Dated evidence | State |
| --- | --- | --- |
| Handbook PR #11 | [PR #11](https://github.com/SumukhaK/open-source-projectFinder/pull/11) merged as `2e4a9ff353de7a137c49fff0c99bea1765a357a2` at 2026-10-24T10:01:57Z; reviewed head `5cba2a4b46315873790629ea55652c9dc64c3f79`; [CI 40084144348](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40084144348) passed | Merged; this task's base |
| Search PR #10 | [PR #10](https://github.com/SumukhaK/open-source-projectFinder/pull/10) merged as `1e681ae5fe1bb309e793c225aa0513335d95ba15`; reviewed head `3b80dad4fefb6ee5e8008ffbbe9217b22b501e2e`; [CI 40083939979](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40083939979) passed | Merged; present in base |
| Security PR #12 | [PR #12](https://github.com/SumukhaK/open-source-projectFinder/pull/12) merged as `be74b1a3b5f3a583787f1d40d62b627881bca005`; reviewed head `163e77deb6542d5adc128ed8a49dcf5d543d7388`; [CI 40083752223](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40083752223) passed | Merged; present in base |
| Mobile discovery foundation | No origin branch and no PR. Only uncommitted files in the operator checkout on `improved-search-endpoint` (for example `mobile/src/features/discovery/`, `mobile/src/config/discovery.ts`, `mobile/tests/discovery*.tsx`, plus modified mobile files). | **Unmerged**; must be delivered as a separate prerequisite PR. Do not copy it here. Blocks T24, T25, T26. |
| Open PRs / other origin branches | `gh pr list --state open` returned none; `git ls-remote --heads origin` returned only `main` | Clean baseline |

CI limitation: the merge commit `2e4a9ff` has no separate push-workflow run recorded. The exact reviewed PR #11 head `5cba2a4` passed [CI 40084144348](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40084144348). This record does not claim a separate main-push run.

### Current contract snapshot (base `2e4a9ff`)

- `POST /projects/search` is authenticated and keyword-only. It accepts `idea` 2-1000 characters, `page` 1-50, optional `per_page` 1-100, optional `sort` (`stars`, `forks`, `updated`) and `order` (`asc`, `desc`). It returns `items`, `total`, `incomplete`, `page`, `per_page`, `sort`, `order` and `source: github_keywords`, appends `is:public archived:false`, and rejects pages beyond GitHub's first 1,000 results. It is a conservative adapter, not semantic search.
- `GET /projects/{owner}/{name}` and the favourites routes remain the existing details/favourites contract.
- `backend/app/core/config.py` contains auth, GitHub, rate-limit, timeout and retry settings only; there are no archive/Milvus/embedding settings yet.
- `mobile/src/` contains auth and branding screens only; there is no merged discovery feature. This is why T24 cannot start.

## 2. Dependency audit (fresh, 2026-10-24)

Environment: Windows 10 Home Single Language; Python 3.11.9; pip-audit 2.10.1; Node 24.19.0; npm 11.17.0; ruff 0.16.10; Bandit 1.9.4.

| Check | Command | Actual result |
| --- | --- | --- |
| Python audit | `python -m pip_audit --strict --no-deps --disable-pip -r backend/requirements.lock.txt -f json -o reports/python-audit.json` | Exit 0; 59 dependencies; 0 known vulnerabilities |
| Python policy | `python scripts/quality.py pip reports/python-audit.json` | Exit 0; gate passed |
| npm audit | `npm audit --package-lock-only --json` in `mobile/` | Exit 1; 4 high entries; one direct advisory `GHSA-86w9-cpqp-85rv` on `node-forge 1.4.0`, propagated to `@expo/cli`, `@expo/code-signing-certificates` and `expo` |
| npm policy | `python scripts/quality.py npm reports/npm-audit.json` | Exit 0; gate passed through the existing `.ci/quality-policy.json` exception |
| Coverage policy | `python scripts/quality.py coverage reports/backend-coverage.json` | Exit 0; 97.0% combined; 93.0% branches |

The `npm audit` exit code is expected when findings exist. The policy gate is authoritative and passes only because the sole direct advisory matches the recorded exception. The exception expires **2026-11-01** (eight days after this audit). It is an inherited blocker, not a clean bill of health: it must be rechecked or replaced before release. This task adds no exception and changes no gate.

Audits are point-in-time checks; they do not prove the absence of all risk.

## 3. Decision gates

Owner for every decision: **Operator**. Date recorded: **2026-10-24**. Recommendations and proposed values are in [REQUEST](REQUEST.md#request-and-decision-boundaries); they are proposals, not approvals. At T00 no decision was resolved. Update 2026-10-29: the owner approved **all eight decisions D1-D8** (below). D8 approves the method; its numeric thresholds are set after T27 measures the baseline and need the owner's sign-off then. Prerequisites P1-P3 are tracked separately.

| ID | Decision | Status | Evidence | Blocking tasks |
| --- | --- | --- | --- | --- |
| D1 | Corpus selection/cap | **Approved 2026-10-29** | Owner: 1,000-repository feasibility sample first, then 10,000 after measured disk/RAM/latency on the laptop; 25k/50k expansion needs separate approval. See [TRACKER](TRACKER.md#blockers-and-decisions) | — (expansion beyond 10k: T28) |
| D2 | Archived content/license policy | **Approved 2026-10-29** | Owner: store only permissive-licence content (`MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `0BSD`, `Unlicense`, `CC0-1.0`); no-licence, unknown/`NOASSERTION`/`other` and copyleft repositories are never stored, but may still appear as live GitHub results. See [TRACKER](TRACKER.md#blockers-and-decisions) | — (T18 still needs P1 rotation ownership) |
| D3 | Retention | **Approved 2026-10-29** | Owner: keep active eligible content while eligible; delete superseded revisions after 30 days; delete content-free run history after 90 days. See [TRACKER](TRACKER.md#blockers-and-decisions) | — |
| D4 | Visibility | **Approved 2026-10-29** | Owner: ID-bound public check before serving (cache ≤15 min, fail closed); periodic sweep removes private/deleted repositories first, then licence changes, then refreshes/adds, and retires 365-day age-outs last; manual removal on request. See [TRACKER](TRACKER.md#blockers-and-decisions) | — (sweep built in T19/T20) |
| D5 | Offline backup exception | **Approved 2026-10-29** | Owner: encrypted backups kept at most 7 days; a restore is quarantined and the current suppression ledger reapplied before use. See [TRACKER](TRACKER.md#blockers-and-decisions) | — |
| D6 | Backup tool/destination | **Approved 2026-10-29** | Owner: restic (free, maintained, encrypted by default) to an owner-owned external drive; restore verified once in T21. See [TRACKER](TRACKER.md#blockers-and-decisions) | — |
| D7 | Schedule/availability | **Approved 2026-10-29** | Owner: daily privacy/removal sweep about 22:00 Asia/Kolkata; full refresh Sunday 03:30 Asia/Kolkata; missed runs catch up when the laptop is next on. See [TRACKER](TRACKER.md#blockers-and-decisions) | — |
| D8 | Quality thresholds | **Method approved 2026-10-29** | Owner: hybrid search must be at least as relevant as today's search within an agreed response time; exact numbers set after T27's baseline and approved by the owner then. See [TRACKER](TRACKER.md#blockers-and-decisions) | T28/T29 until the numbers are approved |

Operational prerequisites that are not among the eight decisions:

| ID | Prerequisite | Status | Blocking tasks |
| --- | --- | --- | --- |
| P1 | Dedicated, revocable operator-owned public-read worker GitHub credential | Created privately on the owner's laptop (2026-10-29) and used only for the T09 one-repository pilot; rotation/revocation ownership still to confirm | T04 real reads; T18; T19 |
| P2 | Reviewed mobile discovery foundation merged into main | Not delivered; no PR | T24, T25, T26 |
| P3 | Docker/WSL2/CUDA/Milvus feasibility proven on the operator host | Unverified | T01 acceptance; T07/T13 real GPU claims |

## 4. Readiness matrix

T00 is the only task this PR advances. After T00 merges, T01 is the only task whose listed prerequisite is satisfied. Later rows describe what can proceed within a task's synthetic/offline scope and what remains gated.

| Readiness | Tasks | Why |
| --- | --- | --- |
| Ready after T00 merges | T01 | Its only listed prerequisite is T00. It is the feasibility probe; GPU may be recorded as blocked pending an approved CPU-only change. |
| Synthetic/offline work can proceed once predecessor tasks merge | T02, T03, T04 (test transport), T05, T06, T07, T08, T11, T12, T13, T14, T16, T17 | Their merged dependency chain does not require live corpus acquisition or production policy approval. Real licensed samples, real reads and production serving still require D2/P1/P3 as applicable. |
| D4 approved (2026-10-29) | T10, T15, T19/T20 | Serving follows the approved check-before-serve and removal-priority policy; production rollout still needs the remaining gates (D8 thresholds). |
| D1 approved (2026-10-29) | T18, T28 | 1k then 10k approved; 25k/50k expansion still needs approval at T28. |
| D2 approved (2026-10-29) | T18 content rule | Permissive SPDX allowlist approved; T18 still needs P1 rotation ownership. |
| D3 approved (2026-10-29) | T20 | Retention periods approved (30 / 90 days). |
| D5/D6 approved (2026-10-29) | T21, T22 | Encrypted 7-day backups with restic to an owner-owned external drive. |
| D7 approved (2026-10-29) | T23 | Daily ~22:00 sweep and Sunday 03:30 refresh (Asia/Kolkata) with catch-up. |
| D8 method approved (2026-10-29) | T27, T28, T29 | T27 measures the baseline; numeric thresholds need owner approval before the T28/T29 rollout recommendation. |
| Blocked by P1 | T04 real reads; T18; T19 | Credential now exists (used for the T09 pilot); confirm rotation/revocation ownership before T18/T19. Test transport remains available. |
| Blocked by P2 | T24, T25, T26 | The mobile discovery foundation is not merged and has no delivery PR. |
| Blocked by P3 | T01 acceptance; T07/T13 real GPU claims | Hardware/runtime is unverified; T01 owns the real evidence. |

This matrix does not change any task status in [TRACKER](TRACKER.md). Only a trusted reviewer can accept T00, and only a merge unblocks T01.

## 5. Verification evidence

All commands were run in the T00 worktree on 2026-10-24 unless noted.

| Check | Command | Actual result |
| --- | --- | --- |
| Lint | `ruff check backend scripts` | Exit 0; all checks passed |
| Format | `ruff format --check backend scripts` | Exit 0; 16 files already formatted |
| Backend tests | `python -m pytest backend/tests scripts/tests -q --cov=backend/app --cov-branch --cov-report=json:reports/backend-coverage.json` | 94 passed; exit 0 |
| Coverage | `python scripts/quality.py coverage reports/backend-coverage.json` | 97.0% combined; 93.0% branches; exit 0 |
| Security scan | `python -m bandit -r backend/app -q` | Exit 0; no findings reported |
| Python audit/policy | See section 2 | 59 dependencies; 0 vulnerabilities; policy exit 0 |
| npm audit/policy | See section 2 | 4 high entries; one direct advisory; policy exit 0 via existing exception |
| Whitespace | `git diff --check` | Exit 0 |
| Links/anchors | Local Markdown link/anchor check over 40 handbook/root docs | 302 relative links and anchors resolved |
| Secrets | Changed-file inspection for token/key patterns | No credential or private-key patterns found |

No behavioral RED is claimed: this is a documentation-only change, so there is no runtime requirement to fail first. The existing backend suite is a regression baseline, not evidence for unimplemented archive/hybrid features.

Limitations:

- No Docker/WSL2/CUDA/Milvus run, GPU visibility check, model download, embedding throughput or index build was performed. T01 owns that evidence.
- No real GitHub corpus read or worker credential was used.
- Mobile code is unchanged and its local suite was not run in this worktree; PR CI runs the existing mobile checks.
- CI for this PR head is not claimed here; reviewers must use the exact-head run.
- The `node-forge` exception was retired: node-forge is locked at patched 1.4.2 (merged 2026-10-28, before the 2026-11-01 expiry).

## 6. Operator actions

1. Approve or reject D1-D8 with the approved values and a dated evidence link in [REQUEST](REQUEST.md#request-and-decision-boundaries). A recommendation is not consent.
2. Confirm ownership, rotation and revocation for the P1 worker credential before T04 real reads or T18/T19.
3. Deliver the P2 mobile discovery foundation through a separate reviewed PR; do not copy the local uncommitted WIP into a task branch.
4. Provide or approve the host/runtime access needed for T01 to prove Docker/WSL2/CUDA/Milvus, or explicitly approve a CPU-only fallback.
5. Review this PR at its exact head and merge only after required checks pass. T01 must not start until T00 is merged.
6. ~~Recheck or replace the `node-forge` exception before 2026-11-01.~~ Done: bumped to node-forge 1.4.2 and the exception removed.

## 7. Rollback

Documentation-only. Revert the T00 commit(s); no schema, data, service, schedule, credential or deployment state changes exist to roll back. The generated `reports/` audit and coverage files are gitignored and are not part of the change.
