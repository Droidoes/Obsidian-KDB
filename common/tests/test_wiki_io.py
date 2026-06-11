"""Tests for wiki_io — slug + page_type -> wiki page body reader."""
from __future__ import annotations

from pathlib import Path

import pytest

from common import paths
from common.paths import PageType, PathError
from common.wiki_io import get_body, ContentNotFoundError


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


def test_get_body_missing_file_raises_content_not_found(tmp_path: Path) -> None:
    # Valid slug + page_type, but no file written -> drift, not a validation error.
    with pytest.raises(ContentNotFoundError) as exc:
        get_body("never-written", "concept", root=tmp_path)
    msg = str(exc.value)
    assert "never-written" in msg
    assert "concept" in msg


def test_content_not_found_is_not_value_error() -> None:
    # Static fact: a missing file is a drift/state error, not input validation.
    assert not issubclass(ContentNotFoundError, ValueError)


def test_get_body_invalid_slug_raises_path_error(tmp_path: Path) -> None:
    with pytest.raises(PathError):
        get_body("Not A Slug", "concept", root=tmp_path)  # spaces/caps invalid


def test_get_body_unknown_page_type_raises_path_error(tmp_path: Path) -> None:
    with pytest.raises(PathError):
        get_body("valid-slug", "nonsense", root=tmp_path)  # type: ignore[arg-type]


def test_get_body_uses_explicit_root_over_env_default(tmp_path: Path, monkeypatch) -> None:
    # Spec test #5: the explicit `root` is honored over the env/default vault.
    # Point the env default at an EMPTY vault; write the real file under a different root.
    env_vault = tmp_path / "env_vault"
    env_vault.mkdir()
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(env_vault))
    explicit_root = tmp_path / "explicit_root"
    _write_page(explicit_root, "root-probe", "concept", "\nBody under explicit root.\n")

    # Explicit root -> reads the file under explicit_root.
    assert get_body("root-probe", "concept", root=explicit_root) == "Body under explicit root.\n"
    # No root -> falls back to vault_root() (the env vault, which lacks the file) -> drift.
    with pytest.raises(ContentNotFoundError):
        get_body("root-probe", "concept")
