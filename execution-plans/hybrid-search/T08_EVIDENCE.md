# T08 publication and reconciliation evidence — 2026-10-28

Status: **Awaiting review** in [PR #30](https://github.com/SumukhaK/open-source-projectFinder/pull/30), not accepted or merged. This implements only [T08](tasks/T08-publication.md); no T09 work, ingestion, API wiring or live data is included. The PR's current head and required CI are authoritative in GitHub.

## Scope and prerequisites

- Branch `codex/hybrid-t08-publication`, created from fetched `origin/main` at `243ef766ab7031776424716391271123353a0d52` (the T07 docs sync).
- Merged prerequisites: [T06](tasks/T06-raw-content.md) / PR #22 as `c73c457b937fd6038f33dbbeb59c54a43c97374c`, and [T07](tasks/T07-milvus-adapter.md) / PR #28 as `21e6db3`. Both are ancestors of the base.
- Production files: new worker-only `backend/app/services/archive_publication.py` and the `ARCHIVE_RECONCILE_DOCUMENTS = 100` bound in `backend/app/core/config.py`. Tests are `backend/tests/test_archive_publication.py` and the opt-in `backend/tests/test_archive_publication_integration.py`.
- No schema migration, dependency, lock, workflow, API route or security-exception change. The existing T03 `archive_documents`/`archive_chunks` columns carry the publication state; T06's `persist_revision` remains the only writer of pending documents and files.

## Contract and decisions

SQLite and Milvus share no transaction, so a revision passes through three explicitly ordered phases:

1. **Stage (short write transaction).** `publish_revision` requires the T06 pending document to already exist and validates the prepared repository and vector set first: repo ID, lowercase revision, model revision, 1..`ARCHIVE_MAX_CHUNKS` contiguous ordinals, unique SHA-256 chunk IDs, non-empty text, matching text hashes, positive token counts, and vectors whose chunk ID, repo, revision, model revision, ordinal and section all match. It inserts the chunk rows as `vector_state='pending'`, then reads the full ordered set back and refuses anything extra or changed.
2. **Write and verify (no SQL transaction held).** Vectors are upserted in adapter-sized batches (at most `milvus_batch_size`, 64) with the deterministic chunk IDs, then the complete expected set is strongly read back through `ready()` before anything is published. A mid-batch or unreadable-set failure raises and leaves the revision pending; the previous active revision is untouched.
3. **Activate (one short write transaction).** The document must still exist and not be `superseded`, the catalogue chunk set must still equal the prepared set, rows are marked `written`, the previous published document becomes `superseded`, the new document becomes `published`, and `archive_repositories.active_revision` moves. The activation is one transaction, so a crash before it leaves the old revision active and a crash after it leaves only the new revision visible.

`publish_revision` deliberately does not delete the previous revision's vectors. `reconcile` retires superseded documents that are not active: it deletes their vectors first (batch-wise), then removes the document row in a transaction that re-checks the document is still superseded and not active. A crash between vector deletion and row removal therefore leaves rows whose vectors are already gone, which a retry deletes idempotently; a crash before deletion leaves both, which retry handles. Pending documents are only counted and reported, never activated or removed, because their publisher replays them with the same prepared revision and IDs.

`load_active_chunks` joins `active_revision` to a `published` document and `written` chunks and returns a tuple only when the set is non-empty, within `ARCHIVE_MAX_CHUNKS`, and ordinal-contiguous. Pending, partial, gapped or over-limit sets return empty, so a caller can never expose a partially published revision.

Retries are idempotent: staging uses `ON CONFLICT DO NOTHING` plus an exact read-back, vector IDs are deterministic, and replaying the active revision returns it as `previous` without duplicating rows. Adapter failures (`MilvusUnavailable`) and SQL failures propagate unchanged rather than being hidden.

## Test-first record

Commands use the existing Windows Python 3.11.9 environment with PyMilvus 2.6.17, from `backend/` with the repository's `pytest.ini`. Logs are private/ignored under `reports/t08/`.

| Stage | Actual result |
| --- | --- |
| Initial focused suite against the stub | Exit 1: **44 failed**, every failure `NotImplementedError` from the three public functions; no production behavior existed yet |
| First implementation | Exit 0: 44 passed; then expanded contract, replay, race and reconcile-skip tests to **54 passed, 1 skipped** (the opt-in real-server test) |
| Focused coverage | 99% module coverage (189 statements, 102 branches); the only uncovered line is the impossible "repository row disappeared between staging and activation" guard |
| Final Windows full suite + coverage | Exit 0: **605 passed, 49 skipped** (48 inherited POSIX-only skips + 1 opt-in real-server test); **95.1% combined / 93.5% branches**; `archive_publication.py` 99%. Unchanged policy passes |
| Baseline `origin/main` at `243ef76` | 550 passed, 48 skipped, 1 pre-existing Windows order-sensitive failure (`test_discovery.py::test_favourite_limit_missing_repository_and_provider_failure`, 500 vs 503); that test passes alone and in the T08 full suite. T08 adds 54 passing tests |
| Ruff check / format / Bandit | Exit 0; all Python files formatted; 0 Bandit findings, 0 `nosec` |

Full commands: `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=json:reports/backend-coverage.json`; `python scripts/quality.py coverage reports/backend-coverage.json`; `python -m ruff check backend scripts`; `python -m ruff format --check backend scripts`; `python -m bandit -r backend/app`.

Failure injection covers: kill before any files/rows, missing pending document, mid-vector-batch failure, vectors written but not readable, activation failure after vectors, activation after a racing delete/supersede/chunk change, replay of the active revision, superseded revision replay, shrinking chunk sets, bounded reconcile, partial vector deletion, and reconcile racing a document back to pending or active. `load_active_chunks` is tested against pending, partial, gapped and over-limit sets.

## Real Milvus result

A disposable CPU-profile stack (`docker compose -p reporadar-t08 --profile cpu`) ran the opt-in test with synthetic vectors only:

`RUN_MILVUS_INTEGRATION=1 MILVUS_PROFILE=cpu python -m pytest backend/tests/test_archive_publication_integration.py -q` exited **0: 1 passed in 17.49 seconds**.

- Published a 3-chunk revision, verified every vector readable and the active chunk set complete.
- Published a shrinking 1-chunk revision and confirmed the previous revision's 3 vectors were still present until reconcile.
- `reconcile` deleted the 3 superseded vectors, then the rows, returned `ReconcileResult(1, 3, 0)`, and a second call returned zero.
- The test-created collection was dropped and the stack removed. Docker Desktop, started only for this proof, was shut down afterwards. The ignored `infra/milvus/.env` holds random local passwords and remains untracked.
- This is a CPU correctness proof with synthetic vectors, not a GPU, capacity, recall or latency claim.

## Rollback, operator steps and limits

There is no migration to undo. Rollback is a code revert after stopping publication consumers; existing collections and volumes are preserved. Rows left `pending` or `superseded` by an interrupted run remain harmless because `load_active_chunks` only serves a published, active, complete `written` set. A worker restart should call `reconcile` and then replay any pending revision with the same prepared revision and deterministic IDs; `reconcile` is bounded to 100 documents per call and should be repeated until it reports no superseded work.

Limits: POSIX-only archive store/content tests are skipped on Windows, so Linux CI remains authoritative. The real proof is CPU-only and synthetic. No real GitHub data, ingestion, API serving, backup/restore, suppression, capacity or relevance work is included; T09 and later tasks own those. No gate, workflow, dependency pin or security exception changed.
