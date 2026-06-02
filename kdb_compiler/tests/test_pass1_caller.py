# kdb_compiler/tests/test_pass1_caller.py
"""Task #95: pass1_caller two-stage flow.

The LLM returns CONTENT-ONLY JSON (11 fields). The caller validates it
(Stage 1), then stamps the 3 code-owned scalar fields. The `override` block is
NOT built here (apply_overrides owns it downstream)."""
import json
import pytest

from kdb_compiler.enrich import pass1_caller as caller_mod
from kdb_compiler.enrich.pass1_caller import call_pass1, Pass1CallError
from kdb_compiler.enrich.pass1_prompt import PASS1_PROMPT_VERSION
from kdb_compiler.enrich.pass1_schema import PASS1_SCHEMA_VERSION
from common.call_model import ModelResponse


def _content_json(**overrides) -> str:
    payload = {
        "kdb_signal": "signal", "domain": "ai-ml", "source_type": "paper",
        "author": None, "summary": "A note.", "key_themes": ["a"],
        "entity_search_keys": ["a"], "confidence": 0.9,
        "uncertainty_reason": None, "reject_reason": None, "other_reason": None,
    }
    payload.update(overrides)
    return json.dumps(payload)


def _fake_response(text: str) -> ModelResponse:
    return ModelResponse(
        text=text, input_tokens=10, output_tokens=5, latency_ms=1,
        model="deepseek-v4-flash", provider="deepseek", raw={},
    )


def test_caller_stamps_code_owned_and_omits_override(monkeypatch):
    monkeypatch.setattr(caller_mod, "call_model",
                        lambda req: _fake_response(_content_json()))
    res = call_pass1(source_text="body", source_path="x.md",
                     provider="deepseek", model="deepseek-v4-flash")
    # code-owned scalars stamped
    assert res.parsed["prompt_version"] == PASS1_PROMPT_VERSION
    assert res.parsed["model"] == "deepseek-v4-flash"
    assert res.parsed["schema_version"] == PASS1_SCHEMA_VERSION
    # override is NOT built by the caller — apply_overrides owns it
    assert "override" not in res.parsed
    assert res.attempts == 1


def test_caller_coerces_over_cap_keys_without_retry(monkeypatch):
    monkeypatch.setattr(
        caller_mod, "call_model",
        lambda req: _fake_response(_content_json(
            entity_search_keys=[f"k{i}" for i in range(13)])),
    )
    res = call_pass1(source_text="b", source_path="x.md",
                     provider="deepseek", model="deepseek-v4-flash")
    assert res.attempts == 1  # coerced, not rejected+retried
    assert res.parsed["entity_search_keys"] == [f"k{i}" for i in range(10)]


def test_caller_retries_on_invalid_content_then_raises(monkeypatch):
    # Always return content with an off-enum domain → Stage-1 fails every time.
    monkeypatch.setattr(
        caller_mod, "call_model",
        lambda req: _fake_response(_content_json(domain="not-a-domain")),
    )
    with pytest.raises(Pass1CallError) as exc:
        call_pass1(source_text="body", source_path="x.md",
                   provider="deepseek", model="deepseek-v4-flash")
    assert exc.value.raw_response_text
    assert "not-a-domain" in exc.value.raw_response_text
    assert exc.value.request_provider == "deepseek"
    assert exc.value.request_model == "deepseek-v4-flash"
    assert exc.value.input_tokens == 10
    assert exc.value.attempts == 2


def test_caller_recovers_on_second_attempt(monkeypatch):
    calls = {"n": 0}

    def flaky(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return _fake_response(_content_json(domain="not-a-domain"))
        return _fake_response(_content_json())

    monkeypatch.setattr(caller_mod, "call_model", flaky)
    res = call_pass1(source_text="body", source_path="x.md",
                     provider="deepseek", model="deepseek-v4-flash")
    assert res.attempts == 2
    assert res.parsed["domain"] == "ai-ml"


def test_caller_model_failure_raises_pass1_error_without_raw(monkeypatch):
    def boom(req):
        raise RuntimeError("provider down")

    monkeypatch.setattr(caller_mod, "call_model", boom)

    with pytest.raises(Pass1CallError) as exc:
        call_pass1(source_text="body", source_path="x.md",
                   provider="deepseek", model="deepseek-v4-flash")

    assert "provider down" in str(exc.value)
    assert exc.value.raw_response_text == ""
    assert exc.value.request_prompt is not None
    assert exc.value.attempts == 2
