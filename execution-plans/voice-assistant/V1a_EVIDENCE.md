# V1a — backend transcription evidence

Date: 2026-11-06. Status: Awaiting review; not accepted or merged.
Branch: `codex/voice-v1a-transcribe`. Base: `662735b5e0b024e54fdbd0352ae0c80eaf226813`.

## Scope and prerequisite checks

P3 PR #62 is MERGED as `4ea0659526666a79fe9373e54f4485c842896f0b`, verified as an ancestor of the base; it supersedes closed PR #61. VD1/VD3 are approved in the voice tracker. The owner approved two PRs: this backend-only V1a, then V1b from main after V1a merges. V0/PR #63 and its worktree were not touched. The previous planning-only PROJECT_TRACKER edit was reverted as requested; the split is recorded only in the voice task/tracker.

Four production Python files: the voice router, Deepgram HTTP integration, central settings and existing app wiring/throttle. No dependencies, locks, workflows or gates changed. The existing `httpx` client and standard-library `wave` module are sufficient for the initial PCM WAV contract.

## Contract and privacy

Authenticated raw `audio/wav`, uncompressed 16-bit PCM, mono/stereo, 8–48 kHz, at most 30 seconds inclusive and 4 MiB. The route checks actual available frames, rebuilds only validated PCM, and never trusts a client duration. V1b must produce compatible WAV; AAC/M4A/WebM are not supported in this slice. This is an integration constraint to review before mobile implementation, not proof of native recorder compatibility.

Key is a central `SecretStr`, empty example value, never mobile configuration. Missing key yields typed retryable `VOICE_UNAVAILABLE`. Only the fixed Deepgram HTTPS origin is called, with no redirects/retries and `mip_opt_out=true`. Response body capped at 64 KiB, compressed responses refused, transcript constrained to the existing search length. Upload plus provider has an overall deadline and bounded per-process concurrency; voice uses the existing discovery IP quota. Cancellation/timeout releases capacity. Logs contain only bytes, audio duration and server latency. No audio/transcript files, cache records or DB writes are introduced.

Sources checked 2026-11-06: [Deepgram pre-recorded REST](https://developers.deepgram.com/reference/speech-to-text/listen-pre-recorded), [data retention/opt-out](https://developers.deepgram.com/trust-security/your-data). Retention opt-out can affect provider pricing and does not eliminate provider usage metadata. HTTPS termination and disabled body capture in proxy/APM remain deployment responsibilities.

## RED / GREEN

Runtime: Windows, Python 3.11.9, SQLite 3.45.1, existing `E:/OpenSourceProjectFinder/backend/.venv/Scripts/python.exe`; no runtime modification.

- Baseline `python -m pytest backend/tests/test_auth.py -q`: **8 passed**.
- Initial RED exposed two test setup errors (large binary pytest IDs exceeding Windows environment limits; fixture referring to the not-yet-defined setting). These are not counted as behavioral RED. Short parameter IDs and the central setting resolved setup, then all **27 failed** with expected missing-route responses under `python -m pytest backend/tests/test_voice.py -q --tb=no`, exit 1, before route/provider implementation.
- GREEN core suite: **27 passed**. Covers auth, empty key, privacy, size, truncated/invalid WAV, inclusive 30-second boundary, unsupported media, provider 400/401/403/429/5xx, timeout, malformed/oversized JSON and unusable transcripts.
- Follow-up typed rate-limit test RED: **1 failed / 32 passed**, because inherited throttle returned a string detail. GREEN after voice-only typed mapping: **41 passed** for voice plus existing auth. Additional boundary checks cover concurrency admission, timeout and cancellation slot release, unknown-length upload cap, extra WAV data excluded, and provider redirects refused.

Test-isolation incident: the first empty-key GREEN attempt inherited a process environment key despite `_env_file=None`, and appears to have made one real request containing only a synthetic one-second PCM clip (no user audio). This is not manual provider acceptance evidence. Tests now explicitly set the key empty and install a rejecting fake transport by default; every provider test uses `httpx.MockTransport`. No key was printed or recorded. Final automated runs use fakes only.

## Full verification

- `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:reports/backend-coverage.json --cov-report=term --tb=short -q`: exit 0, **989 passed, 65 skipped**, 66.70 seconds. Existing skips include Linux/WAL/hardware-dependent checks; Windows is not evidence that these paths pass.
- `python scripts/quality.py coverage reports/backend-coverage.json`: exit 0, **93.6% combined / 90.9% branches**, unchanged gate.
- `python -m ruff check backend scripts`: exit 0.
- `python -m ruff format --check backend scripts`: exit 0, 68 files formatted.
- `python -m bandit -r backend/app -q`: exit 0, no findings.
- `git diff --check`: exit 0.
- Existing Starlette TestClient/httpx deprecation warning remains; no dependency change to hide it. No configured static Python type checker exists in the backend CI; runtime tests and Ruff ran.

Required Linux CI results belong to the PR checks at the current head. Local WSL tests were not run: memory was initially about 2.2 GiB; after the owner closed apps it rose to about 6 GiB. Only three task-owned stalled log-reader shells were terminated. No user applications were closed.

## Limits and rollback

Manual spoken Deepgram run and release-to-transcript latency: **not verified**. Device recording, light/dark development build, consent/permission, screen reader and mobile cleanup: **V1b, not implemented or verified here**. Server latency does not measure device/network latency. Concurrency is per process, not a distributed quota. No schema/data migration; revert V1a and remove its environment settings to roll back. No self-acceptance, merge or next-task work.
