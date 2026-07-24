# Task #120 Spec v1.3 Review — Codex R4

**Date:** 2026-07-24

**Reviewed:** `docs/superpowers/specs/2026-07-24-task120-pass2-wikilink-emission-restoration.md`

**Repository anchor:** `main` at `9a320fd`

**Verdict:** **REVISE**

The v1.3 revision absorbs the three explicit R3 findings: it defines a concrete edge sample and evidence authority, moves evaluations to a tracked path, makes D5's retrospective 4.x replay policy explicit, pins post-coercion prefix rejection, and applies the #118/#120 ledger edits. D1-D3, the lower D4 equations/gates, and D5's boundary remain sound.

One Important mismatch remains in the upper audit: the trigger measures **all** stored `LINKS_TO` edges, while the audit samples only edges originating from concept pages. The audit can therefore pass without examining the summary/article edges that caused the trigger. One Minor ledger label also closes the ratification gate prematurely.

## Findings

### 1. Important — the upper audit samples a different population from the metric that triggers it

**Location:** spec `:26,35-37`; `compiler/kpi/graph.py:105-132`; `kdb_graph/queries.py:425-428`

`overall_resolved_density` uses every stored `LINKS_TO` edge in its numerator, regardless of source page type. The `>= 1.78` upper trigger is therefore an all-page signal.

The audit candidate set is narrower:

> candidate `(source_page_slug, target_slug)` pairs whose source is a canonical concept

That excludes summary- and article-origin edges even when those edges are what pushed the overall density above the upper band. This is not theoretical noise in the retained cohorts:

- DeepSeek 3.0.0: `272` resolved edges total, only `76` from concepts; `196/272` originate from summaries/articles.
- GPT 4.0.1: `400` resolved edges total, only `137` from concepts; `263/400` originate from summaries/articles.

A model can over-link summaries or articles, trigger on overall density, and still pass an 18/20 concept-edge audit that never samples the affected population. The current `min(20, candidate_edges)` rule also leaves `supported_edges / audited_edges` undefined when a triggered run has zero concept-edge candidates. That case is not excluded for GPT because its gate has no concept-density floor.

**Concrete fix:** align the sample population with the trigger:

1. Make candidates all resolved edges counted by `overall_resolved_density`, preferably limited to the current cohort's final compiled-page occurrences.
2. Sort them by `source_outdegree DESC, source_page_slug ASC, target_slug ASC`, take `min(20, candidate_edges)`, and persist `source_page_type` alongside the existing evidence fields.
3. Keep the final-occurrence/source-excerpt authority and `>=0.90` rule unchanged.

Alternatively, if the team intentionally wants a concept-only audit, trigger it from an explicit concept-density upper band and add a separate all-page or stratified audit for the overall-density trigger. The sample and trigger must cover the same population.

### 2. Minor — TASKS.md labels v1.3 ratified before Joseph's ratification

**Location:** spec `:3,59`; `docs/TASKS.md:47`

The spec correctly says it is “awaiting Joseph's ratification,” and Task #120 remains `proposed`. The edited ledger row nevertheless says:

> **Ratified design (2026-07-24):** spec v1.3

No explicit Proceed has closed that gate yet. The row is internally contradictory and could be read as authorization to start implementation before this review is resolved.

**Concrete fix:** change the ledger wording to `Candidate design v1.3 (awaiting ratification)` while the task remains proposed. After Joseph explicitly ratifies the corrected spec, update both the label and task status together.

## R3 absorption status

| R3 finding | v1.3 status |
|---|---|
| F1 — executable edge audit, named evidence authority, and tracked persistence | **Partially absorbed.** Unit, ordering, evidence authority, denominator, and tracked path are now explicit. The edge population does not match the all-edge trigger; Finding 1 is the remaining correction. |
| F2 — explicit D5 replay policy and post-coercion pin | **Fully absorbed.** D5 is deliberately retrospective across 4.x, broad dispatch stays, valid fixtures remain controls, and `SUMMARY--Foo` pins planned-slug enforcement. |
| F3 — apply the #118/#120 ledger edits | **Content absorbed.** The decomposition and revised #120 scope are present; only the premature “Ratified design” label remains. |

## Items accepted as designed

- D1's constrained B+ wording and two restored schema surfaces.
- D2's `4.0.2` version bump and unchanged golden system-prompt SHA.
- D3's mixed downstream realization semantics and controlled-comparison boundary.
- D4 equations 1-5, historical `13/285` calibration, lower model gates, and exact `1.78` trigger.
- The tracked evaluation path under `docs/superpowers/evaluations/`; nothing is force-added under gitignored `benchmark/runs/`.
- Mapping an audited edge to the concrete final page occurrence that produced its stored outgoing set; `wire_links()` deterministically applies compiled sources/pages in order with replacement semantics.
- D5's `slug_collision` classification, retrospective 4.x policy, replay controls, and post-coercion bridge cases.
- Deferring historical namespace cleanup to #116/WS3 and the search-key decomposition to #118.

## Verification performed

- Rechecked all v1.3 changes against the R3 review.
- Confirmed the #118 decomposition and revised #120 scope are present in the `docs/TASKS.md` worktree diff.
- Re-audited graph link-density and wiring semantics.
- Recomputed resolved edges by source page type from retained artifacts:
  - DeepSeek 3.0.0: summary `155`, concept `76`, article `41`;
  - DeepSeek 4.0.1: summary `120`, concept `15`, article `15`;
  - GPT 4.0.1: summary `163`, concept `137`, article `100`.
- Rechecked broad 4.x replay dispatch and D5's planned post-coercion placement.
- No production code changed; this was a design review, so no test suite was rerun.

## Recommendation

Issue spec v1.4 with the upper audit sampling the same all-edge population as `overall_resolved_density`, and correct the ledger's premature ratification label. After those two edits, the design is ready for Joseph's explicit ratification.
