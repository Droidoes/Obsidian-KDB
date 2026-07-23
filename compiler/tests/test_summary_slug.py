"""Tests for compiler.summary_slug — the centralized expected_summary_slug (#115, Task 1.4)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from common.paths import MAX_SLUG_LEN, PathError
from compiler.summary_slug import STEM_BUDGET, expected_summary_slug


def test_basic_derivation() -> None:
    assert expected_summary_slug("KDB/raw/Foo Bar.md") == "summary-foo-bar"


def test_nested_path_uses_stem_only() -> None:
    assert expected_summary_slug("a/b/c/My Note.md") == "summary-my-note"


def test_underivable_stem_raises() -> None:
    with pytest.raises(PathError):
        expected_summary_slug("KDB/raw/日本語.md")


def test_accented_stem_folds_to_ascii() -> None:
    """Codex Gate-2 F1 prompt-contract case: accents fold, spaces/punctuation
    collapse — the derivation is NOT a verbatim stem copy."""
    assert expected_summary_slug("KDB/raw/Café déjà vu.md") == "summary-cafe-deja-vu"


def test_prompt_example_stems_match_derivation() -> None:
    """Codex Gate-2 F1: every summary-slug example taught in the packaged
    system prompt must equal the executable derivation."""
    assert expected_summary_slug(
        "KDB/raw/attention-is-all-you-need.md") == "summary-attention-is-all-you-need"
    assert expected_summary_slug(
        "KDB/raw/EP1 - The Journey of China.md") == "summary-ep1-the-journey-of-china"
    assert expected_summary_slug(
        "KDB/raw/04-research-debt.md") == "summary-04-research-debt"


def test_long_stem_budget() -> None:
    slug = expected_summary_slug("KDB/raw/" + "a" * 200 + ".md")
    assert slug.startswith("summary-")
    assert len(slug) <= MAX_SLUG_LEN
    assert not slug.endswith("-")


def test_trailing_hyphen_rstripped_after_budget() -> None:
    # stem whose 112-char budget cut lands on a hyphen boundary
    stem = "x" * 111 + "-" + "y" * 100
    slug = expected_summary_slug(f"KDB/raw/{stem}.md")
    assert not slug.endswith("-")
    assert len(slug) <= MAX_SLUG_LEN


# --- Equivalence with the Task-0.3 guard script (pinned identical) ---

def _load_guard():
    spec = importlib.util.spec_from_file_location(
        "cohort_slug_collision_guard",
        Path(__file__).resolve().parents[2] / "scripts" / "cohort_slug_collision_guard.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("source_id", [
    "KDB/raw/Foo Bar.md",
    "KDB/raw/foo-bar.md",
    "a/b/c/My Note.md",
    "KDB/raw/Café déjà vu.md",
    "KDB/raw/Value Investing__Li Lu__Li Lu Lecture at Columbia Business School 2006.md",
    "KDB/raw/" + "a" * 200 + ".md",
    "KDB/raw/" + "x" * 111 + "-" + "y" * 100 + ".md",
])
def test_guard_derivation_identical(source_id: str) -> None:
    guard = _load_guard()
    assert expected_summary_slug(source_id) == guard.expected_summary_slug(source_id)
    assert STEM_BUDGET == guard.STEM_BUDGET


@pytest.mark.parametrize("source_id", [
    "KDB/raw/日本語.md",          # non-ASCII-only stem → empty normalization
    "KDB/raw/---.md",             # punctuation-only stem → empty normalization
])
def test_guard_exception_identical(source_id: str) -> None:
    """Codex Gate-2 F7: BOTH implementations must REJECT underivable stems
    identically — equivalence pinned for the failure path, not just the
    success path."""
    guard = _load_guard()
    with pytest.raises(PathError):
        expected_summary_slug(source_id)
    with pytest.raises(PathError):
        guard.expected_summary_slug(source_id)
