"""Shared source-file I/O for kdb_compiler.

Owns `parse_existing_frontmatter`, `SourceFrontmatter` (re-exported from
types), and `parse_source_file()`. Used by the orchestrator and `compiler.py`
(compile-time `source_text_for` wrapper) for frontmatter read at enrich/compile
time.

Historical note: originally split from the deleted `planner.py` to break a
circular-import cycle (Task #90 D-90-10, Bug B-1). The neutral placement here
lets the enrich and compile stages import UP from this common leaf.

Layering note (phase-a refactor): `parse_existing_frontmatter` lived in
`kdb_compiler/enrich/frontmatter_embedder.py` (a stage subpackage) but is
a primitive needed by this common leaf; moved here so the enrich stage
imports UP from the leaf, not the other way around.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from common.types import SourceFrontmatter

__all__ = ["SourceFrontmatter", "parse_existing_frontmatter", "parse_source_file"]

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


def parse_existing_frontmatter(text: str) -> tuple[dict, str]:
    """Split (frontmatter_dict, body_text). Returns ({}, text) if no
    frontmatter block."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_text, body = m.group(1), m.group(2)
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return {}, text
    return fm, body


def parse_source_file(path: Path) -> tuple[SourceFrontmatter | None, str]:
    """Read a source file as UTF-8; parse YAML frontmatter; return (frontmatter, body).

    Returns:
        (frontmatter, body) where frontmatter is a SourceFrontmatter instance
        if the file is Pass-1 enriched (GraphDB-input keys present), else None.
        body is the file content excluding the YAML frontmatter block.

    Error handling:
        - OSError (missing / permission) → propagates. Caller decides degrade vs raise.
        - UnicodeDecodeError (binary) → propagates.
        - YAML parse error inside frontmatter → (None, full_raw_content) per
          parse_existing_frontmatter's degrade contract. Body fallback rather
          than raise — Pass-1's bug to fix, not ours.

    Used by:
        - orchestrator / enrich stage (wraps in try/except for source-level degrade)
        - compiler.source_text_for (thin wrapper; propagates for compile_one's
          scaffold-and-fill error classification)
    """
    raw = path.read_text(encoding="utf-8")
    fm_dict, body = parse_existing_frontmatter(raw)
    return SourceFrontmatter.from_dict(fm_dict), body
