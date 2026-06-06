"""Tests for compiler.kpi.graph.compute_graph (#109).

GRAPH-family KPI computation over a hand-rolled Kuzu graph + an emitted-link
compile_result payload + a finalize_artifacts report. Each KPI is asserted
against hand-computed values.

The graph is hand-rolled via raw conn.execute (the established
test_canonicalization_invariants pattern) because the precise mix of canonical/
alias/orphan entities, SUPPORTS multiplicity, BELONGS_TO, and a null-domain
source cannot be produced through apply_compile_result without fighting the
ingestion derivations.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from compiler.kpi.graph import compute_graph, _largest_component_fraction
from kdb_graph.graphdb import GraphDB


@pytest.fixture
def graph_dir(tmp_path: Path) -> Path:
    """Per-test ephemeral Kuzu directory (mirrors kdb_graph.tests.conftest —
    not importable here as compiler/tests has its own conftest scope)."""
    return tmp_path / "GraphDB-KDB"


# ---------- hand-rolled graph seeding ----------

def _mk_entity(conn, slug, *, canonical_id="NULL", page_type="concept",
               status="active"):
    cid = "NULL" if canonical_id == "NULL" else f"'{canonical_id}'"
    conn.execute(
        f"CREATE (e:Entity {{slug: '{slug}', canonical_id: {cid}, "
        f"title: '', page_type: '{page_type}', status: '{status}', "
        f"confidence: '', created_at: '2026-06-05', updated_at: '2026-06-05', "
        f"first_run_id: 'm', last_run_id: 'm'}})"
    )


def _mk_source(conn, sid, *, domain="'finance'"):
    conn.execute(
        f"CREATE (s:Source {{source_id: '{sid}', source_type: 'file', "
        f"canonical_path: '{sid}', status: 'active', file_type: 'markdown', "
        f"hash: 'h', size_bytes: 1, first_seen_at: '', last_seen_at: '', "
        f"last_ingested_at: '', ingest_state: '', ingest_count: 1, "
        f"last_run_id: 'm', moved_to: '', summary: '', author: '', "
        f"domain: {domain}}})"
    )


def _mk_supports(conn, sid, slug):
    conn.execute(
        f"MATCH (s:Source {{source_id: '{sid}'}}), (e:Entity {{slug: '{slug}'}}) "
        f"CREATE (s)-[:SUPPORTS {{role: '', hash_at_time: '', run_id: 'm', "
        f"created_at: ''}}]->(e)"
    )


def _seed(gdb):
    """Canonical entities: alpha, beta, gamma, summary-x (summary), orphan-z
    (status orphan_candidate). Alias: alpha-alias (canonical_id=alpha).
    Sources: s1, s2 (finance), s3 (NULL domain). SUPPORTS: alpha<-s1,s2;
    beta<-s1; gamma none. Domain finance + BELONGS_TO from alpha. LINKS_TO:
    alpha->beta (the only edge; both canonical → one 2-node component, the
    rest singletons)."""
    c = gdb.conn
    _mk_entity(c, "alpha")
    _mk_entity(c, "beta")
    _mk_entity(c, "gamma")
    _mk_entity(c, "summary-x", page_type="summary")
    _mk_entity(c, "orphan-z", status="orphan_candidate")
    _mk_entity(c, "alpha-alias", canonical_id="alpha", page_type="alias")
    c.execute(
        "MATCH (a:Entity {slug: 'alpha-alias'}), (b:Entity {slug: 'alpha'}) "
        "CREATE (a)-[:ALIAS_OF {run_id: 'm', created_at: '', algorithm: 'l'}]->(b)"
    )
    _mk_source(c, "s1")
    _mk_source(c, "s2")
    _mk_source(c, "s3", domain="NULL")
    _mk_supports(c, "s1", "alpha")
    _mk_supports(c, "s2", "alpha")
    _mk_supports(c, "s1", "beta")
    c.execute("CREATE (d:Domain {name: 'finance', created_at: '', first_run_id: 'm'})")
    c.execute(
        "MATCH (e:Entity {slug: 'alpha'}), (d:Domain {name: 'finance'}) "
        "CREATE (e)-[:BELONGS_TO {run_id: 'm', created_at: '', support_count: 2}]->(d)"
    )
    c.execute(
        "MATCH (a:Entity {slug: 'alpha'}), (b:Entity {slug: 'beta'}) "
        "CREATE (a)-[:LINKS_TO {run_id: 'm', created_at: ''}]->(b)"
    )


def _compile_result(links_per_page):
    """Wrap a list of outgoing_links lists into a compile_result, one page each."""
    return {
        "run_id": "test",
        "success": True,
        "compiled_sources": [
            {
                "source_id": "KDB/raw/s.md",
                "pages": [
                    {"slug": f"p{i}", "outgoing_links": links}
                    for i, links in enumerate(links_per_page)
                ],
            }
        ],
        "errors": [],
        "warnings": [],
    }


_FINALIZE = {"reaped": [{"page_id": "p", "slug": "orphan-z", "page_type": "concept"}],
             "retracted_slugs": ["orphan-z"]}


# ---------- SCORED: link_resolution_rate ----------

def test_link_resolution_alias_resolves_dangling_counts(graph_dir):
    """beta resolves (active canonical), alpha-alias resolves via canonical_id
    -> alpha (a link to an alias is RESOLVED), nonexistent-xyz dangles.
    dangling=1, total=3 → 1/3."""
    cr = _compile_result([["beta", "alpha-alias"], ["nonexistent-xyz"]])
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, cr, _FINALIZE)
    assert out["scored"]["link_resolution_rate"] == pytest.approx(1 / 3)


def test_link_resolution_none_when_zero_links(graph_dir):
    """Zero emitted links → None (NOT 0.0 — don't conflate with all-resolve)."""
    cr = _compile_result([[], []])
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, cr, _FINALIZE)
    assert out["scored"]["link_resolution_rate"] is None


def test_link_resolution_all_resolve_is_zero_not_none(graph_dir):
    cr = _compile_result([["alpha", "beta", "alpha-alias"]])
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, cr, _FINALIZE)
    assert out["scored"]["link_resolution_rate"] == 0.0


# ---------- WATCHED ----------

def test_entity_reuse(graph_dir):
    """canonical non-summary: alpha(2 sources), beta(1), gamma(0), orphan-z(0).
    >=2 sources: alpha → 1/4 = 0.25."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _compile_result([[]]), _FINALIZE)
    assert out["watched"]["entity_reuse"] == pytest.approx(0.25)


def test_graph_connectivity_two_components(graph_dir):
    """canonical = {alpha,beta,gamma,summary-x,orphan-z} (5). Edge alpha-beta
    → largest component {alpha,beta}=2; gamma/summary-x/orphan-z singletons.
    2/5 = 0.4."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _compile_result([[]]), _FINALIZE)
    assert out["watched"]["graph_connectivity"] == pytest.approx(0.4)


def test_orphan_rate(graph_dir):
    """len(reaped)=1 ÷ total entities=6 (5 canonical + 1 alias) = 1/6."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _compile_result([[]]), _FINALIZE)
    assert out["watched"]["orphan_rate"] == pytest.approx(1 / 6)


def test_orphan_rate_empty_finalize_is_zero(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _compile_result([[]]), {})
    assert out["watched"]["orphan_rate"] == 0.0


# ---------- DIAGNOSTIC ----------

def test_diagnostic_values(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _compile_result([[]]), _FINALIZE)
    d = out["diagnostic"]
    assert d["belongs_to_coverage"] == pytest.approx(1 / 5)   # alpha of 5 canonical
    assert d["domain_null_rate"] == pytest.approx(1 / 3)      # s3 of 3 sources
    assert d["link_density"] == pytest.approx(1 / 5)          # 1 edge / 5 canonical
    assert d["supports_density"] == pytest.approx(3 / 3)      # 3 SUPPORTS / 3 sources
    assert d["domain_breadth"] == pytest.approx(1 / 23)       # 1 domain / 23


def test_return_dict_keys(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _compile_result([[]]), _FINALIZE)
    assert set(out) == {"scored", "watched", "diagnostic"}
    assert set(out["scored"]) == {"link_resolution_rate"}
    assert set(out["watched"]) == {"entity_reuse", "graph_connectivity", "orphan_rate"}
    assert set(out["diagnostic"]) == {
        "belongs_to_coverage", "domain_null_rate", "link_density",
        "supports_density", "domain_breadth",
    }


# ---------- union-find unit coverage (empty + singleton + chain) ----------

def test_connectivity_empty_is_none():
    assert _largest_component_fraction([], [("a", "b")]) is None


def test_connectivity_all_singletons():
    """No edges among 3 canonical → largest component size 1 → 1/3."""
    frac = _largest_component_fraction(["a", "b", "c"], [])
    assert frac == pytest.approx(1 / 3)


def test_connectivity_undirected_chain():
    """a->b->c directed edges, treated undirected → one component of 3 → 3/3."""
    frac = _largest_component_fraction(["a", "b", "c"], [("a", "b"), ("b", "c")])
    assert frac == 1.0


def test_connectivity_skips_noncanonical_endpoints():
    """An edge to a non-canonical (alias/dangling) slug is ignored; it does not
    merge canonical nodes nor inflate the component."""
    frac = _largest_component_fraction(["a", "b"], [("a", "ghost"), ("ghost", "b")])
    # a and b stay separate singletons → largest = 1, 1/2.
    assert frac == pytest.approx(0.5)
