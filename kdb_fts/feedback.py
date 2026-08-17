"""feedback — Joseph's immutable event log (D13/D18): the irreplaceable asset.

One JSONL file: <state_root>/feedback/events.jsonl. Append = read + atomic
rewrite via common.atomic_io (crash-safe, write-guard-clean; fine at
Phase-1 scale — thousands of events, low MB). There is deliberately NO
update or delete path. The SQLite mirror table arrives with the ranker
that consumes it (Phase 3; plan deviation 2).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from common.atomic_io import atomic_write_text

ACTIONS = frozenset({
    "strong", "interesting", "weak", "noise",          # article buckets ≙ 3/2/1/0
    "accept", "reject",                                 # ideas (D21)
    "helpful", "not-helpful",                           # lessons (D21)
    "save", "skip", "wrong-extraction", "promote-to-extract",
})
TARGET_TYPES = frozenset({"article", "idea", "lesson", "author"})

_EVENTS_NAME = "events.jsonl"


def _events_path(root: Path) -> Path:
    return Path(root) / "feedback" / _EVENTS_NAME


def append_event(root: Path, *, action: str, target_type: str, target_id: str,
                 reason_text: str | None = None,
                 reason_tags: list[str] | None = None,
                 ranker_version: str | None = None,
                 score_shown: float | None = None,
                 position_shown: int | None = None,
                 batch_id: str | None = None,
                 exploration: bool = False) -> dict:
    """Validate + stamp + append one immutable event. Returns the event."""
    if action not in ACTIONS:
        raise ValueError(f"unknown feedback action {action!r} (allowed: {sorted(ACTIONS)})")
    if target_type not in TARGET_TYPES:
        raise ValueError(f"unknown target_type {target_type!r}")
    event = {
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "reason_text": reason_text,
        "reason_tags": reason_tags,
        "ranker_version": ranker_version,
        "score_shown": score_shown,
        "position_shown": position_shown,
        "batch_id": batch_id,
        "exploration": bool(exploration),
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    path = _events_path(root)
    prior = path.read_text(encoding="utf-8") if path.exists() else ""
    atomic_write_text(path, prior + json.dumps(event, sort_keys=True) + "\n")
    return event


def load_events(root: Path, *, batch_id: str | None = None) -> list[dict]:
    path = _events_path(root)
    if not path.exists():
        return []
    events = [json.loads(line) for line in
              path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if batch_id is not None:
        events = [e for e in events if e.get("batch_id") == batch_id]
    return events
