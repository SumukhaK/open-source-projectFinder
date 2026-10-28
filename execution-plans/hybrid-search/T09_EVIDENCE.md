# T09: Single-repository ingestion evidence

Date: 2026-10-29. [PR #34](https://github.com/SumukhaK/open-source-projectFinder/pull/34). Status: Awaiting review; real integration evidence **BLOCKED**.
Branch: `codex/hybrid-t09-one-repository`.
Original base: `d1ae76139ba80dd3eac5d3b5dc1656a41387eb35`.
OpenCode's existing work was preserved as `9bfed5a`; main
`62a316d0dc1454f49a3e443bdf26779c337bcb73` was merged with merge commit
`43194db0bbcf864452eb1dba34cc37a6bba39e98`. A final fetch found main unchanged.
T04/T05/T08 are merged prerequisites. The PR description records the final head
and required CI run; no acceptance, review marker or merge is claimed.

## Implemented contract

Run `python -m app.workers.archive ingest --repo-id <numeric-id>` from `backend/`
with the dedicated Linux worker interpreter and private configuration. IDs must
be positive signed-64-bit integers. Preflight checks settings, a dedicated token,
an explicitly populated licence allowlist, both content/catalogue free-disk
locations (default minimum 2 GiB), WAL-capable catalogue, pinned offline E5 model,
and T07 Milvus 2.6 family/collection/index/load contract. It reuses existing
adapters; no interpreter, dependency, workflow or quality-policy changes.

Metadata is acquired through `/repositories/{id}` and its numeric ID verified.
Policy refusal precedes README acquisition: public, not archived, not a fork,
pushed at or after the fixed request UTC time minus 365 days, and an allowed SPDX
licence. `ARCHIVE_LICENSE_ALLOWLIST` has no built-in approved entries: empty
means refuse everything. D2 remains pending. README/blob reads reuse T04's
validated canonical route and content-verified blob identities; metadata is
rechecked by numeric ID after content acquisition to reject an intervening move
or eligibility change. Owner/name is never the repository identity.

T05 prepares passages; missing README produces metadata-only content. A complete
T08 active revision with the same semantic hash returns `unchanged` before T06
persistence, with zero embedding calls and zero vector writes. This also handles
nonsemantic raw README changes without conflicting with immutable T06 source
objects. Otherwise T06 persists, T02 embeds, T07 builds vectors, T08 publishes and
reconciles. Interruption before SQL activation preserves the previous active
revision; replay uses deterministic IDs. An incomplete active catalogue does not
qualify as an unchanged replay.

A review found that token-bounded section titles can exceed Milvus's 512-byte
section limit. Preparation now applies both limits, includes the byte budget in
the semantic identity, and preserves that exact section through publication.
This changes prepared revision identities relative to earlier T05 output;
existing published revisions remain readable and a new ingestion publishes the
new identity safely. No catalogue migration is added or edited.

Output is sanitized JSON: ID/revision, counts, timings and result. Provider/model/
storage exception messages are not echoed. `embedding_calls` counts logical
adapter calls (one call may contain several encoder batches), not HTTP calls or
model batches. Cleanup and malformed JSON settings failures return non-zero
with safe messages. T19/T20 retain scalar-metadata refresh and suppression
recovery; T09 never clears T10 suppression. Production serving remains gated by
D4 and later integration tasks.

## TDD and verification

OpenCode's historical RED output was not available; its inherited worker and
HTTP tests ran first: **177 passed**. No retroactive TDD claim is made for them.
New regression runs, all using fake HTTP/model/Milvus:

| Regression group | RED observed before fix | GREEN |
| --- | --- | --- |
| Safe errors/cleanup, licence-before-content, signed-64-bit ID, nonsemantic replay | 6 failed, 27 passed | 184 worker/HTTP tests passed |
| Incomplete active repair; catalogue as well as content disk check | 2 failed, 1 passed, 33 deselected | 36 worker tests passed |
| Malformed JSON environment configuration gets actionable sanitized error | 1 failed, 40 deselected | 41 worker tests passed |
| Long, low-token-count section heading preserves publication identity | 1 failed, 41 deselected (`vector section does not match`) | 103 worker/chunker tests passed |

The licence-before-content regression was subsequently corrected to fail on the
actual `fetch_readme` call (rather than the obsolete combined acquisition call);
the focused test passed. Additional tests cover fake HTTP end-to-end publish /
unchanged replay / `filter_active_hits`, rename and private transitions during
acquisition, cutoff boundary, missing README, invalid models and server contracts,
and interrupted vector publication without duplicate IDs. The final read-only
implementation review found no remaining important implementation defects after
the heading fix; it is not PR acceptance.

Windows Python 3.11.9 / SQLite 3.45.1 verification:

```text
python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:reports/t09/coverage.json -q
701 passed, 49 skipped, 1 existing Starlette/httpx deprecation warning
python scripts/quality.py coverage reports/t09/coverage.json
94.2% combined; 92.1% branches (unchanged 90/80 gate)
python -m ruff check backend scripts
python -m ruff format --check backend scripts
python -m bandit -r backend/app -f json -o reports/t09/bandit.json
git diff --check
```

All listed checks passed. Final test-only correction was verified separately.
Local ignored logs are under `reports/t09/` (including RED/GREEN and coverage).
Windows store tests retain their platform skips. Worker unit fixtures use a
transactional catalogue without enabling WAL; they do not prove WAL support on
this unpatched Windows runtime. Production `ArchiveStore` still refuses it.
Linux CI uses the existing pinned Python 3.11.17 / WAL-fixed SQLite runtime and
must pass the complete Linux suite. The CI link and results belong in the PR.

## Real evidence: BLOCKED, not simulated

No live GitHub fetch, real E5 embedding or real Milvus ingestion/search was run.
The owner has not yet supplied an approved numeric repository ID, URL and exact
licence, or confirmed the dedicated P1 worker credential. Approval was requested;
no token value should be posted. WSL startup also failed with
`HCS/ERROR_NO_SYSTEM_RESOURCES` even after a 7.54 GiB available-RAM check. No apps
were closed, WSL limits changed, interpreter modified or packages installed.

Acceptance still requires the approved local-profile run: first ingestion
publishes, second returns unchanged with zero embedding calls, and a real T07
search returns its chunks through T08 `filter_active_hits`. Fake integration
coverage cannot replace those observations. Keep D2/P1/P3 and production D4 gates.

## Operator recovery / rollback

Before running, approve the sample/licence, configure private credentials and
Linux-native catalogue/content paths, cache the pinned model, and bring up the
approved local Milvus profile. Keep `HF_HUB_OFFLINE=1`. Do not use `/mnt/c` or
`/mnt/e` for the live catalogue. The command does not download a model.

On failure, correct the sanitized preflight cause and retry the same numeric ID.
Before activation the previous revision stays active; after activation the new
revision is active even if retirement is deferred. Stopping the worker does not
undo an already activated revision. Keep the catalogue/content/vector data
intact; do not delete volumes or edit active pointers to roll back. Reverting
this code stops the new command but does not revert published data.
