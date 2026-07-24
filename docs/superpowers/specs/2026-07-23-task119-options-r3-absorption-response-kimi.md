# Task #119 options doc — Codex R3 absorption response (Kimi)

> **Erratum (2026-07-23, per Codex R4 F2):** the "The deepest finding (F2)" section below carried the ambiguity-policy contradiction — it said ambiguous references must be *rejected* and, in the same breath, that unsafe tokens may *preserve dangling behavior, nonfatal*. Resolved in the options doc **v1.2** §4 as a single reference policy: preserve without authority (nonfatal); reject on attempted-rewrite ambiguity; under form (b) + links-to-summary-unnecessary the summary-propagation case disappears. This note is superseded by options doc v1.2.

**Date:** 2026-07-23 · **Author:** Kimi (for Joseph + Codex)
**Pairs with:** `2026-07-23-task119-normalization-boundary-architecture-options-review-codex.md` (Codex R3) → absorbed into `2026-07-23-task119-normalization-boundary-architecture-options.md` **v1.1**
**Context:** Codex R3 verdict was **REVISE BEFORE OPTION PICK**. All four findings were verified against code before absorption (receiving-code-review discipline — same as the R1/R2 rounds).

## Verdict acknowledged

Codex endorsed Joseph's challenge outright: *"The boundary move answers Joseph's challenge correctly: Python should own the mechanical summary identity, and strictness should protect the canonical product rather than punish model punctuation."*

## Verification results (all four findings: accurate)

- **F1 (High) — reject taxonomy incomplete.** Accurate. Today the structural classes (malformed root, invalid `pages`, non-object entries, missing/wrong-type fields) are caught only by the strict schema gate (`compiler/compiler.py:408-411`); any pre-schema normalizer would see unvalidated structure. v1.1 §4 now carries the full typed taxonomy (structural insufficiency + semantic reject classes).
- **F2 (High) — body-wikilink targets ungated.** Accurate on all citations (schema body = opaque string; `semantic_check` = summary-only at `validate_source_response.py:58-85`; intake silently skips missing targets at `kdb_graph/intake.py:345-373`). **Bonus catch while verifying:** the intake docstring's "dangling links are a validator catch upstream" is stale post-#115 — no such gate exists; `dangling_link_rate` is a benchmark KPI, not a gate. Flagged in §8; not touched (out of scope).
- **F3 (Medium) — form (a)/(b) couples option costs.** Accurate. The canonical schema requires `slug` on every page (`compiled_source_response.schema.json:37-42`), so slugless summaries are unvalidatable against it — Option 1 under form (b) needs a handwritten proposal contract and loses its reversibility. Also: `coerce_slugs_and_propagate` mutates `parsed_json` in place today, so pre-mutation values survive only in `raw_response_text`. v1.1 §5 is now a 2×3 form-coupled matrix; raw-proposal preservation is a cross-cutting requirement (§4).
- **F4 (Low) — wording.** Both accurate: governing rule is *proposed*, not ratified (Joseph ratified the #115 disposition; rule ratification is a #119 blueprint item); `main` has moved to `4d60e6d` (docs-only delta over the verified code anchor `f8c9ad8`).

## The deepest finding (F2)

It splits two things v1.0 fused:

1. **Stamping** the derived summary identity on the unique summary page — *always* safe (role + provenance authority).
2. **Propagating** that identity into body wikilinks — *conditionally* safe. A raw token that also names another response page, an EXISTING CONTEXT entry, or an alias-ledger target is ambiguous → reject, never silently rewrite.

Stamping must not depend on propagation safety. The blueprint either validates every remapped target against the normalized page set + authoritative context, or explicitly preserves today's dangling-link behavior for unsafe tokens (KPI-visible, never fatal).

## The emerging architecture (Codex's conditional recommendation)

**Option 2 + form (b) + fail-closed alias handling:**

- discriminated proposal schema — summary: `page_type`/`title`/`body`; concept/article: + `slug`;
- typed bridge stamps the Python-derived summary slug;
- unchanged canonical schema validates the bridge's output (plus the exact pre-persistence summary invariant + post-canonicalization invariant — all three now guard Python's derivation and the alias ledger, never the model's raw slug form).

Form (b) aligns with Joseph's lean: don't require an ignored model field just to manufacture telemetry. Option 1 remains materially simpler **only** under form (a) — so the form decision gates the option decision.

## Two open points for Joseph (flagged for the pick)

1. **Form (b) side effect:** if the model no longer emits the summary slug, bodies can't link *to* the summary by slug. Blueprint candidates: declare links-to-summary unnecessary, or a reserved proposal-local reference token the bridge resolves deterministically. (Canonical summary-slug prompt injection stays a #115-ratified non-goal.)
2. **Retry policy change (§6.4 of v1.1):** the summary slug's raw value *never* triggers a retry — removing the wasted-retry half of the Phase-5 failure, not just the quarantine. Retries survive only for model-correctable classes (malformed/incomplete proposal, zero/multiple summaries, response-local collision, ambiguous model-authored reference); deterministic Python/state failures never retry.

## State of play

**This note is the historical R3 absorption response (v1.1-era)** — its reference-policy discussion was superseded the same day (see the erratum above). The current artifact of record is the options doc **v1.2+**, which resolved R4's two contradictions and carries the converged Phase-1 package: **Option 2 + form (b) + no links-to-current-summary + fail-closed alias handling** — Codex R5 verdict **GO** (minor documentation corrections only). Awaiting Joseph's confirmation of that package → then the task-ledger + North Star update (the ratified Phase-1 gate) and the blueprint phase.
