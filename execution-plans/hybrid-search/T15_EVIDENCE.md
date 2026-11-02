# T15 hybrid API evidence

Date: 2026-11-02. Status: **Awaiting review**. Branch:
`codex/hybrid-t15-hybrid-api`. Base:
`5d1b404ff8a0ea650a5f411c3d60d88f8d697c5d` (fetched `origin/main`).
Prerequisite T14 is merged into `main` as `5d1b404`; T13, T12, T11 and T10
are merged ancestors. D1-D8 are approved. No acceptance or merge is claimed.

## Contract

`backend/app/api/archive.py` adds two authenticated routes to the existing app
factory. The route never selects a source: every ordinary search runs both T13
branches. Pagination always goes through T14 `HybridPager`; there is no second
pagination path.

### `POST /v1/projects/search`

Request body (extra fields are rejected):

```json
{"idea":"an offline-first app for sharing community tools",
 "page_size":20,"cursor":null,"filters":{"language":"TypeScript"}}
```

- `idea` is 2-1000 characters after trimming; `page_size` is 1-50 (default 20);
  `cursor` is optional and bounded to 2048 characters.
- `filters.language` and `filters.license` are optional typed values.
  `license` is mapped through T13 `LICENSE_FILTERS` to both source spellings;
  an unmappable value is a typed `422 UNSUPPORTED_FILTER`. Unknown body fields
  are a typed `422 INVALID_REQUEST`.
- Session authentication and the legacy discovery rate limit guard the route.
  The request body limit also covers `/v1`.
- First page: `await pager.first_page(token, idea, account=github_id, ...)`.
  Later pages: `pager.next_page(...)` through the T13 `BoundedExecutor` with
  the remaining request deadline, so the synchronous pager and its T10
  revalidation never block the event loop.
- `account` is the authenticated numeric `github_id`; `generation` is the
  pinned embedding manifest revision plus `rrf-v1`, identical on every page.
- The injected `FusedRevalidator` adapts fused cards to T10
  `EligibilityService.check`: archived cards become T07 hit identities
  (`repo_id`, `revision`, `chunk_id`), live-only cards are freshly re-read with
  `ArchiveGitHubReader.fetch_metadata` and passed as `live`, and only freshly
  verified public/eligible repositories are kept. Reader or identity failures
  fail closed by dropping the card. Stored snapshot metadata is never reused as
  the visibility check.
- Response items keep the existing card fields and add `sources`,
  `freshness` (`live`, `archive` or `live+archive`), `license`,
  `license_conflict`, `matched_section`, `snippet`, `rank` and `rrf_score`.
  T13 already drops an archive snippet when the licence conflicts, so the live
  licence wins and no possibly disallowed archive text is serialized. Rank
  scores are raw RRF values, never percentages or probabilities.
- The page also returns `next_cursor`, `has_more`, `total: null`,
  `degraded`, per-source `status`/`incomplete`/`reason`/`retry_after`,
  `archive_as_of` and `ranking_version`.
- `ok`, `degraded` and `empty` pages are served. `incomplete` maps to
  `503 SEARCH_INCOMPLETE`; `busy` maps to `503 SEARCH_BUSY`; an exhausted
  deadline maps to `503 SEARCH_TIMEOUT`; all are typed and retryable.
  Expired/evicted cursors map to `410 CURSOR_EXPIRED`; tampered, cross-account,
  cross-idea or cross-filter cursors map to `400 CURSOR_INVALID`.

### `GET /v1/archive/status`

- Requires the same session authentication; there is no authentication bypass.
- Returns a sanitized lifecycle view: `state`
  (`uninitialized`/`initialized`/`unknown`), `search_configured`,
  `collection`, `profile`, `model_revision`, `ranking_version`,
  `generation`, `coverage`, `archive_as_of`, repository/document/chunk counts
  and the latest recorded run.
- `archive_as_of` stays `null` and no last-success is invented: T17/T19 own
  real lifecycle data. `latest_run` is the latest recorded `archive_runs` row
  with its honest `completed` flag, not a claim of a successful refresh.
- No filesystem path, token, exception text or secret is returned. On a
  platform without the private POSIX archive filesystem, or when the
  catalogue cannot be read, `state` is `unknown` and the numeric fields stay
  `null`; the endpoint still returns `200`.

### Lazy runtime

`backend/app/services/hybrid_runtime.py` builds the serving stack on first use,
never at import or app boot:

1. check `HYBRID_CURSOR_SIGNING_KEY` (at least 32 characters);
2. load the pinned embedding model through the public `EmbeddingAdapter.load()`;
3. connect Milvus (the SDK is imported locally, after the key/model checks);
4. open the private archive store and the bounded public archive reader;
5. construct the T10 eligibility service, T13 search service, T14 pager and
   the revalidator.

Any failure raises `HybridUnavailable`, which the route maps to
`503 SEARCH_UNAVAILABLE`. The first build runs in a worker thread. Missing
signing key, model, Milvus or archive reader never stops boot and never breaks
the legacy `POST /projects/search` route.

`backend/app/discovery.py` extracts the existing decrypted-credential helper as
`credentials(store, cipher, current)`; the legacy discovery router and the v1
route share it unchanged.

## Tests-first record

Platform: Windows (win32), Python 3.11.9, existing worktree virtual
environment. All tests use fakes, a fixed clock and an injected runtime; no
live GitHub, OAuth, Milvus, Docker, embedding-model or real HTTP flow is
claimed.

| Step | Command | Result |
| --- | --- | --- |
| RED | `python -m pytest backend/tests/test_archive_api.py backend/tests/test_hybrid_runtime.py -q` | 2 collection errors, exit 1: `ModuleNotFoundError: No module named 'app.services.hybrid_runtime'` |
| GREEN focused | same command | 32 passed, exit 0 |
| Affected existing tests | `python -m pytest backend/tests/test_archive_api.py backend/tests/test_hybrid_runtime.py backend/tests/test_discovery.py backend/tests/test_fused_cursor.py backend/tests/test_hybrid_search.py backend/tests/test_eligibility.py backend/tests/test_auth.py backend/tests/test_crashes.py backend/tests/test_body_limit.py -q` | 263 passed, exit 0 |
| Full suite | `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=term-missing --cov-report=json:reports/backend-coverage.json --junitxml=reports/backend-tests.xml -q` | 938 passed, 65 skipped, 1 warning, exit 0 |
| Coverage gate | `python scripts/quality.py coverage reports/backend-coverage.json` | 93.6% combined, 91.3% branches, exit 0; unchanged 90/80 policy |
| Ruff check | `python -m ruff check backend scripts` | All checks passed, exit 0 |
| Ruff format | `python -m ruff format --check backend scripts` | 65 files already formatted, exit 0 |
| Bandit | `python -m bandit -r backend/app -f json -o reports/bandit.json` | 0 findings, exit 0 |
| Whitespace | `git diff --check` | exit 0 |
| Secret inspection | changed-file scan for credential patterns and ignored secret files | no credential-like value or secret file staged |

The 32 focused tests cover: unauthenticated search and status; the shared
legacy rate limit and `Retry-After`; idea/page-size/cursor/extra-field bounds;
typed language/licence canonicalization; unmappable licence rejection; value-
free validation errors that do not echo the idea; first-page semantic cards
with provenance, freshness, licence, ranking fields and `total: null`; a licence
conflict that serves the live licence without archive text; no similarity
percentages; degraded partial hits with source health; empty
success; `incomplete` and `busy` typed retryable errors; later-page fresh
visibility revalidation off the event loop, including a private card and an
archive card; the remaining-deadline timeout; expired, tampered, cross-account
and cross-idea/filter cursors; unchanged legacy search; an unconfigured signing
key that keeps boot and legacy working while v1 is typed unavailable; and a
sanitized status response without paths or tokens.

Runtime tests additionally prove the T10 adapter keeps only freshly verified
repositories, fails closed on a reader error, and drops cards without a usable
name; `archive_counts` distinguishes an empty catalogue from recorded runs;
status never invents a last success and contains no path/error text; and the
signing key is checked before the embedding model is loaded.

## Limits and handoff

- **Real-stack run not run (T26 owns it).** No Docker, Milvus, embedding
  model, live GitHub call or HTTP round trip was started. These tests prove the
  route contract, guards, pagination and revalidation wiring with fakes, not
  latency, capacity or a real corpus.
- **Single process only.** T14 snapshots are in memory, so cursors do not
  survive a restart or span API hosts. `CURSOR_EXPIRED` is the explicit
  restart signal.
- **No exact global total.** `total` is always `null`; source totals are never
  added.
- **Status is honest but shallow.** `archive_as_of` stays `null` until a later
  lifecycle task supplies it. On Windows the private POSIX catalogue cannot be
  opened, so status reports `state: "unknown"`; on Linux an empty catalogue
  reports `uninitialized` and a populated one `initialized`. `coverage` stays
  `unknown` because T13 does not supply a curated/partial coverage fact.
- **Serving prerequisites.** Production v1 search needs the signing key, the
  cached pinned model, a reachable Milvus collection, the private archive
  catalogue and `ARCHIVE_GITHUB_TOKEN` for fresh public reads. Any missing
  prerequisite returns the typed unavailable error; the legacy route is
  unaffected.
- No worker control, mode/source parameter, scheduler, mobile change, new
  dependency, CI gate or quality-policy change is included.
- No raw idea, transcript, query embedding, archive text or provider
  credential is persisted or logged by the new routes.

Rollback: revert the T15 commit. There is no migration, stored data or
scheduled job to undo. The new routes are additive; the legacy
`POST /projects/search`, details and favourites contracts remain unchanged.
Operators only need the existing hybrid settings (`HYBRID_*`, Milvus and
archive configuration) before the v1 route can serve.
