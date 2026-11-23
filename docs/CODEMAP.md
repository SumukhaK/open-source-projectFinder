# Codebase map

A short orientation for people and coding agents. Use it to find where things
live before reading code; it does not replace reading the code you change.
**Keep it current:** a PR that adds, moves or removes a module, route, command
or decision updates this file in the same PR.

## What the product is

RepoRadar helps a signed-in GitHub user find open-source projects for an idea.
An Expo mobile app talks to a FastAPI backend. Search is **keyword-first**
(ranking `keyword-first-v1`, D8 option A): live GitHub keyword results, with a
private local archive (Milvus vectors over README chunks) fused below them.
Voice input/output and a grounded LLM summary sit on top. Everything runs on
the owner's laptop; nothing is deployed elsewhere (Phase 7 not planned).

## Request flow

```
mobile (src/features/discovery) ──► POST /v1/projects/search  (app/api/archive.py)
                                     └─ hybrid_runtime.py ─► hybrid_search.py
                                          ├─ keyword_candidates.py / keyword_query.py ─► integrations/github.py
                                          ├─ archive branch: embeddings.py ─► integrations/milvus.py ─► archive_store.py
                                          ├─ eligibility.py (live visibility/licence re-checks, single-flight)
                                          └─ rank_fusion.py ─► fused_cursor.py (signed later pages)
                                   POST /v1/projects/search/summary (api/summary.py ─► integrations/llm.py)
                                   POST /v1/voice/transcribe (api/voice.py ─► integrations/deepgram.py)
                                   GET  /v1/voice/speech/{id} (api/speech.py)
```

Archive writes never happen in the API; they belong to the workers below.

## Backend (`backend/app`)

| Area | Files | Notes |
| --- | --- | --- |
| App, auth | `main.py` | App factory, `/health`, GitHub OAuth (`/auth/*`), router wiring |
| Legacy discovery | `discovery.py` | `/projects/search`, project details, favourites |
| Hybrid API | `api/archive.py`, `api/summary.py`, `api/voice.py`, `api/speech.py` | Versioned `/v1/*` routes, all authenticated |
| Config | `core/config.py` | **Only** place settings are read (pydantic `Settings`; secrets are `SecretStr`) |
| Stores | `core/store.py` (app DB), `core/archive_store.py` (private archive catalogue, migrations), `core/sqlite_runtime.py` | SQLite (WAL) |
| Integrations | `integrations/github.py` (OAuth and the user's own GitHub reads), `archive_github.py` (bounded public-metadata reader: the API's hybrid checks use `API_GITHUB_TOKEN`, workers use `ARCHIVE_GITHUB_TOKEN`), `milvus.py`, `llm.py`, `deepgram.py` | Bounded clients; no provider error text leaks |
| Search services | `hybrid_runtime.py`, `hybrid_search.py`, `rank_fusion.py`, `fused_cursor.py`, `keyword_*.py`, `live_scope.py`, `eligibility.py`, `embeddings.py` | Deadline-bounded (D8: hybrid p95 ≤ 7 s at c=1) |
| Archive services | `archive_partitions.py` (search partitioning), `archive_runs.py` (runs, leases, checkpoints), `archive_index.py` (chunking), `archive_content.py` (content-addressed files), `archive_publication.py` (crash-safe publish/reconcile), `archive_retirement.py` (suppression, purge, retention), `archive_backup.py`, `archive_restore.py` | |
| Workers / CLI | `workers/archive.py` (CLI entry: `python -m app.workers.archive <ingest|backfill|refresh|retire|backup|restore|init-collection>`), `backfill.py`, `refresh.py`, `retire.py`, `state_sync.py` (HD1: `restore`/`run` the hosted API's SQLite via a private HF dataset), `schedule.py` (`run daily` = retire at 22:00 IST; `run weekly` = refresh then backup, Sunday 03:30 IST) | Serial, resumable, one fenced writer |
| Prompts | `prompts/*.txt` | Versioned LLM prompts |

Tests: `backend/tests/test_<module>.py`, offline fakes for HTTP, Milvus and the
model. Scripts with their own tests: `scripts/` (`quality.py` CI gates,
`relevance_eval.py` T27, `capacity_bench.py` T28, `merge_reviewed.py`).

## Mobile (`mobile/src`)

Bulletproof-React layout (see `mobile/AGENTS.md`): `app/` composition,
`features/auth`, `features/discovery` (search screen, cards, summary, voice
hooks, API clients, cache), `features/branding`, shared `components/`,
`hooks/`, `lib/` (theme), `config/` (branding tokens, public config only).

## Commands

- Backend: `ruff check backend scripts`, `ruff format --check backend scripts`,
  `python -m pytest backend/tests scripts/tests`, `bandit -r backend/app`.
- Mobile (in `mobile/`): `npm run typecheck`, `npm run lint`, `npm test`.
- Hugging Face Space image (H1; H2 adds `start.sh` state sync; not deployed): `docker build -f
  deploy/hf-space/Dockerfile -t reporadar-api .` from the repository root; see
  `deploy/hf-space/README.md`.
- CI: `.github/workflows/quality.yml` (also coverage gate, dependency audit,
  gitleaks); `reviewed-merge.yml`.
- Known local noise: `test_embeddings` smoke tests need the embeddings extras;
  `test_archive_restore.py` fails on Windows SQLite/WAL. Linux CI is the truth.

## Decisions that shape the code

- **D1** archive cap 1,000 kept repositories (`backfill --cap`, `refresh --cap`;
  any new admission needs owner approval). `backfill --examine` (≤ 5,000) bounds
  candidates examined. 10k (T28b) deferred.
- **D2** licence allowlist (`ARCHIVE_BACKFILL_LICENSES`); only ~20% of
  candidates qualify.
- **D4** privacy/removal order (retire sweep); **D5/D6** restic backups to the
  owner's external sync folder; **D3** retention.
- **HD1** (hosting on a free Hugging Face Space, not deployed): SQLite persists by
  syncing snapshots to a private HF dataset (`workers/state_sync.py`); Milvus moves to a managed service.
  Plan in `execution-plans/hf-hosting/TRACKER.md`.
- **D8** keyword-first ranking; archive may outrank keyword results only via a
  new ranking version that passes the option B gate (T27).

## Where to look for more

- Running and operating it: `docs/OPERATIONS.md` (setup, jobs, backup/restore,
  limits, rollout).
- Plans and history: `execution-plans/hybrid-search/TRACKER.md`, task files in
  `tasks/`, evidence in `T*_EVIDENCE.md`; voice in `execution-plans/voice-assistant/`; hosting in `execution-plans/hf-hosting/`.
- Product: `README.md`, `REQUIREMENTS.md`, `SCOPE.md`, `PROJECT_TRACKER.md`.

## Never

- Read, print, log or commit secrets (`.env` values, tokens, restic password).
- Run `docker compose down -v` or prune volumes.
- Work in the owner's dirty main checkout; use a worktree (see `AGENTS.md`).
