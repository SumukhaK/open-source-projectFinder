"""Opt-in real server proof; no repository or user data is ingested."""

import json
import math
import os
import random
import time
import uuid
from dataclasses import replace

import pytest
from app.core.config import Settings
from app.integrations.milvus import (
    MilvusAdapter,
    MilvusContractError,
    ScalarFilters,
    VectorChunk,
)
from app.services.embeddings import ModelManifest
from pymilvus import __version__

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MILVUS_INTEGRATION") != "1",
    reason="Opt-in synthetic proof needs the private pinned Milvus server",
)


def test_real_selected_collection_round_trip():
    name = "reporadar_t07_" + uuid.uuid4().hex
    settings = Settings(_env_file=None, milvus_collection=name, milvus_timeout=30)
    manifest = ModelManifest.load()
    adapter = MilvusAdapter.connect(settings, manifest)
    client = adapter.client
    owned = not client.has_collection(name, timeout=30)
    started = time.monotonic()
    try:
        assert owned, "Never reuse an existing collection for the disposable proof"
        adapter.ensure_collection()
        rng = random.Random(17)
        chunks = []
        for i in range(1000):
            values = [rng.uniform(-1, 1) for _ in range(384)]
            norm = math.hypot(*values)
            chunks.append(
                VectorChunk(
                    chunk_id=f"{i:064x}",
                    repo_id=i + 1,
                    revision="b" * 64,
                    model_revision=manifest.revision,
                    language="Python" if i % 2 else "C++",
                    license="MIT",
                    pushed_at=1793059200,
                    ordinal=0,
                    section="Overview",
                    snippet="Synthetic maps",
                    vector=tuple(v / norm for v in values),
                )
            )
        for start in range(0, len(chunks), 64):
            batch = chunks[start : start + 64]
            assert adapter.upsert(batch) == len(batch)
            assert adapter.ready(batch)
        client.flush(name, timeout=120)
        deadline = time.monotonic() + 120
        while True:
            index = client.describe_index(name, "vector_index", timeout=30)
            if (
                index.get("indexed_rows") == 1000
                and index.get("pending_index_rows") == 0
            ):
                break
            assert time.monotonic() < deadline, (
                "All 1,000 rows must be indexed, not a flat-scan proof"
            )
            time.sleep(0.5)
        assert index["state"] == "Finished"
        hits = adapter.search(chunks[0].vector, limit=1000)
        assert len(hits) == 1000
        assert hits[0]["chunk_id"] == chunks[0].chunk_id
        assert hits[0]["score"] == pytest.approx(1.0, abs=1e-4)
        filtered = adapter.search(
            chunks[0].vector,
            filters=ScalarFilters(
                language="Python", license="MIT", pushed_after=1793059199
            ),
        )
        assert filtered and all(
            h["language"] == "Python" and h["repo_id"] % 2 == 0 for h in filtered
        )
        assert (
            adapter.search(
                chunks[0].vector,
                filters=ScalarFilters(
                    language='Python" or repo_id > 0 or language == "'
                ),
            )
            == []
        )
        updated = replace(chunks[0], snippet="Changed synthetic maps", language="Rust")
        assert adapter.upsert([updated]) == adapter.upsert([updated]) == 1
        assert adapter.ready([updated])
        assert not adapter.ready([chunks[0]])
        assert (
            adapter.search(updated.vector, filters=ScalarFilters(repo_id=1))[0][
                "snippet"
            ]
            == updated.snippet
        )
        alias = name + "_alias"
        client.create_alias(name, alias, timeout=30)
        stale = MilvusAdapter(
            settings.model_copy(update={"milvus_collection": alias}), manifest, client
        )
        with pytest.raises(MilvusContractError):
            stale.search(chunks[0].vector)
        client.drop_alias(alias, timeout=30)
        assert adapter.delete([updated.chunk_id]) == 1
        assert not adapter.ready([updated])
        assert adapter.search(updated.vector, filters=ScalarFilters(repo_id=1)) == []
        print(
            json.dumps(
                {
                    "server": client.get_server_version(timeout=30),
                    "sdk": __version__,
                    "profile": settings.milvus_profile,
                    "generation": adapter.generation,
                    "index": index,
                    "max_top_k": 1000,
                    "consistency": "Strong",
                    "rows": 1000,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "operations": [
                        "upsert",
                        "readback",
                        "search",
                        "filter",
                        "update",
                        "replay",
                        "alias_refusal",
                        "delete",
                    ],
                }
            )
        )
    finally:
        if owned:
            client.drop_collection(name, timeout=30)
        adapter.close()
