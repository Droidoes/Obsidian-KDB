"""Shared source-file I/O for kdb_compiler.

Owns the `SourceFrontmatter` dataclass and `parse_source_file()`. Used by
both `planner.py` (plan-time frontmatter read for context-loader T2
construction) and `compiler.py` (compile-time `source_text_for` wrapper).

Fixes Bug B-1 (planner→compiler.py circular import) per Task #90 D-90-10:
`compiler.py` already imports `planner` at module load, so `planner.py`
cannot import `SourceFrontmatter` from `compiler.py`. Hoisting both the
dataclass and the parse helper into this neutral module breaks the cycle.
Also retires `planner._read_source_text`'s double-disk-read (Gemini F-4)
by routing both callers through a single parse.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kdb_compiler.ingestion.frontmatter_embedder import parse_existing_frontmatter


@dataclass
class SourceFrontmatter:
    """Parsed GraphDB-input section of Pass-1 frontmatter. Audit section +
    user-added keys are ignored by compile per D-89-16."""
    kdb_signal: str
    domain: str
    source_type: str
    author: str | None
    summary: str
    key_themes: list[str]
    entity_search_keys: list[str]  # ≤10 slugs; T2-rewrite input (D-89-20); not seen by Pass-2

    @classmethod
    def from_dict(cls, fm: dict) -> "SourceFrontmatter | None":
        """Return None if frontmatter does not contain Pass-1 GraphDB-input keys.

        v0.2.2 (D-89-20): key_entities dropped; entity_search_keys added (the
        sole consumer is Task #90 context-loader T2-rewrite). Pre-v0.2.2
        frontmatter without `entity_search_keys` still parses (defaults to []).
        """
        required = {"kdb_signal", "domain", "source_type", "summary"}
        if not required.issubset(fm.keys()):
            return None
        return cls(
            kdb_signal=fm["kdb_signal"],
            domain=fm["domain"],
            source_type=fm["source_type"],
            author=fm.get("author"),
            summary=fm["summary"],
            key_themes=fm.get("key_themes", []) or [],
            entity_search_keys=fm.get("entity_search_keys", []) or [],
        )


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
        - planner.build_jobs (wraps in try/except for plan-time degrade)
        - compiler.source_text_for (thin wrapper; propagates for compile_one's
          scaffold-and-fill error classification)
    """
    raw = path.read_text(encoding="utf-8")
    fm_dict, body = parse_existing_frontmatter(raw)
    return SourceFrontmatter.from_dict(fm_dict), body
