# Task #119 options R3 absorption response — Codex review

**Date:** 2026-07-23  
**Reviewer:** Codex  
**Reviewed response:** `docs/superpowers/specs/2026-07-23-task119-options-r3-absorption-response-kimi.md`  
**Artifact checked:** `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-architecture-options.md` v1.1

**Verdict:** **REVISE BEFORE OPTION PICK.** R3 correctly absorbs most prior
feedback, but two high-severity contradictions remain.

## Findings

### F1 [High] — Form `(a)` violates the governing constraint

The design says the raw summary-slug value must never cause a retry or
rejection (`architecture-options.md:71`), yet form `(a)` keeps `slug`
**required** in the proposal contract (`architecture-options.md:82`).

A missing or non-string summary slug would therefore still fail proposal
validation—the exact unhandled class identified in Codex R1.

Resolve this before presenting form `(a)` as viable:

- make the summary slug optional and unconstrained telemetry that can never
  reject; or
- remove form `(a)` from consideration and select form `(b)`.

Given Joseph's constraint and the ownership model, form `(b)` remains the
coherent choice.

### F2 [High] — Ambiguous body-reference policy contradicts itself

The design says an ambiguous raw summary reference must be rejected
(`architecture-options.md:74`), then says unsafe tokens may preserve today's
dangling-link behavior and remain nonfatal (`architecture-options.md:75`).
Kimi's absorption response repeats the same contradiction at lines 23–25.

Choose one policy.

Under form `(b)`, the simplest resolution is:

- declare links to the current summary unnecessary;
- do not propagate a raw summary slug because none exists; and
- continue allowing the summary body to link outward to concepts, as the
  current prompt already expects.

If links to the current summary are genuinely required, use a reserved
proposal-local token outside the canonical slug namespace. The bridge can
rewrite that token unambiguously without consulting similarity or context.

### F3 [Medium] — The “complete” structural taxonomy remains incomplete

The taxonomy at `architecture-options.md:68-70` still omits:

- missing or wrong-type concept/article `slug`;
- invalid `page_type` enum values;
- empty or overlength `title`;
- empty `body`; and
- invalid `compilation_notes`.

Avoid maintaining the schema-error inventory manually. Define structural
insufficiency as **any proposal-schema violation**, with typed categories for
root, pages, page fields, and notes. Define semantic rejects separately.

### F4 [Medium] — The canonical schema cannot remain literally unchanged

Option 2 calls the current artifact an “unchanged canonical schema”
(`architecture-options.md:95`). Its validation shape can remain unchanged,
but the artifact currently identifies itself as the per-call model-output
contract:

- `compiler/schemas/compiled_source_response.schema.json:3-5`
- `compiler/prompt_builder.py:36,84-92`

Under Option 2:

- a new proposal schema becomes the prompt-facing model contract;
- the current validation shape becomes the canonical schema; and
- its title, description, `$id`, loader ownership, CLI routing, and tests must
  reflect that new role.

Use the phrase **“unchanged canonical validation shape,”** not “unchanged
schema.”

## Absorption status

Correctly absorbed:

- form-coupled 2×3 comparison;
- raw-proposal preservation;
- fail-closed alias handling;
- #106 movement into the bridge;
- model-correctable versus deterministic retry policy;
- explicit #115 decision deltas; and
- ratification and code-anchor corrections.

Still not fully absorbed:

- R3 F1, because form `(a)` retains a raw-boundary failure mode; and
- R3 F2, because ambiguous reference handling has two conflicting
  dispositions.

## Final disposition

Once F1 and F2 are resolved, **Option 2 + form `(b)` + no links to the current
summary + fail-closed alias handling** is ready for Joseph's confirmation and
North-Star ratification.
