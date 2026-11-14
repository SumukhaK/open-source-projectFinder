"""T28 capacity benchmark: bounded timings on the real local archive stack.

``embed``   CPU passage-embedding throughput at the worker batch size, using
            synthetic passages of the chunker's token budget (no repository text).
``search``  timed hybrid searches over the frozen T27 ideas. ``--mode archive``
            replaces the GitHub keyword source with an empty answer, so only the
            archive branch runs (query embedding, Milvus, public-visibility
            checks); ``--mode hybrid`` runs the real service. Per-stage times
            are recorded, plus busy rejections above the admission limit.
``disk``    sizes of the catalogue, raw content and backup repository.

Every run appends one JSON line of sanitized numbers to ``--out``: no ideas,
results, tokens, paths or secrets. Runs stop early when the host is short of
memory (see ``--guard-file``). Reads backend/.env like the archive workers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from scripts.relevance_eval import _percentile, load_ideas  # noqa: E402

MIN_HOST_AVAILABLE_MB = 1000  # same abort guard as the T01 GPU run
MIN_FREE_DISK_MB = 5000


def summarize(values):
    """Median/p95/max of a list of numbers, or None when empty."""
    values = [v for v in values if isinstance(v, (int, float))]
    if not values:
        return None
    return {
        "n": len(values),
        "p50": round(_percentile(values, 0.5), 1),
        "p95": round(_percentile(values, 0.95), 1),
        "max": round(max(values), 1),
    }


class Guard:
    """Stops a run when Windows or WSL memory, or disk, runs low."""

    def __init__(self, guard_file):
        self.guard_file = Path(guard_file) if guard_file else None
        self.min_host_mb = None

    def host_available_mb(self):
        if not self.guard_file or not self.guard_file.exists():
            return None
        lines = self.guard_file.read_text().strip().splitlines()
        try:
            return int(float(lines[-1].split(",")[-1]))
        except (IndexError, ValueError):
            return None

    def check(self):
        host = self.host_available_mb()
        if host is not None:
            self.min_host_mb = (
                host if self.min_host_mb is None else min(self.min_host_mb, host)
            )
            if host < MIN_HOST_AVAILABLE_MB:
                raise SystemExit(f"stopped: host available memory {host} MB")
        if shutil.disk_usage("/").free // 2**20 < MIN_FREE_DISK_MB:
            raise SystemExit("stopped: WSL disk nearly full")


class Sampler:
    """Samples this process's RSS and the WSL VM's available memory each second."""

    def __init__(self):
        self.peak_rss_mb = 0
        self.min_vm_available_mb = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            rss = _proc_kb("/proc/self/status", "VmRSS:") // 1024
            avail = _proc_kb("/proc/meminfo", "MemAvailable:") // 1024
            self.peak_rss_mb = max(self.peak_rss_mb, rss)
            if avail:
                self.min_vm_available_mb = (
                    avail
                    if self.min_vm_available_mb is None
                    else min(self.min_vm_available_mb, avail)
                )
            self._stop.wait(1)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()


def _proc_kb(path, key):
    try:
        for line in Path(path).read_text().splitlines():
            if line.startswith(key):
                return int(line.split()[1])
    except OSError:
        pass
    return 0


class Timed:
    """Wraps one dependency method and records each call's milliseconds."""

    def __init__(self, inner, method, calls):
        self._inner, self._method, self._calls = inner, method, calls

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if name != self._method:
            return attr

        def timed(*args, **kwargs):
            started = time.perf_counter()
            try:
                return attr(*args, **kwargs)
            finally:
                self._calls.append((time.perf_counter() - started) * 1000)

        return timed


class _EmptyKeyword:
    """Stands in for GitHub in archive mode: a completed empty answer, no call."""

    def search(self, token, idea, filters=None):
        from app.services.keyword_candidates import KeywordCandidates

        return KeywordCandidates()


async def run_searches(service, token, ideas, *, requests, concurrency, guard, pause):
    """Runs ``requests`` searches, at most ``concurrency`` at once, cycling ideas."""
    stages = {"github": [], "embed": [], "milvus": [], "visibility_call": []}
    service.github = Timed(service.github, "search", stages["github"])
    service.embeddings = Timed(service.embeddings, "embed", stages["embed"])
    service.vectors = Timed(service.vectors, "search", stages["milvus"])
    reader = service.eligibility.reader
    service.eligibility.reader = Timed(
        reader, "fetch_metadata", stages["visibility_call"]
    )
    totals, statuses = [], {}
    gate = asyncio.Semaphore(concurrency)

    async def one(index):
        async with gate:
            guard.check()
            if pause:
                await asyncio.sleep(pause)
            idea = ideas[index % len(ideas)]["idea"]
            started = time.perf_counter()
            outcome = await service.search(token, idea)
            totals.append((time.perf_counter() - started) * 1000)
            archive = outcome.fused.archive
            key = f"{outcome.status}/archive={archive.status}:{archive.reason}"
            statuses[key] = statuses.get(key, 0) + 1

    await asyncio.gather(*(one(i) for i in range(requests)))
    return {
        "total_ms": summarize(totals),
        "stages_ms": {name: summarize(values) for name, values in stages.items()},
        "github_search_calls": sum(1 for ms in stages["github"] if ms >= 1),
        "visibility_calls": len(stages["visibility_call"]),
        "outcomes": statuses,
    }


def _settings():  # pragma: no cover - needs the real stack
    from app.core.config import Settings

    env = Path(os.environ.get("CAPACITY_ENV_FILE", ROOT / "backend" / ".env"))
    os.chdir(env.parent)  # relative archive paths resolve like the workers'
    return Settings(_env_file=env)


def _base_record(command):
    return {
        "command": command,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpus": os.cpu_count(),
    }


def bench_embed(args):  # pragma: no cover - needs the real model
    from app.core.config import ARCHIVE_CHUNK_TOKENS
    from app.services.embeddings import EmbeddingAdapter

    settings = _settings()
    adapter = EmbeddingAdapter.load(batch_size=settings.milvus_batch_size)
    # Grow a neutral sentence until it reaches the chunk budget, like a full chunk.
    word = "archive capacity measurement sentence "
    text = word
    while adapter.encoder.count_tokens([text])[0] < ARCHIVE_CHUNK_TOKENS:
        text += word
    passages = [f"{i} {text}" for i in range(args.passages)]
    import torch

    if args.threads:
        torch.set_num_threads(args.threads)
    with Sampler() as sampler:
        started = time.perf_counter()
        adapter.embed(passages, kind="passage")
        seconds = time.perf_counter() - started
    return {
        **_base_record("embed"),
        "passages": len(passages),
        "tokens_per_passage": adapter.encoder.count_tokens([passages[0]])[0],
        "batch_size": settings.milvus_batch_size,
        "torch_threads": torch.get_num_threads(),
        "device": "cpu",
        "seconds": round(seconds, 2),
        "passages_per_second": round(len(passages) / seconds, 2),
        "peak_rss_mb": sampler.peak_rss_mb,
        "min_vm_available_mb": sampler.min_vm_available_mb,
    }


def bench_search(args):  # pragma: no cover - needs the real stack
    from scripts.relevance_eval import _build_service

    settings = _settings()
    token = settings.archive_github_token.strip()
    if args.mode == "hybrid" and not token:
        raise SystemExit("Set ARCHIVE_GITHUB_TOKEN in backend/.env first")
    if args.mode == "hybrid" and args.requests > args.max_github_searches:
        raise SystemExit("hybrid requests exceed --max-github-searches")
    guard = Guard(args.guard_file)
    guard.check()
    started = time.perf_counter()
    service, _ = _build_service(settings)
    load_seconds = time.perf_counter() - started
    if args.mode == "archive":
        service.github = _EmptyKeyword()
    ideas = load_ideas()

    async def cold_then_timed():
        # One event loop for both, so the service's admission semaphore stays bound.
        cold_started = time.perf_counter()
        await service.search(token, ideas[0]["idea"])
        cold = (time.perf_counter() - cold_started) * 1000
        with Sampler() as sampler:
            timed = await run_searches(
                service,
                token,
                ideas,
                requests=args.requests,
                concurrency=args.concurrency,
                guard=guard,
                pause=args.pause,
            )
        return cold, timed, sampler

    try:
        cold_ms, result, sampler = asyncio.run(cold_then_timed())
    finally:
        service.close()
    return {
        **_base_record("search"),
        "mode": args.mode,
        "label": args.label,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "admission_limit": settings.hybrid_search_max_concurrent,
        "service_load_seconds": round(load_seconds, 2),
        "first_request_ms": round(cold_ms, 1),
        **result,
        "peak_rss_mb": sampler.peak_rss_mb,
        "min_vm_available_mb": sampler.min_vm_available_mb,
        "min_host_available_mb": guard.min_host_mb,
    }


def _tree_mb(path):
    path = Path(path)
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = [p for p in path.rglob("*") if p.is_file()]
    else:
        return None
    return round(sum(p.stat().st_size for p in files) / 2**20, 1)


def bench_disk(args):  # pragma: no cover - needs the real archive
    from app.services.hybrid_runtime import archive_counts

    settings = _settings()
    database = settings.archive_database_path
    return {
        **_base_record("disk"),
        "catalogue_mb": sum(
            _tree_mb(p) or 0 for p in database.parent.glob(database.name + "*")
        ),
        "content_mb": _tree_mb(settings.archive_content_path),
        "backup_repository_mb": _tree_mb(settings.archive_backup_repository)
        if settings.archive_backup_repository
        else None,
        "repositories": archive_counts(database).get("repositories"),
    }


def main(argv=None):  # pragma: no cover - thin argument wrapper
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--out", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    embed = commands.add_parser("embed")
    embed.add_argument("--passages", type=int, default=256)
    embed.add_argument("--threads", type=int, default=0)
    search = commands.add_parser("search")
    search.add_argument("--mode", choices=["archive", "hybrid"], required=True)
    search.add_argument("--requests", type=int, required=True)
    search.add_argument("--concurrency", type=int, default=1)
    search.add_argument("--pause", type=float, default=0.0)
    search.add_argument("--label", default="")
    search.add_argument("--max-github-searches", type=int, default=60)
    search.add_argument("--guard-file", default="")
    commands.add_parser("disk")
    args = parser.parse_args(argv)
    record = {"embed": bench_embed, "search": bench_search, "disk": bench_disk}[
        args.command
    ](args)
    with Path(args.out).open("a", encoding="utf-8") as out:
        out.write(json.dumps(record, sort_keys=True) + "\n")
    print(json.dumps(record, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
