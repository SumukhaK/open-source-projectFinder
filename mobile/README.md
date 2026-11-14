# RepoRadar mobile

Expo / React Native / TypeScript client with the Bracket Navigator identity.

## Run locally

```sh
npm ci
npm start
```

Open on an iOS or Android device with the matching Expo Go version, or use a development build. `npm run web` runs a browser preview. The sign-in screen can be previewed without backend credentials. GitHub login needs the configured backend and an iOS/Android development build; Expo Go and web are visual previews only.

## Verification

```sh
npm test
npm run typecheck
npm run lint
npm run assets:generate
npx expo-doctor
npx expo export --platform all
```

## Architecture

Adapted from [Bulletproof React](https://github.com/alan2207/bulletproof-react/blob/master/docs/project-structure.md):

- `src/app`: app entry and provider composition.
- `src/features/auth`: login page, API flow and secure session storage.
- `src/features/discovery`: authenticated idea search, project details, favourites and account-scoped local cache. The signed-in screen has a Home/Profile bottom bar: Home holds search and results; Profile holds the account, favourites, settings (appearance and voice) and about/privacy.
- `src/features/branding/components`: preserved branding preview component.
- `src/components`: shared vector mark and accessible animated loader.
- `src/hooks`: platform accessibility hooks.
- `src/lib`: theme state and preference resolution.
- `src/config`: centralized branding, public authentication and discovery configuration.
- `assets/branding`: generated SVG masters and native PNG exports.
- `scripts`: repeatable asset generation from shared geometry.

Shared code cannot import features or the app; features cannot import the app. Compose future features at the app layer; avoid feature-to-feature imports. Create only folders needed by each feature.

## Implemented

Saved System / Dark / Light appearance selection; adaptive Android and light/dark/tinted iOS icon assets; themed Android splash; minimal iOS launch background; and a shared Bracket Navigator loader with a pulsing needle, accessible loading status, and a static Reduce Motion fallback. The loader stops when unmounted. The sign-in page uses this loader while restoring, signing in or signing out.

Discovery uses the legacy `GET /projects/{owner}/{name}` details and favourites routes, while search itself calls the hybrid `POST /v1/projects/search` through the same single zod-validated transport. The v1 request sends `{idea, page_size, cursor?, filters?}` only (extra fields are forbidden client-side; `page_size` is capped at the server's 50 and defaults to 20); the response schemas cover `items[]`, `next_cursor`, `has_more`, `total: null` (a numeric total means the payload is not v1 and is rejected), `degraded`, per-source health and ranking metadata. Typed error envelopes (`{code, message, retryable}`) map to explicit states: `SEARCH_INCOMPLETE` says results may be partial and never "no matches"; `SEARCH_BUSY`/`SEARCH_TIMEOUT`/`SEARCH_UNAVAILABLE` are retryable notices; `CURSOR_EXPIRED`/`CURSOR_INVALID` drop the cursor, keep the idea and ask the user to search again; 429 honours `Retry-After`; 401 returns to sign-in. Paging is cursor-based "Load more" shown only while `has_more` is true; total is never displayed. Cards show the licence, hide the archive snippet when the archive licence conflicts with the live licence, show the freshness/source label and render snippets under a "README excerpt" label (also read by screen readers); degraded searches show a source-unavailable notice. Search results are cached per GitHub account under a versioned (`version: 2`) AsyncStorage envelope: legacy page-based snapshots fail the schema and are dropped without touching favourites, and `next_cursor` is stripped on save/restore so it never survives an app restart (a restored page always says "search again to load more"). Raw idea text is never persisted. Favourite changes stay optimistic with rollback, and stale search/load-more/details responses are ignored via request sequences (the cache restore is also sequence-guarded, so a search started before storage resolves wins). Results render as one combined list (T25): partial searches name the source that did not respond, a partial search with zero results offers Try again and never says "no matches", only a complete healthy empty search says no projects matched, cached results always show a stale banner, and pull to refresh on Home results starts a new search for the current idea. Late responses after sign-out or unmount never write the cache. Known limits: no device, light/dark visual inspection or live-hybrid run has been performed (T26 owns real HTTP).

Operator steps, rollback, and migration evidence for this change are in [T24_EVIDENCE.md](../execution-plans/hybrid-search/T24_EVIDENCE.md).

Native splash uses the OS appearance at launch; a saved in-app override is applied after JavaScript restores preferences. There are no artificial launch delays. Native asset changes require rebuilding the app binary. Expo Go and web previews cannot validate release splash screens.

## Device checks still required

Build release binaries for both platforms and check launcher masks, native splash behavior, theme changes, screen reader output, Reduce Motion, font scaling, and startup on devices. iOS compilation needs macOS or a configured cloud build; the app identifier is `com.sumukhak.reporadar` (Android package and iOS bundle ID); the repository contains no signing credentials. `npx expo prebuild` output (`android/`, `ios/`) is generated and git-ignored. Voice capture is implemented but still needs native device validation; the hybrid `/v1` search path and real account search against a live backend have not been run on a device in this change (T26 owns the real HTTP check).

## Dependency audit

Initial npm audit: Initial scan had 13 inherited Expo tooling advisories. UUID is now overridden to patched 11.1.1; node-forge is locked at the patched 1.4.2 (within Expo's `^1.3.3` range), so it needs no exception. deepmerge 4.3.1 (GHSA-gcqx-w48m-w2h4, low, no patched release) has an exact exception expiring 2026-12-31 in `.ci/quality-policy.json`; it is used only by `@expo/config` and `jest-config` and is not in the exported app bundles. Do not apply npm audit fix --force blindly: its suggested Expo downgrade is incompatible with this SDK. Reassess upstream fixes before signing or shipping a release.

## Authentication setup and end-to-end checks

Copy `.env.example` to ignored `.env` and set `EXPO_PUBLIC_API_URL` to your reachable HTTPS backend. This is a public URL, never a GitHub secret. The native callback is `reporadar://auth/callback`; the backend allowlist must include it. Register GitHub's callback to the backend URL, not the device scheme. Configure native bundle/package identifiers and build with the project's Expo SDK before device validation. Rebuild after scheme/native-plugin changes. See [backend setup](../backend/README.md).

Authentication follows system/saved appearance and provides System/Dark/Light controls. Native tokens use SecureStore; no tokens use AsyncStorage. Browser login is outside this mobile phase.

Run the real HTTP cross-layer test after installing backend dependencies:

```powershell
$env:RUN_AUTH_E2E='1'
npm test
Remove-Item Env:RUN_AUTH_E2E
```

On Unix: `RUN_AUTH_E2E=1 npm test`. The test launches a temporary FastAPI server using backend/.venv by default; set `PYTHON_EXECUTABLE` to override. Only GitHub, native browser and device storage are simulated.

## Quality pipeline

Use `npm run test:coverage` for enforced application coverage, `npm run lint` for lint and security rules with zero warnings, and `npm run typecheck`. Shared theme access avoids untrusted dynamic lookup. The root crash boundary provides themed retry and sanitized local reporting. See [pipeline documentation](../docs/QUALITY_PIPELINE.md) for thresholds, audits, free-runner boundaries and review-controlled merging.

## Voice input (V1b, merged; device check open)

Home has a hold-to-record mic beside the editable idea. Consent precedes system microphone permission; release shows “We heard” before starting the existing search. Slide away or use Cancel to discard; capture stops at 30 seconds. Permission denial and provider errors keep typed search available. Profile > Voice shows microphone status, phone settings and How voice works. Consent is account-scoped and cleared on sign-out.

SDK 57 expo-audio records HIGH_QUALITY AAC/M4A; expo-file-system reads and removes the cache clip, expo-haptics provides start feedback, and expo/fetch sends raw audio/m4a to the authenticated backend. No provider key belongs in the app. Voice configuration lives in src/config/voice.ts. Native plugin changes require rebuilding; background recording is disabled. Web offers typed search only. Tests cover permission/release, cancellation, background, sign-out, unmount and late-upload races using fakes.

See [V1b evidence](../execution-plans/voice-assistant/V1b_EVIDENCE.md) for RED/GREEN, coverage and export results. Native light/dark, accessibility and release-to-transcript latency checks remain outstanding because no development-build device was connected. A failed filesystem delete is surfaced to the user; abrupt process death is not a guaranteed cleanup path.

## Result summary (V2b, merged #71)

After a fresh first page renders, a separate authenticated SSE request sends only its first ten full_names to `/v1/projects/search/summary`. The static, theme-aware Summary card has an AI tag and “Based only on the results below”; chunks render as received and a polite accessibility announcement occurs once on grounded completion. No summary request is made for empty results, cached results or later pages. The list never waits for, changes with, or persists the summary.

New search, navigation, sign-out, backgrounding and unmount cancel the summary; stale responses cannot restore it. Errors, ungrounded completion, missing completion, oversized output and the 20-second deadline hide the card. Limits live in discoveryConfig. No new dependencies, animation or spoken output. Text is memory-only and never logged. Native light/dark and screen-reader checks remain unrun (no device connected). This mobile PR must merge after backend PR #68; until that endpoint exists, summaries silently remain absent.

## Spoken summaries (V3b, merged #73)

Profile > Voice includes Read summaries aloud (default on, per account, removed on sign-out). Only the immediate search from a voice transcript can auto-speak; typed/edited submissions, retries and refreshes do not. Auto-play waits for a grounded summary_id, loaded preferences, an active app and a fresh screen-reader check. Any grounded summary with an ID also has a 48-dp Read aloud/Stop button, independent of that setting.

Expo Audio streams the authenticated summary-ID URL with downloadFirst false and silent-mode playback disabled. The app never sends summary text to the speech route or writes audio files. New search, leaving Home, background, sign-out, summary cancellation and unmount stop/release playback. Provider/native errors leave the text and list intact without alerts or retry loops. A content-free per-account tip flag remembers the first successful auto-play across sign-outs; the playback setting itself is cleared.

V3b merged after V3a (#74). See [V3b evidence](../execution-plans/voice-assistant/V3b_EVIDENCE.md) for tests and platform limits. Native streaming, silent mode, accessibility, light/dark and latency checks are deferred to the separate Android development-build step; no device run is claimed here.

Voice permission results are handled after a released hold: denial opens the settings sheet, while a grant updates microphone status without starting a recording. The user must hold again to record; explicit cancellation still discards the pending result.

First-page searches stay locked across up to two quiet retries for retryable 503 `SEARCH_UNAVAILABLE` / `SEARCH_INCOMPLETE` errors. Retry-After (seconds or HTTP date) is clamped to 1–10 seconds; missing/invalid values use 2 then 4 seconds. The loader names the retry wait, and refresh, Retry and voice cannot start or queue another search during it; a transcript that arrives mid-search only fills the box. Typing never cancels or unlocks a search. Leaving Home, opening details or backgrounding stops only a pending retry wait (showing "Search was interrupted. Try again." with Retry); a request already in flight still delivers its results. Sign-out, account/session changes and unmount cancel silently and ignore late responses. Only `background` blocks searching, so a `null`/`unknown`/`inactive` AppState at launch does not. After exhaustion, the existing error and Retry button return. Successful partial/degraded results, rate limits/429, 401/403, offline/network failures, load-more and summaries never auto-retry; offline consent behavior is unchanged.
