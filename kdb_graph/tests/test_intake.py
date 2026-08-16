"""Tests for kdb_graph.intake.apply_compile_result (#63.2).

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

from kdb_graph import intake
from kdb_graph.graphdb import GraphDB
from kdb_graph.tests.conftest import (
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


# ---------- 1b. Task #136: per-source wiring + PendingLink drain ----------

def _count(gdb, query: str) -> int:
    r = gdb.conn.execute(query)
    return int(r.get_next()[0]) if r.has_next() else 0


def _rows(gdb, query: str) -> list[list]:
    r = gdb.conn.execute(query)
    out = []
    while r.has_next():
        out.append(list(r.get_next()))
    return out


_PENDING_Q = ("MATCH (p:PendingLink) RETURN p.link_id, p.source_slug, "
              "p.target_slug, p.first_run_id, p.last_run_id ORDER BY p.link_id")


def test_pending_created_for_unresolved_target(graph_dir):
    """A link whose target doesn't exist yet is pended durably (not silently
    skipped): no edge, one PendingLink row with the right shape (#136)."""
    cr = make_compile_result([
        make_compiled_source("KDB/raw/a.md", [make_page("a", outgoing_links=["b"])])])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(cr, scan, "run-1")
        n_edges = _count(gdb, "MATCH ()-[r:LINKS_TO]->() RETURN COUNT(r)")
        pendings = _rows(gdb, _PENDING_Q)
    assert n_edges == 0
    assert res.links_pended == 1
    assert res.links_drained == 0
    assert pendings == [["a|b", "a", "b", "run-1", "run-1"]]


def test_drain_on_target_arrival(graph_dir):
    """A later commit that upserts the pended target drains the ledger row in
    the same txn: edge created, pending deleted, links_drained counted."""
    cr1 = make_compile_result([
        make_compiled_source("KDB/raw/a.md", [make_page("a", outgoing_links=["b"])])])
    cr2 = make_compile_result([
        make_compiled_source("KDB/raw/b.md", [make_page("b")])])
    scan1 = make_scan([make_scan_entry("KDB/raw/a.md")])
    scan2 = make_scan([make_scan_entry("KDB/raw/b.md")])
    edge_q = ("MATCH (:Entity {slug: 'a'})-[r:LINKS_TO]->(:Entity {slug: 'b'}) "
              "RETURN COUNT(r)")
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan1, "run-1")
        assert _count(gdb, edge_q) == 0
        res2 = gdb.apply_compile_result(cr2, scan2, "run-2")
        after = _count(gdb, edge_q)
        pendings = _rows(gdb, _PENDING_Q)
    assert after == 1                # b's commit drained a|b
    assert res2.links_drained == 1
    assert pendings == []


def test_pending_merge_idempotent(graph_dir):
    """Same source re-pending the same absent target keeps ONE row (MERGE on
    link_id): first_run_id preserved, last_run_id bumped, no re-create count."""
    cr = make_compile_result([
        make_compiled_source("KDB/raw/a.md", [make_page("a", outgoing_links=["b"])])])
    scan = make_scan([make_scan_entry("KDB/raw/a.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        res2 = gdb.apply_compile_result(cr, scan, "run-2")
        pendings = _rows(gdb, _PENDING_Q)
    assert res2.links_pended == 0    # re-pend is a merge, not a create
    assert pendings == [["a|b", "a", "b", "run-1", "run-2"]]


def test_no_duplicate_edges_on_recommit(graph_dir):
    """Re-committing an unchanged source re-runs drop+recreate: edge count
    unchanged, no duplicate LINKS_TO, no pendings."""
    cr = make_compile_result([
        make_compiled_source("KDB/raw/s.md", [
            make_page("a", outgoing_links=["b"]), make_page("b")])])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        gdb.apply_compile_result(cr, scan, "run-2")
        n_edges = _count(gdb, "MATCH ()-[r:LINKS_TO]->() RETURN COUNT(r)")
        pendings = _rows(gdb, _PENDING_Q)
    assert n_edges == 1
    assert pendings == []


def test_stale_pending_cleared_on_rewire(graph_dir):
    """Current-state replacement covers the ledger: a recompiled page that
    DROPS a link must not leave a stale pend that would wire it later
    (batch-equivalence: the batch never wires a link the final body lacks)."""
    src = "KDB/raw/a.md"
    scan = make_scan([make_scan_entry(src)])
    cr_link = make_compile_result([
        make_compiled_source(src, [make_page("a", outgoing_links=["x"])])])
    cr_nolink = make_compile_result([
        make_compiled_source(src, [make_page("a")])])
    cr_x = make_compile_result([
        make_compiled_source("KDB/raw/x.md", [make_page("x")])])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr_link, scan, "run-1")
        assert _rows(gdb, _PENDING_Q) == [["a|x", "a", "x", "run-1", "run-1"]]
        gdb.apply_compile_result(cr_nolink, scan, "run-2")
        assert _rows(gdb, _PENDING_Q) == []      # stale pend GC'd at rewire
        gdb.apply_compile_result(
            cr_x, make_scan([make_scan_entry("KDB/raw/x.md")]), "run-3")
        n_edges = _count(gdb, "MATCH ()-[r:LINKS_TO]->() RETURN COUNT(r)")
    assert n_edges == 0              # x's arrival must NOT wire the dropped link


def test_pending_gc_on_source_delete(graph_dir):
    """DELETED-source erasure GCs pendings SOURCED at the erased pages (their
    carrier is gone); pendings keyed on an erased page as TARGET survive — a
    later source may legitimately re-emit that slug (#136 §3.3)."""
    s1, s2 = "KDB/raw/gone.md", "KDB/raw/keep.md"
    cr1 = make_compile_result([
        make_compiled_source(s1, [make_page("a", outgoing_links=["ghost"])]),
        make_compiled_source(s2, [make_page("b", outgoing_links=["ghost2"])]),
    ])
    scan1 = make_scan([make_scan_entry(s1), make_scan_entry(s2)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan1, "run-1")
        assert [r[0] for r in _rows(gdb, _PENDING_Q)] == ["a|ghost", "b|ghost2"]

        # Deleting s1 erases page a → a's outgoing pend dies with it.
        gdb.apply_compile_result(
            make_compile_result([]),
            make_scan([make_scan_entry(s2)],
                      to_reconcile=[{"type": "DELETED", "source_id": s1}]),
            "run-2")
        assert [r[0] for r in _rows(gdb, _PENDING_Q)] == ["b|ghost2"]

        # b re-pends the now-erased 'a' — target-keyed pends on erased slugs
        # legitimately re-form and SURVIVE (the re-emit revival path).
        gdb.apply_compile_result(
            make_compile_result([
                make_compiled_source(s2, [make_page("b", outgoing_links=["ghost2", "a"])])]),
            make_scan([make_scan_entry(s2)]), "run-3")
        assert [r[0] for r in _rows(gdb, _PENDING_Q)] == ["b|a", "b|ghost2"]

        # Deleting s2 GCs b's outgoing pends (incl. the one keyed on erased
        # 'a' — its CARRIER is now gone too).
        gdb.apply_compile_result(
            make_compile_result([]),
            make_scan([], to_reconcile=[{"type": "DELETED", "source_id": s2}]),
            "run-4")
        assert _rows(gdb, _PENDING_Q) == []


def test_drain_stress_pendings_at_scale(graph_dir):
    """R1 pin: drain + selective-GC lookups are PendingLink scans (no secondary
    index assumed) — must stay correct and cheap at scale. 2k sources pend the
    same absent target in one commit; the target's arrival drains all 2k.
    (Production commits are per-source, ~10 pages against a small ledger; this
    mega-commit is the deliberately harsher shape.)"""
    import time
    n = 2_000
    cr = make_compile_result([
        make_compiled_source(
            f"KDB/raw/s{i}.md", [make_page(f"src-{i}", outgoing_links=["hub"])])
        for i in range(n)
    ])
    scan = make_scan([make_scan_entry(f"KDB/raw/s{i}.md") for i in range(n)])
    with GraphDB(graph_dir) as gdb:
        t0 = time.monotonic()
        gdb.apply_compile_result(cr, scan, "run-1")
        assert _count(gdb, "MATCH (p:PendingLink) RETURN COUNT(p)") == n
        res = gdb.apply_compile_result(
            make_compile_result(
                [make_compiled_source("KDB/raw/hub.md", [make_page("hub")])]),
            make_scan([make_scan_entry("KDB/raw/hub.md")]), "run-2")
        elapsed = time.monotonic() - t0
        n_edges = _count(gdb, "MATCH ()-[r:LINKS_TO]->() RETURN COUNT(r)")
        n_pend = _count(gdb, "MATCH (p:PendingLink) RETURN COUNT(p)")
    assert res.links_drained == n
    assert n_edges == n
    assert n_pend == 0
    # Generous smoke bound — catches asymptotic blowup, not a perf gate.
    assert elapsed < 120, f"2k-pend commit + drain took {elapsed:.1f}s"


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


# ---------- 5. DELETED reconciliation (erasure — #130 R-130-4) ----------

def test_deleted_reconcile_erases_sole_supported_page(graph_dir):
    """#130: source deletion is total erasure. A page whose ONLY SUPPORTS came
    from the deleted source is DETACH DELETEd — not deprecated, no residue."""
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
        res = gdb.apply_compile_result(cr2, scan2, "run-2")
        s = gdb.get_source(sid)
        zeta = gdb.get_entity("zeta")
    assert s is not None
    assert s.status == "deleted"
    assert zeta is None  # erased, not deprecated
    assert {"slug": "zeta", "page_type": "concept"} in res.erased_pages


def test_deleted_reconcile_keeps_dual_supported_page_active(graph_dir):
    """A page with a second supporting source survives the deletion active,
    with exactly one SUPPORTS edge remaining."""
    s1, s2 = "KDB/raw/one.md", "KDB/raw/two.md"
    scan = make_scan([make_scan_entry(s1), make_scan_entry(s2)])
    cr1 = make_compile_result([
        make_compiled_source(s1, [make_page("shared")]),
        make_compiled_source(s2, [make_page("shared")]),
    ])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan, "run-1")

    scan2 = make_scan(
        files=[make_scan_entry(s2)],
        to_reconcile=[{"type": "DELETED", "source_id": s1}],
    )
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(make_compile_result([]), scan2, "run-2")
        shared = gdb.get_entity("shared")
        r = gdb.conn.execute(
            "MATCH (:Source)-[r:SUPPORTS]->(:Entity {slug: 'shared'}) RETURN COUNT(r)"
        )
        n_supports = int(r.get_next()[0])
    assert shared is not None
    assert shared.status == "active"
    assert n_supports == 1
    assert res.erased_pages == []


def _alias_entry(alias_slug: str, canonical_slug: str) -> dict:
    return {"alias_slug": alias_slug, "canonical_slug": canonical_slug,
            "algorithm": "ledger"}


def _canonical_meta(aliases: list[dict]) -> dict:
    return {
        "algorithm_version": "1.0",
        "ledger_snapshot_sha256": "deadbeef",
        "aliases_emitted": aliases,
        "outgoing_link_remaps": [],
        "merged_pages": [],
    }


def test_deleted_reconcile_erases_alias_rows(graph_dir):
    """Alias rows are identity assertions about the canonical — erasure removes
    them with it (no dangling aliases)."""
    sid = "KDB/raw/x.md"
    cr1 = make_compile_result(
        [make_compiled_source(sid, [make_page("apple-inc")])],
        canonical_meta=_canonical_meta([_alias_entry("aapl", "apple-inc")]),
    )
    scan1 = make_scan([make_scan_entry(sid)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan1, "run-1")
        assert gdb.get_entity("aapl") is not None

    scan2 = make_scan(files=[], to_reconcile=[{"type": "DELETED", "source_id": sid}])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(make_compile_result([]), scan2, "run-2")
        assert gdb.get_entity("apple-inc") is None
        assert gdb.get_entity("aapl") is None


def test_deleted_reconcile_reports_dead_links(graph_dir):
    """Surviving pages that linked to an erased page are reported (never
    rewritten) via IntakeResult.erased_dead_links; the edge dies with the node."""
    s1, s2 = "KDB/raw/keep.md", "KDB/raw/gone.md"
    scan = make_scan([make_scan_entry(s1), make_scan_entry(s2)])
    cr1 = make_compile_result([
        make_compiled_source(s1, [make_page("a", outgoing_links=["zeta"])]),
        make_compiled_source(s2, [make_page("zeta")]),
    ])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan, "run-1")

    scan2 = make_scan(
        files=[make_scan_entry(s1)],
        to_reconcile=[{"type": "DELETED", "source_id": s2}],
    )
    with GraphDB(graph_dir) as gdb:
        res = gdb.apply_compile_result(make_compile_result([]), scan2, "run-2")
        r = gdb.conn.execute("MATCH ()-[r:LINKS_TO]->() RETURN COUNT(r)")
        n_edges = int(r.get_next()[0])
    assert {"slug": "zeta", "page_type": "concept"} in res.erased_pages
    assert res.erased_dead_links == [{"from_slug": "a", "to_slug": "zeta"}]
    assert n_edges == 0


# ---------- 6. deprecation + revival (#130) ----------

def test_deprecation_flags_page_with_no_supports(graph_dir):
    """A page whose only supporting source recompiles without it becomes deprecated
    (#130 R-130-1 — the node stays, invisible to active-readers, revivable)."""
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
    assert {"slug": "b", "page_type": "concept"} in res.deprecations_detected
    assert page_b is not None
    assert page_b.status == "deprecated"


def test_deprecation_revival_on_resupport(graph_dir):
    """A page re-supported by a new compile transitions back to active."""
    src = "KDB/raw/s.md"
    # Initial: a, b. Then drop b → deprecated. Then re-add b → revival.
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
        assert gdb.get_entity("b").status == "deprecated"

        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a"), make_page("b")])]),
            scan, "r3",
        )
        b = gdb.get_entity("b")
    assert b.status == "active"


# ---------- 7. transaction rollback ----------

def test_transaction_rollback_on_bad_input(graph_dir, monkeypatch):
    """If a helper raises mid-intake, the transaction rolls back."""
    src = "KDB/raw/a.md"
    cr_seed = make_compile_result([make_compiled_source(src, [make_page("alpha")])])
    scan_seed = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr_seed, scan_seed, "run-seed")
        seed_stats = gdb.stats()

    # Patch _upsert_entity to raise mid-Phase-3.
    def boom(*args, **kwargs):
        raise RuntimeError("simulated mid-intake failure")
    monkeypatch.setattr(intake, "_upsert_entity", boom)

    src2 = "KDB/raw/b.md"
    cr_fail = make_compile_result([make_compiled_source(src2, [make_page("beta")])])
    scan_fail = make_scan([make_scan_entry(src), make_scan_entry(src2)])

    with GraphDB(graph_dir) as gdb:
        with pytest.raises(RuntimeError, match="simulated mid-intake"):
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
        # #136 v2.5 — PendingLink ledger counter.
        "pending_links": 0,
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
    assert s1.ingest_state == "in_graph_db"
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
    assert s2.ingest_state == "in_graph_db"
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


# ---------- 13. Pass-1 frontmatter flows into Source node (D-89-17) ----------

def test_ingest_source_writes_summary_author_domain_from_frontmatter(graph_dir):
    """When compile_result carries source_meta with Pass-1-derived fields,
    intake MERGE's Source with summary/author/domain populated (D-89-17)."""
    src = "KDB/raw/enriched.md"
    source_meta = {
        "summary": "A note about value investing principles. Themes: margin-of-safety, compounding.",
        "author": "Warren Buffett",
        "domain": "value-investing",
        "source_type": "personal-note",
    }
    cr = make_compile_result([
        make_compiled_source(src, [make_page("alpha")], source_meta=source_meta)
    ])
    scan = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        source = gdb.get_source(src)
    assert source.summary == "A note about value investing principles. Themes: margin-of-safety, compounding."
    assert source.author == "Warren Buffett"
    assert source.domain == "value-investing"
    # Bug #1 fix (v0.2.2): source_type from Pass-1 frontmatter now flows through,
    # replacing the first-create default "obsidian-kdb-raw".
    assert source.source_type == "personal-note"


def test_ingest_source_without_source_meta_leaves_columns_null(graph_dir):
    """When compile_result has no source_meta, summary/author/domain stay NULL
    (backward-compat: existing compile_results without source_meta remain valid).
    source_type stays at the first-create default per Bug #1 fix backward-compat."""
    src = "KDB/raw/plain.md"
    cr = make_compile_result([
        make_compiled_source(src, [make_page("beta")])
    ])
    scan = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        source = gdb.get_source(src)
    assert source.summary is None
    assert source.author is None
    assert source.domain is None
    assert source.source_type == "obsidian-kdb-raw"


def test_ingest_source_meta_without_source_type_preserves_default(graph_dir):
    """Bug #1 fix backward-compat: source_meta dict missing source_type key
    (e.g., pre-v0.2.2 compile_results) leaves source_type at first-create default."""
    src = "KDB/raw/partial.md"
    source_meta = {
        "summary": "Some summary",
        "author": "Some Author",
        "domain": "personal-finance",
        # source_type intentionally absent
    }
    cr = make_compile_result([
        make_compiled_source(src, [make_page("gamma")], source_meta=source_meta)
    ])
    scan = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        source = gdb.get_source(src)
    assert source.summary == "Some summary"
    assert source.source_type == "obsidian-kdb-raw"


# ---------- Task #136: per-source deprecation diff ----------

def test_per_source_deprecation_diff(graph_dir):
    """Recompile dropping a page flips it deprecated IN the commit txn (the
    end-of-run whole-graph scan is deleted); sibling pages stay untouched."""
    src = "KDB/raw/s.md"
    scan = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a"), make_page("b")])]),
            scan, "r1")
        res = gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a")])]),
            scan, "r2")
        a, b = gdb.get_entity("a"), gdb.get_entity("b")
    assert res.deprecations_detected == [{"slug": "b", "page_type": "concept"}]
    assert b.status == "deprecated"
    assert a.status == "active"


def test_revive_on_resupport_at_commit(graph_dir):
    """Cross-source: a second source re-supporting a deprecated page revives it
    in the re-supporter's own commit txn (the #136 R2 transient window
    self-heals at the re-supporter's commit)."""
    s1, s2 = "KDB/raw/one.md", "KDB/raw/two.md"
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(s1, [make_page("shared")])]),
            make_scan([make_scan_entry(s1)]), "r1")
        res_drop = gdb.apply_compile_result(
            make_compile_result([make_compiled_source(s1, [make_page("other")])]),
            make_scan([make_scan_entry(s1)]), "r2")
        assert res_drop.deprecations_detected == [
            {"slug": "shared", "page_type": "concept"}]
        assert gdb.get_entity("shared").status == "deprecated"
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(s2, [make_page("shared")])]),
            make_scan([make_scan_entry(s2)]), "r3")
        revived = gdb.get_entity("shared")
    assert revived.status == "active"


def test_shared_page_survives_single_source_drop(graph_dir):
    """Deprecation exactness: losing ONE of two supporters leaves the page's
    remaining SUPPORTS intact → stays active, no deprecation recorded."""
    s1, s2 = "KDB/raw/one.md", "KDB/raw/two.md"
    scan = make_scan([make_scan_entry(s1), make_scan_entry(s2)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(
            make_compile_result([
                make_compiled_source(s1, [make_page("shared")]),
                make_compiled_source(s2, [make_page("shared")]),
            ]), scan, "r1")
        res = gdb.apply_compile_result(
            make_compile_result([make_compiled_source(s1, [make_page("other")])]),
            make_scan([make_scan_entry(s1)]), "r2")
        shared = gdb.get_entity("shared")
    assert res.deprecations_detected == []
    assert shared.status == "active"


def test_aliases_not_deprecated(graph_dir):
    """Alias rows (canonical_id set) never carry SUPPORTS; the per-source diff
    must never flag them — only emitted/lost canonical pages are eligible."""
    sid = "KDB/raw/x.md"
    cr1 = make_compile_result(
        [make_compiled_source(sid, [make_page("apple-inc")])],
        canonical_meta=_canonical_meta([_alias_entry("aapl", "apple-inc")]),
    )
    scan = make_scan([make_scan_entry(sid)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr1, scan, "run-1")
        res = gdb.apply_compile_result(
            make_compile_result([make_compiled_source(sid, [])]), scan, "run-2")
        alias = gdb.get_entity("aapl")
        canon = gdb.get_entity("apple-inc")
    assert res.deprecations_detected == [
        {"slug": "apple-inc", "page_type": "concept"}]
    assert canon.status == "deprecated"
    assert alias.status == "alias"       # untouched by the diff


# ---------- 3. #115 T2.4: graph-owned edge derivation from body wikilinks ----------

def _body_page(slug, body, *, page_type="concept", title=None):
    """New #115 page shape: NO outgoing_links key — links live in the body."""
    return {"slug": slug, "page_type": page_type,
            "title": title or f"Title for {slug}", "body": body}


class TestBodyWikilinkEdgeDerivation:
    def test_body_links_become_edges(self, graph_dir):
        """New-shape page (no outgoing_links key): LINKS_TO edges derive
        from body wikilinks."""
        cr = make_compile_result([make_compiled_source("KDB/raw/s.md", [
            _body_page("a", "Links [[b]] and [[c|see c]]."),
            _body_page("b", "x"),
            _body_page("c", "y"),
        ])])
        scan = make_scan([make_scan_entry("KDB/raw/s.md")])
        with GraphDB(graph_dir) as gdb:
            gdb.apply_compile_result(cr, scan, "run-1")
            s = gdb.stats()
        assert s["links_to"] == 2          # a→b, a→c from the body

    def test_legacy_outgoing_links_preferred_over_body(self, graph_dir):
        """Historical payload (outgoing_links present): the stored list wins
        over the body — read-compat, never a merge."""
        cr = make_compile_result([make_compiled_source("KDB/raw/s.md", [
            make_page("a", outgoing_links=["b"], body="Body mentions [[c]]."),
            make_page("b"), make_page("c"),
        ])])
        scan = make_scan([make_scan_entry("KDB/raw/s.md")])
        with GraphDB(graph_dir) as gdb:
            gdb.apply_compile_result(cr, scan, "run-1")
            s = gdb.stats()
        assert s["links_to"] == 1          # only a→b (stored list), NOT a→c

    def test_recompile_body_only_page_preserves_edges(self, graph_dir):
        """R8 regression: a page compiled WITH links (legacy list), then
        recompiled body-only (new shape), must NOT lose its edges — the old
        code read page.get('outgoing_links', []) and erased them."""
        scan = make_scan([make_scan_entry("KDB/raw/s.md")])
        cr_legacy = make_compile_result([make_compiled_source("KDB/raw/s.md", [
            make_page("a", outgoing_links=["b"]),
            make_page("b"),
        ])])
        cr_new = make_compile_result([make_compiled_source("KDB/raw/s.md", [
            _body_page("a", "Still links [[b]]."),
            _body_page("b", "x"),
        ])])
        with GraphDB(graph_dir) as gdb:
            gdb.apply_compile_result(cr_legacy, scan, "run-1")
            assert gdb.stats()["links_to"] == 1
            gdb.apply_compile_result(cr_new, scan, "run-2")
            s2 = gdb.stats()
        assert s2["links_to"] == 1         # edge survived the new-shape recompile

    def test_body_derived_cross_source_edge_drains_on_arrival(self, graph_dir):
        """Body-derived links pend + drain like stored-list links: a's body
        wikilink to not-yet-existent b pends; b's commit drains it (#136)."""
        cr1 = make_compile_result([make_compiled_source("KDB/raw/a.md", [
            _body_page("a", "Points at [[b]].")])])
        cr2 = make_compile_result([make_compiled_source("KDB/raw/b.md", [
            _body_page("b", "x")])])
        scan1 = make_scan([make_scan_entry("KDB/raw/a.md")])
        scan2 = make_scan([make_scan_entry("KDB/raw/b.md")])
        edge_q = ("MATCH (:Entity {slug: 'a'})-[r:LINKS_TO]->(:Entity {slug: 'b'}) "
                  "RETURN COUNT(r)")
        with GraphDB(graph_dir) as gdb:
            gdb.apply_compile_result(cr1, scan1, "run-1")
            before = _count(gdb, edge_q)
            gdb.apply_compile_result(cr2, scan2, "run-2")
            after = _count(gdb, edge_q)
        assert before == 0               # pended (b absent)
        assert after == 1                # drained at b's commit


def test_mirrored_extractor_matches_compiler():
    """Drift guard: kdb_graph.body_wikilink_slugs must stay byte-equivalent
    to the kdb_graph_compiler's extractor (mirrored, B.3)."""
    from kdb_graph_compiler.validate_source_response import body_wikilink_slugs as comp
    from kdb_graph.intake import body_wikilink_slugs as graph
    bodies = [
        "See [[foo]] and [[bar-baz|Alias]] and [[qux#Heading]].",
        "Real [[foo]]. ```\nExample [[not-a-link]].\n``` Inline `[[nope]]`.",
        "Escaped \\[[nope]] and good [[yes]].",
        "[[Foo Bar]] is out-of-pattern; [[ok-one]] counts.",
        "",
        "no links at all",
    ]
    for body in bodies:
        assert comp(body) == graph(body), body
