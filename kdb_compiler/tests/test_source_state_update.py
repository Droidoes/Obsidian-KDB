"""Tests for source_state_update — source-meta-only ledger (D50 Phase D).

Covers: scan reconciliation (NEW/CHANGED/UNCHANGED/MOVED/DELETED),
compile-state advancement, previous_versions cap, tombstone semantics,
runs pointer, and stats recomputation. No pages, no orphans, no links.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from kdb_compiler.run_context import RunContext, SCHEMA_VERSION
from kdb_compiler.source_state_update import (
    build_source_state_update,
    apply_scan_reconciliation,
    apply_compile_sources,
    recompute_source_stats,
    ensure_source_state_shape,
    PREV_VERSIONS_CAP,
)


# ---- fixtures ----

def _ctx(run_id: str = "2026-05-17T10-00-00-04-00",
         started_at: str = "2026-05-17T10:00:00-04:00") -> RunContext:
    return RunContext(
        run_id=run_id,
        started_at=started_at,
        compiler_version="0.9.0",
        schema_version=SCHEMA_VERSION,
        dry_run=False,
        vault_root=Path("/vault"),
        kdb_root=Path("/vault/KDB"),
    )


def _scan_file(path: str, *, action: str = "NEW", h: str = "sha256:aaa",
               mtime: float = 1700000000.0, size: int = 100,
               file_type: str = "markdown", is_binary: bool = False,
               previous_path: str | None = None) -> dict:
    entry = {
        "path": path, "action": action, "current_hash": h,
        "current_mtime": mtime, "size_bytes": size,
        "file_type": file_type, "is_binary": is_binary,
    }
    if previous_path:
        entry["previous_path"] = previous_path
    return entry


def _scan(files: list[dict] | None = None,
          to_compile: list[str] | None = None,
          to_reconcile: list[dict] | None = None) -> dict:
    return {
        "run_id": "2026-05-17T10-00-00-04-00",
        "files": files or [],
        "to_compile": to_compile or [],
        "to_reconcile": to_reconcile or [],
    }


def _compiled_source(source_id: str, summary_slug: str, title: str = "Title",
                     pages: list[dict] | None = None) -> dict:
    return {
        "source_id": source_id,
        "summary_slug": summary_slug,
        "pages": pages or [{"slug": summary_slug, "page_type": "summary",
                            "title": title, "body": "b"}],
        "concept_slugs": [],
        "article_slugs": [],
    }


# ===========================================================================
# ensure_source_state_shape
# ===========================================================================

def test_bootstrap_empty_seeds_all_keys() -> None:
    """Empty prior → full shape with empty sources/tombstones/runs."""
    ctx = _ctx()
    state = ensure_source_state_shape({}, ctx=ctx)
    assert "sources" in state
    assert "tombstones" in state
    assert "runs" in state
    assert state["schema_version"] == SCHEMA_VERSION
    assert state["sources"] == {}
    assert state["tombstones"] == {}


def test_shape_idempotent_on_existing() -> None:
    """Non-empty prior retains its data."""
    ctx = _ctx()
    prior = {"schema_version": SCHEMA_VERSION, "sources": {"x": {}},
             "tombstones": {}, "runs": {"last_run_id": "r1"},
             "updated_at": "old", "stats": {}}
    state = ensure_source_state_shape(prior, ctx=ctx)
    assert state["sources"] == {"x": {}}
    assert state["runs"]["last_run_id"] == "r1"


# ===========================================================================
# apply_scan_reconciliation (source-only)
# ===========================================================================

def test_scan_new_seeds_source_record() -> None:
    """NEW file creates a source record with correct fields."""
    ctx = _ctx()
    state = ensure_source_state_shape({}, ctx=ctx)
    scan = _scan(files=[_scan_file("KDB/raw/a.md")])
    state = apply_scan_reconciliation(state, scan, ctx)
    rec = state["sources"]["KDB/raw/a.md"]
    assert rec["source_id"] == "KDB/raw/a.md"
    assert rec["canonical_path"] == "KDB/raw/a.md"
    assert rec["status"] == "active"
    assert rec["hash"] == "sha256:aaa"
    assert rec["compile_state"] == "pending"
    assert rec["compile_count"] == 0
    assert rec["last_compiled_hash"] is None
    assert rec["previous_versions"] == []


def test_scan_new_binary_sets_last_compiled_hash() -> None:
    """Binary NEW file gets last_compiled_hash = current_hash (no LLM step)."""
    ctx = _ctx()
    state = ensure_source_state_shape({}, ctx=ctx)
    scan = _scan(files=[_scan_file("KDB/raw/img.png", is_binary=True,
                                   file_type="image")])
    state = apply_scan_reconciliation(state, scan, ctx)
    rec = state["sources"]["KDB/raw/img.png"]
    assert rec["compile_state"] == "metadata_only"
    assert rec["last_compiled_hash"] == "sha256:aaa"


def test_scan_changed_appends_previous_version() -> None:
    """CHANGED appends old values to previous_versions."""
    ctx = _ctx()
    state = ensure_source_state_shape({}, ctx=ctx)
    state["sources"]["KDB/raw/a.md"] = {
        "source_id": "KDB/raw/a.md", "canonical_path": "KDB/raw/a.md",
        "status": "active", "file_type": "markdown",
        "hash": "sha256:old", "mtime": 1600000000.0, "size_bytes": 50,
        "first_seen_at": "2026-01-01", "last_seen_at": "2026-01-01",
        "last_compiled_at": "2026-01-01", "last_run_id": "r0",
        "compile_state": "compiled", "compile_count": 1,
        "last_compiled_hash": "sha256:old",
        "summary_slug": None, "compiled_title": None,
        "parser": None, "compiler_version": None, "schema_version_used": None,
        "previous_versions": [],
    }
    scan = _scan(files=[_scan_file("KDB/raw/a.md", action="CHANGED",
                                   h="sha256:new", mtime=1700000001.0,
                                   size=200)])
    state = apply_scan_reconciliation(state, scan, ctx)
    rec = state["sources"]["KDB/raw/a.md"]
    assert rec["hash"] == "sha256:new"
    assert rec["mtime"] == 1700000001.0
    assert rec["size_bytes"] == 200
    assert len(rec["previous_versions"]) == 1
    pv = rec["previous_versions"][0]
    assert pv["hash"] == "sha256:old"
    assert pv["mtime"] == 1600000000.0


def test_scan_unchanged_only_bumps_last_seen() -> None:
    """UNCHANGED bumps last_seen_at but not last_run_id or compile fields."""
    ctx = _ctx()
    state = ensure_source_state_shape({}, ctx=ctx)
    state["sources"]["KDB/raw/a.md"] = {
        "source_id": "KDB/raw/a.md", "canonical_path": "KDB/raw/a.md",
        "status": "active", "file_type": "markdown",
        "hash": "sha256:aaa", "mtime": 1700000000.0, "size_bytes": 100,
        "first_seen_at": "2026-01-01", "last_seen_at": "2026-01-01",
        "last_compiled_at": "2026-01-01", "last_run_id": "r0",
        "compile_state": "compiled", "compile_count": 1,
        "last_compiled_hash": "sha256:aaa",
        "summary_slug": "a", "compiled_title": "A",
        "parser": "markdown-basic", "compiler_version": "0.8.0",
        "schema_version_used": SCHEMA_VERSION,
        "previous_versions": [],
    }
    scan = _scan(files=[_scan_file("KDB/raw/a.md", action="UNCHANGED")])
    state = apply_scan_reconciliation(state, scan, ctx)
    rec = state["sources"]["KDB/raw/a.md"]
    assert rec["last_seen_at"] == ctx.started_at
    assert rec["last_run_id"] == "r0"  # NOT bumped
    assert rec["compile_count"] == 1  # NOT bumped


def test_scan_moved_writes_tombstone_and_relocates() -> None:
    """MOVED removes old key, inserts new key, writes tombstone."""
    ctx = _ctx()
    state = ensure_source_state_shape({}, ctx=ctx)
    state["sources"]["KDB/raw/old.md"] = {
        "source_id": "KDB/raw/old.md", "canonical_path": "KDB/raw/old.md",
        "status": "active", "file_type": "markdown",
        "hash": "sha256:aaa", "mtime": 1700000000.0, "size_bytes": 100,
        "first_seen_at": "2026-01-01", "last_seen_at": "2026-01-01",
        "last_compiled_at": None, "last_run_id": "r0",
        "compile_state": "pending", "compile_count": 0,
        "last_compiled_hash": None,
        "summary_slug": None, "compiled_title": None,
        "parser": None, "compiler_version": None, "schema_version_used": None,
        "previous_versions": [],
    }
    scan = _scan(files=[_scan_file("KDB/raw/new.md", action="MOVED",
                                   previous_path="KDB/raw/old.md")])
    state = apply_scan_reconciliation(state, scan, ctx)
    assert "KDB/raw/old.md" not in state["sources"]
    assert "KDB/raw/new.md" in state["sources"]
    rec = state["sources"]["KDB/raw/new.md"]
    assert rec["source_id"] == "KDB/raw/new.md"
    assert rec["canonical_path"] == "KDB/raw/new.md"
    tomb = state["tombstones"]["KDB/raw/old.md"]
    assert tomb["status"] == "moved"
    assert tomb["moved_to"] == "KDB/raw/new.md"


def test_scan_deleted_writes_tombstone_and_removes_source() -> None:
    """DELETED via to_reconcile removes source and writes tombstone."""
    ctx = _ctx()
    state = ensure_source_state_shape({}, ctx=ctx)
    state["sources"]["KDB/raw/gone.md"] = {
        "source_id": "KDB/raw/gone.md", "canonical_path": "KDB/raw/gone.md",
        "status": "active", "file_type": "markdown",
        "hash": "sha256:dead", "mtime": 1700000000.0, "size_bytes": 50,
        "first_seen_at": "2026-01-01", "last_seen_at": "2026-01-01",
        "last_compiled_at": None, "last_run_id": "r0",
        "compile_state": "pending", "compile_count": 0,
        "last_compiled_hash": None,
        "summary_slug": None, "compiled_title": None,
        "parser": None, "compiler_version": None, "schema_version_used": None,
        "previous_versions": [],
    }
    scan = _scan(to_reconcile=[{"type": "DELETED", "path": "KDB/raw/gone.md",
                                "hash": "sha256:dead"}])
    state = apply_scan_reconciliation(state, scan, ctx)
    assert "KDB/raw/gone.md" not in state["sources"]
    tomb = state["tombstones"]["KDB/raw/gone.md"]
    assert tomb["status"] == "deleted"


# ===========================================================================
# apply_compile_sources
# ===========================================================================

def test_compile_advances_source_state() -> None:
    """Compiling a source bumps compile_count, sets compile fields."""
    ctx = _ctx()
    state = ensure_source_state_shape({}, ctx=ctx)
    state["sources"]["KDB/raw/a.md"] = {
        "source_id": "KDB/raw/a.md", "canonical_path": "KDB/raw/a.md",
        "status": "active", "file_type": "markdown",
        "hash": "sha256:aaa", "mtime": 1700000000.0, "size_bytes": 100,
        "first_seen_at": "2026-01-01", "last_seen_at": "2026-01-01",
        "last_compiled_at": None, "last_run_id": "r0",
        "compile_state": "pending", "compile_count": 0,
        "last_compiled_hash": None,
        "summary_slug": None, "compiled_title": None,
        "parser": None, "compiler_version": None, "schema_version_used": None,
        "previous_versions": [],
    }
    cr = {"compiled_sources": [_compiled_source("KDB/raw/a.md", "a-summary",
                                                title="A Summary")],
          "success": True}
    scan = _scan(files=[_scan_file("KDB/raw/a.md", action="CHANGED")],
                 to_compile=["KDB/raw/a.md"])
    state = apply_compile_sources(state, cr, scan, ctx)
    rec = state["sources"]["KDB/raw/a.md"]
    assert rec["compile_state"] == "compiled"
    assert rec["compile_count"] == 1
    assert rec["last_compiled_at"] == ctx.started_at
    assert rec["last_compiled_hash"] == "sha256:aaa"
    assert rec["summary_slug"] == "a-summary"
    assert rec["compiled_title"] == "A Summary"
    assert rec["parser"] == "markdown-basic"
    assert rec["compiler_version"] == ctx.compiler_version
    assert rec["schema_version_used"] == ctx.schema_version


def test_recompile_increments_count() -> None:
    """Second compile bumps compile_count and sets state to 'recompiled'."""
    ctx = _ctx()
    state = ensure_source_state_shape({}, ctx=ctx)
    state["sources"]["KDB/raw/a.md"] = {
        "source_id": "KDB/raw/a.md", "canonical_path": "KDB/raw/a.md",
        "status": "active", "file_type": "markdown",
        "hash": "sha256:bbb", "mtime": 1700000001.0, "size_bytes": 200,
        "first_seen_at": "2026-01-01", "last_seen_at": "2026-05-17",
        "last_compiled_at": "2026-01-01", "last_run_id": "r0",
        "compile_state": "compiled", "compile_count": 1,
        "last_compiled_hash": "sha256:aaa",
        "summary_slug": "a-summary", "compiled_title": "A",
        "parser": "markdown-basic", "compiler_version": "0.8.0",
        "schema_version_used": SCHEMA_VERSION,
        "previous_versions": [],
    }
    cr = {"compiled_sources": [_compiled_source("KDB/raw/a.md", "a-summary",
                                                title="A v2")],
          "success": True}
    scan = _scan(files=[_scan_file("KDB/raw/a.md", action="CHANGED",
                                   h="sha256:bbb")],
                 to_compile=["KDB/raw/a.md"])
    state = apply_compile_sources(state, cr, scan, ctx)
    rec = state["sources"]["KDB/raw/a.md"]
    assert rec["compile_state"] == "recompiled"
    assert rec["compile_count"] == 2
    assert rec["last_compiled_hash"] == "sha256:bbb"
    assert rec["compiled_title"] == "A v2"


def test_missing_compile_marks_error() -> None:
    """Source in to_compile but not in compiled_sources → compile_state=error."""
    ctx = _ctx()
    state = ensure_source_state_shape({}, ctx=ctx)
    state["sources"]["KDB/raw/a.md"] = {
        "source_id": "KDB/raw/a.md", "canonical_path": "KDB/raw/a.md",
        "status": "active", "file_type": "markdown",
        "hash": "sha256:aaa", "mtime": 1700000000.0, "size_bytes": 100,
        "first_seen_at": "2026-01-01", "last_seen_at": "2026-01-01",
        "last_compiled_at": None, "last_run_id": "r0",
        "compile_state": "pending", "compile_count": 0,
        "last_compiled_hash": None,
        "summary_slug": None, "compiled_title": None,
        "parser": None, "compiler_version": None, "schema_version_used": None,
        "previous_versions": [],
    }
    cr = {"compiled_sources": [], "success": True}
    scan = _scan(to_compile=["KDB/raw/a.md"])
    state = apply_compile_sources(state, cr, scan, ctx)
    rec = state["sources"]["KDB/raw/a.md"]
    assert rec["compile_state"] == "error"
    assert rec["last_run_id"] == ctx.run_id


# ===========================================================================
# previous_versions cap
# ===========================================================================

def test_previous_versions_capped_at_20() -> None:
    """previous_versions never exceeds PREV_VERSIONS_CAP."""
    ctx = _ctx()
    state = ensure_source_state_shape({}, ctx=ctx)
    state["sources"]["KDB/raw/a.md"] = {
        "source_id": "KDB/raw/a.md", "canonical_path": "KDB/raw/a.md",
        "status": "active", "file_type": "markdown",
        "hash": "sha256:old", "mtime": 1600000000.0, "size_bytes": 50,
        "first_seen_at": "2026-01-01", "last_seen_at": "2026-01-01",
        "last_compiled_at": "2026-01-01", "last_run_id": "r0",
        "compile_state": "compiled", "compile_count": 1,
        "last_compiled_hash": "sha256:old",
        "summary_slug": None, "compiled_title": None,
        "parser": None, "compiler_version": None, "schema_version_used": None,
        "previous_versions": [{"hash": f"v{i}", "mtime": float(i),
                               "size_bytes": 10, "compiled_at": None,
                               "run_id": f"r{i}"} for i in range(20)],
    }
    scan = _scan(files=[_scan_file("KDB/raw/a.md", action="CHANGED",
                                   h="sha256:new")])
    state = apply_scan_reconciliation(state, scan, ctx)
    assert len(state["sources"]["KDB/raw/a.md"]["previous_versions"]) == PREV_VERSIONS_CAP
    # Most recent entry is the one we just pushed
    last = state["sources"]["KDB/raw/a.md"]["previous_versions"][-1]
    assert last["hash"] == "sha256:old"


# ===========================================================================
# recompute_source_stats + runs pointer
# ===========================================================================

def test_recompute_stats_counts_sources() -> None:
    """Stats reflect source count and total_runs increments."""
    ctx = _ctx()
    state = ensure_source_state_shape({}, ctx=ctx)
    state["sources"]["a"] = {}
    state["sources"]["b"] = {}
    cr = {"success": True, "compiled_sources": []}
    prior_runs = {"last_run_id": None, "total_runs": 0}
    state = recompute_source_stats(state, cr, ctx, prior_runs=prior_runs)
    assert state["stats"]["total_raw_files"] == 2
    assert state["stats"]["total_runs"] == 1
    assert state["runs"]["last_run_id"] == ctx.run_id
    assert state["runs"]["last_successful_run_id"] == ctx.run_id


def test_recompute_stats_failed_run_does_not_advance_success_pointer() -> None:
    """success=false preserves prior last_successful_run_id."""
    ctx = _ctx()
    state = ensure_source_state_shape({}, ctx=ctx)
    state["sources"]["a"] = {}
    cr = {"success": False, "compiled_sources": []}
    prior_runs = {"last_run_id": "r-old", "last_successful_run_id": "r-old",
                  "total_runs": 5}
    state = recompute_source_stats(state, cr, ctx, prior_runs=prior_runs)
    assert state["runs"]["last_run_id"] == ctx.run_id
    assert state["runs"]["last_successful_run_id"] == "r-old"
    assert state["stats"]["total_runs"] == 6


# ===========================================================================
# build_source_state_update (end-to-end orchestrator)
# ===========================================================================

def test_build_source_state_update_bootstrap() -> None:
    """From empty prior: seeds shape, applies scan, applies compile."""
    ctx = _ctx()
    scan = _scan(
        files=[_scan_file("KDB/raw/a.md", action="NEW")],
        to_compile=["KDB/raw/a.md"],
    )
    cr = {"compiled_sources": [_compiled_source("KDB/raw/a.md", "a-summary",
                                                title="A")],
          "success": True, "run_id": ctx.run_id}
    next_state, payload = build_source_state_update({}, scan, cr, ctx)
    assert "KDB/raw/a.md" in next_state["sources"]
    rec = next_state["sources"]["KDB/raw/a.md"]
    assert rec["compile_state"] == "compiled"
    assert rec["summary_slug"] == "a-summary"
    assert next_state["stats"]["total_raw_files"] == 1
    assert payload["sources_added"] == ["KDB/raw/a.md"]


def test_build_source_state_update_second_run() -> None:
    """Second run with CHANGED source increments compile_count."""
    ctx = _ctx(run_id="2026-05-17T11-00-00-04-00",
               started_at="2026-05-17T11:00:00-04:00")
    prior = {
        "schema_version": SCHEMA_VERSION,
        "sources": {
            "KDB/raw/a.md": {
                "source_id": "KDB/raw/a.md", "canonical_path": "KDB/raw/a.md",
                "status": "active", "file_type": "markdown",
                "hash": "sha256:aaa", "mtime": 1700000000.0, "size_bytes": 100,
                "first_seen_at": "2026-05-17T10:00:00-04:00",
                "last_seen_at": "2026-05-17T10:00:00-04:00",
                "last_compiled_at": "2026-05-17T10:00:00-04:00",
                "last_run_id": "2026-05-17T10-00-00-04-00",
                "compile_state": "compiled", "compile_count": 1,
                "last_compiled_hash": "sha256:aaa",
                "summary_slug": "a-summary", "compiled_title": "A",
                "parser": "markdown-basic", "compiler_version": "0.8.0",
                "schema_version_used": SCHEMA_VERSION,
                "previous_versions": [],
            },
        },
        "tombstones": {},
        "runs": {"last_run_id": "2026-05-17T10-00-00-04-00",
                 "last_successful_run_id": "2026-05-17T10-00-00-04-00"},
        "updated_at": "2026-05-17T10:00:00-04:00",
        "stats": {"total_raw_files": 1, "total_runs": 1},
    }
    scan = _scan(
        files=[_scan_file("KDB/raw/a.md", action="CHANGED", h="sha256:bbb",
                          mtime=1700000001.0, size=200)],
        to_compile=["KDB/raw/a.md"],
    )
    cr = {"compiled_sources": [_compiled_source("KDB/raw/a.md", "a-summary",
                                                title="A v2")],
          "success": True, "run_id": ctx.run_id}
    next_state, payload = build_source_state_update(prior, scan, cr, ctx)
    rec = next_state["sources"]["KDB/raw/a.md"]
    assert rec["compile_state"] == "recompiled"
    assert rec["compile_count"] == 2
    assert rec["hash"] == "sha256:bbb"
    assert rec["compiled_title"] == "A v2"
    assert len(rec["previous_versions"]) == 1
    assert payload["sources_changed"] == ["KDB/raw/a.md"]


def test_build_source_state_update_no_pages_in_output() -> None:
    """Output must not contain pages, orphans, or ontology keys."""
    ctx = _ctx()
    scan = _scan(files=[_scan_file("KDB/raw/a.md")])
    cr = {"compiled_sources": [_compiled_source("KDB/raw/a.md", "a-summary")],
          "success": True, "run_id": ctx.run_id}
    next_state, _ = build_source_state_update({}, scan, cr, ctx)
    assert "pages" not in next_state
    assert "orphans" not in next_state
    assert "outgoing_links" not in str(next_state)
    assert "supports_page_existence" not in str(next_state)
    assert "concept_ids" not in str(next_state)
    assert "link_operations" not in str(next_state)
