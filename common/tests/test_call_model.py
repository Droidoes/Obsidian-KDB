"""Tests for call_model — provider dispatch, request shaping, response assembly."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from google.genai import types as genai_types

from common import call_model as cm
from common.call_model import ModelConfigError, ModelRequest, call_model
from common.config import Settings


# ---------- helpers ----------

def _use_settings(monkeypatch: pytest.MonkeyPatch, **overrides) -> None:
    monkeypatch.setattr(cm, "settings", Settings(**overrides))


@pytest.fixture
def anthropic_resp() -> MagicMock:
    r = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = "hello from claude"
    r.content = [block]
    r.usage.input_tokens = 10
    r.usage.output_tokens = 5
    return r


@pytest.fixture
def openai_resp() -> MagicMock:
    r = MagicMock()
    r.choices = [MagicMock(message=MagicMock(content="hello from gpt"))]
    r.usage.prompt_tokens = 12
    r.usage.completion_tokens = 7
    return r


# ---------- dispatch ----------

def test_anthropic_dispatch(monkeypatch: pytest.MonkeyPatch, anthropic_resp: MagicMock) -> None:
    _use_settings(monkeypatch, anthropic_api_key="sk-ant-test")
    client = MagicMock()
    client.messages.create.return_value = anthropic_resp
    with patch("anthropic.Anthropic", return_value=client):
        resp = call_model(ModelRequest(
            provider="anthropic", model="claude-opus-4-7",
            prompt="hi", system="be nice",
        ))
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["system"] == "be nice"
    assert kwargs["messages"] == [{"role": "user", "content": "hi"}]
    assert kwargs["model"] == "claude-opus-4-7"
    assert resp.text == "hello from claude"
    assert resp.input_tokens == 10
    assert resp.output_tokens == 5
    assert resp.model == "claude-opus-4-7"
    assert resp.provider == "anthropic"
    assert resp.latency_ms >= 0
    assert resp.raw is anthropic_resp


def test_openai_dispatch(monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock) -> None:
    _use_settings(monkeypatch, openai_api_key="sk-oai-test")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        resp = call_model(ModelRequest(
            provider="openai", model="gpt-4.1-mini",
            prompt="hi", system="be nice",
        ))
    # Standard OpenAI endpoint — base_url None
    assert ctor.call_args.kwargs.get("base_url") is None
    # system rendered as role=system message (not first-class kwarg)
    msgs = client.chat.completions.create.call_args.kwargs["messages"]
    assert msgs == [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "hi"},
    ]
    assert resp.text == "hello from gpt"
    assert resp.input_tokens == 12
    assert resp.output_tokens == 7
    assert resp.provider == "openai"


def _make_gemini_resp() -> MagicMock:
    """Build a minimal google-genai response mock.

    finish_reason uses the REAL FinishReason enum so the test exercises
    `.value` extraction rather than trivially passing on a plain string.
    """
    resp = MagicMock()
    resp.text = "hello from gemini"
    resp.usage_metadata.prompt_token_count = 8
    resp.usage_metadata.candidates_token_count = 3
    resp.usage_metadata.thoughts_token_count = 1
    cand = MagicMock()
    cand.finish_reason = genai_types.FinishReason.STOP  # real enum, not a plain string
    resp.candidates = [cand]
    return resp


def test_gemini_native_dispatch_bare_model_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini native path passes model id BARE — no 'models/' prefix."""
    _use_settings(monkeypatch, gemini_api_key="AIza-test")
    gemini_resp = _make_gemini_resp()
    client = MagicMock()
    client.models.generate_content.return_value = gemini_resp
    with patch("common.call_model.genai.Client", return_value=client):
        resp = call_model(ModelRequest(
            provider="gemini", model="gemini-3.1-flash-lite", prompt="hi",
        ))
    kwargs = client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-3.1-flash-lite"
    assert resp.text == "hello from gemini"
    assert resp.provider == "gemini"


def test_gemini_native_json_mode_sets_response_mime_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """json_mode=True → config.response_mime_type == 'application/json'."""
    _use_settings(monkeypatch, gemini_api_key="AIza-test")
    gemini_resp = _make_gemini_resp()
    client = MagicMock()
    client.models.generate_content.return_value = gemini_resp
    with patch("common.call_model.genai.Client", return_value=client):
        call_model(ModelRequest(
            provider="gemini", model="gemini-3.1-flash-lite", prompt="hi", json_mode=True,
        ))
    kwargs = client.models.generate_content.call_args.kwargs
    config = kwargs["config"]
    assert config.response_mime_type == "application/json"


def test_gemini_native_thinking_level_minimal_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default thinking_level is 'minimal' (floor for flash-lite)."""
    _use_settings(monkeypatch, gemini_api_key="AIza-test")
    gemini_resp = _make_gemini_resp()
    client = MagicMock()
    client.models.generate_content.return_value = gemini_resp
    with patch("common.call_model.genai.Client", return_value=client):
        call_model(ModelRequest(
            provider="gemini", model="gemini-3.1-flash-lite", prompt="hi",
        ))
    kwargs = client.models.generate_content.call_args.kwargs
    config = kwargs["config"]
    # SDK normalises "minimal" → ThinkingLevel.MINIMAL enum; compare by value.
    assert str(config.thinking_config.thinking_level.value).upper() == "MINIMAL"


def test_gemini_native_system_instruction_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """system is forwarded as system_instruction in GenerateContentConfig."""
    _use_settings(monkeypatch, gemini_api_key="AIza-test")
    gemini_resp = _make_gemini_resp()
    client = MagicMock()
    client.models.generate_content.return_value = gemini_resp
    with patch("common.call_model.genai.Client", return_value=client):
        call_model(ModelRequest(
            provider="gemini", model="gemini-3.1-flash-lite",
            prompt="hi", system="be concise",
        ))
    kwargs = client.models.generate_content.call_args.kwargs
    config = kwargs["config"]
    assert config.system_instruction == "be concise"


def test_gemini_native_usage_maps_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    """input_tokens = prompt_token_count; output_tokens = candidates + thoughts."""
    _use_settings(monkeypatch, gemini_api_key="AIza-test")
    gemini_resp = _make_gemini_resp()
    client = MagicMock()
    client.models.generate_content.return_value = gemini_resp
    with patch("common.call_model.genai.Client", return_value=client):
        resp = call_model(ModelRequest(
            provider="gemini", model="gemini-3.1-flash-lite", prompt="hi",
        ))
    assert resp.input_tokens == 8   # prompt_token_count
    assert resp.output_tokens == 4  # candidates_token_count(3) + thoughts_token_count(1)


def test_gemini_native_stop_reason_bare_enum_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """stop_reason is the bare enum value string ("STOP"), NOT the verbose repr.

    This test would FAIL against the old ``str(fr)`` code which emits
    "FinishReason.STOP" — it verifies that ``.value`` extraction is in place.
    """
    _use_settings(monkeypatch, gemini_api_key="AIza-test")
    gemini_resp = _make_gemini_resp()  # finish_reason = FinishReason.STOP (real enum)
    client = MagicMock()
    client.models.generate_content.return_value = gemini_resp
    with patch("common.call_model.genai.Client", return_value=client):
        resp = call_model(ModelRequest(
            provider="gemini", model="gemini-3.1-flash-lite", prompt="hi",
        ))
    assert resp.stop_reason == "STOP"


def test_gemini_native_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty gemini_api_key → ModelConfigError."""
    _use_settings(monkeypatch, gemini_api_key="")
    with pytest.raises(ModelConfigError, match="GEMINI_API_KEY"):
        call_model(ModelRequest(provider="gemini", model="gemini-3.1-flash-lite", prompt="hi"))


def test_ollama_local_dispatch_uses_local_url(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    _use_settings(monkeypatch, ollama_base_url="http://localhost:11434/v1")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="ollama-local", model="qwen3.5-max", prompt="hi"))
    assert ctor.call_args.kwargs["base_url"] == "http://localhost:11434/v1"
    assert ctor.call_args.kwargs["api_key"] == "ollama"


def test_ollama_cloud_dispatch_uses_ollama_com_endpoint(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    _use_settings(monkeypatch, ollama_api_key="ollama-cloud-test")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="ollama-cloud", model="deepseek-v4-flash:cloud", prompt="hi"))
    assert ctor.call_args.kwargs["base_url"] == "https://ollama.com/v1"
    assert ctor.call_args.kwargs["api_key"] == "ollama-cloud-test"
    # Ollama Cloud passes the model id verbatim (including the :cloud tag).
    assert client.chat.completions.create.call_args.kwargs["model"] == "deepseek-v4-flash:cloud"


def test_xai_dispatch_uses_xai_endpoint(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    _use_settings(monkeypatch, xai_api_key="xai-test")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="xai", model="grok-4-1-fast-reasoning", prompt="hi"))
    assert ctor.call_args.kwargs["base_url"] == "https://api.x.ai/v1"
    assert ctor.call_args.kwargs["api_key"] == "xai-test"
    # Unlike gemini, xAI does NOT require a "models/" prefix on model id.
    assert client.chat.completions.create.call_args.kwargs["model"] == "grok-4-1-fast-reasoning"


def test_alibaba_dispatch_uses_dashscope_endpoint(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    _use_settings(monkeypatch, qwen_us_api_key="dash-test")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="alibaba", model="qwen3.5-flash", prompt="hi"))
    assert ctor.call_args.kwargs["base_url"] == "https://dashscope-us.aliyuncs.com/compatible-mode/v1"
    assert ctor.call_args.kwargs["api_key"] == "dash-test"
    # Like xAI, Alibaba's OpenAI-compat endpoint does NOT require a "models/" prefix.
    assert client.chat.completions.create.call_args.kwargs["model"] == "qwen3.5-flash"


# ---------- request features ----------

def test_json_mode_threads_through(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    _use_settings(monkeypatch, openai_api_key="sk")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("common.call_model.OpenAI", return_value=client):
        call_model(ModelRequest(
            provider="openai", model="gpt-4.1-mini", prompt="hi", json_mode=True,
        ))
    assert client.chat.completions.create.call_args.kwargs["response_format"] == {"type": "json_object"}


def test_use_completion_tokens_switches_to_max_completion_tokens_param(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    """GPT-5+ family rejects `max_tokens`; the openai-compat path emits
    `max_completion_tokens` instead when the flag is set."""
    _use_settings(monkeypatch, openai_api_key="sk")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("common.call_model.OpenAI", return_value=client):
        call_model(ModelRequest(
            provider="openai", model="gpt-5.4-mini", prompt="hi",
            max_tokens=128000, use_completion_tokens=True,
        ))
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs.get("max_completion_tokens") == 128000
    assert "max_tokens" not in kwargs  # mutual exclusion


def test_default_uses_max_tokens_param(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    """Pre-GPT-5 OpenAI / Gemini / Ollama keep using `max_tokens`."""
    _use_settings(monkeypatch, openai_api_key="sk")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("common.call_model.OpenAI", return_value=client):
        call_model(ModelRequest(
            provider="openai", model="gpt-4.1-mini", prompt="hi", max_tokens=4096,
        ))
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs.get("max_tokens") == 4096
    assert "max_completion_tokens" not in kwargs


def test_extra_body_forwarded_to_openai_compat(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    """`extra_body` carries provider-specific knobs (e.g. Qwen `{"think": false}`)."""
    _use_settings(monkeypatch, openai_api_key="sk")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("common.call_model.OpenAI", return_value=client):
        call_model(ModelRequest(
            provider="openai", model="gpt-4.1-mini", prompt="hi",
            extra_body={"reasoning_effort": "low"},
        ))
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs.get("extra_body") == {"reasoning_effort": "low"}


def test_extra_body_omitted_when_none(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    """No `extra_body` kwarg when the request didn't set one — keeps the
    SDK call shape minimal for the common case."""
    _use_settings(monkeypatch, openai_api_key="sk")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("common.call_model.OpenAI", return_value=client):
        call_model(ModelRequest(
            provider="openai", model="gpt-4.1-mini", prompt="hi",
        ))
    kwargs = client.chat.completions.create.call_args.kwargs
    assert "extra_body" not in kwargs


def test_extra_dict_overrides_kwargs(
    monkeypatch: pytest.MonkeyPatch, anthropic_resp: MagicMock
) -> None:
    _use_settings(monkeypatch, anthropic_api_key="sk-ant")
    client = MagicMock()
    client.messages.create.return_value = anthropic_resp
    with patch("anthropic.Anthropic", return_value=client):
        call_model(ModelRequest(
            provider="anthropic", model="claude", prompt="hi",
            max_tokens=100, extra={"max_tokens": 999, "custom": "value"},
        ))
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["max_tokens"] == 999  # extra wins
    assert kwargs["custom"] == "value"


def test_timeout_threads_to_client(
    monkeypatch: pytest.MonkeyPatch, anthropic_resp: MagicMock
) -> None:
    _use_settings(monkeypatch, anthropic_api_key="sk", llm_timeout_seconds=600)
    client = MagicMock()
    client.messages.create.return_value = anthropic_resp
    with patch("anthropic.Anthropic", return_value=client) as ctor:
        call_model(ModelRequest(provider="anthropic", model="claude", prompt="hi"))
    assert ctor.call_args.kwargs["timeout"] == 600


# ---------- error paths ----------

def test_missing_anthropic_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_settings(monkeypatch, anthropic_api_key="")
    with pytest.raises(ModelConfigError, match="ANTHROPIC_API_KEY"):
        call_model(ModelRequest(provider="anthropic", model="claude", prompt="hi"))


def test_missing_openai_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_settings(monkeypatch, openai_api_key="")
    with pytest.raises(ModelConfigError):
        call_model(ModelRequest(provider="openai", model="gpt", prompt="hi"))


def test_missing_xai_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_settings(monkeypatch, xai_api_key="")
    with pytest.raises(ModelConfigError):
        call_model(ModelRequest(provider="xai", model="grok-4-1-fast-reasoning", prompt="hi"))


def test_missing_qwen_us_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_settings(monkeypatch, qwen_us_api_key="")
    with pytest.raises(ModelConfigError):
        call_model(ModelRequest(provider="alibaba", model="qwen3.5-flash", prompt="hi"))


def test_missing_ollama_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_settings(monkeypatch, ollama_api_key="")
    with pytest.raises(ModelConfigError):
        call_model(ModelRequest(provider="ollama-cloud", model="deepseek-v4-flash:cloud", prompt="hi"))


def test_unknown_provider_raises() -> None:
    with pytest.raises(ModelConfigError, match="Unknown provider"):
        call_model(ModelRequest(provider="moonshot", model="x", prompt="hi"))  # type: ignore[arg-type]
