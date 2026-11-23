# Hugging Face hosting tracker

Status (2026-11-23): feasibility agreed, persistence decision approved; H1
merged ([PR #153](https://github.com/SumukhaK/open-source-projectFinder/pull/153),
`4e17553`); H2 merged ([PR #154](https://github.com/SumukhaK/open-source-projectFinder/pull/154), `0c6e686`); H3 in review. Nothing is deployed to Hugging Face or Zilliz until the owner gives the
go-ahead for H4.

## Original request (verbatim)

> i have made this account on hugging face that lets me use CPU basic 2 vCPU 16 gb and zero gpu free. is it possible to use them to host the backend of this project on it so that my laptop wont take the load ?

## Requirements

- Serve the API (auth, keyword and hybrid search, summaries, voice) from the
  owner's free Hugging Face Space so the laptop no longer runs the API, Docker
  Desktop or Milvus day to day.
- Stay on free tiers. AGENTS.md: don't enable paid services, upgrade plans or
  raise spending limits.
- Keep secrets in Space secrets and the ignored local `.env`, never in git.
- Keep D1 (1,000-repository cap), D2, D4 and D8 unchanged.

## Feasibility (from the repository, 2026-11-23)

| Piece | Today (laptop) | On Hugging Face |
| --- | --- | --- |
| FastAPI API + e5-small CPU embeddings | ~1.3 GB RSS | Fits a Docker Space (2 vCPU, 16 GB) |
| Milvus standalone + etcd + MinIO, `GPU_CAGRA` | ~0.7-0.85 GB, Docker Desktop | Doesn't fit: one container, no GPU, ephemeral disk. Use Zilliz Cloud free tier |
| SQLite auth DB + archive catalogue + content files | `backend/data/` | Ephemeral disk; persistent storage is paid. Sync to a private HF dataset (HD1) |
| Daily retire, weekly refresh + restic backup | Windows Task Scheduler | Spaces have no scheduler. Stays on the laptop, pointed at Zilliz |
| Ollama qwen2.5 7B summaries | laptop GPU | Too slow on 2 vCPU; use the existing `workers_ai` profile or leave off |
| ZeroGPU | n/a | Gradio-only, on-demand GPU functions; not usable for a long-running API, not needed |

## Decisions

| ID | Decision | Status | Value |
| --- | --- | --- | --- |
| HD1 | How the Space keeps logins, favourites and the catalogue across restarts | **Approved 2026-11-23** | Sync SQLite snapshots to a private HF dataset: restore at startup, upload periodically. A restart may lose up to `STATE_SYNC_INTERVAL_SECONDS` (default 300) of changes. A start whose restore download fails exits instead of serving an empty DB. Paid persistent storage and "reset on restart" were declined. |
| HD2 | Vector store | Proposed (code in H3) | Zilliz Cloud free cluster: 1 per organisation, 5 GB, vector index `AUTOINDEX` only, IP supported ([Zilliz limits](https://docs.zilliz.com/docs/limits)). The owner creates the account and cluster; nothing is created for them. |
| HD3 | Forwarded client IPs | Proposed | Keep `--no-proxy-headers`; per-IP limits count HF's proxy. Acceptable for a single-owner app. |

## Phases

| Feature | Scope | Verification | Status |
| --- | --- | --- | --- |
| H1 | `deploy/hf-space/` Dockerfile and Space card; port 7860, uid 1000, build-time pinned model download, `HF_HUB_OFFLINE=1` | Image builds; container serves `GET /health` on 7860 as uid 1000 | Merged 2026-11-23 (`4e17553`); full image unbuilt, see below |
| H2 | Private-dataset SQLite sync (HD1): `app/workers/state_sync.py` `restore` before the API starts (never overwrites, fails the start on a failed download), `run` uploads a consistent auth DB copy every interval when changed; catalogue download-only; `deploy/hf-space/start.sh` | Unit tests with a fake hub client; container start paths | Merged 2026-11-23 (`0c6e686`); real HF round trip unrun, see below |
| H3 | `MILVUS_PROFILE=zilliz`: `AUTOINDEX` with no build or search params, same IP metric, schema, index-state and load checks; skips only the pinned 2.6 server-version check. The Space image uses it. Filling the cluster (re-embedding the 980 repositories into it) is an H4 operator step | Unit tests (`test_milvus.py`, 4 new); live `init-collection` and search against Zilliz in H4 | In review |
| H4 | Deploy: create the Space repo contents, set secrets, update the GitHub OAuth callback and the mobile API URL | Signed-in search from the phone through the Space | Waits for owner go-ahead |
| H5 | Retarget laptop jobs (retire, refresh, backup) to Zilliz and the dataset catalogue; stop Docker Milvus | One scheduled weekly run against the hosted stack | Not started |

### H1 verification (2026-11-23)

- This cloud sandbox can't reach `download.pytorch.org` or `huggingface.co`, so
  the full image (CPU torch, model download) was **not** built here.
- A copy of the Dockerfile without the embeddings stack built cleanly. Its
  container served `{"status":"ok"}` on `GET /health` at port 7860, as
  `uid=1000(user)`, with SQLite created under `data/`.
- The full build is first proven by the Space's own build in H4, or on any
  machine that can reach both hosts.

### H2 verification (2026-11-23)

- `backend/tests/test_state_sync.py`: 13 tests with a fake hub client (restore
  when missing, never overwrite, skip absent, fail closed, no-op without a
  repo; snapshot consistency, upload only on change, never the catalogue;
  `run` survives upload errors and never logs the token; `main` exit codes).
  Full backend suite: 1426 passed, 9 skipped, and the 2 documented
  `test_embeddings` smoke failures (no embeddings extras locally).
- Container check, embeddings-free variant: with `STATE_SYNC_REPO` empty, both
  sync steps log `state_sync_disabled` and `/health` answers. With it set and
  no hub client importable, the restore exits 1 and the API never starts.
- Not run: a real upload or download against Hugging Face (the sandbox can't
  reach it). That's the first H4 check.

## Open questions

- Zilliz: whether `describe_collection` on the free cluster reports
  `consistency_level` 0 (Strong) and an index `state` of `Finished` exactly as
  Milvus 2.6 does. The adapter fails closed if not. The first live
  `init-collection` in H4 answers this.
