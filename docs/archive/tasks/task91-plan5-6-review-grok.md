# Task #91 Plan 5+6 Review — Grok Build

**Reviewer:** Grok Build (CLI, code-grounded)  
**Date:** 2026-05-29  
**Artifact reviewed:** `docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md`  
**Primary references:**  
- Design spec: `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md` (Orchestrator loop, Pass-1 egress, Pass-2 ingress)  
- Ratified decisions: `docs/task91-kdb-orchestrate-blueprint.md` (D-91-1..D-91-14, especially D-91-8/10/13/14)  
- Shipped foundations (usage only): `compile_source`, `apply_compile_result` + `detect_orphans`, `pipeline_registry`, `scan_scope`, `build_source_state_update`, `enrich_one`, `patch_applier`, `kdb_clean`

This review is strictly read-only per the fire-prompt guardrail. Exactly one file created. No other repository changes.

---

## Verdict

**proceed-with-changes** — The plan is a solid capstone integration that correctly wires the four shipped foundations into a per-source loop with proper fail-fast (D-91-8), D-91-13 case-(a)/(b) boundaries, and single shared read-write connection. The primary open fork (D1 journaling granularity) is well-framed for panel judgment. Minor clarifications on sidecar/journal ordering and the deferred OQ-91-8 MOVED+CHANGED edge case would strengthen the plan before execution.

---

## Findings

**Finding F-1 (D1 — Per-source journaling / replayability — PRIMARY)**  
The plan's lean (accumulate per-source `cr`s, write the run journal + `compile_result` sidecar once at `_finalize`) reuses the existing `graphdb-kdb rebuild` machinery with zero changes. This is the lowest-machinery path.

However, it creates a real (if narrow) consistency window: after per-source manifest + graph-sync commit but before finalize, a crash leaves sources that are live in the graph and manifest but absent from any replayable journal/sidecar. The "double fault" (graph also lost) is the only real recovery gap, but the plan correctly surfaces this as the central trade-off.

**Evidence:** Plan "⚠️ Design points" §1 + Task 2 (the `# (journaling: accumulate cr for finalize per Design Point 1)` comment) + Task 4 (`_finalize` writes journal/sidecar) + spec D-91-10 + D-91-13.

**Recommendation:** Keep the accumulate-at-finalize lean for v1 (machinery cost is real). Add one explicit sentence in the plan: "A mid-loop crash before `_finalize` produces committed-but-unjournaled sources. Recovery is `graphdb-kdb rebuild` only if the GraphDB is also lost (double fault). Single-fault (GraphDB intact) is safe because per-source commits already landed." This makes the residual risk transparent for the panel and for Joseph.

**Finding F-2 (D2 — Per-source commit ordering + D-91-13 correctness)**  
The sequence in Task 2 (apply-wiki → manifest write ← BOUNDARY → sidecar/journal comment → graph-sync with `detect_orphans=False`) is correct for D-91-13.

- Pre-boundary failure (wiki written, manifest fails) → case (a): source not committed, self-healing on next run (next run sees hash mismatch and re-enriches).
- Post-boundary (manifest + wiki + sidecar landed, graph-sync fails) → case (b): rebuild required.

The plan places the sidecar/journal write *after* the manifest boundary in the comment, which aligns with the "replayable payload" contract.

**Evidence:** Plan Task 2 `_commit_source` pseudocode + D-91-13 text + spec "Per-source commit ordering".

**Recommendation:** Make the sidecar/journal write explicit (not just a comment) in the pseudocode, and note that it happens after the manifest boundary but before graph-sync. This removes any ambiguity about whether a crash between manifest and sidecar write could leave a non-replayable but committed source.

**Finding F-3 (D3 — Integration correctness / batch-assumption traps)**  
The fire-prompt states that `build_source_state_update` is already verified as per-source-safe (it only iterates `last_scan`'s files + reconcile ops, no full prior keyset diff). Inspection of `source_state_update.py:146-179` confirms this: the function only touches entries present in the incoming `last_scan`.

`apply_compile_result` (with `detect_orphans=False`) is also correctly used: Phase 4 orphan marking is deferred to the single `_finalize` call (plan Task 4), avoiding the transient-orphan context pollution problem that drove the deferral decision.

No hidden cross-source assumptions were found in the loop's usage of the four foundations.

**Evidence:** Plan "Task 2 Step 2" note + `source_state_update.py:146` (only `last_scan` files) + `ingestor.py:715-720` (`detect_orphans` as standalone end-of-run pass) + plan Task 4.

**Recommendation:** None required. The "already verified" claim holds under inspection. Add a one-line cross-reference in the plan to the specific verification (file:line) so future readers do not have to re-prove it.

**Finding F-4 (D3 — patch_applier per-source source_refs)**  
The plan correctly accepts the cross-source wiki merge trade-off (last-writer-wins on the wiki page body) that was ratified during Plan 1 review. `patch_applier` is called with a synthetic one-source `last_scan`; any `source_refs` drift is punted to the out-of-band `kdb-audit` (#93) reconciler, consistent with `[[feedback_obsidian_wikilinks_are_vanity]]`.

**Evidence:** Plan Task 2 (single-source `last_scan` construction) + spec "Cross-source page-merge — accepted single-user trade-off".

**Recommendation:** None. The plan faithfully carries forward the accepted trade-off.

**Finding F-5 (D4 — Fail-fast / resume / idempotency)**  
Per-source commit + fail-fast (D-91-8) makes re-run a natural resume. The embed-during-enrich + post-embed whole-file hash (Task 1 + spec "Hash basis") ensures that a committed source appears UNCHANGED on the next scan, so it is skipped. A mid-run failed source (pre-manifest) will be re-detected on re-run and re-enriched (self-healing).

Read-after-write on the single shared connection was already empirically grounded in the spec (Kuzu 0.11.3 probe); the plan correctly threads that one connection through the entire loop.

**Evidence:** Plan Task 3 (routing off `scan.to_compile` / `to_reconcile`) + Task 1 (EnrichResult gains `post_embed_hash`) + spec "Graph connection structure" + D-91-8/13.

**Recommendation:** None required. Idempotency holds. Add a one-sentence note: "Re-run after fail-fast is safe and is the intended resume mechanism; no explicit `--resume-from` flag is needed (per D-91-8)."

**Finding F-6 (D4 / OQ-91-8 edge — MOVED+CHANGED)**  
The plan notes the deferred OQ-91-8 case (a file that is both moved *and* content-changed appears in both `to_compile` and `to_reconcile`). The lean ("dedupe to the compile path") is reasonable, but it is still an open edge that should be explicitly exercised or logged during the live run.

**Evidence:** Plan Task 3 (the parenthetical about OQ-91-8).

**Recommendation:** During the Joseph-fired live run, deliberately include (or synthesize) one MOVED+CHANGED case if possible, or at minimum add a log line when the dedupe path is taken. This turns the deferred edge into observed behavior rather than an untested assumption.

**Observation O-1 (minor — sidecar/journal ordering clarity)**  
The plan's Task 2 pseudocode has the sidecar/journal write as a comment inside `_commit_source`. Making it an explicit step (even if it is just "accumulate for finalize") would make the D-91-13 boundary and the D1 journaling decision visually clearer in the primary artifact.

---

## What you checked and found sound

- Single shared read-write connection model (spec + plan Task 3) is correctly threaded; read-after-write for context is free and already verified.
- Fail-fast (D-91-8) + two-phase boundary (D-91-13) is respected in the per-source commit helper.
- `detect_orphans` + `kdb-clean orphans` (D-91-4) is correctly deferred to a single `_finalize` pass after the full loop (avoids transient-orphan context pollution).
- `enrich_one` egress change (Task 1) is the minimal required delta to support post-embed hash + in-memory handoff to `compile_source`.
- `build_source_state_update` per-source safety (the "already verified" claim) was re-inspected in source code and holds.
- No hidden batch assumptions in the loop's usage of the four shipped foundations were found.
- Scope discipline: the plan stays within wiring the loop; it does not pull in registry/scanner/Plan 2-4 work.

---

**Guardrail compliance:** This review created exactly one file (`docs/task91-plan5-6-review-grok.md`). No other files were created, modified, moved, or deleted. No code changes or patches were proposed. The review is confined to the four mandated dimensions and the explicitly scoped foundations.

All findings are grounded in the plan text, the spec sections on the orchestrator loop + egress/ingress, the D-91 decision table, and direct inspection of the relevant shipped foundation code (`source_state_update.py`, `ingestor.py`, `enrich.py`).

The review is now available for advisor + panel synthesis before the live run.