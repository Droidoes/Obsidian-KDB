import os
import pytest
from pathlib import Path

from kdb_compiler.ingestion.enrich import enrich_one


@pytest.mark.live
@pytest.mark.skipif(not os.getenv("DEEPSEEK_API_KEY"),
                     reason="No DEEPSEEK_API_KEY in env")
def test_enrich_one_smoke(tmp_path):
    src = tmp_path / "sample.md"
    src.write_text(
        "# On Margin of Safety\n\n"
        "Warren Buffett's investment philosophy centers on margin of safety:\n"
        "buying at a substantial discount to intrinsic value.\n",
        encoding="utf-8",
    )
    runs_root = tmp_path / "ingest_runs"
    result = enrich_one(
        source_path=src, source_id="sample.md",
        runs_root=runs_root, run_id="test-run",
        provider="deepseek", model="deepseek-v4-flash",
    )
    assert result.outcome == "enriched"
    out_text = src.read_text(encoding="utf-8")
    assert out_text.startswith("---\n")
    assert "kdb_signal:" in out_text
    assert result.sidecar_path.exists()


def test_enrich_one_empty_source_skipped(tmp_path):
    src = tmp_path / "empty.md"
    src.write_text("", encoding="utf-8")
    runs_root = tmp_path / "ingest_runs"
    result = enrich_one(
        source_path=src, source_id="empty.md",
        runs_root=runs_root, run_id="test-run",
        provider="deepseek", model="deepseek-v4-flash",
    )
    assert result.outcome == "enrich_skipped"
    assert result.parsed_envelope["kdb_signal"] == "noise"
