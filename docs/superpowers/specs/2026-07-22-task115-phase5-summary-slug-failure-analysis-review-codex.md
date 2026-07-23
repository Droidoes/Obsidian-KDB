# Task #115 Phase-5 summary-slug failure analysis — Codex review

**Date:** 2026-07-22

**Reviewer:** Codex

**Reviewed document:** `docs/superpowers/specs/2026-07-22-task115-phase5-summary-slug-failure-analysis.md`

**Verdict:** Revise before ratification — the root issue is broader than the
summary slug

Kimi correctly concludes that rejecting and retrying the entire payload over
`gemini31` versus `gemini3-1` is the wrong disposition. However,
derive-and-stamp for this one field is only an instance of the required fix.
The architectural defect is that the raw LLM proposal is being judged against
Python's canonical storage representation before Python has interpreted and
normalized it.

The governing rule should be:

> **Reject ambiguity, not harmless representational differences. If Python
> can deterministically map an LLM proposal to exactly one valid meaning,
> normalize it and continue. Reject only when there is no valid
> interpretation, more than one plausible interpretation, information loss,
> or a collision.**

Canonical exactness remains mandatory, but it belongs at the output of
Python's normalization boundary—not at the raw model-response boundary.

## Blocking findings

### F1 — Phase 5 failed its declared acceptance gate

The plan requires comparison-cohort quarantine/retry/recovery KPIs to remain
stable:

- `docs/superpowers/plans/2026-07-21-task115-pass2-contract-revision-blueprint.md:381-391`
- `docs/superpowers/specs/2026-07-21-task115-pass2-contract-audit-findings.md:175-189`

The result changed from zero quarantines to one quarantine plus a wasted retry
in each model run. These are not “explained canonical-collision graph deltas.”
Therefore:

- The cohort is valid diagnostic evidence.
- It is not a successful Phase-5 sign-off.
- “Close #115, then fix #119” would waive the ratified gate after it caught a
  real design defect.

This should be resolved as a #115 design amendment, followed by a new clean
anchor and cohort re-fire. A separate #119 is appropriate only if Joseph
explicitly accepts the failed gate as temporary production behavior.

### F2 — The proposal identifies a field-level symptom, not the system-level defect

Kimi frames the defect as model authorship of a Python-derivable summary slug.
That is true but incomplete. The broader problem is the absence of a clear
boundary between:

1. what the model proposes in semantically recognizable but potentially
   non-canonical form; and
2. what Python permits into the canonical internal and persisted model.

Today the same strict schema both describes the model's raw response and
stands in for the canonical representation. For example, it requires `slug`
on every raw page before Python can apply source identity or page-role context
(`compiler/schemas/compiled_source_response.schema.json:33-45`). This makes a
representational deviation look like a semantic failure.

Keeping summary `slug` required in the raw response and merely overwriting
valid-but-different strings does not eliminate the class:

- A missing `slug` still fails schema validation.
- A non-string slug still fails.
- A malformed slug still fails before Python can normalize it.
- Equivalent representations in other fields remain exposed to the same
  reject/retry/quarantine behavior.

The revision must establish a normalization boundary, not add a one-off
exception for two punctuation examples.

### F3 — Define a proposal contract and a canonical contract

The design needs two logical contracts, whether or not they are implemented as
two physical JSON Schema files:

#### Proposal contract

The proposal contract determines whether Python has enough structure and
semantic evidence to interpret the response. It may accept harmless
representational variation where a field-specific policy can resolve one
meaning deterministically.

#### Canonical contract

The canonical contract is exact. It is the only shape allowed to reach
canonicalization, persistence, the wiki, the manifest, the run journal, and
the graph.

The processing order should become:

```text
model response
  → recover JSON
  → parse proposal
  → structural sufficiency checks
  → deterministic normalization and identity resolution
  → strict canonical schema and semantic validation
  → canonicalization
  → post-canonicalization invariant validation
  → write
```

The current `schema → semantic check → retry` ordering validates raw
representation too early (`compiler/compiler.py:309-475`).

### F4 — “Close enough” must mean uniquely resolvable, not globally fuzzy

Python should not use a general edit-distance threshold, punctuation-blind
comparison, or another probabilistic model to decide equivalence. Those
approaches could silently merge genuinely different identities.

Instead, each model-authored field needs a deterministic resolution policy
based on its meaning and available authority:

| Proposal variation | Python disposition |
|---|---|
| Case, whitespace, punctuation, or path decoration with one canonical interpretation | Normalize |
| Known enum alias with one registered target | Map to the canonical enum |
| Losslessly coercible representation | Coerce |
| Repeated identical values | Deduplicate |
| Non-canonical reference with one authoritative target | Resolve |
| Two plausible canonical targets | Reject as ambiguous |
| Conflicting content or missing semantic information | Reject |
| Normalization that would collide with another distinct object | Reject |

For the observed summary cases, Python does not need to decide that two
strings “look similar.” The unique `page_type == "summary"` page, the current
compile unit, and `source_id` jointly establish the page's identity. Python
therefore has exactly one valid summary slug regardless of punctuation in the
model's proposed representation.

This distinction generalizes beyond summary slugs: use role, provenance,
registries, known context, and structural invariants to resolve meaning.
String similarity alone is not authority.

### F5 — Move strict equality after normalization; do not delete it

Kimi's proposed “count-check only” gate is incomplete. Exact equality should
disappear only from validation of the raw proposal. The normalized object must
still contain exactly one summary whose slug equals
`expected_summary_slug(source_id)`.

The existing post-canonicalization check remains load-bearing
(`compiler/compiler.py:717-736`). Kimi's claim that it becomes “trivially
true” is incorrect: the alias canonicalizer can attempt to rename or merge the
normalized summary and currently rejects that explicitly
(`compiler/canonicalize.py:424-457`).

The revised design must decide whether system-resolved summary identities:

- bypass alias resolution entirely, or
- remain fail-closed against any alias-ledger operation.

Body-link resolution must follow the same identity policy.

### F6 — Body links need deterministic reference resolution, not prose rewriting

If the model's summary representation is normalized from an emitted value to
the canonical value, Python may propagate that mapping only where the old
value is unambiguously a reference to that page.

Safe propagation means:

- operate only on parsed wikilink target tokens;
- preserve display aliases and heading suffixes;
- leave prose and code spans byte-identical;
- require one old target → one canonical target;
- reject a mapping that collides with another page or has multiple plausible
  targets;
- validate all resulting links against the normalized page set and known
  context.

Prompt-injecting the canonical summary slug remains a possible architecture
when the model genuinely needs it to author links, but it should not be the
default remedy for a normalization defect. It would reverse #115's current
“never prompt-injected” decision
(`docs/superpowers/plans/2026-07-21-task115-pass2-contract-revision-blueprint.md:393-397`)
and therefore requires explicit ratification.

## Architectural options for the normalization boundary

The revised proposal should present these as distinct choices and receive
Joseph's selection before implementation.

### Option 1 — In-place proposal normalizer

After JSON parsing, a dedicated stage applies field-specific, deterministic
normalizers to the proposal and then sends the resulting object through the
existing strict schema and semantic gates.

- **Implementation cost:** lowest.
- **Operational cost:** negligible.
- **Compounding effect:** risks becoming a collection of ad hoc mutations
  unless every rule has an explicit authority, ambiguity policy, and test.
- **Reversibility:** high; the stage can later be replaced without changing
  persisted artifacts.

### Option 2 — Explicit proposal schema plus canonical schema

Introduce a tolerant proposal schema for the raw model boundary and retain a
strict canonical schema for the normalized object. A typed normalization step
is the only bridge between them.

- **Implementation cost:** moderate; two schemas and their compatibility must
  be maintained.
- **Operational cost:** negligible.
- **Compounding effect:** makes the trust boundary explicit and prevents raw
  permissiveness from leaking into persistence.
- **Reversibility:** moderate to high; both sides are versioned contracts.

### Option 3 — Typed intent decoder

Parse raw JSON into proposal-specific types and resolve them into canonical
domain types through field-owned adapters. The raw JSON shape and the
persisted `CompiledSource` shape are deliberately different.

- **Implementation cost:** highest and potentially disproportionate for
  #115.
- **Operational cost:** negligible.
- **Compounding effect:** strongest long-term ownership and type guarantees;
  easiest to extend without conflating raw and canonical data.
- **Reversibility:** moderate because it changes more integration boundaries.

## Accuracy corrections to Kimi's analysis

Kimi should correct three statements:

- **“Deletes the entire source's content” is inaccurate.** A compile failure
  prevents that run's candidate update from being committed and marks the
  source `error_compile` (`orchestrator/kdb_orchestrate.py:717-772`). In a
  fresh cohort graph the source is absent; in an existing KB previously
  committed content is not automatically deleted.
- **The slug has more than uniqueness value.** It is the wiki filename/path,
  graph entity identity, wikilink target, manifest identity, and replay
  identity. It is mechanical but operationally load-bearing.
- **“~3% if generalized” is not yet an estimated population rate.** The
  measured observation is 1/36, or 2.8%, in each run. Cross-model and retry
  recurrence demonstrates systematic risk, but not its general prevalence.

## Telemetry and prompt feedback

The raw proposal should remain observable so normalization does not conceal
model behavior. Record at least:

- the normalization rule applied;
- the raw value when safely capturable;
- the canonical value;
- whether the decision used role, provenance, registry, or another authority.

This evidence belongs in telemetry or the archived raw response—not in the
canonical product contract. A field should not remain required in model output
solely to manufacture a quality metric.

Do not automatically turn the two summary punctuation examples into global
concept-slug rules. Concept identity is semantic; punctuation, version dots,
apostrophes, `C++`, and `C#` can carry meaning. A concept slug may be
normalized or resolved only when an authoritative context yields one target.
Otherwise Python must preserve it or reject an actual ambiguity rather than
guess.

## Required Pass-2 audit

The summary failure is evidence for a contract-wide audit, not permission for
unbounded fuzzy repair. For each current Pass-2 field, the amended blueprint
should record:

| Question | Required answer |
|---|---|
| Who owns the meaning? | Model, Python, or shared |
| What semantic information does the field carry? | Explicit statement |
| Which proposal variations are harmless? | Enumerated, evidence-backed forms |
| What is the canonical form? | One deterministic representation |
| What authority proves equivalence? | Role, source, registry, context, or none |
| When is normalization forbidden? | Ambiguity, collision, loss, or missing meaning |
| What telemetry records the decision? | Raw/canonical values plus rule |

The audit need not implement every imaginable coercion in #115. It must ensure
that every existing rejection gate is classified correctly as either:

- a semantic/structural failure that must remain fail-closed; or
- a representational difference Python can normalize deterministically.

## Recommended disposition

Revise the proposal as follows:

1. Amend #115 with the general rule: reject ambiguity, not harmless
   representation differences.
2. Update the North Star before code. It currently says the summary slug is
   fully model-authored (`docs/CODEBASE_OVERVIEW.md:15`) and does not define
   the proposal-versus-canonical boundary.
3. Present the normalization-boundary options above and receive Joseph's
   selection.
4. Define and test the proposal contract, canonical contract, and ordering
   between them.
5. Audit every current Pass-2 field and gate using the ownership/resolution
   table above.
6. Treat the unique summary's source and role—not string similarity—as the
   authority for its canonical identity.
7. Keep exact canonical invariants before persistence and after
   canonicalization.
8. Resolve alias-ledger and body-link behavior under the same deterministic
   identity policy.
9. Add both observed sources as regression fixtures, plus ambiguity and
   collision negatives.
10. Establish a new clean comparison anchor and re-fire both complete
    cohorts.
11. Close #115 only after quarantine/retry/recovery KPIs satisfy the original
    gate.

**Final disposition:** accept Kimi's evidence and the conclusion that these
payloads should not have been rejected. Revise the root cause from
“model-authored summary slug” to “canonical representation enforced before
deterministic semantic normalization,” and do not close #115 until that design
is ratified, implemented, and cohort-validated.
