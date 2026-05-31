"""Tests for the derived BELONGS_TO projection (0.5.0 producer rebuild).

Domain membership is now derived from Source.domain + SUPPORTS edges via
graphdb_kdb.ingestor.rederive_domains().  There are no longer page-level
domain/sub_domain fields, no _normalize_domain(), and no _ingest_page_domains().
"""
from __future__ import annotations

from graphdb_kdb import ingestor
from graphdb_kdb.graphdb import GraphDB
from graphdb_kdb.tests.conftest import (
    make_compile_result,
    make_compiled_source,
    make_page,
    make_scan,
    make_scan_entry,
)
from graphdb_kdb.types import SyncResult


# ---------- helpers ----------


def _domain_count(gdb: GraphDB) -> int:
    r = gdb.conn.execute("MATCH (d:Domain) RETURN COUNT(*)")
    return int(r.get_next()[0])


def _belongs_to_count(gdb: GraphDB) -> int:
    r = gdb.conn.execute("MATCH ()-[r:BELONGS_TO]->() RETURN COUNT(*)")
    return int(r.get_next()[0])


def _belongs_to(gdb: GraphDB, entity_slug: str, domain_name: str) -> dict | None:
    """Return {support_count} for (entity)-[:BELONGS_TO]->(domain), or None."""
    r = gdb.conn.execute(
        "MATCH (e:Entity {slug:$s})-[r:BELONGS_TO]->(d:Domain {name:$n}) "
        "RETURN r.support_count",
        {"s": entity_slug, "n": domain_name},
    )
    if r.has_next():
        return {"support_count": r.get_next()[0]}
    return None


def _src(source_id: str, pages: list[dict], domain: str) -> dict:
    return make_compiled_source(
        source_id, pages,
        source_meta={"domain": domain, "source_type": "blog", "author": None, "summary": "x"},
    )


# ---------- tests ----------


def test_single_source_confers_its_domain(graph_dir):
    cr = make_compile_result([_src("VI/a.md", [make_page("buffett")], "value-investing")])
    scan = make_scan([make_scan_entry("VI/a.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "r1")
        assert _domain_count(gdb) == 1
        assert _belongs_to(gdb, "buffett", "value-investing") == {"support_count": 1}


def test_entity_belongs_to_multiple_domains(graph_dir):
    """An entity supported by sources in two domains belongs to both."""
    cr = make_compile_result([
        _src("VI/a.md", [make_page("attention")], "value-investing"),
        _src("AI/b.md", [make_page("attention")], "ai-ml"),
    ])
    scan = make_scan([make_scan_entry("VI/a.md"), make_scan_entry("AI/b.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "r1")
        assert _belongs_to(gdb, "attention", "value-investing") == {"support_count": 1}
        assert _belongs_to(gdb, "attention", "ai-ml") == {"support_count": 1}


def test_support_count_is_distinct_source_count(graph_dir):
    """Two value-investing sources supporting the same entity -> support_count=2."""
    cr = make_compile_result([
        _src("VI/a.md", [make_page("moat")], "value-investing"),
        _src("VI/b.md", [make_page("moat")], "value-investing"),
    ])
    scan = make_scan([make_scan_entry("VI/a.md"), make_scan_entry("VI/b.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "r1")
        assert _belongs_to(gdb, "moat", "value-investing") == {"support_count": 2}


def test_source_without_domain_confers_nothing(graph_dir):
    """A source with no Source.domain produces no BELONGS_TO."""
    cs = make_compiled_source("x/c.md", [make_page("lonely")])  # no source_meta
    cr = make_compile_result([cs])
    scan = make_scan([make_scan_entry("x/c.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "r1")
        assert _belongs_to_count(gdb) == 0
        assert _domain_count(gdb) == 0


def test_rederive_is_idempotent(graph_dir):
    """Re-applying the same compile_result yields the same projection (recomputable)."""
    cr = make_compile_result([_src("VI/a.md", [make_page("buffett")], "value-investing")])
    scan = make_scan([make_scan_entry("VI/a.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "r1")
        gdb.apply_compile_result(cr, scan, "r2")
        assert _domain_count(gdb) == 1
        assert _belongs_to_count(gdb) == 1


def test_alias_entity_excluded_from_derived_domains(graph_dir):
    """Alias entities (canonical_id IS NOT NULL) must NOT receive BELONGS_TO edges.

    Because rederive_domains runs before _upsert_alias_entities_and_edges in
    apply_compile_result, the compile_result path cannot naturally route a
    SUPPORTS edge to an alias Entity row.  This test uses the direct-edge
    approach to isolate and prove the `e.canonical_id IS NULL` filter in
    rederive_domains: we build the graph state manually (canonical + alias
    entities each with a SUPPORTS edge from a domain-classified source), then
    call rederive_domains directly and assert the alias is excluded.
    """
    # Bootstrap the graph: canonical entity + source via apply_compile_result.
    cr = make_compile_result([_src("VI/a.md", [make_page("apple-inc")], "value-investing")])
    scan = make_scan([make_scan_entry("VI/a.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "r1")

        # Insert an alias Entity row with canonical_id pointing at apple-inc.
        gdb.conn.execute(
            """
            MERGE (a:Entity {slug: $alias})
            SET a.canonical_id=$canonical, a.status='alias', a.page_type='alias',
                a.title=$alias, a.confidence='n/a', a.created_at='t', a.updated_at='t',
                a.first_run_id='r1', a.last_run_id='r1'
            """,
            {"alias": "aapl", "canonical": "apple-inc"},
        )

        # Wire a SUPPORTS edge from the same domain-classified source to the alias.
        gdb.conn.execute(
            """
            MATCH (s:Source {source_id: $sid}), (a:Entity {slug: $alias})
            CREATE (s)-[:SUPPORTS {role:'primary', hash_at_time:'h', run_id:'r1', created_at:'t'}]->(a)
            """,
            {"sid": "VI/a.md", "alias": "aapl"},
        )

        # Re-run rederive_domains with both SUPPORTS edges in place.
        result = SyncResult()
        ingestor.rederive_domains(gdb.conn, "r1", "t", result)

        # Canonical entity MUST have a BELONGS_TO edge.
        assert _belongs_to(gdb, "apple-inc", "value-investing") == {"support_count": 1}
        # Alias entity MUST NOT receive a BELONGS_TO edge (canonical_id IS NULL filter).
        assert _belongs_to(gdb, "aapl", "value-investing") is None
        # Exactly one BELONGS_TO edge in total.
        assert _belongs_to_count(gdb) == 1
        assert result.belongs_to_upserted == 1
