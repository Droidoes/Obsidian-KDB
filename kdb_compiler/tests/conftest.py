"""Test isolation for kdb_compiler/tests.

Autouse fixture:

1. KDB_GRAPH_PATH isolation — redirects graph writes to a per-test tmp
   directory so Stage 9 (graph_sync) doesn't leak synthetic fixtures into
   the live production graph.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_graph_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("KDB_GRAPH_PATH", str(tmp_path / "graph_isolated"))
    yield
