# Benchmark KPI Enumeration — Qwen Panel Review

**Reviewer:** Qwen Code (Claude Opus 4.7-class analysis)
**Date:** 2026-06-05
**Artifact under review:** `docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md`
**Code base:** v0.5.3 (`main` branch)
**Companion context:** `docs/superpowers/specs/2026-06-03-benchmark-redesign-directions.md`

---

## 1. Verdict: **GO-WITH-CHANGES**

The KPI list is structurally sound — the scored/diagnostic cut is principled, the kills are justified, and the two-family separation is clean. Two load-bearing issues must be resolved before proceeding to the anchors/weights spec: (1) the **M1 dangling-link rate cannot be computed from the graph alone** as stated — the ingestor silently drops dangling links, so the KPI's data source claim is wrong; and (2) the **scored graph set at two is genuinely too lean**, not because the two chosen KPIs are weak, but because a third directional GT-free graph signal exists and is being left on the table. Several medium-severity refinements (normalization correction, BELONGS_TO attribution, repair/retry overlap) should also be folded in.

---

## 2. Findings

### (a) Scored-vs-diagnostic & directionality

**F1. [Medium] · brief §2B semantic-pass row, `validate_compile_result.py:44-60` · semantic-pass rate is partially redundant with S0 (folded into quarantine rate) but correctly scored as a distinct signal**

The brief scores semantic-pass rate (↑) as a Pass-2-specific KPI, claiming it's "distinct from robustness: a source can parse perfectly yet fail semantically (e.g. duplicate slug)." Code check confirms this: `validate_compile_result.py` `_check_source()` checks duplicate_slug, summary_slug_missing, summary_slug_wrong_type, and reserved_slug — these are content-consistency checks that fire on structurally-valid JSON. A model can produce clean JSON that has internal slug conflicts. So semantic-pass is genuinely independent of the robustness ladder.

**However**, the brief's claim that semantic-pass is "Post-#106 the check sits inside the retry loop, so this reflects coherence after a second chance" slightly overstates the independence. If a model fails semantic checks on attempt 1, gets retried, and passes on attempt 2, the retry-load KPI goes up AND the semantic-pass KPI stays clean. These aren't redundant (different models could have different profiles), but there's a mild positive correlation: models that retry more will have artificially higher semantic-pass rates (they get a second chance to fix semantic defects). Not a blocking issue — flag as a known correlation for the weights spec.

**Suggested change:** Add a note to the semantic-pass KPI definition: "Known mild positive correlation with retry load (semantic defects can be retried away post-#106). Weights spec should account for this when setting relative weights."

---

**F2. [Low] · brief §2A · all four robustness KPIs have clean, defensible directions**

Audit of the four scored processing KPIs:
- **quarantine rate (↓):** `RespStatsRecord.final_status == 'quarantined'` / `orchestrator_events.jsonl` source_quarantined. Lower = better. Clean.
- **retry load (↓):** `RespStatsRecord.attempts > 1`. Less retries = better. Clean.
- **token-overrun rate (↓):** `RespStatsRecord.token_overrun`. Fewer truncations = better. Clean.
- **repair-rung usage (↓):** `RespStatsRecord.syntax_repaired ∨ slug_coerced`. Fewer repairs = better. Clean.

All four are genuinely directional. No misclassification found. The graded ladder framing (clean → repaired → retried → quarantined) is well-grounded in the `RespStatsRecord` fields.

---

**F3. [Low] · brief §2C · BELONGS_TO coverage (↑) direction is sound but the "Pass-1/derivation under-emit failure mode" attribution is imprecise**

The brief claims BELONGS_TO coverage is model-discriminating because "there is a known Pass-1/derivation under-emit failure mode." Code check on `kdb_graph/ingestor.py` `rederive_domains()`: BELONGS_TO is derived from `Source.domain` (set by Pass-1 via `_write_source_meta()`) + SUPPORTS edges (set by Pass-2 via `_replace_supports_for_source()`). So the failure mode is actually a **Pass-1 × Pass-2 joint failure**: either Pass-1 doesn't assign a valid domain (causing `Source.domain` to be NULL), or Pass-2 doesn't emit SUPPORTS edges. Both contribute.

This doesn't change the KPI's directionality (higher = still better), but the brief should attribute the failure mode to both passes, not just Pass-1. If a model's Pass-2 emits many entities but SUPPORTS replacement drops them, BELONGS_TO coverage drops — that's a pure Pass-2 failure.

**Suggested change:** Amend the BELONGS_TO coverage rationale: "Two-path dependency: requires Pass-1 to assign valid Source.domain AND Pass-2 to emit SUPPORTS edges. Failure in either pass reduces coverage."

---

### (b) Double-counting / redundancy

**F4. [Medium] · brief §2A · repair-rung usage and retry load share a partial overlap that the brief doesn't acknowledge**

The brief asks whether "quarantine / retry / repair-rung / token-overrun overlap enough that scoring all four over-weights robustness." Code check reveals:

- `RespStatsRecord.compile_attempts` (the #106 retry loop counter) and `syntax_repaired` / `slug_coerced` are **compositional, not mutually exclusive** (per the field docstring at `common/types.py:~330`). A source can be retried AND repaired in the same run.
- Concretely: attempt 1 fails semantic checks → retry fires → attempt 2 succeeds but needs slug coercion. Both `attempts=2` (retry load fires) and `slug_coerced=True` (repair-rung fires).
- The correlation is partial, not total: a transient network error triggers retry without repair; a first-attempt JSON escape issue triggers repair without retry.

The overlap is real but moderate (~20-30% of defective sources will fire both, based on the compositional structure). Scoring all four doesn't severely over-weight robustness because they measure different *rungs* of the ladder. But the weights spec should set the combined robustness weight with awareness that the four KPIs aren't fully independent.

**Suggested change:** Add a note to the processing-KPI family: "Known partial overlap between retry load and repair-rung usage (compositional, not mutually exclusive — `RespStatsRecord` field docs). Combined robustness weight should reflect this."

---

**F5. [Low] · brief §2A/§2B · quarantine rate and semantic-pass rate are structurally independent**

A quarantined source never reaches the semantic gate (it fails before validation completes). So quarantine rate measures pre-semantic-gate failures; semantic-pass rate measures post-semantic-gate outcomes on the non-quarantined population. These are complementary, not redundant. Confirmed by `kdb_orchestrate.py:700` — `source_quarantined` fires on compile failure (pre-validation); `semantic_ok` is set during validation.

No finding here — the brief is correct.

---

### (c) Kills & the M1 migration

**F6. [Critical] · brief §2C link-resolution row, `kdb_graph/ingestor.py:309-346` · the M1 dangling-link rate CANNOT be computed from the graph alone — the ingestor silently drops dangling links**

The brief states the data source for link-resolution / dangling-link rate is `kdb_graph.queries` ("wikilink set vs entity set / `links_to_edges`"). This is incorrect.

Code check on `kdb_graph/ingestor.py` `_replace_outgoing_links()` (lines 309-346):
```python
# 2. Recreate per outgoing_links entry. The MATCH-with-two-patterns
# form silently skips when target doesn't exist.
for target in page.get("outgoing_links", []):
    conn.execute(
        "MATCH (a:Entity {slug: $a}), (b:Entity {slug: $b}) "
        "CREATE (a)-[:LINKS_TO ...]->(b)",
        ...
    )
```

The `MATCH-then-CREATE` pattern requires both endpoints to exist. If `target` isn't in the Entity table, the MATCH fails silently and no LINKS_TO edge is created. The dangling link **leaves no trace in the graph**.

Therefore, `links_to_edges()` (which returns only edges that exist in the graph) cannot identify dangling links. The KPI as defined is **uncomputable from graph queries alone**.

The correct computation requires **two data sources**:
1. **Declared links:** union of `page.outgoing_links` from `compile_result.json` (preserved in `state/runs/<run_id>/compile_result.json` per Stage 10 archival).
2. **Entity set:** all Entity slugs in the graph (available via `active_entities()` or `active_entity_slugs()` from `kdb_graph.queries`).

Dangling rate = |{declared links where target ∉ entity set}| / |{declared links}|.

This is a hybrid compute: compile-result (Pass-2 output) × graph state. It belongs in the `compiler/kpi/graph.py` module (per the directions doc's architecture) reading both sources.

**Suggested change:**
1. Amend the link-resolution data source from "`kdb_graph.queries`" to "`compile_result.json` outgoing_links ∪ `kdb_graph.queries.active_entity_slugs()`."
2. Add an implementation note: "Dangling links are invisible in the graph (ingestor silently drops them). KPI computation must read declared links from compile_result.json."
3. Consider whether the ingestor should record (not create) dangling links for measurement purposes — e.g., a `DANGLING_LINK` rel table or a sidecar log. This would make the KPI graph-native but adds schema complexity. Recommendation: don't add a rel table; the hybrid compute is simpler and the compile_result.json is always available for full-corpus benchmark runs.

---

**F7. [Medium] · brief §3, `validate_compile_result.py:115-170` · M2/M3 kill is correct for scoring but the pairing signal survives as a measure-severity finding — consider as diagnostic**

The brief kills M2 (concept_slugs Jaccard) and M3 (article_slugs Jaccard) because "that pairing model is gone after the 0.5.x ontology rebuild."

Code check: `validate_compile_result.py` `_check_source()` still checks concept/article slug pairing — but the findings are now **measure severity** (reconcilable), not gate errors:
- `pairing_commission` (measure): slug in list with no matching page — reconcilable by deletion.
- `pairing_type_mismatch` (measure): slug matches but page_type disagrees — reconcilable by slug-list rebuild.
- `pairing_omission` (measure): page exists but slug missing from list — reconcilable by addition.

Task #65 / D45 made all pairing findings reconcilable — `reconcile_slug_lists()` auto-fixes them before downstream processing. So the old M2/M3 Jaccard signal is now a measure of how much reconcile work was needed.

**The signal isn't entirely dead** — a model that produces many pairing defects forces more reconcile corrections, which is a quality signal (the model isn't emitting clean output). But it's correctly killed as a *scored* KPI because:
1. The reconcile stage auto-fixes the defects, so the final graph doesn't reflect them.
2. The defects are mechanical (slug-list ↔ page consistency), not semantic.

**Suggested change:** Consider adding a **diagnostic** KPI: "pairing-defect rate" — count of measure-severity findings from `validate_compile_result` per source. This is the natural successor to M2/M3: not scored (auto-fixed), but emitted for insight into how much reconcile cleanup each model requires. Low priority — the brief's kill is correct for scoring.

---

**F8. [Low] · brief §3, `compiler/validate_source_response.py:115` · M5 kill is correct**

M5 measured body `[[wikilink]]` coverage of declared slugs. Code check confirms body wikilinks (`body_wikilink_slugs()` at `validate_source_response.py:115`) are used in the old scorer but have **no programmatic role** in the current pipeline. The graph's LINKS_TO edges come from the LLM's structured `outgoing_links` field (`common/types.py` `PageIntent.outgoing_links`), not from body text parsing. Body wikilinks are Obsidian display artifacts.

The canonicalization stage does remap body wikilinks (`canonicalize.py:308` `_remap_body_wikilinks()`), but this is cosmetic — it updates display text, not graph structure.

Kill confirmed. No residual signal.

---

### (d) Graph-set completeness

**F9. [High] · brief §2C, fork 5, `kdb_graph/schema.py` · the scored graph set at two IS too lean — graph connectivity (component count) is a third genuinely directional, GT-free, model-discriminating signal**

The brief deliberately chose "two sharp directional signals" over a wider set. I agree link-resolution and BELONGS_TO coverage are sharp. But the brief asks whether there's a **third** — and there is.

**Proposed third KPI: graph connectivity — largest connected component ratio (↑)**

- **Definition:** Size of the largest connected component (treating LINKS_TO as undirected) ÷ total canonical entities. 1.0 = single connected graph; near 0 = highly fragmented.
- **Direction:** ↑ higher = better. A model that produces a single coherent graph is better than one that produces N isolated clusters.
- **GT-free:** Yes — internal graph structure only, no labels needed.
- **Model-discriminating:** Yes. Two models can be processing-clean (valid JSON, no quarantines) yet produce very different graph topologies. A model that emits thoughtful outgoing_links creates a connected web; a model that emits sparse or random links creates isolated clusters. This is exactly the "graph quality is the most model-discriminating axis" claim from the directions doc (§5).
- **Data source:** `kdb_graph.queries.links_to_edges()` + entity set → standard connected-components algorithm. Already computable from existing query primitives without any schema change.
- **Independence from link-resolution:** Low correlation. Link-resolution measures "do link targets exist?" (binary per link); connectivity measures "does the overall graph form a coherent structure?" (topological). A model could have 95% link-resolution but still produce a fragmented graph (many small clusters that internally resolve well but don't cross-link). Conversely, a model with 80% link-resolution could produce a well-connected graph if its dangling links are randomly distributed.

**Why not the other candidates:**
- **ALIAS_OF/dedup quality:** Alias emission is driven by the canonicalization stage (Python), not the model. The model emits surface forms; the canonicalizer decides what becomes an alias. This makes ALIAS_OF coverage more pipeline-quality than model-quality. Not clean for cross-model comparison.
- **Link reciprocity:** Non-directional. Asymmetric links (A→B without B→A) aren't provably worse — many valid knowledge structures have directed references.
- **Domain breadth:** Correctly classified as diagnostic (non-directional).

**Suggested change:** Add **graph connectivity (largest component ratio, ↑)** as a third scored graph KPI. Data source: `kdb_graph.queries.links_to_edges()` + `active_entity_slugs()`. This directly addresses the "most model-discriminating axis" claim and gives the graph family the weight it deserves without relying solely on weight tuning.

---

**F10. [Low] · brief §2C · orphan rate as "watched diagnostic" is correctly classified**

The brief's two reasons for demoting orphan rate are sound:
1. Correlation with link-resolution (both measure linking richness).
2. Possible near-zero-for-all spread.

Code check confirms orphan detection works via `_detect_and_mark_orphans()` in `ingestor.py` — entities with zero SUPPORTS get `status='orphan_candidate'`. `orphan_entities()` in `queries.py` reads this flag. The classification is correct: orphan status is a downstream consequence of poor SUPPORTS, which is itself a consequence of poor entity extraction — correlated with, but not identical to, link-resolution.

The "promote if first run shows real spread" rule is the right data-before-principle approach.

No change needed.

---

### (e) Classification & normalization

**F11. [Medium] · brief §2C, fork 4 · link-resolution (dangling-link rate) should be ratio pass-through, NOT per-token — the brief is correct but should state why explicitly**

The brief tags link-resolution as a coverage/pass-rate (ratio pass-through). For the reformulated KPI (dangling/total-declared-links), this is correct:

- It's already a 0–1 ratio: dangling_count / total_declared_links.
- Per-token normalization would distort cross-model comparison: a model that emits more links per token would have a lower per-token dangling rate even with the same fraction of dangling links. The ratio correctly normalizes by the model's own link volume.
- The denominator (total declared links) is model-controlled — different models emit different numbers of links. The ratio accounts for this naturally.

**Suggested change:** Add an explicit normalization note: "Dangling-link rate is a ratio (dangling / total-declared-links), not per-token. The denominator is model-controlled (models emit different numbers of links); the ratio normalizes by each model's own link volume."

---

**F12. [Medium] · brief §2A · retry load normalization should be ratio, not per-token**

The brief classifies all four robustness KPIs as "per-token." For retry load, this is debatable. Retry load is defined as "fraction of retry budget consumed (`attempts > 1`), normalized." The old scorer (`scorer.py` `retry_load()`) computes it as `Σ min(MAX_RETRIES, max(0, attempts-1)) / (|R| × MAX_RETRIES)` — a **ratio** (cap-normalized fraction), not a per-token rate.

If reformulated as per-token (retries per 1M tokens), a model processing long sources would be unfairly penalized: a single retry on a 10K-token source contributes more per-token than a single retry on a 500-token source, even though the retry behavior is the same.

The other three (quarantine, token-overrun, repair-rung) are correctly per-token because they're **event rates** (how often do failures happen per volume processed). Retry load is a **budget consumption fraction** — inherently a ratio.

**Suggested change:** Re-classify retry load normalization from per-token to ratio pass-through (cap-normalized fraction). This matches the existing scorer implementation and avoids penalizing models for processing longer sources.

---

**F13. [Low] · brief §2A · token-overrun and repair-rung correctly per-token**

- Token-overrun: count of responses hitting `max_tokens` stop reason, per 1M tokens processed. Event rate. Per-token correct.
- Repair-rung: count of repair interventions, per 1M tokens. Event rate. Per-token correct.

Both are genuinely "how often does this event happen per volume processed." No issue.

---

### (f) Pass-1 / #108 coupling

**F14. [Medium] · brief §4 fork 1, `ingestion/enrich/pass1_caller.py:24-30` · Pass-1 telemetry IS computed but discarded — contract-first is the right sequencing**

Code check confirms the brief's claim:
- `pass1_caller.py` `Pass1CallResult` (line 24) carries `input_tokens`, `output_tokens`, `latency_ms`, `attempts` — all the fields needed for Pass-1 robustness telemetry.
- `call_pass1()` returns these fields on success (line 90+) and on failure (line 106+).
- But the orchestrator (`kdb_orchestrate.py`) only records `source_quarantined` events (line 610, line 700) — it does NOT persist the per-source Pass-1 call telemetry to any durable store. The `Pass1CallResult` fields are consumed in-memory and lost.

The brief's fork: (a) spec a Pass-1 telemetry record as a *contract* here, or (b) fold #108's scope into this design.

**Recommendation: option (a) — contract-first.** Reasons:
1. The `Pass1CallResult` dataclass already defines the shape. The contract is essentially: "persist `Pass1CallResult` alongside `RespStatsRecord` for each source."
2. #108's repair ladder is a separate implementation effort. Coupling the KPI spec to #108's timeline delays the benchmark unnecessarily.
3. The KPI framework can consume Pass-1 telemetry when it becomes available without redesigning the KPI definitions.

**Suggested change:** Add a §2A note: "Pass-1 robustness KPIs (retry, token-overrun, repair-rung) are Pass-2-only until #108 lands. Contract: when Pass-1 telemetry becomes available, it will mirror `RespStatsRecord` fields (`attempts`, `token_overrun`, `syntax_repaired`, `final_status`) in a persisted `Pass1CallResult`. The KPI framework will aggregate Pass-1 + Pass-2 records per-run without KPI definition changes."

---

**F15. [Low] · brief §2B · Pass-1 quality is genuinely unmeasurable GT-free beyond signal/noise**

The brief asks whether there's a GT-free Pass-1 quality signal worth scoring beyond the non-directional signal/noise ratio.

After reviewing the Pass-1 schema (`pass1_schema.py`), the LLM emits 11 content fields: `kdb_signal`, `domain`, `source_type`, `author`, `summary`, `key_themes`, `entity_search_keys`, `confidence`, `uncertainty_reason`, `reject_reason`, `other_reason`.

Possible Pass-1 quality signals:
- **Classification confidence distribution:** mean/median of `confidence` field. But not directional without GT — a model that always says 0.95 confidence isn't necessarily better than one that varies.
- **Domain distribution entropy:** how evenly the model spreads sources across domains. Not directional — could be over-splitting or over-lumping.
- **entity_search_keys yield:** average number of entity search keys per source. Not directional — more keys ≠ better (could be noisy).

None of these have a defensible "higher = better" direction without ground truth. The brief's conclusion is correct: Pass-1 quality is genuinely unmeasurable GT-free beyond signal/noise, and signal/noise is correctly diagnostic.

No change needed.

---

### (g) Blind spots / omissions

**F16. [High] · brief §2 overall · canonicalization / alias quality is the most important missing category**

The pipeline has a full canonicalization stage (`compiler/canonicalize.py` — 500+ lines, 5-pass algorithm including body wikilink remapping, slug normalization, alias detection). This stage processes every source's output. Yet no KPI measures canonicalization behavior.

**Why this matters for cross-model comparison:** Different models produce different surface-form distributions. Model A consistently emits "warren-buffett" (clean); Model B emits "Warren Buffett", "warren-buffett", and "Buffett" across sources. The canonicalizer works harder for Model B — more alias merges, more slug coercions, more body remaps. This is a real quality difference that the current KPI list is blind to.

**Candidate KPI (diagnostic):** `canonicalization-intervention rate` — count of canonicalization actions (slug coercions + alias merges + body remaps) per 1M tokens. Non-directional (some interventions are the canonicalizer doing its job correctly on valid surface-form variation; zero interventions might mean the model is already clean, or that it's emitting so few entities there's nothing to canonicalize). Emitted as diagnostic for insight.

**Candidate KPI (scored, if directionality can be established):** `entity fragmentation proxy` — ratio of alias entities to canonical entities. Lower = model produces more consistent surface forms = less fragmentation. Direction: ↓ lower = better. GT-free (uses only graph ALIAS_OF edges). Model-discriminating (different models will have different alias rates). But: the canonicalizer, not the model, creates ALIAS_OF edges — so this measures canonicalizer behavior as much as model behavior. Not clean enough for scoring.

**Suggested change:** Add `canonicalization-intervention rate` as a **diagnostic** KPI (weight 0). Data source: canonicalization stage logs (count of interventions per stage). This fills the most important blind spot without overcommitting to a scored KPI that conflates model and pipeline behavior. Revisit for scoring after first multi-model run shows whether models produce materially different surface-form distributions.

---

**F17. [Medium] · brief §2 overall · cross-run stability is a known blind spot but correctly out of scope**

For a compiler, running the same model twice on the same corpus should produce similar graphs. This isn't measured. But the brief explicitly scopes to "latest run per model, no historical averaging" (§5 settled set). Cross-run stability requires multiple runs per model, which conflicts with the "no historical averaging" decision.

This is a known gap. It's correctly deferred — it requires a different benchmark mode (repeat runs) that's out of scope for this design.

No change needed, but flag for the future benchmark roadmap.

---

**F18. [Low] · brief §2C · SUPPORTS density's "no direction" claim is correct for the full range but may miss a floor effect**

The brief classifies SUPPORTS density (entities per source) as non-directional ("more isn't better"). For the full range, this is correct — a model that extracts 50 entities per source isn't better than one that extracts 10; it might be noisier.

But there's a **floor effect**: a model that extracts 1 entity per source is clearly broken (the compiler's value proposition is entity extraction). Below a floor (~2-3 entities/source), lower is definitely worse. This is a threshold-gated direction, not a monotone direction — so it can't be a Borda-scored KPI.

**Suggested change:** No change to classification (diagnostic stays diagnostic). But add a threshold alert to the diagnostic output: "SUPPORTS density below 2.0 entities/source flagged as potential extraction failure." This gives the diagnostic actionable signal without misclassifying it as scored.

---

## 3. Weights & graph/processing balance (fork 2)

The brief's scored set is 5 processing + 2 graph. The directions doc (§5) says graph quality is "plausibly the most model-discriminating axis." The brief asks whether to up-weight graph or accept the lean set.

**With F9 adopted (graph connectivity as third scored graph KPI):** the set becomes 5 processing + 3 graph. At 3 graph KPIs, equal per-KPI weights give graph ~37.5% of the total Borda score — a meaningful share without papering over the processing signals. This is the right balance: the real fix IS finding a third graph KPI (per F9), not up-weighting two.

**If F9 is NOT adopted:** up-weighting graph to ~40% total (e.g., each graph KPI at 1.5× the weight of each processing KPI) would be defensible but fragile — two KPIs carrying that much weight means a single noisy measurement dominates the score. Adding the third KPI is strictly more robust.

---

## 4. Promotion criteria (fork 3)

The brief asks about promotion rules for watched diagnostics. Suggested framework:

**Promotion rule:** "Promote a watched diagnostic to scored if, on the first ≥3-model benchmark run, the cross-model coefficient of variation (CV = σ/μ) exceeds 0.25 AND the interquartile range (IQR) excludes zero." This combines two criteria:
1. **Meaningful spread** (CV > 0.25): models actually differ, so the KPI discriminates.
2. **Non-trivial values** (IQR excludes zero): the KPI isn't near-zero for all models (a near-zero-for-all KPI would produce noisy Borda rankings).

Demotion rule: "Demote a scored KPI to diagnostic if, after 3 benchmark runs, CV < 0.10 consistently." This catches KPIs that looked directional in theory but don't discriminate in practice.

---

## 5. Bottom line

The KPI list is sound enough to turn into an anchors/weights spec **after folding in two must-fix changes**:

1. **F6 (Critical):** Correct the M1 / link-resolution data source — it requires `compile_result.json` + graph entity set, not graph queries alone. The dangling-link rate is uncomputable from the graph because the ingestor silently drops dangling links.
2. **F9 (High):** Add **graph connectivity (largest component ratio, ↑)** as a third scored graph KPI. This is the decision most likely to be wrong in the current brief: the scored graph set at two is too lean, not because the two chosen KPIs are weak, but because the "graph quality is the most model-discriminating axis" claim demands more than two signals. Graph connectivity is genuinely directional, GT-free, model-discriminating, independent from link-resolution, and computable from existing query primitives. Leaving it out means the benchmark's graph family is underpowered relative to the claim.

The remaining medium-severity findings (F4 repair/retry overlap acknowledgment, F11/F12 normalization corrections, F14 Pass-1 contract-first sequencing, F16 canonicalization diagnostic) are refinements that should be folded in but don't block the spec.

**On the "is the scored graph set too lean at two" fork:** Yes, it is too lean. Two is one short of what the claim requires and what the data supports. Add graph connectivity as the third. This makes the graph family robust enough to carry the weight the brief wants to give it, without relying on weight inflation to compensate for a thin signal set.
