# T11 keyword candidate evidence

Date: 2026-10-29. Status: Awaiting review. Branch:
`codex/hybrid-t11-keyword-candidates`. Base:
`2492d60401ea698017bc1a3386da1b02ddf24dd5` (fetched `origin/main`).
Prerequisites T00 (`6dc4233`) and T10 (`22295fa`) are merged into `main`.
No acceptance or merge is claimed; the PR link is recorded after creation.

## Contract

The merged legacy adapter is now one pure compiler in
`backend/app/services/keyword_query.py`: Unicode-aware keyword text, the same
stop words, at most six keywords, and the same 256-character bound. The legacy
`POST /projects/search` route calls it and keeps its existing response keys,
default `per_page` 20, `sort: relevance` / `order: desc` defaults, 422 messages,
and public/unarchived query scope.

`backend/app/services/keyword_candidates.py` is an internal source, not an API
route. `GitHubKeywordCandidates.search(token, idea, filters=None)` requests one
GitHub search page with `per_page=100`, `page=1` and no upstream sort/order. It
returns ranked `KeywordCandidate(rank, metadata)` values and one source status:

| Status | Meaning |
| --- | --- |
| `ok` | Completed search, including a completed empty result |
| `incomplete` | GitHub returned `incomplete_results=true`; partial hits are retained |
| `query_not_supported` | `reason` is `empty` or `too_long`; no provider request is made |
| `failed` | `reason` is `rate_limited`, `unavailable` or `invalid_response`; optional `retry_after` |

`completed` is true only for `ok`; `incomplete` is true only for `incomplete`.
Live candidates require an exact positive numeric ID, `private=false`,
`archived=false`, and public/default visibility. They do not inherit the archive
365-day cutoff, catalogue membership or licence-content policy. Older and
copyleft live repositories remain eligible.

`CandidateFilters(language=..., license=...)` is the only typed shared filter.
Values are restricted to a bounded safe character set; multi-word values are
quoted, and quotes, colons, newlines and backslashes are rejected before any
provider call. The query is always the compiled keywords plus the fixed
`in:name,description,readme is:public archived:false` scope; a valid idea that
cannot compile a safe query never becomes a qualifiers-only broad search.

`backend/app/services/live_scope.py` holds the dependency-free `live_eligible`
predicate used by both T10 eligibility and the live keyword source, avoiding a
heavy archive/vector import on the keyword branch.

## Tests-first record

Platform: Windows (win32), Python 3.11.9, clean worktree virtual environment
created from `backend/requirements.lock.txt`. Tests use fake providers and
`httpx.MockTransport`; no live GitHub, OAuth or Milvus call is claimed.

| Step | Command | Result |
| --- | --- | --- |
| Baseline focused regression | `python -m pytest backend/tests/test_discovery.py backend/tests/test_provider.py -q` | 87 passed, exit 0 |
| RED | `python -m pytest backend/tests/test_keyword_candidates.py backend/tests/test_discovery.py -q` | 25 failed, 78 passed, exit 1; expected assertion failures for the missing compiler, ranked source, statuses, and filter handling |
| GREEN focused | `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_keyword_candidates.py backend/tests/test_discovery.py backend/tests/test_provider.py backend/tests/test_eligibility.py -q` | 163 passed, 1 warning, exit 0 |
| Full suite and coverage | `backend\.venv\Scripts\python.exe -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=term-missing --cov-report=json:reports/backend-coverage.json --cov-report=xml:reports/backend-coverage.xml --junitxml=reports/backend-tests.xml` | 729 passed, 49 skipped, 1 warning, exit 0 |
| Coverage gate | `backend\.venv\Scripts\python.exe scripts\quality.py coverage reports\backend-coverage.json` | 94.4% combined, 92.3% branches, exit 0; unchanged policy |
| Ruff check | `backend\.venv\Scripts\python.exe -m ruff check backend scripts` | All checks passed, exit 0 |
| Ruff format | `backend\.venv\Scripts\python.exe -m ruff format --check backend scripts` | 48 files already formatted, exit 0 |
| Bandit | `backend\.venv\Scripts\python.exe -m bandit -r backend/app -f json -o reports/bandit.json` | 0 findings, 0 errors, exit 0 |
| Whitespace | `git diff --check` | exit 0; only an LF-to-CRLF notice for `PROJECT_TRACKER.md` |
| Secret inspection | changed-file scan for credential patterns and `.env` staging | no secret values; only test placeholders and setting names; no `.env` staged |

RED covered the unchanged legacy contract and default response shape, long,
stop-word, Unicode and operator-like input, `incomplete_results`, provider
limits/errors and typed filter escaping. GREEN covered retaining the full
semantic input outside the six-keyword GitHub adapter and turning unsupported
compilation into a source status rather than an endpoint-wide 422.

One RED test constructed a 1,000-character idea with a length typo; the input
was corrected before GREEN without changing its assertion. The recorded RED run
predates that input-only correction.

## Limits and handoff

- This is one bounded GitHub search page. Fused ranking, source totals, cursors,
  concurrency and the versioned API are T12-T15 work and are not implemented here.
- No real GitHub request was made. The source relies on the existing provider's
  bounded timeout, retry, response-size and error mapping; live OAuth search
  remains unverified.
- The filter character set is a safety allowlist, not a canonical language or
  licence catalogue. Unsupported values raise `ValueError` before the provider
  call; the future orchestration layer must map that to a request validation
  result.
- 49 platform/server skips are unchanged (WAL/Milvus integration). No migration,
  hardware or capacity claim is made.
- The worktree virtual environment was used because the shared checkout's
  `pymilvus` import loads an unrelated local `.env`; this is a local environment
  issue, not a code change. CI installs from the same lock file in a clean job.

No raw idea, transcript, embedding or provider credential is persisted or
logged by this source. Provider failures are reduced to sanitized status values.

Rollback: revert this task's commit. There is no migration, stored data, new
configuration or API route to undo; the legacy endpoint keeps its previous
compiler behavior. Operators need take no action.

Source checked: [GitHub repository search syntax](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories).
