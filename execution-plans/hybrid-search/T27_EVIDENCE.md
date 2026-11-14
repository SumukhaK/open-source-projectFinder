# T27 Evidence — human-judged relevance evaluation

Base: `origin/main` `ff9d6b72dd1146739c5c30277c43fffa9fda556a` (work started on `40546ba`; T26 merged as `6315e23`, [PR #111](https://github.com/SumukhaK/open-source-projectFinder/pull/111)).
Prerequisite verified merged into main: T26 `6315e23`. D8 method approved 2026-10-29; its numbers are set from this task's baseline.

T27 has two parts. **Part A** ([PR #114](https://github.com/SumukhaK/open-source-projectFinder/pull/114), merged as `bf58d1e`, plus the collect fixes in #117 and #118) is the frozen query set, the offline
evaluation tool and its tests. **Part B** ([below](#part-b-results-run-3-2026-11-13))
is the real snapshot, the judging, the results and the D8 options. T27 is done
only when Part B is reviewed and the owner has picked a D8 option. Both happened on 2026-11-13: Part B merged as `f039f2f` and the owner chose A+B.

## What Part A adds

| File | Role |
| --- | --- |
| `scripts/relevance/ideas.json` | 58 frozen ideas: 18 common, 12 rare, 12 naming a language/framework, 8 non-English (German, Spanish, French, Portuguese, Japanese, Chinese, Hindi, Kannada), 5 expected no-match, 3 vague. All written for this evaluation; none comes from a user, log or transcript, and none holds personal data, so the voice plan can reuse it. Change only by adding new ids. |
| `scripts/relevance_eval.py` | `collect`, `sheet` and `report` subcommands (below). Standard library plus the existing backend services; no new dependency. |
| `scripts/tests/test_relevance_eval.py` | 29 tests: hand-computed nDCG, ideal from the whole judged pool, cut-off and duplicate handling, ties, unjudged results, undefined scores with nothing relevant, judged-pool recall, pool construction, snapshot binding, eight invalid-judgment cases, incomplete ideas, source contributions, the failure-margin boundary, the blind sheet (exact item keys, so no stars or source leak) and its script escaping, the query set, and collection from one search without writing the token. |
| `scripts/tests/conftest.py` | Puts `backend/` on the import path so script tests also run on their own. |

### How the three runs are made

`collect` builds the same `HybridSearchService` the v1 route uses and runs each
idea once. Thin wrappers record the live GitHub keyword answer and the checked
archive evidence from that same call, then:

- **Keyword (today)**: `fuse_candidates(github)` alone. It uses the same
  `compile_keyword_query` and GitHub scope as today's `/projects/search`.
- **Archive only**: `fuse_candidates(empty, archive_evidence)`, after the normal
  eligibility check.
- **Hybrid**: the service's fused result (`rrf-v1`).

All three see the same GitHub answer and the same archive state, so the
comparison is fair at one moment. The snapshot keeps the top 20 per run and
records the ranking version, RRF k, model revision, Milvus collection, archive
repository count and date, ideas-file hash, commit and per-idea latency. These
are offline evaluation runs, not product search modes.

### Judging and metrics

- The **judged pool** for an idea is the union of each run's top 10. The
  `sheet` page shows it shuffled (seeded by the snapshot digest), with name,
  language, description and a GitHub link only: no run names, scores, snippets
  or stars, so the judge cannot tell which search found what. Grades: 2 good
  match, 1 partly, 0 not useful, plus an "unsure" tick. Progress stays in the
  browser and downloads as `judgments.json`, bound to the snapshot's SHA-256.
- **nDCG@10** uses gain `2^grade - 1`; the ideal is the best order of the whole
  judged pool, so a run is not rewarded for missing what another run found.
- **Recall@20 is judged-pool recall**: relevant (grade 1 or 2) judged results
  found in a run's top 20, divided by all relevant judged results for the idea.
  It is not recall over all of GitHub. Results 11-20 that no run put in its
  top 10 are unjudged and count as not relevant.
- An idea with any unjudged pooled result is left out of the means and listed.
  An idea where nothing is relevant has undefined scores and is listed as
  no-match rather than averaged as 0.
- The report adds nDCG by category, where hybrid's relevant top-10 results came
  from (both, keyword only, archive only), keyword-source and hybrid latency
  (median, p95), failure cases (hybrid more than 0.1 below keyword) and a
  side-by-side top-10 table per idea with the owner's grades.

## Verification (2026-11-13, Linux cloud container, Python 3.13.18, SQLite 3.53.1)

- RED: `python -m pytest scripts/tests/test_relevance_eval.py -q` failed at
  collection (`ModuleNotFoundError: No module named 'scripts.relevance_eval'`)
  before the module existed.
- GREEN: the same command — 27 passed; 29 after the review fixes below.
- Full suite: `python -m pytest backend/tests scripts/tests -q` — 1397 passed, 9 skipped (exit 0).
- `ruff check backend scripts` and `ruff format --check backend scripts` passed.
- Browser check of the sheet with a synthetic 4-idea snapshot (headless
  Chromium): every item graded, reload restored progress, the download produced
  a valid judgments file, `report` scored it, no console errors, and a
  description containing `</script>` rendered as text.
- Not run: `collect` against the real stack. It needs the laptop's model,
  Milvus and catalogue plus a GitHub token, so it is Part B.

## Review fixes (2026-11-13)

Independent review of `5c685d0` asked for: `collect` to load `backend/.env`
explicitly and resolve relative paths from `backend/` (it previously read
`.env` from the current directory, so a run from the repo root missed the
Milvus token and catalogue path); exact blind-item keys in the sheet test; a
`FAILURE_MARGIN` boundary test; `archive_as_of` always present in versions; and
a role label for the judge name. Gitleaks also flagged the sheet's `const KEY = ...`
local-storage name as a generic API key (a false positive); it is renamed
`storageName` and the branch history was squashed so no commit carries it. All
are done; `scripts/tests` 66 passed, ruff
clean.

## Warm-up fix (2026-11-13)

The first real `collect` on the laptop (main `d8905d8`) found the archive source
timing out on exactly the first 5 ideas (cold start, hybrid about 8.0 s) and ok
on the other 53, which would unfairly zero archive-only and degrade hybrid for
c01-c05. `collect` now runs an unscored warm-up first (fixed text not in
`ideas.json`, up to 3 tries until the archive is ok) and records
`versions.warmup = {archive_status, attempts}`. RED: the new tests failed to
import `WARMUP_IDEA`; GREEN: `scripts/tests/test_relevance_eval.py` 32 passed.
Other facts from that first run: 426 s wall, 1.24 GiB max RSS, a judged pool of
1,057 results, and no repository returned by both keyword and archive for any
of the 58 ideas. That snapshot is discarded; collect is rerun after this fix.

## Per-idea retry and a cold-cache finding (2026-11-13)

The rerun with the warm-up (main `3fe2d94`) ended with
`versions.warmup = {archive_status: "failed", attempts: 3}`; c01 and c02 still
timed out (about 8.0 s each) and c03 onward were ok. Run 2 facts: 410 s wall,
1.31 GB max RSS, archive ok on 56 of 58 ideas, hybrid degraded on 3, a judged
pool of 1,087, and still no repository shared by keyword and archive.

Cause, checked in `EligibilityService.check`: every archive hit whose
repository is not in the visibility cache needs its own GitHub metadata read
(`reader.fetch_metadata`), one after another, before it can be served. A cold
cache therefore needs up to about 100 sequential reads for one search, which
does not fit the 8 s `hybrid_search_budget`. Reads are cached for
`archive_visibility_ttl_seconds` (900 s), so once a few searches have touched
most of the ~204 pilot repositories, later ideas are fast. A fixed warm-up text
only warms the repositories it hits. It is not a model or Milvus warm-up.

Fix: `collect` keeps the warm-up and now searches an idea again, whole, up to
2 more times (with the normal pause) when its archive source failed. All three
runs of a kept entry still come from one search call; `entry.attempts` records
how many ran, and the report header counts retried and still-failed ideas.
RED: the two new tests failed against the previous `collect`; GREEN: 34 passed.

**Product finding for T28:** after a restart, or once the 15-minute
visibility cache has expired, the first real searches can lose the archive
source at the 8 s budget because eligibility reads GitHub once per uncached
hit, serially. Users would see degraded results (live-only) for the first
queries. T28 should measure it and consider bounded parallel reads, a
pre-warm of the catalogue's visibility after start, or serving a still-fresh
check longer; it is not changed here.

## Part B results (run 3, 2026-11-13)

Branch `claude/t27-part-b`: the owner's laptop data (`86d9871`, 8 files in
[`scripts/relevance/runs/2026-11-13/`](../../scripts/relevance/runs/2026-11-13/))
merged with three small tool changes. No product code changes.

### Run facts

- `collect` at `0b27f24` (main after #118) on the owner's laptop: model
  revision `614241f`, collection `repo_chunks_e5small_v1`, `rrf-v1`, k=60, 100
  keyword candidates, **204 archive repositories**.
- Warm-up `{archive_status: failed, attempts: 3}`. c02 needed 2 attempts and
  c01 still failed after 3 (the cold eligibility cache, see the T28 finding
  above). Archive ok on 57 of 58 ideas.
- Judged pool 1,097 results (union of each run's top 10). No repository was
  returned by both keyword and archive for any idea.
- Latency: keyword source median 3,764 ms, p95 4,738 ms; hybrid median 3,771
  ms, p95 5,068 ms. This is not a capacity measurement; T28 owns that.
- **The snapshot is not committed.** Its archive snippets are verbatim README
  text that gitleaks flags (sample keys, JWTs) and that holds third-party
  e-mail addresses. It stays private on the owner's laptop: file sha256
  `a06572d6a6353f13d157373d6921302f10b5b138fd910c1cef1ba90e4c2b0409`
  (2,074,630 bytes); relevance_eval digest
  `8a7733149acd97e2ed2b736a2001516b5ab33ba809b6a37d33ecc14c5d6aece0`, which
  every committed judgment file is bound to. `collect` no longer stores
  snippets (below), so later snapshots can be committed.

### Judging and agreement ([agreement.md](../../scripts/relevance/runs/2026-11-13/agreement.md))

- **Owner:** 50 blind labels on 3 ideas (c01-budget 10, c02-markdown-notes 20,
  c04-static-blog 20), in `owner-judgments.json`.
- **Two blind Claude judges** graded all 1,097 (`model-judgments.json`,
  `model2-judgments.json`). Model vs model: 95.2% exact, weighted kappa 0.93.
  Owner vs each model on the 50 owner labels: 66% exact, 80% on relevant vs
  not, weighted kappa 0.53 / 0.51; the models are more lenient.
- **Caveat:** model 1 saw the owner's c01 and c02 grades before grading those
  two ideas, so owner-vs-model agreement there is not fully blind. c04 and all
  of model 2's grades were blind.
- **Reconciled** (`judgments.json`, used for the headline numbers): the owner's
  label where present; else the grade both models agree on; else the lower
  grade, marked unsure. 1,097 labels, 215 unsure.
- **Against the T27 rule** ("human judges, not the implementing model, approve
  labels"): only the owner's 50 labels are human. The other 1,047 are model
  labels, and they are the main input to the means. The conclusion below holds
  on each model's labels alone, but the reviewer and owner should decide
  whether this counts as T27's human-judged baseline or whether more owner
  judging is needed first.

### Results ([report.md](../../scripts/relevance/runs/2026-11-13/report.md))

Means over the 45 ideas with at least one relevant result (13 ideas, including
all 5 no-match ideas, had nothing relevant). Recall@20 is judged-pool recall.

| Run | nDCG@10 reconciled | nDCG@10 model / model 2 | Judged-pool Recall@20 |
| --- | --- | --- | --- |
| Keyword (today) | 0.695 | 0.709 / 0.710 | 0.969 |
| Archive only | 0.034 | see reports | 0.031 |
| Hybrid (`rrf-v1`) | 0.428 | 0.429 / 0.431 | 1.000 |

| Category (reconciled nDCG@10) | Keyword | Archive only | Hybrid |
| --- | --- | --- | --- |
| common | 0.736 | 0.017 | 0.480 |
| language | 0.652 | 0.050 | 0.414 |
| non_english | 0.470 | 0.153 | 0.214 |
| rare | 0.788 | 0.000 | 0.445 |
| vague | 0.431 | 0.000 | 0.333 |

- Hybrid is more than 0.1 below keyword on **36 of 58 ideas**; the failure list
  is in the report.
- Hybrid's relevant top-10 results: keyword only 109, archive only 5, both 0.
- Hybrid's judged-pool recall of 1.000 only means its top 20 contains both
  lists' top 10s; it is not a quality gain.

### Offline re-ranking what-if (`whatif`, run on the laptop at `123a278`)

Re-ranks the frozen keyword and archive lists with the reconciled judgments;
offline only, not a product mode. All 58 ideas complete; no strategy put an
unjudged result into a top 10.

| Strategy | nDCG@10 | Recall@20 | Ideas >0.1 below keyword | nDCG@10 model / model 2 |
| --- | --- | --- | --- | --- |
| frozen hybrid (served) | 0.428 | 1.000 | 36 | 0.429 / 0.431 |
| `rrf` recomputed | 0.428 | 1.000 | 36 | 0.429 / 0.431 |
| weighted RRF, archive 0.9 | 0.640 | 1.000 | 15 | 0.642 / 0.654 |
| weighted RRF, archive 0.75 | 0.695 | 0.969 | 0 | 0.709 / 0.710 |
| weighted RRF, archive 0.5 | 0.695 | 0.969 | 0 | 0.709 / 0.710 |
| weighted RRF, archive 0.25 | 0.695 | 0.969 | 0 | 0.709 / 0.710 |
| keyword, then archive | 0.695 | 0.969 | 0 | 0.709 / 0.710 |
| keyword top 5, then archive | 0.511 | 0.606 | 28 | 0.515 / 0.518 |

The recomputed `rrf` reproduces the served hybrid exactly. With k=60 an
archive rank-1 result passes keyword rank 10 only when its weight is above
61/70 (about 0.87), so every weight of 0.75 or less is identical to keyword
only on this data. Each step that brings archive results into the top 10 costs
nDCG.

### Conclusion

On today's 204-repository pilot archive, adding archive results makes ranking
worse: the archive rarely holds a relevant repository for these ideas (5
relevant archive-only results in 58 top-10s), and equal-weight RRF interleaves
its weak matches from position 2. No tested mix improves on keyword-only. The
cause is coverage, not fusion: archive-only nDCG@10 is 0.034. The archive's
promise (semantic matches GitHub keywords miss) cannot be measured until the
archive is much larger. D8's rule ("at least as relevant as today's") is
**not met** by the shipped `rrf-v1` hybrid.

### D8 options for the owner (no number chosen here)

- **A. Keep the archive out of the top 10 for now.** Serve keyword first, by
  ranking archive after keyword or by weighted RRF with an archive weight of
  0.75 or less, which equals keyword-only here: nDCG@10 0.695, 0 ideas worse.
  Rerun T27 with the same ideas after the 10k pilot, and only then let the
  archive into the top 10. This needs a ranking change (a new
  `RANKING_VERSION`) in its own reviewed task, not in this one; it was
  implemented 2026-11-14 in
  [PR #125](https://github.com/SumukhaK/open-source-projectFinder/pull/125) (see
  "Option A implemented" below).
- **B. Set a numeric acceptance bar for any later hybrid ranking,** checked
  with this tool on a fresh snapshot. For example: hybrid nDCG@10 at least
  keyword minus 0.02, AND at least N relevant archive-only results in hybrid
  top 10s across the 58 ideas (N for the owner to choose; today it is 5), AND
  no more than M ideas more than 0.1 below keyword.
- A and B combine: A now, B as the gate for re-enabling the archive.
- **Owner's choice (2026-11-13, project thread decision card): A + B.** Keep the
  archive out of the top 10 now (a separate ranking task), and gate its return
  on a numeric bar. The owner approved B's numbers on 2026-11-13; see the
  Option B bar below. Option A remains a separate ranking task.
- Latency is not a deciding factor yet: hybrid median is within 10 ms of the
  keyword source here. T28 sets the response-time part of D8.

### Option B bar (owner-approved 2026-11-13)

D8 B follow-up base: `931f7ffe84ba294f6f4502e839832ca207dbb6a5`, isolated
`codex/hybrid-t27-d8b-gate`, [PR #121](https://github.com/SumukhaK/open-source-projectFinder/pull/121), merged as `875f71b`. Plan: independently assess the approved bar from
committed run-3 reports/labels; RED synthetic gate/CLI tests; reuse `evaluate`
for the five checks; GREEN and full quality gates; one PR, awaiting review.
No ranking change, stack run, snapshot collection or new dependency.

The approved checks are: (1) mean hybrid nDCG@10 >= keyword minus **0.02**;
(2) at least **15** relevant archive-only idea/repository pairs in hybrid top
10s, counted only when the supplied owner file also grades them >=1;
(3) at most **3** ideas with a hybrid drop strictly greater than the existing
`FAILURE_MARGIN` (**0.1**); (4) model-only or owner-rejected pairs do not count;
(5) every frozen idea is completely judged and archive is `ok` on at least
**57 of 58**. Missing completeness/availability, a different frozen set, or
undefined quality means yields **INCONCLUSIVE** even if another check fails.

```text
python scripts/relevance_eval.py gate SNAPSHOT JUDGMENTS --owner-judgments OWNER_JUDGMENTS --out OUT.md [--depth N]
```

Exit codes: PASS 0, FAIL 1, INCONCLUSIVE 2. A mismatched owner snapshot digest
is refused with exit 2 and no new report. Depth is 10-20: a smaller pool cannot
judge a top-10 acceptance bar. The command reuses `evaluate()` and adds only the
archive-only relevant pair list to its result. Existing metrics and reports
are unchanged; no-relevant ideas remain excluded from means and are counted
in the gate report. The five-row report lists missing owner labels by frozen
idea ID/numeric repo ID only. Check 4 reports that the counting rule was applied;
it does not require labels for excluded pairs once 15 confirmed pairs exist.
The caller must supply actual owner judgments: a file name/digest is not proof
of who graded it. General metric labels still come from JUDGMENTS, so use the
owner-reconciled file. No snippet, query text, judge name or repository metadata
is copied into the report. D8's response-time bound is out of scope; T28 sets it.

**Approved numbers: implementer's review.** Agree to implement 0.02 as a policy
non-inferiority tolerance, not as demonstrated run-to-run noise. A standard-library
paired percentile bootstrap of the approved run-3 snapshot, using the committed
reconciled labels and `evaluate()`, resampled all 58 idea pairs with replacement
20,000 times (`random.Random(20261113)`), excluded undefined means inside each
replicate as the metric does, and used sorted replicates 500 and 19499 for the
95% endpoints. There are 45 scored and 13 no-relevant ideas. Mean hybrid minus
keyword is **-0.267172**, approximate 95% interval **[-0.315467, -0.216300]**,
bootstrap standard error **0.025258**. The earlier calculation from rounded
committed report scores gave [-0.315532, -0.216318], consistent with the exact
snapshot calculation. These are across-idea sampling estimates conditional on
this corpus and these mostly model labels; the purposively selected ideas are
not a random sample of users. One frozen run cannot measure temporal/provider
noise or remove label bias. No bootstrap criterion is added to the gate.

Agree with **15** as an initial, modest benefit requirement (about 0.26 confirmed
pairs per idea, three times the baseline's five model/reconciled pairs). It is
not fifteen distinct repositories or ideas; the count may cluster. Agree with
**3** as a guard against mean scores hiding large losses (3/58 = 5.17%, or
3/45 = 6.67% of today's scored ideas). All approved values are unchanged.
**Proposed, not approved:** report benefit spread and per-category regressions
before choosing category-specific floors; consider a judged-pool Recall@20
non-regression requirement and a held-out human-judged set before repeated tuning.
Also proposed, not approved: require a healthy keyword baseline, since a failed
keyword source can artificially make the relative hybrid score look better.
Small categories and thirteen undefined/no-relevant ideas make a universal
category floor premature. The existing no-relevant metric convention stays
unchanged; it must not be presented as proof of good no-match behavior. Only
50/1,097 baseline labels are human and owner/model relevant-vs-not agreement
is 80%; owner-confirmed contributions alone do not validate the overall means.

Verification (2026-11-13, Windows Python 3.11.9 / SQLite 3.45.1):
- Baseline relevance tests: 40 passed. RED: eight assertion failures on the
  missing gate command/report and mismatch diagnostic; privacy follow-up RED:
  one assertion showing an arbitrary invalid idea ID leaked into the error.
- GREEN: `python -m pytest scripts/tests/test_relevance_eval.py -q`: 59 passed,
  including PASS/FAIL/INCONCLUSIVE process exit codes, each numeric failure in
  isolation, missing and negative owner labels, exact frozen set, one/two
  archive outages, undefined means, depth bounds and sanitized validation.
- `ruff check backend scripts`, `ruff format --check backend scripts`,
  `bandit -r backend/app`, `git diff --check`: pass. Bandit emits existing
  comment-parsing warnings; no findings.
- Full final command: `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:reports/backend-coverage.json`:
  **1,332 passed / 99 skipped / 21 failed**, 137.64 s. Untouched base in a
  separate detached worktree: **1,313 passed / 99 skipped / the same 21 failed**,
  136.57 s. Failures are inherited T22 paths refusing unpatched Windows SQLite.
  No version patch, new skip, dependency or gate change. Linux CI is authoritative.
- `python scripts/quality.py coverage reports/backend-coverage.json`: exit 1
  on both trees, below the unchanged 90% combined gate; final combined/branch
  **89.47%/85.18%** on both trees. Production backend files are unchanged.

The owner supplied the private snapshot path for
one offline gate check; the snapshot was read in place, never copied or committed.
Only its verdict table is included in the PR; the report's missing-label list
stays local. No production ranking, `RANKING_VERSION`, API, migration or config
changes. Reverting this PR removes only the offline gate; existing subcommands
remain compatible. Independently reviewed by Claude and merged as `875f71b`.

### Option A implemented (2026-11-14)

The separate ranking task the owner asked for in the D8 options is
[PR #125](https://github.com/SumukhaK/open-source-projectFinder/pull/125) on base
`b3e81a7c6d1f96942cd91f759e417c37e79b79b0` (branch
`opencode/hybrid-d8a-keyword-first`), merged as `0c1752b` after independent review. `RANKING_VERSION` is now
`keyword-first-v1`: the served order is every GitHub keyword result in keyword
order, then archive-only repositories in archive rank order, tie-broken by
numeric repository ID. The archive therefore cannot push a keyword result out of
the top 10. `rrf_score` is still computed and returned exactly as before (the
mobile contract requires it) but no longer decides the order. If the keyword
source fails, is rate limited or returns nothing, the archive results are served
alone in archive order with unchanged source health; eligibility, visibility,
cursors and pagination are unchanged. This is the `keyword_then_archive` row of
the what-if table above (nDCG@10 0.695, the same as keyword-only), implemented
in the service rather than re-ranked offline. No snapshot was re-collected and no
new relevance number is claimed; archive-only results may rank above keyword
results again only through a new ranking version that passes the D8 B gate.

### Part B tool changes

- The judging sheet declares `:root { color-scheme: light dark; }`. On the
  laptop it was unreadable in a dark-themed browser (dark canvas, black text).
- `collect` no longer stores archive snippet text. The sheet and report never
  used it, and it is what kept the run-3 snapshot private.
- New `whatif` subcommand for the offline re-ranking above.
- RED: the new tests failed at import against `0b27f24` (no `refuse`/`render_whatif`;
  the colour-scheme and snippet tests target behaviour that did not exist). GREEN:
  `scripts/tests/test_relevance_eval.py` 39 passed; full suite 1,423 passed, 9
  skipped; ruff check and format clean; gitleaks clean on the branch.

## Part B runbook (laptop, WSL worker venv)

1. Bring the pilot stack up (Milvus running). `collect` always reads the ignored
   `backend/.env` and resolves its relative paths from `backend/`, exactly like
   the workers, so it finds the real catalogue and Milvus credentials from any
   directory. The keyword source uses `ARCHIVE_GITHUB_TOKEN` from that file; an
   optional `RELEVANCE_GITHUB_TOKEN` environment variable overrides it. No export
   step is needed. The token goes to GitHub only and is never written to the
   snapshot or logs. Run with `HF_HUB_OFFLINE=1`, as the scheduled jobs do.
2. `python scripts/relevance_eval.py collect --out scripts/relevance/runs/<date>-snapshot.json`
   (58 ideas with a 2.5 s pause stays under GitHub's search rate limit; the
   first real run took about 7 minutes). It first runs one unscored warm-up
   search, retried up to 3 times until the archive reports ok, so a cold model
   or Milvus cannot time out the archive on the first ideas only; the outcome is
   recorded as `versions.warmup` and the warm-up search is never stored. An
   idea whose archive source still fails is searched again, whole, up to 2
   more times; each idea's `attempts` is stored and the report header counts
   retried and still-failed ideas. Before judging, check that no idea's
   archive status is `failed`. The command prints the snapshot digest.
3. `python scripts/relevance_eval.py sheet <snapshot> --out judge.html`, open it
   in a browser, enter a role label such as "owner" as the judge name (not a
   personal name, since the file is committed), judge, and download `judgments.json`. Expect roughly 15-25
   results per idea; the page can be closed and resumed.
4. `python scripts/relevance_eval.py report <snapshot> judgments.json --out report.md`.
5. Commit the snapshot, judgments and report as evidence in a follow-up PR (all
   public repository metadata and synthetic ideas; no user data). Propose the D8
   numbers from the report for the owner's approval before T28/T29.

Rollback: Part A adds an offline script, data and tests only; it changes no
route, schema, migration or configuration. Reverting the PR removes it.

## Known limits

- The pilot archive holds about 204 repositories, so archive-only and hybrid
  coverage is far smaller than GitHub's. The report must say so next to any
  comparison, and D8 thresholds should be read against that coverage.
- One judge; "unsure" marks record uncertainty. A second judge is optional.
- Live GitHub results drift; the snapshot, not a rerun, is the frozen baseline.
