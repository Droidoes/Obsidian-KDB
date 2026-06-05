# Benchmark KPI Enumeration — Panel Review (Deepseek)

**Reviewer:** Deepseek (deepseek-v4-pro)
**Date:** 2026-06-05
**Artifact reviewed:** `docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md`

---

## Verdict: `GO-WITH-CHANGES`

The KPI list is fundamentally sound — the scored/diagnostic cut is disciplined, no scored KPI lacks a defensible direction, and the kills are correct. However, one **High** finding (M1 migration computability) and two **Medium** findings (robustness-vs-graph Borda imbalance, Claims blind spot) should be addressed before the anchors/weights spec. The list can proceed after those changes land.

---

## Findings

### (a) scored-vs-diagnostic & directionality

**[Severity: Medium]** · brief §2C BELONGS_TO coverage · direction relies on an unstated assumption

BELONGS_TO coverage is scored ↑ (higher = better). The brief's rationale: "there is a known Pass-1/derivation under-emit failure mode." This is a practical, empirical defense — it holds for today's models. But the direction is contingent on under-emission being the dominant failure mode. If a future model *over-classifies* domains (e.g., assigns every source a domain, however poorly), BELONGS_TO coverage rises without improving graph quality — and the benchmark would reward it. The derivation path (`rederive_domains()` at `kdb_graph/ingestor.py:488-544`) shows an entity gets BELONGS_TO for every domain its supporting sources claim, with no quality gate.

**Why it matters:** A directional KPI whose direction flips under a different failure regime is fragile. The benchmark could silently reward wrong behavior.

**Suggested change:** Keep BELONGS_TO coverage scored (the direction is correct for the current failure landscape), but (1) document the assumption explicitly, and (2) add a companion watched-diagnostic: **mean domains per entity** (BELONGS_TO edges / canonical entity count). If that number spikes while BELONGS_TO coverage also rises, the operator can spot over-classification. Optionally, add a soft cap to the Borda contribution when the companion diagnostic exceeds some threshold (defer to data from first multi-model run).

---

**[Severity: Low]** · brief §2C orphan rate · correctly parked as diagnostic

The brief demotes orphan rate to "watched diagnostic" for two reasons: (a) correlation with link-resolution (scoring both over-weights linking), and (b) unknown spread (near-zero-for-all dilutes Borda). Both reasons are sound. The "promote if cross-model CV exceeds X" fork (fork 3) is the right mechanism. No change needed.

---

### (b) double-counting/redundancy

**[Severity: Medium]** · brief §2A robustness ladder · four correlated scored KPIs create structural Borda imbalance

The four scored processing KPIs (quarantine, retry load, token-overrun, repair-rung) form a graded ladder. They're not double-counting in the statistical sense — each measures a different severity level. But in a Borda ranking with a small cohort (likely 3–5 models), four correlated signals give "robustness" 4× the voting power of each individual graph KPI. A model that is robust but produces a poor graph wins 4 ranks and loses 2 — even with up-weighting, the Borda sum tilts toward robustness.

The brief's fork 2 (up-weight graph KPIs) acknowledges this but understates the problem: weight is not the same as voting power. In Borda, each KPI contributes one rank position. A weight multiplier up-weights the *contribution to the final weighted sum* but doesn't change the fact that 4 correlated ranks amplify robustness relative to 2 ranks for graph quality.

**Why it matters:** The brief's own claim is that "graph quality is the axis that matters most" (directions doc §5). Yet the KPI design gives robustness 4× the ranking power. This is the single most important structural tension in the design.

**Suggested change:** Three options, in order of preference:
1. **Merge repair-rung into retry load** (both measure "pipeline had to help"). This reduces the robustness scored set from 4→3 without losing signal (the diagnostic breakdown still surfaces rung detail). Combined with up-weighting graph KPIs, this brings the Borda balance closer to intent.
2. Add a third graph KPI (see (d) below) to bring the scored graph set to 3, matching a 3:3 balance.
3. Accept the imbalance and document it explicitly — robustness IS the foundational processing signal, and a model that can't produce parseable output shouldn't be saved by graph quality.

---

**[Severity: Low]** · brief §2B semantic-pass rate vs. final_status · distinct enough to keep both

semantic-pass rate (fraction of compiled signal sources passing content-consistency gate) is partially correlated with quarantine rate — semantic failures eventually route to `final_status='quarantined'`. But the overlap is not complete: semantic-pass measures a specific failure category (content coherence: duplicate slugs, missing summary, reserved slugs) within the quarantined universe. A source could be quarantined for parse failure without ever reaching the semantic gate. The two KPIs provide orthogonal information. Keep both.

---

### (c) kills & the M1 migration

**[Severity: High]** · brief §2C link-resolution / §3 M1 migration · dangling-link rate is NOT computable from `links_to_edges` alone

The brief defines the new link-resolution KPI as "body `[[wikilinks]]` that resolve to no entity, over total wikilinks" and cites `kdb_graph.queries.links_to_edges` as the data source. This is incorrect.

The ingestor's `_replace_outgoing_links()` (`kdb_graph/ingestor.py:309-344`) uses a MATCH-then-CREATE pattern that **silently drops** LINKS_TO edges when the target entity doesn't exist. The docstring is explicit: *"If a target slug doesn't yet exist as an Entity node, the CREATE is silently skipped — dangling outgoing_links are a validator catch upstream, not the ingestor's job"* (lines 317-319). As a result, `links_to_edges` (`kdb_graph/queries.py:310-319`) returns only the **surviving** edges — dropped links leave no trace in the graph. You cannot compute a ratio of dangling/total from graph data alone because the dangling numerator is invisible.

**Why it matters:** This KPI is the brief's "purest graph signal of model skill." If the computation path is wrong, the benchmark's most load-bearing graph KPI produces garbage.

**Suggested change:** The dangling-link rate must be computed by comparing the declared `outgoing_links` from the compile payload (`CompiledSource.pages[].outgoing_links` in `compile_result.json` or equivalent) against the entity slug set (from `kdb_graph/queries.py:active_entity_slugs` or a direct Kuzu query). Denominator = total `outgoing_links` entries across all pages. Numerator = entries whose target slug is NOT in the entity set. The graph query `links_to_edges` can serve as a cross-check (surviving edge count) but cannot be the primary data source.

Update the brief's data source column from `links_to_edges` to: "`compile_result.json` → `pages[].outgoing_links` vs entity slug set (`active_entity_slugs`)."

---

**[Severity: Low]** · brief §3 kills M2, M3, M5 · verified correct

- **M2/M3** (slug-pairing Jaccard): The old pairing model measured declared-slug ↔ emitted-page overlap. The current pipeline reconciles pairing discrepancies via the reconcile pass (`validate_compile_result.py` — `pairing_commission`, `pairing_type_mismatch`, `pairing_omission` are all `measure`-severity, not gates). Post-reconcile, pairing is always perfect. Pre-reconcile measurement would be an implementation artifact, not a quality signal. Kill correct.

- **M5** (body wikilink emit-set coverage): Measured whether body `[[wikilinks]]` covered declared slugs. The brief's rationale is correct: Obsidian wikilinks are display-only rendering artifacts; the knowledge graph lives in Kuzu as LINKS_TO edges. The new link-resolution KPI directly measures graph-level linking. No residual signal worth keeping.

These kills are clean. No change needed.

---

### (d) graph-set completeness

**[Severity: Medium]** · brief §2C, fork 5 · two graph KPIs is correct, but the 2-vs-5 imbalance needs a structural fix, not just weights

The brief chose two sharp directional graph signals over a wider noisy set. This is the right call. I reviewed the candidates:

- **ALIAS_OF/dedup quality:** No GT-free direction. More aliases isn't provably better (could be over-dedup or under-dedup).
- **Link reciprocity:** Non-directional. Higher reciprocity could be "better connected" or "echo chamber."
- **Component/connectivity count:** Non-directional. Fewer components = more connected, but could indicate over-linking.
- **Entity yield (SUPPORTS density):** Correctly diagnostic. More entities isn't provably better.

None of these are directionally scoreable. The brief's choice of two sharp signals is correct.

However, there is a subtle candidate worth considering as a **third scored graph KPI: entity empty-compile rate** — sources that compiled cleanly (`final_status='clean'`) but produced zero entities/pages. A source reaching Pass-2 as signal, passing all repair rungs, and emitting zero entities is a distinct quality failure invisible to both quarantine rate (source wasn't quarantined) and link-resolution (no entities → no links). This is not the same as SUPPORTS density (which is about how many entities per source); a zero-entity compile is unambiguously worse than a non-zero compile. **Direction:** ↓ (lower empty-compile rate = better).

**Why it matters:** This is the only candidate that (a) has a defensible direction, (b) is GT-free computable, and (c) captures a failure mode currently invisible to the scored set. It bridges processing and graph — it's a processing artifact (the compile produced nothing) with graph impact (no entities entered the graph).

**Suggested change:** Add "entity empty-compile rate" as a scored graph KPI (or a processing KPI — it lives at the boundary). Denominator = signal sources that compiled successfully (`final_status != 'quarantined'`). Numerator = those with zero pages/entities. Direction ↓. If first-run data shows near-zero across all models, demote to watched diagnostic (same promotion rule as orphan rate, fork 3).

---

**[Severity: Low]** · brief §2C · orphan rate as watched diagnostic

The brief's argument for keeping orphan rate diagnostic (correlated with link-resolution, unknown spread) is sound. The watch-then-promote mechanism (fork 3) is the right approach. Keep as-is.

---

### (e) classification & normalization

**[Severity: Low]** · brief §2, fork 4 · all normalization choices are correct

- Robustness KPIs (quarantine, retry load, token-overrun, repair-rung): per-token ✓. A quarantine on a 95KB source ≠ quarantine on a 2KB source.
- Semantic-pass rate: ratio pass-through ✓. Already 0–1 (fraction of compiled signal sources).
- Link-resolution/dangling-link rate: ratio pass-through ✓. Dangling/total-wikilinks is 0–1.
- BELONGS_TO coverage: ratio pass-through ✓. Entities-with-BELONGS_TO / canonical-entities is 0–1.
- Diagnostics (cost, latency): per-source-word ✓.

No distortion found. The per-run vs. pass-specific classification is also sound: per-token normalization handles different denominators between Pass-1 (all sources) and Pass-2 (signal-only sources). The diagnostic breakdown preserves pass-specific insight. No changes needed.

---

### (f) Pass-1 / #108 coupling

**[Severity: Low]** · brief §4 fork 1 · contract-first approach (a) is correct

Pass-1 telemetry (`attempts`, tokens, `latency_ms`) is computed by `pass1_caller.py` but not durably persisted — only the quarantine count and signal/noise split surface via `orchestrator_events.jsonl`. The per-run robustness KPIs are therefore Pass-2-only until #108 ships.

The brief's fork (a) — spec a Pass-1 telemetry record as a contract and let the KPI framework consume it when #108 lands — is the correct sequencing. The KPI definitions are valid; the data source column should note the Pass-1 gap and the contract dependency.

**Pass-1 quality signal:** No GT-free Pass-1 quality signal beyond signal/noise ratio is worth scoring. Pass-1's quality feeds indirectly into BELONGS_TO coverage (via domain classification) and signal/noise ratio (changes which sources reach Pass-2, shifting every downstream graph KPI). Both are already captured — BELONGS_TO coverage as scored, signal/noise as diagnostic. No additional KPI needed.

No changes to the KPI list required; just note the contract dependency in the data source columns.

---

### (g) blind spots / omissions

**[Severity: Medium]** · not in brief · the Claim layer is a complete blind spot

The graph schema (`kdb_graph/schema.py`) includes a full Claim layer: Claim nodes, EVIDENCES, ABOUT, SUPERSEDES, CONTRADICTS, QUALIFIES relations. The brief mentions "the empty Claim layer" in item 10 but the KPI list has zero Claim-layer KPIs — not even diagnostics.

**Why it matters:** When Claims are populated (via the O1 promotion pipeline), they become a rich model-discriminating axis. A model that produces well-connected entities but poor/no Claims is missing half the ontology. The benchmark should acknowledge this gap so the anchors/weights spec can include a placeholder for Claim-layer KPIs (scored or diagnostic, TBD when Claims have data).

**Suggested change:** Add a §2D "Graph — Claim layer (future)" section noting that Claim-layer KPIs are deferred until the O1 promotion pipeline produces run data. This prevents the anchors/weights spec from baking in a weight distribution that assumes the current KPI list is final. Even a single scored Claim KPI (e.g., claim coverage — entities with ≥1 ABOUT edge / total entities) would materially change the graph/processing balance.

---

**[Severity: Low]** · brief §2A/B · entity empty-compile rate is a blind spot (see (d) above)

---

**[Severity: Low]** · brief §5 · cross-run stability is correctly out of scope

The benchmark uses latest-run-per-model, no historical averaging. Cross-run stability (does the same model on the same corpus produce the same graph twice?) is interesting but belongs in the deferred telemetry layer, not the benchmark. Correctly omitted.

---

## Bottom Line

This KPI list is sound enough to turn into an anchors/weights spec after three changes: **(1) fix the M1 link-resolution data source** — the dangling-link rate cannot be computed from `links_to_edges` alone; the ingestor silently drops unresolvable links and the computation must compare declared `outgoing_links` against the entity set; **(2) address the robustness-vs-graph Borda imbalance** — either merge repair-rung into retry load to reduce the scored robustness set from 4→3, or add entity empty-compile rate as a third scored graph KPI, or accept and document the robustness tilt as intentional; **(3) add a placeholder for Claim-layer KPIs** so the anchors/weights spec doesn't assume the current list is final.

On the **"is the scored graph set too lean at two"** fork: **two is correct.** Adding a non-directional third graph KPI (density, reciprocity, component count) would dilute the Borda signal. The real fix for the graph/processing imbalance is on the processing side (reduce the scored robustness set) or at the graph/processing boundary (add empty-compile rate, which bridges both families). Up-weighting graph KPIs helps but doesn't fully compensate — Borda voting power (4 robustness ranks vs 2 graph ranks) is not the same as weight.
