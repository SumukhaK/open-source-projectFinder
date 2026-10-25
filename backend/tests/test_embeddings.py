import hashlib
import json
import math
import sys
import types
from dataclasses import replace

import pytest
from app.services.embeddings import (
    MANIFEST_PATH,
    PREFIXES,
    EmbeddingAdapter,
    EmbeddingError,
    ModelManifest,
    UnsupportedInput,
    _sentence_transformer_encoder,
    _SentenceTransformerEncoder,
)


class FakeEncoder:
    """Deterministic, offline stand-in for the pinned Sentence Transformer."""

    def __init__(self, dimension=384, vector=None, counter=None):
        self.dimension = dimension
        self.vector = vector
        self.counter = counter or (lambda text: len(text) + 2)
        self.calls = []

    @property
    def max_seq_length(self):
        return 512

    def get_embedding_dimension(self):
        return self.dimension

    def count_tokens(self, texts):
        return [self.counter(text) for text in texts]

    def encode(self, texts, *, batch_size):
        self.calls.append((list(texts), batch_size))
        if self.vector is not None:
            return [self.vector for _ in texts]
        return [[1.0] + [0.0] * 383 for _ in texts]


def make_manifest(**changes):
    manifest = ModelManifest.load(MANIFEST_PATH)
    return replace(manifest, **changes)


def test_shipped_manifest_pins_the_published_safe_weights():
    manifest = ModelManifest.load(MANIFEST_PATH)

    assert manifest.name == "intfloat/multilingual-e5-small"
    assert manifest.revision == "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    assert manifest.dimensions == 384
    assert manifest.max_tokens == 512
    assert manifest.license == "MIT"
    assert manifest.weights_file == "model.safetensors"
    assert manifest.weights_sha256 == (
        "1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477"
    )
    assert manifest.tokenizer_file == "tokenizer.json"
    assert manifest.tokenizer_sha256 == (
        "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"
    )
    assert PREFIXES == {"query": "query: ", "passage": "passage: "}


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"revision": "main"}, "commit SHA"),
        ({"weights_file": "pytorch_model.bin"}, "safetensors"),
        ({"weights_file": "../model.safetensors"}, "filename"),
        ({"weights_sha256": "abc"}, "sha256"),
        ({"tokenizer_file": ""}, "filename"),
        ({"tokenizer_sha256": "z" * 64}, "sha256"),
        ({"dimensions": 0}, "dimensions"),
        ({"max_tokens": True}, "max_tokens"),
        ({"license": ""}, "license"),
        ({"name": ""}, "name"),
    ],
)
def test_manifest_rejects_unsafe_or_incomplete_values(changes, message):
    manifest = make_manifest(**changes)
    with pytest.raises(EmbeddingError, match=message):
        manifest.validate()


def test_manifest_load_rejects_broken_json(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(EmbeddingError, match="manifest"):
        ModelManifest.load(path)

    path.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(EmbeddingError, match="object"):
        ModelManifest.load(path)

    path.write_text(json.dumps({"name": "x"}), encoding="utf-8")
    with pytest.raises(EmbeddingError, match="weights"):
        ModelManifest.load(path)

    valid = {
        "name": "intfloat/multilingual-e5-small",
        "revision": "a" * 40,
        "dimensions": 384,
        "max_tokens": 512,
        "license": "MIT",
        "weights": {"file": "model.safetensors", "sha256": "a" * 64},
        "tokenizer": {"file": "tokenizer.json", "sha256": "b" * 64},
    }
    path.write_text(json.dumps({**valid, "revision": ""}), encoding="utf-8")
    with pytest.raises(EmbeddingError, match="revision"):
        ModelManifest.load(path)

    path.write_text(json.dumps({**valid, "dimensions": "384"}), encoding="utf-8")
    with pytest.raises(EmbeddingError, match="dimensions"):
        ModelManifest.load(path)


def test_adapter_adds_the_required_prefixes_and_rejects_caller_prefixes():
    encoder = FakeEncoder()
    adapter = EmbeddingAdapter(make_manifest(), encoder, batch_size=4)

    adapter.embed(["find a tool"], kind="query")
    adapter.embed(["a tool"], kind="passage")

    assert encoder.calls[0][0] == ["query: find a tool"]
    assert encoder.calls[1][0] == ["passage: a tool"]

    for text in ("query: find a tool", "passage: a tool", "Query: find a tool"):
        with pytest.raises(EmbeddingError, match="omit the E5 prefix"):
            adapter.embed([text], kind="query")
    assert len(encoder.calls) == 2


def test_token_budget_counts_the_prefix_and_rejects_overflow():
    encoder = FakeEncoder()
    adapter = EmbeddingAdapter(make_manifest(), encoder)

    # "query: " is 7 characters and the fake tokenizer adds two special tokens.
    adapter.embed(["x" * 503], kind="query")
    with pytest.raises(EmbeddingError, match="512"):
        adapter.embed(["x" * 504], kind="query")
    assert len(encoder.calls) == 1

    # The passage prefix is two characters longer, so the same text overflows.
    with pytest.raises(EmbeddingError, match="512"):
        adapter.embed(["x" * 502], kind="passage")
    adapter.embed(["x" * 501], kind="passage")


def test_invalid_vectors_are_rejected_and_valid_vectors_are_normalized():
    def adapter_with(vector):
        return EmbeddingAdapter(make_manifest(), FakeEncoder(vector=vector))

    for vector, message in (
        ([float("nan")] + [0.0] * 383, "non-finite"),
        ([float("inf")] + [0.0] * 383, "non-finite"),
        ([1.0] * 383, "383 dimensions"),
        ([0.0] * 384, "zero vector"),
        (["x"] + [0.0] * 383, "non-numeric"),
    ):
        with pytest.raises(EmbeddingError, match=message):
            adapter_with(vector).embed(["a tool"], kind="query")

    vectors = adapter_with([3.0, 4.0] + [0.0] * 382).embed(["a tool"], kind="query")
    assert len(vectors) == 1
    assert math.isclose(vectors[0][0], 0.6)
    assert math.isclose(vectors[0][1], 0.8)
    assert math.isclose(
        math.sqrt(math.fsum(value * value for value in vectors[0])), 1.0
    )


def test_manifest_mismatch_is_rejected_before_encoding():
    encoder = FakeEncoder(dimension=768)
    with pytest.raises(EmbeddingError, match="768"):
        EmbeddingAdapter(make_manifest(), encoder)
    assert encoder.calls == []

    class ShortEncoder(FakeEncoder):
        @property
        def max_seq_length(self):
            return 256

    with pytest.raises(EmbeddingError, match="256"):
        EmbeddingAdapter(make_manifest(), ShortEncoder())


def test_batches_are_bounded_and_output_count_matches_input():
    encoder = FakeEncoder()
    adapter = EmbeddingAdapter(make_manifest(), encoder, batch_size=2)

    vectors = adapter.embed(["a", "b", "c", "d", "e"], kind="passage")

    assert len(vectors) == 5
    assert [len(texts) for texts, _ in encoder.calls] == [2, 2, 1]
    assert all(batch_size == len(texts) for texts, batch_size in encoder.calls)
    with pytest.raises(EmbeddingError, match="batch_size"):
        EmbeddingAdapter(make_manifest(), FakeEncoder(), batch_size=0)
    with pytest.raises(EmbeddingError, match="batch_size"):
        EmbeddingAdapter(make_manifest(), FakeEncoder(), batch_size=65)


def test_bad_input_and_encoder_shapes_are_rejected():
    adapter = EmbeddingAdapter(make_manifest(), FakeEncoder())

    assert adapter.embed([], kind="query") == []
    with pytest.raises(EmbeddingError, match="kind"):
        adapter.embed(["a"], kind="document")
    with pytest.raises(EmbeddingError, match="text"):
        adapter.embed("a tool", kind="query")
    with pytest.raises(EmbeddingError, match="empty"):
        adapter.embed(["   "], kind="query")
    with pytest.raises(EmbeddingError, match="text"):
        adapter.embed([None], kind="query")

    class WrongCount(FakeEncoder):
        def count_tokens(self, texts):
            return []

    with pytest.raises(EmbeddingError, match="token"):
        EmbeddingAdapter(make_manifest(), WrongCount()).embed(["a"], kind="query")

    class WrongRows(FakeEncoder):
        def encode(self, texts, *, batch_size):
            return []

    with pytest.raises(EmbeddingError, match="vector"):
        EmbeddingAdapter(make_manifest(), WrongRows()).embed(["a"], kind="query")


def test_input_side_rejections_raise_unsupported_input():
    adapter = EmbeddingAdapter(make_manifest(), FakeEncoder())
    cases = (
        (lambda: adapter.embed([None], kind="query"), "text"),
        (lambda: adapter.embed(["   "], kind="query"), "empty"),
        (
            lambda: adapter.embed(["Query: find a tool"], kind="query"),
            "omit the E5 prefix",
        ),
        (lambda: adapter.embed(["x" * 504], kind="query"), "512"),
    )
    for call, message in cases:
        with pytest.raises(UnsupportedInput, match=message):
            call()


def test_programming_and_model_faults_stay_plain_embedding_errors():
    adapter = EmbeddingAdapter(make_manifest(), FakeEncoder())

    class WrongCount(FakeEncoder):
        def count_tokens(self, texts):
            return []

    class WrongRows(FakeEncoder):
        def encode(self, texts, *, batch_size):
            return []

    cases = (
        (lambda: adapter.embed("a tool", kind="query"), "text"),
        (lambda: adapter.embed(["a"], kind="document"), "kind"),
        (lambda: EmbeddingAdapter(make_manifest(), FakeEncoder(dimension=768)), "768"),
        (
            lambda: EmbeddingAdapter(
                make_manifest(), FakeEncoder(vector=[float("nan")] + [0.0] * 383)
            ).embed(["a"], kind="query"),
            "non-finite",
        ),
        (
            lambda: EmbeddingAdapter(
                make_manifest(), FakeEncoder(vector=[0.0] * 384)
            ).embed(["a"], kind="query"),
            "zero vector",
        ),
        (
            lambda: EmbeddingAdapter(make_manifest(), WrongCount()).embed(
                ["a"], kind="query"
            ),
            "token",
        ),
        (
            lambda: EmbeddingAdapter(make_manifest(), WrongRows()).embed(
                ["a"], kind="query"
            ),
            "vector",
        ),
    )
    for call, message in cases:
        with pytest.raises(EmbeddingError, match=message) as caught:
            call()
        assert not isinstance(caught.value, UnsupportedInput)


def test_load_wires_the_injected_factory_and_warms_by_default():
    encoder = FakeEncoder()
    seen = []

    def factory(manifest):
        seen.append(manifest)
        return encoder

    adapter = EmbeddingAdapter.load(encoder_factory=factory)
    assert seen == [adapter.manifest]
    assert encoder.calls == [(["query: warm up"], 1)]

    encoder.calls.clear()
    EmbeddingAdapter.load(encoder_factory=factory, warm=False)
    assert encoder.calls == []


def test_missing_optional_dependency_explains_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(EmbeddingError, match="requirements.embeddings.txt"):
        _SentenceTransformerEncoder(make_manifest())


class FakeTokenizer:
    def __call__(self, texts, **kwargs):
        return {"input_ids": [[1] * (len(text) + 2) for text in texts]}


class RecordingModel:
    def __init__(self, path, **kwargs):
        self.path = path
        self.kwargs = kwargs
        self.max_seq_length = 123
        self.tokenizer = FakeTokenizer()

    def get_embedding_dimension(self):
        return 384

    def encode(self, texts, **kwargs):
        return [[1.0] + [0.0] * 383 for _ in texts]


class FakeHub:
    def __init__(self, path=None, error=None):
        self.path = path
        self.error = error
        self.calls = []

    def snapshot_download(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return str(self.path)


def install_fakes(monkeypatch, hub, model=RecordingModel):
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=model),
    )


def write_snapshot(tmp_path, weights=b"safe weights", tokenizer=b"tokenizer"):
    (tmp_path / "model.safetensors").write_bytes(weights)
    (tmp_path / "tokenizer.json").write_bytes(tokenizer)
    return make_manifest(
        weights_sha256=hashlib.sha256(weights).hexdigest(),
        tokenizer_sha256=hashlib.sha256(tokenizer).hexdigest(),
    )


def test_wrapper_requires_a_cached_snapshot_and_never_downloads(monkeypatch):
    hub = FakeHub(error=OSError("not cached"))
    built = []

    def model(path, **kwargs):
        built.append((path, kwargs))
        raise AssertionError("must not construct the model")

    install_fakes(monkeypatch, hub, model=model)

    with pytest.raises(EmbeddingError, match="--download"):
        _SentenceTransformerEncoder(make_manifest())

    assert built == []
    assert hub.calls == [
        {
            "repo_id": "intfloat/multilingual-e5-small",
            "revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
            "local_files_only": True,
            "allow_patterns": make_manifest().snapshot_files,
        }
    ]


def test_wrapper_rejects_a_weights_hash_mismatch(monkeypatch, tmp_path):
    manifest = write_snapshot(tmp_path)
    hub = FakeHub(path=tmp_path)
    built = []

    def model(path, **kwargs):
        built.append(path)
        return RecordingModel(path, **kwargs)

    install_fakes(monkeypatch, hub, model=model)

    with pytest.raises(EmbeddingError, match="weights sha256 mismatch"):
        _SentenceTransformerEncoder(replace(manifest, weights_sha256="a" * 64))
    assert built == []


def test_wrapper_rejects_a_tokenizer_hash_mismatch(monkeypatch, tmp_path):
    manifest = write_snapshot(tmp_path)
    hub = FakeHub(path=tmp_path)
    built = []

    def model(path, **kwargs):
        built.append(path)
        return RecordingModel(path, **kwargs)

    install_fakes(monkeypatch, hub, model=model)

    with pytest.raises(EmbeddingError, match="tokenizer sha256 mismatch"):
        _SentenceTransformerEncoder(replace(manifest, tokenizer_sha256="b" * 64))
    assert built == []


def test_wrapper_rejects_a_missing_pinned_file(monkeypatch, tmp_path):
    (tmp_path / "tokenizer.json").write_bytes(b"tokenizer")
    manifest = make_manifest(
        weights_sha256=hashlib.sha256(b"safe weights").hexdigest(),
        tokenizer_sha256=hashlib.sha256(b"tokenizer").hexdigest(),
    )
    hub = FakeHub(path=tmp_path)
    built = []

    def model(path, **kwargs):
        built.append(path)
        return RecordingModel(path, **kwargs)

    install_fakes(monkeypatch, hub, model=model)

    with pytest.raises(EmbeddingError, match="weights file is missing"):
        _SentenceTransformerEncoder(manifest)
    assert built == []


def test_wrapper_loads_only_from_the_verified_snapshot(monkeypatch, tmp_path):
    manifest = write_snapshot(tmp_path)
    hub = FakeHub(path=tmp_path)
    built = []

    def model(path, **kwargs):
        instance = RecordingModel(path, **kwargs)
        built.append(instance)
        return instance

    install_fakes(monkeypatch, hub, model=model)

    encoder = _SentenceTransformerEncoder(manifest)

    assert hub.calls == [
        {
            "repo_id": manifest.name,
            "revision": manifest.revision,
            "local_files_only": True,
            "allow_patterns": make_manifest().snapshot_files,
        }
    ]
    assert len(built) == 1
    assert built[0].path == str(tmp_path)
    assert built[0].kwargs == {
        "device": "cpu",
        "trust_remote_code": False,
        "local_files_only": True,
        "model_kwargs": {"use_safetensors": True},
    }
    assert encoder.max_seq_length == manifest.max_tokens
    assert encoder.get_embedding_dimension() == manifest.dimensions
    assert encoder.count_tokens(["ab"]) == [4]
    assert len(encoder.encode(["ab"], batch_size=1)) == 1
    assert _sentence_transformer_encoder(manifest).max_seq_length == manifest.max_tokens


def test_wrapper_rejects_a_model_without_a_tokenizer(monkeypatch, tmp_path):
    manifest = write_snapshot(tmp_path)
    hub = FakeHub(path=tmp_path)

    class NoTokenizerModel(RecordingModel):
        def __init__(self, path, **kwargs):
            super().__init__(path, **kwargs)
            self.tokenizer = None

    install_fakes(monkeypatch, hub, model=NoTokenizerModel)
    with pytest.raises(EmbeddingError, match="tokenizer"):
        _SentenceTransformerEncoder(manifest)


@pytest.mark.parametrize("count", [True, "5", None, -1, 0, float("nan")])
def test_invalid_token_counts_are_model_faults(count):
    encoder = FakeEncoder(counter=lambda text: count)
    with pytest.raises(EmbeddingError, match="token") as caught:
        EmbeddingAdapter(make_manifest(), encoder).embed(["a"], kind="query")
    assert not isinstance(caught.value, UnsupportedInput)
    assert encoder.calls == []


@pytest.mark.parametrize("method", ["count_tokens", "encode"])
def test_encoder_runtime_faults_are_model_errors(method):
    encoder = FakeEncoder()

    def fail(*args, **kwargs):
        raise RuntimeError("model unavailable")

    setattr(encoder, method, fail)
    with pytest.raises(EmbeddingError) as caught:
        EmbeddingAdapter(make_manifest(), encoder).embed(["a"], kind="query")
    assert not isinstance(caught.value, UnsupportedInput)


def test_model_load_failure_is_not_an_input_error(monkeypatch, tmp_path):
    manifest = write_snapshot(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("model unavailable")

    install_fakes(monkeypatch, FakeHub(path=tmp_path), model=fail)
    with pytest.raises(EmbeddingError) as caught:
        _SentenceTransformerEncoder(manifest)
    assert not isinstance(caught.value, UnsupportedInput)


@pytest.mark.parametrize("download", [False, True])
def test_smoke_setup_is_explicit_and_excludes_other_weights(
    monkeypatch, tmp_path, download
):
    from scripts import embeddings_smoke

    manifest = write_snapshot(tmp_path)
    adapter = EmbeddingAdapter(manifest, FakeEncoder())
    hub = FakeHub(path=tmp_path)
    hub.__version__ = "test"
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    for name in (
        "numpy",
        "safetensors",
        "scipy",
        "sentence_transformers",
        "sklearn",
        "tokenizers",
        "torch",
        "transformers",
    ):
        monkeypatch.setitem(
            sys.modules, name, types.SimpleNamespace(__version__="test")
        )
    monkeypatch.setattr(ModelManifest, "load", classmethod(lambda cls: manifest))
    monkeypatch.setattr(EmbeddingAdapter, "load", classmethod(lambda cls: adapter))

    result = embeddings_smoke.run(1, download=download)

    assert result["weights"]["verified"] and result["tokenizer"]["verified"]
    assert result["checks"] == {
        "caller_prefix_rejected": True,
        "overflow_rejected": True,
    }
    assert hub.calls[0]["revision"] == manifest.revision
    assert hub.calls[0]["local_files_only"] is (not download)
    assert "allow_patterns" in hub.calls[0]
    assert set(hub.calls[0]["allow_patterns"]) == {
        manifest.weights_file,
        manifest.tokenizer_file,
        "*.json",
        "*.txt",
        "sentencepiece.bpe.model",
    }


def test_partial_snapshot_resolution_uses_the_same_setup_file_filter(
    monkeypatch, tmp_path
):
    manifest = write_snapshot(tmp_path)

    class PartialCache(FakeHub):
        def snapshot_download(self, **kwargs):
            assert kwargs["local_files_only"] is True
            expected = {
                manifest.weights_file,
                manifest.tokenizer_file,
                "*.json",
                "*.txt",
                "sentencepiece.bpe.model",
            }
            if set(kwargs.get("allow_patterns", [])) != expected:
                raise OSError("unselected repository files are not cached")
            return super().snapshot_download(**kwargs)

    install_fakes(monkeypatch, PartialCache(path=tmp_path))
    encoder = _SentenceTransformerEncoder(manifest)
    assert encoder.get_embedding_dimension() == 384


def test_model_dimension_failure_is_an_embedding_error():
    class BrokenModel(FakeEncoder):
        def get_embedding_dimension(self):
            raise RuntimeError("model unavailable")

    with pytest.raises(EmbeddingError) as caught:
        EmbeddingAdapter(make_manifest(), BrokenModel())
    assert not isinstance(caught.value, UnsupportedInput)


@pytest.mark.parametrize(
    "value,message",
    [(1e308, "non-finite"), (1e154, "non-finite"), (10**1000, "non-numeric")],
    ids=["nonfinite-norm", "sum-overflow", "conversion-overflow"],
)
def test_overflowing_vector_norm_is_rejected_as_a_model_fault(value, message):
    adapter = EmbeddingAdapter(make_manifest(), FakeEncoder(vector=[value] * 384))
    with pytest.raises(EmbeddingError, match=message) as caught:
        adapter.embed(["a"], kind="query")
    assert not isinstance(caught.value, UnsupportedInput)
