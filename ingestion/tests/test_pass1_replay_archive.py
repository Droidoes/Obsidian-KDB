# ingestion/tests/test_pass1_replay_archive.py
import json
from pathlib import Path

from ingestion.enrich.replay_archive import (
    encode_source_id, write_sidecar, SidecarPayload,
)


def test_encode_source_id_replaces_slash_with_double_underscore():
    assert encode_source_id("Investing/Buffett-letter-2020.md") == "Investing__Buffett-letter-2020.md"
    assert encode_source_id("top-level-note.md") == "top-level-note.md"
    assert encode_source_id("a/b/c.md") == "a__b__c.md"


def test_write_sidecar_creates_json_at_expected_path(tmp_path):
    runs_root = tmp_path / "ingest_runs"
    payload = SidecarPayload(
        source_id="Notes/Quick-thoughts.md",
        source_path="/home/x/Obsidian/Notes/Quick-thoughts.md",
        source_content_hash="sha256:abc123",
        request={"prompt": "...", "model": "deepseek-v4-flash"},
        raw_response={"body": "{...}", "usage": {"in": 100, "out": 50}},
        parsed_envelope={"kdb_signal": "signal", "domain": "ai-ml"},
        override={"applied": None, "rule": None, "match": None,
                  "llm_original": "signal", "reject_reason_cleared": None},
        user_overrides_detected=[],
        timestamp="2026-05-26T20:30:00-04:00",
        outcome="enriched",
    )
    written = write_sidecar(runs_root, "ingest-2026-05-26", payload)
    expected = runs_root / "ingest-2026-05-26" / "Notes__Quick-thoughts.md.json"
    assert written == expected
    data = json.loads(written.read_text(encoding="utf-8"))
    assert data["source_id"] == "Notes/Quick-thoughts.md"
    assert data["outcome"] == "enriched"
    assert data["parsed_envelope"]["kdb_signal"] == "signal"


def test_sidecar_carries_cost_usd():
    # Task #110: per-call cost diagnostic threaded onto the Pass-1 sidecar.
    p = SidecarPayload(
        source_id="s", source_path="s.md", source_content_hash="h",
        request={}, raw_response={}, parsed_envelope={}, override={},
        user_overrides_detected=[], timestamp="2026-06-06T00:00:00-05:00",
        outcome="enriched", cost_usd=0.42,
    )
    from dataclasses import asdict
    assert asdict(p)["cost_usd"] == 0.42
