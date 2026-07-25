# Codex review — Task #122 event-time context capture blueprint v0.1

**Reviewed:** 2026-07-24  
**Artifact:** `docs/superpowers/specs/2026-07-24-task122-search-key-decomposition-blueprint.md`  
**Architecture baseline:** options v1.3 + D-122  
**Verdict:** **REVISE — correct architecture, but not yet safe to Proceed**

## Executive assessment

The blueprint faithfully carries the ratified event-time architecture into an implementation shape:

- the North-Star and task-ledger P0 gate is complete;
- prompt data and telemetry are separate products;
- per-key dispositions distinguish resolution, pre-cap seeding, and delivery;
- tier records preserve candidate-versus-delivered meaning;
- context-build failures remain observable without changing source outcomes;
- identity reconciliation, complete-only substantive populations, and board surfacing are present;
- the legacy post-run metric remains intact for continuity.

No return to architecture options is needed. The design direction is settled.

Four contracts still need correction before Joseph's Proceed:

1. the existing no-finalize KPI gate suppresses exactly the failure evidence this task says it will publish;
2. ownership and versioning of the persisted record are inconsistent with the builder interface;
3. record validation and reconciliation are not specified tightly enough to support fail-closed aggregation;
4. the late/never rate denominator is internally ambiguous.

Two smaller amendments should make the resolver refactor and TDD plan executable without interpretation.

## Findings

### 1. Important — the current no-finalize gate makes the failure-population contract unreachable

Blueprint §§4–6 correctly preserve a `context_failed` record and state that:

- it counts toward record coverage;
- `context_build_success_rate` is complete records divided by expected records;
- an expected set with zero complete records still has auditable coverage while substantive metrics are `None`;
- context evidence remains valid even if a later model, validation, canonicalization, or commit stage fails.

The current emission lifecycle prevents those cases from producing any measurement artifact. `orchestrator/kdb_orchestrate.py:992-1005` passes `finalize_ran=finalize_stats is not None`, and `orchestrator/emit_kpis.py:192-205` returns without emitting when no source committed and finalize did not run.

Consequences:

- if every context build fails, all expected `context_failed` records exist but `context_build_success_rate=0.0` is never emitted;
- if every context build succeeds but all sources fail later, valid event-time evidence is still discarded;
- the blueprint's “expected-but-zero-complete” and later-failure acceptance cases cannot be exercised end to end.

Freeze the no-finalize behavior in the blueprint. The recommended contract is:

1. `--emit-kpis` still writes an auditable measurement artifact when Pass-1 produced expected signal IDs, even if finalize did not run;
2. processing and Task-122 context metrics are emitted from their available evidence;
3. graph fields that would incorrectly characterize an uncommitted run are fail-closed/unrankable rather than computed from the unchanged baseline graph;
4. the declared final-graph miss-explanation read may still run, because it is part of Task-122's definition, but it must not make the run rankable;
5. the artifact records that finalize did not run.

If the team instead retains the existing gate, the architecture and acceptance contract must explicitly concede that Task-122 publishes no evidence for all-no-commit runs. That would materially weaken `context_build_success_rate`, so it is not recommended.

Add orchestration-level tests for:

- all expected records are `context_failed`;
- all context records are complete but every source fails after context build;
- no-finalize artifacts cannot enter scored ranking.

### 2. Important — separate builder telemetry from the versioned persistence envelope

The proposed `ContextTelemetry` contains `run_id` (`§1:29-44`), but the current builder has no `run_id` parameter and the blueprint does not add one. The builder is a pure graph-read boundary; `compile_source` is the layer that owns `ctx.run_id`. Section 4 also says the writer stamps the real run ID from `ctx`.

The persistence schema has a second split-brain:

- `schema_version` is absent from the data types and sample shape;
- §10 adds it only as a risk note;
- the success record comes from `ContextTelemetry`, while the failure record is an ad hoc dictionary;
- `status`, configured mode, and effective strategy are typed as unconstrained `str` even though they are schema enums.

Define one explicit v1 persistence contract before implementation. A clean boundary is:

```text
ContextTelemetry
    builder-owned successful event payload
    no orchestration run_id and no persistence schema metadata

ContextRecordV1
    schema_version = 1
    run_id
    source_id
    status = complete | context_failed
    telemetry fields / frozen failure defaults
```

`compile_source` should construct both success and failure records through the same typed factory/serializer, stamp `ctx.run_id`, and send the result through the same atomic writer. Keep the on-disk object flat if that is preferred; the important point is one schema and one construction path.

Also freeze the failure shape. In particular, decide whether `keys_emitted` retains the Pass-1 input keys or is empty when `status=="context_failed"`, and state the corresponding invariant. Empty `key_outcomes` alone does not answer this.

This keeps orchestration identity out of the context builder, makes `"schema_version": 1` real rather than aspirational, and prevents the direct failure dictionary from drifting away from successful records.

### 3. Important — specify a strict v1 loader and make reconciliation a typed boundary

`_gather_context_records(run_dir/context/)` is currently asked to validate the run ID and count unexpected sources (§5:89), but its signature receives neither the expected run ID nor the expected source set. The expected IDs are derived only on the following line. More importantly, “validate well-formedness” is too loose for evidence that deliberately fails all aggregates closed.

Split loading from reconciliation:

```text
load_context_records(context_dir, expected_run_id)
    -> parsed ContextRecordV1 values + load/integrity errors

reconcile_context_records(records, expected_ids, header.p2_attempted)
    -> typed ContextEvidence
       {matched records, coverage, complete, error counts/reasons}
```

The v1 parser should reject, rather than coerce:

- a missing/unsupported `schema_version`;
- missing or wrong-typed run/source IDs and enum values;
- negative or boolean-as-integer counts;
- a `complete` record whose `key_outcomes` are not positionally aligned one-for-one with `keys_emitted`;
- an unresolved outcome with a non-null canonical target, or a resolved disposition without one;
- a `target_first_run_id` that is neither null nor a nonempty string (normalize an empty graph stamp to null; null means `age_unknown`, while any nonempty value is compared by equality only);
- `delivered != len(slugs)`, `delivered > candidates`, or total delivered above `page_cap`;
- a `context_failed` record that violates the frozen failure shape.

Then pin the reconciliation order:

1. derive authoritative expected signal IDs;
2. load and validate records against the requested run;
3. detect duplicate and unexpected IDs;
4. compute matched IDs and coverage;
5. compare `len(expected_ids)` with `header.p2_attempted`;
6. expose a single typed evidence value to aggregation.

Prefer passing that `ContextEvidence` object into `compute_graph` over the five parallel arguments proposed in §5:93. It makes it harder for the KPI layer to recompute completeness differently.

Coverage alone is not an adequate explanation channel: it can be `1.0` while an unexpected, duplicate, malformed, or wrong-run extra record invalidates the set. Surface at least an integrity boolean or error count in `measurements.json`/the report, even when substantive metrics are `None`; otherwise fail-closed output is opaque.

### 4. Important — late/never classification and late/never rate denominators are different concepts

Section 6 says:

```text
search_key_late_resolution_rate,
search_key_never_resolved_rate (over unresolved keys)
```

but the next line requires:

```text
resolved + late + never == emissions
```

Those statements are compatible for counts, not for rates, if late and never are divided only by unresolved keys. The ratified options' arithmetic requires one emission denominator.

Freeze the equations over complete records:

```text
N = all emitted keys
R = dispositions resolved_at_load
L = unresolved_at_load that resolve on the final read
V = unresolved_at_load that remain unresolved

R + L + V == N

search_key_resolved_at_load_rate = R / N
search_key_late_resolution_rate  = L / N
search_key_never_resolved_rate   = V / N
```

The final graph query is **performed only for unresolved-at-load keys**; the public late/never rates are still divided by all emitted keys. Likewise, pre-run/cohort/age-unknown counts partition `R`, but their public rates use `N`, so their sum equals `search_key_resolved_at_load_rate`.

When `N == 0`, every key rate is `None`. When `N > 0`, any zero numerator is `0.0`. Pin both identities with `pytest.approx`.

### 5. Moderate — “precedence exists exactly once” needs an implementable resolver design

Section 2 proposes two enriched cores:

- a simple-query implementation;
- a separate batch-query implementation.

It then says precedence and active-target rules exist exactly once. Today those rules are already implemented differently: Python branching in `resolve_to_canonical_slugs` and a Cypher `CASE` in `resolve_to_canonical_slugs_batch` (`kdb_graph/queries.py:459-566`). Merely projecting the legacy APIs over two new enriched functions removes duplication from the public slug-only wrappers, but it does not make precedence single-sourced.

Choose one accurate contract:

- have both query shapes return neutral resolution rows and feed one shared Python row classifier that chooses canonical slug plus provenance stamp; or
- retain two independent enriched implementations and describe parity tests as the drift control, without claiming precedence exists once.

The first is architecturally cleaner if Kuzu can return a common row shape without sacrificing the batch escape hatch. Either choice is acceptable, but the blueprint should not promise a property the implementation shape does not provide.

### 6. Moderate — tighten the test seams and freeze the pre-change prompt fixture

The test plan is strong but needs these concrete amendments:

- resolver coverage belongs primarily in the existing `kdb_graph/tests/test_queries_context.py` and `compiler/tests/test_t2_resolver_parity.py`, not only the generic `kdb_graph/tests/test_queries.py`;
- add strict parser tests for every required field, enum, integer type, cross-field invariant, schema version, and failure-record shape;
- add the no-finalize orchestration cases from Finding 1;
- add an integrity-output assertion for coverage `1.0` plus an unexpected/duplicate extra record;
- create and review the pre-Task-122 prompt text/hash fixture **before** changing `build_context_snapshot`; do not generate the expected bytes through the post-change implementation at test time;
- pin that the prompt identity check covers structured, explicit-empty, legacy, layered, and empty-graph paths, or explain why a smaller set is sufficient.

## What is already approved in principle

The following parts do not need redesign:

- the dedicated `context/` namespace and collision-safe filename;
- the two-product context result and unchanged `ContextSnapshot.to_dict()`;
- the five per-key dispositions and pre-cap `search_key_t2_seed_rate`;
- complete-only tier/key populations plus record-inclusive coverage;
- all-delivered tier slug lists and shared-cap arithmetic;
- equality-only cohort classification with an honest unknown residual;
- two declared final-graph reads;
- warn-only record persistence failure;
- Pass-1 board surfacing for ranked, partial, and fallback rows;
- retaining `entity_search_key_resolution` unchanged and unscored.

## Required amendments before Proceed

- Define no-finalize KPI emission and prevent such artifacts from becoming scored/rankable.
- Introduce one versioned context-record contract and one success/failure serializer; keep `run_id` ownership at `compile_source`.
- Freeze strict record validation, reconciliation order, failure-record shape, and a typed aggregation boundary.
- Define every search-key rate over the all-emissions denominator while limiting only the late/never query population to unresolved-at-load keys.
- Make the simple/batch resolver sharing claim match the actual implementation strategy.
- Extend TDD coverage for no-finalize emission, strict schema integrity, observable integrity failure, and a genuinely pre-change prompt fixture.

## Verification performed

Read-only baseline verification through the project virtual environment passed:

```text
kdb_graph/tests/test_queries_context.py
compiler/tests/test_t2_resolver_parity.py
compiler/tests/test_context_loader.py
compiler/tests/test_compile_source.py
```

The first attempt through the system interpreter stopped during collection because that interpreter lacks the optional `google` package; rerunning through `.venv/bin/pytest` passed all selected tests. No product code was changed.

## Recommendation

Revise the blueprint to v0.2 with the amendments above, then return directly for a focused blueprint re-review. The architecture is converged; the remaining work is to make the failure path observable, the persisted evidence schema singular and strict, and the published rate identities mathematically unambiguous.
