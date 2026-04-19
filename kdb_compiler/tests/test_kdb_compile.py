"""Integration tests for kdb_compile — end-to-end orchestrator (M1.7)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from kdb_compiler.kdb_compile import CompileRunResult, compile
from kdb_compiler.run_context import SCHEMA_VERSION, RunContext

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RUN1_ID = "2026-04-19T10-00-00Z"
_RUN1_AT = "2026-04-19T10:00:00Z"
_RUN2_ID = "2026-04-19T11-00-00Z"
_RUN2_AT = "2026-04-19T11:00:00Z"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(run_id: str, started_at: str, vault_root: Path, *,
         dry_run: bool = False) -> RunContext:
    return RunContext(
        run_id=run_id,
        started_at=started_at,
        compiler_version="0.0.0-test",
        schema_version=SCHEMA_VERSION,
        dry_run=dry_run,
        vault_root=vault_root,
        kdb_root=vault_root / "KDB",
    )


def _make_vault(root: Path) -> tuple[Path, Path, Path]:
    """Create KDB directory skeleton; return (vault, raw, state)."""
    vault = root / "vault"
    raw = vault / "KDB" / "raw"
    state = vault / "KDB" / "state"
    raw.mkdir(parents=True)
    state.mkdir(parents=True)
    return vault, raw, state


def _cr(run_id: str, source_id: str, slug: str, *,
        body: str = "Body content.",
        concept_slug: str | None = None) -> dict:
    """Minimal valid compile_result for one source."""
    pages: list[dict] = [{
        "slug": slug,
        "page_type": "summary",
        "title": slug.replace("-", " ").title(),
        "status": "active",
        "body": body,
        "supports_page_existence": [source_id],
        "outgoing_links": [concept_slug] if concept_slug else [],
        "confidence": "high",
    }]
    if concept_slug:
        pages.append({
            "slug": concept_slug,
            "page_type": "concept",
            "title": concept_slug.replace("-", " ").title(),
            "status": "active",
            "body": f"Concept linked from [[{slug}]].",
            "supports_page_existence": [source_id],
            "outgoing_links": [slug],
            "confidence": "medium",
        })
    return {
        "run_id": run_id,
        "success": True,
        "compiled_sources": [{
            "source_id": source_id,
            "summary_slug": slug,
            "concept_slugs": [concept_slug] if concept_slug else [],
            "article_slugs": [],
            "pages": pages,
        }],
        "log_entries": [],
    }


def _empty_cr(run_id: str) -> dict:
    return {"run_id": run_id, "success": True, "compiled_sources": []}


def _write_cr(state: Path, cr: dict) -> None:
    (state / "compile_result.json").write_text(json.dumps(cr), encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1 — Happy path dry-run
# ---------------------------------------------------------------------------

def test_happy_path_dry_run(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper\nSome content.", encoding="utf-8")
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault, dry_run=True)
    _write_cr(state, _cr(_RUN1_ID, "KDB/raw/paper.md", "paper"))

    result = compile(vault, run_ctx=ctx)

    assert result.success is True
    assert result.dry_run is True
    assert result.pages_written == []
    assert result.manifest_written is False
    assert result.journal_written is False
    assert result.errors == []


# ---------------------------------------------------------------------------
# Test 2 — Happy path wet-run: all outputs written
# ---------------------------------------------------------------------------

def test_happy_path_wet_run(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper\nSome content.", encoding="utf-8")
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault)
    _write_cr(state, _cr(_RUN1_ID, "KDB/raw/paper.md", "paper"))

    result = compile(vault, run_ctx=ctx)

    assert result.success is True
    assert result.manifest_written is True
    assert result.journal_written is True
    assert "KDB/wiki/summaries/paper.md" in result.pages_written
    assert (vault / "KDB/wiki/summaries/paper.md").exists()
    assert (vault / "KDB/wiki/index.md").exists()
    assert (vault / "KDB/wiki/log.md").exists()
    assert (state / "manifest.json").exists()
    runs_dir = state / "runs"
    assert runs_dir.is_dir()
    assert any(runs_dir.iterdir())


# ---------------------------------------------------------------------------
# Test 3 — Missing compile_result.json → clear failure, no traceback
# ---------------------------------------------------------------------------

def test_missing_compile_result(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper", encoding="utf-8")
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault)
    # Do NOT write compile_result.json

    result = compile(vault, run_ctx=ctx)

    assert result.success is False
    assert len(result.errors) == 1
    assert "compile_result.json not found" in result.errors[0]
    assert "M2 compile step" in result.errors[0]
    assert not (state / "manifest.json").exists()


# ---------------------------------------------------------------------------
# Test 4 — run_id mismatch between scan and compile_result
# ---------------------------------------------------------------------------

def test_run_id_mismatch(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper", encoding="utf-8")
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault)
    # Compile result has a different run_id
    _write_cr(state, _cr(_RUN2_ID, "KDB/raw/paper.md", "paper"))

    result = compile(vault, run_ctx=ctx)

    assert result.success is False
    assert any("run_id mismatch" in e for e in result.errors)
    assert not (state / "manifest.json").exists()


# ---------------------------------------------------------------------------
# Test 5 — Malformed compile_result.json → failure, no partial writes
# ---------------------------------------------------------------------------

def test_malformed_compile_result(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper", encoding="utf-8")
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault)
    (state / "compile_result.json").write_text("{ not valid json !!!", encoding="utf-8")

    result = compile(vault, run_ctx=ctx)

    assert result.success is False
    assert any("unreadable" in e for e in result.errors)
    assert not (state / "manifest.json").exists()


# ---------------------------------------------------------------------------
# Test 6 — Empty raw/ → zero pages, manifest bootstrapped
# ---------------------------------------------------------------------------

def test_empty_raw_dir(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    # raw/ exists but has no files
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault)
    _write_cr(state, _empty_cr(_RUN1_ID))

    result = compile(vault, run_ctx=ctx)

    assert result.success is True
    assert result.pages_written == []
    assert result.manifest_written is True
    assert (state / "manifest.json").exists()


# ---------------------------------------------------------------------------
# Test 7 — Second run incremental: CHANGED file updates page on disk
# ---------------------------------------------------------------------------

def test_second_run_incremental(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    src = raw / "paper.md"

    # Run 1
    src.write_text("# Paper\nFirst version.", encoding="utf-8")
    ctx1 = _ctx(_RUN1_ID, _RUN1_AT, vault)
    _write_cr(state, _cr(_RUN1_ID, "KDB/raw/paper.md", "paper", body="First version body."))
    result1 = compile(vault, run_ctx=ctx1)
    assert result1.success is True

    page_path = vault / "KDB/wiki/summaries/paper.md"
    assert "First version body." in page_path.read_text()

    # Modify source (different content → different hash)
    src.write_text("# Paper\nSecond version — updated.", encoding="utf-8")

    # Run 2
    ctx2 = _ctx(_RUN2_ID, _RUN2_AT, vault)
    _write_cr(state, _cr(_RUN2_ID, "KDB/raw/paper.md", "paper", body="Second version body."))
    result2 = compile(vault, run_ctx=ctx2)
    assert result2.success is True

    assert "Second version body." in page_path.read_text()
    manifest = json.loads((state / "manifest.json").read_text())
    source = manifest["sources"]["KDB/raw/paper.md"]
    assert source["compile_count"] >= 2


# ---------------------------------------------------------------------------
# Test 8 — Moved file: tombstone written, page rekeyed in manifest
# ---------------------------------------------------------------------------

def test_moved_file(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)

    # Run 1: source-a.md
    (raw / "source-a.md").write_text("# Source A\nContent.", encoding="utf-8")
    ctx1 = _ctx(_RUN1_ID, _RUN1_AT, vault)
    _write_cr(state, _cr(_RUN1_ID, "KDB/raw/source-a.md", "source-a"))
    result1 = compile(vault, run_ctx=ctx1)
    assert result1.success is True

    # Rename (same content → same hash → MOVED detected by scan)
    (raw / "source-a.md").rename(raw / "source-b.md")

    # Run 2: compile result references new path; empty compiled_sources (no recompile needed)
    ctx2 = _ctx(_RUN2_ID, _RUN2_AT, vault)
    _write_cr(state, _empty_cr(_RUN2_ID))
    result2 = compile(vault, run_ctx=ctx2)
    assert result2.success is True

    manifest = json.loads((state / "manifest.json").read_text())
    assert "KDB/raw/source-b.md" in manifest["sources"]
    # Old path appears in tombstones or was reconciled as MOVED
    tombstones = manifest.get("tombstones", {})
    assert any("source-a" in k for k in tombstones)


# ---------------------------------------------------------------------------
# Test 9 — Dry-run leaves absolutely no artifacts
# ---------------------------------------------------------------------------

def test_dry_run_leaves_no_artifacts(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper", encoding="utf-8")
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault, dry_run=True)
    _write_cr(state, _cr(_RUN1_ID, "KDB/raw/paper.md", "paper"))

    result = compile(vault, dry_run=True, run_ctx=ctx)

    assert result.success is True
    # No state files written (compile_result.json was INPUT, not output)
    assert not (state / "last_scan.json").exists()
    assert not (state / "manifest.json").exists()
    assert not (state / "runs").exists()
    # No wiki pages written
    assert not (vault / "KDB" / "wiki").exists()


# ---------------------------------------------------------------------------
# Test 10 — CLI exits 1 with clear message when compile_result.json is missing
# ---------------------------------------------------------------------------

def test_cli_exits_1_missing_compile_result(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper", encoding="utf-8")
    # No compile_result.json planted

    result = subprocess.run(
        [sys.executable, "-m", "kdb_compiler.kdb_compile",
         "--vault-root", str(vault), "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "compile_result.json not found" in result.stderr


# ---------------------------------------------------------------------------
# Test 11 — CLI summary line format on successful empty-vault dry-run
# ---------------------------------------------------------------------------

def test_cli_summary_line_format(tmp_path: Path) -> None:
    """CLI always prints a kdb_compile: summary line — whether success or failure."""
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper", encoding="utf-8")
    # No compile_result.json → deterministic failure with known error message

    result = subprocess.run(
        [sys.executable, "-m", "kdb_compiler.kdb_compile",
         "--vault-root", str(vault), "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "kdb_compile:" in result.stdout
    assert "compile_result.json not found" in result.stderr


# ---------------------------------------------------------------------------
# Test 12 — CLI missing --vault-root exits 2
# ---------------------------------------------------------------------------

def test_cli_missing_vault_root_exits_2() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "kdb_compiler.kdb_compile"],
        capture_output=True, text=True,
    )
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Test 13 — CLI invalid vault (no KDB/) exits 1
# ---------------------------------------------------------------------------

def test_cli_invalid_vault_exits_1(tmp_path: Path) -> None:
    empty_dir = tmp_path / "no_kdb"
    empty_dir.mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "kdb_compiler.kdb_compile",
         "--vault-root", str(empty_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "KDB" in result.stderr


# ---------------------------------------------------------------------------
# Test 14 — Compile_result with invalid schema fails validation, no writes
# ---------------------------------------------------------------------------

def test_invalid_compile_result_schema(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper", encoding="utf-8")
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault)
    # Missing required "success" field and invalid compiled_sources type
    (state / "compile_result.json").write_text(
        json.dumps({"run_id": _RUN1_ID, "compiled_sources": "not-a-list"}),
        encoding="utf-8",
    )

    result = compile(vault, run_ctx=ctx)

    assert result.success is False
    assert len(result.errors) > 0
    assert not (state / "manifest.json").exists()
