"""Task #91 Plan 1 — compile_source (produce-don't-write Pass-2 core) tests.

All non-live: the model is faked via monkeypatch (the test_compiler.py pattern).
Run: python -m pytest kdb_compiler/tests/test_compile_source.py -v -m "not live"
"""
import json
from pathlib import Path

import pytest

from kdb_compiler import compiler, prompt_builder
from kdb_compiler.call_model import ModelResponse
from kdb_compiler.canonicalize import load_or_empty
from kdb_compiler.run_context import RunContext
from kdb_compiler.source_io import SourceFrontmatter
from kdb_compiler.types import CompileJob, CompileSourceResult, ContextSnapshot
from graphdb_kdb.graphdb import GraphDB


@pytest.fixture(autouse=True)
def _clear_prompt_caches():
    prompt_builder.load_system_prompt.cache_clear()
    prompt_builder.load_response_schema_text.cache_clear()


def _fm() -> SourceFrontmatter:
    return SourceFrontmatter(
        kdb_signal="signal", domain="value-investing", source_type="essay",
        author="Test", summary="A summary.", key_themes=["a"],
        entity_search_keys=["value-investing"],
    )


def _vault(tmp_path: Path) -> Path:
    (tmp_path / "KDB").mkdir(parents=True, exist_ok=True)
    (tmp_path / "KDB" / "KDB-Compiler-System-Prompt.md").write_text(
        "# KDB invariants\n", encoding="utf-8")
    (tmp_path / "KDB" / "state").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _good_response(source_name: str, *, summary_slug="summary-foo",
                   concept_slugs=None, pages=None) -> dict:
    return {
        "source_name": source_name, "summary_slug": summary_slug,
        "concept_slugs": concept_slugs or [], "article_slugs": [],
        "pages": pages or [{
            "slug": summary_slug, "page_type": "summary", "title": "Foo",
            "body": "Body.", "status": "active", "outgoing_links": [],
            "confidence": "medium",
        }],
        "log_entries": [], "warnings": [],
    }


def _fake_model(response: dict):
    def fake(req):
        return ModelResponse(
            text=json.dumps(response), input_tokens=100, output_tokens=50,
            latency_ms=10, model="m", provider="p", attempts=1,
        )
    return fake


# ---------- Task 1: CompileJob in-memory fields + source_text_for ----------

def test_source_text_for_prefers_in_memory(tmp_path: Path) -> None:
    p = tmp_path / "s.md"
    p.write_text("DISK BODY", encoding="utf-8")
    fm = _fm()
    job = CompileJob(
        source_id="KDB/raw/s.md", abs_path=str(p),
        context_snapshot=ContextSnapshot(source_id="KDB/raw/s.md", pages=[]),
        source_text="MEM BODY", frontmatter=fm,
    )
    got_fm, got_text = compiler.source_text_for(job)
    assert got_text == "MEM BODY"
    assert got_fm is fm


def test_source_text_for_falls_back_to_disk(tmp_path: Path) -> None:
    # Regression guard (passes pre-impl too); the in-memory test is the red one.
    p = tmp_path / "s.md"
    p.write_text("DISK BODY", encoding="utf-8")
    job = CompileJob(
        source_id="KDB/raw/s.md", abs_path=str(p),
        context_snapshot=ContextSnapshot(source_id="KDB/raw/s.md", pages=[]),
    )
    got_fm, got_text = compiler.source_text_for(job)
    assert got_text == "DISK BODY"
    assert got_fm is None


# ---------- Task 2: CompileSourceResult shape ----------

def test_compile_source_result_shape() -> None:
    r = CompileSourceResult(cr={"run_id": "x"})
    assert r.cr["run_id"] == "x"
    assert r.failure_stage is None and r.exception_type is None and r.error is None
    assert r.ok is True


def test_compile_source_result_error_not_ok() -> None:
    r = CompileSourceResult(cr=None, failure_stage="validate", error="boom")
    assert r.ok is False
    assert r.failure_stage == "validate"


# ---------- Task 3: compile_source produce-don't-write core ----------

def test_compile_source_produces_cr_and_writes_nothing(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )

    assert result.ok, (result.failure_stage, result.error)
    assert result.cr is not None
    assert len(result.cr["compiled_sources"]) == 1
    assert result.cr["compiled_sources"][0]["source_id"] == "KDB/raw/s.md"
    assert "canonical_meta" in result.cr            # canonicalize ran (stage 6)
    # produce-don't-write: no wiki pages written anywhere under the vault
    assert not list((vault / "KDB").rglob("summary-foo.md")), "compile_source must not write"


def test_compile_source_accepts_prebuilt_snapshot(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))
    snap = ContextSnapshot(source_id="KDB/raw/s.md", pages=[])

    # conn=None proves the pre-built snapshot path does no graph read.
    result = compiler.compile_source(
        source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=None,
        vault_root=vault, state_root=state_root, ctx=ctx,
        ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
        provider="p", model="m", max_tokens=4096, context_snapshot=snap,
    )
    assert result.ok, (result.failure_stage, result.error)
    assert result.cr is not None
