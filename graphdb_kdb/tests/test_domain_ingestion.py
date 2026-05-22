"""Tests for #76.3 — Phase 3.6 domain node + BELONGS_TO edge ingest.

Covers the domain-field implementation added to graphdb_kdb.ingestor:
- _normalize_domain(): two-stage normalization regex
- _ingest_page_domains(): Domain MERGE + BELONGS_TO MERGE per page
- canonical-only tagging (alias pages are skipped — OQ-10)
- omit-when-plural: sub_domain is None when domain is an array (R5)
- post-normalize deduplication: ["Investing", "investing"] → one edge
- SyncResult counter increments (domains_upserted, belongs_to_upserted)
"""
from __future__ import annotations

import pytest

from graphdb_kdb import ingestor
from graphdb_kdb.graphdb import GraphDB
from graphdb_kdb.tests.conftest import (
    make_compile_result,
    make_compiled_source,
    make_page,
    make_scan,
    make_scan_entry,
)


# ---------- helpers ----------


def make_page_with_domain(slug: str, domain=None, sub_domain=None, **kwargs) -> dict:
    """Extend make_page with optional domain/sub_domain fields."""
    p = make_page(slug, **kwargs)
    if domain is not None:
        p["domain"] = domain
    if sub_domain is not None:
        p["sub_domain"] = sub_domain
    return p


def _domain_count(gdb: GraphDB) -> int:
    r = gdb.conn.execute("MATCH (d:Domain) RETURN COUNT(*)")
    return int(r.get_next()[0])


def _belongs_to_count(gdb: GraphDB) -> int:
    r = gdb.conn.execute("MATCH ()-[r:BELONGS_TO]->() RETURN COUNT(*)")
    return int(r.get_next()[0])


def _belongs_to_edge(gdb: GraphDB, entity_slug: str, domain_name: str) -> dict | None:
    """Return edge properties for (entity)-[:BELONGS_TO]->(domain), or None."""
    r = gdb.conn.execute(
        """
        MATCH (e:Entity {slug: $slug})-[r:BELONGS_TO]->(d:Domain {name: $name})
        RETURN r.sub_domain, r.run_id
        """,
        {"slug": entity_slug, "name": domain_name},
    )
    if r.has_next():
        row = r.get_next()
        return {"sub_domain": row[0], "run_id": row[1]}
    return None


def _canonical_meta(aliases: list[dict] | None = None) -> dict:
    return {
        "algorithm_version": "1.0",
        "ledger_snapshot_sha256": "deadbeef",
        "aliases_emitted": aliases or [],
        "outgoing_link_remaps": [],
        "merged_pages": [],
    }


# ---------- unit test: _normalize_domain ----------


def test_normalize_domain_lowercase_and_hyphen():
    assert ingestor._normalize_domain("Value Investing") == "value-investing"


def test_normalize_domain_collapses_consecutive_dashes():
    assert ingestor._normalize_domain("value--investing") == "value-investing"


def test_normalize_domain_strips_trailing_punctuation():
    assert ingestor._normalize_domain("investing.") == "investing"


def test_normalize_domain_mixed_case_with_spaces():
    assert ingestor._normalize_domain("  Deep Learning  ") == "deep-learning"


def test_normalize_domain_mixed_dash_and_space():
    assert ingestor._normalize_domain("value - investing") == "value-investing"


# ---------- 1. single domain string ----------


def test_single_domain_creates_node_and_edge(graph_dir):
    """Page with domain='investing' → one Domain node + one BELONGS_TO edge."""
    page = make_page_with_domain("alpha", domain="investing")
    cr = make_compile_result([make_compiled_source("KDB/raw/a.md", [page])])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        dc = _domain_count(gdb)
        bc = _belongs_to_count(gdb)
        edge = _belongs_to_edge(gdb, "alpha", "investing")
    assert dc == 1
    assert bc == 1
    assert edge is not None
    assert res.domains_upserted == 1
    assert res.belongs_to_upserted == 1


def test_single_domain_with_sub_domain(graph_dir):
    """sub_domain propagates to the BELONGS_TO edge when domain is a string."""
    page = make_page_with_domain("alpha", domain="investing", sub_domain="value-investing")
    cr = make_compile_result([make_compiled_source("KDB/raw/a.md", [page])])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        edge = _belongs_to_edge(gdb, "alpha", "investing")
    assert edge is not None
    assert edge["sub_domain"] == "value-investing"


# ---------- 2. multi-domain array ----------


def test_multi_domain_array_creates_multiple_edges(graph_dir):
    """domain=['investing', 'biography'] → 2 Domain nodes + 2 BELONGS_TO edges."""
    page = make_page_with_domain("alpha", domain=["investing", "biography"])
    cr = make_compile_result([make_compiled_source("KDB/raw/a.md", [page])])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        dc = _domain_count(gdb)
        bc = _belongs_to_count(gdb)
    assert dc == 2
    assert bc == 2
    assert res.domains_upserted == 2
    assert res.belongs_to_upserted == 2


def test_sub_domain_omitted_when_multi_domain(graph_dir):
    """R5 omit-when-plural: sub_domain is None on all edges when domain is an array."""
    page = make_page_with_domain(
        "alpha", domain=["investing", "biography"], sub_domain="value-investing"
    )
    cr = make_compile_result([make_compiled_source("KDB/raw/a.md", [page])])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        edge_inv = _belongs_to_edge(gdb, "alpha", "investing")
        edge_bio = _belongs_to_edge(gdb, "alpha", "biography")
    assert edge_inv is not None
    assert edge_inv["sub_domain"] is None
    assert edge_bio is not None
    assert edge_bio["sub_domain"] is None


# ---------- 3. normalization ----------


def test_normalization_applied_at_ingest(graph_dir):
    """'Value Investing' normalizes to 'value-investing' Domain node."""
    page = make_page_with_domain("alpha", domain="Value Investing")
    cr = make_compile_result([make_compiled_source("KDB/raw/a.md", [page])])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        edge = _belongs_to_edge(gdb, "alpha", "value-investing")
        dc = _domain_count(gdb)
    assert edge is not None
    assert dc == 1


def test_sub_domain_normalized_at_ingest(graph_dir):
    """R12 (blueprint §6.3): sub_domain runs through _normalize_domain at
    ingest, not stored verbatim. 'Value Investing' → 'value-investing'."""
    page = make_page_with_domain("alpha", domain="investing", sub_domain="Value Investing")
    cr = make_compile_result([make_compiled_source("KDB/raw/a.md", [page])])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        edge = _belongs_to_edge(gdb, "alpha", "investing")
    assert edge is not None
    assert edge["sub_domain"] == "value-investing"


def test_sub_domain_empty_string_becomes_null(graph_dir):
    """Defensive: an LLM-emitted empty/whitespace sub_domain normalizes to
    empty string, which we coerce to None so the edge property stays NULL."""
    page = make_page_with_domain("alpha", domain="investing", sub_domain="   ")
    cr = make_compile_result([make_compiled_source("KDB/raw/a.md", [page])])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        edge = _belongs_to_edge(gdb, "alpha", "investing")
    assert edge is not None
    assert edge["sub_domain"] is None


def test_post_normalize_deduplication(graph_dir):
    """['Investing', 'investing'] normalizes to the same name → only one edge."""
    page = make_page_with_domain("alpha", domain=["Investing", "investing"])
    cr = make_compile_result([make_compiled_source("KDB/raw/a.md", [page])])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        dc = _domain_count(gdb)
        bc = _belongs_to_count(gdb)
    assert dc == 1
    assert bc == 1
    assert res.belongs_to_upserted == 1


def test_cross_page_domain_sharing(graph_dir):
    """Two pages with the same domain share the same Domain node."""
    pages = [
        make_page_with_domain("alpha", domain="investing"),
        make_page_with_domain("beta", domain="investing"),
    ]
    cr = make_compile_result([make_compiled_source("KDB/raw/a.md", pages)])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        dc = _domain_count(gdb)
        bc = _belongs_to_count(gdb)
    assert dc == 1   # one shared Domain node
    assert bc == 2   # two BELONGS_TO edges (one per entity)


# ---------- 4. canonical-only tagging (OQ-10) ----------


def test_alias_page_skipped_no_belongs_to_edge(graph_dir):
    """Alias pages (canonical_id set) are skipped; BELONGS_TO written only for
    the canonical entity."""
    canonical_page = make_page_with_domain("apple-inc", domain="technology")
    alias_page = make_page_with_domain("aapl", domain="technology")
    alias_page["canonical_id"] = "apple-inc"  # mark as alias

    cr = make_compile_result(
        [make_compiled_source("KDB/raw/a.md", [canonical_page, alias_page])],
        canonical_meta=_canonical_meta([
            {"alias_slug": "aapl", "canonical_slug": "apple-inc", "algorithm": "ledger"}
        ]),
    )
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        dc = _domain_count(gdb)
        bc = _belongs_to_count(gdb)
        canonical_edge = _belongs_to_edge(gdb, "apple-inc", "technology")
        alias_edge = _belongs_to_edge(gdb, "aapl", "technology")
    assert dc == 1
    assert bc == 1
    assert canonical_edge is not None
    assert alias_edge is None
    assert res.belongs_to_upserted == 1


# ---------- 5. no domain → no edge ----------


def test_no_domain_no_node_no_edge(graph_dir):
    """Pages without domain field produce no Domain nodes or BELONGS_TO edges."""
    cr = make_compile_result([make_compiled_source("KDB/raw/a.md", [make_page("alpha")])])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        dc = _domain_count(gdb)
        bc = _belongs_to_count(gdb)
    assert dc == 0
    assert bc == 0
    assert res.domains_upserted == 0
    assert res.belongs_to_upserted == 0


# ---------- 6. idempotency ----------


def test_domain_merge_idempotency(graph_dir):
    """Re-running the same compile twice produces exactly the same graph state."""
    page = make_page_with_domain("alpha", domain="investing", sub_domain="value-investing")
    cr = make_compile_result([make_compiled_source("KDB/raw/a.md", [page])])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-2")
        dc = _domain_count(gdb)
        bc = _belongs_to_count(gdb)
        edge = _belongs_to_edge(gdb, "alpha", "investing")
    assert dc == 1
    assert bc == 1
    assert edge is not None
    assert edge["run_id"] == "run-2"  # ON MATCH SET updates run_id
