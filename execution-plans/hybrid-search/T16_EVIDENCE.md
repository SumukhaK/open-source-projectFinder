# T16 partitioned rolling-year discovery evidence - 2026-10-27

Status: **Awaiting review** in [PR #24](https://github.com/SumukhaK/open-source-projectFinder/pull/24). This implements only [T16](tasks/T16-discovery-partitions.md): a pure planner with no HTTP calls, persistence, worker or scheduler.

## Authorship

- The initial planner and 20 tests were written by an OpenCode/DeepSeek session (commit `8eaaa1b`). That session ran out of quota before its verification gates, so the owner pushed the uncommitted work.
- The owner then handed T16 to Claude Code to finish, review and merge. Claude Code made the corrections in `e52d5fe` (described below), merged main (`d7b9ccf`), and wrote this evidence.
- The final review is therefore by a partial author, at the owner's explicit direction.

## Scope and prerequisites

- **Branch:** `codex/hybrid-t16-discovery-partitions`, created from `origin/main` at `c73c457b937fd6038f33dbbeb59c54a43c97374c`. Main `d7b9ccf` (the T06 docs sync) was merged in with a merge commit.
- **Prerequisite:** [T04](tasks/T04-archive-http.md) / PR #19 merged as `d2354e9`. No policy decision gates T16. The planner never contacts GitHub; D1 (corpus cap) and P1 (worker credential) gate T18, not this task.
- **Files:** one production file, `backend/app/services/archive_partitions.py`, and its tests, `backend/tests/test_archive_partitions.py`.
- **Not changed:** dependencies, configuration, schema, API, CI, gates, exceptions, mobile or unrelated work.

## Contract

| Rule | Implemented behavior |
| --- | --- |
| Root window | `plan_root(run_at)` returns the inclusive UTC interval `[run - 365 days, run]` at whole-second precision. Naive datetimes are rejected. |
| Split trigger | `needs_split` is true when `reported_count > 750` (`SPLIT_THRESHOLD`, below the 1,000-result cap) or `incomplete_results` is true. This includes incomplete empty pages. |
| Split ladder | **Pushed time:** halved while the span is wider than `MIN_PUSHED_SPAN` (1 hour).<br>**Created time:** from 2008-01-01 up to `pushed_to`, halved while wider than `MIN_CREATED_SPAN` (1 day).<br>**Stars:** 12 disjoint bands, then halving of a band; the open-ended band splits by doubling. |
| Boundaries | Time splits share the midpoint second; the inclusive overlap is resolved by `dedupe_repository_ids`, which keeps first-seen order. Star splits are disjoint integers with no gap. |
| Bounds | `MAX_SPLIT_DEPTH = 32` per path. From the root, a persistently dense bucket takes 14 pushed splits, 13 created splits and then star splits, and stops at depth 28 with `indivisible`. A path that still needs splits at the bound stops with `max_depth`. |
| Retries | None. The planner makes no requests. T17/T18 own retry attempts and quota. |
| Serialization | `DiscoveryPartition.as_record`/`from_record` round-trip every bound, plus a stable SHA-256 `key`, the `parent_key` and the derived `query`. A tampered key or query is rejected. `PartitionSplit.as_record` records the parent, the children (each with `parent_key`), the reason, the cap, the threshold and the depth bound. |
| Selection cap | `DiscoverySelection(cap, selected, unresolved, deferred)` serializes and round-trips. Coverage is `curated` (cap reached or deferred partitions), `partial` (unresolved partitions) or `partitioned`. It is never `complete`, because GitHub's index moves while pages are read. |
| Query | `is:public archived:false pushed:<from>..<to>`, plus optional `created:` and `stars:` (exact, range or `>=`). There is no keyword term and no language qualifier, so no language is silently omitted. Forks are excluded by GitHub's default. Queries are bounded to 256 characters; the deepest generated query is 133. |

## Official qualifier sources (checked 2026-10-27)

- [Understanding the search syntax](https://docs.github.com/en/search-github/getting-started-with-searching-on-github/understanding-the-search-syntax) documents `YYYY-MM-DD..YYYY-MM-DD` ranges and optional time; its example `created:2016-03-21T14:11:00Z..2016-04-07T20:45:00Z` uses the `…Z` form this planner emits.
- [Searching for repositories](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories) documents `pushed:` and `created:` with ISO-8601 dates and optional time, `stars:` ranges and `archived:false`. It states: "To include forks in the search results, you will need to add fork:true or fork:only to your query."
- [REST search](https://docs.github.com/en/rest/search/search) documents the 1,000-result cap and `incomplete_results`.
- No live GitHub spike was run, because no worker credential (P1) exists.

## Verification

Runtime: Linux, CPython 3.11.17 / SQLite 3.53.1 (the CI runtime), 2026-10-27.

| Stage | Command / actual result |
| --- | --- |
| Initial RED (DeepSeek, Windows, reported) | 20 failed against a `NotImplementedError` stub; the log stayed on the operator laptop (`reports/t16/red.log`) and was not reproduced here |
| Initial GREEN at `8eaaa1b` | `pytest backend/tests scripts/tests --cov=backend/app --cov-branch`: **516 passed**, module 100%. Ruff, Bandit and `git diff --check` clean. |
| Finding | A probe from `plan_root` with persistently dense counts split **only by pushed time** for 8 levels and stopped at a 1.4-day bucket with `max_depth`. The created/star fallbacks were reachable only from hand-built zero-width partitions. There were also no partition keys or parent links, and no selection-cap record. |
| Follow-up RED | `pytest backend/tests/test_archive_partitions.py`, with constants and a `DiscoverySelection` stub: **6 failed / 28 passed**. Failures: the ladder showed pushed splits only; a 1-hour bucket did not use created time; `key` was missing; a tampered key was accepted; selection raised `NotImplementedError` (2 tests). |
| Follow-up GREEN | The same command: **35 passed**. A probe from the root now gives 14 pushed, 13 created and 1 star split, then `indivisible` at depth 28. |
| Full regression | `pytest backend/tests scripts/tests --cov=backend/app --cov-branch`: **524 passed**, 0 skipped; `archive_partitions.py` 100% lines and branches; `scripts/quality.py coverage`: **97.6% combined / 96.3% branches** against the unchanged gate. |
| Lint / format / security | `ruff check backend scripts`, `ruff format --check backend scripts`, `bandit -r backend/app` and `git diff --check`: all clean. |

## Limits and rollback

- **Partitions are a plan, not a snapshot.** Overlap plus deduplication prevents lost boundaries, but moving pages can still miss or reorder repositories. Coverage records say so.
- **Limits are per path.** The planner has no global partition budget, so the T17/T18 runner must apply the pilot cap (D1) and the search quota, and record deferred partitions with `DiscoverySelection`.
- **Rollback:** revert the PR. Nothing persists or calls this module yet.
