# V1: Hold-to-talk voice input

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/voice-v1-voice-input` |
| Prerequisites | P3 merged; VD1 and VD3 approved |
| Intended scope | a backend `/v1/voice/transcribe` route and Deepgram client, the mobile Home search action, consent and permission handling, tests and docs |

Read first: [voice UX](../../../docs/VOICE_UX.md) (journey steps 1-4, 6-7), [voice architecture](../../../docs/VOICE_ASSISTANT_ARCHITECTURE.md), [plan rules](../README.md), the hybrid [EXECUTION_GUIDE](../../hybrid-search/EXECUTION_GUIDE.md) and the current code, tests and configuration.

## Copy-ready execution prompt

```text
Execute V1 only. Follow AGENTS.md, execution-plans/hybrid-search/EXECUTION_GUIDE.md
and execution-plans/voice-assistant/README.md. Verify the listed prerequisites are
MERGED into main and the listed decisions are approved; stop if missing. Read
current code/tests before editing. Fetch origin main and create branch
codex/voice-v1-voice-input FROM origin/main; record base SHA.
Minimum complete, human-readable code, existing patterns and standard library
first, no speculative abstractions or unrelated changes. Write and RUN failing
tests FIRST (RED), implement the minimum (GREEN), then refactor and run affected
tests/lint/type/security checks. CI uses fake providers only; never commit keys.
Implement only the scope and acceptance criteria below. Do not lower CI gates or
claim unrun device/provider checks passed. Update docs and the voice TRACKER to
Awaiting review with actual evidence. Commit explicit task files, push, and RAISE
ONE PR AGAINST main. Return PR URL, full head SHA and verification/limits; STOP
AND WAIT FOR REVIEW. Do not self-accept, merge or start the next task.
```

## Work and boundaries

Hold the search button to record; release to upload the clip over HTTPS to an authenticated `/v1/voice/transcribe` route with bounded size and duration. The backend forwards the clip to Deepgram's pre-recorded API with the server-side key and returns the transcript, without storing the audio or transcript. The app shows the transcript as editable text, then the user runs the existing hybrid search. Ask for microphone permission, show a one-time notice that audio is processed by Deepgram, and keep the full text path when the user declines or Deepgram fails. Handle release before permission, app backgrounding, sign-out and unmount during recording or upload. Log only durations and sizes. Measure release-to-transcript latency. UX: a mic button inside the idea box with the first-use hint; the one-time "Search by voice" sheet before the system prompt (Continue / Not now); haptic, pulsing ring, timer, slide to cancel and a 30-second limit; the "We heard" label with search starting at once; the denied-permission sheet with "Open phone settings"; a Profile › Voice screen with the microphone status row and the "How voice works" page. The consent flag is stored per account and cleared on sign-out.

## Tests and verification before acceptance

RED: size/duration limits, unauthenticated requests, Deepgram timeout/error mapped to a typed retryable error, no audio or transcript persisted or logged, permission denied, release races, background and sign-out cleanup, editable transcript feeding the existing search. GREEN: backend and mobile suites with a fake Deepgram; one manual run against Deepgram with latency recorded; a real mobile-sized light/dark inspection on a development build (or the honest reason it could not run).

## What counts as acceptable

One search action with optional voice; the list still comes from hybrid search; voice failures leave text search working. An independent trusted reviewer must accept the exact current PR head after required checks pass.

## Do not do

No WebSocket or WebRTC, no key in the app, no audio files kept on the device after upload, no auto-search without showing the transcript.
