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
| U1 | T07, [PR #28](https://github.com/SumukhaK/open-source-projectFinder/pull/28) | Milvus adapter's chunk-ordinal upper bound is a hard-coded literal | Derive it from `ARCHIVE_MAX_CHUNKS - 1`; **fixed in PR #90, awaiting review** |
| U2 | T07, [PR #28](https://github.com/SumukhaK/open-source-projectFinder/pull/28) | Vector dimension 384 is hard-coded in the adapter | Read it from the embedding manifest's `dimensions`; **fixed in PR #90, awaiting review** |
| U3 | T07, [PR #28](https://github.com/SumukhaK/open-source-projectFinder/pull/28) | `close()` does not guard a client that was never created | Make `close()` a safe no-op when the client is `None`; **fixed in PR #90, awaiting review** |
| U4 | T05, [PR #20](https://github.com/SumukhaK/open-source-projectFinder/pull/20) | README chunking drops a whole paragraph that contains inline HTML | Keep the surrounding text. Changes prepared output: bump `CHUNKER_VERSION` and plan the re-ingest through T19's refresh; separate slice |
| U5 | T09, [PR #34](https://github.com/SumukhaK/open-source-projectFinder/pull/34) | Milvus snippets are cut at 2,048 bytes, possibly mid-word | Truncate on a word/character boundary and confirm the app labels snippets as excerpts (if T15/T25 have not already) Since 2026-11-05: land this before voice V2 if the grounded summary quotes snippets, so the LLM never receives a mid-word cut. |
| U6 | T09, [PR #34](https://github.com/SumukhaK/open-source-projectFinder/pull/34) | Worker preflight (`ensure_collection`) creates the Milvus collection on first run | Split creation into an explicit operator init step so a misconfigured run cannot silently create an empty collection |
| U7 | T11, [PR #38](https://github.com/SumukhaK/open-source-projectFinder/pull/38) | A GitHub 422 (rejected query) is reported as `failed`/`unavailable`; owner accepted this for now | If real logs show 422s, report a distinct `query_rejected` reason |
| U8 | T09, [PR #34](https://github.com/SumukhaK/open-source-projectFinder/pull/34) | Operator: the worker token sits in two ignored `.env` files (main checkout and T09 worktree) | Keep one private copy; document its location in the operator runbook. No secret values in the repository |
| U9 | T04, [PR #19](https://github.com/SumukhaK/open-source-projectFinder/pull/19) | Compressed-response burst bound is documented, not measured | Measure peak memory during T18/T19 runs; tighten only if pressure is observed |
| U10 | T14, [PR #49](https://github.com/SumukhaK/open-source-projectFinder/pull/49) | One key both signs cursors and computes the HMAC idea/filter digests | Add domain separation (for example, prefix digest input with `b"digest:"`) or derive two subkeys; invalidates live cursors, which is acceptable after a restart; **fixed in PR #85, merged as `14a82b6`** |
| U11 | T15, [PR #51](https://github.com/SumukhaK/open-source-projectFinder/pull/51) | Requests that arrive while the lazy hybrid build runs each hold a `to_thread` worker blocked on the build lock until the build ends (the route itself returns a retryable 503 after `HYBRID_BUILD_WAIT_SECONDS`) | Let waiters check a build-in-progress flag and return immediately instead of queueing on the lock, so a slow build cannot drain the default thread pool |
| U12 | T15, [PR #51](https://github.com/SumukhaK/open-source-projectFinder/pull/51) | Later-page live rechecks in `FusedRevalidator` reuse the worker-only `ARCHIVE_GITHUB_TOKEN` (documented in T15 evidence) | Give the API its own read-only public-metadata token, or a separate reader instance with its own budget, so serving traffic cannot spend the worker's rate limit |
| ~~U13~~ (closed by T24, [PR #55](https://github.com/SumukhaK/open-source-projectFinder/pull/55)) | P2, [PR #53](https://github.com/SumukhaK/open-source-projectFinder/pull/53) | The mobile discovery screen's cache restore on mount is not guarded by the search sequence ref; a search submitted before the AsyncStorage read finishes could be replaced by the cached page (millisecond window) | Bump/check `listSeq` in the cache-restore effect and skip `setResults` if a search started; fold into T24 if it touches this screen |
| ~~U14~~ (closed by [PR #57](https://github.com/SumukhaK/open-source-projectFinder/pull/57), merged as `3504014`) | T15/T24, [PR #55](https://github.com/SumukhaK/open-source-projectFinder/pull/55) | `HybridRuntime._build` raises `HybridUnavailable` when Milvus, the E5 model or the archive reader is unavailable, so the whole v1 route (and therefore all mobile search) returns 503, losing the live GitHub half too; query-time archive failures already degrade to live-only | Build a live-only target when archive components fail (archive source reported `failed`/`degraded`), keep the typed 503 only for a missing signing key; do this before T26 if mobile search must work during archive outages |
| U15 | T25, [PR #58](https://github.com/SumukhaK/open-source-projectFinder/pull/58) | T25's GREEN criterion asks for a real mobile-sized light/dark UI inspection of the notices, Try again button, refresh control, focus/labels and touch targets; it was not performed because sign-in needs a live backend and OAuth | Do the inspection during T26's real-HTTP run on a phone-sized device or simulator, in both themes, and record screenshots or findings Voice UI (V1, V3) carries its own device inspection in the voice plan, so U15 covers only the T25 screen. |
| U16 | V1b/V2b/V3b, [PR #76](https://github.com/SumukhaK/open-source-projectFinder/pull/76), [#78](https://github.com/SumukhaK/open-source-projectFinder/pull/78) | Voice device acceptance never ran on a physical phone; the emulator retries could not drive hold-to-talk and lacked RAM for Ollama (see V1b/V2b/V3b evidence) | Owner decision 2026-11-10: the owner runs this manually on a real phone once the app is complete end to end. Checklist: consent/deny/settings; hold/speak/release, slide cancel, 30 s cap, background cancel, release-to-transcript latency (3 clips); summary card after the list; auto-speak after voice search, first-sound latency (3 runs), one-time tip, typed search Read aloud/Stop, mic press stops speech, setting off, silent mode, TalkBack suppression and announcement; stops on new search/tab/sign-out/background; Ollama stopped -> card hidden; light/dark. Record results in V1b/V2b/V3b evidence and flip their TRACKER rows to device check done. |
| U17 | T18 Phase B, [PR #81](https://github.com/SumukhaK/open-source-projectFinder/pull/81) | A refused early restart (`WriterBusy`, a live lease) falls through `_safe_error` in `backend/app/workers/archive.py` and prints "Archive storage failed; check private paths, free disk and WAL-fixed SQLite". Behaviour is safe (exit 1, zero requests) but the message misleads | Map `WriterBusy` to its own message saying another worker holds the lease and when it expires; add a test. |
| U18 | T18 Phase B, [PR #81](https://github.com/SumukhaK/open-source-projectFinder/pull/81) | The WSL VM sat at its 6 GB `.wslconfig` cap and stopped once mid-run with low host RAM; an earlier `HCS/ERROR_NO_SYSTEM_RESOURCES` needed a full Windows Restart (not Shut down, because of Fast Startup) | Document the operator preflight for real runs in backend/README (close heavy apps, check host free RAM, Restart if WSL will not start) and decide whether the worker can lower peak memory (e.g. smaller embedding batches) before the 10k pilot. |
| ~~U19~~ (closed by T19b, [PR #87](https://github.com/SumukhaK/open-source-projectFinder/pull/87)) | T19a, [PR #83](https://github.com/SumukhaK/open-source-projectFinder/pull/83) | `_stage` checks `with_generation(prepared, generation).chunks == prepared.chunks`, but generation 1 returns the input unchanged, so a salted payload staged against a generation-1 row would pass | Compare against chunk IDs recomputed from ordinal/text hash for every generation (including the unsalted generation-1 form) and add a test. Owner prompt 2026-11-10 folds this into T19b; close it here when T19b merges. |

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
| T14, [PR #49](https://github.com/SumukhaK/open-source-projectFinder/pull/49) | T15 | Inject T10's fresh visibility check as the required `HybridPager` revalidator and call `next_page` off the event loop (closed by T15, [PR #51](https://github.com/SumukhaK/open-source-projectFinder/pull/51)) |
| T18 Phase A, [PR #47](https://github.com/SumukhaK/open-source-projectFinder/pull/47) | T18 Phase B | Watch `skipped.forbidden` in the real run; a broad 403 skips repositories instead of stopping, so add a consecutive-forbidden stop if it appears |
| Operations | Owner | P1 worker-token rotation/revocation ownership confirmed; deepmerge audit exception (expires 2026-12-31) and glob/minimatch exceptions (expire 2026-11-30) rechecked or removed |

## Work and boundaries

Split the backlog into small reviewable slices, each its own branch and PR (for example: adapter nits U1-U3; snippet/collection handling U5-U6; chunker change U4 alone because it changes prepared revisions). Each slice follows the normal TDD, review and merge rules. No new features, dependencies or gate changes beyond what an item states.

## Tests and verification before acceptance

RED for each behavioural item (U1-U7), showing the current defect; GREEN plus the full suite, coverage gate, ruff, bandit and `git diff --check`. U4 additionally needs a chunker-version fixture and a re-ingest/refresh dry run. U8-U9 are documentation/measurement items with recorded evidence.

## What counts as acceptable

Every backlog row and every "Verify closed" row is marked fixed (with PR), already fixed (with evidence) or declined (with the owner's reason). No regression in the existing suites; no reduction of coverage, security or CI gates.

An independent trusted reviewer must accept the exact current PR head of each slice after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md).

## Do not do

Do not start T30 before T29 merges, fold unrelated refactors into it, or treat a "Verify closed" row as T30's implementation work. Do not persist user ideas, weaken validation, add security exceptions or install paid services.

## U1-U3 execution — 2026-11-11

Owner-authorized early slice before T29. Base main:
`18b8632a137ce27079bb06869117a4c87ae1a7d9`.
Branch: `codex/hybrid-t30-u1-u3-milvus-nits`, isolated worktree.
Reverified all three on main: literal ordinal 7; dimension 384 in schema,
input validation and readiness; unguarded client close. None already fixed.
Plan: RED for changed chunk bound, manifest dimension and absent client; minimum
adapter-only fixes; focused and full fake-only quality checks; one PR then stop.
Keep pinned generation, collection, index and field names unchanged. No changes
to worker/publication/content/index files or other T30 items.

### U1-U3 verification and compatibility

2026-11-11, Windows Python 3.11.9 / SQLite 3.45.1. Existing interpreter:
`E:/OpenSourceProjectFinder/backend/.venv/Scripts/python.exe` (`python` below),
`PYTHONPATH=backend`. The owner's explicit file scope takes precedence over the
usual root tracker update: this plan/evidence stays in T30 and hybrid TRACKER.

Original [PR #28 review](https://github.com/SumukhaK/open-source-projectFinder/pull/28#pullrequestreview-5665207748)
and [re-review](https://github.com/SumukhaK/open-source-projectFinder/pull/28#pullrequestreview-5665285392)
confirm these three nits were deferred. T07 merged as
`21e6db3260e7e6368afd5d5bbfd54387b71fa4f8`; [T07 evidence](../T07_EVIDENCE.md)
was read. All three are fixed here, none skipped as already fixed.

- Baseline: `python -m pytest backend/tests/test_milvus.py -q` -> 74 passed.
- RED before adapter edits:
  `python -m pytest backend/tests/test_milvus.py -q -k "follows_archive or follows_manifest or follow_manifest or without_a_client or fingerprint"`
  -> 7 failed, 1 passed, 74 deselected. U1: a cap of 4 allowed ordinal 4,
  a cap of 10 refused ordinal 9. U2: a test-pinned 3-dimensional manifest still
  produced a 384-dimensional schema and refused vectors on upsert/search/ready.
  U3: closing an adapter without a client raised AttributeError. The original
  generation fingerprint test passed before and after the fix.
- GREEN: `python -m pytest backend/tests/test_milvus.py -q` -> 82 passed.
  Wrong-length inputs still fail; wrong-length read-back returns false. Existing
  manifest pinning, index/field/schema checks and connected-client close pass.
- `python -m ruff check backend scripts` -> passed.
- `python -m ruff format --check backend scripts` -> passed, 78 files.
- `python -m bandit -r backend/app -q` -> passed, no findings.
- `git diff --check` -> passed.

Only the adapter and its tests change behavior. `ARCHIVE_MAX_CHUNKS` remains 8,
the production manifest remains 384-dimensional, and the generation fingerprint
remains `df9cf05b1daae6801246d15bd9655a33b91241a686acc5cdef8e95a9a901ad7c`.
Collection/index/field names and settings are untouched. The alternate manifest
is test-only; arbitrary production manifests are still rejected. No migration,
re-ingestion or collection rebuild is needed. Rollback is a code revert; preserve
all collections and volumes. No dependencies, configuration or gates changed.

Fakes only. No Docker, server, WSL, model, application provider calls or app closure.
Real CPU/GPU integration and Linux-only catalogue behavior are not claimed locally.
This is not a model migration or acceptance of another upkeep item.

Full regression (2026-11-11):
`python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:reports/backend-coverage.json`
-> **1120 passed, 67 skipped**, exit 0, 90.21 s; one existing Starlette/httpx
warning. `python scripts/quality.py coverage reports/backend-coverage.json` ->
**92.5% combined / 89.4% branches**, exit 0, unchanged gate passed. Skips include
platform/runtime restrictions and opt-in integration tests; Linux/real-server
checks were not run locally, as required by this fake-only slice.
