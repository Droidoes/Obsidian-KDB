"""journal — append-only feeder conversion journal (#143 D4).

One JSONL line per processed message at
`<vault>/KDB/state/feeders/gmail.jsonl`. Small file, single process (D22):
read-all + atomic rewrite on append. Audit + dedup-by-canonical-URL only —
this is not an ingestion ledger (the Gmail label is the processed-state).
"""
from __future__ import annotations

import json
from pathlib import Path

from common.atomic_io import atomic_write_text


def load_journal(path: Path | str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip()]


def append_journal(path: Path | str, record: dict) -> None:
    p = Path(path)
    prior = p.read_text(encoding="utf-8") if p.exists() else ""
    atomic_write_text(p, prior + json.dumps(record, ensure_ascii=False) + "\n")


def seen_message_ids(records: list[dict]) -> set[str]:
    return {r["message_id"] for r in records if "message_id" in r}


def seen_urls(records: list[dict]) -> dict[str, str]:
    """source_url -> filename for converted records (dedup-by-canonical-URL)."""
    return {r["source_url"]: r["filename"] for r in records
            if r.get("source_url") and r.get("filename")}
