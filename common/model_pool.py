"""model_pool — user-owned model registry loaded from common/models.json.

The JSON is DATA (pool + per-model knobs + curation ledger); this module is
the LOOKUP layer (alias -> ModelSpec, dropped-guard) plus token-estimate
helpers for the context-overrun pre-flight guard.
call_model.py (the engine) is untouched and still takes explicit provider+model.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache

_POOL_PATH = Path(__file__).with_name("models.json")
WORDS_TO_TOKENS = 1.3  # deliberate over-estimate; no tokenizer dependency

# Provider -> the extra_body param that DISABLES thinking. ONLY verified providers
# go here — never guess a param (it would fire on a paid call). Unmapped providers
# are a no-op: anthropic/ollama (thinking off by default / no thinking mode), and
# gemini/openai/xai (TODO: verify their disable param before adding).
_THINKING_DISABLE_EXTRA_BODY = {
    "alibaba": {"enable_thinking": False},
    "deepseek": {"thinking": {"type": "disabled"}},
}


class PoolError(ValueError):
    """Base: unknown id, or selection of a dropped (documented-rejected) model."""


class UnknownModelError(PoolError):
    """Model id not found in the pool."""


class DroppedModelError(PoolError):
    """Model id is in the pool but marked dropped (documented-rejected)."""


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    model: str
    ctx_window: int | None = None
    max_output_tokens: int | None = None
    use_completion_tokens: bool = False
    extra_body: dict | None = None
    price_in: float = 0.0
    price_out: float = 0.0


@lru_cache(maxsize=1)
def load_pool() -> list[dict]:
    """Load the raw pool (all entries, including dropped)."""
    return json.loads(_POOL_PATH.read_text(encoding="utf-8"))


def resolve_models_json(model_id: str) -> ModelSpec:
    """alias id -> ModelSpec. Raises PoolError on unknown or dropped id."""
    by_id = {e["id"]: e for e in load_pool()}
    entry = by_id.get(model_id)
    if entry is None:
        avail = ", ".join(sorted(e["id"] for e in load_pool() if not e.get("dropped")))
        raise UnknownModelError(f"Unknown model id {model_id!r}. Available: {avail}")
    if entry.get("dropped"):
        reason = entry.get("dropped_reason", "(no reason recorded)")
        raise DroppedModelError(f"Model {model_id!r} is dropped: {reason}")

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
        ctx_window=entry.get("ctx_window"),
        max_output_tokens=entry.get("max_output_tokens"),
        use_completion_tokens=entry.get("use_completion_tokens", False),
        extra_body=extra_body,
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
