"""HD1: keep a hosted API's SQLite state in a private Hugging Face dataset.

A free Space wipes its disk on every restart. The Space's start script runs
``restore`` before the API starts, then ``run`` beside it:

- ``restore`` downloads ``auth.sqlite3`` (logins, favourites) and
  ``catalogue.sqlite3`` (the archive catalogue the laptop worker publishes) when
  they are missing locally. It never overwrites a local file, and a failed
  download exits non-zero so the API never starts empty and then uploads that
  empty database over the good snapshot.
- ``run`` uploads a consistent copy of the auth DB every
  ``STATE_SYNC_INTERVAL_SECONDS`` when it changed. A restart can lose at most
  that interval of changes. The catalogue is read-only here: only the worker
  writes it.

This runs as its own process because the API serves with ``HF_HUB_OFFLINE=1``.
Nothing here is imported by the API, and the token is never logged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

from app.core.config import Settings

AUTH_NAME = "auth.sqlite3"
CATALOGUE_NAME = "catalogue.sqlite3"
REPO_TYPE = "dataset"


def _targets(settings: Settings) -> list[tuple[str, Path]]:
    return [
        (AUTH_NAME, Path(settings.database_path)),
        (CATALOGUE_NAME, Path(settings.archive_database_path)),
    ]


def restore(settings: Settings, hub) -> list[str]:
    """Download missing databases; return the names restored."""
    repo = settings.state_sync_repo
    if not repo:
        return []
    restored = []
    for name, target in _targets(settings):
        if target.exists() or not hub.file_exists(repo, name, repo_type=REPO_TYPE):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent) as scratch:
            downloaded = hub.hf_hub_download(
                repo, name, repo_type=REPO_TYPE, local_dir=scratch
            )
            # Same directory, so the rename is atomic: no half-written database.
            Path(downloaded).replace(target)
        restored.append(name)
    return restored


def snapshot(settings: Settings, hub, last_digest: str | None) -> str | None:
    """Upload a consistent auth DB copy if it changed; return its digest."""
    source = Path(settings.database_path)
    if not settings.state_sync_repo or not source.exists():
        return last_digest
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / AUTH_NAME
        # SQLite's online backup gives a consistent copy while the API writes.
        with closing(sqlite3.connect(source)) as live:
            with closing(sqlite3.connect(copy)) as out:
                live.backup(out)
        digest = _sha256(copy)
        if digest == last_digest:
            return digest
        hub.upload_file(
            path_or_fileobj=str(copy),
            path_in_repo=AUTH_NAME,
            repo_id=settings.state_sync_repo,
            repo_type=REPO_TYPE,
            commit_message="Snapshot auth state",
        )
    return digest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _hub(settings: Settings):
    from huggingface_hub import HfApi  # optional dependency: embeddings lock

    return HfApi(token=settings.state_sync_token.get_secret_value() or None)


def _log(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}), flush=True)


def run(settings: Settings, hub, sleep=time.sleep, rounds: int | None = None):
    digest = None
    done = 0
    while rounds is None or done < rounds:
        sleep(settings.state_sync_interval_seconds)
        try:
            digest = snapshot(settings, hub, digest)
            _log("state_sync_snapshot", ok=True)
        except Exception as error:  # keep serving; retry next interval
            _log("state_sync_snapshot", ok=False, error=type(error).__name__)
        done += 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["restore", "run"])
    args = parser.parse_args(argv)
    settings = Settings()
    if not settings.state_sync_repo:
        _log("state_sync_disabled")
        return 0
    hub = _hub(settings)
    if args.command == "restore":
        try:
            _log("state_sync_restore", restored=restore(settings, hub))
        except Exception as error:
            _log("state_sync_restore_failed", error=type(error).__name__)
            return 1
        return 0
    run(settings, hub)
    return 0


if __name__ == "__main__":
    sys.exit(main())
