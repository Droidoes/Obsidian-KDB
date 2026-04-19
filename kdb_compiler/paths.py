"""paths — vault discovery, slug policy, slug <-> filesystem path resolution.

Single source of truth for path decisions. No other module should construct
a KDB path by string concatenation.

Slug policy (D19):
    * Lowercase ASCII kebab-case matching /^[a-z0-9]+(?:-[a-z0-9]+)*$/.
    * Reserved slugs: "index", "log" — Python-owned pages, LLM cannot emit.
    * Derived from titles via slugify() with NFKD normalization + strip.
    * Collisions raise; never silent numeric suffixes.

This module is pure computation — no filesystem I/O.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Literal

PageType = Literal["summary", "concept", "article"]
PAGE_TYPES: tuple[PageType, ...] = ("summary", "concept", "article")

RESERVED_SLUGS = frozenset({"index", "log"})
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SLUG_LEN = 120

_SUBDIR: dict[PageType, str] = {
    "summary": "summaries",
    "concept": "concepts",
    "article": "articles",
}


class PathError(ValueError):
    """Raised for invalid slug, unknown page_type, or path outside KDB/."""


def vault_root() -> Path:
    """Resolve vault root from OBSIDIAN_VAULT_PATH env var, else $HOME/Obsidian."""
    env = os.environ.get("OBSIDIAN_VAULT_PATH")
    root = Path(env).expanduser() if env else Path.home() / "Obsidian"
    return root.resolve()


def kdb_root(root: Path | None = None) -> Path:
    return (root if root is not None else vault_root()) / "KDB"


def slugify(title: str) -> str:
    """Title -> kebab-case ASCII slug. Raises PathError if result is empty."""
    normalized = unicodedata.normalize("NFKD", title)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    kebab = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    if not kebab:
        raise PathError(f"Cannot slugify title (no ASCII letters/digits): {title!r}")
    if len(kebab) > MAX_SLUG_LEN:
        kebab = kebab[:MAX_SLUG_LEN].rstrip("-")
    return kebab


def validate_slug(slug: str) -> str:
    """Validate slug against policy. Returns the slug unchanged on success."""
    if not isinstance(slug, str) or not SLUG_PATTERN.match(slug):
        raise PathError(f"Invalid slug (must match {SLUG_PATTERN.pattern}): {slug!r}")
    if len(slug) > MAX_SLUG_LEN:
        raise PathError(f"Slug too long (max {MAX_SLUG_LEN}): {slug!r}")
    if slug in RESERVED_SLUGS:
        raise PathError(f"Reserved slug (Python-owned page): {slug!r}")
    return slug


def _validate_page_type(page_type: str) -> PageType:
    if page_type not in _SUBDIR:
        raise PathError(f"Unknown page_type: {page_type!r} (expected one of {PAGE_TYPES})")
    return page_type  # type: ignore[return-value]


def slug_to_relpath(slug: str, page_type: PageType) -> str:
    """POSIX relative path from vault root (for manifest entries)."""
    validate_slug(slug)
    _validate_page_type(page_type)
    return f"KDB/wiki/{_SUBDIR[page_type]}/{slug}.md"


def slug_to_abspath(slug: str, page_type: PageType, *, root: Path | None = None) -> Path:
    """Absolute filesystem path."""
    rel = slug_to_relpath(slug, page_type)
    return (root if root is not None else vault_root()) / rel


def relpath_to_slug(relpath: str) -> tuple[PageType, str]:
    """Inverse of slug_to_relpath. Raises PathError for paths outside KDB/wiki/{subdirs}."""
    if not relpath.endswith(".md"):
        raise PathError(f"Not a markdown file: {relpath}")
    parts = relpath.split("/")
    if len(parts) < 4 or parts[0] != "KDB" or parts[1] != "wiki":
        raise PathError(f"Not a KDB wiki path: {relpath}")
    subdir = parts[2]
    for page_type, sub in _SUBDIR.items():
        if sub == subdir:
            slug = parts[-1][:-3]
            validate_slug(slug)
            return page_type, slug
    raise PathError(f"Unknown wiki subdirectory: {subdir!r}")


def rawpath_to_relpath(abs_path: Path, *, root: Path | None = None) -> str:
    """Return POSIX relative path 'KDB/raw/...' for an absolute raw file path."""
    p = Path(abs_path).resolve()
    kdb = kdb_root(root).resolve()
    try:
        rel = p.relative_to(kdb)
    except ValueError as e:
        raise PathError(f"Path is outside KDB/: {abs_path}") from e
    return f"KDB/{rel.as_posix()}"


def within_kdb(abs_path: Path, *, root: Path | None = None) -> bool:
    try:
        Path(abs_path).resolve().relative_to(kdb_root(root).resolve())
        return True
    except (ValueError, OSError):
        return False
