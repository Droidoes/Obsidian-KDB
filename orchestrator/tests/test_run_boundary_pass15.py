"""#123 P3a.2b — run()-boundary selector wiring (blueprint §4.4).

The run resolves the pass-1.5 selector seat ONCE (module constant
PASS15_SELECTOR_MODEL_ID, seat settled 2026-08-03 in docs/TASKS.md #123),
validates it against the request's max_tokens BEFORE the source loop, and
threads the same ModelSpec plus a positional intra_run_order into every
compile_source call. All non-live: pass-1/pass-2/compile are faked; the
selector spec is either the real pool entry (no network — models.json only)
or a canned ModelSpec.
"""
import json
from pathlib import Path

import pytest

from common.model_pool import (
    ModelSpec, PoolError, UnknownModelError, resolve_models_json,
)
from common.model_route import ModelRoute
from common.types import CompileSourceResult
from ingestion.enrich.pass1_caller import Pass1CallResult
from orchestrator import kdb_orchestrate


def _vault(tmp_path: Path, source_ids: list[str]) -> Path:
    (tmp_path / "KDB" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "AIML").mkdir()
    for source_id in source_ids:
        (tmp_path / source_id).write_text("# Note\n\nValue investing.\n", encoding="utf-8")
    return tmp_path


def _write_pipelines(state_root: Path, vault_root: Path) -> None:
    ddir = state_root / "pipelines.d"           # #143: one file per pipeline
    ddir.mkdir(parents=True, exist_ok=True)
    (ddir / "vt.json").write_text(json.dumps(
        {"id": "vt", "type": "in-place", "root": str(vault_root),
         "excludes": ["KDB/"], "force_noise": ["noise/*"], "file_types": [".md"]}
    ), encoding="utf-8")


def _fake_pass1(**kwargs):
    return Pass1CallResult(
        parsed={
            "kdb_signal": "signal", "domain": "value-investing",
            "source_type": "paper", "author": "T", "summary": "S.",
            "key_themes": ["a"], "entity_search_keys": ["a"],
            "confidence": 0.9, "uncertainty_reason": None,
            "reject_reason": None,
            "prompt_version": "p1", "model": kwargs["model"], "schema_version": 1,
            "override": {"applied": None, "rule": None, "match": None,
                         "llm_original": "signal", "reject_reason_cleared": None},
            "other_reason": None,
        },
        raw_response_text="{}", request_prompt="p", request_model=kwargs["model"],
        request_provider=kwargs["provider"], input_tokens=1, output_tokens=1,
        latency_ms=1, attempts=1)


def _spec(**overrides) -> ModelSpec:
    base = dict(
        id="test-selector",
        provider="deepseek",
        model="test",
        route=ModelRoute("openai_compat", "https://example.invalid", "DEEPSEEK_API_KEY"),
        ctx_window=400_000,
        max_output_tokens=65_536,
        tokens_lte_bytes=True,
    )
    return ModelSpec(**{**base, **overrides})


def _run(vault, state_root, tmp_path, max_tokens=4096, **kwargs):
    return kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m",
        max_tokens=max_tokens, **kwargs)


def test_seat_resolved_once_and_threaded_with_intra_run_order(tmp_path, monkeypatch):
    """One resolution per run; the SAME ModelSpec object reaches every
    compile_source call; intra_run_order is the loop position 0,1,2."""
    source_ids = ["AIML/a.md", "AIML/b.md", "AIML/c.md"]
    vault = _vault(tmp_path, source_ids)
    state_root = vault / "KDB" / "state"
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    resolutions: list[str] = []
    real_resolve = resolve_models_json

    def spy_resolve(model_id: str) -> ModelSpec:
        resolutions.append(model_id)
        return real_resolve(model_id)

    monkeypatch.setattr(kdb_orchestrate, "resolve_models_json", spy_resolve)

    compile_calls: list[dict] = []

    def fake_compile(**kwargs):
        compile_calls.append(kwargs)
        return CompileSourceResult(
            cr=None, failure_stage="compile", exception_type="Boom", error="stop")

    monkeypatch.setattr(kdb_orchestrate, "compile_source", fake_compile)

    res = _run(vault, state_root, tmp_path)

    assert res.counts["sources_failed"] == 3   # every source quarantined, loop continued
    assert resolutions == [kdb_orchestrate.PASS15_SELECTOR_MODEL_ID]
    assert [c["source_id"] for c in compile_calls] == source_ids
    assert [c["intra_run_order"] for c in compile_calls] == [0, 1, 2]
    selectors = [c["selector"] for c in compile_calls]
    assert all(s is selectors[0] for s in selectors)
    assert selectors[0].id == "qwen3.7-flash"


def test_unknown_seat_raises_unknown_model_before_loop(tmp_path, monkeypatch):
    vault = _vault(tmp_path, ["AIML/a.md"])
    state_root = vault / "KDB" / "state"
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr(kdb_orchestrate, "PASS15_SELECTOR_MODEL_ID", "no-such-model")

    def forbidden_compile(**kwargs):  # the loop must never start
        raise AssertionError("compile_source called despite seat failure")

    monkeypatch.setattr(kdb_orchestrate, "compile_source", forbidden_compile)

    with pytest.raises(UnknownModelError):
        _run(vault, state_root, tmp_path)


def test_seat_without_ctx_window_raises_pool_error_before_loop(tmp_path, monkeypatch):
    """A seat without a ctx_window cannot budget the selector — PoolError."""
    vault = _vault(tmp_path, ["AIML/a.md"])
    state_root = vault / "KDB" / "state"
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr(
        kdb_orchestrate, "resolve_models_json", lambda model_id: _spec(ctx_window=None))
    monkeypatch.setattr(
        kdb_orchestrate, "compile_source",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("loop started")))

    with pytest.raises(PoolError):
        _run(vault, state_root, tmp_path)


def test_max_tokens_above_seat_output_cap_raises_before_loop(tmp_path, monkeypatch):
    """max_tokens > selector.max_output_tokens (65_536) ⇒ ValueError before
    the loop — the pass-2 cap must fit the selector's output envelope."""
    vault = _vault(tmp_path, ["AIML/a.md"])
    state_root = vault / "KDB" / "state"
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr(
        kdb_orchestrate, "compile_source",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("loop started")))

    with pytest.raises(ValueError, match="max_tokens"):
        _run(vault, state_root, tmp_path, max_tokens=70_000)


def test_selector_model_id_overrides_the_constant_seat(tmp_path, monkeypatch):
    """Per-run selector_model_id beats the module fallback: resolved ONCE,
    same ModelSpec threaded into every compile_source call."""
    source_ids = ["AIML/a.md", "AIML/b.md"]
    vault = _vault(tmp_path, source_ids)
    state_root = vault / "KDB" / "state"
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    resolutions: list[str] = []
    real_resolve = resolve_models_json

    def spy_resolve(model_id: str) -> ModelSpec:
        resolutions.append(model_id)
        return real_resolve(model_id)

    monkeypatch.setattr(kdb_orchestrate, "resolve_models_json", spy_resolve)

    compile_calls: list[dict] = []

    def fake_compile(**kwargs):
        compile_calls.append(kwargs)
        return CompileSourceResult(
            cr=None, failure_stage="compile", exception_type="Boom", error="stop")

    monkeypatch.setattr(kdb_orchestrate, "compile_source", fake_compile)

    _run(vault, state_root, tmp_path, selector_model_id="deepseek-v4-flash")

    assert resolutions == ["deepseek-v4-flash"]
    assert [c["selector"].id for c in compile_calls] == ["deepseek-v4-flash"] * 2


class _StubResult:
    run_id = "r"
    exit_code = 0
    exit_reason = "ok"
    counts = {"sources_scanned": 0, "sources_compiled": 0, "sources_noise": 0,
              "sources_moved": 0, "sources_deleted": 0, "sources_failed": 0}
    planned = None
    finalize = None
    summary_path = None
    event_log_path = None
    quarantined_sources = []


def test_main_defaults_selector_seat_to_model(tmp_path, monkeypatch):
    """Single-model default (Joseph 2026-08-04): no --selector-model ⇒
    run() receives selector_model_id = args.model; --selector-model pins."""
    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return _StubResult()

    monkeypatch.setattr(kdb_orchestrate, "run", fake_run)

    rc = kdb_orchestrate.main([
        "--pipeline", "vt", "--vault-root", str(tmp_path),
        "--model", "deepseek-v4-flash"])
    assert rc == 0
    assert captured["selector_model_id"] == "deepseek-v4-flash"

    captured.clear()
    rc = kdb_orchestrate.main([
        "--pipeline", "vt", "--vault-root", str(tmp_path),
        "--model", "deepseek-v4-flash", "--selector-model", "qwen3.7-flash"])
    assert rc == 0
    assert captured["selector_model_id"] == "qwen3.7-flash"
