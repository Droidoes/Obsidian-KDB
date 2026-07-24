# Task #120 Spec v1.1 Review — Codex R2

**Date:** 2026-07-24

**Reviewed:** `docs/superpowers/specs/2026-07-24-task120-pass2-wikilink-emission-restoration.md`

**Repository anchor:** `main` at `9a320fd`

**Verdict:** **REVISE**

The revision absorbs the architectural direction of all four round-one findings. The schema wording is now constrained to authoritative targets, the GPT run closes the cross-model regression gap, the novelty complement is gone, the live run is correctly treated as a canary, and the provenance test covers both injected schema surfaces.

Two load-bearing details remain. D4 still postpones the exact acceptance math until after the run and carries an incorrect historical dangling baseline. D3 adopts the correct name, “final-graph realization,” but immediately reintroduces the interpretation that round one rejected by calling the same mixed post-intake value a reuse/maturity measure. One smaller task-ledger update is also needed for the work deferred to #118.

## Findings

### 1. Important — D4's formulas are still not predeclared, and its historical dangling baseline is incorrect

**Location:** spec `:6,30-36`; `compiler/validate_source_response.py:95-114`; `kdb_graph/intake.py:338-382`; `compiler/kpi/graph.py:105-132`; `compiler/proposal_bridge.py:239-267`; `common/paths.py:63-92`

The revised gate correctly moves the product objective to stored `LINKS_TO` edges. It also correctly adds self-link, current-summary, dangling, and over-linking safety checks. However, saying that the eventual evidence file will contain numerators and denominators does not define those populations before results are observed.

In particular, the spec still does not say:

- whether the concept denominator includes inactive canonical concepts;
- whether the concept numerator counts edges by canonical source type and whether alias endpoints are included;
- whether raw targets are literal bracket occurrences, corpus-unique targets, or the per-page target sets production actually attempts to wire;
- whether dangling resolution is exact-slug graph membership, as intake implements it, or alias-aware canonical resolution;
- what exact value “approaching” `1.78` means, or what sample size, selection rule, and pass criterion make the semantic audit a gate.

The historical artifacts expose why this precision matters. Recomputing the prompt-3.0.0 DeepSeek run with the production extractor and its retained final graph gives:

- overall resolved density: `272 / 222 = 1.225225`;
- resolved canonical-concept density: `76 / 183 = 0.415301`, which validates the proposed `>= 0.4` canary;
- production-extracted page-target pairs: `285`;
- absent exact-slug targets: `13 / 285 = 4.561%`;
- self-links: `0`;
- links to the current source's summary: `0`.

The spec's `15 of 288` is not the production dangling calculation. There are 288 literal `[[...]]` openings, but production ignores the code example `[[abc123]]`, ignores the invalid non-kebab target `[[wheat germ]]`, and de-duplicates repeated targets within a page before wiring. The two `summary-*` references mentioned in round one both target an emitted concept page named `summary-callout`; they resolve and are not links to the current source's summary. My round-one description of those two references as guessed summaries was incorrect.

The historical output did violate the intended reserved-prefix rule by creating that concept, and current normalization does **not** prevent it: `collapse_slug()` reserves only `index` and `log`, while `normalize_proposal()` accepts a concept slug such as `summary-callout` unless it exactly collides with the current derived summary slug. That is a distinct safety condition, not dangling or current-summary linking.

**Concrete fix:** add the normative acceptance equations to D4 now, before implementation:

1. `overall_resolved_density` is exactly the persisted `graph.scored.link_density`: all stored `LINKS_TO` edges divided by all entities where `canonical_id IS NULL`, matching `compiler.kpi.graph`.
2. `concept_resolved_density` is stored `LINKS_TO` edges whose source has `canonical_id IS NULL AND page_type = 'concept'`, divided by entities with that same source predicate. State explicitly whether status is intentionally unfiltered; that matches the current scored denominator and reproduces `76/183`.
3. `raw_target_pairs` is the sum of `body_wikilink_slugs(body)` set sizes over pages. `dangling_pairs` is the subset whose target slug has no exact `Entity` match in the final graph, matching intake's exact-slug `MATCH`; no alias-aware rewrite is performed by link wiring. Correct the historical gate to `<= 13/285` (or a clearly rounded `<= 4.6%`).
4. Define self-link comparison against the post-normalization page slug and current-summary comparison against that compiled source's Python-derived summary slug.
5. Add zero concept/article slugs beginning with `summary-` to the safety gate. Either enforce the already-documented invariant at the normalization boundary in this task or route that enforcement explicitly, but do not let a 4.0.2 cohort pass while reproducing the historical namespace violation.
6. Replace “approaching/exceeding” with an exact trigger such as `link_density >= 1.78`, and predeclare a deterministic audit sample, selection method, and pass/fail rule. Persist all listed populations, target lists, formulas, and results beside each run evaluation as already planned.

### 2. Important — “reuse/maturity” still contradicts the final-graph realization semantics

**Location:** spec `:26`; `compiler/kpi/graph.py:162-176`; `orchestrator/emit_kpis.py:116-124`

Choosing Path 1 is correct: removing `entity_search_key_novelty` avoids adding an information-free complement, and deferring the three-way decomposition is the right scope cut. The new primary label, **final-graph realization**, is also accurate.

The following appositive is not:

> a reuse/maturity measure and within-cohort cross-model comparator

The final post-intake numerator combines at least three causes:

- a key resolved to an entity that existed before the cohort;
- a new key was successfully materialized by Pass 2 during this cohort;
- alias/canonicalization behavior made the final key resolvable.

The first can indicate reuse; the second indicates successful new materialization, not maturity. As round one noted, the unchanged value is neither a pure reuse/maturity measure nor a Pass-1 extraction-quality measure. Cross-model comparison is also interpretable only for controlled runs with the same corpus fingerprint and equivalent initial graph state.

**Concrete fix:** document it as the **mixed downstream final-graph realization rate of Pass-1 search keys**, influenced by Pass-1 selection, Pass-2 materialization, and canonicalization. State that it is watched-not-scored, is not a reuse/maturity or extraction-quality metric, and may be compared across models only when corpus and initial graph state are controlled. Keep the true pre-existing/materialized/unresolved decomposition deferred to #118.

### 3. Minor — the #118 deferral is not recorded in #118's task-ledger scope

**Location:** spec `:26,59-61`; `docs/TASKS.md:46`

The spec defers the three-way search-key decomposition to #118, but the #118 ledger entry currently covers split-model orchestration, provenance, and leaderboard identity only. It does not record the new diagnostic scope. A deferral that exists only in #120's spec is easy to lose when #118 is revived.

**Concrete fix:** extend Task #118's ledger row with the controlled three-way diagnostic—resolved to a pre-cohort canonical entity, materialized in the cohort, or unresolved after the cohort—using the run-aware `first_run_id` design and keeping all buckets watched-not-scored.

## Round-one absorption status

| Round-one finding | R2 status |
|---|---|
| F1 — gate the scored regression on resolved graph edges and persist reproducible safety evidence | **Partially absorbed.** The correct resolved gates and safety categories are present; the predeclared equations, exact upper audit rule, and correct `13/285` baseline remain open. |
| F2 — drop the novelty complement or implement a real decomposition | **Partially absorbed.** Novelty is correctly dropped and decomposition deferred; the “reuse/maturity” interpretation still needs removal. |
| F3 — constrain B+ and add a GPT non-regression run | **Fully absorbed.** The target authority and no-invent/no-self/no-current-summary guardrails are explicit; DeepSeek and GPT are both exercised. |
| F4 — pin both schema surfaces through the actual injection loader | **Fully absorbed.** The planned suite uses `load_response_schema_text()` and pins both descriptions plus `PASS2_PROMPT_VERSION == "4.0.2"`. |

## Items accepted as designed

- The exact constrained B+ schema text is consistent with the system prompt's authoritative target set.
- Restoring both lost 3.0.0 schema surfaces without changing the system prompt or restoring mirror fields is the right boundary.
- `PASS2_PROMPT_VERSION = "4.0.2"` is the correct provenance bump; replay remains in the 4.x era.
- DeepSeek `link_density >= 1.2` and resolved concept density `>= 0.4` are defensible one-run restoration canaries. The retained 3.0.0 graph reproduces the latter as `76/183 = 0.4153`.
- The GPT `>= 1.5` lower guard is consistent with the retained 3.0.0 (`1.709`) and 4.0.1 (`1.538`) runs, provided the upper audit is made executable.
- A failed single run routes to investigation rather than purporting to falsify the mechanism.
- The provenance canary should interpret “contains the constrained directive” as pinning the complete authoritative-target sentence and all three prohibitions, not merely the presence of the `[[slug]]` token.

## Verification performed

- Re-audited the schema loader, system/schema precedence, body-link extractor, exact-slug graph intake, scored graph KPI, and post-intake search-key computation.
- Recomputed the prompt-3.0.0 DeepSeek overall and concept resolved-edge populations from `graph-view.html`.
- Recomputed raw production target sets, dangling targets, self-links, and current-source-summary links from `compile_result.json` using `body_wikilink_slugs`.
- Confirmed with a direct bridge probe that a non-summary `summary-callout` proposal currently normalizes successfully.
- Checked the current #118 and #120 task-ledger entries.
- No production code changed; this was a design/evidence review, so no test suite was rerun.

## Recommendation

Issue spec v1.2 with Findings 1 and 2 resolved before ratification. Finding 3 is a small tracking correction and should be folded into the same revision. The implementation itself remains narrow once the acceptance equations and metric semantics are locked.
