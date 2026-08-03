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


# ---------------------------------------------------------------------------
# #122 provenance resolver — per-path stamps, classifier normalization, parity
# ---------------------------------------------------------------------------


@pytest.fixture
def prov_graph(tmp_path: Path):
    """Resolution graph with DISTINCT first_run_id stamps per entity — proves
    the per-path stamp selection (target's stamp, never the alias row's)."""
    with GraphDB(tmp_path / "prov-graph") as g:
        conn = g.conn

        def add_entity(slug, status="active", canonical_id=None, first_run_id="r-self"):
            conn.execute(
                "CREATE (e:Entity {slug: $s, title: $s, page_type: 'concept', "
                "status: $st, confidence: 'medium', canonical_id: $ci, "
                "created_at: '2026-01-01', updated_at: '2026-01-01', "
                "first_run_id: $fr, last_run_id: 'r1'})",
                {"s": slug, "st": status, "ci": canonical_id, "fr": first_run_id},
            )

        def add_alias_of(alias, canonical):
            conn.execute(
                "MATCH (a:Entity {slug: $alias}), (c:Entity {slug: $canonical}) "
                "CREATE (a)-[:ALIAS_OF {run_id: 'r1', created_at: '2026-01-01', "
                "algorithm: 'manual'}]->(c)",
                {"alias": alias, "canonical": canonical},
            )

        add_entity("value-investing", first_run_id="r-direct")
        add_entity("warren-buffett", first_run_id="r-target")
        add_entity("wb", canonical_id="warren-buffett", first_run_id="r-aliasrow")
        add_entity("buffett", first_run_id="r-aliasrow2")
        add_alias_of("buffett", "warren-buffett")
        add_entity("dead", status="inactive", first_run_id="r-dead")
        add_entity("old-name", canonical_id="dead", first_run_id="r-oldrow")
        add_entity("dead-alias", status="inactive", first_run_id="r-dead2")
        add_entity("alias-to-dead", first_run_id="r-a2d")
        add_alias_of("alias-to-dead", "dead-alias")
        add_entity("nostamp", first_run_id="")   # legacy row: empty stamp
        yield conn


def test_provenance_path1_direct_leaf_stamp_is_own(prov_graph):
    prov = queries.resolve_to_canonical_slugs_with_provenance(prov_graph, ["value-investing"])
    assert prov == {"value-investing": ("value-investing", "r-direct")}


def test_provenance_path2_canonical_id_stamp_is_targets(prov_graph):
    """Path 2: the stamp is the canonical_id TARGET's first_run_id — never the
    alias row's own."""
    prov = queries.resolve_to_canonical_slugs_with_provenance(prov_graph, ["wb"])
    assert prov == {"wb": ("warren-buffett", "r-target")}


def test_provenance_path3_alias_of_stamp_is_canonicals(prov_graph):
    """Path 3: the stamp is the ALIAS_OF canonical's first_run_id."""
    prov = queries.resolve_to_canonical_slugs_with_provenance(prov_graph, ["buffett"])
    assert prov == {"buffett": ("warren-buffett", "r-target")}


def test_provenance_dead_targets_fail_closed(prov_graph):
    """canonical_id → inactive target AND ALIAS_OF → inactive canonical both
    stay unresolved (no Path-1 fallback)."""
    prov = queries.resolve_to_canonical_slugs_with_provenance(
        prov_graph, ["old-name", "alias-to-dead"])
    assert prov == {}


def test_provenance_empty_stamp_normalized_to_none(prov_graph):
    """Empty first_run_id → None AT THE CLASSIFIER (construction) — the strict
    record parser rejects an empty persisted stamp, so it never leaves here."""
    prov = queries.resolve_to_canonical_slugs_with_provenance(prov_graph, ["nostamp"])
    assert prov == {"nostamp": ("nostamp", None)}


def test_provenance_batch_matches_simple_outcomes_and_stamps(prov_graph):
    raw = ["value-investing", "wb", "buffett", "old-name", "alias-to-dead",
           "nostamp", "nonexistent"]
    simple = queries.resolve_to_canonical_slugs_with_provenance(prov_graph, raw)
    batch = queries.resolve_to_canonical_slugs_with_provenance_batch(prov_graph, raw)
    assert simple == batch
    assert simple == {
        "value-investing": ("value-investing", "r-direct"),
        "wb": ("warren-buffett", "r-target"),
        "buffett": ("warren-buffett", "r-target"),
        "nostamp": ("nostamp", None),
    }


def test_legacy_resolvers_are_slug_only_projections(prov_graph):
    """projection ≡ legacy: the legacy dict is exactly the provenance map with
    stamps dropped — for BOTH query shapes."""
    raw = ["value-investing", "wb", "buffett", "old-name", "nostamp", "nonexistent"]
    prov_s = queries.resolve_to_canonical_slugs_with_provenance(prov_graph, raw)
    prov_b = queries.resolve_to_canonical_slugs_with_provenance_batch(prov_graph, raw)
    expected = {raw: canonical for raw, (canonical, _stamp) in prov_s.items()}
    assert queries.resolve_to_canonical_slugs(prov_graph, raw) == expected
    assert queries.resolve_to_canonical_slugs_batch(prov_graph, raw) == expected
    assert prov_s == prov_b


def test_classifier_normalizes_empty_stamp_directly():
    """classify_resolution_rows: row-level unit pin for '' → None on all three
    paths (no graph needed)."""
    rows = [
        # (raw, e_status, canonical_id, e_fr, target_status, target_fr,
        #  alias_slug, alias_status, alias_fr)
        ("direct", "active", None, "", None, None, None, None, None),
        ("via-ci", "active", "canon", "x", "active", "", None, None, None),
        ("via-alias", "active", None, "x", None, None, "canon", "active", ""),
    ]
    assert queries.classify_resolution_rows(rows) == {
        "direct": ("direct", None),
        "via-ci": ("canon", None),
        "via-alias": ("canon", None),
    }


# ---------------------------------------------------------------------------
# Task #123 P3a: entity_first_run_ids — batched provenance stamp read
# ---------------------------------------------------------------------------


def test_entity_first_run_ids_known_active(prov_graph):
    assert queries.entity_first_run_ids(prov_graph, ["value-investing"]) == {
        "value-investing": "r-direct",
    }


def test_entity_first_run_ids_empty_stamp_is_none(prov_graph):
    assert queries.entity_first_run_ids(prov_graph, ["nostamp"]) == {"nostamp": None}


def test_entity_first_run_ids_null_stamp_is_none(prov_graph):
    prov_graph.execute(
        "MATCH (e:Entity {slug: 'buffett'}) SET e.first_run_id = NULL")
    assert queries.entity_first_run_ids(prov_graph, ["buffett"]) == {"buffett": None}


def test_entity_first_run_ids_unknown_slug_is_none(prov_graph):
    assert queries.entity_first_run_ids(prov_graph, ["no-such-slug"]) == {
        "no-such-slug": None,
    }


def test_entity_first_run_ids_inactive_slug_is_none(prov_graph):
    assert queries.entity_first_run_ids(prov_graph, ["dead"]) == {"dead": None}


def test_entity_first_run_ids_mixed_batch(prov_graph):
    slugs = ["value-investing", "nostamp", "dead", "no-such-slug", "warren-buffett"]
    assert queries.entity_first_run_ids(prov_graph, slugs) == {
        "value-investing": "r-direct",
        "nostamp": None,
        "dead": None,
        "no-such-slug": None,
        "warren-buffett": "r-target",
    }


def test_entity_first_run_ids_empty_list_issues_no_query(prov_graph, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("query issued for empty input")

    monkeypatch.setattr(prov_graph, "execute", _boom)
    assert queries.entity_first_run_ids(prov_graph, []) == {}
