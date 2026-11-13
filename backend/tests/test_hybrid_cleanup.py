"""Default-suite guards for the T26 lane's destructive cleanup helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hybrid_e2e_support import (
    PILOT_ROOT,
    assert_owned_collection,
    assert_temp_root,
    drop_owned_collection,
    new_collection_name,
)


def test_collection_names_are_unique_and_owned():
    names = {new_collection_name() for _ in range(20)}
    assert len(names) == 20
    for name in names:
        assert assert_owned_collection(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "repo_chunks_e5small_v1",
        "reporadar_t26_short",
        "reporadar_t26_" + "g" * 32,
        "reporadar_t26_" + "0" * 31,
        "",
        None,
    ],
)
def test_owned_collection_guard_rejects_other_names(name):
    with pytest.raises(ValueError):
        assert_owned_collection(name)


class FakeClient:
    def __init__(self):
        self.calls = []

    def has_collection(self, name, **kwargs):
        self.calls.append(("has", name))
        return True

    def drop_collection(self, name, **kwargs):
        self.calls.append(("drop", name))


def test_drop_refuses_foreign_collection_before_touching_client():
    client = FakeClient()
    with pytest.raises(ValueError):
        drop_owned_collection(client, "repo_chunks_e5small_v1")
    assert client.calls == []


def test_drop_only_removes_an_owned_collection():
    client = FakeClient()
    name = new_collection_name()
    drop_owned_collection(client, name)
    assert client.calls == [("has", name), ("drop", name)]


def test_temp_root_guard_accepts_a_fresh_directory_below_temp():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "lane"
        root.mkdir()
        assert assert_temp_root(root) == root.resolve()


def test_temp_root_guard_rejects_pilot_and_non_temp_paths():
    with pytest.raises(ValueError):
        assert_temp_root(PILOT_ROOT)
    with pytest.raises(ValueError):
        assert_temp_root(PILOT_ROOT / "child")
    with pytest.raises(ValueError):
        assert_temp_root(Path("/"))
    with pytest.raises(ValueError):
        assert_temp_root(Path(tempfile.gettempdir()))
