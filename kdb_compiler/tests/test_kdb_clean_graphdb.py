"""Tests for `kdb-clean orphans` Phase E — GraphDB-backed orphan enumeration.

The migration (D50 Phase E) moves the orphan-candidate authority from
manifest.pages to GraphDB. These tests exercise `reap_orphans_from_graph()`
and the rewired CLI path. The old manifest-based `reap_orphans()` is kept
(covered by test_kdb_clean.py) but no longer called from the CLI.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphdb_kdb.graphdb import GraphDB
from graphdb_kdb.tests.conftest import (
    make_compile_result,
    make_compiled_source,
    make_page,
    make_scan,
    make_scan_entry,
)

from kdb_compiler.kdb_clean import reap_orphans_from_graph


# ---------- helpers ----------

@pytest.fixture
def graph_dir(tmp_path: Path) -> Path:
    return tmp_path / "GraphDB-KDB"


def _seed_with_orphans(gdb: GraphDB) -> None:
    """Ingest run-1 (4 entities), then run-2 dropping source support for 2.

    After run-2:
      - 'alive' and 'hub' are active (still supported by source-b)
      - 'gone' and 'dead' become orphan_candidate (source-a removed from run-2)
      - hub -> gone (LINKS_TO edge exists — dead link scenario)
    """
    pages_a = [
        make_page("gone", outgoing_links=["dead"]),
        make_page("dead"),
    ]
    pages_b = [
        make_page("alive"),
        make_page("hub", outgoing_links=["gone", "alive"]),
    ]
    cr1 = make_compile_result([
        make_compiled_source("KDB/raw/a.md", pages_a),
        make_compiled_source("KDB/raw/b.md", pages_b),
    ], run_id="run-1")
    scan1 = make_scan([
        make_scan_entry("KDB/raw/a.md"),
        make_scan_entry("KDB/raw/b.md"),
    ])
    gdb.apply_compile_result(cr1, scan1, "run-1")

    # run-2: source-a deleted; its SUPPORTS edges drop → orphan_candidate
    cr2 = make_compile_result([
        make_compiled_source("KDB/raw/b.md", pages_b),
    ], run_id="run-2")
    scan2 = make_scan(
        [make_scan_entry("KDB/raw/b.md")],
        to_reconcile=[{"type": "DELETED", "path": "KDB/raw/a.md"}],
    )
    gdb.apply_compile_result(cr2, scan2, "run-2")


# ---------- reap_orphans_from_graph ----------

def test_identifies_orphan_candidate_entities(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_with_orphans(gdb)
        report = reap_orphans_from_graph(gdb.conn)
    reaped_slugs = {r["slug"] for r in report["reaped"]}
    assert reaped_slugs == {"gone", "dead"}


def test_reconstructs_page_id_from_slug_and_page_type(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_with_orphans(gdb)
        report = reap_orphans_from_graph(gdb.conn)
    page_ids = {r["page_id"] for r in report["reaped"]}
    assert "KDB/wiki/concepts/gone.md" in page_ids
    assert "KDB/wiki/concepts/dead.md" in page_ids


def test_detects_dead_links_from_active_to_reaped(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_with_orphans(gdb)
        report = reap_orphans_from_graph(gdb.conn)
    # 'hub' is active and links to 'gone' (reaped) — dead link
    dead = [d for d in report["dead_links"] if d["to_slug"] == "gone"]
    assert len(dead) == 1
    assert dead[0]["from_slug"] == "hub"


def test_ignores_links_between_two_orphans(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_with_orphans(gdb)
        report = reap_orphans_from_graph(gdb.conn)
    # 'gone' -> 'dead' is orphan-to-orphan — NOT a dead link
    orphan_to_orphan = [
        d for d in report["dead_links"]
        if d["from_slug"] == "gone" and d["to_slug"] == "dead"
    ]
    assert orphan_to_orphan == []


def test_retracted_slugs_lists_fully_removed(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_with_orphans(gdb)
        report = reap_orphans_from_graph(gdb.conn)
    assert sorted(report["retracted_slugs"]) == ["dead", "gone"]


def test_slug_with_active_support_not_retracted(graph_dir):
    """Entity with slug 'foo' supported by two sources — only one deleted.

    GraphDB keys Entity by slug alone (no composite slug+page_type), so the
    old manifest scenario (same slug, different page_types) is structurally
    impossible. Instead test multi-source support: foo is supported by both
    source-a and source-b; deleting source-a leaves source-b's SUPPORTS edge
    intact, so foo remains active.
    """
    with GraphDB(graph_dir) as gdb:
        pages_a = [make_page("foo")]
        pages_b = [make_page("foo")]
        cr1 = make_compile_result([
            make_compiled_source("KDB/raw/a.md", pages_a),
            make_compiled_source("KDB/raw/b.md", pages_b),
        ], run_id="run-1")
        scan1 = make_scan([
            make_scan_entry("KDB/raw/a.md"),
            make_scan_entry("KDB/raw/b.md"),
        ])
        gdb.apply_compile_result(cr1, scan1, "run-1")

        # run-2: source-a deleted, but source-b still supports foo
        cr2 = make_compile_result([
            make_compiled_source("KDB/raw/b.md", pages_b),
        ], run_id="run-2")
        scan2 = make_scan(
            [make_scan_entry("KDB/raw/b.md")],
            to_reconcile=[{"type": "DELETED", "path": "KDB/raw/a.md"}],
        )
        gdb.apply_compile_result(cr2, scan2, "run-2")

        report = reap_orphans_from_graph(gdb.conn)

    # foo still has SUPPORTS from source-b — not orphaned at all
    assert report["reaped"] == []
    assert "foo" not in report["retracted_slugs"]


def test_no_orphans_returns_empty_report(graph_dir):
    with GraphDB(graph_dir) as gdb:
        pages = [make_page("alive")]
        cr = make_compile_result([
            make_compiled_source("KDB/raw/a.md", pages),
        ], run_id="run-1")
        scan = make_scan([make_scan_entry("KDB/raw/a.md")])
        gdb.apply_compile_result(cr, scan, "run-1")
        report = reap_orphans_from_graph(gdb.conn)
    assert report["reaped"] == []
    assert report["dead_links"] == []
    assert report["retracted_slugs"] == []


# ---------- CLI integration (rewired path) ----------

def test_cli_dry_run_reads_from_graph(tmp_path, monkeypatch, graph_dir):
    """Dry-run enumerates from GraphDB, no disk writes."""
    from kdb_compiler.kdb_clean import main

    # Set up vault with graph (no manifest needed post-Phase F)
    state = tmp_path / "KDB" / "state"
    state.mkdir(parents=True)

    # Seed graph with an orphan
    with GraphDB(graph_dir) as gdb:
        pages_a = [make_page("gone")]
        cr1 = make_compile_result([
            make_compiled_source("KDB/raw/a.md", pages_a),
        ], run_id="run-1")
        scan1 = make_scan([make_scan_entry("KDB/raw/a.md")])
        gdb.apply_compile_result(cr1, scan1, "run-1")
        # run-2: source-a deleted → 'gone' orphaned
        cr2 = make_compile_result([], run_id="run-2")
        scan2 = make_scan(
            [],
            to_reconcile=[{"type": "DELETED", "path": "KDB/raw/a.md"}],
        )
        gdb.apply_compile_result(cr2, scan2, "run-2")

    # Patch default_graph_path to point at our test DB
    monkeypatch.setattr(
        "kdb_compiler.kdb_clean.default_graph_path", lambda: graph_dir)

    rc = main(["orphans", "--vault-root", str(tmp_path)])
    assert rc == 0
    # Dry-run — no journal or retraction written
    assert not list(state.glob("runs/clean-orphans-*"))
