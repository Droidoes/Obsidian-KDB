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

score subcommand (Task #109):
  Load one or more measurements.json files produced by kdb-orchestrate
  --emit-kpis.  All runs must share the same corpus_fingerprint (same
  source corpus) — a mismatch aborts with an error.  Where multiple runs
  share a group_key the latest (lexically-greatest run_id) is kept; others
  are skipped and reported.  Computes cross-model Borda composite over the
  merged scored KPIs and writes benchmark/scores/<scorecard_id>.json plus a
  rendered terminal table.

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
            "Cross-model Borda scoring over measurements.json files from "
            "kdb-orchestrate --emit-kpis runs. All supplied runs must share "
            "the same corpus_fingerprint; latest run per group_key wins "
            "(tie-break: lexical-max of run_id, which is timestamp-prefixed)."
        ),
    )
    p.add_argument(
        "run_ids",
        nargs="+",
        metavar="RUN_ID",
        help="One or more run_ids (directory names under --runs-root).",
    )
    p.add_argument(
        "--runs-root",
        type=Path,
        default=RUNS_DIR,
        help=f"Where per-run benchmark outputs land (default: {RUNS_DIR})",
    )
    p.add_argument(
        "--scores-dir",
        type=Path,
        default=SCORES_DIR,
        help=f"Where cross-model scorecards are written (default: {SCORES_DIR})",
    )
    return p


def _render_score_table(borda_result: dict, diagnostics_by_model: dict) -> str:
    """Render a terminal table for the score subcommand.

    Columns: rank | group_key | <scored KPI columns> | composite
    Followed by a diagnostics/watched section for human inspection.
    """
    per_model = borda_result["per_model"]
    weights = borda_result["weights"]
    all_kpis = list(weights.keys())

    # Sort models by composite descending
    ranked = sorted(
        per_model.items(),
        key=lambda kv: (-(kv[1]["composite"] or 0.0),),
    )

    lines: list[str] = []
    lines.append("=" * 100)
    lines.append(
        f"Cross-model Borda scorecard  "
        f"(weights: equal — post-run-1 calibration not yet applied)"
    )
    lines.append("=" * 100)

    # Header row
    kpi_header = "  ".join(f"{k:>22}" for k in all_kpis)
    lines.append(
        f"{'rank':>4}  {'group_key':<36}  {kpi_header}  {'composite':>9}"
    )
    lines.append("-" * 100)

    for i, (gk, entry) in enumerate(ranked, start=1):
        per_kpi = entry["per_kpi_borda"]
        kpi_cells = "  ".join(
            f"{per_kpi[k]:.4f}" if per_kpi[k] is not None else "   n/a"
            for k in all_kpis
        )
        # Each cell is right-justified to 22 chars
        kpi_cells = "  ".join(
            f"{(f'{per_kpi[k]:.4f}' if per_kpi[k] is not None else 'n/a'):>22}"
            for k in all_kpis
        )
        composite_str = f"{entry['composite']:.4f}"
        lines.append(
            f"{i:>4}  {gk:<36}  {kpi_cells}  {composite_str:>9}"
        )

    # Diagnostics/watched section
    if diagnostics_by_model:
        lines.append("")
        lines.append("Diagnostics / watched (not ranked, for inspection only):")
        # Collect all diag/watched KPI names
        all_diag: list[str] = []
        seen_d: set[str] = set()
        for vals in diagnostics_by_model.values():
            for k in vals:
                if k not in seen_d:
                    all_diag.append(k)
                    seen_d.add(k)
        diag_header = "  ".join(f"{k:>24}" for k in all_diag)
        lines.append(f"  {'group_key':<36}  {diag_header}")
        lines.append("  " + "-" * 90)
        for gk, vals in sorted(diagnostics_by_model.items()):
            cells = "  ".join(
                f"{(f'{vals[k]:.4f}' if (k in vals and vals[k] is not None) else 'n/a'):>24}"
                for k in all_diag
            )
            lines.append(f"  {gk:<36}  {cells}")

    lines.append("")
    lines.append(
        "NOTE: composite is comparable ONLY within this candidate set "
        "(average-rank Borda — adding/removing a candidate shifts ranks)."
    )
    return "\n".join(lines) + "\n"


def _score_command(argv: list[str]) -> int:
    """Implement the `score` subcommand (Task #109).

    Tie-break policy: when multiple run_ids share the same group_key,
    keep the one with the lexically GREATEST run_id.  Run IDs are
    timestamp-prefixed (YYYY-MM-DDTHH-MM-SS_TZ format), so lexical-max
    equals chronologically-latest.

    Epsilon / quantile method: defined in promotion.py (EPSILON = 1e-3,
    method="inclusive") — not used here; score_command carries diagnostics
    and watched KPI values for human reading but promotion is a separate
    tool.
    """
    from compiler.kpi.score import borda_score

    parser = _build_score_parser()
    args = parser.parse_args(argv)

    runs_root: Path = args.runs_root
    scores_dir: Path = args.scores_dir

    # --- Load measurements.json for each run_id ---
    loaded: list[dict] = []  # {"run_id", "group_key", "corpus_fingerprint", "measurements"}
    for run_id in args.run_ids:
        mpath = runs_root / run_id / "measurements.json"
        if not mpath.exists():
            print(
                f"error: measurements.json not found for run_id '{run_id}' "
                f"(expected: {mpath})",
                file=sys.stderr,
            )
            return 1
        try:
            data = json.loads(mpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(
                f"error: failed to parse {mpath}: {exc}",
                file=sys.stderr,
            )
            return 1

        header = data.get("header", {})
        group_key = header.get("group_key")
        corpus_fp = header.get("corpus_fingerprint")
        if not group_key:
            print(
                f"error: run_id '{run_id}': measurements.json missing "
                f"header.group_key",
                file=sys.stderr,
            )
            return 1
        if not corpus_fp:
            print(
                f"error: run_id '{run_id}': measurements.json missing "
                f"header.corpus_fingerprint",
                file=sys.stderr,
            )
            return 1

        loaded.append({
            "run_id": run_id,
            "group_key": group_key,
            "corpus_fingerprint": corpus_fp,
            "measurements": data,
        })

    if not loaded:
        print("error: no valid runs loaded", file=sys.stderr)
        return 1

    # --- GATE: all runs must share the same corpus_fingerprint ---
    fingerprints = {r["corpus_fingerprint"] for r in loaded}
    if len(fingerprints) > 1:
        details = "\n".join(
            f"  {r['run_id']}: {r['corpus_fingerprint']}" for r in loaded
        )
        print(
            f"error: corpus_fingerprint mismatch — all runs must come from the "
            f"same source corpus to be comparable.\n{details}",
            file=sys.stderr,
        )
        return 1

    # --- Keep latest run per group_key (lexical-max run_id) ---
    # Tie-break: run_ids are timestamp-prefixed → lexical-max = latest.
    best_by_group: dict[str, dict] = {}
    skipped: list[tuple[str, str]] = []  # (run_id, group_key)

    for entry in loaded:
        gk = entry["group_key"]
        if gk not in best_by_group:
            best_by_group[gk] = entry
        else:
            prior_run_id = best_by_group[gk]["run_id"]
            if entry["run_id"] > prior_run_id:
                skipped.append((prior_run_id, gk))
                best_by_group[gk] = entry
            else:
                skipped.append((entry["run_id"], gk))

    if skipped:
        for skipped_id, gk in skipped:
            print(
                f"[score] skipped {skipped_id} (superseded by later run for "
                f"group_key '{gk}')"
            )

    active_entries = list(best_by_group.values())

    # --- Build models list for borda_score ---
    # scored = {**processing["scored"], **graph["scored"]}
    # Key overlap check: processing scored keys:
    #   quarantine_rate, intervention_burden, latency
    # graph scored keys:
    #   link_resolution_rate
    # No overlap in current schema.
    models: list[dict] = []
    diagnostics_by_model: dict[str, dict] = {}

    for entry in active_entries:
        meas = entry["measurements"]
        processing = meas.get("processing", {})
        graph = meas.get("graph", {})

        p_scored = processing.get("scored", {}) or {}
        g_scored = graph.get("scored", {}) or {}
        merged_scored: dict[str, float | None] = {**p_scored, **g_scored}

        models.append({
            "group_key": entry["group_key"],
            "scored": merged_scored,
        })

        # Carry diagnostics + watched for human reading (not ranked)
        p_diag = processing.get("diagnostic", {}) or {}
        g_diag = graph.get("diagnostic", {}) or {}
        g_watched = graph.get("watched", {}) or {}
        combined_diag: dict[str, float | None] = {**p_diag, **g_diag, **g_watched}
        diagnostics_by_model[entry["group_key"]] = combined_diag

    # --- Run borda_score (equal weights — calibration is post-run-1) ---
    borda_result = borda_score(models, weights=None)

    # --- Write scorecard JSON ---
    scorecard_id = now_iso().replace(":", "-")
    payload: dict = {
        "scorecard_id": scorecard_id,
        "emitted_at": now_iso(),
        "corpus_fingerprint": next(iter(fingerprints)),
        "candidate_set": sorted(best_by_group.keys()),
        "borda": borda_result,
        "diagnostics_by_model": diagnostics_by_model,
        "run_ids_used": {gk: e["run_id"] for gk, e in best_by_group.items()},
    }

    scores_dir.mkdir(parents=True, exist_ok=True)
    out_path = scores_dir / f"{scorecard_id}.json"
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # --- Render table ---
    table = _render_score_table(borda_result, diagnostics_by_model)
    print(table)
    print(f"scorecard written: {out_path}")
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
