# V1a — backend transcription evidence

Outcome: merged 2026-11-05 as [PR #65](https://github.com/SumukhaK/open-source-projectFinder/pull/65) (`f4f4bf3c6b25bd819d932ef106765017012bc877`) after trusted review of head `1a9209d` and green CI. Sections below are kept as recorded.

## One authorized manual M4A run — 2026-11-06

Tested head: `c8111f559dc24fb601721d338e4fd68f176a393a`. The owner supplied a saved synthetic-voice AAC/M4A clip and authorized one real Deepgram call. The run used the existing authenticated `/v1/voice/transcribe` route with `Content-Type: audio/m4a`, the server key from the owner's ignored `.env`, and the real provider integration (no fake transport for Deepgram). No retries or second calls were made.

| Measurement | Observed |
| --- | --- |
| Upload-to-transcript latency (saved clip) | 2288.67 ms |
| Bytes | 89330 |
| Provider audio duration | 4.744 s |
| Non-empty transcript returned | true |

Timing used a monotonic clock immediately around the upload request to the app through a local ASGI client, including authentication, route processing and the real outbound provider round trip. It excludes mobile capture/finalization and a device-to-server network hop. It is **not release-to-transcript latency**; that measurement belongs to V1b on device. This is one sample, not a latency distribution or performance guarantee.

Only the four measurements above were output. Neither transcript text nor key was printed or saved; the original clip was read in place and not copied into this checkout. A temporary auth-only database supplied an ephemeral app session and was cleaned up afterward. No production code changed for the run. The manual-run blocker below is historical and is now resolved for saved-clip verification; device checks remain pending.

## Review follow-up — 2026-11-06

Validated implementation head: `48349a8e0277925e80fa41be2d219e617526c329` (the evidence-only commit follows it). This section supersedes the original WAV-only contract below.

- Accept `audio/mp4`, `audio/m4a`, `audio/aac` unchanged with their content type. `VOICE_MAX_COMPRESSED_BYTES` defaults/caps at 1 MiB, checked before any provider call. WAV validation remains unchanged.
- Compressed duration comes from finite positive numeric `metadata.duration`; reject over 30.5 seconds as `VOICE_TOO_LONG`, allowing 0.5 seconds tolerance around the configured 30-second maximum. Missing/invalid metadata fails closed. This check occurs after provider processing and cannot prevent provider usage for rejected overlong clips. Logs contain measurements, never transcript text.
- Added a direct regression asserting the default test app's transport refuses a provider request. The first version crossed pytest's BaseException through ASGI and caused a test-lifespan error; the corrected test exercises the transport directly. Behavioral RED: **11 failed / 34 passed**, all compressed cases rejected with the previous 415. GREEN: **45 voice tests passed**.
- Full backend/scripts suite, same command and Windows runtime as below: **1001 passed / 65 skipped**, 66.11 seconds. Unchanged coverage gate passes at **93.4% combined / 90.5% branches**. Ruff check, Ruff format check, Bandit and `git diff --check` pass. Existing TestClient deprecation warning remains.
- History moved to oldest-first with no extra blank line. Approval date retained as **2026-11-06, Asia/Kolkata**, the date supplied for the approval turn; no alternate approval date has been provided. README explicitly distinguishes server-only `latency_ms` from release-to-transcript timing.
- **Manual run BLOCKED, not performed this round:** owner identified `E:/OpenSourceProjectFinder/backend/.env`; key presence was checked without displaying its value. A short spoken `.m4a` clip/path has not been provided. No transcript or release-to-transcript measurement is claimed. A saved clip alone permits upload-to-transcript measurement; genuine release latency requires a recording-stop timestamp from the same timed session. The one authorized manual call remains outstanding.

Date: 2026-11-06. Status: Awaiting review on [PR #65](https://github.com/SumukhaK/open-source-projectFinder/pull/65); not accepted or merged.
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
