# ingestion/enrich/replay_archive.py
"""Pass-1 replay archive sidecar (Task #89 §5.3 + D-89-13).

One JSON sidecar per Pass-1 call (success or fail) at
<state_root>/runs/<run_id>/pass1/<encoded_source_id>.json.

Encoded source ID replaces `/` with `__` (Codex F-4 + Gemini F-3).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path


def encode_source_id(source_id: str) -> str:
    """Source IDs are vault-relative paths; encode `/` → `__` for flat
    sidecar lookup (per Task #89 §5.3)."""
    return source_id.replace("/", "__")


@dataclass
class SidecarPayload:
    source_id: str
    source_path: str
    source_content_hash: str
    request: dict
    raw_response: dict
    parsed_envelope: dict
    override: dict
    user_overrides_detected: list
    timestamp: str  # local ISO with offset per [[feedback_local_time_everywhere]]
    outcome: str  # "enriched" | "enriched_force_overridden" | "enrich_failed" | "enrich_skipped"
    # Task #110: per-call cost diagnostic =
    #   price_in/1e6 * total_input_tokens + price_out/1e6 * total_output_tokens.
    # Defaults to 0.0 for skipped/failed paths (no successful token usage to bill).
    cost_usd: float = 0.0


def write_sidecar(runs_root: Path, run_id: str, payload: SidecarPayload) -> Path:
    """Write the sidecar JSON. Returns the path written."""
    pass1_dir = runs_root / run_id / "pass1"
    pass1_dir.mkdir(parents=True, exist_ok=True)
    filename = encode_source_id(payload.source_id) + ".json"
    out_path = pass1_dir / filename
    out_path.write_text(json.dumps(asdict(payload), indent=2, ensure_ascii=False),
                        encoding="utf-8")
    return out_path
