# Voice assistant execution plan

Agreed with the owner on 2026-11-05. **Proposed implementation, not shipped functionality.** Design: [docs/VOICE_ASSISTANT_ARCHITECTURE.md](../../docs/VOICE_ASSISTANT_ARCHITECTURE.md) and [docs/VOICE_UX.md](../../docs/VOICE_UX.md). Progress and decisions: [TRACKER](TRACKER.md).

Every task follows the hybrid plan's [EXECUTION_GUIDE](../hybrid-search/EXECUTION_GUIDE.md) and [REVIEW_CHECKLIST](../hybrid-search/REVIEW_CHECKLIST.md): a fresh main-based branch, tests first (RED then GREEN), one PR, exact-head review, and merge before a dependent task starts.

## Order

0. **P3** Home/Profile bottom bar and settings home (the original Home/Profile design), before any voice UI. See [voice UX](../../docs/VOICE_UX.md).
1. **V0** LLM provider profiles, one OpenAI-compatible client and the eval harness. No user-facing change.
2. **V1** Voice in: hold to talk, HTTPS clip upload, Deepgram speech to text, editable transcript, consent. Measures latency.
3. **V2** Grounded summary of the result list (and optional query tidy-up), streamed as text.
4. **V3** Voice out: Deepgram text to speech for the summary, plus the voice-output setting.
5. **V4** Streaming transcription over WebSocket, **only if** V1's measured latency is too slow.

The hybrid archive tasks (T18-T30) run alongside; nothing here blocks them or depends on them, except that V0's evals reuse the T27 query set once it exists.

## Rules that apply to every task

- The result list always comes from `POST /v1/projects/search`. The LLM never adds, removes or reorders results.
- The list never waits for the LLM or audio. Any failure in speech, the LLM or TTS degrades to the text path, never to a search error.
- No audio, transcript, idea or summary is persisted or logged. Logs record counts, durations, profile, model and prompt version only.
- Provider keys stay in ignored backend environment files; mobile configuration never holds a key. CI uses fake providers only and needs no key.
- No code names a model; models are settings profiles (see the [switching rules](../../docs/VOICE_ASSISTANT_ARCHITECTURE.md#llm-providers-and-switching)).
- Mobile voice UI work includes a real mobile-sized light/dark inspection on a development build, or records honestly why it could not be done.
