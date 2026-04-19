"""Tests for call_model — provider dispatch, request shaping, response assembly."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from kdb_compiler import call_model as cm
from kdb_compiler.call_model import ModelConfigError, ModelRequest, call_model
from kdb_compiler.config import Settings


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
    with patch("kdb_compiler.call_model.OpenAI", return_value=client) as ctor:
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


def test_gemini_dispatch_uses_compat_endpoint(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    _use_settings(monkeypatch, gemini_api_key="AIza-test")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("kdb_compiler.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="gemini", model="gemini-2.5-flash", prompt="hi"))
    assert "generativelanguage.googleapis.com" in ctor.call_args.kwargs["base_url"]
    # Gemini endpoint needs the 'models/' prefix
    assert client.chat.completions.create.call_args.kwargs["model"] == "models/gemini-2.5-flash"


def test_gemini_does_not_double_prefix_models(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    _use_settings(monkeypatch, gemini_api_key="AIza-test")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("kdb_compiler.call_model.OpenAI", return_value=client):
        call_model(ModelRequest(provider="gemini", model="models/gemini-2.5-flash", prompt="hi"))
    assert client.chat.completions.create.call_args.kwargs["model"] == "models/gemini-2.5-flash"


def test_ollama_dispatch_uses_local_url(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    _use_settings(monkeypatch, ollama_base_url="http://localhost:11434/v1")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("kdb_compiler.call_model.OpenAI", return_value=client) as ctor:
        call_model(ModelRequest(provider="ollama", model="qwen3.5-max", prompt="hi"))
    assert ctor.call_args.kwargs["base_url"] == "http://localhost:11434/v1"
    assert ctor.call_args.kwargs["api_key"] == "ollama"


# ---------- request features ----------

def test_json_mode_threads_through(
    monkeypatch: pytest.MonkeyPatch, openai_resp: MagicMock
) -> None:
    _use_settings(monkeypatch, openai_api_key="sk")
    client = MagicMock()
    client.chat.completions.create.return_value = openai_resp
    with patch("kdb_compiler.call_model.OpenAI", return_value=client):
        call_model(ModelRequest(
            provider="openai", model="gpt-4.1-mini", prompt="hi", json_mode=True,
        ))
    assert client.chat.completions.create.call_args.kwargs["response_format"] == {"type": "json_object"}


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


def test_missing_gemini_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_settings(monkeypatch, gemini_api_key="")
    with pytest.raises(ModelConfigError):
        call_model(ModelRequest(provider="gemini", model="gemini-pro", prompt="hi"))


def test_unknown_provider_raises() -> None:
    with pytest.raises(ModelConfigError, match="Unknown provider"):
        call_model(ModelRequest(provider="alibaba", model="x", prompt="hi"))  # type: ignore[arg-type]
