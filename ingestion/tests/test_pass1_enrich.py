import hashlib
import json
import os
import pytest
from pathlib import Path

from ingestion.enrich import enrich as enrich_mod
from ingestion.enrich import pass1_caller as caller_mod
from ingestion.enrich.enrich import enrich_one
from ingestion.enrich.pass1_caller import Pass1CallResult


def _signal_parsed(model: str = "m") -> dict:
    return {
        "kdb_signal": "signal",
        "domain": "value-investing", "source_type": "paper", "author": "T",
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


def test_enrich_sidecar_cost_usd_from_aggregated_tokens(tmp_path, monkeypatch):
    # Task #110: the success-path sidecar bills aggregated tokens (#108) at
    # pool pricing: price_in/1e6*total_in + price_out/1e6*total_out.
    src = tmp_path / "s.md"
    src.write_text("# Heading\n\nA note about value investing.\n", encoding="utf-8")
    runs = tmp_path / "ingest_runs"

    def fake_call_pass1(*, source_text, source_path, provider, model):
        return Pass1CallResult(
            parsed=_signal_parsed(model), raw_response_text="{}",
            request_prompt="prompt", request_model=model, request_provider=provider,
            input_tokens=10, output_tokens=5, latency_ms=1, attempts=2,
            total_input_tokens=30, total_output_tokens=12,
        )
    monkeypatch.setattr(enrich_mod, "call_pass1", fake_call_pass1)

    price_in, price_out = 2.0, 8.0
    res = enrich_one(source_path=src, source_id="s.md", runs_root=runs,
                     run_id="r1", provider="p", model="m",
                     price_in=price_in, price_out=price_out)

    expected = price_in / 1e6 * 30 + price_out / 1e6 * 12
    data = json.loads(Path(res.sidecar_path).read_text(encoding="utf-8"))
    assert data["cost_usd"] == pytest.approx(expected)


def test_enrich_pipeline_force_noise_param_overrides(tmp_path, monkeypatch):
    # Task #91: the orchestrator threads the pipeline's force_noise globs; a
    # signal envelope under Daily Notes/* must be deterministically routed noise.
    src = tmp_path / "daily.md"
    src.write_text("# Standup\n\nNotes for today.\n", encoding="utf-8")
    runs = tmp_path / "ingest_runs"

    def fake_call_pass1(*, source_text, source_path, provider, model):
        return Pass1CallResult(
            parsed=_signal_parsed(model), raw_response_text="{}",
            request_prompt="p", request_model=model, request_provider=provider,
            input_tokens=1, output_tokens=1, latency_ms=1, attempts=1)
    monkeypatch.setattr(enrich_mod, "call_pass1", fake_call_pass1)

    res = enrich_one(source_path=src, source_id="Daily Notes/daily.md",
                     runs_root=runs, run_id="r1", provider="p", model="m",
                     force_noise=["Daily Notes/*"])

    assert res.parsed_envelope["kdb_signal"] == "noise"
    assert res.parsed_envelope["override"]["rule"] == "force_noise"
    assert res.parsed_envelope["override"]["match"] == "Daily Notes/*"


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


def test_enrich_failed_sidecar_preserves_last_raw_response(tmp_path, monkeypatch):
    src = tmp_path / "bad.md"
    src.write_text("# Bad\n\nA note.\n", encoding="utf-8")
    runs_root = tmp_path / "ingest_runs"

    monkeypatch.setattr(
        caller_mod,
        "call_model",
        lambda req: caller_mod.ModelResponse(
            text="{not valid json",
            input_tokens=7,
            output_tokens=3,
            latency_ms=11,
            model="m",
            provider="p",
        ),
    )

    result = enrich_one(
        source_path=src, source_id="bad.md", runs_root=runs_root,
        run_id="r1", provider="p", model="m",
    )

    sidecar = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
    assert result.outcome == "enrich_failed"
    assert result.raw_response_available is True
    assert sidecar["raw_response"]["body"] == "{not valid json"
    assert sidecar["raw_response"]["input_tokens"] == 7
    assert sidecar["request"]["prompt"] != "<see error>"
