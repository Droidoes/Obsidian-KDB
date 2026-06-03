# ingestion/tests/test_pass1_frontmatter_embedder.py
from pathlib import Path

import pytest

from ingestion.enrich.frontmatter_embedder import (
    embed_frontmatter, parse_existing_frontmatter, build_yaml_block,
)


def test_build_yaml_block_has_sectionalized_comments():
    """Per D-89-16: frontmatter has GraphDB-input + Audit section comments."""
    env = {
        "kdb_signal": "signal", "domain": "ai-ml", "source_type": "blog",
        "author": "Joseph", "summary": "test",
        "key_themes": ["y"], "entity_search_keys": ["y", "z-related"],
        "confidence": 0.9, "uncertainty_reason": None, "reject_reason": None,
        "prompt_version": "1.0.0", "model": "deepseek-v4-flash",
        "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": "signal", "reject_reason_cleared": None},
        "other_reason": None,
    }
    block = build_yaml_block(env)
    assert block.startswith("---\n")
    assert block.endswith("---\n")
    assert "# GraphDB-input section" in block
    assert "# Audit section" in block
    # Field order check: kdb_signal should appear before confidence
    assert block.index("kdb_signal:") < block.index("confidence:")


def test_embed_frontmatter_on_pristine_source(tmp_path):
    src = tmp_path / "essay.md"
    src.write_text("# My Essay\n\nThe body content.\n", encoding="utf-8")
    env = _make_envelope()
    embed_frontmatter(src, env)
    out = src.read_text(encoding="utf-8")
    assert out.startswith("---\n")
    assert "kdb_signal: signal" in out
    assert "# My Essay" in out
    assert "The body content." in out


def test_embed_frontmatter_preserves_body_bytes(tmp_path):
    """The body must be byte-identical to the pre-enrichment version."""
    src = tmp_path / "essay.md"
    body = "# Essay\n\nLine 1\n\nLine 2 with `code`.\n"
    src.write_text(body, encoding="utf-8")
    embed_frontmatter(src, _make_envelope())
    out = src.read_text(encoding="utf-8")
    assert body in out


def test_embed_frontmatter_atomic_via_temp(tmp_path):
    """The write goes through atomic_io: temp file rename, no partial state."""
    # We don't directly test atomicity, but we verify no .tmp files are left behind
    src = tmp_path / "essay.md"
    src.write_text("body\n", encoding="utf-8")
    embed_frontmatter(src, _make_envelope())
    leftover = list(tmp_path.glob("*.tmp"))
    assert leftover == []


def test_re_enrichment_replaces_pass1_fields(tmp_path):
    """When existing frontmatter has stale Pass-1 fields matching previous
    archive, new values replace them."""
    src = tmp_path / "essay.md"
    initial = """---
kdb_signal: noise
domain: undecided
source_type: other
author: null
summary: stale
key_themes: []
entity_search_keys: []
confidence: 0.5
uncertainty_reason: null
reject_reason: stale
prompt_version: 1.0.0
model: old-model
schema_version: 1
override:
  applied: null
  rule: null
  match: null
  llm_original: noise
  reject_reason_cleared: null
other_reason: null
---
The body.
"""
    src.write_text(initial, encoding="utf-8")
    env = _make_envelope()
    env["domain"] = "ai-ml"  # new value
    embed_frontmatter(src, env)
    out = src.read_text(encoding="utf-8")
    assert "domain: ai-ml" in out
    assert "domain: undecided" not in out
    assert "The body." in out


def test_user_added_frontmatter_keys_preserved(tmp_path):
    """User-added non-Pass-1 frontmatter keys must be preserved verbatim."""
    src = tmp_path / "essay.md"
    initial = """---
title: My Custom Title
tags: [favorite, important]
---
The body.
"""
    src.write_text(initial, encoding="utf-8")
    embed_frontmatter(src, _make_envelope())
    out = src.read_text(encoding="utf-8")
    assert "title: My Custom Title" in out
    assert "favorite" in out


def test_parse_existing_frontmatter_handles_missing(tmp_path):
    src = tmp_path / "essay.md"
    src.write_text("Just body. No frontmatter.\n", encoding="utf-8")
    fm, body = parse_existing_frontmatter(src.read_text(encoding="utf-8"))
    assert fm == {}
    assert body == "Just body. No frontmatter.\n"


def test_embed_frontmatter_does_not_strip_trailing_dash_from_other_reason(tmp_path):
    """Regression: rstrip('---\\n') vs removesuffix. If the last YAML value
    ends in '-' or '\\n', a chars-strip would silently corrupt it."""
    src = tmp_path / "essay.md"
    src.write_text(
        "---\n"
        "title: Custom\n"
        "---\n"
        "The body.\n",
        encoding="utf-8",
    )
    env = _make_envelope()
    env["source_type"] = "other"
    env["other_reason"] = "weird-suffix-"  # ends in dash
    embed_frontmatter(src, env)
    out = src.read_text(encoding="utf-8")
    assert "weird-suffix-" in out, f"trailing dash was stripped from other_reason: {out!r}"


def _make_envelope():
    return {
        "kdb_signal": "signal", "domain": "ai-ml", "source_type": "blog",
        "author": "Joseph", "summary": "test",
        "key_themes": ["y"], "entity_search_keys": ["y", "z-related"],
        "confidence": 0.9, "uncertainty_reason": None, "reject_reason": None,
        "prompt_version": "1.0.0", "model": "deepseek-v4-flash",
        "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": "signal", "reject_reason_cleared": None},
        "other_reason": None,
    }
