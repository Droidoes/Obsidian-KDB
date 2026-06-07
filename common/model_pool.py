"""model_pool — user-owned model registry loaded from common/models.json.

The JSON is DATA (pool + per-model knobs + curation ledger); this module is
the LOOKUP layer (alias -> ModelSpec, dropped-guard).
call_model.py (the engine) is untouched and still takes explicit provider+model.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache

_POOL_PATH = Path(__file__).with_name("models.json")
WORDS_TO_TOKENS = 1.3  # deliberate over-estimate; no tokenizer dependency


class PoolError(ValueError):
    """Unknown id, or selection of a dropped (documented-rejected) model."""


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


def resolve(model_id: str) -> ModelSpec:
    """alias id -> ModelSpec. Raises PoolError on unknown or dropped id."""
    by_id = {e["id"]: e for e in load_pool()}
    entry = by_id.get(model_id)
    if entry is None:
        avail = ", ".join(sorted(e["id"] for e in load_pool() if not e.get("dropped")))
        raise PoolError(f"Unknown model id {model_id!r}. Available: {avail}")
    if entry.get("dropped"):
        reason = entry.get("dropped_reason", "(no reason recorded)")
        raise PoolError(f"Model {model_id!r} is dropped: {reason}")
    return ModelSpec(
        id=entry["id"],
        provider=entry["provider"],
        model=entry["model"],
        ctx_window=entry.get("ctx_window"),
        max_output_tokens=entry.get("max_output_tokens"),
        use_completion_tokens=entry.get("use_completion_tokens", False),
        extra_body=entry.get("extra_body"),
        price_in=entry.get("price_in", 0.0),
        price_out=entry.get("price_out", 0.0),
    )
