# Task #120 Spec v1.0 Review — Codex

**Date:** 2026-07-24

**Reviewed:** `docs/superpowers/specs/2026-07-24-task120-pass2-wikilink-emission-restoration.md`

**Repository anchor:** `main` at `9a320fd`

**Verdict:** **REVISE**

The core restoration is well motivated: restore the wiki-native schema guidance, bump the contract version to `4.0.2`, add a regression canary, and re-fire the model that regressed. The proposed lower bands are reasonable one-run restoration canaries given the size of the observed collapse.

Three load-bearing issues remain. The acceptance gate currently names raw body-link emission while the product impact is the resolved graph-edge KPI; the proposed novelty metric is the exact complement of final resolution and has the wrong semantics on a cold graph; and the novel B+ sentence can induce invalid or excessive linking without a cross-model non-regression gate. One smaller test-surface correction is also needed.

## Findings

### 1. Important — D4 can pass on links that the graph discards, so it does not yet gate the scored regression

**Location:** spec `:4,29,35-41`; `compiler/kpi/graph.py:129-132`; `kdb_graph/intake.py:338-382`

The quoted concept and overall values are raw unique body-link targets divided by emitted page rows:

- prompt `2.0.0`: concept `114/170 = 0.671`; overall `366/210 = 1.743`
- prompt `3.0.0`: concept `81/184 = 0.440`; overall `285/223 = 1.278`
- prompt `4.0.1`: concept `15/190 = 0.079`; overall `150/224 = 0.670`

Those reproduce the spec's rounded `0.45 → 0.08` and `1.30 → 0.68` evidence. They are useful emission diagnostics, but they are not `graph.scored.link_density`.

Production derives a unique target set from each body, then creates a `LINKS_TO` edge only when both source and target entities exist. Missing targets are silently skipped (`kdb_graph/intake.py:345-375`). The scored KPI then divides actual stored `LINKS_TO` edges by canonical entities (`compiler/kpi/graph.py:129-132`), not raw body targets by emitted page rows.

This is observable in the evidence. The prompt-3.0.0 deepseek result contains 13 body targets absent from its final page set and two guessed `summary-*` targets; its scored `link_density` is `1.225`, not the raw `1.278`. A 4.0.2 run can therefore clear D4 by emitting dangling, self, or guessed-summary links while the scored graph remains sparse or noisy. The gate also does not define how the page-type numerator and denominator are calculated, so the result is not independently reproducible.

**Concrete fix:**

1. Define and persist the exact acceptance calculation, including unique-target semantics, page-type denominator, alias resolution, canonical-only population, and the run artifacts used.
2. Keep raw body emission as a diagnostic, but gate the product objective on resolved edges:
   - `measurements.json → graph.scored.link_density >= 1.2`;
   - resolved concept outgoing edges per canonical concept page `>= 0.4`.
3. Add safety conditions: zero self-links, zero links to the current source's summary, and no regression in unresolved/dangling target rate. Predeclare an upper investigation band or require a small semantic sample audit if B+ exceeds the historical 2.0.0 band; `link_density` is unbounded and higher-is-better, so a lower bound alone cannot detect over-linking.
4. Save the acceptance analysis beside the run with numerators, denominators, unresolved targets, and pass/fail results rather than relying on an ad hoc console calculation.

### 2. Important — D3 labels non-materialization as novelty and adds no independent information

**Location:** spec `:24-27,39-40`; `compiler/kpi/graph.py:162-180`; `orchestrator/emit_kpis.py:116-124`

`entity_search_key_resolution` is computed after finalize against the final graph. Under D3:

```text
novelty = keys not resolved in the final graph
        = 1 - final_resolution
```

The planned `resolution + novelty == 1.0` test confirms that the new field is only the same signal with its sign reversed.

More importantly, the proposed interpretation is backwards on the cold-start case it is meant to fix:

- On an empty graph, a genuinely new Pass-1 key that Pass 2 successfully materializes resolves in the final graph. D3 reports `resolution=1`, `novelty=0`, despite maximal corpus growth.
- A malformed or irrelevant key that Pass 2 never materializes remains unresolved. D3 reports `novelty=1`, despite no healthy growth.

The unchanged computation is therefore neither a pure reuse/maturity measure nor an extraction-quality measure. Adding its complement does not separate those causes.

**Concrete fix:** choose one of these two paths before implementation:

1. **Narrow Task #120:** retain the existing metric, rename/document it honestly as final graph realization/resolution, and defer a real decomposition to #118.
2. **Implement a real three-way decomposition:** for each Pass-1 key classify it as:
   - resolved to an entity present before the cohort;
   - materialized during this cohort;
   - unresolved after the cohort.

   This requires a pre-run canonical inventory or a run-aware query over canonical `first_run_id`; pass `run_id` into the KPI computation and keep all three values watched, not scored. Add cold-graph tests proving a newly materialized key lands in the second bucket and a bad key lands in the third.

Keeping these diagnostics watched while the graph is young is correct. Calling the unresolved complement “novelty” is not.

If the split remains, also add it to the **Pass-1 board's diagnostic `raw_values`** in both recomputed and fallback/unranked paths. The main board will pick it up automatically through `tools/benchmark/cli.py:403-431`, but neither pass board currently carries graph-watched values (`tools/benchmark/pass_boards.py:94-119,163-183`). It belongs on the Pass-1 board as a downstream-realization diagnostic, not as a scored Pass-2 graph axis.

### 3. Important — B+ broadens the allowed target set, but D4 tests only deepseek and has no non-regression guard

**Location:** spec `:8-20,29,48`; `compiler/prompts/KDB-Compiler-System-Prompt.md:65,121-123,152-155`

The first restored sentence is safe and proven: link inline whenever referring to **another page in this response or EXISTING CONTEXT**.

The new B+ sentence is materially broader:

> Whenever you name a concept, technology, person, organization, or work that could be its own page, make the mention a wikilink.

“Could be its own page” does not require that a target actually exists. For a schema-literal model it can encourage:

- fabricated/dangling targets;
- extra low-value pages created merely to make the target exist;
- self-links from a concept page to itself;
- guessed links to the current summary, which #119 explicitly declared unnecessary.

The system prompt says every target must exist, but also says the injected schema is the final contract when the two appear to disagree (`compiler/prompts/KDB-Compiler-System-Prompt.md:65`). Historical prompt-3.0.0 deepseek output already violated the system rule with 13 absent targets and two guessed summary targets, so the stronger schema-local imperative cannot be assumed harmless.

The sentence is also new for GPT, not merely a restoration of a contract GPT has already demonstrated. A deepseek-only run tests deepseek recovery; it does not test whether the B+ addition pushes GPT from its healthy band into over-linking.

**Concrete fix:**

1. Constrain the B+ sentence to the authoritative target set, for example:

   > Whenever you mention a concept, technology, person, organization, or work that already has a page in this response or EXISTING CONTEXT, make that mention a wikilink to that page. Do not invent a target, self-link, or link to the current source's summary merely to satisfy this instruction.

2. If B+ remains novel wording, add a GPT non-regression re-fire with the same resolved-link safety checks and a predeclared historical band. If the team wants a deepseek-only experiment, restore only the proven 3.0.0 clauses and defer the B+ amplification.
3. Treat one deepseek run as a restoration canary, not causal proof. A failure should trigger the stated investigation; it does not by itself “falsify” the schema-surface mechanism when the spec simultaneously acknowledges run variance, served-model drift, and stochastic Pass-1 source selection.

### 4. Minor — the canary pins only one of the two restored schema surfaces

**Location:** spec `:31-33,37-40`; `compiler/prompt_builder.py:90-99`

The seed attributes the regression to losing both the top-level wiki-native clause and the `body` directive. The proposed canary checks only the `body` description. It can remain green while the second restored surface disappears.

**Concrete fix:** test the schema through the actual injection loader:

1. parse `prompt_builder.load_response_schema_text()`;
2. assert the top-level description contains the wiki-native `[[wikilinks]]` clause;
3. assert `$defs.pageProposal.properties.body.description` contains the constrained `[[slug]]` linking directive;
4. keep the `PASS2_PROMPT_VERSION == "4.0.2"` assertion in the same focused provenance suite.

This tests what the model actually receives rather than only reading the source JSON independently.

## Items accepted as designed

- **D2 is correct.** The injected schema is prompt-contract content, so `PASS2_PROMPT_VERSION` must become `4.0.2`. The system-prompt bytes do not change, so the existing golden system-prompt SHA remains unchanged. Clean release commit + version + existing system-prompt SHA satisfy the ratified D-115-13 attribution model; no additional schema fingerprint is required.
- **Replay dispatch needs no new era.** The structural proposal contract is unchanged and 4.x replay already dispatches by major version. Description-only schema edits do not alter validation of historical 4.0.0/4.0.1 payloads.
- **The lower bands are reasonable canaries once the metric is defined correctly.** `0.4` is about 11% below the raw 3.0.0 concept value; `1.2` is about 6% below the raw overall value (`1.278`) and about 2% below the scored 3.0.0 graph density (`1.225`), consistent with the stated variance allowance.
- **Watched-not-scored is the right disposition** for any corrected search-key decomposition until multiple cohorts establish direction, spread, and independence from scored axes.

## Verification performed

- Current focused baseline: **83 passed** (`test_kpi_graph`, `test_prompt_builder`, `test_pass_boards`, `test_score`)
- Recomputed raw body-link evidence from the retained 2.0.0, 3.0.0, and 4.0.1 deepseek `compile_result.json` artifacts
- Compared those values with each run's emitted `graph.scored.link_density`
- Audited prompt/schema precedence, graph target materialization, main-board diagnostic propagation, and per-pass board raw-value construction

## Recommendation

Issue spec v1.1 with Findings 1–3 resolved before implementation. Finding 4 is small enough to absorb in the same revision. The implementation remains a narrow task once the acceptance contract and D3 disposition are corrected.
