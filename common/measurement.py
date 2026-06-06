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
