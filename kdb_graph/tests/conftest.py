"""Shared pytest fixtures + synthetic factories for kdb_graph tests."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def graph_dir(tmp_path: Path) -> Path:
    """Per-test ephemeral Kuzu directory path. Kuzu creates the directory itself."""
    return tmp_path / "GraphDB-KDB"


# Synthetic factories now live in the shippable kdb_graph.testing module so
# cross-package consumers import a stable surface. Re-exported here so existing
# `from kdb_graph.tests.conftest import make_*` call sites keep working.
from kdb_graph.testing import (  # noqa: E402,F401
    make_page,
    make_compiled_source,
    make_compile_result,
    make_scan_entry,
    make_scan,
)
