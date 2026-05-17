"""Tests for planner.py graph-context wiring (#70.2)."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from graphdb_kdb.graphdb import GraphDB
from kdb_compiler.planner import build_jobs


@pytest.fixture
def graph_path_with_source(tmp_path: Path) -> Path:
    """Seed a temp GraphDB with one source + one entity, close it, return path.

    Closed before returning so build_jobs() can open it via KDB_GRAPH_PATH
    without conflicting with an already-open handle.
    """
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
    def test_graphdb_context_source_uses_graph_loader(
        self, graph_path_with_source, vault_with_source, scan_one_source, manifest_minimal
    ):
        """KDB_CONTEXT_SOURCE=graphdb routes through graph_context_loader."""
        with patch.dict(os.environ, {
            "KDB_CONTEXT_SOURCE": "graphdb",
            "KDB_GRAPH_PATH": str(graph_path_with_source),
        }):
            jobs = build_jobs(
                scan_one_source,
                manifest_minimal,
                vault_with_source,
            )
        assert len(jobs) == 1
        # alpha is supported by this source → must appear
        slugs = [p.slug for p in jobs[0].context_snapshot.pages]
        assert "alpha" in slugs

    def test_manifest_context_source_uses_manifest_loader(
        self, vault_with_source, scan_one_source, manifest_minimal
    ):
        """KDB_CONTEXT_SOURCE=manifest (default) uses context_loader."""
        with patch.dict(os.environ, {"KDB_CONTEXT_SOURCE": "manifest"}):
            jobs = build_jobs(
                scan_one_source,
                manifest_minimal,
                vault_with_source,
            )
        assert len(jobs) == 1
        # manifest has no pages → empty context
        assert jobs[0].context_snapshot.pages == []

    def test_graphdb_missing_path_raises(
        self, vault_with_source, scan_one_source, manifest_minimal, tmp_path
    ):
        """If graphdb requested but path doesn't exist → RuntimeError."""
        bogus_path = tmp_path / "nonexistent" / "graph"
        with patch.dict(os.environ, {
            "KDB_CONTEXT_SOURCE": "graphdb",
            "KDB_GRAPH_PATH": str(bogus_path),
        }):
            with pytest.raises(RuntimeError, match="GraphDB unavailable"):
                build_jobs(scan_one_source, manifest_minimal, vault_with_source)

    def test_graphdb_empty_graph_raises(
        self, vault_with_source, scan_one_source, manifest_minimal, tmp_path
    ):
        """If graphdb requested but graph has 0 entities → RuntimeError."""
        empty_graph_path = tmp_path / "empty-graph"
        with GraphDB(empty_graph_path) as g:
            pass  # creates schema but no data — closes on exit
        with patch.dict(os.environ, {
            "KDB_CONTEXT_SOURCE": "graphdb",
            "KDB_GRAPH_PATH": str(empty_graph_path),
        }):
            with pytest.raises(RuntimeError, match="GraphDB unavailable"):
                build_jobs(scan_one_source, manifest_minimal, vault_with_source)
