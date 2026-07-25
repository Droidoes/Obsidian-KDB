"""Tests for config — dotenv loading, resolve_required_env, llm_timeout_seconds."""
from __future__ import annotations

import os

import pytest

from common import config
from common.config import (
    llm_inactivity_timeout_seconds,
    llm_timeout_seconds,
    resolve_required_env,
)
from common.model_route import ModelConfigError


# ---------- dotenv loading (kept semantics) ----------

def test_find_dotenv_discovers_repo_env() -> None:
    """_find_dotenv walks up from the package and finds the repo-root .env."""
    found = config._find_dotenv()
    assert found is not None
    assert found.name == ".env"
    assert found.is_file()


def test_dotenv_load_semantics(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The import-time block is load_dotenv(_find_dotenv(), override=False) —
    pin the semantics: values load; a pre-existing env var is NOT overridden."""
    sentinel = "KDB_DOTENV_TEST_SENTINEL"
    env_file = tmp_path / ".env"
    env_file.write_text(f"{sentinel}=from-dotenv\n")

    monkeypatch.delenv(sentinel, raising=False)
    config.load_dotenv(dotenv_path=env_file, override=False)
    assert os.getenv(sentinel) == "from-dotenv"

    monkeypatch.setenv(sentinel, "pre-existing")
    config.load_dotenv(dotenv_path=env_file, override=False)
    assert os.getenv(sentinel) == "pre-existing"


# ---------- resolve_required_env ----------

def test_resolve_required_env_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KDB_TEST_KEY_OK", "sk-test-value")
    assert resolve_required_env("KDB_TEST_KEY_OK", model="m1", provider="acme") == "sk-test-value"


def test_resolve_required_env_missing_names_var_model_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KDB_TEST_KEY_MISSING", raising=False)
    with pytest.raises(ModelConfigError) as excinfo:
        resolve_required_env("KDB_TEST_KEY_MISSING", model="m1", provider="acme")
    msg = str(excinfo.value)
    assert "KDB_TEST_KEY_MISSING" in msg
    assert "m1" in msg
    assert "acme" in msg


def test_resolve_required_env_empty_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KDB_TEST_KEY_EMPTY", "")
    with pytest.raises(ModelConfigError) as excinfo:
        resolve_required_env("KDB_TEST_KEY_EMPTY", model="m1", provider="acme")
    msg = str(excinfo.value)
    assert "KDB_TEST_KEY_EMPTY" in msg
    assert "m1" in msg
    assert "acme" in msg


def test_resolve_required_env_error_never_contains_the_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sentinel secret sitting in the environment must NOT leak into the error."""
    secret = "sk-live-SENTINEL-do-not-leak"
    monkeypatch.setenv("KDB_TEST_SENTINEL_SECRET", secret)
    monkeypatch.setenv("KDB_TEST_KEY_EMPTY2", "")
    with pytest.raises(ModelConfigError) as excinfo:
        resolve_required_env("KDB_TEST_KEY_EMPTY2", model="m1", provider="acme")
    assert secret not in str(excinfo.value)


# ---------- llm_timeout_seconds ----------

def test_llm_timeout_seconds_default_120(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
    assert llm_timeout_seconds() == 120


def test_llm_timeout_seconds_valid_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "600")
    assert llm_timeout_seconds() == 600


@pytest.mark.parametrize("raw", ["abc", "10.5", ""])
def test_llm_timeout_seconds_non_integer_fails_hard(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", raw)
    with pytest.raises(ModelConfigError, match="LLM_TIMEOUT_SECONDS"):
        llm_timeout_seconds()


@pytest.mark.parametrize("raw", ["0", "-30"])
def test_llm_timeout_seconds_non_positive_fails_hard(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", raw)
    with pytest.raises(ModelConfigError, match="LLM_TIMEOUT_SECONDS"):
        llm_timeout_seconds()


# ---------- llm_inactivity_timeout_seconds ----------

def test_llm_inactivity_timeout_seconds_default_900(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_INACTIVITY_TIMEOUT_SECONDS", raising=False)
    assert llm_inactivity_timeout_seconds() == 900


def test_llm_inactivity_timeout_seconds_valid_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_INACTIVITY_TIMEOUT_SECONDS", "45")
    assert llm_inactivity_timeout_seconds() == 45


@pytest.mark.parametrize("raw", ["abc", "10.5", ""])
def test_llm_inactivity_timeout_seconds_non_integer_fails_hard(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("LLM_INACTIVITY_TIMEOUT_SECONDS", raw)
    with pytest.raises(ModelConfigError, match="LLM_INACTIVITY_TIMEOUT_SECONDS"):
        llm_inactivity_timeout_seconds()


@pytest.mark.parametrize("raw", ["0", "-30"])
def test_llm_inactivity_timeout_seconds_non_positive_fails_hard(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("LLM_INACTIVITY_TIMEOUT_SECONDS", raw)
    with pytest.raises(ModelConfigError, match="LLM_INACTIVITY_TIMEOUT_SECONDS"):
        llm_inactivity_timeout_seconds()
