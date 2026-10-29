# T09: Single-repository ingestion evidence

Date: 2026-10-29. [PR #34](https://github.com/SumukhaK/open-source-projectFinder/pull/34). Status: **Merged** as `7766744` (2026-10-29) after exact-head acceptance of `722e62a` ([review 5694484582](https://github.com/SumukhaK/open-source-projectFinder/pull/34#pullrequestreview-5694484582)); owner-approved single-repository GPU-profile functional pilot **PASSED**. Tiny-sample search does not establish CAGRA acceleration; see the live evidence below.
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

## Initial real-evidence blocker (resolved by the approved pilot below)

At the initial implementation handoff, no live GitHub fetch, real E5 embedding or real Milvus ingestion/search had run.
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

## Owner-approved live pilot — 2026-10-29

Authorization: **only** [fastapi/typer](https://github.com/fastapi/typer), numeric
repository ID **229937405**, licence **MIT**. This is narrow D1/D2 approval for one
repository, not approval of a wider MIT corpus or bulk ingestion. The catalogue
contains exactly one repository, and its stored canonical name/licence match that
approval. No other repository was ingested. P1 was supplied privately for this run;
production D4 and broader readiness/capacity decisions remain pending.

Tested application head: `7da7f406d1b19e84dde31e1fec4f680ee3b8da92`.
This follow-up changes evidence/documentation only. Latest main `62a316d` was
fetched and was already an ancestor through merge commit `43194db`; no redundant
merge was created. Final follow-up head and required CI are in PR #34's description.

### Runtime and preparation

- Backend source: `/mnt/e/OpenSourceProjectFinder-t09/backend`; interpreter:
  `/home/sumukha/reporadar-worker-venv/bin/python`, Python 3.11.17 / SQLite 3.53.1,
  `wal_is_fixed=True`; actual pilot catalogue `journal_mode=wal`.
- Pilot catalogue/content: `/home/sumukha/reporadar-t09-pilot/` on Linux-native
  storage. Private root mode 0700; no catalogue under `/mnt/e`.
- The token was found in the main checkout's ignored `.env`; only
  `ARCHIVE_GITHUB_TOKEN` and `ARCHIVE_LICENSE_ALLOWLIST=["MIT"]` were copied to
  the ignored T09 backend `.env`. No credential value was printed or committed.
  Milvus credentials were read privately from the existing T01 Compose `.env`.
- The worker venv lacked the optional embedding stack. Installed the unchanged
  `backend/requirements.embeddings.lock.txt`; a slow WSL download was interrupted,
  then the same pinned Linux wheels were downloaded through Windows and installed
  offline into that venv. `pip check`: no broken requirements. Neither interpreter,
  system SQLite nor repository dependency pins changed. Existing cached E5 weights
  were loaded offline (`HF_HUB_OFFLINE=1`) and verified by the T02 loader.
- NVIDIA GTX 1650 Ti, 4096 MiB, driver 617.42; CUDA container pre-check passed.
  Existing pinned Compose GPU profile became healthy in **18.61 seconds**.
  Server reports `2.6-20261023-b8d2ca4240`; collection `repo_chunks_e5small_v1`,
  configured index `GPU_CAGRA`, IP, no CPU-profile fallback.

The local ignored helper invokes the actual worker `main(['ingest', '--repo-id',
'229937405'])` twice in separate processes with those environment settings. Search
uses a real T02 query embedding, T07 `search(limit=8,
filters=ScalarFilters(repo_id=229937405))` and T08 `filter_active_hits` in a catalogue
read transaction. Query text was the synthetic phrase `command line interface`;
no user idea/transcript was used. Only IDs/counts were emitted for hits.

The first attempt exited 1 at storage preflight because the newly created pilot
parent directory was 0755. It was made private (0700), leaving the guard unchanged;
that attempt fetched/published nothing. The next three successful operations all
exited **0**:

### First successful ingestion

```json
{
  "chunks": 8,
  "embedded_chunks": 8,
  "embedding_calls": 1,
  "readme": "present",
  "reconcile": {
    "documents": 0,
    "pending": 0,
    "vectors": 0
  },
  "repo_id": 229937405,
  "result": "published",
  "revision": "871e488937e2c7e25078311102f64f842f1f7bdfecd1b279dcc4e3e4d7b126c1",
  "timings_ms": {
    "acquire": 697.977,
    "embed": 1814.497,
    "persist": 27.285,
    "prepare": 1167.883,
    "publish": 64.462,
    "reconcile": 0.726,
    "total": 16966.894
  },
  "vectors_written": 8
}
```

### Second ingestion: unchanged replay

```json
{
  "chunks": 8,
  "embedded_chunks": 0,
  "embedding_calls": 0,
  "readme": "present",
  "repo_id": 229937405,
  "result": "unchanged",
  "revision": "871e488937e2c7e25078311102f64f842f1f7bdfecd1b279dcc4e3e4d7b126c1",
  "timings_ms": {
    "acquire": 558.644,
    "prepare": 1071.421,
    "total": 9723.974
  },
  "vectors_written": 0
}
```

Same revision, **0 embedding calls, 0 embedded chunks, 0 vector writes**.

### Real T07 search through T08 active filtering

```json
{
  "active_hit_count": 8,
  "hits": [
    {
      "chunk_id": "b6dcf818d75117f29809bfa96ecba3ac3ecbf63583d1c6f34a6659b450846a5e",
      "ordinal": 1,
      "repo_id": 229937405,
      "revision": "871e488937e2c7e25078311102f64f842f1f7bdfecd1b279dcc4e3e4d7b126c1"
    },
    {
      "chunk_id": "30a3f65be794c03f552f88ad9ec7059ebb836b8e3a66c7e3141d2aa6d083a552",
      "ordinal": 6,
      "repo_id": 229937405,
      "revision": "871e488937e2c7e25078311102f64f842f1f7bdfecd1b279dcc4e3e4d7b126c1"
    },
    {
      "chunk_id": "a07023dd43b48b96e6a999a9502cd5142971a1ded2846f042baf49b508194b93",
      "ordinal": 4,
      "repo_id": 229937405,
      "revision": "871e488937e2c7e25078311102f64f842f1f7bdfecd1b279dcc4e3e4d7b126c1"
    },
    {
      "chunk_id": "3026f7ce527e1664f34e89c6773d200c05d3ac98820d9c895c8439c52e486aee",
      "ordinal": 7,
      "repo_id": 229937405,
      "revision": "871e488937e2c7e25078311102f64f842f1f7bdfecd1b279dcc4e3e4d7b126c1"
    },
    {
      "chunk_id": "cc3b0032aeab27f0646ca826101d8ae92ada5971c614616b15c7dff74458b300",
      "ordinal": 5,
      "repo_id": 229937405,
      "revision": "871e488937e2c7e25078311102f64f842f1f7bdfecd1b279dcc4e3e4d7b126c1"
    },
    {
      "chunk_id": "7df64ced4244a89d75577536015a7f0cc33f46dbf80201a858c09d6848615edd",
      "ordinal": 3,
      "repo_id": 229937405,
      "revision": "871e488937e2c7e25078311102f64f842f1f7bdfecd1b279dcc4e3e4d7b126c1"
    },
    {
      "chunk_id": "24d7b84fccde449835260912dee16805669b16fcd8feaf87fd7839c96ec48a59",
      "ordinal": 2,
      "repo_id": 229937405,
      "revision": "871e488937e2c7e25078311102f64f842f1f7bdfecd1b279dcc4e3e4d7b126c1"
    },
    {
      "chunk_id": "8541f7e6137127b4a30882b88e52f2e5e4b631089e86bf26e7f9214459c225e9",
      "ordinal": 0,
      "repo_id": 229937405,
      "revision": "871e488937e2c7e25078311102f64f842f1f7bdfecd1b279dcc4e3e4d7b126c1"
    }
  ],
  "index_type": "GPU_CAGRA",
  "profile": "gpu",
  "raw_hit_count": 8,
  "repo_id": 229937405,
  "result": "passed"
}
```

All eight hits belong to the active published revision and the approved numeric
ID. This validates the live fetch/model/publication/replay/search/filter path.
It does **not** prove GPU-accelerated indexing for this sample: index inspection
reported `Finished`, `total_rows=0`, `indexed_rows=0`, `pending_index_rows=0`.
The eight rows are queryable through Strong consistency but below the configured
64-row indexing threshold; growing-segment/flat search can serve them. No filler
rows, threshold changes, larger corpus or forced flush were introduced to disguise
that limitation. T07's existing separate 1,000-row proof covers its prior indexed
GPU check; this run supplies no new capacity, relevance or performance claim.

### Resources, cleanup and retained evidence

The temporary monitor sampled at approximately two-second intervals (325 samples,
07:36:40–07:48:13 UTC). Minimum available Windows RAM was **1.241 GiB**; sampled
VRAM maximum was **208 MiB / 4096 MiB**. These are sampled readings, not guaranteed
instantaneous peaks. The below-1-GiB automatic stop did not fire.

| Container | After first ingestion | After replay | After search |
| --- | --- | --- | --- |
| GPU Milvus | 328.4 MiB / 4 GiB | 335.6 MiB / 4 GiB | 344.4 MiB / 4 GiB |
| MinIO | 97.14 MiB / 512 MiB | 100.7 MiB / 512 MiB | 103.5 MiB / 512 MiB |
| etcd | 39.93 MiB / 256 MiB | 45.57 MiB / 256 MiB | 39.21 MiB / 256 MiB |

Owner-authorized RAM cleanup closed background Edge, Slack, WhatsApp, Boom3D and
optional assistant context-compression helpers. Active database/security services
were preserved. The pilot GPU/MinIO/etcd containers were stopped with ordinary
Compose `down`; volumes, collection, catalogue and content were preserved. The
resource monitor was stopped; no `down -v`, prune, WSL shutdown, host-limit changes
or driver installation occurred. Docker Desktop/WSL remain running.

Ignored local evidence under `reports/t09/` is intentionally not uploaded as raw
logs. The following hashes bind the sanitized JSON artifacts copied above:

| Artifact | SHA-256 |
| --- | --- |
| `live-first-publish.json` | `fdbfbc92805153296b74e7e7b003ca54cff083d86bb15a75cefb88d033edef34` |
| `live-second-unchanged.json` | `1e7b21d43ba7776849314fd7ce7ef5a4f03f7992ecaf1cf8cd4490c0152301c3` |
| `live-search.json` | `08649751f61b874253070f03b14e71cd92322ac31660e39b2d30fda138de9fe5` |
| `live-verification.json` | `68553c669617c9fb53409b05e1ccdd22f5f05d0f227885d40d1d82e1e07e6dbb` |
| `resources.jsonl` | `950510275609ddda9a4c0f866bd69cba21c0e85132ee1d8988ec90d5edc7275f` |
