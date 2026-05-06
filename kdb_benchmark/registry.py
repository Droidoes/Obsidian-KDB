"""registry — load and shape-check the pinned model registry (models.json).

The registry is the list of LLM models the benchmark fans out to. Per Task #29
each entry now carries `price_in` / `price_out` (USD per 1M tokens). Both are
required and must be numeric ≥ 0; local/Ollama models use `0.0` for both.
Task #21 will flesh out further per-model knobs (context window, max output,
etc.) by porting the yt-comment-chat shape.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kdb_benchmark.paths import MODELS_JSON


@dataclass(frozen=True)
class ModelEntry:
    id: str          # stable short label used in filenames / scorecards
    provider: str    # anthropic | openai | gemini | ollama
    model: str       # provider-native model ID
    price_in: float  # USD per 1M input tokens; 0.0 for local
    price_out: float # USD per 1M output tokens; 0.0 for local


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


def load_registry(path: Path = MODELS_JSON) -> list[ModelEntry]:
    """Read models.json and return the list of entries.

    Validates: file exists, top-level is a list, each entry has the three
    required string fields (id/provider/model) plus price_in/price_out as
    non-negative numerics, and ids are unique.
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
        entries.append(ModelEntry(
            id=raw["id"],
            provider=raw["provider"],
            model=raw["model"],
            price_in=_coerce_price(raw["price_in"], index=i, field="price_in"),
            price_out=_coerce_price(raw["price_out"], index=i, field="price_out"),
        ))

    return entries
