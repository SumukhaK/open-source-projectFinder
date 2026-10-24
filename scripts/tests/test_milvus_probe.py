import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

from scripts.milvus_probe import run_probe, validate_settings, vectors, wal_is_fixed


def test_vectors_are_reproducible_normalized_and_bounded():
    rows = vectors(4)
    assert rows == vectors(4)
    assert [row["id"] for row in rows] == [0, 1, 2, 3]
    assert [row["cohort"] for row in rows] == [0, 1, 0, 1]
    for row in rows:
        assert len(row["vector"]) == 384
        assert math.isclose(sum(x * x for x in row["vector"]), 1, abs_tol=1e-6)
    assert rows[0]["vector"] != rows[1]["vector"]
    for count in (0, 1001, -1):
        with pytest.raises(ValueError):
            vectors(count)


@pytest.mark.parametrize(
    "uri,token,profile",
    [
        ("http://example.com:19530", "root:private", "cpu"),
        ("http://127.0.0.1:19530/path", "root:private", "cpu"),
        ("http://user:password@127.0.0.1:19530", "root:private", "cpu"),
        ("http://127.0.0.1:19530", "root:Milvus", "cpu"),
        ("http://127.0.0.1:19530", "", "cpu"),
        ("http://127.0.0.1:19530", "root:private", "unknown"),
    ],
)
def test_probe_rejects_remote_or_default_credentials(uri, token, profile):
    with pytest.raises(ValueError):
        validate_settings(uri, token, profile)


def test_probe_accepts_explicit_local_authenticated_settings():
    validate_settings("http://127.0.0.1:19530", "root:private-password", "gpu")


@pytest.mark.parametrize(
    "version,fixed",
    [
        ("3.46.1", False),
        ("3.51.2", False),
        ("3.51.3", True),
        ("3.50.7", True),
        ("3.50.6", False),
        ("3.44.6", True),
        ("3.45.1", False),
        ("3.52.0", True),
    ],
)
def test_sqlite_gate_requires_a_documented_fixed_release(version, fixed):
    assert wal_is_fixed(version) is fixed


def client_fixture():
    client = MagicMock()
    client.insert.return_value = {"insert_count": 1000}
    client.get_server_version.return_value = "2.6.26"
    client.describe_index.return_value = {"index_type": "HNSW", "metric_type": "IP"}
    client.search.side_effect = [
        [[{"id": 0, "distance": 1.0, "entity": {"cohort": 0}}]],
        [[{"id": 1, "distance": 0.2, "entity": {"cohort": 1}}]],
    ]
    client.get.side_effect = [[{"id": 0, "cohort": 2}], []]
    return client


DATATYPE = SimpleNamespace(INT64=5, FLOAT_VECTOR=101)


def test_probe_checks_results_and_drops_only_its_own_collection():
    client = client_fixture()
    result = run_probe(client, DATATYPE, "cpu")
    assert result["index_type"] == "HNSW"
    assert result["rows"] == 1000
    assert result["operations"] == [
        "insert",
        "build",
        "load",
        "search",
        "filter",
        "upsert",
        "delete",
    ]
    name = client.create_collection.call_args.kwargs["collection_name"]
    assert name.startswith("reporadar_t01_cpu_")
    client.drop_collection.assert_called_once_with(collection_name=name, timeout=30)
    client.close.assert_called_once()
    assert client.search.call_count == 2
    assert client.upsert.call_count == 1
    assert client.delete.call_count == 1


@pytest.mark.parametrize("failure", ["filter", "upsert", "delete", "index"])
def test_probe_fails_instead_of_claiming_unsupported_operations(failure):
    client = client_fixture()
    if failure == "filter":
        client.search.side_effect = [
            [[{"id": 0, "distance": 1.0, "entity": {"cohort": 0}}]],
            [[{"id": 0, "distance": 1.0, "entity": {"cohort": 0}}]],
        ]
    elif failure == "upsert":
        client.get.side_effect = [[{"id": 0, "cohort": 0}], []]
    elif failure == "delete":
        client.get.side_effect = [[{"id": 0, "cohort": 2}], [{"id": 0}]]
    else:
        client.describe_index.return_value = {
            "index_type": "GPU_CAGRA",
            "metric_type": "IP",
        }
    with pytest.raises(ValueError):
        run_probe(client, DATATYPE, "cpu")
    client.drop_collection.assert_called_once()
    client.close.assert_called_once()


def test_failed_creation_does_not_drop_an_existing_collection():
    client = client_fixture()
    client.create_collection.side_effect = RuntimeError("creation failed")
    with pytest.raises(RuntimeError, match="creation failed"):
        run_probe(client, DATATYPE, "cpu")
    client.drop_collection.assert_not_called()
    client.close.assert_called_once()


def test_probe_rejects_incomplete_insertion():
    client = client_fixture()
    client.insert.return_value = {"insert_count": 999}
    with pytest.raises(ValueError, match="insert"):
        run_probe(client, DATATYPE, "cpu")
    client.drop_collection.assert_called_once()


def test_gpu_profile_requires_gpu_index_without_cpu_fallback():
    client = client_fixture()
    client.describe_index.return_value = {
        "index_type": "GPU_CAGRA",
        "metric_type": "IP",
    }
    result = run_probe(client, DATATYPE, "gpu")
    assert result["index_type"] == "GPU_CAGRA"
    params = client.prepare_index_params.return_value.add_index.call_args.kwargs
    assert params["index_type"] == "GPU_CAGRA"
    assert params["metric_type"] == "IP"


def test_probe_rejects_wrong_server_and_always_closes_client():
    client = client_fixture()
    client.get_server_version.return_value = "3.0.0"
    with pytest.raises(ValueError, match="Server"):
        run_probe(client, DATATYPE, "cpu")
    client.drop_collection.assert_not_called()
    client.close.assert_called_once()


def test_release_image_may_report_its_26_build_identifier():
    client = client_fixture()
    client.get_server_version.return_value = "2.6-20261023-b8d2ca4240"
    result = run_probe(client, DATATYPE, "cpu")
    assert result["server"] == "2.6-20261023-b8d2ca4240"


def test_compose_is_authenticated_private_pinned_and_resource_bounded():
    path = Path(__file__).resolve().parents[2] / "infra/milvus/compose.yaml"
    services = yaml.safe_load(path.read_text())["services"]
    for service in services.values():
        assert "@sha256:" in service["image"]
        assert service["mem_limit"]
        assert service["cpus"]
        assert service["logging"]["options"]["max-size"]
        assert not service.get("privileged")
        assert "docker.sock" not in str(service)
    for profile in ("cpu", "gpu"):
        service = services[profile]
        assert service["profiles"] == [profile]
        assert service["ports"] == ["127.0.0.1:19530:19530"]
        env = service["environment"]
        assert env["COMMON_SECURITY_AUTHORIZATIONENABLED"] == "true"
        assert env["COMMON_SECURITY_DEFAULTROOTPASSWORD"].startswith(
            "${MILVUS_PASSWORD:?"
        )
        assert env["MINIO_SECRETACCESSKEY"].startswith("${MINIO_PASSWORD:?")
        assert env["ETCD_ROOTPATH"].endswith(profile)
        assert env["MINIO_BUCKETNAME"].endswith(profile)
    assert "ports" not in services["etcd"]
    assert "ports" not in services["minio"]
    assert services["gpu"]["deploy"]["resources"]["reservations"]["devices"] == [
        {"driver": "nvidia", "capabilities": ["gpu"], "device_ids": ["0"]}
    ]
