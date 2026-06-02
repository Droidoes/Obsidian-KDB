# Phase B — Structural split into peer packages — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the flat `kdb_compiler/` package (plus top-level `graphdb_kdb/` and `kdb_benchmark/`) into **six peer top-level packages** — `common` · `ingestion` · `compiler` · `kdb_graph` · `orchestrator` · `tools` — with **zero live-path behavior change**, gated on a clean **run-7** E2E.

**Architecture:** Phase B of the ratified realignment blueprint (`docs/superpowers/specs/2026-06-01-codebase-realignment-panel-brief.md` §B). This is **move-don't-rewrite**: `git mv` modules into peer packages and rewrite imports; do not rewrite logic. Extract **leaf-first** in dependency order (`common → kdb_graph → ingestion → compiler → orchestrator → tools`) so each extracted package's imports resolve against already-moved packages. The existing **1175-test non-live suite is the regression net**; each task ends green. Only two tasks add real new tests (the dependency-contract guard; the `resp_stats_writer` split).

**Tech Stack:** Python 3, pytest, Kuzu (graph), Jinja2, setuptools (`pip install -e .`), `pyproject.toml` `[project.scripts]` entry points.

---

## Standing rules

- **Tests:** `python3 -m pytest -q -m "not live" common/ ingestion/ compiler/ kdb_graph/ orchestrator/ tools/` once dirs exist; until then include whichever of `kdb_compiler/ graphdb_kdb/ kdb_benchmark/` still hold tests. `.env` auto-loads API keys, so a bare `pytest` fires live `$` tests — **NEVER run the live suite as the assistant** (Joseph fires run-7).
- **Branch:** this plan executes on a dedicated branch `refactor/phase-b-package-split`, not `main`.
- **After each task:** full non-live suite green + the task's stale-reference grep returns nothing + `pip install -e . -q` still resolves → commit.
- **Constraints (binding, from blueprint):** move-don't-duplicate · prefer renames/moves over rewrites (reversibility) · single-user (no locking/retry ceremony) · leave a clean `ingestion/feeder/` seam for 0.6 · surface-don't-delete anything on a live path.
- **The `kdb_compiler/` directory persists (shrinking) until its last module leaves and tests redistribute (Task 11). It is the staging ground, not deleted early.**
- **Sweep order within a task:** handle the grouped/multi-name `from kdb_compiler import (a, b, …)` statements that mix a moved + not-yet-moved module **by hand FIRST**, then run the targeted `sed`. The `sed`s only match single-name `from kdb_compiler import <mod>` lines; a mixed grouped line they leave alone surfaces as an `ImportError` (red), not silent corruption — fixing first just avoids a red-loop. Hazard sites: `compiler.py`, `kdb_orchestrate.py`, `response_replay.py`.

---

## Target tree (what Phase B produces)

```
common/         atomic_io · call_model · call_model_retry · run_context · types · source_io · paths ·
                config/ (settings) · llm_telemetry (NEW: generic half of resp_stats_writer) · __version__
ingestion/      kdb_scan · enrich/ (was kdb_compiler/enrich) · config/ (pipeline_registry + domains.json +
                source_types.json + scope-config.yaml) · feeder/ (empty seam for 0.6)
compiler/       compiler · prompt_builder · response_normalizer · repair · canonicalize · page_writer ·
                validate_compile_result · validate_source_response · context_loader ·
                resp_summary (NEW: compiler half of resp_stats_writer) · schemas/*.json
kdb_graph/      (git mv of graphdb_kdb) graphdb · ingestor · queries · rebuilder · schema · snapshot ·
                verifier · analytics · types · cli · adapters/ · ops/ · core/ (dormant 2.0)
orchestrator/   kdb_orchestrate · orchestrator_events · manifest_writer
tools/          cleanup (was kdb_clean) · replay (was response_replay) · benchmark/ (was kdb_benchmark) ·
                diagnostics/ (validate_last_scan + last_scan.schema.json) · viewer/ (already here)
```

**Module → target package map** (65 modules, 0 unassigned; verified by survey):

| Target | Modules (current `kdb_compiler/` unless noted) |
|---|---|
| **common** | atomic_io · call_model · call_model_retry · run_context · types · source_io · paths · config/ (settings `__init__.py` only) · `__version__` (from `__init__.py`) |
| **ingestion** | kdb_scan · enrich/* (11) · pipeline_registry → `ingestion/config/` · `config/domains.json`+`source_types.json`+`scope-config.yaml` → `ingestion/config/` |
| **compiler** | compiler · prompt_builder · response_normalizer · repair · canonicalize · page_writer · validate_compile_result · validate_source_response · context_loader · schemas/*.json |
| **kdb_graph** | all of `graphdb_kdb/*` (19, incl. adapters/, ops/, core/) — pure package rename |
| **orchestrator** | kdb_orchestrate · orchestrator_events · manifest_writer |
| **tools** | kdb_clean→`tools/cleanup.py` · response_replay→`tools/replay.py` · validate_last_scan→`tools/diagnostics/` · `kdb_benchmark/*` (7)→`tools/benchmark/` |
| **SPLIT** | `resp_stats_writer.py` → generic half `common/llm_telemetry.py` + compiler half `compiler/resp_summary.py` (Task 8) |

---

## Surfaced decisions (baked into the plan; flagged for review)

1. **`config/` split** (resolved above): settings `__init__.py` → `common/config/`; vocab data + `pipeline_registry` → `ingestion/config/`. Two distinct namespaces, both named in B.1.
2. **`__version__` home:** currently `kdb_compiler/__init__.py`. Moves to **`common/__init__.py`**; `kdb_benchmark/runner.py:36` (`from kdb_compiler import __version__`) repoints to `from common import __version__`.
3. **`kdb_scan` stays a module** (`ingestion/kdb_scan.py`), not a `scan/` subpackage — minimal move. The blueprint tree's `scan/`/`feeder/` sub-structuring is left as a future seam (we create an empty `ingestion/feeder/` for 0.6, per the constraint).
4. **Module renames in `tools`:** `kdb_clean`→`cleanup`, `response_replay`→`replay` (blueprint B.2 names). `validate_last_scan` keeps its filename inside `tools/diagnostics/`. `kdb_benchmark` module filenames unchanged inside `tools/benchmark/`.
5. **Known dependency-contract exception:** the contract says "nothing depends on `tools`", but `kdb_orchestrate.finalize` calls `kdb_clean` inline (structural exhibit 1.4) → `orchestrator → tools/cleanup` edge persists. **Decoupling cleanup from the orchestrator is a behavior change, out of Phase B's move-only scope.** The Task 12 dependency-guard test encodes the contract **with this one documented exception**; full decoupling is deferred (note it in the North Star).

---

## Task 1: Branch + scaffold the six packages

**Files:** Create `common/__init__.py`, `ingestion/__init__.py`, `ingestion/config/__init__.py`, `ingestion/feeder/__init__.py`, `compiler/__init__.py`, `orchestrator/__init__.py`, `tools/__init__.py`, `tools/diagnostics/__init__.py`, `tools/benchmark/__init__.py` (note: `tools/viewer/` already exists; `kdb_graph/` is created by Task 4's `git mv`).

- [ ] **Step 1: Branch.** Run: `git checkout -b refactor/phase-b-package-split` — Expected: on the new branch off `main`.
- [ ] **Step 2: Create the package dirs with empty `__init__.py`.**
```bash
for p in common ingestion ingestion/config ingestion/feeder compiler orchestrator tools tools/diagnostics tools/benchmark; do
  mkdir -p "$p" && touch "$p/__init__.py"
done
```
(`tools/viewer/` already exists. Do **not** create `kdb_graph/` — Task 4 `git mv`s `graphdb_kdb` onto it.)
- [ ] **Step 3: Add the empty-feeder seam marker.** Put a one-line docstring in `ingestion/feeder/__init__.py`: `"""0.6 ingestion feeders land here (seam reserved by Phase B)."""`
- [ ] **Step 4: Verify nothing breaks.** Run: `python3 -m pytest -q -m "not live" kdb_compiler/ graphdb_kdb/ kdb_benchmark/` — Expected: all pass (new empty packages are inert).
- [ ] **Step 5: Commit.**
```bash
git add -A
git commit -m "refactor(phase-b): scaffold six peer packages (empty) + ingestion/feeder seam"
```

## Task 2: Extract `common` (the leaf) + the `__version__`

**Files:** `git mv` into `common/`: `atomic_io.py` · `call_model.py` · `call_model_retry.py` · `run_context.py` · `types.py` · `source_io.py` · `paths.py` · `config/` (the whole dir — but **first** pull the vocab data out, see Step 2). Move `__version__` from `kdb_compiler/__init__.py` → `common/__init__.py`.

- [ ] **Step 1: Move the eight leaf modules.**
```bash
git mv kdb_compiler/atomic_io.py kdb_compiler/call_model.py kdb_compiler/call_model_retry.py \
       kdb_compiler/run_context.py kdb_compiler/types.py kdb_compiler/source_io.py kdb_compiler/paths.py common/
```
- [ ] **Step 2: Move the settings package, leaving vocab data behind for Task 5.** The vocab data (`domains.json`, `source_types.json`, `scope-config.yaml`) belongs to `ingestion/config` (Task 5), not `common`. Move only the settings code:
```bash
git mv kdb_compiler/config/__init__.py common/config/__init__.py   # common/config/ already exists from Task 1
git mv kdb_compiler/config/domains.json kdb_compiler/config/source_types.json kdb_compiler/config/scope-config.yaml ingestion/config/
rmdir kdb_compiler/config 2>/dev/null || true
```
- [ ] **Step 3: Move `__version__`.** Read `kdb_compiler/__init__.py`; cut the `__version__ = "..."` line into `common/__init__.py`. Leave `kdb_compiler/__init__.py` (it still hosts shrinking modules); if it had only the version + a stale pipeline docstring, reduce it to a short transitional docstring.
- [ ] **Step 4: Sweep imports → `common`.** Rewrite every importer of the moved modules. The moved module names are: `atomic_io call_model call_model_retry run_context types source_io paths config`. For each, rewrite `kdb_compiler.<mod>` → `common.<mod>` and `from kdb_compiler import <mod>` → `from common import <mod>`, plus `from kdb_compiler.config import settings` → `from common.config import settings`, and `from kdb_compiler import __version__` → `from common import __version__`.
```bash
mods="atomic_io call_model call_model_retry run_context types source_io paths"
files=$(grep -rln "kdb_compiler" --include=*.py . | grep -v __pycache__)
for f in $files; do
  for m in $mods; do
    sed -i -E "s/\bkdb_compiler\.$m\b/common.$m/g; s/from kdb_compiler import $m\b/from common import $m/g" "$f"
  done
  sed -i -E "s/from kdb_compiler\.config import/from common.config import/g; s/from kdb_compiler import __version__/from common import __version__/g" "$f"
done
```
  **HAZARD — grouped imports:** `compiler.py:29` has `from kdb_compiler import (\n repair, ... )` spanning common + compiler modules. The `sed` above only catches single-name `from kdb_compiler import <mod>`. **Manually split** any multi-name `from kdb_compiler import (...)` block: move the common-bound names (`atomic_io`, `call_model`, `call_model_retry`, `run_context`, `types`, `source_io`, `paths`) into a `from common import (...)` block; leave the rest as `from kdb_compiler import (...)` for now (they move in later tasks). Check `compiler.py`, `kdb_orchestrate.py`, `response_replay.py`, `canonicalize.py`, `kdb_clean.py`, `kdb_scan.py`, `validate_compile_result.py`, `benchmark/runner.py`.
- [ ] **Step 5: Update `pyproject` discovery so the new packages are importable in editable mode.** In `[tool.setuptools.packages.find]`, add the new names to `include`: `["kdb_compiler*", "kdb_benchmark*", "graphdb_kdb*", "common*", "ingestion*", "compiler*", "orchestrator*", "tools*"]` (keep the old names until their packages are emptied; `kdb_graph*` is added in Task 4). Run `pip install -e . -q`.
- [ ] **Step 6: Stale-ref grep.** Run: `grep -rn "kdb_compiler\.\(atomic_io\|call_model\|call_model_retry\|run_context\|types\|source_io\|paths\|config\)\b" --include=*.py . | grep -v __pycache__` — Expected: none.
- [ ] **Step 7: Full suite green.** Run the standing-rules pytest command (include `common/` now). Expected: all pass.
- [ ] **Step 8: Commit.**
```bash
git add -A
git commit -m "refactor(phase-b): extract common/ (atomic_io·call_model[_retry]·run_context·types·source_io·paths·config-settings·__version__); split vocab data out to ingestion/config"
```

## Task 3: Add the dependency-contract guard test (initially permissive)

**Files:** Create `tools/tests/test_package_boundaries.py` (or a root `tests/` — placed under `tools/` so it ships with a package pytest can find). This test grows teeth in Task 12; here it just establishes the harness and asserts the **`common` leaf** property, which is already true after Task 2.

- [ ] **Step 1: Write the guard.** Create `tools/tests/test_package_boundaries.py`:
```python
import ast, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
INTERNAL = {"common", "ingestion", "compiler", "kdb_graph", "orchestrator", "tools",
            "kdb_compiler", "graphdb_kdb", "kdb_benchmark"}

def _top_level_imports(pkg: str) -> set[str]:
    """All internal top-level packages imported anywhere under ROOT/pkg (non-test .py)."""
    out: set[str] = set()
    for path in (ROOT / pkg).rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text())
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module:
                root = n.module.split(".")[0]
                if root in INTERNAL and root != pkg:
                    out.add(root)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    root = a.name.split(".")[0]
                    if root in INTERNAL and root != pkg:
                        out.add(root)
    return out

def test_common_is_a_leaf():
    assert _top_level_imports("common") == set(), \
        f"common must import no internal package, found: {_top_level_imports('common')}"
```
- [ ] **Step 2: Run it.** Run: `python3 -m pytest -q tools/tests/test_package_boundaries.py` — Expected: PASS (`common` imports nothing internal).
- [ ] **Step 3: Add `tools/tests` to a temporary testpaths** so it runs in the suite: in `[tool.pytest.ini_options].testpaths`, append `"tools/tests"`. (Final testpaths set in Task 11.)
- [ ] **Step 4: Commit.**
```bash
git add -A
git commit -m "refactor(phase-b): add package-boundary guard test (asserts common is a leaf)"
```

## Task 4: Rename `graphdb_kdb` → `kdb_graph` (pure package rename)

**Files:** `git mv graphdb_kdb kdb_graph`; sweep all `graphdb_kdb` imports → `kdb_graph`; update the `graphdb-kdb` entry point. CLI **name** stays `graphdb-kdb`.

- [ ] **Step 1: Move the package.** Run: `git mv graphdb_kdb kdb_graph`.
- [ ] **Step 2: Sweep imports.** Run:
```bash
for f in $(grep -rln "graphdb_kdb" --include=*.py . | grep -v __pycache__); do
  sed -i -E "s/\bgraphdb_kdb\b/kdb_graph/g" "$f"
done
```
  (This rewrites `import kdb_graph`, `from kdb_graph...`, `kdb_graph.queries`, etc. There are ~20 sites incl. `context_loader`, `kdb_clean`, `kdb_orchestrate`, viewer, and `kdb_graph/`-internal imports.)
- [ ] **Step 3: Update the entry point + discovery.** In `pyproject.toml` `[project.scripts]`: `graphdb-kdb = "kdb_graph.cli:main"`. In `[tool.setuptools.packages.find].include`, replace `"graphdb_kdb*"` with `"kdb_graph*"`. Run `pip install -e . -q`.
- [ ] **Step 4: Stale-ref grep.** Run: `grep -rn "graphdb_kdb" --include=*.py --include=*.toml . | grep -v __pycache__` — Expected: none (the CLI *string* `graphdb-kdb` is hyphenated, not `graphdb_kdb`, so it won't match).
- [ ] **Step 5: Full suite green** (now include `kdb_graph/`). Run the standing pytest. Expected: all pass.
- [ ] **Step 6: Commit.**
```bash
git add -A
git commit -m "refactor(phase-b): rename python package graphdb_kdb -> kdb_graph (graphdb-kdb CLI name unchanged)"
```

## Task 5: Extract `ingestion` (scan · enrich · config)

**Files:** `git mv kdb_compiler/kdb_scan.py ingestion/`; `git mv kdb_compiler/enrich ingestion/enrich`; `git mv kdb_compiler/pipeline_registry.py ingestion/config/`. (Vocab data already landed in `ingestion/config/` in Task 2 Step 2.) Update the `kdb-scan` + `kdb-enrich` entry points + the vocab-data loader paths.

- [ ] **Step 1: Move the modules.**
```bash
git mv kdb_compiler/kdb_scan.py ingestion/
git mv kdb_compiler/enrich ingestion/enrich
git mv kdb_compiler/pipeline_registry.py ingestion/config/pipeline_registry.py
```
- [ ] **Step 2: Fix the vocab-data loader paths.** `ingestion/enrich/config_loader.py` and `ingestion/config/pipeline_registry.py` locate `domains.json`/`source_types.json`/`scope-config.yaml` by a `Path(__file__).parent…` expression that assumed the old `kdb_compiler/config/` location. Update each to point at `ingestion/config/` (e.g. `Path(__file__).resolve().parents[1] / "config" / "domains.json"` from within `enrich/`). **Grep first:** `grep -rn "domains.json\|source_types.json\|scope-config\|scope_config" ingestion/ | grep -v __pycache__` and fix every path constant.
- [ ] **Step 3: Sweep imports.** Rewrite importers of the moved modules:
```bash
for f in $(grep -rln "kdb_compiler" --include=*.py . | grep -v __pycache__); do
  sed -i -E "s/\bkdb_compiler\.kdb_scan\b/ingestion.kdb_scan/g; s/from kdb_compiler import kdb_scan\b/from ingestion import kdb_scan/g" "$f"
  sed -i -E "s/\bkdb_compiler\.enrich\b/ingestion.enrich/g; s/from kdb_compiler\.enrich\b/from ingestion.enrich/g" "$f"
  sed -i -E "s/\bkdb_compiler\.pipeline_registry\b/ingestion.config.pipeline_registry/g" "$f"
done
```
  **HAZARD:** `kdb_orchestrate.py:30` `from kdb_compiler import manifest_writer, page_writer, pipeline_registry` — split it: `pipeline_registry` → `from ingestion.config import pipeline_registry`; leave `manifest_writer`/`page_writer` for Tasks 7/8. Also fix any `from kdb_compiler import kdb_scan`-style grouped lines.
- [ ] **Step 4: Update entry points + package-data + discovery.** `pyproject` `[project.scripts]`: `kdb-scan = "ingestion.kdb_scan:main"`, `kdb-enrich = "ingestion.enrich.kdb_enrich:main"`. `[tool.setuptools.package-data]`: add `ingestion = ["config/*.json", "config/*.yaml", "enrich/*.j2"]` (covers the vocab data + the Pass-1 Jinja template `pass1_prompt.j2`). Run `pip install -e . -q`.
- [ ] **Step 5: Stale-ref grep.** Run: `grep -rn "kdb_compiler\.\(kdb_scan\|enrich\|pipeline_registry\)\b" --include=*.py . | grep -v __pycache__` — Expected: none.
- [ ] **Step 6: Guard the Jinja-template path with a NON-live test.** The `pass1_prompt.j2` template is loaded via a `FileSystemLoader` path that moved with `enrich/`. A broken path here passes every existing non-live test but **breaks run-7 at live time.** Confirm a non-live test renders the template; if none exists, add `ingestion/tests/test_pass1_prompt_render.py`:
```python
def test_pass1_prompt_template_resolves():
    from ingestion.enrich.pass1_prompt import render_pass1_prompt  # adjust to real symbol
    out = render_pass1_prompt(source_text="x", title="t")          # minimal args; adjust signature
    assert isinstance(out, str) and out
```
  (Inspect `ingestion/enrich/pass1_prompt.py` for the real render function + signature.) Run it; Expected: PASS (template path resolves).
- [ ] **Step 7: Full suite green** (include `ingestion/`). Run the standing pytest. Expected: all pass — the Pass-1 config-loader tests gate the vocab-data paths; the render test gates the template path.
- [ ] **Step 8: Commit.**
```bash
git add -A
git commit -m "refactor(phase-b): extract ingestion/ (kdb_scan·enrich·config[pipeline_registry+vocab data]); repoint loader paths + entry points"
```

## Task 6: Extract `compiler` (compile + helpers + schemas)

**Files:** `git mv` into `compiler/`: `compiler.py` · `prompt_builder.py` · `response_normalizer.py` · `repair.py` · `canonicalize.py` · `page_writer.py` · `validate_compile_result.py` · `validate_source_response.py` · `context_loader.py` · `schemas/` (the dir). Update `kdb-validate` + `kdb-validate-response` entry points.

- [ ] **Step 1: Move the modules + schemas.**
```bash
git mv kdb_compiler/compiler.py kdb_compiler/prompt_builder.py kdb_compiler/response_normalizer.py \
       kdb_compiler/repair.py kdb_compiler/canonicalize.py kdb_compiler/page_writer.py \
       kdb_compiler/validate_compile_result.py kdb_compiler/validate_source_response.py \
       kdb_compiler/context_loader.py compiler/
git mv kdb_compiler/schemas/compile_result.schema.json kdb_compiler/schemas/compiled_source_response.schema.json compiler/schemas/
```
  **Move ONLY the two compiler schemas.** `last_scan.schema.json` **stays** in `kdb_compiler/schemas/` until Task 9 moves it *with* its validator `validate_last_scan.py` (which still lives in `kdb_compiler/` and loads the schema by `Path(__file__).parent/"schemas"/...`). Moving it now would break `validate_last_scan`'s schema path → red suite. (Create `compiler/schemas/` first: `mkdir -p compiler/schemas`.)
- [ ] **Step 2: Fix the schema path constants.** `compiler/validate_compile_result.py` and `compiler/validate_source_response.py` load their schema via `Path(__file__).parent / "schemas" / "...json"` — that still resolves (schemas moved alongside them). **Verify:** `grep -rn "schemas/" compiler/*.py | grep -v __pycache__` and confirm each `Path(__file__).parent / "schemas"` is intact.
- [ ] **Step 3: Sweep imports.** Rewrite importers of the nine moved modules:
```bash
cmods="compiler prompt_builder response_normalizer repair canonicalize page_writer validate_compile_result validate_source_response context_loader"
for f in $(grep -rln "kdb_compiler" --include=*.py . | grep -v __pycache__); do
  for m in $cmods; do
    sed -i -E "s/\bkdb_compiler\.$m\b/compiler.$m/g; s/from kdb_compiler import $m\b/from compiler import $m/g" "$f"
  done
done
```
  **HAZARD:** `compiler/compiler.py:29`'s grouped `from kdb_compiler import (...)` — after Task 2 it should already be split into a `from common import (...)` block + a residual `from kdb_compiler import (...)`. Now rewrite the residual compiler-bound names to **intra-package** imports: `from compiler import (repair, response_normalizer, canonicalize, prompt_builder, validate_compile_result, validate_source_response)` (or relative `from . import ...`). Also `response_replay.py:28` `from kdb_compiler import response_normalizer, validate_source_response` → `from compiler import response_normalizer, validate_source_response`. `kdb_orchestrate.py`'s `page_writer`/`canonicalize` refs → `from compiler import ...`.
- [ ] **Step 4: Update entry points + package-data + discovery.** `[project.scripts]`: `kdb-validate = "compiler.validate_compile_result:main"`, `kdb-validate-response = "compiler.validate_source_response:main"`. `[tool.setuptools.package-data]`: add `compiler = ["schemas/*.json"]`. Run `pip install -e . -q`.
- [ ] **Step 5: Stale-ref grep.** Run: `grep -rn "kdb_compiler\.\(compiler\|prompt_builder\|response_normalizer\|repair\|canonicalize\|page_writer\|validate_compile_result\|validate_source_response\|context_loader\)\b" --include=*.py . | grep -v __pycache__` — Expected: none.
- [ ] **Step 6: Full suite green** (include `compiler/`). Run the standing pytest. Expected: all pass.
- [ ] **Step 7: Commit.**
```bash
git add -A
git commit -m "refactor(phase-b): extract compiler/ (compile·prompt_builder·response_normalizer·repair·canonicalize·page_writer·validate_*·context_loader·schemas)"
```

## Task 7: Extract `orchestrator` (conductor · events · manifest_writer)

**Files:** `git mv` into `orchestrator/`: `kdb_orchestrate.py` · `orchestrator_events.py` · `manifest_writer.py`. Update the `kdb-orchestrate` entry point.

- [ ] **Step 1: Move the modules.**
```bash
git mv kdb_compiler/kdb_orchestrate.py kdb_compiler/orchestrator_events.py kdb_compiler/manifest_writer.py orchestrator/
```
- [ ] **Step 2: Sweep imports.**
```bash
for f in $(grep -rln "kdb_compiler" --include=*.py . | grep -v __pycache__); do
  sed -i -E "s/\bkdb_compiler\.kdb_orchestrate\b/orchestrator.kdb_orchestrate/g; \
             s/\bkdb_compiler\.orchestrator_events\b/orchestrator.orchestrator_events/g; \
             s/\bkdb_compiler\.manifest_writer\b/orchestrator.manifest_writer/g; \
             s/from kdb_compiler import manifest_writer\b/from orchestrator import manifest_writer/g; \
             s/from kdb_compiler import orchestrator_events\b/from orchestrator import orchestrator_events/g" "$f"
done
```
  **HAZARD:** finish splitting `kdb_orchestrate.py:30`'s original grouped line — `manifest_writer` → `from orchestrator import manifest_writer` (intra-package, or `from . import manifest_writer`); `page_writer` → `from compiler import page_writer`; `pipeline_registry` already moved in Task 5.
- [ ] **Step 3: Update entry point.** `[project.scripts]`: `kdb-orchestrate = "orchestrator.kdb_orchestrate:main"`. Run `pip install -e . -q`.
- [ ] **Step 4: Stale-ref grep.** Run: `grep -rn "kdb_compiler\.\(kdb_orchestrate\|orchestrator_events\|manifest_writer\)\b" --include=*.py . | grep -v __pycache__` — Expected: none.
- [ ] **Step 5: Full suite green** (include `orchestrator/`). Run the standing pytest. Expected: all pass.
- [ ] **Step 6: Commit.**
```bash
git add -A
git commit -m "refactor(phase-b): extract orchestrator/ (kdb_orchestrate·orchestrator_events·manifest_writer)"
```

## Task 8: Split `resp_stats_writer` → `common/llm_telemetry` + `compiler/resp_summary`

**Files:** Delete `kdb_compiler/resp_stats_writer.py`; create `common/llm_telemetry.py` (generic) + `compiler/resp_summary.py` (compiler-specific). Update the two importers (`compiler/compiler.py`, `tools/benchmark/runner.py` — benchmark moves in Task 9, currently still `kdb_benchmark/runner.py`). New test asserts both halves.

- [ ] **Step 1: Write the failing split test.** Create `compiler/tests/test_resp_summary_split.py` (or `common/tests/`):
```python
def test_llm_telemetry_has_generic_helpers():
    from common.llm_telemetry import safe_source_id, build_resp_stats, write_resp_stats
    assert safe_source_id("a/b c") == "a_b_c" or isinstance(safe_source_id("x"), str)

def test_resp_summary_has_compiler_builder():
    from compiler.resp_summary import build_parsed_summary
    summary = build_parsed_summary({"pages": [], "summary_slug": "summary-x",
                                    "concept_slugs": [], "article_slugs": []})
    assert summary is not None
```
- [ ] **Step 2: Run — expect failure.** Run: `python3 -m pytest -q compiler/tests/test_resp_summary_split.py` — Expected: FAIL (modules don't exist).
- [ ] **Step 3: Create `common/llm_telemetry.py`.** Move the **generic** members from `resp_stats_writer.py`: `_sha256`, `_capture_full`, `safe_source_id`, `build_resp_stats`, `write_resp_stats`, and the `_NONE_HASH`/`_CAPTURE_FULL_ENV` constants. Imports: `from common import atomic_io, run_context`; `from common.call_model import ModelResponse` (or wherever `ModelResponse` lives). Keep `RespStatsRecord` in `common/types` (it already lives in `types`).
- [ ] **Step 4: Create `compiler/resp_summary.py`.** Move `build_parsed_summary` there. `ParsedSummary` stays in `common/types` (cross-stage dataclass shape); `resp_summary` imports it: `from common.types import ParsedSummary`. `build_resp_stats` in `llm_telemetry` takes an already-built `parsed_summary` argument (it must **not** import `compiler` — that would invert the dependency). Verify `build_resp_stats`'s signature accepts the summary as a param; if it currently calls `build_parsed_summary` internally, lift that call up to `compiler.py`'s call site.
- [ ] **Step 5: Delete the old module + update importers.** `git rm kdb_compiler/resp_stats_writer.py`. Update `compiler/compiler.py`: `from common.llm_telemetry import build_resp_stats, write_resp_stats` + `from compiler.resp_summary import build_parsed_summary`. Update `kdb_benchmark/runner.py`: `from common.llm_telemetry import safe_source_id`.
- [ ] **Step 6: Stale-ref grep.** Run: `grep -rn "resp_stats_writer" --include=*.py . | grep -v __pycache__` — Expected: none.
- [ ] **Step 7: Split test + full suite green.** Run: `python3 -m pytest -q compiler/tests/test_resp_summary_split.py` then the standing pytest. Expected: all pass.
- [ ] **Step 8: Commit.**
```bash
git add -A
git commit -m "refactor(phase-b): split resp_stats_writer -> common/llm_telemetry (generic) + compiler/resp_summary (build_parsed_summary)"
```

## Task 9: Extract `tools` (cleanup · replay · benchmark · diagnostics)

**Files:** `git mv kdb_compiler/kdb_clean.py tools/cleanup.py`; `git mv kdb_compiler/response_replay.py tools/replay.py`; `git mv kdb_compiler/validate_last_scan.py tools/diagnostics/validate_last_scan.py`; `git mv compiler/schemas/last_scan.schema.json tools/diagnostics/last_scan.schema.json`; `git mv kdb_benchmark/* tools/benchmark/` (modules + `models.json` + tests). Update `kdb-clean`/`kdb-replay`/`kdb-benchmark` entry points. (`tools/viewer/` already in place.)

- [ ] **Step 1: Move cleanup + replay + diagnostics.**
```bash
git mv kdb_compiler/kdb_clean.py tools/cleanup.py
git mv kdb_compiler/response_replay.py tools/replay.py
git mv kdb_compiler/validate_last_scan.py tools/diagnostics/validate_last_scan.py
git mv kdb_compiler/schemas/last_scan.schema.json tools/diagnostics/last_scan.schema.json
rmdir kdb_compiler/schemas 2>/dev/null || true   # now empty (compiler schemas left in Task 6)
```
- [ ] **Step 2: Fix `validate_last_scan`'s schema path.** It loads `Path(__file__).parent / "schemas" / "last_scan.schema.json"`. The schema now sits **beside** it in `tools/diagnostics/`, so change to `Path(__file__).parent / "last_scan.schema.json"`. Grep to confirm: `grep -n "last_scan.schema.json" tools/diagnostics/validate_last_scan.py`.
- [ ] **Step 3: Move the benchmark package.**
```bash
git mv kdb_benchmark/cli.py kdb_benchmark/paths.py kdb_benchmark/registry.py kdb_benchmark/runner.py \
       kdb_benchmark/scorecard.py kdb_benchmark/scorer.py tools/benchmark/
git mv kdb_benchmark/models.json tools/benchmark/models.json
git mv kdb_benchmark/tests tools/benchmark/tests
rm -f kdb_benchmark/__init__.py && rmdir kdb_benchmark 2>/dev/null || true
```
  (If `kdb_benchmark/__init__.py` had content, `git mv` it to `tools/benchmark/__init__.py` instead of recreating.)
- [ ] **Step 4: Sweep imports.** Rewrite references to the moved modules:
```bash
for f in $(grep -rln "kdb_compiler\.kdb_clean\|kdb_compiler\.response_replay\|kdb_compiler\.validate_last_scan\|kdb_benchmark" --include=*.py . | grep -v __pycache__); do
  sed -i -E "s/\bkdb_compiler\.kdb_clean\b/tools.cleanup/g; \
             s/from kdb_compiler import kdb_clean\b/from tools import cleanup/g; \
             s/\bkdb_compiler\.response_replay\b/tools.replay/g; \
             s/\bkdb_compiler\.validate_last_scan\b/tools.diagnostics.validate_last_scan/g; \
             s/\bkdb_benchmark\b/tools.benchmark/g" "$f"
done
```
  **Note** the `kdb_orchestrate.finalize` call site for `kdb_clean` → now `tools.cleanup` (the documented contract exception, Surfaced Decision 5). Fix any `from kdb_compiler import kdb_clean` and references to `kdb_clean.<fn>` → `cleanup.<fn>`.
- [ ] **Step 5: Update entry points + package-data + discovery.** `[project.scripts]`: `kdb-clean = "tools.cleanup:main"`, `kdb-replay = "tools.replay:main"`, `kdb-benchmark = "tools.benchmark.cli:main"`. `[tool.setuptools.package-data]`: add `tools = ["benchmark/models.json", "diagnostics/*.json", "viewer/*.html"]`. In `[tool.setuptools.packages.find].include`, drop `"kdb_benchmark*"` (package gone). Run `pip install -e . -q`.
- [ ] **Step 6: Stale-ref grep.** Run: `grep -rn "kdb_benchmark\|kdb_compiler\.\(kdb_clean\|response_replay\|validate_last_scan\)\b" --include=*.py --include=*.toml . | grep -v __pycache__` — Expected: none.
- [ ] **Step 7: Full suite green** (include `tools/`). Run the standing pytest. Expected: all pass.
- [ ] **Step 8: Commit.**
```bash
git add -A
git commit -m "refactor(phase-b): extract tools/ (cleanup·replay·benchmark·diagnostics[+last_scan.schema]); viewer already present"
```

## Task 10: Redistribute tests + shared fixtures (root conftest)

**Files:** Create root `conftest.py` (shared graph-isolation fixture + the `graphdb_kdb` synthetic factories); distribute `kdb_compiler/tests/*` into the owning packages' `tests/` dirs; `git mv graphdb_kdb`'s tests already rode along in Task 4 (they live at `kdb_graph/tests/`); benchmark tests rode along in Task 9. Update `pyproject` testpaths.

- [ ] **Step 1: Create the root `conftest.py`.** Move the graph-isolation autouse fixture from `kdb_compiler/tests/conftest.py` and the synthetic factories (`graph_dir`, `make_page`, `make_compiled_source`, `make_compile_result`, `make_scan_entry`, `make_scan`) from `kdb_graph/tests/conftest.py` into a single repo-root `conftest.py`. Keep package-local conftests only for fixtures unique to that package.
```python
# conftest.py (repo root)
import pytest
from pathlib import Path

@pytest.fixture(autouse=True)
def _isolate_graph_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("KDB_GRAPH_PATH", str(tmp_path / "graph_isolated"))
    yield

# ... the make_* factories, verbatim from kdb_graph/tests/conftest.py ...
```
- [ ] **Step 2: Distribute the `kdb_compiler/tests/` files** to the package that owns the module under test: e.g. `test_paths.py`/`test_source_io.py`/`test_atomic_io.py` → `common/tests/`; `test_compiler.py`/`test_repair.py`/`test_validate_*`/`test_response_replay.py`(replay → `tools/tests/`)/`test_canonicalize.py` → `compiler/tests/` (or `tools/tests/` for replay); `test_pass1_*`/`test_kdb_scan*` → `ingestion/tests/`; `test_kdb_orchestrate*` → `orchestrator/tests/`; `test_kdb_clean*` → `tools/tests/`. Use `git mv`. Move `kdb_compiler/tests/fixtures/` to wherever the fixtures are consumed (most are compiler/ingestion — put shared ones beside the root conftest or under the primary consumer). **The dedup'd package conftests** (`kdb_compiler/tests/conftest.py`, `kdb_graph/tests/conftest.py`) become empty → `git rm` them.
- [ ] **Step 3: Remove the now-empty `kdb_compiler/` package.** After all modules + tests have left: `git rm kdb_compiler/__init__.py` (and any leftover) then `rmdir kdb_compiler kdb_compiler/tests 2>/dev/null`. **Gate:** `find kdb_compiler -name '*.py' 2>/dev/null` returns nothing first.
- [ ] **Step 4: Update `pyproject` testpaths + discovery.** `[tool.pytest.ini_options].testpaths = ["common/tests", "ingestion/tests", "compiler/tests", "kdb_graph/tests", "orchestrator/tests", "tools/tests"]`. In `[tool.setuptools.packages.find].include`, drop `"kdb_compiler*"`. Run `pip install -e . -q`.
- [ ] **Step 5: Full suite green at new testpaths.** Run: `python3 -m pytest -q -m "not live" common/ ingestion/ compiler/ kdb_graph/ orchestrator/ tools/` — Expected: all pass, count ≈ the pre-Phase-B baseline (no tests lost in the move). Cross-check the collected count against the Phase-A baseline (~1175) minus none.
- [ ] **Step 6: Commit.**
```bash
git add -A
git commit -m "refactor(phase-b): redistribute tests into package tests/ dirs; shared root conftest; remove empty kdb_compiler/"
```

## Task 11: Make the dependency-contract guard real

**Files:** Modify `tools/tests/test_package_boundaries.py` (created Task 3) to assert the full B.3 contract, with the one documented exception.

- [ ] **Step 1: Extend the guard.** Add tests encoding B.3:
```python
ALLOWED = {
    "common":       set(),
    "kdb_graph":    {"common"},
    "ingestion":    {"common"},
    "compiler":     {"common", "kdb_graph"},
    "orchestrator": {"common", "kdb_graph", "ingestion", "compiler", "tools"},  # 'tools' = documented
    "tools":        {"common", "kdb_graph", "ingestion", "compiler"},           # cleanup exception
}

import pytest
@pytest.mark.parametrize("pkg,allowed", ALLOWED.items())
def test_package_dependency_contract(pkg, allowed):
    actual = _top_level_imports(pkg)
    illegal = actual - allowed
    assert not illegal, f"{pkg} imports outside its contract: {illegal}"

def test_nothing_depends_on_tools_except_orchestrator_cleanup():
    # 'nothing depends on tools' holds EXCEPT orchestrator->tools.cleanup
    # (orchestrate.finalize calls cleanup inline; decoupling is deferred, out of Phase B move-scope).
    for pkg in ("common", "ingestion", "compiler", "kdb_graph"):
        assert "tools" not in _top_level_imports(pkg), f"{pkg} must not depend on tools"
```
- [ ] **Step 2: Run it.** Run: `python3 -m pytest -q tools/tests/test_package_boundaries.py -v` — Expected: PASS. If `orchestrator`'s actual imports include something not in `ALLOWED["orchestrator"]`, that's a real finding — investigate before widening the set.
- [ ] **Step 3: Commit.**
```bash
git add -A
git commit -m "refactor(phase-b): dependency-contract guard asserts the B.3 edges (+ documented orchestrator->tools.cleanup exception)"
```

## Task 12: North Star + docs + deferred Phase-A cleanups

**Files:** `docs/CODEBASE_OVERVIEW.md` (package-structure section → the six-package tree), `docs/JOURNEY.md` (Milestone Changelog entry; the `:118` `source_state.json`→`manifest.json` fix), `compiler/compiler.py` (`failure_stage="reconcile"`→`"repair"`, the test-pinned Phase-A leftover), plus any doc that names `kdb_compiler`/`graphdb_kdb` as the structure.

- [ ] **Step 1: Rewrite the structure section** of `CODEBASE_OVERVIEW.md` to the six-package tree + the B.3 dependency contract; note the deferred `orchestrator→tools.cleanup` exception (cleanup is inline in `orchestrate.finalize`; decoupling is post-Phase-B).
- [ ] **Step 2: Land the deferred Phase-A cleanups.** In `compiler/compiler.py`, change the `failure_stage="reconcile"` literal → `"repair"`; update the test that pins it (grep: `grep -rn '"reconcile"' compiler/ | grep -v __pycache__`). Fix `docs/JOURNEY.md:118` `source_state.json` → `manifest.json` (the file's real name).
- [ ] **Step 3: Stale-ref sweep in docs/comments.** Run: `grep -rn "kdb_compiler\b\|graphdb_kdb\b" --include=*.py --include=*.md docs/CODEBASE_OVERVIEW.md compiler/ ingestion/ common/ orchestrator/ tools/ kdb_graph/ | grep -v __pycache__` — fix stale module/structure mentions in comments + the North Star (not historical archive docs).
- [ ] **Step 4: Add the Milestone Changelog entry** to `CODEBASE_OVERVIEW.md`: one dated line — Phase B package split shipped (run-7 gate).
- [ ] **Step 5: Full suite green** (the `failure_stage` test change is the only behavior-adjacent edit). Run the standing pytest. Expected: all pass.
- [ ] **Step 6: Commit.**
```bash
git add -A
git commit -m "docs(phase-b): North Star six-package structure + B.3 contract; land deferred Phase-A cleanups (failure_stage repair, JOURNEY manifest.json)"
```

## Task 13: Phase-B gate — non-live green, editable install, then live run-7

**Files:** none (verification).

- [ ] **Step 1: Full non-live suite green.** Run: `python3 -m pytest -q -m "not live" common/ ingestion/ compiler/ kdb_graph/ orchestrator/ tools/` — Expected: all pass; collected count ≈ pre-Phase-B baseline (no tests dropped in the redistribution).
- [ ] **Step 2: Editable install resolves all entry points + data files.** Run: `pip install -e . -q` then verify each console script imports:
```bash
for c in kdb-orchestrate kdb-enrich kdb-scan graphdb-kdb kdb-clean kdb-replay kdb-benchmark kdb-validate kdb-validate-response; do
  echo "== $c =="; "$c" --help >/dev/null 2>&1 && echo ok || echo "FAIL: $c";
done
```
  Expected: all `ok`. (A `FAIL` usually means an entry-point path is stale.) **Caveat:** under `pip install -e .` Python imports from the source tree, so `[tool.setuptools.package-data]` globs are **not exercised** by this gate — a green Task 13 does **not** prove the package-data globs are correct (they only matter for a non-editable wheel build, which this single-user project doesn't do). Update them per the tasks for correctness, but don't read green here as their proof.
- [ ] **Step 3: Data-file presence check.** Confirm the relocated data files resolve from their new packages: `python3 -c "import ingestion.enrich.config_loader as c; c.load_domains; print('domains ok')"` and a `validate_source_response` schema-load smoke + a `validate_last_scan` schema-load smoke. Expected: no `FileNotFoundError`.
- [ ] **Step 4: Hand off the live gate to Joseph.** Present the run-7 commands (reset + `kdb-orchestrate` on the sandbox vault `~/Obsidian/Vault-in-place-test-run`; runbook `docs/reference/test-run-procedure.md`). **Joseph fires the live run** (API cost). Pass criteria: `exit_reason=ok`, 0 quarantined, 0 invariant, links wired, 0 orphans — a clean E2E matching the run-6/v0.5.1 standard (zero-behavior-change confirmation).
- [ ] **Step 5: On clean run-7 — post-migration external panel CODE REVIEW** (Joseph, 2026-06-02). Once the migration is complete and run-7 is clean, send the **whole Phase-B diff** to the project-default panel for a full code review (CLI reviewers under the output-file-only guardrail) — not a design review (design was ratified), but a correctness/quality sweep of the executed migration. Fold any findings.
- [ ] **Step 6: Phase B DONE.** Record the gate result in `docs/RELEASES.md`/daily note; merge `refactor/phase-b-package-split`; tag (e.g. `v0.5.2`). **Then #106** (panel-review the spec → writing-plans → run-8).

---

## Self-review notes

- **Spec coverage:** B.1 target tree (Tasks 2,4,5,6,7,9) · B.2 relocation deltas — resp_stats split (Task 8), pipeline_registry→ingestion/config (Task 5), graphdb_kdb→kdb_graph (Task 4), validate_last_scan→tools/diagnostics (Task 9) · B.3 dependency contract (Task 11 guard) · B.4 CLI surface (entry-point updates in Tasks 4–9) · B.5 tests/fixtures + pyproject package-data/discovery/testpaths (Tasks 5,6,9,10) · B.6 gate (Task 13). All covered.
- **No behavior change** in Tasks 1–7, 9–10, 12 (except the deliberate `failure_stage="reconcile"→"repair"` leftover, test-updated) — the 1175-test suite is the regression net; each task adds a stale-reference grep + green gate. Task 3/11 add the dependency-contract guard; Task 8 adds the split test.
- **Ordering:** scaffold → common (leaf) → guard harness → kdb_graph → ingestion → compiler → orchestrator → resp_stats split → tools → tests redistribute → guard teeth → docs → gate. Leaf-first so each sweep resolves against already-moved packages.
- **Grouped-import hazard** (`from kdb_compiler import (...)` spanning packages) is called out explicitly in Tasks 2, 5, 6, 7 — these are the manual edits a blind `sed` would corrupt.
- **Known residual:** `orchestrator → tools.cleanup` (inline cleanup) violates "nothing depends on tools" — documented exception in the guard (Task 11) + North Star (Task 12); full decoupling deferred (behavior change, out of move-only scope).
