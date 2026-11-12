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
| ~~U1~~ (closed by [PR #90](https://github.com/SumukhaK/open-source-projectFinder/pull/90), merged as `f4983e7`) | T07, [PR #28](https://github.com/SumukhaK/open-source-projectFinder/pull/28) | Milvus adapter's chunk-ordinal upper bound is a hard-coded literal | Derive it from `ARCHIVE_MAX_CHUNKS - 1`; **fixed in PR #90, merged as `f4983e7`** |
| ~~U2~~ (closed by [PR #90](https://github.com/SumukhaK/open-source-projectFinder/pull/90), merged as `f4983e7`) | T07, [PR #28](https://github.com/SumukhaK/open-source-projectFinder/pull/28) | Vector dimension 384 is hard-coded in the adapter | Read it from the embedding manifest's `dimensions`; **fixed in PR #90, merged as `f4983e7`** |
| ~~U3~~ (closed by [PR #90](https://github.com/SumukhaK/open-source-projectFinder/pull/90), merged as `f4983e7`) | T07, [PR #28](https://github.com/SumukhaK/open-source-projectFinder/pull/28) | `close()` does not guard a client that was never created | Make `close()` a safe no-op when the client is `None`; **fixed in PR #90, merged as `f4983e7`** |
| U4 | T05, [PR #20](https://github.com/SumukhaK/open-source-projectFinder/pull/20) | README chunking drops a whole paragraph that contains inline HTML | Keep the surrounding text. Changes prepared output: bump `CHUNKER_VERSION` and plan the re-ingest through T19's refresh; separate slice |
| ~~U5~~ (closed by [PR #100](https://github.com/SumukhaK/open-source-projectFinder/pull/100), merged as `69e9cab`) | T09, [PR #34](https://github.com/SumukhaK/open-source-projectFinder/pull/34) | Milvus snippets are cut at 2,048 bytes, possibly mid-word | Truncate on a word/character boundary and confirm the app labels snippets as excerpts (if T15/T25 have not already) Since 2026-11-05: land this before voice V2 if the grounded summary quotes snippets, so the LLM never receives a mid-word cut. **fixed in PR #100, merged as `69e9cab`**: cut at serving time on a word boundary with `…`; cards are labelled "README excerpt"; the summary receives only `full_names`, so no snippet reaches the LLM |
| ~~U6~~ (closed by [PR #101](https://github.com/SumukhaK/open-source-projectFinder/pull/101), merged as `85ee3cb`) | T09, [PR #34](https://github.com/SumukhaK/open-source-projectFinder/pull/34) | Worker preflight (`ensure_collection`) creates the Milvus collection on first run | Split creation into an explicit operator init step so a misconfigured run cannot silently create an empty collection; **fixed in PR #101, merged as `85ee3cb`**: preflight calls `verify_collection()`, creation only through `python -m app.workers.archive init-collection` |
| U7 | T11, [PR #38](https://github.com/SumukhaK/open-source-projectFinder/pull/38) | A GitHub 422 (rejected query) is reported as `failed`/`unavailable`; owner accepted this for now | If real logs show 422s, report a distinct `query_rejected` reason |
| U8 | T09, [PR #34](https://github.com/SumukhaK/open-source-projectFinder/pull/34) | Operator: the worker token sits in two ignored `.env` files (main checkout and T09 worktree) | Keep one private copy; document its location in the operator runbook. No secret values in the repository |
| U9 | T04, [PR #19](https://github.com/SumukhaK/open-source-projectFinder/pull/19) | Compressed-response burst bound is documented, not measured | Measure peak memory during T18/T19 runs; tighten only if pressure is observed |
| U10 | T14, [PR #49](https://github.com/SumukhaK/open-source-projectFinder/pull/49) | One key both signs cursors and computes the HMAC idea/filter digests | Add domain separation (for example, prefix digest input with `b"digest:"`) or derive two subkeys; invalidates live cursors, which is acceptable after a restart; **fixed in PR #85, merged as `14a82b6`** |
| ~~U11~~ (closed by [PR #93](https://github.com/SumukhaK/open-source-projectFinder/pull/93), merged as `b0a1981`) | T15, [PR #51](https://github.com/SumukhaK/open-source-projectFinder/pull/51) | Requests that arrive while the lazy hybrid build runs each hold a `to_thread` worker blocked on the build lock until the build ends (the route itself returns a retryable 503 after `HYBRID_BUILD_WAIT_SECONDS`) | Let waiters check a build-in-progress flag and return immediately instead of queueing on the lock, so a slow build cannot drain the default thread pool; **fixed in PR #93, merged as `b0a1981`** |
| U12 | T15, [PR #51](https://github.com/SumukhaK/open-source-projectFinder/pull/51) | Later-page live rechecks in `FusedRevalidator` reuse the worker-only `ARCHIVE_GITHUB_TOKEN` (documented in T15 evidence) | Give the API its own read-only public-metadata token, or a separate reader instance with its own budget, so serving traffic cannot spend the worker's rate limit |
| ~~U13~~ (closed by T24, [PR #55](https://github.com/SumukhaK/open-source-projectFinder/pull/55)) | P2, [PR #53](https://github.com/SumukhaK/open-source-projectFinder/pull/53) | The mobile discovery screen's cache restore on mount is not guarded by the search sequence ref; a search submitted before the AsyncStorage read finishes could be replaced by the cached page (millisecond window) | Bump/check `listSeq` in the cache-restore effect and skip `setResults` if a search started; fold into T24 if it touches this screen |
| ~~U14~~ (closed by [PR #57](https://github.com/SumukhaK/open-source-projectFinder/pull/57), merged as `3504014`) | T15/T24, [PR #55](https://github.com/SumukhaK/open-source-projectFinder/pull/55) | `HybridRuntime._build` raises `HybridUnavailable` when Milvus, the E5 model or the archive reader is unavailable, so the whole v1 route (and therefore all mobile search) returns 503, losing the live GitHub half too; query-time archive failures already degrade to live-only | Build a live-only target when archive components fail (archive source reported `failed`/`degraded`), keep the typed 503 only for a missing signing key; do this before T26 if mobile search must work during archive outages |
| U15 | T25, [PR #58](https://github.com/SumukhaK/open-source-projectFinder/pull/58) | T25's GREEN criterion asks for a real mobile-sized light/dark UI inspection of the notices, Try again button, refresh control, focus/labels and touch targets; it was not performed because sign-in needs a live backend and OAuth | Do the inspection during T26's real-HTTP run on a phone-sized device or simulator, in both themes, and record screenshots or findings Voice UI (V1, V3) carries its own device inspection in the voice plan, so U15 covers only the T25 screen. |
| U16 | V1b/V2b/V3b, [PR #76](https://github.com/SumukhaK/open-source-projectFinder/pull/76), [#78](https://github.com/SumukhaK/open-source-projectFinder/pull/78) | Voice device acceptance never ran on a physical phone; the emulator retries could not drive hold-to-talk and lacked RAM for Ollama (see V1b/V2b/V3b evidence) | Owner decision 2026-11-10: the owner runs this manually on a real phone once the app is complete end to end. Checklist: consent/deny/settings; hold/speak/release, slide cancel, 30 s cap, background cancel, release-to-transcript latency (3 clips); summary card after the list; auto-speak after voice search, first-sound latency (3 runs), one-time tip, typed search Read aloud/Stop, mic press stops speech, setting off, silent mode, TalkBack suppression and announcement; stops on new search/tab/sign-out/background; Ollama stopped -> card hidden; light/dark. Record results in V1b/V2b/V3b evidence and flip their TRACKER rows to device check done. |
| U17 | T18 Phase B, [PR #81](https://github.com/SumukhaK/open-source-projectFinder/pull/81) | A refused early restart (`WriterBusy`, a live lease) falls through `_safe_error` in `backend/app/workers/archive.py` and prints "Archive storage failed; check private paths, free disk and WAL-fixed SQLite". Behaviour is safe (exit 1, zero requests) but the message misleads | Map `WriterBusy` to its own message saying another worker holds the lease and when it expires; add a test. |
| U18 | T18 Phase B, [PR #81](https://github.com/SumukhaK/open-source-projectFinder/pull/81) | The WSL VM sat at its 6 GB `.wslconfig` cap and stopped once mid-run with low host RAM; an earlier `HCS/ERROR_NO_SYSTEM_RESOURCES` needed a full Windows Restart (not Shut down, because of Fast Startup) | Document the operator preflight for real runs in backend/README (close heavy apps, check host free RAM, Restart if WSL will not start) and decide whether the worker can lower peak memory (e.g. smaller embedding batches) before the 10k pilot. |
| ~~U19~~ (closed by T19b, [PR #87](https://github.com/SumukhaK/open-source-projectFinder/pull/87)) | T19a, [PR #83](https://github.com/SumukhaK/open-source-projectFinder/pull/83) | `_stage` checks `with_generation(prepared, generation).chunks == prepared.chunks`, but generation 1 returns the input unchanged, so a salted payload staged against a generation-1 row would pass | Compare against chunk IDs recomputed from ordinal/text hash for every generation (including the unsalted generation-1 form) and add a test. Owner prompt 2026-11-10 folds this into T19b; close it here when T19b merges. |
| U20 | T22, [PR #102](https://github.com/SumukhaK/open-source-projectFinder/pull/102) | After `restore --activate` the restored catalogue's `archive_runs` and cleanup tombstones are from the backup era, so `MAX(fence)` and each repository's generation high-water mark can go backwards. Safe today: activation holds the writer and OS locks, deletes orphan vectors and reads every rebuilt vector back | Before the swap, carry the live `MAX(fence)` and each repository's `MAX(generation)` tombstone into the restored catalogue; add a regression test |

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

## U11 execution — 2026-11-11

Owner-authorized early slice. Base `434fa8ce6ae19ede7bd340e3e62d4fc1b2b6fa8b`;
U10 `14a82b6` and U1-U3 `f4983e7` verified as merged ancestors.
Branch `codex/hybrid-t30-u11-build-waiters` in an isolated worktree.
Reverified cold-start waiters block on the build lock; U14 fallback already uses
non-blocking acquisition. Plan: event-controlled RED for pool/HTTP waiters,
non-blocking acquisition with existing starting response, retry/cleanup/U14
regressions, full fake-only gates, one PR and stop. Per the owner's file scope,
plan/evidence stay here and in hybrid TRACKER; no root tracker or worker edits.

### U11 verification and compatibility

2026-11-11, Windows Python 3.11.9 / SQLite 3.45.1. Commands use the existing
`E:/OpenSourceProjectFinder/backend/.venv/Scripts/python.exe` (`python` below),
with `PYTHONPATH=backend`. Read [T15 evidence](../T15_EVIDENCE.md), PR #51's
review-fix record in its body (GitHub returned no formal reviews), and PR #57's
U14 fallback/backoff changes. No already-fixed item was skipped.

- Baseline: `python -m pytest backend/tests/test_hybrid_runtime.py backend/tests/test_archive_api.py -q`
  -> 50 passed.
- RED before runtime edits: same command with
  `-k "cold_build or failed_build_releases"` -> 2 failed, 2 passed, 50 deselected.
  An event-held fake build occupied one worker and four additional waiters stayed
  blocked; eight HTTP requests also stayed pending before the route's five-second
  configured timeout. Both failures are assertions, not setup errors. Failure
  backoff/retry tests passed already and are retained as regressions.
- GREEN focused: original focused command -> 54 passed. Tests prove immediate
  waiter completion while the builder stays blocked, a reusable free pool worker,
  exactly one build, successful next request, retry after either expected or
  unexpected build failure, released lock, and joined test-pool threads. Existing
  U14 model/Milvus fallback, retry/backoff, shared executor and recovery tests pass.
- `python -m ruff check backend scripts` -> passed.
- `python -m ruff format --check backend scripts` -> passed, 78 files.
- `python -m bandit -r backend/app -q` -> passed, no findings.
- `git diff --check` -> passed.

The existing build lock itself supplies the atomic in-progress check; no flag,
new executor, future, setting or dependency is added. Contending cold-start
`target()` calls raise TimeoutError without waiting on that lock. The unchanged
route already maps this to 503 / SEARCH_UNAVAILABLE / "Search is starting. Try
again shortly." / retryable true. Its existing response has no Retry-After header;
the test asserts that remains unchanged. Calls still briefly execute through
`to_thread`, but no waiter holds its worker until the build finishes. The original
builder retains its route wait bound and finishes in the background if timed out.
Live-only fallback is still returned during rebuild, and failure retry backoff
and the build lock's finally-release remain unchanged.

No migration or operator configuration change; revert code to roll back (which
restores the blocking-waiter behavior). No worker, publication, archive storage,
Milvus or T20 file edits. Fakes only: no Docker/server/WSL/model or app closure.
Live-server behavior and Linux-only catalogue tests are not verified locally.

Full regression: `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:reports/backend-coverage.json`
-> **1124 passed, 67 skipped**, exit 0, 94.99 s. Existing Starlette/httpx warning;
platform/runtime and opt-in integration skips unchanged. Coverage command
`python scripts/quality.py coverage reports/backend-coverage.json` ->
**92.6% combined / 89.4% branches**, unchanged gate passed (exit 0).

## U5 and U6 execution — 2026-11-12

Owner-authorized slices before T29, done by Claude in the project thread, one PR
each from `origin/main` (U5 base `f273be6`, U6 base `69e9cab`). Both were
re-verified on main first; neither was already fixed. Fakes only (Linux
container, Python 3.13; CI on pinned Python 3.11.17 is the authority). Each PR
was reviewed by a separate Claude session at its exact head and squash-merged on
green.

**U5** ([PR #100](https://github.com/SumukhaK/open-source-projectFinder/pull/100),
reviewed at `6a5d46c`, merged as `69e9cab3b6994f424bebe846a171a3f7783646ed`,
[CI 43164076387](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/43164076387)).
`rank_fusion._excerpt` turns a stored snippet within 3 bytes of the 2,048-byte
limit (the only lengths the worker's character-boundary cut produces) into an
excerpt ending at the last whole word (any whitespace) plus `…`, still within
the limit; text without whitespace keeps its character cut; shorter snippets are
unchanged. It runs at serving time on purpose: the stored snippet is part of the
fenced `payload_digest`, so changing the worker's cut would make replays of
already-staged revisions fail. No re-ingest is needed. Known limit: a whole chunk
that is itself 2,045-2,048 bytes loses its last word. The mobile card labels the
text "README excerpt" (also for screen readers); licence-conflict cards still
hide it. RED: 4 fusion tests and 1 mobile test failed; GREEN: full backend 1251
passed / 3 skipped, 93.2% / 90.4%; mobile 207 passed / 1 skipped, typecheck and
lint clean.

**U6** ([PR #101](https://github.com/SumukhaK/open-source-projectFinder/pull/101),
reviewed at `4da2bd1`, merged as `85ee3cbb3bea5eecdbbc9834c963369f6c5972ea`,
[CI 43164551331](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/43164551331)).
Worker preflight now calls `MilvusAdapter.verify_collection()`, which keeps
every server, schema, index and load-state check and loads an existing
collection, but raises `MilvusCollectionMissing` (a `MilvusContractError`)
instead of creating a missing collection or index. `ensure_collection()` is the
operator init step only and reports what it created; it runs through the new
`python -m app.workers.archive init-collection` command, which needs only Milvus
and the pinned manifest. Existing collections need no action; a fresh
environment or a renamed `MILVUS_COLLECTION` runs `init-collection` once. RED:
12 tests failed; GREEN: full backend 1263 passed / 3 skipped, 93.3% / 90.4%;
ruff, format, bandit and `git diff --check` clean. Not run: a real Milvus
server.
