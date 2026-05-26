# kdb_compiler/ingestion/pass1_schema.py
"""Pass-1 output schema (D-89-16 sectionalized: GraphDB-input + Audit).

The Pass-1 LLM returns a structured JSON envelope; a deterministic
post-processor validates it against this schema, applies overrides
(overrides.py), serializes to YAML frontmatter (frontmatter_embedder.py),
and atomically writes the source. The LLM never sees the source body in
its output; never re-emits the body.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kdb_compiler.ingestion.config_loader import load_domains, load_source_types

PASS1_SCHEMA_VERSION = 1


@dataclass
class OverrideAudit:
    """Per D-89-3 §4.6: override block is always emitted, never omitted.
    `applied: None` indicates no override fired."""
    applied: str | None  # "signal" | "noise" | None
    rule: str | None  # "force_signal" | "force_noise" | None
    match: str | None  # which glob fired
    llm_original: str  # the LLM's pre-override kdb_signal
    reject_reason_cleared: str | None  # original reject_reason if force_signal cleared it


@dataclass
class Pass1Envelope:
    # GraphDB-input section (Pass-2 consumes; D-89-17)
    kdb_signal: str  # "signal" | "noise"
    domain: str  # one of 23 NW-4 v0.4 IDs
    source_type: str  # one of 21 NW-7 v0.2 IDs
    author: str | None
    summary: str
    key_entities: list[str]
    key_themes: list[str]

    # Audit section (Pass-2 ignores; D-89-16)
    confidence: float
    uncertainty_reason: str | None
    reject_reason: str | None
    prompt_version: str
    model: str
    schema_version: int = PASS1_SCHEMA_VERSION
    override: OverrideAudit = field(default_factory=lambda: OverrideAudit(
        applied=None, rule=None, match=None, llm_original="signal",
        reject_reason_cleared=None,
    ))
    other_reason: str | None = None  # required-non-null when source_type=other (OQ-NW7-7)


def build_json_schema() -> dict[str, Any]:
    """Build the JSON Schema used by the LLM's structured-output mode.
    Enums are loaded from domains.json + source_types.json (D-NW4-4 /
    D-NW7-3 — config is the source of truth, not Python constants)."""
    domain_ids = [d.id for d in load_domains()]
    source_type_ids = [s.id for s in load_source_types()]

    return {
        "type": "object",
        "required": [
            "kdb_signal", "domain", "source_type", "author", "summary",
            "key_entities", "key_themes",
            "confidence", "uncertainty_reason", "reject_reason",
            "prompt_version", "model", "schema_version", "override",
            "other_reason",
        ],
        "properties": {
            "kdb_signal": {"enum": ["signal", "noise"]},
            "domain": {"enum": domain_ids},
            "source_type": {"enum": source_type_ids},
            "author": {"type": ["string", "null"]},
            "summary": {"type": "string"},
            "key_entities": {"type": "array", "items": {"type": "string"}},
            "key_themes": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "uncertainty_reason": {"type": ["string", "null"]},
            "reject_reason": {"type": ["string", "null"]},
            "prompt_version": {"type": "string"},
            "model": {"type": "string"},
            "schema_version": {"type": "integer"},
            "override": {
                "type": "object",
                "required": ["applied", "rule", "match", "llm_original", "reject_reason_cleared"],
                "properties": {
                    "applied": {"enum": ["signal", "noise", None]},
                    "rule": {"enum": ["force_signal", "force_noise", None]},
                    "match": {"type": ["string", "null"]},
                    "llm_original": {"enum": ["signal", "noise"]},
                    "reject_reason_cleared": {"type": ["string", "null"]},
                },
            },
            "other_reason": {"type": ["string", "null"]},
        },
    }


def validate_envelope(payload: dict[str, Any]) -> None:
    """Validate a parsed JSON envelope. Raises ValueError on failure.

    Uses jsonschema (already in pyproject.toml deps). Adds the OQ-NW7-7
    cross-field rule: other_reason must be non-null when source_type='other'.
    """
    import jsonschema
    schema = build_json_schema()
    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as e:
        # Bubble up with cleaner message
        path = ".".join(str(p) for p in e.absolute_path) or "<root>"
        raise ValueError(f"Pass-1 envelope invalid at {path}: {e.message}") from e

    if payload["source_type"] == "other" and not payload.get("other_reason"):
        raise ValueError(
            "Pass-1 envelope invalid at other_reason: "
            "must be non-null string when source_type='other' (OQ-NW7-7)"
        )
