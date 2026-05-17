"""Tests for planner.py graph-context wiring (D49 — GraphDB only).

Marked uses_real_graph_context to opt out of the conftest stub and test
the real graph_context_loader integration.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from graphdb_kdb.graphdb import GraphDB
from kdb_compiler.planner import build_jobs

pytestmark = pytest.mark.uses_real_graph_context


@pytest.fixture
def graph_path_with_source(tmp_path: Path) -> Path:
    """Seed a temp GraphDB with one source + one entity, close it, return path."""
    gpath = tmp_path / "test-graph"
    with GraphDB(gpath) as g:
        conn = g.conn
        conn.execute(
            "CREATE (e:Entity {slug: 'alpha', title: 'Alpha', page_type: 'concept', "
            "status: 'active', confidence: 'medium', "
            "created_at: '2026-01-01', updated_at: '2026-01-01', "
            "first_run_id: 'r1', last_run_id: 'r1'})"
        )
        conn.execute(
            "CREATE (s:Source {source_id: 'raw/test.md', source_type: 'raw', "
            "canonical_path: 'raw/test.md', status: 'active', file_type: 'markdown', "
            "hash: 'sha256:aaa', size_bytes: 100, "
            "first_seen_at: '2026-01-01', last_seen_at: '2026-01-01', "
            "last_ingested_at: '2026-01-01', ingest_state: 'compiled', "
            "ingest_count: 1, last_run_id: 'r1', moved_to: ''})"
        )
        conn.execute(
            "MATCH (s:Source {source_id: 'raw/test.md'}), (e:Entity {slug: 'alpha'}) "
            "CREATE (s)-[:SUPPORTS {run_id: 'r1'}]->(e)"
        )
    return gpath


@pytest.fixture
def vault_with_source(tmp_path: Path):
    """Vault root with a raw source file."""
    vault = tmp_path / "vault"
    raw_dir = vault / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "test.md").write_text("This is alpha content.")
    return vault


@pytest.fixture
def scan_one_source():
    return {
        "to_compile": ["raw/test.md"],
        "files": [
            {
                "path": "raw/test.md",
                "current_hash": "sha256:bbb",
                "size_bytes": 100,
                "file_type": "markdown",
                "is_binary": False,
            }
        ],
        "to_skip": [],
        "to_reconcile": [],
    }


@pytest.fixture
def manifest_minimal():
    return {"pages": {}, "sources": {}}


class TestPlannerGraphContext:
    def test_graphdb_produces_context(
        self, graph_path_with_source, vault_with_source, scan_one_source, manifest_minimal
    ):
        """GraphDB with SUPPORTS edge → context includes the supported entity."""
        with patch.dict(os.environ, {
            "KDB_GRAPH_PATH": str(graph_path_with_source),
        }):
            jobs = build_jobs(
                scan_one_source,
                manifest_minimal,
                vault_with_source,
            )
        assert len(jobs) == 1
        slugs = [p.slug for p in jobs[0].context_snapshot.pages]
        assert "alpha" in slugs

    def test_manifest_env_var_raises(
        self, vault_with_source, scan_one_source, manifest_minimal
    ):
        """KDB_CONTEXT_SOURCE=manifest is deprecated (D49) → explicit error."""
        with patch.dict(os.environ, {"KDB_CONTEXT_SOURCE": "manifest"}):
            with pytest.raises(RuntimeError, match="deprecated"):
                build_jobs(scan_one_source, manifest_minimal, vault_with_source)

    def test_graphdb_missing_path_raises(
        self, vault_with_source, scan_one_source, manifest_minimal, tmp_path
    ):
        """If graph path doesn't exist → RuntimeError."""
        bogus_path = tmp_path / "nonexistent" / "graph"
        with patch.dict(os.environ, {"KDB_GRAPH_PATH": str(bogus_path)}):
            with pytest.raises(RuntimeError, match="GraphDB unavailable"):
                build_jobs(scan_one_source, manifest_minimal, vault_with_source)

    def test_graphdb_empty_graph_raises(
        self, vault_with_source, scan_one_source, manifest_minimal, tmp_path
    ):
        """If graph has 0 entities → RuntimeError."""
        empty_graph_path = tmp_path / "empty-graph"
        with GraphDB(empty_graph_path) as g:
            pass
        with patch.dict(os.environ, {"KDB_GRAPH_PATH": str(empty_graph_path)}):
            with pytest.raises(RuntimeError, match="0 entities"):
                build_jobs(scan_one_source, manifest_minimal, vault_with_source)
