# V3: Spoken summary and voice-output setting

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/voice-v3-voice-output` |
| Prerequisites | V1 and V2 merged; VD4 approved |
| Intended scope | a backend text-to-speech route through Deepgram, mobile playback and the voice-output setting, tests and docs |

Read first: [voice architecture](../../../docs/VOICE_ASSISTANT_ARCHITECTURE.md), [plan rules](../README.md), the hybrid [EXECUTION_GUIDE](../../hybrid-search/EXECUTION_GUIDE.md) and the current code, tests and configuration.

## Copy-ready execution prompt

```text
Execute V3 only. Follow AGENTS.md, execution-plans/hybrid-search/EXECUTION_GUIDE.md
and execution-plans/voice-assistant/README.md. Verify the listed prerequisites are
MERGED into main and the listed decisions are approved; stop if missing. Read
current code/tests before editing. Fetch origin main and create branch
codex/voice-v3-voice-output FROM origin/main; record base SHA.
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

When voice output is on, stream the validated summary through Deepgram text to speech from the backend and play it on the phone as it arrives. Add "Read summaries aloud" to Profile › Voice, default on for voice searches only (VD4); typed searches never speak on their own. Add the summary card's speaker/Stop button so any summary can be heard once, and the one-time tip "Turn this off in Profile › Voice". Never auto-speak while a screen reader runs, and respect silent mode (see [voice UX](../../../docs/VOICE_UX.md)). Stop playback on a new search, sign-out, background or leaving Home. Never speak an unvalidated summary.

## Tests and verification before acceptance

RED: setting off means no TTS request, playback stops on new search/sign-out/background, TTS failure leaves the text summary, only validated summaries are spoken, no audio stored. GREEN: suites with a fake Deepgram; one manual device run with first-sound latency recorded and a real light/dark inspection on a development build.

## What counts as acceptable

The list and text summary work with voice output on or off; speech never blocks or changes them. An independent trusted reviewer must accept the exact current PR head after required checks pass.

## Do not do

No always-listening mode, no barge-in, no stored audio.
