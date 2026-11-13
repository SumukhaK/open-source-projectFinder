# T27 Evidence — human-judged relevance evaluation

Base: `origin/main` `ff9d6b72dd1146739c5c30277c43fffa9fda556a` (work started on `40546ba`; T26 merged as `6315e23`, [PR #111](https://github.com/SumukhaK/open-source-projectFinder/pull/111)).
Prerequisite verified merged into main: T26 `6315e23`. D8 method approved 2026-10-29; its numbers are set from this task's baseline.

T27 has two parts. **Part A** (this PR) is the frozen query set, the offline
evaluation tool and its tests. **Part B** needs the real stack and the owner:
freeze a real snapshot on the laptop, the owner judges it blind, and the report
and the proposed D8 numbers are added in a follow-up PR. T27 is not done until
Part B is reviewed; nothing here claims a real relevance result.

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
