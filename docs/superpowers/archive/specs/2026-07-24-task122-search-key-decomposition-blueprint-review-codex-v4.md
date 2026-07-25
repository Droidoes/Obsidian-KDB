# Codex ratification review — Task #122 event-time context capture blueprint v0.4

**Reviewed:** 2026-07-24  
**Artifact:** `docs/superpowers/archive/specs/2026-07-24-task122-search-key-decomposition-blueprint.md`  
**Architecture baseline:** options v1.3 + D-122  
**Prior review:** `docs/superpowers/archive/specs/2026-07-24-task122-search-key-decomposition-blueprint-review-codex-v3.md`  
**Verdict:** **REVISE NARROWLY — architecture ratifiable; one execution branch and two self-containment sections remain**

## Executive assessment

v0.4 correctly absorbs every substantive R3 finding:

- “no finalize” now means unfinalized/possibly partial, never unchanged;
- the late/never read uses the actual post-run graph without legitimizing the run for scoring;
- stale `compile_result.json` and live-wiki packaging are excluded;
- the persistence/evidence dataclasses are fully located and enumerated;
- success/failure factory states and nullability are frozen;
- shared mode/strategy vocabularies preserve the package boundary;
- raw score inputs have historical, skip, and malformed rules;
- record-unit and orchestration tests have appropriate ownership.

No architectural redesign is needed. The event-time boundary, metric definitions, lifecycle semantics, and score eligibility are converged.

Before Joseph's Proceed, one implementation detail must be explicit: a no-finalize run must **skip** the existing finalized graph-quality queries, not execute them and overwrite their results with `None`. The current blueprint also needs to restore the builder and Pass-1-board interfaces that were present in earlier drafts but are no longer self-contained in v0.4.

## R3 absorption

| R3 finding | v0.4 assessment |
|---|---|
| F1 — no-finalize graph-state truth | **Fully absorbed.** |
| F2 — stale finalized-output packaging | **Fully absorbed.** |
| F3 — concrete record/evidence types | **Fully absorbed.** |
| F4 — raw score-boundary validation | **Fully absorbed.** |
| F5 — test placement and missing lifecycle case | **Fully absorbed.** |

## Findings

### 1. Important — branch before finalized graph-quality reads on no-finalize runs

Section 7 defines the correct output:

- finalized graph scored fields are `None`;
- finalized-run watched fields are `None`;
- Task-122 context/integrity fields remain;
- the unresolved-key read still uses the actual post-run graph.

The current `compute_graph` implementation eagerly performs the finalized-run reads before assembling its output:

- canonical entity sets and edges;
- source and entity counts;
- support counts;
- link/support density reads;
- orphan inputs;
- legacy search-key resolution;
- domain diagnostics.

See `compiler/kpi/graph.py:104-205`. Merely replacing those values with `None` in `emit_run_kpis` would still:

- spend work on deliberately ineligible metrics;
- query a residual or partially finalized graph for results that must be discarded;
- risk losing the audit artifact if the same graph condition that prevented finalize also makes one of those reads fail.

Freeze the execution branch, not only the output policy. A direct interface is:

```python
compute_graph(
    conn,
    finalize_artifacts,
    *,
    finalize_ran: bool = True,
    pass1_search_keys: list[str] | None = None,
    run_id: str | None = None,
    context_evidence: ContextEvidence | None = None,
) -> dict
```

Behavior:

```text
finalize_ran=True:
    existing graph-quality reads and legacy metric unchanged;
    compute/merge Task-122 context fields

finalize_ran=False:
    do not execute finalized graph-quality or legacy-resolution reads;
    emit their established keys as None;
    compute Task-122 fields from ContextEvidence;
    execute only the unresolved-at-load resolver read needed for L/V
      (and make no query when that population is empty)
```

An equally valid design is a separate pure context-KPI helper called by two emitter branches. Whichever shape is chosen, the no-finalize path must not call the existing quality-query block and then discard it.

Add a pin that monkeypatches an ordinary finalized graph-quality query to raise, runs the no-finalize branch, and proves:

- that query was never called;
- Task-122 context/integrity values still emit;
- finalized graph fields are present as `None`;
- the unresolved resolver is called only when unresolved evidence exists.

### 2. Moderate — make v0.4 self-contained instead of referencing overwritten v0.3

Section 3 says disposition derivation, tier records, effective strategy, and empty-graph telemetry are “unchanged from v0.3 §3.” The blueprint path is updated in place; there is no separate v0.3 blueprint artifact in the repository, and this file is currently untracked, so a future first commit will not provide a prior Git revision to consult.

Restore the complete builder contract in v0.4:

```text
for each emitted key, in order:
    unresolved
    resolved_already_t1
    resolved_out_of_scope
    resolved_duplicate_seed
    resolved_t2_seed
```

Include:

- the exact precedence predicates;
- `candidates` as pre-cap tier set size;
- `delivered/slugs` as post-cap, post-projection prompt pages;
- `sum(delivered) == len(snapshot.pages) <= page_cap`;
- effective-strategy mapping for structured keys, explicit empty, legacy fallback, and layered union;
- empty-graph values, including unresolved outcomes, zero tiers, `cold_start=True`, and the recorded hop policy;
- the exact definition of `candidate_universe_size` (domain-scoped pool or all active entities).

This is not a design change; it prevents the implementation plan from depending on a superseded document that does not exist independently.

### 3. Moderate — restore the explicit Pass-1-board plumbing section

v0.3 contained the required data path:

```text
CLI extracts search_key_* and context_* fields per model
    -> build_pass_board(..., pass1_watched_by_model=...)
    -> _build_row merges into ranked, partial, and fallback Pass-1 raw_values
    -> JSON and Markdown render from the same values
```

That implementation section is absent from v0.4. Only board tests and the generic word “boards” remain. The current benchmark code does not automatically propagate arbitrary Task-122 watched fields into Pass-1 rows.

Restore the interface explicitly, including:

- all search-key, context, coverage, and integrity fields;
- ranked, partial, and measurements-fallback rows;
- the explicit merge rather than the `_pass1` suffix filter;
- eligible artifacts only (`finalize_ran=false` inputs are skipped before pointer updates);
- JSON and Markdown parity.

Again, this preserves the already-ratified design; it does not introduce new scope.

### 4. Minor — make the raw `finalize_ran` truth table exhaustive in prose

Section 7c lists missing, false, and “any other type.” Add the explicit successful case:

```text
value is bool True -> eligible
```

The tests already name the True variant, so this is only a wording correction.

## What is approved

The following contracts are ratification-ready:

- event-time context capture and prompt isolation;
- the five key dispositions;
- pre-cap seed versus delivered-page semantics;
- neutral resolver rows and shared precedence;
- provenance stamps and equality-only cohort age;
- versioned success/failure records;
- strict parsing and identity reconciliation;
- complete-only substantive metrics and zero-expected behavior;
- all-emissions key-rate equations;
- partial/no-finalize lifecycle truth;
- status-aware artifact packaging;
- no-finalize score exclusion;
- package dependency direction;
- phase boundaries and commit gates.

## Required v0.5 amendments

- Add an explicit no-finalize execution branch that bypasses finalized graph-quality/legacy queries while retaining Task-122 computation.
- Restore the full context-builder/disposition/tier/strategy/empty-graph contract in the current blueprint.
- Restore the explicit CLI-to-Pass-1-board watched-field interface.
- Add the `finalize_ran is True` line to the raw score truth table.

## Verification performed

The following current seams passed through `.venv/bin/pytest`:

```text
compiler/tests/test_kpi_graph.py
tools/benchmark/tests/test_score.py
tools/benchmark/tests/test_pass_boards.py
tools/tests/test_package_boundaries.py
orchestrator/tests/test_kdb_orchestrate.py (emit-kpis/graph selection)
```

Source inspection confirmed that today's `compute_graph` performs all finalized graph-quality reads eagerly and that v0.4 contains neither the prior builder detail nor the `pass1_watched_by_model` interface.

No product code was changed.

## Recommendation

Make the four narrow v0.5 documentation amendments, then the blueprint is ready for **APPROVE / Joseph's Proceed** without another architecture-options round. The system design is complete; this final edit makes the executable branch and implementation interfaces as explicit as the already-settled behavior.
