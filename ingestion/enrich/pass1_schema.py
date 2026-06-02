# kdb_compiler/enrich/pass1_schema.py
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

from ingestion.enrich.config_loader import load_domains, load_source_types

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
    # GraphDB-input section (Pass-2 consumes; D-89-17 amended by D-89-20)
    # NB v0.2.2 (D-89-20): key_entities dropped; entity_search_keys added
    # (≤10 slugs; sole consumer = Task #90 context-loader T2-rewrite).
    kdb_signal: str  # "signal" | "noise"
    domain: str  # one of 23 NW-4 v0.4 IDs
    source_type: str  # one of 21 NW-7 v0.2 IDs
    author: str | None
    summary: str
    key_themes: list[str]
    entity_search_keys: list[str]  # ≤10 kebab-case slugs; T2-rewrite input (D-89-20)

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


# The 11 fields the Pass-1 LLM is contractually responsible for (Task #95).
# The 4 code-owned fields (prompt_version / model / schema_version / override)
# are stamped/constructed by the deterministic layer AFTER the call — the LLM
# is never asked for them. See docs/task95-pass1-review/two-stage-validation-sketch.md.
_CONTENT_REQUIRED = [
    "kdb_signal", "domain", "source_type", "author", "summary",
    "key_themes", "entity_search_keys",
    "confidence", "uncertainty_reason", "reject_reason", "other_reason",
]
_CODE_OWNED_REQUIRED = ["prompt_version", "model", "schema_version", "override"]


def _content_properties(domain_ids: list[str], source_type_ids: list[str]) -> dict[str, Any]:
    """JSON-Schema property defs for the 11 LLM-owned fields."""
    return {
        "kdb_signal": {"enum": ["signal", "noise"]},
        "domain": {"enum": domain_ids},
        "source_type": {"enum": source_type_ids},
        "author": {"type": ["string", "null"]},
        "summary": {"type": "string"},
        "key_themes": {"type": "array", "items": {"type": "string"}},
        # Shape validation only (string array, ≤10); content-format
        # quality is a prompt-discipline concern. Downstream T2-rewrite
        # (Task #90) does Entity.slug PK lookup — imperfect slugs simply
        # miss, no harm. A strict regex caused real LLM emissions like
        # "see's-candies" to reject the whole envelope (2026-05-26 night
        # live fire); empirically too strict for prompt-only discipline.
        "entity_search_keys": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 10,
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "uncertainty_reason": {"type": ["string", "null"]},
        "reject_reason": {"type": ["string", "null"]},
        "other_reason": {"type": ["string", "null"]},
    }


_CODE_OWNED_PROPERTIES: dict[str, Any] = {
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
}


def build_content_schema() -> dict[str, Any]:
    """STAGE 1 schema (Task #95): the 11 LLM-owned fields ONLY.

    Used to validate the raw LLM output BEFORE the deterministic layer stamps
    the code-owned fields. Does NOT require override/model/prompt_version/
    schema_version — the prompt no longer asks the LLM for them, so their
    absence is correct. This is the validation whose failure gates the retry."""
    domain_ids = [d.id for d in load_domains()]
    source_type_ids = [s.id for s in load_source_types()]
    return {
        "type": "object",
        "required": list(_CONTENT_REQUIRED),
        "properties": _content_properties(domain_ids, source_type_ids),
    }


def build_json_schema() -> dict[str, Any]:
    """STAGE 2 schema (Task #95): the COMPLETE assembled envelope.

    11 content fields + 4 code-owned fields. Run on the final envelope AFTER
    stamping + override construction — the gap-closer that nothing validated
    before. Enums are loaded from domains.json + source_types.json (D-NW4-4 /
    D-NW7-3 — config is the source of truth, not Python constants)."""
    domain_ids = [d.id for d in load_domains()]
    source_type_ids = [s.id for s in load_source_types()]
    return {
        "type": "object",
        "required": _CONTENT_REQUIRED + _CODE_OWNED_REQUIRED,
        "properties": {
            **_content_properties(domain_ids, source_type_ids),
            **_CODE_OWNED_PROPERTIES,
        },
    }


def _validate_against(payload: dict[str, Any], schema: dict[str, Any], *, label: str) -> None:
    import jsonschema
    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) or "<root>"
        raise ValueError(f"Pass-1 {label} invalid at {path}: {e.message}") from e
    # OQ-NW7-7's other_reason-required cross-field rule was dropped 2026-05-31
    # (run-4 Finding 1): other_reason is an audit field (Pass-2 ignores it), so a
    # missing "why other" note is coerced-through, not a reject. Trade-off: loses
    # the vocab-evolution signal when the LLM omits it (still recorded when given).


def validate_llm_content(payload: dict[str, Any]) -> None:
    """STAGE 1 (Task #95): validate the 11 LLM-owned fields. Raises ValueError.

    This is the retry-gated validation in pass1_caller — it runs on raw LLM
    output before any code-owned field is stamped."""
    _validate_against(payload, build_content_schema(), label="LLM content")


def validate_envelope(payload: dict[str, Any]) -> None:
    """STAGE 2 (Task #95): validate the COMPLETE assembled envelope. Raises
    ValueError. Belt-and-suspenders — catches a stamping/override-construction
    bug before the malformed envelope is embedded."""
    _validate_against(payload, build_json_schema(), label="envelope")


def normalize_llm_content(payload: dict[str, Any]) -> None:
    """Coerce benign shape deviations IN PLACE, before validation — don't reject
    + retry over a lossless, mechanical fix (feedback_coerce_dont_reject).

    Currently: truncate entity_search_keys to the first 10. The ≤10 cap is a
    retrieval budget, not a correctness bound — extra/imperfect slugs just miss
    the Entity.slug PK lookup harmlessly. The strict schema (maxItems:10) stays
    the gate; this runs ahead of it so an over-supply never trips validation."""
    keys = payload.get("entity_search_keys")
    if isinstance(keys, list) and len(keys) > 10:
        payload["entity_search_keys"] = keys[:10]
