# #123 Semantic Graph Search Spec v0.2 — Codex Re-review

**Date:** 2026-07-25  
**Reviewer:** GPT-5.6 / Codex  
**Artifact:** [`2026-07-25-task123-semantic-graph-search-spec.md`](2026-07-25-task123-semantic-graph-search-spec.md)  
**Prior review:** [`2026-07-25-task123-semantic-graph-search-spec-review-codex.md`](2026-07-25-task123-semantic-graph-search-spec-review-codex.md)  
**Review scope:** Closure of the v0.1 seven-condition re-review gate,
SD-1–SD-6 dispositions, and readiness for spec ratification

## Verdict

**REVISE — DISAPPROVE v0.2 for ratification as currently written.**

v0.2 makes substantial progress. It corrects the 163-entity baseline and the
`teledyne` label, restores whole-response fail-closed validation, defines a
stage-aware artifact, separates the evaluation boundaries, retains `author`,
records the architectural options for SD-4, and amends vision P1.

The selected scale path still does not fit the contract's projected
whole-graph human search under its own conservative 100k-token budget,
however. The durable SearchSnapshot and adjudicated truth-set artifacts
required by the previous re-review gate also do not exist yet. They are
specified as future gates, not frozen artifacts.

The direction is close. Resolve the remaining substrate and scale-path
findings before ratifying v0.2 or vision v1.3 P1.

## Seven-condition gate closure

| Prior re-review condition | Status in v0.2 | Assessment |
|---|---|---|
| 1. Correct and verify vault-scale arithmetic | **PARTIAL** | The 163/29 baseline and average fat-evidence cost are corrected. Thin-prompt serialization remains materially underestimated, and the exact run-end largest domain is not used. |
| 2. Freeze a durable, restorable SearchSnapshot | **OPEN** | The required fixture is designed and correctly gated, but `benchmark/truth/` currently contains only `.gitkeep`. |
| 3. Check in the adjudicated truth set and replace invalid probes | **PARTIAL** | `teledyne` is corrected and the JSON schema is defined. The checked-in probe artifact, labels, alternatives, and gates do not yet exist. |
| 4. Resolve SD-4 through an explicit architecture decision | **PARTIAL** | The comparison, Joseph's option-2 selection, and proposed vision amendment are recorded. Option 2 does not fit projected whole-graph Stage 1 under the stated budget. |
| 5. Make artifacts, evidence status, and telemetry stage-aware | **RESOLVED IN DESIGN** | The stage model and fat-pool coverage denominator are sound. The replay-byte and hash refinements in F4 remain. |
| 6. Restore unambiguous fail-closed validation | **RESOLVED** | Any contract violation now invalidates the complete response and activates fallback. Honest partial is correctly redefined. |
| 7. Separate scope, candidate, selection, and policy metrics | **RESOLVED** | Scope coverage, Stage-1 recall, final relevance, attempted/escaped violations, semantic abstention, and availability are separated. |

Four of the seven conditions remain open or partial. The previous ratification
gate is therefore not closed.

## Load-bearing findings

### F1 — Thin Stage 1 is materially underestimated and does not scale to whole-graph search

**Severity: Important**

Section 7.1 estimates the complete 163-identity thin projection at
approximately 0.8k tokens and the projected 9,600-identity whole graph at
approximately 48k tokens.

Using the exact thin field layout shown in §2.1 over the selected snapshot,
the evidence block alone is:

- 14,342 characters;
- 1,655 whitespace-delimited words;
- approximately 2,152 tokens under the repository's established
  `words × 1.3` estimator;
- approximately 3,586 tokens under a simple four-characters-per-token
  estimate.

Those counts exclude the system task, query, JSON output allowance, and
provider safety margin. Projected linearly to 9,600 identities:

- the repository estimator yields approximately **127k input tokens**;
- the character estimate yields approximately **211k input tokens**.

Both exceed the spec's conservative 100k budget before overhead. The selected
all-title Stage 1 may fit pass-1.5's domain-scoped space, but it does not fit
the contract's default whole-graph human/CLI/MCP search at projected vault
scale. A consumer-neutral capability needs a complete path for both.

The fixed cold-run end state also permits an exact largest-domain count:
`value-investing` has **51 unique eligible entities**, not merely the
46-entity mid-run floor. Its run-end share is approximately 31%, projecting
to roughly 3,000 of 9,600 identities under the same simple scaling premise.

**Required resolution:** correct the thin serialization counts and select a
whole-graph Stage-1 strategy. Distinct options include:

1. require a Stage-1 selector model and operational budget large enough for
   the measured complete thin graph;
2. shard or hierarchically partition thin selection, then perform a global
   retained-candidate merge;
3. use measured lexical/structural candidate generation for spaces whose
   complete thin projection cannot fit.

Each option changes cost, recall risk, ordering, or operational model
coupling. Record the collective decision and make its artifact/replay trace
explicit. SD-4 and vision v1.3 P1 should remain open until one option closes
whole-graph search end to end.

### F2 — The durable SearchSnapshot and truth set are still promises, not artifacts

**Severity: Important**

Section 8 correctly acknowledges the false rebuild claim and specifies a
tracked, checksummed fixture plus restoration smoke test. It also specifies
the necessary checked-in truth-set fields and Joseph's label/gate
ratification.

Neither artifact exists yet. [`benchmark/truth/`](../../../benchmark/truth/)
contains only `.gitkeep`; there is no frozen identity/excerpt fixture,
checksum manifest, restoration test, probe JSON, adjudicated relevance set,
or numerical gate record.

This is an improvement to the plan but does not satisfy the prior gate to
*freeze* the SearchSnapshot and *check in* the truth set. D7 is load-bearing:
labeling cannot be trusted until the substrate is immutable, and selector
choice or tuning cannot begin until the labels and gates are fixed.

**Required resolution before ratification:**

1. materialize the tracked SearchSnapshot fixture;
2. land and pass the restoration smoke test;
3. check in the complete probe artifact;
4. have Joseph ratify its labels, acceptable alternatives, abstentions, and
   numerical gates.

If the team intentionally wants spec-design ratification before those
artifacts exist, record that as a narrower gate—such as **spec design
approved; evaluation substrate open**—rather than representing the previous
seven-condition ratification gate as closed.

### F3 — Body-length distribution remains a sizing variable

**Severity: Moderate**

The selected snapshot verifies the current measurements:

- 163 unique pages;
- two bodies over 250 words;
- approximately 73 capped words per entity on average;
- current medians of 62 words for concepts, 57 for summaries, and 135 for
  articles.

That supports the empirical expected-case estimate of approximately 97 tokens
per fat entity. It does not make the 250-word cap inert at vault scale or make
entity count the only variable. The future vault can have a different mix and
body-length distribution. Under the safety-bound case, many more pages may
approach 250 words, causing the single-stage switch to activate far below the
approximately 1,000-entity seed.

**Required resolution:** retain both:

- an empirical expected-case projection from the frozen snapshot; and
- a conservative safety-bound projection using the 250-word cap plus
  identity-field and prompt overhead.

Runtime measured serialized tokens should remain the authoritative switch.
Entity count is a useful trend series, not the sole sizing variable. SD-5's
principle is sound, but `~1,000 entities` should remain an explicitly
provisional measurement rather than a ratified capacity claim.

## Contract and replay refinements

### F4 — Exact rendered prompt and failure output bytes are not yet preserved

**Severity: Moderate**

The stage-aware artifact is the right architecture, but
`repo_path + version + sha256 + git_commit` resolves the historical prompt
*template*, not necessarily the exact rendered messages sent to the model.
Byte-identical rendering also depends on serializer, escaping, message
assembly, and request-shaping code.

Likewise, `output: <raw stage output JSON>` cannot represent malformed JSON,
non-JSON model text, transport failure, or timeout—the cases most important
to fallback audit.

**Required resolution:** archive per stage:

- exact rendered system and user message bytes, or an immutable renderer
  identity plus an enforceable historical reconstruction mechanism;
- exact raw response text/bytes;
- parsed output as nullable;
- call/validation failure class and detail.

The current `search_space_hash` scope also omits `graph_ref`, even though the
ratified SearchSnapshot includes graph identity. Define a
`search_snapshot_hash` over graph reference, ordered manifest, exact evidence,
and projection-policy identity. A separate request/artifact integrity hash
can additionally cover query, prompt, stage trace, and result.

### F5 — Empty-space and consumer-neutral artifact states are under-specified

**Severity: Moderate**

The missing/empty-space behavior is correct operationally, but it has no
faithful representation in the result type:

- `execution` permits only `single_stage | two_stage`, although no selector
  executes;
- `body_coverage` has a zero-sized denominator;
- `evidence_status` has no not-applicable state;
- `degraded_mode` includes `llm`, although LLM execution is not degraded.

Use explicit orthogonal fields, for example:

```text
execution: not_executed | single_stage | two_stage
selection_mode: llm | deterministic_fallback | abstain_empty_space
evidence_status: not_applicable | complete | partial
body_coverage: float | None
```

The core artifact also requires `run_id` and `source_id` and mandates a
per-source orchestrator path, while the contract is intended to serve ad hoc
MCP/CLI/human searches that may have neither. Separate:

```text
consumer-neutral SearchAuditPayload
  + optional/injected artifact sink

pass-1.5 SearchRunEnvelope
  + run_id, source_id, intra_run_order, persisted path
```

This turns artifact-sink separability from an open comment into a type shape
that the blueprint can implement without weakening the consumer-neutral
contract.

Finally, the integration test wording “batched once per source” is stale
under SD-4. It should require one `graph_search` invocation per source and one
or two selector calls according to the recorded `execution`.

### F6 — Stage-2 fallback search space should be explicit

**Severity: Moderate**

On Stage-2 failure, “the same search space” can mean either the complete
original eligible space or the Stage-2 retained subset. Survival semantics
require deterministic exact/alias fallback over the **complete original
eligible space**; otherwise a correct exact identity omitted by failed
Stage 1 cannot survive.

State this explicitly in §3.4 and add a test where Stage 1 omits an exact key,
Stage 2 fails, and fallback still resolves that key from the original space.

## Findings resolved from v0.1

The following changes are approved:

- corrected total identity count and explicit source denominator;
- `author` retained in pass-1.5 query text;
- Stage-1 retained pool separated from T2 candidate/delivered counts;
- `teledyne` moved from abstention into semantic retrieval;
- proposed abstention terms checked against frozen source-run evidence;
- whole-response fail-closed contract validation;
- valid matched/unresolved expression accounting;
- honest partial separated from contract failure;
- attempted versus escaped identity violations separated;
- stage-aware artifact and fat-evidence coverage denominator;
- scope, candidate, final selector, abstention, and availability metrics
  separated;
- resolver exercised on the happy path for match annotations;
- class-A labels recognized as the operative semantic success definition;
- distinct live-search, record-replay, and historical-re-call modes retained.

## SD votes

| SD | Codex v0.2 vote | Reason |
|---|---|---|
| **SD-1** | **APPROVE** | The five-field package, including `author`, is coherent. |
| **SD-2** | **APPROVE** | T2 counts preserve #122 meaning; Stage 1 is separate. |
| **SD-3** | **APPROVE WITH WORDING REVISION** | Keep the deterministic 250-word safety cap, but do not call it inert at future vault scale. |
| **SD-4** | **HOLD / REVISE** | Option 2 is selected and vision-amended, but its thin Stage 1 does not fit projected whole-graph search under the stated budget. |
| **SD-5** | **APPROVE THE PRINCIPLE; HOLD THE SEED** | Runtime serialized-token switching is correct; the ~1,000-entity seed depends on expected body length and corrected prompt serialization. |
| **SD-6** | **APPROVE THE CORPUS CHOICE; SUBSTRATE OPEN** | The real corpus is appropriate, but its durable fixture, restoration test, truth labels, and gates have not landed. |

## Re-review gate

Request the next re-review after:

1. correcting thin serialized-prompt and exact largest-domain measurements;
2. resolving whole-graph Stage-1 fit and updating vision P1 accordingly;
3. landing the tracked, checksummed SearchSnapshot and restoration smoke test;
4. landing and ratifying the checked-in truth-set labels and numerical gates;
5. preserving exact rendered request and raw failure-output bytes;
6. defining empty-space result states and the consumer-neutral audit envelope;
7. making Stage-2 failure fallback explicitly search the original eligible
   space.

No implementation, selector tuning, or vault ingestion should cross the D7
gate until items 3 and 4 are complete.
