# External Panel Review Prompt — Task #91 Plan 1 (`kdb-compile` rebuild)

> **Panel:** Codex · Deepseek · Qwen · Grok · Gemini (agy `gemini-3.5-flash-high`). Joseph fires this same prompt to all 5; each writes ONE review file. Assistant synthesizes by convergence (n/n load-bearing, (n-1)/n strong, 1/n unique catch).
>
> **Scope is deliberately narrow** — see "What is OUT of scope" below. This review exists to fill the two dimensions a same-model (Claude) automated review is weakest at: independent design judgment. Mechanical correctness was already verified separately.

---

## Your role

You are an independent senior architect reviewing an **implementation plan** before it is executed. You bring a perspective the plan's author (Claude) cannot bring: a *different* model's independent judgment, free of the author's blind spots. Be skeptical and specific.

## Artifacts to read (repo root: `/home/ftu/Droidoes/Obsidian-KDB`)

1. **The plan under review:** `docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md`
2. **The design spec it implements:** `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md` — read especially the **"Component: Pass-2 ingress"** section (the `compile_source` input contract + stage-redistribution table) and the **"Component: Orchestrator loop"** section (per-source routing, fail-fast, the connection model) for context on what `compile_source` must compose with.
3. **The ratified decisions:** `docs/task91-kdb-orchestrate-blueprint.md` — the D-91-1..D-91-14 decision table (esp. D-91-8 fail-fast, D-91-12 direct Python API, D-91-13 two-phase failure, D-91-14 delete-via-sidecar).
4. **The code the plan modifies/assembles:** `kdb_compiler/compiler.py` (`compile_one`, `run_compile`, `source_text_for`), `kdb_compiler/types.py`, `kdb_compiler/canonicalize.py`, `kdb_compiler/reconcile.py`, `kdb_compiler/validate_compile_result.py`, `kdb_compiler/patch_applier.py`, `kdb_compiler/graph_context_loader.py`.

## Context (what this plan is and why)

`kdb-orchestrate` (Task #91) is an end-to-end ingestion conductor: `feeder → ingestion (Pass-1 enrich) → compiler (Pass-2) → GraphDB`. The current `kdb-compile` is the *original monolithic* orchestrator (pre-split); it owns its own scan, persists, and graph-syncs. **Plan 1** freezes that monolith as `kdb-old-compile` and extracts a per-source library function **`compile_source(...)`** = the Pass-2 compiler core (spec stages 3→6+8: compile → validate → reconcile → canonicalize → apply-pages), operating on **in-memory inputs** (no disk re-read) and a caller-supplied Kuzu connection. The orchestrator (a later plan) will own scan, the per-source loop, manifest commit, graph-sync, and cleanup.

## The TWO dimensions to review (and ONLY these)

### Dimension A — Spec fidelity (design intent, not signatures)
Does Plan 1 faithfully realize the spec's *intent* for the compiler core?
- Does the `compile_source` contract match the spec's Pass-2 ingress section (in-memory `(source_id, body, keep-frontmatter)` payload; the only graph read is the context-snapshot build; zero disk re-reads)?
- Does the stage redistribution match the spec's table (3→6+8 in the core; 1-2 / 7 / 9 / 10 reserved for the orchestrator)?
- Does any plan step **contradict or omit** a ratified spec/blueprint decision?
- **Scope discipline:** does Plan 1 stay within "the `kdb-compile` rebuild," or does it leak into the pipeline registry / scanner generalization / orchestrator loop / `detect_orphans` work that the spec assigns to *later* plans?
- Is the make-before-break freeze (`kdb-old-compile` retained, not deleted) faithful?

### Dimension B — Architectural risk / hidden design flaws
Beyond mechanical correctness (signatures, file:lines, test-runnability — **already verified, do not re-check**), what *design* risks does `compile_source`-as-specified carry?
- **One-element `cr` assumption:** `compile_source` wraps a single compiled source in a `cr` dict and runs `validate` / `reconcile` / `canonicalize` — functions originally written for a *batch* of compiled_sources. Do any of them carry batch-level or cross-source assumptions (dedup, aggregate invariants, ordering) that are silently wrong on a one-element list?
- **The context-snapshot seam:** `compile_source` builds the snapshot *internally* from the passed `conn`. Should the orchestrator instead build it and pass the snapshot in (so the compiler core does no graph reads at all)? Which seam composes better with the orchestrator's shared read-write connection + per-source read-after-write requirement?
- **The provenance contract:** the plan adds `source_hash` / `source_mtime` params to `compile_source` (the orchestrator owns these — post-embed hash + stat mtime — and they flow into each page's frontmatter via `patch_applier`). Is threading orchestrator-owned provenance into the compiler core the right contract, or a leak of concerns?
- **Error model:** the plan funnels *all* pre-commit failures (compile / validate-gate / canonicalize / apply) into `CompileSourceResult(cr=None, error=...)`. Is collapsing them to one error field right, or should some failure classes stay distinguishable for the orchestrator's D-91-13 case-(a)/(b) handling?
- **Side effects per source:** `compile_one` writes a `resp_stats` record per call; `canonicalize.run` mutates `cr` in place; a failure mid-`compile_source` may leave partial wiki writes. Any of these unsafe under the eventual per-source loop?
- **Composition with Plan 6:** does any design choice here force rework when the orchestrator loop (shared connection, fail-fast, per-source commit, embed-at-commit sequencing) is built on top?

## What is OUT of scope (do NOT spend effort here)
- Function signatures, file:line accuracy, import paths, dataclass field names — **already verified correct**.
- TDD mechanics (will a test fail-then-pass, placeholders, fixture ordering) — **already verified**.
- The pipeline registry, scanner, orchestrator loop, `detect_orphans` — those are *later* plans; only flag them here if Plan 1 wrongly pulls them in (that's a Dimension-A scope finding).

## Output format

Write your review as a SINGLE markdown file (path provided to you when fired). Structure:

1. **Verdict:** one of `proceed` / `proceed-with-changes` / `revise-before-execution`, one sentence why.
2. **Findings** — for each, a block with:
   - **Title:** a short stable label (so reviews can be matched for convergence)
   - **Dimension:** A (spec-fidelity) or B (architectural-risk)
   - **Severity:** critical / high / medium / low
   - **Issue:** what's wrong or risky
   - **Evidence:** spec quote, blueprint decision id, or code reference grounding the claim
   - **Recommendation:** concrete change
3. **What you checked and found sound** (brief — so we know coverage, not just problems).

## Guardrail (MANDATORY)

This is a **READ-ONLY** review. Do **NOT** modify, create, move, or delete ANY file in the repository **except** writing your single review file to the output path you are given. Do not run formatters, do not "fix" code, do not edit the plan or spec. Your entire deliverable is the one review file.
