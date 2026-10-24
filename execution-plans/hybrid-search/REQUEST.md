# Request and decision boundaries

Execution-handbook request, verbatim:

```text
now , we will be using deepseek flash v4 available on open code to implemnt this plan, so what u should do is dicide this plan into smaller executable plans, write anothe detailed doc that invloves prompt for execution that explains what to do, what counts as acceptable right solution, what not to do, include a tracker option to mark each tasks as done when its accepted via code review.  include this instruction in each task, deepseek shouldcut a branch from main, execute plan there, raise PR and wait for review. TDD approach for coding so tests first then actaul code. use ponytail and other coding plugins to plan the task with detaile instruction, so codes are minimal, human readable and underestandable, follow lint and other coding discipline. add all these docs on main branch under a newly created folder and push it on main repo as well
```

Earlier architecture request, verbatim:

```text
scan through the whole codebase again and plan for last one year s projects data on our vector db archive and how we refresh it once every week. the api s, archtiecture, libraries needed to implement that , everything. think like a senior software architect and plan in detail and show me the summary
```

Corpus clarification: repositories with code pushed in the last 365 days. The user chose local Milvus and wants to use their 4 GB GPU. Subsequent clarification, verbatim:

```text
i think i missed one important piece of info to give u, search option in our app is hybrid, one end it scans thorugh github search api provided by github docs and we scan through our 365 days indexed in local vector db, we present combined results to the user. now scan through ur own plan with this added info and see if any tweaks in plan is requires and show me updated plan
```

Confirmed product requirements: one combined hybrid search, live GitHub plus local Milvus, a rolling pushed-within-365-days archive, weekly refresh, existing authentication/privacy contracts and a local GPU preference subject to hardware proof. The live branch keeps broader public/unarchived eligibility. Every execution task uses a fresh main-based branch, TDD for behavior, a separate PR and a stop for review.

These recommendations still require an operator/product decision in T00 before real corpus ingestion or public rollout:

| Decision | Recommendation to evaluate | Blocking use |
| --- | --- | --- |
| Corpus selection/cap | 1k feasibility sample, then 10k, diverse language/activity/star bands | T18 acquisition beyond an explicitly approved sample |
| Archived content/license policy | Approved SPDX allowlist; no unknown-license full README content | T09 real content acquisition; T18 |
| Retention | Active eligible content; superseded 30 days; content-free run history 90 days | T20 policy activation |
| Visibility | ID-bound public check, cache at most 15 minutes; fail closed when unverified | T10/T15 production serving |
| Offline backup exception | Encrypted backup maximum 7 days; quarantine and reapply current suppression ledger on restore | T21/T22 live-content backups |
| Backup tool/destination | Select a maintained, free encryption-capable backup tool and private destination; verify restore | T21; do not invent encryption |
| Schedule/availability | Sunday 03:30 Asia/Kolkata, missed-run catch-up, laptop availability disclosed | T23 host activation |
| Quality thresholds | Record measured latency baseline and acceptable relevance changes before tuning | T27/T28 rollout recommendation |

T00 records decision owner, date, evidence and approved values here. A recommendation is not consent. If an answer is missing, keep dependent real-data/rollout work blocked and continue only independent synthetic/offline work. No DeepSeek/OpenCode model ID, provider configuration, availability, free quota or pricing was verified by this handbook; use the model the user has already selected and do not change billing/settings.

## Publication baseline, 2026-10-24

At initial authoring, main was `2237c7e5241a698258a28952150194b943d616b0`, PR #10 (enhanced keyword search) was open, and the mobile discovery foundation was local/unmerged. The following audit paragraphs preserve that historical baseline; the delivery update below records its resolution. Recheck current main on execution.

A fresh audit of main's committed mobile lock failed the existing policy on `zod 3.25.76 / GHSA-mrhx-c7xc-m3w5`. The existing node-forge exception expires 2026-11-01 and must be rechecked. The old [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) and [sprintf-js advisory](https://github.com/advisories/GHSA-hp3w-g68c-fv3c) were withdrawn; withdrawal is not a package patch. Do not carry their earlier proposed exceptions forward. Consult the current [Zod advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5), audit output and dependency consumers before proposing a compatible fix. Do not force the audit's Expo downgrade or silently override Zod across a major version. A new exception needs explicit authorization and normal review; documentation cannot waive the gate.

The [first handbook CI run](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40082178448) also failed main's unchanged Python lock on six advisories in four packages: certifi 2026.7.22, filelock 4.0.9, opentelemetry-api 1.45.0 and setuptools 84.0.0. Its audit job stopped at Python before reaching npm; the Zod finding is from the separate local lock-only audit, not that remote npm step. Backend quality, mobile quality/E2E and secret scanning passed in that run. This is dated baseline evidence, not proof of later-head CI or a remediation. Re-audit both lockfiles in T00 and resolve dependency fixes through separate reviewed work before claiming readiness.

## Delivered prerequisites, 2026-10-24

[Security PR #12](https://github.com/SumukhaK/open-source-projectFinder/pull/12) merged as `be74b1a3b5f3a583787f1d40d62b627881bca005`. It updates certifi/filelock/opentelemetry-api/setuptools and uses a scoped Expo CLI override to Zod 4.6.6, with a failing-then-passing bounded-array regression and actual Expo schema compatibility tests. Both audit gates and the full [exact-head CI](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40083752223) passed; no new exceptions or gate changes. The existing node-forge exception remains due for review before 2026-11-01; audits are not an absence-of-all-risk guarantee.

[Search PR #10](https://github.com/SumukhaK/open-source-projectFinder/pull/10) merged as `1e681ae5fe1bb309e793c225aa0513335d95ba15`, after independent review and passing [current-head CI](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40083939979). It adds the tested legacy keyword-search controls; PR #11's handbook does not duplicate that implementation. Main now contains this search foundation and the dependency fixes. T00/T11 must verify them, preserve their actual contract and audit again on execution.

The mobile discovery foundation is still local/unmerged, and archive/hybrid tasks T00-T29 remain not started. Do not mistake these prerequisite merges or this handbook for Milvus/GPU/weekly-refresh/hybrid implementation. No model download, ingestion or host scheduling was performed.
