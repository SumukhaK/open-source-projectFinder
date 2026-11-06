# V1: Hold-to-talk voice input

Status: split into V1a (backend, merged in [PR #65](https://github.com/SumukhaK/open-source-projectFinder/pull/65), `f4f4bf3`) and V1b (mobile, awaiting review; records AAC/M4A, which the route accepts; [evidence](../V1b_EVIDENCE.md)), approved by the owner on 2026-11-06. [V1a verification evidence](../V1a_EVIDENCE.md); review/merge evidence belongs in [TRACKER](../TRACKER.md).

## Approved execution split

- **V1a**: `codex/voice-v1a-transcribe`, from current `origin/main`; backend only. Authenticated `/v1/voice/transcribe`, Deepgram HTTP client with fake-provider tests, empty `DEEPGRAM_API_KEY` example and central `SecretStr`, bounded size/duration, typed retryable provider errors, content-free latency logging, no stored/logged audio or transcripts, backend README and evidence. Raise one PR and stop for review.
- **V1b**: `codex/voice-v1b-mobile`, from `origin/main` **after V1a merges**. Recording lifecycle and all mobile UX below: mic, consent/permission/denial, hold/slide-cancel/30-second limit, editable “We heard” transcript and existing search, Profile Voice/help, account-scoped consent cleared on sign-out, race/background/unmount tests. Raise its own PR and stop. No V1b work belongs in V1a.

V1a base: `662735b5e0b024e54fdbd0352ae0c80eaf226813`. Plan: (1) RED route/provider boundary tests; (2) minimum backend implementation and GREEN; (3) full backend checks, evidence and PR. Real provider latency remains unverified unless actually measured. The original combined journey below remains the product specification, not permission to start V1b early.

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | V1a: `codex/voice-v1a-transcribe`; V1b: `codex/voice-v1b-mobile` |
| Prerequisites | V1a: P3 merged, VD1 and VD3 approved; V1b: V1a merged |
| Intended scope | V1a backend route/client/tests/docs; V1b mobile recording/UI/tests/docs |

Read first: [voice UX](../../../docs/VOICE_UX.md) (journey steps 1-4, 6-7), [voice architecture](../../../docs/VOICE_ASSISTANT_ARCHITECTURE.md), [plan rules](../README.md), the hybrid [EXECUTION_GUIDE](../../hybrid-search/EXECUTION_GUIDE.md) and the current code, tests and configuration.

## Execution prompt (select one approved slice)

```text
Execute only the owner-selected V1a or V1b slice above. Follow AGENTS.md, execution-plans/hybrid-search/EXECUTION_GUIDE.md
and execution-plans/voice-assistant/README.md. Verify the listed prerequisites are
MERGED into main and the listed decisions are approved; stop if missing. Read
current code/tests before editing. Fetch origin main and create branch
the selected slice's branch FROM origin/main; record base SHA. V1b starts only after V1a merges.
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
