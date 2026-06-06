"""
Measurement dataclasses for the KDB benchmark pipeline (B1 design).

These are *projections* over existing telemetry (Pass-2 RespStatsRecord,
Pass-1 sidecar) — not a new persistent store.  The KPI layer consumes
these structures to compute per-run scoring metrics.

`common` is a leaf package: only stdlib imports are allowed here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PassCallMeasurement:
    """Logical projection of one LLM pass-call's telemetry for KPI scoring."""

    run_id: str
    source_id: str
    pass_: str                  # "pass1" | "pass2" (trailing _ avoids keyword clash)
    provider: str
    model: str
    prompt_version: str
    final_status: str
    attempts: int
    syntax_repaired: bool
    slug_coerced: bool
    token_overrun: bool
    total_input_tokens: int
    total_output_tokens: int
    total_latency_ms: int
    call_count: int
    final_attempt_index: int
    source_words: int
    parse_ok: bool
    schema_ok: bool
    semantic_ok: bool | None

    @classmethod
    def from_pass2(cls, rec: dict) -> "PassCallMeasurement":
        """Project a RespStatsRecord dict (from to_dict() or persisted JSON)
        into a PassCallMeasurement.

        RespStatsRecord has no prompt_version field; prompt_version is set to "".

        Back-compat: records persisted before Task #109 (missing total_input_tokens,
        total_output_tokens, total_latency_ms, call_count, final_attempt_index) fall
        back to the single-attempt per-call values so older runs still project cleanly.
        """
        return cls(
            run_id=rec["run_id"],
            source_id=rec["source_id"],
            pass_="pass2",
            provider=rec["provider"],
            model=rec["model"],
            # RespStatsRecord has no prompt_version; closest field is prompt_hash (a
            # hash, not a version string).  Emit "" so callers can fill in from
            # run-level metadata if needed.
            prompt_version="",
            final_status=rec.get("final_status") or "",
            attempts=rec["attempts"],
            syntax_repaired=rec.get("syntax_repaired", False),
            slug_coerced=rec.get("slug_coerced", False),
            token_overrun=rec.get("token_overrun", False),
            # Aggregate totals — new in #109.  Fall back to single-attempt values
            # for records written before these fields existed.
            total_input_tokens=rec.get("total_input_tokens", rec.get("input_tokens", 0)),
            total_output_tokens=rec.get("total_output_tokens", rec.get("output_tokens", 0)),
            total_latency_ms=rec.get("total_latency_ms", rec.get("latency_ms", 0)),
            call_count=rec.get("call_count", 1),
            final_attempt_index=rec.get("final_attempt_index", 1),
            source_words=rec.get("source_words", 0),
            parse_ok=rec.get("parse_ok", False),
            schema_ok=rec.get("schema_ok", False),
            semantic_ok=rec.get("semantic_ok"),
        )


@dataclass(frozen=True)
class RunMeasurementHeader:
    """Per-run metadata projection consumed by the KPI scoring layer."""

    run_id: str
    corpus_fingerprint: str
    pass1_prompt_version: str
    pass2_prompt_version: str
    scanned: int
    to_compile: int
    signal: int
    noise: int
    p1_attempted: int
    p2_attempted: int
