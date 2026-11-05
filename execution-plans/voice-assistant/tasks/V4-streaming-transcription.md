# V4: Streaming transcription (conditional)

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/voice-v4-streaming` |
| Prerequisites | V1 merged, and V1 latency evidence shows the clip upload is too slow (owner decides) |
| Intended scope | a backend WebSocket relay to Deepgram live transcription, a native audio-chunk module on mobile, tests and docs |

Read first: [voice architecture](../../../docs/VOICE_ASSISTANT_ARCHITECTURE.md), [plan rules](../README.md), the hybrid [EXECUTION_GUIDE](../../hybrid-search/EXECUTION_GUIDE.md) and the current code, tests and configuration.

## Copy-ready execution prompt

```text
Execute V4 only. Follow AGENTS.md, execution-plans/hybrid-search/EXECUTION_GUIDE.md
and execution-plans/voice-assistant/README.md. Verify the listed prerequisites are
MERGED into main and the listed decisions are approved; stop if missing. Read
current code/tests before editing. Fetch origin main and create branch
codex/voice-v4-streaming FROM origin/main; record base SHA.
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

Only if approved after V1: stream audio chunks over an authenticated WebSocket to the backend while the button is held; the backend relays them to Deepgram's live API and returns interim and final transcripts. Keep the V1 upload path as the fallback. Same privacy, cleanup and consent rules as V1.

## Tests and verification before acceptance

RED: auth on connect, bounded duration and bytes, disconnect and reconnect, fallback to upload, cleanup on release/background/sign-out, no persistence. GREEN: suites with fakes; device latency compared with V1 and recorded.

## What counts as acceptable

Measurably faster release-to-transcript than V1 with no loss of reliability. An independent trusted reviewer must accept the exact current PR head after required checks pass.

## Do not do

No WebRTC, no media server.
