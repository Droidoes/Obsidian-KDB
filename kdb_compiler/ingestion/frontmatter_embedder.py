# kdb_compiler/ingestion/frontmatter_embedder.py
"""Deterministic YAML frontmatter embedder (Task #89 §3 + D-89-13).

The LLM returns structured JSON; this module serializes the JSON envelope
as YAML, merges with any existing user-added frontmatter keys, and writes
atomically to disk. The body content is never modified by Pass-1.

Per D-89-16 sectionalized layout: GraphDB-input section first, Audit section
second, both within the same YAML block. Comments in the YAML separate them.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from kdb_compiler.atomic_io import atomic_write_text

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)\Z", re.DOTALL)

# Pass-1 schema fields (the keys this module owns).
_GRAPHDB_INPUT_FIELDS = (
    "kdb_signal", "domain", "source_type", "author", "summary",
    "key_themes", "entity_search_keys",
)
_AUDIT_FIELDS = (
    "confidence", "uncertainty_reason", "reject_reason",
    "prompt_version", "model", "schema_version", "override", "other_reason",
)
_PASS1_FIELDS = frozenset(_GRAPHDB_INPUT_FIELDS + _AUDIT_FIELDS)


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


def build_yaml_block(envelope: dict) -> str:
    """Build the sectionalized YAML frontmatter block (with --- delimiters
    and section comments). Pass-1 fields only; user-added keys merged
    separately by embed_frontmatter."""
    graphdb_input = {f: envelope[f] for f in _GRAPHDB_INPUT_FIELDS}
    audit = {f: envelope[f] for f in _AUDIT_FIELDS}

    gi_yaml = yaml.safe_dump(graphdb_input, sort_keys=False, allow_unicode=True,
                             default_flow_style=False)
    au_yaml = yaml.safe_dump(audit, sort_keys=False, allow_unicode=True,
                             default_flow_style=False)

    return (
        "---\n"
        "# GraphDB-input section — Pass-2 (compile) consumes (D-89-17)\n"
        f"{gi_yaml}"
        "\n"
        "# Audit section — Pass-1's own; Pass-2 ignores (D-89-16)\n"
        f"{au_yaml}"
        "---\n"
    )


def embed_frontmatter(source_path: Path, envelope: dict) -> None:
    """Embed the Pass-1 envelope as YAML frontmatter at the top of the
    source. Preserves existing user-added non-Pass-1 keys. Body byte-identical."""
    raw = source_path.read_text(encoding="utf-8")
    existing_fm, body = parse_existing_frontmatter(raw)

    # User-added keys = anything in existing_fm not in _PASS1_FIELDS
    user_keys = {k: v for k, v in existing_fm.items() if k not in _PASS1_FIELDS}

    pass1_block = build_yaml_block(envelope)

    if user_keys:
        user_yaml = yaml.safe_dump(user_keys, sort_keys=False, allow_unicode=True,
                                   default_flow_style=False)
        # Append user keys as a third sub-block within the same frontmatter
        pass1_block = (
            pass1_block.removesuffix("---\n")
            + "\n# User-added keys (preserved)\n"
            + user_yaml
            + "---\n"
        )

    new_text = pass1_block + body
    atomic_write_text(source_path, new_text, encoding="utf-8")
