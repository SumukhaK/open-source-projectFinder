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
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(EmbeddingError, match="requirements.embeddings.txt"):
        _SentenceTransformerEncoder(make_manifest())


class FakeTokenizer:
    def __call__(self, texts, **kwargs):
        return {"input_ids": [[1] * (len(text) + 2) for text in texts]}


class FakeModel:
    def __init__(self, name, **kwargs):
        self.name = name
        self.kwargs = kwargs
        self.max_seq_length = 123
        self.tokenizer = FakeTokenizer()

    def get_embedding_dimension(self):
        return 384

    def encode(self, texts, **kwargs):
        return [[1.0] + [0.0] * 383 for _ in texts]


def test_real_wrapper_pins_cpu_revision_and_no_remote_code(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FakeModel),
    )
    manifest = make_manifest()
    encoder = _SentenceTransformerEncoder(manifest)

    assert encoder.max_seq_length == manifest.max_tokens
    assert encoder._model.name == manifest.name
    assert encoder._model.kwargs == {
        "revision": manifest.revision,
        "device": "cpu",
        "trust_remote_code": False,
    }
    assert encoder.get_embedding_dimension() == manifest.dimensions
    assert encoder.count_tokens(["ab"]) == [4]
    assert len(encoder.encode(["ab"], batch_size=1)) == 1
    assert _sentence_transformer_encoder(manifest).max_seq_length == manifest.max_tokens


def test_real_wrapper_rejects_a_model_without_a_tokenizer(monkeypatch):
    class NoTokenizerModel(FakeModel):
        def __init__(self, name, **kwargs):
            super().__init__(name, **kwargs)
            self.tokenizer = None

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=NoTokenizerModel),
    )
    with pytest.raises(EmbeddingError, match="tokenizer"):
        _SentenceTransformerEncoder(make_manifest())
