# Deepseek Review — Task #91 Plan 1 (`kdb-compile` rebuild)

## Verdict

**`proceed-with-changes`** — The plan is mechanically sound and faithfully implements the spec's Pass-2 ingress contract, but has two medium-severity design risks that should be addressed before execution: (1) the context-snapshot seam places Kuzu coupling inside the compiler core that will complicate future context-loading redesign, and (2) the one-element `cr` degeneracy for cross-source checks should be explicitly documented so the orchestrator loop author knows which invariants Plan 1 silently leaves for them.

## Findings

### F1 — Context-snapshot self-read couples compiler core to Kuzu

- **Dimension:** B (architectural risk)
- **Severity:** medium
- **Issue:** `compile_source` builds the context snapshot *internally* from the passed `conn` (plan Task 3, lines 374–378). This is faithful to the spec's Pass-2 ingress, but it means the compiler core — whose stated purpose is "stages 3→6+8 on in-memory inputs" — has a live Kuzu read as its very first step. This has three downstream consequences:

  1. **Test coupling.** Every test of `compile_source` needs a real `GraphDB` instance (the plan already does this with `tmp_path / "graph"` — the cost is paid, but it's worth being explicit that this is now the *only* way to test the compiler core).
  2. **Future redesign friction.** The T2/T3 context-loading redesign hypothesis (`docs/nw9-context-list-t2-t3-redesign-hypothesis.md`) and the spec's own orchestrator-loop section already show the context-construction logic is the most volatile part of the pipeline. Baking it inside `compile_source` means every context-loading change is also a `compile_source` change — even though `compile_source`'s *real* job (artifact production) doesn't care how the snapshot was built.
  3. **Seam placement.** The spec's orchestrator loop opens one shared read-write conn and threads it through. If the orchestrator built the snapshot and passed it in, `compile_source` would be a pure function of `(source_id, body, frontmatter, snapshot) → artifacts` — zero graph reads, zero Kuzu dependency. The current seam is one hop inside the boundary, making it harder to test artifact production in isolation.

- **Evidence:** Plan Task 3 lines 374–378: `snapshot = build_context_snapshot(conn, source_id=source_id, source_text=body, frontmatter=frontmatter, ...)`. Spec Pass-2 ingress: `compile_source(source_id, body, frontmatter, conn, ...)` — spec explicitly chose `conn`-in not `snapshot`-in. This finding is about the spec's design choice, not a plan deviation from spec.

- **Recommendation:** Accept the spec's design for Plan 1 (it works, it's simple, it closes the loop). **Add a brief design note** in the `compile_source` docstring: "Context snapshot is built internally from the passed Kuzu connection — the ONLY graph read in Pass-2. If context-loading is redesigned (T2/T3), this is the single seam to modify; the rest of compile_source is graph-agnostic." Also flag in the plan's Self-Review checklist that snapshot construction is the only Kuzu coupling point and should be extracted to a parameter (`snapshot_in: ContextSnapshot | None = None`) if the context-loading redesign lands before the orchestrator loop ships.

---

### F2 — Cross-source invariants degenerate on one-element `cr`; orchestrator must own them

- **Dimension:** A (spec fidelity)
- **Severity:** medium
- **Issue:** The plan wraps a single compiled source in a one-element `cr` dict and passes it through `validate_compile_result.validate()` → `reconcile.reconcile()` → `canonicalize.run()`. Two of these functions carry cross-source invariants that are silently no-op on a one-element list:

  - **`validate`** — `duplicate_slug` check iterates all `compiled_sources[]` looking for slug collisions across sources. With one source, this check never fires. No bug — there's nothing to collide with — but the plan doesn't acknowledge that the orchestrator loop (Plan 6) now owns cross-source slug uniqueness, since each source is compiled independently with no visibility into other sources' slugs.
  - **`canonicalize.run`** — Pass 2 (`_merge_page_intents`) resolves OQ-F cases where two compiled sources emit the same page slug. With one source, no merges occur. Again, not a bug — but the orchestrator loop must handle the case where source B emits a slug source A already emitted and committed to the graph earlier in the same run.

  Neither is a correctness problem in Plan 1's scope, but both are **load-bearing invariants silently demoted from compile-time to orchestrator-time** by the per-source split. The plan's Self-Review checklist (lines 597–601) says "Not in Plan 1 (later plans): detect_orphans flag (Plan 2), registry (Plan 3), scanner (Plan 4), the loop (Plan 6)" — it should also call out these cross-source invariants.

- **Evidence:**
  - `validate_compile_result.py` — `duplicate_slug` is emitted inside `_check_source` which iterates `compiled_sources[]` with a seen-slugs set scoped to the full `cr`.
  - `canonicalize.py:591` — `_merge_page_intents(cr, resolve)` merges same-slug pages from different compiled_sources.
  - Spec stage-redistribution table: stages 4/5/6 are all in the compiler core — but the table doesn't call out which invariants become per-source degeneracies.

- **Recommendation:** Add a bullet to the plan's Task 5 rationale or Self-Review checklist: "Per-source `duplicate_slug` and `page-intent merging` degenerate to no-ops on a one-element `cr`. The orchestrator loop (Plan 6, not this plan) owns cross-source slug-uniqueness and page-intent deconfliction across the run's full source set. Plan 1's `compile_source` correctly leaves these to the orchestrator."

---

### F3 — Partial wiki writes on apply failure leave orphan pages (acknowledged gap)

- **Dimension:** B (architectural risk)
- **Severity:** low
- **Issue:** `patch_applier.apply` iterates pages and writes each atomically via `atomic_write_text`. If the N-th page write raises `PagePatchError`, pages 1..N-1 are already on disk. The plan wraps this in `CompileSourceResult(error=...)` (Task 4, lines 487–488), so the orchestrator sees a failure and fail-fasts — but the partial writes remain. In a later run, `kdb-scan` sees these orphan pages as new files (they have no manifest entry) and could flag them.

  This is **not** a new problem — the monolith has the same behavior (all pages written, then manifest committed; a crash mid-apply leaves partial writes). But the per-source split amplifies it: the monolith writes ALL sources' pages before committing, so a crash loses one run's work; the per-source loop writes one source's pages, commits, then moves to the next — so a crash loses only one source's work. The spec's ingestion section (§ "Self-healing edge") already covers this: "a failed signal-source can leave frontmatter on disk with no committed manifest entry — the next run re-enriches + re-embeds, overwriting."

- **Evidence:**
  - `patch_applier.py:287–290` — writes pages one-by-one in a `for` loop; no batch rollback.
  - Plan Task 4 lines 487–488 — `except patch_applier.PagePatchError as e: return CompileSourceResult(cr=None, error=...)`.
  - Spec ingestion section — "Self-healing edge: embed precedes a possible [B] fail-fast, so a failed signal-source can leave frontmatter on disk with no committed manifest entry."

- **Recommendation:** Add a one-line note in the `compile_source` docstring or Task 4 rationale: "Partial wiki writes from a failed `apply()` do not roll back — this is the same self-healing edge the monolith and spec ingestion section accept for v1; the next run cleans up any orphan pages."

---

### F4 — `source_name` derivation change affects ALL paths (regression surface)

- **Dimension:** B (architectural risk)
- **Severity:** low
- **Issue:** Plan Task 3a changes `source_name = Path(job.abs_path).name` to `Path(job.source_id).name` (compiler.py:235). The plan argues this is safe because `Path(abs_path).name == Path(source_id).name` for normal sources — which is correct: both paths share the same basename. However, this change affects the **legacy** `kdb-old-compile` path too (since `compile_one` is shared), and the plan's only regression test is the monolith suite (`test_kdb_compile.py`). That suite may not cover edge cases like: (a) source_id with a different basename than abs_path (currently impossible in the monolith, but the invariant is implicit), or (b) non-POSIX path separators if the vault is ever on a different OS.

  The plan indirectly validates this: `test_compile_source_happy_path` uses `abs_path=""` + `source_id="KDB/raw/s.md"` with a model echoing `"s.md"` — and if `source_name` were wrong, the `semantic_check` in `validate_compiled_source_response` (which compares echoed `source_name` against the prompt's `source_name`) would fail. So the test *would* catch a mismatch. The risk is low but the invariant is undocumented.

- **Evidence:**
  - `compiler.py:235` — current: `source_name = Path(job.abs_path).name`
  - Plan Task 3a — proposed: `source_name = Path(job.source_id).name`
  - `validate_compiled_source_response.py:68-72` — `semantic_check` compares model-echoed `source_name` against the prompt's `source_name`; hard-errors on mismatch.

- **Recommendation:** Add a comment above the changed line: "Derived from `source_id` not `abs_path` — safe because both share the same basename for all source types; validated by semantic_check on model response." No code change needed.

---

## What I checked and found sound

1. **Spec fidelity — Pass-2 ingress contract.** Plan's `compile_source` maps 1:1 onto the spec's 3-step ingress: build snapshot → compile_one on in-memory job → validate/reconcile/canonicalize/apply. Zero disk re-reads verified (in-memory `CompileJob` with `source_text` + `frontmatter` fields, `source_text_for` preference). ✅

2. **Stage redistribution.** Stages 3→6+8 in compiler core, 1-2/7/9/10 reserved for orchestrator — matches the spec table exactly. ✅

3. **Make-before-break.** `kdb-old-compile` freeze (Task 2 Step 5) adds a CLI alias without touching the monolith — follows the established Task #73 precedent. `kdb-compile` is NOT repointed yet (plan calls this out as a later cleanup). ✅

4. **D-91-12 (direct Python API).** `compile_source` is a library function, not a subprocess — matches the ratified decision. ✅

5. **D-91-13 two-phase failure model.** Plan 1's `compile_source` only produces case-(a) failures (pre-commit); case-(b) (post-manifest graph-sync) is exclusively the orchestrator's concern. The error model (`CompileSourceResult(cr=None, error=...)`) is correct for case-(a). ✅

6. **Scope discipline.** Plan explicitly defers pipeline registry, scanner generalization, orchestrator loop, and `detect_orphans` to later plans. Self-Review checklist confirms. ✅

7. **Mechanical correctness of key seams (verified, not re-checked):**
   - `compile_one` signature + return shape — plan's `cs, logs, warns, err = compile_one(...)` matches `compiler.py:198-221`.
   - `validate_compile_result.validate(cr) → ValidationResult` — plan's `vres.gate_errors` access correct per `validate_compile_result.py:63-70`.
   - `reconcile.reconcile(cr, vres.measure_findings)` — mutates `cr` in place per `reconcile.py:220-241`.
   - `canonicalize.run(cr, ledger, run_id)` — mutates `cr` in place, raises `CircularAliasError` per `canonicalize.py:563-612`.
   - `patch_applier.apply(vault_root, compile_result=cr, last_scan=single_scan, run_ctx=ctx, write=write)` — returns `ApplyResult` with `.pages_written` per `patch_applier.py:255-291`.
   - `build_context_snapshot(conn, *, source_id, source_text, frontmatter, mode, resolver)` — per `graph_context_loader.py:54-63`.

8. **`single_scan` construction for patch_applier.** Plan correctly includes `current_mtime` (numeric, mandatory — `_source_mtime_from_scan` raises `PagePatchError` on non-numeric per `patch_applier.py:154-156`) and `current_hash`. ✅

9. **Error-path coverage.** Task 5 tests cover `compile_one` exception propagation and `validate` gate-error handling — the two most likely failure modes. The note about `CircularAliasError` + `PagePatchError` wrapping (no dedicated test, deferred) is honest about coverage gaps. ✅

10. **Regression safety.** Task 2 Step 7 runs the full monolith suite; Task 5 Step 3 runs the full `kdb_compiler/tests/` suite. ✅
