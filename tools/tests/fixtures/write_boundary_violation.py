"""Fixture: a module that violates the kdb_fts write boundary (R1/R2/R3)."""
import sqlite3
from pathlib import Path


def bad_write(path: Path) -> None:
    with open(path, "w") as f:  # R2: bare open for write
        f.write("nope")
    with path.open("w") as f:  # R2: Path.open for write
        f.write("nope")
    sqlite3.connect(path)  # R1: connect outside ledger.py
    path.unlink()  # R3: mutator outside the allowlist
