"""kdb-benchmark CLI — score subcommand (Task #109, redesigned 2026-06-06).

score subcommand:
  Incremental model leaderboard. Each invocation incorporates one or more
  run dirs (measurements.json from kdb-orchestrate --emit-kpis), one row per
  header.model (latest run per model wins), re-reads every listed run live,
  and Borda-ranks the scored KPIs at equal weight. No corpus_fingerprint gate
  — cross-run corpora are assumed to differ; comparability is the user's
  judgment. The leaderboard (--leaderboard, default benchmark/scores/
  leaderboard.json) stores model→run-dir pointers + the ranking; delete it to
  reset. KPI values are never copied — they live in each run's measurements.json.

Exit code: 0 on success, non-zero on user error / runtime failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.benchmark.paths import RUNS_DIR, SCORES_DIR
from common.run_context import now_iso


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


def _add_score_args(p: argparse.ArgumentParser) -> None:
    """Register the `score` subcommand's arguments on its subparser."""
    p.add_argument(
        "run_dirs", nargs="+", metavar="RUN_DIR",
        help="One or more run-dir names (under --runs-root) to incorporate.",
    )
    p.add_argument(
        "--runs-root", type=Path, default=RUNS_DIR,
        help=f"Where per-run benchmark outputs land (default: {RUNS_DIR})",
    )
    p.add_argument(
        "--leaderboard", type=Path, default=SCORES_DIR / "leaderboard.json",
        help=(
            f"Persistent leaderboard file (default: {SCORES_DIR / 'leaderboard.json'}). "
            "Delete it to reset the ranking."
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point — kdb-benchmark dispatches to its subcommands."""
    effective = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="kdb-benchmark",
        description="Cross-model KPI leaderboard from kdb-orchestrate --emit-kpis runs.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    score_p = sub.add_parser(
        "score",
        help="Update the model leaderboard from --emit-kpis runs.",
        description=(
            "Incrementally update a model leaderboard by hierarchically Borda-"
            "ranking the scored KPIs from kdb-orchestrate --emit-kpis runs. Each "
            "run dir contributes one row keyed by its header.model (latest run per "
            "model wins); the leaderboard accumulates across invocations. No "
            "corpus_fingerprint gate — comparability is the user's judgment. Reset "
            "by deleting the --leaderboard file."
        ),
    )
    _add_score_args(score_p)
    args = parser.parse_args(effective)
    if args.command == "score":
        return _score_command(args)
    return 2  # unreachable: subparsers required=True


def _score_command(args: argparse.Namespace) -> int:
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


if __name__ == "__main__":
    sys.exit(main())
