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


## Device check — 2026-11-07 (blocked)

Base: `553c4529239b7c1718a94159a00e1e4880db82ef`, branch
`codex/voice-device-check`. Owner requested a virtual device after ADB found no
physical phone. Created `RepoRadar_Device_Check`: Pixel 5 hardware profile,
Android 15/API 35 Google APIs x86_64, 2 GiB RAM, WHPX acceleration. ADB reported
`emulator-5554` connected and `sys.boot_completed=1`.
[Emulator readiness screenshot](evidence/2026-11-07-emulator-ready.png) shows
only Android Home, **not RepoRadar**.

Build type attempted: local Android development/debug build. Locked `npm ci`
completed. Reproduction on unchanged main: from `mobile`, run
`CI=1 npx expo prebuild --platform android --no-install`. Expo reports:
`Cannot automatically write to dynamic config at: app.config.ts` and requests
an `android.package` value (it suggests `com.anonymous.reporadar`). The current
dynamic config has no package identifier. No APK was built or installed.
No feature/configuration fix was made in this docs-only run. A separately
reviewed native package configuration is needed before retrying.

Laptop available RAM: 5.69 GiB before preparation, 5.44 GiB during SDK setup,
3.17 GiB with the emulator running, 6.10 GiB after shutdown. Stopped the idle
Ollama server; no model was loaded. Codex tool processes were preserved. No
Docker containers, Gradle build/daemon or Metro server were started. Emulator
was stopped after capturing readiness; its AVD remains installed for reuse.

NOT RUN: list-before-card ordering, AI/grounding labels, native streamed text, light/dark, TalkBack announcement, and loss of Ollama leaving the list intact. No LLM was started. Device check remains open.


## Device check — 2026-11-07/08 retry (partial; not accepted)

Base `9b8272fc801ad332f3a3a47dd89a8c9c7c2cb205`; branch
`codex/voice-device-check-retry`. Android 15/API 35 Google APIs x86_64 emulator,
Pixel 5 profile, 2 GiB configured RAM. Local debug APK, not Expo Go or a physical
phone. The merged package-identifier fix allowed Expo prebuild to finish.

First Gradle build was deliberately stopped when available RAM reached 0.70 GiB.
The retry used one worker, a 1 GiB heap, 384 MiB metaspace, in-process Kotlin and
x86_64 only; it succeeded in 2m 7s (225 tasks: 23 executed, 202 up-to-date).
Gradle stopped afterward. APK size: 56,038,718 bytes.
APK SHA-256: `26a47be13d16e6708092dc098c2728dc188516d4b1df8b702da310721e5ff595`.

Metro required IPv4-first localhost resolution for ADB reverse; it then bundled
1020 modules and the installed app launched. Backend ran current-main modules
from the original checkout holding the ignored `.env`, with LLM disabled and
a process-only random hybrid signing key. No key was copied or printed. The
owner completed normal GitHub login; no test-session bypass was used. On Nov 8
the saved session was rejected, and normal browser sign-in restored it.

RAM: 4.79 GiB at the Nov 7 retry start, 0.70 GiB at the deliberate build stop,
8.23 GiB after build-process cleanup. Nov 8 restart: 5.14 GiB; during checks
about 2.3–2.7 GiB; final cleanup: 5.81 GiB. WhatsApp and NVIDIA Overlay were
closed during the build attempt; active coding sessions were preserved. The
emulator, task-owned Metro and backend were stopped at the end; Android night
mode was returned to auto. No Docker or Ollama workload was started in this
retry. No feature, dependency or configuration changes are included.

Phase B was NOT RUN: recording interaction remained unresolved and available
RAM with the emulator was insufficient for the planned 5–6 GiB Ollama model.
No summary ordering, automatic/manual playback, first-sound latency, silence,
TalkBack, tip persistence, cancellation or Ollama-failure outcome is claimed.
The Voice settings screen and its default enabled switch were visible; see the
[V1b retry evidence](V1b_EVIDENCE.md). That does not establish playback behaviour.
Device status remains open.
