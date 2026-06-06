"""kdb-benchmark CLI — Tasks #30 / #31 / #22 / #33 / #42 / #46 / #109 orchestrator.

Usage:
  kdb-benchmark --models <model_id> \\
                [--sources benchmark/sources] \\
                [--system-prompt-path PATH] \\
                [--runs-root benchmark/runs] \\
                [--scores-dir benchmark/scores] \\
                [--max-tokens 32768] \\
                [--no-merge]

  kdb-benchmark score <run_id> [<run_id> ...] \\
                [--runs-root benchmark/runs] \\
                [--scores-dir benchmark/scores]

Single-model invocation (Task #46): `--models` accepts ONE model_id.
Multi-model comparison happens via cross-run merge (Task #42) — fire each
model separately and the latest final scorecard accumulates the union.

score subcommand (Task #109; redesigned 2026-06-06):
  Incremental model leaderboard. Each invocation incorporates one or more
  run dirs (measurements.json from kdb-orchestrate --emit-kpis), one row per
  header.model (latest run per model wins), re-reads every listed run live,
  and Borda-ranks the scored KPIs at equal weight. No corpus_fingerprint gate
  — cross-run corpora are assumed to differ; comparability is the user's
  judgment. The leaderboard (--leaderboard, default benchmark/scores/
  leaderboard.json) stores model→run-dir pointers + the ranking; delete it to
  reset. KPI values are never copied — they live in each run's measurements.json.

Flow:
  1. Print config header (provider/model, ctx, --max-tokens, prices, sources)
  2. runner.run_benchmark — compile every source (isolated state_root);
     prints per-source progress line as each compile_one returns
     (Task #46)
  3. scorer.score_run — derive a RunScore from the captured records
  4. scorer.score_runs — Borda + final_score (degenerate single-candidate
     rank for the per-run scorecard; full Borda happens at merge)
  5. Print KPI summary + total run time (compile + score)
  6. scorecard.build_per_run_scorecard with run_config + run_timing
     embedded; write to <scores_dir>/runs/
  7. Final scorecard merge (Task #42 — unless --no-merge):
       a. Load latest <scores_dir>/final/<ts>.json (if any)
       b. Merge by model_id; partition active vs dropped via registry
          (Task #44); re-Borda over active subset
       c. Write a NEW versioned final at <scores_dir>/final/<ts>.json

Exit code: 0 on success, non-zero on user error / runtime failure.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from tools.benchmark.paths import BENCHMARK_DIR, MODELS_JSON, RUNS_DIR, SCORES_DIR, SOURCES_DIR
from tools.benchmark.registry import ModelEntry, load_registry
from tools.benchmark.runner import run_benchmark
from tools.benchmark.scorecard import (
    build_final_scorecard,
    build_per_run_scorecard,
    fmt_duration,
    latest_final_scorecard_path,
    load_runs_from_scorecard,
    render_terminal,
    write_scorecard,
)
from dataclasses import replace

from tools.benchmark.scorer import RunScore, score_run, score_runs
from common.run_context import now_iso


_DEFAULT_SYSTEM_PROMPT = Path.home() / "Obsidian" / "KDB" / "KDB-Compiler-System-Prompt.md"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kdb-benchmark", description=__doc__.split("\n")[0])
    p.add_argument(
        "--models",
        required=True,
        help="Single model_id from tools/benchmark/models.json. Multi-model "
             "comparison happens via cross-run merge — fire each model "
             "separately. (Task #46: legacy comma-separated form is no "
             "longer accepted; use `--models X` for one model per fire.)",
    )
    p.add_argument(
        "--sources",
        type=Path,
        default=SOURCES_DIR,
        help=f"Directory of .md source files (default: {SOURCES_DIR})",
    )
    p.add_argument(
        "--system-prompt-path",
        type=Path,
        default=_DEFAULT_SYSTEM_PROMPT,
        help=f"Path to KDB-Compiler-System-Prompt.md (default: {_DEFAULT_SYSTEM_PROMPT})",
    )
    p.add_argument(
        "--runs-root",
        type=Path,
        default=RUNS_DIR,
        help=f"Where per-(model, run) state lands (default: {RUNS_DIR})",
    )
    p.add_argument(
        "--scores-dir",
        type=Path,
        default=SCORES_DIR,
        help=f"Where scorecards are written, split into runs/ + final/ "
             f"(default: {SCORES_DIR})",
    )
    p.add_argument(
        "--max-tokens",
        type=int,
        default=32768,
        help="max_tokens passed to compile_one's model invocation (default: 32768)",
    )
    p.add_argument(
        "--registry-path",
        type=Path,
        default=MODELS_JSON,
        help=f"Path to models.json registry (default: {MODELS_JSON})",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Emit a per-measure scoring trace to stdout (numerator, "
             "denominator, rate, weight, plus evidence for S0 / M1 / M6 / M7 / Borda).",
    )
    p.add_argument(
        "--no-merge",
        action="store_true",
        help="Skip the cross-run final-scorecard merge step. Per-run "
             "scorecard is still written under runs/, but final/ is left "
             "untouched.",
    )
    return p


def _merge_with_prior_final(
    new_per_run_runs: list[RunScore],
    new_per_run_scorecard_id: str,
    *,
    scores_dir: Path,
    registry_entries: list[ModelEntry],
) -> tuple[list[RunScore], list[RunScore], dict[str, str], dict[str, str]]:
    """Combine the new per-run RunScores with the prior final scorecard
    (if any) and partition the result by registry drop-status.

    Returns (active_runs_with_borda, dropped_runs_no_borda, source_map,
    dropped_reasons) — ready for build_final_scorecard.

    Merge rule (Task #42 + Task #44):
      * Union by model_id (prior final + new per-run; load_runs_from_scorecard
        combines prior active + prior dropped into one list).
      * Where a model_id appears in BOTH the prior and the new per-run,
        the new per-run wins (latest measurement).
      * Partition by current registry: models flagged `dropped: true`
        route to the dropped subset; everyone else stays active.
      * Borda + final_score recomputed across ACTIVE only (excluded from
        dropped). Dropped runs get m6_borda / m7_borda / final_score = None
        — they are not part of the active candidate set, so Borda over
        them isn't meaningful.
      * source_map carries per-model originating per-run scorecard_id for
        BOTH active and dropped (callers may need it for either).
      * dropped_reasons maps each dropped model_id → its reason string
        from the registry, for inline display in the scorecard.

    A model can flip between active/dropped between fires by editing
    `dropped: true|false` in models.json — the next merge re-partitions
    fresh. Drop status is registry-driven, not scorecard-snapshot-driven.
    """
    by_model: dict[str, RunScore] = {}
    source_map: dict[str, str] = {}

    prior_path = latest_final_scorecard_path(scores_dir)
    if prior_path is not None:
        prior_runs, prior_source_map = load_runs_from_scorecard(prior_path)
        for r in prior_runs:
            by_model[r.model_id] = r
            source_map[r.model_id] = prior_source_map[r.model_id]

    # New per-run wins on overlap.
    for r in new_per_run_runs:
        by_model[r.model_id] = r
        source_map[r.model_id] = new_per_run_scorecard_id

    # Strip stale Borda/final fields — they are re-derived for active
    # below, and forced None for dropped.
    cleaned = {
        mid: replace(r, m6_borda=None, m7_borda=None, final_score=None)
        for mid, r in by_model.items()
    }

    dropped_set = {e.id for e in registry_entries if e.dropped}
    dropped_reasons = {e.id: e.dropped_reason for e in registry_entries if e.dropped}

    active = [r for mid, r in cleaned.items() if mid not in dropped_set]
    dropped = [r for mid, r in cleaned.items() if mid in dropped_set]

    enriched_active = score_runs(active)
    return enriched_active, dropped, source_map, dropped_reasons


# ---------------------------------------------------------------------------
# score subcommand (Task #109)
# ---------------------------------------------------------------------------

def _build_score_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kdb-benchmark score",
        description=(
            "Incrementally update a model leaderboard by Borda-ranking the "
            "scored KPIs from kdb-orchestrate --emit-kpis runs. Each run dir "
            "contributes one row keyed by its header.model (latest run per "
            "model wins); the leaderboard accumulates across invocations. "
            "No corpus_fingerprint gate — cross-run corpora are assumed to "
            "differ and comparability is the user's judgment. "
            "Reset by deleting the --leaderboard file."
        ),
    )
    p.add_argument(
        "run_dirs",
        nargs="+",
        metavar="RUN_DIR",
        help="One or more run-dir names (under --runs-root) to incorporate.",
    )
    p.add_argument(
        "--runs-root",
        type=Path,
        default=RUNS_DIR,
        help=f"Where per-run benchmark outputs land (default: {RUNS_DIR})",
    )
    p.add_argument(
        "--leaderboard",
        type=Path,
        default=SCORES_DIR / "leaderboard.json",
        help=(
            f"Persistent leaderboard file (default: {SCORES_DIR / 'leaderboard.json'}). "
            "Delete it to reset the ranking."
        ),
    )
    return p


def _render_leaderboard_md(
    ranking: list[dict],
    scored_by_model: dict,
    diagnostics_by_model: dict,
    top_weights: dict,
    updated_at: str,
) -> str:
    """Render the leaderboard as a Markdown document (written to leaderboard.md).

    Main table = the ranking (processing-KPI Borda + combined graph_score +
    composite). Detail table = the RAW measured values per model (all scored
    KPIs + diagnostics/watched) so the actual numbers are readable, not just
    their Borda ranks.
    """
    from compiler.kpi.score import GRAPH_WEIGHTS

    graph_set = set(GRAPH_WEIGHTS)
    proc_kpis = [k for k in (ranking[0]["per_kpi_borda"] if ranking else {})
                 if k not in graph_set]

    def fmt(v) -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            if v == 0.0:
                return "0"
            if abs(v) >= 1000:
                return f"{v:,.0f}"
            return f"{v:.4g}"
        return str(v)

    def row(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    def sep(n: int) -> str:
        return "|" + "|".join(["---"] * n) + "|"

    lines: list[str] = ["# Model leaderboard", ""]
    lines.append(
        f"_Hierarchical weighted Borda — §6 starting weights: "
        f"quarantine {top_weights.get('quarantine_rate')} / "
        f"graph {top_weights.get('graph')} / "
        f"recovery {top_weights.get('recovery_rate')} / "
        f"latency {top_weights.get('latency')}. Updated {updated_at}._"
    )
    lines.append("")

    # --- ranking (Borda) ---
    head = ["rank", "model"] + [f"{k} ↓" for k in proc_kpis] + ["graph_score ↑", "composite"]
    lines.append(row(head))
    lines.append(sep(len(head)))
    for r in ranking:
        pkb = r.get("per_kpi_borda", {})
        cells = [str(r.get("rank", "")), str(r.get("model", ""))]
        cells += [fmt(pkb.get(k)) for k in proc_kpis]
        cells.append(fmt(r.get("graph_score")))
        cells.append(fmt(r.get("composite")))
        lines.append(row(cells))
    lines.append("")

    # --- raw measured values (the actual numbers behind the ranks) ---
    scored_cols: list[str] = []
    for m in scored_by_model.values():
        for k in m:
            if k not in scored_cols:
                scored_cols.append(k)
    diag_cols: list[str] = []
    for d in diagnostics_by_model.values():
        for k in d:
            if k not in diag_cols:
                diag_cols.append(k)
    all_cols = scored_cols + diag_cols
    lines.append("## Raw measured values (scored KPIs + diagnostics / watched)")
    lines.append("")
    lines.append(row(["model"] + all_cols))
    lines.append(sep(len(all_cols) + 1))
    for r in ranking:
        model = r["model"]
        sc = scored_by_model.get(model, {})
        dg = diagnostics_by_model.get(model, {})
        cells = [model] + [fmt(sc.get(k)) for k in scored_cols] + [fmt(dg.get(k)) for k in diag_cols]
        lines.append(row(cells))
    lines.append("")

    lines.append(
        "> Composite & graph_score are comparable ONLY within this candidate set "
        "(average-rank Borda — adding/removing a model shifts ranks). "
        "graph_score = weighted Borda of the 4 graph KPIs (connectivity 35 / link 30 / "
        "supports 20 / reuse 15)."
    )
    return "\n".join(lines).rstrip() + "\n"


def _render_score_table(ranking: list[dict], diagnostics_by_model: dict) -> str:
    """Render the leaderboard table for the score subcommand.

    Main table: rank | model | <processing KPIs (Borda)> | graph_score | composite
    — the four graph KPIs are collapsed into the combined graph_score; their
    individual Borda values + the watched/diagnostic KPIs follow in a detail
    section for inspection.  `ranking` rows carry model / rank / composite /
    graph_score / per_kpi_borda.
    """
    from compiler.kpi.score import GRAPH_WEIGHTS

    graph_kpis = list(GRAPH_WEIGHTS.keys())
    graph_set = set(graph_kpis)

    # Processing KPI columns = scored KPIs that aren't graph KPIs (stable order).
    proc_kpis: list[str] = []
    if ranking:
        for k in ranking[0].get("per_kpi_borda", {}):
            if k not in graph_set:
                proc_kpis.append(k)

    def _cell(v) -> str:
        return f"{v:.4f}" if isinstance(v, (int, float)) else "n/a"

    lines: list[str] = []
    lines.append("=" * 100)
    lines.append(
        "Model leaderboard — weighted Borda "
        "(§6 starting weights: quarantine .40 / graph .40 / recovery .10 / latency .10)"
    )
    lines.append("=" * 100)

    cols = proc_kpis + ["graph_score"]
    header = "  ".join(f"{c:>20}" for c in cols)
    lines.append(f"{'rank':>4}  {'model':<32}  {header}  {'composite':>9}")
    lines.append("-" * 100)

    for row in ranking:
        pkb = row.get("per_kpi_borda", {})
        cells = [_cell(pkb.get(k)) for k in proc_kpis]
        cells.append(_cell(row.get("graph_score")))
        cellstr = "  ".join(f"{c:>20}" for c in cells)
        comp = row.get("composite")
        lines.append(
            f"{row.get('rank', 0):>4}  {row.get('model', ''):<32}  {cellstr}  "
            f"{(_cell(comp)):>9}"
        )

    # Graph-KPI detail (the components behind graph_score) + diagnostics/watched.
    lines.append("")
    lines.append("Graph KPIs (components of graph_score) + diagnostics / watched (not ranked):")
    detail_cols = graph_kpis + [
        k for k in (
            next(iter(diagnostics_by_model.values()), {}) if diagnostics_by_model else {}
        )
    ]
    # Collect the union of all diagnostic keys across models (stable order).
    seen = set(graph_kpis)
    all_detail = list(graph_kpis)
    for vals in diagnostics_by_model.values():
        for k in vals:
            if k not in seen:
                all_detail.append(k)
                seen.add(k)
    detail_header = "  ".join(f"{k:>24}" for k in all_detail)
    lines.append(f"  {'model':<32}  {detail_header}")
    lines.append("  " + "-" * 94)
    # graph-KPI bordas come from each model's per_kpi_borda; diagnostics from
    # diagnostics_by_model.
    pkb_by_model = {row["model"]: row.get("per_kpi_borda", {}) for row in ranking}
    for model in sorted(pkb_by_model):
        pkb = pkb_by_model[model]
        diag = diagnostics_by_model.get(model, {})
        cells = []
        for k in all_detail:
            v = pkb.get(k) if k in graph_set else diag.get(k)
            cells.append(_cell(v))
        cellstr = "  ".join(f"{c:>24}" for c in cells)
        lines.append(f"  {model:<32}  {cellstr}")

    lines.append("")
    lines.append(
        "NOTE: composite & graph_score are comparable ONLY within this candidate "
        "set (average-rank Borda — adding/removing a model shifts ranks). "
        "graph_score = weighted Borda of the 4 graph KPIs (35/30/20/15)."
    )
    return "\n".join(lines) + "\n"


def _read_measurements(mpath: Path) -> dict | None:
    """Read + parse a measurements.json, or None on missing/invalid (caller logs)."""
    if not mpath.exists():
        return None
    try:
        return json.loads(mpath.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _scored_and_diag(meas: dict) -> tuple[dict, dict]:
    """Split a measurements payload into (merged scored KPIs, merged diag+watched).

    scored = {**processing.scored, **graph.scored} (data-driven — new scored
    KPIs flow through automatically). Current scored keys: quarantine_rate,
    recovery_rate, latency (processing) + entity_reuse, graph_connectivity,
    link_density, supports_density (graph).

    KPI VALUES are looked up by name across ALL emitted tiers (scored / watched /
    diagnostic, both families). The emit-time tier is just where the producing run
    happened to file each value — it's a *classification*, not part of the value —
    so a KPI promoted between tiers (e.g. §6 moved graph_connectivity / link_density
    / supports_density from watched/diagnostic into scored) is found in older runs
    without re-emitting them. What's *scored* is the score command's own contract
    (KPI_LOWER_IS_BETTER); everything else is carried as a diagnostic for display.
    """
    from compiler.kpi.score import KPI_LOWER_IS_BETTER

    processing = meas.get("processing", {}) or {}
    graph = meas.get("graph", {}) or {}
    all_vals: dict = {}
    for section in (processing, graph):
        for tier in ("scored", "watched", "diagnostic"):
            all_vals.update(section.get(tier, {}) or {})
    # scored = the contract's KPIs, valued from wherever they were emitted (None
    # if a run genuinely never measured one — borda drops it, pro-rata).
    scored = {k: all_vals.get(k) for k in KPI_LOWER_IS_BETTER}
    diag = {k: v for k, v in all_vals.items() if k not in KPI_LOWER_IS_BETTER}
    return scored, diag


def _score_command(argv: list[str]) -> int:
    """Implement the `score` subcommand: an incremental model leaderboard.

    The leaderboard file persists ``{models: {model_slug: run_dir}, ranking: [...]}``.
    Each invocation incorporates the given run dirs (one row per header.model;
    latest run per model wins), re-reads every listed run's measurements.json
    LIVE, hierarchically scores them (§6 score_models: per-KPI Borda → combined
    graph_score → top-level composite), and rewrites the leaderboard. The
    leaderboard stores only model→run-dir pointers + the ranking — KPI values live
    solely in each run's measurements.json. No corpus_fingerprint gate:
    cross-run corpora are assumed to differ; comparability is the user's
    judgment. Reset = delete the leaderboard file.
    """
    from compiler.kpi.score import score_models

    parser = _build_score_parser()
    args = parser.parse_args(argv)

    runs_root: Path = args.runs_root
    leaderboard_path: Path = args.leaderboard

    # --- Load the existing leaderboard (model_slug -> run_dir), or start empty ---
    models_to_rundir: dict[str, str] = {}
    if leaderboard_path.exists():
        try:
            prior = json.loads(leaderboard_path.read_text(encoding="utf-8"))
            models_to_rundir = dict(prior.get("models", {}))
        except (json.JSONDecodeError, OSError) as exc:
            print(
                f"error: failed to read leaderboard {leaderboard_path}: {exc}",
                file=sys.stderr,
            )
            return 1

    # --- Incorporate the incoming run dirs (latest run per model_slug wins) ---
    # Process in sorted order so that within one invocation, a lexically-greater
    # run dir (timestamp-suffixed) overwrites an earlier one for the same model.
    for run_dir in sorted(args.run_dirs):
        data = _read_measurements(runs_root / run_dir / "measurements.json")
        if data is None:
            print(
                f"error: measurements.json missing or invalid for run dir "
                f"'{run_dir}' (expected: {runs_root / run_dir / 'measurements.json'})",
                file=sys.stderr,
            )
            return 1
        model_slug = (data.get("header", {}) or {}).get("model")
        if not model_slug:
            print(
                f"error: run dir '{run_dir}': measurements.json missing header.model",
                file=sys.stderr,
            )
            return 1
        models_to_rundir[model_slug] = run_dir  # latest replaces

    if not models_to_rundir:
        print(
            "error: leaderboard is empty — supply at least one run dir",
            file=sys.stderr,
        )
        return 1

    # --- Re-read every listed run LIVE and build the Borda input ---
    models: list[dict] = []
    diagnostics_by_model: dict[str, dict] = {}
    for model_slug, run_dir in models_to_rundir.items():
        data = _read_measurements(runs_root / run_dir / "measurements.json")
        if data is None:
            print(
                f"error: leaderboard references missing/invalid run dir '{run_dir}' "
                f"for model '{model_slug}'. Re-incorporate a current run or reset "
                f"the leaderboard ({leaderboard_path}).",
                file=sys.stderr,
            )
            return 1
        # scored values are looked up across all emitted tiers (see _scored_and_diag),
        # so a KPI promoted between tiers needs no re-run; a genuinely-unmeasured
        # scored KPI comes back None and borda drops it pro-rata.
        scored, diag = _scored_and_diag(data)
        models.append({"model": model_slug, "scored": scored})
        diagnostics_by_model[model_slug] = diag

    # --- Hierarchical score (§6: per-KPI Borda → graph_score → composite) ---
    result = score_models(models)

    # --- Build the ranked list (composite desc), persisted for display ---
    ranking = sorted(
        (
            {
                "model": m,
                "composite": e["composite"],
                "graph_score": e["graph_score"],
                "per_kpi_borda": e["per_kpi_borda"],
            }
            for m, e in result["per_model"].items()
        ),
        key=lambda r: -(r["composite"] or 0.0),
    )
    for i, row in enumerate(ranking, start=1):
        row["rank"] = i

    # --- Persist the leaderboard (pointers + ranking only; no KPI values) ---
    payload: dict = {
        "models": models_to_rundir,
        "ranking": ranking,
        "top_weights": result["top_weights"],
        "graph_weights": result["graph_weights"],
        "updated_at": now_iso(),
    }
    leaderboard_path.parent.mkdir(parents=True, exist_ok=True)
    leaderboard_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # --- Rendered Markdown leaderboard alongside the JSON ---
    scored_by_model = {m["model"]: m["scored"] for m in models}
    md_path = leaderboard_path.with_suffix(".md")
    md_path.write_text(
        _render_leaderboard_md(
            ranking, scored_by_model, diagnostics_by_model,
            result["top_weights"], payload["updated_at"],
        ),
        encoding="utf-8",
    )

    # --- Render terminal table ---
    table = _render_score_table(ranking, diagnostics_by_model)
    print(table)
    print(
        f"leaderboard updated: {leaderboard_path} (+ {md_path.name})  "
        f"({len(models)} models)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point — dispatches to 'score' subcommand or legacy run path."""
    effective = list(sys.argv[1:] if argv is None else argv)

    # Dispatch: if the first positional token is 'score', route there.
    # This preserves the flat --models legacy path byte-for-byte.
    if effective and effective[0] == "score":
        return _score_command(effective[1:])

    return _main_run(effective)


def _main_run(argv: list[str] | None = None) -> int:
    """Original kdb-benchmark run logic (formerly `main`)."""
    args = _build_parser().parse_args(argv)
    model_ids = [m.strip() for m in args.models.split(",") if m.strip()]
    if not model_ids:
        print("error: --models must be non-empty", file=sys.stderr)
        return 2
    # Task #46: single model only. Cross-run merge handles comparison.
    if len(model_ids) > 1:
        print(
            "error: --models takes a single model_id (Task #46) — fire each "
            "model separately and the cross-run merge accumulates them",
            file=sys.stderr,
        )
        return 2
    model_id = model_ids[0]

    # Task #44: load registry early so we can fail-fast when the selected
    # --models entry is flagged dropped, before incurring any API cost.
    try:
        registry_entries = load_registry(args.registry_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    by_id = {e.id: e for e in registry_entries}
    entry = by_id.get(model_id)
    if entry is not None and entry.dropped:
        print(
            f"error: model '{model_id}' is marked dropped in registry — "
            f"un-drop it or select an active model",
            file=sys.stderr,
        )
        return 2

    # Task #36: trace is ALWAYS captured per-run and ALWAYS persisted to
    # disk. --verbose now controls only whether the trace also prints to
    # stdout after the scorecard. Disk path: <run_dir>/score_trace.txt.
    sink: list[str] = []
    cross_run_sink: list[str] = []

    # Task #46: config header — surface the inputs before the runner
    # produces output, so the user sees exactly what's about to fire.
    if entry is not None:
        print(
            f"[{model_id}] config: {entry.provider}/{entry.model}  "
            f"ctx_window={entry.ctx_window}  --max-tokens={args.max_tokens}  "
            f"prices=${entry.price_in}/{entry.price_out}/1M-tok"
        )
    print(f"[{model_id}] sources: {args.sources}")
    print(f"[{model_id}] running benchmark...", flush=True)

    t_compile_start = time.monotonic()
    try:
        run_id, state_root, compile_metrics = run_benchmark(
            sources_dir=args.sources,
            model_id=model_id,
            runs_root=args.runs_root,
            system_prompt_path=args.system_prompt_path,
            max_tokens=args.max_tokens,
            registry_path=args.registry_path,
        )
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    compile_seconds = time.monotonic() - t_compile_start
    print(f"[{model_id}] compile complete: {fmt_duration(compile_seconds)}")

    print(f"[{model_id}] scoring run {run_id}...", flush=True)
    t_score_start = time.monotonic()
    try:
        run_score = score_run(
            state_root, run_id, model_id,
            registry_path=args.registry_path,
            trace_sink=sink,
        )
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    enriched = score_runs([run_score], trace_sink=cross_run_sink)
    score_seconds = time.monotonic() - t_score_start

    # Persist this run's trace (self-contained per-run + cross-run section).
    full = sink + [""] + cross_run_sink
    (state_root.parent / "score_trace.txt").write_text(
        "\n".join(full) + "\n", encoding="utf-8",
    )

    # Task #46: KPI summary + timing footer. The full table follows from
    # render_terminal below; this gives a one-line at-a-glance view.
    rs = enriched[0]
    m = rs.measures
    print(
        f"[{model_id}] KPIs:  "
        f"S0={rs.s0.rate:.3f}  M1={m['M1'].rate:.3f}  M2={m['M2'].rate:.3f}  "
        f"M3={m['M3'].rate:.3f}  M4={m['M4'].rate:.3f}  M5={m['M5'].rate:.3f}  "
        f"M6_raw=${m['M6'].rate:.4f}/1Kw  M7_raw={m['M7'].rate:.0f}ms/1Kw"
    )
    print(f"[{model_id}] score complete: {fmt_duration(score_seconds)}")
    print(f"[{model_id}] total run time: {fmt_duration(compile_seconds + score_seconds)}")

    # Task #46: snapshot inputs + timing onto the per-run scorecard so it
    # is self-describing — readers don't need to consult outside artifacts.
    run_config: dict = {
        "max_tokens": args.max_tokens,
        "sources_dir": str(args.sources),
        "n_sources": compile_metrics["n_sources"],
        "n_source_words": compile_metrics["n_source_words"],
        "system_prompt_path": str(args.system_prompt_path),
    }
    if entry is not None:
        run_config["provider"] = entry.provider
        run_config["model"] = entry.model
        run_config["ctx_window"] = entry.ctx_window
        run_config["price_in"] = entry.price_in
        run_config["price_out"] = entry.price_out
    run_timing: dict = {
        "compile_seconds": round(compile_seconds, 2),
        "score_seconds": round(score_seconds, 2),
        "total_seconds": round(compile_seconds + score_seconds, 2),
    }

    per_run_sc = build_per_run_scorecard(
        enriched, single_model_id=model_id,
        run_config=run_config, run_timing=run_timing,
    )
    per_run_path = write_scorecard(per_run_sc, scores_dir=args.scores_dir, subdir="runs")
    print(f"\nper-run scorecard written: {per_run_path}\n")
    print(render_terminal(per_run_sc))

    # ---- Final scorecard (merge with prior, unless --no-merge) ----
    if not args.no_merge:
        print("merging with prior final scorecard...")
        active_runs, dropped_runs, source_map, dropped_reasons = _merge_with_prior_final(
            enriched, per_run_sc.scorecard_id,
            scores_dir=args.scores_dir,
            registry_entries=registry_entries,
        )
        final_sc = build_final_scorecard(
            active_runs,
            source_scorecard_id_by_model=source_map,
            dropped_runs=dropped_runs,
            dropped_reasons=dropped_reasons,
        )
        final_path = write_scorecard(final_sc, scores_dir=args.scores_dir, subdir="final")
        print(f"\nfinal scorecard written: {final_path}\n")
        print(render_terminal(final_sc))

    # --verbose: per-measure trace prints AFTER the scorecard so the table
    # stays at the top of the user's terminal when they scroll up. The
    # trace is on disk regardless; this just mirrors it to the screen.
    if args.verbose:
        print("\n" + "=" * 100)
        print("Verbose trace (--verbose)")
        print("=" * 100)
        for line in sink:
            print(line)
        for line in cross_run_sink:
            print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
