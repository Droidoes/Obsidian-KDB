"""kdb_benchmark.scorecard — Task #22 + Task #42 cross-model scorecard.

Renders a list of post-Borda RunScores as:
  * JSON (sorted models, full nested measure/diagnostic detail) for
    archival.
  * Terminal-friendly table (rank | model_id | S0 | M1..M5 | M6_b | M7_b
    | FINAL | RAN_AT) plus a raw-rates footer for human magnitude
    inspection.

Round 4 DC4: every scorecard MUST emit the disclaimer that final_score is
comparable only within this candidate set; cross-set comparisons are not
meaningful under average-rank Borda. Raw rates remain the cross-run
inspection surface.

Task #42 layout — scores_dir is now split into two subdirectories:

    benchmark/scores/runs/<scorecard_id>.json   — per-invocation only
    benchmark/scores/final/<timestamp>.json     — versioned merged view

Per-run scorecards carry only the models from this invocation; their
filename is `<ts>-<model_id>` for single-model runs, `<ts>` otherwise.
Final scorecards always use timestamp-only filenames; each model entry
carries a `source_scorecard_id` field pointing at the per-run scorecard
that produced it. Finals are versioned (never overwritten) so prior
states remain inspectable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
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
    free function `render_terminal`.

    `source_scorecard_id_by_model` is populated only for FINAL scorecards
    (see Task #42): each entry maps a model_id → the per-run scorecard_id
    it originated from. For per-run scorecards this stays empty — the
    per-run scorecard *is* the source.
    """
    scorecard_id: str
    candidate_set: list[str]                  # sorted model_ids
    emitted_at: str                           # local ISO timestamp with offset
    disclaimer: str
    runs: list[RunScore] = field(default_factory=list)  # ordered by final_score desc
    source_scorecard_id_by_model: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "scorecard_id": self.scorecard_id,
            "candidate_set": list(self.candidate_set),
            "emitted_at": self.emitted_at,
            "disclaimer": self.disclaimer,
            "models": [
                _run_summary(r, self.source_scorecard_id_by_model.get(r.model_id))
                for r in self.runs
            ],
        }


def _run_summary(run: RunScore, source_scorecard_id: Optional[str]) -> dict:
    """Per-model JSON entry for the scorecard. Adds `ran_at` (Round 4 [4])
    and, for final scorecards, the `source_scorecard_id` pointer (Task #42)."""
    d = run.to_dict()
    d["ran_at"] = run.run_id  # full run_id includes the timestamp suffix
    if source_scorecard_id is not None:
        d["source_scorecard_id"] = source_scorecard_id
    return d


def _format_scorecard_id(emitted_at: str, *, single_model_id: Optional[str]) -> str:
    """Filename-safe scorecard_id. Replaces `:` from the local-ISO-with-offset
    timestamp; appends model_id only for single-model per-run scorecards."""
    base = emitted_at.replace(":", "-")
    if single_model_id is not None:
        return f"{base}-{single_model_id}"
    return base


def build_per_run_scorecard(
    runs: list[RunScore],
    *,
    single_model_id: Optional[str] = None,
) -> Scorecard:
    """Per-invocation scorecard (Task #42).

    Carries only the models scored in this invocation. Filename is
    `<ts>-<model_id>` when `single_model_id` is provided (1-model runs),
    else `<ts>`. No source_scorecard_id_by_model — the per-run scorecard
    IS the source.

    Models are ordered by final_score descending (None goes last).
    """
    emitted_at = now_iso()
    candidate_set = sorted(r.model_id for r in runs)
    scorecard_id = _format_scorecard_id(emitted_at, single_model_id=single_model_id)
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


def build_final_scorecard(
    runs: list[RunScore],
    *,
    source_scorecard_id_by_model: dict[str, str],
) -> Scorecard:
    """Merged-view scorecard (Task #42).

    `runs` is the post-Borda union across all known models (caller is
    responsible for de-duping by model_id and re-scoring across the
    union — see cli.py merge logic). Filename is always timestamp-only
    so finals form a clean version history when sorted lexically.
    `source_scorecard_id_by_model` MUST cover every model in `runs`.
    """
    emitted_at = now_iso()
    candidate_set = sorted(r.model_id for r in runs)
    scorecard_id = _format_scorecard_id(emitted_at, single_model_id=None)
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
        source_scorecard_id_by_model=dict(source_scorecard_id_by_model),
    )


# Back-compat shim — Task #22 callers and tests still use this.
def build_scorecard(runs: list[RunScore]) -> Scorecard:
    """Deprecated alias for build_per_run_scorecard with no single_model_id.
    Retained so existing tests / external callers keep working; new code
    should call build_per_run_scorecard or build_final_scorecard explicitly.
    """
    return build_per_run_scorecard(runs)


def write_scorecard(
    sc: Scorecard,
    *,
    scores_dir: Path,
    subdir: Optional[str] = None,
) -> Path:
    """Persist a scorecard as `<scores_dir>/[<subdir>/]<scorecard_id>.json`
    plus the rendered table at the same stem with `.txt`.

    `subdir` selects between `runs/` (per-invocation) and `final/` (merged
    versioned view). Pass `None` to write at the top level (back-compat).
    """
    target_dir = scores_dir if subdir is None else scores_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"{sc.scorecard_id}.json"
    out_path.write_text(
        json.dumps(sc.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    txt_path = target_dir / f"{sc.scorecard_id}.txt"
    txt_path.write_text(render_terminal(sc), encoding="utf-8")
    return out_path


def latest_final_scorecard_path(scores_dir: Path) -> Optional[Path]:
    """Return the most-recent final scorecard JSON path, or None if no
    finals exist yet. Sort is lexical on filename — safe because the
    filename is the local-ISO timestamp with `:` → `-` substitution,
    which preserves chronological order character-for-character.
    """
    final_dir = scores_dir / "final"
    if not final_dir.is_dir():
        return None
    candidates = sorted(final_dir.glob("*.json"))
    return candidates[-1] if candidates else None


def load_runs_from_scorecard(
    path: Path,
) -> tuple[list[RunScore], dict[str, str]]:
    """Reverse-load a scorecard JSON into (runs, source_scorecard_id_by_model).

    The source map carries each model's per-run scorecard_id when the
    scorecard JSON declares it on the entry. For bootstrap cases (entries
    without a `source_scorecard_id` field), we fall back to the
    scorecard's own `scorecard_id` — meaning "we don't know which per-run
    produced this; this scorecard is the best handle we have".
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    fallback_id = data.get("scorecard_id")
    runs: list[RunScore] = []
    source_map: dict[str, str] = {}
    for entry in data.get("models", []):
        rs = RunScore.from_dict(entry)
        runs.append(rs)
        source_map[rs.model_id] = entry.get("source_scorecard_id") or fallback_id
    return runs, source_map


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
