# Task #91 Plan 1 Review — Grok Build

**Reviewer:** Grok Build (CLI, code-grounded)  
**Date:** 2026-05-29  
**Artifact reviewed:** `docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md` (the TDD plan)  
**Primary references:**  
- Design spec: `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md` (Pass-2 ingress + Orchestrator loop sections)  
- Ratified decisions: `docs/task91-kdb-orchestrate-blueprint.md` (D-91-1..D-91-14)  
- Code surface: `kdb_compiler/compiler.py`, `types.py`, `patch_applier.py`, `validate_compile_result.py`, `canonicalize.py`, `reconcile.py`, `graph_context_loader.py`  

This review is strictly read-only per the fire-prompt guardrail. No files other than this review document were created or modified.

---

## Verdict

**proceed-with-changes** — The plan faithfully extracts the Pass-2 compiler core (`compile_source`) per the spec's stage-redistribution table and in-memory ingress contract, with solid make-before-break discipline. However, two design seams (context-snapshot ownership and orchestrator-owned provenance threading into the core) create latent coupling that should be explicitly acknowledged (or lightly adjusted) before execution begins, as they directly affect Plan 6 composition and the orchestrator's ownership model.

---

## Findings

**Finding F-1 (Dimension A — Spec fidelity / Stage redistribution)**  
The plan correctly maps stages 3→6+8 into `compile_source` and reserves 1-2/7/9/10 for the orchestrator. The one-element `cr` wrapper + early return on compile/validate/canonicalize failure matches the "core does the heavy lifting, orchestrator owns the loop and commit" intent.

**Evidence:** Spec §"Pass-2 no longer scans" table + plan Tasks 3-4 (validate → reconcile → canonicalize → apply wired inside `compile_source`, with `kdb-old-compile` untouched).

**Recommendation:** No change required. This dimension is clean.

**Finding F-2 (Dimension B — Architectural risk / Context snapshot seam)**  
`compile_source` builds the `ContextSnapshot` internally via `build_context_snapshot(conn, ...)` (plan Task 3, `compiler.py:375`). The spec explicitly calls this "the only graph read" for the core. However, the prompt itself flags the open seam question: should the orchestrator (which owns the shared read-write conn and must guarantee read-after-write visibility for source N+1) pre-build the snapshot and pass it in, making the core do *zero* graph reads?

Current design couples the core to the live connection model. If Plan 6 later changes connection strategy (e.g., connection-per-source, snapshot caching, or explicit "read your own writes" helpers), this internal build becomes a hidden dependency.

**Evidence:** Fire-prompt Dimension B bullet 2 + spec "Forward flag — RESOLVED in *Component: Orchestrator loop*" (single read-write conn decision) + plan `compile_source` body that unconditionally calls `build_context_snapshot`.

**Recommendation:** Before execution, add an explicit one-paragraph "Seam decision record" in the plan (or a short appendix) stating: "We accept the compiler core performing the single snapshot read from the caller-supplied conn. This keeps `compile_source` self-contained for the v1 orchestrator loop. If future plans require the orchestrator to own all graph reads, we will invert the seam by adding an optional pre-built `snapshot: ContextSnapshot | None` parameter (default None = build internally)."

**Finding F-3 (Dimension B — Architectural risk / Provenance contract leak)**  
The plan threads `source_hash` and `source_mtime` (orchestrator-owned post-embed provenance) through `compile_source(...)` and then synthesizes a `single_scan` dict solely to satisfy `patch_applier._source_mtime_from_scan` + `current_hash` requirements (plan Task 4, `compiler.py:474-481`).

This is a clean technical workaround, but it is orchestrator metadata leaking into the compiler core's public interface. The core should ideally not need to know the shape of the orchestrator's scan ledger.

**Evidence:** Plan Task 4 Step 3 ("Feed the real provenance params") + `patch_applier.py:154-156` (hard requirement for numeric `current_mtime` or `PagePatchError`) + spec "Hash basis — whole-file, recalculated after embed".

**Recommendation:** Accept for Plan 1 (it works and unblocks). Document it as a known boundary smell. In Plan 6 (or a small follow-up), consider one of:
- Passing a tiny `Provenance` dataclass instead of two raw primitives.
- Moving the final apply step out of `compile_source` entirely (orchestrator calls `patch_applier` after the core returns the `cr`).
- Adding a narrow "apply-only" helper that the core can delegate to.

**Finding F-4 (Dimension B — Architectural risk / Error model collapse)**  
All pre-commit failures (model error, validation gate, `CircularAliasError`, `PagePatchError`) are collapsed into `CompileSourceResult(cr=None, error=str)`. This satisfies D-91-13 case (a) uniformity for the orchestrator's fail-fast handler.

However, the string is now the only diagnostic channel. Future observability, run summaries, or human triage may want to distinguish "LLM blew up" vs. "schema gate failed" vs. "circular alias during canonicalize".

**Evidence:** Plan Tasks 3-5 (early returns with string errors) + D-91-13 text on two-phase failure + `CompileSourceResult` shape in `types.py` (plan Task 2).

**Recommendation:** Keep the uniform `error: str` surface for the orchestrator (per D-91-13). Add an optional `error_code: str | None` field (or a small enum) in `CompileSourceResult` for the three main classes (compile, validate_gate, canonicalize/apply). This is cheap, backward-compatible (default None), and gives the orchestrator and telemetry something structured to key on without changing the primary failure path.

**Finding F-5 (Dimension B — Architectural risk / Side effects & partial state)**  
`compile_one` unconditionally writes a `resp_stats` record (via its internal `finally` path). `canonicalize.run` mutates the `cr` dict in place. If `compile_source` fails after canonicalize but before/during apply (with `write=True`), the caller gets a `cr=None` result but may have left a stats record and a partially mutated `cr` object.

Under the eventual per-source fail-fast loop this is mostly harmless (the whole run aborts), but it leaves an audit artifact for a source that never reached manifest commit.

**Evidence:** `compiler.py` (the `compile_one` call + stats writing) + plan note on resp_stats + canonicalize mutation.

**Recommendation:** Acceptable for v1. The stats record is useful even for failed sources (diagnostics). Add a one-line comment in the plan: "Partial state (resp_stats + in-place cr mutation) on mid-core failure is accepted; the orchestrator's fail-fast + per-source commit model makes it non-leaking for the live graph/manifest."

**Finding F-6 (Dimension A — Spec fidelity / One-element cr assumption)**  
validate / reconcile / canonicalize were originally written for a batch `compiled_sources` list. The plan wraps a single source as `{"compiled_sources": [cs]}` and passes it through. Current implementations iterate the list and have no cross-source aggregate logic, so it works.

This is a latent assumption, not a current bug. If future reconcile or canonicalize logic ever adds batch-level dedup, ordering, or global invariants, the one-element wrapper becomes a silent hazard.

**Evidence:** Plan "Wrapping rationale" + current `reconcile.py` and `canonicalize.py` (they operate on `cr["compiled_sources"]`).

**Recommendation:** Add a one-sentence note in the plan: "The one-element cr wrapper is safe because reconcile/canonicalize have no cross-source logic today. Any future batch-level behavior must be reviewed against this assumption."

---

## What you checked and found sound

- Stage redistribution exactly matches the spec table (3-4-5-6-8 inside core; 1-2/7/9/10 reserved).
- In-memory ingress contract honored: `CompileJob` extension + `source_text_for` preference + `source_name = Path(source_id).name` fix eliminates the two disk re-reads that existed in the monolith path.
- Direct Python API (D-91-12) used throughout; no subprocess calls.
- Fail-fast + uniform pre-commit error shape supports D-91-8 and D-91-13 case (a).
- `kdb-old-compile` freeze + make-before-break present and non-destructive.
- No scope creep into registry, scanner, orchestrator loop, or `detect_orphans` (those remain later plans).
- TDD structure (failing tests first, then implementation) is followed; the two "open verification points" (patch_applier path assertion, ValidationFinding constructor) are explicitly flagged for execution-time confirmation.
- Error paths for compile_one failure and validation gate are explicitly tested.

---

**Guardrail compliance:** This review created exactly one file (`docs/task91-plan1-review-grok.md`). No other files were created, modified, or deleted. No code, schemas, plans, or specs were edited. No implementation patches were proposed. All analysis stayed within the two mandated dimensions and the explicitly out-of-scope items (signatures, TDD mechanics, later plans) were ignored except where they directly impacted fidelity or risk.

The review is grounded in the actual plan text, the spec's ingress/orchestrator sections, the D-91 decision table, and direct inspection of the touched code paths.