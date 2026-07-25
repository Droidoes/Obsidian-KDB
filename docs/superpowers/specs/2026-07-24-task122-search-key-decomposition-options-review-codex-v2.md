# Codex review — Task #122 search-key decomposition options v1.1

**Reviewed:** 2026-07-24  
**Artifact:** `docs/superpowers/specs/2026-07-24-task122-search-key-decomposition-options.md`  
**Verdict:** **REVISE — the event-time pivot is correct; the artifact and metric contracts need another pass**

## Executive assessment

v1.1 resolves the central flaw in v1.0. Capturing the context decision when it is made is the correct boundary; final-graph re-resolution must never be used to retroactively claim that a key contributed to Pass-2 context.

The six R1 findings are directionally absorbed. The revised design nevertheless exposes two concrete integration breakages and several still-ambiguous measurement contracts:

1. `pass2/*.context.json` collides with the existing Pass-2 measurement namespace and would break KPI emission;
2. telemetry attached to `ContextSnapshot` can enter the model prompt unless a non-prompt projection is explicitly designed;
3. “resolved at load” is not the same as “entered T2” because domain, T1, and dedup filters run after resolution;
4. warn-only sidecar failures can silently bias every aggregate without a completeness contract;
5. T1/T2/T3 counts are not defined relative to the shared page cap;
6. the cold-graph acceptance case currently asserts the opposite of event-time truth.

These are correctable without returning to a post-run architecture.

## R1 absorption

| R1 finding | v1.1 disposition | R2 assessment |
|---|---|---|
| F1 — equality, not ordering | `==` / `!=`; unknown-age residual | **Absorbed** |
| F2 — final target age is not retrieval | pivot to context-load capture | **Absorbed in architecture** |
| F3 — post-run option semantics | post-run options superseded | **Absorbed** |
| F4 — explicit Pass-1-board plumbing | explicit CLI → board path | **Absorbed, with surfacing gap below** |
| F5 — no resolver-precedence copy | shared enriched core + projection | **Mostly absorbed; batch path unresolved** |
| F6 — arithmetic and stable names | frozen rate names + count identities | **Absorbed** |

## Findings

### 1. Critical — the proposed sidecar location breaks the existing Pass-2 loader

Spec line 18 places records at:

```text
state/runs/<run_id>/pass2/<source_id>.context.json
```

The current measurement loader treats **every** `pass2/*.json` file as a `RespStatsRecord` and immediately projects it with `PassCallMeasurement.from_pass2` (`common/measurement.py:345-365`). There is no Pass-2 identification predicate. A context record lacks the response-stat fields, so:

- strict emit-time loading raises and suppresses `measurements.json`;
- tolerant score-time loading counts the context file as malformed;
- Pass-2 boards become incomplete/unranked.

The raw `source_id` is also not a safe filename: production IDs contain `/`. Existing response telemetry uses `safe_source_id` with a collision-resistant suffix (`common/llm_telemetry.py:55-67`).

Use a dedicated namespace, for example:

```text
state/runs/<run_id>/context/<safe_source_id>.json
```

or `pass2_context/`. Write atomically, retain the real `source_id` inside the record, and gather only from that directory. Do not overload `pass2/`.

Add a coexistence test proving that a run with response records plus context records:

- still loads strictly;
- reports the original `pass2_records` count;
- reports `pass2_malformed == 0`;
- emits measurements and builds both pass boards.

### 2. Critical — context telemetry must be structurally excluded from the model prompt

Spec line 70 says `ContextSnapshot` gains a telemetry payload. Today the prompt builder serializes `context_snapshot.to_dict()` directly into `## EXISTING CONTEXT` (`compiler/prompt_builder.py:193-207`). A careless extension of `to_dict()` would disclose `target_first_run_id`, mode diagnostics, candidate counts, and key outcomes to the model and would change Pass-2 prompt bytes/tokens.

Prefer a two-product result:

```text
ContextBuildResult
  snapshot: ContextSnapshot       # prompt-facing; source_id + pages only
  telemetry: ContextTelemetry     # persistence/KPI-facing; never serialized
```

If telemetry remains attached to `ContextSnapshot`, define two explicit projections and keep the existing `to_dict()` prompt projection byte-compatible. In either shape, pin:

- prompt JSON contains only the existing `source_id` and `pages` contract;
- no `first_run_id`, keys, tier diagnostics, or telemetry field reaches the prompt;
- the same graph/source produces byte-identical prompt text and prompt hash before and after Task #122.

Also define the caller-supplied `context_snapshot=` path in `compile_source`: either it supplies telemetry separately, or it intentionally produces no context record and is reflected in coverage. Do not infer outcomes from an already flattened page list.

### 3. Important — “resolver hit” and “T2 contribution” are different events

The proposed `key_outcomes` has only `key`, `resolved`, and target age (lines 25-27), while `search_key_hit_rate` is described as both “resolved at load” and a legitimate retrieval claim (lines 53 and 79).

Current execution has another gate after resolver success:

```python
return {
    canonical for canonical in resolved_map.values()
    if canonical in candidate_slugs
}
```

(`compiler/context_loader.py:419-437`). `candidate_slugs` is already restricted by:

- the same-domain pool;
- exclusion of T1 slugs;
- set deduplication of multiple keys resolving to one canonical target.

A key can therefore resolve successfully but add nothing to T2 because it is off-domain, already present in T1, or duplicates another canonical seed. The current record cannot distinguish those cases despite line 37 claiming it can explain tight scope and many-to-one behavior.

Freeze an outcome state per emitted key, for example:

```text
unresolved
resolved_t2_seed
resolved_already_t1
resolved_out_of_scope
resolved_duplicate_seed
```

Then either:

- rename the existing rate to `search_key_resolved_at_load_rate` and add `search_key_t2_contribution_rate`; or
- define “hit” strictly as `resolved_t2_seed` and emit a separate resolver-success diagnostic.

The former is clearer. Late/never classification must operate only on keys that were genuinely **unresolved** at load, not on keys that resolved but were filtered out. Pin off-domain, already-T1, and many-to-one examples.

### 4. Important — define record lifecycle, denominator, and completeness together

Lines 18, 38, 52, and 71 alternate between “compiled source,” “compiled sources only,” and snapshot-build time. The production sequence is:

```text
Pass-1 signal
  -> build context
  -> Pass-2 model/validation/canonicalization
  -> commit
```

A record written after a successful context build exists even when the later model call, validation, canonicalization, or commit fails. It therefore represents a **context-built Pass-2 attempt**, not a successfully compiled or committed source.

There is also a partial-evidence hazard. `p2_attempted` is currently the number of Pass-1 signal sources (`orchestrator/kdb_orchestrate.py:972-987`), including a source whose context build fails. A warn-only context-sidecar write failure leaves no record. Aggregating whatever files happen to exist would silently improve or degrade means and rates.

The revised contract should specify:

- exactly one record attempt per Pass-1 signal source;
- an explicit record status such as `complete` or `context_failed`;
- no duplicate record per model/content retry;
- expected count and uniqueness checked against `header.p2_attempted`;
- `context_record_coverage = unique_valid_records / p2_attempted`;
- malformed, duplicate, missing, and wrong-run/source records are detected;
- incomplete coverage never masquerades as complete model evidence.

My recommendation is: preserve the orchestration outcome when telemetry writing fails, but emit the new aggregate rates/means as `None` unless coverage is complete; publish the coverage diagnostic so the reason is visible. A different partial-evidence policy is possible, but it must be explicit and consistent with the Pass-board completeness discipline.

“None-on-zero” must mean **zero denominator**, not zero numerator. With emitted keys but zero hits, the hit and age-component rates are `0.0`, while only a no-key denominator produces `None`.

### 5. Important — define T1/T2/T3 counts before or after the shared page cap

The record example stores tier counts and caps only the T3 slug sample (lines 29-32). Current context construction forms complete T1/T2/T3 sets, ranks their union, applies one shared `page_cap`, and then projects valid `ContextPage` rows (`compiler/context_loader.py:91-142`).

Consequently, at least three different counts exist:

1. tier candidates before ranking/cap;
2. tier rows selected by the shared cap;
3. valid pages actually serialized into the prompt.

Calling all of these `context_t*_mean` is ambiguous. If the headline question is “how much context did Pass-2 receive?”, the primary means should count **prompt-delivered pages per tier**, after the shared cap and projection. Candidate-set size can remain a separate diagnostic:

```text
t1_candidates / t2_candidates / t3_candidates
t1_delivered / t2_delivered / t3_delivered
```

If only one family ships, freeze which one. Bound every persisted slug sample, record an overflow count per tier, and preserve deterministic rank order. A T3-only 50-item cap does not model the actual shared `page_cap=50`.

### 6. Important — the cold-graph acceptance case is backwards

Line 95 says:

> cold-graph test (all hits → cohort bucket)

On a truly cold graph, no key can hit at context-load time. If the current source later creates those entities, its keys are **late resolutions**, not cohort hits. A cohort hit requires an earlier source in the same run to have already materialized the target before the tested source builds context.

Replace this with a sequential truth-table test:

- old pre-seeded target → load hit / pre-run age;
- target created by an earlier source under the same `run_id` → load hit / cohort age;
- empty-graph miss later created by this or a later source → late resolution;
- miss still absent post-run → never resolved;
- load hit with missing stamp → age unknown.

Also pin the current empty-graph early-return path (`context_loader.py:78-80`): it must still produce a complete telemetry result containing emitted keys as misses and zero tier counts.

### 7. Moderate — effective modes and the batch resolver need explicit treatment

The example's `t2_mode` values (`structured | legacy-regex | explicit-empty`) do not match the configured `T2Mode` enum (`structured | layered | legacy`), and `layered` can combine key and regex strategies. Separate:

```text
configured_t2_mode: structured | layered | legacy
effective_t2_strategy: structured_keys | explicit_empty | legacy_regex | layered_union
```

Line 39 promises an explicit-empty diagnostic counter, but no frozen watched field supplies it. Either define that field (and the corresponding legacy/layered source counts) or remove the aggregation promise and keep mode only in the raw records.

The current resolver switch also has two implementations: `simple` and the explicitly selectable `batch` escape hatch. “One shared resolver core” must either:

- retire the batch path explicitly; or
- enrich both paths and retain simple-vs-batch parity for outcomes and stamps.

Projection parity inside only the simple resolver does not cover the existing `resolver="batch"` contract.

### 8. Moderate — reconcile surfacing, final-graph reads, and the design gate

- T1/T2/T3 means are called the “headline KPI,” but the explicit Pass-1-board path on line 65 carries only `search_key_*`. Decide whether the three `context_*` means belong there too; my recommendation is to surface all Task-122 fields together.
- Line 12 says the final graph is consulted only to explain misses, while the unchanged legacy metric still re-resolves the broader Pass-1 key set. State the two legitimate final reads: legacy continuity and miss explanation. They may share one batched query, but neither may redefine a load-time hit.
- `docs/TASKS.md` still describes the superseded v1.0 post-run age decomposition. Update the ledger and North Star with the selected event-time contract before Proceed.
- The document is now one pivoted architecture plus a record of rejected options, yet its status says “then Joseph's pick.” Either present the remaining live choice (for example, separate context sidecar vs augmentation of existing telemetry) or label event-time capture as the candidate architecture and ask Joseph to ratify it explicitly.

## Required amendments before ratification

- Move context records out of `pass2/`; use collision-safe filenames and atomic writes.
- Separate prompt-facing context from telemetry-facing context and pin prompt-byte/hash compatibility.
- Define per-key disposition after resolver, domain/T1 eligibility, and dedup; distinguish resolver success from T2 contribution.
- Freeze record lifecycle, status, expected count, uniqueness, coverage, and incomplete-evidence policy.
- Define tier candidate versus prompt-delivered counts and bounded samples.
- Replace the cold-graph test with the event-time truth table.
- Cover structured, explicit-empty, legacy, and layered strategies; preserve or retire batch resolution explicitly.
- Surface the complete selected Task-122 field set consistently.
- Correct the final-graph-read wording and update the task ledger/North Star before Proceed.

## Recommendation

Keep the **context-load capture** architecture. Use a dedicated `context/` sidecar namespace and return prompt data and telemetry as separate products from the context builder. Measure both:

1. whether each emitted key resolved at load; and
2. whether it actually contributed a T2 seed after scope/T1/dedup gates.

That design answers Joseph's real question without contaminating the prompt or reconstructing history from a graph the run already changed.
