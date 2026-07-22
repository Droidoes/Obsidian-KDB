# Task #115 — Pass-2 contract audit: Codex review

**Date:** 2026-07-21  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-audit-findings.md`  
**Repository anchor:** `main` at `7d8263b`  
**Verdict:** Revise findings before architecture selection

## Executive assessment

The audit is directionally correct on three central points:

1. version and independently fingerprint the live Pass-2 contract before editing it;
2. remove constant `status` from the LLM response and stamp `active` in Python;
3. remove `concept_slugs` / `article_slugs` from the LLM response and derive them from `pages[]`.

It is not yet complete enough to serve as the design basis. The same data-flow test
identifies three additional redundant model outputs (`outgoing_links`, `source_name`,
and the top-level `summary_slug`). The audit also overstates the runtime use of
`warnings` and `log_entries`, and its proposed slug-list cleanup conflates removing
fields from the LLM contract with removing derived fields from the persisted aggregate
contract.

## Findings

### F1 — High: `outgoing_links` is also dead LLM output

The audit classifies `outgoing_links` as consumed, but the model-emitted value never
reaches a downstream consumer. After the response passes schema and semantic checks,
`compiler.compiler.compile_one` calls `reconcile_body_links`, which unconditionally
replaces each page's `outgoing_links` with the sorted set of wikilinks extracted from
`body`:

- `compiler/compiler.py:447-448`
- `compiler/repair.py:242-265`

`CompiledSource` is assembled only after this normalization. This is the exact same
dead-output pattern as `concept_slugs` / `article_slugs`.

**Disposition:** Remove `outgoing_links` from the Pass-2 LLM schema, prompt, and
exemplars. Retain it as a Python-derived internal field because canonicalization,
graph intake, and replay consume the normalized value.

### F2 — High: `source_name` is a parrot-only response field

The model echoes a value Python already supplied. The response value is checked once
against the expected basename in `validate_source_response.semantic_check`
(`compiler/validate_source_response.py:68-73`) and then discarded. `CompiledSource`
uses `job.source_id`, not the echoed value.

The filename remains necessary as prompt input because it informs the summary-page
identity. It does not need to be model output.

**Disposition:** Remove `source_name` from the response schema and exemplar. Keep the
filename in the user prompt and use Python's known `source_name` directly for semantic
validation and deterministic derivations.

### F3 — High: top-level `summary_slug` is redundant and under-validated

Downstream stages need an internal `summary_slug`, but the LLM supplies the same
classification twice:

- a top-level `summary_slug`; and
- a page with `page_type: "summary"` and its own `slug`.

The semantic gate only verifies that the two model-authored answers agree
(`compiler/validate_source_response.py:75-95`). It does not mechanically enforce the
prompt's stronger promise that the value equals `summary-` plus the kebab-cased source
filename stem.

This duplication has already produced a real quarantine: qwen3.6 emitted a
`summary_slug` absent from `pages[].slug` (`common/models_dropped.json:97`).

**Disposition:** Require exactly one summary page, validate that page's slug against
the deterministic source-derived expectation, and derive the aggregate
`CompiledSource.summary_slug` from that page. The field can remain in the persisted
aggregate contract without remaining in the LLM contract.

### F4 — High: the `warnings` and `log_entries` consumption map is inaccurate

#### `warnings`

LLM warning strings are merged into `compile_result.json`, and their count appears in
per-call `parsed_summary`. They are not what populates
`last_orchestrate.json.counts.warnings`. That count comes from events whose severity is
`warning` (`orchestrator/kdb_orchestrate.py:453-457`).

In the retained GLM run, `compile_result.json` contains 10 LLM warning strings while
the event journal contains one orchestrator warning event, demonstrating that the two
surfaces are independent.

#### `log_entries.related_slugs`

The audit says the runner derives `related_source_ids` from `related_slugs`. The
current implementation does not. It stamps an empty array on every entry:

```python
state["log_entries"] = [
    {**le, "related_source_ids": []}
    for le in parsed.get("log_entries", [])
]
```

See `compiler/compiler.py:508-511`. No later manifest lookup populates the array. In
the retained GLM compile result, all 38 log entries have empty `related_source_ids`,
including the 35 entries with non-empty `related_slugs`.

**Disposition:** Judge `warnings` and `log_entries` solely as human audit channels.
Keep them if that journal has demonstrated value, but make them optional rather than
required. Remove the fictitious new-artifact `related_source_ids` injection while
retaining read compatibility for historical compile results.

### F5 — High: the slug-list removal cascade overreaches

I concur that `concept_slugs` and `article_slugs` should leave the LLM contract. The
proposed deletion of aggregate pairing validation and its tests is not automatically
safe, however.

If Python continues to persist derived lists in `CompiledSource` and
`compile_result.json`, the following surfaces remain relevant to historical fixtures,
replay inputs, externally supplied aggregate artifacts, and defense against future
producer defects:

- `common/types.py:243-266`
- `compiler/schemas/compile_result.schema.json:138-158`
- `compiler/validate_compile_result.py:180-230,248-252`
- `compiler/canonicalize.py:465-500`
- `compiler/repair.py:80-153`

The pairing rules are moot only for the normal live `compile_one` path after
`reconcile_slug_lists`; they are not necessarily moot for the aggregate contract.

**Required design fork:**

1. **LLM-only removal:** remove the lists from the per-source response; derive and
   persist them; retain aggregate integrity checks and historical compatibility.
2. **End-to-end deprecation:** stop writing the lists in new aggregate artifacts and
   remove their active consumers, while keeping an explicit compatibility path for
   historical journals and rebuild/replay.

Do not partially mix these scopes.

### F6 — Medium: provenance must identify the effective contract bundle

The audit correctly requires provenance before contract edits, but “edits are
currently invisible” is too strong. `RespStatsRecord.prompt_hash` already hashes the
effective system and user prompt together (`common/llm_telemetry.py:150-154`). A vault
prompt edit therefore changes the hash, but the change cannot be isolated from source
text, context, metadata, or schema changes.

The effective Pass-2 contract has at least three independently mutable components:

1. vault-owned `KDB-Compiler-System-Prompt.md`;
2. code-owned `RESPONSE_CONTRACT`;
3. normalized `compiled_source_response.schema.json` embedded in the user prompt.

The prompt loader is memoized by vault path (`compiler/prompt_builder.py:60-66`). A
file SHA recomputed from disk at run completion could therefore differ from the bytes
actually cached and sent if the operator edits the file during the process.

**Disposition:** Record from the actual loaded strings:

- `pass2_prompt_version` — human-readable contract release;
- `pass2_system_prompt_sha256` — vault prompt text actually loaded;
- `pass2_response_contract_sha256` — code-owned contract block;
- `pass2_response_schema_sha256` — normalized schema text actually embedded.

The existing per-call full `prompt_hash` remains useful and should not be replaced.
The findings document should also anchor external prompt evidence with a SHA rather
than claiming the vault file is anchored by repository commit `7d8263b`. At review
time, the live prompt SHA was:

```text
dcfa3d1cd9c1e7c543527b5d4357ce46fb9f1e31a766a8127b8565942c11e12a
```

### F7 — Medium: `confidence` is an unresolved data-model problem, not merely unused data

`confidence` is persisted and exposed, but its current placement does not match its
prompt semantics. The prompt defines per-page confidence in how directly the current
source supports the generated material. Graph intake stores it on the shared
`Entity` node and overwrites it on every upsert (`kdb_graph/intake.py:283-299`). When
multiple sources support one entity, the resulting value is whichever source was
compiled last. It is order-dependent, not aggregated entity confidence.

The parked belief-classifier code consumes candidate/evidence confidence values; the
audit does not establish that it consumes this `Entity.confidence` attribute.

The retained benchmark compile results also show weak discrimination:

```text
956 high
 45 medium
  0 low
```

**Disposition:** Do not justify the field by the parked 2.0 tier without an explicit
mapping. The sound architectural choices are:

1. store source-grounding confidence on source-to-entity evidence/SUPPORTS provenance;
2. define a deterministic aggregation contract for entity confidence; or
3. deprecate the value.

For Task #115 alone, retaining it temporarily avoids silently replacing all values
with an equally misleading default such as `medium`. The data-model correction should
be separately scoped if it cannot fit this task without graph/MCP migration.

### F8 — Medium: the GLM `page_type` failure has a plausible redundancy mechanism

The four retained failing payloads have the same structural signature:

```text
summary page:      page_type present
all other pages:   page_type absent
top-level lists:   concept/article membership still present
```

The failures contain 5, 13, 5, and 6 missing `page_type` errors respectively. This is
strong evidence that GLM treated the top-level slug lists as sufficient classification
for non-summary pages, even though the schema and examples require the per-page field.

**Disposition:** Remove the redundant lists first, retain `page_type` as required, and
re-run the cohort. Do not add repair yet. Once the redundant lists are gone, Python
cannot safely infer `concept` versus `article` from the remaining response.

### F9 — Medium: the live prompt contains additional cleanup defects

The current vault prompt has at least three issues outside the audit's removal list:

1. line 1 begins with stray text: `do youd# KDB Compiler — System Prompt`;
2. line 13 calls EXISTING CONTEXT a “manifest snapshot,” although GraphDB has been the
   only supported context authority since D49 and `prompt_builder` labels it a graph
   snapshot;
3. line 209 says malformed output aborts the run, while the orchestrator now
   quarantines the source and continues, producing `completed_with_quarantines` when
   appropriate.

These should be corrected only after the provenance change lands.

## Answers to the review questions

### 1. Are `concept_slugs` / `article_slugs` dead, and is the cascade complete?

Yes, they are dead **LLM output**. No, the cascade is not complete. It omits several
prompt/exemplar/coercion surfaces and prematurely assumes aggregate validation and
historical compatibility can be deleted. Choose LLM-only removal versus end-to-end
deprecation explicitly.

### 2. Keep or remove `confidence`?

Do not ratify it on the current rationale. Its present graph placement is
order-dependent and does not match the prompt's per-source semantics. Keep it
temporarily only if Task #115 must remain a prompt-contract cleanup; otherwise re-home
or deprecate it through a separately designed graph/API migration.

### 3. Keep or trim `log_entries`?

Keep the human audit channel if it is useful, but make it optional. No graph consumer
currently exists. Remove the claim and implementation that `related_source_ids` is
derived, unless a real resolver is intentionally added.

### 4. Other dead or parrot-prone fields?

Yes:

- `outgoing_links` — dead model output; derive from body;
- `source_name` — parrot-only response echo;
- top-level `summary_slug` — redundant response identity; derive after validating the
  one summary page;
- required empty `warnings` / `log_entries` arrays — unnecessary hard-failure surface;
- `confidence` — highly skewed and architecturally mislocated, though removal has a
  larger compatibility boundary.

### 5. Is prompt ambiguity a plausible cause of GLM's `page_type` omissions?

Yes. The top-level concept/article lists are a parallel type encoding, and the exact
failure pattern shows GLM retained that encoding while omitting the per-page copy.
Remove the redundancy and benchmark before considering a repair rule or additional
prompt prose.

## Candidate architecture scopes

### Option A — Minimal cleanup

Remove only the already-decided `status`, slug-list output, and jargon; add provenance.
This is cheapest but leaves other known duplicate response fields and failure surfaces.

### Option B — Derivation-first Pass-2 contract

The LLM emits semantic page content:

- `pages[]`: `slug`, `page_type`, `title`, `body`, provisionally `confidence`;
- optional `log_entries` and `warnings`.

Python derives or stamps:

- source identity;
- top-level `summary_slug`;
- `concept_slugs` / `article_slugs` if retained in aggregate artifacts;
- `status`;
- `outgoing_links`;
- support/provenance fields.

This most directly follows the controller-style North Star while preserving the
current aggregate/replay contract.

### Option C — Full contract and graph cleanup

Adopt Option B and also redesign/deprecate confidence, log-entry provenance, and the
aggregate slug lists. This produces the cleanest end state but crosses into graph
schema, MCP surface, rebuild compatibility, and historical-journal migration.

## Ratification blockers

Before requesting Proceed on a Task #115 blueprint:

- [ ] Choose the LLM-only versus end-to-end scope for derived slug lists.
- [ ] Decide whether `outgoing_links`, `source_name`, and top-level `summary_slug`
      join the cleanup.
- [ ] Correct the `warnings` / `log_entries` consumption analysis.
- [ ] Specify version plus component hashes from the actual loaded contract strings.
- [ ] Decide whether confidence stays temporarily or expands into a separate
      data-model migration.
- [ ] Correct the live prompt's stray prefix and stale architecture prose after the
      provenance gate lands.
- [ ] Benchmark the simplified contract before adding any `page_type` repair.
