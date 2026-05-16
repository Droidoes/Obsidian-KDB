"""Tests for the Task #66 one-shot last_compiled_hash migration."""
from __future__ import annotations

from scripts.migrate_task66_compiled_hash import backfill_manifest

_ABSENT = object()


def _src(*, hash, compile_state, last_compiled_hash=_ABSENT):
    rec = {"hash": hash, "compile_state": compile_state}
    if last_compiled_hash is not _ABSENT:
        rec["last_compiled_hash"] = last_compiled_hash
    return rec


def test_backfill_sets_hash_for_compiled_state():
    h = "sha256:" + "a" * 64
    manifest = {"sources": {"KDB/raw/a.md": _src(hash=h, compile_state="compiled")}}
    report = backfill_manifest(manifest, repair_error_sources=[])
    assert manifest["sources"]["KDB/raw/a.md"]["last_compiled_hash"] == h
    assert "KDB/raw/a.md" in report["backfilled"]


def test_backfill_sets_hash_for_recompiled_and_metadata_only():
    h = "sha256:" + "b" * 64
    manifest = {"sources": {
        "KDB/raw/r.md": _src(hash=h, compile_state="recompiled"),
        "KDB/raw/x.png": _src(hash=h, compile_state="metadata_only"),
    }}
    backfill_manifest(manifest, repair_error_sources=[])
    assert manifest["sources"]["KDB/raw/r.md"]["last_compiled_hash"] == h
    assert manifest["sources"]["KDB/raw/x.png"]["last_compiled_hash"] == h


def test_backfill_leaves_error_markdown_absent():
    h = "sha256:" + "c" * 64
    manifest = {"sources": {
        "KDB/raw/e.md": dict(_src(hash=h, compile_state="error"), file_type="markdown"),
    }}
    report = backfill_manifest(manifest, repair_error_sources=[])
    assert "last_compiled_hash" not in manifest["sources"]["KDB/raw/e.md"]
    assert "KDB/raw/e.md" in report["left_eligible"]


def test_backfill_sets_hash_for_error_binary():
    # a binary has no LLM compile — metadata recording IS successful processing
    # (Q6); even a binary mis-marked compile_state=="error" is compiled-at-hash.
    h = "sha256:" + "c" * 64
    manifest = {"sources": {
        "KDB/raw/x.png": dict(_src(hash=h, compile_state="error"), file_type="binary"),
    }}
    report = backfill_manifest(manifest, repair_error_sources=[])
    assert manifest["sources"]["KDB/raw/x.png"]["last_compiled_hash"] == h
    assert "KDB/raw/x.png" in report["backfilled"]


def test_backfill_is_idempotent():
    h = "sha256:" + "d" * 64
    manifest = {"sources": {
        "KDB/raw/a.md": _src(hash=h, compile_state="compiled", last_compiled_hash=h),
    }}
    report = backfill_manifest(manifest, repair_error_sources=[])
    assert report["backfilled"] == []


def test_repair_reverts_error_then_backfill_sets_hash():
    h = "sha256:" + "e" * 64
    manifest = {"sources": {"KDB/raw/EP1.md": _src(hash=h, compile_state="error")}}
    report = backfill_manifest(manifest, repair_error_sources=["KDB/raw/EP1.md"])
    rec = manifest["sources"]["KDB/raw/EP1.md"]
    assert rec["compile_state"] == "recompiled"
    assert rec["last_compiled_hash"] == h
    assert "KDB/raw/EP1.md" in report["repaired"]


def test_repair_skips_source_not_in_error_state():
    h = "sha256:" + "f" * 64
    manifest = {"sources": {"KDB/raw/EP1.md": _src(hash=h, compile_state="recompiled")}}
    report = backfill_manifest(manifest, repair_error_sources=["KDB/raw/EP1.md"])
    assert "KDB/raw/EP1.md" in report["repair_skipped"]
