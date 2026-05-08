"""Tests for kdb_benchmark.runner — Task #30 isolation-contract orchestrator.

The runner invokes `compile_one` directly (NOT the production kdb-compile
pipeline) once per (source, model). These tests monkeypatch compile_one so
they verify orchestration only — not LLM interaction.
"""
from __future__ import annotations

import os
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
            "source_id_prefix": kwargs.get("source_id_prefix"),
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
        run_id, state_root = runner.run_benchmark(
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
    """Task #34 — runner derives a path-prefix from sources_dir, constructs
    source_ids as `<prefix>/<filename>`, and forwards the prefix to
    compile_one so the schema validator accepts the resulting source_ids."""

    def test_derive_source_id_prefix_relative(self):
        assert runner._derive_source_id_prefix(Path("benchmark/sources")) == "benchmark/sources"

    def test_derive_source_id_prefix_strips_leading_dot_slash(self):
        assert runner._derive_source_id_prefix(Path("./benchmark/sources/")) == "benchmark/sources"

    def test_derive_source_id_prefix_absolute(self):
        assert runner._derive_source_id_prefix(Path("/tmp/kdb-smoke/")) == "tmp/kdb-smoke"

    def test_derive_source_id_prefix_strips_trailing_slash(self):
        assert runner._derive_source_id_prefix(Path("benchmark/sources/")) == "benchmark/sources"

    def test_compile_one_receives_matching_source_id_prefix(
        self, fake_corpus, fake_system_prompt, runs_root, patched_compile_one
    ):
        """The prefix passed to compile_one as a kwarg must equal the prefix
        embedded in each source_id — otherwise the schema validator will
        reject what the runner constructs."""
        runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        expected_prefix = runner._derive_source_id_prefix(fake_corpus)
        for c in patched_compile_one:
            assert c.get("source_id_prefix") == expected_prefix
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
        run_id, state_root = runner.run_benchmark(
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
        run_id, state_root = runner.run_benchmark(
            sources_dir=fake_corpus, model_id="haiku-4.5",
            runs_root=runs_root, system_prompt_path=fake_system_prompt,
        )
        for c in patched_compile_one:
            assert c["state_root"] == state_root
            assert str(c["state_root"]).startswith(str(runs_root))
