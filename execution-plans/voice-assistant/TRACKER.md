# Voice assistant tracker

Status (2026-11-05): plan and UX agreed; all decisions approved; P3 merged, V0 next. Owner: the implementer records progress and PR links; only a trusted reviewer records acceptance. Same table rules as the [hybrid tracker](../hybrid-search/TRACKER.md).

| Accepted | Task | Requires merged / approved | Status | PR / base SHA | Reviewed head / review / CI evidence | Merged main SHA / date |
| --- | --- | --- | --- | --- | --- | --- |
| [x] | [P3: Home/Profile navigation and settings](tasks/P3-home-profile.md) | T25; UX1 | Merged | [PR #62](https://github.com/SumukhaK/open-source-projectFinder/pull/62) (supersedes [#61](https://github.com/SumukhaK/open-source-projectFinder/pull/61)) / base `dc4ea0a7de50bb9762cf0ac35160c08677374419` | Head `374bb522bc08dc7d4ca3e36567e3b348575c8fa1`; trusted review in thread; [CI run 41989787081](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/41989787081) green; [evidence](P3_EVIDENCE.md) | `4ea0659526666a79fe9373e54f4485c842896f0b` / 2026-11-05 |
| [ ] | [V0: LLM provider profiles and eval harness](tasks/V0-llm-profiles.md) | T15; VD2 | Not started | — | — | — |
| [ ] | [V1a: Backend transcription](tasks/V1-voice-input.md) | P3; VD1, VD3 | Awaiting review | [PR #65](https://github.com/SumukhaK/open-source-projectFinder/pull/65) / base `662735b5e0b024e54fdbd0352ae0c80eaf226813` | [Evidence](V1a_EVIDENCE.md); acceptance pending | — |
| [ ] | [V1b: Mobile voice input](tasks/V1-voice-input.md) | V1a merged | Not started | — | — | — |
| [ ] | [V2: Grounded result summary](tasks/V2-grounded-summary.md) | V0 | Not started | — | — | — |
| [ ] | [V3: Spoken summary and voice-output setting](tasks/V3-voice-output.md) | V1, V2; VD4 | Not started | — | — | — |
| [ ] | [V4: Streaming transcription (conditional)](tasks/V4-streaming-transcription.md) | V1 latency evidence | Not started | — | — | — |

## Decisions

| ID | Decision | Status | Value |
| --- | --- | --- | --- |
| VD1 | Speech provider | **Approved 2026-11-05** | Deepgram (owner's $200 credit) for speech to text and text to speech, called only from the backend. Supersedes the earlier "native speech recognition, no paid transcription keys" item in PROJECT_TRACKER. Requires a consent notice and a text-only path; use Deepgram's data-retention opt-out if offered. |
| VD2 | LLM provider path | **Approved 2026-11-05** | No frontier model. Ollama locally, small then larger; then Cloudflare Workers AI open models up to about 30B (Qwen or Mistral class). One OpenAI-compatible client; switch by settings profile and evals only. |
| VD3 | Interaction and transport | **Approved 2026-11-05** | Hold-to-talk. HTTPS clip upload first; WebSocket streaming only if V1 latency needs it; no WebRTC for now. |
| VD4 | Voice output default | **Approved 2026-11-05** | On, for voice searches only; typed searches never speak; no auto-speech while a screen reader runs; respect silent mode. Owner delegated the UX calls; see [voice UX](../../docs/VOICE_UX.md) UX1-UX5. |
| UX1-UX5 | Settings place, toggle, default, mic button, in-context explanations | **Approved 2026-11-05** | Owner: "UI/UX decisions are yours, whatever u recommend is fine by me". Recorded in [voice UX](../../docs/VOICE_UX.md). |
| VD5 | Workers AI account and key ownership | **Approved 2026-11-05** | The owner's existing Cloudflare account and token, shared with another of the owner's projects; the owner rotates and revokes it (rotating breaks both projects, so update both `.env` files together). Stored only in the laptop's ignored `backend/.env` as `WORKERS_AI_ACCOUNT_ID` and `WORKERS_AI_API_TOKEN`. The token needs the Workers AI permission. |

## Model profile evaluations

Record one row per profile run. A profile becomes the default only when it meets the current default's bar on the same eval set.

| Date | Profile / provider / model | Prompt version | Grounding | Faithfulness | First word / total (p50, p95) | Tidied vs raw query | Default? |
| --- | --- | --- | --- | --- | --- | --- | --- |

## History

- 2026-11-06 - Owner approved splitting V1 into two PRs: V1a backend transcription first (`codex/voice-v1a-transcribe`), then V1b mobile recording/UI (`codex/voice-v1b-mobile`) from main only after V1a merges. P3 merge and VD1/VD3 approval verified. V0 is independent; no LLM work in either V1 slice.

- 2026-11-05 - Plan agreed in the owner's project thread (architecture review, LLM decision and switching rules). VD1-VD3 approved, VD4 pending. VD5 approved the same day (existing shared Cloudflare token, owner-rotated). No code yet.
- 2026-11-05 - UX decisions UX1-UX5 approved (owner delegated them); VD4 approved as "on for voice searches only". Added P3 (Home/Profile navigation and settings) before V1; V1-V3 now carry the UX details.
- 2026-11-05 - P3 merged as PR #62. GPT opened #61, then its session ended before it pushed the review fixes (tab-aware header, username once, section heading styles, two tests). Claude applied those fixes, verified them RED/GREEN, merged #62 and closed #61. Device light/dark and screen-reader checks remain open in the [evidence](P3_EVIDENCE.md).
