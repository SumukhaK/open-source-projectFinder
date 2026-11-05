# Voice assistant tracker

Status (2026-11-05): plan and UX agreed; all decisions approved; no task started. Owner: the implementer records progress and PR links; only a trusted reviewer records acceptance. Same table rules as the [hybrid tracker](../hybrid-search/TRACKER.md).

| Accepted | Task | Requires merged / approved | Status | PR / base SHA | Reviewed head / review / CI evidence | Merged main SHA / date |
| --- | --- | --- | --- | --- | --- | --- |
| [ ] | [P3: Home/Profile navigation and settings](tasks/P3-home-profile.md) | T25; UX1 | Awaiting review | [PR #61](https://github.com/SumukhaK/open-source-projectFinder/pull/61) / base `dc4ea0a7de50bb9762cf0ac35160c08677374419` | [Evidence](P3_EVIDENCE.md) | — |
| [ ] | [V0: LLM provider profiles and eval harness](tasks/V0-llm-profiles.md) | T15; VD2 | Awaiting review | [PR #63](https://github.com/SumukhaK/open-source-projectFinder/pull/63); base `dc4ea0a7de50bb9762cf0ac35160c08677374419` | 29 new tests (24 client + 5 eval); full backend+scripts suite 985 passed / 65 skipped; coverage 93.4% combined / 90.5% branches; ruff and bandit clean; hand Ollama eval row below | — |
| [ ] | [V1: Hold-to-talk voice input](tasks/V1-voice-input.md) | P3; VD1, VD3 | Not started | — | — | — |
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
| 2026-11-05 | ollama/ollama/qwen2.5:7b-instruct | query_tidy_v1+summary_grounded_v1 | 100% | 100% | 1109/5391 ms (p95 1438/6109) | 2/2 shorter | no |

## History

- 2026-11-05 - Plan agreed in the owner's project thread (architecture review, LLM decision and switching rules). VD1-VD3 approved, VD4 pending. VD5 approved the same day (existing shared Cloudflare token, owner-rotated). No code yet.
- 2026-11-05 - UX decisions UX1-UX5 approved (owner delegated them); VD4 approved as "on for voice searches only". Added P3 (Home/Profile navigation and settings) before V1; V1-V3 now carry the UX details.
- 2026-11-05 - V0: Not started -> Awaiting review. LLM profiles in central config, one OpenAI-compatible client, versioned prompts, startup probe, eval harness and tests, based on `dc4ea0a7de50bb9762cf0ac35160c08677374419`; [PR #63](https://github.com/SumukhaK/open-source-projectFinder/pull/63). Hand-run Ollama eval recorded above; the eval used the built-in 2-query sample set because the T27 query set does not exist yet.
