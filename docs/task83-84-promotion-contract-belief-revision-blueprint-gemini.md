# External Review: Task #83 + #84 — Claim Node Schema Design (D-83/84-6)
**Reviewer:** Gemini 3.5 Flash (High) — Antigravity Alter Ego
**Date:** 2026-05-22
**Target Doc:** `docs/task83-84-promotion-contract-belief-revision-blueprint.md` (v1 draft)
**Context:** Targeted architectural feedback on the four genuine forks (F1..F4) proposed for Decision D-83/84-6 (OQ-3 + OQ-5), aligning with the North Star documentation and our system-over-implementation philosophy.

---

## 1. Architectural Fit Assessment

The proposed transition into the **Claim Node Schema Design (D-83/84-6)** is a major step forward for operationalizing KDB's "Learn" layer. By building on the **Hybrid Model (D-83/84-1)** and structured predicate representation, these decisions define how contested, versioned belief states are reified, managed, and queried.

The proposed leans are highly compliant with our core principles:
*   **System over Implementation**: Standardizing on graph-native evidence edges and explicit version chains constructs a robust, queryable data asset rather than a series of brittle database hacks.
*   **YAGNI & No Imaginary Risk**: Deferring meta-claims (F4) keeps the v1 scope clean, predictable, and aligned with classical syntactic belief bases, avoiding speculative research-frontier complexity.
*   **Concrete First, Extract Later**: Leveraging structured slugs (F1) and standardizing on the `Page—EVIDENCES→Claim` edge pattern (F3) ensures that our physical graph topology directly matches our conceptual model.

---

## 2. Rigorous Breakdown of the Four Forks (F1..F4)

Dedicated to high-integrity deliberation, we analyze each fork through distinct architectural lenses, noting pros, cons, and essential refinements.

---

### F1 — `claim_id` format

The challenge is balancing **human debuggability** with **determinism** and **schema mutability**.

#### Option F1.a: The Structured Versioned Slug (Leaned)
*   **Format**: `<subject>__<predicate_class_canonical>__<polarity>__v<N>`
*   **Example**: `buffett__tech-investing-stance__rejects__v1`
*   **Pros**:
    *   **Maximum Observability**: The ID itself carries semantic meaning. When querying raw Kuzu tables or inspecting JSONL dumps, developers can immediately understand the node's identity without performing joins.
    *   **Ontology Synergy**: Directly mirrors KDB's existing slug-based patterns for `Entity` nodes.
*   **Cons**:
    *   **State-Lookup Dependency**: During incremental compilation, the Promotion Contract must query the existing graph to find the current highest version ($N$) to assign $N+1$.
    *   **Canonical Mutability**: If a subject is merged (e.g., `buffett` becomes `warren-buffett` during Stage [6] canonicalization), the Claim ID must change.
*   **Refinement**: The mutability concern is completely resolved by KDB's **rebuild-first architecture** (`graphdb-kdb rebuild`). Since the database is fully reconstructed chronologically from source journals, any canonicalization change propagates naturally through the rebuild pipeline, deriving the new Claim IDs organically without requiring complex database migration scripts.
*   **Critical Guardrail**: We must enforce a **Delimiter Guard**. The subject slug and canonical predicate class slug must not contain double underscores (`__`), ensuring that the ID parser can always split the slug reliably.

#### Option F1.b: The Content-Hashed Slug (O(1) Generation)
*   **Format**: `<subject>__<predicate_class_canonical>__<polarity>__<short_sha256>`
*   **Pros**:
    *   **O(1) Execution**: Generated locally and deterministically from content and provenance, eliminating database lookups during the compile phase.
*   **Cons**:
    *   **Loss of Epistemic Progression**: Version sequences (`v1`, `v2`, `v3`) are lost at first glance, requiring timestamp-based sorting during manual inspection.

#### Option F1.c: Opaque UUID
*   **Format**: Standard UUID v4.
*   **Pros**: Complete isolation from data values; immune to subject/predicate renaming.
*   **Cons**: Completely unreadable during manual Cypher debugging; requires a composite index over `(subject, predicate, polarity, version)` for basic lookups.

---

### F2 — State machine

The transition logic determines how temporal validity, supersession, and retraction behave under belief revision.

```
active  ──supersedes──→  superseded   (when a Supersedes candidate is accepted)
active  ──retract────→  retracted    (explicit retraction or decay-to-zero)
superseded  ─────────→  active        (revival path — only if newer claim itself retracted)
retracted   ──────────  (terminal)     (no path out)
```

#### Option F2.a: Linear Succession Stack (Implicit Predecessor Cascade)
*   **Logic**: Claim versions form a strict succession chain: `v3 (active) —SUPERSEDES→ v2 (superseded) —SUPERSEDES→ v1 (superseded)`. When `v3` is retracted, `v2` (its immediate predecessor) is automatically revived and marked `active`.
*   **Pros**:
    *   **Simple & Deterministic**: The revival query is straightforward, walking the `SUPERSEDES` edge backward by one hop.
    *   **Audit Trail**: The graph physically stores the lineage of thought transitions.
*   **Cons**:
    *   Assumes a linear progression; does not easily model complex branching paths (though branching is rare in personal scale belief revision).
*   **Refinement**: The revival query must ensure that a revived claim was not itself previously retracted. The cascade query should find the latest non-retracted predecessor in the chain:
    ```cypher
    MATCH (c:Claim {state: 'active'})-[r:SUPERSEDES]->(prev:Claim)
    WHERE c.id = $retracted_id
    SET c.state = 'retracted'
    // Revive immediate predecessor if not explicitly retracted
    SET prev.state = CASE WHEN prev.state <> 'retracted' THEN 'active' ELSE prev.state END
    ```

#### Option F2.b: Query-Time Recalculation Model
*   **Logic**: Historical claims do not carry a direct `SUPERSEDES` edge. Instead, when an active claim is retracted, the Promotion Contract queries all historical claims with the same `(subject, predicate_class)` that are in the `superseded` state and marks the one with the highest confidence or latest timestamp as `active`.
*   **Pros**:
    *   Highly resilient to non-linear retractions.
*   **Cons**:
    *   Increases query complexity and removes explicit topological records of transitions.

---

### F3 — Provenance representation

This determines how the system links the **source page context** to the **consolidated belief node**.

#### Option F3.a: Graph-Native Evidence Edges (Leaned Option β)
*   **Pattern**: `Page—EVIDENCES→Claim`
*   **Pros**:
    *   **High Queryability**: Standard Cypher traversals can identify which pages are the most influential hubs for a given claim.
    *   **Edge-Attribute Enrichment**: *This is the load-bearing advantage.* We can store source-specific metadata directly on the edge:
        *   `quoted_text`: The exact source quote supporting the claim.
        *   `confidence_score`: The confidence emitted by the extractor for this specific page.
        *   `ingest_run_id`: The specific run that introduced this evidence link.
    *   This leaves the `Claim` node clean, storing only unified consensus properties (e.g. state, global version, aggregate confidence).
*   **Cons**:
    *   Requires a new edge type and increases the relationship count (negligible scale cost).
*   **Refinement**: The schema mapping for `Page—EVIDENCES→Claim` should match the exact variable types used in our Kuzu models. Let's document the properties on the edge:
    ```yaml
    EVIDENCES edge properties:
      quoted_text: STRING
      confidence: FLOAT
      run_id: STRING
      created_at: TIMESTAMP
    ```

#### Option F3.b: Flat List Property (Option α)
*   **Pattern**: `evidenced_by: [page_slug_1, page_slug_2]` on the `Claim` node.
*   **Pros**:
    *   Slightly faster reads when querying the Claim node in isolation.
*   **Cons**:
    *   Cannot store edge-specific attributes (like quotes or specific confidence metrics) cleanly, forcing us to use complex list-of-JSON fields that break Cypher's native querying capabilities.

---

### F4 — Meta-claims (Claim—ABOUT→Claim)

This determines whether claims can be made about other claims in the initial release.

#### Option F4.a: Strict v1 Bounds (Leaned Option b)
*   **Logic**: `Claim—ABOUT→Entity` is the only valid target in v1. Meta-claims are completely deferred to v2.
*   **Pros**:
    *   Keeps the graph schema clean and easy to test.
    *   Avoids introducing structural self-loops or complex multi-hop belief networks in v1.
*   **Cons**:
    *   None. Fits current requirement boundaries perfectly.

#### Option F4.b: Schema-Agnostic Union
*   **Logic**: Declare `Claim—ABOUT` as targeting a union of `Entity | Claim` in the database schema from day one, but enforce a validation rule in the compiler to only allow `Entity` targets in v1.
*   **Pros**:
    *   Saves a minor schema migration step in the future.
*   **Cons**:
    *   Increases Kuzu schema definition complexity unnecessarily before we have concrete demand.

---

## 3. Consolidated Proposal for Decision D-83/84-6 (OQ-3 + OQ-5)

Below is the structured registry of our collective choices, capturing the consensus and their architectural implications:

| Decision Element | Chosen Choice | Concrete Schema / Architectural Implications |
| :--- | :--- | :--- |
| **F1: `claim_id` Format** | **(a) Structured versioned slug** | `<subject>__<predicate_class_canonical>__<polarity>__v<N>`<br>• Enforces a strict `__` delimiter check on creation.<br>• Derived organically during `rebuild` passes. |
| **F2: State Machine** | **Linear succession stack** | • Active claims carry a `SUPERSEDES` edge to their immediate predecessor.<br>• Retracting a claim triggers a cascade transition marking the predecessor `active` (if it was not explicitly retracted). |
| **F3: Provenance** | **(β) `Page—EVIDENCES→Claim` edge** | • Stores source-specific attributes (`quoted_text`, `confidence`, `run_id`, `created_at`) directly on the edge.<br>• Keeps `Claim` node attributes limited to aggregate consensus states. |
| **F4: Meta-Claims** | **(b) Defer to v2** | • The `ABOUT` relationship table strictly connects `Claim → Entity`.<br>• No self-referential claim cycles are allowed in v1. |

---

## 4. Next Steps & State Machine Gate

In accordance with **Phase 2 (Collective Selection)** of our system rules:
1.  Please review this architectural analysis and select or refine the proposed options.
2.  Once we sign off on this path, we will proceed to **Phase 3 (Detailed Logic Confirmation)**, where we will construct the concrete technical blueprint—including exact Cypher schemas, Python models/dataclasses, and logic flows—before making any code changes.
