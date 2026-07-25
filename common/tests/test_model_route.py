"""Tests for model_route — provider identity + the ordered validate_route matrix."""
from __future__ import annotations

import pytest

from common.model_route import (
    API_CALL_TYPES,
    ModelConfigError,
    ModelRoute,
    validate_provider_identity,
    validate_route,
)


# ---------- validate_provider_identity ----------

def test_provider_identity_accepts_normal_string() -> None:
    assert validate_provider_identity("deepseek") == "deepseek"


@pytest.mark.parametrize("bad", [None, 123, 4.5, ["openai"], object()])
def test_provider_identity_rejects_non_str(bad: object) -> None:
    with pytest.raises(ModelConfigError):
        validate_provider_identity(bad)


@pytest.mark.parametrize("bad", ["", "   ", "\t\n"])
def test_provider_identity_rejects_empty_or_whitespace_only(bad: str) -> None:
    with pytest.raises(ModelConfigError):
        validate_provider_identity(bad)


@pytest.mark.parametrize("bad", [" openai", "openai ", " openai ", "\topenai"])
def test_provider_identity_rejects_padded(bad: str) -> None:
    """Canonical rule: leading/trailing whitespace is REJECTED, never silently
    normalized — routing/lookup/echo/telemetry must see ONE identical string."""
    with pytest.raises(ModelConfigError):
        validate_provider_identity(bad)


# ---------- validate_route — happy paths ----------

def test_valid_route_returned_unchanged() -> None:
    route = ModelRoute("openai_compat", None, "TEST_API_KEY")
    assert validate_route(route, provider="acme", allow_no_auth=False) is route


def test_valid_endpoint_override_accepted() -> None:
    route = ModelRoute("openai_compat", "https://api.deepseek.com", "DEEPSEEK_API_KEY")
    assert validate_route(route, provider="deepseek", allow_no_auth=False) is route


def test_api_call_types_closed_set_matches_literal() -> None:
    assert API_CALL_TYPES == frozenset({"openai_compat", "anthropic", "gemini"})


# ---------- check 1: route is a ModelRoute instance ----------

def test_route_must_be_model_route_instance() -> None:
    with pytest.raises(ModelConfigError, match="acme"):
        validate_route("not-a-route", provider="acme", allow_no_auth=False)  # type: ignore[arg-type]


# ---------- check 2: api_call_type — str BEFORE membership ----------

@pytest.mark.parametrize("bad", [None, 123, object()])
def test_api_call_type_non_str_rejected(bad: object) -> None:
    route = ModelRoute(bad, None, "TEST_API_KEY")  # type: ignore[arg-type]
    with pytest.raises(ModelConfigError, match="api_call_type"):
        validate_route(route, provider="acme", allow_no_auth=False)


def test_api_call_type_unhashable_list_rejected_without_typeerror() -> None:
    """The str check must run BEFORE closed-set membership — a list would
    otherwise leak a raw TypeError (unhashable) from `in frozenset`."""
    route = ModelRoute(["openai_compat"], None, "TEST_API_KEY")  # type: ignore[arg-type]
    with pytest.raises(ModelConfigError):  # ModelConfigError, NOT TypeError
        validate_route(route, provider="acme", allow_no_auth=False)


def test_api_call_type_unknown_rejected() -> None:
    route = ModelRoute("telepathy", None, "TEST_API_KEY")  # type: ignore[arg-type]
    with pytest.raises(ModelConfigError, match="telepathy"):
        validate_route(route, provider="acme", allow_no_auth=False)


# ---------- check 3: endpoint — None or non-empty, non-padded str ----------

@pytest.mark.parametrize("bad", [123, 4.5, ["https://x"], object()])
def test_endpoint_non_str_rejected(bad: object) -> None:
    route = ModelRoute("openai_compat", bad, "TEST_API_KEY")  # type: ignore[arg-type]
    with pytest.raises(ModelConfigError, match="endpoint"):
        validate_route(route, provider="acme", allow_no_auth=False)


@pytest.mark.parametrize("bad", ["", "   "])
def test_endpoint_empty_or_whitespace_only_rejected(bad: str) -> None:
    route = ModelRoute("openai_compat", bad, "TEST_API_KEY")
    with pytest.raises(ModelConfigError, match="endpoint"):
        validate_route(route, provider="acme", allow_no_auth=False)


def test_endpoint_padded_rejected() -> None:
    route = ModelRoute("openai_compat", " https://api.x.ai/v1 ", "TEST_API_KEY")
    with pytest.raises(ModelConfigError, match="endpoint"):
        validate_route(route, provider="acme", allow_no_auth=False)


# ---------- check 4: api_key_env — None or non-empty, non-padded str ----------

@pytest.mark.parametrize("bad", [123, ["KEY"], object()])
def test_api_key_env_non_str_rejected(bad: object) -> None:
    route = ModelRoute("openai_compat", None, bad)  # type: ignore[arg-type]
    with pytest.raises(ModelConfigError, match="api_key_env"):
        validate_route(route, provider="acme", allow_no_auth=True)


@pytest.mark.parametrize("bad", ["", "   ", " KEY", "KEY "])
def test_api_key_env_empty_whitespace_padded_rejected(bad: str) -> None:
    """Run under allow_no_auth=True — the flag NEVER disables type/shape validation."""
    route = ModelRoute("openai_compat", None, bad)
    with pytest.raises(ModelConfigError, match="api_key_env"):
        validate_route(route, provider="acme", allow_no_auth=True)


# ---------- check 5: auth policy ----------

def test_api_key_env_none_rejected_when_auth_required() -> None:
    route = ModelRoute("openai_compat", None, None)
    with pytest.raises(ModelConfigError, match="api_key_env"):
        validate_route(route, provider="acme", allow_no_auth=False)


def test_api_key_env_none_accepted_when_no_auth_allowed() -> None:
    route = ModelRoute("openai_compat", "http://localhost:11434/v1", None)
    assert validate_route(route, provider="ollama-local", allow_no_auth=True) is route


# ---------- check 6: native transports require endpoint=None ----------

@pytest.mark.parametrize("native", ["anthropic", "gemini"])
def test_native_call_type_rejects_non_null_endpoint(native: str) -> None:
    route = ModelRoute(native, "https://example.com", "TEST_API_KEY")  # type: ignore[arg-type]
    with pytest.raises(ModelConfigError, match="endpoint"):
        validate_route(route, provider="acme", allow_no_auth=False)


@pytest.mark.parametrize("native", ["anthropic", "gemini"])
def test_native_call_type_accepts_none_endpoint(native: str) -> None:
    route = ModelRoute(native, None, "TEST_API_KEY")  # type: ignore[arg-type]
    assert validate_route(route, provider="acme", allow_no_auth=False) is route


# ---------- error messages name provider + rule ----------

def test_error_messages_name_provider_and_rule() -> None:
    with pytest.raises(ModelConfigError) as excinfo:
        validate_route(ModelRoute("telepathy", None, "K"), provider="acme", allow_no_auth=False)  # type: ignore[arg-type]
    msg = str(excinfo.value)
    assert "acme" in msg
    assert "api_call_type" in msg

    with pytest.raises(ModelConfigError) as excinfo:
        validate_route(ModelRoute("openai_compat", None, None), provider="acme", allow_no_auth=False)
    msg = str(excinfo.value)
    assert "acme" in msg
    assert "api_key_env" in msg
