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
- the pinned **E5** model available offline, reachable and validated by `FusedRevalidator`,
- **Milvus** reachable and empty or populated,
- `ARCHIVE_GITHUB_TOKEN` (worker-only) configured.

Otherwise every search returns `{"detail": {"code":"SEARCH_UNAVAILABLE", "message":"Search is starting or unavailable."}}` (503), and even hub finding will fail until the missing item is provisioned.

### Verification steps

1. Ensure the backend server is running with the v1 route registered.
2. Call `GET /v1/archive/status` (authenticated) and confirm it returns the current `generation`, `status` and, if configured, `coverage`.
3. Issue one authenticated search: `POST /v1/projects/search` with body `{idea: "dotnet"} `{page_size: 20}`; assert 200 and that the response contains `next_cursor` (or `null`) and `has_more`, plus `total: null`, `degraded` and `source_health`. If 503 `SEARCH_UNAVAILABLE`, supply the missing runtime conditions and repeat until the route works.
4. Test cursor paging: `POST ...{cursor: "<from previous">}` to confirm subsequent pages until `has_more: false`.

### Rollback procedures

Revert **this PR's merge commit** (`e934ed2`) with `git revert HEAD`. This restores the legacy POST endpoint `/projects/search` only; the older build does not attempt to parse v2 envelopes so it naturally ignores the new caches, and favourites are not touched. Because the transport reverts to `page`-based pagination, a user's restored page will re-offer "Load more" with `page` arithmetic and will not see the v1 `has_more` semantics; users must search again to go forward.

## Local verification in this change

- RED test run on the original v1 contract gaps: 33 failing tests across 3 suites confirmed the exact v1 requirements.
- GREEN discovery suite: 66 tests pass, a full suite run 98 passed / 1 skipped. Coverage gates pass: **95.24% statements**, **86.23% branches**, **94.73% functions**, **99.54% lines** (mobile thresholds from `.ci/quality-policy.json`).
- `npm run typecheck`: passed
- `npm run lint`: passed with zero warnings
- `npx expo export --platform all`: passed for Android, iOS, Web
- `git diff --check`: clean
- Changed-file secret scan: only fixture names (`cursor-secret`, `token="session"`), no real secrets
- CI run `41757416542` passed all six required checks (Backend quality, Dependency audit, Mobile quality and E2E, Secret scan, GitGuardian, Quality gate)
