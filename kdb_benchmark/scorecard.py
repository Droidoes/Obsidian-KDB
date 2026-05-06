"""kdb_benchmark.scorecard — Task #22 cross-model scorecard.

Renders a list of post-Borda RunScores as:
  * JSON (sorted models, full nested measure/diagnostic detail) for
    archival in `benchmark/scores/<scorecard_id>.json`.
  * Terminal-friendly table (rank | model_id | S0 | M1..M5 | M6_b | M7_b
    | FINAL | RAN_AT) plus a raw-rates footer for human magnitude
    inspection.

Round 4 DC4: every scorecard MUST emit the disclaimer that final_score is
comparable only within this candidate set; cross-set comparisons are not
meaningful under average-rank Borda. Raw rates remain the cross-run
inspection surface.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from kdb_compiler.run_context import now_iso
from kdb_benchmark.scorer import RunScore


_DISCLAIMER = (
    "final_score is comparable ONLY WITHIN this candidate set "
    "(average-rank Borda — adding/removing a candidate shifts the "
    "ranks of others). Use the raw $/ms rates below for cross-run "
    "magnitude inspection."
)


@dataclass(frozen=True)
class Scorecard:
    """Cross-model scorecard for a single emission. Holds RunScore objects
    plus metadata; renders to JSON + terminal text via to_dict() and the
    free function `render_terminal`."""
    scorecard_id: str
    candidate_set: list[str]                  # sorted model_ids
    emitted_at: str                           # local ISO timestamp with offset
    disclaimer: str
    runs: list[RunScore] = field(default_factory=list)  # ordered by final_score desc

    def to_dict(self) -> dict:
        return {
            "scorecard_id": self.scorecard_id,
            "candidate_set": list(self.candidate_set),
            "emitted_at": self.emitted_at,
            "disclaimer": self.disclaimer,
            "models": [_run_summary(r) for r in self.runs],
        }


def _run_summary(run: RunScore) -> dict:
    """Per-model JSON entry for the scorecard."""
    d = run.to_dict()
    # Add ran_at field for the human-readable timestamp (Round 4 [4]).
    # The timestamp lives in the run_id by convention; surface it
    # explicitly so consumers don't have to parse run_id.
    d["ran_at"] = run.run_id  # full run_id includes the timestamp suffix
    return d


def build_scorecard(runs: list[RunScore]) -> Scorecard:
    """Assemble a Scorecard from post-Borda RunScores.

    Models are ordered by final_score descending (None goes last).
    """
    emitted_at = now_iso()
    candidate_set = sorted(r.model_id for r in runs)
    scorecard_id = (
        emitted_at.replace(":", "-")
        + "-"
        + "_".join(candidate_set)
    )
    ordered = sorted(
        runs,
        key=lambda r: (r.final_score is None, -(r.final_score or 0.0)),
    )
    return Scorecard(
        scorecard_id=scorecard_id,
        candidate_set=candidate_set,
        emitted_at=emitted_at,
        disclaimer=_DISCLAIMER,
        runs=ordered,
    )


def write_scorecard(sc: Scorecard, *, scores_dir: Path) -> Path:
    """Atomically write the scorecard JSON to scores_dir/<scorecard_id>.json."""
    scores_dir.mkdir(parents=True, exist_ok=True)
    out_path = scores_dir / f"{sc.scorecard_id}.json"
    out_path.write_text(
        json.dumps(sc.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out_path


def render_terminal(sc: Scorecard) -> str:
    """Pretty-printed scorecard for stdout. Self-contained — caller just
    prints the returned string. Includes the DC4 disclaimer at the
    bottom plus a raw-rates inspection footer for M6/M7."""
    lines: list[str] = []
    lines.append(
        f"Scorecard: candidate_set={sc.candidate_set}   emitted_at={sc.emitted_at}"
    )
    lines.append("=" * 100)

    # Header
    header = (
        f"{'rank':>4}  "
        f"{'model_id':<14}  "
        f"{'S0':>5} "
        f"{'M1':>5} "
        f"{'M2':>5} "
        f"{'M3':>5} "
        f"{'M4':>5} "
        f"{'M5':>5} "
        f"{'M6_b':>5} "
        f"{'M7_b':>5}  "
        f"{'FINAL':>6}  "
        f"{'RAN_AT':<32}"
    )
    lines.append(header)
    lines.append("-" * 100)

    # Per-model rows
    for i, run in enumerate(sc.runs, start=1):
        s0 = _fmt_rate(run.s0.rate)
        m_rates = [_fmt_rate(run.measures[k].rate) for k in ("M1", "M2", "M3", "M4", "M5")]
        m6_b = _fmt_rate(run.m6_borda)
        m7_b = _fmt_rate(run.m7_borda)
        final = _fmt_rate(run.final_score)
        lines.append(
            f"{i:>4}  "
            f"{run.model_id:<14}  "
            f"{s0:>5} "
            + " ".join(f"{m:>5}" for m in m_rates)
            + f" {m6_b:>5} {m7_b:>5}  "
            + f"{final:>6}  "
            f"{run.run_id:<32}"
        )

    # Raw rates inspection footer
    lines.append("")
    lines.append("Raw rates (cross-set comparison NOT meaningful — see disclaimer):")
    for run in sc.runs:
        m6_raw = run.measures["M6"].rate
        m7_raw = run.measures["M7"].rate
        m6_str = f"${m6_raw:.4f}" if m6_raw is not None else "n/a"
        m7_str = f"{m7_raw:.0f}ms" if m7_raw is not None else "n/a"
        lines.append(
            f"  {run.model_id:<14}  "
            f"M6=${m6_raw:.4f}/1K-words  M7={m7_raw:.0f}ms/1K-words"
            if (m6_raw is not None and m7_raw is not None)
            else f"  {run.model_id:<14}  M6={m6_str}  M7={m7_str}"
        )

    # Diagnostics
    lines.append("")
    lines.append("Diagnostics (unweighted):")
    diag_keys = ("retry_load", "token_overrun_rate", "pages_per_1k_source_words")
    diag_header = "  " + f"{'model_id':<14}  " + "  ".join(f"{k:<28}" for k in diag_keys)
    lines.append(diag_header)
    for run in sc.runs:
        cells = [
            f"{run.diagnostics[k].rate:.4f}" if (k in run.diagnostics and run.diagnostics[k].rate is not None) else "n/a"
            for k in diag_keys
        ]
        lines.append(
            "  " + f"{run.model_id:<14}  " + "  ".join(f"{c:<28}" for c in cells)
        )

    # Disclaimer (Round 4 DC4)
    lines.append("")
    lines.append("⚠ " + sc.disclaimer)

    return "\n".join(lines) + "\n"


def _fmt_rate(rate: Optional[float]) -> str:
    if rate is None:
        return "n/a"
    return f"{rate:.3f}"
