from dataclasses import replace

import pytest
from app.services import archive_index
from app.services.archive_index import prepare_repository
from app.services.embeddings import EmbeddingAdapter, ModelManifest


class CharacterEncoder:
    """Offline counter; adversarially uses one token per Unicode character."""

    max_seq_length = 512

    def get_embedding_dimension(self):
        return 384

    def count_tokens(self, texts):
        return [len(text) + 2 for text in texts]

    def encode(self, texts, *, batch_size):
        raise AssertionError("Preparation must not embed content")


@pytest.fixture
def adapter():
    return EmbeddingAdapter(ModelManifest.load(), CharacterEncoder())


def prepare(adapter, readme=None, **changes):
    metadata = {
        "id": 42,
        "full_name": "acme/compass",
        "description": "Offline maps",
        "topics": ["maps", "offline"],
        "language": "Python",
    }
    metadata.update(changes)
    return prepare_repository(metadata, readme, adapter=adapter)


def test_missing_readme_keeps_useful_metadata_overview(adapter):
    result = prepare(adapter)
    assert result.readme_status == "missing"
    assert not result.omissions
    assert len(result.chunks) == 1
    text = result.chunks[0].text
    assert all(
        value in text for value in ("acme/compass", "Offline maps", "offline", "Python")
    )
    assert result.chunks[0].section == "Overview"


def test_missing_optional_metadata_still_identifies_repository(adapter):
    result = prepare(adapter, description=None, topics=None, language=None)
    assert result.chunks[0].text == "Repository: acme/compass\nSection: Overview"


def test_unicode_sections_and_code_are_inert_normalized_text(adapter):
    result = prepare(
        adapter,
        "# Cafe\u0301\n\n地図を共有\n\n```python\nopen_map('京都')\n```".encode(),
    )
    assert result.readme_status == "present"
    assert result.chunks[1].section == "Café"
    assert "地図を共有" in result.chunks[1].text
    assert "open_map('京都')" in result.chunks[1].text
    assert "```" not in result.chunks[1].text


def test_images_html_and_navigation_are_not_semantic_content(adapter):
    readme = b"""[![Build](https://bad.test/badge.svg)](https://bad.test)
<script>danger()</script>

## Contents
[Features](#features)

## Features
Works **offline** with `map_cache` and [SQLite](https://sqlite.org).

Unsafe <script>danger()</script> paragraph.
"""
    result = prepare(adapter, readme)
    text = "\n".join(chunk.text for chunk in result.chunks)
    assert "Works offline with map_cache and SQLite." in text
    assert all(
        value not in text
        for value in ("bad.test", "Build", "danger", "Contents", "<script>")
    )


def test_malformed_markdown_is_bounded_literal_text(adapter):
    result = prepare(
        adapter, b"# Usage\nUnclosed [link and **emphasis\n\n```\nuse_map()"
    )
    assert "use_map()" in result.chunks[1].text
    assert "Unclosed" in result.chunks[1].text


@pytest.mark.parametrize(
    "readme", [b"\xff\xfe", b"abc\x00def", b"abc\x1b[31m", b"abc\x7f"]
)
def test_invalid_readme_falls_back_without_losing_metadata(adapter, readme):
    result = prepare(adapter, readme)
    assert result.readme_status == "invalid"
    assert len(result.chunks) == 1
    assert "Offline maps" in result.chunks[0].text


def test_readme_byte_limit_is_checked_before_parsing(adapter):
    result = prepare(adapter, b"x" * (256 * 1024 + 1))
    assert result.readme_status == "too_large"
    assert result.omissions == ("readme_bytes",)
    assert len(result.chunks) == 1


def test_empty_readme_is_distinct_from_absence(adapter):
    assert prepare(adapter, b" \r\n\t").readme_status == "empty"


def test_identical_sections_do_not_waste_chunk_budget(adapter):
    result = prepare(adapter, b"## Usage\nRun compass.\n\n## Usage\nRun compass.")
    assert len(result.chunks) == 2
    assert result.chunks[1].text.count("Run compass.") == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"id": 0},
        {"id": True},
        {"id": 2**63},
        {"full_name": ""},
        {"description": 123},
        {"description": "x" * 17000},
        {"topics": "not-a-list"},
        {"topics": [1]},
        {"topics": ["x"] * 101},
    ],
)
def test_invalid_or_oversized_metadata_is_rejected(adapter, changes):
    with pytest.raises(ValueError, match="metadata"):
        prepare(adapter, **changes)


def test_chunks_enforce_prefixed_budget_and_cap_without_overlap(adapter):
    result = prepare(adapter, ("# Features\n" + "different words " * 1000).encode())
    assert len(result.chunks) == 8
    assert "chunk_limit" in result.omissions
    for chunk in result.chunks:
        assert chunk.token_count == len("passage: " + chunk.text) + 2 <= 512
        body = chunk.text.partition("\n\n")[2]
        assert len(body) + 2 <= 400
    assert [chunk.ordinal for chunk in result.chunks] == list(range(8))
    assert len({chunk.chunk_id for chunk in result.chunks}) == 8


def test_long_title_and_overview_leave_space_for_content(adapter):
    result = prepare(
        adapter,
        ("# " + "名" * 1000 + "\nUseful capability.").encode(),
        full_name="owner/" + "name" * 250,
        description="meaningful " * 400,
    )
    assert all(chunk.token_count <= 512 for chunk in result.chunks)
    assert "Useful capability." in result.chunks[1].text
    assert set(result.omissions) == {"title_tokens", "overview_tokens"}
    assert all(len(chunk.section) <= 64 for chunk in result.chunks)


def test_all_text_fits_without_character_loss_or_overlap(adapter):
    prose = "".join(chr(0x4E00 + i) for i in range(900))
    result = prepare(adapter, prose.encode())
    assert (
        "".join(chunk.text.partition("\n\n")[2] for chunk in result.chunks[1:]) == prose
    )
    assert not result.omissions


def test_parser_budget_and_upstream_clipping_are_explicit(adapter):
    result = prepare(adapter, b"a " * 100000)
    assert "parse_chars" in result.omissions
    assert "chunk_limit" in result.omissions
    incomplete = prepare_repository(
        {"id": 42, "full_name": "acme/compass"},
        b"short",
        adapter=adapter,
        source_truncated=True,
    )
    assert incomplete.omissions == ("source_truncated",)


def test_semantic_hash_and_chunk_keys_are_stable_and_ignore_stars(adapter):
    first = prepare(adapter, b"# Maps\nWorks offline.", stargazers_count=1)
    second = prepare(
        adapter,
        b"# Maps\nWorks  offline.\r\n",
        stargazers_count=999,
        topics=["offline", "maps", "maps"],
    )
    assert first == second
    assert len(first.semantic_hash) == 64
    assert all(len(chunk.chunk_id) == 64 for chunk in first.chunks)


@pytest.mark.parametrize(
    "changes",
    [
        {"description": "Online maps"},
        {"topics": ["routing"]},
        {"language": "Rust"},
        {"full_name": "acme/new-name"},
    ],
)
def test_semantic_metadata_changes_invalidate_revision(adapter, changes):
    first = prepare(adapter, b"Works offline.")
    second = prepare(adapter, b"Works offline.", **changes)
    assert first.semantic_hash != second.semantic_hash
    assert set(c.chunk_id for c in first.chunks).isdisjoint(
        c.chunk_id for c in second.chunks
    )


def test_removed_readme_does_not_retain_old_chunk_keys(adapter):
    first = prepare(adapter, b"## Features\nWorks offline.")
    second = prepare(adapter)
    assert len(second.chunks) == 1
    assert first.semantic_hash != second.semantic_hash
    assert first.chunks[0].chunk_id != second.chunks[0].chunk_id


def test_chunk_keys_are_bound_to_numeric_identity(adapter):
    first = prepare(adapter, b"same")
    second = prepare(adapter, b"same", id=43)
    assert first.repo_id == 42 and second.repo_id == 43
    assert set(c.chunk_id for c in first.chunks).isdisjoint(
        c.chunk_id for c in second.chunks
    )


@pytest.mark.parametrize("field", ["NORMALIZER_VERSION", "CHUNKER_VERSION"])
def test_content_algorithm_version_changes_invalidate_hash(adapter, monkeypatch, field):
    first = prepare(adapter, b"same")
    monkeypatch.setattr(archive_index, field, "next-version")
    second = prepare(adapter, b"same")
    assert first.semantic_hash != second.semantic_hash
    assert first.chunks[0].chunk_id != second.chunks[0].chunk_id


@pytest.mark.parametrize(
    "changes", [{"revision": "a" * 40}, {"tokenizer_sha256": "a" * 64}]
)
def test_model_or_tokenizer_change_invalidates_semantic_hash(adapter, changes):
    first = prepare(adapter, b"same")
    other = EmbeddingAdapter(replace(adapter.manifest, **changes), CharacterEncoder())
    assert prepare(other, b"same").semantic_hash != first.semantic_hash


@pytest.mark.parametrize("counts", [[], [0], [True], [1, 2], [1.5]])
def test_invalid_tokenizer_counts_fail_closed(adapter, monkeypatch, counts):
    monkeypatch.setattr(adapter.encoder, "count_tokens", lambda texts: counts)
    with pytest.raises(ValueError, match="token"):
        prepare(adapter, b"readme")


def test_tokenizer_failures_are_sanitized(adapter, monkeypatch):
    def fail(texts):
        raise RuntimeError("PRIVATE README OR PATH")

    monkeypatch.setattr(adapter.encoder, "count_tokens", fail)
    with pytest.raises(ValueError, match="token") as error:
        prepare(adapter, b"readme")
    assert "PRIVATE" not in str(error.value)


def test_readme_heading_named_overview_is_not_limited_to_metadata_slot(adapter):
    result = prepare(adapter, ("# Overview\n" + "界" * 900).encode())
    assert len(result.chunks) == 4
    assert not result.omissions


@pytest.mark.parametrize(
    "changes",
    [
        {"topics": False},
        {"topics": 0},
        {"description": "bad\x00text"},
        {"description": "界" * 6000},
    ],
)
def test_metadata_rejects_binary_and_falsey_wrong_types(adapter, changes):
    with pytest.raises(ValueError, match="metadata"):
        prepare(adapter, **changes)


def test_exact_byte_limit_is_accepted_and_parser_clipping_is_recorded(adapter):
    result = prepare(adapter, b"a " * (128 * 1024))
    assert result.readme_status == "present"
    assert "parse_chars" in result.omissions


def test_unusable_prefixed_token_budget_is_refused(adapter):
    encoder = CharacterEncoder()
    encoder.max_seq_length = 16
    small = EmbeddingAdapter(replace(adapter.manifest, max_tokens=16), encoder)
    with pytest.raises(ValueError, match="token budget"):
        prepare(small, b"readme")


def test_plaintext_line_breaks_and_indented_code_remain_searchable(adapter):
    result = prepare(adapter, b"Line one\nline two  \nline three\n\n    tool.run()")
    assert "Line one line two line three" in result.chunks[1].text
    assert "tool.run()" in result.chunks[1].text
