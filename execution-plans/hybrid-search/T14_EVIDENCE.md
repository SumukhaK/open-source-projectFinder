# T14 fused snapshot cursor evidence

Date: 2026-11-01. Status: **Awaiting review**. Branch:
`codex/hybrid-t14-fused-cursors`. Base:
`c4e320424f2859f325b2b21e30dcc34e20e2f351` (fetched `origin/main`).
Prerequisite T13 (`74de757`) is merged into `main`. T14 needs no new policy
decision; production serving of these cursors still needs D4 and the T15 route.
No acceptance or merge is claimed.

## Contract

`backend/app/services/fused_cursor.py` is one internal pagination module. The
task file proposed "hybrid snapshot/cursor helpers"; main already has the T13
service at `backend/app/services/hybrid_search.py`, so the pager wraps it rather
than changing it.

`HybridPager(service, settings, *, now=None, revalidate=None)` exposes:

```python
async def first_page(token, idea, *, account, page_size, generation,
                     language=None, license=None) -> CursorPage
def next_page(*, account, idea, cursor, page_size, generation,
              language=None, license=None) -> CursorPage
```

- `first_page` runs the normal T13 search once, stores one bounded snapshot and
  returns its first page. `next_page` never calls either source again, so a
  source that recovers between pages cannot splice new repositories into the
  stored ranking.
- A snapshot keeps at most `HYBRID_SNAPSHOT_MAX_CANDIDATES` (200) fused cards
  for `HYBRID_CURSOR_TTL_SECONDS` (300, the approved five-minute lifetime), and
  `page_size` must be 1-200. `HYBRID_CURSOR_CACHE_SIZE` (256) bounds all
  snapshots and `HYBRID_CURSOR_CACHE_PER_ACCOUNT` (8) bounds one account; both
  use `OrderedDict` insertion order and a `Lock`, so concurrent threads cannot
  grow the cache past the limit.
- A cursor is an opaque `body.signature` token: base64url canonical JSON plus
  HMAC-SHA256 over the encoded body. The payload has exactly
  `{"v","sid","acc","q","f","g","exp","off"}` where `v` is the cursor version,
  `sid` the process-local snapshot ID, `acc` the account, `q`/`f` HMAC-SHA256
  digests of the idea and typed filters keyed by the signing key, `g` the
  caller's model/ranking generation, `exp` the absolute expiry and `off` the
  next index. It contains no idea, transcript, query embedding or repository
  list, and all digest comparisons use `hmac.compare_digest`.
- `next_page` requires the same account, idea, typed filters and `generation`
  that produced the cursor. A tampered, cross-account/query/filter/generation,
  wrong-shape, out-of-range or another snapshot's ID raises `CursorInvalid`.
  Expiry, eviction or a process restart raises `CursorExpired`; both mean the
  client must start a fresh search.
- Later pages recheck only their own page window through the required
  `revalidate` callable; there is no stored-metadata default. Removed cards
  shorten the page and `off` still advances by the examined count, so pages stay
  stable, non-overlapping and non-duplicating. `next_page` is synchronous
  because the callable may block: T15 must call it off the event loop with the
  request's remaining deadline and adapt fused cards to T10
  `EligibilityService.check` input.
- `HYBRID_CURSOR_SIGNING_KEY` is a required random value of at least 32
  characters. An empty or short key refuses pager construction (fail closed)
  instead of signing with a guessable default.
- An empty fused result returns an empty page with no cursor and stores nothing.
  Degraded/incomplete source provenance is copied onto every later page.

## Tests-first record

Platform: Windows (win32), Python 3.11.9, the existing worktree virtual
environment. All tests use fakes and a fixed clock; no live GitHub, OAuth,
Milvus, SQLite, Docker or embedding-model call is claimed.

| Step | Command | Result |
| --- | --- | --- |
| RED (stub module) | `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_fused_cursor.py -q` | 37 failed, 4 passed, exit 1; the 4 passes only exercise trivial stub paths (expired/evicted/restart/bounded-writes) |
| GREEN focused | same command | 41 passed, exit 0 |
| Hardening tests added | same command | 52 passed, exit 0 (cursor shape/tamper, cross-snapshot binding, cache expiry, store limits, non-mapping payload) |
| Review-fix RED (2026-11-01) | `python -m pytest backend/tests/test_fused_cursor.py -q -k "keyed or different_signing or revalidator or page_size"` | 6 failed, 1 passed, exit 1: keyed digests, different keys, missing revalidator, `page_size` 201/1000 and the next-page bound; the equal-limit case passed |
| Review-fix GREEN | `python -m pytest backend/tests/test_fused_cursor.py -q` | 59 passed, exit 0 |
| Requested focused | `python -m pytest backend/tests/test_fused_cursor.py backend/tests/test_hybrid_search.py -q` | 96 passed, exit 0 |
| Affected existing tests | `python -m pytest backend/tests/test_fused_cursor.py backend/tests/test_hybrid_search.py backend/tests/test_rank_fusion.py backend/tests/test_eligibility.py backend/tests/test_keyword_candidates.py -q` | 167 passed, exit 0 |
| Full suite | `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:reports/backend-coverage.json -q` | 899 passed, 65 skipped, 1 warning, exit 0 |
| Full suite after review fixes | same command | 906 passed, 65 skipped, 1 warning, exit 0 |
| Coverage gate | `python scripts/quality.py coverage reports/backend-coverage.json` | 93.8% combined, 91.4% branches, exit 0; unchanged 90/80 policy; new module 98.5% |
| Ruff check | `python -m ruff check backend scripts` | All checks passed, exit 0 |
| Ruff format | `python -m ruff format --check backend scripts` | 60 files already formatted, exit 0 |
| Bandit | `python -m bandit -r backend/app -f json -o reports/bandit.json` | 0 findings, exit 0 |
| Whitespace | `git diff --check` | exit 0 |
| Secret inspection | changed-file scan for credential patterns and `.env` staging | only placeholder `backend/.env.example` changed; no `.env` or key value staged |

The 59 tests cover: first-page order plus cursor binding/expiry/offset; full
coverage of a snapshot without duplicates or rank splicing; stable repeat of a
page; seven tamper shapes; account, idea, filter and generation binding; expired
cursor; evicted snapshot; process restart; foreign signing key; keyed digests
that differ from plain SHA-256 and from another signing key; later-page
visibility shortening and examined-count advancement; no splice after source
recovery; total and per-account cache bounds; missing/short signing key; a
required explicit revalidator; no idea or embedding in snapshot/cursor;
eligibility recheck through the injected callable; concurrent bounded writes;
invalid inputs; page-size bounds on both pages; signed out-of-range offsets;
degraded provenance on later pages; 200-candidate cap; empty result; unexpected
signed payload shapes; another account's snapshot ID; cache expiry/removal;
store limit validation; and a non-mapping payload.

Two test expectations were corrected during GREEN rather than changing the
design: the last-character signature mutation could decode to the same bytes
because base64 ignores padding bits, so the tamper test now flips the first
signature character deterministically; and the expiry test now checks `get` and
`size` against two expired snapshots so both removal paths are exercised.

## Review fixes (2026-11-01)

Exact-head review of `0863dcf` requested three changes. All are in
`fused_cursor.py`, its tests and the docs:

1. **Keyed digests.** `CursorCodec.digest` computes
   `hmac.new(key, data, sha256).hexdigest()`, and `_binding` uses it for both
   the idea and typed-filter digests. Equality checks remain
   `hmac.compare_digest`. New tests prove `q` is not
   `hashlib.sha256(idea).hexdigest()` and that two pagers with different keys
   produce different digests for the same idea.
2. **Fail-closed revalidation.** The stored-metadata `_still_eligible` default
   and the `live_eligible` import are removed. `HybridPager` raises
   `ValueError` at construction unless `revalidate` is callable, so later pages
   cannot silently serve stale visibility. Tests now pass an explicit
   revalidator, and the visibility-change test is unchanged. For the executor
   choice, the documentation option was taken: `next_page` stays synchronous,
   and the pager docstring, backend README and T15 task require T15 to call it
   off the event loop with the request's remaining deadline and adapt fused
   cards to T10 `EligibilityService.check` input.
3. **Bounded page size.** `page_size` is now 1..`HYBRID_SNAPSHOT_MAX_CANDIDATES`
   (1-200) on both `first_page` and `next_page`; 0, non-integers and values above
   the limit raise `ValueError`. Tests cover 201, 1000, the next-page path and
   the equal-to-limit boundary.

RED/GREEN: the new tests were run against the previous implementation and
failed as expected (`6 failed, 1 passed`: keyed digests, different keys, missing
revalidator, both over-limit `page_size` values and the next-page bound; the
equal-limit case passed). Against the fixed implementation the focused suite is
`59 passed`, the requested `test_fused_cursor` + `test_hybrid_search` pair is
`96 passed`, and the full backend/scripts suite is `906 passed, 65 skipped`
with the unchanged 90/80 coverage gate at 93.8% combined / 91.4% branches.
Ruff check/format, Bandit (0 findings) and `git diff --check` are clean.

## Limits and handoff

- **Single process only.** Snapshots are in memory: they do not survive a
  restart and are not shared between API hosts. `CursorExpired` is the explicit
  restart signal. Multi-host serving would need shared state and is not claimed.
- **No exact global total.** `CursorPage.has_more` means "more cards exist in
  this snapshot"; the count is bounded by the 200-candidate snapshot, not by all
  possible repositories. T15's nullable total stays nullable.
- **T15 must run the fresh check off the event loop.** `next_page` is
  synchronous and calls the caller-supplied revalidator, which may block. T15
  must run it in a worker thread with the remaining deadline and adapt fused
  cards to T10 `EligibilityService.check` input so a repository made private
  after the first page is not served on a later page.
- **Real-stack run not run (deferred to T26).** No Docker, Milvus, embedding
  model, real GitHub call or HTTP flow was started. Unit tests prove cursor
  isolation and pagination semantics, not multi-host behaviour or latency.
- No T15 route, mobile UI, scheduler, new dependency, CI gate or quality-policy
  change is included. The legacy `POST /projects/search` contract is unchanged.
- `generation` is a caller-supplied string (model revision plus ranking
  version). T15 owns building it from the pinned manifest; T14 only binds and
  compares it.

No raw idea, transcript, query embedding or provider credential is stored,
logged or signed by this module.

Rollback: revert the T14 commit. There is no migration, stored data, route or
scheduled job to undo. The `HYBRID_CURSOR_*`/`HYBRID_SNAPSHOT_*` settings are
inert without a caller. T13 and the legacy endpoint remain unchanged. Operators
only need to set `HYBRID_CURSOR_SIGNING_KEY` before enabling a caller; leaving
it empty keeps pagination disabled (fail closed).
