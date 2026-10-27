import logging
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from app.core.config import Settings
from app.integrations.milvus import (
    MilvusAdapter,
    MilvusContractError,
    MilvusUnavailable,
    ScalarFilters,
    VectorChunk,
)
from app.services.embeddings import ModelManifest
from pydantic import ValidationError
from pymilvus import DataType, MilvusClient
from pymilvus.client.search_result import Hit
from pymilvus.client.types import LoadState
from pymilvus.exceptions import MilvusException
from pymilvus.grpc_gen import common_pb2


def settings(**changes):
    return Settings(
        _env_file=None,
        **{
            "milvus_collection": "reporadar_t07_test",
            "milvus_profile": "gpu",
            "milvus_token": "root:" + "synthetic-only-credential",
            **changes,
        },
    )


def chunk(**changes):
    return replace(
        VectorChunk(
            chunk_id="a" * 64,
            repo_id=42,
            revision="b" * 64,
            model_revision=ModelManifest.load().revision,
            language="Python",
            license="MIT",
            pushed_at=1793059200,
            ordinal=0,
            section="Overview",
            snippet="Synthetic offline maps",
            vector=(1.0,) + (0.0,) * 383,
        ),
        **changes,
    )


@pytest.fixture
def adapter():
    client = MagicMock(spec=MilvusClient)
    client.create_schema.side_effect = MilvusClient.create_schema
    client.prepare_index_params.side_effect = MilvusClient.prepare_index_params
    result = MilvusAdapter(settings(), ModelManifest.load(), client)
    # Independent server-shaped fixture, not the production schema builder.
    client.describe_collection.return_value = {
        "collection_name": "reporadar_t07_test",
        "description": "reporadar-chunks-v1:" + result.generation,
        "auto_id": False,
        "enable_dynamic_field": False,
        "consistency_level": 0,
        "fields": [
            {
                "name": name,
                "type": DataType.VARCHAR,
                "params": {"max_length": size},
                "is_primary": name == "chunk_id",
            }
            for name, size in (
                ("chunk_id", 64),
                ("revision", 64),
                ("model_revision", 40),
                ("generation", 64),
                ("language", 128),
                ("license", 128),
                ("section", 512),
                ("snippet", 2048),
            )
        ]
        + [
            {"name": name, "type": DataType.INT64, "params": {}}
            for name in ("repo_id", "pushed_at", "ordinal")
        ]
        + [{"name": "vector", "type": DataType.FLOAT_VECTOR, "params": {"dim": 384}}],
    }
    client.describe_index.return_value = {
        "field_name": "vector",
        "index_type": "GPU_CAGRA",
        "metric_type": "IP",
        "state": "Finished",
        "total_rows": 1000,
        "indexed_rows": 1000,
        "pending_index_rows": 0,
    }
    client.get_load_state.return_value = {"state": LoadState.Loaded}
    client.get_server_version.return_value = "2.6-20261023-b8d2ca4240"
    client.has_collection.return_value = True
    return result


@pytest.mark.parametrize(
    "changes",
    [
        {"milvus_timeout": 0},
        {"milvus_timeout": 31},
        {"milvus_build_timeout": 0},
        {"milvus_build_timeout": 121},
        {"milvus_batch_size": 0},
        {"milvus_batch_size": 65},
        {"milvus_profile": "auto"},
        {"milvus_collection": "name;drop"},
        {"milvus_uri": "http://example.com:19530"},
        {"milvus_uri": "local.db"},
        {"milvus_uri": "http://root:password@127.0.0.1:19530"},
    ],
)
def test_settings_refuse_unbounded_or_nonlocal_operations(changes):
    with pytest.raises(ValidationError):
        settings(**changes)


def test_token_is_not_in_settings_representation():
    assert "synthetic-only-credential" not in repr(settings())


@pytest.mark.parametrize(
    "changes",
    [
        {"dimensions": 768},
        {"revision": "c" * 40},
        {"tokenizer_sha256": "d" * 64},
        {"weights_sha256": "e" * 64},
        {"max_tokens": 1024},
    ],
)
def test_only_pinned_manifest_can_open_this_generation(changes):
    with pytest.raises(MilvusContractError):
        MilvusAdapter(settings(), replace(ModelManifest.load(), **changes), MagicMock())


@pytest.mark.parametrize(
    "field,value",
    [
        ("description", "other-model"),
        ("collection_name", "old_alias_target"),
        ("enable_dynamic_field", True),
        ("auto_id", True),
        ("consistency_level", 2),
    ],
)
def test_existing_incompatible_collection_is_never_repaired(adapter, field, value):
    adapter.client.describe_collection.return_value[field] = value
    with pytest.raises(MilvusContractError):
        adapter.ensure_collection()
    adapter.client.create_collection.assert_not_called()
    adapter.client.drop_collection.assert_not_called()


@pytest.mark.parametrize(
    "field,params", [("vector", {"dim": 768}), ("snippet", {"max_length": 65535})]
)
def test_schema_dimensions_and_scalar_bounds_are_checked(adapter, field, params):
    next(
        f
        for f in adapter.client.describe_collection.return_value["fields"]
        if f["name"] == field
    )["params"] = params
    with pytest.raises(MilvusContractError):
        adapter.ensure_collection()


@pytest.mark.parametrize(
    "field,value", [("index_type", "HNSW"), ("metric_type", "COSINE")]
)
def test_index_profile_and_metric_never_fall_back(adapter, field, value):
    adapter.client.describe_index.return_value[field] = value
    with pytest.raises(MilvusContractError):
        adapter.ensure_collection()


def test_new_collection_has_only_bounded_schema_and_selected_index(adapter):
    adapter.client.has_collection.return_value = False
    adapter.client.list_indexes.return_value = []
    adapter.ensure_collection()
    call = adapter.client.create_collection.call_args
    assert call is not None, "new collection must be created explicitly"
    schema = call.kwargs["schema"].to_dict()
    assert schema["enable_dynamic_field"] is False
    fields = {f["name"]: f for f in schema["fields"]}
    assert fields["chunk_id"]["is_primary"]
    assert fields["vector"]["params"]["dim"] == 384
    assert fields["snippet"]["params"]["max_length"] == 2048
    index = adapter.client.create_index.call_args.kwargs["index_params"][0].to_dict()
    assert index["index_type"] == "GPU_CAGRA"
    assert index["metric_type"] == "IP"


@pytest.mark.parametrize(
    "changes",
    [
        {"vector": (1.0,)},
        {"vector": (0.0,) * 384},
        {"vector": (float("nan"),) + (0.0,) * 383},
        {"vector": (float("inf"),) + (0.0,) * 383},
        {"vector": (2.0,) + (0.0,) * 383},
        {"model_revision": "0" * 40},
        {"chunk_id": 'x" or true'},
        {"repo_id": True},
        {"repo_id": 0},
        {"repo_id": 2**63},
        {"ordinal": 8},
        {"pushed_at": -1},
        {"revision": ""},
        {"snippet": "地" * 683},
        {"language": "a" * 129},
    ],
)
def test_bad_chunk_rejects_entire_batch_before_any_write(adapter, changes):
    invalid = chunk(**{"chunk_id": "c" * 64, **changes})
    with pytest.raises(MilvusContractError):
        adapter.upsert([chunk(), invalid])
    adapter.client.upsert.assert_not_called()


def test_duplicate_ids_in_one_batch_are_rejected(adapter):
    with pytest.raises(MilvusContractError):
        adapter.upsert([chunk(), chunk()])


def test_replaying_same_upsert_preserves_primary_keys(adapter):
    adapter.client.upsert.return_value = {"upsert_count": 1, "ids": ["a" * 64]}
    assert adapter.upsert([chunk()]) == 1
    assert adapter.upsert([chunk()]) == 1
    for call in adapter.client.upsert.call_args_list:
        assert call.kwargs["data"][0]["chunk_id"] == "a" * 64
        assert call.kwargs["data"][0]["generation"] == adapter.generation
    adapter.client.insert.assert_not_called()


@pytest.mark.parametrize("reply", [{"upsert_count": 0}, {"upsert_count": 1, "ids": []}])
def test_partial_batch_never_claims_publication_readiness(adapter, reply):
    adapter.client.upsert.return_value = reply
    with pytest.raises(MilvusUnavailable):
        adapter.upsert([chunk()])


def test_retryable_failure_is_sanitized_and_does_not_retry_a_batch(adapter):
    adapter.client.upsert.side_effect = TimeoutError("private-token-and-content")
    with pytest.raises(MilvusUnavailable) as caught:
        adapter.upsert([chunk()])
    assert "private-token-and-content" not in str(caught.value)
    assert adapter.client.upsert.call_count == 1


def test_bound_applies_to_whole_operation(adapter):
    with pytest.raises(MilvusContractError):
        adapter.upsert([chunk(chunk_id=f"{i:064x}") for i in range(65)])
    adapter.client.upsert.assert_not_called()


def test_readiness_requires_all_expected_revision_and_generation_rows(adapter):
    row = {**vars(chunk()), "generation": adapter.generation}
    adapter.client.get.return_value = [row]
    assert adapter.ready([chunk()]) is True
    for changed in ({"revision": "c" * 64}, {"generation": "d" * 64}, {"repo_id": 43}):
        adapter.client.get.return_value = [{**row, **changed}]
        assert adapter.ready([chunk()]) is False
    adapter.client.get.return_value = []
    assert adapter.ready([chunk()]) is False
    assert all(
        c.kwargs["consistency_level"] == "Strong"
        for c in adapter.client.get.call_args_list
    )


def test_unloaded_collection_is_unavailable_not_an_empty_search(adapter):
    adapter.client.get_load_state.return_value = {"state": LoadState.NotLoad}
    with pytest.raises(MilvusUnavailable):
        adapter.search(chunk().vector)


@pytest.mark.parametrize(
    "filters",
    [
        "repo_id > 0",
        {"filter": "true"},
        ScalarFilters(repo_id=True),
        ScalarFilters(language=""),
        ScalarFilters(pushed_after=-1),
    ],
)
def test_filters_only_accept_typed_bounded_fields(adapter, filters):
    with pytest.raises(MilvusContractError):
        adapter.search(chunk().vector, filters=filters)
    adapter.client.search.assert_not_called()


def test_filter_values_are_parameters_never_executable_expressions(adapter):
    adapter.client.search.return_value = [[]]
    value = 'Python" or repo_id > 0 or language == "'
    assert (
        adapter.search(
            chunk().vector,
            filters=ScalarFilters(language=value, license="MIT", pushed_after=123),
        )
        == []
    )
    call = adapter.client.search.call_args.kwargs
    assert value not in call["filter"]
    assert call["filter_params"]["language"] == value
    assert call["filter_params"]["generation"] == adapter.generation
    assert "pushed_at >= {pushed_after}" in call["filter"]
    assert call["consistency_level"] == "Strong"


@pytest.mark.parametrize("limit", [0, 1001, True])
def test_top_k_is_bounded(adapter, limit):
    with pytest.raises(MilvusContractError):
        adapter.search(chunk().vector, limit=limit)


def test_max_top_k_has_sufficient_cagra_candidates(adapter):
    adapter.client.search.return_value = [[]]
    assert adapter.search(chunk().vector, limit=1000) == []
    call = adapter.client.search.call_args.kwargs
    assert call["search_params"]["params"]["itopk_size"] >= 1000
    assert "vector" not in call["output_fields"]


def test_delete_accepts_only_bounded_explicit_ids(adapter):
    adapter.client.delete.return_value = {"delete_count": 1}
    assert adapter.delete(["a" * 64]) == 1
    assert adapter.client.delete.call_args.kwargs["ids"] == ["a" * 64]
    assert "filter" not in adapter.client.delete.call_args.kwargs
    for bad in ([], ["true"], ["a" * 64] * 65):
        with pytest.raises(MilvusContractError):
            adapter.delete(bad)


def test_connection_refuses_empty_or_default_credentials(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(MilvusClient, "__init__", factory)
    for token in ("", "root:Milvus", "root:short", "root:replace_me"):
        with pytest.raises(MilvusContractError):
            MilvusAdapter.connect(settings(milvus_token=token), ModelManifest.load())
    factory.assert_not_called()


def test_connect_and_close_use_bounded_private_client(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr("app.integrations.milvus.MilvusClient", factory)
    result = MilvusAdapter.connect(settings(), ModelManifest.load())
    assert factory.call_args.kwargs["uri"] == "http://127.0.0.1:19530"
    assert factory.call_args.kwargs["timeout"] <= 30
    result.close()
    factory.return_value.close.assert_called_once()


def test_sdk_diagnostics_do_not_log_private_payloads(adapter, caplog):
    def fail(**kwargs):
        logging.getLogger("pymilvus.decorators").error(
            "raw %s", "private-token-and-content", exc_info=True
        )
        raise MilvusException(message="private-token-and-content")

    adapter.client.upsert.side_effect = fail
    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError):
        adapter.upsert([chunk()])
    assert "private-token-and-content" not in caplog.text


def test_incomplete_index_is_not_ready(adapter):
    adapter.client.describe_index.return_value["state"] = "InProgress"
    adapter.client.get.return_value = [
        {**vars(chunk()), "generation": adapter.generation}
    ]
    with pytest.raises(MilvusUnavailable):
        adapter.ready([chunk()])


def test_valid_search_returns_bounded_chunk_evidence(adapter):
    adapter.client.search.return_value = [
        [
            {
                "chunk_id": "a" * 64,
                "distance": 1.0,
                "entity": {**vars(chunk()), "generation": adapter.generation},
            }
        ]
    ]
    hits = adapter.search(chunk().vector)
    assert hits[0]["repo_id"] == 42
    assert hits[0]["score"] == 1.0
    assert "vector" not in hits[0]


def test_sdk_uses_custom_primary_key_outside_entity(adapter):
    entity = {**vars(chunk()), "generation": adapter.generation}
    entity.pop("chunk_id")
    adapter.client.search.return_value = [
        [
            Hit(
                {"chunk_id": "a" * 64, "distance": 1.0, "entity": entity},
                pk_name="chunk_id",
            )
        ]
    ]
    assert adapter.search(chunk().vector)[0]["chunk_id"] == "a" * 64


def test_incompatible_server_is_rejected_without_creating(adapter):
    adapter.client.get_server_version.return_value = "3.0.0"
    with pytest.raises(MilvusContractError):
        adapter.ensure_collection()
    adapter.client.create_collection.assert_not_called()


@pytest.mark.parametrize("bad", [[], [[{"id": "bad", "distance": 1, "entity": {}}]]])
def test_malformed_search_fails_clearly(adapter, bad):
    adapter.client.search.return_value = bad
    with pytest.raises(MilvusContractError):
        adapter.search(chunk().vector)


def test_cpu_profile_is_explicit_and_uses_same_metric(adapter):
    cpu = MilvusAdapter(
        settings(milvus_profile="cpu"), ModelManifest.load(), adapter.client
    )
    cpu.client.describe_index.return_value["index_type"] = "HNSW"
    cpu.client.search.return_value = [[]]
    assert cpu.search(chunk().vector, limit=1000) == []
    assert cpu.client.search.call_args.kwargs["search_params"] == {
        "metric_type": "IP",
        "params": {"ef": 1000},
    }


def test_expired_budget_never_calls_sdk(adapter, monkeypatch):
    clock = iter([10, 21])
    monkeypatch.setattr("app.integrations.milvus.time.monotonic", lambda: next(clock))
    with pytest.raises(MilvusUnavailable):
        adapter.delete(["a" * 64])
    adapter.client.delete.assert_not_called()


def test_sdk_late_success_is_unavailable_not_success(adapter, monkeypatch):
    now = [10.0]
    monkeypatch.setattr("app.integrations.milvus.time.monotonic", lambda: now[0])

    def slow_delete(**kwargs):
        now[0] = 21.0
        return {"delete_count": 1}

    adapter.client.delete.side_effect = slow_delete
    with pytest.raises(MilvusUnavailable):
        adapter.delete(["a" * 64])


def test_sdk_legacy_rate_limit_remains_retryable(adapter):
    adapter.client.upsert.side_effect = MilvusException(
        code=0, message="private provider text", compatible_code=common_pb2.RateLimit
    )
    with pytest.raises(MilvusUnavailable):
        adapter.upsert([chunk()])
