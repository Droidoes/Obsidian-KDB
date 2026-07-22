# Task #115 — Pass-2 contract revision (Phases 1–2) — Gate-2 CODE Review Prompt (Codex)

> Sent **verbatim** to Codex CLI. Repo root: `/home/ftu/Droidoes/Obsidian-KDB`, branch `feat/115-pass2-contract`, base commit `e9ca323` (Gate 0). The change under review is the **uncommitted working-tree diff** on top of `e9ca323` — 56 tracked files (+1275/−3277) plus 2 new source files. Write your review to `docs/superpowers/plans/2026-07-22-task115-pass2-contract-gate2-code-review-codex.md`.

---

You are a senior staff engineer doing a **pre-commit CODE review** at a phase gate. The design is already ratified — your job is to verify the **implementation** matches it, is correct, and has no regressions or scope creep. Be skeptical and specific; cite `file:line`. A sharp catch here is still cheap — nothing is committed.

## HARD GUARDRAIL — read first, non-negotiable
- **Read-only.** Do NOT modify, create, rename, or delete ANY file **except** the single output file named above. Write your entire review there and nowhere else.
- No state-changing git (`add`/`commit`/`checkout`/etc.), no `pip install`, no formatters.
- You MAY run tests: `.venv/bin/python -m pytest` (use the venv python — bare `pytest` resolves to a broken system install). Full suite currently claimed green: **1360 passed / 1 live-skip / 1 deselected**.

## Ground truth (ratified design — the diff must match THIS, not your own taste)
- Spec v1.6: `docs/superpowers/specs/2026-07-21-task115-pass2-contract-audit-findings.md`
- Blueprint v1.10: `docs/superpowers/plans/2026-07-21-task115-pass2-contract-revision-blueprint.md` — 12 tasks: T1.1–T1.7 (Phase 1) + T2.1–T2.5 (Phase 2). Read §"Task list" first, then check the diff task-by-task.

## What the change is (intended contract revision)
Old Pass-2 response contract carried 6 fields the compiler could derive or the graph should own (`summary_slug`, `outgoing_links`, `status`, `confidence`, slug lists, log entries). New contract: the LLM emits **only** `pages` (slug/page_type/title/body) + optional `compilation_notes`. Everything else is derived deterministically post-hoc. Repair stage (reconcile_slug_lists/reconcile_body_links) is **deleted whole**; summary slug is **derived** from `source_id`; graph edges are derived from page **bodies** at intake. Backward compat is **dual-mode**: legacy-shape journals/fixtures (with `summary_slug` etc.) must still validate, rebuild, and replay.

## How to see the diff
- Tracked changes: `git diff` (against index; working tree == index is NOT guaranteed — review the working tree: `git diff HEAD` is safest).
- New files (review them too; `git diff` won't show them): `compiler/summary_slug.py`, `compiler/tests/test_summary_slug.py`.
- **Excluded from review:** `docs/session-handoff-2026-07-22-evening.md` (session bookkeeping, not part of the gate).

## Pressure-test these (the load-bearing decisions)
1. **Contract cutover coherence.** `compiler/schemas/compiled_source_response.schema.json` (pages required; six fields gone), the rewritten `compiler/prompts/KDB-Compiler-System-Prompt.md`, and `compiler/prompt_builder.py` (RESPONSE_CONTRACT, no-arg 4-field `exemplar_response()`, `PASS2_PROMPT_VERSION = "3.0.0"`) — do these three agree **exactly** on field names, required-ness, and shapes? Any field the prompt still asks for but the schema forbids (or vice versa)?
2. **Summary-slug derivation equivalence.** `compiler/summary_slug.py:expected_summary_slug` must be **algorithm-identical** to `scripts/cohort_slug_collision_guard.py:53` (the guard that stamped the baseline cohort at Gate 0 — drift invalidates the Phase-5 comparison cohort). Does `compiler/tests/test_summary_slug.py` pin equivalence behaviorally (edge cases: >112-char stems, slugify edge cases, non-ASCII), or just assert one happy path?
3. **Semantic gate + fail-closed routing.** `compiler/validate_source_response.py:semantic_check(payload, *, expected_summary_slug=...)` — exactly one summary page + derived-slug match. In `compiler/compiler.py`, an underivable stem must route to stage `"validate"` **before any model call** (attempts=0, zero tokens) on BOTH the inner record and the outer result; a semantic-fail after the call maps inner `validate` → outer `validate`. Verify no path lets a summary-less or mis-slugged payload through.
4. **Repair deletion is clean.** `compiler/repair.py` is stripped to `coerce_slugs_and_propagate` (page slug + body wikilinks only). Grep for dangling imports/callers of the removed reconcile functions across the repo (incl. `tools/`, `orchestrator/`, tests). Any survivor that still "fixes" LLM output beyond slug coercion?
5. **Canonicalize rewrite.** `compiler/canonicalize.py`: `CanonicalizationError` (@213) raised when a merge group contains a summary page and on alias-singleton summary renames; `outgoing_links` UNION pass and old pass 3 deleted; remaps are body-only. `compiler/compiler.py` catches `CanonicalizationError` and runs a post-canon per-source summary re-check. Can a summary page still be silently merged/renamed into a wrong slug?
6. **Dual-mode aggregate validation.** `compiler/validate_compile_result.py:_check_source` — LEGACY mode (record has `summary_slug` → old referential checks) vs NEW mode (derived exact match; new finding `summary_slug_mismatch` in `HARD_ZERO_FINDING_TYPES`). Can a mixed record spoof the mode check? Is mode detection per-source (not global)?
7. **types.py field drops + fail-closed helper.** `common/types.py`: PageIntent drops status/outgoing_links/confidence; CompiledSource drops summary_slug/lists; CompileResult → `compilation_notes` (LogEntry gone); `summary_page()` (@457) must raise unless exactly one summary page exists. Consumers (`compiler/page_writer.py`, `orchestrator/manifest_writer.py`) use the dual-mode `cs.get("summary_slug") or summary_page(cs)["slug"]` — can that expression mask a zero-summary or two-summary record in NEW mode?
8. **Graph-owned edge derivation + layering.** `kdb_graph/intake.py:body_wikilink_slugs` (@43) is a **mirror** of the compiler's (kdb_graph must not import compiler — layering invariant guarded by `tools/tests/test_package_boundaries.py`); a drift-guard test pins them equal. `_replace_outgoing_links` prefers the legacy `outgoing_links` key when present, else derives from body. Confirm: no `import compiler`/`from compiler` under `kdb_graph/`; edge sets identical for a legacy record vs its derived equivalent.
9. **Mixed-shape rebuild + replay (T2.5).** `kdb_graph/tests/test_rebuilder.py` has a journal-pair test: legacy-shape + new-shape compiled records rebuilt together. `tools/replay.py` + `tests/fixtures/response_replay/` gained source_id + derived-slug semantic gating; `compiler/tests/fixtures/pass2_recovery/` — 18 fixtures migrated (noise preserved verbatim), `19.txt` kept as `legacy_negative`. Do the fixtures actually exercise BOTH modes?
10. **Scope discipline.** This diff must be Phases 1–2 ONLY. Phase 3 (confidence deprecation in `kdb_graph` snapshot v7), Phase 4 (parity corpus), Phase 5 (comparison cohort) are LATER — flag any leakage. Conversely, flag any of the 12 tasks not fully implemented. `scripts/cohort_slug_collision_guard.py` and `common/measurement.py` must be UNTOUCHED (they're stamped against the baseline cohort / owned by merged #117 on main) — confirm they're absent from the diff.
11. **Suite-delta sanity.** Gate 0 suite was 1386; now 1360 = −55 retired pairing/reconcile tests +29 new contract tests. Spot-check that retired tests map to deleted functionality (not silently dropped coverage) and the +29 new ones cover the new gates (summary-derive, validate-stage routing, dual-mode validate, drift guard, mixed rebuild).

## Output — write ONLY to `docs/superpowers/plans/2026-07-22-task115-pass2-contract-gate2-code-review-codex.md`
1. **Verdict:** `GO` (commit Gate 2 as-is) / `GO-WITH-CHANGES` (commit after specific fixes) / `REWORK` (a load-bearing decision is wrongly implemented).
2. **Findings**, each: `[Severity: Critical | High | Medium | Low]` · `file:line` · the flaw · why it matters · concrete suggested change.
3. Group under: **(a) contract coherence (schema/prompt/builder)**, **(b) correctness of new gates (derive/semantic/canonicalize)**, **(c) dual-mode & backward compat**, **(d) layering & cross-package**, **(e) scope & test coverage**. If a group is empty, say "none".
4. **One-paragraph bottom line:** is this diff safe to commit as Gate 2, and what (if anything) must change first.
