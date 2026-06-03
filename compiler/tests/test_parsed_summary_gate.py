"""Gate test: parsed_summary populated iff parse_ok=True in compile_one.

The gate expression lives in compiler/compiler.py's `finally` block:

    parsed_summary = (
        build_parsed_summary(state["parsed_json"])
        if (state["parse_ok"] and isinstance(state["parsed_json"], dict))
        else None
    )

This test drives the *real* compiler path (not a unit-test of the
expression) and asserts both branches via the on-disk resp-stats record,
which is the authoritative evidence pattern used throughout test_compiler.py.

Phase-B note: the gate was lifted out of build_resp_stats (common/llm_telemetry)
into compile_one's finally block when the resp_stats_writer module was split
into common/llm_telemetry (generic) + compiler/resp_summary (compiler-only).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler import compiler, prompt_builder
from common.call_model import ModelResponse
from common.run_context import RunContext
from common.types import CompileJob, ContextSnapshot

SOURCE_A = "KDB/raw/gate_test.md"


@pytest.fixture(autouse=True)
def _clear_prompt_caches() -> None:
    prompt_builder.load_system_prompt.cache_clear()
    prompt_builder.load_response_schema_text.cache_clear()


def _write_vault(tmp_path: Path) -> Path:
    (tmp_path / "KDB").mkdir(parents=True, exist_ok=True)
    (tmp_path / "KDB" / "KDB-Compiler-System-Prompt.md").write_text(
        "# KDB invariants\n\nRule 1: be honest.\n", encoding="utf-8"
    )
    (tmp_path / "KDB" / "state").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_raw(vault: Path, source_id: str, body: str = "body") -> None:
    p = vault / source_id
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _job(vault: Path, source_id: str) -> CompileJob:
    return CompileJob(
        source_id=source_id,
        abs_path=str(vault / source_id),
        context_snapshot=ContextSnapshot(source_id=source_id, pages=[]),
    )


def _resp_stats_record(state_root: Path, run_id: str) -> dict:
    files = sorted((state_root / "llm_resp" / run_id).glob("*.json"))
    assert len(files) == 1, f"expected exactly 1 resp-stats file, found: {files}"
    return json.loads(files[0].read_text(encoding="utf-8"))


def _good_response(source_id: str) -> dict:
    return {
        "source_name": Path(source_id).name,
        "summary_slug": "summary-gate",
        "concept_slugs": [],
        "article_slugs": [],
        "pages": [
            {
                "slug": "summary-gate",
                "page_type": "summary",
                "title": "Gate Summary",
                "body": "Body.",
                "status": "active",
                "outgoing_links": [],
                "confidence": "medium",
            }
        ],
        "log_entries": [],
        "warnings": [],
    }


def test_parsed_summary_gate_both_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """parsed_summary on the resp-stats record is None when parse_ok=False
    (malformed JSON → state["parse_ok"] stays False) and is not None when
    parse_ok=True (valid compile response).

    Drives the real compiler.compile_one path so the gate expression in the
    finally block is exercised directly, not re-implemented in the test.
    Both branches are in one function so the test count stays at exactly +1.
    """
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "gate body")
    state_root = vault / "KDB" / "state"

    # --- branch 1: parse_ok=False → parsed_summary must be None ---
    # Text passes extract (bare {...}) but fails json.loads (double comma).
    ctx_bad = RunContext.new(dry_run=False, vault_root=vault)
    bad_mr = ModelResponse(
        text='{"source_id": "x",,}',
        input_tokens=10, output_tokens=5, latency_ms=1,
        model="m", provider="anthropic", attempts=1,
    )
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        lambda _req: bad_mr,
    )
    compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault, state_root=state_root, ctx=ctx_bad,
        provider="anthropic", model="m", max_tokens=4096,
    )
    record_bad = _resp_stats_record(state_root, ctx_bad.run_id)
    assert record_bad["parse_ok"] is False, "precondition: parse must have failed"
    assert record_bad["parsed_summary"] is None, (
        "gate: parsed_summary must be None when parse_ok=False"
    )

    # --- branch 2: parse_ok=True → parsed_summary must not be None ---
    ctx_good = RunContext.new(dry_run=False, vault_root=vault)
    good_mr = ModelResponse(
        text=json.dumps(_good_response(SOURCE_A)),
        input_tokens=100, output_tokens=50, latency_ms=10,
        model="m", provider="anthropic", attempts=1,
    )
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        lambda _req: good_mr,
    )
    compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault, state_root=state_root, ctx=ctx_good,
        provider="anthropic", model="m", max_tokens=4096,
    )
    record_good = _resp_stats_record(state_root, ctx_good.run_id)
    assert record_good["parse_ok"] is True, "precondition: parse must have succeeded"
    assert record_good["parsed_summary"] is not None, (
        "gate: parsed_summary must be populated when parse_ok=True"
    )
    assert record_good["parsed_summary"]["page_count"] == 1
