# V3b spoken summary evidence

Status: Merged 2026-11-07 as `a4b7b8c` (#73), after V3a #74; device check open. Base `2d522ea07678a40a7f694b786be65dc619c8beb3`; branch `codex/voice-v3b-spoken-summary`. Mobile only; V3a is built separately and must merge before V3b.

Plan: RED UI/lifecycle and SSE contract tests, then minimal account-scoped preferences and authenticated native playback, then full mobile verification and one PR. Reuse expo-audio 57.0.5; installed AudioSource declares headers?: Record<string,string>, createAudioPlayer accepts that source, and downloadFirst defaults false. No dependency or backend changes. No Docker, model, native build or live provider call.

Origin rule: only the immediate automatic search after transcription is voice-originated. Typed submit (including edited transcript), retry and refresh do not auto-speak. The manual control is available for any grounded summary with a nonempty summary_id.

Source: https://docs.expo.dev/versions/v57.0.0/sdk/audio/ plus installed declarations/source. playsInSilentMode false suppresses Android silent/vibrate ringer modes per SDK 57 docs; native behavior still needs later device verification.

## RED / GREEN (2026-11-07)

- RED: spoken-summary integration tests reported 10 failures (no native player, no manual control and no setting) and 5 pre-existing no-speech guards passed. The SSE contract test failed because completion returned text without the new ID.
- GREEN: all 16 selected speech/contract tests passed. Extended checks cover pending accessibility/audio-mode promises after cancellation, preference-write/sign-out ordering, native failures, storage failures and stalled playback. The unmount race test initially resolved audio setup inside the same React act as unmount, before cleanup committed; moving unmount outside that act tested the intended completed-unmount boundary and passed.
- Full coverage suite: **204 passed, zero skipped**, including the existing fake-provider authentication E2E. Coverage gates unchanged. No live speech calls or keys used.

## Implementation

Read summaries aloud defaults on but auto-play waits for account preferences to load; a storage read failure disables auto-play for that session. The preference is stored as `reporadar.voice.<account>.readAloud`, persists across unmount and is removed on sign-out after pending writes finish. Manual playback ignores the preference and screen-reader auto-play guard, but still requires an active app and a grounded completion ID.

The one-time tip is marked only on native `playing: true`, not when a request is merely attempted. Its content-free per-account `speechTip` flag persists across sign-outs so the same account is not tipped again. No summary text, audio or ID is persisted. The existing signed-in bearer header accompanies the encoded ID URL; no request body or audio-file fallback exists. `downloadFirst: false` avoids Expo's explicit temporary-file download path.

The existing summary component lifetime and search sequence stop and release playback on cancellation/navigation. The player also stops on background, sign-out, unmount, native error or completion; delayed accessibility/audio-mode promises check an invalidated sequence before creating a player. A 120-second maximum bounds stalled loading/playback. Native 404/503/429 failures all degrade silently through the player error event; the native player does not expose the JSON error body to JS, so the app neither displays server messages nor retries automatically. The text summary and result list remain independent.

## Limits / platform evidence

Installed `expo-audio` 57.0.5 declares `AudioSource.headers`, accepts that source in `createAudioPlayer`, and exposes `AudioStatus.error` / `didJustFinish`. Playback uses `playsInSilentMode: false`, `shouldPlayInBackground: false`, `allowsRecording: false` and `interruptionMode: doNotMix`. SDK 57 Android source checks AudioManager ringer mode and suppresses playback in silent/vibrate modes when playsInSilentMode is false; iOS uses its native audio session. Device behavior, volume/DND/headset routing and header delivery still require the separately scheduled native check.

Per the owner's resource instruction, no Docker, Ollama, Gradle or development build ran. Native audio streaming, first-sound latency, silent-mode behavior, light/dark UI and TalkBack/VoiceOver are **not verified on device**. Exports are JS bundle checks only. V3a was not yet an open PR at the implementation recheck; this uses the owner's supplied contract and must not merge before V3a. Until IDs appear in grounded done events, text works without speech controls. No backend, lockfile, dependency or CI gate edits.

Final checks on Windows (2026-11-07): `RUN_AUTH_E2E=1 npm run test:coverage` (204 passed, no skips; unchanged coverage gates), `npm run typecheck`, `npm run lint`, `npx expo export --platform all` (Android/iOS/web), and `git diff --check` passed. Only the existing NO_COLOR/FORCE_COLOR export warning was emitted.

Delivery: [PR #73](https://github.com/SumukhaK/open-source-projectFinder/pull/73), implementation head `d05c49a52349bc934e00f90f2968c32f3b6cc050`; the following documentation-only commit links the PR. Latest origin/main merge check was already up to date at the recorded base. Awaiting review, not accepted; must merge after V3a.

## PR #73 review fixes (2026-11-07)

RED: four regression cases failed before implementation: mic press-in did not pause/release speech, completion and native errors during iOS inactive did not release the player, and the first-play tip disappeared on completion. GREEN: the four focused cases passed. The mic regression asserts both pause and release happen before the new recorder's record() invocation. The same wrapped start function handles accessible recording actions.

The current player's finish/error events now stop playback before the active-state gate; a player-identity guard prevents a late old-player event from stopping a replacement. Ordinary stop/completion preserves the visible tip, while a new search/summary cancellation or sign-out clears it. The persisted seen flag still prevents showing it on subsequent searches. Copy is now “Turn this off in Profile › Voice”.

Full mobile coverage run: **207 passed, zero skipped**, including fake-provider auth E2E; unchanged coverage gates passed. No backend, dependency, lockfile or CI changes. No Docker/Ollama/Gradle or device run; native recording/playback arbitration and platform behavior remain for the separate device check.

Review-fix verification also passed: `npm run typecheck`, `npm run lint`, `npx expo export --platform all` (Android, iOS, web), and `git diff --check`. Only the existing NO_COLOR/FORCE_COLOR export warning was emitted.


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

NOT RUN: automatic playback/three first-sound timings, one-time tip, typed manual Read aloud/Stop, mic interrupt, setting off, silent/vibrate behaviour, TalkBack suppression, or stop on search/tab/sign-out/background. No LLM was started. Emulator results would not establish physical-phone audio or latency in any event. Device check remains open.


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
