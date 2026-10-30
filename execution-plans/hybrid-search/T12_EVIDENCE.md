# T12 rank fusion evidence

Date: 2026-10-30. Status: Awaiting review. Branch:
`codex/hybrid-t12-rank-fusion`. Base:
`f2d86d14a64979391e3210dd5b9f12db9a78943c` (fetched `origin/main`).
Prerequisites T10 (`22295fa`) and T11 (`0655834`) are merged into `main`.
D1-D8 are approved; T12 needs no policy gate. No acceptance or merge is claimed.

## Contract

`backend/app/services/rank_fusion.py` is the one pure fusion helper. The task
file proposed `backend/app/services/discovery.py`, but main has the legacy
router at `backend/app/discovery.py` and the service layer at
`backend/app/services/`; a small module there keeps the legacy endpoint
untouched and matches the existing service boundary.

`fuse_candidates(github, archive=(), *, archive_status="ok")` accepts the real
T11 `KeywordCandidates` and T10 `ArchiveEvidence` values. It performs no HTTP,
Milvus, SQLite or file access.

- Archive chunks are grouped by numeric repository ID and collapsed to the
  best chunk: highest Milvus relevance score, then lowest ordinal, then chunk
  ID. Archive source rank is the repository's best-chunk order (score
  descending, then repository ID), capped at 100 repositories.
- GitHub candidates are deduplicated by numeric ID (lowest source rank wins),
  ordered by source rank then repository ID, and capped at 100 repositories.
  T11 already applies the 100-candidate and public/unarchived rules; the
  defensive checks here prevent invalid evidence from being attributed.
- The union is keyed only by numeric repository ID. A repository never needs
  to appear in both sources, and live-only results keep their broader
  public/unarchived scope without the archive 365-day or licence-content
  gates.
- Equal-weight reciprocal rank fusion uses `k=60`: each repository's
  `rrf_score` is the sum of `1 / (60 + source_rank)` over the sources that
  contain it. Final ordering is `rrf_score` descending, then the best source
  rank, then numeric repository ID. The score ranks relevance only; it is not
  a probability or percentage match.
- `FusedResults.total` is always `None`; source totals are never added.
  GitHub health (`status`, `reason`, optional `retry_after`) and the archive
  status are preserved as `SourceHealth` values, so completed-empty,
  incomplete, unsupported and failed sources stay distinguishable.
- Current live metadata wins a card conflict. Archive snippet/section/revision/
  chunk provenance is attached only for an `ArchiveEvidence` whose metadata
  still has the matching positive numeric ID, is public/unarchived, and whose
  T07 hit fields are well formed. Invalid evidence is dropped, never attached.
- Licences are reported as SPDX IDs. The live side is read only from
  `metadata["license"]["spdx_id"]` (never a GitHub filter keyword); the archive
  side is the stored SPDX value on the chunk hit. A case-only difference
  (`mit` vs `MIT`) is not a conflict; differing SPDX IDs set
  `license_conflict=True` while the current live value remains the card value.

## Tests-first record

Platform: Windows (win32), Python 3.11.9, worktree virtual environment from
`backend/requirements.lock.txt`. Tests use real T10/T11 dataclasses and
synthetic metadata; no live GitHub, OAuth, Milvus or SQLite call is claimed.

| Step | Command | Result |
| --- | --- | --- |
| RED (skeleton returning an empty union) | `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_rank_fusion.py -q` | 14 failed, 0 passed, exit 1; expected assertion failures for the empty union, missing ranks/scores, missing archive cards, source health, caps, invalid-input rejection and SPDX handling |
| GREEN focused | same command | 14 passed, exit 0 |
| Affected existing tests | `python -m pytest backend/tests/test_rank_fusion.py backend/tests/test_keyword_candidates.py backend/tests/test_eligibility.py -q` | 89 passed, exit 0 |
| Full suite and coverage | `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=term-missing --cov-report=json:reports/backend-coverage.json --cov-report=xml:reports/backend-coverage.xml --junitxml=reports/backend-tests.xml` | 743 passed, 49 skipped, 1 warning, exit 0 |
| Coverage gate | `python scripts/quality.py coverage reports/backend-coverage.json` | 94.5% combined, 92.4% branches, exit 0; unchanged 90/80 policy |
| Ruff check | `python -m ruff check backend scripts` | All checks passed, exit 0 |
| Ruff format | `python -m ruff format --check backend scripts` | 50 files already formatted, exit 0 |
| Bandit | `python -m bandit -r backend/app -f json -o reports/bandit.json` | 0 findings, 0 errors, exit 0 |
| Whitespace | `git diff --check` | exit 0 |
| Secret inspection | changed-file scan for credential patterns and `.env` staging | no credential values; no `.env` staged |

The RED skeleton was a temporary empty-union stub, replaced by the implemented
helper before GREEN. The first RED run exposed a duplicated `score` argument in
one test fixture; the fixture was corrected. Two defensive tests (invalid GitHub
candidates and invalid input rejection) were added during GREEN hardening to
cover otherwise-uncovered branches, and the final 14-test set was rerun against
the same stub, so the recorded 14 failures are the final test set.

`main` moved from `f2d86d1` to `1479b8f` (T17 merge) before this PR. `origin/main`
was merged with a merge commit (no rebase) and the checks were rerun on the
merged tree: full suite 770 passed, 65 skipped, 1 warning; coverage 94.5%
combined / 92.2% branches; Ruff check/format, Bandit (0 findings) and
`git diff --check` clean.

Hand-computed RRF fixture: GitHub ranks 1/2/3 for repositories 10/20/30 and
archive ranks 1/2/3 for 20/40/10 produce
`20 = 1/62 + 1/61`, `10 = 1/61 + 1/63`, `40 = 1/62`, `30 = 1/63`, and the
asserted order `[20, 10, 40, 30]`.

## Limits and handoff

- This is a pure helper only. Concurrent retrieval, deadlines, degradation
  rules and API wiring are T13-T15; cursors are T14. No route, cursor,
  configurable ranker, popularity rerank or persistence was added.
- The helper imports the existing T10 `ArchiveEvidence` type and T11
  `KeywordCandidates` type, so importing it also imports their modules. It
  still performs no I/O; T13 owns the calls that produce those values.
- Unit evidence cannot prove live GitHub or Milvus behaviour. The 49 platform/
  server skips are unchanged, and no real-server, hardware or relevance claim
  is made.
- The licence allowlist remains an ingestion policy (D2). Fusion reports the
  current SPDX value and a conflict flag; it does not decide whether a licence
  is acceptable for storage or filtering.
- `ArchiveCard` exposes the best chunk's snippet/section/revision/chunk ID.
  It deliberately does not expose raw vector similarity as a probability.

No raw idea, transcript, embedding or provider credential is read, persisted
or logged by this helper.

Rollback: revert the T12 commit. There is no migration, stored data, route,
configuration or scheduled job to undo; T08/T10/T11 and the legacy endpoint
are unchanged. Operators need take no action.

Source checked: [GitHub repository search syntax](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories)
for the live licence field, and the T10/T11 contracts recorded in their
evidence files.
