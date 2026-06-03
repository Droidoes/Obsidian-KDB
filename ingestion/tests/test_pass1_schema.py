# ingestion/tests/test_pass1_schema.py
import json
import pytest
from ingestion.enrich.pass1_schema import (
    Pass1Envelope, OverrideAudit, validate_envelope, build_json_schema,
    build_content_schema, validate_llm_content, PASS1_SCHEMA_VERSION,
)


# --- Task #95: Stage-1 content-only validation ---

def _content_only():
    """The 11 LLM-owned fields — NO override/model/prompt_version/schema_version."""
    return {
        "kdb_signal": "signal", "domain": "ai-ml",
        "source_type": "paper", "author": None, "summary": "Test.",
        "key_themes": [], "entity_search_keys": [],
        "confidence": 0.8, "uncertainty_reason": None,
        "reject_reason": None, "other_reason": None,
    }


def test_validate_llm_content_accepts_content_without_code_owned_fields():
    """Stage 1 must NOT require override/model/prompt_version/schema_version —
    the prompt no longer asks the LLM for them (Task #95)."""
    validate_llm_content(_content_only())  # no raise


def test_validate_llm_content_rejects_bad_kdb_signal():
    payload = _content_only()
    payload["kdb_signal"] = "maybe"
    with pytest.raises(ValueError, match="kdb_signal"):
        validate_llm_content(payload)


def test_validate_llm_content_rejects_off_enum_domain():
    payload = _content_only()
    payload["domain"] = "not-a-domain"
    with pytest.raises(ValueError, match="domain"):
        validate_llm_content(payload)


def test_validate_llm_content_rejects_more_than_10_entity_search_keys():
    payload = _content_only()
    payload["entity_search_keys"] = [f"k{i}" for i in range(11)]
    with pytest.raises(ValueError, match="entity_search_keys"):
        validate_llm_content(payload)


def test_normalize_truncates_entity_search_keys_to_10():
    from ingestion.enrich.pass1_schema import normalize_llm_content
    p = _content_only()
    p["entity_search_keys"] = [f"k{i}" for i in range(13)]
    normalize_llm_content(p)
    assert p["entity_search_keys"] == [f"k{i}" for i in range(10)]
    validate_llm_content(p)  # passes after normalize (no raise)


def test_normalize_leaves_short_keys_untouched():
    from ingestion.enrich.pass1_schema import normalize_llm_content
    p = _content_only()
    p["entity_search_keys"] = ["a", "b"]
    normalize_llm_content(p)
    assert p["entity_search_keys"] == ["a", "b"]


def test_validate_llm_content_allows_null_other_reason():
    # Finding 1 (run-4): other_reason is an audit field (Pass-2 ignores it);
    # a missing "why other" note is not worth a reject + retry. Let it pass.
    payload = _content_only()
    payload["source_type"] = "other"
    payload["other_reason"] = None
    validate_llm_content(payload)  # no raise


def test_content_schema_excludes_code_owned_required():
    req = build_content_schema()["required"]
    for f in ("override", "model", "prompt_version", "schema_version"):
        assert f not in req
    assert "kdb_signal" in req and "other_reason" in req


def test_full_schema_still_requires_code_owned():
    req = build_json_schema()["required"]
    for f in ("override", "model", "prompt_version", "schema_version"):
        assert f in req


def test_envelope_dataclass_has_graphdb_input_section():
    """GraphDB-input fields per D-89-16 amended by D-89-20 (v0.2.2):
    key_entities dropped, entity_search_keys added."""
    fields = {f.name for f in Pass1Envelope.__dataclass_fields__.values()}
    assert {"kdb_signal", "domain", "source_type", "author", "summary",
            "key_themes", "entity_search_keys"}.issubset(fields)
    assert "key_entities" not in fields


def test_envelope_dataclass_has_audit_section():
    """All audit fields per D-89-16 + other_reason per OQ-NW7-7."""
    fields = {f.name for f in Pass1Envelope.__dataclass_fields__.values()}
    assert {"confidence", "uncertainty_reason", "reject_reason",
            "prompt_version", "model", "schema_version", "override",
            "other_reason"}.issubset(fields)


def test_validate_envelope_accepts_signal_envelope():
    payload = {
        "kdb_signal": "signal", "domain": "value-investing",
        "source_type": "letter", "author": "Warren Buffett",
        "summary": "Annual letter.",
        "key_themes": ["intrinsic value"],
        "entity_search_keys": ["berkshire-hathaway", "warren-buffett", "intrinsic-value"],
        "confidence": 0.9, "uncertainty_reason": None, "reject_reason": None,
        "prompt_version": "1.0.0", "model": "deepseek-v4-flash",
        "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": "signal", "reject_reason_cleared": None},
        "other_reason": None,
    }
    validate_envelope(payload)  # no raise


def test_validate_envelope_rejects_invalid_domain():
    payload = _valid_payload()
    payload["domain"] = "not-a-real-domain"
    with pytest.raises(ValueError, match="domain"):
        validate_envelope(payload)


def test_validate_envelope_rejects_invalid_source_type():
    payload = _valid_payload()
    payload["source_type"] = "podcast"  # dropped from NW-7
    with pytest.raises(ValueError, match="source_type"):
        validate_envelope(payload)


def test_validate_envelope_rejects_kdb_signal_outside_enum():
    payload = _valid_payload()
    payload["kdb_signal"] = "uncertain"  # not in enum
    with pytest.raises(ValueError, match="kdb_signal"):
        validate_envelope(payload)


def test_validate_envelope_allows_null_other_reason_when_other():
    # Finding 1 (run-4): the OQ-NW7-7 other_reason-required rule was dropped at
    # both stages — other_reason is an audit field, null is coerced-through.
    payload = _valid_payload()
    payload["source_type"] = "other"
    payload["other_reason"] = None
    validate_envelope(payload)  # no raise


def test_json_schema_is_valid_jsonschema():
    schema = build_json_schema()
    assert schema["type"] == "object"
    assert "kdb_signal" in schema["required"]
    assert "domain" in schema["required"]


def _valid_payload():
    return {
        "kdb_signal": "signal", "domain": "ai-ml",
        "source_type": "paper", "author": None,
        "summary": "Test.",
        "key_themes": [],
        "entity_search_keys": [],
        "confidence": 0.8, "uncertainty_reason": None, "reject_reason": None,
        "prompt_version": "1.0.0", "model": "deepseek-v4-flash",
        "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": "signal", "reject_reason_cleared": None},
        "other_reason": None,
    }
