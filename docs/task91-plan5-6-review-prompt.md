# External Panel Review Prompt — Task #91 Plan 5+6 (`kdb-orchestrate` loop)

> **Panel:** Codex · Deepseek · Qwen · Grok · Gemini (agy `gemini-3.5-flash-high`). Same prompt to all 5; each writes ONE review file. Assistant synthesizes by convergence (n/n load-bearing, (n-1)/n strong, 1/n unique).
>
> This is the **capstone integration** — the E2E conductor that wires four already-shipped, already-tested foundations into a per-source loop ending in the first live run. Your independent, model-diverse design judgment is what we want here.

## Your role
Independent senior architect reviewing an implementation plan before execution. Be skeptical and specific; ground every finding in the plan text, the spec, or the actual code.

## Artifacts to read (repo root: `/home/ftu/Droidoes/Obsidian-KDB`)
1. **Plan under review:** `docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md`
2. **Spec:** `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md` — "Component: Orchestrator loop", "Pass-2 ingress", "Pass-1 egress" (embed-during-enrich + post-embed hash), the per-source routing branches, fail-fast (D-91-8/13).
3. **Ratified decisions:** `docs/task91-kdb-orchestrate-blueprint.md` (D-91-1..14).
4. **The four SHIPPED foundations the loop composes** (already built + tested — review how the loop *uses* them, not the foundations themselves):
   - `kdb_compiler/compiler.py::compile_source` (produce-don't-write; returns `cr`)
   - `graphdb_kdb/ingestor.py::apply_compile_result(detect_orphans=…)` + `detect_orphans()`
   - `kdb_compiler/pipeline_registry.py`
   - `kdb_compiler/kdb_scan.py::scan_scope` (pipeline-scoped)
   - plus `kdb_compiler/source_state_update.py::build_source_state_update`, `patch_applier.apply`, `kdb_clean.py` (reap_orphans_from_graph + apply_cleanup), `ingestion/enrich.py::enrich_one`.

## Context
`kdb-orchestrate` runs: registry → select pipeline → open ONE shared read-write `GraphDB` connection → `scan_scope` → per-source loop → finalize. NEW/CHANGED signal sources go enrich→gate→`compile_source`→commit (apply-wiki → manifest → sidecar → graph-sync with `detect_orphans=False`); noise → `metadata_only`; DELETE/MOVED → reconcile. Finalize runs ONE `detect_orphans()` pass → `kdb-clean orphans` → `last_orchestrate.json`. Single-user, infrequent workload.

## ALREADY VERIFIED — do NOT re-litigate (flag only if you find these claims FALSE)
- **`build_source_state_update` is per-source-safe** — `apply_scan_reconciliation` iterates only `last_scan`'s files + reconcile ops; it does NOT diff the full prior keyset, so a single-source commit doesn't mass-tombstone others.
- **Loop routes off `scan.to_compile` / `scan.to_reconcile`** (not raw `files`) — pure-MOVED transfers SUPPORTS without recompiling.
- **Sandbox isolation:** the test sandbox dir is its own `vault_root` (wiki/state/graph/prompt all under it); production untouched.
- **Accepted trade-offs (settled, not open):** produce-don't-write; cross-source wiki merge = last-writer-wins (graph authoritative; `kdb-audit`/#93 reconciles); embed-during-enrich + self-healing edge; deferred orphan-marking; fail-fast.

## Focus your review on these dimensions

### D1 — Per-source journaling / replayability (the PRIMARY open fork)
The monolith writes ONE run journal + one batch `compile_result.json` sidecar; `graphdb-kdb rebuild` replays journals. The per-source loop graph-syncs + commits the manifest **per source** but the plan's lean is to **accumulate per-source `cr`s and write the journal + sidecar once at finalize** (reuses existing machinery). The residual gap: a crash *mid-loop before finalize* leaves committed-but-not-journaled sources (live graph has them; only lost if the graph is *also* lost — a double fault). **Is accumulate-at-finalize the right call, or should the loop append a per-source journal entry?** Weigh the crash-window vs the machinery cost. This is the call we most want diverse judgment on.

### D2 — Per-source commit ordering + D-91-13 correctness
Commit sequence: apply-wiki(8) → manifest-write(BOUNDARY) → sidecar → graph-sync(`detect_orphans=False`). Is the case-(a)/(b) boundary correct? Partial-write windows (wiki written, manifest fails; or manifest written, graph-sync fails)? Does graph-sync-as-last-step correctly land case-(b) (manifest committed, graph stale → rebuild)?

### D3 — Integration correctness + batch-assumption traps
This bug-class has bitten us twice (orphan Phase-4 marking; canonicalize cross-source merge). **Beyond the verified `build_source_state_update`, does any foundation carry a hidden batch/cross-source assumption that breaks when driven per-source in a loop?** Specifically: `apply_compile_result` Phase-1 source-upsert + Phase-3 (does a 1-source `cr` + 1-file `scan_dict` behave correctly?); `patch_applier.apply` per-source `source_refs` (the Plan-1 cross-source finding — is it handled consistently with the accepted last-writer-wins trade-off?). Also: does the loop correctly compose the foundations' contracts (types, return shapes)?

### D4 — Fail-fast / resume / idempotency
Per-source commit + fail-fast (re-run = resume). With embed-during-enrich + post-embed-hash stored in the manifest: is re-run genuinely idempotent (a committed source → UNCHANGED → skipped; a mid-run-failed source → re-enriched + overwritten)? Any non-idempotent step? Read-after-write across the loop on the single connection (does source N+1's context see source N's committed mutations)?

## Output format
Write a SINGLE markdown file (path provided when fired):
1. **Verdict:** `proceed` / `proceed-with-changes` / `revise-before-execution` + one sentence.
2. **Findings** — each: **Title** (short, stable) · **Dimension** (D1–D4 or "other") · **Severity** (critical/high/medium/low) · **Issue** · **Evidence** (plan line / spec quote / code ref) · **Recommendation**.
3. **What you checked and found sound** (brief).

## Guardrail (MANDATORY)
READ-ONLY review. Do NOT modify, create, move, or delete ANY repo file **except** writing your single review file to the output path you are given. No code edits, no "fixes". Your entire deliverable is the one review file.
