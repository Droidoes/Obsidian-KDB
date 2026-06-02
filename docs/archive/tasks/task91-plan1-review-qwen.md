# Task #91 Plan 1 Review — Qwen CLI (qwen3.7-max)

**Reviewer:** Qwen CLI / qwen3.7-max
**Plan reviewed:** `docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md`
**Date:** 2026-05-27
**Guardrail compliance:** Single review file produced; no other repo files modified.

---

## 1. Verdict

**proceed-with-changes** — Plan 1 is architecturally faithful to the spec and blueprint, with sound TDD sequencing. Two medium-severity design risks need resolution before execution: the wiki-write/manifest-commit ordering gap (F-2) and the collapsed error model that loses D-91-13 case-(a)/(b) distinguishability (F-3). Neither blocks the plan's structure — both are addressable with targeted annotations and a minor type extension.

---

## 2. Findings

### F-1: `canonicalize.run` on one-element `cr` — alias-singleton rename is a silent behavioral change

**Dimension:** B (architectural risk)
**Severity:** medium

**Issue:** `canonicalize._merge_page_intents` iterates all page intents across all `compiled_sources` and renames slugs that resolve through the alias ledger. On a batch `cr`, this deduplicates across sources. On a one-element `cr`, there's only one source — so cross-source merging is vacuous. But the **alias-singleton rename** (lines ~310-325 of `canonicalize.py`) still fires: if the LLM emits `page.slug = "aapl"` and the ledger maps `aapl → apple-inc`, the page is renamed in-place to `apple-inc`.

This is *correct* behavior (it's what canonicalize is supposed to do). But it's a **new code path being exercised** for the first time on a one-element `cr` — the monolith's `run_compile` always produces a multi-source `cr`. The plan's happy-path test (`test_compile_source_happy_path`) asserts `"canonical_meta" in result.cr` but does **not** assert that alias-singleton rename actually fires or that the renamed page lands correctly.

**Evidence:** `canonicalize.py:310-325` — the `if _normalize_slug(page["slug"]) != canonical` branch fires for any page whose slug has an alias mapping, regardless of `compiled_sources` length. The test at Plan Task 3 Step 1 uses `concept_slugs: []` and a single summary page — no alias-mapped concept/article pages to exercise this path.

**Recommendation:** Add a dedicated test in Task 5 (error paths) or a new Task 3b that exercises alias-singleton rename on a one-element `cr`. Build a ledger with at least one alias entry, have the model emit a page whose slug matches the alias surface, and assert (a) the page's slug was renamed to the canonical, and (b) `canonical_meta.aliases_emitted` contains the mapping. This locks the most novel behavioral change in the plan.

---

### F-2: Wiki writes happen inside `compile_source` but D-91-13 case-(a) says "manifest untouched"

**Dimension:** B (architectural risk)
**Severity:** medium

**Issue:** `patch_applier.apply` (wired in Task 4) writes wiki pages to disk **inside** `compile_source`. If wiki writes succeed but the orchestrator's subsequent manifest commit fails (exit 5, D-91-13 case-(a)), the result is: wiki pages exist on disk for a source whose manifest entry was never updated. The source will be re-detected as CHANGED on the next scan (manifest hash ≠ on-disk hash), causing a re-compile that overwrites the wiki pages — so the system **self-heals** on re-run.

However, this creates a subtle inconsistency within a single run: the "manifest untouched" invariant from D-91-13 case-(a) doesn't fully hold because wiki writes are a **committed side effect** that happens before the manifest commit. This is the same trade-off the monolith already makes (wiki writes in Stage 8, manifest commit in Stage 9), so it's not a *new* risk — but the plan should surface it explicitly rather than letting the reader discover it.

**Evidence:** D-91-13 phase-(a) definition: "pre-commit failures... failing source NOT committed, manifest untouched." Plan Task 4 wires `patch_applier.apply` before the function returns, so wiki pages land before the orchestrator's manifest commit. The monolith has the same ordering (`kdb_compile.py` Stage 8 → Stage 9), so this is inherited behavior, not a regression.

**Recommendation:** Add a brief annotation in the plan's architecture section (or in `compile_source`'s docstring) acknowledging: "Wiki writes happen inside compile_source but the manifest commit happens in the orchestrator. A manifest-commit failure after successful wiki writes leaves orphan wiki pages that self-heal on next run (same trade-off as the monolith's Stage 8→9 ordering)." This prevents the orchestrator-plan author from being surprised when composing Plan 6 on top.

---

### F-3: Collapsed error model loses orchestrator-actionable signal

**Dimension:** B (architectural risk)
**Severity:** medium

**Issue:** All pre-commit failures collapse into `CompileSourceResult(cr=None, error=<string>)`. The orchestrator can only distinguish success (`ok=True`) from failure (`ok=False`). But D-91-8 fail-fast exit codes distinguish enrich failure (exit 3) from compile failure (exit 4), and the orchestrator's run summary needs to report **what stage** failed (model error vs. validation gate vs. canonicalize vs. apply) for operator debuggability.

With the current `error: str | None` field, the orchestrator must parse the error string to determine the failure stage — fragile and lossy. A `failure_stage` enum field (e.g., `"compile" | "validate" | "canonicalize" | "apply"`) would give the orchestrator structured signal without string parsing.

**Evidence:** D-91-10 run summary includes `sources_failed` count and the pseudocode in the blueprint (§4.2) distinguishes `CompilerError` from `GraphSyncError`. The plan's `CompileSourceResult` only has `error: str | None` — no structured stage field. Plan Task 3 Step 3b wraps `CircularAliasError` as `"canonicalize failed: {e}"` and Task 4 wraps `PagePatchError` as `"apply-pages failed: {e}"` — the stage is encoded in the string prefix, not in a structured field.

**Recommendation:** Add a `failure_stage: str | None` field to `CompileSourceResult` alongside `error`. Set it to `"compile"`, `"validate"`, `"canonicalize"`, or `"apply"` in each error-return path. This costs one field and four string literals but gives the orchestrator structured routing without regex parsing. Low-effort, high-signal refinement.

---

### F-4: `source_hash` / `source_mtime` passthrough is a minor contract leak

**Dimension:** B (architectural risk)
**Severity:** low

**Issue:** `compile_source` accepts `source_hash: str` and `source_mtime: float` solely to construct the `single_scan` dict for `patch_applier.apply`. The function never uses these values for any logic of its own — it's pure passthrough. This makes `compile_source`'s parameter list 2 fields longer than its own logic requires, coupling its signature to a downstream consumer's needs.

**Evidence:** Plan Task 4 Step 3: `single_scan = {"files": [{"path": source_id, ..., "current_hash": source_hash, "current_mtime": source_mtime}]}`. The only consumer of these values is `patch_applier._source_mtime_from_scan` and `_fm_for_page` (which stamps `raw_hash` / `raw_mtime` into page frontmatter).

**Recommendation:** Acceptable for v1 — the provenance must reach `patch_applier` somehow, and threading it through `compile_source` is the simplest path. For v1.1, consider a `SourceProvenance` dataclass (`source_id`, `source_hash`, `source_mtime`) that bundles the three orchestrator-owned fields into one parameter, reducing `compile_source`'s arity by 2. Not blocking.

---

## 3. What was checked and found sound

- **Stage redistribution (§3→6+8 in core, 1-2/7/9/10 reserved):** Matches the spec's table exactly. No stages leaked into the compiler core that belong to the orchestrator.

- **In-memory `CompileJob` extension:** `source_text: str | None` and `frontmatter: SourceFrontmatter | None` with `None` defaults preserve full backward compatibility with the legacy planner path. `source_text_for`'s preference logic is clean — short-circuits on `source_text is not None`.

- **`source_name` derivation fix (Task 3 Step 3a):** Changing from `Path(job.abs_path).name` to `Path(job.source_id).name` is correct. Verified that for normal sources, `Path(abs_path).name == Path(source_id).name` (both yield the filename). The in-memory path (`abs_path=""`) would have yielded `""` — a hard error in `semantic_check`. Good catch in the plan.

- **Monolith freeze as `kdb-old-compile`:** Minimal and correct. Both `kdb-old-compile` and `kdb-compile` point to the same module temporarily. No module logic changes.

- **One-element `cr` pattern for validate/reconcile:** Verified that `validate_compile_result.validate` (schema + semantic), `reconcile.reconcile` (finding dispatch), and `canonicalize.run` (5-pass algorithm) all operate correctly on a `compiled_sources` list of length 1. No cross-source aggregate invariants or ordering assumptions are violated.

- **`single_scan` construction for `patch_applier`:** The synthetic scan dict correctly provides `current_hash` and `current_mtime` from the orchestrator-supplied provenance, satisfying `patch_applier._source_mtime_from_scan`'s requirement (raises `PagePatchError` on non-numeric mtime).

- **Context-snapshot seam (internal build):** `compile_source` builds the snapshot from `conn` before compiling, matching the spec's ingress contract. Under the single-connection model (Kuzu read-after-write is immediate), each source gets a fresh snapshot. No stale-read risk.

- **Make-before-break discipline:** `kdb-old-compile` is preserved. The monolith's module is untouched. Console scripts are additive only. Clean.

- **TDD sequencing:** Each task follows fail-then-pass correctly. Tests are well-targeted — Task 1 (in-memory preference), Task 2 (result shape), Task 3 (happy path), Task 4 (wiki write), Task 5 (error paths). The gate-error test uses monkeypatch correctly.

- **No scope creep:** Plan 1 does not touch the pipeline registry, scanner generalization, orchestrator loop, or `detect_orphans`. Stays within "the `kdb-compile` rebuild."
