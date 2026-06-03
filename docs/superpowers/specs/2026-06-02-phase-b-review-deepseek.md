# Phase B Migration — DeepSeek Review

**Date:** 2026-06-02 · **Branch:** `refactor/phase-b-package-split` · **Scope:** correctness + quality review of the completed six-package split

---

## Verdict: `GO-WITH-FIXES`

The migration is well-executed. Two one-shot migration scripts and `setup.sh` have stale `kdb_compiler.*` import paths — they're the only broken artifacts and are not on any live pipeline path. Everything else (imports, data-file resolution, the resp_stats split, the dependency contract, CLI bindings) is correct. Fix the three stale-path items, then merge and tag `v0.5.2`.

---

## (a) Correctness bugs

### [Severity: High] `scripts/migrate_task66_compiled_hash.py:37` — broken import

```python
from kdb_compiler.manifest_update import assert_manifest_invariants
```

`kdb_compiler.manifest_update` was moved to `orchestrator/manifest_writer.py`. This import will raise `ModuleNotFoundError`. The script is a one-shot migration (Task #66) and is not on any live flow, but if anyone runs it post-B it will fail immediately.

**Fix:** Change to `from orchestrator.manifest_writer import assert_manifest_invariants`.

### [Severity: High] `scripts/migrate_task64_supersession.py:27` — broken import

```python
from kdb_compiler.manifest_update import (
```

Same root cause — `manifest_update` is now `orchestrator/manifest_writer.py`. Same fix. Same risk profile (one-shot migration, not live flow).

**Fix:** Change to `from orchestrator.manifest_writer import ...`.

### [Severity: Medium] `setup.sh:63,65` — stale paths

Line 63 references the retired `kdb-compile --help` (the legacy driver CLI, now dropped). Line 65 references `kdb_compiler/tests/test_m2_first_compile.py` which no longer exists (the file moved to `compiler/tests/` or was removed).

**Fix:** Update line 63 to reference `kdb-orchestrate --help` and update line 65's test path to the new location (or drop it — the live-smoke command was always optional).

---

## (b) Test-fidelity gaps

### [Severity: Low] `tools/tests/test_package_boundaries.py:4-5` — duplicate `"kdb_graph"` in INTERNAL set

```python
INTERNAL = {"common", "ingestion", "compiler", "kdb_graph", "orchestrator", "tools",
            "kdb_compiler", "kdb_graph"}
```

`"kdb_graph"` appears twice. Harmless (set dedup takes care of it), but `"kdb_compiler"` is still in the INTERNAL set — it's needed so the boundary test correctly classifies a hypothetical `kdb_compiler` import as "internal" (so it shows up as an illegal import rather than being silently ignored). This is deliberate and correct. 

**Fix (cosmetic):** Drop the duplicate `"kdb_graph"` on line 5.

### [Severity: Low] `common/tests/test_layering_leaf.py:4` — stale comment

> `source_io.py must not import kdb_compiler.enrich.*`

The test correctly checks for both `kdb_compiler.enrich` and `ingestion.enrich` (line 27-28), but the comment on line 4 only mentions the old path. The layering fix itself is correct — `parse_existing_frontmatter` was moved from `ingestion/enrich/frontmatter_embedder.py` to `common/source_io.py` (line 31), and `frontmatter_embedder` now imports *up* from `common.source_io` (line 18). The inversion is resolved. 

**No behavioral impact; comment is stale only.**

### [Severity: None — confirmed correct] D34 producer-agnostic guard (`kdb_graph/tests/test_snapshot.py:184-218`)

Verified: the guard now checks against `compiler`, `ingestion`, `orchestrator` — the new package names. No stale `kdb_compiler` reference in its checked prefixes. The earlier commit `f13fecb` already de-vacuumed this test. ✅

### [Severity: None — confirmed correct] `compiler/tests/test_resp_stats_writer.py:19`

Comment says "The kdb_compiler.resp_stats_writer module is removed." — this is a test file comment explaining the test's purpose, not a broken import. Acceptable.

---

## (c) Packaging & data-file risks

### [Severity: Low] `common/__init__.py` — stale version string

```python
__version__ = "0.1.0-m0"
```

This is the original M0 scaffold version. At `v0.5.2` this should reflect the actual release. The benchmark runner (`tools/benchmark/runner.py`) imports this version string. Not load-bearing — nothing gates on it — but stale metadata.

**Fix:** Bump to `"0.5.2"` before tagging.

### [Severity: None — confirmed correct] Schema path resolution

All three schema-location strategies verified correct:
- `compiler/schemas/`: `Path(__file__).parent / "schemas" / "xxx.json"` — `schemas/` moved with compiler. ✅
- `tools/diagnostics/`: `Path(__file__).parent / "last_scan.schema.json"` — schema file moved to same directory from `kdb_compiler/schemas/`. Path adjusted from `parent/schemas/` to `parent/`. ✅
- `ingestion/enrich/pass1_prompt.py`: `_TEMPLATE_DIR = Path(__file__).parent` — `pass1_prompt.j2` lives in the same directory. ✅
- `ingestion/enrich/config_loader.py:19`: `CONFIG_DIR = Path(__file__).parent.parent / "config"` — resolves `ingestion/enrich/` → `ingestion/` → `ingestion/config/`. ✅
- `tools/benchmark/paths.py:18`: `REPO_ROOT = Path(__file__).resolve().parent.parent.parent` — resolves `tools/benchmark/paths.py` → `tools/benchmark/` → `tools/` → repo root. The `benchmark/` data directory still lives at the repo root (not under `tools/benchmark/`), so 3 parents is correct. ✅

### [Severity: None — confirmed correct] `pyproject.toml` packaging

- `[project.scripts]`: All 9 entry points resolve to their new module paths. Legacy bindings (`kdb-compile`, `kdb-old-compile`, `kdb-compile-sources`, `kdb-plan`, `kdb-validate-scan`) are correctly dropped. Two new bindings (`kdb-validate`, `kdb-validate-response`) for the compiler validators — not in the brief's B.4 CLI surface but a reasonable addition (operators may want standalone validation). ✅
- `[tool.setuptools.packages.find]`: Correctly includes all 6 new packages and excludes `benchmark/` (data dir), `knowledge_graph/` (standalone renderer), `docs/`, `tests/`. No stale `kdb_compiler*` or `graphdb_kdb*` includes. ✅
- `[tool.setuptools.package-data]`: `compiler = ["schemas/*.json"]`, `tools = ["benchmark/models.json", "diagnostics/*.json", "viewer/*.html"]`, `ingestion = ["config/*.json", "config/*.yaml", "enrich/*.j2"]`. All globs match actual file locations. ✅
- `[tool.pytest.ini_options].testpaths`: Covers all 6 packages + `tools/benchmark/tests`. ✅

### [Severity: Low — potential wheel-build gap] `package-data` glob for `tools/diagnostics/*.json`

The `tools` package-data glob is `["benchmark/models.json", "diagnostics/*.json", "viewer/*.html"]`. This correctly captures `tools/diagnostics/last_scan.schema.json`. However, `tools/diagnostics/` also contains non-data `.md` files (`pass-1-run-3.md`, `pass-2-run-3.md`) and `.py` files — these are not package-data and correctly not globbed. No issue. ✅

---

## (d) Cleanliness / naming nits

### [Severity: Low] `setup.sh:63` — references retired CLI

> `3. Try the CLIs: kdb-scan --help    kdb-compile --help`

`kdb-compile` is now dropped. Should reference the live orchestrator.

**Fix:** `kdb-scan --help    kdb-orchestrate --help`

### [Severity: Info] Planner removal is a scope deviation from brief

The Phase B brief's relocation map listed `planner → compiler/planner` and said "stays; see A.2." But `planner.py` is now deleted — it was removed during the extract commits (no `planner.py` exists anywhere in the tree). `compiler/compiler.py`'s `run_compile()` batch function was also removed; the compiler now only has per-source `compile_one` and `compile_source`. The orchestrator handles job scheduling directly.

This is a **clean removal** — the code works without it (1191 tests pass, run-7 green), and it aligns with the target architecture where the orchestrator is the conductor. But it's a deviation from the brief's explicit "not retirable" statement. Worth noting for the v0.5.2 changelog — it should say "planner removed" or "batch compile path retired" rather than implying planner was just relocated.

### [Severity: Info] New CLI bindings not in brief's B.4 surface

`kdb-validate` and `kdb-validate-response` are new CLI entry points exposing the compile-result and source-response validators. The brief's B.4 CLI surface didn't list them; the brief said "`kdb-validate-*` unless kept as deliberate diagnostics." This seems like a deliberate decision to keep them (they ARE diagnostics). Fine, but worth confirming with Joseph that these earn a binding (particularly since the old `kdb-validate-scan` was dropped).

---

## The resp_stats split — detailed verification

This is the one "real restructure" (not a pure move). I diffed the old `kdb_compiler/resp_stats_writer.py` against `common/llm_telemetry.py` + `compiler/resp_summary.py`:

1. **`build_parsed_summary` body is byte-identical.** The function was moved verbatim from `resp_stats_writer.py` to `compiler/resp_summary.py`. ✅
2. **The lifted gate in `compiler/compiler.py:421-424` is byte-identical to the old internal gate.** Old: `if parse_ok and isinstance(parsed_json, dict): summary = build_parsed_summary(parsed_json)`. New: `parsed_summary = build_parsed_summary(state["parsed_json"]) if (state["parse_ok"] and isinstance(state["parsed_json"], dict)) else None`. Identical condition, identical outcome. ✅
3. **`common/llm_telemetry` is a true leaf.** Imports only from `common.{atomic_io, call_model, run_context, types}`. No imports from `compiler`, `ingestion`, `orchestrator`, `tools`. The boundary test (`test_common_is_a_leaf`) asserts this. ✅
4. **Duck-typing cleanup:** The old code had `TYPE_CHECKING` imports for `BuiltPrompt` and `FailureTelemetry` from the compiler pipeline — soft couplings that were unnecessary. The new code drops them and uses duck-typed `prompt` and `failure` parameters (any object with `.system`/`.user` or `.stage`/`.exception_type`/`.message`). This is a strict improvement — `common` no longer even has a type-checking dependency on compiler types. ✅
5. **`resp_stats_writer.py` commentary:** The old module docstring said "per compile call"; the new says "per LLM call." This is more accurate (Pass-1 enrichment also calls the LLM and could use `llm_telemetry` if desired). ✅

---

## Import hygiene

- **Zero `from kdb_compiler` imports** in non-test, non-script production code. ✅
- **Zero `from graphdb_kdb` imports** anywhere outside `kdb_graph/`. The only grep hits are comments in `kdb_graph/tests/test_queries_context.py:4`. ✅
- **`kdb_compiler/` directory no longer exists.** ✅
- The `scripts/` directory is the only place with real stale imports (tracked above as correctness bugs).

---

## The `orchestrator → tools.cleanup` exception

`orchestrator/kdb_orchestrate.py:37`: `from tools.cleanup import build_cleanup_artifacts, reap_orphans_from_graph`. Called in `_finalize()` (lines 196, 200). The boundary test (`test_package_dependency_contract`) allows this via `"orchestrator": {"common", "kdb_graph", "ingestion", "compiler", "tools"}` with the comment "documented cleanup edge." The test `test_nothing_depends_on_tools_except_orchestrator_cleanup` enforces that no other package depends on `tools`.

**Acceptable deferral.** Decoupling cleanup from the orchestrator's finalize would require either (a) a post-orchestration hook system, or (b) making the operator remember to run `kdb-clean` after every orchestrate run. Both are behavior changes out of move-only scope. The current coupling is clean, documented, and guard-tested. ✅

---

## Bottom line

The migration is correct. The 6-package split is clean, the dependency contract holds, the one real restructure (resp_stats split) preserves byte-identical behavior, all path resolutions resolve, and the 1191-test suite + run-7 green gate confirms no regression. The only broken artifacts are two one-shot migration scripts and `setup.sh` — all with stale `kdb_compiler.manifest_update` or `kdb_compiler/tests/` paths. Fix those three items, then merge and tag `v0.5.2`.

**Must-fix before merge:** `scripts/migrate_task66_compiled_hash.py`, `scripts/migrate_task64_supersession.py`, `setup.sh:63,65`.
