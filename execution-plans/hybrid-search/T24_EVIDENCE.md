# T24 Evidence — hybrid v1 mobile transport and cache migration

Base: `origin/main` `b0b9281d9...` (contains merged T15 `f5da7c7` and P2 `1a67d63`).
Branch: `codex/hybrid-t24-mobile-contract` from base.
Every change belongs to this PR; no shared refactor or speculative abstraction was landed.

## Summary

The mobile discovery transport is now bound to `/v1/projects/search` with strict zod schemas, typed FastAPI error envelopes (`{code, message, retryable}`), and versioned AsyncStorage results (`version: 2`). Legacy page payloads and `next_cursor` are never stored; cache restoration is guarded by the search sequence ref. Details and favourites remain on the legacy routes.

## Operator steps and rollback

### Before shipping this build

The backend **must** have:

- `HYBRID_CURSOR_SIGNING_KEY` configured with ≥ 32 random characters (stored in an ignored `.env` by the operator),
- **EmbeddingAdapter** loads the pinned **E5** model (offline, validated at startup),
- **FusedRevalidator** performs live rechecks (it does not load the embedding model),
- **Milvus** reachable (empty or populated); `GET /v1/archive/status` does not prove Milvus reachability,
- `ARCHIVE_GITHUB_TOKEN` (worker-only) configured.

Otherwise every search returns `{"detail": {"code":"SEARCH_UNAVAILABLE", "message":"Search is starting or unavailable."}}` (503), and even hub finding will fail until the missing item is provisioned.

### Verification steps

1. Ensure the backend server is running with the v1 route registered.
2. Call `GET /v1/archive/status` (authenticated) and confirm it returns the current `generation`, `status` and, if configured, `coverage`. Note: this does **not** prove Milvus is reachable.
3. Issue one authenticated search: `POST /v1/projects/search` with body `{ "idea": "dotnet", "page_size": 20 }`; assert 200 and that the response contains `next_cursor` (or `null`), `has_more`, `total: null`, `degraded`, and `sources` (per-source health). If 503 `SEARCH_UNAVAILABLE`, supply the missing runtime conditions and repeat until the route works.
4. Test cursor paging: `POST /v1/projects/search` with body `{ "idea": "dotnet", "page_size": 20, "cursor": "<from previous>" }` to confirm subsequent pages until `has_more: false`.

### Rollback procedures

On `main`, revert **this PR's squash-merge commit** by its SHA (not `git revert HEAD` on the feature branch). The P2 mobile foundation build restores the legacy `POST /projects/search` endpoint; it does **not** restore any results cache — the older build ignores v2 envelopes (they fail its schema), and favourites are unaffected. Users simply search again.

## Local verification in this change

- RED test run on the original v1 contract gaps: 33 failing tests across 3 suites confirmed the exact v1 requirements.
- GREEN discovery suite: 66 tests pass, a full suite run 98 passed / 1 skipped. Coverage gates pass: **95.24% statements**, **86.23% branches**, **94.73% functions**, **99.54% lines** (mobile thresholds from `.ci/quality-policy.json`).
- `npm run typecheck`: passed
- `npm run lint`: passed with zero warnings
- `npx expo export --platform all`: passed for Android, iOS, Web
- `git diff --check`: clean
- Changed-file secret scan: only fixture names (`cursor-secret`, `token="session"`), no real secrets
- CI run `41757416542` passed all six required checks (Backend quality, Dependency audit, Mobile quality and E2E, Secret scan, GitGuardian, Quality gate)

## Migration evidence

The test `a search started before the cache restore wins over the cached page` (in `mobile/tests/discovery-screen.test.tsx`) proves that a legacy snapshot is dropped while favourites survive. The test sets up a pending cache load, starts a fresh search, then resolves the cache with a different item — the fresh search result wins and the stale cached item never appears; favourites are loaded from a separate cache key and are unaffected.
