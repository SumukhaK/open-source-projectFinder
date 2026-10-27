# T06 raw content and provenance evidence - 2026-10-27

Status: **Awaiting review** in [PR #22](https://github.com/SumukhaK/open-source-projectFinder/pull/22), not accepted or merged. This implements only [T06](tasks/T06-raw-content.md). The PR's current head and required CI are authoritative in GitHub.

## Scope and prerequisites

- Branch: `codex/hybrid-t06-raw-content`, created from `origin/main` at `c821ce1e93c144482c6aaf934e7db6d88306464c`.
- [T03](tasks/T03-catalogue.md) / PR #18 merged as `776bf654551fd0466386c6bc008df6ae606b0dcb`, [T04](tasks/T04-archive-http.md) / PR #19 merged as `d2354e9`, and [T05](tasks/T05-chunking.md) / PR #20 merged as `adfd0f8` are ancestors of the base. No dependent task is started.
- Three production/configuration files: new `backend/app/services/archive_content.py`, additive migration 2 in `backend/app/core/archive_store.py`, and the `ARCHIVE_CONTENT_MAX_BYTES` storage bound in `backend/app/core/config.py`. Tests are `backend/tests/test_archive_content.py` and the updated `backend/tests/test_archive_store.py`.
- No new dependency, lock change, API route, worker, scheduler, Milvus call, model download, CI workflow, coverage/security gate or exception change. No mobile or unrelated search work.

## Contract and decisions

`ArchiveContentStore` owns one private content root (`ARCHIVE_CONTENT_PATH`) and stores files under `<kind>/<sha256[:2]>/<sha256>` where `kind` is `raw` or `normalized`. Raw content is the exact decoded README UTF-8 byte sequence. Normalized content is canonical JSON (`format: "prepared-v1"`) containing repository ID, semantic hash, normalizer/chunker/model versions, README status, omission flags and every prepared chunk's ID, ordinal, section, text, token count and text hash. Chunk text is stored once; T06 does not duplicate it into `archive_chunks`.

`persist_revision(db, content, *, metadata, prepared, readme, raw=None, source_ref=None, source_truncated=False, expected_repo_id=None)` requires an already-open write transaction and a schema at version 2. It validates identity and provenance, writes content-addressed files first, then inserts the repository (if absent) and a `pending` document revision. A later task (T08) owns publication and chunk/vector rows.

| Rule | Implemented behavior |
| --- | --- |
| Revision identity | `PreparedRepository.semantic_hash` is the document revision; raw/normalized SHA-256 values are separate columns |
| Provenance | Source endpoint and ETag/Last-Modified from the README response, or metadata response when no README exists; `blob_sha` is the Git file blob SHA; `source_ref` is an optional resolved 40-character commit SHA and is never conflated with the blob SHA |
| Size and truncation | Raw README bytes, decoded byte count and the caller's explicit `source_truncated` flag; defensive storage bound is 1 MiB per file |
| Preparation versions | Normalizer, chunker and model revision are stored with the revision and repeated in normalized JSON |
| Absent README | No raw file/blob; normalized metadata-only payload records `readme_status` and omissions; metadata response supplies validators |
| Identity guards | Metadata, prepared content, README and optional expected repository ID must agree; SHAs must be lowercase 40-hex; raw bytes must equal the README text and the Git blob SHA |
| Path confinement | Reject traversal, absolute paths, backslashes, symlinked components/targets and non-regular targets; POSIX roots/shards are 0700 and files 0600; existing shared permissions are refused, not repaired |
| Atomic write | Exclusive temporary file in the target shard, flush + fsync, then `os.replace`; POSIX also fsyncs the parent directory; temporary files are removed on failure |
| Database failure | Newly created files are removed when the document insert fails, so no active catalogue row points at missing content |
| Replay | Identical content identity is idempotent, creates no duplicate row/file and repairs a missing file; a changed content identity raises `RevisionConflict` without overwriting |
| Observation refresh | A replay with identical content identity updates `source_endpoint`, `source_ref`, `etag` and `last_modified` in the same transaction and returns `replayed=True`, so a T19 refresh does not fail on unchanged content |
| Repository metadata | `archive_repositories.full_name` and `metadata_json` are first-seen values and are not refreshed by a replay; T10/T19 own refreshing repository metadata |
| Existing content | A file whose size or digest does not match is rejected and left untouched |
| Recovery read | Reads verify the expected SHA-256 and refuse tampered or shared-permission files; no GitHub, model or Milvus call is needed |

Migration 2 only appends nullable/defaulted columns to `archive_documents`: `normalized_path`, `source_endpoint`, `source_ref`, `blob_sha`, `etag`, `last_modified`, `raw_bytes` and `truncated`. Existing v1 rows remain valid with NULL provenance and `truncated = 0`. `source_ref` and `blob_sha` are each constrained to 40 lowercase hex characters; `raw_bytes >= 0`; `truncated IN (0, 1)`. Migration 1 is unchanged.

The normalized file is sufficient to rebuild prepared passages without Milvus; raw README bytes are retained separately for audit/rebuild. Files are content-addressed and deterministic from verified source plus preparation versions, but T06 does not claim that a live archive can be reconstructed without GitHub. No user query, embedding, idea, transcript or token is stored.

## TDD and checks

Platform/date: Windows, Python 3.11.9, 2026-10-27. Commands ran from the isolated worktree with the existing `E:/OpenSourceProjectFinder/backend/.venv/Scripts/python.exe`; `ruff` and `bandit` are its adjacent tools. No system packages or existing environments were modified.

| Stage | Command / actual result |
| --- | --- |
| Baseline | `python -B -m pytest backend/tests scripts/tests -q -p no:cacheprovider` -> exit 0, 390 passed / 40 existing POSIX skips |
| RED, stub surface | `python -B -m pytest backend/tests/test_archive_content.py -q -p no:cacheprovider` -> exit 1, **1 failed / 2 skipped / 27 errors**: missing migration 2 and `NotImplementedError` for every behavior; not an import-only failure |
| RED, file store only | Same file, `-k 'content_reads or content_paths or symlinked or interrupted_replace or disk_full or existing_content_with or recovery_read_rejects'` -> exit 1, **1 failed / 11 passed / 2 skipped / 16 deselected**: recovery read still needed persistence |
| GREEN focused | `python -B -m pytest backend/tests/test_archive_content.py backend/tests/test_archive_store.py -q -p no:cacheprovider` -> exit 0, **45 passed / 6 skipped** (36 test functions, parameterized cases) |
| Full regression | `python -B -m pytest backend/tests scripts/tests -q -p no:cacheprovider --cov=backend/app --cov-branch --cov-report=term-missing --cov-report=json:reports/t06/backend-coverage.json` -> exit 0, **435 passed / 47 skipped**, one inherited Starlette/httpx warning, 27.39s |
| Coverage gate | `python scripts/quality.py coverage reports/t06/backend-coverage.json` -> exit 0, **93.5% combined / 91.0% branches**, unchanged 90/80 gate. `archive_index.py` and `embeddings.py` remain 100%; the new module reports 87% on Windows because six POSIX-only cases are skipped |
| Linux CI | [run 40449100006](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40449100006) on head `d8029c8464960d1ee4f1a2431b672584277a2f3c`: **482 passed, no skips**, **97.2% combined / 95.4% branches**, new module 91% with CPython 3.11.17 / SQLite 3.53.1; Backend quality, Dependency audit, Mobile quality/E2E, Secret scan, GitGuardian and Quality gate all passed |
| Lint / format | `ruff check backend scripts`; `ruff format --check backend scripts` -> exit 0 |
| Security | `bandit -r backend/app -q -f json -o reports/t06/bandit.json` -> exit 0, 0 findings, 2,760 LOC, no scanner errors |
| Whitespace | `git diff --check` -> clean |
| Schema CHECK probe | Direct SQLite inserts confirmed migration 2 rejects uppercase/short `source_ref`/`blob_sha` values and `truncated = 2`, and accepts a valid 40-hex pair with `truncated = 1` |

The focused tests cover path traversal and absolute paths, symlinked directories/targets/roots (POSIX), shared POSIX permissions, duplicate replay with file repair, conflicting provenance, interrupted replace and fsync disk-full failures, wrong-size/wrong-digest existing files, database-trigger failure rollback, absent optional content, mismatched repository IDs, strict SHA validation, oversize content/metadata, open-transaction requirement, unmigrated schema refusal, tamper detection and portable v1 -> v2 migration. `test_archive_store.py` adds a POSIX v1 -> v2 upgrade through `ArchiveStore` and updates the existing version assertions to 2.

The first Linux run exposed two test-fixture defects, not production failures: fixture files were created with default POSIX modes, so the privacy check fired before the intended size/digest assertion, and the `sqlite3.Row` column probe iterated values instead of column names. Commit `d8029c8` sets the fixtures to 0600 and reads the name column; the rerun above passes. No production behavior or gate changed.

## Review follow-up: identity vs observation

Review of PR #22 found that `persist_revision` compared fetch observation (`source_endpoint`, `source_ref`, `etag`, `last_modified`) as part of content identity, so an unchanged repository would be rejected on its next refresh. The comparison is now split:

- Content identity: `raw_path`, `raw_sha256`, `normalized_path`, `normalized_sha256`, `blob_sha`, `raw_bytes`, `truncated`, `model_revision`, `normalizer_version`, `chunker_version`. Any difference still raises `RevisionConflict`.
- Observation provenance: the four fetch fields are updated on a matching replay in the caller's transaction. Missing content files are still repaired and `replayed=True` is returned.
- A caller that supplies `raw` bytes without a `ReadmeDocument` now raises `RevisionIdentityError`; no file or row is written.
- `archive_repositories.full_name`/`metadata_json` remain first-seen values (`ON CONFLICT(repo_id) DO NOTHING`); T10/T19 own refreshing them.

| Stage | Command / actual result |
| --- | --- |
| Review RED | `pytest backend/tests/test_archive_content.py -q -k 'replay_updates or different_blob or different_normalized or raw_content_without_readme'` -> exit 1, **5 failed / 2 passed / 51 deselected**: four observation refreshes raised `RevisionConflict`, raw-without-README did not raise |
| Review GREEN focused | `pytest backend/tests/test_archive_content.py -q` -> exit 0, **52 passed / 6 skipped** |
| Review full regression | `pytest backend/tests scripts/tests -q --cov=backend/app --cov-branch --cov-report=term-missing --cov-report=json:reports/t06/backend-coverage.json` -> exit 0, **442 passed / 47 skipped**, one inherited Starlette/httpx warning, 22.04s |
| Review coverage gate | `python scripts/quality.py coverage reports/t06/backend-coverage.json` -> exit 0, **93.6% combined / 91.2% branches**, unchanged gate; new module 88% locally (POSIX-only cases skipped) |
| Review lint / format | `ruff check backend scripts`; `ruff format --check backend scripts` -> exit 0 |
| Review security | `bandit -r backend/app -f json -o reports/t06/bandit.json` -> exit 0, 0 findings, 2,769 LOC |
| Review whitespace | `git diff --check` -> clean |

The new tests cover README ETag/Last-Modified refresh, metadata ETag refresh when no README exists, `source_ref` refresh, endpoint refresh after a rename, rejection of a different `blob_sha` under the same revision, rejection of different normalized content under the same revision, and raw bytes without a README.

## Migration compatibility and rollback

- New installations start at v2. Existing v1 catalogues upgrade transactionally through the same ordered migration path; the POSIX test inserts v1 repository/document rows and verifies they survive with NULL new fields and `truncated = 0`.
- Migration 2 is forward-only and additive. Reverting only the T06 code after an upgrade would make T03's version check refuse the newer schema. A full rollback therefore means stopping archive consumers, restoring a pre-upgrade consistent snapshot (or keeping the T06 code) and reverting the T06 files. Do not edit migration 1, delete the database to bypass a migration error, or move a live WAL database.
- Content files are immutable and content-addressed. Remove unreferenced files only after confirming no document references them; T06 creates `pending` rows only, so no active published revision exists. T08 owns publication, obsolete-content cleanup and vector reconciliation.

## Limits

- Local verification is Windows only. WSL remains unavailable (`Wsl/Service/CreateInstance/CreateVm/HCS/ERROR_NO_SYSTEM_RESOURCES`), so the POSIX permission/symlink tests and the `ArchiveStore` v1 -> v2 upgrade test are skipped locally; they pass in the pinned Linux CI runtime above (Python 3.11.17 / SQLite 3.53.1).
- Windows SQLite 3.45.1 is below the catalogue WAL gate; no local WAL/catalogue run is claimed. The WAL gate is unchanged.
- Tests use synthetic README/metadata fixtures. No live GitHub fetch, real repository archive, embedding inference, Milvus write, worker integration, scheduler or API change is claimed.
- The normalized JSON retains prepared chunk text; T06 does not create `archive_chunks` rows, publish revisions, delete superseded content or cache user queries. Those remain T08/T09/T13/T20 work.
- Storage capacity, corpus/licence/retention policy and live ingestion approvals remain open. Trusted review and merge remain outside this implementation session.
