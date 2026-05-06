"""Tests for kdb_benchmark.cli — end-to-end glue.

CLI is mostly orchestration glue (runner → scorer → scorecard). Tests use
monkeypatch on `kdb_benchmark.cli.run_benchmark` to avoid LLM calls; the
underlying runner is already covered by test_runner.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kdb_benchmark import cli, scorer
from kdb_benchmark.scorer import MeasureScore, RunScore


def _fake_runscore(model_id: str, m6_rate: float, m7_rate: float) -> RunScore:
    return RunScore(
        run_id=f"{model_id}-fake",
        model_id=model_id,
        provider="anthropic",
        model="m",
        n_attempted=2,
        s0=MeasureScore("S0", 2, 2, 1.0, 0.20),
        s1=MeasureScore("S1", 2, 2, 1.0, 0.0),
        s2=MeasureScore("S2", 2, 2, 1.0, 0.0),
        s3=MeasureScore("S3", 2, 2, 1.0, 0.0),
        measures={
            "M1": MeasureScore("M1", 1, 1, 1.0, 0.20),
            "M2": MeasureScore("M2", 1, 1, 1.0, 0.05),
            "M3": MeasureScore("M3", 1, 1, 1.0, 0.05),
            "M4": MeasureScore("M4", 2, 2, 1.0, 0.15),
            "M5": MeasureScore("M5", 1, 1, 1.0, 0.05),
            "M6": MeasureScore("M6", 0.001, 1000, m6_rate, 0.15),
            "M7": MeasureScore("M7", 2000, 1000, m7_rate, 0.15),
        },
        diagnostics={
            "retry_load":              MeasureScore("retry_load", 0, 4, 0.0, 0.0),
            "token_overrun_rate":      MeasureScore("token_overrun_rate", 0, 2, 0.0, 0.0),
            "pages_per_1k_source_words": MeasureScore("pages_per_1k_source_words", 2, 2000, 1.0, 0.0),
        },
        m6_borda=None, m7_borda=None, final_score=None,
    )


@pytest.fixture
def fake_corpus(tmp_path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "01.md").write_text("# Source 1\n")
    return sources


@pytest.fixture
def fake_prompt(tmp_path):
    p = tmp_path / "prompt.md"
    p.write_text("# fake\n")
    return p


@pytest.fixture
def patched_runner_and_scorer(monkeypatch, tmp_path):
    """Mock run_benchmark + score_run so the CLI's orchestration is
    exercised without LLM calls or real file IO from compile_one."""

    fake_run_states: dict[str, Path] = {}

    def fake_run_benchmark(*, sources_dir, model_id, runs_root, system_prompt_path, **kwargs):
        run_id = f"{model_id}-fake"
        state_root = runs_root / run_id / "state"
        state_root.mkdir(parents=True, exist_ok=True)
        fake_run_states[model_id] = state_root
        return run_id, state_root

    def fake_score_run(state_root, run_id, model_id, **kwargs):
        # Return a synthesized RunScore keyed off model_id
        rates = {
            "haiku-4.5": (0.001, 2000.0),
            "sonnet-4.6": (0.018, 3500.0),
        }
        m6, m7 = rates.get(model_id, (0.005, 2500.0))
        return _fake_runscore(model_id, m6, m7)

    monkeypatch.setattr("kdb_benchmark.cli.run_benchmark", fake_run_benchmark)
    monkeypatch.setattr("kdb_benchmark.cli.score_run", fake_score_run)
    return fake_run_states


# ---------------------------------------------------------------------------

class TestCLI:
    def test_main_runs_end_to_end_and_writes_scorecard(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer
    ):
        scores_dir = tmp_path / "scores"
        runs_root = tmp_path / "runs"
        rc = cli.main([
            "--models", "haiku-4.5,sonnet-4.6",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(runs_root),
            "--scores-dir", str(scores_dir),
        ])
        assert rc == 0
        # Scorecard JSON exists
        json_files = list(scores_dir.glob("*.json"))
        assert len(json_files) == 1
        data = json.loads(json_files[0].read_text())
        assert sorted(data["candidate_set"]) == ["haiku-4.5", "sonnet-4.6"]
        # Models sorted by final_score desc — haiku faster + cheaper → wins
        assert data["models"][0]["model_id"] == "haiku-4.5"
        assert data["models"][1]["model_id"] == "sonnet-4.6"

    def test_main_prints_terminal_table_to_stdout(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer, capsys
    ):
        cli.main([
            "--models", "haiku-4.5,sonnet-4.6",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(tmp_path / "scores"),
        ])
        captured = capsys.readouterr()
        assert "haiku-4.5" in captured.out
        assert "sonnet-4.6" in captured.out
        assert "FINAL" in captured.out
        assert "candidate" in captured.out.lower()  # disclaimer

    def test_main_returns_nonzero_on_unknown_model_id(
        self, tmp_path, fake_corpus, fake_prompt, monkeypatch
    ):
        # Don't patch run_benchmark — let it raise the real ValueError
        rc = cli.main([
            "--models", "no-such-model",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(tmp_path / "scores"),
        ])
        assert rc != 0
