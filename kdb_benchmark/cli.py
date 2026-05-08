"""kdb-benchmark CLI — Tasks #30 / #31 / #22 + #33 v1 orchestrator.

Usage:
  kdb-benchmark --models haiku-4.5,sonnet-4.6 \\
                [--sources benchmark/sources] \\
                [--system-prompt-path PATH] \\
                [--runs-root benchmark/runs] \\
                [--scores-dir benchmark/scores] \\
                [--max-tokens 32768]

For each model_id in --models:
  1. runner.run_benchmark — compile every source (isolated state_root)
  2. scorer.score_run — derive a RunScore from the captured records
Then once across all models:
  3. scorer.score_runs — Borda-normalize M6/M7 + compute final_score
  4. scorecard.build_scorecard + write_scorecard — persist JSON + render table

Exit code: 0 on success, non-zero on user error / runtime failure.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kdb_benchmark.paths import BENCHMARK_DIR, MODELS_JSON, RUNS_DIR, SCORES_DIR, SOURCES_DIR
from kdb_benchmark.runner import run_benchmark
from kdb_benchmark.scorecard import build_scorecard, render_terminal, write_scorecard
from kdb_benchmark.scorer import score_run, score_runs


_DEFAULT_SYSTEM_PROMPT = Path.home() / "Obsidian" / "KDB" / "KDB-Compiler-System-Prompt.md"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kdb-benchmark", description=__doc__.split("\n")[0])
    p.add_argument(
        "--models",
        required=True,
        help="Comma-separated list of model_ids from kdb_benchmark/models.json.",
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
        help=f"Where the scorecard JSON is written (default: {SCORES_DIR})",
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
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    model_ids = [m.strip() for m in args.models.split(",") if m.strip()]
    if not model_ids:
        print("error: --models must be non-empty", file=sys.stderr)
        return 2

    # Task #36: trace is ALWAYS captured per-run and ALWAYS persisted to
    # disk. --verbose now controls only whether the trace also prints to
    # stdout after the scorecard. Disk path: <run_dir>/score_trace.txt.
    per_run_sinks: dict[str, list[str]] = {}
    per_run_dirs:  dict[str, Path]      = {}
    cross_run_sink: list[str] = []

    raw_run_scores = []
    try:
        for model_id in model_ids:
            print(f"[{model_id}] running benchmark...")
            run_id, state_root = run_benchmark(
                sources_dir=args.sources,
                model_id=model_id,
                runs_root=args.runs_root,
                system_prompt_path=args.system_prompt_path,
                max_tokens=args.max_tokens,
                registry_path=args.registry_path,
            )
            print(f"[{model_id}] scoring run {run_id}...")
            sink: list[str] = []
            per_run_sinks[run_id] = sink
            per_run_dirs[run_id]  = state_root.parent  # <runs_root>/<run_id>/
            run_score = score_run(
                state_root, run_id, model_id,
                registry_path=args.registry_path,
                trace_sink=sink,
            )
            raw_run_scores.append(run_score)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("aggregating Borda + final_score...")
    enriched = score_runs(raw_run_scores, trace_sink=cross_run_sink)

    # Persist each run's trace to <run_dir>/score_trace.txt — self-contained
    # (per-run section + cross-run Borda/final_score section).
    for run_id, run_dir in per_run_dirs.items():
        full = per_run_sinks[run_id] + [""] + cross_run_sink
        (run_dir / "score_trace.txt").write_text("\n".join(full) + "\n", encoding="utf-8")

    sc = build_scorecard(enriched)
    out_path = write_scorecard(sc, scores_dir=args.scores_dir)
    print(f"\nscorecard written: {out_path}\n")
    print(render_terminal(sc))

    # --verbose: per-measure trace prints AFTER the scorecard so the table
    # stays at the top of the user's terminal when they scroll up. The
    # trace is on disk regardless; this just mirrors it to the screen.
    if args.verbose:
        print("\n" + "=" * 100)
        print("Verbose trace (--verbose)")
        print("=" * 100)
        for sink in per_run_sinks.values():
            for line in sink:
                print(line)
        for line in cross_run_sink:
            print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
