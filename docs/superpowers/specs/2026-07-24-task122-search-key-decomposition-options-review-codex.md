# Codex review — Task #122 search-key decomposition options v1.0

**Reviewed:** 2026-07-24  
**Artifact:** `docs/superpowers/specs/2026-07-24-task122-search-key-decomposition-options.md`  
**Verdict:** **REVISE before Joseph's pick**

## Executive assessment

The spec identifies a real defect: the legacy final-graph resolution rate cannot distinguish a canonical target that predates the run from one created by the run. Option 1 remains the smallest architecture for a **final-target-age decomposition**, and keeping the legacy per-emission rate is the right compatibility choice.

Four load-bearing details need correction before selection:

1. run IDs must be compared for equality, not ordered lexically;
2. a final resolution to an older canonical target is not proof that the key retrieved that target before Pass-2;
3. Options 2 and 3 are not currently described with equivalent semantics;
4. Pass-1-board surfacing needs an explicit data path because that board deliberately recomputes from `run_state/` and drops emit-time watched values.

## Findings

### 1. Important — `first_run_id < run_id` is not a valid or exhaustive classifier

Spec lines 25 and 42 define:

- pre-cohort: `first_run_id < current run_id`;
- during-cohort: `first_run_id == current run_id`.

`run_id` is an identity token, not a declared ordered type. The normal conductor currently generates timestamp-shaped IDs (`common/run_context.py:46-59,74-79`), but graph APIs, rebuild fixtures, tests, and migration tooling legitimately use values such as `run-1`, `r1`, `m`, and `task64-migration-...`. Lexical ordering is therefore an accidental property of one producer.

It also leaves a resolved target whose stamp sorts after the current ID out of all three buckets, contradicting the partition identity in line 51.

The graph write contract already provides the required binary fact: `_upsert_entity` stamps `first_run_id=$run_id` only on create and never overwrites it (`kdb_graph/intake.py:293-319`). Classify by:

```text
during_current_run := canonical_first_run_id == current_run_id
preexisting_target := canonical_first_run_id != current_run_id
unresolved          := no final canonical resolution
```

No ordering operation is needed. The revised spec should also declare a policy for a resolved canonical target with a null, empty, or wrongly typed stamp. Because the design treats this field as canonical provenance, the high-integrity policy is to reject KPI emission with a bounded, typed diagnostic rather than silently assign invented provenance. `maybe_emit_kpis` already contains emission failures without aborting the orchestration run (`orchestrator/emit_kpis.py:178-222`). This is a new diagnostic failure mode, so Option 1 should not claim “failures: none new.”

### 2. Important — bucket 1 measures final target age, not actual retrieval

The context and recommendation repeatedly equate bucket 1 with “retrieval value.” Option 1 cannot establish that.

Search keys are resolved for T2 before the Pass-2 call (`compiler/context_loader.py:419-437`). The proposed KPI resolves them later against the final graph. During intake, the same run can create an alias row and `ALIAS_OF` edge pointing to a canonical entity whose `first_run_id` is old (`kdb_graph/intake.py:633-665`). A key that did not resolve at context-load time can therefore resolve after the run to an older canonical target and land in bucket 1.

That bucket is still useful, but its honest meaning is:

> Fraction of emitted keys whose **final active canonical target** was materialized before the current run.

It measures pre-existing-target realization/convergence, not proof of pre-call retrieval or context use.

The spec needs an explicit semantic decision:

- If Task #122 is the small **final-target-age decomposition**, retain Option 1 and remove the retrieval-effectiveness claim.
- If the requirement is **actual retrieval effectiveness**, record per-source resolution at context-load time (including raw key, canonical target, and whether it entered T2). Neither a final `first_run_id` query nor a run-start canonical inventory proves this.

The first interpretation matches the filed task and is my recommendation, but Joseph should ratify that meaning knowingly.

### 3. Important — Options 2 and 3 need semantically accurate tradeoffs

Option 2 snapshots **active** canonical slugs and calls absence from that set “materialized during cohort.” An older inactive/orphan candidate can be revived during the run; it was not newly materialized, but this option would classify it as bucket 2. To compare target-age architectures, snapshot all pre-run canonical entity identities, not only active ones. If Option 2 instead intends retrieval availability, it must snapshot the complete alias-aware active resolution state and say that it measures a different thing.

Option 3 says it persists resolution inputs at run time, then rejects the approach because the graph is gone at score time. If the persisted facts include the raw key, final canonical target, and canonical `first_run_id`, the design **does** survive graph reset. Its real disadvantages are a new raw-facts artifact/schema, delayed aggregation/version coupling, no decomposition for historical runs lacking the facts, and additional score-time logic. If it persists only raw keys, it is indeed impossible after reset. Define which design is being evaluated.

The revision should make all options target the same selected semantic contract before weighing simplicity and reversibility.

### 4. Important — Pass-1-board surfacing is not data-driven and needs explicit plumbing

The spec correctly notes that the combined report/leaderboard carries new watched fields automatically, but line 45 and the acceptance sketch understate the Pass-1-board work.

For normal rows, `tools/benchmark/pass_boards.py:_build_row` reconstructs `raw_values` from `run_state/` processing measurements and never merges emit-time graph watched values (`pass_boards.py:163-180`). For fallback rows, `_fallback_raw` only copies diagnostic names ending in `_pass1` (`pass_boards.py:94-119`). The proposed bucket fields therefore will not appear merely because they are present in `measurements.json`.

Specify one path, for example:

```text
CLI extracts selected Task-122 watched fields per model
  -> build_pass_board(..., pass1_watched_by_model=...)
  -> _build_row merges them into Pass-1 raw_values
     for ranked, partial, and fallback/unranked rows
  -> JSON and Markdown render from the same raw_values
```

Do not rely on a `_pass1` naming suffix to smuggle graph values through a processing fallback. Add acceptance tests for both a ranked row and a fallback/unranked row so the board's symmetric evidence contract remains intact.

### 5. Moderate — avoid a third independent copy of alias-resolution precedence

The proposed resolver sibling must reproduce the current precedence and active-target rules:

```text
canonical_id target > ALIAS_OF target > direct canonical leaf
```

including dead-target fail-closed behavior (`kdb_graph/queries.py:459-517`). Copying that logic into an enriched sibling creates another implementation that can drift.

Prefer an authoritative enriched resolver (or a shared private core) returning canonical slug plus canonical target stamp, with the existing `resolve_to_canonical_slugs` API projecting only the slug. Pin projection parity across direct, `canonical_id`, `ALIAS_OF`, dead-target, duplicate-emission, and unresolved cases. The KPI must read the canonical target's stamp on every path.

### 6. Moderate — arithmetic and field contracts need precision

Lines 28 and 51 say `b1+b2 == legacy metric exactly` and `b1+b2+b3 == 1`. The **count partition** can and should be exact:

```text
n_preexisting + n_during + n_unresolved == n_emissions
n_preexisting + n_during == n_resolved
```

Separately computed floating-point rates should be tested with `pytest.approx`, not bit equality. Preserve the legacy formula as `n_resolved / n_emissions` so its emitted value and history remain continuous.

The blueprint should also freeze the three public watched-field names and state that they are rates, not counts. “b1/b2/b3” is not yet a durable artifact contract.

## Required amendments before selection

- Replace all ordered run-ID comparisons with equality/complement and define invalid-stamp behavior.
- Decide whether Task #122 measures final target age or actual context-load retrieval; align every option and label to that decision.
- Correct Option 2's inventory semantics and Option 3's reset-survival analysis.
- Define stable watched-field names and exact count-based partition logic.
- Make the enriched resolver share one precedence implementation with the legacy resolver and pin parity.
- Specify Pass-1-board plumbing for ranked and unranked rows.
- Extend acceptance with:
  - non-orderable identifier examples (`m`, `r1`, timestamp-shaped current ID);
  - invalid canonical stamp behavior;
  - direct, `canonical_id`, `ALIAS_OF`, and dead-target stamp resolution;
  - duplicate per-emission weighting;
  - exact count identities and approximate rate identities;
  - `emit_run_kpis` forwarding the current `run_id`;
  - persisted `measurements.json`, combined report/leaderboard, and Pass-1-board JSON/Markdown coverage.
- At ratification, link the chosen spec from `docs/TASKS.md` and add the selected semantic contract to `docs/CODEBASE_OVERVIEW.md` before Proceed.

## Recommendation

Revise around **Option 1 as a final-target-age decomposition**, using current-run equality, per-emission weighting, the legacy mixed rate, and explicit Pass-1-board surfacing. This preserves the intended 80/20 change and makes the metric materially more honest without claiming observability it does not have.

If Joseph's actual question is “did Pass-1 cause Pass-2 to retrieve useful existing context?”, stop and choose a context-load telemetry architecture instead; Option 1 cannot answer that question after the fact.
