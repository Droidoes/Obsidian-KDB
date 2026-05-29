# Task #91 C1 + F-ord Decision Brief Review — Grok Build

**Reviewer:** Grok Build (CLI, code-grounded)  
**Date:** 2026-05-29  
**Artifact reviewed:** `docs/task91-c1-ford-decision-brief.md` (the focused decision brief)  
**Primary context:**  
- Plan 5+6: `docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md`  
- Panel synthesis (Plan 5+6): `docs/task91-plan5-6-review-synthesis.md`  
- Design spec: `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md` (orchestrator loop + per-source commit)  
- Ratified decisions: `docs/task91-kdb-orchestrate-blueprint.md` (D-91-8, D-91-13)  
- Code evidence: `graphdb_kdb/ingestor.py:_replace_outgoing_links`, `graphdb_kdb/rebuilder.py:rebuild`, `apply_compile_result` behavior, single read-write connection model

This review is strictly read-only per the fire-prompt guardrail. Exactly one file created. No other repository changes of any kind.

---

## Verdict

**C1 recommendation: (a) stub-upsert** (with lightweight finalize stub-GC safety net).  
**F-ord recommendation: β (graph-sync first, manifest+sidecar only on success)** — accept the revision to D-91-13.  

**One-sentence why:** Per-source graph-sync (required for read-after-write and correct T3 context for later sources in the same run) makes batch-style edge wiring impossible during the loop; stub-upsert preserves the core liveness property with minimal blast radius, while graph-sync-first + rollback eliminates the "committed-but-graph-stale" state entirely and is the cleaner engineering outcome given the now-verified single read-write connection + clean Kuzu rollback behavior.

**Coherent combined commit sequence (recommended):**
1. apply-wiki (stage 8)
2. graph-sync via `apply_compile_result` (with stub-upsert for any missing LINKS_TO targets)
3. [only on success] manifest write (durable per-source boundary)
4. per-source sidecar/journal entry (replay payload)
5. (finalize, after full successful loop) batch link-rewire cleanup for any remaining un-promoted stubs + single `detect_orphans()` + `kdb-clean orphans` + run summary

---

## Findings

**Finding F-1 (C1 — core defect, Dimension: architectural risk)**  
`_replace_outgoing_links` (ingestor.py:326-333) uses a `MATCH (a:Entity {slug: $a}), (b:Entity {slug: $b}) CREATE ...` pattern. When `b` does not yet exist (because its defining source is later in the per-source loop), the CREATE is silently skipped and the edge is never recreated. Batch replay (rebuilder) does all upserts first, then wires edges → complete cross-source LINKS_TO. Result: live graph ≠ its own replay, violating the D50 live≡replay invariant that the #73 Phase-G verifier enforces.

**Evidence:** Code at `graphdb_kdb/ingestor.py:326-333` ("The MATCH-with-two-patterns form silently skips when target doesn't exist"), rebuilder.py `rebuild` (full `apply_compile_result` per journal, all upserts before edges), Plan 5+6 synthesis (Gemini F-1, only 1/5 caught it), spec "live graph mutations must be visible to later sources."

**Recommendation:** Adopt (a) stub-upsert as the primary fix. When wiring A→B and B is absent, upsert a minimal inactive stub Entity B (`status='inactive'`, `title=''`, etc.), then create the edge. Later real source promotes it to active via normal upsert. Inactive stubs are excluded from context (`_load_active_entities` already filters `status='active'`). Add a cheap finalize GC pass that drops any still-inactive stubs whose canonical source never appeared (or let the next rebuild naturally skip them). This keeps per-source mutations visible to the rest of the run (T3 works) while remaining reversible and low-risk.

**Finding F-2 (C1 vs (b′) — T3 degradation during run)**  
Deferring all LINKS_TO wiring to a finalize batch-rewire pass (option b′) guarantees live≡replay for edges "by construction," but it means any source whose T3 expansion depends on entities defined by a later source in the same run will see incomplete neighbors until finalize. T1 (SUPPORTS) and T2 (structured keys) still work, but T3 — the "graph discovery" tier — is degraded mid-run.

**Evidence:** Spec "T3 = 1/2-hop neighbors of T1∪T2", Plan 5+6 context loader usage, the entire rationale for the per-source loop + single read-write connection (source N+1 must see N's mutations).

**Recommendation:** (b′) is acceptable only if we are willing to accept weaker context for Pass-2 during long runs. Given that the whole point of the per-source architecture was to give later sources better context, (a) stub-upsert is the better fit for v1 correctness. Use (b′) only as a fallback if stub-upsert proves problematic in the live run.

**Finding F-3 (F-ord / β — simplification of failure model)**  
β (graph-sync first, manifest+sidecar only on success) turns a graph-sync failure into a clean rollback. Because `apply_compile_result` is per-source idempotent (drop+recreate SUPPORTS + LINKS_TO + entities), a later re-run safely re-applies. This eliminates the entire "committed-but-graph-stale → manual `graphdb-kdb rebuild`" state (D-91-13 case b). The only residual is a crash between successful graph-sync and sidecar write + simultaneous graph loss — the same bounded one-source double-fault class already accepted for the per-source journaling decision.

**Evidence:** Plan 5+6 synthesis (Gemini F-2), spec "Graph connection structure" + Kuzu probe results (single rw conn + clean rollback), D-91-13 text, per-source idempotency of `apply_compile_result`.

**Recommendation:** Accept β. It is the cleaner engineering outcome given the new evidence (single read-write connection + verified clean rollback). The revision to ratified D-91-13 is justified; document it explicitly as an evolution based on runtime data that did not exist when D-91-13 was written.

**Finding F-4 (Interaction of C1 + F-ord on the commit sequence)**  
Both decisions live in the same per-source commit window. Choosing (a) stub-upsert for C1 + β for F-ord produces a coherent sequence (see Verdict) that:
- Gives later sources full context including cross-source edges (via stubs).
- Makes graph-sync failures self-healing.
- Preserves a clear durable boundary (manifest write).
- Keeps per-source sidecar for replayability.

**Evidence:** All of the above + Plan 5+6 Task 2 commit sequence + D-91-13 two-phase boundary.

**Recommendation:** Use the combined sequence stated in the Verdict. It is the only ordering that simultaneously solves the C1 completeness problem, takes advantage of the new rollback capability, and respects the per-source sidecar convergence from the Plan 5+6 panel.

**Observation O-1 (minor — finalize stub-GC hygiene)**  
If we adopt stub-upsert, we should also add (or explicitly plan) a finalize pass that cleans up any still-inactive stubs whose real source never materialized in the run. This prevents slow accumulation of ghost stubs across many runs. Low cost, high hygiene.

---

## What you checked and found sound

- The per-source loop + single read-write connection model is correctly motivated and already empirically grounded (Kuzu 0.11.3 probe in the spec).
- The silent-skip behavior in `_replace_outgoing_links` is real and directly produces the live-vs-replay divergence.
- Per-source idempotency of `apply_compile_result` (drop+recreate) makes β safe.
- The Plan 5+6 panel convergence on per-source sidecar + the Gemini-only catch of C1 are both respected.
- D-91-8 fail-fast and the overall two-phase failure philosophy remain intact under the recommended sequence.

---

**Guardrail compliance:** This review created exactly one file (`docs/task91-c1-ford-decision-brief-review-grok.md`). No other files were created, modified, moved, or deleted. No code, plans, specs, or blueprints were touched. The review is strictly read-only and confined to the two decisions plus the required coherent sequence.

All positions are grounded in the decision brief, the Plan 5+6 documents, the spec, the D-91 decisions, and direct code inspection of the critical paths (`_replace_outgoing_links`, rebuilder, `apply_compile_result`).

The review is now available for advisor + Joseph deliberation.