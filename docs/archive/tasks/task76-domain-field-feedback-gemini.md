# External Review: Task #76 — Round 5 `domain` field implementation (blueprint v1)
**Reviewer:** Gemini 3.5 Flash (High) — Antigravity Alter Ego
**Date:** 2026-05-21
**Target Doc:** `docs/task76-domain-field-blueprint.md` (v1 draft)
**Context:** Prepared as targeted review feedback to guide Claude (Opus) in upgrading the blueprint to v2.

---

## 1. Architectural Fit Assessment (Option B)

### 1.1 Alignment with Round 5 §7.3 (C2 Calibration)
*   **Coordinate, Not Gate:** Option B (separate `Domain` nodes + `BELONGS_TO` edges) is a highly compliant architectural fit. By storing domains as separate nodes linked via relationships, we treat domain as a first-class coordinate on the graph, matching the "domain as coordinate, not gate" philosophy. Ingestion remains open and schemaless-ish; partitioning happens purely at query time.
*   **Vocabulary Freedom:** Option B captures plain-text, unconstrained domain names without imposing a rigid upfront controlled vocabulary, preserving the stochastic pattern-matching nature of Philosophy B.

### 1.2 Alignment with Task #75 §6.1 Narrowing
*   **Gate Count Integrity:** Task #75 §6.1 establishes that the `domain` field's critical-path role is to support the **community/domain-ratio acceptance gate** (`n_communities ≥ 1.5 × n_distinct_domains`) and empirical hedge-watch rule **HW-3** (domain re-discovery). 
*   **Structural Superiority over Option A:** Option A (flat property on `Entity`) would require a `SELECT DISTINCT domain` string scan to calculate `n_distinct_domains`. This makes the gate formula highly vulnerable to spelling and casing drift. Option B maintains an authoritative, enumerable set of canonical `Domain` nodes (`MATCH (d:Domain) RETURN count(d)`). When paired with aggressive ingest-side normalization (OQ-3), this ensures that the distinct-domain count is statistically stable and mathematically reliable for the gate formula.
*   **YAGNI for Option C:** Option C (`PART_OF` taxonomy) is correctly deferred as speculative. Since no planned step-3 query or gate requires parent-child traversal, Option B keeps the Cypher codebase clean and readable.

---

## 2. Review and Resolutions of the 10 Open Questions (OQ-1..OQ-10)

### OQ-1: Tagging Granularity (Entity-level vs. Source-level)
*   **Resolution:** **(a) Entity-level.**
*   **Rationale:** Tagging at the source level (b) would cause high graph entropy. Fanning out a source's main domain (e.g., `"deep-learning"`) to every entity mentioned in it would mistakenly tag generic entities (like `"google"`, `"gpu"`, or `"python"`) as deep learning coordinates. Entity-level tagging preserves the precision of the coordinate space.

### OQ-2: Multi-domain Cap
*   **Resolution:** **(b) Soft cap N=5** (JSON schema) and prompting for 1–3 max.
*   **Rationale:** Strikes the ideal balance. It supports realistic polymath entities (e.g., `karl-marx` spanning history, economics, and philosophy) while preventing "domain inflation" (where the LLM over-tags everything, diluting the utility of the coordinate).

### OQ-3: Domain Name Normalization
*   **Resolution:** **(a) Aggressive normalize at ingest.**
*   **Rationale:** Crucial to prevent casing and spacing drift from corrupting the community/domain-ratio gate.
*   **Refinement:** The v1 regex `re.sub(r"\s+", "-", ...)` handles spaces but fails on consecutive dashes (e.g. `"value - investing"`, `"value--investing"`) or trailing punctuation (e.g., `"investing."`). We recommend upgrading the regex to collapse spaces/dashes and strip non-alphanumeric punctuation.

### OQ-4: `sub_domain` Shape
*   **Resolution:** **Stay with property-on-edge (Option B).**
*   **Critical Catch:** There is a structural mismatch in v1's pseudocode. If an entity has *multiple* domains (OQ-2) but a single `sub_domain` string, the v1 pseudocode attaches that `sub_domain` to *every* domain edge. For example, if domains are `["investing", "biography"]` and sub-domain is `"value-investing"`, `"value-investing"` would be incorrectly linked as a subdomain of `"biography"`.
*   **Resolution:** The adapter should attach the `sub_domain` property **only to the first (primary) domain** in the list.

### OQ-5: Capture `confidence` on `BELONGS_TO`?
*   **Resolution:** **(b) Skip.**
*   **Rationale:** Page-level confidence already exists. Edge confidence adds prompt overhead and ingest ceremony with zero current query utilization (YAGNI).

### OQ-6: Backfill
*   **Resolution:** **(B1) Lazy.**
*   **Rationale:** Prevents high-cost, automated LLM API calls during migrations. Fully backward-compatible since the adapter handles missing fields gracefully.

### OQ-7: Operator Inspection CLI
*   **Resolution:** **(a) Include.**
*   **Rationale:** Immediate observability into what domains the LLM is emitting is invaluable for early prompt tuning and drift monitoring. Recommend adding a simple `graphdb-kdb domains list` command.

### OQ-8: Schema Additivity
*   **Resolution:** **(a) Additive only.**
*   **Rationale:** Mandatory for maintaining D39 replay-eligibility of historical journals.

### OQ-9: Multi-source Domain Consensus
*   **Resolution:** **(a) Additive.**
*   **Rationale:** Standard graph-native practice. 
*   **Architectural Insight:** Because KDB relies on `graphdb-kdb rebuild` to construct the graph from compiled journals, stale or orphaned domain edges from modified sources are automatically purged during rebuilds. This makes the incremental ingest path simple and robust without requiring complex tombstone tracking.

### OQ-10: Alias Entity Domain Propagation
*   **Resolution:** **(a) Canonical only.**
*   **Rationale:** Aligns with "canonical is the authority" from Task #74.
*   **Architectural Insight:** During ingestion, the adapter can build a fast lookup map `alias_to_canonical` from `cr["canonical_meta"]["aliases_emitted"]` (which is present in the same compile result payload). This allows resolving page slugs to their canonical slugs *before* writing the `BELONGS_TO` edge. To prevent matching failures on cold starts, the adapter should run a quick `MERGE` on the canonical entity slug.

---

## 3. Targeted Revisions to Blueprint v1 for Opus (v2 Upgrades)

To upgrade the blueprint to v2, apply the following edits directly to `docs/task76-domain-field-blueprint.md`:

### Revision 3.1: OQ-1 Lean (tagging granularity)
In §8, OQ-1:
```diff
- **Lean: (a) Entity-level.** Matches §7.3 literal query; preserves
- granularity; aligns with "LLM-extracted at compilation". The cost is
- slightly more LLM tokens per page — acceptable.
+ **Lean: (a) Entity-level.** Matches §7.3 literal query and preserves granularity. 
+ Crucially, source-level fan-out (b) would over-tag generic entities mentioned in 
+ specific sources (e.g., tagging 'Google' or 'GPU' as 'deep-learning' because they 
+ appear in a machine learning paper), resulting in high graph entropy and degraded 
+ domain-filtering precision. The slightly higher token cost is acceptable.
```

### Revision 3.2: OQ-2 Lean (multi-domain cap)
In §8, OQ-2:
```diff
- **Lean: (b).** Plural anticipated, but if LLM goes wild and emits 10
- domains per entity, the Domain table inflates with low-signal tags.
- Soft cap protects without forbidding.
+ **Lean: (b) Soft cap N=5.** Plural is anticipated, but a soft cap protects the 
+ coordinate space from dilution (excessive density) while still supporting 
+ realistic multi-domain spans for polymath entities.
```

### Revision 3.3: Ingest-side Normalization Regex
In §6.3, update the normalization regex:
```diff
-        d_norm = re.sub(r"\s+", "-", d.strip().lower())
+        # Collapses consecutive spaces/dashes and strips non-alphanumeric punctuation
+        d_norm = re.sub(r"[^a-z0-9-]+", "", re.sub(r"[-\s]+", "-", d.strip().lower()))
```
And in §8, OQ-3:
```diff
- **Lean: (a).** Protects HW-3 distinct-domain count from arbitrary
- LLM-output drift; cheap and reversible (we can see if (a) over-
- collapses by inspecting the Domain set after the first compile
- cycle). We deliberately do *not* introduce a richer domain-
- canonicalization layer (Task #74-shaped Levenshtein/LLM-judge work)
- unless aggressive-normalize proves insufficient.
+ **Lean: (a) Aggressive normalize at ingest.** Collapses casing, spacing, and 
+ punctuation drift to protect the distinct-domain count needed for the HW-3 hedge.
+ The normalizer collapses consecutive spaces/dashes and strips non-alphanumeric chars
+ (e.g. "investing." and "value--investing" both canonicalize correctly). Richer 
+ canonicalization layers (Task #74-shaped) are deferred.
```

### Revision 3.4: Resolve Sub-domain Multi-domain Mismatch
In §6.3, update the pseudocode loop in `_ingest_page_domains` to assign `sub_domain` only to the primary (first) domain:
```diff
-    sub_domain = page_dict.get("sub_domain")
-    for d in domains:
+    sub_domain = page_dict.get("sub_domain")
+    for i, d in enumerate(domains):
-        d_norm = re.sub(r"\s+", "-", d.strip().lower())
+        d_norm = re.sub(r"[^a-z0-9-]+", "", re.sub(r"[-\s]+", "-", d.strip().lower()))
+        # Multi-domain safety: associate sub_domain with the primary (first) domain only
+        sub = sub_domain if i == 0 else None
         # MERGE Domain
         conn.execute(
             "MERGE (d:Domain {name: $name}) "
             "ON CREATE SET d.created_at = $ts, d.first_run_id = $run_id",
             {"name": d_norm, "ts": created_at, "run_id": run_id},
         )
         # MERGE BELONGS_TO edge
         conn.execute(
             "MATCH (e:Entity {slug: $slug}), (d:Domain {name: $name}) "
             "MERGE (e)-[r:BELONGS_TO]->(d) "
             "ON CREATE SET r.run_id = $run_id, r.created_at = $ts, "
             "              r.sub_domain = $sub "
             "ON MATCH SET r.run_id = $run_id, r.created_at = $ts",
-            {"slug": entity_slug, "name": d_norm, "run_id": run_id,
-             "ts": created_at, "sub": sub_domain},
+            {"slug": entity_slug, "name": d_norm, "run_id": run_id,
+             "ts": created_at, "sub": sub},
         )
```

### Revision 3.5: Schema Delta DDL Cleanup
In §6.2, remove the deferred `confidence` mentions from the schema delta definition to align with OQ-5 Skip:
```diff
 CREATE REL TABLE BELONGS_TO (
     FROM Entity TO Domain,
     run_id      STRING,
     created_at  STRING,
-    sub_domain  STRING   -- nullable; LLM's narrower label if emitted.
-                         -- `confidence` column deferred per OQ-5.
+    sub_domain  STRING    -- nullable; LLM's narrower label if emitted.
 )
```
And in §8, OQ-5:
```diff
- **Lean: (b) skip.** No current query needs it. Promotable later.
- Removing the `confidence STRING` from §6.2 DDL if (b) is selected.
+ **Lean: (b) Skip.** Confirmed. Page-level confidence already exists; edge 
+ confidence is unnecessary overhead (YAGNI).
```

### Revision 3.6: OQ-6 Lean (backfill)
In §8, OQ-6:
```diff
- **Lean: B1.** Single-user, no urgency, gate is diagnostic. User can
- fire B2 anytime via `kdb-compile --all`.
+ **Lean: B1 (Lazy).** Confirmed. Standardizes migration non-destructiveness and 
+ prevents automatic high-cost LLM API invocations.
```

### Revision 3.7: CLI Command Section
Add a new subsection in §6 of the blueprint:
```markdown
### 6.6 CLI Command Delta (`graphdb-kdb domains list`)
Executes the following query to list domains, sorted by popularity:
```cypher
MATCH (e:Entity)-[:BELONGS_TO]->(d:Domain)
RETURN d.name AS domain, count(e) AS entities, d.first_run_id AS first_run
ORDER BY entities DESC
```
And update §8, OQ-7:
```diff
- **Lean: (a).** Tiny addition; valuable for inspecting LLM output
- early. Command: `graphdb-kdb domains list` → prints
- `name, n_entities, first_run_id` per Domain.
+ **Lean: (a) Include.** Confirmed. Provides immediate developer observability 
+ into LLM extraction behavior during bootstrapping.
```

### Revision 3.8: OQ-8 Lean (schema additivity)
In §8, OQ-8:
```diff
- **Lean: (a).** Matches the Task #74 canonical_meta precedent (added
- optionally without journal-version bump). Adapter handles "domain
- missing" gracefully by skipping the BELONGS_TO insert.
+ **Lean: (a) Additive only.** Confirmed. Crucial for D39 replay-eligibility.
```

### Revision 3.9: OQ-9 Lean (multi-source consensus)
In §8, OQ-9:
```diff
- **Lean: (a) additive.** Matches the "coordinate, not gate" stance —
- we capture all signals; queries can filter by edge property
- (`run_id`) if needed.
+ **Lean: (a) Additive.** Confirmed. Graph captures all signals natively. 
+ Crucially, KDB's rebuild-friendly architecture (`graphdb-kdb rebuild`) naturally 
+ purges stale edges from historical compile results when a source is deleted or 
+ recompiled differently. This avoids complex tombstone or deletion logic in the 
+ incremental ingest path.
```

### Revision 3.10: OQ-10 Lean (alias propagation)
In §8, OQ-10:
```diff
- **Lean: (a) canonical only.** Cleaner; aligns with "canonical is the
- authority" stance from #74. Adapter resolves alias slug → canonical
- slug before edge insert (small adapter change to wire into existing
- canonicalization helpers). Queries that hit aliases must traverse
- `canonical_id` (already required for many post-#74 queries).
+ **Lean: (a) Canonical only.** Confirmed. Keeps the canonical entity as the source 
+ of truth.
+ 
+ **Ingest implementation:**
+ 1. Pre-build a fast `alias_to_canonical` lookup map from the run's 
+    `cr["canonical_meta"]["aliases_emitted"]` list.
+ 2. Resolve the page slug to its canonical slug prior to processing domain edges.
+ 3. To prevent match failures on new canonical entities, run:
+    `MERGE (e:Entity {slug: $canonical_slug}) ON CREATE SET e.status = 'canonical'`
+    prior to creating the `BELONGS_TO` edge.
```
