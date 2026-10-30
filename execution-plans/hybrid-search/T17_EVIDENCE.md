# T17 durable runs and fenced publication

Status: Awaiting review in [PR #40](https://github.com/SumukhaK/open-source-projectFinder/pull/40). No acceptance, merge or review marker has been recorded.
Implemented and verified 2026-10-29/30. Branch: `codex/hybrid-t17-durable-runs`.
Base: `f2d86d14a64979391e3210dd5b9f12db9a78943c`.

## Scope and verified prerequisites

T03 `776bf654`, T08 `952f7e2`, T16 `539d02e` and T09 `7766744` are ancestors
of the base. A fresh fetch before submission still returned the same main SHA.
D7 is approved: daily privacy/removal about 22:00 and Sunday refresh 03:30
Asia/Kolkata with catch-up. T17 represents these as separate run kinds plus the
original scheduled instant normalized to UTC; it does not calculate schedules,
install host tasks or fetch GitHub data.

Four production files changed: catalogue migration, central lease constants,
`archive_runs` and T08 publication. T09 calls remain source-compatible. There are
no dependencies, lockfile, workflow, gate or quality-policy changes.

## Durable state and fencing

Migration 4 adds only runs, partitions and tasks. A unique run kind/due instant
prevents overlapping launches from creating duplicate periods. One live writer
exists across all runs. Claim/heartbeat/release use short immediate transactions;
every takeover advances a catalogue-wide fence and invalidates previous owners.
The clock is injectable. Default lease 300 seconds; accepted duration 1..3600.

Partitions retain the complete T16 `as_record` representation under its stable
key and restore through `from_record`. A split validates and inserts the whole
T16 child set atomically. Page, stage, last repository ID, retry count and retry
instant survive a new RunStore/process; future retries are refused without
sleeping. Completion and its checkpoint commit together. Completed intervals
retain their pushed/created/star ranges, so a high completed timestamp cannot
hide an unfinished interval. Completed partitions cannot reopen and a parent
cannot complete with unfinished children.

Publication and cleanup take a nonblocking OS lock on the catalogue's adjacent
private `.writer.lock` file. They never hold SQLite transactions over vector IO.
A successor can take over an expired lease while an old RPC is running, but its
vector operation gets WriterBusy until the OS lock is released. Fence checks
inside staging, activation and cleanup transactions reject the old owner; batch
checks stop further IO once lease loss is observed.

A local lock cannot cancel remote requests. The task ledger therefore binds a
repository/revision to a digest of the **entire vector payload**, including
scalar metadata, before upserting. No vector values or README text are stored
in this ledger. Identical retries are safe even if a late request arrives;
different payloads for the same revision are refused. Activation verifies the
staged digest. Cleanup commits intent before deletion and permanently retains
a content-free repo/revision tombstone, even after successful calls: the SDK
can hide an earlier ambiguous request behind a successful retry. Retired IDs
cannot become current again. Existing active-revision filtering remains intact.

Unfenced T09 publication/reconciliation calls acquire temporary leases and the
same OS lock. They cannot bypass an active scheduled worker. Their expiry
fails closed; unchanged ingestion still returns before embedding/vector writes.
Existing T08/T09 regressions pass. Legacy failure-injection fixtures were moved
from the second write transaction to the fourth (temporary run, claim, stage,
activation), preserving their original failure boundary and assertions.

## Tests-first evidence

All commands ran from the task checkout. Windows Python:
`E:/OpenSourceProjectFinder-t01/backend/.venv/Scripts/python.exe` (3.11.9,
SQLite 3.45.1). Linux Python: `/home/sumukha/reporadar-worker-venv/bin/python`
(3.11.17, SQLite 3.53.1). WAL fixtures use Linux-native pytest temporary paths.
Neither interpreter nor system SQLite was modified.

| Check | Actual result |
| --- | --- |
| Baseline Windows: pytest store/publication/worker/partitions | 133 passed, 41 POSIX skips |
| RED `pytest backend/tests/test_archive_runs.py -q` before implementation | Windows: 5 failures, 6 skips; Linux: 11 failures. Missing durable operations and v4 migration asserted explicitly. Covers same period, takeover, restart mid-page, durable retry and checkpoint rollback. |
| Initial GREEN durable tests | Windows 5 passed/6 skips; Linux 11 passed, including real WAL/v3 migration |
| RED fencing tests before boundary integration | 4 failures: unfenced bypass and absent lease-aware publish/activate/cleanup |
| RED parent coverage | 1 failure: incomplete children allowed premature parent completion |
| RED atomic split | 1 failure: absent atomic split registration |
| RED late delete | 1 failure: retired ID could be reused after ambiguous deletion |
| RED late upsert | 3 failures: pending/active changed-payload replay and reuse after uncertain upsert cleanup |
| Final full Linux pytest backend/tests scripts/tests with branch coverage | **819 passed, 2 skipped**, exit 0; optional live Milvus tests skipped, no live service claims |
| `python scripts/quality.py coverage reports/t17/backend-coverage.json` | **96.4% combined, 94.5% branches**, exit 0; unchanged 90/80 gate |
| `ruff check backend scripts`; `ruff format --check backend scripts` | Exit 0; 51 files formatted |
| `bandit -r backend/app -f json -o reports/t17/bandit.json` | Exit 0 |
| `git diff --check` | Exit 0 |
| AST comparison of MIGRATIONS against base | Migrations 1-3 exactly unchanged; exactly one additive migration 4 |

Final Windows full suite: **756 passed, 65 skipped**, exit 0, one inherited
Starlette/httpx deprecation warning. Windows does not establish WAL correctness.
Concurrent coverage initially shared the default data file and produced Windows
path warnings; that Windows coverage report is not used for a gate claim. Linux
was rerun independently with `COVERAGE_FILE=reports/t17/.coverage-linux`.
Ignored logs are in `reports/t17/`; they are not needed to run the committed tests.
No tests use wall-clock sleeps: lease expiry uses an injected clock; the real
cross-process lock test synchronizes through a pipe with bounded failure waits.

An independent implementation reviewer reproduced partial split registration,
late deletes, late upserts and hidden SDK retries. All were corrected. The final
review found no remaining important issue and independently passed six focused
fencing regressions. This feedback is not exact-head acceptance or a review
marker. Required remote CI and the trusted PR review remain separate gates.

## Migration, rollback and operator notes

The v3 upgrade test creates a real catalogue with migrations 1-3, existing
repository and suppression rows, upgrades/reopens it twice, checks version 4,
checks preserved IDs and runs foreign_key_check. Checkpoint rollback is injected
after the task update but before partition completion: both changes roll back
while a previously completed interval remains intact. A split insertion trigger
fails the second child and proves the first child/task also roll back.

Before deploying, stop **all** old workers and drain in-flight vector requests;
old binaries do not participate in the new fence/lock protocol. Take a consistent
SQLite backup with its private content manifest using the backup API, not a copy
of a live database file without its WAL. Start only the upgraded worker on the
same Linux-native private path. Do not delete the lock file, reset leases, edit
fences, remove task tombstones or run mixed old/new writers to recover.

Old v3 code correctly refuses a v4 catalogue. There is no down migration. A
rollback requires stopping writers, draining remote operations, restoring the
matching pre-upgrade backup into quarantine and reconciling/rebuilding vectors
before serving; it must not resurrect suppressed content. No real production
catalogue was migrated and no production restore was attempted in T17.

Run rows currently carry the monotonically increasing fence high-water mark.
Future T20 90-day run retention must preserve that counter and the task identity
ledger before deleting history; foreign keys intentionally prevent blind run
removal. Do not purge these records manually.

## Limits

Single host, one canonical Linux catalogue/lock path and one vector generation;
this is not a distributed transaction or a cluster lease. A stuck live process
can hold the operation lock beyond lease expiry: fail closed and stop/drain it
rather than deleting the lock. Clock rollback may delay expiry, but takeover
invalidates old ownership even if time subsequently moves backwards.

T17 deliberately refuses changed scalar/vector payloads for an existing revision
and all reuse of retired revision IDs. T19/recovery work must introduce an
explicit safe generation protocol before enabling those operations. No automatic
quarantine expiry/recovery command is supplied. Daily/weekly orchestration,
backfill, retention and host activation remain later tasks. No live GitHub or
Milvus calls were made; delayed remote behavior was tested with deterministic
fakes and the review also inspected the installed SDK retry behavior.
