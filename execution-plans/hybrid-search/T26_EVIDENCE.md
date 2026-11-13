# T26 Evidence — verify the cross-layer hybrid path over real HTTP

Base: `origin/main` `36a6953` (after the T23 merge `9667ea5`, [PR #105](https://github.com/SumukhaK/open-source-projectFinder/pull/105)). Work started on `5bd2046` (T22, [PR #102](https://github.com/SumukhaK/open-source-projectFinder/pull/102)) and was rebased onto the current main before the gate below.
Branch: `codex/hybrid-t26-hybrid-integration`.
Prerequisites verified merged into main: T09 `722e62a`, T15 `9aa3b94`, T22 `5bd2046`, T25 `b8daa40`.

## What the lane proves

One opt-in pytest module drives the real path end to end: the real archive worker
(`ingest_one` + `IngestRuntime`) writes the real catalogue/content store and the
real CPU Milvus collection; the real FastAPI app runs under uvicorn on a free
`127.0.0.1` port; the test talks to it over real HTTP with `httpx` and a real
PKCE fake-OAuth session. Only upstream GitHub is a deterministic
`httpx.MockTransport`, and embeddings are deterministic fixtures that expose the
real manifest (384 dimensions, unit-norm vectors). No model is downloaded, no
live GitHub call is made and no GPU is used.

Assertions (one test each):

1. Mobile adapter contract: response envelope, item keys/types, source health and `ranking_version` (`rrf-v1`), `total: null`.
2. Union and provenance: keyword ∪ vector candidates, no duplicate repository IDs, `["github","archive"]` / `["github"]` / `["archive"]` labels, archive cards carry `matched_section` + `snippet`.
3. Known fused ranking: exact order, `rank` 1..7 and exact RRF scores.
4. Fused-cursor paging: 2/2/2/1 pages, no repeated cursor, no repeated or missing repository, clean last page (`next_cursor: null`, `has_more: false`).
5. Incomplete source is never labelled empty: an incomplete keyword source with verified archive hits is `200` + `degraded`; the same incomplete source with no archive hits is `503 SEARCH_INCOMPLETE` (retryable), never an empty success.
6. Private repository suppression: repo D is public in server v1, private in a new server v2 (D is suppressed and absent), and still absent after a third server restart against the same catalogue and collection, while D's vectors remain in Milvus.

## Harness layout

| File | Role |
| --- | --- |
| `backend/tests/hybrid_e2e_fixtures.py` | Repos A–G, deterministic 384-dim unit vectors, metadata/README transport, expected order/provenance |
| `backend/tests/hybrid_e2e_support.py` | Settings, unique collection name, temp-root/pilot guards, server process, PKCE login |
| `backend/tests/hybrid_e2e_server.py` | Test-only uvicorn entry point wiring the fixture transport/embeddings into the real app |
| `backend/tests/test_hybrid_integration.py` | The opt-in lane (skipped unless `RUN_HYBRID_INTEGRATION=1`) |
| `backend/tests/test_hybrid_cleanup.py` | Default-suite guards: only `reporadar_t26_<32 hex>` may be dropped, never the pilot or a non-temp path |
| `backend/tests/test_hybrid_runtime_seam.py` | Default-suite proof that injected reader/embeddings are used by the build |

The lane uses `pytest`'s `tmp_path_factory` for the auth database, archive
catalogue, content store and server logs. Teardown drops only the collection it
created (`reporadar_t26_<uuid hex>`), and the drop now runs even when ingestion or
the server fails to start.

## Fixture scenario and expected result

| Repo | ID | Sources | Keyword rank | Archive rank |
| --- | --- | --- | --- | --- |
| B | 910002 | github + archive | 1 | 2 |
| A | 910001 | github + archive | 4 | 1 |
| D | 910004 | github + archive | 3 | 4 |
| G | 910007 | github only (never ingested) | 2 | — |
| C | 910003 | archive only | — | 3 |
| E | 910005 | archive only | — | 5 |
| F | 910006 | archive only | — | 6 |

Fused order (RRF k=60): **B, A, D, G, C, E, F**, with exact scores
`1/61+1/62`, `1/64+1/61`, `1/63+1/64`, `1/62`, `1/63`, `1/65`, `1/66`.

## Production defect found by the lane

The first lane run reached the real stack and returned HTTP 500 (`KeyError`,
redacted by the production crash boundary) on the **second** identical search.
Root cause: `EligibilityService` cached only validation fields
(`id, full_name, private, archived, pushed_at, visibility`), and a cache hit was
returned as the evidence metadata used to build result cards. On a repeat search
inside the 15-minute visibility TTL, archive-only cards lost `name`, `owner`,
`description`, `stargazers_count`, `language` and `license`, so
`discovery.summary()` raised `KeyError: 'name'`.

Fix (one production file, `backend/app/services/eligibility.py`): the bounded
cache now keeps the public card subset as well as the validation fields, returns
copies so a caller cannot mutate the shared nested dicts, and still stores no
provider response body or README text. Regression test:
`test_cached_validation_keeps_the_public_card_fields` in
`backend/tests/test_eligibility.py`.

The lane also needed a small, inert-by-default test seam in
`backend/app/services/hybrid_runtime.py`: `HybridRuntime` accepts optional
`archive_reader` and `embeddings`, defaulting to the existing construction.

## RED evidence

Each regression was injected temporarily, run against the real stack, then
reverted. Command (same each time, in WSL from the repo root):

```sh
RUN_HYBRID_INTEGRATION=1 python -m pytest backend/tests/test_hybrid_integration.py -q -k <test>
```

| Injected regression | Observed failure | Exit |
| --- | --- | --- |
| Route renamed `/v1/projects/search` → `/v1/projects/hybrid-search` | `assert 404 == 200` in `test_mobile_adapter_contract` | 1 |
| Fusion always returns `sources = ("github",)` | `assert ('github',) == ('github', 'archive')` in `test_union_and_provenance` | 1 |
| Pager re-emits the same cursor (`next_offset = offset`) | `assert cursor not in seen_cursors` in `test_fused_cursor_paging_has_no_repeats_or_gaps` | 1 |
| Private leak (`live_eligible` ignores private/visibility; both suppression branches disabled) | `assert 'D' not in ['B', 'A', 'D', ...]` in `test_private_repository_is_suppressed_and_stays_gone` | 1 |
| `_overall_status` returns `"empty"` when no candidates | `assert 200 == 503` in `test_incomplete_source_is_never_labelled_empty` | 1 |
| Eligibility cache drops card fields (main's behaviour) | unit: `KeyError: 'name'`; lane: HTTP 500 on the second search | 1 |

## GREEN evidence

- Platform: WSL2 Ubuntu on Windows 11, Python 3.11.17, SQLite 3.53.1, pymilvus 2.6.17, Milvus 2.6 CPU profile (image `2.6-20261023-b8d2ca4240`).
- Date: 2026-11-12 (lane runs), 2026-11-13 (final gate and docs).
- Lane: `RUN_HYBRID_INTEGRATION=1 python -m pytest backend/tests/test_hybrid_integration.py -q` → **6 passed**; exit 0. Run once before the rebase (16.02 s, cold) and once on the final rebased tree (10.46 s, warm Milvus and page cache).
- Measured run (`/usr/bin/time -v`, same command, rebased tree): wall **11.10 s**, maximum resident set size **149,500 KiB** for the pytest process (the uvicorn child is a separate process and is not included).
- Collection cleanup after the final run: `collections: []`, no `reporadar_t26_*` left behind.
- Full gate, from the repo root on WSL:

  | Check | Result | Exit |
  | --- | --- | --- |
  | `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:reports/backend-coverage.json` | 1,346 passed, 9 skipped (6 are this lane) in 63.48 s | 0 |
  | `python scripts/quality.py coverage reports/backend-coverage.json` | 93.1% combined, 89.7% branches | 0 |
  | `ruff check backend scripts` | clean | 0 |
  | `ruff format --check backend scripts` | 91 files already formatted | 0 |
  | `bandit -r backend/app` | no findings (only its comment-parsing warnings) | 0 |
  | `git diff --check` (run on Windows; WSL cannot resolve the worktree's `.git` path) | clean | 0 |

- Default-suite isolation: without `RUN_HYBRID_INTEGRATION=1` the six lane tests skip; the two new guard modules run as normal unit tests.

## CI decision

The lane is documented as a **local opt-in lane**, not a hosted job. A
`workflow_dispatch` job added on this PR branch could not be triggered before
merge, and the real CPU Milvus stack plus ingestion is heavy for a free hosted
runner. No gate was lowered and no security exception was added.

Exact commands (WSL, from the repo root):

```sh
# 1. Start the CPU stack (never use -v or prune).
cd infra/milvus
docker compose --env-file /path/to/private/milvus.env --profile cpu up -d --wait

# 2. Export the worker token without echoing it.
export MILVUS_TOKEN="root:$(sed -n 's/^MILVUS_PASSWORD=//p' /path/to/private/milvus.env)"

# 3. Run the lane.
export RUN_HYBRID_INTEGRATION=1
python -m pytest backend/tests/test_hybrid_integration.py -q

# 4. Stop the stack (keeps volumes).
docker compose --env-file /path/to/private/milvus.env down
```

## Limits

- Deterministic fixture embeddings are used instead of the pinned E5 model. The
  manifest (name, revision, 384 dimensions, max tokens) is the real one, and
  vectors are unit-norm, but this does **not** claim real model quality,
  embedding parity or GPU behaviour.
- No live GitHub request is made; OAuth, keyword search and archive reads are a
  `MockTransport`. The real OAuth/session code, rate limiter and HTTP stack do run.
- The Windows default suite was not re-run for this change. The known Windows
  baseline is four environment-only failures on main; Linux CI and this WSL gate
  are authoritative.
- The host needed roughly 7 GB free RAM for the Milvus CPU container. Under
  memory pressure the container exited once and was restarted; the lane itself
  is short (about 17 s).
- Peak RSS above covers only the pytest process; the uvicorn server runs in a
  child process.
- `hybrid_e2e_server.py` prints the real traceback to its own temp log because
  the production crash boundary redacts it. It is test-only and never imported
  by the application.

## Operator steps and rollback

No migration or stored-data change. The eligibility fix is in-memory only, so
rollback is a revert of the merge commit; the lane and its guard tests are
opt-in/default-suite tests with no production effect. The lane creates and drops
its own uniquely named collection and never touches the pilot catalogue,
restore-quarantine folders, `repo_chunks_e5small_v1`, the Drive backup
repository or `backend/.env`.
