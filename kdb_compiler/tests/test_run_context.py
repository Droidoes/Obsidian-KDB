"""Tests for run_context — the single source of run-time metadata (D8)."""
from __future__ import annotations

import re
from pathlib import Path

from kdb_compiler import run_context
from kdb_compiler.run_context import RunContext, SCHEMA_VERSION


# Local ISO: '2026-04-19T22:34:09-04:00' (offset) or '...+00:00' (UTC-tz machine).
ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$"
)


def test_now_iso_format() -> None:
    ts = run_context.now_iso()
    assert ISO_RE.match(ts), ts


RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}_[A-Za-z0-9+\-]+$")


def test_run_id_from_timestamp_is_filename_safe() -> None:
    rid = run_context.run_id_from_timestamp("2026-04-18T12:34:56-04:00")
    assert ":" not in rid
    # Wall-clock portion is deterministic; TZ suffix depends on the
    # system zone (EDT/EST on the dev box; UTC in CI containers).
    assert rid.startswith("2026-04-18T12-34-56_")
    assert RUN_ID_RE.match(rid), rid


def test_runcontext_new_populates_fields(tmp_path: Path) -> None:
    ctx = RunContext.new(vault_root=tmp_path, dry_run=True)
    assert ISO_RE.match(ctx.started_at)
    assert RUN_ID_RE.match(ctx.run_id), ctx.run_id
    assert ctx.schema_version == SCHEMA_VERSION
    assert ctx.dry_run is True
    assert ctx.vault_root == tmp_path
    assert ctx.kdb_root == tmp_path / "KDB"
    assert isinstance(ctx.compiler_version, str) and ctx.compiler_version
    assert ctx.log_entries == []


def test_runcontext_dry_run_default_false(tmp_path: Path) -> None:
    ctx = RunContext.new(vault_root=tmp_path)
    assert ctx.dry_run is False


def test_frontmatter_for_shape(tmp_path: Path) -> None:
    ctx = RunContext.new(vault_root=tmp_path)
    fm = ctx.frontmatter_for(
        raw_path="KDB/raw/note.md",
        raw_hash="sha256:" + "a" * 64,
        raw_mtime=1_700_000_000.0,
    )
    assert set(fm) == {
        "raw_path", "raw_hash", "raw_mtime",
        "compiled_at", "compiler_version", "schema_version_used",
    }
    assert fm["raw_path"] == "KDB/raw/note.md"
    assert fm["raw_hash"].startswith("sha256:")
    assert fm["compiled_at"] == ctx.started_at
    assert fm["compiler_version"] == ctx.compiler_version
    assert fm["schema_version_used"] == ctx.schema_version


def test_append_log_accumulates(tmp_path: Path) -> None:
    ctx = RunContext.new(vault_root=tmp_path)
    ctx.append_log("info", "scan started", stage="scan")
    ctx.append_log("warning", "skipped symlink", path="KDB/raw/a.md")
    assert len(ctx.log_entries) == 2
    first, second = ctx.log_entries
    assert first["level"] == "info"
    assert first["message"] == "scan started"
    assert first["run_id"] == ctx.run_id
    assert first["stage"] == "scan"
    assert second["level"] == "warning"
    assert second["path"] == "KDB/raw/a.md"
