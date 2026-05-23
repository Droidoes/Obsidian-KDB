"""Tests for graphdb_kdb.ingestor.apply_compile_result (#63.2).

Covers the algorithm in docs/task-graphdb-kdb-blueprint.md §5 with explicit
verification for the Codex-review-driven design decisions:
- C2  SUPPORTS replacement clears stale edges on source recompile
- M3  MOVED transfers SUPPORTS to destination
- C3  timestamp offset round-trip (STRING + local ISO)
- NEW M1  Phase 1 scan refresh does NOT mutate compile-state fields
- NEW C2  MOVED reconciliation writes only Source-schema-defined fields
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


# ---------- 1. single + multi page upsert ----------

def test_single_page_upsert(graph_dir):
    cr = make_compile_result([
        make_compiled_source("KDB/raw/a.md", [make_page("alpha")])
    ])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        page = gdb.get_entity("alpha")
        stats = gdb.stats()
    assert res.entities_upserted == 1
    assert res.sources_upserted == 1
    assert page is not None
    assert page.slug == "alpha"
    assert page.first_run_id == "run-1"
    assert page.last_run_id == "run-1"
    assert stats["entities"] == 1
    assert stats["sources"] == 1


def test_multi_page_upsert(graph_dir):
    pages = [make_page(f"page-{i}") for i in range(3)]
    cr = make_compile_result([make_compiled_source("KDB/raw/a.md", pages)])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        stats = gdb.stats()
    assert res.entities_upserted == 3
    assert stats["entities"] == 3


# ---------- 2. outgoing edges replace (add / remove / change) ----------

def test_outgoing_edges_replace_add(graph_dir):
    """Re-apply with extended outgoing_links adds new LINKS_TO edges."""
    pages_v1 = [
        make_page("a", outgoing_links=["b"]),
        make_page("b"),
    ]
    cr1 = make_compile_result([make_compiled_source("KDB/raw/s.md", pages_v1)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan, "run-1")
        s1 = gdb.stats()
    assert s1["links_to"] == 1

    pages_v2 = [
        make_page("a", outgoing_links=["b", "c"]),
        make_page("b"),
        make_page("c"),
    ]
    cr2 = make_compile_result([make_compiled_source("KDB/raw/s.md", pages_v2)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr2, scan, "run-2")
        s2 = gdb.stats()
    assert s2["links_to"] == 2  # a→b, a→c


def test_outgoing_edges_replace_remove(graph_dir):
    """Re-apply with shortened outgoing_links removes stale LINKS_TO edges."""
    pages_v1 = [
        make_page("a", outgoing_links=["b", "c"]),
        make_page("b"),
        make_page("c"),
    ]
    cr1 = make_compile_result([make_compiled_source("KDB/raw/s.md", pages_v1)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan, "run-1")
        s1 = gdb.stats()
    assert s1["links_to"] == 2

    pages_v2 = [
        make_page("a", outgoing_links=["b"]),
        make_page("b"),
        make_page("c"),
    ]
    cr2 = make_compile_result([make_compiled_source("KDB/raw/s.md", pages_v2)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr2, scan, "run-2")
        s2 = gdb.stats()
    assert s2["links_to"] == 1


def test_outgoing_edges_replace_change(graph_dir):
    """Re-apply with disjoint outgoing_links swaps the edge set."""
    pages_v1 = [
        make_page("a", outgoing_links=["b"]),
        make_page("b"),
        make_page("c"),
        make_page("d"),
    ]
    cr1 = make_compile_result([make_compiled_source("KDB/raw/s.md", pages_v1)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan, "run-1")

    pages_v2 = [
        make_page("a", outgoing_links=["c", "d"]),
        make_page("b"),
        make_page("c"),
        make_page("d"),
    ]
    cr2 = make_compile_result([make_compiled_source("KDB/raw/s.md", pages_v2)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr2, scan, "run-2")
        # Verify a→b is gone; a→c and a→d exist.
        r = gdb.conn.execute(
            "MATCH (a:Entity {slug: 'a'})-[:LINKS_TO]->(t) RETURN t.slug ORDER BY t.slug"
        )
        targets = []
        while r.has_next():
            targets.append(r.get_next()[0])
    assert targets == ["c", "d"]


# ---------- 3. SUPPORTS edges ----------

def test_supports_upsert(graph_dir):
    """A source compiling N pages creates N SUPPORTS edges."""
    pages = [make_page("a"), make_page("b")]
    cr = make_compile_result([make_compiled_source("KDB/raw/s.md", pages)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        stats = gdb.stats()
    assert res.supports_upserted == 2
    assert stats["supports"] == 2


def test_supports_replacement_clears_stale(graph_dir):
    """Codex C2: source recompile dropping a page clears its SUPPORTS edge."""
    pages_v1 = [make_page("a"), make_page("b")]
    cr1 = make_compile_result([make_compiled_source("KDB/raw/s.md", pages_v1)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan, "run-1")
        assert gdb.stats()["supports"] == 2

    # Recompile: source now produces only page-a (drops page-b).
    pages_v2 = [make_page("a")]
    cr2 = make_compile_result([make_compiled_source("KDB/raw/s.md", pages_v2)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr2, scan, "run-2")
        # Source supports only 'a' now.
        r = gdb.conn.execute(
            "MATCH (s:Source {source_id: 'KDB/raw/s.md'})-[:SUPPORTS]->(p) RETURN p.slug"
        )
        targets = []
        while r.has_next():
            targets.append(r.get_next()[0])
    assert targets == ["a"]


# ---------- 4. MOVED reconciliation ----------

def test_moved_source_transfers_supports(graph_dir):
    """Codex M3: MOVED transfers active SUPPORTS edges from old to new Source."""
    old_sid = "KDB/raw/old.md"
    new_sid = "KDB/raw/new.md"
    pages = [make_page("alpha"), make_page("beta")]
    cr1 = make_compile_result([make_compiled_source(old_sid, pages)])
    scan1 = make_scan([make_scan_entry(old_sid)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan1, "run-1")
        assert gdb.stats()["supports"] == 2

    # Next run: source moved old→new
    scan2 = make_scan(
        files=[make_scan_entry(new_sid)],
        to_reconcile=[{
            "type": "MOVED",
            "from_source_id": old_sid,
            "to_source_id": new_sid,
        }],
    )
    cr2 = make_compile_result([])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr2, scan2, "run-2")
        # New source should hold both SUPPORTS edges.
        r = gdb.conn.execute(
            "MATCH (s:Source {source_id: $sid})-[:SUPPORTS]->(p) RETURN p.slug ORDER BY p.slug",
            {"sid": new_sid},
        )
        new_targets = []
        while r.has_next():
            new_targets.append(r.get_next()[0])
        # Old source should hold zero SUPPORTS edges.
        r2 = gdb.conn.execute(
            "MATCH (s:Source {source_id: $sid})-[:SUPPORTS]->(p) RETURN p.slug",
            {"sid": old_sid},
        )
        old_targets = []
        while r2.has_next():
            old_targets.append(r2.get_next()[0])
    assert new_targets == ["alpha", "beta"]
    assert old_targets == []


def test_moved_reconcile_marks_old_source(graph_dir):
    """MOVED marks old Source status='moved' and sets moved_to."""
    old_sid = "KDB/raw/old.md"
    new_sid = "KDB/raw/new.md"
    cr1 = make_compile_result([
        make_compiled_source(old_sid, [make_page("alpha")])
    ])
    scan1 = make_scan([make_scan_entry(old_sid)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan1, "run-1")

    scan2 = make_scan(
        files=[make_scan_entry(new_sid)],
        to_reconcile=[{
            "type": "MOVED",
            "from_source_id": old_sid,
            "to_source_id": new_sid,
        }],
    )
    cr2 = make_compile_result([])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr2, scan2, "run-2")
        old = gdb.get_source(old_sid)
    assert old is not None
    assert old.status == "moved"
    assert old.moved_to == new_sid


# ---------- 5. DELETED reconciliation ----------

def test_deleted_reconcile_marks_source(graph_dir):
    sid = "KDB/raw/gone.md"
    cr1 = make_compile_result([make_compiled_source(sid, [make_page("zeta")])])
    scan1 = make_scan([make_scan_entry(sid)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan1, "run-1")

    scan2 = make_scan(
        files=[],
        to_reconcile=[{"type": "DELETED", "source_id": sid}],
    )
    cr2 = make_compile_result([])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr2, scan2, "run-2")
        s = gdb.get_source(sid)
        # SUPPORTS edges dropped, so zeta should be orphaned
        r = gdb.conn.execute("MATCH (p:Entity {slug: 'zeta'}) RETURN p.status")
        zeta_status = r.get_next()[0] if r.has_next() else None
    assert s is not None
    assert s.status == "deleted"
    assert zeta_status == "orphan_candidate"


# ---------- 6. orphan detection + revival ----------

def test_orphan_detection_flags_page_with_no_supports(graph_dir):
    """A page whose only supporting source recompiles without it becomes orphan_candidate."""
    src = "KDB/raw/s.md"
    pages_v1 = [make_page("a"), make_page("b")]
    cr1 = make_compile_result([make_compiled_source(src, pages_v1)])
    scan = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan, "run-1")

    # Source drops page 'b'.
    cr2 = make_compile_result([make_compiled_source(src, [make_page("a")])])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr2, scan, "run-2")
        page_b = gdb.get_entity("b")
    assert "b" in res.orphans_detected
    assert page_b is not None
    assert page_b.status == "orphan_candidate"


def test_orphan_revival_on_resupport(graph_dir):
    """A page re-supported by a new compile transitions back to active."""
    src = "KDB/raw/s.md"
    # Initial: a, b. Then drop b → orphan. Then re-add b → revival.
    scan = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a"), make_page("b")])]),
            scan, "r1",
        )
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a")])]),
            scan, "r2",
        )
        assert gdb.get_entity("b").status == "orphan_candidate"

        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a"), make_page("b")])]),
            scan, "r3",
        )
        b = gdb.get_entity("b")
    assert b.status == "active"


# ---------- 7. transaction rollback ----------

def test_transaction_rollback_on_bad_input(graph_dir, monkeypatch):
    """If a helper raises mid-ingestion, the transaction rolls back."""
    src = "KDB/raw/a.md"
    cr_seed = make_compile_result([make_compiled_source(src, [make_page("alpha")])])
    scan_seed = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr_seed, scan_seed, "run-seed")
        seed_stats = gdb.stats()

    # Patch _upsert_entity to raise mid-Phase-3.
    def boom(*args, **kwargs):
        raise RuntimeError("simulated mid-ingest failure")
    monkeypatch.setattr(ingestor, "_upsert_entity", boom)

    src2 = "KDB/raw/b.md"
    cr_fail = make_compile_result([make_compiled_source(src2, [make_page("beta")])])
    scan_fail = make_scan([make_scan_entry(src), make_scan_entry(src2)])

    with GraphDB(graph_dir) as gdb:
        with pytest.raises(RuntimeError, match="simulated mid-ingest"):
            gdb.apply_compile_result(cr_fail, scan_fail, "run-fail")
        post_stats = gdb.stats()
    # Phase 1 had already upserted src2 — rollback must undo that too.
    assert post_stats == seed_stats


# ---------- 8. idempotent re-apply ----------

def test_idempotent_reapply_same_run(graph_dir):
    """Applying the same compile_result twice converges to the same end state."""
    src = "KDB/raw/s.md"
    pages = [make_page("a", outgoing_links=["b"]), make_page("b")]
    cr = make_compile_result([make_compiled_source(src, pages)])
    scan = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        s1 = gdb.stats()
        gdb.apply_compile_result(cr, scan, "run-1-replay")
        s2 = gdb.stats()
    assert s1 == s2


# ---------- 9. multiple sources in one run ----------

def test_multiple_sources_in_one_run(graph_dir):
    """A run with N compiled_sources upserts N Source nodes + their SUPPORTS edges."""
    cs1 = make_compiled_source("KDB/raw/s1.md", [make_page("a"), make_page("b")])
    cs2 = make_compiled_source("KDB/raw/s2.md", [make_page("c")])
    cr = make_compile_result([cs1, cs2])
    scan = make_scan([
        make_scan_entry("KDB/raw/s1.md"),
        make_scan_entry("KDB/raw/s2.md"),
    ])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        stats = gdb.stats()
    assert res.sources_upserted == 2
    assert res.entities_upserted == 3
    assert res.supports_upserted == 3
    assert stats == {
        "entities": 3, "sources": 2, "links_to": 0, "supports": 3,
        "alias_of": 0, "domains": 0, "belongs_to": 0,
        # #83/#84 v2.2 — Claim layer counters all zero (no Claims written by ingestion).
        "claims": 0, "evidences": 0, "about": 0,
        "supersedes": 0, "contradicts": 0, "qualifies": 0,
    }


# ---------- 10. timestamp offset round-trip (Codex C3) ----------

def test_timestamp_offset_roundtrip(graph_dir):
    """ISO timestamp with local offset is preserved through write + read.

    Per project rule `feedback_local_time_everywhere`: storing as STRING
    avoids Kuzu's UTC normalization that the native TIMESTAMP type would apply.
    """
    iso = "2026-05-13T22:30:00-04:00"
    src = "KDB/raw/a.md"
    cr = make_compile_result([make_compiled_source(src, [make_page("alpha")])])
    scan = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1", now=iso)
        page = gdb.get_entity("alpha")
        source = gdb.get_source(src)
    assert page.created_at == iso
    assert page.updated_at == iso
    assert source.first_seen_at == iso
    assert source.last_ingested_at == iso


# ---------- 11. Phase 1 does NOT mutate compile-state (Codex v2 NEW M1) ----------

def test_phase1_does_not_mutate_ingest_state(graph_dir):
    """Scan-only run does NOT update last_ingested_at / ingest_state / ingest_count.

    Codex v2 NEW MATERIAL #1: pre-fix, _upsert_source_from_scan set
    last_ingested_at (then-named last_compiled_at) during scan refresh,
    making unchanged sources look freshly compiled. The Phase 1/Phase 3 split fixes this.
    """
    src = "KDB/raw/a.md"
    t1 = "2026-05-13T10:00:00-04:00"
    t2 = "2026-05-13T11:00:00-04:00"

    # Initial compile run.
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("alpha")])]),
            make_scan([make_scan_entry(src, hash_="sha256:v1")]),
            "run-1", now=t1,
        )
        s1 = gdb.get_source(src)
    assert s1.ingest_count == 1
    assert s1.ingest_state == "compiled"
    assert s1.last_ingested_at == t1

    # Scan-only run (no compiled_sources). Phase 1 fires; Phase 3 does NOT.
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(
            make_compile_result([]),
            make_scan([make_scan_entry(src, hash_="sha256:v2")]),
            "run-2", now=t2,
        )
        s2 = gdb.get_source(src)
    # Compile-state fields are UNCHANGED.
    assert s2.ingest_count == 1
    assert s2.ingest_state == "compiled"
    assert s2.last_ingested_at == t1  # still the original compile timestamp
    # Scan-derived fields ARE refreshed.
    assert s2.hash == "sha256:v2"
    assert s2.last_seen_at == t2


# ---------- 12. MOVED writes only schema fields (Codex v2 NEW C2) ----------

def test_moved_writes_only_schema_fields(graph_dir):
    """MOVED reconciliation Cypher uses only Source-schema-defined fields.

    Codex v2 NEW C2: pre-fix, the Cypher tried to set old.updated_at, but
    Source schema has no updated_at field — that would fail at runtime
    against a schema-enforced Kuzu table. The fix uses last_seen_at instead.
    """
    old_sid = "KDB/raw/old.md"
    new_sid = "KDB/raw/new.md"
    t1 = "2026-05-13T10:00:00-04:00"
    t2 = "2026-05-13T11:00:00-04:00"

    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(old_sid, [make_page("zeta")])]),
            make_scan([make_scan_entry(old_sid)]),
            "run-1", now=t1,
        )

    # MOVED reconcile — should not raise.
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(
            make_compile_result([]),
            make_scan(
                files=[make_scan_entry(new_sid)],
                to_reconcile=[{
                    "type": "MOVED",
                    "from_source_id": old_sid,
                    "to_source_id": new_sid,
                }],
            ),
            "run-2", now=t2,
        )
        old = gdb.get_source(old_sid)
    assert old.status == "moved"
    assert old.moved_to == new_sid
    assert old.last_run_id == "run-2"
    assert old.last_seen_at == t2  # Used in place of the non-existent updated_at.
