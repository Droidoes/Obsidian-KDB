"""Tests for kdb_benchmark.runner — Task #30 isolation-contract orchestrator.

The runner invokes `compile_one` directly (NOT the production kdb-compile
pipeline) once per (source, model). These tests monkeypatch compile_one so
they verify orchestration only — not LLM interaction.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from kdb_benchmark import runner
from kdb_compiler.types import ContextSnapshot


@pytest.fixture
def fake_corpus(tmp_path: Path) -> Path:
    """Build a tiny benchmark/sources/-shaped directory."""
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "01-foo.md").write_text("# Foo\n\nbody.\n")
    (sources / "02-bar.md").write_text("# Bar\n\nbody.\n")
    # Distractor: meta.yaml file should be skipped by source globber
    (sources / "01-foo.meta.yaml").write_text("license: x\n")
    return sources


@pytest.fixture
def fake_system_prompt(tmp_path: Path) -> Path:
    """Build a stand-in for KDB-Compiler-System-Prompt.md."""
    p = tmp_path / "fake-prompt.md"
    p.write_text("# Fake KDB Compiler System Prompt\n")
    return p


@pytest.fixture
def runs_root(tmp_path: Path) -> Path:
    return tmp_path / "runs"


@pytest.fixture
def patched_compile_one(monkeypatch):
    """Monkeypatch compile_one to capture invocation args without calling the LLM."""
    captured = []

    def fake_compile_one(job, *, vault_root, state_root, ctx, provider, model, max_tokens, **kwargs):
        captured.append({
            "job": job,
            "vault_root": vault_root,
            "state_root": state_root,
            "ctx": ctx,
            "provider": provider,
            "model": model,
            "max_tokens": max_tokens,
            "env_capture_full": os.environ.get("KDB_RESP_STATS_CAPTURE_FULL"),
        })
        return (None, [], [], None)

    monkeypatch.setattr("kdb_benchmark.runner.compile_one", fake_compile_one)
    return captured


# ---------------------------------------------------------------------------

class TestRunnerEntryPoint:
    def test_run_benchmark_returns_run_id_and_state_root(
        self, fake_corpus, fake_system_prompt, runs_root, patched_compile_one
    ):
        run_id, state_root, _metrics = runner.run_benchmark(
            sources_dir=fake_corpus,
            model_id="haiku-4.5",
            runs_root=runs_root,
            system_prompt_path=fake_system_prompt,
        )
        assert run_id.startswith("haiku-4.5-")
        assert state_root == runs_root / run_id / "state"
        assert state_root.exists()

    def test_run_benchmark_invokes_compile_one_per_md_source(
        self, fake_corpus, fake_system_prompt, runs_root, patched_compile_one
    ):
        runner.run_benchmark(
            sources_dir=fake_corpus,
            model_id="haiku-4.5",
            runs_root=runs_root,
            system_prompt_path=fake_system_prompt,
        )
        assert len(patched_compile_one) == 2  # only the 2 .md files
        # Task #34: source_ids carry the derived path-prefix so they match
        # the schema validator's pattern. fake_corpus is tmp_path/sources/
        # → prefix is everything up to and including "/sources" with a leading
        # slash stripped.
        expected_prefix = runner._derive_source_id_prefix(fake_corpus)
        source_ids = sorted(c["job"].source_id for c in patched_compile_one)
        assert source_ids == [
            f"{expected_prefix}/01-foo.md",
            f"{expected_prefix}/02-bar.md",
        ]

    def test_run_benchmark_skips_meta_yaml_files(
        self, fake_corpus, fake_system_prompt, runs_root, patched_compile_one
    ):
        runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        # No CompileJob should be built for the .meta.yaml file
        for c in patched_compile_one:
            assert not c["job"].source_id.endswith(".meta.yaml")


class TestSourceIdPrefix:
    """Task #34 + #41 — runner derives a path-prefix from sources_dir and
    constructs source_ids as `<prefix>/<filename>`. Post-#41 the prefix
    is no longer threaded to compile_one (the LLM contract no longer
    constrains source_id format); the runner uses the prefix only when
    constructing each job's source_id for downstream artifacts."""

    def test_derive_source_id_prefix_relative(self):
        assert runner._derive_source_id_prefix(Path("benchmark/sources")) == "benchmark/sources"

    def test_derive_source_id_prefix_strips_leading_dot_slash(self):
        assert runner._derive_source_id_prefix(Path("./benchmark/sources/")) == "benchmark/sources"

    def test_derive_source_id_prefix_absolute(self):
        assert runner._derive_source_id_prefix(Path("/tmp/kdb-smoke/")) == "tmp/kdb-smoke"

    def test_derive_source_id_prefix_strips_trailing_slash(self):
        assert runner._derive_source_id_prefix(Path("benchmark/sources/")) == "benchmark/sources"

    def test_each_job_source_id_starts_with_derived_prefix(
        self, fake_corpus, fake_system_prompt, runs_root, patched_compile_one
    ):
        """Source_ids built by the runner must use `<derived-prefix>/<filename>`."""
        runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        expected_prefix = runner._derive_source_id_prefix(fake_corpus)
        for c in patched_compile_one:
            assert c["job"].source_id.startswith(f"{expected_prefix}/")

    def test_run_benchmark_uses_registry_provider_model_for_id(
        self, fake_corpus, fake_system_prompt, runs_root, patched_compile_one
    ):
        runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        for c in patched_compile_one:
            assert c["provider"] == "anthropic"
            assert c["model"] == "claude-haiku-4-5-20251001"

    def test_run_benchmark_raises_on_unknown_model_id(
        self, fake_corpus, fake_system_prompt, runs_root, patched_compile_one
    ):
        with pytest.raises(ValueError, match="not found in registry"):
            runner.run_benchmark(
                sources_dir=fake_corpus, model_id="no-such-model",
                runs_root=runs_root, system_prompt_path=fake_system_prompt,
            )

    def test_run_benchmark_raises_on_missing_sources_dir(
        self, tmp_path, fake_system_prompt, runs_root, patched_compile_one
    ):
        """Task #40: a non-existent sources_dir must fail loud at runner
        start with a clear message naming the path. No side effects (no
        run dir, no vault snapshot) should be created."""
        missing = tmp_path / "does-not-exist"
        with pytest.raises(FileNotFoundError, match=str(missing)):
            runner.run_benchmark(
                sources_dir=missing, model_id="haiku-4.5",
                runs_root=runs_root, system_prompt_path=fake_system_prompt,
            )
        assert not runs_root.exists()
        assert len(patched_compile_one) == 0

    def test_run_benchmark_raises_on_empty_sources_dir(
        self, tmp_path, fake_system_prompt, runs_root, patched_compile_one
    ):
        """Task #40: a sources_dir that exists but has no .md files must
        also fail loud (typo / wrong dir). Companion .meta.yaml-only dirs
        without their .md siblings hit this same path."""
        empty = tmp_path / "empty-sources"
        empty.mkdir()
        (empty / "stray.meta.yaml").write_text("license: x\n")  # not .md
        with pytest.raises(ValueError, match="no .md files"):
            runner.run_benchmark(
                sources_dir=empty, model_id="haiku-4.5",
                runs_root=runs_root, system_prompt_path=fake_system_prompt,
            )
        assert not runs_root.exists()
        assert len(patched_compile_one) == 0

    def test_run_benchmark_uses_empty_context_snapshot(
        self, fake_corpus, fake_system_prompt, runs_root, patched_compile_one
    ):
        """Round 4 [3]: every benchmark source compiled cold for determinism."""
        runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        for c in patched_compile_one:
            snap = c["job"].context_snapshot
            assert isinstance(snap, ContextSnapshot)
            assert snap.pages == []

    def test_run_benchmark_sets_capture_full_env_during_compile(
        self, fake_corpus, fake_system_prompt, runs_root, patched_compile_one
    ):
        """Phase 3 §3: benchmark mode mandates KDB_RESP_STATS_CAPTURE_FULL=1.
        Runner sets it before calling compile_one."""
        runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        for c in patched_compile_one:
            assert c["env_capture_full"] == "1"

    def test_run_benchmark_copies_system_prompt_to_benchmark_vault_stub(
        self, fake_corpus, fake_system_prompt, runs_root, patched_compile_one
    ):
        run_id, state_root, _metrics = runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        # vault_root sits next to state_root under run_dir; system prompt lives there
        run_dir = state_root.parent
        copied = run_dir / "vault" / "KDB" / "KDB-Compiler-System-Prompt.md"
        assert copied.exists()
        assert "Fake KDB Compiler System Prompt" in copied.read_text()

    def test_run_benchmark_passes_benchmark_state_root_to_compile_one(
        self, fake_corpus, fake_system_prompt, runs_root, patched_compile_one
    ):
        """Isolation: state_root must be under runs_root/<run_id>/, NEVER
        the user's live vault state."""
        run_id, state_root, _metrics = runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        for c in patched_compile_one:
            assert c["state_root"] == state_root
            assert str(c["state_root"]).startswith(str(runs_root))


# ---------------------------------------------------------------------------
# Task #46 — per-source progress + compile_metrics return
# ---------------------------------------------------------------------------

import json as _json


@pytest.fixture
def patched_compile_one_writing_records(monkeypatch):
    """Variant of patched_compile_one that also writes a fake
    RespStatsRecord JSON file — mimics compile_one's `finally`-block
    side effect — so the runner can read tokens/latency/stop_reason for
    its per-source progress line.

    Returns a callable `set_record(stop_reason, in_tok, out_tok, latency_ms,
    source_words)` so individual tests can vary the record content per call.
    """
    from kdb_compiler.resp_stats_writer import safe_source_id

    record_template = {
        "stop_reason": "stop",
        "input_tokens": 1234,
        "output_tokens": 567,
        "latency_ms": 8200,
        "source_words": 250,
    }

    def fake_compile_one(job, *, vault_root, state_root, ctx, provider, model, max_tokens, **kwargs):
        # Mimic the resp_stats writer path (Task #29 via Task #28 fields).
        rec_dir = state_root / "llm_resp" / ctx.run_id
        rec_dir.mkdir(parents=True, exist_ok=True)
        rec = dict(record_template)
        rec_path = rec_dir / f"{safe_source_id(job.source_id)}.json"
        rec_path.write_text(_json.dumps(rec), encoding="utf-8")
        return (None, [], [], None)

    def set_record(**kwargs):
        record_template.update(kwargs)

    monkeypatch.setattr("kdb_benchmark.runner.compile_one", fake_compile_one)
    return set_record


class TestRunBenchmarkProgressOutput:
    def test_compile_metrics_returned(
        self, fake_corpus, fake_system_prompt, runs_root, patched_compile_one_writing_records
    ):
        """Task #46: third return value carries compile_seconds, n_sources,
        n_source_words. n_source_words is summed from per-source records."""
        _, _, metrics = runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        assert set(metrics.keys()) == {"compile_seconds", "n_sources", "n_source_words"}
        assert metrics["n_sources"] == 2  # fake_corpus has 2 .md files
        assert metrics["n_source_words"] == 500  # 2 sources × 250 words each
        assert isinstance(metrics["compile_seconds"], (int, float))
        assert metrics["compile_seconds"] >= 0

    def test_per_source_progress_line_printed(
        self, fake_corpus, fake_system_prompt, runs_root,
        patched_compile_one_writing_records, capsys,
    ):
        """Task #46: every completed compile_one prints a progress line
        with ordinal, filename, latency, and token counts."""
        runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        out = capsys.readouterr().out
        # Two sources → two progress lines
        assert "[haiku-4.5]   1/2" in out
        assert "[haiku-4.5]   2/2" in out
        # Token + latency shape (format: right-justified width 6)
        assert "in=  1234" in out
        assert "out=   567" in out
        assert "8.2s" in out  # 8200ms → 8.2s

    def test_truncation_warning_emitted_when_stop_reason_length(
        self, fake_corpus, fake_system_prompt, runs_root,
        patched_compile_one_writing_records, capsys,
    ):
        """Task #46: when a per-source record's stop_reason is `length` or
        `max_tokens`, the progress line gets a `⚠ stop=length` warning —
        surfaces truncation IMMEDIATELY, ahead of scorer-side detection."""
        patched_compile_one_writing_records(stop_reason="length")
        runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        out = capsys.readouterr().out
        assert "⚠ stop=length" in out

    def test_no_warning_for_clean_stop(
        self, fake_corpus, fake_system_prompt, runs_root,
        patched_compile_one_writing_records, capsys,
    ):
        """No ⚠ when stop_reason is the normal `stop`."""
        runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        out = capsys.readouterr().out
        assert "⚠" not in out


# ---------------------------------------------------------------------------
# Task #49 — live progress timer during compile_one
# ---------------------------------------------------------------------------


class TestRunBenchmarkLiveProgress:
    def test_starting_line_printed_before_compile_one(
        self, fake_corpus, fake_system_prompt, runs_root,
        patched_compile_one_writing_records, capsys,
    ):
        """Task #49: every source emits a `⏳ starting...` line BEFORE
        compile_one is invoked — gives liveness signal even when the LLM
        call is about to take 10+ minutes."""
        runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        out = capsys.readouterr().out
        # Two sources → two starting lines
        assert out.count("⏳ starting...") == 2
        # Starting line appears BEFORE the corresponding completion line
        starting_idx = out.find("1/2")
        # Find the completion line for source 1 (has "in=" / "out=")
        completion_idx = out.find("in=  1234")
        assert starting_idx < completion_idx

    def test_periodic_ticker_emits_elapsed_lines(self, capsys):
        """Direct unit test of `_periodic_progress_ticker` — start with a
        tiny interval, let it tick a few times, then signal stop and
        verify multiple `⏳ Xs elapsed` lines were printed."""
        import threading
        stop_event = threading.Event()
        started_at = time.monotonic()
        ticker = threading.Thread(
            target=runner._periodic_progress_ticker,
            args=("[test]   1/1  fake.md", stop_event, started_at, 0.05),
            daemon=True,
        )
        ticker.start()
        time.sleep(0.2)
        stop_event.set()
        ticker.join(timeout=1)
        out = capsys.readouterr().out
        # 0.2s @ 0.05s interval → at least 2 ticks (allowing jitter)
        assert out.count("⏳") >= 2
        assert "elapsed" in out

    def test_periodic_ticker_emits_no_lines_when_stopped_immediately(self, capsys):
        """If compile_one returns in less than `interval` seconds, the
        ticker should fire zero times (Event.wait returns True before
        the first interval elapses)."""
        import threading
        stop_event = threading.Event()
        started_at = time.monotonic()
        ticker = threading.Thread(
            target=runner._periodic_progress_ticker,
            args=("[test]   1/1  fake.md", stop_event, started_at, 5.0),
            daemon=True,
        )
        ticker.start()
        stop_event.set()  # stop immediately
        ticker.join(timeout=1)
        out = capsys.readouterr().out
        assert "⏳ " not in out  # no elapsed lines emitted
        assert "elapsed" not in out
