"""Bounded collection adapter; publication and API orchestration belong to callers."""

import hashlib
import json
import logging
import math
import re
import time
from dataclasses import asdict, dataclass, field

from app.core.config import MILVUS_MAX_TOP_K, MILVUS_TEXT_BYTES, Settings
from app.services.embeddings import PREFIXES, ModelManifest
from grpc import RpcError, StatusCode
from pymilvus import DataType, MilvusClient
from pymilvus.client.types import LoadState
from pymilvus.exceptions import ErrorCode, MilvusException
from pymilvus.grpc_gen import common_pb2


class MilvusContractError(ValueError):
    """The selected collection or input violates the embedding contract."""


class MilvusUnavailable(RuntimeError):
    """The operation can be retried using the same stable IDs."""


class MilvusOperationError(RuntimeError):
    """A sanitized non-retryable SDK failure; operator investigation is needed."""


@dataclass(frozen=True)
class VectorChunk:
    chunk_id: str
    repo_id: int
    revision: str
    model_revision: str
    language: str
    license: str
    pushed_at: int
    ordinal: int
    section: str
    snippet: str = field(repr=False)
    vector: tuple[float, ...] = field(repr=False)


@dataclass(frozen=True)
class ScalarFilters:
    language: str | None = None
    license: str | None = None
    pushed_after: int | None = None
    repo_id: int | None = None


class _SafeSDKLog(logging.Filter):
    def filter(self, record):
        # SDK exception messages may embed request contents; retain only event/level.
        record.msg = "Milvus SDK event (details suppressed)"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def _sanitize_sdk_logs():
    for name in (
        "pymilvus.decorators",
        "pymilvus.client.grpc_handler",
        "pymilvus.client.connection_manager",
        "pymilvus.milvus_client.milvus_client",
    ):
        logger = logging.getLogger(name)
        if not any(isinstance(f, _SafeSDKLog) for f in logger.filters):
            logger.addFilter(_SafeSDKLog())


class MilvusAdapter:
    @classmethod
    def connect(cls, settings, manifest):
        result = cls(settings, manifest, None)
        user, _, password = settings.milvus_token.get_secret_value().partition(":")
        if (
            not user
            or len(password) < 16
            or password.lower() in ("milvus", "replace_me")
        ):
            raise MilvusContractError("Configure a non-default Milvus token")
        try:
            result.client = MilvusClient(
                uri=settings.milvus_uri,
                token=settings.milvus_token.get_secret_value(),
                timeout=settings.milvus_timeout,
            )
        except (MilvusException, RpcError, TimeoutError, ConnectionError):
            raise MilvusUnavailable("Could not connect to local Milvus") from None
        return result

    def close(self):
        self.client.close()

    def __init__(self, settings: Settings, manifest: ModelManifest, client):
        if manifest != ModelManifest.load():
            raise MilvusContractError("This collection requires the pinned E5 manifest")
        _sanitize_sdk_logs()
        self.settings = settings
        self.manifest = manifest
        self.client = client
        contract = [
            asdict(manifest),
            PREFIXES,
            "unit-norm/IP",
            "chunks-v1",
            MILVUS_TEXT_BYTES,
        ]
        self.generation = hashlib.sha256(
            json.dumps(contract, sort_keys=True).encode()
        ).hexdigest()
        self.index_type = {"cpu": "HNSW", "gpu": "GPU_CAGRA"}[settings.milvus_profile]

    def _call(self, deadline, operation, **kwargs):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MilvusUnavailable("Milvus operation deadline exhausted")
        try:
            result = getattr(self.client, operation)(
                collection_name=self.settings.milvus_collection,
                timeout=remaining,
                **kwargs,
            )
        except (MilvusException, RpcError, TimeoutError, ConnectionError) as error:
            code = (
                error.code()
                if isinstance(error, RpcError)
                else getattr(error, "code", None)
            )
            if (
                isinstance(error, (TimeoutError, ConnectionError))
                or code
                in (
                    StatusCode.UNAVAILABLE,
                    StatusCode.DEADLINE_EXCEEDED,
                    StatusCode.RESOURCE_EXHAUSTED,
                    ErrorCode.RATE_LIMIT,
                )
                or getattr(error, "compatible_code", None) == common_pb2.RateLimit
            ):
                raise MilvusUnavailable(
                    "Milvus operation unavailable; retry stable IDs"
                ) from None
            raise MilvusOperationError("Milvus operation failed") from None
        # The synchronous SDK may retry past its timeout; never accept a late success.
        if time.monotonic() > deadline:
            raise MilvusUnavailable("Milvus operation deadline exhausted")
        return result

    def _schema(self):
        schema = MilvusClient.create_schema(
            auto_id=False,
            enable_dynamic_field=False,
            description="reporadar-chunks-v1:" + self.generation,
        )
        for name, size in MILVUS_TEXT_BYTES.items():
            schema.add_field(
                name, DataType.VARCHAR, max_length=size, is_primary=name == "chunk_id"
            )
        for name in ("repo_id", "pushed_at", "ordinal"):
            schema.add_field(name, DataType.INT64)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=384)
        return schema

    def _check_collection(self, deadline):
        info = self._call(deadline, "describe_collection")
        expected = self._schema().to_dict()
        fields = {f["name"]: f for f in info["fields"]}
        if (
            info.get("collection_name") != self.settings.milvus_collection
            or info.get("description") != expected["description"]
            or info.get("auto_id") is not False
            or info.get("enable_dynamic_field") is not False
            or info.get("consistency_level") != 0
            or set(fields) != {f["name"] for f in expected["fields"]}
        ):
            raise MilvusContractError(
                "Collection generation/schema mismatch or stale alias"
            )
        for spec in expected["fields"]:
            actual = fields[spec["name"]]
            if (
                actual["type"] != spec["type"]
                or actual.get("params", {}) != spec.get("params", {})
                or bool(actual.get("is_primary")) != bool(spec.get("is_primary"))
            ):
                raise MilvusContractError("Collection field/dimension mismatch")

    def _check_index(self, deadline):
        info = self._call(deadline, "describe_index", index_name="vector_index")
        if (
            info.get("field_name") != "vector"
            or info.get("index_type") != self.index_type
            or info.get("metric_type") != "IP"
        ):
            raise MilvusContractError("Milvus index/profile/metric mismatch")
        return info

    def _check_loaded(self, deadline):
        self._check_collection(deadline)
        if self._check_index(deadline).get("state") != "Finished":
            raise MilvusUnavailable("Milvus index is not finished")
        if self._call(deadline, "get_load_state").get("state") != LoadState.Loaded:
            raise MilvusUnavailable("Milvus collection is not loaded")

    def ensure_collection(self):
        """Explicit worker setup; never drop, replace, or redirect an existing collection."""
        deadline = time.monotonic() + self.settings.milvus_build_timeout
        if not self._call(deadline, "get_server_version").startswith(("2.6.", "2.6-")):
            raise MilvusContractError("Milvus server must match the pinned 2.6 family")
        if not self._call(deadline, "has_collection"):
            self._call(
                deadline,
                "create_collection",
                schema=self._schema(),
                consistency_level="Strong",
            )
        self._check_collection(deadline)
        if "vector_index" not in self._call(deadline, "list_indexes"):
            params = MilvusClient.prepare_index_params()
            params.add_index(
                field_name="vector",
                index_name="vector_index",
                index_type=self.index_type,
                metric_type="IP",
                params={"M": 16, "efConstruction": 100}
                if self.settings.milvus_profile == "cpu"
                else {
                    "intermediate_graph_degree": 32,
                    "graph_degree": 16,
                    "build_algo": "NN_DESCENT",
                },
            )
            self._call(deadline, "create_index", index_params=params)
        self._check_index(deadline)
        self._call(deadline, "load_collection")
        self._check_loaded(deadline)

    def _rows(self, chunks):
        self._batch(chunks)
        rows = []
        for chunk in chunks:
            if not isinstance(chunk, VectorChunk):
                raise MilvusContractError("Upsert requires VectorChunk records")
            row = asdict(chunk)
            _metadata(row, self.manifest)
            _vector(row["vector"])
            rows.append({**row, "generation": self.generation})
        if len({row["chunk_id"] for row in rows}) != len(rows):
            raise MilvusContractError("Duplicate chunk IDs within one batch")
        return rows

    def _batch(self, items):
        if (
            not isinstance(items, (tuple, list))
            or not 1 <= len(items) <= self.settings.milvus_batch_size
        ):
            raise MilvusContractError(
                "Batch must be non-empty and within the configured limit"
            )

    def upsert(self, chunks):
        rows = self._rows(chunks)
        deadline = time.monotonic() + self.settings.milvus_timeout
        self._check_collection(deadline)
        self._check_index(deadline)
        result = self._call(deadline, "upsert", data=rows)
        if result.get("upsert_count") != len(rows) or set(result.get("ids", [])) != {
            row["chunk_id"] for row in rows
        }:
            raise MilvusUnavailable(
                "Partial Milvus upsert; retry the complete stable-ID batch"
            )
        return len(rows)

    def ready(self, chunks):
        """Strong read-back, not SQL activation or a claim that every row is indexed."""
        rows = self._rows(chunks)
        deadline = time.monotonic() + self.settings.milvus_timeout
        self._check_loaded(deadline)
        actual = self._call(
            deadline,
            "get",
            ids=[r["chunk_id"] for r in rows],
            output_fields=list(rows[0]),
            consistency_level="Strong",
        )
        found = {row["chunk_id"]: row for row in actual}
        if len(actual) != len(rows) or set(found) != {r["chunk_id"] for r in rows}:
            return False
        for expected in rows:
            value = found[expected["chunk_id"]]
            if any(value.get(k) != v for k, v in expected.items() if k != "vector"):
                return False
            vector = value.get("vector", [])
            if len(vector) != 384 or not all(
                math.isclose(a, b, rel_tol=1e-5, abs_tol=1e-7)
                for a, b in zip(vector, expected["vector"], strict=True)
            ):
                return False
        return True

    def search(self, vector, *, limit=200, filters=None):
        _vector(vector)
        _integer(limit, 1, MILVUS_MAX_TOP_K)
        filters = ScalarFilters() if filters is None else filters
        if not isinstance(filters, ScalarFilters):
            raise MilvusContractError("Search requires typed ScalarFilters")
        clauses = ["generation == {generation}"]
        parameters = {"generation": self.generation}
        for name, value in asdict(filters).items():
            if value is None:
                continue
            if name in ("language", "license"):
                _text(value, MILVUS_TEXT_BYTES[name], empty=False)
            else:
                _integer(value, 1 if name == "repo_id" else 0, 2**63 - 1)
            clauses.append(
                "pushed_at >= {pushed_after}"
                if name == "pushed_after"
                else f"{name} == {{{name}}}"
            )
            parameters[name] = value
        deadline = time.monotonic() + self.settings.milvus_timeout
        self._check_loaded(deadline)
        fields = list(MILVUS_TEXT_BYTES) + ["repo_id", "pushed_at", "ordinal"]
        hits = self._call(
            deadline,
            "search",
            data=[list(vector)],
            anns_field="vector",
            limit=limit,
            filter=" and ".join(clauses),
            filter_params=parameters,
            output_fields=fields,
            consistency_level="Strong",
            search_params={
                "metric_type": "IP",
                "params": {"ef": max(64, limit)}
                if self.settings.milvus_profile == "cpu"
                else {"itopk_size": max(64, 1 << (limit - 1).bit_length())},
            },
        )
        if len(hits) != 1 or len(hits[0]) > limit:
            raise MilvusContractError("Malformed Milvus search response")
        results = []
        for hit in hits[0]:
            try:
                row = {key: hit["entity"][key] for key in fields if key != "chunk_id"}
                row["chunk_id"] = hit["chunk_id"]
                score = hit["distance"]
            except (KeyError, TypeError):
                raise MilvusContractError("Malformed Milvus search result") from None
            _metadata(row, self.manifest)
            if (
                row["generation"] != self.generation
                or type(score) not in (int, float)
                or not math.isfinite(score)
            ):
                raise MilvusContractError("Incompatible Milvus search result")
            results.append({**row, "score": score})
        return results

    def delete(self, chunk_ids):
        self._batch(chunk_ids)
        for key in chunk_ids:
            _hash(key, 64)
        deadline = time.monotonic() + self.settings.milvus_timeout
        self._check_collection(deadline)
        return self._call(deadline, "delete", ids=list(chunk_ids))["delete_count"]


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise MilvusContractError("Scalar integer outside supported bounds")


def _text(value, maximum, *, empty=True):
    if (
        not isinstance(value, str)
        or (not empty and not value.strip())
        or len(value.encode("utf-8")) > maximum
    ):
        raise MilvusContractError("Scalar text outside UTF-8 byte bounds")


def _hash(value, size):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{%d}" % size, value):
        raise MilvusContractError("Invalid revision/chunk identity")


def _metadata(row, manifest):
    for name in ("chunk_id", "revision"):
        _hash(row[name], 64)
    if row["model_revision"] != manifest.revision:
        raise MilvusContractError("Chunk model revision mismatch")
    for name in ("language", "license", "section", "snippet"):
        _text(row[name], MILVUS_TEXT_BYTES[name])
    _integer(row["repo_id"], 1, 2**63 - 1)
    _integer(row["pushed_at"], 0, 2**63 - 1)
    _integer(row["ordinal"], 0, 7)


def _vector(values):
    if (
        not isinstance(values, (list, tuple))
        or len(values) != 384
        or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
    ):
        raise MilvusContractError("Expected 384 finite vector components")
    norm = math.hypot(*values)
    if not math.isclose(norm, 1, rel_tol=1e-4):
        raise MilvusContractError("Inner product requires a unit-normalized vector")
