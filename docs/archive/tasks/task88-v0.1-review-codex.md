# Task #88 v0.1 Checkpoint Review — Codex

**Reviewer:** Codex  
**Date:** 2026-05-24  
**Scope:** v0.1 checkpoint architecture review of `docs/task88-ingestion-pipeline-blueprint.md`, with cross-check against `docs/graphdb-kdb-producer-contract.md` v1.0.

## 1. Convergence

The v0.1 skeleton mostly holds. The "one source-storage component, two configurations" framing is the right simplification for v1, and D-88-3's dir-exclusion-only pre-gate is defensible given the current cost model. The two-pass worth judgment is also directionally right: Pass-1 can only answer "is this source plausibly signal?" while Pass-2 is the first point with ontology context.

The main issue is not the high-level shape. It is that the blueprint currently blurs three boundaries that need to stay explicit:

1. source identity vs rename correlation
2. enrichment artifacts vs GraphDB producer artifacts
3. binary routing vs auditable uncertainty

## 2. Findings

### F1 — §3.5 has an identity / rename contradiction

The blueprint says identity is `vault-relative path`, while also tracking `filename change` and `dir-path change` per source.

> `Identity scheme | vault-relative path`

If identity is path, then a filename change is not a mutation of the same source identity. It appears as old path deleted plus new path created unless there is separate rename correlation. The pseudocode also cannot detect same-content renames if it skips on `(size, mtime)` before cross-path correlation.

The fix is to separate:

- `source_id`: stable operational identity, likely `config_id + normalized vault-relative path`
- `content_hash`: authoritative content identity
- `rename/move correlation`: best-effort event linking old path to new path when hashes match

A rename should trigger re-enrichment because path/filename may carry semantics, but it should not necessarily orphan lineage as "new unrelated source."

### F2 — Lifecycle is under-split in §3.2 / §3.5

"Lifecycle = new / change / delete + dir-as-meta" compresses different semantics. New detection, content change, metadata-only move, rename, delete, revive, and excluded-by-scope are different events. They have different replay/audit behavior.

**Recommendation:** Split lifecycle into an event taxonomy before implementation:

- `created`
- `content_changed`
- `path_changed`
- `metadata_changed`
- `deleted`
- `revived`
- `excluded`
- `unchanged`

### F3 — Producer Contract alignment is not yet explicit enough

The review prompt says #88's source-storage/enrichment produce artifacts the producer contract consumes, but the blueprint only defines per-source state and enrichment outputs. The frozen contract requires four run-shaped artifacts: mutation payload, scan/state payload, run journal, and sidecar archive.

Read-in-place is compatible with the contract, but only if every ingestion/enrichment run emits durable run snapshots. "State-tracking-only" must not mean "only the latest state exists." Replay requires archived, byte-stable payloads.

**Recommendation:** Add a §4.5 or §6.3 called "Run artifact boundary" that names the actual v1 artifacts, for example:

- `ingest_scan.json`: inventory + source lifecycle events
- `enrichment_result.json`: Pass-1 verdicts, domains, tags, wikilink suggestions
- `ingest_run_journal.json`: success / dry_run / schema_version / artifact paths
- sidecar archive under `state/ingest_runs/<run_id>/...`

Then state whether compile consumes these directly, or whether an adapter normalizes them into the existing `compile_result` / `last_scan` contract.

### F4 — Pass-1 binary routing is fine, but binary-only observability is not

D-88-4's "uncertain -> pass" is correct as a routing rule. But if the emitted field is only `pass | not_pass`, uncertainty disappears from the audit trail. That weakens the sample-audit mitigation for silent false rejects.

**Recommendation:** Keep the routing binary, but require audit fields:

- `verdict`
- `confidence`
- `uncertainty_reason`
- `reject_reason`
- `prompt_version`
- `model`
- `schema_version`

This does not reopen the settled "uncertain routes to pass" decision. It just preserves the diagnostic signal.

### F5 — D-88-3's hedge is too vague to fire reliably

> "if vault grows large AND LLM cost reverts"

This is directionally right but operationally soft. Define concrete watch rules:

- file-count threshold, e.g. `vault_candidate_count >= 5,000`
- monthly projected enrichment spend threshold
- Pass-1 false-reject audit threshold
- sample size and cadence, e.g. audit `max(50, 5%)` of `not_pass` per month

Also persist all `not_pass` decisions so false-reject audits are possible later.

### F6 — Pass-2 should be explicit, not implicit

For OQ-88-2, I recommend **explicit**.

Implicit "zero emitted pages means no contribution" overloads too many states: true no-op, compiler failure, schema suppression, prompt weakness, or source duplication. Given the project's existing schema-gated discipline, Pass-2 should emit an explicit source-level field such as:

- `ontology_contribution: pass | not_pass`
- `reason`
- `matched_existing_entities`
- `new_claims_or_edges_count`

This should be schema-validated and archived with the mutation payload.

### F7 — The D-88-5 exception is defensible only with a tighter boundary

Pass-2 is a valid exception to the pivot rule because ontology-aware judgment cannot happen at Pass-1. But the blueprint should define an exception test so this does not become precedent for compile-side expansion.

**Proposal:** A future end-A exception is allowed only if all are true:

- it consumes a #88 artifact
- it requires live ontology context
- it cannot be moved to ingestion without losing correctness
- it is schema-gated and replayable
- it does not add broad new compile behavior beyond the named gate

### F8 — OQ-88-4 attention dilution is real but should be measured before splitting

The single-call enrichment design is acceptable for v1 if the output schema forces the decision fields first and separately from generative outputs. I would not split immediately.

**Recommendation:** Predeclare split triggers. If Pass-1 audit accuracy, domain accuracy, or wikilink quality falls below threshold, split into `verdict+domain` and `tags+wikilinks`.

### F9 — Vocabulary should be cleaned now

**Recommendation for OQ-88-1:** Choose **(a)**.

Use:

- "Ingestion System" for Task #88 umbrella
- "source feeders" for producers that place material into storage
- "source storage configs" for raw-drop / vault-in-place
- "GraphDB producer" only for the frozen producer-contract role

This avoids collision with the existing producer/adapter vocabulary.

## 3. Recommendations

**Recommendation:** Amend §3.5 to separate `source_id`, `content_hash`, and `rename_correlation`, and make `config_id` part of the state key.

**Recommendation:** Add a run-artifact section mapping #88 outputs to `docs/graphdb-kdb-producer-contract.md` §3. Without this, the design is not yet contract-complete.

**Recommendation:** Pick explicit Pass-2 for OQ-88-2, with a schema-gated source-level verdict archived in sidecars.

**Recommendation:** Keep Pass-1 routing binary, but add non-routing diagnostic fields so "uncertain -> pass" remains auditable.

**Recommendation:** Replace D-88-3's hedge with concrete cost/count/audit watch rules.

**Recommendation:** Default-exclude `Daily Notes/` for Config B unless there is a strong reason not to. They are structurally likely to be meta-work and will otherwise burn enrichment budget repeatedly.

## 4. Open questions

1. Should rename/move with identical content preserve the old source lineage, or intentionally orphan old and create new? I recommend preserving lineage with a `path_changed` event.
2. Is #88 itself a GraphDB producer, or is it a pre-compile producer whose artifacts are consumed by `kdb-compile`? The blueprint currently gestures both ways.
3. What is the first v1 replay target: replay enrichment decisions, replay graph mutations, or both? That answer determines how heavy the ingest sidecar must be.
