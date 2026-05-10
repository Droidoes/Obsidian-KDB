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
        m6_borda=None, m7_borda=None,
        final_score_pre_penalty=None, penalty=0.0, final_score=None,
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
        # Task #46: 3-tuple return — (run_id, state_root, compile_metrics)
        compile_metrics = {
            "compile_seconds": 1.5,
            "n_sources": 1,
            "n_source_words": 250,
        }
        return run_id, state_root, compile_metrics

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
            "--models", "haiku-4.5",
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
        assert data["candidate_set"] == ["haiku-4.5"]
        assert data["models"][0]["model_id"] == "haiku-4.5"
        # Final scorecard auto-written under final/ (Task #42)
        final_jsons = list((scores_dir / "final").glob("*.json"))
        assert len(final_jsons) == 1

    def test_main_prints_terminal_table_to_stdout(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer, capsys
    ):
        cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(tmp_path / "scores"),
        ])
        captured = capsys.readouterr()
        assert "haiku-4.5" in captured.out
        assert "FINAL" in captured.out
        assert "candidate" in captured.out.lower()  # disclaimer

    def test_main_persists_score_trace_per_run_without_verbose(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer
    ):
        """Task #36 — every run dir must contain a score_trace.txt with
        per-run + cross-run sections, regardless of --verbose."""
        runs_root = tmp_path / "runs"
        cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(runs_root),
            "--scores-dir", str(tmp_path / "scores"),
        ])
        trace_path = runs_root / "haiku-4.5-fake" / "score_trace.txt"
        assert trace_path.exists(), f"missing {trace_path}"
        content = trace_path.read_text()
        # Per-run section: marker line from fake_score_run
        assert "[verbose] fake S0 trace for haiku-4.5" in content
        # Cross-run section: Borda + final_score lines from real score_runs
        assert "score_runs: candidate_set=" in content
        assert "final_score_pre_penalty=" in content

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
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(scores_dir),
        ])
        [final_json] = list((scores_dir / "final").glob("*.json"))
        d = json.loads(final_json.read_text())
        for entry in d["models"]:
            assert "source_scorecard_id" in entry


# ---------- Dropped Models (Task #44) ----------


def _write_registry(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries), encoding="utf-8")


class TestCLIDroppedModelsGuard:
    def test_main_errors_when_selected_model_is_dropped(
        self, tmp_path, fake_corpus, fake_prompt, capsys
    ):
        """Fail-fast guard (Task #44 + #46): firing a dropped model exits
        with code 2 BEFORE any runner invocation (no API cost wasted).
        Single-model only after #46 — there's no "mixed selection" path."""
        registry_path = tmp_path / "models.json"
        _write_registry(registry_path, [
            {"id": "haiku-4.5", "provider": "anthropic", "model": "m",
             "price_in": 1.0, "price_out": 5.0,
             "dropped": True, "dropped_reason": "test"},
        ])
        rc = cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(tmp_path / "scores"),
            "--registry-path", str(registry_path),
        ])
        assert rc == 2
        captured = capsys.readouterr()
        assert "is marked dropped in registry" in captured.err


class TestCLIDroppedModelsMergePartition:
    def test_merge_partitions_dropped_via_registry(self, tmp_path):
        """Direct unit test of `_merge_with_prior_final`. New per-run runs
        for two models — one active in registry, one dropped. Merge must
        route them to active vs dropped subsets and recompute Borda over
        active only (forced None for dropped)."""
        from kdb_benchmark.registry import ModelEntry
        scores_dir = tmp_path / "scores"
        scores_dir.mkdir()

        registry = [
            ModelEntry(id="haiku-4.5", provider="anthropic", model="m",
                       price_in=1.0, price_out=5.0),
            ModelEntry(id="sonnet-4.6", provider="anthropic", model="m",
                       price_in=3.0, price_out=15.0,
                       dropped=True, dropped_reason="ex-broken"),
        ]
        new_runs = [
            _fake_runscore("haiku-4.5", m6_rate=0.001, m7_rate=2000.0),
            _fake_runscore("sonnet-4.6", m6_rate=0.018, m7_rate=3500.0),
        ]
        active, dropped, source_map, dropped_reasons = cli._merge_with_prior_final(
            new_runs, "fake-scorecard-id",
            scores_dir=scores_dir,
            registry_entries=registry,
        )
        assert {r.model_id for r in active} == {"haiku-4.5"}
        assert {r.model_id for r in dropped} == {"sonnet-4.6"}
        # Active gets Borda (1 candidate → degenerate but Borda computes)
        for r in active:
            assert r.m6_borda is not None
            assert r.final_score is not None
        # Dropped have Borda nulled
        for r in dropped:
            assert r.m6_borda is None
            assert r.m7_borda is None
            assert r.final_score is None
        assert dropped_reasons == {"sonnet-4.6": "ex-broken"}
        # source_map covers both
        assert source_map["haiku-4.5"] == "fake-scorecard-id"
        assert source_map["sonnet-4.6"] == "fake-scorecard-id"

    def test_merge_carries_prior_dropped_through_when_new_run_doesnt_touch(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer
    ):
        """End-to-end: Run #1 fires gemini-3-flash-preview while it's
        active (registry says active). Then registry flips gemini to
        dropped. Run #2 fires haiku — gemini is carried through from the
        prior final into the new dropped subset (registry-driven, not
        scorecard-snapshot-driven)."""
        registry_path = tmp_path / "models.json"
        scores_dir = tmp_path / "scores"
        runs_root = tmp_path / "runs"

        # Registry v1: gemini active
        _write_registry(registry_path, [
            {"id": "haiku-4.5", "provider": "anthropic", "model": "m",
             "price_in": 1.0, "price_out": 5.0},
            {"id": "gemini-3-flash-preview", "provider": "gemini", "model": "g",
             "price_in": 0.5, "price_out": 3.0},
        ])
        # Run #1 — gemini active
        rc = cli.main([
            "--models", "gemini-3-flash-preview",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(runs_root),
            "--scores-dir", str(scores_dir),
            "--registry-path", str(registry_path),
        ])
        assert rc == 0
        d1 = json.loads(sorted((scores_dir / "final").glob("*.json"))[-1].read_text())
        assert sorted(d1["candidate_set"]) == ["gemini-3-flash-preview"]
        assert d1["dropped_models"] == []

        # Registry v2: flip gemini to dropped
        _write_registry(registry_path, [
            {"id": "haiku-4.5", "provider": "anthropic", "model": "m",
             "price_in": 1.0, "price_out": 5.0},
            {"id": "gemini-3-flash-preview", "provider": "gemini", "model": "g",
             "price_in": 0.5, "price_out": 3.0,
             "dropped": True, "dropped_reason": "flipped post-run"},
        ])
        # Run #2 — fire haiku (different model). Merge inherits gemini
        # from prior final, but registry says it's now dropped → routes
        # to dropped subset.
        rc = cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(runs_root),
            "--scores-dir", str(scores_dir),
            "--registry-path", str(registry_path),
        ])
        assert rc == 0
        d2 = json.loads(sorted((scores_dir / "final").glob("*.json"))[-1].read_text())
        assert sorted(d2["candidate_set"]) == ["haiku-4.5"]
        active_ids = [m["model_id"] for m in d2["models"]]
        dropped_ids = [m["model_id"] for m in d2["dropped_models"]]
        assert active_ids == ["haiku-4.5"]
        assert dropped_ids == ["gemini-3-flash-preview"]
        assert d2["dropped_models"][0]["drop_reason"] == "flipped post-run"


# ---------- Task #46 — single-model + run metadata + progress output ----------


class TestCLISingleModelEnforcement:
    def test_main_rejects_comma_separated_models(
        self, tmp_path, fake_corpus, fake_prompt, capsys
    ):
        """Task #46: --models must be a single model_id. Comma-separated
        invocations are rejected with code 2 and a guidance message."""
        rc = cli.main([
            "--models", "haiku-4.5,sonnet-4.6",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(tmp_path / "scores"),
        ])
        assert rc == 2
        err = capsys.readouterr().err
        assert "single model_id" in err


class TestCLIRunMetadataPersistence:
    def test_per_run_scorecard_carries_run_config_and_run_timing(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer
    ):
        """Task #46: per-run scorecard JSON has populated `run_config` and
        `run_timing` so the artifact is self-describing."""
        scores_dir = tmp_path / "scores"
        cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(scores_dir),
            "--max-tokens", "24000",
        ])
        [run_json] = list((scores_dir / "runs").glob("*.json"))
        d = json.loads(run_json.read_text())
        # run_config: at least max_tokens + sources_dir + n_sources + n_source_words
        assert d["run_config"]["max_tokens"] == 24000
        assert d["run_config"]["sources_dir"] == str(fake_corpus)
        assert d["run_config"]["n_sources"] == 1  # fake_corpus has 1 .md file
        assert "n_source_words" in d["run_config"]
        # When the model is in the registry, provider/model/ctx/prices land too
        assert d["run_config"]["provider"] == "anthropic"
        # run_timing: compile + score + total seconds
        assert "compile_seconds" in d["run_timing"]
        assert "score_seconds" in d["run_timing"]
        assert "total_seconds" in d["run_timing"]

    def test_final_scorecard_has_empty_run_metadata(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer
    ):
        """Final scorecards aggregate across many fires — they intentionally
        leave run_config/run_timing empty (no single config/timing applies)."""
        scores_dir = tmp_path / "scores"
        cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(scores_dir),
        ])
        [final_json] = list((scores_dir / "final").glob("*.json"))
        d = json.loads(final_json.read_text())
        assert d["run_config"] == {}
        assert d["run_timing"] == {}


class TestCLIProgressOutput:
    def test_config_header_printed_at_start(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer, capsys
    ):
        """Task #46: a config header line names provider/model, ctx,
        --max-tokens, and prices BEFORE the runner produces output —
        so the user knows exactly what's about to fire."""
        cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(tmp_path / "scores"),
            "--max-tokens", "24000",
        ])
        out = capsys.readouterr().out
        assert "[haiku-4.5] config:" in out
        assert "anthropic/claude-haiku-4-5-20251001" in out
        assert "--max-tokens=24000" in out
        assert "[haiku-4.5] sources:" in out

    def test_kpi_summary_and_total_time_printed(
        self, tmp_path, fake_corpus, fake_prompt, patched_runner_and_scorer, capsys
    ):
        """Task #46: end-of-run summary line(s) carry per-measure KPIs +
        total wall time so users see the headline outcome without scrolling
        to find it in the table."""
        cli.main([
            "--models", "haiku-4.5",
            "--sources", str(fake_corpus),
            "--system-prompt-path", str(fake_prompt),
            "--runs-root", str(tmp_path / "runs"),
            "--scores-dir", str(tmp_path / "scores"),
        ])
        out = capsys.readouterr().out
        assert "[haiku-4.5] KPIs:" in out
        # Single-shot scorecard line includes S0, M1..M5, M6_raw, M7_raw
        assert "S0=" in out
        assert "M5=" in out
        assert "M6_raw=" in out
        assert "M7_raw=" in out
        # Timing footer
        assert "[haiku-4.5] compile complete:" in out
        assert "[haiku-4.5] score complete:" in out
        assert "[haiku-4.5] total run time:" in out
