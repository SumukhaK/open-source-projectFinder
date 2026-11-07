# V3a backend speech evidence

Status: Awaiting review. [PR #74](https://github.com/SumukhaK/open-source-projectFinder/pull/74), code head `56c92fc479cb6ef91ae93ab40511a5461798e5bd`; base `2d522ea07678a40a7f694b786be65dc619c8beb3`; branch `opencode/voice-v3a-speech`. Backend only; preserves the supplied PR #73 mobile contract. No mobile files changed.

## Scope delivered

- A grounded, validated summary's SSE `done` event now carries an opaque `summary_id` (`secrets.token_urlsafe(24)`, 32 characters). No ID is emitted for any `grounded: false` result, including empty, ungrounded, busy, failed or late summaries.
- IDs are account-bound, expire after a fixed 300 seconds and live only in a process-local `OrderedDict` LRU bounded by the existing `HYBRID_CURSOR_CACHE_SIZE` / `HYBRID_CURSOR_CACHE_PER_ACCOUNT` settings. Nothing is written to disk.
- `GET /v1/voice/speech/{summary_id}` uses the normal session guard and the same discovery/voice throttle key and metrics convention as `/v1/voice/transcribe`. The client sends no text; the route resolves the stored text for the requesting account.
- Unknown, expired and other-account IDs return 404 `speech_not_found`. A missing `DEEPGRAM_API_KEY` or a provider failure before the first audio byte returns 503 `speech_unavailable` with `retryable: true`. Capacity returns 503 `speech_busy` with `retryable: true` without calling Deepgram. Throttling keeps the existing 429 `VOICE_RATE_LIMITED` shape.
- `app/integrations/deepgram.py::speech_audio` calls `POST https://api.deepgram.com/v1/speak` with `model` and `encoding=mp3` query parameters, `Authorization: Token <key>`, `Accept-Encoding: identity` and JSON `{"text": ...}`. It requires status 200, content type `audio/mpeg` and identity encoding, and enforces the byte cap while yielding.
- The route reads the first chunk before sending headers, then streams the rest as `audio/mpeg` through `SpeechResponse`. The total deadline covers preflight and streaming. A post-header timeout, provider error or byte-cap breach closes partial audio rather than appending JSON. The wrapper closes the provider stream and releases the concurrency slot on success, failure and client cancellation.
- New bounded settings and `.env.example` entries: `DEEPGRAM_TTS_MODEL` (default `aura-2-thalia-en`, 1-100 safe characters), `SPEECH_DEADLINE` (default 30 s, 0 < x <= 120), `SPEECH_MAX_BYTES` (default 4 MiB, 1 byte-16 MiB) and `SPEECH_MAX_CONCURRENT` (default 1, 1-4).
- Logs contain only `bytes` and `latency_ms`; tests assert that summary text, IDs, the API key and audio bytes never appear in application logs.

## TDD evidence

RED: implementation files were set aside and the four changed implementation modules were restored to base while the new tests stayed in place. Result: `25 failed, 14 passed in 7.81s` across `backend/tests/test_speech.py` and `backend/tests/test_summary_api.py`. Failures covered the missing `summary_id`, account/expiry/unknown lookups, missing-key and provider preflight, byte/deadline bounds, concurrency, cancellation, bounded settings and the summary-ID assertions in the existing summary tests.

GREEN: with the implementation restored, the focused pair passed: `39 passed, 1 warning in 6.35s`.

Tests in `backend/tests/test_speech.py` cover: exact stored text sent to the provider; `audio/mpeg` passthrough; `no-store`; account binding; expiry at exactly 300 s; unknown/other-account 404; no ID on ungrounded or empty summaries; missing key (no provider call), provider error, empty audio and first-byte deadline all returning typed 503; byte-cap and deadline truncation closing the provider; concurrency reserved before the provider call; shared voice throttle and session guard; LRU bounds; settings bounds; cancellation closing the provider and releasing the slot; no sensitive log content.

## Full verification (run 2026-11-07)

| Check | Command | Result |
| --- | --- | --- |
| Backend + scripts suite with coverage | `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=...` | `1074 passed, 65 skipped, 1 warning in 99.41s` |
| Coverage gate | `python scripts/quality.py coverage reports/backend-coverage.json` | `93.3% combined; 90.0% branches` (gate: 90% combined, 80% branches) |
| New route coverage | coverage report | `app/api/speech.py` 97% (line 131 unexpected-error re-raise); `app/api/summary.py` 98% |
| Lint | `ruff check backend scripts` | All checks passed |
| Format | `ruff format --check backend scripts` | 76 files already formatted |
| Security | `bandit -r backend/app -f json -o reports/bandit.json` | 0 findings across 8,467 lines of code |

The interpreter was `E:\OpenSourceProjectFinder-t24\backend\.venv\Scripts\python.exe` (the v1b worktree has no virtual environment). Archive tests skipped on Windows as designed; no Docker, Ollama or Milvus was used.

## Optional real Deepgram call

Not run. Neither worktree has `backend/.env`, so no `DEEPGRAM_API_KEY` was available. This check stays owner-run; automated tests use `httpx.MockTransport` and no key. If run, record time to first byte, total bytes and the short sentence only, never the key.

## Limits and operational notes

- IDs are process-local. A restart, LRU eviction or a different worker invalidates them, so run one serving process or use sticky routing. V3b already treats a 404 as "read aloud unavailable".
- The fixed 300-second TTL matches the maximum existing cursor TTL; it is not configurable.
- The application must keep running with `--no-access-log`; proxy access logs must also be disabled or redacted for `/v1/voice/speech/` because the opaque ID is in the URL. Application logs themselves never include IDs.
- Once audio headers are sent, a later provider/deadline/byte-cap failure closes a truncated MP3 stream; it cannot become a JSON error. The client keeps the text summary.
- CI uses a fake Deepgram transport only. No real-provider latency, Android playback, TalkBack or light/dark check is claimed here; playback and the setting belong to V3b (PR #73).

## Files changed

- `backend/app/api/speech.py` (new route, `SpeechResponse`, concurrency and preflight)
- `backend/app/api/summary.py` (`ValidatedSummaries`, grounded-only ID issuance)
- `backend/app/integrations/deepgram.py` (`speech_audio`)
- `backend/app/core/config.py` (bounded speech settings)
- `backend/app/main.py` (store wiring, speech router, voice-throttle path)
- `backend/tests/test_speech.py` (new)
- `backend/tests/test_summary_api.py` (`summary_id` assertions)
- `backend/.env.example`, `backend/README.md`
- `execution-plans/voice-assistant/TRACKER.md`, `tasks/V3-voice-output.md`, this file
