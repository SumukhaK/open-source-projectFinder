# T13 hybrid orchestration evidence

Date: 2026-10-30. Status: **Awaiting review**. Branch:
`codex/hybrid-t13-hybrid-service`. Base:
`d6927f4ea8fe18ead3fcff2927ebe4ed62583faf` (fetched `origin/main`).
Prerequisites T02 (`e400076`), T07 (`21e6db3`), T10 (`22295fa`), T11
(`0655834`) and T12 (`aec996f`) are merged into `main`. D1-D8 are approved;
T13 needs no new policy gate, but production serving remains gated by D4 and
the T15 route. No acceptance or merge is claimed.

## Contract

`backend/app/services/hybrid_search.py` is the one internal orchestration
service. The task file proposed `backend/app/services/discovery.py`, but main
has the legacy router at `backend/app/discovery.py` and the service layer at
`backend/app/services/`; a separate service module keeps the legacy endpoint
untouched.

`HybridSearchService(settings, github, embeddings, vectors, eligibility, *,
executor=None)` exposes:

```python
async def search(token, idea, *, language=None, license=None) -> HybridSearchResult
```

`HybridSearchResult` carries the T12 `FusedResults`, an overall status
(`ok`, `empty`, `degraded`, `incomplete` or `busy`) and the sanitized archive
reason. There is no route, cursor or persistence.

- Both sources start as concurrent asyncio tasks. The live task calls
  `GitHubKeywordCandidates.search`. The archive task embeds the full idea with
  T02's adapter (`kind="query"`, so the adapter applies `query: ` once), calls
  T07 `MilvusAdapter.search` starting at 200 chunks, doubles the limit while
  fewer than 100 distinct repositories are found, and stops at 1000 or when a
  page is shorter than the requested limit. T08 `filter_active_hits` is
  applied inside T10 `EligibilityService.check`, together with the ID-bound
  public check (cache TTL remains `archive_visibility_ttl_seconds`, at most
  15 minutes). T13 never re-implements those checks.
- One overall budget (`hybrid_search_budget`, default 8 seconds) is converted
  to a monotonic deadline. Admission, embedding, GitHub, Milvus and T10
  validation each receive `min(remaining, setting)`. T07 has no deadline
  parameter, so T13 bounds the synchronous call externally with
  `asyncio.wait_for`; this is a caller-side wait, not a claim that native
  Milvus work is cancelled.
- Blocking CPU, HTTP, Milvus and SQLite work runs in `BoundedExecutor`
  (`ThreadPoolExecutor` plus a `BoundedSemaphore` outstanding cap). A timed-out
  or disconnected caller keeps its slot until the worker really finishes, so
  abandoned native work is capped. A full executor returns `BusyError` rather
  than queueing indefinitely. Admission uses a separate asyncio semaphore and
  returns the explicit `busy` result when its bounded wait expires.
- Archive status is derived from the real outcome, never assumed `ok`:
  `failed` for embedding/model failure, missing or incompatible index,
  Milvus unavailability, timeout, overload, invalid source data, or a
  validation failure with no verified hits; `incomplete` for an overfetch
  ceiling, partial validation, or hits that T10 cannot verify; `ok` otherwise.
  A complete empty Milvus page is `ok` and distinct from a missing index.
  T02 `UnsupportedInput` becomes archive `query_not_supported`;
  `EmbeddingError` becomes `embedding_failed`; neither fails the request.
- Overall status: `empty` only when both sources completed (`ok`) and produced
  no candidates; `ok` when candidates exist and both sources are `ok`;
  `degraded` when candidates survive at least one non-`ok` source;
  `incomplete` when no candidates survive any non-`ok` source; `busy` when
  admission rejects the request. T11's GitHub 422 mapping remains
  `failed`/`unavailable`, and archive results still serve.
- One explicit `LICENSE_FILTERS` table maps a typed licence value to the T11
  GitHub keyword (`mit`, `apache-2.0`) and the T07/T10 SPDX ID (`MIT`,
  `Apache-2.0`). Unmappable values raise before either source is called.
  Language is passed to both sources.
- After T12 fusion, a `license_conflict` card keeps the live licence and drops
  its archive snippet/provenance (`archive=None`).
- Logging uses only counts, source statuses and duration on
  `reporadar.hybrid`; the raw idea, transcript, token and query embedding are
  never persisted or logged.

## Tests-first record

Platform: Windows (win32), Python 3.11.9, worktree virtual environment from
`backend/requirements.lock.txt`. All tests use fakes and barriers; no live
GitHub, OAuth, Milvus, SQLite, Docker or embedding-model call is claimed.

| Step | Command | Result |
| --- | --- | --- |
| RED (module absent) | `backend\.venv\Scripts\python.exe -m pytest tests/test_hybrid_search.py -q` | 1 error, exit 1: `ModuleNotFoundError: No module named 'app.services.hybrid_search'` for the newly written 33-test suite |
| GREEN focused | same command | 33 passed, exit 0 |
| Hardening tests added | same command | 35 passed, exit 0 (added unsupported live query and unverifiable-hits cases) |
| Review-fix RED | same command with the new tests against the previous implementation | 4 failed, 2 passed: all-ineligible hits (`True`/`False`), `operation_failed`, and queued-work cancellation |
| Review-fix GREEN | same command | 37 passed, exit 0 |
| Affected existing tests | `python -m pytest tests/test_hybrid_search.py tests/test_rank_fusion.py tests/test_keyword_candidates.py tests/test_eligibility.py tests/test_milvus.py -q` | 198 passed, exit 0 |
| Affected after review fixes | `python -m pytest tests/test_hybrid_search.py tests/test_rank_fusion.py tests/test_eligibility.py -q` | 99 passed, exit 0 |
| Full suite | `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=term-missing --cov-report=json:reports/backend-coverage.json --cov-report=xml:reports/backend-coverage.xml --junitxml=reports/backend-tests.xml` | 807 passed, 65 skipped, 1 warning, exit 0 |
| Coverage gate | `python scripts/quality.py coverage reports/backend-coverage.json` | 93.9% combined, 91.6% branches, exit 0; unchanged 90/80 policy |
| Ruff check | `python -m ruff check backend scripts` | All checks passed, exit 0 |
| Ruff format | `python -m ruff format --check backend scripts` | 55 files already formatted, exit 0 |
| Bandit | `python -m bandit -r backend/app -f json -o reports/bandit.json` | 0 findings, 0 errors, exit 0 |
| Whitespace | `git diff --check` | exit 0 |
| Secret inspection | changed-file scan for credential patterns and `.env` staging | no credential-like values; only placeholder `backend/.env.example` changed; no `.env` staged |

The 37 focused tests cover: concurrent start with a two-party barrier;
both complete-empty vs one incomplete/failed source; slow live and slow
archive with verified hits from the other source; GitHub 422 with archive
results; unsupported keyword query; unsupported embedding and model failure;
broken/unavailable/incompatible index vs empty index; validation failure and
partial validation; all-ineligible hits (no issues) as a complete `ok` answer
vs unverifiable hits (issues present); overfetch stop and ceiling; both
licence mappings and unmappable rejection with no source call; `license_conflict`
snippet removal; live metadata reuse; disconnect; overload; backlog cap after
timeouts and cancellation of queued work; no raw idea in logs; invalid source
results; and executor guards.

The first RED run failed at import because the new module did not exist yet.
After the module existed, two expectations were corrected to match the
architecture: a healthy archive-only result is `ok` (a repository need not be
in both sources), and a partial archive result with verified hits is
`degraded` regardless of the live branch. Two hardening tests were added for
the unsupported live query and unverifiable archive hits.

## Review fixes (2026-10-31)

Exact-head review of `b85298f` requested two fixes and noted two low items. All
four are addressed in `hybrid_search.py` and its tests:

1. **All-ineligible archive hits are now a complete answer.** When T10 returns
   no evidence and no issues, every hit was definitively dropped (archived,
   private, suppressed, stale or no longer catalogued). `_archive` returns
   `ok` (or `incomplete`/`overfetch_exhausted` if the ceiling was hit) instead
   of `incomplete`/`unverified_hits`. A stale archive can now contribute to a
   definitive `empty`, and with live candidates the overall status is `ok`.
   Hits that T10 reports as `issues` still fail (`failed` with no evidence) or
   are `incomplete` (partial evidence), unchanged.
2. **Queued work for a timed-out or cancelled caller is cancelled.**
   `BoundedExecutor.run` keeps the `concurrent.futures.Future` from
   `submit`. On `TimeoutError`/`CancelledError` it calls `cancel()`; if the job
   had not started, the slot is reclaimed there because `task()` will never
   run. A running job still keeps its slot until it finishes, so abandoned
   native work remains capped.
3. **`MilvusOperationError` is reported as `operation_failed`.** T07 documents
   it as a generic sanitized non-retryable SDK failure, not specifically a
   missing index. It still yields archive `failed`, distinct from an empty
   index, which stays `ok` with no hits.
4. **Overfetch replaces rather than accumulates pages.** A larger Milvus search
   already contains the previous top-k, so `rows = page` avoids holding up to
   2,400 overlapping rows. T12 re-sorts by score, so the result is unchanged.

RED/GREEN: the new tests were run against the previous implementation and
failed as expected (`4 failed, 2 passed`: both all-ineligible cases,
`operation_failed`, and queued-work cancellation). Against the fixed
implementation the focused suite is `37 passed`; the requested affected suite
is `99 passed`; the full backend/scripts suite is `807 passed, 65 skipped`
with the unchanged 90/80 coverage gate at 93.9% combined / 91.6% branches.
Ruff check/format, Bandit (0 findings) and `git diff --check` are clean.

## Limits and handoff

- **Real-stack run not run (deferred to T26).** No Docker, Milvus, embedding
  model, real GitHub call or cross-layer HTTP flow was started. Unit tests use
  fakes and prove orchestration/status semantics, not real latency, Milvus
  behaviour or live GitHub rate limits.
- T07's synchronous SDK can overshoot its own operation budget during an
  in-flight call or backoff. T13 bounds the caller-side wait and caps
  outstanding work; it does not claim that native work stops. Reconcile with
  stable IDs if a late Milvus operation may have completed.
- T10's visibility cache is at most 15 minutes by configuration. If validation
  cannot complete, archive hits are suppressed and the source is marked
  failed/incomplete rather than served unverified. Production serving still
  needs D4/T15 activation.
- The archive overfetch ceiling is 1000 chunks. Hitting it returns
  `incomplete`/`overfetch_exhausted` and still serves verified hits; it does not
  claim exhaustive archive coverage.
- No T14 cursor, T15 route, mobile UI, scheduler, new dependency, CI gate or
  quality-policy change is included. The legacy `POST /projects/search`
  contract is unchanged.
- The service is constructed with explicit dependencies by its caller; app
  startup still does not construct Milvus, embeddings or the archive store.

No raw idea, transcript, query embedding or provider credential is read,
persisted or logged by this service.

Rollback: revert the T13 commit. There is no migration, stored data, route or
scheduled job to undo. The new `HYBRID_*` settings are inert without a caller;
removing them restores the previous configuration surface. T02/T07/T08/T10/T11/
T12 and the legacy endpoint remain unchanged. Operators need take no action.
