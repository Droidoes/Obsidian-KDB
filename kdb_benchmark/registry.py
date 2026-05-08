"""registry — load and shape-check the pinned model registry (models.json).

The registry is the list of LLM models the benchmark fans out to. Shape
mirrors the proven pattern from
`~/Droidoes/Code-projects/youtube-comment-chat/src/eval/models.json`:

    Required:
      id          — stable short label (used in filenames, scorecards, CLI)
      provider    — SDK route: anthropic | openai | gemini | ollama
      model       — provider-native API model string
      price_in    — USD per 1M input tokens; 0.0 for local
      price_out   — USD per 1M output tokens; 0.0 for local

    Optional (informational + behavior knobs):
      ctx_window           — int, context window in tokens
      max_output_tokens    — int, max output tokens the model supports
      use_completion_tokens — bool, true for GPT-5+ family that uses
                              `max_completion_tokens` instead of `max_tokens`
                              in OpenAI-compat API calls
      extra_body           — dict, passed to the SDK's `extra_body` (for
                              provider-specific knobs like `think: false`)

Optional fields default to None / False / None when absent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kdb_benchmark.paths import MODELS_JSON


@dataclass(frozen=True)
class ModelEntry:
    id: str                   # stable short label used in filenames / scorecards
    provider: str             # anthropic | openai | gemini | ollama
    model: str                # provider-native model ID
    price_in: float           # USD per 1M input tokens; 0.0 for local
    price_out: float          # USD per 1M output tokens; 0.0 for local
    ctx_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    use_completion_tokens: bool = False
    extra_body: Optional[dict] = None


def _coerce_price(raw: object, *, index: int, field: str) -> float:
    """Numeric ≥ 0, with int → float coercion. Reject bool, str, None, neg."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(
            f"models.json[{index}] field '{field}' must be a number, got {type(raw).__name__}"
        )
    value = float(raw)
    if value < 0:
        raise ValueError(
            f"models.json[{index}] field '{field}' must be non-negative, got {value}"
        )
    return value


def _coerce_optional_int(raw: object, *, index: int, field: str) -> Optional[int]:
    """Optional positive int. Missing → None. Reject bool, float, neg, zero."""
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise ValueError(
            f"models.json[{index}] field '{field}' must be a positive integer, got {raw!r}"
        )
    return raw


def load_registry(path: Path = MODELS_JSON) -> list[ModelEntry]:
    """Read models.json and return the list of entries.

    Validates required fields (id/provider/model strings; price_in/price_out
    non-negative numerics) and parses optional behavior knobs (ctx_window,
    max_output_tokens, use_completion_tokens, extra_body). Ids must be unique.
    """
    if not path.exists():
        raise FileNotFoundError(f"models registry not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"models.json must be a list, got {type(data).__name__}")

    entries: list[ModelEntry] = []
    seen_ids: set[str] = set()
    for i, raw in enumerate(data):
        if not isinstance(raw, dict):
            raise ValueError(f"models.json[{i}] must be an object")
        for field in ("id", "provider", "model"):
            if field not in raw or not isinstance(raw[field], str) or not raw[field]:
                raise ValueError(f"models.json[{i}] missing/empty string field '{field}'")
        for field in ("price_in", "price_out"):
            if field not in raw:
                raise ValueError(f"models.json[{i}] missing required field '{field}'")
        if raw["id"] in seen_ids:
            raise ValueError(f"models.json: duplicate id '{raw['id']}'")
        seen_ids.add(raw["id"])

        extra_body_raw = raw.get("extra_body")
        if extra_body_raw is not None and not isinstance(extra_body_raw, dict):
            raise ValueError(
                f"models.json[{i}] field 'extra_body' must be an object or omitted"
            )
        use_completion_tokens_raw = raw.get("use_completion_tokens", False)
        if not isinstance(use_completion_tokens_raw, bool):
            raise ValueError(
                f"models.json[{i}] field 'use_completion_tokens' must be a boolean"
            )

        entries.append(ModelEntry(
            id=raw["id"],
            provider=raw["provider"],
            model=raw["model"],
            price_in=_coerce_price(raw["price_in"], index=i, field="price_in"),
            price_out=_coerce_price(raw["price_out"], index=i, field="price_out"),
            ctx_window=_coerce_optional_int(
                raw.get("ctx_window"), index=i, field="ctx_window"
            ),
            max_output_tokens=_coerce_optional_int(
                raw.get("max_output_tokens"), index=i, field="max_output_tokens"
            ),
            use_completion_tokens=use_completion_tokens_raw,
            extra_body=extra_body_raw,
        ))

    return entries
