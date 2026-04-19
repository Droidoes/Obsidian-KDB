"""Tests for typed dataclasses — shape fidelity + JSON-ready to_dict()."""
from __future__ import annotations

from kdb_compiler.types import (
    CompiledSource,
    CompileResult,
    LogEntry,
    PageIntent,
    ReconcileOp,
    ScanEntry,
    ScanResult,
    SkippedEntry,
)


# ---------- ScanEntry ----------

def test_scan_entry_to_dict() -> None:
    e = ScanEntry(
        path="KDB/raw/foo.md",
        current_hash="sha256:" + "a" * 64,
        current_mtime=1700000000.0,
        size_bytes=123,
        file_type="markdown",
        is_binary=False,
        action="NEW",
    )
    d = e.to_dict()
    assert d["path"] == "KDB/raw/foo.md"
    assert d["action"] == "NEW"
    assert d["file_type"] == "markdown"


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
    d = op.to_dict()
    assert d == {
        "type": "DELETED",
        "path": "KDB/raw/gone.md",
        "hash": "sha256:" + "c" * 64,
    }


def test_reconcile_op_hash_optional() -> None:
    op = ReconcileOp(type="DELETED", path="KDB/raw/gone.md")
    d = op.to_dict()
    assert "hash" not in d
    assert d == {"type": "DELETED", "path": "KDB/raw/gone.md"}


# ---------- SkippedEntry ----------

def test_skipped_entry_to_dict() -> None:
    s = SkippedEntry(path="KDB/raw/link.md", reason="symlink")
    assert s.to_dict() == {"path": "KDB/raw/link.md", "reason": "symlink"}


# ---------- ScanResult ----------

def test_scan_result_to_dict_has_all_top_level_keys() -> None:
    sr = ScanResult(
        schema_version="1.0",
        run_id="2026-04-18T00-00-00Z",
        scanned_at="2026-04-18T00:00:00Z",
        vault_root="/tmp/vault",
    )
    d = sr.to_dict()
    assert set(d) == {
        "schema_version", "run_id", "scanned_at", "vault_root",
        "files", "to_compile", "to_reconcile", "skipped", "stats",
    }
    assert d["files"] == [] and d["to_compile"] == [] and d["to_reconcile"] == []
    assert d["skipped"] == [] and d["stats"] == {}


def test_scan_result_serializes_children() -> None:
    sr = ScanResult(
        schema_version="1.0",
        run_id="r",
        scanned_at="2026-04-18T00:00:00Z",
        vault_root="/tmp/vault",
        files=[ScanEntry(
            path="KDB/raw/a.md", current_hash="sha256:" + "a" * 64,
            current_mtime=1.0, size_bytes=1, file_type="markdown",
            is_binary=False, action="NEW",
        )],
        to_reconcile=[ReconcileOp(type="DELETED", path="KDB/raw/b.md")],
        skipped=[SkippedEntry(path="KDB/raw/c.md", reason="symlink")],
    )
    d = sr.to_dict()
    assert d["files"][0]["path"] == "KDB/raw/a.md"
    assert d["to_reconcile"][0] == {"type": "DELETED", "path": "KDB/raw/b.md"}
    assert d["skipped"][0] == {"path": "KDB/raw/c.md", "reason": "symlink"}


# ---------- PageIntent / CompiledSource ----------

def test_page_intent_to_dict_defaults() -> None:
    p = PageIntent(slug="attention-paper", page_type="summary", title="Attention Paper", body="Body here.")
    d = p.to_dict()
    assert d["slug"] == "attention-paper"
    assert d["status"] == "active"
    assert d["confidence"] == "medium"
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
    assert d["source_id"].startswith("sha256:")
    assert d["summary_slug"] == "attention-paper"
    assert len(d["pages"]) == 2
    assert d["pages"][0]["slug"] == "attention-paper"
    assert d["concept_slugs"] == ["attention-mechanism"]
    assert d["article_slugs"] == []


# ---------- LogEntry / CompileResult ----------

def test_log_entry_to_dict() -> None:
    le = LogEntry(level="warning", message="ambiguous rename", related_slugs=["x"], related_source_ids=["sha256:"+"e"*64])
    d = le.to_dict()
    assert d["level"] == "warning"
    assert d["related_slugs"] == ["x"]


def test_compile_result_to_dict_keys() -> None:
    cr = CompileResult(run_id="r", success=True)
    d = cr.to_dict()
    assert set(d) == {"run_id", "success", "compiled_sources", "log_entries", "errors", "warnings"}
    assert d["compiled_sources"] == [] and d["log_entries"] == []
    assert d["errors"] == [] and d["warnings"] == []
