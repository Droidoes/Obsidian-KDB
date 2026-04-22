"""Tests for kdb_benchmark.paths — layout constants stay stable."""
from __future__ import annotations

from kdb_benchmark import paths


def test_benchmark_dir_is_repo_sibling_of_package() -> None:
    assert paths.BENCHMARK_DIR.parent == paths.REPO_ROOT
    assert paths.BENCHMARK_DIR.name == "benchmark"


def test_data_subdirs_are_under_benchmark_dir() -> None:
    for sub in (paths.SOURCES_DIR, paths.TRUTH_DIR, paths.RUNS_DIR,
                paths.SCORES_DIR, paths.INSPECT_DIR):
        assert sub.parent == paths.BENCHMARK_DIR


def test_models_json_is_inside_package() -> None:
    assert paths.MODELS_JSON.name == "models.json"
    assert paths.MODELS_JSON.parent.name == "kdb_benchmark"
