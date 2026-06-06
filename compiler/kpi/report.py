"""compiler.kpi.report — render a single-run measurements payload as Markdown.

`render_report(payload)` turns the `measurements.json` dict (header + processing
+ graph, the shape assembled by orchestrator.emit_kpis) into a human-readable
Markdown report. Written alongside `measurements.json` at `--emit-kpis` time so
each per-run dir is self-describing without running `kdb-benchmark score`.

Pure function, no I/O. None values render as `—` (don't fabricate zeros).
"""
from __future__ import annotations

from typing import Any

from compiler.kpi.score import KPI_LOWER_IS_BETTER

# Derive the ↑ set from the single source of truth in score.py — adding a new
# scored ↑ KPI there automatically arrows it here (no second table to drift).
_HIGHER_IS_BETTER = {k for k, lower in KPI_LOWER_IS_BETTER.items() if not lower}


def _fmt(v: Any) -> str:
    """Format a KPI value for the table. None → em-dash; floats to 4 sig figs."""
    if v is None:
        return "—"
    if isinstance(v, float):
        if v == 0.0:
            return "0.0"
        # Large per-1M-token rates read better without scientific notation.
        if abs(v) >= 1000:
            return f"{v:,.1f}"
        return f"{v:.4g}"
    return str(v)


def _arrow(kpi: str) -> str:
    """Direction marker for a scored KPI."""
    return "↑" if kpi in _HIGHER_IS_BETTER else "↓"


def _kv_table(rows: dict[str, Any], *, with_direction: bool = False) -> list[str]:
    """Render a dict as a two-column Markdown table (KPI | value)."""
    if not rows:
        return ["_(none)_", ""]
    header = "| KPI | value |"
    sep = "|---|---|"
    lines = [header, sep]
    for k, v in rows.items():
        label = f"{k} {_arrow(k)}" if with_direction else k
        lines.append(f"| {label} | {_fmt(v)} |")
    lines.append("")
    return lines


def render_report(payload: dict) -> str:
    """Render a measurements payload (header + processing + graph) as Markdown."""
    header = payload.get("header", {}) or {}
    processing = payload.get("processing", {}) or {}
    graph = payload.get("graph", {}) or {}

    lines: list[str] = []
    lines.append(f"# Benchmark run — {header.get('model', '?')}")
    lines.append("")
    lines.append(
        f"- **model:** `{header.get('model', '?')}`  ·  "
        f"**provider:** `{header.get('provider', '?')}`"
    )
    lines.append(f"- **run_id:** `{header.get('run_id', '?')}`")
    lines.append(f"- **corpus_fingerprint:** `{header.get('corpus_fingerprint', '?')}`")
    lines.append(
        f"- **prompt versions:** pass1 `{header.get('pass1_prompt_version', '')}` · "
        f"pass2 `{header.get('pass2_prompt_version', '')}`"
    )
    lines.append(
        f"- **corpus:** {header.get('scanned', '?')} scanned · "
        f"{header.get('signal', '?')} signal · {header.get('noise', '?')} noise · "
        f"p1 {header.get('p1_attempted', '?')} / p2 {header.get('p2_attempted', '?')} attempted"
    )
    lines.append("")

    lines.append("## Processing")
    lines.append("")
    lines.append("**Scored**")
    lines.extend(_kv_table(processing.get("scored", {}) or {}, with_direction=True))
    lines.append("**Diagnostic**")
    lines.extend(_kv_table(processing.get("diagnostic", {}) or {}))

    lines.append("## Graph")
    lines.append("")
    lines.append("**Scored**")
    lines.extend(_kv_table(graph.get("scored", {}) or {}, with_direction=True))
    lines.append(
        "> ⚠️ Graph KPIs are confounded on a single run by corpus selection, "
        "prior-graph density, and the empty-start build — they isolate model "
        "quality only across a same-corpus multi-model cohort. `entity_reuse` "
        "is the best-available scored signal (canonicalization), not a "
        "high-confidence one; read it alongside the watched diagnostics."
    )
    lines.append("")
    lines.append("**Watched** (promotion candidates)")
    lines.extend(_kv_table(graph.get("watched", {}) or {}))
    lines.append("**Diagnostic**")
    lines.extend(_kv_table(graph.get("diagnostic", {}) or {}))

    return "\n".join(lines).rstrip() + "\n"
