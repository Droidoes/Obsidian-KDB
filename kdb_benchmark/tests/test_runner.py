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
        source_ids = sorted(c["job"].source_id for c in patched_compile_one)
        assert source_ids == ["01-foo.md", "02-bar.md"]

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
