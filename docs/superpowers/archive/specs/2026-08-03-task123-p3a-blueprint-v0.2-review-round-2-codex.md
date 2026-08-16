# #123 P3a Blueprint v0.2 — Codex Review, Round 2

Date: 2026-08-03  
Reviewer: Codex  
Artifact reviewed: `2026-08-03-task123-p3a-blueprint-v0.2.md`

## Disposition

**REVISE.** v0.2 closes most Round 1 findings, but two load-bearing gaps remain.

## Findings

### 1. High — The pre-run cost projection materially underestimates thin-stage input

The P3a.0 projection bounds thin input using `M × MAX_SLUG_LEN`, but thin receives the entire eligible identity space `N`; `M` is its retention ceiling, not its input ceiling. Each thin identity line also includes slug, title, and page type, so `MAX_SLUG_LEN` alone does not bound its bytes.

The projection additionally measures the current active graph and multiplies that result across 1,586 sources, despite the graph growing after each successful compile. The blueprint retains `intra_run_order` precisely because search space is a function of compile order. Treating every search as if it sees the initial graph can materially understate cumulative thin-stage input and therefore distort the selector-seat decision.

Produce lower, expected, and upper scenarios using source-specific eligible `N`, exact rendered thin-line bytes, and projected graph growth across compile order. Fat input can remain based on the bounded/budget-filled stage-2 pool. Account separately for empty-space and thin-only terminal branches rather than assuming two paid calls for every source.

### 2. High — Compact-success persistence lacks an implementable schema

The current `SearchRunEnvelope` requires `audit: SearchAuditPayload`. It cannot remain unchanged while wrapping a different compact success receipt. Saying that the compact type lives “alongside” the envelope does not define where it appears on disk or how a strict loader distinguishes compact success from full failure.

Define a discriminated, versioned envelope—for example:

```text
SearchRunEnvelope {
  schema_version,
  run_id,
  source_id,
  intra_run_order,
  artifact_path,
  receipt_kind: "compact" | "full",
  receipt: CompactSearchReceipt | SearchAuditPayload
}
```

Specify its strict parser and status-to-`receipt_kind` predicate. The inner audit schema version is not a substitute for versioning the outer persistence union.

### 3. Medium — `RunMeasurements` does not currently exist

The blueprint says an existing `RunMeasurements` bundle gains a search list, but the cited source lines are local `pass1` and `pass2` lists. The public loaders currently return tuples containing one combined `list[PassCallMeasurement]`.

Choose and document one API:

- introduce a real bundle dataclass and migrate all loader callers; or
- preserve the existing tuple API and add a separate search-measurement loader.

A real bundle is coherent, but it is a new contract rather than an extension of an existing type.

### 4. Medium — Measurement counting and unknown-usage semantics remain ambiguous

Define `calls` versus `attempts` precisely. `StageRecord` is one logical attempt, including attempts that receive no provider response, so the two counts otherwise risk becoming identical or model-dependent without explanation.

Also define how `total_input_tokens` is computed when a StageRecord has `provider_input_tokens=None`. Either make the total nullable when any attempt has unknown usage or retain the sum of known usage alongside an `input_token_unknown_attempts` count. Silently coercing missing usage to zero would undercount diagnostics.

### 5. Medium — The full-versus-compact retention predicate is undefined

“SUCCESS” and “FAILURE” need a closed mapping to search outcomes. State explicitly whether full receipts are retained for:

- `selector_failure`;
- pre-call or post-call `budget_exceeded`;
- a completed search followed by an envelope/provenance warning; and
- only thrown exceptions for which an audit exists.

This predicate belongs in the persistence contract and its tests, not solely in logging prose.

### 6. Medium — The complete V1/V2 context-record type boundary is not widened

The blueprint widens `ContextLoadResult.records` to `ContextRecordV1 | ContextRecordV2`, but `ContextEvidence.records` also carries the same records into KPI computation and must be widened. KPI logic then needs explicit version dispatch before accessing version-specific fields.

The V2 `key_outcomes.annotation` field also needs a closed vocabulary and nullability rules for strict parsing, including how the controller-level `cap_exhausted_possible` and `unattributed_possible` flags project onto individual unresolved expressions.

## Round 1 closure audit

- **Finding 1:** satisfactorily closed by removing output-token measurements; the YAGNI disposition is reasonable.
- **Finding 2:** closed by moving V2 serialization into P3a.2 before wiring/deletion.
- **Finding 3:** direction accepted, but the persistence schema gap remains as Round 2 finding 2.
- **Finding 4:** direction accepted, but the nonexistent bundle/API gap remains as Round 2 finding 3.
- **Findings 5–8:** satisfactorily closed.

## Clerical corrections

Several normative references became stale during section renumbering:

- “measurement contract §11” points to the amendment changelog;
- “full measurement contract §8” points to the implementation plan; and
- the test plan's “per the §8 table” points to a phase table, not the branch call-count table.

Replace these with exact references to §4.7 and the appropriate ratified external branch table, or reproduce the small branch table in this integration blueprint.

## Recommended disposition

Revise before ratification. The minimum closure set is:

- correct the thin-stage cost model for `N`, complete rendered identities, and graph growth;
- define a discriminated compact/full envelope and strict parser;
- settle the actual measurement-loader return API;
- define call, attempt, and unknown-token semantics;
- close the full-receipt retention predicate; and
- widen the complete context-evidence union and annotation schema.
