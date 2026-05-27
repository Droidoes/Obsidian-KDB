# Task #90 v0.1 Review — Grok Build

**Reviewer:** Grok Build (CLI, code-grounded)  
**Date:** 2026-05-27  
**Artifact reviewed:** `docs/task90-context-loader-t2-rewrite-blueprint.md` (v0.1)  
**Context:** Follows Task #89 v0.2.2 (D-89-20 input contract) + Task #74 alias machinery. Panel discipline per `docs/external-review-panel.md`.

---

## 1. Convergence

The architectural shape is coherent and respects prior decisions.

- **T2Mode enum + dispatcher** (§2.1) cleanly encodes the three paths (STRUCTURED / LAYERED / LEGACY) with no hidden coupling. This is the "paint no corner" property Joseph called for; switching modes for NW-9 requires zero code change. Strong.
- **Option A as v1 default** (D-90-1) is the right minimal step. The legacy regex is a pre-Pass-1 heuristic strictly dominated by an explicit, consumer-designed signal on enriched sources. Keeping the legacy branch only for pre-Pass-1 sources is honest.
- **Alias reachability paths** (§3.1) correctly defer to the ratified #74 order (direct PK → canonical_id → ALIAS_OF). No re-litigation needed; the blueprint simply consumes the existing contract.
- **Zero-hit policy** (D-90-6) correctly applies `[[feedback_no_imaginary_risk]]`. Shipping a fallback without telemetry would be speculative ceremony.
- **Benchmark scaffolding** (§7) is well-placed. The three-mode harness plus predeclared criteria pattern (precedent #75/#87) gives the later flip decision empirical grounding rather than intuition.

The design is a clean producer→consumer handoff: Pass-1 emits `entity_search_keys` (already present in `Pass1Envelope` and the live E.1 test at `kdb_compiler/tests/test_pass1_end_to_end.py:132`); the loader becomes the first real consumer.

---

## 2. Findings

**Finding F-1 (OQ-90-1 / §2.2 / §6.1):** Treating `entity_search_keys=[]` identically to "absent frontmatter" erodes signal value.

> "if frontmatter is not None and frontmatter.entity_search_keys: return _t2_from_search_keys... # Pre-Pass-1 path: current regex"

An empty list after Pass-1 enrichment is not the same as a pre-Pass-1 source. The former is the LLM asserting "no useful graph anchors in this source." Falling back to the whole-word regex in that case risks injecting low-precision noise that the structured path was meant to avoid. The current selector collapses a positive signal into a heuristic.

**Finding F-2 (OQ-90-4 / §4 prompt):** Category 4 ("Closely-related concepts that frequently co-occur... even if not named explicitly") is too open-ended for a 10-slot budget.

The prompt already asks the LLM to maximize hit rate against `Entity.slug` PK lookups after alias resolution. Category 4 invites speculative fanout ("frequently co-occur") without requiring the concept to appear in the source or in `key_themes`. On a finance source this may produce "circle-of-competence"; on an AI source it may emit "scaling-laws" or "emergence" that are thematically adjacent but not load-bearing for T2. This increases zero-hit or low-precision risk, directly counter to the consumer-purpose test that drove D-89-20.

**Finding F-3 (OQ-90-4 / §4):** Single finance-domain example risks anchoring LLM emissions.

The only in-prompt exemplar is Buffett/Munger/value-investing. The vault contains substantial non-finance material (AI/ML, philosophy, daily notes, equity research that is not pure value investing). An LLM that has only seen one finance-shaped list may over-emit person/organization slugs and under-emit framework or abstract-concept slugs for sources in `ai-ml` or `philosophy-ethics`. This is a measurable distribution shift risk for hit rate.

**Finding F-4 (OQ-90-3 / §3.3):** The proposed batch Cypher uses Kuzu-optional features whose exact semantics are unknown at design time.

The sketch:
```cypher
UNWIND $raw_slugs AS raw
OPTIONAL MATCH (e:Entity {slug: raw})
WITH raw, e
OPTIONAL MATCH (e)-[:ALIAS_OF]->(canon:Entity)
RETURN ... CASE ...
```
Kuzu's `OPTIONAL MATCH` + `WITH` + multi-`OPTIONAL` + `CASE` behavior on missing nodes is not documented in the current codebase (the existing queries in `graph_context_loader.py` are simple single-`MATCH` patterns). A single complex query that silently returns wrong `NULL` rows on certain alias topologies would be a silent correctness bug in T2. The fallback to 1–2 simpler queries is not just "nice to have"—it is risk mitigation.

**Observation O-1 (§5 / §6.2):** Double-parsing frontmatter (Option (i)) is acceptable for v1 but creates a latent maintenance hazard.

`source_text_for` is already called from `compiler.py` at compile time. Adding a second call site in the planner for the same job is cheap YAML but creates two places that must stay in sync on `SourceFrontmatter` evolution. The lean toward (i) per `[[feedback_no_imaginary_risk]]` is correct for v1, but the review surface should note the coupling.

**Observation O-2 (§8.3):** Parametrizing the existing `test_graph_context_loader.py` suite with `T2Mode.LEGACY` is necessary but insufficient regression protection.

Once STRUCTURED becomes the production default, the "current behavior" that the LEGACY path must preserve will no longer be what production runs on most sources. The regression tests will be guarding a branch that fewer and fewer real runs exercise. This is acceptable as a transitional measure; it should be called out as temporary.

---

## 3. Recommendations

**OQ-90-1 (entity_search_keys=[] semantics):**  
**Recommendation:** On the STRUCTURED branch, treat a present but empty `entity_search_keys` list as "LLM asserted no anchors — emit empty T2." Only fall back to legacy regex when `frontmatter is None` (pre-Pass-1 source). This preserves the positive signal value of the new field. Document the distinction in telemetry so zero-hit analysis can separate "LLM said none" from "LLM said some but none resolved."

**OQ-90-2 (5% zero-hit threshold):**  
**Recommendation:** Keep the raw rate for v1 simplicity, but add a secondary "precision-on-substantive-source" view in the telemetry (§10). 5% is a reasonable initial trigger; the secondary metric prevents over-reaction to a few noisy daily-note sources.

**OQ-90-3 (Kuzu Cypher batch query):**  
**Recommendation:** Implement `_resolve_to_canonical_slug_batch` with the sketched UNWIND+CASE query as the fast path, but **immediately** provide a reference implementation that decomposes into 1–2 simple queries (one for direct+canonical_id, one for ALIAS_OF) as a `KDB_T2_RESOLVER=simple` escape hatch. Add a unit test that asserts both implementations produce identical results on the same fixture graph. This makes the Kuzu-specific risk observable and containable.

**OQ-90-4 (Pass-1 prompt review):** See dedicated block below.

**OQ-90-5 / D-90-7 (frontmatter plumbing):**  
**Recommendation:** Confirm Option (i) double-parse for v1. The risk is low (YAML parse of a small frontmatter block) and the `CompileJob` schema change is unnecessary ceremony. Add a one-line comment at both call sites noting the intentional duplication and the follow-up ticket if profiling shows measurable cost.

**OQ-90-6 (mode selection mechanism):**  
**Recommendation:** `KDB_T2_MODE` env var is sufficient for v1 and for the NW-9 benchmark harness. A config-file mechanism can be added later if operators (future multi-user or CI) need it; it is not required for the single-operator workflow that owns the current vault.

**OQ-90-7 (T2Mode enum location):**  
**Recommendation:** Keep `T2Mode` inside `graph_context_loader.py` for v1. The type is an implementation detail of the T2 production strategy; it does not need to be a first-class citizen in `types.py` alongside `ContextSnapshot` and `CompileJob`. Move it only if a second consumer appears.

**OQ-90-8 (legacy branch sunset):**  
**Recommendation:** Do not wire a hard trigger now. The correct signal is "vault 100% enriched + NW-9 benchmark shows STRUCTURED dominates on cold-start and precision." Add a one-line telemetry counter (`legacy_t2_sources_total`) so the team can watch the denominator shrink. Revisit in the NW-9 decision report.

**D-90-5 (cold-start title-phrase widening on structured branch):**  
**Recommendation:** Keep title-phrase widening **only on the legacy branch**. Once a source carries `entity_search_keys`, the explicit signal is the contract; re-applying the #71 heuristic would be reintroducing a dominated strategy. This is consistent with the consumer-purpose discipline that produced D-89-20.

**D-90-6 (zero-hit fallback):**  
**Recommendation:** Agree with the current stance. Adding a fuzzy or regex fallback in v1 would violate `[[feedback_no_imaginary_risk]]`. The 5% telemetry gate is the correct place to decide whether the failure mode is real.

---

## 4. Prompt-Review Block (§4 of blueprint)

The current `entity_search_keys` section is already in production (`kdb_compiler/ingestion/pass1_prompt.j2:62-84` and the E.1 test that exercises it). The review therefore evaluates a live prompt, not a proposal.

**Anchoring to consumer mechanism:**  
Reasonably good. The prompt tells the LLM the downstream graph uses `slug` keys and that alias resolution will occur. It does not, however, explicitly say "your output will be passed to a function that does direct PK match then canonical_id then ALIAS_OF traversal." Adding one sentence ("The lookup will succeed if the emitted slug matches an Entity.slug directly, points to an active entity via its canonical_id, or has an ALIAS_OF edge to an active canonical entity") would tighten the mental model without adding length.

**Category boundaries — Category 4 risk:**  
Too loose. The phrase "closely-related concepts that frequently co-occur with the source's themes, even if not named explicitly" invites the LLM to perform light topic expansion. For T2 this is usually noise.  
**Suggested tightening (quoted edit):**
> 4. Only if a concept is **substantively referenced** (explicitly or via a clear synonym the source itself uses) and would be a high-value T2 seed for a reader of this exact source. Do not emit general "related work" or "commonly discussed alongside" items that the source does not engage.

**Name disambiguation guidance:**  
The "surname-only AND full-name form" rule is pragmatic and matches real author/organization usage in the vault. It does risk padding the 10-cap with near-duplicates ("buffett" + "warren-buffett"). The cap plus "prefer specificity" language mitigates this; no change required, but the prompt could add: "If both forms are plausible, prefer the more specific one and omit the short form unless the source itself uses the short form as primary reference."

**Cap of 10:**  
Generous but defensible given the top-50 context page cap and the fact that T3 will still expand from whatever T2 seeds survive. A realistic well-tuned hit rate target (post-alias-resolution) is 60–80% on substantive sources. The current cap gives the LLM headroom to be slightly over-inclusive without catastrophic precision loss. Keep 10 for v1; the NW-9 benchmark can measure whether a tighter cap (7–8) improves downstream Pass-2 quality.

**Example diversity:**  
Clear gap. One finance example is insufficient.  
**Proposal:** Add two more compact examples in the prompt (or as comments the LLM sees):
- One `ai-ml` source with themes around scaling and evaluation.
- One philosophy/ethics source discussing a named argument or thinker.
This prevents the model from over-generalizing the Buffett-shaped pattern to every domain.

---

## 5. Edge-Case Probes

**Probe 1 — Duplicate raw keys after alias resolution**  
`entity_search_keys = ["buffett", "warren-buffett"]` where both resolve to the same canonical `warren-buffett` (one via direct, one via ALIAS_OF).  
**Option A behavior:** `_t2_from_search_keys` uses a `set`; only one entry lands in T2. Correct and cheap.

**Probe 2 — Raw key is itself an alias of an alias (pre-#74 flattened graph)**  
`entity_search_keys = ["wm"]` where `wm` → ALIAS_OF `warren-munger` → ALIAS_OF `warren-buffett` (hypothetical).  
**Behavior:** Per #74 D-R5-13 the graph stores flattened `canonical_id`. The single resolution step (direct or one ALIAS_OF hop) will surface the ultimate active canonical. The blueprint's "no multi-hop" assumption holds because the ingestion already flattened. Safe.

**Probe 3 — Non-empty keys, all miss the active graph (zero-hit on enriched source)**  
Source about a brand-new framework the vault has never seen. Pass-1 emits 6 plausible slugs; none exist as Entity rows.  
**Behavior:** T2 = ∅ for this source. T3 expands from T1 only. If T1 is also empty (cold-start), T3 is empty. Source ships with `context_snapshot.pages = []`. This is the exact zero-hit case D-90-6 deliberately leaves unfilled. Telemetry will surface it; no imaginary rescue layer.

**Probe 4 — Cold-start source where entity_search_keys produce usable T2**  
New source, no SUPPORTS edges yet (T1 empty), but Pass-1 correctly emits 4 slugs that resolve to active entities the rest of the graph already links to.  
**Behavior:** T2 receives the 4 resolved slugs (score 2). Because |T2| ≥ 5? No — still < _MIN_SEED_THRESHOLD, so T3 expands to 2 hops. Title-phrase widening is correctly skipped (structured branch). The explicit signal gives better seeds than the old title heuristic would have. This is the expected win.

**Probe 5 — Unicode / apostrophe slug that passed shape validation**  
`entity_search_keys = ["see's-candies"]` (the exact case that caused the #89 E.1 schema relaxation).  
**Behavior:** The shape check in `pass1_schema.py` no longer rejects it. The lookup in `_resolve_to_canonical_slug` will do an exact string match against `Entity.slug`. If the canonical entity was stored as `sees-candies` or `see-s-candies`, it will miss. This is a prompt + ingestion hygiene issue, not a lookup bug. The relaxed schema was the right call; the failure mode is now visible in hit-rate telemetry rather than a hard 422 at enrichment time.

---

## 6. Open Questions (additional, not resolvable in this review)

- How will the NW-9 probe corpus be stratified? The blueprint says "≥3 domains and ≥3 source_types." Should it also deliberately oversample cold-start sources (those with few or zero prior SUPPORTS edges) since that is where the T2 signal change is most load-bearing?
- Should the alias resolver surface which path (direct / canonical_id / ALIAS_OF) produced each hit, purely for §10 telemetry? The data is cheap to collect and would let us detect when the alias ledger or Pass-1 slug conventions are drifting.
- Is there a future need for a "T2 explanation" field in the ContextSnapshot (or a sidecar) so Pass-2 (and later debugging) can know whether a given page arrived via T1 SUPPORTS, T2 structured keys, or legacy regex? Not required for v1, but worth a one-sentence note in the decision log.

---

**Guardrail compliance:** This review created exactly one file (`docs/task90-v0.1-review-grok.md`). No other files were modified, created, or deleted. No code, schemas, or blueprints were edited. No implementation patches were proposed. The review stays strictly within the scope defined by the fire-prompt and the locked decisions (D-89-20, D-90-1..4, alias reachability order, etc.).

**Length note:** Review is intentionally concise while hitting every required section and citing specific anchors. All positions are grounded in the actual code and prior ratified artifacts read during this session.