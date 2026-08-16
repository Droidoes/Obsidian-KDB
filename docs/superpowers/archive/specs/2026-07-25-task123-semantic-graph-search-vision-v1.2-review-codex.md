# #123 Semantic Graph Search Vision v1.2 — Codex Re-review

**Date:** 2026-07-25
**Reviewer:** GPT-5.6 / Codex
**Artifact:** [`2026-07-25-task123-semantic-graph-search-vision.md`](2026-07-25-task123-semantic-graph-search-vision.md)
**Review scope:** Closure of the v1.1 Codex findings, D10 re-vote,
missing-domain proposal, and readiness for vision re-ratification

## Verdict

**APPROVE v1.2 for vision ratification.**

All three Important findings from my v1.1 review are substantively resolved:

1. P6 persists exact historical selector evidence rather than relying on a
   hash alone.
2. P10 recognizes wiki excerpts as untrusted prompt data and establishes the
   required isolation and adversarial-test boundary.
3. P7/D10 define one SearchSnapshot spanning graph identity and deterministic
   wiki evidence, while the engine is bound to the read-only graph identity
   authority used to build it.

The four remaining v1.1 findings are also correctly folded. No load-bearing
issue remains at the vision level. The clarifications in this review belong in
the spec or blueprint and do not block ratification.

This vote approves the vision and D10. It does not close the later North Star,
spec, blueprint, TDD-plan, Proceed, or implementation gates.

## Finding-closure check

### F1 — artifact, not hash alone

**Status: RESOLVED.**

P6 now requires a retained search artifact containing:

- normalized query payload;
- ordered search-space identities and metadata;
- exact excerpt bytes;
- excerpt-policy version;
- selector prompt version/hash;
- model route and identity.

The context record stores ordered T2 selection plus an artifact reference and
hash. Default replay uses the recorded selection; opt-in selector evaluation
uses the archived artifact rather than mutable current wiki content. This
meets the original audit and replay requirement.

### F2 — untrusted body evidence

**Status: RESOLVED.**

P10 explicitly treats candidate titles and excerpts as data, never
instructions. It requires:

- data-only structured encoding;
- stable task/evidence boundaries;
- system-level instruction precedence;
- escaping/serialization rules;
- adversarial prompt-like candidate fixtures;
- both structural and relevance assertions.

This is the correct right-sized response: an explicit trust boundary in the
prompt and tests, not a speculative security subsystem.

### F3 — graph plus wiki SearchSnapshot

**Status: RESOLVED.**

D10.2 defines SearchSnapshot as:

- graph identity reference;
- ordered eligible canonical entities;
- deterministic evidence projection;
- projection-policy version;
- content hash;
- retained P6 artifact.

The capability section also binds the engine to the same read-only graph
instance from which the snapshot was built. P7 correctly changes the held-out
truth target from a fixed graph snapshot to a fixed SearchSnapshot.

### F4 — FTS before fat-text hydration

**Status: RESOLVED.**

P4 and the scale flow now place FTS identity prefiltering before wiki-body
hydration. The vision accurately states that Kuzu FTS indexes thin
`Entity.slug/title` properties, not filesystem bodies, and requires measured
candidate recall before a top-k cap becomes load-bearing.

### F5 — missing body means partial evidence

**Status: RESOLVED.**

D10.3 defines:

- `complete | partial` evidence status;
- body-evidence coverage;
- per-caller acceptance policy;
- fail-closed aggregate evaluation below a ratified threshold;
- title-only fallback as an integrity-degraded observation.

This matches the existing meaning of `ContentNotFoundError` as graph/disk
drift rather than ordinary absence.

### F6 — composable selection provenance

**Status: RESOLVED.**

The output now records:

```text
selected_by: llm
identity_match_annotations:
  exact_matchable: bool
  alias_matchable: bool
```

This correctly reflects that all happy-path hits pass through the LLM while
still measuring the incremental value beyond deterministic identity matching.

### F7 — missing-domain behavior

**Status: RESOLVED, proposal APPROVED.**

The proposed adapter rule is coherent with P3:

- empty domain cluster → empty space and correct abstention;
- missing/null domain → empty space, `domain_missing` telemetry, and
  abstention;
- never a silent whole-graph fallback for context-build.

I vote **APPROVE** on this missing-domain rule for Joseph's ratification.

## D10 re-vote

**APPROVE D10 as revised.**

Wiki-page bodies are the correct v1 evidence source for graph entities:

- prose is owned by the corresponding entity page;
- `get_body` provides an established frontmatter-stripped read boundary;
- graph identity and filesystem content authority remain explicitly separate;
- exact excerpt bytes are retained for audit/replay;
- missing bodies produce typed partial evidence;
- candidate prose is isolated as untrusted data;
- SearchSnapshot binds identities, evidence, policy, and content.

Excluding `Source.summary` from v1 entity evidence is coherent. It avoids
mixing source-level description with entity-owned page prose while a later
Source-return projection remains explicitly deferred.

## Non-blocking spec and blueprint clarifications

### 1. Keep artifact construction and storage separable

The consumer-neutral signature does not include `run_id` or `state_root`, and
MCP/CLI requests are not necessarily part of an orchestrator run. The
blueprint should preserve this division:

```text
graph search execution
  → returns result + complete audit artifact payload

artifact sink / pass-1.5 adapter
  → persists payload and returns artifact reference
```

Alternatively, inject a `SearchArtifactSink` into the engine. In either shape,
graph search owns canonical artifact construction; consumer policy owns where
and whether it is persisted. Do not couple the general semantic function to
orchestrator filesystem paths.

### 2. Distinguish historical selector evaluation from live graph search

Operational graph search must re-verify identities against its bound live
read-only Kuzu instance. Historical opt-in re-call is different: it evaluates
the selector against an archived SearchSnapshot whose entities may later have
changed status or identity.

The blueprint should name these modes separately:

- **live search:** live-graph identity verification required;
- **record replay:** return persisted historical selection, no LLM call;
- **historical selector re-call:** validate against the archived candidate
  manifest for evaluation, never present the result as current graph search.

This prevents current graph mutation from corrupting historical selector
experiments.

### 3. Define degraded-mode fallback ordering

P1's deterministic exact/alias fallback is sound and avoids losing trivial T2
hits on API failure. Because the LLM supplies no order in degraded mode, the
spec must define a deterministic order, for example:

1. pass-1 expression order;
2. exact before alias for the same expression;
3. canonical slug as final tie-break.

The context record should identify the fallback mode so its T2 ordering is not
misread as semantic ranking.

### 4. Archive or immutably resolve selector prompt bytes

P6 retains selector prompt version/hash. Historical re-call also needs the
actual historical prompt bytes. The blueprint should either:

- store those bytes with the artifact; or
- use a content-addressed/versioned prompt loader whose historical bytes are
  immutable and resolvable by the recorded hash.

A hash alone is sufficient for verification only when the corresponding bytes
remain available.

### 5. Preserve two completeness denominators

P3 correctly treats domain-empty abstention as selector-ineligible while
retaining the all-request domain-empty outcome. The KPI design should pin both:

- selector-eligible relevance quality;
- all-context-request search availability.

Neither denominator should be substituted for the other.

### 6. Treat vault-scale sizing as a pre-implementation gate

The §6 arithmetic shows that whole-domain fat-text payloads may exceed current
context limits at the planned vault scale. The spec must therefore decide,
before implementation:

- excerpt policy and exact token budget;
- maximum unfiltered identity count;
- whether FTS prefiltering is required in v1;
- required candidate recall before a cap activates;
- behavior when the candidate population still exceeds budget.

This is an observed first-workload constraint, not speculative scale
engineering.

## Architecture-integrity assessment

The revised vision preserves the project's load-bearing principles:

- graph identity remains Kuzu-owned;
- wiki prose remains separately content-owned;
- search is read-only with respect to product state;
- LLM output is strict, closed-world semantic selection;
- Python owns all identity, validation, persistence coordination, and
  telemetry;
- domain scoping belongs to the context adapter;
- T1 and T3 remain structural;
- the general capability is not coupled to Pass-1.5;
- search evidence is reproducible even though selection is stochastic;
- relevance is predeclared against held-out truth before tuning;
- no ontology mutation or parked metacognition work enters #123.

P1's deterministic selector-failure fallback is a useful availability
improvement and does not recreate the old multiple-production-mode problem
because `LEGACY` and `LAYERED` retire.

## Readiness

v1.2 is ready for:

1. Joseph's re-ratification of D10 and the missing-domain rule;
2. the North Star milestone update;
3. spec work, including the truth-set program and vault-scale sizing;
4. blueprint comparison of package placement and selector model;
5. a TDD-first implementation plan.

No implementation should begin until those documentation and Proceed gates
are closed in the order required by `AGENTS.md`.

## Verification performed

- Re-read vision v1.2 in full.
- Compared every v1.1 Codex finding against its v1.2 fold.
- Rechecked the Round-1 synthesis decisions D1–D8.
- Rechecked `common.wiki_io.get_body` authority and missing-content behavior.
- Rechecked `kdb_graph.schema.Entity`: entity bodies remain outside Kuzu.
- Rechecked `compiler.context_record.ContextRecordV1`: selector/search
  artifacts require intentional schema evolution or an artifact reference.
- Rechecked current context-loader tier construction: ordered semantic T2 and
  deterministic degraded-mode T2 need distinct, explicit integration paths.

