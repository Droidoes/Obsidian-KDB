"""Tests for graph_context_loader — real Kuzu, no mocks."""
from __future__ import annotations

from pathlib import Path

import kuzu
import pytest

from graphdb_kdb.graphdb import GraphDB
from kdb_compiler.types import ContextSnapshot


@pytest.fixture
def gdb(tmp_path: Path):
    """Temp GraphDB with the reference topology."""
    with GraphDB(tmp_path / "test-graph") as g:
        conn = g.conn
        # Entities
        for slug, title, ptype in [
            ("hub", "Hub Concept", "concept"),
            ("spoke-1", "Spoke One", "concept"),
            ("spoke-2", "Spoke Two", "concept"),
            ("leaf-a", "Leaf Alpha", "article"),
            ("leaf-b", "Leaf Beta", "concept"),
            ("orphan-x", "Orphan X", "concept"),
        ]:
            conn.execute(
                "CREATE (e:Entity {slug: $s, title: $t, page_type: $pt, "
                "status: 'active', confidence: 'medium', "
                "created_at: '2026-01-01', updated_at: '2026-01-01', "
                "first_run_id: 'r1', last_run_id: 'r1'})",
                {"s": slug, "t": title, "pt": ptype},
            )

        # Sources
        for sid in ["src-alpha", "src-beta"]:
            conn.execute(
                "CREATE (s:Source {source_id: $sid, source_type: 'raw', "
                "canonical_path: $sid, status: 'active', file_type: 'markdown', "
                "hash: 'sha256:aaa', size_bytes: 100, "
                "first_seen_at: '2026-01-01', last_seen_at: '2026-01-01', "
                "last_ingested_at: '2026-01-01', ingest_state: 'compiled', "
                "ingest_count: 1, last_run_id: 'r1', moved_to: ''})",
                {"sid": sid},
            )

        # SUPPORTS edges (src-alpha → hub, spoke-1, spoke-2; src-beta → leaf-a)
        for src, slug in [
            ("src-alpha", "hub"),
            ("src-alpha", "spoke-1"),
            ("src-alpha", "spoke-2"),
            ("src-beta", "leaf-a"),
        ]:
            conn.execute(
                "MATCH (s:Source {source_id: $src}), (e:Entity {slug: $slug}) "
                "CREATE (s)-[:SUPPORTS {run_id: 'r1'}]->(e)",
                {"src": src, "slug": slug},
            )

        # LINKS_TO edges
        for from_slug, to_slug in [
            ("hub", "spoke-1"),
            ("hub", "spoke-2"),
            ("hub", "leaf-a"),
            ("spoke-1", "hub"),
            ("spoke-2", "leaf-a"),
            ("leaf-b", "hub"),
        ]:
            conn.execute(
                "MATCH (a:Entity {slug: $f}), (b:Entity {slug: $t}) "
                "CREATE (a)-[:LINKS_TO {run_id: 'r1'}]->(b)",
                {"f": from_slug, "t": to_slug},
            )

        yield g


from kdb_compiler import graph_context_loader


class TestTierRanking:
    def test_t1_source_supported_entities_ranked_highest(self, gdb):
        """Entities supported by the source appear first (tier 3 score)."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="unrelated text with no slug mentions",
            page_cap=50,
        )
        slugs = [p.slug for p in snapshot.pages]
        # src-alpha supports hub, spoke-1, spoke-2 — all must be present
        assert "hub" in slugs
        assert "spoke-1" in slugs
        assert "spoke-2" in slugs
        # They should be the first 3 (highest tier)
        assert set(slugs[:3]) == {"hub", "spoke-1", "spoke-2"}

    def test_t2_slug_in_text_ranked_below_t1(self, gdb):
        """Slugs mentioned in source_text rank below source-supported."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="See also leaf-b for more context.",
            page_cap=50,
        )
        slugs = [p.slug for p in snapshot.pages]
        # leaf-b is T2 (slug in text), should appear after T1 seeds
        assert "leaf-b" in slugs
        t1_slugs = {"hub", "spoke-1", "spoke-2"}
        leaf_b_idx = slugs.index("leaf-b")
        for s in t1_slugs:
            assert slugs.index(s) < leaf_b_idx

    def test_t3_neighbors_ranked_below_t2(self, gdb):
        """1-hop neighbors of seeds rank below text-mention seeds."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-beta",
            source_text="no slug mentions here",
            page_cap=50,
        )
        slugs = [p.slug for p in snapshot.pages]
        # src-beta supports leaf-a (T1). leaf-a has no outgoing links,
        # but spoke-2 links TO leaf-a (incoming). spoke-2 is T3.
        assert "leaf-a" in slugs
        if "spoke-2" in slugs:
            assert slugs.index("leaf-a") < slugs.index("spoke-2")

    def test_pagerank_breaks_ties_within_tier(self, gdb):
        """Within same tier, higher PageRank sorts first."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="",
            page_cap=50,
        )
        slugs = [p.slug for p in snapshot.pages]
        # Within T1: hub has highest PageRank (most inbound).
        # hub should sort before spoke-1, spoke-2 within the T1 band.
        assert slugs[0] == "hub"

    def test_page_cap_truncates(self, gdb):
        """page_cap limits total output."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="leaf-b orphan-x",
            page_cap=3,
        )
        assert len(snapshot.pages) == 3

    def test_outgoing_links_populated(self, gdb):
        """Each ContextPage carries its outgoing_links from the graph."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="",
            page_cap=50,
        )
        hub_page = next(p for p in snapshot.pages if p.slug == "hub")
        assert set(hub_page.outgoing_links) == {"spoke-1", "spoke-2", "leaf-a"}

    def test_source_id_set_on_snapshot(self, gdb):
        """ContextSnapshot carries source_id."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="",
            page_cap=50,
        )
        assert snapshot.source_id == "src-alpha"


class TestEdgeCases:
    def test_empty_graph_returns_empty_snapshot(self, tmp_path):
        """Empty graph → empty pages, no crash."""
        with GraphDB(tmp_path / "empty-graph") as g:
            snapshot = graph_context_loader.build_context_snapshot(
                g.conn,
                source_id="nonexistent",
                source_text="anything",
                page_cap=50,
            )
        assert snapshot.pages == []
        assert snapshot.source_id == "nonexistent"

    def test_unknown_source_returns_text_matches_and_neighbors(self, gdb):
        """Source not in graph → no T1 seeds, but T2/T3 still work."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="unknown-source",
            source_text="hub is mentioned here",
            page_cap=50,
        )
        slugs = [p.slug for p in snapshot.pages]
        assert "hub" in slugs

    def test_only_active_entities_included(self, gdb):
        """Entities with status != 'active' are excluded."""
        # Mark orphan-x as inactive
        gdb.conn.execute(
            "MATCH (e:Entity {slug: 'orphan-x'}) SET e.status = 'inactive'"
        )
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="orphan-x is mentioned",
            page_cap=50,
        )
        slugs = [p.slug for p in snapshot.pages]
        assert "orphan-x" not in slugs
