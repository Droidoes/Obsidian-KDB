"""Tests for manifest_update — pure core + I/O shell + CLI."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from kdb_compiler import manifest_update
from kdb_compiler.manifest_update import (
    PREV_VERSIONS_CAP,
    ManifestInvariantError,
    apply_compile_result,
    apply_scan_reconciliation,
    assert_manifest_invariants,
    build_manifest_update,
    ensure_manifest_shape,
    load_inputs,
    reconcile_incoming_links,
    recompute_stats,
    update,
    write_outputs,
)
from kdb_compiler.run_context import SCHEMA_VERSION, RunContext

H1 = "sha256:" + "1" * 64
H2 = "sha256:" + "2" * 64
H3 = "sha256:" + "3" * 64
H4 = "sha256:" + "4" * 64
H5 = "sha256:" + "5" * 64


def _ctx(run_id: str = "2026-04-19T14-00-00Z",
         started_at: str = "2026-04-19T14:00:00Z") -> RunContext:
    return RunContext(
        run_id=run_id,
        started_at=started_at,
        compiler_version="0.0.0-test",
        schema_version=SCHEMA_VERSION,
        dry_run=False,
        vault_root=Path("/tmp/vault"),
        kdb_root=Path("/tmp/vault/KDB"),
    )


def _file(path: str, action: str, *, h: str = H1, mtime: float = 1700000000.0,
          size: int = 100, file_type: str = "markdown",
          prev_hash: str | None = None, prev_mtime: float | None = None,
          prev_path: str | None = None, is_binary: bool = False) -> dict:
    fe = {
        "path": path, "action": action, "current_hash": h,
        "current_mtime": mtime, "size_bytes": size,
        "file_type": file_type, "is_binary": is_binary,
    }
    if prev_hash is not None:
        fe["previous_hash"] = prev_hash
    if prev_mtime is not None:
        fe["previous_mtime"] = prev_mtime
    if prev_path is not None:
        fe["previous_path"] = prev_path
    return fe


def _scan(*, run_id: str = "2026-04-19T14-00-00Z", files=(), to_compile=(),
          to_reconcile=(), to_skip=(), summary: dict | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "scanned_at": "2026-04-19T14:00:00Z",
        "vault_root": "/tmp/vault",
        "raw_root": "KDB/raw",
        "settings_snapshot": {
            "rename_detection": True, "symlink_policy": "skip",
            "scan_binary_files": True, "binary_compile_mode": "metadata_only",
        },
        "summary": summary or {"new": 0, "changed": 0, "unchanged": 0, "moved": 0,
                                "deleted": 0, "error": 0, "skipped_symlink": 0},
        "files": list(files),
        "to_compile": list(to_compile),
        "to_reconcile": list(to_reconcile),
        "to_skip": list(to_skip),
        "errors": [],
        "skipped_symlinks": [],
    }


def _page(slug: str, ptype: str, title: str = "T", *,
          outgoing_links=(), supports=(), confidence: str = "medium") -> dict:
    return {
        "slug": slug, "page_type": ptype, "title": title, "body": "b",
        "status": "active",
        "supports_page_existence": list(supports),
        "outgoing_links": list(outgoing_links),
        "confidence": confidence,
    }


def _cs(source_id: str, summary_slug: str, pages: list[dict],
        concept_slugs=(), article_slugs=()) -> dict:
    return {
        "source_id": source_id,
        "summary_slug": summary_slug,
        "pages": pages,
        "concept_slugs": list(concept_slugs),
        "article_slugs": list(article_slugs),
    }


def _compile(run_id: str = "2026-04-19T14-00-00Z", *, success: bool = True,
             compiled_sources=(), errors=(), warnings=()) -> dict:
    return {
        "run_id": run_id, "success": success,
        "compiled_sources": list(compiled_sources),
        "log_entries": [],
        "errors": list(errors),
        "warnings": list(warnings),
    }


# ---------- ensure_manifest_shape ----------

def test_ensure_manifest_shape_bootstrap_empty() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx, kb_id="test-kdb")
    assert m["schema_version"] == SCHEMA_VERSION
    assert m["kb_id"] == "test-kdb"
    assert m["created_at"] == ctx.started_at
    assert set(m.keys()) >= {
        "schema_version", "kb_id", "created_at", "updated_at", "settings",
        "stats", "runs", "sources", "pages", "orphans", "tombstones",
    }
    assert m["stats"]["total_runs"] == 0
    assert m["runs"] == {"last_run_id": None, "last_successful_run_id": None}


def test_ensure_manifest_shape_idempotent_on_prior() -> None:
    ctx = _ctx()
    prior = ensure_manifest_shape({}, ctx=ctx)
    prior["kb_id"] = "preserved"
    prior["created_at"] = "1999-01-01T00:00:00Z"
    m = ensure_manifest_shape(prior, ctx=ctx)
    assert m["kb_id"] == "preserved"
    assert m["created_at"] == "1999-01-01T00:00:00Z"


# ---------- scan reconciliation ----------

def test_apply_scan_new_seeds_source_record() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx)
    scan = _scan(files=[_file("KDB/raw/a.md", "NEW")])
    apply_scan_reconciliation(m, scan, ctx)
    rec = m["sources"]["KDB/raw/a.md"]
    assert rec["status"] == "active"
    assert rec["hash"] == H1
    assert rec["compile_count"] == 0
    assert rec["first_seen_at"] == ctx.started_at
    assert rec["previous_versions"] == []


def test_apply_scan_changed_appends_previous_version() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx)
    m["sources"]["KDB/raw/x.md"] = {
        "source_id": "KDB/raw/x.md", "canonical_path": "KDB/raw/x.md",
        "status": "active", "file_type": "markdown",
        "hash": H2, "mtime": 1.0, "size_bytes": 10,
        "first_seen_at": "2026-04-01T00:00:00Z",
        "last_seen_at": "2026-04-01T00:00:00Z",
        "last_compiled_at": "2026-04-01T00:00:00Z",
        "last_run_id": "prev-run", "compile_state": "compiled",
        "compile_count": 1, "summary_page": None,
        "outputs_created": [], "outputs_touched": [], "concept_ids": [],
        "link_operations": {"links_added": 0, "links_removed": 0, "backlink_edits": 0},
        "provenance": {}, "previous_versions": [],
    }
    scan = _scan(files=[_file("KDB/raw/x.md", "CHANGED", h=H1,
                              prev_hash=H2, prev_mtime=1.0)])
    apply_scan_reconciliation(m, scan, ctx)
    rec = m["sources"]["KDB/raw/x.md"]
    assert rec["hash"] == H1
    assert len(rec["previous_versions"]) == 1
    pv = rec["previous_versions"][0]
    assert pv["hash"] == H2 and pv["run_id"] == "prev-run"


def test_apply_scan_unchanged_only_bumps_last_seen() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx)
    base = {
        "source_id": "KDB/raw/u.md", "canonical_path": "KDB/raw/u.md",
        "status": "active", "file_type": "markdown", "hash": H1,
        "mtime": 1.0, "size_bytes": 10,
        "first_seen_at": "2026-04-01T00:00:00Z",
        "last_seen_at": "2026-04-01T00:00:00Z",
        "last_compiled_at": "2026-04-01T00:00:00Z",
        "last_run_id": "prev-run", "compile_state": "compiled",
        "compile_count": 5, "summary_page": "KDB/wiki/summaries/u.md",
        "outputs_created": [], "outputs_touched": [], "concept_ids": [],
        "link_operations": {"links_added": 0, "links_removed": 0, "backlink_edits": 0},
        "provenance": {}, "previous_versions": [],
    }
    m["sources"]["KDB/raw/u.md"] = dict(base)
    scan = _scan(files=[_file("KDB/raw/u.md", "UNCHANGED", h=H1)])
    apply_scan_reconciliation(m, scan, ctx)
    rec = m["sources"]["KDB/raw/u.md"]
    assert rec["last_seen_at"] == ctx.started_at
    assert rec["compile_count"] == 5               # untouched
    assert rec["last_compiled_at"] == "2026-04-01T00:00:00Z"
    assert rec["last_run_id"] == "prev-run"        # untouched


def test_apply_scan_moved_writes_tombstone_and_relocates() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx)
    # Seed old record + a page referencing it.
    m["sources"]["KDB/raw/old.md"] = {
        "source_id": "KDB/raw/old.md", "canonical_path": "KDB/raw/old.md",
        "status": "active", "file_type": "markdown", "hash": H1,
        "mtime": 1.0, "size_bytes": 10, "first_seen_at": "x",
        "last_seen_at": "x", "last_compiled_at": None, "last_run_id": "prev",
        "compile_state": "compiled", "compile_count": 1,
        "summary_page": None, "outputs_created": [], "outputs_touched": [],
        "concept_ids": [], "link_operations": {"links_added": 0, "links_removed": 0, "backlink_edits": 0},
        "provenance": {}, "previous_versions": [],
    }
    m["pages"]["KDB/wiki/summaries/x.md"] = {
        "page_id": "KDB/wiki/summaries/x.md", "slug": "x", "page_type": "summary",
        "status": "active", "title": "T", "created_at": "x", "updated_at": "x",
        "last_run_id": "prev",
        "source_refs": [{"source_id": "KDB/raw/old.md", "hash": H1, "role": "primary"}],
        "supports_page_existence": ["KDB/raw/old.md"],
        "outgoing_links": [], "incoming_links_known": [],
        "last_link_reconciled_at": "x", "confidence": "medium",
        "orphan_candidate": False,
    }
    scan = _scan(files=[_file("KDB/raw/new.md", "MOVED", h=H1,
                              prev_hash=H1, prev_mtime=1.0,
                              prev_path="KDB/raw/old.md")])
    apply_scan_reconciliation(m, scan, ctx)
    assert "KDB/raw/old.md" not in m["sources"]
    assert m["sources"]["KDB/raw/new.md"]["source_id"] == "KDB/raw/new.md"
    assert m["tombstones"]["KDB/raw/old.md"]["moved_to"] == "KDB/raw/new.md"
    # Page rekeyed.
    page = m["pages"]["KDB/wiki/summaries/x.md"]
    assert page["source_refs"][0]["source_id"] == "KDB/raw/new.md"
    assert page["supports_page_existence"] == ["KDB/raw/new.md"]


def test_apply_scan_deleted_writes_tombstone_and_orphans_page() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx)
    m["sources"]["KDB/raw/dead.md"] = {
        "source_id": "KDB/raw/dead.md", "canonical_path": "KDB/raw/dead.md",
        "status": "active", "file_type": "markdown", "hash": H1,
        "mtime": 1.0, "size_bytes": 10, "first_seen_at": "x",
        "last_seen_at": "x", "last_compiled_at": None, "last_run_id": "prev",
        "compile_state": "compiled", "compile_count": 1,
        "summary_page": None, "outputs_created": [], "outputs_touched": [],
        "concept_ids": [], "link_operations": {"links_added": 0, "links_removed": 0, "backlink_edits": 0},
        "provenance": {}, "previous_versions": [],
    }
    m["pages"]["KDB/wiki/summaries/dead.md"] = {
        "page_id": "KDB/wiki/summaries/dead.md", "slug": "dead",
        "page_type": "summary", "status": "active", "title": "T",
        "created_at": "x", "updated_at": "x", "last_run_id": "prev",
        "source_refs": [{"source_id": "KDB/raw/dead.md", "hash": H1, "role": "primary"}],
        "supports_page_existence": ["KDB/raw/dead.md"],
        "outgoing_links": [], "incoming_links_known": [],
        "last_link_reconciled_at": "x", "confidence": "medium",
        "orphan_candidate": False,
    }
    scan = _scan(to_reconcile=[{"type": "DELETED", "path": "KDB/raw/dead.md", "hash": H1}])
    apply_scan_reconciliation(m, scan, ctx)
    assert "KDB/raw/dead.md" not in m["sources"]
    assert m["tombstones"]["KDB/raw/dead.md"]["status"] == "deleted"
    page = m["pages"]["KDB/wiki/summaries/dead.md"]
    assert page["source_refs"] == []
    assert page["supports_page_existence"] == []


# ---------- compile apply ----------

def test_compile_apply_creates_summary_and_concept_pages() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx)
    scan = _scan(files=[_file("KDB/raw/p.md", "NEW")],
                 to_compile=["KDB/raw/p.md"])
    apply_scan_reconciliation(m, scan, ctx)
    cr = _compile(compiled_sources=[_cs(
        "KDB/raw/p.md", "attention-paper",
        pages=[
            _page("attention-paper", "summary", "Attention"),
            _page("attention-mechanism", "concept", "Attention Mechanism"),
        ],
        concept_slugs=["attention-mechanism"],
    )])
    apply_compile_result(m, cr, scan, ctx)
    assert "KDB/wiki/summaries/attention-paper.md" in m["pages"]
    assert "KDB/wiki/concepts/attention-mechanism.md" in m["pages"]
    rec = m["sources"]["KDB/raw/p.md"]
    assert rec["compile_count"] == 1
    assert rec["compile_state"] == "compiled"
    assert rec["summary_page"] == "KDB/wiki/summaries/attention-paper.md"
    assert rec["concept_ids"] == ["attention-mechanism"]
    summary_refs = m["pages"]["KDB/wiki/summaries/attention-paper.md"]["source_refs"]
    assert summary_refs[0]["role"] == "primary"
    assert summary_refs[0]["hash"] == H1
    concept_refs = m["pages"]["KDB/wiki/concepts/attention-mechanism.md"]["source_refs"]
    assert concept_refs[0]["role"] == "supporting"


def test_compile_apply_recompile_updates_link_operations() -> None:
    ctx1 = _ctx(run_id="r1", started_at="2026-04-19T01:00:00Z")
    m = ensure_manifest_shape({}, ctx=ctx1)
    scan1 = _scan(files=[_file("KDB/raw/p.md", "NEW")], to_compile=["KDB/raw/p.md"])
    apply_scan_reconciliation(m, scan1, ctx1)
    cr1 = _compile("r1", compiled_sources=[_cs(
        "KDB/raw/p.md", "x",
        pages=[_page("x", "summary", outgoing_links=["a", "b"])],
    )])
    apply_compile_result(m, cr1, scan1, ctx1)

    ctx2 = _ctx(run_id="r2", started_at="2026-04-19T02:00:00Z")
    scan2 = _scan(run_id="r2",
                  files=[_file("KDB/raw/p.md", "CHANGED", h=H2, prev_hash=H1, prev_mtime=1.0)],
                  to_compile=["KDB/raw/p.md"])
    apply_scan_reconciliation(m, scan2, ctx2)
    cr2 = _compile("r2", compiled_sources=[_cs(
        "KDB/raw/p.md", "x",
        pages=[_page("x", "summary", outgoing_links=["b", "c"])],  # a removed, c added
    )])
    apply_compile_result(m, cr2, scan2, ctx2)
    rec = m["sources"]["KDB/raw/p.md"]
    assert rec["compile_count"] == 2
    assert rec["compile_state"] == "recompiled"
    assert rec["link_operations"] == {"links_added": 1, "links_removed": 1, "backlink_edits": 2}


def test_previous_versions_cap_at_20() -> None:
    rec = {"previous_versions": []}
    for i in range(25):
        manifest_update._append_prev_version(
            rec, hash_=f"sha256:{i:064x}", mtime=float(i),
            size_bytes=i, compiled_at="t", run_id=f"r{i}",
        )
    assert len(rec["previous_versions"]) == PREV_VERSIONS_CAP
    # Oldest 5 evicted (FIFO).
    assert rec["previous_versions"][0]["run_id"] == "r5"
    assert rec["previous_versions"][-1]["run_id"] == "r24"


def test_to_compile_missing_marks_error_and_warns() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx)
    scan = _scan(files=[_file("KDB/raw/p.md", "NEW")],
                 to_compile=["KDB/raw/p.md"])
    apply_scan_reconciliation(m, scan, ctx)
    cr = _compile(compiled_sources=[])  # missing!
    apply_compile_result(m, cr, scan, ctx)
    assert m["sources"]["KDB/raw/p.md"]["compile_state"] == "error"
    assert any("missing compile output" in e["message"] for e in ctx.log_entries)


def test_success_false_policy_applies_partial_and_does_not_advance_success_pointer() -> None:
    prior_runs = {"last_run_id": "r0", "last_successful_run_id": "r0", "total_runs": 1}
    ctx = _ctx(run_id="r1")
    m = ensure_manifest_shape({}, ctx=ctx)
    scan = _scan(files=[_file("KDB/raw/a.md", "NEW"), _file("KDB/raw/b.md", "NEW", h=H2)],
                 to_compile=["KDB/raw/a.md", "KDB/raw/b.md"])
    apply_scan_reconciliation(m, scan, ctx)
    cr = _compile(success=False, compiled_sources=[_cs(
        "KDB/raw/a.md", "a", pages=[_page("a", "summary")],
    )])
    apply_compile_result(m, cr, scan, ctx)
    recompute_stats(m, cr, ctx, prior_runs=prior_runs)

    assert m["sources"]["KDB/raw/a.md"]["compile_state"] == "compiled"
    assert m["sources"]["KDB/raw/b.md"]["compile_state"] == "error"
    assert m["runs"]["last_run_id"] == "r1"
    assert m["runs"]["last_successful_run_id"] == "r0"     # unchanged


# ---------- links ----------

def test_reconcile_incoming_links_derives_known_incoming() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx)
    m["pages"]["KDB/wiki/summaries/a.md"] = {
        "page_id": "KDB/wiki/summaries/a.md", "slug": "a", "page_type": "summary",
        "status": "active", "title": "A", "created_at": "x", "updated_at": "x",
        "last_run_id": "r", "source_refs": [{"source_id": "KDB/raw/a.md", "hash": H1, "role": "primary"}],
        "supports_page_existence": ["KDB/raw/a.md"],
        "outgoing_links": ["b"], "incoming_links_known": [],
        "last_link_reconciled_at": "x", "confidence": "medium", "orphan_candidate": False,
    }
    m["pages"]["KDB/wiki/concepts/b.md"] = {
        "page_id": "KDB/wiki/concepts/b.md", "slug": "b", "page_type": "concept",
        "status": "active", "title": "B", "created_at": "x", "updated_at": "x",
        "last_run_id": "r", "source_refs": [{"source_id": "KDB/raw/a.md", "hash": H1, "role": "supporting"}],
        "supports_page_existence": ["KDB/raw/a.md"],
        "outgoing_links": ["ghost"], "incoming_links_known": [],
        "last_link_reconciled_at": "x", "confidence": "medium", "orphan_candidate": False,
    }
    reconcile_incoming_links(m, ctx)
    assert m["pages"]["KDB/wiki/concepts/b.md"]["incoming_links_known"] == ["a"]
    # Unknown target "ghost" is silently skipped.
    assert m["pages"]["KDB/wiki/summaries/a.md"]["incoming_links_known"] == []


# ---------- orphans ----------

def test_orphan_reactivation_clears_flag_and_orphans_dict() -> None:
    ctx = _ctx(run_id="r2", started_at="2026-04-19T02:00:00Z")
    m = ensure_manifest_shape({}, ctx=ctx)
    # Seed an orphaned page with empty support.
    m["pages"]["KDB/wiki/summaries/p.md"] = {
        "page_id": "KDB/wiki/summaries/p.md", "slug": "p", "page_type": "summary",
        "status": "orphan_candidate", "title": "P",
        "created_at": "x", "updated_at": "x", "last_run_id": "r1",
        "source_refs": [{"source_id": "KDB/raw/p.md", "hash": H1, "role": "primary"}],
        "supports_page_existence": [],
        "outgoing_links": [], "incoming_links_known": [],
        "last_link_reconciled_at": "x", "confidence": "medium",
        "orphan_candidate": True,
    }
    m["orphans"]["KDB/wiki/summaries/p.md"] = {
        "page_id": "KDB/wiki/summaries/p.md", "flagged_at": "x",
        "reason": "r", "previous_supporting_sources": [],
        "recommended_action": "review_manually", "last_run_id": "r1",
    }
    m["sources"]["KDB/raw/p.md"] = {
        "source_id": "KDB/raw/p.md", "canonical_path": "KDB/raw/p.md",
        "status": "active", "file_type": "markdown", "hash": H1,
        "mtime": 1.0, "size_bytes": 10, "first_seen_at": "x",
        "last_seen_at": "x", "last_compiled_at": None, "last_run_id": "r1",
        "compile_state": "compiled", "compile_count": 0,
        "summary_page": None, "outputs_created": [], "outputs_touched": [],
        "concept_ids": [], "link_operations": {"links_added": 0, "links_removed": 0, "backlink_edits": 0},
        "provenance": {}, "previous_versions": [],
    }
    scan = _scan(files=[_file("KDB/raw/p.md", "UNCHANGED")], to_compile=["KDB/raw/p.md"])
    cr = _compile(compiled_sources=[_cs(
        "KDB/raw/p.md", "p",
        pages=[_page("p", "summary", supports=["KDB/raw/p.md"])],
    )])
    apply_compile_result(m, cr, scan, ctx)
    page = m["pages"]["KDB/wiki/summaries/p.md"]
    assert page["status"] == "active"
    assert page["orphan_candidate"] is False
    assert "KDB/wiki/summaries/p.md" not in m["orphans"]


# ---------- stats ----------

def test_recompute_stats_counts_and_rerun_guard() -> None:
    ctx = _ctx(run_id="r1")
    m = ensure_manifest_shape({}, ctx=ctx)
    m["sources"]["s1"] = {}
    m["pages"]["a"] = {"page_type": "summary"}
    m["pages"]["b"] = {"page_type": "concept"}
    m["pages"]["c"] = {"page_type": "article"}
    recompute_stats(m, _compile("r1"), ctx, prior_runs={"last_run_id": None, "total_runs": 0})
    assert m["stats"]["total_raw_files"] == 1
    assert m["stats"]["total_summary_pages"] == 1
    assert m["stats"]["total_concept_pages"] == 1
    assert m["stats"]["total_article_pages"] == 1
    assert m["stats"]["total_pages"] == 3
    assert m["stats"]["total_runs"] == 1
    # Re-run same run_id — total_runs must not increment.
    recompute_stats(m, _compile("r1"), ctx, prior_runs={"last_run_id": "r1", "total_runs": 1})
    assert m["stats"]["total_runs"] == 1


# ---------- invariants ----------

def test_invariant_empty_source_refs_raises() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx)
    m["pages"]["p"] = {"source_refs": []}
    with pytest.raises(ManifestInvariantError, match="empty source_refs"):
        assert_manifest_invariants(m)


def test_invariant_unknown_source_id_in_ref_raises() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx)
    m["pages"]["p"] = {"source_refs": [{"source_id": "missing", "hash": H1, "role": "primary"}]}
    with pytest.raises(ManifestInvariantError, match="references unknown source_id"):
        assert_manifest_invariants(m)


def test_invariant_orphan_not_in_pages_raises() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx)
    m["orphans"]["ghost"] = {}
    with pytest.raises(ManifestInvariantError, match="missing from pages"):
        assert_manifest_invariants(m)


def test_invariant_source_also_in_deleted_tombstone_raises() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx)
    m["sources"]["p"] = {"source_id": "p", "previous_versions": []}
    m["tombstones"]["p"] = {"source_id": "p", "status": "deleted"}
    with pytest.raises(ManifestInvariantError, match="both sources"):
        assert_manifest_invariants(m)


def test_invariant_created_after_updated_raises() -> None:
    ctx = _ctx()
    m = ensure_manifest_shape({}, ctx=ctx)
    m["sources"]["KDB/raw/p.md"] = {
        "source_id": "KDB/raw/p.md", "previous_versions": [],
    }
    m["pages"]["KDB/wiki/summaries/p.md"] = {
        "page_id": "KDB/wiki/summaries/p.md",
        "source_refs": [{"source_id": "KDB/raw/p.md", "hash": H1, "role": "primary"}],
        "created_at": "2026-04-19T02:00:00Z",
        "updated_at": "2026-04-19T01:00:00Z",
    }
    with pytest.raises(ManifestInvariantError, match="created_at > updated_at"):
        assert_manifest_invariants(m)


# ---------- pure orchestrator ----------

def test_build_manifest_update_bootstrap_happy_path() -> None:
    ctx = _ctx(run_id="r1")
    scan = _scan(
        files=[_file("KDB/raw/p.md", "NEW")],
        to_compile=["KDB/raw/p.md"],
        summary={"new": 1, "changed": 0, "unchanged": 0, "moved": 0, "deleted": 0,
                 "error": 0, "skipped_symlink": 0},
    )
    cr = _compile("r1", compiled_sources=[_cs(
        "KDB/raw/p.md", "paper",
        pages=[_page("paper", "summary", "Paper"),
               _page("idea", "concept", "Idea")],
        concept_slugs=["idea"],
    )])
    m, j = build_manifest_update({}, scan, cr, ctx)
    assert m["schema_version"] == SCHEMA_VERSION
    assert m["stats"]["total_pages"] == 2
    assert m["stats"]["total_runs"] == 1
    assert m["runs"]["last_run_id"] == "r1"
    assert m["runs"]["last_successful_run_id"] == "r1"
    # Journal shape.
    assert j["run_id"] == "r1"
    assert j["success"] is True
    assert sorted(j["deltas"]["pages_created"]) == [
        "KDB/wiki/concepts/idea.md", "KDB/wiki/summaries/paper.md",
    ]
    assert j["deltas"]["sources_added"] == ["KDB/raw/p.md"]


def test_build_manifest_update_second_run_same_runid_does_not_double_count() -> None:
    ctx1 = _ctx(run_id="r1", started_at="2026-04-19T01:00:00Z")
    scan = _scan(
        files=[_file("KDB/raw/p.md", "NEW")], to_compile=["KDB/raw/p.md"],
        summary={"new": 1, "changed": 0, "unchanged": 0, "moved": 0, "deleted": 0,
                 "error": 0, "skipped_symlink": 0},
    )
    cr = _compile("r1", compiled_sources=[_cs(
        "KDB/raw/p.md", "p", pages=[_page("p", "summary", "P")],
    )])
    m1, _ = build_manifest_update({}, scan, cr, ctx1)
    assert m1["stats"]["total_runs"] == 1

    ctx_same = _ctx(run_id="r1", started_at="2026-04-19T02:00:00Z")
    m2, _ = build_manifest_update(m1, scan, cr, ctx_same)
    assert m2["stats"]["total_runs"] == 1  # unchanged


# ---------- I/O: write_outputs ordering ----------

def test_write_outputs_journal_before_manifest(tmp_path: Path) -> None:
    ctx = _ctx(run_id="r1")
    scan = _scan(files=[_file("KDB/raw/p.md", "NEW")], to_compile=["KDB/raw/p.md"],
                 summary={"new": 1, "changed": 0, "unchanged": 0, "moved": 0, "deleted": 0,
                          "error": 0, "skipped_symlink": 0})
    cr = _compile("r1", compiled_sources=[_cs(
        "KDB/raw/p.md", "p", pages=[_page("p", "summary")],
    )])
    m, j = build_manifest_update({}, scan, cr, ctx)
    write_outputs(m, j, tmp_path, ctx)
    journal_path = tmp_path / "runs" / "r1.json"
    manifest_path = tmp_path / "manifest.json"
    assert journal_path.exists() and manifest_path.exists()
    # Journal was written first → its mtime should be ≤ manifest's mtime.
    assert journal_path.stat().st_mtime_ns <= manifest_path.stat().st_mtime_ns
    # sort_keys discipline: keys appear in alpha order at top level.
    with manifest_path.open() as f:
        txt = f.read()
    keys_in_order = [line.split(":", 1)[0].strip().strip('"')
                     for line in txt.splitlines()
                     if line.startswith("  \"")]
    assert keys_in_order == sorted(keys_in_order)


# ---------- public update() ----------

def _write_state(state_root: Path, scan: dict, cr: dict,
                 manifest: dict | None = None) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "last_scan.json").write_text(json.dumps(scan), encoding="utf-8")
    (state_root / "compile_result.json").write_text(json.dumps(cr), encoding="utf-8")
    if manifest is not None:
        (state_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_update_writes_and_returns(tmp_path: Path) -> None:
    scan = _scan(files=[_file("KDB/raw/p.md", "NEW")], to_compile=["KDB/raw/p.md"],
                 summary={"new": 1, "changed": 0, "unchanged": 0, "moved": 0, "deleted": 0,
                          "error": 0, "skipped_symlink": 0})
    cr = _compile(compiled_sources=[_cs(
        "KDB/raw/p.md", "p", pages=[_page("p", "summary")],
    )])
    _write_state(tmp_path, scan, cr)
    ctx = _ctx(run_id=scan["run_id"])
    m, j = update(tmp_path, run_ctx=ctx, write=True)
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "runs" / f"{ctx.run_id}.json").exists()
    assert m["stats"]["total_runs"] == 1


def test_update_dry_run_does_not_write(tmp_path: Path) -> None:
    scan = _scan(files=[_file("KDB/raw/p.md", "NEW")], to_compile=["KDB/raw/p.md"],
                 summary={"new": 1, "changed": 0, "unchanged": 0, "moved": 0, "deleted": 0,
                          "error": 0, "skipped_symlink": 0})
    cr = _compile(compiled_sources=[_cs(
        "KDB/raw/p.md", "p", pages=[_page("p", "summary")],
    )])
    _write_state(tmp_path, scan, cr)
    ctx = _ctx(run_id=scan["run_id"])
    ctx.dry_run = True
    m, _ = update(tmp_path, run_ctx=ctx, write=True)
    assert not (tmp_path / "manifest.json").exists()
    assert not (tmp_path / "runs").exists()
    assert m["stats"]["total_runs"] == 1


def test_load_inputs_mismatched_run_id_raises(tmp_path: Path) -> None:
    _write_state(tmp_path, _scan(run_id="rA"), _compile("rB"))
    with pytest.raises(ValueError, match="run_id mismatch"):
        load_inputs(tmp_path)


def test_load_inputs_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_inputs(tmp_path)


# ---------- CLI ----------

def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "kdb_compiler.manifest_update", *args],
        capture_output=True, text=True,
    )


def test_cli_happy_path_exits_zero(tmp_path: Path) -> None:
    scan = _scan(files=[_file("KDB/raw/p.md", "NEW")], to_compile=["KDB/raw/p.md"],
                 summary={"new": 1, "changed": 0, "unchanged": 0, "moved": 0, "deleted": 0,
                          "error": 0, "skipped_symlink": 0})
    cr = _compile(compiled_sources=[_cs(
        "KDB/raw/p.md", "p", pages=[_page("p", "summary")],
    )])
    _write_state(tmp_path, scan, cr)
    r = _run_cli(["--state-root", str(tmp_path)])
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "manifest.json").exists()


def test_cli_dry_run_skips_writes(tmp_path: Path) -> None:
    scan = _scan(files=[_file("KDB/raw/p.md", "NEW")], to_compile=["KDB/raw/p.md"],
                 summary={"new": 1, "changed": 0, "unchanged": 0, "moved": 0, "deleted": 0,
                          "error": 0, "skipped_symlink": 0})
    cr = _compile(compiled_sources=[_cs(
        "KDB/raw/p.md", "p", pages=[_page("p", "summary")],
    )])
    _write_state(tmp_path, scan, cr)
    r = _run_cli(["--state-root", str(tmp_path), "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "manifest.json").exists()


def test_cli_missing_input_exits_two(tmp_path: Path) -> None:
    r = _run_cli(["--state-root", str(tmp_path)])
    assert r.returncode == 2


def test_cli_runid_mismatch_exits_two(tmp_path: Path) -> None:
    _write_state(tmp_path, _scan(run_id="rA"), _compile("rB"))
    r = _run_cli(["--state-root", str(tmp_path)])
    assert r.returncode == 2
