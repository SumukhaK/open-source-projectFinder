# Voice assistant tracker

Status (2026-11-05): plan agreed; no task started. Owner: the implementer records progress and PR links; only a trusted reviewer records acceptance. Same table rules as the [hybrid tracker](../hybrid-search/TRACKER.md).

| Accepted | Task | Requires merged / approved | Status | PR / base SHA | Reviewed head / review / CI evidence | Merged main SHA / date |
| --- | --- | --- | --- | --- | --- | --- |
| [ ] | [V0: LLM provider profiles and eval harness](tasks/V0-llm-profiles.md) | T15; VD2 | Not started | — | — | — |
| [ ] | [V1: Hold-to-talk voice input](tasks/V1-voice-input.md) | T25; VD1, VD3 | Not started | — | — | — |
| [ ] | [V2: Grounded result summary](tasks/V2-grounded-summary.md) | V0 | Not started | — | — | — |
| [ ] | [V3: Spoken summary and voice-output setting](tasks/V3-voice-output.md) | V1, V2; VD4 | Not started | — | — | — |
| [ ] | [V4: Streaming transcription (conditional)](tasks/V4-streaming-transcription.md) | V1 latency evidence | Not started | — | — | — |

## Decisions

| ID | Decision | Status | Value |
| --- | --- | --- | --- |
| VD1 | Speech provider | **Approved 2026-11-05** | Deepgram (owner's $200 credit) for speech to text and text to speech, called only from the backend. Supersedes the earlier "native speech recognition, no paid transcription keys" item in PROJECT_TRACKER. Requires a consent notice and a text-only path; use Deepgram's data-retention opt-out if offered. |
| VD2 | LLM provider path | **Approved 2026-11-05** | No frontier model. Ollama locally, small then larger; then Cloudflare Workers AI open models up to about 30B (Qwen or Mistral class). One OpenAI-compatible client; switch by settings profile and evals only. |
| VD3 | Interaction and transport | **Approved 2026-11-05** | Hold-to-talk. HTTPS clip upload first; WebSocket streaming only if V1 latency needs it; no WebRTC for now. |
| VD4 | Voice output default | **Pending owner** | Whether spoken summaries are on or off by default (the list always shows). Needed before V3. |
| VD5 | Workers AI account and key ownership | **Pending owner** | Which Cloudflare account and who rotates or revokes its key. Needed before the first Workers AI profile run, not before V0. |

## Model profile evaluations

Record one row per profile run. A profile becomes the default only when it meets the current default's bar on the same eval set.

| Date | Profile / provider / model | Prompt version | Grounding | Faithfulness | First word / total (p50, p95) | Tidied vs raw query | Default? |
| --- | --- | --- | --- | --- | --- | --- | --- |

## History

- 2026-11-05 - Plan agreed in the owner's project thread (architecture review, LLM decision and switching rules). VD1-VD3 approved, VD4-VD5 pending. No code yet.
