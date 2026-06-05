# Benchmark KPI Enumeration — Panel Review (Gemini)

**Date:** 2026-06-05 · **Reviewer:** Gemini (Staff Architect & Thought-Partner)
**Verdict:** `REWORK`

---

## 1. One-paragraph bottom line

While the overall architectural directions (such as Borda scoring, per-token normalization, and full-corpus sandbox runs) are solid and should remain locked, the proposed **KPI list requires a rework before proceeding to the anchors/weights specification**. Two of the core load-bearing KPI designs are mathematically flawed under a ground-truth-free (GT-free) regime: `BELONGS_TO` coverage is a dead metric that will return a flat 100% for all models, and the graph-level dangling-link rate is physically uncomputable from the Kuzu database alone because the ingestor silently drops unresolved link targets. This leaves the scored graph set with zero working indicators. Furthermore, the `semantic-pass rate` is 100% redundant with the `quarantine rate` because the semantic check acts as a hard gate within the compilation loop. We recommend separating Pass-1/Pass-2 telemetry denominators, dropping the redundant semantic gate, and introducing **Dangling Alias Rate** and **Dangling Claim Reference Rate** to provide genuine, model-discriminating, and queryable graph-quality metrics.

---

## 2. Findings & Recommendations

### (a) Scored-vs-diagnostic & directionality

#### Finding 1: `BELONGS_TO` coverage is a dead metric (Trivially 100%)
* **Severity:** Critical
* **Citations:** brief §2C (`BELONGS_TO` coverage definition), [kdb_graph/ingestor.py:512-518](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_graph/ingestor.py#L512-L518) (`rederive_domains`)
* **Flaw:** In `rederive_domains()`, `BELONGS_TO` edges are dynamically derived by matching `(s:Source)-[:SUPPORTS]->(e:Entity)` where `s.domain` is populated. Because every canonical `Entity` in the graph is upserted from a page in a compiled source, every canonical entity has a `SUPPORTS` edge from its originating source. During benchmark runs, every compiled source goes through Pass-1 classification, which enforces that `domain` is a required string in the controlled vocabulary. Consequently, every canonical entity will always have at least one `BELONGS_TO` edge to its source's domain. `BELONGS_TO` coverage will evaluate to exactly 1.0 (100%) for all models.
* **Why it matters:** As a scored KPI, it has zero variance and zero model-discriminating power, diluting the Borda scoring system.
* **Concrete change:** Demote `BELONGS_TO` coverage to diagnostic. If domain accuracy is to be scored, it must be evaluated via a different semantic validation or replaced by a real structural metric like **Dangling Alias Rate** (see group d).

---

### (b) Double-counting / redundancy

#### Finding 2: `semantic-pass rate` is 100% redundant with `quarantine rate`
* **Severity:** High
* **Citations:** brief §2B (`semantic-pass rate`), [compiler/compiler.py:391-406](file:///home/ftu/Droidoes/Obsidian-KDB/compiler/compiler.py#L391-L406) (`compile_one` retry loop)
* **Flaw:** The semantic gate check (`validate_source_response.semantic_check`) runs *inside* the main compilation retry loop of `compile_one`. If a source fails semantic validation on its final attempt, it sets `state["error"]` and returns `None`, which sets its `final_status` to `"quarantined"`. If it succeeds, `state["semantic_ok"]` is `True`. Thus, `state["semantic_ok"]` is exactly `True` if and only if compilation succeeds (i.e., `final_status != "quarantined"`).
* **Why it matters:** Scoring both `quarantine rate` and `semantic-pass rate` double-counts the exact same failure mode, over-weighting the same pipeline exit path.
* **Concrete change:** Drop `semantic-pass rate` as a standalone scored processing metric. Robustness is already captured by the quarantine/retry/repair metrics.

#### Finding 3: Over-weighting processing robustness via overlapping metrics
* **Severity:** Medium
* **Citations:** brief §2A (Processing - per-run)
* **Flaw:** Scoring `quarantine rate`, `retry load`, and `repair-rung usage` together over-weights output formatting compliance. These are highly correlated steps of the same progressive repair ladder.
* **Why it matters:** A model's formatting failures will cascade through repair rungs, retries, and quarantines, penalizing the model multiple times on the same underlying issue and masking graph-quality signals.
* **Concrete change:** Combine `retry load` and `repair-rung usage` into a single "friction index" or reduce their individual weights to ensure processing robustness does not drown out graph topology quality.

---

### (c) Kills & the M1 migration

#### Finding 4: Dangling-link rate is not computable from the GraphDB alone
* **Severity:** High
* **Citations:** brief §2C and §3 (M1 migration), [kdb_graph/ingestor.py:317-319](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_graph/ingestor.py#L317-L319) (`_replace_outgoing_links`)
* **Flaw:** During ingestion, `_replace_outgoing_links` silently skips creating a `LINKS_TO` edge if the target slug does not exist as an Entity node. The raw markdown body text is not persisted on the `Entity` node. Consequently, the Kuzu GraphDB contains no record of the unresolved target slugs. A Cypher query over `LINKS_TO` edges will only see resolved target nodes, making it impossible to detect which links failed to resolve from the database state alone.
* **Why it matters:** The dangling-link rate cannot be computed as a "pure" graph-level query. It requires a hybrid calculation that reads the Pass-2 output (`RespStatsRecord.parsed_json`'s `pages[].outgoing_links`) and checks them against the set of active entity slugs in the database.
* **Concrete change:** Classify dangling-link rate as a hybrid KPI (requiring both telemetry records and graph entity sets) and clarify its computation formula, or update the ingestor schema to write unresolved links to a `dangling_links` string array on the source/entity node.

#### Finding 5: Kills (M2, M3, M5) are correct
* **Severity:** Low
* **Citations:** brief §3 (Disposition of old metrics), [compiler/compiler.py:411-415](file:///home/ftu/Droidoes/Obsidian-KDB/compiler/compiler.py#L411-L415) (`reconcile_slug_list`)
* **Flaw:** None. Because `reconcile_slug_list` mechanically overwrites the declared concept/article slug lists to match page emits, the pairing similarity for M2/M3 is always 1.0. Furthermore, body wikilinks are no longer the primary edge definition in the Kuzu graph, rendering M5 obsolete.
* **Why it matters:** Eliminating these metrics prevents wasting benchmark run cycles on dummy constants.
* **Concrete change:** Confirm the kill of M2, M3, and M5.

---

### (d) Graph-set completeness

#### Finding 6: Graph scored set has zero working metrics
* **Severity:** Critical
* **Citations:** brief §2C (Graph metrics)
* **Flaw:** With `BELONGS_TO` coverage being a flat 100% constant (Finding 1) and dangling-link rate being unqueryable from Kuzu alone (Finding 4), the scored graph KPI set is effectively empty of valid, pure-graph signals.
* **Why it matters:** The benchmark is blind to the primary quality axis of a graph compiler.
* **Concrete change:** Introduce two new, pure-graph, directional, and queryable KPIs:
  1. **Dangling Alias Rate:** Measures alias Entity nodes whose `canonical_id` targets do not exist in the graph (representing broken alias linkages). This is queryable from Kuzu:
     ```cypher
     MATCH (e:Entity) 
     WHERE e.canonical_id IS NOT NULL 
       AND NOT EXISTS { MATCH (c:Entity {slug: e.canonical_id}) } 
     RETURN COUNT(e)
     ```
  2. **Dangling Claim Reference Rate:** Measures the fraction of `Claim` nodes whose `subject_slug`, `object_slugs`, or `predicate_scope_slugs` do not resolve to active canonical `Entity` nodes.

---

### (e) Classification & normalization

#### Finding 7: Dangling-link rate must use ratio normalization, not per-token
* **Severity:** High
* **Citations:** brief §2C, §4 (Fork 4)
* **Flaw:** If dangling-link rate is normalized per token, a model that generates a high volume of wikilinks (rich integration) but has 5 errors will be scored identically to a model that generates very few wikilinks (poor integration) and has 5 errors, assuming similar token counts.
* **Why it matters:** Per-token normalization distorts cross-model link-resolution skill. It must remain a ratio of `dangling links / total wikilinks` to represent link precision.
* **Concrete change:** Settle Fork 4 by enforcing ratio normalization for the dangling-link rate. Handle the zero-denominator edge case by assigning a default penalty score (1.0 rate of failure) if a model emits zero wikilinks.

#### Finding 8: Token denominator coupling distorting Pass-1 vs Pass-2 failure rates
* **Severity:** High
* **Citations:** brief §2A (Processing per-run), §4 (Fork 4)
* **Flaw:** Combining Pass-1 and Pass-2 telemetry into a single per-token rate is distorted. Pass-2 prompts include large context snapshots (containing surrounding entity states) and expect structured pages, making Pass-2 token volumes orders of magnitude larger than Pass-1 token volumes.
* **Why it matters:** If a model fails early in Pass-1, it will quarantines the source and never run Pass-2. Because Pass-1 token counts are small, a single Pass-1 quarantine results in an extremely high rate-per-token. Conversely, Pass-2's massive token volume will wash out Pass-2 failure rates.
* **Concrete change:** Separate Pass-1 and Pass-2 processing metrics. Normalize Pass-1 failures on a per-source basis (since Pass-1 always processes the same 36 scanned sources), and keep token-level normalization restricted to Pass-2.

---

### (f) Pass-1 / #108 coupling

#### Finding 9: Pass-1 telemetry is already persisted in sidecars (Fact Check)
* **Severity:** Medium
* **Citations:** brief §4 (Fork 1), [ingestion/enrich/enrich.py:139-143](file:///home/ftu/Droidoes/Obsidian-KDB/ingestion/enrich/enrich.py#L139-L143)
* **Flaw:** The brief states that `pass1_caller` computes `attempts`/tokens/latency but discards them. However, `enrich.py` writes them to the JSON sidecar file in the run directory under the `raw_response` property of the `SidecarPayload`.
* **Why it matters:** The benchmark script can extract Pass-1 metrics today by reading these sidecars. There is no need to block the benchmark framework on Task #108.
* **Concrete change:** Settle Fork 1 by adopting option (a): define the sidecar JSON structure as the contract for Pass-1 telemetry and read it directly.

---

### (g) Blind spots / omissions

#### Finding 10: Complete omission of the Claim layer
* **Severity:** High
* **Citations:** brief §10 (Omissions)
* **Flaw:** The proposed KPI list includes zero metrics for the `Claim` layer (introduced in v2.2), which represents the core semantic output of the compiler.
* **Why it matters:** A model could output syntactically valid pages but completely fail to extract claims, extract empty claim lists, or reference non-existent entity slugs.
* **Concrete change:** Introduce **Dangling Claim Reference Rate** (see Finding 6) as a scored graph-level KPI, and keep claim yield (claims per entity) as a diagnostic.
