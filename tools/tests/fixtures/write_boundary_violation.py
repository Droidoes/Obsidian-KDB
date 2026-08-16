"""Fixture: a module that violates the kdb_fts write boundary (R2)."""
from pathlib import Path


def bad_write(path: Path) -> None:
    with open(path, "w") as f:  # noqa: guard-test fixture — direct open-for-write
        f.write("nope")
