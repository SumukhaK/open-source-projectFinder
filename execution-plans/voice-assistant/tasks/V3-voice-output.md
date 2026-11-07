# V3: Spoken summary and voice-output setting

Status: V3a (backend speech route) and V3b (mobile playback and setting, PR #73) are awaiting review in parallel. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `opencode/voice-v3a-speech` (V3b: `codex/voice-v3b-spoken-summary`) |
| Prerequisites | V1b, V2a, V2b merged; VD4 approved; V3b also needs V3a merged |
| Intended scope | V3a: a backend `/v1/voice/speech/{summary_id}` route that streams Deepgram MP3 for a stored grounded summary. V3b: mobile playback and the voice-output setting. |

V3a is the backend half. It issues an opaque, account-bound summary ID in the grounded `done` event and streams the exact validated text; the client sends no text. V3b is the mobile half, built against this contract, and starts only after V3a merges.

Read first: [voice architecture](../../../docs/VOICE_ASSISTANT_ARCHITECTURE.md), [plan rules](../README.md), the hybrid [EXECUTION_GUIDE](../../hybrid-search/EXECUTION_GUIDE.md) and the current code, tests and configuration.

## Copy-ready execution prompt

```text
Execute V3a only. Follow AGENTS.md, execution-plans/hybrid-search/EXECUTION_GUIDE.md
and execution-plans/voice-assistant/README.md. Verify the listed prerequisites are
MERGED into main and the listed decisions are approved; stop if missing. Read
current code/tests before editing. Fetch origin main and create branch
opencode/voice-v3a-speech FROM origin/main; record base SHA. Backend only: do not
touch mobile/. The mobile half is V3b in PR #73 and was built against this exact
contract; do not change it.
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

V3a: the summary SSE `done` event for a grounded, validated summary carries an opaque random `summary_id` bound to the requesting account and expiring after 300 seconds, but only when the text fits Deepgram's 2,000-character speech limit (`SPEECH_MAX_CHARS`); no ID is issued for any ungrounded result or over-limit text. The authenticated `GET /v1/voice/speech/{summary_id}` resolves that stored text and streams Deepgram MP3 as `audio/mpeg`, with a total byte cap and deadline. Unknown, expired or other-account IDs are `speech_not_found`; a missing key or pre-audio provider failure is retryable `speech_unavailable`; capacity is retryable `speech_busy`. The route never speaks anything that is not a stored validated summary, and logs no text, IDs or audio.

V3b: when voice output is on, play the streamed summary on the phone as it arrives. Add "Read summaries aloud" to Profile › Voice, default on for voice searches only (VD4); typed searches never speak on their own. Add the summary card's speaker/Stop button so any summary can be heard once, and the one-time tip "Turn this off in Profile › Voice". Never auto-speak while a screen reader runs, and respect silent mode (see [voice UX](../../../docs/VOICE_UX.md)). Stop playback on a new search, sign-out, background or leaving Home. Never speak an unvalidated summary.

## Tests and verification before acceptance

V3a RED/GREEN: only grounded summaries get an ID; the ID maps to the exact validated text; expiry, unknown and other-account IDs return 404; a missing key returns 503 without a provider call; provider failure before audio returns 503; streamed bytes pass through as `audio/mpeg`; byte cap and deadline close the stream; concurrency is reserved before the provider call; no summary text, IDs or audio in logs. Suites use a fake Deepgram transport. The optional real TTS call is owner-run only.

V3b RED/GREEN: setting off means no TTS request, playback stops on new search/sign-out/background, TTS failure leaves the text summary, only validated summaries are spoken, no audio stored; one manual device run with first-sound latency recorded and a real light/dark inspection on a development build.

## What counts as acceptable

The list and text summary work with voice output on or off; speech never blocks or changes them. An independent trusted reviewer must accept the exact current PR head after required checks pass.

## Do not do

No always-listening mode, no barge-in, no stored audio. V3a does not change mobile code or the summary grounding rules.
