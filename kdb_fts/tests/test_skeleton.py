"""Phase 0 smoke: package imports, and nothing internal leaks in/out."""
from __future__ import annotations


def test_package_imports():
    import kdb_fts

    assert kdb_fts.__doc__ is not None
