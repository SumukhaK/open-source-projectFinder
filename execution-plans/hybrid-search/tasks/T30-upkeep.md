# T30: Upkeep — apply deferred improvements in one pass

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t30-upkeep` (one branch per slice, see below) |
| Prerequisites, merged into main | [T29](T29-rollout-readiness.md) — that is, the whole T00-T29 list |
| Intended scope | the backlog items below; nothing else |

Owner request (2026-10-30): collect the non-blocking review notes that could improve the system into one upkeep task, add to it as each task is accepted, and take it up after the whole task list is implemented so the system improves in one pass.

Read first: this backlog, the linked review of each item, the current code it names and the merged evidence of the task that introduced it. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md) and [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Code may have moved since a note was written; re-verify every item against current main before changing anything, and drop items that are already fixed (record that).

## How this backlog grows

At each post-merge tracker sync, the reviewer adds that task's non-blocking review notes here **unless** a named later task owns them; owned notes go into that task's RED list/acceptance criteria instead and are listed under "Verify closed" below so nothing is lost. Each entry names its source PR/review, the problem, and the intended change. Remove nothing from this list until T30 records it as fixed, already fixed, or deliberately declined with a reason.

## Backlog — improvements owned by T30

| ID | Source | Note | Intended change |
| --- | --- | --- | --- |
| U1 | T07, [PR #28](https://github.com/SumukhaK/open-source-projectFinder/pull/28) | Milvus adapter's chunk-ordinal upper bound is a hard-coded literal | Derive it from `ARCHIVE_MAX_CHUNKS - 1` |
| U2 | T07, [PR #28](https://github.com/SumukhaK/open-source-projectFinder/pull/28) | Vector dimension 384 is hard-coded in the adapter | Read it from the embedding manifest's `dimensions` |
| U3 | T07, [PR #28](https://github.com/SumukhaK/open-source-projectFinder/pull/28) | `close()` does not guard a client that was never created | Make `close()` a safe no-op when the client is `None` |
| U4 | T05, [PR #20](https://github.com/SumukhaK/open-source-projectFinder/pull/20) | README chunking drops a whole paragraph that contains inline HTML | Keep the surrounding text. Changes prepared output: bump `CHUNKER_VERSION` and plan the re-ingest through T19's refresh; separate slice |
| U5 | T09, [PR #34](https://github.com/SumukhaK/open-source-projectFinder/pull/34) | Milvus snippets are cut at 2,048 bytes, possibly mid-word | Truncate on a word/character boundary and confirm the app labels snippets as excerpts (if T15/T25 have not already) |
| U6 | T09, [PR #34](https://github.com/SumukhaK/open-source-projectFinder/pull/34) | Worker preflight (`ensure_collection`) creates the Milvus collection on first run | Split creation into an explicit operator init step so a misconfigured run cannot silently create an empty collection |
| U7 | T11, [PR #38](https://github.com/SumukhaK/open-source-projectFinder/pull/38) | A GitHub 422 (rejected query) is reported as `failed`/`unavailable`; owner accepted this for now | If real logs show 422s, report a distinct `query_rejected` reason |
| U8 | T09, [PR #34](https://github.com/SumukhaK/open-source-projectFinder/pull/34) | Operator: the worker token sits in two ignored `.env` files (main checkout and T09 worktree) | Keep one private copy; document its location in the operator runbook. No secret values in the repository |
| U9 | T04, [PR #19](https://github.com/SumukhaK/open-source-projectFinder/pull/19) | Compressed-response burst bound is documented, not measured | Measure peak memory during T18/T19 runs; tighten only if pressure is observed |

## Verify closed — notes owned by other tasks

T30 does not implement these; it confirms each was closed by its owner (link the PR) or reopens it as a finding.

| Source | Owner | Requirement |
| --- | --- | --- |
| T02, [PR #16](https://github.com/SumukhaK/open-source-projectFinder/pull/16) | T13 | Input faults (`UnsupportedInput`, e.g. an idea starting with `query:`) degrade the archive source instead of failing the request |
| T10, [PR #32](https://github.com/SumukhaK/open-source-projectFinder/pull/32) | T19 | Refresh catalogue scalar metadata including `pushed_at` |
| T10, [PR #32](https://github.com/SumukhaK/open-source-projectFinder/pull/32) | T19/T20 | Explicit re-check path for sticky suppressions |
| T11, [PR #38](https://github.com/SumukhaK/open-source-projectFinder/pull/38) | T12/T13 | One typed licence filter mapped to GitHub keyword and SPDX ID (T12 part done in PR #42) |
| T12, [PR #42](https://github.com/SumukhaK/open-source-projectFinder/pull/42) | T13 | `license_conflict` cards show the live licence and drop the archive snippet; `archive_status` from the real outcome |
| T16, [PR #24](https://github.com/SumukhaK/open-source-projectFinder/pull/24) | T18 | First real run logs per-partition query, `total_count`, `incomplete_results`, pages, IDs and split decision |
| T17, [PR #40](https://github.com/SumukhaK/open-source-projectFinder/pull/40) | T19 | Safe generation protocol for README reverts (A→B→A) with a regression test |
| T17, [PR #40](https://github.com/SumukhaK/open-source-projectFinder/pull/40) | T20 | Run-row compaction preserves `MAX(fence)` |
| Operations | Owner | P1 worker-token rotation/revocation ownership confirmed; deepmerge audit exception (expires 2026-12-31) rechecked or removed |

## Work and boundaries

Split the backlog into small reviewable slices, each its own branch and PR (for example: adapter nits U1-U3; snippet/collection handling U5-U6; chunker change U4 alone because it changes prepared revisions). Each slice follows the normal TDD, review and merge rules. No new features, dependencies or gate changes beyond what an item states.

## Tests and verification before acceptance

RED for each behavioural item (U1-U7), showing the current defect; GREEN plus the full suite, coverage gate, ruff, bandit and `git diff --check`. U4 additionally needs a chunker-version fixture and a re-ingest/refresh dry run. U8-U9 are documentation/measurement items with recorded evidence.

## What counts as acceptable

Every backlog row and every "Verify closed" row is marked fixed (with PR), already fixed (with evidence) or declined (with the owner's reason). No regression in the existing suites; no reduction of coverage, security or CI gates.

An independent trusted reviewer must accept the exact current PR head of each slice after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md).

## Do not do

Do not start T30 before T29 merges, fold unrelated refactors into it, or treat a "Verify closed" row as T30's implementation work. Do not persist user ideas, weaken validation, add security exceptions or install paid services.
