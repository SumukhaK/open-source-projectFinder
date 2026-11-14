# T28a evidence: capacity on the current corpus (2026-11-14)

Status: **Merged (slice T28a), `b6a835e`, 2026-11-14.** The D8 bound and expansion gates below are proposals awaiting the owner. Base `50663f7f14d1c1be11c318f5371dc20792cc2413`, branch `claude/hybrid-t28-capacity`. Measured on the real local stack with the current published archive (**204 repositories**); nothing was ingested beyond it. The 10k measurement is a later slice (**T28b**) that needs the owner's separate 10k approval (D1 caps the archive at 1,000 until then). No behaviour, limit or setting was changed.

Raw sanitized numbers, one JSON object per run: [T28_results.jsonl](T28_results.jsonl). They hold timings, counts, memory and sizes only: no ideas, results, tokens or paths.

## How it was measured

| Item | Value |
| --- | --- |
| Host | Windows 10, Ryzen 7 4800H, 15.8 GB RAM; GTX 1650 Ti 4 GB (driver 617.42) |
| Archive runtime | WSL2 Ubuntu (kernel 6.18.58.1), 16 vCPU, VM capped at ~5.9 GB by the existing `.wslconfig`; Python 3.11.17; torch 2.14.1+cpu; sentence-transformers 6.2.0 |
| Model | `intfloat/multilingual-e5-small` (384 dimensions), CPU, worker batch 64 |
| Milvus | 2.6.26 via `E:\OpenSourceProjectFinder-t01\infra\milvus\compose.yaml`, **GPU profile** (the profile the scheduled jobs use); Docker 29.8.2 |
| Code | this branch (= main `50663f7`, ranking `keyword-first-v1`), settings from the scheduler worker's private `backend/.env` (never printed) |
| Tool | new [scripts/capacity_bench.py](../../scripts/capacity_bench.py): `embed`, `search --mode archive/hybrid`, `disk` |
| Ideas | the 58 frozen T27 ideas, cycled |
| Safety | run stopped if Windows available memory < 1,000 MB or WSL free disk < 5 GB; at most 60 GitHub keyword searches in total, paced under the 30/min search limit |

`--mode archive` swaps the GitHub keyword source for an empty answer, so only the archive branch runs: query embedding, Milvus search, then the public-visibility recheck of each archive hit (GitHub REST, worker token). `--mode hybrid` runs the real service. Each request's stages are timed separately. Each run is a fresh process, so the in-memory visibility cache starts empty, as it does after an API restart.

Commands (from WSL, `CAPACITY_ENV_FILE` = the worker's `.env`):

```text
python scripts/capacity_bench.py --out results.jsonl disk
python scripts/capacity_bench.py --out results.jsonl embed --passages 256
python scripts/capacity_bench.py --out results.jsonl search --mode archive --requests 100 --concurrency 1|4|8 --guard-file winmem.csv
python scripts/capacity_bench.py --out results.jsonl search --mode hybrid --requests 39 --concurrency 1 --pause 2.2 --guard-file winmem.csv
python scripts/capacity_bench.py --out results.jsonl search --mode hybrid --requests 19 --concurrency 4 --pause 8 --guard-file winmem.csv
```

Fairness runs repeated `search --mode archive --requests 60 --concurrency 1` while (a) a second process ran `embed --passages 768`, and (b) a real bounded weekly refresh ran from the scheduler's worker checkout: `python -m app.workers.archive refresh --sweep-buckets 1 --cap 0`.

## Results

### CPU embedding throughput

| Run | Passages | Tokens each | Batch | Threads | Seconds | Passages/s | Peak RSS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Alone | 256 | 405 | 64 | 8 | 38.47 | **6.65** | 1,423 MB |
| During the fairness run | 768 | 405 | 64 | 8 | 102.93 | 7.46 | 1,628 MB |

Passages are synthetic neutral text grown to the chunker's 400-token budget, so this is the worst case per chunk. Real chunks are often shorter, which makes them faster. At about 7 passages/s, embedding the full ≤8 chunks per repository takes **about 20 minutes per 1,000 repositories** (≤8,000 chunks) and **about 3.3 hours for 10,000** at worst.

### Search latency (milliseconds)

| Run | Requests | Concurrency | p50 | p95 | Max | Outcomes |
| --- | --- | --- | --- | --- | --- | --- |
| Archive, cold cache | 100 | 1 | 120 | 5,485 | 8,009 | 95 ok, 5 archive timeout |
| Archive, repeat | 100 | 1 | 107 | 3,348 | 8,010 | 95 ok, 5 archive timeout |
| Archive | 100 | 4 | 864 | 8,009 | 8,013 | 84 ok, 16 archive timeout |
| Archive | 100 | 8 | 253 | 297 | 8,002 | **96 busy**, 4 archive timeout |
| Hybrid | 39 | 1 | **3,674** | **8,014** | 8,014 | 35 ok, 4 degraded (archive timeout) |
| Hybrid | 19 | 4 | 3,878 | 8,017 | 8,017 | 11 ok, 8 degraded (archive timeout) |

The first request of each run took **about 8.0 s** (cold model/collection/caches), recorded separately as `first_request_ms`. Service start-up (model + Milvus connect) took about 14 s.

Stage times inside those requests:

| Stage | p50 | p95 | Notes |
| --- | --- | --- | --- |
| Query embedding (c=1) | 55 | 64 | 137 / 181 at c=4 |
| Milvus search (c=1) | 28 | 40 | 36 / 55 at c=4 |
| GitHub keyword search (hybrid) | 3,590 | 5,363 | 39 calls; 19 more at c=4 (3,463 / 4,261) |
| Public-visibility recheck, per call | 480 | 590 | **about 4 calls per search** (393 for 100 archive searches) |

Semantic retrieval itself (embedding + Milvus) is about **0.1 s**. End-to-end latency is set by GitHub: the keyword search (about 3.6 s) and the per-hit visibility rechecks, which hit the 8 s search budget (`hybrid_search_budget`) for 5% of single searches and 16–42% at concurrency 4.

**Finding (cause of the tail):** `EligibilityService._metadata` only caches a repository that is currently live-eligible. Archive hits that fail the live check are fetched from GitHub again on every search, so about 400 visibility calls were made for 100 searches over 58 ideas. Proposed follow-up, not changed here: also cache the negative decision for the same 15-minute TTL (safe direction: it can only hide a result longer) and/or run the per-hit rechecks concurrently within the existing bounds.

### Admission and busy behaviour

With `hybrid_search_max_concurrent = 4` and `hybrid_search_admission_timeout = 0.25 s`, 8 concurrent clients got **96 of 100 requests rejected as busy within about 0.3 s**. The 4 admitted searches held their slots for up to the 8 s budget. The limiter is bounded and fails fast (no unbounded queue), but slow visibility rechecks collapse useful throughput above 4 concurrent searches on this host.

### Fairness: foreground searches during background work

| Background | Searches | p50 | p95 | Embedding p50 / p95 | Milvus p50 / p95 | Outcomes |
| --- | --- | --- | --- | --- | --- | --- |
| None (archive, c=1) | 100 | 107 | 3,348 | 55 / 64 | 28 / 40 | 95 ok, 5 timeout |
| Worker-sized embedding (768 passages) | 60 | 246 | 8,007 | 114 / 151 | 55 / 78 | 55 ok, 5 timeout |
| Real bounded weekly refresh | 60 | 143 | 8,009 | 57 / 112 | 30 / 131 | 55 ok, 5 timeout |

No foreground search was starved or rejected as busy during background work. Query embedding roughly doubled under a concurrent embedding load and stayed below 0.2 s. The background embedding kept its throughput (7.46 passages/s). The timeouts are the same visibility-recheck tail as without load.

The refresh exited 0 in **486 s** for one sweep bucket over the 204 known repositories: **612 GitHub REST requests**, 0 search requests, 0 admitted (cap 0), 0 failed, result `cap`, coverage `partial`, 204 published.

### Memory, VRAM and disk

| Item | Peak / size |
| --- | --- |
| Search process RSS (model + service) | 1,262 MB |
| Embedding process RSS | 1,628 MB |
| WSL VM available memory, minimum | 3,520 MB of ~5,900 MB |
| Milvus GPU container | 849 MiB |
| MinIO / etcd containers | 155 / 58 MiB |
| GPU memory (nvidia-smi, 5 s samples) | 372 of 4,096 MiB |
| Windows available memory, minimum during runs | 1,207 MB (guard 1,000 MB, not triggered) |
| Starting Docker Desktop alone, with the owner's apps open | Windows available fell from 3.3 GB to 0.57 GB; run aborted and Docker stopped; measurements were taken after the owner closed apps |
| Milvus volumes (gpu / minio / etcd / cpu) | 11.7 / 21.1 / 145.4 / 7.6 MB |
| Catalogue (SQLite + WAL) / raw content / encrypted backup repository | 2.0 / 1.6 / 1.7 MB |

Container memory and VRAM come from `docker stats` and `nvidia-smi` every 5 s (624 samples). Peaks between samples may be missed.

### GPU

A usable GPU exists and Milvus runs on its GPU profile (372 MiB VRAM at peak). **GPU embedding was not measured:** the pinned runtime is CPU-only torch (`2.14.1+cpu`, `torch.cuda.is_available() == False`) and `EmbeddingAdapter` pins `device="cpu"`. Comparing it would need a CUDA torch dependency change, which is out of scope. A Milvus CPU-vs-GPU comparison was not repeated at 204 repositories; T01 found no meaningful difference at 1k vectors.

## Proposals (need owner approval; nothing is activated)

1. **D8 response time (proposed):** the server always answers within its 8 s budget (`hybrid_search_budget`), degrading rather than hanging. Measured today: hybrid p50 3.7 s, p95 8.0 s. The planned hypothesis "hybrid p95 < 5 s, warm semantic p95 < 2 s" **is not met** end to end. The semantic part alone is about 0.1 s. Proposed target: **hybrid p95 ≤ 5 s at concurrency 1 after the visibility-cache follow-up lands**, measured with this script; until then the bound is the 8 s budget.
2. **Expansion gates (proposed):**
   - Growing toward the approved **1,000** cap is within measured capacity: about 20 min of embedding, Milvus under 1 GB, disk in MB.
   - **10k (T28b)** only after the owner approves, and only once the visibility-recheck tail is fixed, because that cost grows with the number of archive hits. Re-run this benchmark at 1k and 10k: no OOM, host available above 1 GB, foreground archive p95 below the D8 bound at concurrency 1 and 4, no busy rejections at concurrency ≤ 4, and embedding of the full 10k within one weekly window (about 3.3 h measured worst case).
   - **25k / 50k:** not proposed for this host. The VM cap (~6 GB), the 4 GB GPU and the observed host memory pressure (Docker Desktop start alone took about 2.7 GB) need a separate measured plan and approval.
3. **Host operating note:** run archive jobs with heavy apps closed. Starting Docker with the usual apps open took Windows below 1 GB available.

## Not measured / limits

- 1k and 10k corpora (T28b; 1k growth is allowed by D1 but was out of this slice's scope, 10k needs approval).
- Disk and time for a full vector rebuild (`restore --activate`, which stops the API): not run here; T22 evidence covers a real restore into quarantine.
- VRAM pressure: GPU memory stayed at 372 of 4,096 MiB at this corpus size, so no pressure behaviour was observed.
- The API was measured in-process, not over HTTP. T26 covers the HTTP path; HTTP and auth overhead are not included here.
- The first archive run (`archive-c1`) predates two small tool fixes: its `github_search_calls` counts the empty stand-in (all 0 ms), and its outcome keys lack the failure reason. Later runs record real GitHub calls only and the reason (`timeout`, `busy`).
- No unbounded soak test: each run is at most 100 requests.

## Verification

- `python -m pytest scripts/tests/test_capacity_bench.py -q`: 4 passed (summary maths, memory guard, stage timer, concurrency bound and outcome counting).
- `ruff check backend scripts`, `ruff format --check backend scripts`, `bandit -r backend/app`, `git diff --check`: see the PR.
- Real-stack runs above: every run exited 0; the memory guard did not trigger during the measured runs.

Rollback: revert this PR. It adds a benchmark script, its test, this evidence and tracker lines only. No production code, setting, migration or data change. The refresh run was the normal weekly job's own command, bounded to one sweep bucket with no new admissions.
