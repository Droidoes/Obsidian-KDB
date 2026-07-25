# Codex re-review — Task #122 event-time context capture blueprint v0.3

**Reviewed:** 2026-07-24  
**Artifact:** `docs/superpowers/archive/specs/2026-07-24-task122-search-key-decomposition-blueprint.md`  
**Architecture baseline:** options v1.3 + D-122  
**Prior review:** `docs/superpowers/archive/specs/2026-07-24-task122-search-key-decomposition-blueprint-review-codex-v2.md`  
**Verdict:** **REVISE — nearly ratifiable; correct the no-finalize lifecycle truth and finish the concrete record type**

## Executive assessment

v0.3 resolves the principal R2 concerns:

- no-finalize artifacts now have an explicit score-input skip gate;
- historical `finalize_ran` compatibility is declared;
- Task-122 fields survive field-level graph fail-closing;
- the miss read is deterministic;
- loader issues reach reconciliation;
- shared evidence types live below the orchestrator layer;
- failure-only observations are honestly nullable;
- zero-expected evidence is not vacuously complete;
- the Pass-1 board interface is restored.

The metric architecture, resolver plan, reconciliation math, and score-exclusion direction are ready.

Two load-bearing lifecycle/type issues remain:

1. `finalize_ran=False` does **not** prove that the graph is unchanged;
2. no-finalize packaging can copy a stale prior run's `compile_result.json`.

The v1 dataclass also remains represented by an ellipsis, leaving its conditional nullability and factory invariants to implementation-time interpretation.

## R2 absorption

| R2 finding | v0.3 assessment |
|---|---|
| F1 — no-finalize consumer eligibility | **Mostly absorbed.** The explicit score skip is sound; the “graph unchanged” premise and artifact packaging are not. |
| F2 — typed API/layer inversion | **Mostly absorbed.** Type placement and error flow are correct; the named types still need complete field definitions. |
| F3 — failed-record schema | **Mostly absorbed.** Known/unknown values are frozen; the actual record type and factory state invariant remain implicit. |
| F4 — zero expected/integrity schema | **Fully absorbed.** |
| F5 — Pass-1 board path | **Fully absorbed.** |

## Findings

### 1. Important — `finalize_ran=False` means “unfinalized,” not “unchanged graph”

Section 7 states:

```text
finalize_ran=False ⇔ zero committed sources ⇔ graph unchanged from baseline
```

The current commit state machine has explicit counterexamples:

- `_commit_source` performs Kuzu graph sync before the manifest boundary;
- if the manifest write then fails, it returns `failure_stage="manifest_post_graph"` with `graph_committed=True` (`orchestrator/kdb_orchestrate.py:130-149`);
- the caller aborts the run and skips finalize (`:815-831`, `:875-912`);
- `finalize_stats` remains `None`, so the proposed header says `finalize_ran=False` even though the graph has changed.

The same issue can occur after earlier sources committed successfully and a later source hits the post-graph failure. A failure inside `_finalize` can also leave some finalize mutations applied before `finalize_stats` is assigned. Reconcile operations may mutate the graph in a run that has no accumulated compile results.

Correct the contract to:

```text
finalize_ran=False:
    the run did not complete the finalize boundary;
    graph state may be unchanged, partially committed, post-graph residual,
    reconciled, or partially finalized;
    therefore finalized-run graph quality is ineligible and remains None.
```

The score skip remains exactly right under this stronger truth.

The deterministic unresolved-key read can also remain, but describe it accurately: it reads the **actual post-run graph state**, complete or partial, solely to classify whether an event-time miss became resolvable later in the run. It never makes the artifact rankable and never redefines the load-time result. `R + L + V == N` still holds.

Add integration coverage for at least:

- zero commits/all context failures — unchanged graph;
- `manifest_post_graph` on the first source — residual graph, no finalize;
- one successful source followed by `manifest_post_graph` — partially committed graph, no finalize;
- a finalize exception after a mutation, if that path can be injected deterministically.

These cases should all emit audit evidence, retain Task-122 fields, fail-close finalized graph KPIs, and be skipped by score.

### 2. Important — no-finalize emission must not package a stale finalized output

The widened emitter currently copies:

```text
state_root/compile_result.json
vault/KDB/wiki/
```

into every benchmark artifact (`orchestrator/emit_kpis.py:158-174`). `compile_result.json` is written only by `_finalize` (`orchestrator/kdb_orchestrate.py:188-221`) and is a stable top-level state file, not a run-scoped file.

When the current run does not finalize, an older run's `state_root/compile_result.json` may still exist. Blindly copying it would place a previous run's replay payload inside the new no-finalize artifact. That is worse than a missing artifact because it looks valid and self-contained.

Freeze packaging by status:

```text
finalize_ran=True:
    copy compile_result.json + wiki snapshot as today

finalize_ran=False:
    copy run_state/context evidence, measurement_header, report,
    prompt snapshot, and console log;
    do NOT copy compile_result.json;
    do NOT label the live wiki tree as this run's finalized output
```

The simplest policy is to omit both `compile_result.json` and `wiki/` for no-finalize artifacts. If a partial live-wiki snapshot is valuable, give it a distinct name and explicit partial-state metadata; do not reuse the finalized artifact contract.

Add a regression test that pre-seeds `state_root/compile_result.json` and wiki content with an unmistakable prior-run sentinel, executes a no-finalize run, and proves neither is packaged as current output.

Also update `emit_run_kpis`'s docstring and comments, which currently assert that finalize ran and `compile_result.json` exists.

### 3. Important — replace the remaining type ellipses with the exact v1 contract

Section 1 now places the types correctly, but:

```python
class ContextRecordV1:
    ... (typed fields per the v1 record, both statuses)

class ContextIntegrityIssue:
    # one per rejected file: path + reason kind + detail
```

still leaves the central persistence type and rejected-file type undefined. The blueprint also defines the configured/effective strategy aliases in `compiler/context_record.py`, while `common.types.ContextTelemetry` continues to type those fields as plain `str`.

Freeze the record explicitly:

```python
@dataclass(frozen=True)
class ContextRecordV1:
    schema_version: Literal[1]
    run_id: str
    source_id: str
    status: ContextStatus
    configured_t2_mode: ConfiguredT2Mode
    effective_t2_strategy: EffectiveT2Strategy
    keys_emitted: list[str]
    key_outcomes: list[KeyOutcome]
    t1: TierRecord
    t2: TierRecord
    t3: TierRecord
    candidate_universe_size: int | None
    domain_scope: str | None
    cold_start: bool | None
    max_hops: int | None
    page_cap: int
```

Then pin the status-dependent invariant:

```text
complete:
    telemetry required; failure_input forbidden;
    candidate_universe_size/cold_start/max_hops non-null

context_failed:
    telemetry forbidden; failure_input required;
    candidate_universe_size/cold_start/max_hops null;
    zero tiers and empty outcomes
```

Invalid factory combinations must raise rather than guess.

Move `ConfiguredT2Mode` and `EffectiveT2Strategy` to `common.types` (or use the Literals inline there) so `ContextTelemetry` is typed with the same vocabulary without creating `common -> compiler`. `ContextStatus` can remain persistence-local.

Define `ContextIntegrityIssue` fields and its closed reason vocabulary as well, for example path, `Literal["malformed", "wrong_run"]`, and detail. Reconciliation-derived missing/duplicate/unexpected/count-mismatch values belong in `ContextIntegrity`, as already designed.

Finally, make the strict parser enforce both sides of the conditional schema: it already rejects non-null failure observations; it must also reject a `complete` record whose candidate universe, cold-start flag, or hop count is null.

### 4. Moderate — apply `finalize_ran` validation at the raw score boundary

Adding and type-checking `RunMeasurementHeader.finalize_ran` protects `load_run_measurements`, but the combined score command reads benchmark `measurements.json` directly as a dictionary (`tools/benchmark/cli.py:386-430`) rather than constructing `RunMeasurementHeader`.

State the raw consumer rule explicitly:

```text
missing finalize_ran   -> True   # historical compatibility
type(value) is bool    -> use it
any other type         -> reject the measurements artifact
False                  -> print skip notice before updating model pointers
```

Apply the same validation while re-reading persisted leaderboard pointers, not only while incorporating new command-line inputs. If all supplied artifacts are skipped and there is no existing eligible leaderboard entry, return a clear “no rankable finalized runs” outcome.

This is a small addition, but it prevents strings such as `"false"` from bypassing or accidentally triggering the gate.

### 5. Moderate — split parser unit tests from loader/reconciliation tests

`parse_context_record_v1` and all record types now live in `compiler/context_record.py`, while §8 places all strict-parser tests in `orchestrator/tests/test_context_records.py`.

Use:

- `compiler/tests/test_context_record.py` for factory state combinations, exact serialization, strict field/type/cross-field validation, and round-trip behavior;
- `orchestrator/tests/test_context_records.py` for filesystem loading, wrong-run/malformed issue capture, duplicate/unexpected/missing reconciliation, and expected-ID matching.

Also restore the v0.2 no-finalize case where every context build completes but all sources fail later; it exercises valid substantive context evidence without a finalized output and complements the all-`context_failed` case.

## What is ready for ratification

No further design work is needed for:

- event-time capture and prompt isolation;
- the five disposition meanings;
- tier candidate/delivered arithmetic;
- resolver neutral rows and shared precedence;
- all-emissions search-key denominators;
- cohort/age partitioning;
- record completeness versus substantive populations;
- integrity field names and zero-expected semantics;
- compiler-owned evidence types and one-way package dependencies;
- Pass-1 board surfacing for eligible artifacts;
- the decision to skip no-finalize artifacts at score input.

## Required v0.4 amendments

- Replace the false no-finalize/unchanged-graph equivalence with the actual partial-state lifecycle and test its residual paths.
- Branch artifact packaging so no-finalize runs cannot inherit a stale `compile_result.json` or masquerade a live wiki tree as finalized output.
- Fully enumerate `ContextRecordV1` and `ContextIntegrityIssue`, type `ContextTelemetry` with the shared Literals, and freeze factory/parser state invariants.
- Validate `finalize_ran` at the raw benchmark-score boundary, including historical default and wrong-type behavior.
- Put pure record tests beside `compiler/context_record.py` and filesystem reconciliation tests beside the orchestrator.

## Verification performed

The following existing baseline seams passed through `.venv/bin/pytest`:

```text
tools/benchmark/tests/test_score.py
tools/benchmark/tests/test_pass_boards.py
tools/tests/test_package_boundaries.py
orchestrator/tests/test_kdb_orchestrate.py (emit-kpis selection)
```

Source inspection additionally confirmed:

- post-graph manifest failure leaves `graph_committed=True` while finalize is skipped;
- `_finalize` alone writes the top-level `compile_result.json`;
- the current emitter copies that path and the live wiki tree unconditionally.

No product code was changed.

## Recommendation

Revise narrowly to v0.4, then return for ratification review. The event-time design itself is complete; the remaining amendments ensure the new failure-evidence artifact tells the truth about partial graph state, never packages stale finalized output, and has a fully executable typed schema.
