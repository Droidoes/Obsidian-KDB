# Independent Senior Architect Review: Task #91 Plan 1 (`kdb-compile` rebuild)
**Reviewer:** agy (Gemini 3.5 Flash High)
**Date:** 2026-05-29

---

## 1. Verdict

**`proceed-with-changes`**

The implementation plan is exceptionally high quality, presenting a logical, TDD-driven sequence that successfully extracts the Pass-2 compiler core without breaking the monolithic legacy path. However, architectural changes are required to address cross-source page merging loss in the per-source loop, prevent dirty disk writes on pre-commit failures, and resolve the circular Python import dependency.

---

## 2. Findings

### **Finding F-1: Cross-Source Page Collision Merging Loss in Per-Source Loop**
*   **Dimension:** B (Architectural Risk)
*   **Severity:** High
*   **Issue:** In the monolithic `kdb-compile`, the `canonicalize.run` stage processes a batch of compiled sources together, merging page intent collisions (e.g., when two modified files both define or edit the same concept page like `margin-of-safety.md`) via the `_merge_page_intents` step. This step unions their `outgoing_links` and `supports_page_existence` and applies the `longest-wins` or `canonical-wins` body strategy. By shifting to a per-source loop where `compile_source` runs on a single source in isolation, we completely lose the ability to merge page intents across sources compiled in the same orchestrator run. The last source compiled will blindly overwrite any previously written concept page instead of merging them.
*   **Evidence:** `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md` §171: `"6 canonicalize | compiler core (per-source; not cross-source-batch-bound)"`.
*   **Recommendation:** Acknowledge this limitation clearly in the design spec as an acceptable single-user vault trade-off, or design a post-loop canonicalization step in the orchestrator finalize phase to scan the compiled pages and merge any multi-source concept pages before committing them.

### **Finding F-2: Dirty Disk State on Case-(a) Pre-Commit Failure**
*   **Dimension:** B (Architectural Risk)
*   **Severity:** High
*   **Issue:** `compile_source` invokes `patch_applier.apply(write=True)` before the orchestrator commits the manifest. If `patch_applier.apply` successfully writes wiki pages to disk, but the subsequent manifest write or graph-sync fails, the orchestrator triggers a fail-fast exit. However, the modified wiki pages have already been written to the vault on disk, leaving the filesystem out of sync with the manifest and GraphDB. This violates the Case-(a) "pre-commit failure" invariant (which states that a failed source must leave no committed or visible side effects).
*   **Evidence:** `docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md` lines 483–490: `apply_result = patch_applier.apply(...)` is called inside `compile_source`. `docs/task91-kdb-orchestrate-blueprint.md` §D-91-13 (two-phase failure).
*   **Recommendation:** We should strictly enforce that `compile_source` is invoked with `write=False` (dry-run) during the orchestrator's main loop to verify all compile, validate, and canonicalize constraints first, and only execute the actual file writes (`write=True`) immediately preceding the manifest commit. Alternatively, have `compile_source` return the generated page patches in the result payload, leaving the actual disk write responsibility to the orchestrator at the commit boundary.

### **Finding F-3: Python Circular Import Dependency via `compiler.py`**
*   **Dimension:** A (Spec Fidelity)
*   **Severity:** High
*   **Issue:** The plan proposes that `CompileJob` in `kdb_compiler/types.py` will import `SourceFrontmatter` from `kdb_compiler/compiler.py` (or reference it). However, `compiler.py` already imports `planner.py` (which imports `types.py`) and is imported by other modules. Because `SourceFrontmatter` is loaded at plan time and compile time, referencing it between `types.py`, `planner.py`, and `compiler.py` creates a **circular import loop** in Python at module load time.
*   **Evidence:** `docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md` lines 84–92: importing `SourceFrontmatter` from `kdb_compiler/compiler.py`.
*   **Recommendation:** Move the definition of the `SourceFrontmatter` dataclass (currently in `kdb_compiler/compiler.py:107`) into `kdb_compiler/types.py` alongside `CompileJob` and `ContextSnapshot`. This centralizes all pipeline type representations and eliminates circular import paths cleanly.

### **Finding F-4: Structural Error Blinding in `CompileSourceResult`**
*   **Dimension:** B (Architectural Risk)
*   **Severity:** Medium
*   **Issue:** The proposed `CompileSourceResult` collapses all pre-commit failures (LLM failures, validate-gate failures, cyclic aliases, filesystem write errors) into a single generic `error: str | None` field. This prevents the orchestrator from programmatically distinguishing between transient model call failures (which can be retried) and permanent structural configuration errors (such as cyclic aliases or schema mismatches).
*   **Evidence:** `docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md` lines 175–188.
*   **Recommendation:** Add optional `failure_stage: str | None` and `exception_type: str | None` fields to `CompileSourceResult` to align with `RespStatsRecord` telemetry and allow the orchestrator to handle retry or logging paths intelligently.

### **Finding F-5: Tight Database Coupling in Ingress Interface**
*   **Dimension:** B (Architectural Risk)
*   **Severity:** Medium
*   **Issue:** By having `compile_source` receive the database connection (`conn`) and internally call `build_context_snapshot`, the compiler core remains highly coupled to Kuzu's connection state. This complicates testing the compiler core in isolation (requiring a mock or live GraphDB instance in every unit test).
*   **Evidence:** `docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md` lines 375–378.
*   **Recommendation:** Allow `compile_source` to accept an optional pre-built `context_snapshot: ContextSnapshot | None = None` parameter. If provided, it bypasses `build_context_snapshot` entirely, enabling complete test isolation and decoupling database connection lifecycles from compilation logic.

---

## 3. What is Sound and Spec-Faithful

The following aspects of the plan are exceptionally well-conceived and represent excellent design choices:

1.  **Make-Before-Break Freeze:** The plan correctly freezes the legacy monolithic runner as `kdb-old-compile` via `pyproject.toml` console scripts, ensuring the pipeline remains fully runnable and testable under the legacy branch during migration.
2.  **In-Memory Pipeline Ingress:** The modifications to `CompileJob` and `source_text_for` to short-circuit disk I/O when in-memory body and frontmatter are supplied fully deliver on the spec's intent to eliminate the dual-read performance tax.
3.  **`source_name` Fix:** The plan proactively catches and resolves the bug where `source_name` was derived from the raw disk path `abs_path` (which becomes empty `""` in an in-memory job). Overriding it to `Path(source_id).name` is elegant and completely correct.
4.  **Atomic Pre-Commit Failure Handling:** Wrapping `CircularAliasError` and `PagePatchError` into `CompileSourceResult(cr=None, error=...)` keeps the result model simple and allows the orchestrator to treat all pre-commit failures uniformly.
