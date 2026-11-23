# RepoRadar API on an Oracle Cloud Always Free VM

Status: **not deployed.** This is the host the owner chose (HD4, 2026-11-23)
after Hugging Face started requiring PRO for Docker Spaces on free CPU basic.
The plan is in the [hosting tracker](../../execution-plans/hf-hosting/TRACKER.md).

```
phone ──HTTPS──► Caddy (:443, automatic Let's Encrypt) ──► api (:7860, deploy/api image)
                                                     ├─► Zilliz Cloud (vectors)
                                                     └─► ./data (SQLite, persistent disk)
```

The API image is [`deploy/api/Dockerfile`](../api/Dockerfile): Python 3.11,
uid 1000, the pinned embedding model downloaded and hash-checked at build time,
`HF_HUB_OFFLINE=1` while serving. Archive workers (refresh, retire, backup) stay
on the laptop for now and write to the same Zilliz cluster (H5).

## 1. Create the VM (owner)

- Oracle Cloud free account. Choose a home region close to you; it can't be
  changed later.
- **Compute > Instances > Create instance**: image **Ubuntu 24.04**, shape
  **VM.Standard.A1.Flex** (Ampere ARM) with 2 OCPU and 12 GB, inside the Always
  Free allowance. Save the SSH private key.
- **Networking**: in the instance's subnet security list, add ingress rules for
  TCP 80 and 443 from `0.0.0.0/0`. Port 22 is there already.

"Out of capacity" is common for free ARM shapes: retry later or pick another
availability domain.

## 2. Prepare the VM

```sh
ssh -i <key> ubuntu@<public-ip>
# Oracle's Ubuntu images also block ports in iptables; open 80 and 443 there too.
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
# Docker Engine and the Compose plugin (Docker's convenience script).
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && exit   # log in again for the group
git clone https://github.com/SumukhaK/open-source-projectFinder.git
cd open-source-projectFinder/deploy/oracle-vm
```

## 3. Settings

- `API_HOST`: the VM's public IP with dashes, under the free sslip.io DNS, for
  example `203-0-113-7.sslip.io`. Caddy gets a real certificate for it, so the
  GitHub callback and the phone use HTTPS without buying a domain. Put it in
  `.env` beside `compose.yaml`: `echo API_HOST=203-0-113-7.sslip.io > .env`.
- `api.env`: `cp api.env.example api.env && chmod 600 api.env`, then fill it in
  with an editor on the VM. Never paste values into chat, issues or commands.
  `GITHUB_CALLBACK_URL` is `https://<API_HOST>/auth/github/callback`. Both files
  are ignored by git.
- GitHub OAuth app "RepoRadar (hosted)": set its homepage to
  `https://<API_HOST>` and its callback to the same `GITHUB_CALLBACK_URL`.

## 4. Data and start

```sh
mkdir -p data/archive && sudo chown -R 1000:1000 data
# Copy the laptop's catalogue (read-only for the API). On the laptop, in the
# worker's backend/ with no job running, take a consistent copy (WAL-safe):
#   python -c "import sqlite3; sqlite3.connect('data/archive/catalogue.sqlite3').backup(sqlite3.connect('/tmp/catalogue.sqlite3'))"
#   scp -i <key> /tmp/catalogue.sqlite3 ubuntu@<public-ip>:
# Then on the VM:
sudo install -o 1000 -g 1000 -m 600 ~/catalogue.sqlite3 data/archive/catalogue.sqlite3
docker compose up -d --build      # first build downloads torch and the model
curl https://<API_HOST>/health    # {"status":"ok"}
```

The laptop worker still updates the catalogue weekly. Until H5 automates it,
repeat the copy after each weekly run and `docker compose restart api`.
`data/` persists across restarts and rebuilds. Back it up by copying `data/auth.sqlite3` while the API is stopped, or set `STATE_SYNC_REPO`
and `STATE_SYNC_TOKEN` in `api.env` for an automatic off-machine copy (HD1).

## 5. Operate

| Task | Command (in `deploy/oracle-vm`) |
| --- | --- |
| Update to latest `main` | `git pull && docker compose up -d --build` |
| Logs | `docker compose logs -f api` |
| Stop / start | `docker compose stop` / `docker compose start` |

Never run `docker compose down -v`: it deletes Caddy's certificates. Never
delete `data/`. Forwarded headers stay off, so per-IP limits count Caddy as one
client. That's fine for a single-owner app; revisit before opening it to others.
Caddy has no access log, because auth callbacks carry codes in the query string.
