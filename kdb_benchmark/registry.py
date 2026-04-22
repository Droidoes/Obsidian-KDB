"""registry — load and shape-check the pinned model registry (models.json).

The registry is the list of LLM models the benchmark fans out to. Shape
is intentionally minimal at #18 (id + provider + model); Task #21 fleshes
out per-model knobs (context window, max output, pricing, etc.) by porting
the yt-comment-chat shape.
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


def load_registry(path: Path = MODELS_JSON) -> list[ModelEntry]:
    """Read models.json and return the list of entries.

    Validates: file exists, top-level is a list, each entry has the three
    required string fields, ids are unique.
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
        if raw["id"] in seen_ids:
            raise ValueError(f"models.json: duplicate id '{raw['id']}'")
        seen_ids.add(raw["id"])
        entries.append(ModelEntry(id=raw["id"], provider=raw["provider"], model=raw["model"]))

    return entries
