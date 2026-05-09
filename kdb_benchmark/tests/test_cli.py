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
        # Append a marker line to the trace_sink (Task #36 — verifies the
        # CLI persists per-run trace lines to <run_dir>/score_trace.txt
        # regardless of --verbose).
        sink = kwargs.get("trace_sink")
        if sink is not None:
            sink.append(f"[verbose] fake S0 trace for {model_id}")
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
        # Per-run scorecard lands under runs/ (Task #42)
        run_jsons = list((scores_dir / "runs").glob("*.json"))
        assert len(run_jsons) == 1
        data = json.loads(run_jsons[0].read_text())
        assert sorted(data["candidate_set"]) == ["haiku-4.5", "sonnet-4.6"]
        # Models sorted by final_score desc — haiku faster + cheaper → wins
        assert data["models"][0]["model_id"] == "haiku-4.5"
        assert data["models"][1]["model_id"] == "sonnet-4.6"
        # Final scorecard auto-written under final/ (Task #42)
        final_jsons = list((scores_dir / "final").glob("*.json"))
        assert len(final_jsons) == 1

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

    def test_main_persists_score_trace_per_run_without_verbose(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer
    ):
        """Task #36 — every run dir must contain a score_trace.txt with
        per-run + cross-run sections, regardless of --verbose."""
        runs_root = tmp_path / "runs"
        cli.main([
            "--models", "haiku-4.5,sonnet-4.6",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(runs_root),
            "--scores-dir", str(tmp_path / "scores"),
        ])
        for model_id in ("haiku-4.5", "sonnet-4.6"):
            trace_path = runs_root / f"{model_id}-fake" / "score_trace.txt"
            assert trace_path.exists(), f"missing {trace_path}"
            content = trace_path.read_text()
            # Per-run section: marker line from fake_score_run
            assert f"[verbose] fake S0 trace for {model_id}" in content
            # Cross-run section: Borda + final_score lines from real score_runs
            assert "score_runs: candidate_set=" in content
            assert "final_score=" in content

    def test_main_verbose_flag_mirrors_trace_to_stdout(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer, capsys
    ):
        """--verbose mirrors the on-disk trace to stdout (after the scorecard)."""
        cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(tmp_path / "scores"),
            "--verbose",
        ])
        out = capsys.readouterr().out
        assert "Verbose trace (--verbose)" in out
        assert "[verbose] fake S0 trace for haiku-4.5" in out

    def test_main_without_verbose_does_not_print_trace_to_stdout(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer, capsys
    ):
        """Without --verbose the trace is only on disk, not on stdout."""
        cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(tmp_path / "scores"),
        ])
        out = capsys.readouterr().out
        assert "Verbose trace" not in out
        assert "[verbose] fake S0 trace" not in out

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


# ---------------------------------------------------------------------------
# Task #42 — cross-run scorecard auto-merge
# ---------------------------------------------------------------------------

@pytest.fixture
def monotonic_now_iso(monkeypatch):
    """now_iso() has second precision; tests that fire two CLI invocations
    back-to-back would collide on the same timestamp and overwrite the
    prior final scorecard. Patch the scorecard module's now_iso to return
    a monotonically-advancing fake."""
    counter = {"n": 0}

    def _fake_now() -> str:
        counter["n"] += 1
        # Use distinct seconds so lexical sort (filename) preserves order.
        return f"2026-05-08T12:00:{counter['n']:02d}-04:00"

    monkeypatch.setattr("kdb_benchmark.scorecard.now_iso", _fake_now)


class TestCLICrossRunMerge:
    def test_no_merge_skips_final_write(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer
    ):
        scores_dir = tmp_path / "scores"
        cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(scores_dir),
            "--no-merge",
        ])
        # runs/ written, final/ untouched
        assert list((scores_dir / "runs").glob("*.json"))
        assert not (scores_dir / "final").exists()

    def test_single_model_per_run_filename_carries_model_id(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer
    ):
        scores_dir = tmp_path / "scores"
        cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(scores_dir),
            "--no-merge",
        ])
        [run_json] = list((scores_dir / "runs").glob("*.json"))
        assert run_json.stem.endswith("-haiku-4.5")

    def test_subsequent_run_merges_into_new_final_keeping_prior_models(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer, monotonic_now_iso
    ):
        """Run #1 with haiku, Run #2 with gpt — final after Run #2 must
        carry BOTH models (combine semantics for the new model)."""
        scores_dir = tmp_path / "scores"
        runs_root = tmp_path / "runs"
        # Run 1
        cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(runs_root),
            "--scores-dir", str(scores_dir),
        ])
        finals_after_1 = sorted((scores_dir / "final").glob("*.json"))
        assert len(finals_after_1) == 1
        d1 = json.loads(finals_after_1[0].read_text())
        assert sorted(d1["candidate_set"]) == ["haiku-4.5"]

        # Run 2 — different model
        cli.main([
            "--models", "gpt-5.4-mini",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(runs_root),
            "--scores-dir", str(scores_dir),
        ])
        finals_after_2 = sorted((scores_dir / "final").glob("*.json"))
        # Versioned: prior final preserved, new final added
        assert len(finals_after_2) == 2
        latest = json.loads(finals_after_2[-1].read_text())
        assert sorted(latest["candidate_set"]) == ["gpt-5.4-mini", "haiku-4.5"]

    def test_subsequent_run_replaces_existing_model_in_final(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer, monotonic_now_iso
    ):
        """Run #1 with haiku, Run #2 with haiku again — new haiku entry
        replaces the prior one (latest measurement wins)."""
        scores_dir = tmp_path / "scores"
        runs_root = tmp_path / "runs"
        cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(runs_root),
            "--scores-dir", str(scores_dir),
        ])
        cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(runs_root),
            "--scores-dir", str(scores_dir),
        ])
        finals = sorted((scores_dir / "final").glob("*.json"))
        latest = json.loads(finals[-1].read_text())
        # Still just one model — replace, not duplicate
        assert sorted(latest["candidate_set"]) == ["haiku-4.5"]
        # Source pointer points at the latest per-run scorecard, not the first
        run_jsons = sorted((scores_dir / "runs").glob("*.json"))
        latest_per_run_id = run_jsons[-1].stem
        assert latest["models"][0]["source_scorecard_id"] == latest_per_run_id

    def test_final_entries_carry_source_scorecard_id(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer
    ):
        scores_dir = tmp_path / "scores"
        cli.main([
            "--models", "haiku-4.5,sonnet-4.6",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(scores_dir),
        ])
        [final_json] = list((scores_dir / "final").glob("*.json"))
        d = json.loads(final_json.read_text())
        for entry in d["models"]:
            assert "source_scorecard_id" in entry
