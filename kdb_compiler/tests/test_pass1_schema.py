# kdb_compiler/tests/test_pass1_schema.py
import json
import pytest
from kdb_compiler.ingestion.pass1_schema import (
    Pass1Envelope, OverrideAudit, validate_envelope, build_json_schema,
    PASS1_SCHEMA_VERSION,
)


def test_envelope_dataclass_has_graphdb_input_section():
    """All 7 GraphDB-input fields per D-89-16."""
    fields = {f.name for f in Pass1Envelope.__dataclass_fields__.values()}
    assert {"kdb_signal", "domain", "source_type", "author", "summary",
            "key_entities", "key_themes"}.issubset(fields)


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
        "summary": "Annual letter.", "key_entities": ["Berkshire"],
        "key_themes": ["intrinsic value"],
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


def test_validate_envelope_requires_other_reason_when_other():
    payload = _valid_payload()
    payload["source_type"] = "other"
    payload["other_reason"] = None  # but other_reason is required when other
    with pytest.raises(ValueError, match="other_reason"):
        validate_envelope(payload)


def test_json_schema_is_valid_jsonschema():
    schema = build_json_schema()
    assert schema["type"] == "object"
    assert "kdb_signal" in schema["required"]
    assert "domain" in schema["required"]


def _valid_payload():
    return {
        "kdb_signal": "signal", "domain": "ai-ml",
        "source_type": "paper", "author": None,
        "summary": "Test.", "key_entities": [],
        "key_themes": [],
        "confidence": 0.8, "uncertainty_reason": None, "reject_reason": None,
        "prompt_version": "1.0.0", "model": "deepseek-v4-flash",
        "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": "signal", "reject_reason_cleared": None},
        "other_reason": None,
    }
