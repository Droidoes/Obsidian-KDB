# Task #91 Plan 1 Review (Revised) — Qwen CLI (qwen3.7-max)

**Reviewer:** Qwen CLI / qwen3.7-max
**Plan reviewed:** `docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md` (revised — produce-don't-write, commit `23ba054`)
**Date:** 2026-05-27
**Guardrail compliance:** Single review file produced; no other repo files modified.
**Previous review:** superseded — all four original findings resolved by the produce-don't-write revision (see §3 table).

---

## 1. Verdict

**proceed-with-changes** — The produce-don't-write revision cleanly resolved all four findings from the first review. Two remaining issues need attention: an uncaught `ReconcileError` that breaks the uniform error-model contract (F-1, medium), and a hardcoded `T2Mode.STRUCTURED` default that diverges from the legacy env-var path (F-2, low). Neither blocks the plan's structure — both are one-line fixes.

---

## 2. Findings

### F-1: `reconcile.reconcile` can raise `ReconcileError` uncaught — breaks produce-don't-write error contract

**Dimension:** B (architectural risk)
**Severity:** medium

**Issue:** Task 3 Step 3's `compile_source` calls `reconcile.reconcile(cr, vres.measure_findings)` without a try/except. `reconcile.reconcile` (`reconcile.py:~185-195`) raises `ReconcileError` in two cases: (a) an unknown finding type not registered in `_RULES`, and (b) a finding referencing an unknown `source_id`. If either fires, the exception propagates uncaught out of `compile_source` — the orchestrator sees a raw Python traceback, not a `CompileSourceResult(cr=None, failure_stage=..., error=...)`.

This violates the plan's own error-model contract stated in the architecture section: "All pre-commit failures return `CompileSourceResult(cr=None, failure_stage, exception_type, error)` so the orchestrator routes case-(a) uniformly." The compile, validate, canonicalize, and context-snapshot stages all correctly catch and wrap their exceptions; reconcile is the sole gap.

**Evidence:** `reconcile.py:185-195` — both `raise ReconcileError(...)` sites. Task 3 Step 3 `compile_source` implementation — the reconcile call has no try/except, while compile (err check), validate (`vres.gate_errors` check), canonicalize (try/except `CircularAliasError`), and context (try/except `Exception`) all do wrap their calls.

**Practical likelihood:** Low in normal operation — `compile_source` always produces exactly one compiled source with a matching `source_id`, and all finding types emitted by `validate_compile_result` have registered rules. But the contract says *all* pre-commit failures are wrapped; a defensive gap here could surface as a hard-to-debug crash during development.

**Recommendation:** Add a try/except around the reconcile call:
```python
try:
    reconcile.reconcile(cr, vres.measure_findings)
except reconcile.ReconcileError as e:
    return CompileSourceResult(
        cr=None, failure_stage="reconcile",
        exception_type=type(e).__name__, error=str(e))
```
Three lines; closes the only gap in the uniform error model.

---

### F-2: `mode: T2Mode = T2Mode.STRUCTURED` default bypasses the `KDB_T2_MODE` env var from Task #90

**Dimension:** B (architectural risk)
**Severity:** low

**Issue:** Task 3's `compile_source` signature hardcodes `mode: T2Mode = T2Mode.STRUCTURED` as the default. The legacy path (`run_compile` → `planner.build_jobs` → `build_context_snapshot`) reads `T2Mode` from `os.environ.get("KDB_T2_MODE", "structured")` (`graph_context_loader.py:193`). With the plan's default, `compile_source` always runs STRUCTURED mode regardless of the env var — unless the orchestrator explicitly passes `mode=...`.

This is *architecturally defensible* (the orchestrator should own the mode decision), but it creates a silent behavioral divergence: `kdb-old-compile` (frozen monolith) respects `KDB_T2_MODE`; `compile_source` does not. A developer switching between the two paths during NW-9 benchmark runs could see different T2 behavior without realizing why.

**Evidence:** `graph_context_loader.py:193` — `mode = T2Mode(os.environ.get("KDB_T2_MODE", "structured").upper())`. Task 3 Step 3 — `mode: T2Mode = T2Mode.STRUCTURED` in `compile_source` signature.

**Recommendation:** Option (b) preferred — add a one-line docstring note: "Default: STRUCTURED. The orchestrator should pass the resolved mode explicitly; this default exists for unit-test convenience and intentionally does not read `KDB_T2_MODE`." Option (a) — change the default to read the env var (matching legacy) — is also fine but adds an implicit dependency that the produce-don't-write design deliberately avoids.

---

## 3. What was checked and found sound

### Previous findings — all resolved by produce-don't-write

| Original finding | Resolution in revised plan |
|---|---|
| F-1: Alias-singleton rename untested on one-element `cr` | **Task 4** — dedicated test `test_compile_source_alias_singleton_rename` with a real `aliases.json` ledger; asserts both slug rename and `aliases_emitted` metadata |
| F-2: Wiki writes inside `compile_source` vs. "manifest untouched" | **Stage 8 removed** — `compile_source` writes nothing; apply-pages deferred to orchestrator (Plan 6) at the commit boundary |
| F-3: Collapsed error model loses stage signal | **`failure_stage` added** to `CompileSourceResult` with values `"context"`, `"compile"`, `"validate"`, `"canonicalize"` |
| F-4: `source_hash`/`source_mtime` provenance passthrough | **Both params removed** — orchestrator owns provenance at the commit boundary; `compile_source` signature is clean |

### Spec fidelity (Dimension A)

- **Stage redistribution:** stages 3→6 in `compile_source`; stages 1-2 / 7 / 8 / 9 / 10 reserved for orchestrator. Matches the spec's revised table exactly. Stage 8 (apply-pages) correctly deferred to the orchestrator's commit boundary.
- **In-memory contract:** `compile_source` takes `(source_id, body, frontmatter, conn)` — zero disk reads when `source_text` is populated. `source_text_for` short-circuits on `job.source_text is not None`. `source_name` derives from `source_id` (fixes the `abs_path=""` edge case that would have yielded an empty `source_name` and triggered `semantic_check` failure). All correct.
- **Optional pre-built snapshot:** `context_snapshot` kwarg allows the orchestrator to own all graph reads; `conn=None` works when snapshot is pre-built. Enables graph-free unit testing. Correct seam per the spec.
- **Make-before-break:** `kdb-old-compile` frozen alongside `kdb-compile` (both point to same module initially). No monolith code changes. Clean.
- **No scope creep:** Plan 1 stays within the `kdb-compile` rebuild. No pipeline registry, scanner, orchestrator loop, or `detect_orphans` work pulled in.
- **Cross-source page-merge trade-off:** Correctly identified and accepted per the spec (4/5 panel convergence). Graph stays authoritative via `SUPPORTS` edges; wiki body is last-writer-wins. `kdb-audit` (#93) handles out-of-band reconciliation.

### Architectural soundness (Dimension B)

- **One-element `cr` for validate/reconcile/canonicalize:** All three operate correctly on `compiled_sources` of length 1. No cross-source aggregate invariants are violated.
- **`CompileSourceResult` shape:** `failure_stage` + `exception_type` + `error` give the orchestrator structured routing without string parsing. `ok` property correctly returns `True` only when `error is None`.
- **TDD sequencing:** Each task follows fail-then-pass correctly. Test helpers (`_fm`, `_vault`, `_good_response`, `_fake_model`) are well-factored and reused. The `autouse` prompt-cache-clearing fixture matches the established `test_compiler.py` pattern.
- **Import cycle safety:** `types.py` uses `TYPE_CHECKING` guard for `SourceFrontmatter` annotation; `compiler.py` already imports from `source_io` at module level (line 46: `from kdb_compiler.source_io import SourceFrontmatter, parse_source_file`). Cycle-free by construction.
- **`source_io.py` integration:** `parse_source_file` and `SourceFrontmatter` live in the neutral module (Task #90 D-90-10), breaking the planner↔compiler circular import. The proposed `source_text_for` rewrite is a clean two-branch function that correctly prefers in-memory over disk.
- **Error-path tests (Task 5):** Compile-error (RuntimeError from model) and gate-error (monkeypatched `ValidationFinding` with `severity="gate"`) tests correctly exercise the `failure_stage` routing. `ValidationFinding` construction includes the required `severity` positional arg.
- **GraphDB test pattern:** `with GraphDB(tmp_path / "graph") as g:` correctly uses the context manager; `g.conn` returns the live `kuzu.Connection` via the `@property`. `build_context_snapshot` receives it correctly.
