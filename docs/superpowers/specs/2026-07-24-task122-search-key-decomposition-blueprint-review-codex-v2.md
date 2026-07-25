# Codex re-review — Task #122 event-time context capture blueprint v0.2

**Reviewed:** 2026-07-24  
**Artifact:** `docs/superpowers/specs/2026-07-24-task122-search-key-decomposition-blueprint.md`  
**Architecture baseline:** options v1.3 + D-122  
**Prior review:** `docs/superpowers/specs/2026-07-24-task122-search-key-decomposition-blueprint-review-codex.md`  
**Verdict:** **REVISE — R1 is substantively absorbed; close the remaining executable interfaces before Proceed**

## Executive assessment

v0.2 resolves the architectural substance of the first review:

- builder telemetry no longer owns orchestration identity;
- one versioned persistence envelope is intended for success and failure;
- the resolver now has one shared precedence classifier;
- strict validation, typed reconciliation, and observable integrity are explicit goals;
- every public key rate uses the all-emissions denominator;
- the pre-change prompt fixture is frozen before implementation;
- no-finalize evidence is no longer silently discarded in the intended lifecycle.

The architecture remains converged, and no new options round is needed.

Three implementation contracts are still incomplete:

1. setting graph KPIs to `None` does not actually keep a no-finalize artifact out of the current combined scorer;
2. the proposed typed record/evidence API is not yet a complete or layer-safe interface;
3. the `context_failed` schema still leaves several required fields and types undefined.

Two moderate clarifications are also needed for zero-expected integrity semantics and Pass-1-board surfacing.

## R1 absorption

| R1 finding | v0.2 assessment |
|---|---|
| F1 — no-finalize evidence suppressed | **Direction absorbed; execution incomplete.** Emission is widened, but scorer/pass-board eligibility and graph watched-field handling need an exact route. |
| F2 — telemetry/persistence split | **Mostly absorbed.** `run_id` ownership and schema version are corrected; the record class/failure metadata remain incomplete. |
| F3 — strict loader/reconciliation | **Mostly absorbed.** Strict rules and typed evidence are present; rejected-record errors are dropped by the proposed function signatures, and type placement would invert the package dependency. |
| F4 — late/never denominator | **Fully absorbed.** |
| F5 — resolver precedence duplicated | **Fully absorbed.** Neutral rows plus one Python classifier is an executable design. |
| F6 — test seams/prompt fixture | **Fully absorbed in intent.** Add the remaining eligibility/layer-boundary cases below. |

## Findings

### 1. Important — make the no-finalize artifact unrankable through an explicit consumer gate

Section 7 says:

- Task-122 context metrics are computed;
- graph scored/watched fields are `None`;
- `finalize_ran: false` is recorded;
- the artifact is excluded from ranking.

Those statements do not yet form one executable contract.

First, Task-122 fields themselves live in `graph.watched` (§6). Therefore “graph scored/watched fields emit `None`” (§7:149) would also erase the context metrics that §7:148 says must be emitted. Freeze a field-level policy rather than nulling the whole graph section:

```text
no finalize:
    graph.scored:
        finalized-run graph-quality fields -> None
    graph.watched / graph.diagnostic:
        Task-122 event-time fields + integrity -> retained
        finalized-run-dependent fields -> None
        legacy final-graph resolution -> explicitly retained or explicitly None
```

Second, the miss-explanation read cannot be optional if late/never fields remain public. “MAY still run” (§7:150) permits two identical runs to emit different values. Choose one deterministic rule. The coherent choice is to run the unresolved-key batch read even without finalize—the graph is unchanged, which is exactly the final state for that failed run—and preserve `R + L + V == N`.

Third, the current combined scorer will still rank this artifact. `tools/benchmark/cli.py:403-430` gathers scored values across all tiers, and `compiler/kpi/score.py:327-336` deliberately prorates missing KPIs. A no-finalize artifact with graph scores `None` but valid processing scores remains rankable. The Pass-1 board can also rank it because that board does not require graph KPIs.

Specify the eligibility gate at every consumer, not only in tests:

1. add `finalize_ran: bool` to `RunMeasurementHeader`, set it explicitly for new runs, and backfill historical headers as `True`;
2. type-check it as a real bool;
3. make `_score_command` test the flag before constructing the `models` input to `score_models`;
4. make `_build_row` apply the same flag to both pass boards;
5. define how unranked evidence is represented in the main leaderboard, which currently has no combined-board `unranked` collection;
6. define replacement semantics when a new no-finalize artifact has the same provider/model/release key as an older rankable run—an unrankable run must not silently overwrite the last valid ranking pointer unless that is explicitly desired.

The smallest alternative is for `kdb-benchmark score` to reject/skip `finalize_ran=false` inputs with a clear message, leaving the artifact's own `report.md` as its audit surface. If the intended contract is “unranked evidence in all three boards,” then add that payload/rendering behavior explicitly. Either is sound; prorating it into the ranking is not.

Add assertions against the **combined** leaderboard and both pass boards. Testing only that graph fields are `None` will not catch this defect.

### 2. Important — complete the typed API and place shared evidence below the orchestrator layer

Section 1 names `ContextRecordV1`, but the only proposed implementation is:

```python
def build_context_record_v1(...) -> dict:
```

Section 5 then returns `list[ContextRecordV1]` from the loader, although no class, `TypedDict`, parser constructor, or serializer for that name is defined.

The loader/reconciler signatures also lose evidence:

```text
load_context_records(...) -> (records, list[IntegrityError])
reconcile_context_records(records, expected_ids, p2_attempted) -> ContextEvidence
```

Because the second function receives only valid records, it cannot populate its promised `malformed` or `wrong_run` counts; those rejected inputs exist only in the discarded `IntegrityError` list.

Finally, if `ContextEvidence` is defined in `orchestrator/emit_kpis.py` as §5 currently implies, `compiler/kpi/graph.py` cannot import it without creating the forbidden `compiler -> orchestrator` dependency. The package-boundary guard allows `orchestrator -> compiler`, never the reverse.

Freeze the lower-layer types and preserve the load result:

```text
compiler/context_record.py
    ContextRecordV1
    ContextIntegrityIssue
    ContextLoadResult
    ContextIntegrity
    ContextEvidence
    parse_context_record_v1(raw) -> ContextRecordV1
    build_context_record_v1(...) -> ContextRecordV1

orchestrator/emit_kpis.py
    load_context_records(...) -> ContextLoadResult(records, errors)
    reconcile_context_records(load_result, expected_ids, p2_attempted)
        -> ContextEvidence
```

`ContextRecordV1.to_dict()` should be the only serialization path used by the writer. `compute_graph` can then import `ContextEvidence` from its own package (or the types can live in `common`, if the team deliberately wants the wider shared contract) without a reverse dependency.

Add the package-boundary test to the P2 gate, plus a test showing that one malformed and one wrong-run file survive loading as integrity counts even though neither becomes a parsed record.

### 3. Important — finish the conditional v1 schema for `context_failed`

The blueprint now freezes keys, outcomes, tiers, mode, and strategy for a failed build, but `build_context_record_v1(..., request_meta: ...)` is still a placeholder. A flat v1 record also requires:

- `source_id`;
- `candidate_universe_size`;
- `domain_scope`;
- `cold_start`;
- `max_hops`;
- `page_cap`.

Several are not observable if the builder raises before reaching their computation. Supplying ordinary successful-record values would create false event facts even though the failed record is excluded from substantive aggregation.

Replace `request_meta: ...` with an exact typed failure input and freeze every field. Prefer honest nullability for observations that never completed:

```text
context_failed:
    source_id                 request-known
    configured_t2_mode       request-known
    effective_t2_strategy    derived from mode/frontmatter before graph reads
    keys_emitted             Pass-1 frontmatter keys
    key_outcomes             []
    t1/t2/t3                 frozen zero sentinel records
    candidate_universe_size  None
    domain_scope             request-known
    cold_start               None
    max_hops                 None
    page_cap                 request-known
```

If zero/false sentinels are preferred instead, state each value and state that they mean “not observed” only when `status=="context_failed"`. Nulls are less likely to be mistaken for measurements.

Also replace the remaining unconstrained strings with aliases in the shared contract:

```text
ConfiguredT2Mode = Literal["structured", "layered", "legacy"]
EffectiveT2Strategy = Literal[
    "structured_keys", "explicit_empty", "legacy_regex", "layered_union"
]
ContextStatus = Literal["complete", "context_failed"]
```

Normalize an empty graph `first_run_id` to `None` in the resolver/classifier before record construction; the strict parser should reject an empty persisted stamp rather than silently normalize data while loading it.

### 4. Moderate — prevent the zero-expected case from becoming vacuously complete

Section 5 defines:

```text
complete := matched == expected AND zero integrity errors
```

When both sets are empty, that is `True`. The ratified options instead freeze zero expected IDs as:

- coverage `None`;
- all substantive aggregates `None`;
- never a vacuous successful evidence set.

Make the predicate explicit:

```text
evidence_complete :=
    bool(expected_ids)
    AND matched_ids == expected_ids
    AND zero integrity errors
```

Also add `missing` to the integrity counts. Otherwise coverage can reveal a missing record while `context_integrity_ok` remains `True`. Freeze public diagnostic names and zero-source behavior, for example:

```text
context_integrity_ok: bool | None  # None when expected_ids is empty
context_missing_record_count
context_malformed_record_count
context_duplicate_record_count
context_unexpected_record_count
context_wrong_run_record_count
context_expected_count_mismatch
```

The exact names may differ, but the report and Pass-1 raw-values contract need a stable schema.

### 5. Moderate — restore the explicit Pass-1-board surfacing interface

v0.1 specified the implementation path:

```text
CLI extracts Task-122 watched fields per model
    -> build_pass_board(..., pass1_watched_by_model=...)
    -> _build_row merges them into ranked, partial, and fallback Pass-1 raw_values
```

v0.2 retains board tests and says “boards” in P2, but the technical interface itself has disappeared. The current `tools/benchmark/cli.py` and `pass_boards.py` do not automatically carry arbitrary `search_key_*`/`context_*` diagnostics into Pass-1 rows.

Restore the explicit interface, including:

- the new integrity diagnostics;
- ranked and partial rows;
- measurements fallback rows;
- JSON and Markdown from the same `raw_values`;
- the selected no-finalize behavior from Finding 1.

This is not a new design request; it preserves the ratified options §7 and prevents the implementation plan from treating the board tests as self-explanatory plumbing.

## What is now ratifiable in principle

No further change is needed to:

- the event-time measurement boundary;
- the two-product prompt/telemetry split;
- resolver neutral rows and one shared precedence classifier;
- per-key dispositions and cap-pressure semantics;
- all-emissions key-rate equations;
- tier candidate/delivered meanings;
- complete-only substantive aggregation;
- strict reject-never-coerce parsing policy;
- equality-only cohort classification;
- the pre-change multi-mode prompt fixture;
- the dedicated sidecar namespace and warn-only writer failure.

## Required v0.3 amendments

- Specify the no-finalize field allowlist, make the miss query deterministic, and add explicit combined/pass-board eligibility gates with replacement semantics.
- Define `ContextRecordV1`, `ContextIntegrityIssue`, `ContextLoadResult`, `ContextIntegrity`, and `ContextEvidence` as real lower-layer types; pass loader errors into reconciliation.
- Replace `request_meta: ...` with an exact failure-record input and freeze all success/failure field types and nullability.
- Make zero expected IDs ineligible for a “complete” evidence set and publish stable missing/integrity diagnostics.
- Restore the explicit Pass-1-board data path from watched fields to every row shape.

## Verification performed

The following existing baseline seams passed through `.venv/bin/pytest`:

```text
tools/benchmark/tests/test_score.py
tools/benchmark/tests/test_pass_boards.py
tools/tests/test_package_boundaries.py
orchestrator/tests/test_kdb_orchestrate.py (emit-kpis selection)
```

The current no-compiled-source test confirms the lifecycle seam under review: finalize is skipped and KPI emission currently returns without writing `measurements.json`. No product code was changed.

## Recommendation

Revise narrowly to v0.3, then return for a final focused blueprint review. The event-time architecture and metric math are ready; the remaining work is to make the new evidence types compile across package boundaries and to ensure no-finalize artifacts are excluded by the actual scoring consumers rather than by convention.
