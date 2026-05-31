# Task #63.10 — Canonicalization-First Stage (Blueprint)

**Status:** Proposed Design — awaiting collective selection and Proceed (see §10)
**Date:** 2026-05-20
**Reference:** [`docs/TASKS.md`](TASKS.md) → Task #63 (continuation family)
**Anchor:** Round 5 §8.2 (canonicalization-first mandate) and §8.4 (5-layer selection structure) in [`docs/what-is-ontology-for-V1.md`](what-is-ontology-for-V1.md)
**Memory:** `feedback_no_imaginary_risk.md`, `feedback_apples_to_apples_within_session.md`, `feedback_measurability_over_defensive_complexity.md`

---

## 1. Why this exists

In a schemaless extraction world (Philosophy B + C1), the compiler accepts any entity or relationship emitted by the LLM without forcing a predefined human ontology. However, this flexibility introduces the risk of **semantic entropy**: the same physical entity may be extracted under different surface forms (e.g., `AAPL`, `Apple Inc.`, `Apple`). If left unresolved, the knowledge graph fragments into a "word soup" of redundant nodes and disconnected edges, rendering advanced GraphRAG operations (like Personalized PageRank or community detection) highly inaccurate.

To manage this entropy, **Canonicalization** is introduced as a first-class, contracted compile-stage component. Rather than a post-hoc cleanup script, canonicalization is performed *up front* during the compilation flow to:
- Normalize raw surface forms systematically.
- Maintain durable, queryable alias-to-canonical mappings.
- Track provenance (which raw surface forms map to which canonical entities).
- Keep downstream ingestion and graph traversals clean, idempotent, and re-derivable.

This blueprint outlines the schema additions, algorithm phasing, pipeline integration, and sequencing for this new subsystem.

---

## 2. Locked Decisions

These decisions form the architectural baseline, rooted in prior consensus and the Round 5 closeout.

| ID | Decision | Rationale |
|---|---|---|
| **D-R5-1** | The compile pipeline is organized as a **5-layer selection cascade** (ingestion / extraction / canonicalization / query-time / human-interpretation). Layers 2 and 3 are named, contracted compile stages; layer 1 is harvester/X6; layer 4 is query architecture; layer 5 is out of compile scope. | Clarifies the boundaries of selection in Philosophy B. It acknowledges that selection is not abolished, but rather relocated from ingestion (Layer 1) to extraction/canonicalization (Layers 2-3). |
| **D-R5-2** | Canonicalization is a first-class compile stage owning: string normalization, alias tracking, embedding-similarity dedup, LLM-as-judge for ambiguous cases, and provenance. | Avoids the high cost of post-hoc reconciliation on a populated graph (merging nodes, re-routing edges, re-clustering communities) by enforcing resolution at compile time. |
| **D-R5-3** | The stage slots logically between extraction (LLM emits raw entities) and Stage 9 (`graph_sync` writes both canonical entities and alias edges). | Extraction emits raw concepts; Stage 9 expects canonical targets. Enforces the contract where ingestion writes clean canonical relationships and explicit alias pointers. |
| **D-R5-4** | The canonicalization contract is idempotent and re-derivable: output is a pure function of (extraction output, alias-state-snapshot). | Ensures that the Kuzu GraphDB remains fully regenerable from run journals via `graphdb-kdb rebuild` (D39) with no hidden in-memory state. |

---

## 3. The 5-Layer Compile Pipeline

The KDB compiler's architecture acts as a pipeline that compresses raw text into structured canonical knowledge, organized by the five selection layers:

```
┌────────────────────────────────────────────────────────┐
│ Layer 1: Ingestion Selection (Harvester / X6 Boundary) │
│ - Curation: Mechanical role exclusion only (.venv, etc.)│
└──────────────────────────┬─────────────────────────────┘
                           │ Raw Source Files
                           ▼
┌────────────────────────────────────────────────────────┐
│ Layer 2: Extraction Selection (LLM Compiler / Stage 3) │
│ - Curation: LLM extracts raw page intents + wikilinks  │
└──────────────────────────┬─────────────────────────────┘
                           │ Raw Extraction Payload
                           ▼
┌────────────────────────────────────────────────────────┐
│ Layer 3: Canonicalization Selection (Ingestor Phase)   │
│ - Curation: String norm, mappings, (future) Embed/LLM  │
└──────────────────────────┬─────────────────────────────┘
                           │ Canonical Entities + Aliases
                           ▼
┌────────────────────────────────────────────────────────┐
│ Layer 4: Query-time Selection (Downstream / HippoRAG)  │
│ - Curation: PPR neighborhood activation, communities   │
└──────────────────────────┬─────────────────────────────┘
                           │ Subgraph Context
                           ▼
┌────────────────────────────────────────────────────────┐
│ Layer 5: Human Interpretation Selection (UX / UI)       │
│ - Curation: Presentation of surfaced notes to user    │
└────────────────────────────────────────────────────────┘
```

---

## 4. Architectural Forks & Open Questions

The following genuine forks must be settled to establish the Phase 1 blueprint consensus.

### OQ-1: Entity Identity Model
How does canonicalization change the `Entity` primary key and structural mapping?

- **Option A (Recommended — Unified Entity):** Keep `slug` as the `PRIMARY KEY` of the `Entity` table. Add a `canonical_id` property to `Entity`. Both canonical entities and aliases exist in the `Entity` table. An alias entity has `canonical_id` pointing to its canonical parent `Entity`. A canonical entity has `canonical_id = NULL` (or self-reference).
  - *Pros:* 100% backward-compatible. Existing grandfathered Obsidian entities remain in the `Entity` table exactly where they are. Downstream query interfaces, context loaders, and manifest replays do not need to support separate tables or complex join queries.
  - *Cons:* The `Entity` table contains both canonical entities and alias entities (though they are easily filtered via `WHERE canonical_id IS NULL`).
- **Option B (Migrate PK):** Destructive migration where `canonical_id` becomes the `PRIMARY KEY` of the `Entity` table, and raw `slug` is demoted to a property or alias node.
  - *Pros:* Cleaner long-term graph model with zero alias pollution in the `Entity` table.
  - *Cons:* High disruption. Breaks existing live data, requires complex migrations for the current compiled vault, and violates `feedback_measurability_over_defensive_complexity`.

> [!NOTE]
> **Staff Recommendation:** **Option A**. It allows us to grandfather existing entities with zero operational disruption, preserving shipped progress while adding clear canonicalization metadata.

---

### OQ-2: Alias Storage Model
How are aliases and their edges represented in the GraphDB schema?

- **Option A (Recommended — Explicit ALIAS_OF Edges):** Represent aliases as explicit nodes that link to their canonical entity via a directed `ALIAS_OF` relationship table.
  - *Pros:* First-class graph representation. Provenance attaches cleanly to the relationships. We can query `MATCH (s:Source)-[:SUPPORTS]->(a:Entity)-[:ALIAS_OF]->(c:Entity)` naturally. It matches the project's brand: *"explicit edges beat implicit similarity."*
  - *Cons:* Marginally more complex Cypher writes compared to a flat list.
- **Option B (List Property):** Store aliases as a flat `aliases: STRING[]` list property directly on the canonical `Entity` node.
  - *Pros:* Simpler schema; no new tables or relationship records.
  - *Cons:* Loses per-alias provenance (e.g., we cannot easily track which specific source referenced the entity using which alias). Fails to represent aliases as first-class graph entities.

> [!NOTE]
> **Staff Recommendation:** **Option A** (using the Unified Entity model from OQ-1). An alias exists as an `Entity` node, and we write an explicit `ALIAS_OF` edge between `Entity` nodes (i.e. `FROM Entity TO Entity`). This offers maximum query power with minimal schema pollution.

---

### OQ-3: Algorithm Phasing for v1
How should the canonicalization toolkit be rolled out?

- **Option A (Full Toolkit v1):** Ship string normalization, vector embedding similarity, and LLM-as-judge reconciliation together in the initial version.
  - *Pros:* Highly automated from day one.
  - *Cons:* High complexity, cost, and latency risk. We do not yet have high duplicate volumes in the canonical corpus, so the ROI on complex LLM-as-judge loops is currently low.
- **Option B (Recommended — Phased v1):** Establish the schema, contracts, and baseline algorithm in v1 using **string normalization + deterministic mapping ledger** (e.g., a local config/rule ledger). Design the integration points for embedding-similarity and LLM-as-judge from day one, but gate their execution behind a config flag or defer them to v2.
  - *Pros:* Delivers an extremely tight, robust, and fast v1 that addresses 80% of duplication immediately. Safely separates algorithm development from schema/pipeline integration.
  - *Cons:* Requires a manual ledger entry for ambiguous, non-obvious alias cases in v1.

> [!NOTE]
> **Staff Recommendation:** **Option B**. String normalization plus a simple local mapping configuration gets us 80% of the value for 20% of the complexity, perfectly aligned with the 80/20 deliberation rule.

---

### OQ-4: Sub-Task Numbering & Pipeline Seam
How should the sub-tasks be sequenced, and where does the code slot in?

- **Option A (Recommended — Ingestion Core Seam):** Treat canonicalization as a phase inside the `graphdb_kdb` ingestion module (specifically in `apply_compile_result`). Sub-tasks numbered under the #63 family (e.g., #63.10, #63.11).
  - *Pros:* Clean import boundaries. The production `kdb_compile.py` orchestrator remains untouched, preserving its simple 9-stage sequence. Zero journal schema changes or version bumps.
  - *Cons:* Canonicalization is less visible as a top-level stage in orchestrator logs.
- **Option B (Orchestrator Stage 8.5):** Introduce a new top-level compile stage `canonicalize` in `kdb_compile.py` and `run_journal.py` between reconcile and build manifest. Assign it a new task ID (e.g. Task #74).
  - *Pros:* Explicit visibility in orchestrator log banners.
  - *Cons:* Forces a journal schema version bump (breaking older replays) and couples orchestrator logic to graph-specific canonicalization metadata.

> [!NOTE]
> **Staff Recommendation:** **Option A**. The Kuzu ingestion core is the natural authority on graph topology; performing canonicalization inside `apply_compile_result` keeps the orchestrator simple and highly decoupled.

---

## 5. Schema Delta (Kuzu DDL)

We will modify the existing database initialization logic in `graphdb_kdb/schema.py` to support canonicalization:

```cypher
-- 1. Add canonical_id property to Entity table (D-A1/D-R5-5)
-- (Kuzu supports ALTER TABLE ADD. On new DB, initialized directly in DDL)
CREATE NODE TABLE Entity (
    slug          STRING PRIMARY KEY,
    title         STRING,
    page_type     STRING,        -- summary | concept | article
    status        STRING,        -- active | stale | archived | orphan_candidate
    confidence    STRING,        -- low | medium | high
    canonical_id  STRING,        -- points to the canonical Entity.slug; NULL if self is canonical
    created_at    STRING,
    updated_at    STRING,
    first_run_id  STRING,        -- run that introduced this page
    last_run_id   STRING         -- most recent run that touched this page
);

-- 2. Create ALIAS_OF relationship table (D-R5-6)
CREATE REL TABLE ALIAS_OF (
    FROM Entity TO Entity,
    run_id      STRING,
    created_at  STRING
);
```

---

## 6. Canonicalization Stage Contract

### Inputs
The stage takes the raw extraction payload from Stage 3/5:
- `cr: dict` (the `compile_result` containing pages, titles, and outgoing links).
- `mappings: dict` (the local deterministic mapping ledger).

### Outputs
A resolved compile payload where:
- Every page is marked as either `canonical` or an `alias`.
- Slugs in `outgoing_links` are resolved to their canonical counterparts.
- An explicit list of `aliases` to write is prepared.

### Error Semantics
- Circular alias mappings (e.g., `A` -> `B` -> `A`) raise `CircularAliasError` and fail the ingestion transaction atomically.
- Multiple competing canonical targets for a single alias raise `AmbiguousAliasError` and are logged as warnings (or resolved via local ledger).

---

## 7. Algorithm Pipeline

The Layer 3 Canonicalization Engine runs the following pipeline:

```
Raw Slug (e.g., "AAPL")
      │
      ▼
[ String Normalization ] ──► Lowercase, trim, remove punctuation ("aapl")
      │
      ▼
[ Ledger Lookup ]        ──► Check local mappings config ("aapl" -> "apple-inc")
      │
      ▼
[ (v2) Embed / LLM ]     ──► Vector similarity (Gated/Configured)
      │
      ▼
[ Resolve Outgoing ]     ──► Re-route outgoing links to "apple-inc"
      │
      ▼
[ Write DB Trans ]       ──► Upsert Entities + Create ALIAS_OF edge
```

---

## 8. Integration & Verification Plan

### Automated Verification
- **Unit Tests:**
  - `test_string_normalization()`: Verify that punctuation, casing, and spacing normalize correctly.
  - `test_alias_ingestion()`: Verify that `ALIAS_OF` edges are created, and `canonical_id` is populated accurately.
  - `test_link_resolution()`: Verify that `outgoing_links` pointing to an alias are mapped to the canonical entity in the graph.
  - `test_circular_dependency()`: Verify that circular aliases are detected and rejected.
  - `test_rebuild_replays()`: Verify that `graphdb-kdb rebuild` reconstructs all aliases and canonical relationships perfectly from historical journals.

### Manual Verification
- Compile a raw file referencing `[[AAPL]]` and `[[Apple Inc.]]` and run `graphdb-kdb query` to inspect the resulting nodes, edges, and PageRank scores.

---

## 9. Sequencing & Sub-tasks

We will organize the implementation into the following tight, incremental sub-tasks under the Task #63 family:

- [ ] **#63.10.1 (DDL & Schema):** Update `graphdb_kdb/schema.py` DDL to add `canonical_id` and the `ALIAS_OF` table. Implement migration/first-connection handling.
- [ ] **#63.10.2 (Normalization & Ledger):** Implement string normalization functions and load the local deterministic mapping ledger (`aliases.json` or inline config).
- [ ] **#63.10.3 (Ingestor Integration):** Update `graphdb_kdb/ingestor.py` to resolve raw slugs, upsert nodes, and create `ALIAS_OF` edges.
- [ ] **#63.10.4 (Test Suite):** Add comprehensive unit and integration tests covering the canonicalization pipeline and rebuilder.

---

## 10. Open Questions (Team Gate)

> [!IMPORTANT]
> **Consensus Check:** Please review the recommendations for **OQ-1 through OQ-4**. Once you select or refine these options, confirm by saying **"Proceed"** or specifying your adjustments, and we will begin the implementation phases!
