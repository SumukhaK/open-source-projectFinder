# T07 Milvus adapter evidence — 2026-10-27

Status: **Merged** via [PR #28](https://github.com/SumukhaK/open-source-projectFinder/pull/28) as `21e6db3` (2026-10-27) after exact-head review of `265d342` and passing [CI 40484923241](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40484923241). T07 only; no acceptance, merge, ingestion, alias activation, API wiring or T06/T08 work. Exact head/CI links are recorded in the PR description and [TRACKER](TRACKER.md).

## Base and scope

- Branch `codex/hybrid-t07-milvus-adapter`, created from fetched `origin/main` at `c821ce1e93c144482c6aaf934e7db6d88306464c`.
- While T07 ran, T06 and T16 merged independently. Main `e9b95ded3455dec7ee61df74c1fae2cb5300c0e2` was merged into this same branch with a merge commit to unblock PR CI. Documentation conflicts retain both tasks and T07; central configuration retains every T06 and T07 bound. No T06/T16 implementation was changed. Relative to current main, the PR remains T07 only.
- Merged prerequisites: T01/#15 `7f94e2f`, T02/#16 `e400076`, T03/#18 `776bf65`. The existing checkout was clean; unrelated worktrees were not edited.
- Production files: `backend/app/integrations/milvus.py`, central `backend/app/core/config.py` and placeholder `.env.example`; unit and opt-in real-server tests plus documentation. No dependencies, locks, workflows, SQL migrations or security exceptions change.
- Current source was read directly because the available code index describes an older checkout and misses the archive modules. Existing T02 manifest, T03 catalogue keys and T05 chunk identities were reused.

## Contract and decisions

The explicit GPU profile uses GPU_CAGRA/IP; explicit CPU uses HNSW/IP. There is no profile fallback. The generation fingerprint covers the pinned model manifest, E5 prefixes, unit normalization/IP and scalar/schema version. The selected canonical collection must match its description, exact bounded fields, 384 dimensions, Strong consistency, primary key and disabled dynamic fields. No extra collection, alias switching or repair/drop of an existing mismatch is performed.

At most 64 rows/IDs per operation; search defaults to 200 and caps at 1000. Metadata is typed and bounded in UTF-8 bytes. Full text stays outside Milvus; snippets are at most 2048 bytes. Language/license/activity/repository filters use template parameters. The vector query is transient and not logged or written. Search returns chunk evidence, not final eligible repository results; T08/T10/T13 still own active revisions, visibility, repository collapse and hybrid orchestration.

Upsert count/IDs must match the complete batch. Replays retain stable keys. `ready()` performs Strong read-back of expected metadata and vectors, so a partial batch or stale revision cannot authorize publication. It does not perform SQL activation or claim that growing rows are physically indexed. The real test separately flushes and verifies all rows indexed. Pending/missing index load raises unavailable, not an empty search.

Each call receives the remaining operation budget; late success is rejected. The pinned synchronous SDK has finite internal retries/polling that can overshoot an in-flight budget. This is a **soft timeout, not hard cancellation**; a late write may have happened and must be reconciled/replayed with the same IDs. No extra adapter retry loop, executor or speculative scheduler is added. T13 must bound blocking admission/cancellation when wiring the async API.

SDK diagnostics on the synchronous path are replaced with a safe event message, preserving logger/level but omitting raw request/error data. Credential values are excluded from settings repr. Missing/default/short credentials fail before connection. All service access is loopback; no model download or GitHub content is involved.

## Test-first record

Commands use the existing Windows Python 3.11.9 environment with PyMilvus 2.6.17, from the repository root and `PYTHONPATH=backend`. Logs are private/ignored under `reports/t07/`.

| Stage | Actual result |
| --- | --- |
| Baseline `python -m pytest backend/tests scripts/tests -q` | Exit 0: 390 passed, 40 existing POSIX-only catalogue skips; one inherited Starlette/httpx deprecation warning |
| Initial `python -m pytest backend/tests/test_milvus.py -q` against skeletal methods | Exit 1: 60 expected failures, 1 pre-existing settings-repr pass; missing bounded settings/schema/manifest/filter/mutation/readiness behavior |
| Initial implementation | Exit 0: 61 passed. An intervening test used `IndexParams.to_dict()` incorrectly; corrected to `[0].to_dict()` after reading the installed SDK. That fixture error is not counted as RED. |
| Hardening | Credentials/connection, raw SDK diagnostics, unfinished index and malformed response failures recorded before fixes; focused suite then 70 passed. Missing connection methods were scaffolded and rerun before implementation. |
| First real GPU attempt | All 1000 rows upserted/readable/indexed, then search failed because the SDK returns the custom PK `chunk_id` outside `entity`, not generic `id`. Test collection removed; owned containers stopped and logs retained. |
| SDK-shape/server-family regression | Exit 1: 3 failures before fix, using the real SDK `Hit` object. Exit 0 afterward: 72 focused tests. |
| Read-only implementation review | Found late SDK success accepted after deadline and legacy `compatible_code=RateLimit` treated as permanent. Two regressions failed first (exit 1); post-call budget check and compatibility-code mapping fixed both (74 focused passed). No other important findings reported; this is not trusted PR acceptance. |
| Final Windows full suite + coverage | Exit 0: 464 passed, 41 skipped (40 existing POSIX catalogue tests + 1 opt-in real-server test). 95.3% combined / 93.4% branch coverage; unchanged policy passes. |
| Final WSL full suite + coverage | Exit 0: 504 passed, 1 opt-in real-server skip; Python 3.11.17 / SQLite 3.53.1 / PyMilvus 2.6.17. All 40 catalogue tests execute on Linux. 98.4% combined / 97.3% branches; unchanged policy passes. |
| WSL after merging main T06/T16 | Exit 0: **598 passed, 1 opt-in real-server skip**; unchanged coverage gate **97.5% combined / 96.2% branches**. Ruff check/format (37 files) and Bandit passed. Every T06/T16 test is included. |
| Ruff check / Ruff format --check / Bandit | Exit 0; 33 Python files formatted; no Bandit findings |

Full commands: `python -m pytest backend/tests scripts/tests -q --cov=backend/app --cov-branch --cov-report=json:reports/t07/coverage.json`; `python scripts/quality.py coverage reports/t07/coverage.json`; `python -m ruff check backend scripts`; `python -m ruff format --check backend scripts`; `python -m bandit -r backend/app -q`. The real-server opt-in is run separately as below, not inferred from a skipped test.

The same checks passed in Ubuntu with `/home/sumukha/reporadar-worker-venv/bin/python`, using `reports/t07/linux-coverage.json`. The interpreter was unchanged; catalogue test files were in Linux temporary directories. WSL startup succeeded after the user-authorized cleanup reached6.19 GiB RAM. Ruff/format/Bandit passed there too. Static checks resolved64 local links in changed root/backend/evidence documents; `git diff --check` passed after removing a trailing blank line.

## Real GPU result

Server image is the unchanged digest-pinned Milvus 2.6.26 GPU image `cb9fde8ccd5bb1b4eada5672e98b8da1f848eb5adf44b15e4f8c5f2ee43f07e7`. Server reports `2.6-20261023-b8d2ca4240`, SDK 2.6.17, Windows Python 3.11.9, driver 617.42, GTX 1650 Ti / 4096 MiB. Existing authenticated T01 Compose stack and private credentials were reused without printing secrets or changing limits. Docker 29.8.2. No CPU fallback.

`RUN_MILVUS_INTEGRATION=1 MILVUS_PROFILE=gpu python -m pytest backend/tests/test_milvus_integration.py -q -s` (equivalent PowerShell environment assignments) exited **0: 1 passed in 7.94 seconds** after the custom-PK fix. Synthetic seed17, 1000 unit-normalized 384-dimensional vectors; 5.938 seconds measured inside the test excluding connection/cleanup. Generation `df9cf05b1daae6801246d15bd9655a33b91241a686acc5cdef8e95a9a901ad7c`.

- Index: GPU_CAGRA, IP, `NN_DESCENT`, intermediate graph degree32, graph degree16; `Finished`, 1000 total / 1000 indexed / 0 pending.
- Strong read-back for every batch; max top-K1000 returns all 1000, self-match score approximately1.
- Language/license/pushed-time filters return expected IDs; quote-containing injection-like language matches nothing.
- Update/replay preserves ID and changed snippet; stale read-back fails. A synthetic serving alias is rejected as a collection target. Deletion becomes invisible under Strong consistency.
- Test-created collection and alias are removed. The application adapter itself has no collection-drop or alias-mutation API.

Start to healthy: **18.723 seconds** (images already present). All three containers healthy. During 133 samples roughly every2.2 seconds: minimum available Windows RAM **1.294 GiB**, peak sampled VRAM **203 MiB**. Initial GPU idle reading13 MiB. Samples are not exhaustive peaks. Post-success Docker stats: GPU317.7 MiB, MinIO84.1 MiB, etcd17.2 MiB. The below1 GiB guard did not trigger. This is a 1k synthetic correctness check, not a capacity, recall, latency percentile or annual-corpus benchmark.

Initial RAM2.79 GiB prevented startup. The user closed Firefox/OpenCode and authorized cleanup; confirmed background-only Edge startup processes, the NVIDIA overlay and the unused Microsoft Security UI were closed, leaving Defender running. Startup RAM reached6.3 GiB. No active editor/chat process, driver, system Python/SQLite, worker interpreter or `.wslconfig` was changed. GPU stack and task-started Docker Desktop were stopped with volumes preserved. An approval-service usage limit temporarily delayed cleanup; it subsequently completed after the user continued. No desktop files were created.

Private evidence: `reports/t07/gpu-live-repeat.txt` SHA256 `ccb469276d2871c52f44475c15da26f56bb39cf9790c15fd0b7fbdde18254cd6`; verified from the local artifact. `reports/t07/resources.jsonl` SHA256 `abb9d9d6554227f93e4f5087e86198a994c3d9fe499a1bd2b41bceb687e86ede`. Raw logs are not uploaded. The later deadline/rate-limit fixes were unit-tested; they do not change the successful vector/schema path. Exact-head CI remains required.

## Compatibility, rollback and limits

No catalogue migration or archive content change. Existing T01 collections are left intact; the opt-in proof uses unique disposable names. Repeated setup checks the existing schema and never drops a mismatched collection. Rollback is a code revert after stopping consumers; preserve real collections/volumes. A model/schema change must use a new collection and a separately validated T08 activation record.

T07 real CPU execution was not repeated; T01 has CPU proof and T07 unit tests check explicit HNSW/IP. No real GitHub data, public serving, ingestion, weekly refresh, relevance/capacity test or container-image security scan. No dependency pins or exceptions changed; required CI audits the locks. The inherited node-forge exception still expires2026-11-01 and must not be extended by this task.

## Authoritative sources

- [PyMilvus 2.6 collection creation](https://milvus.io/api-reference/pymilvus/v2.6.x/MilvusClient/Collections/create_collection.md) and [description](https://milvus.io/api-reference/pymilvus/v2.6.x/MilvusClient/Collections/describe_collection.md): explicit schema, dynamic fields, primary key and consistency.
- [2.6 filter templates](https://milvus.io/docs/v2.6.x/filtering-templating.md) and [search API](https://milvus.io/api-reference/pymilvus/v2.6.x/MilvusClient/Vector/search.md): separate template values, search bounds/output.
- [GPU_CAGRA](https://milvus.io/docs/v2.6.x/gpu-cagra.md): candidate `itopk_size` at least top-K (1024 for1000); T01's measured build settings retained.
- Installed **PyMilvus2.6.17** source `milvus_client/milvus_client.py`, `client/search_result.py`, `decorators.py`: custom primary-key result shape, upsert count/IDs and retry/compatibility-code behavior. Current web docs alone were insufficient for the exact hit shape.
