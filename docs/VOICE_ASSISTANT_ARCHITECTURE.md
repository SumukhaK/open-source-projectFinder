# Voice assistant architecture

Agreed with the owner on 2026-11-05. This is the repository copy of the architecture review; the task plan, decisions and progress live in [execution-plans/voice-assistant](../execution-plans/voice-assistant/README.md).

## Summary

- **Voice and an LLM summary sit on top of the hybrid search; they do not replace it.** `POST /v1/projects/search` stays the engine. The result list always comes from hybrid search, never from the LLM.
- **No voice code existed before this plan.** The app and backend never recorded or sent audio, so the transport is chosen fresh: there is no HTTP-to-WebRTC migration.
- **Hold-to-talk, not open conversation.** The user speaks, releases, and gets a list plus an optional spoken summary. WebRTC is not used. The clip is uploaded over HTTPS first; WebSocket streaming is added only if measured latency needs it.
- **The LLM only tidies the query and summarises the results it was given.** A summary that names a repository outside the list is rejected. A rejected or late summary drops to list only.
- **Speech goes through Deepgram; the LLM runs on Ollama, then Cloudflare Workers AI.** This replaces the earlier plan of on-device speech recognition with no paid transcription keys.

## Flow

1. **Hold to talk.** The phone records while the button is held. Audio goes to our backend only; the Deepgram key never reaches the phone.
2. **Speech to text.** The backend sends the clip to Deepgram and returns the words. The phone shows them as an editable transcript before searching.
3. **Search.** The transcript, optionally tidied by the LLM into a short query, goes into the existing `POST /v1/projects/search` (live GitHub and the Milvus archive in parallel, one merged list).
4. **List first.** The phone shows the list as soon as search returns. It never waits for the LLM or for audio.
5. **Grounded summary.** The backend gives the LLM the top results (name, description, licence) and asks for a summary of those only. The summary streams to the phone as text.
6. **Voice reply.** If voice output is on, the backend streams the summary through Deepgram text to speech and the phone plays it. If it is off, only the text summary shows.

Latency to measure in V1-V3, from button release: about 0.3-0.5 s to the transcript, 1-3 s for search (existing 8-second hybrid deadline), 0.5-1 s to the first summary words and about 0.3 s more to the first sound. These are estimates, not targets.

## Transport

| Option | Use | Notes |
| --- | --- | --- |
| HTTPS clip upload | **V1, first choice** | One request after release; Deepgram pre-recorded API; simplest to test |
| WebSocket streaming | V4, only if V1 is too slow | Transcript ready almost as the user stops; needs a native audio-chunk module and a development build |
| WebRTC | Not planned | For full-duplex calls with interruption; needs media/TURN servers; drops lost packets instead of resending, which a one-shot query does not want |

HTTP and WebSocket run over TCP, so no audio is lost on a bad network; it only arrives later.

## LLM providers and switching

The owner chose: no frontier model. Start with small Ollama models on the laptop, step up in size while collecting eval results, then use Cloudflare Workers AI for open models up to about 30B parameters (Qwen or Mistral class) that the laptop cannot run. The laptop's 4 GB GPU is shared with E5 and Milvus, so local models are expected to be small quantised ones (about 3-8B) run outside heavy indexing.

Rules so a switch never surprises:

1. **One settings profile per model** in `backend/app/core/config.py`: provider, base URL, model, server-side key reference, timeouts, max output tokens, temperature, context limit and streaming support. No code names a model.
2. **One OpenAI-compatible client** serves Ollama and Workers AI. Switching is a settings change.
3. **Fail at startup, not mid-search.** The active profile is validated with one tiny call at start; a bad profile is logged clearly and search keeps working without summaries.
4. **Versioned prompt files** shared by every provider. Changing the model never silently changes the prompt.
5. **Validated output.** Query tidy-up returns a small validated structure; summaries are checked against the result list.
6. **Hard deadlines per step.** A slow model costs the summary, never the list.
7. **Labelled replies.** Logs and eval results record profile, model and prompt version, never the user's words.
8. **Switch through evals only.** A profile becomes the default after it runs the same eval set and meets the current default's bar, with the result recorded in the voice tracker.
9. **Contract tests** run in CI against a fake provider and by hand against Ollama and Workers AI before a switch.

Eval measures: grounding (no repository outside the list), faithfulness to each project's description and licence, time to first word, total time and whether the tidied query beats the raw transcript. The T27 human-judged query set is reused as the test set.

## Privacy and security

- Audio, transcripts, ideas and summaries are never stored. Logs carry counts, durations, profile and prompt version only.
- Deepgram and Workers AI keys live in ignored environment files on the backend; mobile configuration never holds them. CI uses fakes only.
- The app asks for microphone permission, explains that audio is processed by Deepgram, and keeps a full text-only path when the user declines.
- Use Deepgram's data-retention opt-out if the account offers it.

## Impact on existing work

| Area | Change |
| --- | --- |
| Archive pipeline (T00-T23) | None. T18 Phase B and T19-T23 continue as planned. |
| Hybrid search and `/v1/projects/search` (T11-T15, U14) | None. Called by the voice flow as is. |
| Mobile transport and results list (P2, T24, T25) | Additions only: voice button and recording, editable transcript, summary card, playback, voice-output setting. |
| Earlier voice plan (native speech, no paid keys) | Superseded by Deepgram, with consent. |
| T26 real-HTTP check | Unchanged; the voice path gets its own device checks in V1 and V3. |

## Risks

- **The laptop is the server.** Voice search needs it awake and reachable through a tunnel, as text search already does.
- **Cost.** Deepgram runs on the owner's $200 credit; Workers AI is billed by Cloudflare. Check current prices against real usage before raising limits.
- **Hallucinated projects.** Prevented by the grounding check and tested like search.
- **Native modules.** Recording and playback need native packages and a development build.
