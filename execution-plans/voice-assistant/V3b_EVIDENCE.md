# V3b spoken summary evidence

Status: Awaiting review; merge only after V3a. Base `2d522ea07678a40a7f694b786be65dc619c8beb3`; branch `codex/voice-v3b-spoken-summary`. Mobile only; V3a is built separately and must merge before V3b.

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
