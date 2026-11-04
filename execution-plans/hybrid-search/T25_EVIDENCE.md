# T25 Evidence — one combined result list with truthful states

Base: `origin/main` after the U14 runtime fix (PR #57). Production change: `mobile/src/features/discovery/components/discovery-screen.tsx`; tests in `mobile/tests/discovery-screen.test.tsx`. No backend, transport or cache-schema change.

## Summary

- One search action and one list. GitHub-only, archive-only and common projects render as the same card type with their freshness/source label; there is no source tab, mode selector or match percentage.
- Partial searches are named honestly. When results exist but a source failed, the screen says "Some sources were unavailable. Results may be incomplete." and adds which source did not respond. When a partial search has zero results it says "No results could be confirmed because a source was unavailable." and offers **Try again**; it never says "no matches".
- Only a complete search (not degraded, both sources `ok` and not incomplete) with zero items says "No projects matched your idea. Try different keywords."
- A failed search offers **Try again** with the same idea. Cursor expiry keeps the T24 behaviour (cursor dropped, idea kept, "search again").
- Cached results always carry a stale banner: "Showing your last results. Search again to load more." when more pages existed, otherwise "Search again for fresh results."
- Pull to refresh starts a new hybrid search for the current idea. It is offered only on Home results with a live idea, not on Favourites, not while details are open and not during load-more. The current list stays visible while refreshing. The UI never triggers corpus ingestion.
- Sign-out and unmount bump a session sequence, so a search or favourite response that arrives later cannot write the results cache or roll back state for the next account.

## Operator steps and rollback

No operator step: the build talks to the same `/v1/projects/search` route and the same `version: 2` cache as T24. Rollback is a revert of this PR's squash-merge commit on `main`; the T24 screen reads the same cache, so users keep their cached results and favourites.

## Local verification

- RED: 9 of the new screen tests failed against main's screen (missing source detail, retry, refresh, stale banner without more pages, post-sign-out and post-unmount cache writes).
- GREEN: 51 screen tests pass; full mobile suite 110 passed / 1 skipped. Coverage 95.47% statements, 87.42% branches, 95.08% functions, 99.58% lines (gates in `.ci/quality-policy.json` held).
- `npm run typecheck` and `npm run lint` clean (zero warnings); `npx expo export --platform all` passed; `git diff --check` clean; changed-file secret scan found only fixture names.

## Limits

- The GREEN criterion asks for a real mobile-sized light/dark UI inspection. It was **not performed**: signing in needs a live backend and OAuth, which this environment does not have. Accessibility is covered by tests only (partial-search notices use the alert role, Try again is a labelled button with the existing button style, and the refresh control has a label). T26 owns the real-HTTP run and should include this inspection.
- The task mentions hold-to-talk, voice races and offline consent. Those features do not exist in the app yet, so there was nothing to preserve or test; background and account-cleanup races are covered by the session-sequence tests above.
