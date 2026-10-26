# Local Milvus archive, weekly refresh and hybrid discovery

Planning date: **2026-10-24**. Status: **proposed design; not implemented**.
This is the proposed architecture snapshot. The executable slices and review evidence live in [TRACKER.md](TRACKER.md); the root PROJECT_TRACKER.md records the delivery phase. Existing unfinished search/mobile/security work is preserved.

## 1. Confirmed goal and scope

The app's normal search is **hybrid**: one user submission searches GitHub's live repository Search API and our local Milvus archive, then presents a single deduplicated, ranked result list. Both retrieval branches are core requirements, not optional future product modes. Build the archive from public GitHub projects with **code pushed in the preceding 365 days**, refreshing it weekly. Use **Milvus**, with GPU acceleration where the laptop passes a compatibility and capacity test.

The 365-day restriction is an **archive eligibility policy**, not an implicit filter on the live GitHub branch. Preserve the live branch's broader public/unarchived search unless a shared activity filter is explicitly requested later. A repository absent from Milvus, outside its pilot cap or older than the archive window may still appear from GitHub. Never require a repository to occur in both sources to be included.

The rolling window is based on GitHub's reported `pushed_at`, not repository creation date or a metadata-only `updated_at`. It is an eligibility signal, not proof of meaningful changes to the default branch. At run start R, pin the discovery interval to `[R - 365 days, R]` in UTC. On 2026-10-24 the lower calendar date is 2025-10-24. Recheck eligibility at query time as the rolling cutoff moves.

This archives each selected project's latest observed state. It does **not** reconstruct every historical README/commit from the preceding year. Source-code indexing, issues, contributors, releases, dependencies and historical analytics are not initial ingestion inputs. Existing on-demand repository details can continue fetching their current optional sections.

**Proposed capacity, requiring product approval:** 1,000 repositories for the hardware/quality experiment, then a 10,000-repository pilot with at most 8 chunks per repository. Expand to 25,000/50,000 only after measured memory, API cost and retrieval quality permit it. These are coverage caps, not a claim that GitHub has only this many active projects. Exhaustive global coverage is not a credible promise for a 4 GB laptop GPU and Search API alone.

## 2. Repository findings from the planning workspace

| Area | Observed implementation | Consequence for this plan |
| --- | --- | --- |
| `backend/app/main.py` | FastAPI app factory, session validation, request protection, sanitized crash handling | Inject a new discovery service through the app factory; retain authentication and limits. Do not start an ingestion scheduler inside Uvicorn. |
| `backend/app/discovery.py` | Public GitHub keyword search, details and account-scoped favourites; search accepts pagination/sort controls | Preserve this endpoint's tested contract for existing callers. Route the updated app to one versioned hybrid endpoint. |
| `backend/app/integrations/github.py` | Synchronous HTTPX reads, bounded retry waits, body-only return, optional 404 handling | Reuse HTTPX/configuration; archive reads need status, headers, validators, redirects and durable retry scheduling. Current `read()` is not sufficient unchanged. |
| `backend/app/core/store.py` | SQLite users, encrypted provider credentials, hashed sessions, favourites and quotas | Keep auth storage separate from the archive catalogue and its write workload. |
| `backend/app/core/config.py` | Central Pydantic settings | Add bounded archive, vector, model and quota settings here; no scattered environment reads. |
| `backend/app/workers`, `services`, `api`, `infra` | Placeholder directories; `services` now contains the T02 embedding adapter | No archive worker, vector integration, scheduler or deployment is implemented. |
| Backend requirements | FastAPI, HTTPX, cryptography, Pydantic settings and verification tools; optional CPU embedding lock | The main lock stays lean; T02 pins the embedding stack separately and the API does not import it yet. |
| `mobile/src/features/discovery/api/projects.ts` (**local, uncommitted workspace file; not on main**) | Workspace client calls `/projects/search`; cards have stable repository IDs. Main's `mobile/src` has only auth and branding features. | Migrate the app's single search action to the versioned hybrid adapter at rollout. Existing callers continue working during migration. |
| Mobile workspace/storage (not on main) | Uncommitted discovery UI; account-specific SQLite caches, transient consented offline ideas, no persistent query history | Preserve privacy rules. A user pull-to-refresh must refresh results, not trigger corpus ingestion. |
| Tests/CI | Existing auth/discovery/provider tests, mobile tests and quality/review workflows | Add focused ingestion tests and a real Milvus integration lane; CPU CI does not verify GPU behavior. |

**Publication baseline:** these observations included unmerged work on `improved-search-endpoint` and local mobile changes. At main commit `2237c7e5241a698258a28952150194b943d616b0`, the legacy search accepts idea/page only and the discovery mobile client is not present. T00 must verify the prerequisite deliveries before tasks rely on them. Do not interpret workspace features as already shipped. As of 2026-10-24 that mobile foundation still has no origin branch or PR (prerequisite P2 in [READINESS](READINESS.md#3-decision-gates)); T24-T26 stay blocked until it merges.

Method: inspected the repository inventory, indexed architecture and search call paths, source for runtime/auth/provider/store/discovery/mobile integration, test coverage areas, requirements and CI. The code graph was generated on October 13 and reported changed metadata; material conclusions were checked against current files. Generated assets, ignored data, credentials and dependency source trees were not treated as project implementation. This is architecture planning, not a new security audit or proof that every existing test currently passes.

## 3. Hardware decision

Read-only inventory on October 24:

| Component | Observed |
| --- | --- |
| GPU | NVIDIA GeForce GTX 1650 Ti; 4,096 MiB VRAM; compute capability 7.5 |
| Driver | 551.61; compatibility with the selected container CUDA runtime still needs testing |
| CPU | AMD Ryzen 7 4800H, 8 cores / 16 threads |
| RAM | Approximately 15.4 GiB usable, shared with Windows and other applications |
| Storage free | Approximately 29.6 GiB on C:, 82 GiB on E: at inspection |
| Runtime | Ubuntu is the default WSL2 distribution; Docker CLI 29.8.2 is present, but the Linux engine did not respond |

The GPU capability is listed in Milvus's supported set, but that alone does not establish a working deployment. Test the Windows driver, WSL GPU passthrough, container runtime and exact Milvus GPU image together. Do not install a Linux display driver into WSL. [Milvus GPU prerequisites](https://milvus.io/docs/prerequisite-gpu.md), [NVIDIA WSL guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html).

Use **Milvus Standalone in Linux containers through WSL2**, initially one replica. The supported Compose deployment includes Milvus's own storage/metadata dependencies; do not omit them or confuse them with our application catalogue. Bind data services to loopback/private container networks, enable authentication, replace example credentials and persist volumes. Reserve disk space for images, indexes, rebuilds and backups before starting. [GPU Compose deployment](https://milvus.io/docs/install_standalone-docker-compose-gpu.md).

Milvus documents 8 GB RAM as a standalone minimum and 16 GB as a recommendation. The laptop's 16 GB is shared with Windows, so it is a constrained development machine, not an assumed production host. The first milestone must measure host/WSL memory and avoid sustained swapping. Do not silently change Docker/WSL memory limits or move its virtual disk. [Standalone requirements](https://milvus.io/docs/prerequisite-docker.md).

**Compute allocation:** reserve GPU headroom for Milvus and the desktop. Run the small embedding model on CPU initially, with one warmed model per API/worker process and bounded thread counts. Do not run a GPU embedding process and GPU index construction concurrently on this card. Later benchmarks may justify time-separated GPU embedding, but this is not the baseline.

Compare GPU_CAGRA with a CPU HNSW baseline using the same vectors. Normalize vectors and use inner product so both profiles share the metric. Implement repository grouping in the application, not GPU grouping/range search. GPU OOM protection is limited; treat memory-pool configuration as scratch allocation rather than a reliable total-VRAM cap. [Versioned GPU limitations](https://milvus.io/docs/v2.6.x/gpu-index-overview.md). Recheck these constraints against the version selected in the hardware spike.

GPU acceleration is an experiment with a CPU fallback **within Milvus**. Milvus cautions that GPU indexes may not improve low-batch query latency. Record the device/profile actually used; a CPU result must not be reported as GPU validated. [GPU index overview](https://milvus.io/docs/gpu_index.md).

## 4. Proposed architecture

```text
Windows weekly task -> WSL worker CLI -> GitHub public APIs
                            |
                   archive catalogue + raw content on SSD
                            |
                 normalize -> CPU embeddings -> Milvus GPU/CPU

                             +-> bounded GitHub keywords -> GitHub candidates --+
Mobile -> FastAPI fan-out ----+                                                 +-> validate/dedup/RRF -> one result list
                             +-> full-idea embedding -> Milvus candidates -----+
```

Keep one codebase and three executable responsibilities: API, resumable ingestion worker and host scheduler. No Kubernetes, Redis, Celery, LangChain or always-running scheduler service is necessary for this laptop pilot.

The mobile app calls FastAPI once; it never queries Milvus or handles ingestion credentials directly. Keyword retrieval and the query-embedding/vector branch run concurrently within bounded source and overall deadlines. A laptop-hosted backend must be awake and reachable for online search; GitHub being online does not make an asleep laptop API reachable. Existing mobile offline caching remains a separate path.

Use a **separate SQLite archive catalogue in WAL mode**, on a Linux-native WSL filesystem, with short transactions and one worker writer. The API can read it concurrently. Persist model/artifact/raw files on the same local Linux filesystem; access paths from Windows only for development. Do not put a live WAL database on a network share or concurrently open it through Windows and Linux SQLite processes. Migrate the catalogue/leases to PostgreSQL before multiple hosts or sustained concurrent writers; leave the authentication migration a separate feature. [SQLite WAL constraints](https://sqlite.org/wal.html).

Verify the SQLite library linked to the **WSL worker/API runtime** before enabling WAL. Require the WAL-reset fix (3.51.3+ or a documented fixed backport such as 3.50.7/3.44.6), not merely a recent Python version. The existing Windows virtual environment reports SQLite 3.45.1; it does not satisfy that version gate and is not evidence about WSL's SQLite. Current auth code does not enable WAL, so this observation is a prerequisite for the proposed archive, not a demonstrated auth corruption defect. [SQLite WAL-reset fix](https://sqlite.org/wal.html#walreset).

Milvus is a derived search index, not the only archive. Retain normalized metadata, bounded raw README content, provenance and version hashes outside it so an index can be rebuilt without repeating every GitHub fetch. Start with private content-addressed files and SQLite references, using the standard library. A separate S3-compatible raw-content bucket is a later deployment choice, not a new initial service.

## 5. Corpus discovery and GitHub API contract

### Eligibility and selection

Initial proposed policy: public, unarchived, nonfork repositories with `pushed_at` in the rolling window. Do not impose a star minimum or silently limit the archive to Python/JavaScript. Keep selection counts by language, activity and star band so the pilot is not solely a popularity list. Missing descriptions/readmes are valid; a useful licensed repository may receive a metadata-only overview vector.

Public visibility is not an open-source license. Record GitHub's license signal and provenance. Before distributing archived README content, define an approved SPDX-license policy; exclude unknown/no-assertion licenses from the full-content pilot unless explicitly approved. This is a product/legal policy to resolve, not a guarantee supplied by the API's license detector. No license claim should be invented for a result.

### Endpoints

| API | Purpose | Fetch policy |
| --- | --- | --- |
| `GET /search/repositories` | Find eligible IDs using public/archive/fork and pushed-time filters | Dedicated worker budget; `per_page=100`; partition queries; inspect `incomplete_results`. |
| `GET /repos/{owner}/{repo}` | Reconcile canonical identity, visibility, license and metadata | Conditional GET; require returned numeric ID to match the expected repository, including redirects. |
| `GET /repos/{owner}/{repo}/readme` | Fetch bounded JSON/base64 README content, path and blob SHA together | Decode with validation/size bounds; record absence separately from a missing repository. |
| `GET /repos/{owner}/{repo}/git/blobs/{file_sha}` | Optional immutable blob fetch if the README response lacks usable inline content | Require the requested/returned blob identity and strict body bounds. Do not use a file blob SHA as a Contents API commit ref. |
| `GET /rate_limit` | Initial credential/quota inspection and diagnostics | Header-driven pacing normally avoids polling this on every request. |

The normal path is metadata plus one README response containing content and its blob SHA, not a separate commit lookup for every file. Record a commit ref only when actually resolved; a blob SHA identifies file content, not a commit. If default-branch identity changes or a rename is observed during acquisition, revalidate the repository ID and retry inconsistent acquisition. This is a latest-observed archive, not an atomic GitHub-wide snapshot. [README/content API](https://docs.github.com/en/rest/repos/contents), [Git blob API](https://docs.github.com/en/rest/git/blobs).

Metadata and visibility caches must be keyed by expected numeric repository ID, not just owner/name. Validate ID equality on every metadata response and redirected destination. If an old name now belongs to another public repository, suppress the original record and discover the replacement separately; it cannot authorize the original's cached README. Use a global-node lookup to recover the original canonical name if needed, or quarantine it rather than guessing. [Repository rename/name-reuse behavior](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository), [global node lookups](https://docs.github.com/en/graphql/guides/using-global-node-ids).

Download URLs are not durable identifiers. Never crawl README links, download images, clone repositories, execute code, install a repository's dependencies or fetch submodules during ingestion. Redirects remain on validated GitHub API origins with a finite hop limit; never forward credentials to an arbitrary host.

### Search completeness

GitHub Search exposes up to 1,000 results per query and can return incomplete results. A single year-wide query cannot enumerate the archive. [Search API](https://docs.github.com/en/rest/search/search).

Persist query partitions and their parent/child relationships. Start with pushed-time intervals over the full rolling year. Split a partition when its reported count exceeds a conservative 750-result threshold or it is incomplete. Use additional disjoint created-time/star ranges where a narrow pushed-time bucket is still dense. Maintain a dedicated catch-all for missing language values if language is ever used to partition. Validate the actual supported qualifier syntax in the acquisition spike. Follow pagination links and deduplicate by numeric repository ID.

Use inclusive boundary overlap with ID deduplication; never drop a boundary timestamp to make paging convenient. GitHub's index changes while pages are fetched, so partitions and counts do not prove snapshot completeness. Retry incomplete partitions with bounded attempts, then report them as unresolved. At the pilot cap, stop deliberately and record `coverage=curated`, selection policy and deferred partitions. Never label a capped or interrupted scan exhaustive.

Weekly discovery prioritizes the last successful discovery boundary minus a 48-hour overlap for new activity, then resumes the remaining rolling-year partitions within quota. Known-repository reconciliation is independent of discovery. A rotating full-window sweep catches eligible old repositories that become public or enter a selection stratum without a new push. Coverage status records how recently each partition was swept; this is not a guarantee of instantaneous global discovery.

### Credentials and rate budgets

Use a dedicated, revocable, operator-owned worker credential with access restricted to public reads, configured separately from end-user OAuth. A fine-grained token's public-repository behavior must be tested with arbitrary public repositories before committing to it; a GitHub App is an alternative if its tested scope and lifecycle fit. Do not harvest user tokens for background work or rotate tokens to evade limits. A token on the same GitHub user may share that user's quota despite having a separate environment variable.

The published baseline authenticated REST allowance is 5,000 requests/hour; actual headers and credential type decide the allowance. Reserve headroom, checkpoint until reset and respect secondary limits. At a 4,000-request/hour working budget, 20,000 noncached requests require at least 5 hours. This is illustrative API arithmetic, not a measured backfill time. [GitHub rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).

Track search and ordinary REST buckets separately. Persist `next_attempt_at` for long waits instead of sleeping in a request handler. Honour Retry-After/reset, use bounded jittered backoff for safe reads, stop on invalid credentials and quarantine persistent record-specific failures. Begin with serial worker requests and measured pacing; add bounded concurrency only when needed.

Store ETag/Last-Modified with endpoint, media type, API version and credential identity. An authenticated conditional request returning 304 does not consume the primary rate budget, but still has network/secondary-limit costs. A 304 without the cached body is a cache miss requiring recovery. Keep the existing OAuth reader's behavior stable while adding a typed archive response carrying status, headers, body and request ID. [Conditional requests](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api).

T04 status (2026-10-26): the worker-only reader is `backend/app/integrations/archive_github.py`, with central settings in `backend/app/core/config.py` and tests in `backend/tests/test_archive_github.py`. It implements the typed conditional response, verified metadata/README/blob reads, same-origin redirects, bounded streaming and retry-at handling. It is not wired into a worker or API yet, and it does not change the OAuth provider. See [T04 evidence](T04_EVIDENCE.md).

## 6. Archive data and indexing schema

| Entity | Key and material fields |
| --- | --- |
| `archive_repositories` | GitHub numeric ID PK; node ID; current canonical owner/name; URLs; description/topics/languages; stars/forks; license signal; created/updated/pushed timestamps; visibility/archive/fork flags; eligibility/status; first_seen/last_seen/last_checked; active revision |
| `archive_documents` | Repository ID + content revision; source endpoint/ref/blob SHA; raw/normalized SHA256; private file reference; fetch validators; bytes/truncation; normalizer/chunker/model revision; pending/published/superseded status |
| `archive_chunks` | Deterministic chunk ID; repository/revision; ordinal/section; normalized text/hash; token count; vector-write status; model/index generation |
| `archive_runs` | Run ID; bootstrap/weekly/rebuild; fixed cutoff and upper bound; due-period key; state; counters; last heartbeat; starts/ends; last complete coverage boundary; sanitized failure summary |
| `archive_tasks` | Unique run/repository/stage or run/partition; state; attempts; retry-at; lease owner/expiry/fencing token; completed checkpoint |
| `archive_partitions` | Query/policy version; interval/range bounds; page/ID checkpoints; reported count; incomplete flag; last sweep and child partitions |

Do not key identity solely by `owner/name`: renames/transfers change it. Preserve favourites' current API contract; a later ID-based favourite migration needs its own tests. A rename updates aliases and canonical metadata without creating a second repository.

Use a Milvus collection per embedding schema generation, e.g. `repo_chunks_e5small_v1`, with a serving alias after validation. Proposed fields: deterministic VARCHAR chunk PK, INT64 `repo_id`, content revision, model version, language, license, pushed timestamp, chunk ordinal/section, bounded snippet, and FLOAT_VECTOR of dimension 384. Store large raw text in the catalogue/files, not a dynamic JSON blob duplicated in every vector. Disable arbitrary dynamic fields; create scalar indexes only for actual filters. Use typed parameterized filter construction, never splice raw user expressions into Milvus filters.

Keep only the active model generation loaded for ordinary serving. A model/dimension/normalization change creates a new collection; never mix incompatible embeddings. Collection alias and application model manifest must advance together through a validated activation record. [Milvus aliases](https://milvus.io/docs/manage-aliases.md).

### Crash-safe publication

There is no cross-database transaction between SQLite and Milvus. Treat this explicitly:

1. Persist a pending content revision and deterministic chunks in a short SQL transaction; store raw files atomically before referencing them.
2. Upsert every chunk using stable IDs. Retry incomplete batches safely; confirm all expected vectors are readable with the chosen consistency policy.
3. Switch the repository's active revision in SQL only after its complete vector set is ready. Search postfilters candidate chunks against current SQL active revisions and eligibility; pending/old revisions never become results.
4. Delete superseded chunks asynchronously after activation. Reconcile orphan vectors/tasks after restart. If a new revision fails, the previous safe published revision remains available subject to current eligibility/visibility checks.

This permits a brief availability gap or extra candidate filtering, not a claim of globally atomic vector/SQL writes. Bound overfetch retries when old chunks occupy the top-K; return fewer qualified results rather than bypassing the active-revision check. Use ordinary idempotent upserts, not an append-only vector row for every weekly observation. [Milvus upserts](https://milvus.io/docs/v2.6.x/upsert-entities.md).

## 7. Content preparation and embeddings

Recommended initial model: **`intfloat/multilingual-e5-small`**, an MIT-licensed 384-dimensional multilingual retrieval model with a 512-token input limit. Use the same pinned model revision, tokenizer, normalization and prefixes for ingestion/query paths: `passage:` for repository content, `query:` for the user's full idea. Persist those choices in an embedding manifest. [Publisher model card](https://huggingface.co/intfloat/multilingual-e5-small).

Use Sentence Transformers on CPU initially. The full idea goes to the embedding model; the existing six-keyword adapter is only for GitHub retrieval. Model download is a one-time setup action with an immutable revision and safe weights; do not enable remote model code. Embed in bounded batches and cache a chunk's embedding by text hash + model revision. Pin the SDK/server/model-library compatibility set during Phase A rather than copying an old package-install example. [Sentence Transformers usage](https://www.sbert.net/docs/sentence_transformer/usage/usage.html).

T02 status (2026-10-25): the adapter is `backend/app/services/embeddings.py`, the manifest is `backend/app/services/embedding_model.json` (revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, `model.safetensors` and `tokenizer.json` hashes, 384 dimensions, 512 tokens), and the optional CPU lock is `backend/requirements.embeddings.lock.txt`. Unit tests use a fake encoder; the real CPU smoke/benchmark and limits are in [T02 evidence](T02_EVIDENCE.md). The adapter is not wired into an API route yet.

Normalize Markdown deterministically with `markdown-it-py`: retain headings, purpose, capabilities and concise technical identifiers; remove HTML execution, badges, navigation boilerplate and remote image content. Produce one metadata overview plus selected README sections. Use approximately 350-400 tokenizer tokens per chunk with up to 50 tokens of overlap, leaving room for the prefix/title. Enforce the actual 512-token budget after adding all prefixes, not by character count. Keep at most 8 chunks per repository initially and record clipping/truncation. These are benchmark starting values, not proven relevance optima.

Proposed input bounds: 256 KiB decoded README source, a separate bounded metadata response budget, at most 8 chunks, finite parse time and bounded embedding batches. Stream and count decoded bytes before accumulation; the existing provider's post-download body check alone is insufficient for worker inputs. Reject binary/malformed payloads safely; a README failure may leave a metadata-only repository instead of deleting its catalogue record.

Change detection uses normalized semantic content hash, not `pushed_at` alone. A star-count update changes metadata but causes no embedding work. An unchanged README response still needs re-embedding if description/topics/chunker/model inputs changed. Missing or removed content must remove obsolete chunks rather than leave stale README vectors indefinitely.

### Size model

Raw vector bytes = vectors × 384 × 4. The estimates below assume four chunks per repository; the eight-chunk cap can double these counts. They exclude scalar data, graph-build peaks, scratch space, growing segments, model memory and Windows display usage.

| Repositories | Vectors at 4 each | Raw vectors | Approximate CAGRA index-only estimate |
| --- | --- | --- | --- |
| 10,000 | 40,000 | 58.6 MiB | 105.5 MiB |
| 25,000 | 100,000 | 146.5 MiB | 263.7 MiB |
| 50,000 | 200,000 | 293.0 MiB | 527.3 MiB |
| 100,000 at **8** each | 800,000 | 1,171.9 MiB | 2,109.4 MiB |

The last column uses Milvus's rough 1.8× CAGRA estimate, not a memory guarantee. [GPU index memory guidance](https://milvus.io/docs/gpu_index.md). Benchmark loaded segments and update/rebuild peaks; raw-vector arithmetic alone cannot establish that a corpus fits. Target substantial VRAM headroom and halt expansion on measured pressure rather than an OOM crash. SSD storage must also accommodate raw content, model weights, container images, index overhead and at least one recoverable backup.

## 8. Weekly refresh and retention

Proposed schedule: **Sunday 03:30 Asia/Kolkata**, equivalent to Saturday 22:00 UTC. Use Windows Task Scheduler to start a WSL worker command, with missed-run catch-up and no concurrent instance. Persist the weekly due-period key in SQL so scheduled/manual/restarted attempts resume the same run. On a Linux deployment, replace the host task with one persistent systemd timer; do not activate both schedulers.

No task is created by this plan. A sleeping/offline laptop cannot guarantee a weekly completion SLA. On the next permitted launch, catch up from durable progress, expose the actual last successful refresh and pause cleanly if the network, quota, memory or disk budget is unavailable.

| Stage | Required behavior |
| --- | --- |
| Preflight | Check migrations, model/index manifest, Docker/Milvus availability, free disk, rate budget and stale leases. Never reset databases to recover. |
| Acquire run | Atomic lease + monotonically increasing fence; heartbeat. A task with an expired lease cannot publish after a newer worker takes ownership. |
| Discover | Resume prioritized recent-activity partitions and rolling-year sweep; persist every page/partition checkpoint and coverage gaps. |
| Reconcile known IDs | Revalidate all selected repositories, including those without a new push; detect rename, archive, license/visibility changes, missing README and deletions. |
| Fetch | Conditional metadata/README reads; source validation and bounded durable retries. Authentication failure stops the run; record-specific errors are quarantined. |
| Normalize/embed | Reuse unchanged content vectors; process only new/changed semantic content. Batch by actual token counts; release CPU capacity for foreground requests. |
| Publish | Per-repository staged publication; deterministic IDs prevent duplicates on restart. Refresh scalar metadata without re-embedding prose. |
| Retire | Immediately suppress confirmed inaccessible/private/archived/ineligible records from search, then delete their active vectors. Do not infer deletion from absence in a search page or from 429/5xx. |
| Complete | Record success/partial/failure, committed counts, pending work and quota consumption. Advance coverage watermarks only for successfully finished intervals; expose partial runs honestly. |

An ambiguous 404 is not proof that a repository was deleted: it may be private, transferred, inaccessible or an invalid credential. Suppress the unsafe result, retain a content-free tombstone for diagnosis, and retry the canonical identity check under a valid public-read credential. A missing README is a separate condition. Do not permanently purge the entire catalogue because a credential expired.

Proposed retention: active latest content while eligible; superseded raw revisions for 30 days for operational rollback, not annual historical analytics; 90 days of content-free run/coverage summaries. Confirmed private/inaccessible status overrides superseded-content retention: purge live raw/normalized content and published snippets promptly, retaining only content-free suppression records. Encrypted offline backups may contain previously public content until a proposed maximum seven-day expiry; they are never searchable or directly served. This backup-retention exception requires approval and is not immediate erasure from every copy. Expired-window records are hidden immediately by the dynamic cutoff and physically swept weekly. Favourite snapshots remain user data under the existing contract and do not keep archive vectors alive.

For strict public-only serving, freshly validate archived candidate repository visibility before emitting results, with only a bounded short-lived validation cache (proposed 15 minutes). A matching repository returned as public by the live GitHub branch can supply the fresh metadata for that ID in the same request; do not make a redundant validation call for it. Never show a known private/inaccessible record. If validation cannot complete, suppress that item and mark archive retrieval degraded; if no verified result is available and a source is incomplete/unavailable, return an explicit 503. Weekly checks alone cannot promise immediate detection of a public-to-private transition. This also means an archive is not automatically a GitHub-independent availability guarantee. Accepting longer-lived public snapshots would be a separate product decision.

## 9. Serving APIs and compatibility

| Route/control | Contract |
| --- | --- |
| Existing `POST /projects/search` | Compatibility endpoint for existing callers: retain keyword-only page/per_page/sort/order and `total`. The updated app no longer uses it as its normal search path. |
| New `POST /v1/projects/search` | The app's single authenticated hybrid-search endpoint: original idea 2-1000 characters, `page_size=1..50`, opaque cursor and typed optional language/license filters. Both sources run by default; no public source/mode selector. Relevance ranking is the initial contract. |
| New `GET /v1/archive/status` | Authenticated sanitized counts, rolling cutoff, selection/coverage policy, last attempt/success, index/model version and actual CPU/GPU profile. No credentials, raw errors or user queries. |
| Existing details/favourites | Existing paths/card fields remain compatible; details continue to fetch live public data. |
| Worker CLI | Bootstrap, refresh/resume, status, reconcile, purge and rebuild. Local operator control; no ordinary user may trigger or configure ingestion. Proposed commands are unavailable until implemented. |

Avoid adding a remotely reachable job-admin API initially: the app has no admin-role model. If a later deployment needs one, introduce separate operator authorization and audit first; an ordinary signed-in GitHub user is not an administrator.

Example **proposed** request:

```json
{"idea":"an offline-first app for sharing community tools","page_size":20,"cursor":null,"filters":{"language":"TypeScript"}}
```

Example response shape (existing card fields omitted here for brevity):

```json
{
  "items": [{"id":123,"full_name":"owner/project","sources":["archive","github"],"matched_section":"Features"}],
  "next_cursor": null,
  "has_more": false,
  "total": null,
  "degraded": false,
  "sources": {"archive":{"status":"ok","coverage":"curated","incomplete":false},"github":{"status":"ok","incomplete":false}},
  "archive_as_of": "2026-10-24T00:00:00Z",
  "ranking_version": "rrf-v1"
}
```

Hybrid `total` is nullable: neither ANN top-K nor merging it with GitHub supplies an exact global match count. Do not add source totals together. Return provenance and freshness; each result may have `sources=["github"]`, `["archive"]` or both. A rank score is not a percentage probability that a project implements the idea. Explanations initially consist of matched sections/snippets from sources, not generated claims. Distinguish the archive's curated coverage from a retrieval error: a successful search over a declared pilot is not automatically a failed source.

### Per-source eligibility

| Rule | Local archive candidates | Live GitHub candidates |
| --- | --- | --- |
| Public and unarchived | Required, with numeric-ID-bound public validation | Required; validate the current response defensively |
| Pushed within 365 days | Required dynamically, even before the next weekly purge | Not required by default; older relevant live results remain eligible |
| Exists in local catalogue / active model revision | Required | Not required |
| Pilot selection and archive-content license policy | Governs indexed content | Must not silently exclude live hits; report known license data truthfully |
| Explicit user language/license filters | Enforced with typed metadata filters and final checks | Translated into supported GitHub qualifiers and checked consistently |

Do not postfilter the entire combined list by archive membership or cutoff. If a repository is ineligible for the archive but is a valid live result, it can still appear with GitHub provenance; no stale archive snippet may be attached. A duplicate's current public GitHub metadata takes precedence over an older archive card, while valid archive evidence retains its own revision/freshness.

### Request pipeline and ranking

1. Validate the one user submission and session; retain the original text for local query embedding. Never reduce semantic input to the six GitHub keywords.
2. Start independent bounded branches: derive a valid GitHub keyword query and call its Search API; concurrently embed the full idea and retrieve Milvus chunks. Keep CPU inference/blocking clients off the async event loop.
3. Validate each branch's data and apply its own scope rules. Collapse archive chunks into repository candidates before source fusion. Use current live metadata or bounded validation for archived-only IDs.
4. Combine the union by GitHub numeric repository ID. Keep source ranks/provenance; do not concatenate source lists or intersect them.
5. Fuse repository ranks, make deterministic tie decisions, create one bounded candidate snapshot and return the first page. Later pages paginate this fused snapshot and recheck serving eligibility.

Initial candidate budgets: up to 100 GitHub repositories (one 100-item search page) and up to 100 archive repositories. Start with 200 Milvus chunks and increase bounded overfetch when needed, never beyond the chosen GPU index's supported top-K (proposed ceiling 1,000). A chunk-rich repository must not occupy multiple result slots. The pilot therefore returns at most 200 distinct source-union candidates, often fewer; `has_more` only describes this snapshot, not all GitHub matches. Candidate limits are tuning settings, not guarantees of full recall.

Use application-level Reciprocal Rank Fusion (RRF), initially equal source weights and k=60: for each repository sum `1 / (60 + source_rank)` over the sources containing it. Break ties deterministically with source ranks then repository ID. Benchmark this baseline; never add raw vector similarities to GitHub rank numbers. Stars are a filter/tiebreaker at most, not a substitute for purpose similarity. Return fewer qualified results when bounded overfetch is exhausted. Milvus's own `hybrid_search`/RRF API combines Milvus search paths; it does not call or merge the external GitHub API. Our discovery service performs that cross-system fusion. [RRF principle and Milvus scope](https://milvus.io/docs/rrf-ranker.md).

Cursor pagination uses a bounded, account-scoped, approximately five-minute in-memory snapshot of the **fused** repository IDs, source membership/ranks and source-health metadata. Store no raw query/transcript or query embedding in this cache. Bind the opaque signed cursor to account, filter/query digest, ranking/model generation and expiry; revalidate source-specific eligibility/visibility on later pages. The new client submits the idea again for binding. Do not independently fetch GitHub page N and Milvus page N and merge them: that produces duplicate/unstable pages. Preserve degraded provenance on later pages; a retry or pull-to-refresh starts a fresh two-source search rather than silently splicing a recovered source into the old snapshot. Return an explicit expired-cursor error and restart, not a silently changed ranking. Recheck this cache design before multiple API hosts.

### Source failures and incomplete search

Both sources must be invoked for an ordinary healthy first-page search. Give them separate budgets within one total deadline; proposed overall server deadline is 8 seconds, below the mobile client's 15 seconds. Do not wait indefinitely for a slow Milvus/GitHub branch. Query rate limiting, CPU inference contention and archived-candidate public validation must all fit that budget; the final performance target remains benchmark-driven.

Propagate remaining deadlines to HTTP/Milvus calls and admission queues; bound inference tokens/batches and concurrency. A timeout or disconnected client must not create an unbounded backlog of abandoned threads or repeated work. Reject excess load explicitly instead of queueing indefinitely; cancellation behavior for the chosen blocking clients needs implementation tests.

| Source outcomes | API/UI behavior |
| --- | --- |
| Both searches succeed | Return the combined ranked list. A repository need not occur in both. |
| Both succeed with no qualified matches | Return a normal empty success; only here may the UI claim no matches from the completed hybrid search. |
| One branch fails, times out, is uninitialized, or is incomplete; verified hits remain | Return useful hits with `degraded=true`, per-source status/reason and an explicit partial-search notice. No claim that both sources completed. |
| Any branch failed/incomplete and no verified hits remain | Return an explicit `503 SEARCH_INCOMPLETE`, preserving sanitized source status; do not show a definitive no-matches screen. |
| Both unavailable | Return explicit 503; the client may show clearly aged cached data through its existing offline/error policy. |

`incomplete_results=true` from GitHub is not equivalent to complete success: retain its partial hits with incomplete provenance. A successful empty archive is distinct from a missing index, unavailable model, failed vector call or rate-limited visibility check. If valid idea text cannot produce a safe GitHub keyword query (for example, the current ASCII adapter yields nothing), do not issue a broad qualifiers-only search or reject otherwise valid semantic input; mark that branch `query_not_supported` and use the same partial-result rules. Do not silently truncate/reinterpret legacy endpoint inputs.

If keyword Search alone is rate limited, archive hits may remain valid when their public-status checks succeed; those checks can use a different REST rate bucket but still need credential/budget handling. If all GitHub validation is unavailable and archived-only IDs cannot be safely validated, suppress them. Source failure is an exception state, not an alternative search mode. Keep liveness `/health` lightweight; add separate readiness/detail status for archive availability.

Move orchestration into a service instead of expanding the current nested endpoint. Preserve the app's existing session guard; decrypt user GitHub credentials only for branches that need user-scoped live requests. Check per-user budget for visibility validation as well as keyword search. Query/model work must run off the async event loop with bounded execution. Set a search-specific body limit without loosening auth-route limits, and keep the server timeout below the mobile client's current 15-second deadline.

The released mobile search action uses the versioned hybrid adapter by default, with one result list, updated results/pagination types, partial-search/freshness presentation and cache-schema versioning. Do not add a user-facing keyword/semantic toggle. Preserve existing account isolation, editable voice transcript and consented foreground-only offline retry. Server refresh scheduling is independent of Home pull-to-refresh. Do not persist ideas as an ingestion queue or automatically archive every user search. The original idea stays local to our backend/model; only the derived GitHub query is sent to GitHub.

## 10. Libraries, configuration and operational controls

| Component | Selection | Reason/constraint |
| --- | --- | --- |
| HTTP/API/config | Existing FastAPI, Pydantic settings, HTTPX | Reuse stack; typed bounded inputs, timeouts and injectable transports. |
| Vector client | `pymilvus` | Match and pin the server-supported SDK release after the GPU probe; use a GPU server image, not Lite, for GPU tests. |
| Embeddings | `sentence-transformers` with its compatible PyTorch/Transformers/safetensors dependencies | Local model, no paid embedding API; CPU first; lock dependencies and model revision separately. |
| Markdown parsing | `markdown-it-py` | Deterministic text/section extraction; no remote asset execution. |
| Catalogue/queue | Python `sqlite3`, migrations, WAL, short transactions | Separate archive DB; one writer on one Linux host. No ORM/new DB server for the pilot. |
| Files/hashes/logs | Standard-library pathlib, hashlib, gzip/json, logging | Bounded content-addressed archive and structured run evidence. |
| Schedule | Windows Task Scheduler calling WSL; later Linux systemd timer | Catch-up and durability without an API-embedded scheduler. |
| Local services | Docker Compose v2, pinned Milvus GPU image and release-matched dependencies | Engine/GPU passthrough and disk/RAM compatibility are prerequisites. |
| Verification | Existing pytest/HTTPX transport mocks; real local CPU/GPU Milvus probes | Unit tests do not substitute for GPU integration or relevance evaluation. |

Do not add FAISS as a second serving database, a paid cloud service, a general LLM, vector orchestration framework, message broker, multi-agent product or Kubernetes to satisfy the initial archive requirement. A later reranker or larger embedding model must earn its additional memory and latency in evaluation.

Central settings to add in `backend/app/core/config.py`: archive DB/content paths; corpus policy/cap/window; worker credential reference; response/token/chunk/batch limits; rate reserve and retry ceilings; run/lease/heartbeat budgets; Milvus URI/auth/profile/collection; embedding model/revision/device; cursor signing and bounded cache policy; visibility-validation TTL and retention. Store secrets only in ignored environment files; safe placeholders in `.env.example`. Worker credentials and data services never reach mobile configuration.

Proposed file boundaries (create only when a slice needs them):

```text
backend/app/core/archive_store.py       # catalogue, migrations, tasks and leases
backend/app/integrations/archive_github.py
backend/app/integrations/milvus.py
backend/app/services/embeddings.py
backend/app/services/archive_index.py   # normalize/chunk/publish
backend/app/services/discovery.py       # retrieval/fusion/visibility
backend/app/workers/archive.py          # CLI/run orchestration
backend/app/api/archive.py              # v1 search/status router
backend/tests/test_archive_*.py
backend/tests/test_hybrid_search.py
infra/milvus/                           # pinned local Compose and documented GPU profile
```

Log counts, durations, bytes, retries, rate headroom, last successful coverage, pending tasks and model/index identifiers. Never log authorization headers, raw user ideas, transcripts or README payloads. Provide operator status/retry tools and a concise failed/partial run summary. No scheduled automation or notification service is installed by this plan.

Use SQLite's backup API plus a matching raw-content manifest; do not copy only a live database file while ignoring its WAL. Backups are encrypted/access-controlled, expire within the approved period and are never served in place. Keep a current content-free suppression ledger separately from historical backups. Restore into quarantine: reapply that ledger, expire restored validation caches, purge suppressed/expired content and revalidate repository IDs/visibility before enabling serving. If the current ledger is unavailable, remain quarantined until all restored records have been reconciled. Test private transition -> purge -> old backup restore specifically. If immediate erasure from offline backups is required, change the backup design before ingestion rather than claiming this seven-day policy meets it.

Treat vectors as rebuildable but test an actual restore of metadata/content/model manifest. Keep at least one backup outside the live volume; same-laptop backup does not protect against laptop loss. Bound disk use and stop acquisition before exhausting C:/E:/WSL storage.

## 11. Phased delivery and verification gates

All phases are **planned**. Each feature gets its own `codex/` branch/PR, meaningful failing tests before behavioral changes, focused checks, exact-commit review and the existing quality gates. Do not include the unrelated mobile/security draft in an archive feature PR.

| Phase | Feature slices and dependencies | Exit criteria |
| --- | --- | --- |
| A: feasibility | Hardware/runtime and pinned compatibility matrix, including a WAL-patched SQLite library; 1k synthetic + real licensed sample; CPU versus GPU benchmark | Docker/WSL GPU visible; build/load/search/upsert/delete/filter work; actual GPU use measured; total RAM/VRAM/rebuild peak and CPU embedding throughput recorded. Approve corpus cap/license/retention. If GPU fails, report exact limitation and use Milvus CPU only with agreement. |
| B: minimal hybrid vertical slice | Archive migrations; fetch/validators; normalize/embed; deterministic Milvus publish; internal dual-source orchestrator | One public licensed repo is retrieved locally and combined with GitHub test-transport results in one list. GitHub-only, archive-only and common IDs are covered; replay creates no duplicates. No crawler/public API rollout yet. |
| C: bounded year-window backfill | Durable discovery partitions; checkpointed queue; 1k then 10k corpus | No silent 1,000-result truncation; boundary/duplicate/incomplete tests pass; coverage/cap reported; pause/resume within budgets works. No claim of full GitHub coverage. |
| D: weekly lifecycle | Conditional refresh; lease/fencing; retirement; host-task instructions; status and backup/restore | Unchanged content makes zero embedding calls; changed/removed content updates correctly; overlap/missed schedule/reboot tests pass; successful local restore; no stale watermark advance on partial failures. |
| E: hybrid serving API | Single versioned dual-source contract; concurrent retrieval; source-specific eligibility/visibility; RRF, fused cursor and error handling | Both healthy branches invoked; old live GitHub projects survive archive-only cutoff; existing legacy endpoint stays green; no duplicates/raw idea persistence; partial/empty/error states and deadline/cursor isolation tests pass. |
| F: mobile rollout | Default hybrid adapter, one combined list and source/cache types | No public mode selector; stable fused pagination and truthful partial/empty states; unchanged offline consent/background rules; real HTTP cross-layer hybrid search test. |
| G: quality/expansion | Frozen labeled idea set; threshold tuning; capacity and recovery exercises | At least 50 diverse labeled queries; compare keyword/semantic/hybrid nDCG@10/Recall@20; record failure cases and no-match behavior. Expand only after relevant quality and memory gates pass. |

Detailed implementation slices should stay approximately 1-5 files each: B separates catalogue/migration, acquisition, and publish; C separates partitioning and durable resume; D separates refresh correctness, retirement and scheduling/restore. Do not implement an entire phase as one large PR.

Required test scenarios: year cutoff and timezone boundaries; older-but-recently-pushed repos; missing language/license/README; Unicode/tokenizer limits; blob-versus-commit identity and branch races; credential/429/503/redirect errors; pagination movement/incomplete partitions; duplicate IDs/renames and old-name reuse by a different repository ID; lease loss and process kill before/after vector write; shrinking chunk sets; private/archive/deletion suppression; model revision mismatch; stale SQL/vector candidates; query injection; malformed signed cursors; no source available; unsafe content; disk/full-GPU failure; cache expiry; private-transition purge followed by an old-backup restore with missing/stale suppression state.

Hybrid-specific acceptance fixtures must additionally prove: both healthy branches run concurrently within bounded deadlines; GitHub-only and archive-only hits survive; common IDs become one card with both provenances; a live hit older than 365 days is retained; stale archive evidence is not attached to an ineligible/live-only hit; multi-chunk repositories collapse before fusion; result order is deterministic; no duplicates across fused cursor pages; source recovery does not alter an existing snapshot; unsupported keyword compilation preserves semantic retrieval without a broad query; one failed/incomplete branch plus zero hits does not become a no-matches success; existing sort/order/page behavior remains unchanged on the compatibility endpoint.

Suggested performance acceptance hypotheses, to confirm in Phase A: semantic retrieval branch p95 below 2 seconds warm; hybrid endpoint p95 below 5 seconds including bounded validation; API responsiveness retained during ingestion. Measure at stated corpus size/concurrency on this laptop. Do not convert these targets into claims or assume weekly jobs finish while the laptop is asleep.

## 12. Decisions still needed and blocking dependencies

Confirmed: hybrid search as the app's normal flow, combining GitHub and local Milvus; local 4 GB GPU preference; pushed-within-365-days archive eligibility; weekly refresh. Preserve broader live GitHub scope by default. Recommendations awaiting approval: bounded pilot/corpus selection, licensed-content policy, 30-day superseded retention, short-lived live visibility verification, schedule time and strict freshness behavior during GitHub outages. The source-specific scope assumption is explicit and may be changed only by a later shared-filter requirement.

Still unverified: running Docker engine; container CUDA/driver pair; runtime/SDK/model pins; patched SQLite in WSL; free disk after image/model download; measured query/build/embedding performance; GPU index compatibility for scalar filters/upserts in the chosen release. Current docs serve both v3.0.x and v2.6.x; do not combine version-specific defaults or claim `gpu.maxMemSize` limits total process VRAM.

Independent architecture review found three issues and their corrections were rechecked: expected repository-ID validation under old-name reuse, file-blob versus commit identity in README acquisition, and private-content suppression across backup/restore. The reviewer found no material remaining defect in those corrections. This document review does not validate the unimplemented runtime.

The hybrid-first revision was separately rechecked for mandatory dual-source retrieval, archive-versus-live scope, app-level RRF/deduplication, bounded concurrency, fused pagination and partial/empty failure semantics. No substantive finding remained; a misleading semantic-endpoint latency label was corrected to describe the internal retrieval branch.

Search/security prerequisites were delivered separately in PRs #10 and #12; see [current delivery evidence](REQUEST.md#delivered-prerequisites-2026-10-24). The mobile discovery foundation remains local/unmerged. T00 must verify the actual main baseline and refresh both dependency audits before implementing. The earlier proposed braces/sprintf exceptions were not used; the existing node-forge exception still requires review before 2026-11-01. These prerequisite merges do not complete any archive/hybrid task.

The architecture analysis did not ingest GitHub data, download model weights, start/install services, create a scheduled task, benchmark Milvus or rerun application tests. Publication of this handbook is tracked separately in the root PROJECT_TRACKER.md and its GitHub PR; it does not implement these capabilities.
