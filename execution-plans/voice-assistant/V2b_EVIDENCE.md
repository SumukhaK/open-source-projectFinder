# V2b summary card evidence

Status: Merged 2026-11-06 as PR #71 (`29a906e`), after V2a #68; device check open. Base `e51e1e0bf2aff1c0112658a3b6a8a4b159a53b8d`; branch `codex/voice-v2b-summary-card`. Mobile only, must merge after V2a PR #68. Contract inspected at `f3fc72a0d875e52b93fac4f92d7db34951eb8f91`: POST full_names (up to 10), summary/text and done/grounded SSE events. No backend changes.

Plan: RED integration tests for list-first rendering, bounded identity-only requests, streaming and fail-closed/cancellation behavior; minimal streaming transport and themed card; GREEN/full mobile gates; merge latest main, one PR, stop. Summary has no animation (including with Reduce Motion); polite completion announcement only. No speech output, storage or provider calls.

Source: Expo streaming fetch documentation https://docs.expo.dev/versions/latest/sdk/expo/ and installed SDK 57 types. The existing voice transport already uses expo/fetch.

## Verification and design

RED: nine new discovery integration tests failed with zero summary HTTP calls against the existing screen. GREEN: 85 focused tests passed after implementing the card and transport. Additional tests cover late first-page responses after navigation and restored-cache/empty-result suppression. Fake fetch/reader tests exercise split UTF-8 bytes, CRLF framing, identity-only payload/auth headers, malformed events, missing completion, size caps and aborted/late responses. No provider or live backend summary request was made.

Summary fetch starts in the card effect after the list commit. A separate first-page sequence is invalidated on cancellation without affecting pagination. Account/session identity gates visibility. Text stays in component state; no cache/schema changes. The SSE response is bounded to 32 KiB and text to 8,000 characters; a 20-second total deadline includes fetch and reading. These fail closed independently of search. The backend at the inspected PR head buffers and validates the provider result before sending summary chunks; the mobile card follows that contract and hides any partial text on a negative done event or error.

The card uses existing light/dark theme tokens and no animation, so Reduce Motion needs no separate motion branch. Completion uses a queued accessibility announcement once; streaming text is not a live region. No speaker button/output belongs in V2b.

Limits: `adb devices -l` returned no devices. No native development-build light/dark, TalkBack/VoiceOver or real SSE integration was run. JS exports and fakes do not prove native streaming/accessibility behavior. V2a PR #68 remains OPEN at `f3fc72a0d875e52b93fac4f92d7db34951eb8f91` on the pre-delivery recheck. Do not merge V2b before #68. No backend, dependencies, lockfiles, CI gates or other tracker rows changed.

Final verification (Windows, 2026-11-06): `RUN_AUTH_E2E=1 npm run test:coverage` passed **182 tests, zero skipped** with unchanged coverage gates; `npm run typecheck`, `npm run lint`, `npx expo export --platform all` (Android/iOS/web) and `git diff --check` passed. Auth E2E used the existing local fake provider and Python venv. Export emitted the existing NO_COLOR/FORCE_COLOR warning only. Latest origin/main was fetched and `git merge --no-ff origin/main` reported already up to date at base `e51e1e0bf2aff1c0112658a3b6a8a4b159a53b8d`. Implementation head: `14fae9a57c29284ee65a8e4ba85ad54a1cb1ebb5`; subsequent changes record delivery documentation only.

PR: [#71](https://github.com/SumukhaK/open-source-projectFinder/pull/71). Awaiting review; must merge after #68. The final documentation commit adds this link and test counts to the V2b row only.
