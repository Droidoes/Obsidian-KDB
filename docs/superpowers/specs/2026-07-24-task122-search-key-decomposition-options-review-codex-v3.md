# Codex review — Task #122 search-key decomposition options v1.2

**Reviewed:** 2026-07-24  
**Artifact:** `docs/superpowers/specs/2026-07-24-task122-search-key-decomposition-options.md`  
**Verdict:** **REVISE — architecture converged; close the completeness and denominator contracts before ratification**

## Executive assessment

v1.2 absorbs both critical R2 findings and nearly all remaining feedback:

- context records now have a dedicated, collision-safe namespace;
- prompt-facing and telemetry-facing context are separate products;
- resolver success is separated from T2 seeding;
- final-graph reads are explicitly bounded;
- candidate and delivered tier counts are distinct;
- the event-time truth table is corrected;
- both resolver implementations and every effective T2 strategy are covered;
- all Task-122 fields share one Pass-1-board path.

The event-time architecture is the right one. No return to the post-run design and no new architecture-options round is needed.

Two load-bearing contracts remain incomplete:

1. coverage by count is not enough to prove record-set completeness;
2. `context_failed` records count as valid coverage but have no defined role in substantive means/rates.

There is also one semantic naming issue: entering the T2 seed set does not guarantee surviving the shared page cap into the prompt.

## R2 absorption

| R2 finding | v1.2 assessment |
|---|---|
| F1 — sidecar namespace collision | **Absorbed**: dedicated `context/`, safe ID, atomic write, coexistence test |
| F2 — prompt contamination | **Absorbed**: `ContextBuildResult(snapshot, telemetry)` and prompt byte/hash pin |
| F3 — resolver hit vs T2 contribution | **Mostly absorbed**: dispositions are sound; page-cap meaning needs one correction |
| F4 — lifecycle/completeness | **Mostly absorbed**: coverage and fail-closed aggregates added; source-set and failed-record semantics remain |
| F5 — candidate vs delivered tiers | **Absorbed in KPI names**; raw-record slug shape needs clarification |
| F6 — cold-graph truth | **Absorbed** |
| F7 — modes and batch resolver | **Absorbed** |
| F8 — surfacing/final reads/gate | **Mostly absorbed**; North-Star update is still scheduled too late |

## Findings

### 1. Important — completeness must reconcile source identities, not only counts

Section 5 defines:

```text
context_record_coverage = unique_valid_records / p2_attempted
```

and says malformed, duplicate, and wrong-run records are detected. That ratio can still be `1.0` while the evidence set is invalid:

- one expected source is missing and one unexpected source substitutes for it;
- all expected sources exist plus an extra duplicate or unexpected record;
- a malformed or wrong-run extra record exists alongside a complete valid set.

In each case, `unique_valid_records == p2_attempted` can hold while evidence-integrity errors remain. Coverage equality must not be the sole “complete” predicate.

The Pass-1 sidecars already provide the authoritative final signal-source IDs. Reconcile exact sets:

```text
expected_ids := source_ids whose final Pass-1 envelope is signal
matched_ids  := valid context-record source_ids ∩ expected_ids

coverage := len(matched_ids) / len(expected_ids)
complete :=
    matched_ids == expected_ids
    AND no duplicate ids
    AND no unexpected ids
    AND no malformed records
    AND no wrong-run records
```

Use `header.p2_attempted` as a count cross-check against `len(expected_ids)`, not as a replacement for identity reconciliation. Any mismatch or integrity error makes the new substantive aggregates `None`, even if numerical coverage is `1.0`.

Freeze the zero-source case: when `expected_ids` is empty, `context_record_coverage` should be `None` and every substantive Task-122 aggregate should be `None`; do not publish a vacuous `1.0`.

Extend acceptance with missing, substituted, duplicate, unexpected, malformed, wrong-run, and zero-expected cases.

### 2. Important — `context_failed` is valid telemetry coverage but not a zero-valued context

v1.2 correctly writes a `context_failed` record when the builder raises, so the record set remains auditable. However:

- Section 5 counts that record as valid coverage;
- section 4 says the key denominator is sources “with a context record”;
- the failed record has zero tiers and no key outcomes.

If it enters the substantive population, tier means silently treat a context-build failure as a legitimate empty context, and key partition identities cannot account for the source's emitted keys. If it is excluded without a declared denominator, comparisons drift silently.

Separate **record completeness** from **measurement eligibility**:

```text
record coverage population:
    every expected Pass-1 signal source, including context_failed

substantive metric population:
    status == complete only
```

Publish a frozen `context_build_success_rate = complete_records / expected_records` (or an equivalent failure count). Compute tier means and key rates only over complete records. A context-build failure is already a Pass-2 quarantine signal; it must not masquerade as a valid zero-context observation.

If there are expected records but zero complete records, substantive means/rates are `None`. State explicitly that a later model/validation/canonicalization/commit failure does **not** exclude a record: its context build was complete and the event-time evidence remains valid.

Also specify that `compile_source` synthesizes the `context_failed` record in the builder-exception path; no `ContextTelemetry` object can be returned by a function that raised.

### 3. Important — a T2 seed may still be capped out before the prompt

`resolved_t2_seed` correctly means the key survived resolution, scope, T1 exclusion, and key dedup. But the shared ranking cap is applied afterward. A T2 seed can be excluded when higher-priority T1 rows consume the page budget.

Therefore `search_key_t2_contribution_rate` overclaims what reached Pass-2. Choose one:

- **Simplest:** rename it `search_key_t2_seed_rate` and define it as pre-cap seeding. Use `context_t2_delivered_mean` for what the prompt actually received.
- **More detailed:** split dispositions into delivered versus capped T2 seeds and retain a true contribution/delivery rate.

The first choice matches the 80/20 design. Add a cap-pressure test: T1 fills the cap, a key becomes a valid T2 seed, but `t2.delivered == 0`. The key must not be described as prompt-delivered.

For consistency, rename the age fields before they become public:

```text
search_key_resolved_pre_run_rate
search_key_resolved_cohort_rate
search_key_resolved_age_unknown_rate
```

They partition `search_key_resolved_at_load_rate`; “hit” is now an unnecessary second term.

### 4. Moderate — freeze what the raw record's tier slug arrays contain

The KPI names clearly distinguish `candidates` and `delivered`, but the sample record's `slugs`/`slugs_overflow` fields do not say which population they sample. T1 has no overflow field, while T2/T3 do, and only T3 claims a bound.

Prefer the smallest record:

```text
tN:
  candidates: <count>
  delivered: <count>
  slugs: <all delivered slugs, in prompt rank order>
```

The three delivered lists together are already bounded by the shared `page_cap`, so no overflow fields are required. If candidate samples are needed, name them `candidate_slugs_sample`, bound every tier consistently, and include an overflow count for every tier.

Pin that the sum of delivered tier counts equals `len(snapshot.pages)` and never exceeds `page_cap`.

### 5. Important — move the documentation gate ahead of the blueprint

The header says the candidate awaits Joseph's ratification and then moves to blueprint. Section 8 schedules the North-Star and task-ledger updates in implementation P2. That violates the project state machine: the chosen architecture must enter `docs/TASKS.md` and `docs/CODEBASE_OVERVIEW.md` before exiting Architecture.

After Joseph ratifies the corrected candidate:

1. update the stale Task #122 row from the v1.0 post-run decomposition to the event-time contract;
2. add the event-time capture decision and metric meanings to the North Star;
3. only then start the blueprint.

Do not defer either update to implementation.

### 6. Minor — correct the version/status wording

- Line 6 says v1.2 supersedes “v1.0/v1.1 (post-run decomposition),” but v1.1 already used context-load capture. Say v1.0's post-run architecture was rejected and v1.2 supersedes the incomplete v1.1 capture contract.
- Line 12 calls the direction “ratified,” while line 3 says the candidate awaits ratification. Distinguish Joseph's selected **event-time direction** from the still-unratified detailed contract.
- The acceptance list should explicitly pin warn-only record-write failure, `context_failed` aggregation behavior, exact expected-ID reconciliation, and candidate/delivered cap arithmetic.

## Required amendments before ratification

- Define exact expected-source-set reconciliation and a completeness predicate independent of the coverage ratio.
- Separate record coverage from complete-context metric eligibility; publish context-build success/failure evidence.
- Rename T2 “contribution” to pre-cap “seed,” or measure actual delivered contribution.
- Freeze tier slug-array semantics and delivered-count invariants.
- Move the task-ledger and North-Star updates to the post-ratification Architecture gate, before blueprint work.
- Correct the status/version wording and extend the acceptance cases above.

## Recommendation

Revise narrowly, then ratify the **context-load capture** architecture. The architectural boundary is settled; the remaining work is to make the evidence set total, the denominators honest, and the public names say exactly what was observed.
