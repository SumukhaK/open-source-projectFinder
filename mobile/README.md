# RepoRadar mobile

Expo / React Native / TypeScript client with the Bracket Navigator identity.

## Run locally

```sh
npm ci
npm start
```

Open on an iOS or Android device with the matching Expo Go version, or use a development build. `npm run web` runs a browser preview. No backend or API key is needed for the branding screen.

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
- `src/features/branding/components`: the branding preview screen.
- `src/components`: shared vector mark and accessible animated loader.
- `src/hooks`: platform accessibility hooks.
- `src/lib`: theme state and preference resolution.
- `src/config/branding.ts`: central colors, geometry, animation settings and storage key.
- `assets/branding`: generated SVG masters and native PNG exports.
- `scripts`: repeatable asset generation from shared geometry.

Shared code cannot import features or the app; features cannot import the app. Compose future features at the app layer; avoid feature-to-feature imports. Create only folders needed by each feature.

## Implemented

Saved System / Dark / Light appearance selection; adaptive Android and light/dark/tinted iOS icon assets; themed Android splash; minimal iOS launch background; and a shared Bracket Navigator loader with a pulsing needle, accessible loading status, and a static Reduce Motion fallback. The loader stops when unmounted. The preview button demonstrates loading without pretending to perform a search.

Native splash uses the OS appearance at launch; a saved in-app override is applied after JavaScript restores preferences. There are no artificial launch delays. Native asset changes require rebuilding the app binary. Expo Go and web previews cannot validate release splash screens.

## Device checks still required

Build release binaries for both platforms and check launcher masks, native splash behavior, theme changes, screen reader output, Reduce Motion, font scaling, and startup on devices. iOS compilation needs macOS or a configured cloud build; this repository does not contain signing credentials or store identifiers. Search and voice features are pending.

## Dependency audit

Initial npm audit: 13 inherited Expo tooling advisories (9 moderate, 4 high), rooted in uuid and node-forge. No patched node-forge release was available when checked. Do not apply npm audit fix --force blindly: its suggested Expo downgrade is incompatible with this SDK. Reassess upstream fixes before signing or shipping a release.
