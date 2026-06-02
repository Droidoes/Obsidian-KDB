# Phase A — Codebase Realignment (in place) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `kdb_compiler/` honest in place — retire the dead batch path, fix two layering defects, rename the lying vocabulary, and route all Kuzu I/O through one door — with **zero live-path behavior change**, gated on a clean **run-6** E2E.

**Architecture:** Phase A of the ratified realignment blueprint (`docs/superpowers/specs/2026-06-01-codebase-realignment-panel-brief.md`). NO files move across package boundaries in Phase A (that is Phase B). Order: retire dead code first (shrinks the surface), then the structural fixes (layering, single Kuzu door), then mechanical renames, then docs, then the gate. Every task ends green; the suite is the regression net for refactors.

**Tech Stack:** Python 3, pytest, Kuzu (graph), Jinja2, `pip install -e .` entry points in `pyproject.toml`.

**Standing rules:**
- Run tests as **`python3 -m pytest -q -m "not live" kdb_compiler/ graphdb_kdb/ kdb_benchmark/`** — `.env` auto-loads API keys, so a bare `pytest` fires live $ tests. NEVER run the live suite as the assistant.
- This plan executes on a dedicated branch (e.g. `refactor/phase-a-realignment`), not `main`.
- After each task: full non-live suite green + the task's stale-reference grep returns nothing → commit.

---

## File-structure map (what Phase A touches)

| Area | Files | Change |
|---|---|---|
| Retire | `kdb_compile.py`, `run_journal.py`, `planner.py`, `compiler.py` (excise `run_compile`/`main`), `pyproject.toml`, `tests/test_kdb_compile.py` | delete / excise |
| Layering | `source_io.py`, `types.py`, `ingestion/frontmatter_embedder.py` | move `parse_existing_frontmatter`↓, `SourceFrontmatter`→`types` |
| Renames | `reconcile.py`, `patch_applier.py`, `source_state_update.py`, `validate_compiled_source_response.py`, `ingestion/`, `ingestion/run_journal.py`, `graph_context_loader.py` (+ all importers, `pyproject.toml`) | `git mv` + import sweep |
| Single Kuzu door | `graphdb_kdb/queries.py` (new context API), `graph_context_loader.py`→`context_loader.py` | new API + migrate off raw `kuzu.Connection` |
| Docs | `docs/CODEBASE_OVERVIEW.md`, `JOURNEY.md`, `kdb_compiler/__init__.py`, `graphdb_kdb/adapters/*`, `canonicalize.py` | rewrite §5, fix `source_state.json`→`manifest.json`, stale-ref sweep |

**Correction to brief v2:** `validate_last_scan.py` is **kept** as a diagnostic, so `test_validate_last_scan.py` is **kept** too. Only `test_kdb_compile.py` is deleted. (Brief v2's A.2 listed both for deletion — that was inconsistent with keeping the module.)

---

## Task 1: Drop the legacy + dead CLI bindings

**Files:** Modify `pyproject.toml` (`[project.scripts]`)

- [ ] **Step 1: Remove the five dead bindings.** Delete these lines from `[project.scripts]`:
  `kdb-compile`, `kdb-old-compile`, `kdb-compile-sources`, `kdb-plan`, `kdb-validate-scan`.
  (Keep: `kdb-orchestrate`, `kdb-enrich`, `kdb-scan`, `kdb-clean`, `kdb-replay`, `kdb-benchmark`, `graphdb-kdb`,
  and for now `kdb-validate`, `kdb-validate-response` — those rationalize in Phase B.)
- [ ] **Step 2: Re-resolve entry points.** Run: `pip install -e . -q` — Expected: succeeds, no `kdb-compile*`/`kdb-plan`/`kdb-validate-scan` console scripts.
- [ ] **Step 3: Verify.** Run: `grep -E "kdb-compile|kdb-old-compile|kdb-compile-sources|kdb-plan|kdb-validate-scan" pyproject.toml` — Expected: no matches.
- [ ] **Step 4: Commit.**
```bash
git add pyproject.toml
git commit -m "refactor(phase-a): drop legacy + dead CLI bindings (kdb-compile/old-compile/compile-sources/plan/validate-scan)"
```

## Task 2: Delete the legacy batch driver + its journal

**Files:** Delete `kdb_compiler/kdb_compile.py`, `kdb_compiler/run_journal.py`, `kdb_compiler/tests/test_kdb_compile.py`

- [ ] **Step 1: Confirm no live importer.** Run: `grep -rn "kdb_compile\b\|from kdb_compiler.run_journal\|import run_journal" --include=*.py kdb_compiler graphdb_kdb kdb_benchmark | grep -v __pycache__ | grep -v "ingestion/run_journal\|test_kdb_compile\|kdb_compile.py:\|run_journal.py:"` — Expected: only references inside the three files being deleted (and the `ingestion/run_journal` which is the *other* journal — leave it).
- [ ] **Step 2: Delete the files.**
```bash
git rm kdb_compiler/kdb_compile.py kdb_compiler/run_journal.py kdb_compiler/tests/test_kdb_compile.py
```
- [ ] **Step 3: Find orphaned test imports.** Run: `grep -rn "kdb_compile\|run_journal" --include=*.py kdb_compiler/tests | grep -v __pycache__ | grep -v "ingestion"` — Expected: none. If any other test imports `kdb_compile`, note it and update/delete that test (it was legacy-driver coverage).
- [ ] **Step 4: Full suite green.** Run: `python3 -m pytest -q -m "not live" kdb_compiler/ graphdb_kdb/ kdb_benchmark/` — Expected: all pass.
- [ ] **Step 5: Commit.**
```bash
git add -A
git commit -m "refactor(phase-a): retire legacy batch driver kdb_compile.py + its 427-ln run_journal.py"
```

## Task 3: Excise the dead `run_compile`/`planner` batch path from `compiler.py`

**Files:** Modify `kdb_compiler/compiler.py` (remove `run_compile` @536, `main` @793, the `planner` import @40, the line-4/15 batch-flow docstring lines); Delete `kdb_compiler/planner.py`

- [ ] **Step 1: Confirm live entries don't use them.** Run: `grep -n "compile_source\|compile_one\|run_compile\|planner" kdb_compiler/kdb_orchestrate.py kdb_benchmark/runner.py` — Expected: orchestrate uses `compile_source`, benchmark uses `compile_one`; neither names `run_compile` or `planner`.
- [ ] **Step 2: Remove `run_compile` and `main` from `compiler.py`** (the functions at lines 536–~660 and 793–end) and drop `planner` from the `from kdb_compiler import (...)` block. Keep `compile_one`, `compile_source`, and all helpers they use. Update the module docstring's pipeline line to drop the `planner` mention.
- [ ] **Step 3: Delete planner.** Run: `git rm kdb_compiler/planner.py`
- [ ] **Step 4: Find orphaned references.** Run: `grep -rn "planner\|run_compile\|compiler.main\|compiler import main" --include=*.py kdb_compiler kdb_benchmark | grep -v __pycache__` — Expected: none outside deleted code. Update/delete any test that imported `run_compile`/`planner` (legacy batch coverage).
- [ ] **Step 5: Full suite green.** Run: `python3 -m pytest -q -m "not live" kdb_compiler/ graphdb_kdb/ kdb_benchmark/` — Expected: all pass (`compile_one`/`compile_source` paths intact).
- [ ] **Step 6: Commit.**
```bash
git add -A
git commit -m "refactor(phase-a): excise dead batch path (run_compile + planner) from compiler.py"
```

## Task 4: Fix the layering inversions (`common` becomes a true leaf)

**Files:** Modify `kdb_compiler/types.py` (gain `SourceFrontmatter`, drop the `source_io` import), `kdb_compiler/source_io.py` (gain `parse_existing_frontmatter` + `_FRONTMATTER_RE`, import `SourceFrontmatter` from `types`, drop the `ingestion.frontmatter_embedder` import), `kdb_compiler/ingestion/frontmatter_embedder.py` (drop the parser def, import it from `source_io`)

- [ ] **Step 1: Write a guard test for the dependency direction.** Create `kdb_compiler/tests/test_layering_leaf.py`:
```python
import ast, pathlib
def _imports(rel):
    src = pathlib.Path(__file__).parents[1] / rel
    tree = ast.parse(src.read_text())
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
    return out

def test_types_does_not_import_source_io():
    assert "kdb_compiler.source_io" not in _imports("types.py")

def test_source_io_does_not_import_ingestion():
    assert not any(m.startswith("kdb_compiler.ingestion") for m in _imports("source_io.py"))
```
- [ ] **Step 2: Run it — expect failure.** Run: `python3 -m pytest -q kdb_compiler/tests/test_layering_leaf.py` — Expected: both FAIL (the inversions still exist).
- [ ] **Step 3: Move `SourceFrontmatter`** dataclass definition from `source_io.py` into `types.py`. In `source_io.py`, replace the definition with `from kdb_compiler.types import SourceFrontmatter`. Remove the now-unused `TYPE_CHECKING` import of `SourceFrontmatter` from `types.py`.
- [ ] **Step 4: Move the parser down.** Cut `_FRONTMATTER_RE` (frontmatter_embedder.py:20) and `parse_existing_frontmatter` (line 34) into `source_io.py`. In `frontmatter_embedder.py`, replace with `from kdb_compiler.source_io import parse_existing_frontmatter`. In `source_io.py`, remove `from kdb_compiler.ingestion.frontmatter_embedder import parse_existing_frontmatter`.
- [ ] **Step 5: Guard test passes + full suite green.** Run: `python3 -m pytest -q -m "not live" kdb_compiler/tests/test_layering_leaf.py kdb_compiler/ graphdb_kdb/ kdb_benchmark/` — Expected: all pass.
- [ ] **Step 6: Commit.**
```bash
git add -A
git commit -m "refactor(phase-a): fix layering inversions — SourceFrontmatter->types, parser->source_io; common is now a leaf"
```

## Task 5: Rename `reconcile` → `repair`

**Files:** `git mv kdb_compiler/reconcile.py kdb_compiler/repair.py`; update importers (`compiler.py`, tests)

- [ ] **Step 1: Move + rename the symbol.** `git mv kdb_compiler/reconcile.py kdb_compiler/repair.py`. Inside `repair.py`, rename the public `reconcile()` function → `repair()` and `ReconcileError` → `RepairError` (keep behavior identical).
- [ ] **Step 2: Update importers.** Run: `grep -rln "reconcile\|ReconcileError" --include=*.py kdb_compiler | grep -v __pycache__` then update each (notably `compiler.py`) to import from `kdb_compiler.repair` and call `repair()`/`RepairError`. Rename the test file `git mv kdb_compiler/tests/test_reconcile.py kdb_compiler/tests/test_repair.py` (if present) and update its imports/asserts.
- [ ] **Step 3: Stale-reference grep.** Run: `grep -rn "\breconcile\b\|ReconcileError\|reconcile_slug_lists\|reconcile_body_links" --include=*.py kdb_compiler | grep -v __pycache__ | grep -v "# "` — Expected: only intended residual (e.g. internal helper names you chose to keep). Note: the *cleanup* tool's cross-store "reconcile" lives in `kdb_clean` — leave it.
- [ ] **Step 4: Full suite green.** Run: `python3 -m pytest -q -m "not live" kdb_compiler/ graphdb_kdb/ kdb_benchmark/` — Expected: all pass.
- [ ] **Step 5: Commit.**
```bash
git add -A
git commit -m "refactor(phase-a): rename compiler reconcile -> repair (frees 'reconcile' for the cleanup cross-store job)"
```

## Task 6: Rename `patch_applier` → `page_writer`

**Files:** `git mv kdb_compiler/patch_applier.py kdb_compiler/page_writer.py`; update importer (`kdb_orchestrate.py`) + tests

- [ ] **Step 1: Move.** `git mv kdb_compiler/patch_applier.py kdb_compiler/page_writer.py`. Rename the test file if present (`test_patch_applier.py` → `test_page_writer.py`).
- [ ] **Step 2: Update importers.** Run: `grep -rln "patch_applier" --include=*.py kdb_compiler | grep -v __pycache__` and update each (`kdb_orchestrate.py` imports it) to `kdb_compiler.page_writer`.
- [ ] **Step 3: Stale grep.** Run: `grep -rn "patch_applier" --include=*.py kdb_compiler | grep -v __pycache__` — Expected: none.
- [ ] **Step 4: Full suite green.** Run: `python3 -m pytest -q -m "not live" kdb_compiler/ graphdb_kdb/ kdb_benchmark/` — Expected: all pass.
- [ ] **Step 5: Commit.**
```bash
git add -A
git commit -m "refactor(phase-a): rename patch_applier -> page_writer (it writes wiki pages; 'patch' was dead vocabulary)"
```

## Task 7: Rename `source_state_update` → `manifest_writer`

**Files:** `git mv kdb_compiler/source_state_update.py kdb_compiler/manifest_writer.py`; update importer (`kdb_orchestrate.py`) + tests. *(Module name `manifest_writer` chosen for consistency with the retained `manifest.json` file — flip to `source_state_writer` if preferred.)*

- [ ] **Step 1: Move.** `git mv kdb_compiler/source_state_update.py kdb_compiler/manifest_writer.py`. Rename test file if present.
- [ ] **Step 2: Update importers.** Run: `grep -rln "source_state_update" --include=*.py kdb_compiler | grep -v __pycache__` and update each to `kdb_compiler.manifest_writer`.
- [ ] **Step 3: Stale grep.** Run: `grep -rn "source_state_update" --include=*.py kdb_compiler | grep -v __pycache__` — Expected: none.
- [ ] **Step 4: Full suite green.** Run: `python3 -m pytest -q -m "not live" kdb_compiler/ graphdb_kdb/ kdb_benchmark/` — Expected: all pass.
- [ ] **Step 5: Commit.**
```bash
git add -A
git commit -m "refactor(phase-a): rename source_state_update -> manifest_writer (names what it does; file stays manifest.json)"
```

## Task 8: Rename `validate_compiled_source_response` → `validate_source_response`

**Files:** `git mv` the module; update importers (`compiler.py`, `response_replay.py`, `kdb_benchmark/scorer.py`) + the `kdb-validate-response` binding path in `pyproject.toml` + tests

- [ ] **Step 1: Move.** `git mv kdb_compiler/validate_compiled_source_response.py kdb_compiler/validate_source_response.py`. Rename test file if present.
- [ ] **Step 2: Update importers + binding.** Run: `grep -rln "validate_compiled_source_response" --include=*.py --include=*.toml . | grep -v __pycache__` and update each (`compiler.py`, `response_replay.py`, `kdb_benchmark/scorer.py`, and `pyproject.toml`'s `kdb-validate-response = "kdb_compiler.validate_source_response:main"`).
- [ ] **Step 3: Stale grep + re-resolve.** Run: `grep -rn "validate_compiled_source_response" --include=*.py --include=*.toml . | grep -v __pycache__` (Expected: none) then `pip install -e . -q`.
- [ ] **Step 4: Full suite green.** Run: `python3 -m pytest -q -m "not live" kdb_compiler/ graphdb_kdb/ kdb_benchmark/` — Expected: all pass.
- [ ] **Step 5: Commit.**
```bash
git add -A
git commit -m "refactor(phase-a): rename validate_compiled_source_response -> validate_source_response"
```

## Task 9: Rename `ingestion/` → `enrich/` (+ `run_journal.py` → `enrich_journal.py`)

**Files:** `git mv kdb_compiler/ingestion kdb_compiler/enrich`; `git mv kdb_compiler/enrich/run_journal.py kdb_compiler/enrich/enrich_journal.py`; sweep all `kdb_compiler.ingestion` imports → `kdb_compiler.enrich`; update `kdb-enrich` binding path

- [ ] **Step 1: Move the package + the journal.**
```bash
git mv kdb_compiler/ingestion kdb_compiler/enrich
git mv kdb_compiler/enrich/run_journal.py kdb_compiler/enrich/enrich_journal.py
```
- [ ] **Step 2: Sweep imports.** Run: `grep -rln "kdb_compiler.ingestion\|ingestion.run_journal\|enrich.run_journal" --include=*.py --include=*.toml . | grep -v __pycache__` then update each: `kdb_compiler.ingestion` → `kdb_compiler.enrich`, and the journal import → `kdb_compiler.enrich.enrich_journal`. Update `pyproject.toml`: `kdb-enrich = "kdb_compiler.enrich.kdb_enrich:main"`.
- [ ] **Step 3: Move tests.** `git mv` any `kdb_compiler/tests/test_pass1*.py` / ingestion tests references are import-only — just fix their imports in the sweep. (Test *files* stay in `kdb_compiler/tests/`.)
- [ ] **Step 4: Stale grep + re-resolve.** Run: `grep -rn "kdb_compiler.ingestion\|enrich.run_journal\b" --include=*.py --include=*.toml . | grep -v __pycache__` (Expected: none) then `pip install -e . -q`.
- [ ] **Step 5: Full suite green.** Run: `python3 -m pytest -q -m "not live" kdb_compiler/ graphdb_kdb/ kdb_benchmark/` — Expected: all pass.
- [ ] **Step 6: Commit.**
```bash
git add -A
git commit -m "refactor(phase-a): rename ingestion/ -> enrich/ (Pass-1 stage) + run_journal -> enrich_journal"
```

## Task 10: Add the graph context-snapshot read API (single Kuzu door — part 1)

**Files:** Modify `graphdb_kdb/queries.py` (add the read primitives `context_loader` needs); Test `graphdb_kdb/tests/test_queries_context.py`

**Why:** `graph_context_loader.py` opens its own `kuzu.Connection` and runs ~7 distinct Cypher reads (active entities, domain pool, T1 source-supported, T3 neighbors, PageRank input edges, batched outgoing links, alias→canonical). A.3 moves those reads behind the graph package's API so the graph owns all Kuzu I/O.

- [ ] **Step 1: Enumerate the reads to expose.** Open `kdb_compiler/graph_context_loader.py` and list every function that takes a `kuzu.Connection` (e.g. `_load_active_entities`, `_domain_pool`, `_t1_source_supported`, `_t3_neighbors`, `_pagerank_scores`, `_batch_outgoing_links`, alias resolution). These become the API surface.
- [ ] **Step 2: Write failing tests for the new API.** Create `graphdb_kdb/tests/test_queries_context.py` with one test per primitive, seeding a temp Kuzu graph via the existing test fixtures (mirror `graphdb_kdb/tests/test_queries.py` setup), e.g.:
```python
def test_active_entities_returns_seeded(tmp_graph_with_entities):
    conn = tmp_graph_with_entities
    from graphdb_kdb.queries import active_entities
    rows = active_entities(conn)
    assert any(r["slug"] == "value-investing" for r in rows)
```
  (Write a test for each primitive you enumerated in Step 1; reuse the seeding helper from `test_queries.py`.)
- [ ] **Step 3: Run — expect failure.** Run: `python3 -m pytest -q graphdb_kdb/tests/test_queries_context.py` — Expected: FAIL (functions not defined).
- [ ] **Step 4: Implement the primitives** in `graphdb_kdb/queries.py` by moving each Cypher string out of `graph_context_loader.py` into a named query function taking `conn` and returning plain dicts/lists (no compiler types — keep `queries.py` graph-only).
- [ ] **Step 5: Tests pass.** Run: `python3 -m pytest -q graphdb_kdb/tests/test_queries_context.py` — Expected: PASS.
- [ ] **Step 6: Commit.**
```bash
git add -A
git commit -m "feat(phase-a): graph context-snapshot read API in queries.py (single Kuzu door, part 1)"
```

## Task 11: Migrate the loader onto the API + rename → `context_loader` (single Kuzu door — part 2)

**Files:** `git mv kdb_compiler/graph_context_loader.py kdb_compiler/context_loader.py`; modify it to call `graphdb_kdb.queries.*` instead of raw `kuzu`; update importer (`compiler.py`)

- [ ] **Step 1: Move + rename.** `git mv kdb_compiler/graph_context_loader.py kdb_compiler/context_loader.py`. Rename the test file if present.
- [ ] **Step 2: Replace raw Kuzu with API calls.** Remove `import kuzu` and all raw `conn.execute(...)` Cypher; call the `graphdb_kdb.queries.*` primitives from Task 10. The ranking/T2Mode/cold-start/domain-scoping composition logic **stays** in `context_loader` — only the reads move out.
- [ ] **Step 3: Update importers.** Run: `grep -rln "graph_context_loader" --include=*.py kdb_compiler | grep -v __pycache__` and update each (`compiler.py`) to `kdb_compiler.context_loader`.
- [ ] **Step 4: Prove the door is shut.** Run: `grep -n "import kuzu\|kuzu.Connection" kdb_compiler/context_loader.py` — Expected: none. Run: `grep -rln "import kuzu" --include=*.py kdb_compiler | grep -v __pycache__ | grep -v kdb_clean` — Expected: empty (only `kdb_clean`, a tool, may still touch the graph directly — acceptable, noted for Phase B).
- [ ] **Step 5: Behavior unchanged — full suite green.** Run: `python3 -m pytest -q -m "not live" kdb_compiler/ graphdb_kdb/ kdb_benchmark/` — Expected: all pass (existing T2/T3 context tests are the behavior gate).
- [ ] **Step 6: Commit.**
```bash
git add -A
git commit -m "refactor(phase-a): graph_context_loader -> context_loader, reads via graph API (single Kuzu door, part 2)"
```

## Task 12: North Star rewrite + stale-reference sweep

**Files:** `docs/CODEBASE_OVERVIEW.md` (§5 + `source_state.json` refs + `manifest_update` refs), `docs/JOURNEY.md` (`source_state.json` ref), `kdb_compiler/__init__.py` (stale pipeline comment), `graphdb_kdb/adapters/obsidian_runs.py` + `adapters/base.py` + `kdb_compiler/canonicalize.py` (kdb_compile comments), `scripts/migrate_task64_supersession.py` + `migrate_task66_compiled_hash.py` (manifest_update refs)

- [ ] **Step 1: Rewrite `CODEBASE_OVERVIEW.md` §5** to the decided architecture (blueprint §1.3): `scan → enrich → compile → graph`, conducted by `kdb_orchestrate.py`; delete the description of `kdb_compile.py` as the 10-stage orchestrator.
- [ ] **Step 2: Fix the disk-noun consistency.** Run: `grep -rln "source_state.json" docs/CODEBASE_OVERVIEW.md docs/JOURNEY.md` and replace `source_state.json` → `manifest.json` (the file's real name; content is source-state — note that inline).
- [ ] **Step 3: Stale-ref sweep.** Run: `grep -rn "manifest_update\|kdb_compile" docs/CODEBASE_OVERVIEW.md kdb_compiler/__init__.py graphdb_kdb/adapters/ kdb_compiler/canonicalize.py scripts/` and fix each: rewrite `kdb_compiler/__init__.py`'s linear-pipeline docstring to the orchestrator flow; update comments naming `kdb_compile.py` → `kdb_orchestrate.py`; mark the one-shot `scripts/migrate_task6*.py` as historical (or drop their dead `manifest_update` references).
- [ ] **Step 4: Verify no stale driver/file names in docs+code comments.** Run: `grep -rn "kdb_compile\b" --include=*.py kdb_compiler graphdb_kdb | grep -v __pycache__` — Expected: none.
- [ ] **Step 5: Commit.**
```bash
git add -A
git commit -m "docs(phase-a): rewrite North Star §5 to the orchestrator architecture + stale-ref/manifest-noun sweep"
```

## Task 13: Phase-A gate — non-live green, then live run-6

**Files:** none (verification)

- [ ] **Step 1: Full non-live suite green.** Run: `python3 -m pytest -q -m "not live" kdb_compiler/ graphdb_kdb/ kdb_benchmark/` — Expected: all pass, count ≥ the pre-Phase-A baseline minus the deleted legacy tests.
- [ ] **Step 2: Editable install resolves.** Run: `pip install -e . -q && kdb-orchestrate --help` — Expected: succeeds; no dropped commands present; `kdb-orchestrate` works.
- [ ] **Step 3: Hand off the live gate to Joseph.** Present the run-6 commands (reset + `kdb-orchestrate` on the sandbox vault `~/Obsidian/Vault-in-place-test-run`; runbook `docs/reference/test-run-procedure.md`). **Joseph fires the live run** (API cost). Pass criteria: `exit_reason=ok`, 0 quarantined, 0 invariant, links wired, 0 orphans — i.e. a clean E2E matching the run-5/v0.5.0 standard.
- [ ] **Step 4: On clean run-6 — Phase A is DONE.** Record the gate result in `docs/RELEASES.md`/daily note; Phase A merges; Phase B begins.

---

## Self-review notes
- **Spec coverage:** A.1 (Tasks 5–9, 11) · A.2 (Tasks 1–3) · A.3 (Tasks 10–11) · A.4 (Task 4) · A.5 (Task 12) · A.6 (Task 13). All covered.
- **No behavior change** in Tasks 1–9, 11–12 — the existing suite is the regression net; each task adds a stale-reference grep as the structural check. Tasks 4 and 10 add real new tests (layering guard, graph API).
- **Ordering:** retire first (shrink surface) → layering leaf → renames → single Kuzu door → docs → gate. Renames after retirement so dead importers don't need updating.
