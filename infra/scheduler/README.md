# Weekly and daily archive jobs (T23)

Two Windows Task Scheduler templates start the archive worker inside WSL. Windows Task Scheduler is the only scheduler. Nothing in the API, the worker or WSL schedules itself or stays running between jobs.

| Task | When (D7) | Runs |
| --- | --- | --- |
| `reporadar-archive-weekly.xml` | Sunday 03:30 Asia/Kolkata (Saturday 22:00 UTC) | `refresh`, then `backup` |
| `reporadar-archive-daily.xml` | Every day 22:00 Asia/Kolkata (16:30 UTC) | `retire` |

Both tasks run one command, `python -m app.workers.schedule run weekly|daily`, from the worker checkout's `backend/` folder. That command runs each step as `python -m app.workers.archive <step>` with that step's defaults. `refresh` therefore runs with `--cap 0`: no new repositories are admitted until the owner approves a cap under D1.

**The templates are imported disabled.** Importing them does not activate anything. Enabling them needs the owner's explicit approval. Until then, run the weekly job by hand after each refresh, as before.

## How a run is identified, caught up and kept single

- **One weekly run per week.** The weekly period is the same Saturday 22:00 UTC boundary that `refresh` already uses as its run identity. A scheduled launch, a catch-up launch on Monday and a manual run in the same week all resume one `refresh` run. A completed week returns its stored summary without doing the work again.
- **Missed runs catch up.** The tasks use *Run task as soon as possible after a scheduled start is missed* (`StartWhenAvailable`). If the laptop was off or asleep at 03:30, the job starts the next time Windows is up and you are signed in. The job still records the period it belongs to, not the time it started.
- **No overlap.** Task Scheduler ignores a new launch while the same task is running (`IgnoreNew`). The worker also takes a private lock file (`schedule.lock` beside the catalogue), so the weekly and daily jobs never run at the same time. A launch that finds the lock held runs nothing, logs `overlap` and exits 1. The archive's own writer lease still protects against a manual command running alongside.
- **A failed refresh still backs up.** The backup is a consistent export on its own, so the 7-day copies stay current. The job exits 1 if any step failed.

## What it will not do

- **It will not run while the laptop sleeps, is off or nobody is signed in.** `WakeToRun` is off on purpose, and the task runs only while you are signed in, so Windows never stores your password. A sleeping laptop does not refresh weekly; it catches up when it next wakes and you sign in.
- **It does not start Docker Desktop or Milvus.** `refresh` and `retire` need the GPU Milvus stack (`infra/milvus`, `--profile gpu`). If Milvus is down, the step fails with a sanitized error and `status` shows it. `backup` does not need Milvus.
- **With `--cap 0`, every weekly refresh ends `partial` (`cap`).** That is by design (T19b) and is not a failure.
- A console window opens briefly while the job runs.

## Status

From `backend/` in WSL, with the worker interpreter:

```sh
/home/sumukha/reporadar-worker-venv/bin/python -m app.workers.schedule status
```

It prints one JSON line. For each job it shows the current due period, whether that period has been attempted (`missed`), `next_due` (`"now"` if the current period was missed), and the state of the last launch (`complete`, `partial` or `failed`). For each step it shows the last attempt, its state and result, the last success, and any `stop_reason`, `retry_at` (Unix seconds) or sanitized `error`. It reads only the job log, so commands run directly with `app.workers.archive` do not appear in it.

The log is `schedule-log.jsonl` beside the catalogue: private (0600), one JSON line per step, the most recent 400 lines kept. It holds counts, timings, stop reasons, run and snapshot IDs only, picked from an allowlist. Ideas, tokens, README text and file paths never reach it. Anything the worker printed that is not its JSON summary is logged as `unreadable`.

Task Scheduler shows the same thing from Windows:

```powershell
Get-ScheduledTask -TaskPath '\RepoRadar\' | Get-ScheduledTaskInfo |
  Select-Object TaskName, LastRunTime, LastTaskResult, NextRunTime
```

`LastTaskResult` 0 means every step exited 0 (a `partial` refresh still exits 0); 1 means at least one step failed or the launch overlapped.

## Import (disabled)

Check that Windows is set to India Standard Time (the trigger times are local):

```powershell
(Get-TimeZone).Id   # expect: India Standard Time
```

Then fill in the three placeholders and register both tasks. Use your WSL distribution name (`wsl -l -q`), the Linux path of the worker checkout's `backend/` folder, and the worker interpreter. No paths in the template contain a secret.

```powershell
$values = @{
  '__WSL_DISTRO__'    = 'Ubuntu'
  '__BACKEND_DIR__'   = '/home/sumukha/<worker-checkout>/backend'
  '__WORKER_PYTHON__' = '/home/sumukha/reporadar-worker-venv/bin/python'
}
foreach ($job in 'weekly', 'daily') {
  $xml = Get-Content -Raw "infra\scheduler\reporadar-archive-$job.xml"
  foreach ($key in $values.Keys) { $xml = $xml.Replace($key, $values[$key]) }
  Register-ScheduledTask -TaskPath '\RepoRadar\' -TaskName "archive-$job" -Xml $xml
}
```

## Dry run, enable, disable, retry

- **Dry run (before enabling).** Run the exact action by hand from PowerShell, then read the status. This is a real run: the weekly job does a real refresh and backup, so make sure Milvus is up.

  ```powershell
  wsl.exe -d Ubuntu --cd /home/sumukha/<worker-checkout>/backend --exec /usr/bin/env HF_HUB_OFFLINE=1 /home/sumukha/reporadar-worker-venv/bin/python -m app.workers.schedule run weekly
  echo $LASTEXITCODE
  ```

- **Enable (owner approval required):** `Enable-ScheduledTask -TaskPath '\RepoRadar\' -TaskName archive-weekly` (and `archive-daily`).
- **Disable:** `Disable-ScheduledTask -TaskPath '\RepoRadar\' -TaskName archive-weekly` (and `archive-daily`). A running job finishes its current step; to stop it now, use `Stop-ScheduledTask`. The archive commands resume safely after a kill.
- **Retry:** run the same job again, either with `Start-ScheduledTask` (enabled tasks only) or the dry-run command. A weekly retry in the same week resumes the same refresh run. After `rate_limit` or `quota`, wait until `retry_at`; an earlier retry returns straight away without any requests.
- **Remove:** `Unregister-ScheduledTask -TaskPath '\RepoRadar\' -TaskName archive-weekly` (and `archive-daily`). Deleting `schedule-log.jsonl` only clears the status history.

## Credentials

The task stores no credential. It runs as you, only while you are signed in, at the lowest privilege. The worker reads its private settings, including the GitHub worker token, the same way a manual run does (the worker checkout's ignored `backend/.env`), and restic reads its password file itself. Nothing secret is passed on the command line or written to the job log. To rotate the worker token, change `backend/.env`; the tasks need no change.
