"""Tests for graphdb_kdb.schema + GraphDB schema bootstrap (#63.1)."""
from __future__ import annotations

from pathlib import Path

import pytest

import graphdb_kdb
from graphdb_kdb import schema
from graphdb_kdb.graphdb import GraphDB


def test_schema_constants_exist():
    """Schema module exposes SCHEMA_VERSION + DDL lists + MIGRATIONS registry."""
    assert isinstance(schema.SCHEMA_VERSION, str)
    assert schema.SCHEMA_VERSION  # non-empty
    assert isinstance(schema.NODE_TABLE_DDL, list) and len(schema.NODE_TABLE_DDL) == 2
    assert isinstance(schema.REL_TABLE_DDL, list) and len(schema.REL_TABLE_DDL) == 2
    node_text = " ".join(schema.NODE_TABLE_DDL)
    assert "CREATE NODE TABLE Page" in node_text
    assert "CREATE NODE TABLE Source" in node_text
    rel_text = " ".join(schema.REL_TABLE_DDL)
    assert "CREATE REL TABLE LINKS_TO" in rel_text
    assert "CREATE REL TABLE SUPPORTS" in rel_text
    # Q6 scaffold — registry exists, empty for v1.
    assert isinstance(schema.MIGRATIONS, dict)
    assert len(schema.MIGRATIONS) == 0


def test_graphdb_init_creates_schema(graph_dir):
    """First open of a fresh path creates tables + persists schema version."""
    with GraphDB(graph_dir) as gdb:
        v = gdb.schema_version()
        stats = gdb.stats()
    assert graph_dir.exists()
    assert v == schema.SCHEMA_VERSION
    assert stats == {"pages": 0, "sources": 0, "links_to": 0, "supports": 0}


def test_graphdb_init_is_idempotent(graph_dir):
    """Re-opening preserves schema version and adds no duplicate state."""
    with GraphDB(graph_dir) as gdb:
        v1 = gdb.schema_version()
    with GraphDB(graph_dir) as gdb:
        v2 = gdb.schema_version()
        stats = gdb.stats()
    assert v1 == v2 == schema.SCHEMA_VERSION
    assert stats == {"pages": 0, "sources": 0, "links_to": 0, "supports": 0}


def test_default_graph_path_default(monkeypatch):
    """default_graph_path returns ~/Droidoes/GraphDB-KDB when env var unset."""
    monkeypatch.delenv("KDB_GRAPH_PATH", raising=False)
    p = graphdb_kdb.default_graph_path()
    assert isinstance(p, Path)
    assert p == Path.home() / "Droidoes" / "GraphDB-KDB"


def test_default_graph_path_env_override(tmp_path, monkeypatch):
    """KDB_GRAPH_PATH env var overrides the default."""
    custom = tmp_path / "custom-graph-location"
    monkeypatch.setenv("KDB_GRAPH_PATH", str(custom))
    p = graphdb_kdb.default_graph_path()
    assert p == custom
