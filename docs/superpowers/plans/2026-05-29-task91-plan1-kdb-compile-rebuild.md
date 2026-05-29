# Plan 1 — `kdb-compile` Rebuild (`compile_source` core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract a per-source `compile_source()` library function that runs Pass-2 stages 3→6+8 on **in-memory** inputs (zero disk re-read), and freeze the current monolithic CLI as `kdb-old-compile`.

**Architecture:** The monolith's stages 4 (validate) / 5 (reconcile) / 6 (canonicalize) already operate on a `cr`-shaped dict and merely iterate `compiled_sources` — so `compile_source` wraps a **one-element `cr`** and calls the same functions. It builds the context snapshot from a caller-supplied Kuzu connection (the orchestrator's shared read-write conn), runs `compile_one` on an in-memory `CompileJob`, then validate→reconcile→canonicalize→apply-pages. No batch write-back (the orchestrator owns per-source persistence). The monolith (`kdb_compiler/kdb_compile.py`) is untouched and stays runnable as `kdb-old-compile`.

**Tech Stack:** Python 3, pytest, Kuzu (GraphDB), existing `kdb_compiler` modules (`compiler.compile_one`, `validate_compile_result.validate`, `reconcile.reconcile`, `canonicalize.run`, `patch_applier.apply`, `graph_context_loader.build_context_snapshot`).

**Spec:** `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md` (Pass-2 ingress + stage-redistribution table). This is Plan 1 of 6 (see spec roadmap). Leaves the app green: `kdb-old-compile` still runs E2E; `compile_source` is unit-tested.

**Run tests with `-m "not live"`** — `.env` auto-loads API keys; plain `pytest` fires live tests. All tests here are non-live (fake the model via monkeypatch).

---

## File Structure

- **Modify** `kdb_compiler/types.py` — add `source_text` + `frontmatter` optional fields to `CompileJob`; add `CompileSourceResult` dataclass.
- **Modify** `kdb_compiler/compiler.py` — `source_text_for` prefers in-memory job fields; **`source_name` derives from `source_id` not `abs_path`** (in-memory path has `abs_path=""`); add `compile_source()`.
- **Modify** `pyproject.toml` — add `kdb-old-compile` console script (freeze the monolith under its new name).
- **Create** `kdb_compiler/tests/test_compile_source.py` — all new tests.

---

## Task 1: `CompileJob` in-memory fields + `source_text_for` preference

**Files:**
- Modify: `kdb_compiler/types.py:291-297` (CompileJob)
- Modify: `kdb_compiler/compiler.py:121-131` (source_text_for)
- Test: `kdb_compiler/tests/test_compile_source.py`

- [ ] **Step 1: Write the failing tests**

```python
# kdb_compiler/tests/test_compile_source.py
from pathlib import Path

from kdb_compiler import compiler
from kdb_compiler.source_io import SourceFrontmatter
from kdb_compiler.types import CompileJob, ContextSnapshot


def _fm() -> SourceFrontmatter:
    return SourceFrontmatter(
        kdb_signal="signal", domain="value-investing", source_type="essay",
        author="Test", summary="A summary.", key_themes=["a"],
        entity_search_keys=["value-investing"],
    )


def test_source_text_for_prefers_in_memory(tmp_path: Path) -> None:
    # On-disk body differs from the in-memory body to prove disk is NOT read.
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
    p = tmp_path / "s.md"
    p.write_text("DISK BODY", encoding="utf-8")
    job = CompileJob(
        source_id="KDB/raw/s.md", abs_path=str(p),
        context_snapshot=ContextSnapshot(source_id="KDB/raw/s.md", pages=[]),
    )
    got_fm, got_text = compiler.source_text_for(job)
    assert got_text == "DISK BODY"
    assert got_fm is None  # no frontmatter delimiter in the file
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest kdb_compiler/tests/test_compile_source.py -v -m "not live"`
Expected: FAIL — `CompileJob.__init__() got an unexpected keyword argument 'source_text'`.

- [ ] **Step 3: Add the fields to `CompileJob`**

In `kdb_compiler/types.py`, add a `TYPE_CHECKING` import near the top (after the existing `from __future__ import annotations` on line 10 — string annotations avoid a runtime import cycle with `source_io`):

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from kdb_compiler.source_io import SourceFrontmatter
```

Then extend `CompileJob` (currently lines 291-297):

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

- [ ] **Step 4: Make `source_text_for` prefer the in-memory fields**

In `kdb_compiler/compiler.py`, replace the body of `source_text_for` (lines 121-131):

```python
def source_text_for(job: CompileJob) -> tuple[SourceFrontmatter | None, str]:
    """Return (frontmatter, body) for a job. Prefers the orchestrator's
    in-memory (source_text, frontmatter) when present — zero disk reads;
    falls back to parse_source_file(abs_path) for the legacy planner path.
    See spec 'Pass-2 ingress — Adaptation'."""
    if job.source_text is not None:
        return job.frontmatter, job.source_text
    return parse_source_file(Path(job.abs_path))
```

- [ ] **Step 5: Run to verify they pass**

Run: `python -m pytest kdb_compiler/tests/test_compile_source.py -v -m "not live"`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add kdb_compiler/types.py kdb_compiler/compiler.py kdb_compiler/tests/test_compile_source.py
git commit -m "feat(task91): CompileJob in-memory fields + source_text_for preference"
```

---

## Task 2: `CompileSourceResult` type + freeze monolith as `kdb-old-compile`

**Files:**
- Modify: `kdb_compiler/types.py` (add dataclass near CompiledSource ~line 232)
- Modify: `pyproject.toml` (`[project.scripts]`)
- Test: `kdb_compiler/tests/test_compile_source.py`

- [ ] **Step 1: Write the failing test**

```python
# append to test_compile_source.py
from kdb_compiler.types import CompileSourceResult


def test_compile_source_result_shape() -> None:
    r = CompileSourceResult(cr={"run_id": "x"}, pages_written=["a.md"], error=None)
    assert r.cr["run_id"] == "x"
    assert r.pages_written == ["a.md"]
    assert r.error is None
    assert r.ok is True


def test_compile_source_result_error_not_ok() -> None:
    r = CompileSourceResult(cr=None, pages_written=[], error="boom")
    assert r.ok is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest kdb_compiler/tests/test_compile_source.py::test_compile_source_result_shape -v -m "not live"`
Expected: FAIL — `cannot import name 'CompileSourceResult'`.

- [ ] **Step 3: Add the dataclass**

In `kdb_compiler/types.py`, after the `CompiledSource` block (before `CompileResult`), add. Keep it dependency-light (no `patch_applier`/`ApplyResult` import — store the page list directly) so `types.py` gains no new imports:

```python
@dataclass
class CompileSourceResult:
    """Per-source Pass-2 result returned by compiler.compile_source().
    The orchestrator feeds `cr` to graph-sync (apply_compile_result) and
    uses `pages_written` for the run summary. `error` non-None ==> the
    source failed pre-commit (D-91-13 case a); cr is None."""
    cr: dict | None
    pages_written: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest kdb_compiler/tests/test_compile_source.py -v -m "not live"`
Expected: PASS.

- [ ] **Step 5: Freeze the monolith CLI under its new name**

In `pyproject.toml`, under `[project.scripts]`, add the alias **above** the existing `kdb-compile` line (keep `kdb-compile` for now — it gets repointed/removed in a later cleanup, per make-before-break):

```toml
kdb-old-compile       = "kdb_compiler.kdb_compile:main"
kdb-compile           = "kdb_compiler.kdb_compile:main"
```

- [ ] **Step 6: Reinstall console scripts + verify the frozen monolith runs**

Run: `pip install -e . >/dev/null && kdb-old-compile --help`
Expected: argparse help for the monolith prints; exit 0.

- [ ] **Step 7: Confirm the existing monolith suite is still green**

Run: `python -m pytest kdb_compiler/tests/test_kdb_compile.py -m "not live" -q`
Expected: all pass (the rename added a script alias; no module logic changed).

- [ ] **Step 8: Commit**

```bash
git add kdb_compiler/types.py pyproject.toml kdb_compiler/tests/test_compile_source.py
git commit -m "feat(task91): CompileSourceResult + freeze monolith as kdb-old-compile"
```

---

## Task 3: `compile_source()` — snapshot → compile_one → validate → reconcile → canonicalize

**Files:**
- Modify: `kdb_compiler/compiler.py` (add `compile_source` after `run_compile`)
- Test: `kdb_compiler/tests/test_compile_source.py`

- [ ] **Step 1: Write the failing test**

This test uses a **real empty test GraphDB** (empty graph → empty snapshot, never raises) and a **monkeypatched model call** (real-but-not-live, the established pattern). Reuse the `test_compiler.py` helpers by importing them.

```python
# append to test_compile_source.py
import pytest

from kdb_compiler import compiler, prompt_builder
from kdb_compiler.call_model import ModelResponse
from kdb_compiler.canonicalize import load_or_empty
from kdb_compiler.run_context import RunContext
from graphdb_kdb.graphdb import GraphDB
import json


@pytest.fixture(autouse=True)
def _clear_prompt_caches():
    prompt_builder.load_system_prompt.cache_clear()
    prompt_builder.load_response_schema_text.cache_clear()


def _vault(tmp_path: Path) -> Path:
    (tmp_path / "KDB").mkdir(parents=True, exist_ok=True)
    (tmp_path / "KDB" / "KDB-Compiler-System-Prompt.md").write_text(
        "# KDB invariants\n", encoding="utf-8")
    (tmp_path / "KDB" / "state").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _good_response(source_name: str) -> dict:
    return {
        "source_name": source_name, "summary_slug": "summary-foo",
        "concept_slugs": [], "article_slugs": [],
        "pages": [{
            "slug": "summary-foo", "page_type": "summary", "title": "Foo",
            "body": "Body.", "status": "active", "outgoing_links": [],
            "confidence": "medium",
        }],
        "log_entries": [], "warnings": [],
    }


def _fake_model(source_name: str):
    def fake(req):
        return ModelResponse(
            text=json.dumps(_good_response(source_name)),
            input_tokens=100, output_tokens=50, latency_ms=10,
            model="m", provider="p", attempts=1,
        )
    return fake


def test_compile_source_happy_path(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry", _fake_model("s.md"))

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md",
            body="A note about value investing.",
            frontmatter=_fm(),
            conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            source_hash="sha256:test", source_mtime=0.0,
            write=False,  # apply-pages added in Task 4
        )

    assert result.ok, result.error
    assert result.cr is not None
    assert len(result.cr["compiled_sources"]) == 1
    assert result.cr["compiled_sources"][0]["source_id"] == "KDB/raw/s.md"
    # canonicalize ran (Pass 5 emits canonical_meta into the cr)
    assert "canonical_meta" in result.cr
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest kdb_compiler/tests/test_compile_source.py::test_compile_source_happy_path -v -m "not live"`
Expected: FAIL — `module 'kdb_compiler.compiler' has no attribute 'compile_source'`.

- [ ] **Step 3a: Fix `source_name` derivation (REQUIRED for the in-memory path — spec line 214).**

`compile_source` builds the job with `abs_path=""`, so `compile_one`'s `source_name = Path(job.abs_path).name` (compiler.py:235) would yield `""` — and `validate_compiled_source_response.semantic_check` (line 68-72) **hard-errors** when the model's echoed `source_name` ≠ the prompt's. Change compiler.py:235:

```python
    source_name = Path(job.source_id).name
```

Safe for the legacy path too: for a normal source `Path(abs_path).name == Path(source_id).name`. Lines 131 and 235 are `abs_path`'s only uses, and 131 already short-circuits on in-memory `source_text` — so `abs_path=""` is never dereferenced on the orchestrator path. `test_compile_source_happy_path` (Step 1, which uses `abs_path=""` + `source_id="KDB/raw/s.md"` and a model echoing `"s.md"`) is the failing test that proves this fix.

- [ ] **Step 3b: Implement `compile_source` (validate gate + reconcile + canonicalize; apply-pages added in Task 4)**

First, a one-line import smoke after adding the imports below confirms no cycle (you were bitten by the planner→compiler B-1 cycle before — though `graph_context_loader`/`canonicalize`/`reconcile` were verified *not* to import `compiler`):
`python -c "import kdb_compiler.compiler"` → exit 0.

Add imports at the top of `kdb_compiler/compiler.py` (alongside existing imports):

```python
from kdb_compiler import canonicalize, reconcile, validate_compile_result
from kdb_compiler.graph_context_loader import T2Mode, build_context_snapshot
from kdb_compiler.canonicalize import AliasLedger
from kdb_compiler.types import CompileSourceResult
```

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
    source_hash: str,
    source_mtime: float,
    mode: T2Mode = T2Mode.STRUCTURED,
    resolver: str = "simple",
    write: bool = True,
) -> CompileSourceResult:
    """Per-source Pass-2 core (spec stages 3->6+8) on in-memory inputs.

    1. build context snapshot from `conn` (the only graph read)
    2. compile_one on an in-memory CompileJob (no disk read)
    3. wrap a one-element cr -> validate (gate) -> reconcile -> canonicalize
    4. apply-pages (Task 4)
    `source_hash`/`source_mtime` are the source's real provenance (the
    orchestrator owns these: post-embed hash + stat mtime); they flow into
    each page's frontmatter via patch_applier. ALL pre-commit failure modes
    (compile / validate / canonicalize / apply) return CompileSourceResult(
    cr=None, error=...) so the orchestrator's D-91-13 case-(a) handler is
    uniform; error non-None => source NOT committed.
    """
    vault_root = Path(vault_root)
    snapshot = build_context_snapshot(
        conn, source_id=source_id, source_text=body,
        frontmatter=frontmatter, mode=mode, resolver=resolver,
    )
    job = CompileJob(
        source_id=source_id, abs_path="",
        context_snapshot=snapshot, source_text=body, frontmatter=frontmatter,
    )
    cs, logs, warns, err = compile_one(
        job, vault_root=vault_root, state_root=state_root, ctx=ctx,
        provider=provider, model=model, max_tokens=max_tokens,
    )
    if err is not None:
        return CompileSourceResult(cr=None, error=err)

    cr: dict = {
        "run_id": ctx.run_id, "success": True,
        "compiled_sources": [cs.to_dict()],
        "log_entries": list(logs), "errors": [], "warnings": list(warns),
    }

    vres = validate_compile_result.validate(cr)
    if vres.gate_errors:
        return CompileSourceResult(
            cr=None, error="; ".join(f.detail for f in vres.gate_errors))

    reconcile.reconcile(cr, vres.measure_findings)
    try:
        canonicalize.run(cr, ledger, ctx.run_id)
    except canonicalize.CircularAliasError as e:
        return CompileSourceResult(cr=None, error=f"canonicalize failed: {e}")

    return CompileSourceResult(cr=cr, pages_written=[], error=None)
```

> **Wrapping rationale (workflow finding #3):** the spec lists canonicalize + apply-pages among case-(a) pre-commit modes. Wrapping `CircularAliasError` (and `PagePatchError` in Task 4) into `CompileSourceResult(error=...)` keeps the result model honest — every pre-commit failure is reported the same way, so the orchestrator's fail-fast handler (Plan 6) treats them uniformly. Dedicated triggering tests for these two modes are deferred (they need a cyclic ledger / forced apply failure); Task 5 locks the two easy-to-trigger modes and the wrap covers the rest at the result-model level.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest kdb_compiler/tests/test_compile_source.py::test_compile_source_happy_path -v -m "not live"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add kdb_compiler/compiler.py kdb_compiler/tests/test_compile_source.py
git commit -m "feat(task91): compile_source core — snapshot/compile/validate/reconcile/canonicalize"
```

---

## Task 4: `compile_source` apply-pages (wiki write)

**Files:**
- Modify: `kdb_compiler/compiler.py` (`compile_source` — add patch_applier.apply)
- Test: `kdb_compiler/tests/test_compile_source.py`

- [ ] **Step 1: Write the failing test**

```python
# append to test_compile_source.py
def test_compile_source_writes_wiki_pages(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry", _fake_model("s.md"))

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(),
            conn=g.conn, vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            source_hash="sha256:test", source_mtime=0.0, write=True,
        )

    assert result.ok, result.error
    assert result.pages_written, "expected at least one wiki page written"
    # the summary page exists on disk under the vault
    assert any((vault).rglob("summary-foo.md")), "summary page not written"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest kdb_compiler/tests/test_compile_source.py::test_compile_source_writes_wiki_pages -v -m "not live"`
Expected: FAIL — `result.pages_written` is empty (apply not wired).

- [ ] **Step 3: Wire `patch_applier.apply`**

Add import to `kdb_compiler/compiler.py`:

```python
from kdb_compiler import patch_applier
```

In `compile_source`, replace the final return with an apply-pages step. `patch_applier.apply` needs a `last_scan` dict whose `files` entry carries **`current_mtime`** (mandatory — `_source_mtime_from_scan`, patch_applier.py:154-156, raises `PagePatchError` on a non-numeric mtime) and **`current_hash`** (becomes each page's `raw_hash` frontmatter). Feed the real provenance params:

```python
    single_scan = {
        "files": [{
            "path": source_id, "is_binary": False,
            "current_hash": source_hash, "current_mtime": source_mtime,
        }],
        "to_compile": [source_id],
        "to_reconcile": [],
    }
    try:
        apply_result = patch_applier.apply(
            vault_root, compile_result=cr, last_scan=single_scan,
            run_ctx=ctx, write=write,
        )
    except patch_applier.PagePatchError as e:
        return CompileSourceResult(cr=None, error=f"apply-pages failed: {e}")
    return CompileSourceResult(
        cr=cr, pages_written=list(apply_result.pages_written), error=None)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest kdb_compiler/tests/test_compile_source.py::test_compile_source_writes_wiki_pages -v -m "not live"`
Expected: PASS.

> The `single_scan` entry now carries `current_mtime` + `current_hash`, so `apply` no longer raises `PagePatchError` (it did when `current_mtime` was absent — `_source_mtime_from_scan`, patch_applier.py:154-156, raises *before* the dry-run return). If the page-path assertion still fails, the summary page lands at `paths.slug_to_relpath("summary-foo","summary")` → `KDB/wiki/summaries/summary-foo.md`; tighten the assertion to that exact path rather than loosening the write check.

- [ ] **Step 5: Commit**

```bash
git add kdb_compiler/compiler.py kdb_compiler/tests/test_compile_source.py
git commit -m "feat(task91): compile_source apply-pages (wiki write)"
```

---

## Task 5: `compile_source` error paths (D-91-13 case a)

**Files:**
- Test: `kdb_compiler/tests/test_compile_source.py`
- (No implementation expected — the branches exist from Tasks 3-4; this locks them.)

- [ ] **Step 1: Write the failing tests**

```python
# append to test_compile_source.py
def test_compile_source_propagates_compile_one_error(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    def boom(req):
        raise RuntimeError("model exploded")
    monkeypatch.setattr("kdb_compiler.compiler.call_model_with_retry", boom)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(),
            conn=g.conn, vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            source_hash="sha256:test", source_mtime=0.0, write=True,
        )

    assert not result.ok
    assert result.cr is None
    assert result.error  # non-empty message


def test_compile_source_gate_error_returns_error(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry", _fake_model("s.md"))

    # Force a gate error to exercise compile_source's fail-fast branch.
    # validate itself is covered by test_validate_compile_result.py; here we
    # test ONLY that compile_source halts and reports when a gate error exists.
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
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(),
            conn=g.conn, vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            source_hash="sha256:test", source_mtime=0.0, write=True,
        )

    assert not result.ok
    assert result.cr is None
    assert "forced for test" in result.error
```

> Note on `ValidationFinding` (`validate_compile_result.py:52-60`): fields are `type, severity, detail, source_id=None, ...` — **`severity` is the 2nd positional and has NO default**, so it is required (omitting it raises `TypeError`). The construction above includes `severity="gate"`. If the dataclass has changed, re-confirm against the source.

- [ ] **Step 2: Run to verify they pass (branches already implemented)**

Run: `python -m pytest kdb_compiler/tests/test_compile_source.py -v -m "not live"`
Expected: both new tests PASS. If `test_compile_source_gate_error_returns_error` fails on the `ValidationFinding` constructor, fix the kwargs to match the real dataclass and re-run.

- [ ] **Step 3: Full Plan-1 regression**

Run: `python -m pytest kdb_compiler/tests/ -m "not live" -q`
Expected: all pass (new `compile_source` tests + untouched monolith suite green).

- [ ] **Step 4: Commit**

```bash
git add kdb_compiler/tests/test_compile_source.py
git commit -m "test(task91): lock compile_source error paths (D-91-13 case a)"
```

---

## Self-Review checklist (run before handoff to execution)

1. **Spec coverage:** stages 3 (compile_one) → 4 (validate) → 5 (reconcile) → 6 (canonicalize) → 8 (apply) all wired into `compile_source` (Tasks 3-4). In-memory `CompileJob` + `source_text_for` preference (Task 1) + `source_name`-from-`source_id` fix (Task 3a, spec line 214) = the "Adaptation to existing compile_one" spec section. `kdb-old-compile` freeze (Task 2) = the rebuild's make-before-break. **Not in Plan 1 (later plans):** `detect_orphans` flag (Plan 2), registry (Plan 3), scanner (Plan 4), the loop (Plan 6).
2. **Type consistency:** `CompileSourceResult(cr, pages_written, error, .ok)` defined Task 2, used Tasks 3-5. `compile_source(...)` signature identical across Tasks 3-5.
3. **Open verification points flagged inline:** the `patch_applier` page-path assertion (Task 4 Step 4) and the `ValidationFinding` constructor kwargs (Task 5) are the two places to confirm against real code during execution.
