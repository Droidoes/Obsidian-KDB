# Task #119 normalization-boundary architecture options — Codex review

**Date:** 2026-07-23  
**Reviewer:** Codex  
**Reviewed document:** `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-architecture-options.md`

**Verdict:** **REVISE BEFORE OPTION PICK.** The boundary move is
architecturally correct: raw summary-slug equality should disappear while
exact canonical invariants remain. Four issues should be resolved before
Joseph selects an implementation option.

## Findings

### F1 [High] — The proposal-boundary rejection taxonomy is incomplete

Section 4 says raw proposals fail only for zero or multiple summaries, a
rename collision, or information loss.

Because normalization now runs before the strict schema, the boundary must
also safely reject malformed roots, invalid `pages` collections, non-object
page entries, and missing or wrong-type `page_type`, `title`, or `body`
fields. Option 1 otherwise requires an undocumented handwritten proposal
validator.

Define the complete structural-sufficiency contract and its typed rejection
classes before comparing options. “Information loss” is too broad to serve as
that contract.

Relevant current boundary:

- `compiler/compiler.py:309-475`
- `compiler/schemas/compiled_source_response.schema.json:33-50`

### F2 [High] — Body-wikilink targets are not currently gated

The audit describes body-wikilink targets as model-authored and gated, but the
current pipeline does not enforce target existence:

- The response schema treats `body` as an arbitrary nonempty string:
  `compiler/schemas/compiled_source_response.schema.json:46-50`.
- `semantic_check` validates only summary count and exact summary slug:
  `compiler/validate_source_response.py:58-85`.
- Graph intake silently skips a target when no corresponding Entity exists:
  `kdb_graph/intake.py:345-373`.

The design must separate two concerns:

1. Assigning the Python-derived summary identity is always safe.
2. Rewriting body references from the model's raw summary slug to that
   identity is not always safe.

If the raw slug also names another response page, an EXISTING CONTEXT entry,
or an alias-ledger target, a body token may be ambiguous. That
known-context/reference collision is a missing reject class.

The blueprint must either:

- validate remapped targets against the normalized page set plus authoritative
  context; or
- explicitly avoid propagation and preserve the current dangling-link
  behavior.

Summary identity stamping must not depend on whether reference propagation is
safe.

### F3 [Medium] — Proposal form and implementation option are coupled

Forms `(a)` and `(b)` materially change the implementation-option tradeoffs:

- Option 1 with form `(b)` needs a handwritten structural contract before the
  existing schema, so it is not merely “one module.”
- Deleting Option 1's normalizer would break form `(b)`, because summary
  proposals would no longer carry slugs. Its stated reversibility therefore
  applies mainly to form `(a)`.
- Form `(b)` eliminates `summary_slug_deviation`; telemetry must instead
  record a Python derivation decision with no raw slug.
- Option 2 naturally supports form `(b)` through a discriminated proposal
  schema while retaining the current canonical schema.

Either select the proposal form first or provide a 2×3 comparison matrix. The
present implementation-cost and reversibility ratings are not form-neutral.

The design must also preserve the raw parsed proposal separately. An in-place
normalizer must not erase the model evidence that normalization telemetry is
supposed to expose.

### F4 [Low] — Ratification and code-anchor wording are inaccurate

The document is explicitly unratified, but §4 calls the governing rule
“ratified.” The v1.2 seed also says the #119 design remains unratified. Use
“proposed governing rule” unless Joseph separately ratified that rule.

The current-state section says `main @ f8c9ad8`; current `main` is `4d60e6d`.
The intervening commit is documentation-only, so the code analysis remains
valid. Describe `f8c9ad8` as the verified code anchor rather than current
`main`.

## Responses to the five design questions

### 1. Does the boundary move preserve the load-bearing strict invariant?

**Yes**, provided the normalized object must pass:

1. the strict canonical schema;
2. the exact pre-persistence summary invariant; and
3. the existing post-canonicalization invariant.

The raw exact-slug check is unnecessary. The canonical-side checks then guard
Python's derivation and the alias ledger rather than probabilistic model
formatting.

### 2. Is “never fail on the summary slug's value” safe?

**Yes for assigning the summary's canonical identity.** The value can be
absent, malformed, or different without invalidating the model-authored
title/body/role.

It is **not sufficient authority for automatic body-reference rewriting**.
Structural insufficiency and ambiguous reference mappings remain legitimate
failures.

Additional reject classes to make explicit:

- malformed proposal structure or missing semantic content;
- expected canonical summary slug colliding with another non-summary page in
  the response;
- an ambiguous raw-slug body reference that could denote another response
  page or authoritative context entry;
- an alias-ledger operation targeting the system-owned summary identity; and
- failure of the normalized object to satisfy the canonical contract.

### 3. Form `(a)` ignored-and-stamped or form `(b)` slug removed?

**Recommendation: form `(b)`.**

Remove `slug` from the summary proposal shape and derive it in Python. Do not
require an ignored model field solely to manufacture telemetry.

Use a discriminated proposal schema:

- summary proposal: `page_type`, `title`, `body`;
- concept/article proposal: `slug`, `page_type`, `title`, `body`.

The bridge stamps the expected summary slug before validating against the
unchanged canonical page contract.

Consequences that must be explicit:

- revise the system prompt, response-contract block, exemplar, and checklist;
- bump the Pass-2 prompt version and preserve the loaded-text SHA;
- record `summary_identity_derived` telemetry rather than
  `summary_slug_deviation`; and
- decide whether links *to* the current summary are unnecessary or require a
  separate proposal-local reference mechanism. Do not reintroduce canonical
  summary-slug prompt injection implicitly.

### 4. Which implementation option is proportionate?

**Conditional recommendation: Option 2 — explicit proposal schema, existing
strict canonical schema, and a typed bridge.**

It directly represents the missing trust boundary without Option 3's parallel
domain-type hierarchy. It is proportionate even for the four-field contract
because:

- the proposal and canonical shapes genuinely differ under form `(b)`;
- malformed raw JSON is rejected before normalization code operates on it;
- every normalization decision has one typed result surface; and
- raw permissiveness cannot leak into canonical consumers.

Option 1 is only materially simpler if form `(a)` is retained and the proposal
remains structurally close to the canonical shape. Option 3 remains
disproportionate for the audited surface.

### 5. Does the challenge reopen more of #115 than the model-authored-slug clause?

**Yes, but only contract mechanics entailed by changing ownership:**

- the uniform four-field raw page shape;
- the Pass-2 system prompt, response-contract block, exemplar, and checklist;
- prompt version and SHA provenance;
- validator ordering and failure classification;
- #106 slug-coercion placement; and
- parsed-response and normalization telemetry.

The canonical `CompiledSource`, page writer, graph intake, manifest, run
journal, replay, and wiki contracts need not change if the bridge restores the
current canonical page shape.

Record this as an explicit #115 decision-delta list rather than saying only
the D-115 slug clause changes.

## Recommended resolutions for the surviving open questions

### Alias-ledger policy

Keep system-owned summary identities **fail-closed against alias-ledger
operations**. Bypassing the ledger would conceal stale or hostile mappings.
The existing summary rename/merge guards should continue to surface such
state as a canonicalization failure.

### #106 slug coercion

Absorb the safe #106 coercion rules into the proposal-to-canonical bridge.
Do not retain them as a post-canonical-schema-failure rung; doing so would
reintroduce normalization after rejection. Preserve the parity corpus and
collision-refusal behavior.

### Retry policy

Retry once only for failures the model can plausibly correct:

- malformed or structurally incomplete proposal;
- zero or multiple summary pages;
- response-local duplicate/collision involving model-authored identities; or
- an ambiguous model-authored reference that a fresh response could avoid.

Do not retry deterministic Python or state failures:

- underivable expected summary slug (already pre-call);
- normalization implementation invariant failure;
- canonical-schema failure after a successful typed bridge;
- alias-ledger cycle or attempted summary-identity operation; or
- cross-source reservation/lifecycle conflict owned by #116.

The summary slug's raw value must never trigger a retry.

## Final disposition

The boundary move answers Joseph's challenge correctly: Python should own the
mechanical summary identity, and strictness should protect the canonical
product rather than punish model punctuation.

Resolve F1–F3 before the option pick. With those corrections, **Option 2 +
form `(b)` + fail-closed alias handling** is the proportionate architecture
for the audited contract surface.
