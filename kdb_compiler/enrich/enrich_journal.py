# kdb_compiler/enrich/enrich_journal.py
"""Pass-1 run journal (Task #89 §5.4). Mirrors kdb_compile journal pattern."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class IngestRunJournal:
    run_id: str
    schema_version: str = "1.0"
    event_type: str = "ingest"
    sources_processed: int = 0
    by_outcome: dict[str, int] = field(default_factory=lambda: {
        "enriched": 0, "enriched_force_overridden": 0,
        "enrich_skipped": 0, "enrich_failed": 0,
    })
    prompt_version: str = ""
    model: str = ""
    force_signal_globs: list[str] = field(default_factory=list)
    force_noise_globs: list[str] = field(default_factory=list)
    timestamp: str = ""  # local ISO with offset
    duration_seconds: float = 0.0


def write_journal(runs_root: Path, journal: IngestRunJournal) -> Path:
    run_dir = runs_root / journal.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / "journal.json"
    out_path.write_text(json.dumps(asdict(journal), indent=2),
                        encoding="utf-8")
    return out_path
