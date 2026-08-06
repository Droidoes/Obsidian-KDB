"""Tests for call_model — provider dispatch, request shaping, response assembly.

Task #121: the Settings singleton is gone — every test seeds env vars with
monkeypatch.setenv (late resolution at the call boundary). The route-less
dispatch tests double as the 9 Class-B registry-row golden pins: each
constructor must observe the byte-identical base_url + api_key + model
passthrough as before the rewrite.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from google.genai import types as genai_types

from common.call_model import (
    ModelConfigError,
    ModelRequest,
    call_model,
    normalize_stop_reason,
)
from common.model_route import ModelRoute


# ---------- fixtures ----------

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


def _openai_client(openai_resp: MagicMock) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    return client


# ---------- registry-row golden pins (route-less dispatch) ----------

def test_anthropic_dispatch(monkeypatch: pytest.MonkeyPatch, anthropic_resp: MagicMock) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    client = MagicMock()
    client.messages.create.return_value = anthropic_resp
    with patch("anthropic.Anthropic", return_value=client) as ctor:
        resp = call_model(ModelRequest(
            provider="anthropic", model="claude-opus-4-7",
            prompt="hi", system="be nice",
        ))
    # Golden pin: injected key + explicit max_retries (D8).
    assert ctor.call_args.kwargs["api_key"] == "sk-ant-test"
    assert ctor.call_args.kwargs["max_retries"] == 2
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
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        resp = call_model(ModelRequest(
            provider="openai", model="gpt-4.1-mini",
            prompt="hi", system="be nice",
        ))
    # Golden pin: standard OpenAI endpoint — base_url None; key from OPENAI_API_KEY.
    assert ctor.call_args.kwargs.get("base_url") is None
    assert ctor.call_args.kwargs["api_key"] == "sk-oai-test"
    assert ctor.call_args.kwargs["max_retries"] == 2
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


def test_xai_dispatch_uses_xai_endpoint(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    monkeypatch.setenv("XAI_GROK_API_KEY", "xai-test")
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="xai", model="grok-4-1-fast-reasoning", prompt="hi"))
    assert ctor.call_args.kwargs["base_url"] == "https://api.x.ai/v1"
    assert ctor.call_args.kwargs["api_key"] == "xai-test"
    # Unlike gemini, xAI does NOT require a "models/" prefix on model id.
    assert client.chat.completions.create.call_args.kwargs["model"] == "grok-4-1-fast-reasoning"


def test_alibaba_dispatch_uses_dashscope_endpoint(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    monkeypatch.setenv("QWEN_US_API_KEY", "dash-test")
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="alibaba", model="qwen3.5-flash", prompt="hi"))
    assert ctor.call_args.kwargs["base_url"] == "https://dashscope-us.aliyuncs.com/compatible-mode/v1"
    assert ctor.call_args.kwargs["api_key"] == "dash-test"
    # Like xAI, Alibaba's OpenAI-compat endpoint does NOT require a "models/" prefix.
    assert client.chat.completions.create.call_args.kwargs["model"] == "qwen3.5-flash"


def test_deepseek_dispatch_uses_deepseek_endpoint(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="deepseek", model="deepseek-v4-flash", prompt="hi"))
    assert ctor.call_args.kwargs["base_url"] == "https://api.deepseek.com"
    assert ctor.call_args.kwargs["api_key"] == "ds-test"
    assert client.chat.completions.create.call_args.kwargs["model"] == "deepseek-v4-flash"


def test_ollama_local_dispatch_uses_local_url(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)  # deterministic default
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="ollama-local", model="qwen3.5-max", prompt="hi"))
    assert ctor.call_args.kwargs["base_url"] == "http://localhost:11434/v1"
    assert ctor.call_args.kwargs["api_key"] == "ollama"


def test_ollama_local_endpoint_resolves_late(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    """The registry is a per-request factory: OLLAMA_BASE_URL is read at CALL
    time (this setenv runs long after the module was imported), and the
    route-less ollama-local call must observe the NEW endpoint + dummy key."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://remote-ollama:11434/v1")
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="ollama-local", model="qwen3.5-max", prompt="hi"))
    assert ctor.call_args.kwargs["base_url"] == "http://remote-ollama:11434/v1"
    assert ctor.call_args.kwargs["api_key"] == "ollama"


def test_ollama_cloud_dispatch_uses_ollama_com_endpoint(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-cloud-test")
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="ollama-cloud", model="deepseek-v4-flash:cloud", prompt="hi"))
    assert ctor.call_args.kwargs["base_url"] == "https://ollama.com/v1"
    assert ctor.call_args.kwargs["api_key"] == "ollama-cloud-test"
    # Ollama Cloud passes the model id verbatim (including the :cloud tag).
    assert client.chat.completions.create.call_args.kwargs["model"] == "deepseek-v4-flash:cloud"


def test_zai_dispatch_uses_zai_endpoint(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    monkeypatch.setenv("ZAI_API_KEY", "zai-test")
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="zai", model="glm-5-turbo", prompt="hi"))
    assert ctor.call_args.kwargs["base_url"] == "https://api.z.ai/api/paas/v4"
    assert ctor.call_args.kwargs["api_key"] == "zai-test"
    assert client.chat.completions.create.call_args.kwargs["model"] == "glm-5-turbo"


# ---------- gemini native path ----------

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


def _gemini_client(gemini_resp: MagicMock) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = gemini_resp
    return client


def test_gemini_native_dispatch_bare_model_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini native path passes model id BARE — no 'models/' prefix."""
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    gemini_resp = _make_gemini_resp()
    client = _gemini_client(gemini_resp)
    with patch("common.call_model.genai.Client", return_value=client) as ctor:
        resp = call_model(ModelRequest(
            provider="gemini", model="gemini-3.1-flash-lite", prompt="hi",
        ))
    # Golden pin: key injected from GEMINI_API_KEY; NO max_retries (google-genai
    # has no such constructor kwarg — D8 preserves retry_options=None behavior).
    assert ctor.call_args.kwargs["api_key"] == "AIza-test"
    assert "max_retries" not in ctor.call_args.kwargs
    kwargs = client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-3.1-flash-lite"
    assert resp.text == "hello from gemini"
    assert resp.provider == "gemini"


def test_gemini_native_json_mode_sets_response_mime_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """json_mode=True → config.response_mime_type == 'application/json'."""
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    client = _gemini_client(_make_gemini_resp())
    with patch("common.call_model.genai.Client", return_value=client):
        call_model(ModelRequest(
            provider="gemini", model="gemini-3.1-flash-lite", prompt="hi", json_mode=True,
        ))
    kwargs = client.models.generate_content.call_args.kwargs
    config = kwargs["config"]
    assert config.response_mime_type == "application/json"


def test_gemini_native_thinking_level_minimal_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default thinking_level is 'minimal' (floor for flash-lite)."""
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    client = _gemini_client(_make_gemini_resp())
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
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    client = _gemini_client(_make_gemini_resp())
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
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    client = _gemini_client(_make_gemini_resp())
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
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    client = _gemini_client(_make_gemini_resp())  # finish_reason = FinishReason.STOP (real enum)
    with patch("common.call_model.genai.Client", return_value=client):
        resp = call_model(ModelRequest(
            provider="gemini", model="gemini-3.1-flash-lite", prompt="hi",
        ))
    assert resp.stop_reason == "STOP"


# ---------- temperature / request features ----------

def test_openai_temperature_default_sent(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    # Default temperature=0.0 → the kwarg IS present on the SDK call.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client):
        call_model(ModelRequest(provider="openai", model="gpt-4.1-mini", prompt="hi"))
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0.0


def test_openai_temperature_none_omits_kwarg(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    # temperature=None (per-model pool override, e.g. gpt-5.4-mini reasoning
    # family that 400s on any non-default temperature) → the kwarg is OMITTED
    # so the API applies its own default.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client):
        call_model(ModelRequest(
            provider="openai", model="gpt-5.4-mini", prompt="hi", temperature=None,
        ))
    kwargs = client.chat.completions.create.call_args.kwargs
    assert "temperature" not in kwargs


def test_anthropic_temperature_none_omits_kwarg(
    monkeypatch: pytest.MonkeyPatch, anthropic_resp: MagicMock
) -> None:
    # temperature=None → omitted on the anthropic path too (symmetry).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    client = MagicMock()
    client.messages.create.return_value = anthropic_resp
    with patch("anthropic.Anthropic", return_value=client):
        call_model(ModelRequest(
            provider="anthropic", model="claude-opus-4-7", prompt="hi",
            temperature=None,
        ))
    kwargs = client.messages.create.call_args.kwargs
    assert "temperature" not in kwargs


def test_json_mode_threads_through(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    client = _openai_client(openai_resp)
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
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    client = _openai_client(openai_resp)
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
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    client = _openai_client(openai_resp)
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
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    client = _openai_client(openai_resp)
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
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client):
        call_model(ModelRequest(
            provider="openai", model="gpt-4.1-mini", prompt="hi",
        ))
    kwargs = client.chat.completions.create.call_args.kwargs
    assert "extra_body" not in kwargs


def test_extra_dict_overrides_kwargs(
    monkeypatch: pytest.MonkeyPatch, anthropic_resp: MagicMock
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
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
    """D7: LLM_TIMEOUT_SECONDS drives connect/write/pool; the read-silence
    watchdog (LLM_INACTIVITY_TIMEOUT_SECONDS) drives `read`."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "600")
    monkeypatch.delenv("LLM_INACTIVITY_TIMEOUT_SECONDS", raising=False)
    client = MagicMock()
    client.messages.create.return_value = anthropic_resp
    with patch("anthropic.Anthropic", return_value=client) as ctor:
        call_model(ModelRequest(provider="anthropic", model="claude", prompt="hi"))
    timeout = ctor.call_args.kwargs["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 600
    assert timeout.write == 600
    assert timeout.pool == 600
    assert timeout.read == 900  # inactivity watchdog default


# ---------- timeout construction pins (D7) ----------

def test_openai_constructor_timeout_httpx_shape_default(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    """Default shape: read=900 (watchdog), connect/write/pool=120."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("LLM_INACTIVITY_TIMEOUT_SECONDS", raising=False)
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="openai", model="gpt-4.1-mini", prompt="hi"))
    timeout = ctor.call_args.kwargs["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 900
    assert timeout.connect == 120
    assert timeout.write == 120
    assert timeout.pool == 120


def test_openai_constructor_timeout_honors_both_knob_overrides(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("LLM_INACTIVITY_TIMEOUT_SECONDS", "45")
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="openai", model="gpt-4.1-mini", prompt="hi"))
    timeout = ctor.call_args.kwargs["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 30
    assert timeout.write == 30
    assert timeout.pool == 30
    assert timeout.read == 45


def test_anthropic_constructor_timeout_httpx_shape_default(
    monkeypatch: pytest.MonkeyPatch, anthropic_resp: MagicMock
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk")
    monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("LLM_INACTIVITY_TIMEOUT_SECONDS", raising=False)
    client = MagicMock()
    client.messages.create.return_value = anthropic_resp
    with patch("anthropic.Anthropic", return_value=client) as ctor:
        call_model(ModelRequest(provider="anthropic", model="claude", prompt="hi"))
    timeout = ctor.call_args.kwargs["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 900
    assert timeout.connect == 120
    assert timeout.write == 120
    assert timeout.pool == 120


def test_gemini_http_options_timeout_scalar_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini's scalar-only HttpOptions takes the inactivity value × 1000
    (also drives X-Server-Timeout)."""
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    monkeypatch.delenv("LLM_INACTIVITY_TIMEOUT_SECONDS", raising=False)
    client = _gemini_client(_make_gemini_resp())
    with patch("common.call_model.genai.Client", return_value=client) as ctor:
        call_model(ModelRequest(provider="gemini", model="gemini-3.1-flash-lite", prompt="hi"))
    assert ctor.call_args.kwargs["http_options"].timeout == 900_000


def test_gemini_http_options_timeout_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    monkeypatch.setenv("LLM_INACTIVITY_TIMEOUT_SECONDS", "45")
    client = _gemini_client(_make_gemini_resp())
    with patch("common.call_model.genai.Client", return_value=client) as ctor:
        call_model(ModelRequest(provider="gemini", model="gemini-3.1-flash-lite", prompt="hi"))
    assert ctor.call_args.kwargs["http_options"].timeout == 45_000


# ---------- retry-budget pins (D8) ----------

def test_openai_and_anthropic_constructors_pass_max_retries_2(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock, anthropic_resp: MagicMock
) -> None:
    """max_retries=2 is EXPLICIT on both SDK constructors — identical to the
    SDK default, pinned against upstream drift (D8)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    oai_client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=oai_client) as oai_ctor:
        call_model(ModelRequest(provider="openai", model="gpt-4.1-mini", prompt="hi"))
    assert oai_ctor.call_args.kwargs["max_retries"] == 2

    ant_client = MagicMock()
    ant_client.messages.create.return_value = anthropic_resp
    with patch("anthropic.Anthropic", return_value=ant_client) as ant_ctor:
        call_model(ModelRequest(provider="anthropic", model="claude", prompt="hi"))
    assert ant_ctor.call_args.kwargs["max_retries"] == 2


# ---------- missing-key error paths ----------

def test_missing_anthropic_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    with pytest.raises(ModelConfigError, match="ANTHROPIC_API_KEY"):
        call_model(ModelRequest(provider="anthropic", model="claude", prompt="hi"))


def test_missing_openai_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with pytest.raises(ModelConfigError, match="OPENAI_API_KEY"):
        call_model(ModelRequest(provider="openai", model="gpt", prompt="hi"))


def test_missing_gemini_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(ModelConfigError, match="GEMINI_API_KEY"):
        call_model(ModelRequest(provider="gemini", model="gemini-3.1-flash-lite", prompt="hi"))


def test_missing_xai_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_GROK_API_KEY", "")
    with pytest.raises(ModelConfigError, match="XAI_GROK_API_KEY"):
        call_model(ModelRequest(provider="xai", model="grok-4-1-fast-reasoning", prompt="hi"))


def test_missing_qwen_us_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QWEN_US_API_KEY", "")
    with pytest.raises(ModelConfigError, match="QWEN_US_API_KEY"):
        call_model(ModelRequest(provider="alibaba", model="qwen3.5-flash", prompt="hi"))


def test_missing_zai_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZAI_API_KEY", "")
    with pytest.raises(ModelConfigError, match="ZAI_API_KEY"):
        call_model(ModelRequest(provider="zai", model="glm-5-turbo", prompt="hi"))


def test_missing_ollama_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "")
    with pytest.raises(ModelConfigError, match="OLLAMA_API_KEY"):
        call_model(ModelRequest(provider="ollama-cloud", model="deepseek-v4-flash:cloud", prompt="hi"))


def test_missing_key_error_names_var_model_provider_never_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The resolver error names the env var + model + provider — and must never
    leak a secret value sitting elsewhere in the environment."""
    secret = "sk-live-SENTINEL-do-not-leak"
    monkeypatch.setenv("OPENAI_API_KEY", secret)  # present, but NOT the var this call needs
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    with pytest.raises(ModelConfigError) as excinfo:
        call_model(ModelRequest(provider="deepseek", model="deepseek-v4-flash", prompt="hi"))
    msg = str(excinfo.value)
    assert "DEEPSEEK_API_KEY" in msg
    assert "deepseek-v4-flash" in msg
    assert "deepseek" in msg
    assert secret not in msg


# ---------- provider identity + registry gating ----------

def test_unknown_provider_raises_before_sdk_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route-less unknown provider → ModelConfigError before ANY SDK constructor."""
    with (patch("common.call_model.OpenAI") as oai,
          patch("common.call_model.genai.Client") as gem,
          patch("anthropic.Anthropic") as ant):
        with pytest.raises(ModelConfigError, match="Unknown provider"):
            call_model(ModelRequest(provider="moonshot", model="x", prompt="hi"))
    oai.assert_not_called()
    gem.assert_not_called()
    ant.assert_not_called()


@pytest.mark.parametrize("bad", ["", "   ", " openai", "openai "])
def test_invalid_provider_identity_rejected(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    """Empty/whitespace/padded provider → ModelConfigError — routing,
    thinking-lookup, echo and telemetry must see ONE canonical string."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    with patch("common.call_model.OpenAI") as oai:
        with pytest.raises(ModelConfigError):
            call_model(ModelRequest(provider=bad, model="gpt", prompt="hi"))
    oai.assert_not_called()


@pytest.mark.parametrize("bad", ["", "   ", " openai", "openai "])
def test_invalid_provider_identity_rejected_even_with_explicit_route(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    """Provider identity is validated FIRST — an explicit route does not skip it."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    route = ModelRoute("openai_compat", None, "OPENAI_API_KEY")
    with patch("common.call_model.OpenAI") as oai:
        with pytest.raises(ModelConfigError):
            call_model(ModelRequest(provider=bad, model="gpt", prompt="hi", route=route))
    oai.assert_not_called()


# ---------- explicit-route authority (Class A) ----------

def test_explicit_route_authority_unknown_provider(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    """D5 zero-code-edits pin: a fabricated provider 'acme' with an explicit
    route dispatches — the registry is never consulted."""
    monkeypatch.setenv("ACME_API_KEY", "acme-secret")
    route = ModelRoute("openai_compat", "https://acme.example.com/v1", "ACME_API_KEY")
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client) as ctor:
        resp = call_model(ModelRequest(provider="acme", model="acme-1", prompt="hi", route=route))
    assert ctor.call_args.kwargs["base_url"] == "https://acme.example.com/v1"
    assert ctor.call_args.kwargs["api_key"] == "acme-secret"
    assert client.chat.completions.create.call_args.kwargs["model"] == "acme-1"
    assert resp.provider == "acme"


def test_explicit_route_api_call_type_differs_from_registry_row(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    """The explicit route's api_call_type alone selects the handler — even when
    it differs from the provider's registry row (gemini → openai_compat here)."""
    monkeypatch.setenv("PROXY_API_KEY", "proxy-secret")
    route = ModelRoute("openai_compat", "https://proxy.example.com/v1", "PROXY_API_KEY")
    client = _openai_client(openai_resp)
    with (patch("common.call_model.OpenAI", return_value=client) as oai_ctor,
          patch("common.call_model.genai.Client") as gem_ctor):
        resp = call_model(ModelRequest(
            provider="gemini", model="gemini-3.1-flash-lite", prompt="hi", route=route,
        ))
    assert oai_ctor.call_args.kwargs["base_url"] == "https://proxy.example.com/v1"
    assert oai_ctor.call_args.kwargs["api_key"] == "proxy-secret"
    gem_ctor.assert_not_called()
    assert resp.text == "hello from gpt"


@pytest.mark.parametrize("provider", ["ollama-local", "acme"])
def test_explicit_route_no_auth_rejected(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    """No-auth is NEVER caller-declared: an explicit route with api_key_env=None
    is rejected for ollama-local and non-ollama providers alike."""
    route = ModelRoute("openai_compat", "http://localhost:11434/v1", None)
    with patch("common.call_model.OpenAI") as oai:
        with pytest.raises(ModelConfigError, match="api_key_env"):
            call_model(ModelRequest(provider=provider, model="m", prompt="hi", route=route))
    oai.assert_not_called()


# ---------- Gate-2 runtime-type pins ----------

def test_gate2_non_model_route_rejected_before_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    with patch("common.call_model.OpenAI") as oai:
        with pytest.raises(ModelConfigError):
            call_model(ModelRequest(
                provider="openai", model="gpt", prompt="hi",
                route="not-a-route",  # type: ignore[arg-type]
            ))
    oai.assert_not_called()


@pytest.mark.parametrize("route", [
    ModelRoute(["openai_compat"], None, "OPENAI_API_KEY"),  # type: ignore[arg-type]  # unhashable: no TypeError leak
    ModelRoute("openai_compat", 123, "OPENAI_API_KEY"),     # type: ignore[arg-type]
    ModelRoute("openai_compat", None, 123),                 # type: ignore[arg-type]
])
def test_gate2_wrong_typed_fields_rejected_before_sdk(
    monkeypatch: pytest.MonkeyPatch, route: ModelRoute
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    with patch("common.call_model.OpenAI") as oai:
        with pytest.raises(ModelConfigError):
            call_model(ModelRequest(provider="openai", model="gpt", prompt="hi", route=route))
    oai.assert_not_called()


def test_unknown_api_call_type_on_fabricated_route_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACME_API_KEY", "acme-secret")
    route = ModelRoute("telepathy", None, "ACME_API_KEY")  # type: ignore[arg-type]
    with patch("common.call_model.OpenAI") as oai:
        with pytest.raises(ModelConfigError, match="telepathy"):
            call_model(ModelRequest(provider="acme", model="m", prompt="hi", route=route))
    oai.assert_not_called()


# ---------- stop-reason normalization (#124) ----------

@pytest.mark.parametrize("raw,api_call_type,expected", [
    # Cap stops — each family's own verified spelling.
    ("length", "openai_compat", "output_cap"),
    ("max_tokens", "anthropic", "output_cap"),
    ("MAX_TOKENS", "gemini", "output_cap"),
    # Ordinary completions.
    ("stop", "openai_compat", "complete"),
    ("end_turn", "anthropic", "complete"),
    ("STOP", "gemini", "complete"),
    # D9.4 no-guessing: a spelling outside the ROUTE's own sets is unknown,
    # even when another route would classify it.
    ("MAX_TOKENS", "openai_compat", "unknown"),
    ("MAX_TOKENS", "anthropic", "unknown"),
    ("max_tokens", "openai_compat", "unknown"),
    ("max_tokens", "gemini", "unknown"),
    ("length", "anthropic", "unknown"),
    ("length", "gemini", "unknown"),
    ("STOP", "openai_compat", "unknown"),
    ("STOP", "anthropic", "unknown"),
    ("stop", "anthropic", "unknown"),
    ("stop", "gemini", "unknown"),
    ("end_turn", "openai_compat", "unknown"),
    ("end_turn", "gemini", "unknown"),
    # Unclassified-but-real values, and absent values.
    ("tool_calls", "openai_compat", "unknown"),
    ("tool_use", "anthropic", "unknown"),
    ("SAFETY", "gemini", "unknown"),
    (None, "openai_compat", "unknown"),
    (None, "anthropic", "unknown"),
    (None, "gemini", "unknown"),
    # Unknown route → never guessed.
    ("length", "telepathy", "unknown"),
    ("MAX_TOKENS", "", "unknown"),
])
def test_normalize_stop_reason_route_aware_table(
    raw: str | None, api_call_type: str, expected: str
) -> None:
    """One closed api_call_type-aware map (D9.4 — never guesses)."""
    assert normalize_stop_reason(raw, api_call_type=api_call_type) == expected


def test_gemini_max_tokens_normalized_at_boundary_raw_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#124 regression pin: gemini's UPPERCASE enum value classifies as
    output_cap at the boundary, and the raw spelling is preserved verbatim."""
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    gemini_resp = _make_gemini_resp()
    gemini_resp.candidates[0].finish_reason = genai_types.FinishReason.MAX_TOKENS
    client = _gemini_client(gemini_resp)
    with patch("common.call_model.genai.Client", return_value=client):
        resp = call_model(ModelRequest(
            provider="gemini", model="gemini-3.6-flash", prompt="hi",
        ))
    assert resp.stop_reason == "MAX_TOKENS"  # raw, verbatim
    assert resp.stop_reason_normalized == "output_cap"


def test_openai_length_normalized_at_boundary(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
    openai_resp.choices[0].finish_reason = "length"
    client = _openai_client(openai_resp)
    with patch("common.call_model.OpenAI", return_value=client):
        resp = call_model(ModelRequest(
            provider="openai", model="gpt-4.1-mini", prompt="hi",
        ))
    assert resp.stop_reason == "length"
    assert resp.stop_reason_normalized == "output_cap"


def test_gemini_stop_normalized_complete_at_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    client = _gemini_client(_make_gemini_resp())  # finish_reason = FinishReason.STOP
    with patch("common.call_model.genai.Client", return_value=client):
        resp = call_model(ModelRequest(
            provider="gemini", model="gemini-3.6-flash", prompt="hi",
        ))
    assert resp.stop_reason == "STOP"
    assert resp.stop_reason_normalized == "complete"


def test_stop_reason_normalized_defaults_unknown_for_direct_construction() -> None:
    """Callers that build a ModelResponse without the boundary (tests, replay)
    get 'unknown' — classification is the boundary's job, never guessed."""
    from common.call_model import ModelResponse
    resp = ModelResponse(
        text="x", input_tokens=1, output_tokens=1, latency_ms=1,
        model="m", provider="p", stop_reason="max_tokens",
    )
    assert resp.stop_reason_normalized == "unknown"
