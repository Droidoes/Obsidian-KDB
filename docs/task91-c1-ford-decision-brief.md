# Decision Brief for Panel Recommendation — Task #91 C1 + F-ord

> **Panel:** Codex · Deepseek · Qwen · Grok · Gemini (agy). Same brief to all 5; each writes ONE file.
> **This is NOT a plan re-review** — it is a focused request for your **recommendation** on two *coupled* design decisions the Plan 5+6 panel surfaced. We want: your pick per decision, the reasoning, the failure modes you'd worry about, and any option we missed. Pick the option that's *right*, not the one we lean toward.

## Background
`kdb-orchestrate` runs a **per-source loop** on ONE shared read-write Kuzu (`GraphDB`) connection: per source → enrich → `compile_source` (produce `cr`) → commit (apply-wiki + manifest + graph-sync via `apply_compile_result(cr, …, detect_orphans=False)`) → finalize (one `detect_orphans()` pass → `kdb-clean orphans` → run summary). Per-source graph-sync is what gives **read-after-write**: source N+1's context snapshot sees source N's just-committed entities/supports (empirically verified on Kuzu 0.11.3). Single-user, infrequent workload. The four foundations (`compile_source`, `apply_compile_result`+`detect_orphans`, `pipeline_registry`, `scan_scope`) are shipped + tested.

Read for context: `docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md`, `docs/task91-plan5-6-review-synthesis.md`, spec `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md` (Orchestrator loop, Pass-1 egress), `docs/task91-kdb-orchestrate-blueprint.md` (esp. **D-91-13** two-phase failure model), and code: `graphdb_kdb/ingestor.py` (`apply_compile_result`, `_replace_outgoing_links`, `detect_orphans`), `graphdb_kdb/rebuilder.py::rebuild`.

## VERIFIED FACTS (do not re-derive; build on these)
- **C1 is real:** `_replace_outgoing_links` (ingestor.py:326-333) wires `LINKS_TO` via `MATCH (a),(b) CREATE …` — it **silently skips** when target `b` doesn't exist yet. In the per-source loop, Source A's link to Entity B (defined by a *later* source) is skipped and never re-created.
- **C1 breaks live≡replay (not just "degraded context"):** `rebuild` (rebuilder.py:151-152) replays each run's **whole `compile_result` in one `apply_compile_result` call** → batch upserts ALL entities, *then* wires edges → cross-source edges come out **complete**. So the rebuilt graph is complete while the live per-source graph is **incomplete** → the live graph **diverges from its own replay**, violating the D50 live≡replay invariant the #73 Phase-G verifier enforces.
- **Kuzu transaction rollback is clean** (probed): a `BEGIN…ROLLBACK` leaves no leak. `apply_compile_result` wraps its mutation in `BEGIN/COMMIT/ROLLBACK` (ingestor.py:53-107) and is **idempotent per source** (drop+recreate SUPPORTS/links/entities).
- **Read-after-write requires per-source graph-sync** — deferring ALL graph mutation to one batch apply at finalize would defeat it (source N+1 wouldn't see source N's entities → variant proliferation). That option is off the table.

---

## DECISION 1 — C1: how to make cross-source `LINKS_TO` complete (live = batch replay)?

The tension: per-source graph-sync wires a source's edges before later sources' entities exist. The fix must make the **live** graph match what **batch replay** produces.

- **Option (b′) — Defer link-wiring to finalize, batch-wire.** Per-source `apply_compile_result` upserts entities + SUPPORTS only (a `wire_links=False` flag, mirroring the existing `detect_orphans=False` deferral); a finalize batch pass wires ALL `LINKS_TO` over the accumulated `cr` with every entity present. **live≡replay by construction.** Dangling links skipped identically to batch (validator's job preserved). Cost: cross-source `LINKS_TO` are not visible in **T3** (neighbor expansion) for sources compiled *mid-loop* — T1 (source-supported) and T2 (Pass-1 keys) still anchor per-source; the full graph (incl. T3 edges) is complete at finalize.
- **Option (a) — Stub-upsert.** When wiring A→B and B is absent, create an inactive stub Entity B so the edge is created immediately; B's real source promotes the stub to active later. Per-source edges immediate (T3 sees them mid-loop). Risks: a *genuinely dangling* link (B never defined by any source) creates a permanent inactive stub → live≠replay (batch skips dangling) **unless** a finalize stub-GC drops un-promoted stubs; also masks the dangling-link signal the validator is meant to surface.
- **Other?** If you see a cleaner option, propose it.

**Recommend one (or a better option), with reasoning + the failure mode you'd most worry about.**

---

## DECISION 2 — F-ord: per-source commit ordering (this would revise ratified D-91-13)

D-91-13 (Joseph-ratified, originally a Codex critical catch) is a two-phase failure model with the **manifest-write as the commit boundary**: pre-commit failures = case-(a) (not committed); post-manifest graph-sync failure = case-(b) (manifest+wiki committed, graph stale → manual `graphdb-kdb rebuild`).

- **Option α — keep D-91-13 (manifest-first):** apply-wiki → **manifest(boundary)** → per-source sidecar → graph-sync. Graph-sync failure = case-(b); recoverable via `rebuild` because the sidecar was written before the sync. Conservative; keeps the ratified decision; case-(b) stays a real (rare) state needing manual remediation.
- **Option β — graph-sync-first:** apply-wiki → **graph-sync (Kuzu txn)** → [on success] manifest + sidecar. A graph-sync failure **rolls back cleanly** → manifest never written → case-(a) self-heal (next run re-detects via hash mismatch, re-compiles; `apply_compile_result` idempotency makes re-sync safe). **Eliminates case-(b)** — collapses the failure taxonomy to "all pre-commit failures self-heal." Residual: a crash *between* graph-sync and sidecar-write, *plus* graph loss, leaves one source's mutation un-replayable (a bounded one-source double-fault — the same class already accepted for journaling). **β revises a ratified, Codex-critical decision.**

**Recommend α or β, with reasoning.** Specifically: does β honor D-91-13's *intent* (sidecar-as-replayable-authority) better or worse than α? Is revising the ratified decision justified given the single-rw-connection + verified Kuzu rollback (which post-date D-91-13)? What breaks under β that α handles?

---

## They interact
C1's fix and F-ord both live in the per-source commit sequence. Please also state the **coherent combined commit sequence** you'd recommend (the exact ordering of: apply-wiki, graph-sync[entities+supports], manifest, sidecar, and the finalize link-wire pass).

## Output format
Single markdown file (path provided): **Decision 1 pick + reasoning**, **Decision 2 pick + reasoning**, **recommended combined commit sequence**, **anything we missed**. Be decisive — we want a recommendation, not just analysis.

## Guardrail (MANDATORY)
READ-ONLY. Do NOT modify/create/delete ANY repo file except your single review file at the path you are given.
