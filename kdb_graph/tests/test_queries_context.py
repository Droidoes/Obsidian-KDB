"""Tests for the context-snapshot read primitives in kdb_graph.queries.

These primitives are the "single Kuzu door" extraction (Phase A): the raw
Cypher reads formerly authored inside kdb_compiler.graph_context_loader now
live here. Each test seeds a real temp Kuzu graph (no mocks) and asserts the
primitive returns the exact plain data the loader's composition logic relies
on. Fixtures are lifted verbatim from the loader/resolver-parity tests so the
primitives are verified against the same graph states those tests trust.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kdb_graph import queries
from kdb_graph.graphdb import GraphDB


# ---------------------------------------------------------------------------
# Reference topology fixture (lifted from test_graph_context_loader.py::gdb)
# ---------------------------------------------------------------------------


@pytest.fixture
def gdb(tmp_path: Path):
    """Temp GraphDB with the reference topology (entities, sources, edges)."""
    with GraphDB(tmp_path / "test-graph") as g:
        conn = g.conn
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


# ---------- active_entities ----------


def test_active_entities_returns_slug_to_title_page_type(gdb):
    ents = queries.active_entities(gdb.conn)
    assert set(ents.keys()) == {
        "hub", "spoke-1", "spoke-2", "leaf-a", "leaf-b", "orphan-x",
    }
    assert ents["hub"] == {"title": "Hub Concept", "page_type": "concept"}
    assert ents["leaf-a"] == {"title": "Leaf Alpha", "page_type": "article"}


def test_active_entities_excludes_inactive(gdb):
    gdb.conn.execute("MATCH (e:Entity {slug: 'orphan-x'}) SET e.status = 'inactive'")
    ents = queries.active_entities(gdb.conn)
    assert "orphan-x" not in ents


def test_active_entities_empty_graph(tmp_path):
    with GraphDB(tmp_path / "empty") as g:
        assert queries.active_entities(g.conn) == {}


# ---------- source_supported_slugs ----------


def test_source_supported_slugs(gdb):
    assert queries.source_supported_slugs(gdb.conn, "src-alpha") == {
        "hub", "spoke-1", "spoke-2",
    }


def test_source_supported_slugs_unknown_source(gdb):
    assert queries.source_supported_slugs(gdb.conn, "nope") == set()


def test_source_supported_slugs_returns_raw_unscoped(gdb):
    """Primitive does NOT filter by active status — caller scopes. Mark a
    supported entity inactive; the slug is still returned (the active filter
    is the loader's job, applied via the slug_set intersection)."""
    gdb.conn.execute("MATCH (e:Entity {slug: 'spoke-1'}) SET e.status = 'inactive'")
    assert "spoke-1" in queries.source_supported_slugs(gdb.conn, "src-alpha")


# ---------- domain_entity_slugs ----------


@pytest.fixture
def gdb_dom(tmp_path: Path):
    """Temp GraphDB with Domain + BELONGS_TO edges (lifted from loader test)."""
    with GraphDB(tmp_path / "dom-graph") as g:
        conn = g.conn
        for slug, title, ptype in [
            ("vi-hub", "VI Hub", "concept"),
            ("vi-spoke", "VI Spoke", "concept"),
            ("vi-leaf", "VI Leaf", "article"),
            ("ai-node", "AI Node", "concept"),
        ]:
            conn.execute(
                "CREATE (e:Entity {slug: $s, title: $t, page_type: $pt, "
                "status: 'active', confidence: 'medium', "
                "created_at: '2026-01-01', updated_at: '2026-01-01', "
                "first_run_id: 'r1', last_run_id: 'r1'})",
                {"s": slug, "t": title, "pt": ptype},
            )
        for name in ["value-investing", "ai-ml"]:
            conn.execute(
                "CREATE (d:Domain {name: $n, created_at: '2026-01-01', "
                "first_run_id: 'r1'})", {"n": name})
        for slug, dom in [
            ("vi-hub", "value-investing"), ("vi-spoke", "value-investing"),
            ("vi-leaf", "value-investing"), ("ai-node", "ai-ml"),
        ]:
            conn.execute(
                "MATCH (e:Entity {slug: $s}), (d:Domain {name: $d}) "
                "CREATE (e)-[:BELONGS_TO {run_id: 'r1'}]->(d)", {"s": slug, "d": dom})
        yield g


def test_domain_entity_slugs(gdb_dom):
    assert queries.domain_entity_slugs(gdb_dom.conn, "value-investing") == {
        "vi-hub", "vi-spoke", "vi-leaf",
    }
    assert queries.domain_entity_slugs(gdb_dom.conn, "ai-ml") == {"ai-node"}


def test_domain_entity_slugs_unknown_domain(gdb_dom):
    assert queries.domain_entity_slugs(gdb_dom.conn, "nonexistent") == set()


def test_domain_entity_slugs_excludes_inactive(gdb_dom):
    gdb_dom.conn.execute("MATCH (e:Entity {slug: 'vi-leaf'}) SET e.status = 'inactive'")
    assert queries.domain_entity_slugs(gdb_dom.conn, "value-investing") == {
        "vi-hub", "vi-spoke",
    }


# ---------- outgoing / incoming neighbor slugs ----------


def test_outgoing_neighbor_slugs(gdb):
    assert set(queries.outgoing_neighbor_slugs(gdb.conn, "hub")) == {
        "spoke-1", "spoke-2", "leaf-a",
    }


def test_outgoing_neighbor_slugs_none(gdb):
    # leaf-a has no outgoing LINKS_TO
    assert queries.outgoing_neighbor_slugs(gdb.conn, "leaf-a") == []


def test_incoming_neighbor_slugs(gdb):
    # spoke-1 (hub->spoke-1), leaf-b (leaf-b->hub) link to hub; also spoke-1->hub
    assert set(queries.incoming_neighbor_slugs(gdb.conn, "hub")) == {
        "spoke-1", "leaf-b",
    }


def test_incoming_neighbor_slugs_none(gdb):
    # leaf-b has no incoming LINKS_TO
    assert queries.incoming_neighbor_slugs(gdb.conn, "leaf-b") == []


# ---------- links_to_edges / active_entity_slugs (PageRank reads) ----------


def test_links_to_edges(gdb):
    edges = set(queries.links_to_edges(gdb.conn))
    assert edges == {
        ("hub", "spoke-1"), ("hub", "spoke-2"), ("hub", "leaf-a"),
        ("spoke-1", "hub"), ("spoke-2", "leaf-a"), ("leaf-b", "hub"),
    }


def test_active_entity_slugs(gdb):
    assert set(queries.active_entity_slugs(gdb.conn)) == {
        "hub", "spoke-1", "spoke-2", "leaf-a", "leaf-b", "orphan-x",
    }


def test_active_entity_slugs_excludes_inactive(gdb):
    gdb.conn.execute("MATCH (e:Entity {slug: 'orphan-x'}) SET e.status = 'inactive'")
    assert "orphan-x" not in queries.active_entity_slugs(gdb.conn)


# ---------- outgoing_links_ordered ----------


def test_outgoing_links_ordered_is_sorted(gdb):
    # hub -> spoke-1, spoke-2, leaf-a; must come back ascending by slug
    assert queries.outgoing_links_ordered(gdb.conn, "hub") == [
        "leaf-a", "spoke-1", "spoke-2",
    ]


def test_outgoing_links_ordered_empty(gdb):
    assert queries.outgoing_links_ordered(gdb.conn, "leaf-a") == []


# ---------------------------------------------------------------------------
# Resolver fixture (lifted from test_t2_resolver_parity.py::resolver_graph)
# ---------------------------------------------------------------------------


@pytest.fixture
def resolver_graph(tmp_path: Path):
    """Graph spanning all §3.1 reachability paths (canonical_id / ALIAS_OF)."""
    with GraphDB(tmp_path / "resolver-graph") as g:
        conn = g.conn

        def add_entity(slug, status="active", canonical_id=None):
            conn.execute(
                "CREATE (e:Entity {slug: $s, title: $s, page_type: 'concept', "
                "status: $st, confidence: 'medium', canonical_id: $ci, "
                "created_at: '2026-01-01', updated_at: '2026-01-01', "
                "first_run_id: 'r1', last_run_id: 'r1'})",
                {"s": slug, "st": status, "ci": canonical_id},
            )

        def add_alias_of(alias, canonical):
            conn.execute(
                "MATCH (a:Entity {slug: $alias}), (c:Entity {slug: $canonical}) "
                "CREATE (a)-[:ALIAS_OF {run_id: 'r1', created_at: '2026-01-01', "
                "algorithm: 'manual'}]->(c)",
                {"alias": alias, "canonical": canonical},
            )

        add_entity("value-investing")
        add_entity("warren-buffett")
        add_entity("wb", canonical_id="warren-buffett")
        add_entity("buffett")
        add_alias_of("buffett", "warren-buffett")
        add_entity("deprecated", status="inactive")
        add_entity("old-name", canonical_id="deprecated")
        add_entity("target-a")
        add_entity("target-b")
        add_entity("ambiguous", canonical_id="target-a")
        add_alias_of("ambiguous", "target-b")
        add_entity("inactive-only", status="inactive")
        add_entity("alias-to-dead")
        add_entity("dead-target", status="inactive")
        add_alias_of("alias-to-dead", "dead-target")
        yield conn


# (raw_input, expected) — same probes the loader's parity test trusts.
_RESOLVER_PROBES = [
    (["value-investing"], {"value-investing": "value-investing"}),
    (["wb"], {"wb": "warren-buffett"}),
    (["buffett"], {"buffett": "warren-buffett"}),
    (["old-name"], {}),
    (["ambiguous"], {"ambiguous": "target-a"}),
    (["inactive-only"], {}),
    (["alias-to-dead"], {}),
    (["nonexistent-slug"], {}),
    ([], {}),
    (["", "  ", "value-investing"], {"value-investing": "value-investing"}),
    (["value-investing", "value-investing"], {"value-investing": "value-investing"}),
]


@pytest.mark.parametrize("raw,expected", _RESOLVER_PROBES)
def test_resolve_to_canonical_slugs_simple(resolver_graph, raw, expected):
    assert queries.resolve_to_canonical_slugs(resolver_graph, raw) == expected


@pytest.mark.parametrize("raw,expected", _RESOLVER_PROBES)
def test_resolve_to_canonical_slugs_batch(resolver_graph, raw, expected):
    assert queries.resolve_to_canonical_slugs_batch(resolver_graph, raw) == expected


def test_resolver_simple_batch_parity(resolver_graph):
    """The two resolvers agree on the mixed batch (D-90-9 parity contract)."""
    raw = ["value-investing", "buffett", "wb", "old-name", "nonexistent-slug"]
    simple = queries.resolve_to_canonical_slugs(resolver_graph, raw)
    batch = queries.resolve_to_canonical_slugs_batch(resolver_graph, raw)
    assert simple == batch == {
        "value-investing": "value-investing",
        "buffett": "warren-buffett",
        "wb": "warren-buffett",
    }
