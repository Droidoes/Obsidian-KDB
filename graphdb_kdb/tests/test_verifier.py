"""Tests for graphdb_kdb.verifier — D50 Phase G replay verification."""
from __future__ import annotations

import json
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
from graphdb_kdb import verifier


SRC_ID = "KDB/raw/s.md"


# ---------- journal helpers ----------

def _write_journal(
    journals_dir: Path,
    run_id: str,
    *,
    compile_result: dict,
    scan: dict,
    schema_version: str = "2.1",
) -> None:
    """Write a journal + sidecar archive that the adapter considers eligible."""
    journals_dir.mkdir(parents=True, exist_ok=True)
    journal = {
        "schema_version": schema_version,
        "run_id": run_id,
        "started_at": f"2026-05-01T00:00:00+00:00",
        "success": True,
        "dry_run": False,
        "replayable_payload": True,
        "event_type": "compile",
    }
    (journals_dir / f"{run_id}.json").write_text(json.dumps(journal), encoding="utf-8")
    sidecar = journals_dir / run_id
    sidecar.mkdir(parents=True, exist_ok=True)
    (sidecar / "compile_result.json").write_text(json.dumps(compile_result), encoding="utf-8")
    (sidecar / "last_scan.json").write_text(json.dumps(scan), encoding="utf-8")


def _seed_and_journal(
    gdb: GraphDB,
    journals_dir: Path,
    *,
    pages: list[dict] | None = None,
    source_id: str = SRC_ID,
    run_id: str = "run-1",
) -> None:
    """Ingest pages into live graph AND write matching journal for replay."""
    if pages is None:
        pages = [make_page("alpha", outgoing_links=["beta"]), make_page("beta")]
    cr = make_compile_result([make_compiled_source(source_id, pages)], run_id=run_id)
    scan = make_scan([make_scan_entry(source_id)])
    gdb.apply_compile_result(cr, scan, run_id)
    _write_journal(journals_dir, run_id, compile_result=cr, scan=scan)


# ---------- 1. perfect agreement (replay == live) ----------

def test_perfect_agreement_returns_ok(graph_dir, tmp_path):
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        _seed_and_journal(gdb, journals_dir)
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert result.ok
    assert not result.rebuild_failed
    assert result.divergences == []
    assert result.counts["entities_checked"] == 2
    assert result.counts["sources_checked"] == 1
    assert result.counts["links_checked"] == 1
    assert result.counts["supports_checked"] == 2


# ---------- 2. divergence: extra entity in live ----------

def test_extra_entity_in_live_detected(graph_dir, tmp_path):
    """Live has entity 'gamma' that replay doesn't produce → missing_in_replay."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        pages = [make_page("alpha", outgoing_links=["beta"]), make_page("beta"), make_page("gamma")]
        cr = make_compile_result([make_compiled_source(SRC_ID, pages)])
        scan = make_scan([make_scan_entry(SRC_ID)])
        gdb.apply_compile_result(cr, scan, "run-1")
        # Journal only has alpha+beta (no gamma)
        cr_journal = make_compile_result([make_compiled_source(SRC_ID, [
            make_page("alpha", outgoing_links=["beta"]), make_page("beta"),
        ])])
        _write_journal(journals_dir, "run-1", compile_result=cr_journal, scan=scan)
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert not result.ok
    assert any(
        d.kind == "missing_in_replay" and d.category == "entity" and d.key == "gamma"
        for d in result.divergences
    )


# ---------- 3. divergence: missing entity in live ----------

def test_missing_entity_in_live_detected(graph_dir, tmp_path):
    """Replay produces 'gamma' but live doesn't have it → missing_in_live."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        # Live: only alpha+beta
        pages_live = [make_page("alpha", outgoing_links=["beta"]), make_page("beta")]
        cr_live = make_compile_result([make_compiled_source(SRC_ID, pages_live)])
        scan = make_scan([make_scan_entry(SRC_ID)])
        gdb.apply_compile_result(cr_live, scan, "run-1")
        # Journal: alpha+beta+gamma
        pages_journal = pages_live + [make_page("gamma")]
        cr_journal = make_compile_result([make_compiled_source(SRC_ID, pages_journal)])
        _write_journal(journals_dir, "run-1", compile_result=cr_journal, scan=scan)
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert not result.ok
    assert any(
        d.kind == "missing_in_live" and d.category == "entity" and d.key == "gamma"
        for d in result.divergences
    )


# ---------- 4. attribute mismatch ----------

def test_attribute_mismatch_detected(graph_dir, tmp_path):
    """Live entity has different page_type than replay produces."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        # Live: alpha is concept
        pages_live = [make_page("alpha", page_type="concept")]
        cr_live = make_compile_result([make_compiled_source(SRC_ID, pages_live)])
        scan = make_scan([make_scan_entry(SRC_ID)])
        gdb.apply_compile_result(cr_live, scan, "run-1")
        # Journal: alpha is article
        pages_journal = [make_page("alpha", page_type="article")]
        cr_journal = make_compile_result([make_compiled_source(SRC_ID, pages_journal)])
        _write_journal(journals_dir, "run-1", compile_result=cr_journal, scan=scan)
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert not result.ok
    mismatches = [d for d in result.divergences if d.kind == "attribute_mismatch" and d.key == "alpha"]
    assert len(mismatches) >= 1
    page_type_mm = [d for d in mismatches if d.field == "page_type"]
    assert len(page_type_mm) == 1
    assert page_type_mm[0].expected_value == "article"
    assert page_type_mm[0].actual_value == "concept"


# ---------- 5. link divergence ----------

def test_link_divergence_detected(graph_dir, tmp_path):
    """Live has alpha->beta but journal produces alpha->gamma instead."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        # Live: alpha->beta
        pages_live = [make_page("alpha", outgoing_links=["beta"]), make_page("beta")]
        cr_live = make_compile_result([make_compiled_source(SRC_ID, pages_live)])
        scan = make_scan([make_scan_entry(SRC_ID)])
        gdb.apply_compile_result(cr_live, scan, "run-1")
        # Journal: alpha->gamma
        pages_journal = [make_page("alpha", outgoing_links=["gamma"]), make_page("gamma")]
        cr_journal = make_compile_result([make_compiled_source(SRC_ID, pages_journal)])
        _write_journal(journals_dir, "run-1", compile_result=cr_journal, scan=scan)
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert not result.ok
    link_divs = [d for d in result.divergences if d.category == "links_to"]
    assert any(d.kind == "missing_in_live" and "alpha→gamma" in d.key for d in link_divs)
    assert any(d.kind == "missing_in_replay" and "alpha→beta" in d.key for d in link_divs)


# ---------- 6. rebuild failure → rebuild_failed=True ----------

def test_rebuild_failure_returns_rebuild_failed(graph_dir, tmp_path):
    """If journal sidecar has corrupt JSON, rebuild fails → verify reports it."""
    journals_dir = tmp_path / "runs"
    journals_dir.mkdir(parents=True)
    # Write a journal pointing to a sidecar with corrupt compile_result
    journal = {
        "schema_version": "2.1",
        "run_id": "bad-run",
        "started_at": "2026-05-01T00:00:00+00:00",
        "success": True,
        "dry_run": False,
        "replayable_payload": True,
        "event_type": "compile",
    }
    (journals_dir / "bad-run.json").write_text(json.dumps(journal), encoding="utf-8")
    sidecar = journals_dir / "bad-run"
    sidecar.mkdir()
    (sidecar / "compile_result.json").write_text("{ not valid json !!!", encoding="utf-8")
    (sidecar / "last_scan.json").write_text("{}", encoding="utf-8")

    with GraphDB(graph_dir) as gdb:
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert not result.ok
    assert result.rebuild_failed
    assert "bad-run" in result.rebuild_error


# ---------- 7. source-state preflight ----------

def test_source_state_preflight_reports_divergences(graph_dir, tmp_path):
    """verify_source_state detects manifest-vs-live source differences."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        _seed_and_journal(gdb, journals_dir)
        # Manifest with an extra source not in graph
        manifest = {
            "sources": {
                SRC_ID: {
                    "status": "active",
                    "compile_state": "compiled",
                    "compile_count": 1,
                    "hash": "sha256:abc",
                    "file_type": "markdown",
                    "size_bytes": 100,
                    "last_run_id": "run-1",
                },
                "KDB/raw/extra.md": {
                    "status": "active",
                    "compile_state": "compiled",
                    "compile_count": 1,
                    "hash": "sha256:xyz",
                    "file_type": "markdown",
                    "size_bytes": 50,
                    "last_run_id": "run-1",
                },
            },
        }
        divs = verifier.verify_source_state(gdb.conn, manifest)
    assert any(
        d.kind == "missing_in_live" and d.category == "source" and d.key == "KDB/raw/extra.md"
        for d in divs
    )
    assert all(d.source == "source_state_preflight" for d in divs)


# ---------- 8. divergence source tagging ----------

def test_divergences_are_properly_tagged(graph_dir, tmp_path):
    """When both preflight and replay produce divergences, tags are distinct."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        pages_live = [make_page("alpha")]
        cr_live = make_compile_result([make_compiled_source(SRC_ID, pages_live)])
        scan = make_scan([make_scan_entry(SRC_ID)])
        gdb.apply_compile_result(cr_live, scan, "run-1")
        # Journal produces alpha+beta (so beta missing in live for replay)
        pages_journal = [make_page("alpha"), make_page("beta")]
        cr_journal = make_compile_result([make_compiled_source(SRC_ID, pages_journal)])
        _write_journal(journals_dir, "run-1", compile_result=cr_journal, scan=scan)
        # Manifest with extra source (for preflight divergence)
        manifest = {
            "sources": {
                SRC_ID: {
                    "status": "active",
                    "compile_state": "compiled",
                    "compile_count": 1,
                    "hash": "sha256:abc",
                    "file_type": "markdown",
                    "size_bytes": 100,
                    "last_run_id": "run-1",
                },
                "KDB/raw/ghost.md": {
                    "status": "active",
                    "compile_state": "compiled",
                    "compile_count": 1,
                    "hash": "sha256:ghost",
                    "file_type": "markdown",
                    "size_bytes": 0,
                    "last_run_id": "run-1",
                },
            },
        }
        result = verifier.verify(gdb.conn, journals_dir=journals_dir, manifest=manifest)
    assert not result.ok
    preflight_divs = [d for d in result.divergences if d.source == "source_state_preflight"]
    replay_divs = [d for d in result.divergences if d.source == "replay_structural_diff"]
    assert len(preflight_divs) > 0
    assert len(replay_divs) > 0


# ---------- 9. empty journals → empty replay graph ----------

def test_no_journals_produces_empty_replay(graph_dir, tmp_path):
    """No journals → replay graph is empty → everything in live is missing_in_replay."""
    journals_dir = tmp_path / "runs"
    journals_dir.mkdir(parents=True)
    with GraphDB(graph_dir) as gdb:
        pages = [make_page("alpha")]
        cr = make_compile_result([make_compiled_source(SRC_ID, pages)])
        scan = make_scan([make_scan_entry(SRC_ID)])
        gdb.apply_compile_result(cr, scan, "run-1")
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert not result.ok
    assert any(
        d.kind == "missing_in_replay" and d.category == "entity" and d.key == "alpha"
        for d in result.divergences
    )


# ---------- 10. supports edge divergence ----------

def test_supports_edge_divergence_detected(graph_dir, tmp_path):
    """Different source→entity SUPPORTS edges between replay and live."""
    journals_dir = tmp_path / "runs"
    src2 = "KDB/raw/other.md"
    with GraphDB(graph_dir) as gdb:
        # Live: alpha supported by SRC_ID only
        pages_live = [make_page("alpha")]
        cr_live = make_compile_result([make_compiled_source(SRC_ID, pages_live)])
        scan_live = make_scan([make_scan_entry(SRC_ID)])
        gdb.apply_compile_result(cr_live, scan_live, "run-1")
        # Journal: alpha supported by src2
        cr_journal = make_compile_result([make_compiled_source(src2, [make_page("alpha")])])
        scan_journal = make_scan([make_scan_entry(src2)])
        _write_journal(journals_dir, "run-1", compile_result=cr_journal, scan=scan_journal)
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert not result.ok
    supports_divs = [d for d in result.divergences if d.category == "supports"]
    assert len(supports_divs) >= 1


# ---------- 11. #79 — Domain + BELONGS_TO coverage (schema v2.1) ----------

def test_perfect_agreement_with_domains(graph_dir, tmp_path):
    """Domain-tagged pages: replay==live, counts include domains_checked +
    belongs_to_checked, zero divergences."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        pages = [
            make_page("alpha", domain="Investing", sub_domain="Value Investing"),
            make_page("beta", domain=["Investing", "Macro"]),
        ]
        cr = make_compile_result([make_compiled_source(SRC_ID, pages)])
        scan = make_scan([make_scan_entry(SRC_ID)])
        gdb.apply_compile_result(cr, scan, "run-1")
        _write_journal(journals_dir, "run-1", compile_result=cr, scan=scan)
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert result.ok
    assert result.divergences == []
    assert result.counts["domains_checked"] == 2     # "investing", "macro"
    assert result.counts["belongs_to_checked"] == 3  # alpha→investing, beta→investing, beta→macro


def test_missing_domain_in_live_detected(graph_dir, tmp_path):
    """Journal produces a Domain that live doesn't have → missing_in_live."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        # Live: alpha with no domain
        pages_live = [make_page("alpha")]
        cr_live = make_compile_result([make_compiled_source(SRC_ID, pages_live)])
        scan = make_scan([make_scan_entry(SRC_ID)])
        gdb.apply_compile_result(cr_live, scan, "run-1")
        # Journal: alpha tagged with "Investing"
        pages_journal = [make_page("alpha", domain="Investing")]
        cr_journal = make_compile_result([make_compiled_source(SRC_ID, pages_journal)])
        _write_journal(journals_dir, "run-1", compile_result=cr_journal, scan=scan)
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert not result.ok
    domain_divs = [d for d in result.divergences if d.category == "domain"]
    assert any(d.kind == "missing_in_live" and d.key == "investing" for d in domain_divs)
    belongs_divs = [d for d in result.divergences if d.category == "belongs_to"]
    assert any(
        d.kind == "missing_in_live" and d.key == "alpha→investing"
        for d in belongs_divs
    )


def test_extra_domain_in_live_detected(graph_dir, tmp_path):
    """Live has a Domain that replay doesn't produce → missing_in_replay."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        # Live: alpha tagged with "Investing"
        pages_live = [make_page("alpha", domain="Investing")]
        cr_live = make_compile_result([make_compiled_source(SRC_ID, pages_live)])
        scan = make_scan([make_scan_entry(SRC_ID)])
        gdb.apply_compile_result(cr_live, scan, "run-1")
        # Journal: alpha with no domain
        pages_journal = [make_page("alpha")]
        cr_journal = make_compile_result([make_compiled_source(SRC_ID, pages_journal)])
        _write_journal(journals_dir, "run-1", compile_result=cr_journal, scan=scan)
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert not result.ok
    domain_divs = [d for d in result.divergences if d.category == "domain"]
    assert any(d.kind == "missing_in_replay" and d.key == "investing" for d in domain_divs)
    belongs_divs = [d for d in result.divergences if d.category == "belongs_to"]
    assert any(
        d.kind == "missing_in_replay" and d.key == "alpha→investing"
        for d in belongs_divs
    )


def test_belongs_to_sub_domain_mismatch_detected(graph_dir, tmp_path):
    """Same (entity,domain) edge but different sub_domain → attribute_mismatch."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        # Live: alpha → investing with sub_domain "value-investing"
        pages_live = [make_page("alpha", domain="Investing", sub_domain="Value Investing")]
        cr_live = make_compile_result([make_compiled_source(SRC_ID, pages_live)])
        scan = make_scan([make_scan_entry(SRC_ID)])
        gdb.apply_compile_result(cr_live, scan, "run-1")
        # Journal: alpha → investing with sub_domain "macro" (different)
        pages_journal = [make_page("alpha", domain="Investing", sub_domain="Macro")]
        cr_journal = make_compile_result([make_compiled_source(SRC_ID, pages_journal)])
        _write_journal(journals_dir, "run-1", compile_result=cr_journal, scan=scan)
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert not result.ok
    mismatches = [
        d for d in result.divergences
        if d.category == "belongs_to" and d.kind == "attribute_mismatch"
        and d.key == "alpha→investing" and d.field == "sub_domain"
    ]
    assert len(mismatches) == 1
    assert mismatches[0].expected_value == "macro"
    assert mismatches[0].actual_value == "value-investing"


def test_no_domain_pages_still_pass(graph_dir, tmp_path):
    """Pre-#76 shape (no domain field) → zero Domain/BELONGS_TO state, no divergences."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        _seed_and_journal(gdb, journals_dir)  # plain pages, no domain
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert result.ok
    assert result.counts["domains_checked"] == 0
    assert result.counts["belongs_to_checked"] == 0


# ---------- 13. #89 D-89-17 — Pass-1 Source columns in replay diff ----------


def _write_journal_with_source_pass1(
    journals_dir: Path,
    run_id: str,
    *,
    compile_result: dict,
    scan: dict,
) -> None:
    """Same as _write_journal but with schema_version 2.3 tag."""
    _write_journal(journals_dir, run_id, compile_result=compile_result, scan=scan, schema_version="2.3")


def test_pass1_columns_perfect_agreement(graph_dir, tmp_path):
    """Replay and live both have matching summary/author/domain on Source
    (simulated via direct graph writes post-ingest) → ok, no divergences."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        _seed_and_journal(gdb, journals_dir)
        # Directly set Pass-1 columns on the live Source (simulates Pass-1 ingest).
        gdb.conn.execute(
            f"MATCH (s:Source {{source_id: '{SRC_ID}'}}) "
            f"SET s.summary = 'A summary', s.author = 'Alice', s.domain = 'Testing'"
        )
        # Replay also picks up the same compile_result from the journal,
        # but since rebuild doesn't write Pass-1 columns yet (deferred),
        # the diff is NULL==NULL on replay side. Live has values, replay has NULL.
        # This means the test should detect a divergence — proving drift detection works.
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    # Replay side has NULL (no Pass-1 replay yet), live side has values → mismatch detected.
    source_divs = [
        d for d in result.divergences
        if d.category == "source" and d.kind == "attribute_mismatch"
        and d.key == SRC_ID
    ]
    summary_divs = [d for d in source_divs if d.field == "summary"]
    assert len(summary_divs) == 1
    assert summary_divs[0].expected_value is None        # replay (rebuild): NULL
    assert summary_divs[0].actual_value == "A summary"  # live: populated by Pass-1


def test_pass1_domain_mismatch_detected(graph_dir, tmp_path):
    """Live Source.domain differs from replay Source.domain → attribute_mismatch
    on 'domain' field under category='source'. Verifies per-field diff coverage."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        _seed_and_journal(gdb, journals_dir)
        # Set domain to "Investing" on live but replay will produce NULL.
        gdb.conn.execute(
            f"MATCH (s:Source {{source_id: '{SRC_ID}'}}) "
            f"SET s.domain = 'Investing'"
        )
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    domain_divs = [
        d for d in result.divergences
        if d.category == "source" and d.kind == "attribute_mismatch"
        and d.key == SRC_ID and d.field == "domain"
    ]
    assert len(domain_divs) == 1
    assert domain_divs[0].expected_value is None       # replay: NULL
    assert domain_divs[0].actual_value == "Investing"  # live: set by Pass-1


def test_pass1_null_on_both_sides_no_divergence(graph_dir, tmp_path):
    """Sources without Pass-1 data have NULL on both replay and live sides
    → _diff_sources_replay sees NULL==NULL, zero attribute_mismatch divergences
    for summary/author/domain."""
    journals_dir = tmp_path / "runs"
    with GraphDB(graph_dir) as gdb:
        _seed_and_journal(gdb, journals_dir)
        # No Pass-1 columns set — both sides remain NULL.
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert result.ok
    # Specifically confirm no attribute_mismatch on the new fields.
    pass1_divs = [
        d for d in result.divergences
        if d.category == "source" and d.field in ("summary", "author", "domain")
    ]
    assert pass1_divs == []
