---
title: RepoRadar API
sdk: docker
app_port: 7860
pinned: false
---

# RepoRadar API on a Hugging Face Space

Status: **H1, not deployed.** The plan and its decisions live in the
[hosting tracker](../../execution-plans/hf-hosting/TRACKER.md). This folder holds
what a free CPU basic Docker Space needs to serve the RepoRadar API. The YAML
block above is the Space card. Hugging Face reads it only when this file is the
Space repository's `README.md`.

## Space repository layout

A Space builds from its own git repository. Its root holds:

```
Dockerfile        <- deploy/hf-space/Dockerfile
.dockerignore     <- deploy/hf-space/Dockerfile.dockerignore
README.md         <- deploy/hf-space/README.md
backend/          <- backend/ (without .env, .venv or data/)
scripts/embeddings_smoke.py
```

The same layout lets you build locally from this repository's root:
`docker build -f deploy/hf-space/Dockerfile -t reporadar-api .`. BuildKit
applies `Dockerfile.dockerignore`, so a local `backend/.env` or `backend/data/`
never enters the image.

## What the image does

- Python 3.11, runs as uid 1000 (as Spaces require), serves on port 7860.
- Installs `backend/requirements.lock.txt` and the CPU embeddings lock.
- Downloads the pinned `intfloat/multilingual-e5-small` snapshot **at build
  time** and checks its hashes, then serves with `HF_HUB_OFFLINE=1`.
- Keeps forwarded headers off. Hugging Face's proxy terminates HTTPS, so
  per-IP limits count the proxy, not each client. That's fine for a single-owner
  app. Revisit it before opening the app to others.
- Uses the `cpu` Milvus profile (HNSW). Milvus itself isn't in the image:
  `MILVUS_URI` must point to a managed service (H3).
- SQLite lives in `/home/user/app/data`, which **is wiped on every restart**
  until H2 adds the private-dataset sync.

## Settings (Space secrets and variables)

Set these in the Space's **Settings > Variables and secrets**, never in the
repository. The names match `backend/.env.example`. Use secrets for
`GITHUB_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY`, `HYBRID_CURSOR_SIGNING_KEY`,
`API_GITHUB_TOKEN`, `MILVUS_TOKEN`, `DEEPGRAM_API_KEY` and
`WORKERS_AI_API_TOKEN`. Use variables for `GITHUB_CLIENT_ID`,
`GITHUB_CALLBACK_URL` (`https://<owner>-<space>.hf.space/auth/github/callback`),
`ALLOWED_REDIRECTS`, `MILVUS_URI`, `MILVUS_COLLECTION`, `LLM_ACTIVE_PROFILE`
(`workers_ai` or empty) and `WORKERS_AI_ACCOUNT_ID`.

Free CPU basic Spaces sleep after 48 hours without traffic. The first request
after that waits for the container to start and load the model.
