"""Tests for config — env-var loading and Settings defaults."""
from __future__ import annotations

import pytest

from kdb_compiler.config import Settings


def test_from_env_reads_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    s = Settings.from_env()
    assert s.anthropic_api_key == "sk-ant-test"
    assert s.openai_api_key == "sk-oai-test"
    assert s.gemini_api_key == "AIza-test"


def test_defaults_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
              "OLLAMA_BASE_URL", "LLM_TIMEOUT_SECONDS"):
        monkeypatch.delenv(k, raising=False)
    s = Settings.from_env()
    assert s.anthropic_api_key == ""
    assert s.openai_api_key == ""
    assert s.gemini_api_key == ""
    assert s.ollama_base_url == "http://localhost:11434/v1"
    assert s.llm_timeout_seconds == 300


def test_ollama_base_url_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://remote-ollama:11434/v1")
    s = Settings.from_env()
    assert s.ollama_base_url == "http://remote-ollama:11434/v1"


def test_timeout_parses_int(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "600")
    s = Settings.from_env()
    assert s.llm_timeout_seconds == 600


def test_settings_is_frozen() -> None:
    s = Settings()
    with pytest.raises(Exception):
        s.anthropic_api_key = "x"  # type: ignore[misc]
