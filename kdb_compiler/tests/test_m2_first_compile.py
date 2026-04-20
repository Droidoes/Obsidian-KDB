"""test_m2_first_compile — env-blocked live compile smoke test.

Skipped unless `KDB_RUN_LIVE_API=1`. When enabled, runs ONE real
Anthropic compile against case01's source.md and verifies the response
passes schema + semantic validation and that an eval record lands on
disk. Costs a single API call per run — not suitable for CI.

To run:
    ANTHROPIC_API_KEY=... KDB_RUN_LIVE_API=1 \\
        .venv/bin/python3 -m pytest kdb_compiler/tests/test_m2_first_compile.py -s

This is the "green-light" milestone per blueprint §14.6: the first
evidence that the entire M2 stack (planner → prompt_builder → call_model
→ response_normalizer → validator → eval_writer) works end-to-end
against a real provider.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from kdb_compiler import compiler, validate_compiled_source_response
from kdb_compiler.run_context import RunContext
from kdb_compiler.types import CompileJob, ContextSnapshot

_LIVE_ENV = "KDB_RUN_LIVE_API"
_CASE_DIR = Path(__file__).parent / "fixtures" / "eval" / "case01_minimal_summary"

pytestmark = pytest.mark.skipif(
    os.environ.get(_LIVE_ENV) != "1",
    reason=f"set {_LIVE_ENV}=1 to run the live-API smoke test",
)


def _write_vault_claude_md(vault: Path) -> None:
    claude = vault / "KDB" / "CLAUDE.md"
    claude.parent.mkdir(parents=True, exist_ok=True)
    # Use the real vault's CLAUDE.md if available, else a minimal stub.
    real = Path.home() / "Obsidian" / "KDB" / "CLAUDE.md"
    if real.exists():
        shutil.copy(real, claude)
    else:
        claude.write_text("# KDB invariants (test stub)\n", encoding="utf-8")


def test_first_real_compile_end_to_end(tmp_path: Path) -> None:
    """One live Anthropic call against case01's source. Verifies that:
      - compile_one returns a non-None CompiledSource
      - the response passes schema + semantic checks
      - exactly one eval record is written under <state>/llm_eval/<run_id>/
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_vault_claude_md(vault)
    state_root = vault / "KDB" / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    source_id = "KDB/raw/transformer.md"
    abs_path = vault / source_id
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        (_CASE_DIR / "source.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    ctx = RunContext.new(dry_run=False, vault_root=vault)
    job = CompileJob(
        source_id=source_id,
        abs_path=str(abs_path),
        context_snapshot=ContextSnapshot(source_id=source_id, pages=[]),
    )

    cs, logs, warnings, err = compiler.compile_one(
        job,
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
    )

    assert err is None, f"live compile failed: {err}"
    assert cs is not None
    assert cs.source_id == source_id

    payload = cs.to_dict()
    # Remove compile_meta (per-source schema doesn't know about it).
    payload.pop("compile_meta", None)
    # Re-attach the run-level fields the response schema requires.
    payload["log_entries"] = logs
    payload["warnings"] = warnings

    schema_errors = validate_compiled_source_response.validate(payload)
    assert schema_errors == [], schema_errors
    semantic_errors = validate_compiled_source_response.semantic_check(
        payload, source_id=source_id
    )
    assert semantic_errors == [], semantic_errors

    eval_dir = state_root / "llm_eval" / ctx.run_id
    records = list(eval_dir.glob("*.json"))
    assert len(records) == 1

    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["extract_ok"] is True
    assert record["parse_ok"] is True
    assert record["schema_ok"] is True
    assert record["semantic_ok"] is True
    assert record["input_tokens"] > 0
    assert record["output_tokens"] > 0
