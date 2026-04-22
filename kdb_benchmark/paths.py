"""paths — layout constants for the top-level `benchmark/` data directory.

The engine package (`kdb_benchmark/`) holds code; `benchmark/` holds data.
These constants are the single place that knows the physical layout so
runner/scorer/scorecard don't hard-code paths.

Layout (relative to repo root):
    benchmark/sources/   — curated markdown inputs fed to every model
    benchmark/truth/     — human-authored ground truth (Task #20)
    benchmark/runs/      — per-run outputs, run-NNN/ per invocation (gitignored)
    benchmark/scores/    — scorecards (Task #22)
    benchmark/inspect/   — ad-hoc failure snapshots (gitignored)
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = REPO_ROOT / "benchmark"

SOURCES_DIR = BENCHMARK_DIR / "sources"
TRUTH_DIR   = BENCHMARK_DIR / "truth"
RUNS_DIR    = BENCHMARK_DIR / "runs"
SCORES_DIR  = BENCHMARK_DIR / "scores"
INSPECT_DIR = BENCHMARK_DIR / "inspect"

MODELS_JSON = Path(__file__).resolve().parent / "models.json"
