"""Tests for typed dataclasses — shape fidelity + JSON-ready to_dict()."""
from __future__ import annotations

from kdb_compiler.types import (
    CompiledSource,
    CompileResult,
    ErrorEntry,
    LogEntry,
    PageIntent,
    ReconcileOp,
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
        file_type="markdown", is_binary=False,
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
    p = PageIntent(slug="attention-paper", page_type="summary", title="Attention Paper", body="Body here.")
    d = p.to_dict()
    assert d["slug"] == "attention-paper"
    assert d["status"] == "active" and d["confidence"] == "medium"
    assert d["supports_page_existence"] == [] and d["outgoing_links"] == []


def test_compiled_source_nests_pages() -> None:
    cs = CompiledSource(
        source_id="sha256:" + "d" * 64,
        summary_slug="attention-paper",
        pages=[
            PageIntent(slug="attention-paper", page_type="summary", title="X", body="b"),
            PageIntent(slug="attention-mechanism", page_type="concept", title="Y", body="b"),
        ],
        concept_slugs=["attention-mechanism"],
    )
    d = cs.to_dict()
    assert d["summary_slug"] == "attention-paper"
    assert len(d["pages"]) == 2
    assert d["concept_slugs"] == ["attention-mechanism"]
    assert d["article_slugs"] == []


def test_log_entry_to_dict() -> None:
    le = LogEntry(level="warning", message="ambiguous rename", related_slugs=["x"])
    d = le.to_dict()
    assert d["level"] == "warning" and d["related_slugs"] == ["x"]


def test_compile_result_to_dict_keys() -> None:
    cr = CompileResult(run_id="r", success=True)
    d = cr.to_dict()
    assert set(d) == {"run_id", "success", "compiled_sources", "log_entries", "errors", "warnings"}
