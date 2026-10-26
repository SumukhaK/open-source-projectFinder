# T04 archive HTTP evidence - 2026-10-26

Status: **Awaiting review** in [PR #19](https://github.com/SumukhaK/open-source-projectFinder/pull/19). This is T04 only; it does not accept, merge or start another task. The PR's current full head SHA and required CI run are authoritative in GitHub; this file cannot embed its own commit SHA. Review/merge evidence belongs in [TRACKER](TRACKER.md).

## Scope and prerequisites

- Branch: `codex/hybrid-t04-archive-http`, cut from `origin/main` at `776bf654551fd0466386c6bc008df6ae606b0dcb`.
- Verified merged prerequisites are ancestors of that base: T00/PR #13 `6dc4233797bc00d2b71fb2c0311574dc55bd5763`, T01/PR #15 `7f94e2f5c8b0e68905dba367c584b4f74d98c175`, T02/PR #16 `e4000764c97b3648ec0b08fe42989ee8d2e56463`, and T03/PR #18 `776bf654551fd0466386c6bc008df6ae606b0dcb` (merged 2026-10-26T02:52:16Z).
- Production change: new `backend/app/integrations/archive_github.py` plus central settings in `backend/app/core/config.py`. Tests: `backend/tests/test_archive_github.py`. No change to the OAuth provider `backend/app/integrations/github.py`.
- No dependency, lockfile, CI workflow, quality-gate or security-exception change. No API route, worker, scheduler, persistence, migration or live GitHub call is added.
- The reader is worker-only and uses a separately configured public-read credential. It is not imported by the API app; normal startup is unchanged and an absent `ARCHIVE_GITHUB_TOKEN` is only an error when a worker constructs the reader.

## TDD and verification

All commands below ran on Windows 10/11 with Python 3.11.9 unless noted. `python` means the local interpreter; `ruff` is 0.16.x.

| Step | Command / assertions | Actual result |
| --- | --- | --- |
| Baseline | `python -m pytest backend/tests scripts/tests -q` | Exit 0, 182 passed, 40 skipped (POSIX-only T03 catalogue tests) |
| RED | `python -m pytest tests/test_archive_github.py -q` against an interface-only scaffold | Exit 1, **80 failed**: missing settings, `NotImplementedError` and absent behavior |
| GREEN focused | `python -m pytest tests/test_archive_github.py -q` | Exit 0, **128 passed** in 0.90s |
| Full regression/coverage | `python -m pytest backend/tests scripts/tests -q --cov=backend/app --cov-branch --cov-report=term-missing --cov-report=json:reports/t04/backend-coverage.json` | Exit 0, **310 passed**, 40 skipped, 1 inherited Starlette/httpx warning |
| Coverage policy | `python scripts/quality.py coverage reports/t04/backend-coverage.json` | Exit 0, **93.9% combined / 91.1% branches**; required 90/80 unchanged |
| New-module coverage | Focused coverage report | **99% lines and branches**; the only miss is the unreachable fall-through after a validated `ge=1` attempt loop |
| Lint | `ruff check backend scripts` | Exit 0, all checks passed |
| Format | `ruff format --check backend scripts` | Exit 0, 28 files already formatted |
| SAST | `bandit -r backend/app -q -f json -o reports/t04/bandit.json` | Exit 0, no findings or scanner errors |
| Dependency audit (backend) | `pip-audit --strict --no-deps --disable-pip -r backend/requirements.lock.txt` | Exit 0, no known vulnerabilities |
| Dependency audit (embeddings) | Same command on the lock with only `torch==2.14.1+cpu` rewritten to `torch==2.14.1` | Exit 0, no known vulnerabilities |
| Secret scan | `gitleaks git --redact --no-banner .` (8.30.1) | Exit 0, 43 commits scanned, **no leaks found** |
| Whitespace | `git diff --check` | Exit 0, clean |

Bandit 1.9.4 and pip-audit 2.10.1 were installed in a disposable temp venv for these checks; the global interpreter and repository locks were not changed. Raw reports remain under ignored `reports/t04/`.

Local WSL could not start on this host (`Wsl/Service/CreateInstance/CreateVm/HCS/ERROR_NO_SYSTEM_RESOURCES`), so the POSIX-only T03 catalogue tests were skipped locally. The unchanged Linux CI job runs them and is the authoritative combined coverage run; the local Windows gate still passed at 93.9%/91.1%. This is a local runtime limitation, not a claim that the POSIX path was exercised here.

## Behavior and acceptance mapping

| Requirement | Implemented evidence |
| --- | --- |
| 200 and 304 with and without a body | `test_metadata_200_returns_a_typed_response_and_verified_identity`, `test_metadata_304_without_a_cached_body_is_a_cache_miss`, `test_metadata_304_with_a_cached_body_returns_the_cached_metadata`, `test_304_with_a_body_is_still_not_modified`, `test_200_without_a_body_is_a_protocol_error` |
| Missing README vs missing repository | `test_missing_repository_is_ambiguous_and_not_a_deletion`, `test_missing_readme_is_distinct_from_missing_repository`; metadata 404 raises `RepositoryNotFound` with "not proof of deletion", README 404 returns `readme_missing=True` only after verified metadata |
| Bad base64 and oversize content | `test_bad_base64_readme_is_rejected`, `test_oversize_readme_is_rejected`, `test_readme_decoded_size_is_bounded_even_when_the_declared_size_lies`, `test_readme_declared_size_must_match_decoded_bytes`, blob equivalents |
| Old-name reuse and renames | `test_old_name_reuse_rejects_a_different_repository_id`, `test_rename_with_the_same_id_uses_the_canonical_name_for_readme`; cached metadata/README are bound to the verified numeric repository ID |
| Off-origin redirects | `test_same_origin_redirect_is_followed_with_the_worker_credential`, six off-origin cases (scheme, host suffix, userinfo, protocol-relative, wrong port), `test_redirect_hop_limit_is_enforced`, malformed/missing `Location` cases |
| Blob vs commit identity | `test_blob_fetch_requires_a_blob_sha_not_a_branch_or_commit`, `test_blob_fetch_rejects_a_returned_sha_that_differs_from_the_requested_blob`, `test_blob_fetch_decodes_and_validates_the_blob_identity`; only 40-character lowercase file blob SHAs reach `/git/blobs/{sha}` |
| 401/403/429/5xx and Retry-After/reset | Authentication/plain-forbidden stop immediately; long 429/403 waits become `retry_at`; short waits retry; long 5xx waits become `retry_at`; bounded 5xx/network retries; invalid headers are protocol errors |
| Credentials are not forwarded or logged | Redirect targets are validated in a response hook before httpx builds/follows them; the token is only sent to the configured HTTPS API origin. Tests assert the token is absent from errors and captured logs. The reader refuses to start without `ARCHIVE_GITHUB_TOKEN` and does not accept an OAuth secret |
| Typed response and byte accounting | `ArchiveResponse` carries status, URL, headers, body, request ID, ETag, Last-Modified, retry-at and encoded/decoded byte counts; gzip and preloaded/fallback byte counts are tested |
| Long waits do not sleep in a handler | `_wait_or_raise` raises `ArchiveRateLimited`/`ArchiveUnavailable` with `retry_at` when the wait exceeds `ARCHIVE_GITHUB_RETRY_MAX_WAIT`; only short waits use the injected sleep |
| Separate worker credential | New `archive_github_token` and related settings; the existing OAuth `GitHubProvider` and its tests are untouched |

Additional hardening added during GREEN/refactor: cached READMEs are bound to the expected repository ID (an old-name reuse cannot authorize the original cached README); a `403` with `X-RateLimit-Remaining: 0` but no reset becomes a 60-second `retry_at`; terminal status errors carry the typed response so request IDs and validators remain available for diagnosis.

## Limits and handoff

- No live GitHub network call, real repository data, worker, API route, database write, ingestion, scheduling or vector operation. Tests use `httpx.MockTransport` and synthetic payloads.
- The reader is not wired into T06/T09 or any other task. T06 must include endpoint (`ArchiveResponse.url`), fixed media type/API version and the dedicated credential identity in its durable cache key; T04 never exposes the token.
- No production rate-limit budget, real redirect behavior or GitHub API compatibility is claimed from synthetic headers. Required remote CI and a trusted exact-head review remain pending.
- Rollback: revert the T04 code and docs. No schema, data file, lockfile or workflow was changed, so rollback has no migration step. The new settings are inert unless a worker constructs the reader.
- No crawling, clone, arbitrary download URL, user-token harvesting, OAuth behavior change, paid service or gate/security exception is included.
