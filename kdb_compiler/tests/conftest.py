"""Test isolation for kdb_compiler/tests.

Two autouse fixtures:

1. KDB_GRAPH_PATH isolation — redirects graph writes to a per-test tmp
   directory so Stage 9 (graph_sync) doesn't leak synthetic fixtures into
   the live production graph.

2. Planner graph-context stub — since D49, build_jobs() always opens
   GraphDB for context. Tests that don't specifically test graph-context
   logic get a stub that returns empty snapshots. Tests that DO test graph
   context (test_planner_graph_context.py, test_graph_context_loader.py)
   override this by setting their own KDB_GRAPH_PATH to a seeded graph.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from kdb_compiler.types import ContextSnapshot


@pytest.fixture(autouse=True)
def _isolate_graph_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("KDB_GRAPH_PATH", str(tmp_path / "graph_isolated"))
    yield


@pytest.fixture(autouse=True)
def _stub_planner_graph_context(request, monkeypatch):
    """Stub the planner's graph-context path for tests that don't need it.

    Skipped when the test module explicitly opts out via the
    `uses_real_graph_context` marker.
    """
    if "uses_real_graph_context" in {m.name for m in request.node.iter_markers()}:
        yield
        return

    def _empty_snapshot(conn, *, source_id, source_text, page_cap=50):
        return ContextSnapshot(source_id=source_id, pages=[])

    monkeypatch.setattr(
        "kdb_compiler.planner._graph_conn_or_raise", _null_graph_ctx
    )
    monkeypatch.setattr(
        "kdb_compiler.planner._build_context", _empty_snapshot
    )
    yield


from contextlib import contextmanager


@contextmanager
def _null_graph_ctx():
    yield None
