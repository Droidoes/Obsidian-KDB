"""Task #90 Phase E acceptance tests.

E.2 — Non-live: Pass-2 (compile prompt-builder) gracefully handles
    ContextSnapshot.pages=[] from State C. Closes Deepseek F-5's
    unverified-assumption concern at the plumbing layer without burning
    API credits.

Run E.2 (in normal suite):
    python3 -m pytest kdb_compiler/tests/test_t2_end_to_end_pass1_path.py::test_pass2_plumbing_on_empty_context_state_c
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kdb_compiler.prompt_builder import build_prompt
from kdb_compiler.types import ContextSnapshot


# ─── E.2 — Non-live: empty-context prompt plumbing (Deepseek F-5) ──────────


def _write_vault_with_stub_system_prompt(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "KDB").mkdir(parents=True, exist_ok=True)
    (vault / "KDB" / "KDB-Compiler-System-Prompt.md").write_text(
        "# KDB invariants (test stub)\n", encoding="utf-8"
    )
    return vault


def test_pass2_plumbing_on_empty_context_state_c(tmp_path: Path) -> None:
    """E.2 — Verify Pass-2 prompt construction gracefully handles
    ContextSnapshot.pages=[] (the State C production state).

    Deepseek F-5: blueprint v0.1 assumed Pass-2 handles empty context but
    never verified. This test exercises build_prompt directly to confirm:
    (a) no exception, (b) prompt assembled, (c) the EXISTING CONTEXT block
    renders as a valid JSON envelope with empty pages array. No LLM cost.
    """
    vault_root = _write_vault_with_stub_system_prompt(tmp_path)
    empty_snapshot = ContextSnapshot(source_id="KDB/raw/stub.md", pages=[])

    built = build_prompt(
        vault_root=vault_root,
        source_name="stub.md",
        source_text="A trivial note with no substantive content.",
        context_snapshot=empty_snapshot,
    )

    # (a) Prompt assembly returned a BuiltPrompt — no exception.
    assert built.system, "system prompt empty"
    assert built.user, "user prompt empty"

    # (b) The EXISTING CONTEXT block is present and renders empty pages.
    assert "## EXISTING CONTEXT (graph snapshot)" in built.user
    # Extract the JSON block between EXISTING CONTEXT and the next "## " header.
    context_section_start = built.user.index("## EXISTING CONTEXT")
    next_section_start = built.user.index("## ", context_section_start + 5)
    context_section = built.user[context_section_start:next_section_start]
    # Parse the JSON inside the section to verify it's well-formed and pages=[].
    json_start = context_section.index("{")
    json_end = context_section.rindex("}") + 1
    context_doc = json.loads(context_section[json_start:json_end])
    assert context_doc["source_id"] == "KDB/raw/stub.md"
    assert context_doc["pages"] == [], (
        f"Expected empty pages array, got: {context_doc['pages']!r}"
    )

    # (c) Source text + schema + exemplar sections all rendered.
    assert "## SOURCE CONTENT" in built.user
    assert "## RESPONSE SCHEMA" in built.user
    assert "## EXAMPLE RESPONSE" in built.user
