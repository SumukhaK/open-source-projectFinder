"""Disposable 1k-vector CPU/GPU proof, never an application ingestion command."""

import argparse
import json
import math
import os
import random
import time
import uuid
from urllib.parse import urlsplit


def vectors(count=1000):
    if not 1 <= count <= 1000:
        raise ValueError("Synthetic row count must be 1..1000")
    rng = random.Random(17)
    rows = []
    for index in range(count):
        vector = [rng.uniform(-1, 1) for _ in range(384)]
        norm = math.sqrt(sum(value * value for value in vector))
        rows.append(
            {"id": index, "cohort": index % 2, "vector": [v / norm for v in vector]}
        )
    return rows


def validate_settings(uri, token, profile):
    address = urlsplit(uri)
    if (
        address.scheme != "http"
        or address.hostname != "127.0.0.1"
        or not address.port
        or address.username is not None
        or address.path not in ("", "/")
        or address.query
        or address.fragment
    ):
        raise ValueError("Probe requires an explicit loopback HTTP endpoint")
    user, _, password = token.partition(":")
    if (
        user != "root"
        or len(password) < 16
        or password.lower() in ("milvus", "replace_me")
    ):
        raise ValueError(
            "Set a non-default root token with a password of at least 16 characters"
        )
    if profile not in ("cpu", "gpu"):
        raise ValueError("Choose cpu or gpu")


def wal_is_fixed(version):
    current = tuple(int(part) for part in version.split("."))
    return (
        current >= (3, 51, 3)
        or (current[:2] == (3, 50) and current >= (3, 50, 7))
        or (current[:2] == (3, 44) and current >= (3, 44, 6))
    )


def run_probe(client, datatype, profile):
    name = f"reporadar_t01_{profile}_{uuid.uuid4().hex}"
    created = False
    index_type = {"cpu": "HNSW", "gpu": "GPU_CAGRA"}[profile]
    timings = {}
    started = time.perf_counter()
    try:
        server = client.get_server_version(timeout=30)
        if not server.startswith(("2.6.", "2.6-")):
            raise ValueError("Server is not in the pinned Milvus 2.6 family")
        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(field_name="id", datatype=datatype.INT64, is_primary=True)
        schema.add_field(field_name="cohort", datatype=datatype.INT64)
        schema.add_field(field_name="vector", datatype=datatype.FLOAT_VECTOR, dim=384)
        client.create_collection(
            collection_name=name, schema=schema, consistency_level="Strong", timeout=30
        )
        created = True
        rows = vectors()
        stage = time.perf_counter()
        inserted = client.insert(collection_name=name, data=rows, timeout=30)
        if inserted.get("insert_count") != len(rows):
            raise ValueError("Incomplete synthetic insert")
        client.flush(collection_name=name, timeout=120)
        timings["insert_flush_seconds"] = round(time.perf_counter() - stage, 4)
        params = client.prepare_index_params()
        params.add_index(
            field_name="vector",
            index_name="vector_index",
            index_type=index_type,
            metric_type="IP",
            params={"M": 16, "efConstruction": 100}
            if profile == "cpu"
            else {
                "intermediate_graph_degree": 32,
                "graph_degree": 16,
                "build_algo": "NN_DESCENT",
            },
        )
        stage = time.perf_counter()
        client.create_index(collection_name=name, index_params=params, timeout=120)
        timings["build_seconds"] = round(time.perf_counter() - stage, 4)
        description = client.describe_index(
            collection_name=name, index_name="vector_index", timeout=30
        )
        if (
            description.get("index_type") != index_type
            or description.get("metric_type") != "IP"
        ):
            raise ValueError(
                "Requested index/metric was not created; no fallback is accepted"
            )
        stage = time.perf_counter()
        client.load_collection(collection_name=name, timeout=120)
        timings["load_seconds"] = round(time.perf_counter() - stage, 4)
        search = {
            "collection_name": name,
            "data": [rows[0]["vector"]],
            "anns_field": "vector",
            "limit": 10,
            "output_fields": ["cohort"],
            "timeout": 30,
            "search_params": {
                "metric_type": "IP",
                "params": {"ef": 64} if profile == "cpu" else {"itopk_size": 64},
            },
        }
        stage = time.perf_counter()
        hits = client.search(**search)[0]
        timings["search_seconds"] = round(time.perf_counter() - stage, 4)
        if (
            not hits
            or hits[0]["id"] != 0
            or not math.isclose(hits[0]["distance"], 1.0, abs_tol=1e-4)
        ):
            raise ValueError(
                "Normalized self-search did not return the expected result"
            )
        filtered = client.search(**search, filter="cohort == 1")[0]
        if not filtered or any(
            hit["entity"]["cohort"] != 1 or hit["id"] % 2 != 1 for hit in filtered
        ):
            raise ValueError("Scalar-filter search returned incorrect results")
        client.upsert(collection_name=name, data=[{**rows[0], "cohort": 2}], timeout=30)
        updated = client.get(
            collection_name=name, ids=[0], output_fields=["cohort"], timeout=30
        )
        if len(updated) != 1 or updated[0]["cohort"] != 2:
            raise ValueError("Upsert was not visible with Strong consistency")
        client.delete(collection_name=name, ids=[0], timeout=30)
        if client.get(
            collection_name=name, ids=[0], output_fields=["cohort"], timeout=30
        ):
            raise ValueError("Deleted row is still visible")
        return {
            "profile": profile,
            "server": server,
            "index_type": index_type,
            "metric": "IP",
            "rows": len(rows),
            "dimensions": 384,
            "seed": 17,
            "operations": [
                "insert",
                "build",
                "load",
                "search",
                "filter",
                "upsert",
                "delete",
            ],
            "timings": timings,
            "elapsed_seconds": round(time.perf_counter() - started, 4),
        }
    finally:
        try:
            # Creation succeeded in this invocation; never delete an operator-selected collection.
            if created:
                client.drop_collection(collection_name=name, timeout=30)
        finally:
            client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["cpu", "gpu"], required=True)
    args = parser.parse_args()
    uri = os.environ.get("MILVUS_URI", "http://127.0.0.1:19530")
    token = os.environ.get("MILVUS_TOKEN", "")
    try:
        validate_settings(uri, token, args.profile)
        # Keep unit tests and ordinary application startup independent of the probe SDK/server.
        from pymilvus import DataType, MilvusClient, __version__

        client = MilvusClient(uri=uri, token=token, timeout=30)
        result = run_probe(client, DataType, args.profile)
        print(json.dumps({**result, "sdk": __version__}))
    except Exception as error:
        # SDK errors may contain endpoints/credentials; print only the failure class.
        raise SystemExit(
            f"Probe failed ({type(error).__name__}); inspect private operator logs"
        ) from None


if __name__ == "__main__":
    main()
