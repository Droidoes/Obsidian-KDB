"""model_pool — user-owned model registry loaded from common/models.json.

The JSON is DATA (pool + per-model knobs + curation ledger); this module is
the LOOKUP layer (alias -> ModelSpec) plus token-estimate helpers for the
context-overrun pre-flight guard. Since Task #121 each entry also declares its
routing (api_call_type / endpoint / api_key_env): load_pool validates the
WHOLE pool once at materialization (Gate 1 — a malformed entry fails the pool
at first touch, D4) and every ModelSpec carries the pre-validated ModelRoute
that call_model dispatches on.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache

from common.model_route import (
    ModelConfigError,
    ModelRoute,
    validate_provider_identity,
    validate_route,
)

_POOL_PATH = Path(__file__).with_name("models.json")
WORDS_TO_TOKENS = 1.3  # deliberate over-estimate; no tokenizer dependency

# Provider -> the extra_body param that DISABLES thinking. ONLY verified providers
# go here — never guess a param (it would fire on a paid call). Unmapped providers
# are a no-op: anthropic/ollama (thinking off by default / no thinking mode), and
# gemini/openai/xai (TODO: verify their disable param before adding).
_THINKING_DISABLE_EXTRA_BODY = {
    "alibaba": {"enable_thinking": False},
    "deepseek": {"thinking": {"type": "disabled"}},
    # z.ai GLM: `thinking.type` enabled|disabled (default enabled) — verified
    # against docs.z.ai GLM-5-Turbo guide (same shape as deepseek's param).
    "zai": {"thinking": {"type": "disabled"}},
}


class PoolError(ValueError):
    """Base: unknown id or invalid pool entry."""


class UnknownModelError(PoolError):
    """Model id not found in the pool."""


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    model: str
    # The pre-validated routing declaration (Gate 1 at load_pool). Stored
    # canonical — Gate 1 rejects non-canonical providers, so this is the one
    # identical string routing/lookup/echo/telemetry all see.
    route: ModelRoute
    ctx_window: int | None = None
    max_output_tokens: int | None = None
    use_completion_tokens: bool = False
    extra_body: dict | None = None
    # `temperature=None` OMITS the temperature kwarg on the call (the API applies
    # its own default), set via an explicit JSON `null` for reasoning-family
    # models like gpt-5.4-mini that 400 on any non-default temperature. An absent
    # key resolves to 0.0 (deterministic default for every other model).
    temperature: float | None = 0.0
    price_in: float = 0.0
    price_out: float = 0.0


def _gate1_validate_entry(entry: dict) -> None:
    """Gate 1 (#121): validate ONE entry's routing declaration at pool load.
    Order: provider identity → required route fields present → build ModelRoute
    → validate_route (no-auth never pool-declared). Any failure raises PoolError
    naming the model id + cause; malformed JSON types are wrapped the same way
    (validate_route never leaks a raw TypeError)."""
    model_id = entry.get("id", "<missing id>")
    try:
        provider = validate_provider_identity(entry.get("provider"))
    except ModelConfigError as e:
        raise PoolError(f"Model {model_id!r}: {e}") from e
    # Three-state endpoint (D4): the KEY must be present — absent → PoolError;
    # explicit null → endpoint=None (SDK-built-in URL); string → override.
    for field_name in ("api_call_type", "endpoint", "api_key_env"):
        if field_name not in entry:
            raise PoolError(
                f"Model {model_id!r}: missing required route field {field_name!r}"
            )
    try:
        route = ModelRoute(entry["api_call_type"], entry["endpoint"], entry["api_key_env"])
        validate_route(route, provider=provider, allow_no_auth=False)
    except ModelConfigError as e:
        raise PoolError(f"Model {model_id!r}: {e}") from e


@lru_cache(maxsize=1)
def load_pool() -> list[dict]:
    """Load the active pool from models.json, validating EVERY entry's route
    declaration once at materialization (Gate 1) — a malformed entry, even one
    never selected, fails the whole pool with PoolError naming the model id.
    lru_cache caches successful loads only (exceptions re-run); tests that swap
    _POOL_PATH must cache_clear(). Dropped entries live in models_dropped.json
    (a human archive the code never reads)."""
    entries = json.loads(_POOL_PATH.read_text(encoding="utf-8"))
    for entry in entries:
        _gate1_validate_entry(entry)
    return entries


def resolve_models_json(model_id: str) -> ModelSpec:
    """alias id -> ModelSpec. Raises UnknownModelError for an id not in the
    active pool (dropped ids were archived out of models.json)."""
    by_id = {e["id"]: e for e in load_pool()}
    entry = by_id.get(model_id)
    if entry is None:
        avail = ", ".join(sorted(e["id"] for e in load_pool()))
        raise UnknownModelError(f"Unknown model id {model_id!r}. Available: {avail}")

    # Translate the semantic `thinking` field to the right per-provider disable
    # param — but ONLY for providers with a verified mapping (never guess a param,
    # it would fire on a paid call). Explicit extra_body keys override.
    thinking = entry.get("thinking", "disabled")
    if thinking not in ("disabled", "enabled"):
        raise PoolError(f"Model {model_id!r}: invalid thinking={thinking!r} (expected 'disabled' or 'enabled')")
    disable_param = (_THINKING_DISABLE_EXTRA_BODY.get(entry["provider"], {})
                     if thinking == "disabled" else {})
    raw_extra = entry.get("extra_body") or {}
    merged = {**disable_param, **raw_extra}  # explicit extra_body wins on key conflict
    extra_body = merged or None

    return ModelSpec(
        id=entry["id"],
        provider=entry["provider"],
        model=entry["model"],
        # Pre-validated at Gate 1 (load_pool) — read verbatim, never re-validated.
        route=ModelRoute(entry["api_call_type"], entry["endpoint"], entry["api_key_env"]),
        ctx_window=entry.get("ctx_window"),
        max_output_tokens=entry.get("max_output_tokens"),
        use_completion_tokens=entry.get("use_completion_tokens", False),
        extra_body=extra_body,
        # Explicit JSON `null` → None (omit temperature); absent key → 0.0.
        temperature=entry.get("temperature", 0.0),
        price_in=entry.get("price_in", 0.0),
        price_out=entry.get("price_out", 0.0),
    )


def estimate_prompt_tokens(system: str | None, user: str) -> int:
    """Rough token estimate for a prompt, words × WORDS_TO_TOKENS (deliberate
    over-estimate; no tokenizer dependency). `system + "\n\n" + user` mirrors
    how prompt_hash is built in llm_telemetry."""
    text = (system or "") + "\n\n" + user
    return round(len(text.split()) * WORDS_TO_TOKENS)


def fits_context(*, est_input: int, requested_output: int, ctx_window: int) -> bool:
    """The call must fit input AND the room reserved for output: a deliberate
    over-estimate erring toward catching overruns early."""
    return est_input + requested_output <= ctx_window
