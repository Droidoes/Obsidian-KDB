# Task 91 Plan 1 Review — Codex

## 1. Verdict

**proceed-with-changes** — Plan 1 is directionally faithful to the Task #91 spec, but it needs explicit handling for batch-boundary semantic changes and pre-commit failure reporting before execution.

## 2. Findings

### Finding 1 — One-source `cr` is not semantically identical to the old batch boundary

**Dimension:** B — architectural risk / hidden design flaws  
**Severity:** High

**Issue:** Plan 1 treats validate / reconcile / canonicalize / apply as modules that "merely iterate `compiled_sources`", so wrapping a one-element `cr` is presented as behavior-preserving. That is true for several checks, but not for all downstream semantics. Both canonicalization and page application currently use the full `compiled_sources` list as a batch-level aggregation boundary.

**Evidence:**
- Plan 1 states that stages 4 / 5 / 6 "already operate on a `cr`-shaped dict and merely iterate `compiled_sources`" and that `compile_source` wraps a one-element `cr` (`docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md:7`).
- `canonicalize._merge_page_intents()` groups page intents across every source in `cr["compiled_sources"]` and merges collisions with unioned `supports_page_existence` (`kdb_compiler/canonicalize.py:336-462`).
- `patch_applier.build_page_patches()` first accumulates `source_refs` per page across all compiled sources in the current `compile_result`, then writes frontmatter from that accumulated set (`kdb_compiler/patch_applier.py:208-238`).
- The spec moves to a per-source loop where the next source sees prior graph writes after `apply_compile_result` (`docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md:266-278`), but Plan 1's wiki-page write happens before graph sync and only has the one-source `cr`.

**Recommendation:** Amend Plan 1 to name this as an intentional semantic change, not an implementation detail. At minimum, add tests or acceptance notes for two changed behaviors:

1. When two sources in one orchestrator run emit the same canonical page slug, cross-source page merging no longer happens inside `canonicalize.run()`; correctness must come from source N graph-sync before source N+1 context construction.
2. Wiki page frontmatter `source_refs` from `patch_applier` will only represent the current one-source `cr`, unless Plan 1 adds a graph-backed enrichment step or later orchestrator stage to project full support refs.

If full wiki `source_refs` fidelity matters, do not leave this to later discovery. Either move page rendering to a point where current graph support can be read, or explicitly downgrade wiki `source_refs` to per-event provenance and keep GraphDB as the authoritative support surface.

### Finding 2 — Apply-page failures can escape the result model and can leave partial wiki writes ambiguous

**Dimension:** A — spec fidelity  
**Severity:** High

**Issue:** Plan 1 says all pre-commit failure modes return `CompileSourceResult(cr=None, error=...)`, but the apply-pages step only catches `PagePatchError`. `patch_applier.apply()` can also raise filesystem errors from the atomic write loop. If that happens, `compile_source()` can raise instead of returning the promised result shape. Also, because the loop writes page-by-page, a failure after one successful write can leave wiki pages changed while manifest and graph remain uncommitted.

**Evidence:**
- Plan 1's result contract says compile / validate / canonicalize / apply failures return `CompileSourceResult(cr=None, error=...)` (`docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md:361-372`).
- The apply implementation only catches `patch_applier.PagePatchError` (`docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md:482-488`).
- `patch_applier.apply()` renders all patches first, but then writes them one at a time with `atomic_write_text()` (`kdb_compiler/patch_applier.py:267-290`), so `OSError` or another filesystem exception can occur during the write loop.
- The Task #91 spec classifies patch-apply failure as pre-commit case (a): source not committed, manifest untouched (`docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md:309-314`).

**Recommendation:** In Plan 1, catch apply-stage filesystem failures as part of the `CompileSourceResult` contract, not just `PagePatchError`. Add `stage="apply_pages"` / `exception_type` metadata to the result or error payload. Also document the residual wiki side effect explicitly: a pre-commit apply failure keeps manifest and graph untouched, but may have already atomically written one or more wiki pages. If that is unacceptable, Plan 1 needs a staging/rollback strategy before implementation; if acceptable for single-user v1, say so and make rerun/rebuild behavior explicit.

### Finding 3 — The collapsed `error: str` result is too thin for the orchestrator contract

**Dimension:** B — architectural risk / hidden design flaws  
**Severity:** Medium

**Issue:** `CompileSourceResult(cr, pages_written, error)` gives the orchestrator enough to fail fast, but not enough to produce the case-aware summary required by the Task #91 design without parsing strings. It also omits context-snapshot failures from the listed pre-commit modes.

**Evidence:**
- Plan 1 defines `CompileSourceResult` with only `cr`, `pages_written`, `error`, and derived `.ok` (`docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md:174-188`).
- The spec requires abort summaries to distinguish "not committed" vs "committed-but-graph-sync-failed" and record the failing source / case (`docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md:309-327`).
- `compile_source()` calls `build_context_snapshot()` before any local failure wrapper in the planned code (`docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md:374-378`). Graph read failures are therefore outside the uniform result model.
- The existing monolithic orchestrator records failures with stage index, stage name, and failure type rather than a bare string (`kdb_compiler/kdb_compile.py:202-224`).

**Recommendation:** Extend `CompileSourceResult` before implementation:

```python
stage: str | None = None
exception_type: str | None = None
committed: bool = False
```

Suggested stage values: `context`, `compile`, `validate`, `reconcile`, `canonicalize`, `apply_pages`. Keep `error` as the human detail, but do not make downstream orchestration infer behavior from text. Wrap context snapshot and reconcile errors too, since both are pre-commit case (a) failures.

## 3. What Checked And Found Sound

- Plan 1 correctly keeps the scope narrow: it does not pull registry, scanner, orchestrator loop, `detect_orphans`, or cleanup into the `compile_source` rebuild.
- The in-memory `CompileJob.source_text` / `frontmatter` seam matches the spec's zero disk re-read ingress contract.
- Deriving `source_name` from `source_id` is required and safe for the in-memory path; it also preserves the legacy path where `Path(abs_path).name == Path(source_id).name`.
- Passing a caller-owned Kuzu connection into `build_context_snapshot()` matches the spec's shared read-write connection decision.
- Keeping `kdb-old-compile` as an alias while leaving the monolith intact is the right make-before-break step.
- Threading `source_hash` and `source_mtime` into the synthetic single-source scan is necessary for `patch_applier` frontmatter and is correctly identified in the plan.
