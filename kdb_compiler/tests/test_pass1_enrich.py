import hashlib
import os
import pytest
from pathlib import Path

from kdb_compiler.ingestion import enrich as enrich_mod
from kdb_compiler.ingestion.enrich import enrich_one
from kdb_compiler.ingestion.pass1_caller import Pass1CallResult


def _signal_parsed(model: str = "m") -> dict:
    return {
        "kdb_signal": "signal",
        "domain": "value-investing", "source_type": "essay", "author": "T",
        "summary": "A summary.", "key_themes": ["a"],
        "entity_search_keys": ["value-investing"],
        "confidence": 0.9, "uncertainty_reason": None, "reject_reason": None,
        "prompt_version": "p1", "model": model, "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": "signal", "reject_reason_cleared": None},
        "other_reason": None,
    }


def test_enrich_returns_body_and_post_embed_hash(tmp_path, monkeypatch):
    # Task #91: enrich_one carries body + post-embed whole-file hash/mtime so the
    # orchestrator reuses them in-memory (no re-read) and stores a stable hash.
    src = tmp_path / "s.md"
    src.write_text("# Heading\n\nA note about value investing.\n", encoding="utf-8")
    runs = tmp_path / "ingest_runs"

    def fake_call_pass1(*, source_text, source_path, provider, model):
        return Pass1CallResult(
            parsed=_signal_parsed(model), raw_response_text="{}",
            request_prompt="prompt", request_model=model, request_provider=provider,
            input_tokens=10, output_tokens=5, latency_ms=1, attempts=1,
        )
    monkeypatch.setattr(enrich_mod, "call_pass1", fake_call_pass1)

    res = enrich_one(source_path=src, source_id="s.md", runs_root=runs,
                     run_id="r1", provider="p", model="m")

    assert res.outcome == "enriched"
    assert res.body and "value investing" in res.body
    on_disk = "sha256:" + hashlib.sha256(src.read_bytes()).hexdigest()
    assert res.post_embed_hash == on_disk          # whole-file hash AFTER embed
    assert res.post_embed_mtime == pytest.approx(src.stat().st_mtime)


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
