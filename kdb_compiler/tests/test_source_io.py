"""Unit tests for kdb_compiler.source_io.

Covers the shared parse_source_file() helper consumed by the orchestrator
and compiler (Task #90 D-90-10). Provides direct coverage previously implicit
via compiler.source_text_for tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kdb_compiler.source_io import SourceFrontmatter, parse_source_file


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_pass1_enriched_full_envelope(tmp_path: Path) -> None:
    """Pass-1 enriched file with all required keys + non-empty entity_search_keys."""
    src = _write(
        tmp_path / "essay.md",
        "---\n"
        "kdb_signal: signal\n"
        "domain: ai-ml\n"
        "source_type: blog\n"
        "author: Joseph\n"
        "summary: Notes on transformers.\n"
        "key_themes:\n"
        "  - attention-mechanism\n"
        "  - scaling-laws\n"
        "entity_search_keys:\n"
        "  - attention-mechanism\n"
        "  - scaling-laws\n"
        "  - transformers\n"
        "---\n"
        "Body of the essay.\n",
    )
    fm, body = parse_source_file(src)
    assert isinstance(fm, SourceFrontmatter)
    assert fm.kdb_signal == "signal"
    assert fm.domain == "ai-ml"
    assert fm.source_type == "blog"
    assert fm.author == "Joseph"
    assert fm.summary == "Notes on transformers."
    assert fm.key_themes == ["attention-mechanism", "scaling-laws"]
    assert fm.entity_search_keys == ["attention-mechanism", "scaling-laws", "transformers"]
    assert "Body of the essay." in body
    assert "kdb_signal" not in body


def test_state_c_explicit_empty_entity_search_keys(tmp_path: Path) -> None:
    """State C per D-90-8: Pass-1 enriched with explicit entity_search_keys: []."""
    src = _write(
        tmp_path / "stub.md",
        "---\n"
        "kdb_signal: signal\n"
        "domain: undecided\n"
        "source_type: note\n"
        "summary: Trivial stub.\n"
        "key_themes: []\n"
        "entity_search_keys: []\n"
        "---\n"
        "Stub body.\n",
    )
    fm, body = parse_source_file(src)
    assert isinstance(fm, SourceFrontmatter)
    assert fm.entity_search_keys == []
    assert fm.key_themes == []
    assert "Stub body." in body


def test_pre_pass1_no_frontmatter(tmp_path: Path) -> None:
    """Source with no YAML frontmatter at all (pre-Pass-1 enrichment)."""
    src = _write(tmp_path / "old.md", "# Some heading\n\nJust body text.\n")
    fm, body = parse_source_file(src)
    assert fm is None
    assert body == "# Some heading\n\nJust body text.\n"


def test_yaml_present_but_missing_required_keys(tmp_path: Path) -> None:
    """YAML frontmatter exists but lacks required Pass-1 GraphDB-input keys."""
    src = _write(
        tmp_path / "partial.md",
        "---\n"
        "title: An old note\n"
        "tags: [misc]\n"
        "---\n"
        "Body.\n",
    )
    fm, body = parse_source_file(src)
    assert fm is None
    assert "Body." in body
    assert "title:" not in body  # frontmatter block stripped


def test_malformed_yaml_falls_back_to_full_content(tmp_path: Path) -> None:
    """Malformed YAML → (None, full_raw_content) per parse_existing_frontmatter degrade."""
    src = _write(
        tmp_path / "broken.md",
        "---\n"
        "kdb_signal: signal\n"
        "  this is: not valid: yaml: at all:\n"  # broken indent + multiple colons
        "---\n"
        "Body.\n",
    )
    fm, body = parse_source_file(src)
    assert fm is None
    # Body fallback: full raw content (frontmatter block NOT stripped)
    assert "kdb_signal" in body


def test_pre_v0_2_2_without_entity_search_keys_defaults_to_empty(tmp_path: Path) -> None:
    """Pre-v0.2.2 enriched frontmatter (no entity_search_keys field) defaults to []."""
    src = _write(
        tmp_path / "old_enriched.md",
        "---\n"
        "kdb_signal: signal\n"
        "domain: ai-ml\n"
        "source_type: blog\n"
        "summary: Pre-v0.2.2.\n"
        "key_themes: [foo, bar]\n"
        "---\n"
        "Body.\n",
    )
    fm, body = parse_source_file(src)
    assert isinstance(fm, SourceFrontmatter)
    assert fm.entity_search_keys == []
    assert fm.key_themes == ["foo", "bar"]


def test_author_null_when_absent(tmp_path: Path) -> None:
    """author is optional — absent or null → None."""
    src = _write(
        tmp_path / "no_author.md",
        "---\n"
        "kdb_signal: signal\n"
        "domain: ai-ml\n"
        "source_type: blog\n"
        "summary: No author here.\n"
        "---\n"
        "Body.\n",
    )
    fm, _ = parse_source_file(src)
    assert fm is not None
    assert fm.author is None


def test_missing_file_raises_oserror(tmp_path: Path) -> None:
    """OSError propagates — caller wraps for source-level degrade."""
    with pytest.raises(OSError):
        parse_source_file(tmp_path / "does-not-exist.md")


def test_binary_file_raises_unicode_decode_error(tmp_path: Path) -> None:
    """Binary content raises UnicodeDecodeError — propagates."""
    src = tmp_path / "binary.md"
    src.write_bytes(b"\xff\xfe\x00\x01binary")
    with pytest.raises(UnicodeDecodeError):
        parse_source_file(src)


def test_source_frontmatter_from_dict_returns_none_on_missing_required(tmp_path: Path) -> None:
    """from_dict contract: returns None if any of kdb_signal/domain/source_type/summary missing."""
    assert SourceFrontmatter.from_dict({}) is None
    assert SourceFrontmatter.from_dict({"kdb_signal": "signal"}) is None
    assert SourceFrontmatter.from_dict({
        "kdb_signal": "signal",
        "domain": "ai-ml",
        "source_type": "blog",
        # summary missing
    }) is None


def test_source_frontmatter_from_dict_minimal_required(tmp_path: Path) -> None:
    """Minimal valid envelope: 4 required keys; optional fields default."""
    fm = SourceFrontmatter.from_dict({
        "kdb_signal": "signal",
        "domain": "ai-ml",
        "source_type": "blog",
        "summary": "Minimal.",
    })
    assert fm is not None
    assert fm.author is None
    assert fm.key_themes == []
    assert fm.entity_search_keys == []
