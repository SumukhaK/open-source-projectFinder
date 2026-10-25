"""Real CPU smoke check and small benchmark for the pinned E5 adapter.

Loads intfloat/multilingual-e5-small from a verified local snapshot with
trust_remote_code disabled, then checks query/passage dimensions, norms and the
512-token boundary. Run once with ``--download`` to fetch the pinned revision;
without that flag the script is offline-only. This is never part of the unit
suite and is never imported by the API.
"""

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

SAMPLE_QUERIES = (
    "find an open source project that tracks personal finances",
    "एक परियोजना जो मौसम का पूर्वानुमान दिखाती है",
    "画像を整理するツールを探しています",
)
SAMPLE_PASSAGES = (
    "A command line tool that imports bank statements and builds a monthly budget.",
    "A web application that tracks expenses across several currencies.",
    "A mobile app that reminds users when recurring bills are due.",
    "A self-hosted service that forecasts rain from public weather data.",
    "मौसम पूर्वानुमान दिखाने वाला एक स्थानीय वेब अनुप्रयोग।",
    "एक उपकरण जो बजट और बचत को एक साथ प्रबंधित करता है।",
    "画像を整理し、重複を検出するデスクトップアプリ。",
    "写真のメタデータを検索できる小さなコマンドラインツール。",
    "A library that exports personal finance reports as CSV files.",
    "A dashboard that compares household spending month over month.",
    "A plugin that downloads public weather alerts and sends summaries.",
    "A script that renames image files from their creation date.",
)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def process_memory_mb():
    """Return (current, peak) resident set size in MiB for this process."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.K32GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        kernel32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
        if not kernel32.K32GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            raise OSError("GetProcessMemoryInfo failed")
        return (
            counters.WorkingSetSize / (1024 * 1024),
            counters.PeakWorkingSetSize / (1024 * 1024),
        )
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KiB; macOS reports bytes.
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return peak / divisor, peak / divisor


def vector_summary(vectors, expected, dimensions):
    if len(vectors) != expected:
        raise SystemExit(f"Expected {expected} vectors, got {len(vectors)}")
    norms = []
    for vector in vectors:
        if len(vector) != dimensions:
            raise SystemExit(f"Expected {dimensions} dimensions, got {len(vector)}")
        if not all(math.isfinite(value) for value in vector):
            raise SystemExit("Model returned a non-finite vector")
        norm = math.sqrt(math.fsum(value * value for value in vector))
        if not math.isclose(norm, 1.0, abs_tol=1e-5):
            raise SystemExit(f"Model returned an unnormalized vector (norm {norm})")
        norms.append(norm)
    return {
        "count": len(vectors),
        "dimensions": dimensions,
        "finite": True,
        "min_norm": round(min(norms), 8),
        "max_norm": round(max(norms), 8),
    }


def timed(call, repeats):
    seconds = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = call()
        seconds.append(round(time.perf_counter() - started, 4))
    return result, seconds


def run(repeats, download=False):
    backend = Path(__file__).resolve().parents[1] / "backend"
    sys.path.insert(0, str(backend))
    import huggingface_hub
    import numpy
    import safetensors
    import scipy
    import sentence_transformers
    import sklearn
    import tokenizers
    import torch
    import transformers
    from app.services.embeddings import (
        EmbeddingAdapter,
        ModelManifest,
        UnsupportedInput,
    )

    manifest = ModelManifest.load()
    # Only this explicit setup path may download. Serving loads the cached snapshot.
    try:
        snapshot = huggingface_hub.snapshot_download(
            repo_id=manifest.name,
            revision=manifest.revision,
            local_files_only=not download,
            # Fetch only safe weights and the configuration/tokenizer files they need.
            allow_patterns=manifest.snapshot_files,
        )
    except Exception as error:
        raise SystemExit(
            "Pinned embedding model is not cached. Run this command once with "
            "network access: python scripts/embeddings_smoke.py --download"
        ) from error

    # Verify the cached bytes, not just the requested revision name.
    weights_sha256 = sha256_file(Path(snapshot) / manifest.weights_file)
    tokenizer_sha256 = sha256_file(Path(snapshot) / manifest.tokenizer_file)
    if (
        weights_sha256 != manifest.weights_sha256
        or tokenizer_sha256 != manifest.tokenizer_sha256
    ):
        raise SystemExit("Cached model files do not match the pinned manifest")

    rss_before, _ = process_memory_mb()
    started = time.perf_counter()
    adapter = EmbeddingAdapter.load()
    load_seconds = time.perf_counter() - started
    rss_loaded, _ = process_memory_mb()

    queries, query_seconds = timed(
        lambda: adapter.embed(list(SAMPLE_QUERIES), kind="query"), repeats
    )
    passages, passage_seconds = timed(
        lambda: adapter.embed(list(SAMPLE_PASSAGES), kind="passage"), repeats
    )
    rss_after, peak = process_memory_mb()

    try:
        adapter.embed(["query: caller supplied prefix"], kind="query")
    except UnsupportedInput:
        pass
    else:
        raise SystemExit("Caller-supplied prefix was not rejected")

    try:
        adapter.embed(["repository search " * 200], kind="query")
    except UnsupportedInput as error:
        overflow_rejected = str(manifest.max_tokens) in str(error)
    else:
        raise SystemExit("Over-budget input was not rejected")
    if not overflow_rejected:
        raise SystemExit("Overflow error did not name the token limit")

    return {
        "model": {
            "name": manifest.name,
            "revision": manifest.revision,
            "license": manifest.license,
            "dimensions": manifest.dimensions,
            "max_tokens": manifest.max_tokens,
        },
        "weights": {
            "file": manifest.weights_file,
            "sha256": weights_sha256,
            "verified": True,
        },
        "tokenizer": {
            "file": manifest.tokenizer_file,
            "sha256": tokenizer_sha256,
            "verified": True,
        },
        "runtime": {
            "device": "cpu",
            "trust_remote_code": False,
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "sentence_transformers": sentence_transformers.__version__,
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "tokenizers": tokenizers.__version__,
            "safetensors": safetensors.__version__,
            "huggingface_hub": huggingface_hub.__version__,
            "numpy": numpy.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "load_seconds": round(load_seconds, 3),
        "queries": {
            "seconds": query_seconds,
            "vectors_per_second": round(len(queries) / min(query_seconds), 2),
            "vectors": vector_summary(
                queries, len(SAMPLE_QUERIES), manifest.dimensions
            ),
        },
        "passages": {
            "seconds": passage_seconds,
            "vectors_per_second": round(len(passages) / min(passage_seconds), 2),
            "vectors": vector_summary(
                passages, len(SAMPLE_PASSAGES), manifest.dimensions
            ),
        },
        "memory_mb": {
            "before_load": round(rss_before, 1),
            "after_load": round(rss_loaded, 1),
            "after_encoding": round(rss_after, 1),
            "peak": round(peak, 1),
        },
        "checks": {
            "caller_prefix_rejected": True,
            "overflow_rejected": True,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--download",
        action="store_true",
        help="download the pinned revision once with network access, then verify it",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5:
        raise SystemExit("--repeats must be between 1 and 5")
    try:
        result = run(args.repeats, download=args.download)
    except Exception as error:
        raise SystemExit(
            f"Embedding smoke check failed ({type(error).__name__})"
        ) from None
    payload = json.dumps(result, indent=2)
    print(payload)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
