# Independent Second Opinion: Round 6 Review of Task #90 Context-loader T2-rewrite
**Reviewer:** agy (Gemini 3.5 Flash)
**Date:** 2026-05-27

---

## 1. Convergence

The core architectural direction proposed in the v0.1 blueprint (`docs/task90-context-loader-t2-rewrite-blueprint.md`) is highly sound and represents an elegant closing of the Pass-1 ↔ Context-loader loop. 

*   **Option A Architecture:** The selection of Option A (clean replacement with legacy fallback) is the correct production default. Seeding T2 strictly from the curated `entity_search_keys` list on enriched sources enforces the structural discipline of the ingestion pipeline.
*   **The T2Mode Enum Dispatch:** Building the `T2Mode` enum (`STRUCTURED`, `LAYERED`, `LEGACY`) directly into the dispatcher is an excellent design choice. It avoids painting the codebase into an architectural corner, enabling side-by-side benchmarking under Task #91/NW-9.
*   **Alias Resolution Logic:** The proposed three reachability paths (Direct PK → `canonical_id` → `ALIAS_OF` edge) align perfectly with the graph model and promotion/retraction logic of Task #74.
*   **Incremental Migration Path:** The decision to let pre-Pass-1 sources fall back organically to the legacy regex path guarantees zero-disruption rollout, requiring no upfront vault-wide backfills or flag days.

---

## 2. Findings

### **Finding F-1: Loop-Query Contradiction in `_t2_from_search_keys` (N+1 Query Pattern)**
*   **Location:** §2.5 `_t2_from_search_keys` vs. §3.3 Implementation Note
*   **Analysis:** The blueprint's code sketch in §2.5 loops over `raw_keys` and executes a query inside each iteration via `_resolve_to_canonical_slug(conn, raw)`:
    ```python
    for raw in raw_keys:
        canonical = _resolve_to_canonical_slug(conn, raw) # Loop-embedded query
    ```
    However, §3.3 explicitly warns: *"For performance, the resolver in `_t2_from_search_keys` should batch the lookup rather than running 10 separate queries per source."* As written, §2.5 violates §3.3's performance directive, introducing an $N+1$ database query pattern for every compiled source.
*   **Impact:** Performance degradation during batch compile passes over large vaults.

### **Finding F-2: Zero-Verification Leak on `canonical_id` Targets in Batch Cypher**
*   **Location:** §3.3 Batch Cypher query
*   **Analysis:** The proposed Cypher query in §3.3 returns `e.canonical_id` directly without verifying that the target entity actually exists and is active in the graph:
    ```cypher
    WHEN e.canonical_id IS NOT NULL THEN e.canonical_id
    ```
    While the Python-side intersection `canonical in candidate_slugs` acts as a safety filter (since `candidate_slugs` only holds active graph slugs), returning unverified string properties from the database layer leaks validation responsibility to the application layer. If a target entity's status changes to `'inactive'` or it is deleted, the query will still blindly return the dead slug string.
*   **Impact:** Loose coupling between database state authority and returned resolution payload.

### **Finding F-3: Circular Import Dependency via `compiler.py`**
*   **Location:** §5 Code Surface (`kdb_compiler/planner.py` ↔ `kdb_compiler/compiler.py`)
*   **Analysis:** Option (i) in §6.2 outlines that `planner.py` will parse frontmatter by invoking `source_text_for()`. However, `source_text_for()` and the `SourceFrontmatter` dataclass are defined in `kdb_compiler/compiler.py`. Since `compiler.py` already imports `planner.py` to drive planning (`jobs = planner.plan(...)` at compiler.py:549), importing `compiler.py` at the module level in `planner.py` will trigger a Python **circular import error** at runtime.
*   **Impact:** Blocking runtime crash on compilation launch.

### **Finding F-4: Unnecessary Disk Double-Read at Plan-Time**
*   **Location:** §6.2 Option (i) Plumbing Rationale
*   **Analysis:** The blueprint states that Option (i) requires double-parsing which is cheap, but assumes `planner.py` and `compiler.py` will independently read the file from disk. In a large vault (1600+ files), reading every markdown file twice from disk under a single compile pass introduces significant, completely avoidable I/O overhead.
*   **Impact:** Sub-optimal compilation latency over large corpora.

### **Observation O-1: Redundant Slug-Matching in the Legacy Regex Branch**
*   **Location:** §2.4 `_t2_legacy`
*   **Analysis:** Today's `planner.py` does not strip YAML frontmatter before passing `source_text` to the regex matcher. As a result, the whole-word regex in `_t2_slug_in_text` matches slugs that appear purely inside the raw frontmatter fields (e.g. `domain` or `key_themes`). This is a known pre-Pass-1 characteristic. Retaining it for `_t2_legacy` is correct for strict regression testing, but we should explicitly note that structured T2 evaluation is cleaner because it completely isolates the text body from frontmatter matches.

---

## 3. Recommendations

### **Recommendation on Finding F-1 & F-2 (Batched Resolver)**
Refactor the helper signature to accept a batch of slugs and return a complete mapping of `{raw_slug: canonical_slug}` in one database round-trip. We should also extend the Cypher query to optionally match the `canonical_id` target node to verify its existence and active status.

**Proposed Batched Resolver Signature:**
```python
def _resolve_to_canonical_slugs(
    conn: kuzu.Connection,
    raw_slugs: list[str],
) -> dict[str, str]:
    """Batch resolve raw_slugs to their active canonical Entity.slugs.
    Returns a mapping of {raw_slug: canonical_slug} for successful matches."""
```

**Proposed Batched Cypher Query (with target entity verification):**
```cypher
UNWIND $raw_slugs AS raw
OPTIONAL MATCH (e:Entity {slug: raw})
WITH raw, e
OPTIONAL MATCH (e)-[:ALIAS_OF]->(canon:Entity)
OPTIONAL MATCH (target:Entity {slug: e.canonical_id})
RETURN raw,
       CASE
         WHEN e IS NULL THEN NULL
         WHEN e.status = 'active' AND e.canonical_id IS NULL THEN e.slug
         WHEN e.canonical_id IS NOT NULL AND target IS NOT NULL AND target.status = 'active' THEN e.canonical_id
         WHEN canon IS NOT NULL AND canon.status = 'active' THEN canon.slug
         ELSE NULL
       END AS canonical
```

### **Recommendation on Finding F-3 & F-4 (Circular Import & Plumbing)**
To decouple the compiler from the planner:
1.  **Move `SourceFrontmatter`** and the `T2Mode` enum out of `compiler.py` and `graph_context_loader.py` and declare them in **`kdb_compiler/types.py`**. This makes them universally accessible to all pipeline stages without circular loops.
2.  **Avoid Double-Read:** Since `planner.py` already loads the full `source_text` from disk (at line 120), it should parse the frontmatter directly from the loaded string using the low-level `parse_existing_frontmatter` helper from `frontmatter_embedder.py` (which is a shared, low-level module).

**Proposed Planner Plumbing (`kdb_compiler/planner.py`):**
```python
from kdb_compiler.ingestion.frontmatter_embedder import parse_existing_frontmatter
from kdb_compiler.types import SourceFrontmatter

# Inside planner.py's job building loop:
abs_path = vault_root / source_id
raw_content = _read_source_text(abs_path)

# Parse once, read once:
fm_dict, body = parse_existing_frontmatter(raw_content)
frontmatter = SourceFrontmatter.from_dict(fm_dict)

# Pass body or raw_content to _build_context along with parsed frontmatter
snapshot = _build_context(
    conn, source_id=source_id,
    frontmatter=frontmatter,
    source_text=raw_content,  # keeps legacy fallback matching stable
    page_cap=context_page_cap,
    mode=t2_mode_from_env,
)
```

---

## 4. Positions on Open Questions & Decisions

### **OQ-90-1: `entity_search_keys=[]` Semantics**
*   **Position:** **Fall back to legacy regex.**
*   **Rationale:** An empty `entity_search_keys` list could stem from a transient LLM generation cap or omission on shorter/fragmented sources. Treating empty-list as a strict "no graph anchors" signal risks silent context-seeding failures on valuable notes. Preserving the legacy regex fallback provides a robust, fail-safe layer.

### **OQ-90-2: Zero-Hit Threshold Telemetry**
*   **Position:** **Precision-on-substantive-sources rate.**
*   **Rationale:** A raw 5% zero-hit rate can be artificially inflated by short notes, templates, or daily log stubs that naturally have zero matching entities in the graph. Telemetry should track the zero-hit rate specifically on *substantive sources* (e.g., body word count > 50 words) that emit a non-empty `entity_search_keys` list. If substantive zero-hit rates exceed 5%, it signals orthographic or normalization drift, indicating that fuzzy matching is required.

### **OQ-90-3: Kuzu Cypher batch query compatibility**
*   **Position:** **Use standard CASE query (as amended in §3 above).**
*   **Rationale:** The optimized Cypher query in §3 of this review is standard Cypher compatible and avoids proprietary Kuzu extensions. It is highly portable and safe across Kuzu updates.

### **OQ-90-5 & D-90-7: Frontmatter Plumbing Path**
*   **Position:** **Option (i) optimized (Planner double-parses the loaded string directly, zero double-read).**
*   **Rationale:** Keeps the `CompileJob` serialization schema light and simple, eliminating double disk I/O while keeping compile pipelines robust.

### **OQ-90-6: Mode Selection Mechanism**
*   **Position:** **Env var `KDB_T2_MODE` is sufficient and correct for v1.**
*   **Rationale:** Keeps runtime ceremony low during local experimentation and benchmarking. We can promote this to a config-file or CLI flag once a default is definitively locked post-NW-9.

### **OQ-90-7: `T2Mode` Enum Location**
*   **Position:** **`kdb_compiler/types.py`.**
*   **Rationale:** Centralizes all cross-stage payload types, preventing circular imports and making tests clean to parametrize.

### **OQ-90-8: Legacy Sunset Trigger**
*   **Position:** **Do not set a hard trigger now; defer to post-NW-9.**
*   **Rationale:** Until we run the empirical evaluation on a fully enriched corpus, retaining the legacy branch as the ultimate fallback is cheap and safe.

### **D-90-5: Cold-Start Title-Phrase Widening**
*   **Position:** **Retain on legacy branch only.**
*   **Rationale:** On enriched sources, `entity_search_keys` is the authoritative hand-off. Adding title-phrase regex matching on top of the structured list dilutes the precision of the LLM's selected seeds.

### **D-90-6: Zero-hit Fallback**
*   **Position:** **No fallback in v1.**
*   **Rationale:** Fully supports `[[feedback_no_imaginary_risk]]`.

---

## 5. Pass-1 Prompt Review Block

Applying the five framed evaluation sub-prompts to the inline prompt in §4:

### **1. Anchoring**
*   **Evaluation:** The prompt currently asks the LLM to emit "slug candidates designed to find related existing entities...". It is slightly blind to how the downstream loader resolves aliases.
*   **Amendment:** The prompt should instruct the LLM to emit the **most common, base canonical concept slug** where possible, rather than speculative variants, because our downstream loader handles alias resolution.

### **2. Category Boundaries**
*   **Evaluation:** Category 4 (*"Closely-related concepts that frequently co-occur... even if not named explicitly"*) is a vector for semantic drift. If the LLM fanout is too speculative, it will either hit unrelated graph entities (injecting noise into T2) or produce dead keys (wasting slots).
*   **Amendment:** Refine Category 4 to focus on *load-bearing conceptual contexts* that are essential to the source's core argument, rather than loose co-occurrences.

### **3. Name Disambiguation**
*   **Evaluation:** The advice to *"Use surname-only for well-known figures ('buffett') and/or full-name form ('warren-buffett')"* is clean but has a massive drawback: if the LLM emits **both** for the same individual, it consumes 2 of the 10-cap slots with duplicate seeds.
*   **Amendment:** Instruct the LLM to prefer the **full-name form** ("warren-buffett") for proper nouns and explicitly tell it **not** to emit both the surname and full-name forms for the same entity in a single list.

### **4. Cap of 10**
*   **Evaluation:** The cap of 10 is perfectly balanced. It provides enough surface area for cold-start neighbor expansion without diluting the PageRank sorting in the compilation prompt.

### **5. Example Diversity**
*   **Evaluation:** The current single example is entirely locked into the finance domain (Buffett, Munger, Berkshire, etc.). This will heavily anchor LLM emissions on technical or scientific notes.
*   **Amendment:** We must replace the single example with a dual-domain example block (one finance, one tech/AI) to establish clear cross-domain stylistic expectations.

### **Proposed Prompt Revision (`kdb_compiler/ingestion/pass1_prompt.j2`):**

```
- `entity_search_keys`: list of up to 10 kebab-case slug candidates designed
  to seed a downstream context-loader that looks up existing entities in a
  knowledge graph. The graph contains entities for notable people, concepts,
  frameworks, and named ideas. What to include:
    1. Each item in `key_themes` (themes themselves are often already entity slugs).
    2. Common base concepts or canonical terms of each theme (prefer base slugs;
       e.g., for "value-investing" you might include "value-investing" or "intrinsic-value",
       preferring the most authoritative, canonical concept slug).
    3. Slugs for entity names mentioned substantively in the source (people,
       organizations, named frameworks). Prefer the full-name form ("warren-buffett")
       over the surname-only form ("buffett"). Do NOT include both forms for the
       same individual in the same list.
    4. Load-bearing concepts that are not explicitly named but are crucial
       for understanding the core argument (e.g., "efficient-market-hypothesis"
       for a debate on index funds). Avoid speculative or weak co-occurrences.
  Format: lowercase, hyphens between words, no spaces, no punctuation other than
  hyphens. Prefer specificity over breadth. Cap at 10 keys total; aim for 5–10.
  Examples:
    - Finance: source about value-investing key_themes ["value-investing", "margin-of-safety"]
      → `["value-investing", "margin-of-safety", "warren-buffett", "charlie-munger",
           "intrinsic-value", "berkshire-hathaway"]`.
    - AI/Tech: source about graph neural networks key_themes ["graph-neural-networks", "node-embedding"]
      → `["graph-neural-networks", "node-embedding", "deep-learning", "graph-rag",
           "graphdb", "personalized-pagerank"]`.
```

---

## 6. Edge-Case Probes

### **Probe 1: Duplicate Raw Slugs post-Resolution (Double-Emission)**
*   **Input:** `entity_search_keys=["buffett", "warren-buffett"]`
*   **Graph State:** 
    *   `(Entity {slug: "buffett", canonical_id: "warren-buffett", status: "active"})`
    *   `(Entity {slug: "warren-buffett", status: "active"})`
*   **Execution trace:**
    1.  `_resolve_to_canonical_slugs` is called with `["buffett", "warren-buffett"]`.
    2.  Cypher resolves `buffett` to `"warren-buffett"` (path 2) and `warren-buffett` to `"warren-buffett"` (path 1).
    3.  Python receives mapping: `{"buffett": "warren-buffett", "warren-buffett": "warren-buffett"}`.
    4.  Values are added to the `resolved` set, yielding `{"warren-buffett"}` (deduplicated).
*   **Outcome:** Successfully yields exactly one active canonical slug `"warren-buffett"`. Correct and robust.

### **Probe 2: Inactive Alias Target**
*   **Input:** `entity_search_keys=["aapl"]`
*   **Graph State:** 
    *   `(Entity {slug: "aapl"})-[:ALIAS_OF]->(canon:Entity {slug: "apple-inc", status: "inactive"})`
*   **Execution trace:**
    1.  `_resolve_to_canonical_slugs` executes the batched Cypher.
    2.  `canon` is matched, but `canon.status` is `'inactive'`. The `CASE` statement falls through to the `ELSE NULL` block.
    3.  Mapping returns `{"aapl": None}`.
*   **Outcome:** Correctly yields an empty T2 set. The inactive entity is completely blocked, preventing dead pages from populating the context snapshot.

### **Probe 3: Nonexistent Slug (Zero-Hit Cascade)**
*   **Input:** `entity_search_keys=["nonexistent-concept"]`
*   **Graph State:** No entity exists matching this slug or any alias.
*   **Execution trace:**
    1.  `_resolve_to_canonical_slugs` executes the batched Cypher.
    2.  `e` is `NULL`. `CASE` yields `NULL`.
    3.  Mapping returns `{"nonexistent-concept": None}`.
*   **Outcome:** Safely yields an empty T2 set. Downstream compile pipeline handles `ContextSnapshot(pages=[])` gracefully.

---

## 7. Open Questions

1.  **Cyclical Alias Safeguard:** While `canonical_id` is flattened in v1, what happens if an operator manually introduces an `ALIAS_OF` cycle in the database (e.g., A -> B -> A)? Should the resolver check for path loops, or should this sanity check live strictly inside `graphdb-kdb verify`? (Highly recommend the latter).
2.  **PageRank Scale Telemetry:** As the vault grows, does loading the full `LINKS_TO` topology into NetworkX in-memory for every compile snapshot scale efficiently? We should track PageRank computation latency separately in our post-ship stats to catch any memory/CPU bottlenecks early.
