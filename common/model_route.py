"""model_route — routing primitives for LLM calls (Task #121).

Neutral home in the LEAF package: imports nothing internal. A ModelRoute
declares HOW to reach a model — which transport (api_call_type, the only
closed value set), which endpoint override (None = the SDK's built-in URL),
and which env var NAMES the API key (resolved late at the call boundary,
never at import).

Two gates share these validators: Gate 1 (common/model_pool.py, P2) wraps
malformed pool JSON in PoolError naming the model id; Gate 2
(common/call_model.py) raises ModelConfigError before any SDK constructor
runs. Both name the provider + the violated rule — never secrets.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

ApiCallType = Literal["openai_compat", "anthropic", "gemini"]  # CLOSED — new type = one handler + one value
API_CALL_TYPES: frozenset[str] = frozenset(get_args(ApiCallType))

# Transports whose SDK builds its own URL — an endpoint override is meaningless there.
_NATIVE_CALL_TYPES: frozenset[str] = frozenset({"anthropic", "gemini"})


class ModelConfigError(ValueError):
    """Missing/incorrect provider config (moved from call_model; re-exported there for compat)."""


@dataclass(frozen=True)
class ModelRoute:
    api_call_type: ApiCallType
    endpoint: str | None      # None = SDK-built-in URL (meaningful for openai_compat)
    api_key_env: str | None   # env-var NAME; None only via the trusted ollama-local registry default


def validate_provider_identity(provider: object) -> str:
    """Provider must be a str, non-empty, AND ALREADY CANONICAL — leading/trailing
    whitespace is REJECTED (provider != provider.strip()), never silently normalized:
    routing, thinking-translation lookup, response echo, and telemetry must see ONE
    identical string. Returns the original valid string. Runs FIRST at both gates."""
    if not isinstance(provider, str):
        raise ModelConfigError(
            f"provider identity must be a str, got {type(provider).__name__}"
        )
    if not provider.strip():
        raise ModelConfigError("provider identity must be non-empty")
    if provider != provider.strip():
        raise ModelConfigError(
            f"provider identity {provider!r} is not canonical — "
            "leading/trailing whitespace is rejected, never normalized"
        )
    return provider


def validate_route(route: ModelRoute, *, provider: str, allow_no_auth: bool) -> ModelRoute:
    """The single route validator (Gate 2 core; Gate 1 wraps it).
    Raises ModelConfigError naming provider + the violated rule (never secrets).

    Checks run IN ORDER so a wrong runtime type surfaces as ModelConfigError —
    never a leaked TypeError/AttributeError (e.g. an unhashable api_call_type
    like a list would TypeError on the closed-set membership test if the str
    check did not run first).
    """
    # 1. route is a ModelRoute instance — anything else rejects.
    if not isinstance(route, ModelRoute):
        raise ModelConfigError(
            f"provider {provider!r}: route must be a ModelRoute, got {type(route).__name__}"
        )
    # 2. api_call_type is a str (BEFORE closed-set membership), then a known type.
    api_call_type = route.api_call_type
    if not isinstance(api_call_type, str):
        raise ModelConfigError(
            f"provider {provider!r}: api_call_type must be a str, "
            f"got {type(api_call_type).__name__}"
        )
    if api_call_type not in API_CALL_TYPES:
        raise ModelConfigError(
            f"provider {provider!r}: unknown api_call_type {api_call_type!r} "
            f"(expected one of {sorted(API_CALL_TYPES)})"
        )
    # 3. endpoint is None or a non-empty, non-padded str — malformed config must
    #    not survive to an SDK URL parser.
    endpoint = route.endpoint
    if endpoint is not None:
        if not isinstance(endpoint, str):
            raise ModelConfigError(
                f"provider {provider!r}: endpoint must be a str or None, "
                f"got {type(endpoint).__name__}"
            )
        if not endpoint.strip():
            raise ModelConfigError(f"provider {provider!r}: endpoint must be non-empty")
        if endpoint != endpoint.strip():
            raise ModelConfigError(
                f"provider {provider!r}: endpoint {endpoint!r} has leading/trailing whitespace"
            )
    # 4. api_key_env is None or a non-empty, non-padded str (it feeds os.getenv).
    api_key_env = route.api_key_env
    if api_key_env is not None:
        if not isinstance(api_key_env, str):
            raise ModelConfigError(
                f"provider {provider!r}: api_key_env must be a str or None, "
                f"got {type(api_key_env).__name__}"
            )
        if not api_key_env.strip():
            raise ModelConfigError(f"provider {provider!r}: api_key_env must be non-empty")
        if api_key_env != api_key_env.strip():
            raise ModelConfigError(
                f"provider {provider!r}: api_key_env {api_key_env!r} has leading/trailing whitespace"
            )
    # 5. Auth policy — the flag NEVER disables the type validation above.
    if not allow_no_auth and api_key_env is None:
        raise ModelConfigError(
            f"provider {provider!r}: api_key_env is required "
            "(no-auth is reserved for the ollama-local registry default)"
        )
    # 6. Native SDKs build their own URL — an endpoint override is meaningless.
    if api_call_type in _NATIVE_CALL_TYPES and endpoint is not None:
        raise ModelConfigError(
            f"provider {provider!r}: api_call_type {api_call_type!r} requires "
            "endpoint=None (native SDK builds its own URL)"
        )
    return route
