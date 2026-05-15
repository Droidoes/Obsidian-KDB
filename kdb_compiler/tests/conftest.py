"""Test isolation for kdb_compiler/tests.

Every test in this package gets `KDB_GRAPH_PATH` redirected to a per-test
tmp directory. Without this, Stage 9 (graph_sync, added by #63.7-pre) would
ingest synthetic test fixtures into the live `~/Droidoes/GraphDB-KDB`
production graph whenever a test calls `compile(...)` or `run(...)`.

Discovered during #63.7-A2 validation (2026-05-14): test fixtures
`paper.md`, `source-a.md`, `mencius`, etc. leaked into the live graph
because most tests in `test_kdb_compile.py` exercise the full pipeline
(including Stage 9) without isolating the graph location.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_graph_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("KDB_GRAPH_PATH", str(tmp_path / "graph_isolated"))
    yield
