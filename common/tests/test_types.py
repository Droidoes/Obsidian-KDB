"""Tests for typed dataclasses — shape fidelity + JSON-ready to_dict()."""
from __future__ import annotations

from common.types import (
    CompiledSource,
    CompileResult,
    ErrorEntry,
    PageIntent,
    ReconcileOp,
    RespStatsRecord,
    ScanEntry,
    ScanResult,
    ScanSummary,
    SettingsSnapshot,
    SkippedSymlinkEntry,
)


# ---------- ScanEntry ----------

def test_scan_entry_new_to_dict_omits_previous_fields() -> None:
    e = ScanEntry(
        path="KDB/raw/foo.md",
        action="NEW",
        current_hash="sha256:" + "a" * 64,
        current_mtime=1700000000.0,
        size_bytes=123,
        file_type="markdown",
        is_binary=False,
        compiled_hash=None,
    )
    d = e.to_dict()
    assert d["path"] == "KDB/raw/foo.md" and d["action"] == "NEW"
    assert "previous_hash" not in d and "previous_mtime" not in d and "previous_path" not in d


def test_scan_entry_changed_includes_previous_fields() -> None:
    e = ScanEntry(
        path="KDB/raw/x.md",
        action="CHANGED",
        current_hash="sha256:" + "a" * 64,
        current_mtime=2.0,
        size_bytes=1,
        file_type="markdown",
        is_binary=False,
        compiled_hash="sha256:" + "b" * 64,
        previous_hash="sha256:" + "b" * 64,
        previous_mtime=1.0,
    )
    d = e.to_dict()
    assert d["previous_hash"] == "sha256:" + "b" * 64
    assert d["previous_mtime"] == 1.0
    assert "previous_path" not in d


def test_scan_entry_moved_includes_previous_path() -> None:
    e = ScanEntry(
        path="KDB/raw/new-loc.md",
        action="MOVED",
        current_hash="sha256:" + "a" * 64,
        current_mtime=2.0,
        size_bytes=1,
        file_type="markdown",
        is_binary=False,
        compiled_hash="sha256:" + "a" * 64,
        previous_hash="sha256:" + "a" * 64,
        previous_mtime=1.0,
        previous_path="KDB/raw/old-loc.md",
    )
    d = e.to_dict()
    assert d["previous_path"] == "KDB/raw/old-loc.md"


# ---------- ReconcileOp ----------

def test_reconcile_op_moved_uses_from_to_keys() -> None:
    op = ReconcileOp(type="MOVED", from_path="KDB/raw/old.md", to_path="KDB/raw/new.md", hash="sha256:" + "b" * 64)
    d = op.to_dict()
    assert d == {
        "type": "MOVED",
        "from": "KDB/raw/old.md",
        "to": "KDB/raw/new.md",
        "hash": "sha256:" + "b" * 64,
    }
    assert "from_path" not in d and "to_path" not in d


def test_reconcile_op_deleted_shape() -> None:
    op = ReconcileOp(type="DELETED", path="KDB/raw/gone.md", hash="sha256:" + "c" * 64)
    assert op.to_dict() == {
        "type": "DELETED",
        "path": "KDB/raw/gone.md",
        "hash": "sha256:" + "c" * 64,
    }


def test_reconcile_op_hash_optional() -> None:
    op = ReconcileOp(type="DELETED", path="KDB/raw/gone.md")
    d = op.to_dict()
    assert "hash" not in d and d == {"type": "DELETED", "path": "KDB/raw/gone.md"}


# ---------- error / skipped / summary / settings ----------

def test_error_entry_to_dict() -> None:
    assert ErrorEntry(path="KDB/raw/x.md", error="perm denied").to_dict() == {
        "path": "KDB/raw/x.md", "error": "perm denied",
    }


def test_skipped_symlink_entry_defaults() -> None:
    assert SkippedSymlinkEntry(path="KDB/raw/l.md").to_dict() == {
        "path": "KDB/raw/l.md", "link_target": None,
    }


def test_scan_summary_defaults_all_zero() -> None:
    d = ScanSummary().to_dict()
    assert d == {"new": 0, "changed": 0, "unchanged": 0, "moved": 0,
                 "deleted": 0, "error": 0, "skipped_symlink": 0}


def test_settings_snapshot_to_dict() -> None:
    s = SettingsSnapshot(
        rename_detection=True, symlink_policy="skip",
        scan_binary_files=True, binary_compile_mode="metadata_only",
    )
    assert s.to_dict() == {
        "rename_detection": True, "symlink_policy": "skip",
        "scan_binary_files": True, "binary_compile_mode": "metadata_only",
    }


# ---------- ScanResult ----------

def _empty_result() -> ScanResult:
    return ScanResult(
        schema_version="1.0",
        run_id="r",
        scanned_at="2026-04-19T00:00:00Z",
        vault_root="/tmp/vault",
        raw_root="KDB/raw",
        settings_snapshot=SettingsSnapshot(True, "skip", True, "metadata_only"),
        summary=ScanSummary(),
    )


def test_scan_result_to_dict_has_all_top_level_keys() -> None:
    d = _empty_result().to_dict()
    assert set(d) == {
        "schema_version", "run_id", "scanned_at", "vault_root", "raw_root",
        "settings_snapshot", "summary", "files", "to_compile", "to_reconcile",
        "to_skip", "errors", "skipped_symlinks",
    }
    assert d["files"] == [] and d["to_compile"] == []
    assert d["to_reconcile"] == [] and d["to_skip"] == []
    assert d["errors"] == [] and d["skipped_symlinks"] == []


def test_scan_result_serializes_children() -> None:
    sr = _empty_result()
    sr.files = [ScanEntry(
        path="KDB/raw/a.md", action="NEW",
        current_hash="sha256:" + "a" * 64, current_mtime=1.0, size_bytes=1,
        file_type="markdown", is_binary=False, compiled_hash=None,
    )]
    sr.to_reconcile = [ReconcileOp(type="DELETED", path="KDB/raw/b.md")]
    sr.skipped_symlinks = [SkippedSymlinkEntry(path="KDB/raw/c.md", link_target="../elsewhere.md")]
    sr.errors = [ErrorEntry(path="KDB/raw/e.md", error="OSError: read")]
    d = sr.to_dict()
    assert d["files"][0]["path"] == "KDB/raw/a.md"
    assert d["to_reconcile"][0] == {"type": "DELETED", "path": "KDB/raw/b.md"}
    assert d["skipped_symlinks"][0] == {"path": "KDB/raw/c.md", "link_target": "../elsewhere.md"}
    assert d["errors"][0] == {"path": "KDB/raw/e.md", "error": "OSError: read"}


# ---------- PageIntent / CompiledSource (unchanged contracts) ----------

def test_page_intent_to_dict_defaults() -> None:
    # #115: LLM-authored fields only — status/outgoing_links/confidence gone
    p = PageIntent(slug="attention-paper", page_type="summary", title="Attention Paper", body="Body here.")
    d = p.to_dict()
    assert d["slug"] == "attention-paper"
    assert d["supports_page_existence"] == []
    assert "status" not in d and "confidence" not in d and "outgoing_links" not in d


def test_compiled_source_nests_pages() -> None:
    cs = CompiledSource(
        source_id="sha256:" + "d" * 64,
        pages=[
            PageIntent(slug="attention-paper", page_type="summary", title="X", body="b"),
            PageIntent(slug="attention-mechanism", page_type="concept", title="Y", body="b"),
        ],
    )
    d = cs.to_dict()
    assert "summary_slug" not in d  # #115: derived, never emitted
    assert len(d["pages"]) == 2
    assert "concept_slugs" not in d and "article_slugs" not in d


def test_summary_page_helper() -> None:
    # #115: fail-closed unique-summary lookup (dual-mode with legacy summary_slug)
    from common.types import SummaryPageError, summary_page
    cs = {"source_id": "s", "pages": [
        {"slug": "c1", "page_type": "concept"},
        {"slug": "summary-s", "page_type": "summary", "title": "S"},
    ]}
    assert summary_page(cs)["slug"] == "summary-s"
    import pytest
    with pytest.raises(SummaryPageError):
        summary_page({"source_id": "s", "pages": []})
    with pytest.raises(SummaryPageError):
        summary_page({"source_id": "s", "pages": [
            {"slug": "a", "page_type": "summary"},
            {"slug": "b", "page_type": "summary"},
        ]})


def test_compile_result_to_dict_keys() -> None:
    cr = CompileResult(run_id="r", success=True)
    d = cr.to_dict()
    assert set(d) == {"run_id", "success", "compiled_sources", "errors", "compilation_notes"}


# ---------- RespStatsRecord (#114 recovery telemetry) ----------

def test_resp_stats_record_boundary_fields_default_and_serialize():
    rec = RespStatsRecord(
        run_id="r", source_id="s", provider="p", model="m",
        attempts=1, latency_ms=1, input_tokens=1, output_tokens=1,
        prompt_hash="h", response_hash="h",
        extract_ok=False, parse_ok=True, schema_ok=True, semantic_ok=True,
        boundary_recovered=True, prefix_discarded_chars=3, tail_discarded_chars=2,
    )
    d = rec.to_dict()
    assert d["boundary_recovered"] is True
    assert d["prefix_discarded_chars"] == 3 and d["tail_discarded_chars"] == 2


def test_resp_stats_record_boundary_defaults():
    rec = RespStatsRecord(
        run_id="r", source_id="s", provider="p", model="m",
        attempts=1, latency_ms=1, input_tokens=1, output_tokens=1,
        prompt_hash="h", response_hash="h",
        extract_ok=True, parse_ok=True, schema_ok=True, semantic_ok=True,
    )
    d = rec.to_dict()
    assert d["boundary_recovered"] is False
    assert d["prefix_discarded_chars"] == 0 and d["tail_discarded_chars"] == 0


def test_resp_stats_record_list_parsed_json_roundtrips():
    """#114 any-value recovery: on schema failure a list payload can flow
    through parsed_json — it must still serialize via to_dict()."""
    payload = [{"slug": "a"}, {"slug": "b"}]
    rec = RespStatsRecord(
        run_id="r", source_id="s", provider="p", model="m",
        attempts=1, latency_ms=1, input_tokens=1, output_tokens=1,
        prompt_hash="h", response_hash="h",
        extract_ok=True, parse_ok=True, schema_ok=False, semantic_ok=False,
        parsed_json=payload,
    )
    d = rec.to_dict()
    assert d["parsed_json"] == payload
