# P3: Home/Profile navigation and settings

Status: Merged 2026-11-05 in [PR #62](https://github.com/SumukhaK/open-source-projectFinder/pull/62) (`4ea0659`). Implementation, verification and visual-check limits are recorded in [evidence](../P3_EVIDENCE.md). Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/mobile-p3-home-profile` |
| Prerequisites | T25 merged; UX1 decided |
| Intended scope | mobile navigation, a Profile screen, existing discovery/appearance components, tests and docs |

Read first: [voice UX](../../../docs/VOICE_UX.md) (UX1), [plan rules](../README.md), the hybrid [EXECUTION_GUIDE](../../hybrid-search/EXECUTION_GUIDE.md), and the current discovery screen and tests.

## Copy-ready execution prompt

```text
Execute P3 only. Follow AGENTS.md, execution-plans/hybrid-search/EXECUTION_GUIDE.md
and execution-plans/voice-assistant/README.md. Verify T25 is MERGED into main; stop
if missing. Read current code/tests before editing. Fetch origin main and create
branch codex/mobile-p3-home-profile FROM origin/main; record base SHA.
Minimum complete, human-readable code, existing patterns first, no new navigation
library unless the existing structure cannot do it, no unrelated changes. Write and
RUN failing tests FIRST (RED), implement the minimum (GREEN), then refactor and run
mobile tests/typecheck/lint/export. Update docs and the voice TRACKER to Awaiting
review with actual evidence. Commit, push and RAISE ONE PR AGAINST main. Return PR
URL, full head SHA and verification/limits; STOP AND WAIT FOR REVIEW.
```

## Work and boundaries

Add a bottom bar with **Home** and **Profile** (each at least 48 pt, labelled tabs). Home keeps the idea box, search, notices, results, pull to refresh and inline details. Profile shows the GitHub avatar and @username, **Favourites** (moved from the top segmented tab, still opening details), a **Settings** list with **Appearance** (reuse `AppearanceControls`) and **About and privacy** (plain text: what is stored on the device, what goes to the backend), and **Sign out** at the bottom (moved from the header). Keep every existing behaviour: favourites optimism and rollback, cache restore, sequence guards, sign-out cleanup. No voice code.

## Tests and verification before acceptance

RED: tab switching and selection state, favourites listed and toggled from Profile, details from both tabs, sign-out from Profile clears caches, appearance change persists, accessible names and focus order. GREEN: full mobile suite and coverage gates, typecheck, lint, `expo export`; a real mobile-sized light/dark inspection (or the recorded reason it could not run).

## What counts as acceptable

One search action on Home, Favourites and settings on Profile, no lost behaviour. An independent trusted reviewer must accept the exact current PR head after required checks pass.

## Do not do

No voice, summary or settings that have no feature yet (the Voice row arrives with V1), no redesign of sign-in or branding, no new storage outside the account-scoped pattern.
