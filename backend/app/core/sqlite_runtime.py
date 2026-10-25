"""Shared linked-SQLite safety checks for archive WAL and operator probes."""


def wal_is_fixed(version):
    current = tuple(int(part) for part in version.split("."))
    return (
        current >= (3, 51, 3)
        or (current[:2] == (3, 50) and current >= (3, 50, 7))
        or (current[:2] == (3, 44) and current >= (3, 44, 6))
    )
