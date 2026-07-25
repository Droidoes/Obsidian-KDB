# Task #115 — Pass-2 contract audit v1.2: Codex review

**Date:** 2026-07-21  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-audit-findings.md` v1.2  
**Repository anchor:** `main` at `7d8263b`  
**Verdict:** Proceed after a minor v1.3 revision

## Executive assessment

v1.2 resolves the previous consolidation problems and is close to
architecture-ready. The investigation itself is complete. One load-bearing taxonomy
claim still overstates current behavior, and the proposed GLM experiment conflicts
with the bundled implementation lean. The remaining items are contract and
experimental-design precision rather than requests for additional broad research.

## Findings

### F1 — High: the central “semantically dead” category overstates current behavior

Lines 20–29 say Python overwrites or ignores all five categories before consumers
read them. That is true for:

- `concept_slugs` / `article_slugs`;
- `outgoing_links`;
- `source_name`.

It is not currently true for:

- `summary_slug`, which is copied directly into `CompiledSource`, then consumed by
  page writing and the manifest; and
- `status`, which is copied directly from the model into `PageIntent`
  (`compiler/compiler.py:466-483`) and persisted downstream.

Both fields have zero useful model discretion and should transfer to deterministic
Python ownership, but they are presently authoritative model fields—not dead model
output.

**Disposition:** Split the taxonomy:

1. **Currently non-authoritative model output:** slug lists, `outgoing_links`, and
   `source_name`.
2. **Currently authoritative but deterministically code-ownable:** `summary_slug`
   and `status`.

The shared higher-level conclusion remains valid: none of these fields earns model
authorship.

### F2 — High: the GLM test and bundled-change lean conflict methodologically

Section 6 calls slug-list removal a “discriminating” test of the GLM `page_type`
hypothesis. Section 9 simultaneously leans toward removing every redundant field in
one contract revision followed by one cohort run.

If GLM improves after that bundled change, the result cannot attribute the improvement
specifically to removing the parallel type encoding. Other simultaneous changes—such
as removing `outgoing_links`, `source_name`, `summary_slug`, and `status`, plus prompt
cleanup—may also affect structured-output reliability.

**Required choice:**

1. **Causal resolution:** run a small GLM A/B on the four affected sources with only
   `concept_slugs` / `article_slugs` removed, then perform the bundled cleanup and its
   final cohort validation.
2. **End-state validation only:** perform one bundled contract revision and cohort,
   but stop describing the result as a discriminating test of the list-redundancy
   mechanism.

Either path is sound; they answer different questions.

### F3 — Medium: define the complete static provenance bundle

Section 2 correctly adds exemplar coverage, but “complete static bundle” should be
defined to include every model-facing static instruction, not only the four currently
named components.

At minimum the bundle should cover:

- vault-owned system-prompt text;
- code-owned `RESPONSE_CONTRACT`;
- normalized response-schema text;
- canonical exemplar rendered with a fixed sentinel source name;
- `_PASS1_META_BLOCK_TEMPLATE` instructions;
- static headings, labels, separators, and other user-prompt scaffolding in
  `build_prompt()`.

Otherwise a change to the Pass-1 metadata instructions or user-prompt framing remains
unattributable at the component level even though it can affect model behavior.

**Disposition:** Define a deterministic serialization order and hash the entire static
contract bundle. Component hashes may remain alongside it for diagnosis.

### F4 — Medium: the status banner contradicts the decided items

Lines 4–5 say that no architectural dispositions are ratified, while §1.5 and §8
explicitly identify `status` removal and jargon removal as Joseph-decided.

**Suggested wording:**

> Status removal and jargon removal are ratified. All other architectural
> dispositions are non-binding leans pending Joseph's §9 decision gate.

### F5 — Medium: complete Python ownership of `summary_slug`

The blueprint should derive `expected_summary_slug` before the model call and include
that exact value in the prompt. Otherwise Python would own validation while still
asking the model to independently perform the filename normalization and truncation.

The model should only:

- identify exactly one summary page through `page_type: "summary"`; and
- use the supplied `expected_summary_slug` as that page's slug.

Python then validates that exact equality and derives the aggregate `summary_slug`
from the validated page. This makes the length, non-ASCII, and collision policies
operational before generation rather than merely post-response checks.

### F6 — Low: tighten the schema/coercion wording

JSON Schema validates all candidate fields, but `coerce_slugs_and_propagate` traverses
only slug-bearing fields. It does not read or rewrite `source_name` or `status`.

**Disposition:** Replace the collective wording at lines 22–24 with the explicit
distinction:

- every candidate field can affect schema validation;
- the slug-bearing subset additionally participates in slug coercion and
  revalidation.

## Exit criteria for v1.3

- [ ] Split currently non-authoritative fields from authoritative-but-code-ownable
      fields.
- [ ] Choose causal GLM A/B testing or bundled end-state validation, and describe the
      evidence claim accordingly.
- [ ] Define the complete static contract bundle covered by provenance hashing.
- [ ] Correct the status banner to recognize the two Joseph-ratified decisions.
- [ ] Make pre-call derivation and prompt injection of `expected_summary_slug` a
      blueprint requirement.
- [ ] Distinguish universal schema effects from slug-subset coercion effects.

## Final verdict

Proceed after a minor v1.3 revision. No additional broad contract investigation is
required. The remaining load-bearing correction is accurately separating fields that
are dead today from fields that are currently authoritative but should transfer to
Python ownership. The GLM validation goal must also choose between causal attribution
and bundled final-contract validation.
