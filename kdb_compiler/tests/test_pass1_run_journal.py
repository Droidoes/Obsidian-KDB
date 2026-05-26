from pathlib import Path
from kdb_compiler.ingestion.run_journal import IngestRunJournal, write_journal


def test_write_journal_creates_journal_json_at_expected_path(tmp_path):
    runs_root = tmp_path / "ingest_runs"
    j = IngestRunJournal(
        run_id="ingest-2026-05-26T20-30-00",
        prompt_version="1.0.0",
        model="deepseek-v4-flash",
        sources_processed=5,
        by_outcome={"enriched": 4, "enriched_force_overridden": 0,
                    "enrich_skipped": 1, "enrich_failed": 0},
        force_signal_globs=[],
        force_noise_globs=["Daily Notes/**", "Projects/**"],
        timestamp="2026-05-26T20:30:00-04:00",
        duration_seconds=12.5,
    )
    written = write_journal(runs_root, j)
    expected = runs_root / "ingest-2026-05-26T20-30-00" / "journal.json"
    assert written == expected

    import json
    data = json.loads(written.read_text(encoding="utf-8"))
    assert data["run_id"] == "ingest-2026-05-26T20-30-00"
    assert data["schema_version"] == "1.0"
    assert data["event_type"] == "ingest"
    assert data["sources_processed"] == 5
    assert data["by_outcome"]["enriched"] == 4
    assert data["model"] == "deepseek-v4-flash"
    assert "Daily Notes/**" in data["force_noise_globs"]
    assert data["duration_seconds"] == 12.5
