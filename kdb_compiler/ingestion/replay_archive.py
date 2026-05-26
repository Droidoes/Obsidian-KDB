# kdb_compiler/ingestion/replay_archive.py
"""Pass-1 replay archive sidecar (Task #89 §5.3 + D-89-13).

One JSON sidecar per Pass-1 call (success or fail) at
~/Obsidian/KDB/state/ingest_runs/<run_id>/<encoded_source_id>.json.

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


def write_sidecar(runs_root: Path, run_id: str, payload: SidecarPayload) -> Path:
    """Write the sidecar JSON. Returns the path written."""
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    filename = encode_source_id(payload.source_id) + ".json"
    out_path = run_dir / filename
    out_path.write_text(json.dumps(asdict(payload), indent=2, ensure_ascii=False),
                        encoding="utf-8")
    return out_path
