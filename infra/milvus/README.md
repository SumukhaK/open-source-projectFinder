# T01 local Milvus feasibility stack

This is a disposable **synthetic development experiment**, not an archive deployment. The API does not use the SDK yet. The CPU profile has passed a 1,000-row proof; the GPU profile is configured but has not passed Milvus indexing on this host. See [dated evidence](../../execution-plans/hybrid-search/T01_EVIDENCE.md). No user ideas, GitHub content, model weights or production database are inputs.

## Pinned compatibility set

Use Python 3.11 and the backend lock (`pymilvus==2.6.17`). Compose pins image tags **and SHA256 digests**: Milvus 2.6.26 CPU/GPU, etcd 3.5.25 and the upstream Milvus MinIO release 2024-12-18. The server API reports a `2.6-...` build identifier; image digest is the exact server identity, not that display string. Do not copy configuration defaults from Milvus 3 documentation. The new Python dependencies are locked and audited; container images have not had a separate vulnerability scan. These are upstream release-compatible dependencies for an isolated probe, not an endorsement for public hosting.

## Start only one profile

From the repository root, create an isolated Python environment and install `backend/requirements.lock.txt`. Then in PowerShell:

```powershell
Set-Location infra/milvus
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Edit ignored .env: supply two independent random passwords, each >=16 characters.
docker compose --profile cpu config --quiet
docker compose --profile cpu up -d --wait --wait-timeout 180
$values = Get-Content .env | ConvertFrom-StringData
$env:MILVUS_URI = 'http://127.0.0.1:19530'
$env:MILVUS_TOKEN = 'root:' + $values.MILVUS_PASSWORD
& ../../backend/.venv/Scripts/python.exe ../../scripts/milvus_probe.py --profile cpu
Remove-Item Env:MILVUS_TOKEN
docker compose --profile cpu down
```

On Linux/WSL use the environment's `bin/python`, export the same URI/token from the private environment, and run the same probe. Do not put a token in a shell command argument or commit environment values. Never print `docker compose config` without `--quiet`: it expands credentials. Password changes in `.env` do not rotate credentials already stored in existing volumes; use Milvus's authenticated password update procedure before reusing those volumes. An empty `.env.example` cannot start the stack unchanged.

Only port 19530 is published, on **127.0.0.1**, with Milvus authorization enabled and an explicitly supplied root password. The root credential is for this synthetic setup only. MinIO, etcd and the management/WebUI port have no host bindings. CPU and GPU use separate metadata roots, buckets and local volumes; start one at a time because the same loopback port is deliberately shared. Do not add global container names, a Docker socket mount, public port binds, `privileged`, a `seccomp:unconfined` override or default example credentials.

The stack uses the project's normal bridge network; Docker Desktop 29.8.2 did not publish the host port when it was marked `internal`. This is localhost/private-network isolation, not a network-egress firewall or TLS deployment. No repository content is executed or fetched.

## GPU verification

After `docker compose --profile cpu down`, the equivalent commands use `--profile gpu` for both Compose and the probe. Run them only after verifying compatible Windows driver/WSL/container support. No CPU fallback is hidden inside this profile: the probe requires `GPU_CAGRA`, an IP metric and actual successful operations. Capture GPU device/process and memory readings during build/load/search; a CUDA `nvidia-smi` check alone is not GPU Milvus proof.

The pinned GPU image declares **CUDA 12.9.1**. On the observed GTX 1650 Ti / driver 551.61, its CUDA requirement fails before startup. Do not bypass `NVIDIA_REQUIRE_CUDA` or add `NVIDIA_DISABLE_REQUIRE`; do not install a Linux display driver into WSL. A compatible Windows driver update or a separately reviewed compatible version set is an operator action. CPU-only continuation requires agreement; this PR does not grant it.

## Resource limits and probe safety

- Milvus process limit: 4 GiB RAM / 4 CPUs; MinIO: 512 MiB / 1 CPU; etcd: 256 MiB / 1 CPU. Logs rotate at 10/5 MiB, two files each. Persistent named volumes are private to project `reporadar-t01`; they are not the future archive catalogue.
- GPU scratch-pool settings are 128/256 MiB for this tiny test. They do **not** cap total VRAM; GPU collection data and index/rebuild peaks require separate measurement. Only GPU device 0 is requested; no embedding model competes for its memory.
- Synthetic vectors: seed17, 1,000 rows, 384 dimensions, normalized; CPU HNSW and prospective GPU_CAGRA both use IP. Counts cannot exceed1,000. Each RPC has a timeout (30s; build/load/flush120s). The tool uses a unique `reporadar_t01_*` collection and drops only one whose creation succeeded in that invocation, even when validation fails. A process kill can leave that named collection; inspect ownership before manual cleanup.
- Checks verify the inserted count, normalized self-match, scalar-filtered IDs, requested index/metric, visible upsert and delete. A failure exits nonzero rather than claiming GPU fallback or an empty successful search. Exceptions are sanitized; inspect private Milvus logs for operational diagnosis. A warm repeat rebuilds a fresh disposable collection.
- Maintain at least 10 GiB host-volume free disk, monitor actual RAM/VRAM/swap while testing, and stop on pressure/OOM rather than expanding limits. The documented standalone minimum is8GiB, above this host's observed5.8GiB Docker cap. Passing a1k CPU sample does not meet the supported-host minimum or establish10k/production capacity. This run used about1.7GiB of additional image disk, not a production storage estimate.

`docker stats --no-stream` gives sampled container memory/CPU, not a complete instantaneous peak or host total. Record sample cadence, first/repeat timings, OOM flags, free disk and GPU readings. No model/latency/relevance or annual-corpus capacity claims follow from this experiment. Confirm the WSL worker's linked SQLite WAL fix before any future archive WAL mode; current WSL3.46.1 fails that gate. From the repository in the actual Linux worker environment, run `python3 -c "import sqlite3; from scripts.milvus_probe import wal_is_fixed; print(sqlite3.sqlite_version, wal_is_fixed(sqlite3.sqlite_version))"`. This reads the linked library only; it does not enable WAL or modify a database.

## Stop, preserve and recover

`docker compose --profile cpu down` (or gpu) stops this project's containers and removes its network while **preserving volumes**. Do not use `down -v`, global Docker prune, or delete unrelated images/volumes to free memory. Restore service with the same private environment, profile and locked versions; rerun the disposable proof. A server error never justifies resetting the future auth/archive databases.

The previous OpenCode session left `%USERPROFILE%/.wslconfig` at memory6GB/swap2GB. T01 continuation preserves that pre-existing file; it does not change host/driver settings. Restoring earlier WSL settings and any `wsl --shutdown` must be explicitly coordinated by the operator because they affect unrelated workloads. The probe containers are stopped after verification; retained images, volumes and ignored `.env` remain local for review/retry.

## Sources

- [Exact CPU Compose source](https://github.com/milvus-io/milvus/blob/v2.6.26/deployments/docker/standalone/docker-compose.yml), [exact GPU Compose source](https://github.com/milvus-io/milvus/blob/v2.6.26/deployments/docker/gpu/standalone/docker-compose.yml), [exact config](https://github.com/milvus-io/milvus/blob/v2.6.26/configs/milvus.yaml). The release's example files still name2.6.25; this experiment pins and measures2.6.26 explicitly.
- [GPU deployment](https://milvus.io/docs/v2.6.x/install_standalone-docker-compose-gpu.md), [GPU constraints and memory](https://milvus.io/docs/v2.6.x/gpu-index-overview.md), [authentication/password update](https://milvus.io/docs/v2.6.x/authenticate.md).
- [WSL CUDA guidance](https://docs.nvidia.com/cuda/wsl-user-guide/index.html), [CUDA compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/), [SQLite WAL-reset fix](https://sqlite.org/wal.html#walreset).
