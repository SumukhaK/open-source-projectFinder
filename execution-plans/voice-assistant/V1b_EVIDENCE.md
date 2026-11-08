# V1b mobile voice input

Status: Merged 2026-11-06 as [PR #69](https://github.com/SumukhaK/open-source-projectFinder/pull/69) (`85cc192`) after trusted review of head `6e33219`; the owner chose merge-then-check, so device validation is still outstanding and must be recorded here before V2b. Base `6a1c95ccd9739920154ba4ff9f817041ab1850d2`; branch `codex/voice-v1b-mobile`. PR #65 verified MERGED (`f4f4bf3c6b25bd819d932ef106765017012bc877`) and an ancestor of this base.

## Implementation plan

1. RED: add visible consent and voice-settings tests to current discovery screen; add fake-native tests for permission/release races, cancellation, background/unmount/sign-out cleanup, cap, typed errors and transcript/search ordering.
2. GREEN: SDK-matched Expo audio/Haptics/FileSystem; AAC/M4A HIGH_QUALITY preset, cache-only recordings, raw-byte abortable upload. Account-scoped consent, no key or transcript storage. Reuse theme, reduced motion and existing hybrid search. No summary card or backend edits.
3. Verify mobile suite/coverage, typecheck, lint, export and dependency audit. Merge latest main before push, preserve all other tracker rows. Raise one PR and stop. Device-only checks require an actual development build; never equate mocks/export with device evidence.

The consent prompt explains only implemented transcription. Summary generation/output remains later work. The first consent flow requests permission and then asks for a fresh hold, preventing recording after the initiating finger has been released.

Sources: [Expo SDK 57 Audio](https://docs.expo.dev/versions/v57.0.0/sdk/audio/), [Haptics](https://docs.expo.dev/versions/v57.0.0/sdk/haptics/), installed SDK types/source for FileSystem and recorder lifecycle. Existing discovery/account cache patterns and theme tokens are retained.

## RED / GREEN evidence (2026-11-06)

- Initial UI/API RED: 7 failed, 55 skipped against missing controls/inert upload; lifecycle RED: 10 failed against the inert hook. Initial focused GREEN: 72 passed, then 78 as race coverage expanded.
- Regression RED: cancelling a pending upload did not immediately delete the stopped clip; permission status did not refresh after returning from settings (2 failed, 11 passed). Fixed both and reran GREEN.
- Regression RED: the native 30-second cap could already stop capture, so calling stop again prevented upload. Check native isRecording before stopping; GREEN covers that path.
- Final mobile coverage: **152 passed, 1 skipped** (the opt-in auth E2E). Statements 95.64%, branches 87.34%, functions 92.85%, lines 99.40%; unchanged coverage thresholds pass. Tests use fake recorder, file, haptic and HTTP modules; no real speech-provider calls.
- Typecheck, ESLint and the existing npm dependency-policy check passed. Android, iOS and web Expo exports passed.
- The existing optional authentication E2E passed in a focused retry, but combined coverage runs timed out during local backend startup. No backend code, readiness timeout or gate was changed; this local E2E is not claimed consistently green.

## Implementation and dependency notes

AAC/M4A uses the SDK 57 HIGH_QUALITY recording preset; recordings stay in cache and are deleted after upload, cancellation or failed upload. Abort plus operation invalidation prevents late transcripts after sign-out, backgrounding or unmount. A native duration cap and JS timer stop at 30 seconds. Uploads are raw audio/m4a with the session bearer token, bounded to 1 MiB and a 20-second timeout. Typed server errors use fixed UX copy. Transcript text is rendered in the editable idea box before the existing search is scheduled; typed edits can submit another search. No summary or speech-output work is included.

Account-scoped consent is cleared only on sign-out and survives screen teardown/remount. Permission denial retains typed search. Profile includes microphone status and voice help. The animated ring respects Reduce Motion; accessibility actions allow start/finish/cancel without a hold gesture.

Added SDK-matched expo-audio, expo-haptics and expo-file-system. Explicit expo-asset 57.0.21 prevents expo-audio's unrestricted peer from resolving Asset 58, which failed export against SDK 57. Existing dependency policy and exceptions are unchanged. The targeted import/namespace suppression identifies Expo's declared native AudioRecorder constructor; typecheck validates its contract.

## Limits and operator verification

No connected Android device was listed by adb. No iOS host/device or native development build was available. Native microphone capture, permission sheets, gesture arbitration, haptics, light/dark appearance, screen-reader behavior and **release-to-transcript latency remain unverified on device**. Mocks and successful exports are not substitutes. Rebuild the native app after the audio plugin change, configure the reachable HTTPS backend, and check those paths on Android and iOS before release. Web remains a typed-search preview because its recorder format is not the approved AAC/M4A transport.

Normal lifecycle cleanup is tested; abrupt process death or a filesystem deletion error cannot guarantee removal. Deletion failures surface an error. No real clip, transcript or provider key was used or committed in V1b. The V1a saved-clip latency is not a V1b device measurement.

## Delivery

[PR #69](https://github.com/SumukhaK/open-source-projectFinder/pull/69). Implementation and main-merge head: `115ecd26f2f49e98edb14615f6dd9ee1dc2c94b2`. Latest main `2653aba` was merged with a merge commit; its changes were documentation only. The tracker conflict retained every main row except the authorized V1b status update. Backend, root README/PROJECT_TRACKER and the V0 task match main. Final diff whitespace check passed. The following documentation-only commit links this PR; the PR head is authoritative. CI results are available on the PR and are not claimed before completion.

## PR #69 review fixes (2026-11-06)

Code head: `68a8c1f51351a0bd4e78438eda623143d717fe96` (following reviewed head `e90d8d6c7895e8d5454eda9eefe3f866869a8574`). Only the three requested behaviors changed: background cancels, active refreshes permission, inactive is ignored; effect cleanup retains consent while signOut removes it; typing, submit and tab navigation reset “We heard”. Cleanup still cancels the operation and removes the listener.

RED: the inactive/denied-permission regression and same-account remount regression failed with the old code. Typing and tab-change tests reproduced the stale label; after correcting the submit test's button selector, its focused run also failed on the stale label. No production changes preceded these failures. GREEN: full mobile suite **157 passed, 1 skipped** (existing opt-in auth E2E), including background cancellation/deletion and sign-out consent removal. Coverage: statements 95.65%, branches 87.38%, functions 93.33%, lines 99.40%; unchanged gates passed.

Android device check: `adb devices -l` returned an empty device list. The owner's phone was therefore not available to this environment. No development build was made or installed, and no real recording/provider call was attempted. Hold/speak/release, denial-to-settings, slide cancellation, 30-second cap, native light/dark and TalkBack remain **NOT RUN on device**. Release-to-transcript latency is **not measured**. Connect and authorize the Android phone over USB debugging before this manual validation can run; successful JS exports are not a native development build.

Review-fix verification also passed: `npm run typecheck`, `npm run lint`, `npx expo export --platform all` (Android, iOS, web), and `git diff --check`. Export emitted only the existing NO_COLOR/FORCE_COLOR warning. The final docs-only commit records these results; the tracker names the tested code head and the PR carries the full delivery head.


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

NOT RUN: consent/deny/settings, hold/speak/release, editable transcript/search, slide cancel/no upload, 30-second cap, background cancellation, three release-to-transcript measurements, light/dark Home/voice/Profile screens, TalkBack labels/actions. Device check remains open.


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

### Observed checks

- First hold displayed Search by voice with Continue / Not now before Android's
  permission prompt (Nov 7). Development warning overlay needed dismissal.
- Android permission denial was confirmed by the OS. Profile > Voice showed
  Microphone: Off. Open phone settings opened the actual Android app info page.
- Granting microphone access through Android settings changed the app row to
  Microphone: Allowed when returning to RepoRadar.
- Voice settings were visually inspected in light and dark; screenshots contain
  no account name, avatar, token or transcript:
  [light](evidence/2026-11-08-voice-settings-light.png),
  [dark](evidence/2026-11-08-voice-settings-dark.png). The debug warning overlay
  covers the bottom navigation in the dark capture; this is not clean visual
  acceptance of that region. Home was viewed in both modes but not committed
  as a screenshot because it includes the account label.

### Unresolved interaction findings (no code fix)

1. Sign in, hold mic, deny Android permission, then hold again. A second Android
   prompt appeared; after denying it the expected app denial sheet was not
   observed. OS state was granted=false, USER_FIXED; Profile recovery worked.
2. Grant through Profile > Voice > Open phone settings, return Home and hold
   the microphone. Continuous ADB holds of 8 and 12 seconds showed no timer or
   uploading state, including after app restart. Separate DOWN/MOVE/UP injection
   was also inconclusive. A later text-field focus attempt did not reliably
   activate the field. These are **unresolved emulator interaction failures**,
   not a confirmed code-level root cause; reproduce by physical touch before
   assigning a microphone-only defect. No native error was found in the scoped
   ReactNativeJS/AndroidRuntime error logs.

Recording, slide-cancel/no-upload, file cleanup, 30-second cap, background
cancellation, three spoken clips/latencies and TalkBack remain UNVERIFIED.
Accessibility labels in the UI tree are not proof of TalkBack operation.
Device status remains open.
