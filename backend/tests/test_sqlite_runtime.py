import pytest
from app.core.sqlite_runtime import wal_is_fixed


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
