"""Tests for paths — slug policy and path resolution (pure, no I/O)."""
from __future__ import annotations

from pathlib import Path

import pytest

from kdb_compiler import paths
from kdb_compiler.paths import PathError


# ---------- slugify ----------

@pytest.mark.parametrize("title,expected", [
    ("Attention Is All You Need", "attention-is-all-you-need"),
    ("  Leading/Trailing  ", "leading-trailing"),
    ("RFC 2119", "rfc-2119"),
    ("Mixed---Dashes", "mixed-dashes"),
    ("café déjà vu", "cafe-deja-vu"),          # NFKD strips accents
    ("中文 Mixed Title", "mixed-title"),        # non-ASCII dropped
])
def test_slugify_happy(title: str, expected: str) -> None:
    assert paths.slugify(title) == expected


def test_slugify_empty_raises() -> None:
    with pytest.raises(PathError):
        paths.slugify("###")
    with pytest.raises(PathError):
        paths.slugify("中文")


def test_slugify_truncates_long_titles() -> None:
    title = "a" * 500
    out = paths.slugify(title)
    assert len(out) <= paths.MAX_SLUG_LEN
    assert out == "a" * paths.MAX_SLUG_LEN


# ---------- validate_slug ----------

@pytest.mark.parametrize("slug", ["a", "ab-cd", "gpt-4", "rfc-2119", "x1-y2-z3"])
def test_validate_slug_accepts(slug: str) -> None:
    assert paths.validate_slug(slug) == slug


@pytest.mark.parametrize("bad", [
    "Attention",        # uppercase
    "-leading",
    "trailing-",
    "double--dash",
    "has space",
    "has_underscore",
    "",
    "UPPER",
])
def test_validate_slug_rejects(bad: str) -> None:
    with pytest.raises(PathError):
        paths.validate_slug(bad)


@pytest.mark.parametrize("reserved", ["index", "log"])
def test_validate_slug_rejects_reserved(reserved: str) -> None:
    with pytest.raises(PathError, match="Reserved"):
        paths.validate_slug(reserved)


# ---------- slug_to_relpath / abspath ----------

def test_slug_to_relpath_summary() -> None:
    assert paths.slug_to_relpath("attention-paper", "summary") == "KDB/wiki/summaries/attention-paper.md"


def test_slug_to_relpath_concept() -> None:
    assert paths.slug_to_relpath("attention-mechanism", "concept") == "KDB/wiki/concepts/attention-mechanism.md"


def test_slug_to_relpath_article() -> None:
    assert paths.slug_to_relpath("why-transformers-won", "article") == "KDB/wiki/articles/why-transformers-won.md"


def test_slug_to_relpath_rejects_unknown_type() -> None:
    with pytest.raises(PathError):
        paths.slug_to_relpath("foo", "essay")  # type: ignore[arg-type]


def test_slug_to_abspath_joins_root(tmp_path: Path) -> None:
    abs_ = paths.slug_to_abspath("attention-paper", "summary", root=tmp_path)
    assert abs_ == tmp_path / "KDB" / "wiki" / "summaries" / "attention-paper.md"


# ---------- relpath_to_slug ----------

def test_relpath_to_slug_roundtrip() -> None:
    for slug, pt in [("attention-paper", "summary"), ("attention-mechanism", "concept"), ("why-x", "article")]:
        rel = paths.slug_to_relpath(slug, pt)  # type: ignore[arg-type]
        back_pt, back_slug = paths.relpath_to_slug(rel)
        assert (back_pt, back_slug) == (pt, slug)


def test_relpath_to_slug_rejects_non_md() -> None:
    with pytest.raises(PathError):
        paths.relpath_to_slug("KDB/wiki/summaries/foo.txt")


def test_relpath_to_slug_rejects_outside_wiki() -> None:
    with pytest.raises(PathError):
        paths.relpath_to_slug("KDB/raw/foo.md")


def test_relpath_to_slug_rejects_unknown_subdir() -> None:
    with pytest.raises(PathError):
        paths.relpath_to_slug("KDB/wiki/essays/foo.md")


# ---------- vault/kdb root ----------

def test_vault_root_honours_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    assert paths.vault_root() == tmp_path.resolve()


def test_kdb_root_under_vault(tmp_path: Path) -> None:
    assert paths.kdb_root(tmp_path) == tmp_path / "KDB"


# ---------- rawpath / within_kdb ----------

def test_rawpath_to_relpath(tmp_path: Path) -> None:
    raw = tmp_path / "KDB" / "raw" / "note.md"
    raw.parent.mkdir(parents=True)
    raw.write_text("x")
    assert paths.rawpath_to_relpath(raw, root=tmp_path) == "KDB/raw/note.md"


def test_rawpath_to_relpath_outside_kdb_raises(tmp_path: Path) -> None:
    elsewhere = tmp_path / "other.md"
    elsewhere.write_text("x")
    with pytest.raises(PathError):
        paths.rawpath_to_relpath(elsewhere, root=tmp_path)


def test_within_kdb(tmp_path: Path) -> None:
    inside = tmp_path / "KDB" / "raw" / "note.md"
    inside.parent.mkdir(parents=True)
    inside.write_text("x")
    outside = tmp_path / "scratch.md"
    outside.write_text("x")
    assert paths.within_kdb(inside, root=tmp_path) is True
    assert paths.within_kdb(outside, root=tmp_path) is False
