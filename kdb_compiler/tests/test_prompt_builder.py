"""Tests for prompt_builder — system/user assembly for one compile call.

Coverage per blueprint §10:
    - load_system_prompt returns the file at <vault>/KDB/KDB-Compiler-System-Prompt.md
    - load_response_schema_text returns schema text with the expected keys
    - build_prompt system includes the system prompt + contract lines
    - build_prompt user includes source_name, source_text, context, schema, exemplar
    - exemplar_response echoes the supplied source_name and is schema+semantic valid
    - key contract sentences are present verbatim

Plus a drift-guard: the user section order must match what compile_one reads.

Task #41: source-id-space fields (source_id, supports_page_existence,
related_source_ids) no longer appear in LLM-emitted shape — runner
injects them post-parse. Tests use source_name accordingly.
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
    load_response_schema_text,
    load_system_prompt,
)
from kdb_compiler.types import ContextPage, ContextSnapshot
from kdb_compiler.validate_compiled_source_response import semantic_check, validate

SOURCE_NAME = "foo.md"
SOURCE_ID = "KDB/raw/foo.md"  # used only for ContextSnapshot construction

SYSTEM_PROMPT_FILENAME = "KDB-Compiler-System-Prompt.md"


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    """The system prompt is cached per-vault-path; the schema is cached
    globally. Both are memoised via functools.cache — clear between tests
    so per-test vaults don't leak."""
    load_system_prompt.cache_clear()
    load_response_schema_text.cache_clear()


def _write_vault_system_prompt(tmp_path: Path, contents: str) -> Path:
    """Create <tmp_path>/KDB/KDB-Compiler-System-Prompt.md and return the vault root."""
    kdb = tmp_path / "KDB"
    kdb.mkdir(parents=True, exist_ok=True)
    (kdb / SYSTEM_PROMPT_FILENAME).write_text(contents, encoding="utf-8")
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


# ---------- load_system_prompt ----------

def test_load_system_prompt_returns_vault_file(tmp_path: Path) -> None:
    vault = _write_vault_system_prompt(tmp_path, "# invariants doc\n")
    assert load_system_prompt(vault) == "# invariants doc\n"


def test_load_system_prompt_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_system_prompt(tmp_path)  # no KDB/KDB-Compiler-System-Prompt.md under tmp_path


def test_load_system_prompt_cached_per_vault_root(tmp_path: Path) -> None:
    vault_a = _write_vault_system_prompt(tmp_path / "a", "aaa")
    vault_b = _write_vault_system_prompt(tmp_path / "b", "bbb")
    assert load_system_prompt(vault_a) == "aaa"
    assert load_system_prompt(vault_b) == "bbb"
    # mutate file on disk — cached result should not change
    (vault_a / "KDB" / SYSTEM_PROMPT_FILENAME).write_text("MUTATED", encoding="utf-8")
    assert load_system_prompt(vault_a) == "aaa"


# ---------- load_response_schema_text ----------

def test_load_response_schema_text_is_valid_json_with_expected_keys() -> None:
    text = load_response_schema_text()
    schema = json.loads(text)
    # Per-source contract has these top-level schema markers
    assert schema.get("title", "").lower().startswith("kdb compiled source response")
    assert schema["type"] == "object"
    assert "source_name" in schema["properties"]
    assert "summary_slug" in schema["properties"]
    assert "pages" in schema["properties"]
    assert schema["additionalProperties"] is False
    # Task #41: source-id-space fields are NOT in the LLM contract
    assert "source_id" not in schema["properties"]


def test_load_response_schema_text_is_pretty_printed() -> None:
    text = load_response_schema_text()
    assert "\n" in text
    # 2-space indent per blueprint
    assert '\n  "' in text


# ---------- exemplar_response ----------

def test_exemplar_echoes_source_name() -> None:
    ex = exemplar_response("other.md")
    assert ex["source_name"] == "other.md"
    # Task #41: exemplar must NOT include source-id-space fields
    assert "source_id" not in ex
    assert "supports_page_existence" not in ex["pages"][0]


def test_exemplar_passes_schema_and_semantic() -> None:
    """The example we send the model must itself satisfy every rule we
    enforce. Otherwise we'd be training the model on invalid shape."""
    ex = exemplar_response(SOURCE_NAME)
    assert validate(ex) == []
    assert semantic_check(ex, source_name=SOURCE_NAME) == []


# ---------- build_prompt: system ----------

def test_system_includes_system_prompt_and_contract(tmp_path: Path) -> None:
    vault = _write_vault_system_prompt(tmp_path, "# KDB invariants\n\nsome rules\n")
    bp = build_prompt(
        vault_root=vault,
        source_name=SOURCE_NAME,
        source_text="hello",
        context_snapshot=_snapshot(),
    )
    assert "# KDB invariants" in bp.system
    assert "some rules" in bp.system
    assert "RESPONSE CONTRACT (non-negotiable):" in bp.system
    assert "Return EXACTLY ONE JSON object." in bp.system
    assert 'The "source_name" field MUST echo' in bp.system


def test_system_does_not_include_user_sections(tmp_path: Path) -> None:
    vault = _write_vault_system_prompt(tmp_path, "# rules")
    bp = build_prompt(
        vault_root=vault,
        source_name=SOURCE_NAME,
        source_text="hello",
        context_snapshot=_snapshot(),
    )
    assert "## SOURCE CONTENT" not in bp.system
    assert "## RESPONSE SCHEMA" not in bp.system


# ---------- build_prompt: user ----------

def test_user_has_all_four_sections_in_locked_order(tmp_path: Path) -> None:
    vault = _write_vault_system_prompt(tmp_path, "# rules")
    bp = build_prompt(
        vault_root=vault,
        source_name=SOURCE_NAME,
        source_text="SOURCE BODY",
        context_snapshot=_snapshot(),
    )
    src_idx = bp.user.index("## SOURCE CONTENT")
    ctx_idx = bp.user.index("## EXISTING CONTEXT")
    schema_idx = bp.user.index("## RESPONSE SCHEMA")
    ex_idx = bp.user.index("## EXAMPLE RESPONSE")
    assert src_idx < ctx_idx < schema_idx < ex_idx
    # source_name header comes before SOURCE CONTENT
    assert bp.user.index(f"source_name: {SOURCE_NAME}") < src_idx


def test_user_includes_source_text_verbatim(tmp_path: Path) -> None:
    vault = _write_vault_system_prompt(tmp_path, "# rules")
    text = "# Transformers\n\nSelf-attention is the key idea.\n"
    bp = build_prompt(
        vault_root=vault,
        source_name=SOURCE_NAME,
        source_text=text,
        context_snapshot=_snapshot(),
    )
    assert text in bp.user  # verbatim, no truncation


def test_user_includes_context_snapshot_as_json(tmp_path: Path) -> None:
    vault = _write_vault_system_prompt(tmp_path, "# rules")
    snap = _snapshot()
    bp = build_prompt(
        vault_root=vault,
        source_name=SOURCE_NAME,
        source_text="hi",
        context_snapshot=snap,
    )
    expected = json.dumps(snap.to_dict(), indent=2, ensure_ascii=False)
    assert expected in bp.user


def test_user_includes_schema_and_exemplar(tmp_path: Path) -> None:
    vault = _write_vault_system_prompt(tmp_path, "# rules")
    bp = build_prompt(
        vault_root=vault,
        source_name=SOURCE_NAME,
        source_text="hi",
        context_snapshot=_snapshot(),
    )
    # Schema section includes a distinctive schema token
    assert "compiled_source_response.schema.json" in bp.user or '"pageIntent"' in bp.user
    # Exemplar section contains the echoed source_name inside the JSON block
    ex_json = json.dumps(exemplar_response(SOURCE_NAME), indent=2, ensure_ascii=False)
    assert ex_json in bp.user


# ---------- source_meta (D-89-17 amended by D-89-19/D-89-20, v0.2.2) ----------

# Per D-89-19: compiler.py pre-appends key_themes to summary before passing in.
# Per D-89-20: source_meta no longer carries key_themes or key_entities separately.
_SAMPLE_SOURCE_META: dict = {
    "domain": "machine-learning",
    "source_type": "research-paper",
    "author": "Vaswani et al.",
    "summary": (
        "Introduces the Transformer architecture based on self-attention. "
        "Themes: self-attention, parallelization, encoder-decoder."
    ),
}


def test_build_prompt_includes_source_meta_block_when_present(tmp_path: Path) -> None:
    """When source_meta is passed the user prompt contains a '## PASS-1 SOURCE
    METADATA' section with field values and an explicit USE instruction (D-89-17)."""
    vault = _write_vault_system_prompt(tmp_path, "# rules")
    bp = build_prompt(
        vault_root=vault,
        source_name=SOURCE_NAME,
        source_text="hi",
        context_snapshot=_snapshot(),
        source_meta=_SAMPLE_SOURCE_META,
    )
    assert "## PASS-1 SOURCE METADATA" in bp.user
    assert "machine-learning" in bp.user
    assert "research-paper" in bp.user
    assert "Vaswani et al." in bp.user
    assert "USE" in bp.user


def test_build_prompt_omits_source_meta_block_when_absent(tmp_path: Path) -> None:
    """Pre-Pass-1 sources (source_meta=None) get the original prompt unchanged —
    no PASS-1 SOURCE METADATA section appears."""
    vault = _write_vault_system_prompt(tmp_path, "# rules")
    bp = build_prompt(
        vault_root=vault,
        source_name=SOURCE_NAME,
        source_text="hi",
        context_snapshot=_snapshot(),
    )
    assert "## PASS-1 SOURCE METADATA" not in bp.user


def test_build_prompt_summary_carries_appended_themes_per_d_89_19(
    tmp_path: Path,
) -> None:
    """Per D-89-19 (v0.2.2): the summary string in source_meta already carries
    key_themes mechanically appended by compiler.py. The prompt renders that
    string verbatim — no LLM-merge instruction (D-89-18 retracted)."""
    vault = _write_vault_system_prompt(tmp_path, "# rules")
    bp = build_prompt(
        vault_root=vault,
        source_name=SOURCE_NAME,
        source_text="hi",
        context_snapshot=_snapshot(),
        source_meta=_SAMPLE_SOURCE_META,
    )
    # The pre-appended summary appears verbatim
    assert "self-attention" in bp.user
    assert "Themes: self-attention, parallelization, encoder-decoder" in bp.user
    # No D-89-18-style merge-instruction language (the retracted instruction
    # used phrases like "MERGE the Pass-1 summary" and "weave the themes
    # organically"). The new contract says "summary is authoritative; you do
    # not need to rewrite or merge it" — that "or merge" is a prohibition, not
    # an instruction.
    assert "MERGE the Pass-1 summary" not in bp.user
    assert "weave the themes" not in bp.user
    assert "Weave the themes" not in bp.user
    # "authoritative" language present per simplified v0.2.2 contract
    assert "authoritative" in bp.user.lower()


def test_build_prompt_omits_key_entities_seed_section_per_d_89_20(
    tmp_path: Path,
) -> None:
    """Per D-89-20 (v0.2.2): key_entities is no longer threaded to Pass-2 as
    seeds (the 'TREAT key_entities as seed candidates' clause of D-89-17 was
    retracted). The prompt renders no entity-seed section and no 'seed'
    instruction language."""
    vault = _write_vault_system_prompt(tmp_path, "# rules")
    bp = build_prompt(
        vault_root=vault,
        source_name=SOURCE_NAME,
        source_text="hi",
        context_snapshot=_snapshot(),
        source_meta=_SAMPLE_SOURCE_META,
    )
    user_lower = bp.user.lower()
    assert "key_entities" not in user_lower
    assert "key entity seeds" not in user_lower
    assert "seed entity-extraction" not in user_lower


def test_build_prompt_source_meta_section_precedes_source_content(
    tmp_path: Path,
) -> None:
    """The PASS-1 SOURCE METADATA block must appear before SOURCE CONTENT so
    the LLM receives context before reading the body (locked ordering)."""
    vault = _write_vault_system_prompt(tmp_path, "# rules")
    bp = build_prompt(
        vault_root=vault,
        source_name=SOURCE_NAME,
        source_text="hi",
        context_snapshot=_snapshot(),
        source_meta=_SAMPLE_SOURCE_META,
    )
    meta_idx = bp.user.index("## PASS-1 SOURCE METADATA")
    src_idx = bp.user.index("## SOURCE CONTENT")
    assert meta_idx < src_idx


def test_build_prompt_source_meta_excludes_kdb_signal(tmp_path: Path) -> None:
    """kdb_signal is the Pass-1 gatekeeper; once compile runs it's noise.
    Even if caller passes it, the block must not surface it to the LLM."""
    vault = _write_vault_system_prompt(tmp_path, "# rules")
    meta_with_signal = {**_SAMPLE_SOURCE_META, "kdb_signal": "signal"}
    bp = build_prompt(
        vault_root=vault,
        source_name=SOURCE_NAME,
        source_text="hi",
        context_snapshot=_snapshot(),
        source_meta=meta_with_signal,
    )
    assert "kdb_signal" not in bp.user


# ---------- drift guard ----------

def test_response_contract_mentions_semantic_rules() -> None:
    """The contract block the model sees must surface every rule enforced
    by validate_compiled_source_response.semantic_check. If that file grows
    a new rule, either add it to RESPONSE_CONTRACT too or update this
    test deliberately."""
    c = RESPONSE_CONTRACT
    assert "echo the provided source_name verbatim" in c
    assert "EXACTLY ONE JSON object" in c
    assert "DO NOT" in c and "fabricate pages" in c
    # Task #41: source-id-space rules are runner-side, not LLM-side
    assert "supports_page_existence" not in c
    assert "source_id" not in c
