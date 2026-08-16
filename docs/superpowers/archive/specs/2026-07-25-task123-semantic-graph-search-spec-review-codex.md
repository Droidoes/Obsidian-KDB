# #123 Semantic Graph Search Spec v0.1 — Codex Review

**Date:** 2026-07-25  
**Reviewer:** GPT-5.6 / Codex  
**Artifact:** [`2026-07-25-task123-semantic-graph-search-spec.md`](2026-07-25-task123-semantic-graph-search-spec.md)  
**Review scope:** Contract completeness, truth-set integrity, vault-scale
sizing, replay/audit semantics, two-stage scale architecture, and SD-1–SD-6

## Verdict

**REVISE — DISAPPROVE v0.1 as currently written.**

The capability contract, caller-owned scoping, pass-1.5 integration point,
ordered T2 handoff, missing-domain behavior, deterministic fallback ordering,
untrusted-evidence boundary, and three replay modes are sound.

Several load-bearing claims are not yet true, however. In particular, the
vault-sizing baseline conflicts with the selected evaluation corpus, the
SearchSnapshot is neither durable nor rebuildable as claimed, one proposed
abstention answer is factually wrong, and the recommended two-stage design is
not represented by the artifact or evidence-status contracts.

This vote does not approve the blueprint or close the later TDD, Proceed,
implementation, or commit gates.

## Load-bearing findings

### F1 — The vault-sizing baseline conflicts with the selected corpus

**Severity: Important**

Section 7 projects from approximately 62 entities across 36 sources. The
selected Gemini cold-run bundle actually contains:

- 29 compiled sources;
- 168 page emissions;
- 163 unique eligible canonical entities;
- 116 unique concepts;
- 29 unique summaries;
- 18 unique articles.

The selected SearchSnapshot therefore yields approximately 5.6 unique
entities per compiled source, not 1.7. Even if all 36 scanned corpus sources
are used as the denominator, the observed value is approximately 4.5, still
well above the stated baseline.

This invalidates the current 2,900-entity vault projection and the claim that
the all-title first stage fits comfortably. SD-3, SD-4, and SD-5 should not be
ratified from the current arithmetic.

**Required resolution:** recompute:

1. total and per-domain eligible identities from the chosen snapshot;
2. entity/source ratios using explicitly defined denominators;
3. projected vault totals and largest-domain distributions;
4. exact serialized Stage-1 and Stage-2 token counts using candidate selector
   model tokenizers;
5. fixed prompt overhead, output allowance, and provider safety margin.

The switch threshold should be based on measured serialized input tokens, not
`space_size × excerpt_tokens` alone.

### F2 — The proposed SearchSnapshot is not durably preserved or rebuildable as claimed

**Severity: Important**

Section 8.1 says the Gemini cold-run state is preserved under
`benchmark/runs/...` and can be re-materialized with `graphdb-kdb rebuild`.
That is not currently true:

- `benchmark/runs/` is gitignored, so the snapshot is local and is not a
  durable project fixture;
- the bundle includes `compile_result.json` and frozen wiki files, but no
  standard top-level run journal;
- it has no `last_scan.json`;
- `ObsidianRunsAdapter` requires the journal plus
  `<run_id>/compile_result.json` and `<run_id>/last_scan.json` before a run is
  replay-eligible.

**Required resolution:** package the fixed SearchSnapshot in one of these
durable forms:

1. a tracked, minimized benchmark fixture containing the complete frozen
   identity manifest and exact projected excerpts; or
2. a durable content-addressed archive containing the journal, graph-rebuild
   sidecars, wiki state, and checksums.

Whichever form is selected needs an automated restoration smoke test that
materializes the snapshot and verifies its expected identity count, excerpt
hash, and representative entities. The spec must name the storage and
retention authority rather than treating a gitignored run directory as
preservation.

### F3 — `teledyne` is not a valid abstention probe

**Severity: Important**

The selected snapshot contains the active canonical concept
`henry-singleton`. Its opening sentence says:

> Henry Singleton was the founder and CEO of Teledyne...

Its body then discusses Teledyne repeatedly. Therefore `teledyne` has at
least one relevant entity in the proposed SearchSnapshot. Returning
`henry-singleton` is a semantically correct result, so labeling the query as
correctly empty would punish the capability for succeeding.

The same term also appears in summary and article entities in the snapshot.

**Required resolution:** move `teledyne` into the semantic/person or vague
query class with an adjudicated relevant set, and replace it with an
abstention query verified against the exact frozen evidence.

### F4 — SD-4 changes the ratified one-call architecture

**Severity: Important**

Vision P1 says one source produces one batched LLM semantic-selection call on
the happy path. The vision's scale diagram likewise uses candidate generation
followed by one fat LLM selector. SD-4 instead proposes:

1. an LLM relevance pre-selection over all titles; then
2. an LLM relevance selection over retained fat evidence.

Both calls perform relevance selection. This is a material architecture
change, not merely a blueprint implementation detail. It may be a valid
decision, but it requires explicit comparison and vision re-ratification if
selected.

The decision should compare at least these distinct approaches:

1. **FTS/exact candidate generation → one fat LLM selector.** Matches the
   ratified scale flow and has lower recurring cost, but a measured recall
   gate is required before the candidate cap becomes load-bearing.
2. **All-title LLM → retained-fat LLM.** Avoids a lexical candidate filter,
   but doubles selector calls, changes D1, and creates a stage-specific
   artifact and evaluation burden.
3. **Sharded fat LLM selection → deterministic or LLM merge.** Semantically
   evaluates every body excerpt and avoids title-only preselection, but has
   the highest implementation, operational, ordering, and replay complexity.

SD-4 should remain open until corrected vault arithmetic and truth-set
measurements support a collectively selected path.

### F5 — The artifact and evidence-status contracts cannot represent SD-4

**Severity: Important**

`SearchArtifactV1` records one manifest, excerpt map, prompt stamp, model
stamp, and hash. A two-stage execution has two materially different selector
observations:

- Stage 1 sees titles for the complete eligible space;
- Stage 2 sees body excerpts only for the retained identities.

The current artifact cannot reconstruct or audit both calls. It also omits
the request's `graph_ref`, although the ratified SearchSnapshot explicitly
includes graph identity.

The evidence-status definition has a related contradiction. `complete`
currently means every original space entity supplied body evidence. In
two-stage mode, bodies are intentionally hydrated only for the retained 150,
so the result would always be partial if the original-space denominator is
used.

**Required resolution:** define a stage-aware trace, either as one artifact
with stage records or linked child artifacts. It should retain:

- original `graph_ref` and eligible-space manifest;
- Stage-1 evidence bytes, prompt bytes or immutable reference, output,
  validation, and retained identities;
- Stage-2 excerpt bytes, prompt bytes or immutable reference, output, and
  validation;
- per-stage model routes, latency, cost, and hashes;
- final normalized result and fallback state.

Report separate counts for eligible-space size, Stage-1 retained candidates,
Stage-2 hydration, Stage-2 body coverage, and final hits. `complete | partial`
should apply to the evidence pool actually presented to the fat selector,
while eligible-space and candidate-stage coverage remain separate metrics.

The statement that a prompt hash references immutable bytes also needs an
enforceable mechanism: either archive the exact prompt bytes or record a
repository commit plus path whose bytes are guaranteed to remain resolvable.
A hash alone does not preserve them.

### F6 — Fail-closed identity semantics are internally contradictory

**Severity: Important**

The contract calls a foreign slug a typed contract failure. Section 2.3,
however, says invalid entries are discarded while the remaining selector
output is accepted, and §3.4 explicitly denies fallback for those
validation-discarded entries.

That weakens the ratified fail-closed boundary and makes “honest partial”
include contract-invalid output.

**Required resolution:** structural or identity-contract violations should
invalidate the selector response as a whole and activate deterministic
fallback:

- foreign slug;
- unknown expression;
- duplicate slug;
- over-cap result;
- invalid JSON shape;
- inconsistent matched/unresolved expression accounting.

An honest partial should mean a fully valid response that found fewer
relevant entities or explicitly left expressions unresolved. It should not
mean accepting the remainder of contract-invalid output.

The controller should also verify that unresolved expressions are valid,
deduplicated, disjoint from matched expressions, and that every request
expression is accounted for as matched or unresolved.

### F7 — The truth-set metrics conflate different boundaries

**Severity: Moderate**

The proposed metric names and denominators need refinement:

- “search-space recall@K” is not an `@K` metric when it asks whether any
  relevant entity exists anywhere in the caller-supplied space;
- after-controller foreign-slug rate is guaranteed to be zero by validation
  and therefore does not measure selector compliance;
- semantic abstention over a non-empty space and domain-empty policy
  abstention measure different things;
- Stage-1 candidate recall is missing from the recommended two-stage path.

**Required resolution:** report these separately:

1. **scope coverage/recall** over the complete caller-materialized space;
2. **Stage-1 candidate recall@M**, if a candidate stage exists;
3. **final selector precision@5, recall@5, and MRR**;
4. **attempted contract-violation rate** from raw selector output;
5. **escaped foreign-identity rate**, with a hard gate of zero;
6. **semantic abstention accuracy** over non-empty eligible spaces;
7. **domain-empty/domain-missing policy outcomes**, reported as availability,
   not selector relevance quality.

### F8 — The draft defines a truth-set program, not yet the truth set

**Severity: Moderate**

The probe taxonomy is useful, but D7 requires the wrong answer to be defined
before tuning. Approximately 40 proposed expressions and later Joseph
adjudication do not yet constitute a fixed held-out truth set.

Before selector-model evaluation or tuning, check in a versioned truth
artifact containing, per probe:

- stable probe ID and class;
- exact `QueryPayload`;
- caller scope or frozen eligible-space reference;
- relevant canonical slug set;
- acceptable alternatives and relevance notes;
- explicit abstention reason where applicable;
- exact-matchable/alias-matchable annotation;
- adjudicator and version.

Joseph should ratify the labels and numerical gates before experiments can
move the target.

## Spec-decision votes

### SD-1 — Pass-1.5 query fields

**APPROVE WITH REVISION.**

`domain`, `summary`, `key_themes`, and `entity_search_keys` are the correct
minimum. Do not label `author` as noise without evidence: authorship can be a
high-value person signal for the motivating retrieval class. Retain it in v1
or A/B test its exclusion on the fixed truth set. Excluding
`confidence`/`uncertainty_reason` is reasonable.

### SD-2 — T2 candidate/delivered counts

**APPROVE.**

Selector-valid hits before and after the merged tier cap preserve #122's
candidate/delivered meaning. If a candidate-generation stage is adopted, its
pool and recall must be recorded separately rather than overloaded into T2
candidates.

### SD-3 — 250-word excerpt bound

**HOLD.**

The deterministic, versioned leading-excerpt policy is coherent, but the
bound must be ratified only after F1's corrected entity counts and exact
tokenization exercise.

### SD-4 — Two-stage all-LLM scale path

**DISAPPROVE AS WRITTEN.**

It changes ratified P1 and is unsupported by corrected sizing or Stage-1
truth-set recall. Select among the architectural options collectively; amend
the vision if the two-LLM path wins.

### SD-5 — Measured switch threshold

**HOLD.**

Approve the principle of a measured threshold, but define it in serialized
input tokens with prompt/output safety margins after correcting the corpus
baseline. Space-size distribution alone is insufficient.

### SD-6 — Gemini cold-run SearchSnapshot

**APPROVE THE CORPUS DIRECTION, WITH REQUIRED PACKAGING FIX.**

A real, messy corpus is preferable to a toy fixture for relevance
evaluation. Approval depends on producing a durable, checksummed,
automatically restorable SearchSnapshot and correcting its truth labels.

## What can advance unchanged

The following sections are ready to carry into the next revision:

- caller-materialized closed search space;
- graph identity versus wiki evidence authority separation;
- pass-1.5 domain scoping and missing-domain abstention;
- ordered selector hits as T2, with T1/T3 behavior preserved;
- deterministic exact/alias fallback order;
- data-only evidence serialization and adversarial prompt fixtures;
- distinct live-search, record-replay, and historical-re-call modes;
- selector-eligible versus all-request reporting denominators;
- cross-domain scoped-versus-whole-graph A/B cohort.

## Re-review gate

Request re-review after the next spec version:

1. corrects and verifies vault-scale arithmetic;
2. freezes a durable, restorable SearchSnapshot;
3. checks in the adjudicated truth set and replaces invalid probes;
4. resolves SD-4 through an explicit architecture decision;
5. makes artifacts, evidence status, and telemetry stage-aware if needed;
6. restores unambiguous fail-closed selector validation;
7. separates scope, candidate-generation, selection, and policy-abstention
   metrics.
