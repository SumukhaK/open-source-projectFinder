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
- `src/features/discovery`: authenticated idea search, project details, favourites and account-scoped local cache.
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

Discovery uses the merged legacy `POST /projects/search`, `GET /projects/{owner}/{name}` and favourites routes through one zod-validated transport module. Results show name, description, stars, language and licence; because the legacy item payload has no licence field, the UI says “Licence not reported” instead of inventing one. Search exposes loading, empty, incomplete (“results may be partial”), rate-limited (honouring `Retry-After`) and generic error states, with page-based load more. Details and favourites use the favourites routes; favourite changes are optimistic and roll back on failure. The last results and favourites are cached per GitHub account in AsyncStorage and cleared on sign-out or account switch. Raw idea text is never persisted. This feature does not call `/v1/projects/search`.

Native splash uses the OS appearance at launch; a saved in-app override is applied after JavaScript restores preferences. There are no artificial launch delays. Native asset changes require rebuilding the app binary. Expo Go and web previews cannot validate release splash screens.

## Device checks still required

Build release binaries for both platforms and check launcher masks, native splash behavior, theme changes, screen reader output, Reduce Motion, font scaling, and startup on devices. iOS compilation needs macOS or a configured cloud build; this repository does not contain signing credentials or store identifiers. Voice capture and hybrid `/v1` search are pending; authenticated live GitHub search has not been run on a device in this change.

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
