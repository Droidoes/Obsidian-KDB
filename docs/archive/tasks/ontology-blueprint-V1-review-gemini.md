# Ontology Blueprint V1 — Gemini Review

## Summary
The Ontology Blueprint V1 establishes a mature and robust architecture that successfully addresses the run-3 domain coverage gap and generic-edge limitations. By adopting Option A for D1, we build a reliable derived view of Entity domains. For D2, we strongly recommend Option C to surgically wire the Claim layer for immediate reasoning (Relate) while safely deferring the complexity of belief revision (Learn). For D3, we pick Option C, establishing Domain as a soft budgeting coordinate to preserve cross-domain Discover capabilities while mitigating critical density.

---

## D1 — Domain model
- **Pick:** A (Derive from `SUPPORTS` + `Source.domain`) · **Confidence:** high
- **Reasoning:**
  Deriving the `Entity BELONGS_TO Domain` edges deterministically from the structural `SUPPORTS` relationship and the authoritative `Source.domain` property is the most elegant, cost-effective, and robust path. 
  1. **Leverages Authority:** Pass-1 source domain classification is highly reliable, has 100% coverage, and correctly captures the full 11-value distribution (such as the largest `value-investing` cluster, which Pass-2 completely failed to emit). Intrinsically, an entity has little semantic context to classify in isolation; a source provides that context.
  2. **Zero Run-time LLM Cost:** By making `BELONGS_TO` a derived view calculated by the Python runtime at compile time, we eliminate token costs, latency, and LLM classification errors at the entity level.
  3. **High Recomputability:** Naive LLM calls on entity pages are stateful and expensive. A derived view can be cleanly backfilled and re-run on past journals (like run-3) with zero API costs, enabling instant verification.
  4. **Philosophy B Alignment:** This respects C2 ("Domain as a coordinate, not a gate"). Domain becomes a structural coordinate inherited from where the human recorded the knowledge.

- **What we missed (The Hub-Pollution Failure Mode):**
  The assistant's framing under-weights the **"Hub-Pollution"** failure mode. In a dense graph, general-purpose hub entities (e.g., `python`, `chatgpt`, `risk`, or `strategy`) will be referenced across sources spanning almost every domain. Under a naive D1-A derivation, these hubs will inherit `BELONGS_TO` edges to *every* domain, causing "coordinate dilution" where filtering by a domain returns a massive, cluttered set of irrelevant connections.
  *   **Recommendation:** To prevent this, derived `BELONGS_TO` edges should carry a **strength metric** (such as the number of supporting sources in that domain, or a normalized ratio). This allows query-time operations to easily filter out low-strength, incidental domain links for hubs.

- **Sub-questions:**
  *   **[via_source?]:** **Yes.** Recording the conferring source IDs or at least a count (`source_count: INT64`) on the `BELONGS_TO` edge is highly valuable. While provenance can technically be recovered by joining back through `SUPPORTS`, storing a list or count directly on the edge significantly optimizes read path operations for the viewer, graph analytics, and sub-graph partitioning.
  *   **[sub_domain?]:** **Retire.** Because Pass-1 classifies sources into a singular primary `domain` without a nested vocabulary, keeping `sub_domain` on the edge would lead to sparse, mostly null attributes. Retiring it simplifies the schema and maintains a clean controlled vocabulary.

---

## D2 — Claim layer
- **Pick:** C (Split along the rung it serves: wire Claims now, defer belief-revision) · **Confidence:** high
- **Reasoning:**
  wiring the Claim layer (Claim node + `EVIDENCES` + `ABOUT`) now is the single most critical step to transition the KDB from a generic traversal graph to a true reasoning graph, directly answering ¶419. Deferring the entire layer (Option B) would permanently stunt the KDB at a "traversal-only" state. However, attempting to wire the entire belief-revision layer (Option A) including `SUPERSEDES`, `CONTRADICTS`, and `QUALIFIES` creates massive risk of pipeline fragility, as cross-run belief evolution is research-adjacent and requires the fully-fledged Hypothesis Promotion contract (#83). 
  Option C strikes the perfect "concrete-first" balance: land the grounded propositional claims today, prove the extraction pipeline is stable and clean, and lay the concrete substrate upon which future belief revision loops can operate.

- **What we missed:**
  The blueprint under-weights the **"Predicate-Class Drift"** failure mode. If the LLM is left to extract claims with a loose or poorly-bounded `predicate_class_canonical` controlled vocabulary, the predicate classes will quickly drift and degenerate into a word soup of near-duplicate verbs (e.g., `is_critical_to`, `is_essential_for`, `helps_in`). This would ruin graph reasoning.
  *   **Recommendation:** The controlled vocabulary of canonical predicates must be strictly defined and validated at the schema level. We suggest a highly focused set of ~10 horizontal predicates (e.g., `SUPPORTS`, `OPPOSES`, `CAUSES`, `PREVENTS`, `INFLUENCES`, `COMPOSED_OF`, `ASSOCIATED_WITH`).

- **Personal-scale value of claim extraction:**
  At small personal scale (~30 sources, ~180 entities), a human can manually trace links. However, the value of claim extraction scales non-linearly with vault size. Once a vault grows to 100+ sources, human memory decays, and the untyped `LINKS_TO` graph becomes a cluttered hairball. A grounded Claim layer acts as an automated semantic index of arguments, enabling the KDB to answer complex queries ("what are the arguments supporting the moat of Apple?") that a simple vector database or untyped graph structurally cannot resolve. The reasoning yield is exceptionally high and fully justifies the Pass-2 complexity.

- **Claim↔LINKS_TO division of labor:**
  **Highly coherent.** The division of labor is clean and elegant. `LINKS_TO` represents untyped, cheap **associative** proximity (the intuitive wiki link, useful for proximity traversal and PPR). `Claim` represents explicit, structured **assertions** (useful for reasoning and logical traversal). A healthy brain needs both: associative intuition and logical propositional reasoning. Coexistence prevents parallel-structure bloat because their operational use cases are completely orthogonal.

---

## D3 — T2/T3 domain-scoping
- **Pick:** C (Domain as a soft coordinate/budget, not a hard gate) · **Confidence:** high
- **Reasoning:**
  A hard domain gate (Option A) would be a catastrophic mistake for the **Discover** rung of our ladder. Creative insights and scientific discoveries (such as Swanson-style link discovery) occur almost exclusively at the *intersections* of disparate domains (e.g., relating a geopolitical event to value investing, or neuroscience to software engineering). Gating T2/T3 context to the same domain at compile time permanently blinds the compiler to these cross-domain relationships, meaning the LLM could never propose those links.
  Option C perfectly honors **C2** ("Domain = coordinate, not gate"). It mitigates the Critical Density noise problem by prioritizing same-domain candidates in the token budget, but leaves the door open for strong cross-domain contextual links to emerge.

- **What we missed:**
  The blueprint underweights the difficulty of tuning soft float weights. Proposing arbitrary mathematical float multipliers for domain affinity leads to unpredictable LLM context windows and fragile runtime behavior.
  *   **Recommendation:** Implement Option C using a **Slotted Token Budget** policy rather than float weights. For example, during compile-time context generation:
      *   **Slot 1 (Domain Anchor):** 70% of the available context token budget is strictly reserved for same-domain T2/T3 candidates.
      *   **Slot 2 (Cross-Domain Bridge):** The remaining 30% of the token budget is opened to the highest-scoring cross-domain T2/T3 candidates.
      This provides hard token-count predictability, solves critical density, and guarantees that cross-domain discovery bridges are never fully closed.

- **Sub-questions:**
  *   **[weighting aggressiveness]:** Under the slotted token budget recommended above, a 70/30 split is a robust baseline. Same-domain candidates dominate the prompt (maintaining Relate precision), but a solid 30% window allows highly prominent cross-domain entities to enter the context.
  *   **[gate-seeds-open-neighbors?]:** **No.** Gating T2 seeds while leaving T3 neighbors open (Variant D) introduces unnecessary asymmetric logic into the context builder. Treating both T2 and T3 uniformly under a soft slotted budget is cleaner to implement, easier to test, and maintains structural symmetry.

---

## Cross-cutting (inventory + frame)
1. **Redundancy in Claim Attributes:** In the DDL (Appendix A), `Claim` carries both `condition_text STRING` and `predicate_scope_slugs STRING[]`. Conceptually, both capture the contextual boundaries of an assertion. However, extracting a list of Entity slugs for `predicate_scope` adds substantial Pass-2 extraction complexity and resolver risk. We recommend **dropping `predicate_scope_slugs`** and merging its intent fully into `condition_text` (e.g., `"in the US market"` stored as raw prose).
2. **Artificial Precision in Confidence Spread:** `Claim.confidence_spread DOUBLE` is highly speculative. In a single-user personal vault, the LLM trying to assert a numerical "spread" on its extraction confidence is a clear case of "prompt-not-engine" hallucination. We recommend **dropping `confidence_spread`** to simplify the schema and prompt contract, keeping only a single `confidence DOUBLE` property.
3. **Domain node Schema alignment:** Under D1-A, Domain nodes are derived from `Source.domain`. Ensure that the `Domain` table's DDL is kept lightweight, which it is.

---

## Convergence note
We predict strong convergence among the reviewers on the following points:
1. **D1-A Unanimity:** Most models will pick Option A because LLM-based entity-level domain classification is historically fragile and expensive, while a derived view is clean, cheap, and deterministic.
2. **D2-C Strong Consensus:** Reviewers will align on Option C (wiring core Claims now, deferring belief revision) because it balances immediate engineering progress with risk management. Some highly conservative reviewers (such as DeepSeek) might lean toward Option B (deferring Claims entirely), but the panel will generally agree that untyped graphs are too weak for high-rung objectives.
3. **D3-C / Rejection of Hard Gates:** Reviewers will convergence on rejecting hard domain gates (Option A) due to the severe threat it poses to cross-domain link discovery. However, they may differ on the exact soft-weighting policy, which makes our **Slotted Token Budget** recommendation a highly valuable, concrete bridge.
