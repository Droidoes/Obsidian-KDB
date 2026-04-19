"""Tests for prompt_builder — system/user assembly for one compile call.

Coverage per blueprint §10:
    - load_claude_md returns the file at <vault>/KDB/CLAUDE.md
    - load_response_schema_text returns schema text with the expected keys
    - build_prompt system includes CLAUDE.md + contract lines
    - build_prompt user includes source_id, source_text, context, schema, exemplar
    - exemplar_response echoes the supplied source_id and is schema+semantic valid
    - key contract sentences are present verbatim

Plus a drift-guard: the user section order must match what compile_one reads.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kdb_compiler import prompt_builder
from kdb_compiler.prompt_builder import (
    RESPONSE_CONTRACT,
    build_prompt,
    exemplar_response,
    load_claude_md,
    load_response_schema_text,
)
from kdb_compiler.types import ContextPage, ContextSnapshot
from kdb_compiler.validate_compiled_source_response import semantic_check, validate

SOURCE_ID = "KDB/raw/foo.md"


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    """CLAUDE.md is cached per-vault-path; the schema is cached globally.
    Both are memoised via functools.cache — clear between tests so per-test
    vaults don't leak."""
    load_claude_md.cache_clear()
    load_response_schema_text.cache_clear()


def _write_vault_claude_md(tmp_path: Path, contents: str) -> Path:
    """Create <tmp_path>/KDB/CLAUDE.md and return the vault root."""
    kdb = tmp_path / "KDB"
    kdb.mkdir(parents=True, exist_ok=True)
    (kdb / "CLAUDE.md").write_text(contents, encoding="utf-8")
    return tmp_path


def _snapshot() -> ContextSnapshot:
    return ContextSnapshot(
        source_id=SOURCE_ID,
        pages=[
            ContextPage(
                slug="attention",
                title="Attention",
                page_type="concept",
                outgoing_links=["self-attention"],
            ),
        ],
    )


# ---------- load_claude_md ----------

def test_load_claude_md_returns_vault_file(tmp_path: Path) -> None:
    vault = _write_vault_claude_md(tmp_path, "# invariants doc\n")
    assert load_claude_md(vault) == "# invariants doc\n"


def test_load_claude_md_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_claude_md(tmp_path)  # no KDB/CLAUDE.md under tmp_path


def test_load_claude_md_cached_per_vault_root(tmp_path: Path) -> None:
    vault_a = _write_vault_claude_md(tmp_path / "a", "aaa")
    vault_b = _write_vault_claude_md(tmp_path / "b", "bbb")
    assert load_claude_md(vault_a) == "aaa"
    assert load_claude_md(vault_b) == "bbb"
    # mutate file on disk — cached result should not change
    (vault_a / "KDB" / "CLAUDE.md").write_text("MUTATED", encoding="utf-8")
    assert load_claude_md(vault_a) == "aaa"


# ---------- load_response_schema_text ----------

def test_load_response_schema_text_is_valid_json_with_expected_keys() -> None:
    text = load_response_schema_text()
    schema = json.loads(text)
    # Per-source contract has these top-level schema markers
    assert schema.get("title", "").lower().startswith("kdb compiled source response")
    assert schema["type"] == "object"
    assert "source_id" in schema["properties"]
    assert "summary_slug" in schema["properties"]
    assert "pages" in schema["properties"]
    assert schema["additionalProperties"] is False


def test_load_response_schema_text_is_pretty_printed() -> None:
    text = load_response_schema_text()
    assert "\n" in text
    # 2-space indent per blueprint
    assert '\n  "' in text


# ---------- exemplar_response ----------

def test_exemplar_echoes_source_id() -> None:
    ex = exemplar_response("KDB/raw/other.md")
    assert ex["source_id"] == "KDB/raw/other.md"
    assert ex["pages"][0]["supports_page_existence"] == ["KDB/raw/other.md"]


def test_exemplar_passes_schema_and_semantic() -> None:
    """The example we send the model must itself satisfy every rule we
    enforce. Otherwise we'd be training the model on invalid shape."""
    ex = exemplar_response(SOURCE_ID)
    assert validate(ex) == []
    assert semantic_check(ex, source_id=SOURCE_ID) == []


# ---------- build_prompt: system ----------

def test_system_includes_claude_md_and_contract(tmp_path: Path) -> None:
    vault = _write_vault_claude_md(tmp_path, "# KDB invariants\n\nsome rules\n")
    bp = build_prompt(
        vault_root=vault,
        source_id=SOURCE_ID,
        source_text="hello",
        context_snapshot=_snapshot(),
    )
    assert "# KDB invariants" in bp.system
    assert "some rules" in bp.system
    assert "RESPONSE CONTRACT (non-negotiable):" in bp.system
    assert "Return EXACTLY ONE JSON object." in bp.system
    assert 'The "source_id" field MUST echo' in bp.system
    assert 'supports_page_existence" array MUST contain' in bp.system


def test_system_does_not_include_user_sections(tmp_path: Path) -> None:
    vault = _write_vault_claude_md(tmp_path, "# rules")
    bp = build_prompt(
        vault_root=vault,
        source_id=SOURCE_ID,
        source_text="hello",
        context_snapshot=_snapshot(),
    )
    assert "## SOURCE CONTENT" not in bp.system
    assert "## RESPONSE SCHEMA" not in bp.system


# ---------- build_prompt: user ----------

def test_user_has_all_four_sections_in_locked_order(tmp_path: Path) -> None:
    vault = _write_vault_claude_md(tmp_path, "# rules")
    bp = build_prompt(
        vault_root=vault,
        source_id=SOURCE_ID,
        source_text="SOURCE BODY",
        context_snapshot=_snapshot(),
    )
    src_idx = bp.user.index("## SOURCE CONTENT")
    ctx_idx = bp.user.index("## EXISTING CONTEXT")
    schema_idx = bp.user.index("## RESPONSE SCHEMA")
    ex_idx = bp.user.index("## EXAMPLE RESPONSE")
    assert src_idx < ctx_idx < schema_idx < ex_idx
    # source_id header comes before SOURCE CONTENT
    assert bp.user.index(f"source_id: {SOURCE_ID}") < src_idx


def test_user_includes_source_text_verbatim(tmp_path: Path) -> None:
    vault = _write_vault_claude_md(tmp_path, "# rules")
    text = "# Transformers\n\nSelf-attention is the key idea.\n"
    bp = build_prompt(
        vault_root=vault,
        source_id=SOURCE_ID,
        source_text=text,
        context_snapshot=_snapshot(),
    )
    assert text in bp.user  # verbatim, no truncation


def test_user_includes_context_snapshot_as_json(tmp_path: Path) -> None:
    vault = _write_vault_claude_md(tmp_path, "# rules")
    snap = _snapshot()
    bp = build_prompt(
        vault_root=vault,
        source_id=SOURCE_ID,
        source_text="hi",
        context_snapshot=snap,
    )
    expected = json.dumps(snap.to_dict(), indent=2, ensure_ascii=False)
    assert expected in bp.user


def test_user_includes_schema_and_exemplar(tmp_path: Path) -> None:
    vault = _write_vault_claude_md(tmp_path, "# rules")
    bp = build_prompt(
        vault_root=vault,
        source_id=SOURCE_ID,
        source_text="hi",
        context_snapshot=_snapshot(),
    )
    # Schema section includes a distinctive schema token
    assert "compiled_source_response.schema.json" in bp.user or '"pageIntent"' in bp.user
    # Exemplar section contains the echoed source_id inside the JSON block
    ex_json = json.dumps(exemplar_response(SOURCE_ID), indent=2, ensure_ascii=False)
    assert ex_json in bp.user


# ---------- drift guard ----------

def test_response_contract_mentions_all_four_semantic_rules() -> None:
    """The contract block the model sees must surface every rule enforced
    by validate_compiled_source_response.semantic_check. If that file grows
    a fifth rule, either add it to RESPONSE_CONTRACT too or update this
    test deliberately."""
    c = RESPONSE_CONTRACT
    assert "echo the provided source_id verbatim" in c
    assert "supports_page_existence" in c
    assert "EXACTLY ONE JSON object" in c
    assert "DO NOT" in c and "fabricate pages" in c
