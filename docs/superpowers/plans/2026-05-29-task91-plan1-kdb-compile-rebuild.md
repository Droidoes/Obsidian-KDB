# Plan 1 — `kdb-compile` Rebuild (`compile_source` core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract a per-source **produce-don't-write** `compile_source()` library function that runs Pass-2 stages 3→6 (compile → validate → reconcile → canonicalize) on **in-memory** inputs and returns a `cr` — writing nothing to disk — and freeze the current monolithic CLI as `kdb-old-compile`.

**Architecture:** The monolith's stages 4 (validate) / 5 (reconcile) / 6 (canonicalize) already operate on a `cr`-shaped dict and iterate `compiled_sources` — so `compile_source` wraps a **one-element `cr`** and calls the same functions. It builds the context snapshot from a caller-supplied Kuzu connection (or accepts a pre-built one), runs `compile_one` on an in-memory `CompileJob`, then validate→reconcile→canonicalize, and **returns the `cr`**. Stage 8 (apply-pages / wiki write) and provenance are the **orchestrator's** job at the commit boundary (Plan 6) — not the core's. The monolith (`kdb_compiler/kdb_compile.py`) is untouched and stays runnable as `kdb-old-compile`.

**Tech Stack:** Python 3, pytest, Kuzu (GraphDB), existing `kdb_compiler` modules (`compiler.compile_one`, `validate_compile_result.validate`, `reconcile.reconcile`, `canonicalize.run`, `graph_context_loader.build_context_snapshot`).

**Spec:** `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md` (Pass-2 ingress, "Produce-don't-write" + stage-redistribution table). **Review basis:** `docs/task91-plan1-review-synthesis.md` (workflow + 5-model panel; Forks 1+2 ratified). Plan 1 of 6 (see spec roadmap). Leaves the app green: `kdb-old-compile` still runs E2E; `compile_source` is unit-tested.

**Run tests with `-m "not live"`** — `.env` auto-loads API keys; plain `pytest` fires live tests. All tests here are non-live (fake the model via monkeypatch, the established `test_compiler.py` pattern).

---

## File Structure

- **Modify** `kdb_compiler/types.py` — add `source_text`/`frontmatter` optional fields to `CompileJob`; add `CompileSourceResult` dataclass.
- **Modify** `kdb_compiler/compiler.py` — `source_text_for` prefers in-memory job fields; `source_name` derives from `source_id`; add `compile_source()` (produce-don't-write).
- **Modify** `pyproject.toml` — add `kdb-old-compile` console script.
- **Create** `kdb_compiler/tests/test_compile_source.py` — all new tests.

> **Deferred to Plan 6 (orchestrator), NOT here:** stage 8 apply-pages (`build_page_patches` + write), source provenance (`current_hash`/`current_mtime`), manifest commit, graph-sync. `compile_source` writes nothing.

---

## Task 1: `CompileJob` in-memory fields + `source_text_for` preference + `source_name` fix

**Files:** Modify `kdb_compiler/types.py:291-297`, `kdb_compiler/compiler.py:121-131` and `:235`; Test `kdb_compiler/tests/test_compile_source.py`.

- [ ] **Step 1: Write the failing tests + shared helpers** (helpers defined here once; later tasks reuse them)

```python
# kdb_compiler/tests/test_compile_source.py
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
    # Regression guard (NOT a red test — passes pre-impl too): the in-memory
    # path is the genuine red test (CompileJob rejects source_text= until impl).
    p = tmp_path / "s.md"
    p.write_text("DISK BODY", encoding="utf-8")
    job = CompileJob(
        source_id="KDB/raw/s.md", abs_path=str(p),
        context_snapshot=ContextSnapshot(source_id="KDB/raw/s.md", pages=[]),
    )
    got_fm, got_text = compiler.source_text_for(job)
    assert got_text == "DISK BODY"
    assert got_fm is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest kdb_compiler/tests/test_compile_source.py -v -m "not live"`
Expected: FAIL — `CompileJob.__init__() got an unexpected keyword argument 'source_text'` (and `cannot import name 'CompileSourceResult'` — added in Task 2).

- [ ] **Step 3: Add the in-memory fields to `CompileJob`**

In `kdb_compiler/types.py` (it already has `from __future__ import annotations` at line 10), add a `TYPE_CHECKING` import so `SourceFrontmatter` is a string annotation (no runtime import cycle with `source_io`):

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from kdb_compiler.source_io import SourceFrontmatter
```

Extend `CompileJob` (currently lines 291-297):

```python
@dataclass
class CompileJob:
    """One unit of compile work: a source_id + resolved path + its
    pre-built context snapshot. The orchestrator (in-memory path) also
    supplies source_text + frontmatter so compile reads nothing from disk."""
    source_id: str                 # "KDB/raw/..."
    abs_path: str                  # absolute filesystem path (legacy path only)
    context_snapshot: ContextSnapshot
    source_text: str | None = None              # in-memory body (orchestrator path)
    frontmatter: "SourceFrontmatter | None" = None
```

- [ ] **Step 4: `source_text_for` prefers in-memory; `source_name` derives from `source_id`**

In `kdb_compiler/compiler.py`, replace `source_text_for` (lines 121-131):

```python
def source_text_for(job: CompileJob) -> tuple[SourceFrontmatter | None, str]:
    """Return (frontmatter, body). Prefers the orchestrator's in-memory
    (source_text, frontmatter) when present — zero disk reads; else falls
    back to parse_source_file(abs_path) for the legacy planner path."""
    if job.source_text is not None:
        return job.frontmatter, job.source_text
    return parse_source_file(Path(job.abs_path))
```

And change `compile_one`'s `source_name` derivation (compiler.py:235) — required because the in-memory path has `abs_path=""`, which would yield `source_name=""` and `validate_compiled_source_response.semantic_check` (line 68-72) hard-errors when the model's echoed `source_name` ≠ the prompt's:

```python
    source_name = Path(job.source_id).name
```

Safe for the legacy path: for a normal source `Path(abs_path).name == Path(source_id).name`. (Lines 131 and 235 are `abs_path`'s only uses; 131 short-circuits on in-memory text — so `abs_path=""` is never dereferenced on the orchestrator path.)

- [ ] **Step 5: Run** — `python -m pytest kdb_compiler/tests/test_compile_source.py -v -m "not live"` → the two `source_text_for` tests PASS (the `CompileSourceResult` import still fails until Task 2; comment those imports out or proceed to Task 2 first if running the whole file).

- [ ] **Step 6: Commit**

```bash
git add kdb_compiler/types.py kdb_compiler/compiler.py kdb_compiler/tests/test_compile_source.py
git commit -m "feat(task91): CompileJob in-memory fields + source_text_for + source_name fix"
```

---

## Task 2: `CompileSourceResult` type + freeze monolith as `kdb-old-compile`

**Files:** Modify `kdb_compiler/types.py` (near `CompiledSource`, ~line 232); `pyproject.toml`; Test `test_compile_source.py`.

- [ ] **Step 1: Write the failing test**

```python
# append to test_compile_source.py
def test_compile_source_result_shape() -> None:
    r = CompileSourceResult(cr={"run_id": "x"})
    assert r.cr["run_id"] == "x"
    assert r.failure_stage is None and r.exception_type is None and r.error is None
    assert r.ok is True


def test_compile_source_result_error_not_ok() -> None:
    r = CompileSourceResult(cr=None, failure_stage="validate", error="boom")
    assert r.ok is False
    assert r.failure_stage == "validate"
```

- [ ] **Step 2: Run** — `python -m pytest kdb_compiler/tests/test_compile_source.py::test_compile_source_result_shape -v -m "not live"` → FAIL (`cannot import name 'CompileSourceResult'`).

- [ ] **Step 3: Add the dataclass**

In `kdb_compiler/types.py`, after the `CompiledSource` block (before `CompileResult`). Dependency-light — no new imports:

```python
@dataclass
class CompileSourceResult:
    """Per-source Pass-2 PRODUCE result from compiler.compile_source().
    Produce-don't-write: holds the compiled `cr` only — the orchestrator
    owns stage-8 apply-pages, provenance, manifest commit, and graph-sync.
    error non-None ==> pre-commit failure (D-91-13 case a); cr is None and
    `failure_stage` ∈ {context, compile, validate, canonicalize} routes the
    orchestrator's case-aware summary without string-parsing."""
    cr: dict | None
    failure_stage: str | None = None
    exception_type: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None
```

- [ ] **Step 4: Run** — PASS.

- [ ] **Step 5: Freeze the monolith CLI** — in `pyproject.toml` `[project.scripts]`, add above the existing `kdb-compile` line (keep `kdb-compile` for now; repointed in a later cleanup):

```toml
kdb-old-compile       = "kdb_compiler.kdb_compile:main"
kdb-compile           = "kdb_compiler.kdb_compile:main"
```

- [ ] **Step 6: Reinstall + verify the frozen monolith runs** — `pip install -e . >/dev/null && kdb-old-compile --help` → argparse help, exit 0.

- [ ] **Step 7: Monolith suite still green** — `python -m pytest kdb_compiler/tests/test_kdb_compile.py -m "not live" -q` → all pass.

- [ ] **Step 8: Commit**

```bash
git add kdb_compiler/types.py pyproject.toml kdb_compiler/tests/test_compile_source.py
git commit -m "feat(task91): CompileSourceResult (produce result) + freeze monolith as kdb-old-compile"
```

---

## Task 3: `compile_source()` — produce-don't-write core (snapshot → compile → validate → reconcile → canonicalize → cr)

**Files:** Modify `kdb_compiler/compiler.py` (add `compile_source` after `run_compile`); Test `test_compile_source.py`.

- [ ] **Step 1: Write the failing test**

Uses a real empty test GraphDB (empty graph → empty snapshot, never raises) + a monkeypatched model. (No `uses_real_graph_context` marker needed — the conftest stub targets `planner._build_context`, not `build_context_snapshot` which `compile_source` calls directly.)

```python
# append to test_compile_source.py
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
    assert not list((vault / "KDB").rglob("*/summary-foo.md")), "compile_source must not write"


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
```

- [ ] **Step 2: Run** — FAIL (`module 'kdb_compiler.compiler' has no attribute 'compile_source'`).

- [ ] **Step 3: Confirm no import cycle, then implement**

Add imports at the top of `kdb_compiler/compiler.py`:

```python
from kdb_compiler import canonicalize, reconcile, validate_compile_result
from kdb_compiler.graph_context_loader import T2Mode, build_context_snapshot
from kdb_compiler.canonicalize import AliasLedger
from kdb_compiler.types import CompileSourceResult
```

Cycle smoke (these modules were verified NOT to import `compiler`): `python -c "import kdb_compiler.compiler"` → exit 0.

Add the function after `run_compile`:

```python
def compile_source(
    source_id: str,
    body: str,
    frontmatter: "SourceFrontmatter | None",
    conn,
    *,
    vault_root: Path,
    state_root: Path,
    ctx: RunContext,
    ledger: AliasLedger,
    provider: str,
    model: str,
    max_tokens: int,
    context_snapshot: "ContextSnapshot | None" = None,
    mode: T2Mode = T2Mode.STRUCTURED,
    resolver: str = "simple",
) -> CompileSourceResult:
    """Per-source Pass-2 PRODUCE core (spec stages 3->6) on in-memory inputs.
    Writes NOTHING. Returns the compiled `cr`; the orchestrator owns stage-8
    apply-pages, provenance, manifest commit, and graph-sync at the commit
    boundary. All pre-commit failures return CompileSourceResult(cr=None,
    failure_stage=..., error=...) so the orchestrator routes case-(a) uniformly.
    """
    vault_root = Path(vault_root)

    # 1. context snapshot — caller-supplied, or the only graph read
    if context_snapshot is None:
        try:
            context_snapshot = build_context_snapshot(
                conn, source_id=source_id, source_text=body,
                frontmatter=frontmatter, mode=mode, resolver=resolver,
            )
        except Exception as e:
            return CompileSourceResult(
                cr=None, failure_stage="context",
                exception_type=type(e).__name__, error=str(e))

    # 2. compile (stage 3) on an in-memory job — no disk read
    job = CompileJob(
        source_id=source_id, abs_path="",
        context_snapshot=context_snapshot, source_text=body, frontmatter=frontmatter,
    )
    cs, logs, warns, err = compile_one(
        job, vault_root=vault_root, state_root=state_root, ctx=ctx,
        provider=provider, model=model, max_tokens=max_tokens,
    )
    if err is not None:
        return CompileSourceResult(cr=None, failure_stage="compile", error=err)

    cr: dict = {
        "run_id": ctx.run_id, "success": True,
        "compiled_sources": [cs.to_dict()],
        "log_entries": list(logs), "errors": [], "warnings": list(warns),
    }

    # 3. validate (stage 4) — gate
    vres = validate_compile_result.validate(cr)
    if vres.gate_errors:
        return CompileSourceResult(
            cr=None, failure_stage="validate",
            error="; ".join(f.detail for f in vres.gate_errors))

    # 4. reconcile (stage 5) — mutates cr in place
    reconcile.reconcile(cr, vres.measure_findings)

    # 5. canonicalize (stage 6) — mutates cr in place, emits canonical_meta
    try:
        canonicalize.run(cr, ledger, ctx.run_id)
    except canonicalize.CircularAliasError as e:
        return CompileSourceResult(
            cr=None, failure_stage="canonicalize",
            exception_type=type(e).__name__, error=str(e))

    return CompileSourceResult(cr=cr)
```

- [ ] **Step 4: Run** — both Task-3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add kdb_compiler/compiler.py kdb_compiler/tests/test_compile_source.py
git commit -m "feat(task91): compile_source produce-don't-write core (stages 3->6, returns cr)"
```

---

## Task 4: lock the alias-singleton-rename path (the novel one-element-`cr` behavior)

Cross-source page *merging* is vacuous on a one-element `cr` (accepted trade-off, spec). But the **alias-singleton rename** path (`canonicalize._merge_page_intents`, the `len(contenders)==1` branch) *does* fire on one source — Qwen flagged it as the most novel untested behavior. Lock it.

**Files:** Test `test_compile_source.py`.

- [ ] **Step 1: Write the failing test**

```python
# append to test_compile_source.py
def test_compile_source_alias_singleton_rename(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    # Ledger mapping surface "aapl" -> canonical "apple-inc".
    # NOTE: confirm the on-disk aliases.json schema against canonicalize.load_or_empty
    # (canonicalize.py:88) + AliasEntry (surface/canonical/note) before running;
    # adjust this dict to match the loader's expected shape.
    ledger_dir = state_root / "canonicalization"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    (ledger_dir / "aliases.json").write_text(
        json.dumps({"aliases": [{"surface": "aapl", "canonical": "apple-inc"}]}),
        encoding="utf-8")
    ledger = load_or_empty(ledger_dir / "aliases.json")

    # Model emits a concept page whose slug is the alias surface.
    resp = _good_response(
        "s.md", concept_slugs=["aapl"],
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "Foo",
             "body": "About [[aapl]].", "status": "active",
             "outgoing_links": ["aapl"], "confidence": "medium"},
            {"slug": "aapl", "page_type": "concept", "title": "AAPL",
             "body": "Apple Inc.", "status": "active",
             "outgoing_links": [], "confidence": "medium"},
        ])
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry", _fake_model(resp))

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx, ledger=ledger,
            provider="p", model="m", max_tokens=4096,
        )

    assert result.ok, (result.failure_stage, result.error)
    slugs = {p["slug"] for p in result.cr["compiled_sources"][0]["pages"]}
    assert "apple-inc" in slugs and "aapl" not in slugs, "alias not renamed to canonical"
    aliases = {(a["alias_slug"], a["canonical_slug"])
               for a in result.cr["canonical_meta"]["aliases_emitted"]}
    assert ("aapl", "apple-inc") in aliases
```

- [ ] **Step 2: Run** — confirm it passes (the rename path is already implemented in `canonicalize`; this test locks it on the one-element `cr` route). If it errors on the `aliases.json` schema, fix the JSON shape to match `load_or_empty` and re-run. If the `aliases_emitted` entry key names differ (`alias_slug`/`canonical_slug`), align to `ingestor.py:75-78` which reads those exact keys.

- [ ] **Step 3: Commit**

```bash
git add kdb_compiler/tests/test_compile_source.py
git commit -m "test(task91): lock alias-singleton-rename on one-element cr (Qwen F-1)"
```

---

## Task 5: error paths with `failure_stage` (D-91-13 case a)

**Files:** Test `test_compile_source.py`. (Branches exist from Task 3; this locks them + the `failure_stage` routing.)

- [ ] **Step 1: Write the tests**

```python
# append to test_compile_source.py
def test_compile_source_compile_error(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    def boom(req):
        raise RuntimeError("model exploded")
    monkeypatch.setattr("kdb_compiler.compiler.call_model_with_retry", boom)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )
    assert not result.ok and result.cr is None
    assert result.failure_stage == "compile" and result.error


def test_compile_source_gate_error(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    # Force a gate error to exercise the fail-fast branch (validate itself is
    # covered by test_validate_compile_result.py). ValidationFinding fields are
    # (type, severity, detail, source_id=None, ...) — severity is the 2nd
    # positional with NO default, so it is required (omitting raises TypeError).
    from kdb_compiler.validate_compile_result import ValidationResult, ValidationFinding
    def fake_validate(cr):
        r = ValidationResult()
        r.gate_errors.append(ValidationFinding(
            type="forced_gate", severity="gate", detail="forced for test",
            source_id="KDB/raw/s.md"))
        return r
    monkeypatch.setattr(
        "kdb_compiler.compiler.validate_compile_result.validate", fake_validate)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )
    assert not result.ok and result.cr is None
    assert result.failure_stage == "validate" and "forced for test" in result.error
```

- [ ] **Step 2: Run** — both PASS. If the `ValidationFinding` constructor signature has changed, align kwargs to the real dataclass (`validate_compile_result.py:52-60`) and re-run.

- [ ] **Step 3: Full Plan-1 regression** — `python -m pytest kdb_compiler/tests/ -m "not live" -q` → all pass (new `compile_source` tests + untouched monolith suite).

- [ ] **Step 4: Commit**

```bash
git add kdb_compiler/tests/test_compile_source.py
git commit -m "test(task91): compile_source error paths + failure_stage routing (D-91-13 a)"
```

---

## Self-Review checklist (run before execution)

1. **Spec coverage:** stages 3 (compile_one) → 4 (validate) → 5 (reconcile) → 6 (canonicalize) wired into `compile_source` returning `cr` (Task 3); **stage 8 apply-pages + provenance are NOT here — deferred to the orchestrator (Plan 6)** per the produce-don't-write decision. In-memory `CompileJob` + `source_text_for` + `source_name`-from-`source_id` (Task 1) = the ingress "Adaptation" section. Optional `context_snapshot` param (panel finding D). `failure_stage`/`exception_type` (panel finding C). `kdb-old-compile` freeze (Task 2) = make-before-break. Alias-singleton-rename locked (Task 4, Qwen F-1).
2. **Type consistency:** `CompileSourceResult(cr, failure_stage, exception_type, error, .ok)` defined Task 2, used Tasks 3-5. `compile_source(...)` signature identical across Tasks 3-5 (note `conn` may be `None` when `context_snapshot` is supplied).
3. **Execution-time verify points (flagged inline):** the `aliases.json` schema + `aliases_emitted` key names (Task 4), and the `ValidationFinding` constructor kwargs (Task 5). Both are isolated and self-flagged.
