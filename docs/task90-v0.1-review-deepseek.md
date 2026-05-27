# Task #90 v0.1 — Deepseek Review

**Reviewer:** deepcode CLI / Deepseek
**Artifact:** `docs/task90-context-loader-t2-rewrite-blueprint.md` v0.1
**Date:** 2026-05-27

---

## 1. Convergence

The blueprint holds together cleanly on the following axes:

- **T2Mode enum + dispatch (§2.1).** Three-mode abstraction is elegant. STRUCTURED/LAYERED/LEGACY map cleanly to the Options A/B/baseline, and the dispatch pattern makes the benchmark's A/B comparison trivial. Joseph's "we paint ourselves no corner" requirement is satisfied.
- **Alias resolver design (§3).** Three-path reachability (direct → canonical_id → ALIAS_OF) is correct and aligns with Task #74's flattened canonical_id chains. A single resolution step suffices.
- **Branch selector semantics (§6.1).** `frontmatter is not None and frontmatter.entity_search_keys` is simple, testable, and correctly gates on "Pass-1 enriched." The incremental migration story (one source at a time) is natural given the 0-of-1663 enriched corpus.
- **§2.5 `_t2_from_search_keys` core.** Resolve → intersect with candidate pool is the right contract. The candidate-pool filter automatically handles T1 exclusion and inactive-entity pruning in one step.
- **No Pass-2 schema change (§1.3).** `ContextSnapshot` stays identical. This is the highest-value invariant in the blueprint — it guarantees that the context-loader rewrite cannot break the compile prompt contract.

---

## 2. Findings

**Finding F-1: `entity_search_keys=[]` conflates two distinct states (§2.2, §6.1, OQ-90-1)**

The branch selector treats `entity_search_keys=[]` identically to `frontmatter is None`. These are semantically different:

| State | Meaning |
|---|---|
| `frontmatter is None` | No Pass-1 run; source is pre-Pass-1 |
| `entity_search_keys=[]` | Pass-1 ran; LLM emitted empty list |

The second state could mean "LLM genuinely found no graph anchors" OR "LLM degraded and failed to produce keys." The current proposal collapses both to legacy-branch fallback, which is safe but loses telemetry signal. If 20% of enriched sources produce `entity_search_keys=[]` and all silently fall through to legacy, we'd never know whether the prompt is under-producing or the LLM is being honest. §10 telemetry should separately track (a) unenriched sources hitting legacy, (b) enriched-with-empty-keys hitting legacy, and (c) enriched-with-nonempty-keys producing zero resolved hits.

**Finding F-2: Batch query doesn't validate canonical_id target's active status (§3.3)**

The `CASE` expression at line 183 tests `e.canonical_id IS NOT NULL` and returns `e.canonical_id` directly — without checking whether the entity at that canonical_id slug is active. Contrast with line 182 (`e.status = 'active' AND e.canonical_id IS NULL`) and line 184 (`canon.status = 'active'`). If an Entity has `canonical_id='old-deprecated-concept'` and that target entity is stale/archived, we'd return an inactive slug. The CASE should fold `canonical_id` path into a subquery or add an active-status check on the resolved target.

**Finding F-3: `UNWIND` with parameterized list — Kuzu compatibility uncertain (§3.3, OQ-90-3)**

The batch query uses `UNWIND $raw_slugs AS raw`. Kuzu supports parameterized scalars, but Kuzu's Python API `conn.execute(query, {"raw_slugs": [...]})` maps Python `list` to Kuzu's `LIST` type, not to a Cypher row-unwinding operation. The `UNWIND` clause is defined in openCypher but may not be in Kuzu's implemented subset. The `OPTIONAL MATCH ... WITH ... OPTIONAL MATCH` chain is also potentially problematic — Kuzu's `WITH` semantics differ from Neo4j's (Kuzu uses `WITH` as a projection barrier, not a pipelining operator). The blueprint's caveat ("may unfold into 1–2 queries") is noted, but I'd strengthen it: **plan on the 1-query-per-key fallback as the primary implementation path**, and attempt the batch query as an optimization only after verifying Kuzu compatibility at implementation time.

**Finding F-4: Shape validation gap between prompt and schema (§4 prompt vs. §3.2 signature)**

The prompt says "no punctuation other than hyphens" — which disallows apostrophes. But §6.4 test plan flags `"see's-candies"` as a shape-relaxation case under `[[feedback_no_imaginary_risk]]`. This creates a tension: the prompt instructs the LLM to avoid apostrophes, but the schema may accept them. Three resolutions: (a) tighten the schema to reject apostrophes (align with prompt), (b) relax the prompt to match schema tolerance, or (c) keep the gap and let the lookup fail harmlessly (resolve returns None). Option (a) is cleanest — if the prompt already constrains the format, the schema should enforce it.

**Finding F-5: §2.7 "context_snapshot.pages = []" — Pass-2 behavior with empty context is assumed but not verified**

The blueprint states that shipping to Pass-2 with `context_snapshot.pages = []` is "the same behavior the snapshot already produces." The current `build_context_snapshot` returns `ContextSnapshot(source_id=source_id, pages=[])` on empty active entities — that path is exercised. But the current code never produces empty pages when active_entities IS non-empty and source_text IS non-empty (the regex will always at least attempt matching). The zero-hit path in the new code would be the first production path that produces empty context on an otherwise healthy graph. A quick audit of the compile prompt template to confirm it handles `pages=[]` gracefully (e.g., emits "no related pages found" rather than crashing on empty context injection) would de-risk this.

---

## 3. Recommendations

### Open Questions (§9)

**OQ-90-1 — `entity_search_keys=[]` semantics: Retain current proposal (fall back to legacy), with telemetry split.**

An empty list is more likely LLM conservatism/degradation than a deliberate "no anchors" signal. The prompt says "aim for 5–10" — an LLM that understood the task but found nothing would likely still emit 1–3 keys at low confidence, not `[]`. Falling back to legacy is the safer default for v1. **But** track enriched-with-empty-keys as a separate telemetry bucket (see F-1). If that bucket's Pass-2 quality is indistinguishable from the unenriched bucket, we have empirical justification to switch to "respect the empty list."

**OQ-90-2 — Zero-hit threshold: 5% on substantive sources, not raw rate.**

A source whose `entity_search_keys` resolves to zero because it's about a niche topic with no graph presence yet is a qualitatively different failure from a source where the LLM emitted garbage slugs. Recommend threshold calculation: zero-hit rate on enriched sources where `|entity_search_keys| ≥ 3` (filtering out LLMs that barely tried). This is a precision-on-substantive-source metric.

**OQ-90-3 — Kuzu Cypher: Plan for 1-query-per-key primary path. See F-3.**

**OQ-90-4 — Prompt review: See dedicated §4 below.**

**OQ-90-5 — Frontmatter plumbing: Confirm option (i), planner double-parses.**

YAML parsing is ~microseconds. The risk of touching `CompileJob` schema (which flows into compiler.py, the most complex module) outweighs any performance concern. `[[feedback_no_imaginary_risk]]` applies directly.

**OQ-90-6 — Mode selection: `KDB_T2_MODE` env var sufficient for v1.**

A config file is over-engineering for a mechanism that exists primarily to enable the NW-9 benchmark. If T2Mode survives long-term, add a `kdb-compile --t2-mode` CLI flag then.

**OQ-90-7 — T2Mode enum location: Keep in `graph_context_loader.py`.**

The enum is tightly coupled to T2 construction. Planner already imports `graph_context_loader` as a module, so `graph_context_loader.T2Mode` requires no new import topology. If future modules need T2Mode independently of the loader, promote to `types.py` at that point.

**OQ-90-8 — Legacy sunset trigger: Fix now.**

Add a `logger.info("T2 falling back to legacy regex for source %s", source_id)` call in the legacy branch. The deletion gate: 100% of compile-eligible corpus enriched AND NW-9 confirms STRUCTURED ≥ LEGACY on cold-start density AND STRUCTURED precision ≥ LEGACY. Document in blueprint v0.2.

### Open Decisions (§11)

**D-90-5 — Title-phrase widening: Agree, legacy-branch only for v1. But flag as explicit NW-9 comparison axis.**

The rationale is sound: `entity_search_keys` is the explicit "slugs to seed" signal. Title-phrase matching on the structured branch would double-count what the LLM should have captured. But the NW-9 benchmark must include a D-90-5 axis: "does LAYERED (which implicitly includes title-phrase via union with legacy) outperform STRUCTURED on cold-start sources where entity_search_keys is non-empty?" This is the cleanest way to test whether title-phrase widening adds signal or noise on enriched sources.

**D-90-6 — Zero-hit fallback: Agree, none in v1.**

`[[feedback_no_imaginary_risk]]` is the governing principle. The >5% telemetry gate is appropriately conservative.

**D-90-7 — Frontmatter plumbing: Agree with option (i).**

See OQ-90-5.

---

## 4. Prompt-Review Block (§4 Pass-1 Prompt)

### 4.1 Anchoring — partial

The prompt says entities are "keyed by a concept slug" but does **not** communicate that:
- The lookup is an **exact PK match** (not fuzzy/search)
- An **alias resolution** layer exists (canonical_id + ALIAS_OF)

Without this anchoring, the LLM may emit slugs that are "close but not exact" (e.g., "value-investing-strategy" instead of "value-investing"), believing the system will fuzzy-match. The prompt should add one sentence explaining how slugs will be consumed, without implementation detail:

> The downstream system matches each key against entity primary keys (exact match) and also resolves aliases automatically — so you can target canonical concepts directly.

### 4.2 Category boundaries — Category 4 is the risk point

Category 4 ("closely-related concepts that frequently co-occur with the source's themes, even if not named explicitly") is correctly scoped by "small fanout" and the 10-cap. But the LLM has no information about **which concepts actually exist** in the graph. Without that constraint, Category 4 is a blind guess. Mitigation: add a qualifier that anchors fanout to confidence:

> 4. Closely-related concepts that frequently co-occur with the source's themes, even if not named explicitly — **prefer concepts you are confident exist in any well-populated knowledge graph** (e.g., canonical named frameworks, widely-cited ideas, standard terminology). This is discovery, not invention.

### 4.3 Name disambiguation — dual-form guidance should reference alias resolution

The prompt tells the LLM to emit both "buffett" and "warren-buffett." With alias resolution (ALIAS_OF edges), this is redundant — both resolve to the same canonical slug. But the LLM doesn't know that. Recommendation: keep the dual-form guidance (alias resolution may not be present for every name in every graph state), but add a note:

> Use surname-only for well-known figures ("buffett") and/or full-name form ("warren-buffett") when ambiguity is possible. The downstream system handles variant resolution, so prefer the form most likely to match an entity slug directly — you don't need to cover every variant exhaustively.

This reduces the pressure to burn multiple slots on the same person.

### 4.4 Cap of 10 — keep 10

At an expected hit rate of 50–70% per §10 thresholds, 10 keys → 5–7 T2 entries. With T1 often contributing 3–8 entries and T3 expanding from there, this is a healthy T2 contribution. A sharper cap (e.g., 7) risks under-filling on sources where the LLM is uncertain and needs the headroom to try more candidates. Keep 10; let telemetry tell us if the average emissions cluster at the cap.

### 4.5 Example diversity — strongest recommendation

**Add ≥3 domain-diverse examples.** The single finance-domain example (Buffett/Munger/value-investing) will anchor LLM emissions to:
- Finance-domain slug patterns ("berkshire-hathaway", "circle-of-competence")
- Heavy proper-name density versus concept-framework density
- "Great Man" framing (people-first) versus idea-first framing

Proposed additional examples:

```
Example 1 (finance/people-heavy):
  ... [current example, kept] ...

Example 2 (AI/ML, concept-heavy):
  source about attention mechanisms in transformer architectures
  with key_themes ["attention-mechanism", "self-attention", "transformers"]
  → ["attention-mechanism", "self-attention", "transformers", "multi-head-attention",
     "vaswani", "bert", "positional-encoding", "sequence-to-sequence",
     "neural-machine-translation", "scaled-dot-product"]

Example 3 (philosophy-ethics, abstract):
  source about Rawls' veil of ignorance and distributive justice
  with key_themes ["veil-of-ignorance", "distributive-justice", "original-position"]
  → ["veil-of-ignorance", "distributive-justice", "original-position", "john-rawls",
     "rawls", "theory-of-justice", "social-contract", "maximin-principle",
     "kantian-ethics", "egalitarianism"]
```

Three examples also gives the LLM a better model of the "5–10" range: one at the cap (10), one that could be 8–10, one at 5–7.

### 4.6 Additional prompt observation

> "Format: lowercase, hyphens between words, no spaces, no punctuation other than hyphens."

The example includes "graham-and-doddsville" — the word "and" inside a slug. The instruction "no punctuation other than hyphens" covers this (letters-and-hyphens), but it's worth explicitly noting that conjunctions and prepositions inside kebab-case are fine, since an LLM might otherwise strip function words (producing "graham-doddsville" or "attention-mechanism-transformers").

---

## 5. Edge-Case Probes

**Probe 1: Duplicate keys after alias resolution.**
`entity_search_keys = ["buffett", "warren-buffett"]`, graph has `ALIAS_OF(buffett)→warren-buffett`. Both resolve to "warren-buffett". `_t2_from_search_keys` uses `set` semantics — deduplication is automatic. ✓ Clean.

**Probe 2: Entity has both canonical_id AND ALIAS_OF edge — ambiguity.**
Entity `"buffett"` has `canonical_id="warren-buffett"` AND `ALIAS_OF→"berkshire-hathaway"`. Per §3.1 order: direct match fails (we're resolving "buffett") → canonical_id check → returns "warren-buffett". The ALIAS_OF edge to "berkshire-hathaway" is never checked. Is "warren-buffett" always the right answer? In this case yes (the alias-pointer is the stronger signal), but if the canonical_id is stale and the ALIAS_OF edge is more current, we'd still surface the stale target. This is a pathological edge case but worth noting in the implementation comments.

**Probe 3: Slug with apostrophe passes relaxed shape validation.**
`entity_search_keys = ["see's-candies"]`. Current prompt says no punctuation beyond hyphens, but schema may relax. `_resolve_to_canonical_slug` does no normalization — passes "see's-candies" to Kuzu as-is. If no entity exists with that exact slug, returns None. No crash, clean miss. ✓ Harmless. See F-4 for alignment recommendation.

**Probe 4: All keys resolve but none survive candidate-pool intersection.**
`entity_search_keys = ["python", "javascript", "rust"]`, all resolve to canonical slugs, but all three are already in T1 (the source SUPPORTS them). `candidate_slugs = active_slugs - t1_slugs` excludes them. Result: empty T2. T1 already has them, so no information loss. ✓ Correct.

**Probe 5: entity_search_keys on cold-start source (T1 empty), LLM emits only obscure keys.**
`entity_search_keys = ["niche-concept-no-graph-presence", "another-obscure-term"]`, T1 is empty. Both miss resolution → empty T2. T3: `max_hops=2` because cold-start + |T2| < 5. But seeds = ∅, so T3 is also empty. Source ships with `pages=[]`. Pass-2 receives zero context. This is the worst-case scenario: enriched source, non-empty search keys, zero context. If Pass-2 with empty context produces acceptable output (no crash, no hallucination spiral), this is survivable. If not, this case warrants a test. See F-5.

---

## 6. Open Questions

1. **Pass-2 behavior on empty context:** Has a compile run with `context_snapshot.pages=[]` on a non-trivial source been tested? The blueprint assumes it's fine (§2.7), but the current production code never produces this state on a healthy graph with non-empty source_text. A smoke test before implementation would de-risk.

2. **Mode-env-var parsing location:** The blueprint says planner threads `mode` from env var. The env var should be parsed once at planner entry (not per-job in a loop). The implementation task should specify this.

3. **`_t2_from_search_keys` signature carries `conn` but `_t2_legacy` does not:** The dispatcher in §2.1 calls `_t2_legacy(source_text, candidate_slugs, cold_start, active_entities)` — no `conn`. This is correct (regex is graph-independent) but creates an asymmetric signature pattern across branches. A minor code-organization concern: `_t2_legacy` and `_t2_structured` take different param sets. The `_build_t2` dispatcher handles this, but it's a readability tax on anyone reading the dispatch code.

4. **Entity status filter in alias resolution:** §3.1 requires active-entity checks on canonical_id targets and ALIAS_OF targets. The batch query in §3.3 checks `e.status = 'active'` and `canon.status = 'active'` but **not** the canonical_id target (see F-2). The 1-query-per-key fallback should explicitly validate active status at each resolution path.
