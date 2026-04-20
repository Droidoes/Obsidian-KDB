"""Integration tests for kdb_compile — end-to-end orchestrator (M1.7)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from kdb_compiler.call_model import ModelResponse
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


def _write_vault_claude_md(vault: Path) -> None:
    """prompt_builder needs <vault>/KDB/CLAUDE.md — any content works."""
    claude = vault / "KDB" / "CLAUDE.md"
    claude.parent.mkdir(parents=True, exist_ok=True)
    claude.write_text("# KDB invariants (test)\n", encoding="utf-8")


def _good_model_response(source_id: str, run_id: str) -> ModelResponse:
    payload = {
        "source_id": source_id,
        "summary_slug": "paper",
        "concept_slugs": [],
        "article_slugs": [],
        "pages": [{
            "slug": "paper",
            "page_type": "summary",
            "title": "Paper",
            "body": "Live-compiled body.",
            "status": "active",
            "supports_page_existence": [source_id],
            "outgoing_links": [],
            "confidence": "medium",
        }],
        "log_entries": [],
        "warnings": [],
    }
    return ModelResponse(
        text=json.dumps(payload),
        input_tokens=10,
        output_tokens=5,
        latency_ms=10,
        model="claude-opus-4-7",
        provider="anthropic",
        attempts=1,
    )


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
    assert not (vault / "KDB/wiki/index.md").exists()
    assert (vault / "KDB/wiki/log.md").exists()
    assert (state / "manifest.json").exists()
    runs_dir = state / "runs"
    assert runs_dir.is_dir()
    assert any(runs_dir.iterdir())


# ---------------------------------------------------------------------------
# Test 3 — Missing compile_result.json triggers live compile (mocked)
# ---------------------------------------------------------------------------

def test_missing_compile_result_triggers_live_compile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under the M2 hybrid, no fixture → compiler.run_compile is invoked.
    Mock the model seam so no real API call is made. Success is threaded
    through to the orchestrator and downstream writes run."""
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper\nContent.", encoding="utf-8")
    _write_vault_claude_md(vault)
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault)

    def fake_call(req):
        # Extract source_id from prompt to echo it back correctly.
        source_id = req.prompt.splitlines()[0][len("source_id: "):]
        return _good_model_response(source_id, ctx.run_id)
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry", fake_call
    )

    result = compile(vault, run_ctx=ctx)

    assert result.success is True
    assert (state / "compile_result.json").exists()
    assert (state / "manifest.json").exists()
    # Resp-stats record written by the inner compile_one call.
    assert any((state / "llm_resp" / ctx.run_id).glob("*.json"))


# ---------------------------------------------------------------------------
# Test 4 — run_id mismatch between scan and compile_result
# ---------------------------------------------------------------------------

def test_stale_compile_result_falls_through_to_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A compile_result.json from a prior run (mismatched run_id) is stale
    and must be ignored — the orchestrator falls through to a live compile
    and overwrites it. Guards against the trap where a leftover artifact
    from the previous run permanently short-circuits new runs."""
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper\nContent.", encoding="utf-8")
    _write_vault_claude_md(vault)
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault)
    # Stale CR from a "previous run" — wrong run_id, different slug.
    _write_cr(state, _cr(_RUN2_ID, "KDB/raw/paper.md", "stale-slug"))

    def fake_call(req):
        source_id = req.prompt.splitlines()[0][len("source_id: "):]
        return _good_model_response(source_id, ctx.run_id)
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry", fake_call
    )

    result = compile(vault, run_ctx=ctx)

    assert result.success is True
    # Live compile overwrote the stale file with current run_id.
    cr = json.loads((state / "compile_result.json").read_text())
    assert cr["run_id"] == _RUN1_ID
    # Stale slug never materialised; live slug did.
    assert not (vault / "KDB/wiki/summaries/stale-slug.md").exists()
    assert (vault / "KDB/wiki/summaries/paper.md").exists()


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
# Test 10 — CLI exits 1 on malformed compile_result.json (deterministic fail)
# ---------------------------------------------------------------------------

def test_cli_exits_1_on_malformed_compile_result(tmp_path: Path) -> None:
    """Under the M2 hybrid a missing compile_result.json triggers live
    compile; to exercise the CLI's non-zero exit path without invoking the
    LLM, plant a malformed compile_result.json which fails JSON parse
    before any compile branch runs."""
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper", encoding="utf-8")
    (state / "compile_result.json").write_text(
        "{ not valid json !!!", encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, "-m", "kdb_compiler.kdb_compile",
         "--vault-root", str(vault), "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "unreadable" in result.stderr


# ---------------------------------------------------------------------------
# Test 11 — CLI summary line format on a deterministic failure
# ---------------------------------------------------------------------------

def test_cli_summary_line_format(tmp_path: Path) -> None:
    """CLI always prints a kdb_compile: summary line — whether success or failure."""
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper", encoding="utf-8")
    (state / "compile_result.json").write_text(
        "{ not valid json !!!", encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, "-m", "kdb_compiler.kdb_compile",
         "--vault-root", str(vault), "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "kdb_compile:" in result.stdout
    assert "unreadable" in result.stderr


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


# ---------------------------------------------------------------------------
# Test 15 — Empty raw/ + no compile_result fixture: live-compile no-op
# ---------------------------------------------------------------------------

def test_empty_plan_live_compile_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No sources, no fixture. The hybrid invokes compiler.run_compile,
    which synthesises a successful empty CompileResult. Orchestrator then
    proceeds through apply/write as a no-op — manifest and journal are
    still written."""
    vault, raw, state = _make_vault(tmp_path)
    _write_vault_claude_md(vault)
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault)

    def should_not_call(_req):
        raise AssertionError("no sources — call_model must never run")
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry", should_not_call
    )

    result = compile(vault, run_ctx=ctx)

    assert result.success is True
    assert result.pages_written == []
    assert result.manifest_written is True
    assert result.journal_written is True
    assert (state / "manifest.json").exists()
    assert (state / "compile_result.json").exists()


# ---------------------------------------------------------------------------
# Test 16 — Fixture branch still works; compiler NOT invoked when present
# ---------------------------------------------------------------------------

def test_fixture_branch_does_not_invoke_compiler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When compile_result.json is pre-staged, the live-compile branch is
    skipped entirely — even call_model won't trip. Guards against the
    hybrid accidentally running both branches."""
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper\nContent.", encoding="utf-8")
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault)
    _write_cr(state, _cr(_RUN1_ID, "KDB/raw/paper.md", "paper"))

    calls: list[object] = []
    def track(req):
        calls.append(req)
        raise AssertionError("compiler.run_compile must not run in fixture branch")
    monkeypatch.setattr("kdb_compiler.compiler.call_model_with_retry", track)

    result = compile(vault, run_ctx=ctx)
    assert result.success is True
    assert calls == []


# ---------------------------------------------------------------------------
# Stage-progress events (Option A — kdb_compile §progress)
# ---------------------------------------------------------------------------

_EXPECTED_STAGES = (
    "scan", "validate scan", "compile", "validate compile_result",
    "build manifest update", "apply pages", "persist state",
)


def _capture_progress() -> tuple[list[tuple[str, dict]], "object"]:
    """Return (events, callback). Callback appends (event_name, fields) tuples."""
    events: list[tuple[str, dict]] = []
    def _cb(event: str, **f: object) -> None:
        events.append((event, dict(f)))
    return events, _cb


def test_stage_events_emit_in_order_wet_run(tmp_path: Path) -> None:
    """All seven stage_start/stage_done pairs arrive in the correct sequence
    for a happy-path wet run with monotonic indices and names from _STAGES."""
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper\nSome content.", encoding="utf-8")
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault)
    _write_cr(state, _cr(_RUN1_ID, "KDB/raw/paper.md", "paper"))

    events, cb = _capture_progress()
    result = compile(vault, run_ctx=ctx, progress=cb)
    assert result.success is True

    stage_events = [(e, f) for e, f in events if e in ("stage_start", "stage_done")]
    # 7 starts + 7 dones = 14 stage events, strictly alternating.
    assert len(stage_events) == 14
    for i in range(7):
        start_evt, start_f = stage_events[2 * i]
        done_evt, done_f = stage_events[2 * i + 1]
        assert start_evt == "stage_start"
        assert done_evt == "stage_done"
        assert start_f["index"] == done_f["index"] == i + 1
        assert start_f["total"] == done_f["total"] == 7
        assert start_f["name"] == done_f["name"] == _EXPECTED_STAGES[i]
        assert done_f["ok"] is True
        assert isinstance(done_f["latency_ms"], int)
        assert done_f["latency_ms"] >= 0


def test_stage_events_abort_after_failed_validation(tmp_path: Path) -> None:
    """Malformed compile_result.json fails stage 4 — stages 1-3 emit done-ok,
    stage 4 emits done-not-ok with a note, stages 5-7 do NOT emit."""
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper\n", encoding="utf-8")
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault)
    # Missing required fields → validate_compile_result rejects.
    bad_cr = {"run_id": _RUN1_ID, "success": True}  # no compiled_sources
    _write_cr(state, bad_cr)

    events, cb = _capture_progress()
    result = compile(vault, run_ctx=ctx, progress=cb)
    assert result.success is False

    stage_done = [f for e, f in events if e == "stage_done"]
    # Stages 1, 2, 3 complete OK; stage 4 reports failure; 5-7 never emit.
    assert [s["index"] for s in stage_done] == [1, 2, 3, 4]
    assert all(s["ok"] for s in stage_done[:3])
    assert stage_done[3]["ok"] is False
    assert stage_done[3]["name"] == "validate compile_result"
    assert stage_done[3]["note"]  # non-empty — carries the first validation error


def test_stage_7_skipped_under_dry_run(tmp_path: Path) -> None:
    """Dry-run still emits stage_done for 'persist state' — with the
    'skipped (dry-run)' note — and neither manifest nor journal is written."""
    vault, raw, state = _make_vault(tmp_path)
    (raw / "paper.md").write_text("# Paper\n", encoding="utf-8")
    ctx = _ctx(_RUN1_ID, _RUN1_AT, vault, dry_run=True)
    _write_cr(state, _cr(_RUN1_ID, "KDB/raw/paper.md", "paper"))

    events, cb = _capture_progress()
    result = compile(vault, run_ctx=ctx, progress=cb)
    assert result.success is True
    assert result.manifest_written is False
    assert result.journal_written is False

    persist_done = next(
        f for e, f in events
        if e == "stage_done" and f["index"] == 7
    )
    assert persist_done["ok"] is True
    assert persist_done["note"] == "skipped (dry-run)"
    assert not (state / "manifest.json").exists()
    assert not (state / "runs").exists() or not any((state / "runs").iterdir())
