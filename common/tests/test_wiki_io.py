"""Tests for wiki_io — slug + page_type -> wiki page body reader."""
from __future__ import annotations

from pathlib import Path

import pytest

from common import paths
from common.paths import PageType
from common.wiki_io import get_body


def _write_page(root: Path, slug: str, page_type: PageType, body: str) -> Path:
    """Write a wiki page (fixed frontmatter block + body) at the resolved path."""
    fm = (
        "---\n"
        "title: Sample Title\n"
        f"slug: {slug}\n"
        f"page_type: {page_type}\n"
        "status: active\n"
        "---\n"
    )
    path = paths.slug_to_abspath(slug, page_type, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fm + body, encoding="utf-8")
    return path


@pytest.mark.parametrize("page_type", ["summary", "concept", "article"])
def test_get_body_returns_prose_for_each_page_type(tmp_path: Path, page_type: str) -> None:
    body = "The 4-7-8 breath is a relaxation exercise.\n"
    # File on disk has a blank line between the closing fence and the prose.
    _write_page(tmp_path, "four-seven-eight-breath", page_type, "\n" + body)
    result = get_body("four-seven-eight-breath", page_type, root=tmp_path)
    assert result == body  # frontmatter gone AND leading blank line stripped


def test_get_body_preserves_horizontal_rule_in_body(tmp_path: Path) -> None:
    body = "Intro line.\n\n---\n\nSection after a horizontal rule.\n"
    _write_page(tmp_path, "has-rule", "concept", "\n" + body)
    result = get_body("has-rule", "concept", root=tmp_path)
    assert result == body
    assert "---" in result  # body's own --- must not be truncated
