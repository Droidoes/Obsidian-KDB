"""Tests for #74.5 — alias Entity + ALIAS_OF writes in apply_compile_result.

Covers the Phase 3.5 alias-write pass added to kdb_graph.intake and the
companion changes in _upsert_entity (canonical_id reset + stale ALIAS_OF
drop) and _detect_and_mark_orphans (canonical-only scope).

Graph-invariant context (verifier C1–C4 land in #74.6):
  C1 — Entity with canonical_id IS NOT NULL has an ALIAS_OF edge to that
       canonical_id (verified inline here).
  C2 — ALIAS_OF edge's source has canonical_id == destination slug.
  C3 — ALIAS_OF is flat (D-R5-13): canonical_id always points at a root.
  C4 — LINKS_TO targets are canonical (canonical_id IS NULL).
"""
from __future__ import annotations

from kdb_graph.graphdb import GraphDB
from kdb_graph.tests.conftest import (
    make_compile_result,
    make_compiled_source,
    make_page,
    make_scan,
    make_scan_entry,
)


# ---------- helpers ----------


def _alias_entry(alias_slug: str, canonical_slug: str, algorithm: str = "ledger") -> dict:
    return {
        "alias_slug": alias_slug,
        "canonical_slug": canonical_slug,
        "algorithm": algorithm,
    }


def _canonical_meta(aliases: list[dict] | None = None) -> dict:
    return {
        "algorithm_version": "1.0",
        "ledger_snapshot_sha256": "deadbeef",
        "aliases_emitted": aliases or [],
        "outgoing_link_remaps": [],
        "merged_pages": [],
    }


def _alias_of_count(gdb: GraphDB) -> int:
    r = gdb.conn.execute("MATCH ()-[r:ALIAS_OF]->() RETURN COUNT(r)")
    return int(r.get_next()[0])


def _alias_of_edge(gdb: GraphDB, alias_slug: str) -> tuple[str, str, str] | None:
    """Return (canonical_slug, algorithm, run_id) for the alias's ALIAS_OF
    edge, or None if no edge exists."""
    r = gdb.conn.execute(
        """
        MATCH (a:Entity {slug: $alias})-[r:ALIAS_OF]->(c:Entity)
        RETURN c.slug, r.algorithm, r.run_id
        """,
        {"alias": alias_slug},
    )
    if not r.has_next():
        return None
    row = r.get_next()
    return row[0], row[1], row[2]


# ---------- 1. single alias resolution ----------


def test_alias_creates_entity_with_canonical_id(graph_dir):
    """Single alias: alias Entity row exists with canonical_id pointing
    at the canonical's slug."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result(
        [cs],
        canonical_meta=_canonical_meta([_alias_entry("aapl", "apple-inc")]),
    )
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        alias = gdb.get_entity("aapl")
        canonical = gdb.get_entity("apple-inc")
    assert alias is not None
    assert alias.canonical_id == "apple-inc"
    assert canonical is not None
    assert canonical.canonical_id is None


def test_alias_of_edge_with_algorithm_provenance(graph_dir):
    """ALIAS_OF edge exists from alias to canonical, carrying the
    algorithm property from canonical_meta."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result(
        [cs],
        canonical_meta=_canonical_meta(
            [_alias_entry("aapl", "apple-inc", algorithm="ledger")]
        ),
    )
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        edge = _alias_of_edge(gdb, "aapl")
    assert edge == ("apple-inc", "ledger", "run-1")
    assert res.alias_of_upserted == 1


def test_canonical_entity_has_null_canonical_id(graph_dir):
    """Canonical page intent → Entity.canonical_id IS NULL."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result([cs])
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        canonical = gdb.get_entity("apple-inc")
    assert canonical is not None
    assert canonical.canonical_id is None


def test_supports_routes_to_canonical_not_alias(graph_dir):
    """OQ-E direct-to-canonical: Source-SUPPORTS edges land on canonical
    only. The alias receives ZERO SUPPORTS edges."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result(
        [cs],
        canonical_meta=_canonical_meta([_alias_entry("aapl", "apple-inc")]),
    )
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        # SUPPORTS edges into the canonical
        rc = gdb.conn.execute(
            "MATCH (s:Source)-[r:SUPPORTS]->(e:Entity {slug: 'apple-inc'}) RETURN COUNT(r)"
        )
        # SUPPORTS edges into the alias (should be zero per OQ-E)
        ra = gdb.conn.execute(
            "MATCH (s:Source)-[r:SUPPORTS]->(e:Entity {slug: 'aapl'}) RETURN COUNT(r)"
        )
    assert int(rc.get_next()[0]) == 1
    assert int(ra.get_next()[0]) == 0


# ---------- 2. fan-out: multiple aliases per canonical / per run ----------


def test_multiple_aliases_for_same_canonical(graph_dir):
    """Many-to-one: aapl, AAPL.US, apple both alias apple-inc; all three
    alias entities exist; three ALIAS_OF edges all land on apple-inc."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result(
        [cs],
        canonical_meta=_canonical_meta([
            _alias_entry("aapl", "apple-inc"),
            _alias_entry("aapl-us", "apple-inc"),
            _alias_entry("apple", "apple-inc"),
        ]),
    )
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        for alias in ("aapl", "aapl-us", "apple"):
            assert gdb.get_entity(alias).canonical_id == "apple-inc"
            edge = _alias_of_edge(gdb, alias)
            assert edge[0] == "apple-inc"
    assert res.alias_of_upserted == 3


def test_multiple_canonicals_each_with_aliases(graph_dir):
    """Independent canonical groups: no cross-contamination of ALIAS_OF
    targets when two canonicals each have their own alias."""
    cr = make_compile_result(
        [
            make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")]),
            make_compiled_source("KDB/raw/y.md", [make_page("microsoft")]),
        ],
        canonical_meta=_canonical_meta([
            _alias_entry("aapl", "apple-inc"),
            _alias_entry("msft", "microsoft"),
        ]),
    )
    scan = make_scan([
        make_scan_entry("KDB/raw/x.md"),
        make_scan_entry("KDB/raw/y.md"),
    ])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        assert _alias_of_edge(gdb, "aapl")[0] == "apple-inc"
        assert _alias_of_edge(gdb, "msft")[0] == "microsoft"
        # Apple's alias does not somehow point at microsoft and vice versa.
        assert gdb.get_entity("aapl").canonical_id == "apple-inc"
        assert gdb.get_entity("msft").canonical_id == "microsoft"


# ---------- 3. backward compat + no-op paths ----------


def test_pre_74_journal_no_canonical_meta_no_alias_writes(graph_dir):
    """Backward compat (D-R5-7): cr without canonical_meta produces zero
    alias entities + zero ALIAS_OF edges. Pre-#74 journals replay clean."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result([cs])  # no canonical_meta
    assert "canonical_meta" not in cr
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        stats = gdb.stats()
    assert res.alias_of_upserted == 0
    assert stats["alias_of"] == 0
    assert stats["entities"] == 1  # just the canonical


def test_empty_aliases_emitted_is_noop(graph_dir):
    """canonical_meta present but aliases_emitted empty → zero alias
    writes. Stage 6 against an empty ledger produces this shape."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result([cs], canonical_meta=_canonical_meta([]))
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        stats = gdb.stats()
    assert res.alias_of_upserted == 0
    assert stats["alias_of"] == 0
    assert stats["entities"] == 1


# ---------- 4. idempotency + flat invariant ----------


def test_rerun_idempotent_no_duplicate_alias_of(graph_dir):
    """D-R5-13 flat invariant: applying the same cr twice leaves exactly
    one ALIAS_OF per alias (drop-then-create per pass). Edge run_id
    reflects the most recent run."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result(
        [cs],
        canonical_meta=_canonical_meta([_alias_entry("aapl", "apple-inc")]),
    )
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        gdb.apply_compile_result(cr, scan, "run-2")
        # Exactly one ALIAS_OF edge from aapl
        rcount = gdb.conn.execute(
            "MATCH (a:Entity {slug: 'aapl'})-[r:ALIAS_OF]->() RETURN COUNT(r)"
        )
        assert int(rcount.get_next()[0]) == 1
        # And the edge's run_id is the latest run
        edge = _alias_of_edge(gdb, "aapl")
    assert edge[2] == "run-2"


# ---------- 5. promotion: alias → canonical re-classification ----------


def test_alias_promoted_to_canonical_clears_canonical_id_and_alias_of(
    graph_dir,
):
    """The promotion case: a slug arrives as alias in run-1, then arrives
    as a canonical page in run-2 (operator removed the alias from the
    ledger and the LLM now emits the entity directly). The slug's
    canonical_id must drop to NULL and the stale ALIAS_OF must be removed
    — otherwise C1 (canonical_id IS NULL ⇔ no outgoing ALIAS_OF) breaks."""
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    # Run 1: aapl is an alias for apple-inc
    cs1 = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr1 = make_compile_result(
        [cs1],
        canonical_meta=_canonical_meta([_alias_entry("aapl", "apple-inc")]),
    )
    # Run 2: aapl appears as a canonical page in its own right
    cs2 = make_compiled_source(
        "KDB/raw/x.md",
        [make_page("apple-inc"), make_page("aapl")],
    )
    cr2 = make_compile_result([cs2])  # no canonical_meta → no aliases

    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan, "run-1")
        # Sanity: aapl is an alias right now
        assert gdb.get_entity("aapl").canonical_id == "apple-inc"
        assert _alias_of_edge(gdb, "aapl") is not None

        gdb.apply_compile_result(cr2, scan, "run-2")
        # After promotion: canonical_id NULL, no outgoing ALIAS_OF
        promoted = gdb.get_entity("aapl")
        assert promoted.canonical_id is None
        assert _alias_of_edge(gdb, "aapl") is None
        # And the total ALIAS_OF count is zero (the only alias was promoted)
        assert _alias_of_count(gdb) == 0


# ---------- 6. orphan-detection scope (canonical only) ----------


def test_aliases_excluded_from_orphan_detection(graph_dir):
    """OQ-E: aliases never receive SUPPORTS. Phase 4 must scope orphan
    flagging to canonical entities (canonical_id IS NULL), otherwise
    every alias would be flagged orphan_candidate on first compile."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result(
        [cs],
        canonical_meta=_canonical_meta([_alias_entry("aapl", "apple-inc")]),
    )
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        alias = gdb.get_entity("aapl")
    # The alias has zero SUPPORTS but is NOT flagged orphan_candidate.
    assert alias.status == "alias"
    assert "aapl" not in res.orphans_detected


# ---------- 7. stats + provenance reporting ----------


# ---------- 8. defensive guards (degenerate inputs Stage 6 shouldn't emit) ----------


def test_self_loop_alias_is_skipped(graph_dir):
    """alias_slug == canonical_slug is a degenerate self-loop. Stage 6
    should never emit this but the adapter guards: the entry is silently
    skipped, no ALIAS_OF edge, no alias Entity created."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result(
        [cs],
        canonical_meta=_canonical_meta([
            _alias_entry("apple-inc", "apple-inc"),  # self-loop
        ]),
    )
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        # canonical's canonical_id stays NULL (guard prevented self-write)
        canonical = gdb.get_entity("apple-inc")
        stats = gdb.stats()
    assert canonical.canonical_id is None
    assert res.alias_of_upserted == 0
    assert stats["alias_of"] == 0


def test_alias_with_missing_canonical_creates_entity_but_no_edge(graph_dir):
    """Defensive: if canonical_meta.aliases_emitted references a canonical
    slug not present as an Entity in the graph (e.g. cross-source dangle
    that Stage 5 reconcile + Stage 6 merge would normally prevent), the
    alias Entity is still upserted with canonical_id set — but the
    MATCH-then-CREATE silently no-ops the ALIAS_OF edge. #74.6's C1
    verifier will catch the inconsistency."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result(
        [cs],
        canonical_meta=_canonical_meta([
            _alias_entry("aapl", "apple-inc"),       # canonical exists
            _alias_entry("msft", "microsoft"),       # canonical missing
        ]),
    )
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        # Both alias Entity rows exist; both carry canonical_id
        assert gdb.get_entity("aapl").canonical_id == "apple-inc"
        assert gdb.get_entity("msft").canonical_id == "microsoft"
        # But only the well-formed alias got an ALIAS_OF edge
        assert _alias_of_edge(gdb, "aapl") is not None
        assert _alias_of_edge(gdb, "msft") is None
    assert res.alias_of_upserted == 1


def test_stats_reports_alias_of_count(graph_dir):
    """gdb.stats()['alias_of'] reflects the count of ALIAS_OF edges
    actually written. Mirrors how 'links_to' and 'supports' are exposed."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result(
        [cs],
        canonical_meta=_canonical_meta([
            _alias_entry("aapl", "apple-inc"),
            _alias_entry("apple", "apple-inc"),
        ]),
    )
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        stats = gdb.stats()
    assert stats["alias_of"] == 2
