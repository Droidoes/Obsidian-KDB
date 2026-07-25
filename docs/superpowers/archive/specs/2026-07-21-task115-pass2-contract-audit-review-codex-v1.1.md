# Task #115 — Pass-2 contract audit v1.1: Codex review

**Date:** 2026-07-21  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-audit-findings.md` v1.1  
**Repository anchor:** `main` at `7d8263b`  
**Verdict:** Revise once more before architecture selection

## Executive assessment

v1.1 absorbs the first Codex review well. The factual investigation is now strong,
and the proposed derivation-first direction is consistent with the controller-style
North Star. One further revision is needed because the document leaves superseded
v1.0 claims in its authoritative sections and corrects them only in an appended
absorption section. A few data-flow and provenance statements also need tighter
wording before the findings become the design basis.

## Remaining findings

### F1 — High: v1.1 remains internally contradictory

Sections 1–7 retain superseded claims while §8 corrects them. Examples:

- §1.3 says prompt edits are “invisible” (`lines 47-50`), while §8.1 correctly
  explains that they are visible through the full prompt hash but not attributable
  (`lines 178-181`).
- §3.1 and §3.2 retain the incorrect warning and log-entry consumers
  (`lines 92-104`), while §8.1 corrects both (`lines 168-177`).
- §2 declares aggregate pairing validators and tests moot (`lines 80-86`), while
  §8.3 correctly introduces the LLM-only versus end-to-end scope fork
  (`lines 207-221`).
- §5 still classifies `source_name`, `summary_slug`, and `outgoing_links` as
  “verified consumed (no action)” (`lines 125-133`), while §8.2 identifies all
  three as redundant model output (`lines 183-205`).
- §6 calls the GLM mechanism an open investigation (`lines 135-144`), while §8.6
  upgrades it to a supported explanation (`lines 248-254`).

An absorption appendix is useful history, but it should not be the authoritative
correction layer.

**Disposition:** Produce a consolidated v1.2. Fold every accepted correction into
the primary sections, remove or rewrite the superseded claims, and reduce §8 to a
brief revision changelog.

### F2 — High: “no gate reads the model's value” is technically incorrect

The central semantic conclusion is sound, but the data-flow wording is too absolute.

JSON Schema currently validates:

- optional `concept_slugs` and `article_slugs` when the model emits them; and
- required per-page `outgoing_links`.

On a schema failure, `coerce_slugs_and_propagate` also reads and may rewrite all three
surfaces before revalidation (`compiler/repair.py:160-235`). Consequently, these
model-authored fields can affect validation, coercion, retry, and quarantine even
though Python later replaces their semantic values.

They are therefore not literally unread. They are **non-authoritative semantic
output whose only surviving effect is unnecessary gate and repair burden**.

**Disposition:** Replace formulations such as “read by no gate and no consumer” and
“read by no consumer” with:

> The model-authored field carries no authoritative downstream semantics. Its only
> current effects occur in schema/coercion gates before Python overwrites it with a
> deterministic derivation.

This is both more precise and a stronger removal rationale: the redundant output can
currently fail a source without contributing any trusted data.

### F3 — Medium: provenance omits the code-generated exemplar

The proposed component hashes cover:

1. vault-owned system-prompt text;
2. code-owned `RESPONSE_CONTRACT`;
3. normalized per-source response schema.

They do not cover `prompt_builder.exemplar_response()`. Task #115 will change that
exemplar when fields leave the response. An exemplar-only change would therefore be
unattributable through the proposed static component hashes; it would appear only in
the source-dependent full `prompt_hash` and the manually maintained version string.

**Disposition:** Add one of:

- `pass2_exemplar_sha256`, computed from a canonical exemplar rendered with a fixed
  sentinel `source_name`; or
- `pass2_static_contract_sha256`, computed from every static contract component,
  including the exemplar/template, in addition to any component hashes retained for
  diagnosis.

The existing per-call full `prompt_hash` should remain unchanged.

### F4 — Medium: GLM causality should remain a supported hypothesis

The evidence is strong:

- the summary page retains `page_type`;
- every non-summary page omits it;
- the top-level concept/article lists remain populated and therefore encode the
  missing classifications.

This establishes a plausible redundancy mechanism, not causal proof. The same shape
could arise from a repetitive-object generation defect independent of the lists.

**Disposition:** Describe list-induced omission as a **supported, evidence-backed
hypothesis**. The proposed discriminating test is correct: remove the redundant lists,
keep `page_type` required, re-run the cohort, and add no repair before seeing the
result.

### F5 — Medium: deterministic `summary_slug` needs edge-case requirements

The derivation-first finding is sound, but the future blueprint must pin the exact
mapping from filename to summary slug. At minimum it must specify:

- the slugification function and normalization rules;
- preservation of the `summary-` prefix within the schema's 120-character limit;
- behavior when a filename stem slugifies to no ASCII letters or digits;
- collision behavior after normalization and truncation.

`common.paths.slugify()` truncates its input-derived slug to 120 characters. Naïvely
prefixing that result with `summary-` can produce a 128-character value that violates
`summarySlug.maxLength`. The summary derivation must reserve prefix capacity or define
a separate helper with an explicit contract.

**Disposition:** Carry these requirements into the blueprint and TDD plan before
ratifying top-level `summary_slug` removal.

### F6 — Low: distinguish accepted findings from unratified dispositions

“All 9 accepted” is clear if it means the factual findings were independently
confirmed. Several proposed dispositions still require Joseph's selection:

- LLM-only slug-list removal versus end-to-end deprecation;
- whether all three newly identified redundant fields join Task #115;
- temporary confidence retention versus immediate removal/migration;
- optional audit arrays and removal of empty `related_source_ids` injection;
- the exact provenance shape.

Some v1.1 language reads as decided—for example, “For #115: retain temporarily”—even
though §8.8 still presents the same item as a decision.

**Disposition:** Label all such statements as non-binding reviewer/author leans until
Joseph ratifies them. Reserve “accepted” for verified factual findings.

## Editorial correction

At §8.7, replace:

> Fix only AFTER the provenance gate lands (else invisible edits...)

with:

> Fix only AFTER the provenance gate lands (else the component-level edits remain
> unattributable...).

This keeps the wording consistent with the corrected §8.1 analysis.

## Exit criteria for v1.2

- [ ] Fold §8's accepted corrections into §§1–7 and remove contradictory text.
- [ ] Describe derived fields as semantically non-authoritative but currently
      gate-affecting.
- [ ] Fingerprint the code-generated exemplar or the complete static contract bundle.
- [ ] Keep the GLM mechanism explicitly hypothesis-level until the discriminating
      cohort runs.
- [ ] Carry deterministic summary-slug edge cases into the blueprint requirements.
- [ ] Mark architectural dispositions as leans pending Joseph's selection.
- [ ] Use “unattributable,” not “invisible,” for the current provenance gap.

## Final verdict

Revise once more, primarily by consolidating the document in place. No additional
contract investigation is required before that revision. After these corrections,
the findings will be a sound input to architecture deliberation and the Task #115
decision gate.
