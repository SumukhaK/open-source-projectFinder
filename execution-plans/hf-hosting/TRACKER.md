# Hugging Face hosting tracker

Status (2026-11-23): feasibility agreed, persistence decision approved; H1 in
review. Nothing is deployed to Hugging Face or Zilliz until the owner gives the
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
| HD1 | How the Space keeps logins, favourites and the catalogue across restarts | **Approved 2026-11-23** | Sync SQLite snapshots to a private HF dataset: restore at startup, upload periodically. A restart may lose the last few minutes of changes. Paid persistent storage and "reset on restart" were declined. |
| HD2 | Vector store | Proposed | Zilliz Cloud free tier (managed Milvus). Needs owner go-ahead before an account or cluster is created. |
| HD3 | Forwarded client IPs | Proposed | Keep `--no-proxy-headers`; per-IP limits count HF's proxy. Acceptable for a single-owner app. |

## Phases

| Feature | Scope | Verification | Status |
| --- | --- | --- | --- |
| H1 | `deploy/hf-space/` Dockerfile and Space card; port 7860, uid 1000, build-time pinned model download, `HF_HUB_OFFLINE=1` | Image builds; container serves `GET /health` on 7860 as uid 1000 | In review: see limitation below |
| H2 | Private-dataset SQLite sync (HD1): restore before startup, consistent snapshot upload on a timer and at shutdown | Unit tests with a fake hub client; restore-after-restart check | Not started |
| H3 | Milvus adapter accepts Zilliz (AUTOINDEX and HNSW) with token auth; one-time copy of the 980-repository archive | Unit tests for the index contract; live search against Zilliz | Not started |
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

## Open questions

- Zilliz free-tier collection and index specifics: confirm before H3.
