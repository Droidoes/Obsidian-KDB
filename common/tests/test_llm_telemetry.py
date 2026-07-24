"""Tests for common.llm_telemetry — per-call cost_usd diagnostic.

Task 2.1 of #110: restore the per-call cost diagnostic on RespStatsRecord,
computed from pool pricing (price_in/price_out, USD per 1,000,000 tokens)
× AGGREGATED tokens (every retry attempt is billed, not just the final one).

Cost was previously derived by a now-deleted benchmark scorer; nothing
computes it today. This test pins the new in-record derivation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

import common.llm_telemetry as resp_stats_writer
from common.call_model import ModelResponse
from common.run_context import RunContext


@dataclass
class _FakePrompt:
    """Duck-typed BuiltPrompt stand-in. build_resp_stats only reads .system/.user."""
    system: str
    user: str


def _ctx(tmp_path: Path) -> RunContext:
    return RunContext.new(dry_run=False, vault_root=tmp_path)


def _model_response(*, input_tokens: int = 10, output_tokens: int = 10) -> ModelResponse:
    """Final-attempt response with deliberately SMALL token counts, so that a
    (wrong) per-call billing would diverge sharply from the aggregated total."""
    return ModelResponse(
        text="{}",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=10,
        model="deepseek-v4-flash",
        provider="deepseek",
        attempts=1,
    )


def test_cost_usd_uses_aggregated_tokens(tmp_path: Path) -> None:
    """cost = price_in/1e6 * agg_input + price_out/1e6 * agg_output.

    price_in=0.14, price_out=0.28 per 1M; aggregated 1,000,000 in / 500,000 out.
    Final-attempt model_response carries only 10/10 tokens — if cost were billed
    from per-call tokens it would be ~3e-6, not 0.28, so this discriminates.
    """
    ctx = _ctx(tmp_path)
    rec = resp_stats_writer.build_resp_stats(
        ctx=ctx,
        source_id="KDB/raw/foo.md",
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text="{}",
        model_response=_model_response(input_tokens=10, output_tokens=10),
        extract_ok=True,
        parse_ok=True,
        parsed_json={},
        schema_ok=True,
        schema_errors=[],
        semantic_ok=True,
        semantic_errors=[],
        total_input_tokens=1_000_000,
        total_output_tokens=500_000,
        price_in=0.14,
        price_out=0.28,
    )
    assert rec.cost_usd == pytest.approx(0.14 + 0.14)  # 0.14*1.0 + 0.28*0.5


def test_cost_usd_defaults_zero_when_unpriced(tmp_path: Path) -> None:
    """No price kwargs -> cost_usd defaults to 0.0 (unpriced run)."""
    ctx = _ctx(tmp_path)
    rec = resp_stats_writer.build_resp_stats(
        ctx=ctx,
        source_id="KDB/raw/foo.md",
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text="{}",
        model_response=_model_response(),
        extract_ok=True,
        parse_ok=True,
        parsed_json={},
        schema_ok=True,
        schema_errors=[],
        semantic_ok=True,
        semantic_errors=[],
        total_input_tokens=1_000_000,
        total_output_tokens=500_000,
    )
    assert rec.cost_usd == 0.0


def test_build_resp_stats_boundary_fields_land(tmp_path: Path) -> None:
    """#114 recovery telemetry: the three boundary kwargs flow through to
    the returned record."""
    ctx = _ctx(tmp_path)
    rec = resp_stats_writer.build_resp_stats(
        ctx=ctx,
        source_id="KDB/raw/foo.md",
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text="{}",
        model_response=_model_response(),
        extract_ok=True,
        parse_ok=True,
        parsed_json={},
        schema_ok=True,
        schema_errors=[],
        semantic_ok=True,
        semantic_errors=[],
        boundary_recovered=True,
        prefix_discarded_chars=2,
        tail_discarded_chars=20,
    )
    assert rec.boundary_recovered is True
    assert rec.prefix_discarded_chars == 2
    assert rec.tail_discarded_chars == 20


def test_build_resp_stats_normalization_fields_land(tmp_path: Path) -> None:
    """#119 bridge telemetry: the four normalization kwargs flow through to
    the returned record (additive/optional — defaults stay None)."""
    ctx = _ctx(tmp_path)
    decisions = [{"rule": "slug_form_coercion", "authority": "form-rule",
                  "location": "pages[1].slug", "raw_type": "string",
                  "raw_value": "Foo--Bar", "raw_preview": None,
                  "raw_sha256": None, "canonical_value": "foo-bar"}]
    rec = resp_stats_writer.build_resp_stats(
        ctx=ctx,
        source_id="KDB/raw/foo.md",
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text="{}",
        model_response=_model_response(),
        extract_ok=True,
        parse_ok=True,
        parsed_json={},
        schema_ok=True,
        schema_errors=[],
        semantic_ok=True,
        semantic_errors=[],
        normalization_decisions=decisions,
        normalization_decision_count=63,
        normalization_decisions_overflow_sha256="f" * 64,
        summary_identity_derived=True,
    )
    assert rec.normalization_decisions == decisions
    assert rec.normalization_decision_count == 63
    assert rec.normalization_decisions_overflow_sha256 == "f" * 64
    assert rec.summary_identity_derived is True

    rec_defaults = resp_stats_writer.build_resp_stats(
        ctx=ctx,
        source_id="KDB/raw/foo.md",
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text="{}",
        model_response=_model_response(),
        extract_ok=True,
        parse_ok=True,
        parsed_json={},
        schema_ok=True,
        schema_errors=[],
        semantic_ok=True,
        semantic_errors=[],
    )
    assert rec_defaults.normalization_decisions is None
    assert rec_defaults.normalization_decision_count is None
    assert rec_defaults.normalization_decisions_overflow_sha256 is None
    assert rec_defaults.summary_identity_derived is None
