# Operator handbook

Status: **T29a, awaiting review** (2026-11-14). This handbook covers the merged
system at `50663f7`. It is the only operator document; the detailed task evidence
stays in [TRACKER](../execution-plans/hybrid-search/TRACKER.md) and the per-task
evidence files.

Every command below names the file it comes from. Where documents disagreed, the
code and the merged evidence won and the other document was corrected in the
same change. T29b will add measured capacity outcomes, the D8 response-time
bound, a rollout recommendation and a real-stack recovery rehearsal after T28;
it does not exist yet.

## 1. Before you start

- **One laptop.** The API, Milvus, the worker and the mobile client all run on
  the owner's Windows laptop. WSL2 Ubuntu runs the archive worker; Docker
  Desktop runs the pinned Milvus stack. There is no second host, failover or
  high-availability path (see [limits](#10-limits)).
- **One worker checkout.** Keep the authoritative worker token and archive
  settings in one ignored `backend/.env` on the Linux filesystem:
  `/home/sumukha/<worker-checkout>/backend/.env`, mode `0600`. Run every manual
  archive command from that `backend/` directory and point the scheduler at the
  same directory. Do not keep extra token copies in worktrees
  ([backend README](../backend/README.md#one-private-worker-token-location)).
- **Never print secrets.** Do not run `docker compose config` without
  `--quiet`, do not put a token in a command argument, and do not paste values
  into logs, evidence or chat
  ([Milvus runbook](../infra/milvus/README.md#start-only-one-profile)).
- **Never destroy archive data to fix an error.** Use ordinary
  `docker compose ... down` (volumes are preserved), never `down -v`, global
  prune or a reset of the auth/archive databases
  ([Milvus runbook](../infra/milvus/README.md#stop-preserve-and-recover)).
- **Respect the archive cap.** The owner set a hard cap of 1,000 archived
  repositories until T28 measures disk/RAM/latency and separately approves the
  10k step. The pilot holds about 204
  ([TRACKER](../execution-plans/hybrid-search/TRACKER.md)).
- **Archive commands are operator commands.** `app.workers.archive` and
  `app.workers.schedule` are local commands, not API routes. Nothing schedules
  itself and nothing stays running between jobs
  ([scheduler runbook](../infra/scheduler/README.md#how-a-run-is-identified-caught-up-and-kept-single)).

## 2. Setup

### 2.1 Backend API

Use Python 3.11. From `backend/`
([backend README](../backend/README.md#setup)):

```sh
python -m venv .venv
# Activate .venv using the command for your shell.
python -m pip install -r requirements.lock.txt
```

Copy `.env.example` to the ignored `.env`. Register a GitHub OAuth app whose
callback is `GITHUB_CALLBACK_URL` (locally
`http://localhost:8000/auth/github/callback`), set `GITHUB_CLIENT_ID` and
`GITHUB_CLIENT_SECRET`, and generate `TOKEN_ENCRYPTION_KEY` with:

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep that key stable and backed up: changing it makes stored provider
credentials unreadable. All settings live in
`backend/app/core/config.py`; the example names and defaults are in
[`backend/.env.example`](../backend/.env.example)
([backend README](../backend/README.md#configuration-and-storage)).

### 2.2 Embedding model

The hybrid route needs the pinned `intfloat/multilingual-e5-small` snapshot. The
stack is separate from the main lock. Install it once, download once with
network access, then keep `HF_HUB_OFFLINE=1` for serving and worker processes
([backend README](../backend/README.md#cpu-embeddings-optional)):

```sh
python -m pip install -r requirements.embeddings.lock.txt
env -u HF_HUB_OFFLINE python ../scripts/embeddings_smoke.py --download --repeats 3
```

### 2.3 Milvus

From the repository root in PowerShell
([Milvus runbook](../infra/milvus/README.md#start-only-one-profile)):

```powershell
Set-Location infra/milvus
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Edit ignored .env: supply two independent random passwords, each >=16 characters.
docker compose --profile gpu config --quiet
docker run --rm --gpus all nvidia/cuda:12.9.1-base-ubuntu24.04 nvidia-smi
docker compose --profile gpu up -d --wait --wait-timeout 180
```

The GPU pre-check is necessary but not proof of GPU indexing. Only port 19530 is
published, on `127.0.0.1`; start one profile at a time. The GPU profile passed
the 1k synthetic proof on driver 617.42, and the runbook baseline is 576.57 or
newer ([Milvus runbook](../infra/milvus/README.md#gpu-verification)). The
`reporadar-t01` Compose project belongs to this archive alone.

### 2.4 Archive worker

Run the worker from the worker checkout's `backend/` with its WSL interpreter,
`HF_HUB_OFFLINE=1` and the private `.env`. Create the Milvus collection once on a
fresh environment
([backend README](../backend/README.md#single-repository-ingestion-t09-merged)):

```sh
python -m app.workers.archive init-collection
```

`init-collection` is the only command that creates the collection; the worker
preflight only verifies and loads it.

### 2.5 Mobile client

From `mobile/` ([mobile README](../mobile/README.md#run-locally)):

```sh
npm ci
npm start
```

Open it on a device with the matching Expo Go version or a development build.
GitHub login needs the configured backend and an iOS/Android development build;
Expo Go and web are visual previews only.

### 2.6 Scheduled jobs (optional, disabled)

The two Windows Task Scheduler templates import **disabled**. Enabling them needs
the owner's explicit approval. Import, dry-run, enable/disable and retry steps are
in the [scheduler runbook](../infra/scheduler/README.md#import-disabled); the
templates contain no secret and the task stores none
([scheduler runbook](../infra/scheduler/README.md#credentials)).

## 3. Start and stop

| Component | Start | Stop | Source |
| --- | --- | --- | --- |
| API | `python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log` | `Ctrl+C` | [backend README](../backend/README.md#setup) |
| Milvus (GPU) | `docker compose --profile gpu up -d --wait --wait-timeout 180` | `docker compose --profile gpu down` | [Milvus runbook](../infra/milvus/README.md#stop-preserve-and-recover) |
| Mobile dev server | `npm start` | `Ctrl+C` | [mobile README](../mobile/README.md#run-locally) |
| Scheduled jobs | `Enable-ScheduledTask -TaskPath '\RepoRadar\' -TaskName archive-weekly` | `Disable-ScheduledTask ...` | [scheduler runbook](../infra/scheduler/README.md#dry-run-enable-disable-retry) |

Stopping the API does not stop Milvus or the worker, and stopping Milvus does not
stop the API. Restarting the API clears its process-local caches: live
visibility is cached for at most 15 minutes and fused pagination snapshots last
5 minutes, so a restart invalidates open cursors
([backend README](../backend/README.md#restore-into-quarantine-t22)).

## 4. Scheduled archive jobs

Windows Task Scheduler is the only scheduler
([scheduler runbook](../infra/scheduler/README.md)):

| Task | When (D7) | Runs |
| --- | --- | --- |
| `reporadar-archive-weekly.xml` | Sunday 03:30 Asia/Kolkata (Saturday 22:00 UTC) | `refresh`, then `backup` |
| `reporadar-archive-daily.xml` | Every day 22:00 Asia/Kolkata (16:30 UTC) | `retire` |

Both tasks run `python -m app.workers.schedule run weekly|daily` from the worker
checkout's `backend/`. Each step is the normal
`python -m app.workers.archive <step>` with its defaults, so the weekly `refresh`
runs with `--cap 0`
([scheduler runbook](../infra/scheduler/README.md#how-a-run-is-identified-caught-up-and-kept-single)).

- **One weekly run per week.** Scheduled, catch-up and manual launches in the
  same Saturday 22:00 UTC period resume one `refresh` run; a completed period
  returns its stored summary without repeating work.
- **Missed runs catch up** when Windows is next up and the owner is signed in.
  `WakeToRun` is off on purpose and the task never stores the Windows password.
- **No overlap.** Task Scheduler uses `IgnoreNew`; the worker also takes
  `schedule.lock` beside the catalogue. A launch still locked out after 2.5 hours
  logs `overlap` and exits 1, and that period stays missed in `status`.
- **A failed refresh still backs up**, because the backup is a consistent export
  on its own; the job exits 1 if any step failed.
- **With `--cap 0` every weekly refresh ends `partial` (`cap`).** That is by
  design, not a failure.

Milvus start/stop settings are optional JSON argument lists in the worker's
ignored `backend/.env`. The job starts Docker Desktop and Milvus only when
needed, waits up to `ARCHIVE_SCHEDULE_MILVUS_READY_SECONDS` (default 300), and
stops only what it started. The settings refuse `-v`, `--volumes` and `--rmi`, so
a stop cannot delete volumes. Leave them empty to only check Milvus. The laptop
values, ordering rules and timings are in the
[scheduler runbook](../infra/scheduler/README.md#starting-and-stopping-milvus);
Milvus uses about 6 GB of RAM while the job runs.

Check status from the worker's `backend/`:

```sh
python -m app.workers.schedule status
```

It prints one JSON line per job: due period, `missed`, `next_due`, last launch
state (`complete`/`partial`/`failed`), each step's last attempt/result/last
success, and any `stop_reason`, `retry_at` or sanitized `error`
([scheduler runbook](../infra/scheduler/README.md#status)). From Windows,
`Get-ScheduledTask -TaskPath '\RepoRadar\' | Get-ScheduledTaskInfo` shows
`LastTaskResult`: 0 means every step exited 0 (a `partial` refresh still exits
0); 1 means a step failed or the launch overlapped.

## 5. Manual weekly refresh

From the worker checkout's `backend/`, with `HF_HUB_OFFLINE=1`, the private
`ARCHIVE_GITHUB_TOKEN`/`MILVUS_TOKEN` and the approved D2 allowlist
([backend README](../backend/README.md#manual-weekly-refresh-t19b-merged)):

```sh
python -m app.workers.archive refresh [--sweep-buckets N] [--cap N]
```

- The run identity is the most recent Saturday 22:00 UTC boundary. Re-running
  the same boundary resumes unfinished work; a completed boundary returns its
  stored summary.
- Every known numeric ID is reconciled with conditional metadata/README reads.
  Unchanged content makes zero embedding calls; a star-only change updates
  metadata without re-embedding.
- Discovery covers the last completed boundary minus 48 hours (the first run
  uses the preceding week), and one 28-day bucket of the rolling 365-day window
  is swept per run. `--sweep-buckets` accepts 1-14; the bucket index advances
  only after a completed run, so a capped or partial bucket is retried.
- `--cap` (0-1000, default 0) bounds repositories not yet in the catalogue. The
  count is durable across resumes; known IDs always reconcile. `--cap 0`
  reconciles known IDs and stops with `cap`.
- **Any `--cap` above 0 needs the owner's explicit approval (D1).** The code
  bounds one run; it does not enforce the 1,000-repository total. Check the
  archive count before admitting repositories and stop below 1,000.
- The command refuses to start unless `ARCHIVE_LICENSE_ALLOWLIST` is exactly the
  approved D2 list.

## 6. Retry a failed or partial run

1. Read `python -m app.workers.schedule status` and
   `schedule-log.jsonl` (below). `partial` is normal with `--cap 0`; `failed`
   needs a look at `stop_reason` and `retry_at`.
2. For `rate_limit` or `quota`, wait until `retry_at` (Unix seconds). An earlier
   retry returns immediately without making requests
   ([scheduler runbook](../infra/scheduler/README.md#dry-run-enable-disable-retry)).
3. Re-run the same job. A weekly retry in the same week resumes the same
   `refresh` run; a completed boundary is idempotent. Use
   `Start-ScheduledTask` for an enabled task, or the dry-run command from the
   scheduler runbook.
4. For a single repository, retry the same numeric ID without deleting
   catalogue, content or vector data:
   `python -m app.workers.archive ingest --repo-id <id>`
   ([backend README](../backend/README.md#single-repository-ingestion-t09-merged)).
5. If WSL fails with `ERROR_NO_SYSTEM_RESOURCES` (including the HCS-prefixed
   form), use **Windows Restart**, not Shut down, because Fast Startup can
   preserve the stuck state
   ([backend README](../backend/README.md#worker-credentials-and-real-run-preflight)).
6. A `WriterBusy` message means another worker holds the archive writer lease;
   wait for it to expire rather than killing processes or deleting locks.

## 7. Back up

From the worker's `backend/`, with the same private settings
([backend README](../backend/README.md#encrypted-backups-t21)):

```sh
python -m app.workers.archive backup
python -m app.workers.archive backup --verify
```

Settings (ignored `backend/.env`; names from
[`backend/app/core/config.py`](../backend/app/core/config.py)):

```sh
ARCHIVE_BACKUP_REPOSITORY=<restic repository on a different volume, outside the catalogue tree>
ARCHIVE_BACKUP_PASSWORD_FILE=/home/sumukha/<private>/restic-password
ARCHIVE_BACKUP_RESTIC=restic
```

- `ARCHIVE_BACKUP_REPOSITORY` must already exist and be initialised; the export
  never creates it. On the laptop it is a folder inside
  `<drive-sync-folder>`, not the catalogue volume.
- `ARCHIVE_BACKUP_PASSWORD_FILE` is `0600`; only restic reads it. The
  application never opens, logs or prints it. A copy of the password is in the
  owner's password manager (owner decision 2026-11-13).
- The catalogue is copied with SQLite's backup API; only referenced content
  files are included, each hash-verified. The suppression ledger is **never**
  included, and Milvus vectors are rebuildable and not backed up.
- The copy runs under the writer lock, so no publication, purge, refresh or
  retention runs meanwhile. Plaintext staging is deleted on success, failure or
  interruption. Only a successful restic snapshot counts as a backup.
- Encrypted snapshots are kept for at most 7 days
  (`backend/app/workers/archive_backup.py`). `--verify` restores the latest
  snapshot privately, checks every manifest hash and runs `restic check`, then
  deletes the restore.

## 8. Restore

Restore is two explicit steps and is never automatic
([backend README](../backend/README.md#restore-into-quarantine-t22)):

```sh
# 1. Restore one snapshot into restore-quarantine/ beside the catalogue.
python -m app.workers.archive restore [--snapshot ID]

# 2. Only after reviewing the quarantine, stop the API, then activate.
python -m app.workers.archive restore --activate
```

Both commands refuse to start unless `ARCHIVE_LICENSE_ALLOWLIST` is exactly the
approved D2 list. `--activate` also needs Milvus, the offline model
(`HF_HUB_OFFLINE=1`) and `MILVUS_TOKEN`.

**Before anything is trusted**, the restore checks exactly one manifest, the
manifest version, every catalogue/content SHA-256 and size, the exact file tree
(no extras, links or ledger), model revision, schema (an older schema is migrated
inside quarantine), SQLite integrity/foreign keys and stored repository IDs. A
failure deletes the restored plaintext and reports a sanitized reason.

**Current suppression wins.** A private, parseable ledger beside the live
catalogue that holds every live suppression is reapplied exactly. A missing or
stale ledger adds every known decision without lifting any, then re-checks every
remaining repository on GitHub by numeric ID. If GitHub stops or an answer is
inconclusive, nothing is kept. An unsafe or unreadable ledger is refused; repair
it first.

**Activation.** Stop the API first. Under the writer lock, activation refuses a
quarantine without a ready verdict or whose catalogue changed since, reapplies
ledger decisions made since the restore and purges again, then embeds every
active chunk, upserts it and reads it back strongly. Only then does it move the
live catalogue and content to `restore-previous-<UTC time>/` and rename the
quarantine in. A failed rename is rolled back.

**Locks and aftercare.** The archive writer lease prevents publication, purge,
refresh, retention or another backup/restore from running at the same time;
`schedule.lock` separately serialises scheduled jobs; SQLite waits up to
`ARCHIVE_BUSY_TIMEOUT_MS` (5000 ms). After activation, restart the API (this
clears the 15-minute visibility cache and 5-minute pagination snapshots), then
run:

```sh
python -m app.workers.archive retire
```

Keep `restore-previous-*` until you are satisfied. To roll back, stop the API and
rename that folder back. Delete it afterwards, because the retirement sweep does
not look inside it.

## 9. Turn the archive off (keyword-only fallback)

There is no user-facing mode switch, and the archive is not a separate product
mode. The merged ranking is `keyword-first-v1`: every GitHub keyword result keeps
its keyword order, then archive-only repositories follow in archive rank order.
If the keyword source fails, is rate-limited or returns nothing, archive-only
results are served alone with unchanged source health
([T27 evidence](../execution-plans/hybrid-search/T27_EVIDENCE.md#option-a-implemented-2026-11-14)).

To run live/keyword-only:

1. Stop Milvus and leave it stopped:
   `docker compose --profile gpu down`
   ([Milvus runbook](../infra/milvus/README.md#stop-preserve-and-recover)).
2. Disable the scheduled tasks so nothing writes to the archive:
   `Disable-ScheduledTask -TaskPath '\RepoRadar\' -TaskName archive-weekly` (and
   `archive-daily`)
   ([scheduler runbook](../infra/scheduler/README.md#dry-run-enable-disable-retry)).
3. Leave the catalogue, content and `ARCHIVE_GITHUB_TOKEN` in place. The hybrid
   runtime serves a live-only target with the archive source reported
   `failed`/`unavailable` and the page marked `degraded`
   ([backend README](../backend/README.md#versioned-hybrid-api-t15-merged)). A
   missing archive reader or signing key instead returns a typed
   `SEARCH_UNAVAILABLE`; removing the token is not a supported way to disable
   the archive.
4. Check `GET /v1/archive/status`; it reports sanitized lifecycle facts only
   (no paths, tokens or exception text) and never invents a last success.

To turn it back on, start Milvus, wait for readiness, and let the runtime retry
the full stack after `HYBRID_BUILD_RETRY_SECONDS` (default 30 s). Open cursors
from the live-only target expire, so the client restarts the search
([backend README](../backend/README.md#versioned-hybrid-api-t15-merged)).

## 10. Limits

### Availability

- Single laptop, single API host, no high availability, failover or multi-host
  rate limiting. SQLite transactions make handoffs and rate counts atomic across
  processes on one host only
  ([backend README](../backend/README.md#configuration-and-storage)).
- Scheduled jobs do not run while the laptop sleeps, is off or nobody is signed
  in; they catch up later, and a daily sweep queued behind a long weekly refresh
  gives up after 2.5 hours
  ([scheduler runbook](../infra/scheduler/README.md#what-it-will-not-do)).
- Fused cursors and visibility checks are process-local; restarting the API
  invalidates open pagination.
- A sleeping laptop does not refresh the archive weekly. Coverage can lag until
  the next catch-up run.

### Coverage and quality

- The archive holds public repositories with a permissive licence and a push in
  the preceding 365 days. The live GitHub branch keeps its broader public,
  unarchived scope.
- The pilot archive holds about 204 repositories. **D1 hard cap: 1,000 archived
  repositories** until T28 measures disk/RAM/latency and the owner separately
  approves 10k
  ([TRACKER](../execution-plans/hybrid-search/TRACKER.md)).
- T27 measured keyword nDCG@10 0.695 versus hybrid 0.428 on 58 ideas, so the
  archive stays out of the top 10 (D8 option A). Option B is the re-entry gate:
  nDCG tolerance 0.02, at least 15 owner-labelled archive-only results, at most 3
  regressions, and archive availability on at least 57 of 58 ideas. **Run 3
  failed the gate: 1 owner-confirmed archive-only pair of 5.** The archive may
  rank above keyword results again only through a new ranking version that
  passes that gate
  ([T27 evidence](../execution-plans/hybrid-search/T27_EVIDENCE.md#option-b-bar-owner-approved-2026-11-13)).
- The D8 response-time bound and capacity outcomes belong to T28/T29b, not this
  handbook.

### Privacy and retention

- User ideas, voice clips, transcripts, summaries and query embeddings exist only
  in request memory. They are not written to the catalogue, auth DB, cache, files
  or application logs; voice logs carry only bytes, duration and latency
  ([backend README](../backend/README.md#v1a-voice-transcription-backend-only)).
- Repository README/metadata chunks and their vectors **are** stored in the
  private archive. Raw content is content-addressed, `0600`, under a private
  `0700` root.
- Voice providers: Deepgram for speech-to-text and text-to-speech, called only
  from the backend with `mip_opt_out=true`; the key never reaches mobile. The
  summary LLM uses switchable profiles: local Ollama, then Cloudflare Workers AI
  on the owner's existing account. Provider failures fall back to text
  ([backend README](../backend/README.md#llm-profiles-v0-merged)).
- The T27 run-3 snapshot and owner labels are private and not committed; only
  aggregate metrics and the verdict are published
  ([T27 evidence](../execution-plans/hybrid-search/T27_EVIDENCE.md#part-b-tool-changes)).
- Backups are encrypted restic snapshots in `<drive-sync-folder>`, kept at most
  7 days, and never include the suppression ledger. The ledger itself is
  content-free: ID, action, reason, time and format version, `0600`, beside the
  catalogue. Purges are not reversible; a purged repository returns only through
  a new ingest after its suppression is lifted
  ([backend README](../backend/README.md#suppression-and-retirement-sweep-t20)).
- Retention (D3): unreferenced content files are deleted after 30 days;
  content-free run history older than 90 days is compacted.

### Open T30 items that affect operations

The [T30 backlog](../execution-plans/hybrid-search/tasks/T30-upkeep.md) still
holds these operator-visible items; this handbook does not claim they are fixed:

- **U7:** a GitHub 422 (rejected query) is reported as `failed`/`unavailable`,
  not a distinct `query_rejected` reason.
- **U9:** the compressed-response burst bound is documented, not measured.
- **U12:** later-page live rechecks reuse the worker-only
  `ARCHIVE_GITHUB_TOKEN`, so serving traffic can spend the worker's rate limit.
- **U15:** the T25 mobile notices/buttons/refresh/focus/touch-target inspection
  on a phone-sized device in both themes has not run.
- **U16:** voice device acceptance on a physical phone has not run; the owner
  performs it manually once the app is complete end to end.

## 11. Logs and private files

All archive files sit beside the catalogue (`ARCHIVE_DATABASE_PATH`, default
`./data/archive/catalogue.sqlite3` relative to `backend/`); content lives under
`ARCHIVE_CONTENT_PATH` (default `./data/archive/content`)
([`backend/.env.example`](../backend/.env.example)).

| File | Contents | Access |
| --- | --- | --- |
| `schedule-log.jsonl` | One sanitized JSON line per step: counts, timings, stop reasons, run/snapshot IDs, `waited_s`; last 400 lines | `0600` |
| `suppression-ledger.jsonl` | Content-free suppression decisions: ID, action, reason, time, version | `0600` |
| `backfill-<run_id>.jsonl` | Sanitized per-partition backfill log | private, beside catalogue |
| `restore-quarantine/` | Restored plaintext awaiting review | private `0700`/`0600` |
| `restore-previous-<UTC time>/` | The archive replaced by activation | private |

Worker output is reduced to allowlisted counts, timings, stop reasons and IDs; an
error containing a path, URL or token-like string is replaced by
`error withheld from the log`. Ideas, tokens, README text and file paths never
reach it ([scheduler runbook](../infra/scheduler/README.md#status)). The API logs
counts and durations, not request bodies or ideas. Windows Task Scheduler keeps
its own history and `LastTaskResult`.

## 12. Troubleshooting

| Symptom | Meaning | Action |
| --- | --- | --- |
| `partial` with `cap` | `--cap 0` reconciled known IDs only | Expected; approve a cap or leave it |
| `overlap`, exit 1 | Another scheduled job held the lock for 2.5 h | Run the missed job manually |
| `WriterBusy` | Another worker holds the writer lease | Wait for expiry; do not delete locks |
| `retry_at` set | GitHub rate limit or quota | Wait until that Unix time; an early retry makes no requests |
| `milvus_unavailable` | Milvus never became ready | Check `GET /v1/archive/status` and the Milvus runbook; backup still ran |
| `SEARCH_UNAVAILABLE` "starting" | Cold build still running | Retry after `HYBRID_BUILD_WAIT_SECONDS`; the runtime caches the build |
| `degraded` page | Archive source failed | Check Milvus/model; live results are still served |
| WSL `ERROR_NO_SYSTEM_RESOURCES` | WSL VM stuck or host RAM exhausted | Close heavy apps, then Windows **Restart** |
| Restore refuses an unsafe ledger | Ledger unreadable or missing live decisions | Repair the ledger first; do not bypass the check |
| Activation refuses the quarantine | No ready verdict or the catalogue changed | Re-run `restore` and review the quarantine again |

## 13. Sources

- [Backend commands and settings](../backend/README.md) and
  [`backend/.env.example`](../backend/.env.example).
- [Milvus stack](../infra/milvus/README.md).
- [Scheduled jobs](../infra/scheduler/README.md).
- [Mobile client](../mobile/README.md).
- [Hybrid architecture and decisions](../execution-plans/hybrid-search/ARCHITECTURE.md).
- [Task tracker and acceptance evidence](../execution-plans/hybrid-search/TRACKER.md).
- [T27 relevance and D8 evidence](../execution-plans/hybrid-search/T27_EVIDENCE.md).
- [T30 upkeep backlog](../execution-plans/hybrid-search/tasks/T30-upkeep.md).
