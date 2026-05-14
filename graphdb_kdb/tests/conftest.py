"""Shared pytest fixtures for graphdb_kdb tests."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def graph_dir(tmp_path: Path) -> Path:
    """Per-test ephemeral Kuzu directory path. Kuzu creates the directory itself."""
    return tmp_path / "GraphDB-KDB"
