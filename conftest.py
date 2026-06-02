"""Root conftest — fixtures available to ALL test packages.

Autouse fixtures:

1. _isolate_graph_dir — redirects KDB_GRAPH_PATH to a per-test tmp directory
   so graph writes (Stage 9 graph_sync etc.) don't leak into the live
   production graph.  Originally scoped to kdb_compiler/tests; promoted here
   so every package's tests share the same isolation guarantee.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_graph_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("KDB_GRAPH_PATH", str(tmp_path / "graph_isolated"))
    yield
