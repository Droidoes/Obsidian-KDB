# Task #90 v0.1 Review — Qwen CLI (qwen3.7-max)

**Reviewer:** Qwen CLI / qwen3.7-max
**Blueprint reviewed:** `docs/task90-context-loader-t2-rewrite-blueprint.md` (v0.1)
**Date:** 2026-05-27
**Guardrail compliance:** Single file produced; no other repo files modified.

---

## 1. Convergence

The blueprint's architectural shape is sound and ready for implementation. Specific elements that hold together cleanly:

- **Three-mode `T2Mode` dispatch** (§2.1) is a clean separation of concerns. STRUCTURED/LAYERED/LEGACY provide exactly the A/B/baseline comparison surface the benchmark (NW-9) needs, with no coupling between modes.
- **Alias-resolution ordering** (§3.1) — direct PK → `canonical_id` → `ALIAS_OF` — is consistent with the C1/C2/C3 invariants enforced by `graphdb_kdb/verifier.py`. Path 2 wins over path 3 via the `canonical_id IS NOT NULL` short-circuit, which is correct per D-R5-13's flat-chain invariant.
- **Backward-compat via branch selector** (§6.1) — `frontmatter is not None and frontmatter.entity_search_keys` — is minimal and correct. Incremental migration (no flag day) matches the project's "no complexity for imaginary risk" philosophy.
- **`T2Mode` + env-var flip protocol** (§7.1/§7.3) achieves the "paint ourselves no corner" property. One-line default change gated on empirical evidence is the right risk model.
- **Pass-2 invariance** (§1.3) — `ContextSnapshot` schema unchanged, `entity_search_keys` never reaches Pass-2 — preserves the compile pipeline's proven contract.

---

## 2. Findings

**Finding F-1: §3.3 batch Cypher uses three Kuzu features with zero codebase precedent (OQ-90-3).**
Grep across the entire project shows no existing Kuzu query uses `UNWIND`, `OPTIONAL MATCH`, or `CASE WHEN`. Every query in `graph_context_loader.py`, `ingestor.py`, `verifier.py`, `queries.py`, and `snapshot.py` uses simple `MATCH` with `$param` binding. Kuzu's Cypher subset is known to diverge from Neo4j's in non-obvious ways (e.g., variable-length path semantics, parameterized UNWIND). The blueprint acknowledges this ("Kuzu Cypher dialect compatibility to be verified at implementation time") but the fallback shape — "1–2 simple queries" — is unspecified.

**Recommendation:** Pin the fallback query shape in the algorithm-details task, not deferred to implementation. The fallback is straightforward: (a) one `MATCH (e:Entity) WHERE e.slug IN $slugs RETURN e.slug, e.status, e.canonical_id` for direct + canonical_id paths; (b) one `MATCH (e:Entity)-[:ALIAS_OF]->(c:Entity) WHERE e.slug IN $slugs RETURN e.slug, c.slug, c.status` for the ALIAS_OF path. Both use only MATCH + WHERE + IN, which Kuzu supports. The batch CASE query is aspirational; the two-query fallback should be the documented default, not the exception.

---

**Finding F-2: §5 planner frontmatter parsing mechanism is underspecified.**
The planner's current `_read_source_text` (line ~92 of `planner.py`) does a raw `abs_path.read_text()` — it does not parse YAML frontmatter. `source_text_for` lives in `compiler.py` (line 156). §6.2 option (i) says "planner.build_jobs calls `source_text_for(job)`" but `source_text_for` takes a `CompileJob` which doesn't exist yet at planner time (the job is the output, not the input). The plumbing needs either: (a) lift `source_text_for`'s internals (`parse_existing_frontmatter` + `SourceFrontmatter.from_dict`) into a shared helper callable with just a path, or (b) inline the two-line parse in the planner.

**Recommendation:** Extract a `parse_source_file(path: Path) -> tuple[SourceFrontmatter | None, str]` helper into a shared module (e.g., `kdb_compiler/source_io.py`). Both planner and compiler call it. This is option (i)'s intent but with the implementation gap closed. The existing `source_text_for` becomes a thin wrapper that calls `parse_source_file(job.abs_path)`.

---

**Finding F-3: Category 4 of the Pass-1 prompt creates an unbounded speculative fanout that works against the hit-rate metric (§4 prompt, OQ-90-4).**
Category 4 instructs the LLM to emit "closely-related concepts that frequently co-occur with the source's themes, **even if not named explicitly**." This directly incentivizes slug invention — keys for entities the LLM thinks *might* exist in the graph but has no evidence for. The hit-rate metric (§10 watch-for #1: "|alias-resolved slugs| / |entity_search_keys emitted|") punishes exactly this behavior. The prompt's category 4 and the telemetry's hit-rate metric are adversarial.

Additionally, category 4 contradicts the prompt's own "prefer specificity over breadth" guidance within the same paragraph.

**Recommendation:** See Prompt-review block §4 below for specific wording edits.

---

**Finding F-4: Surname-only AND full-name guidance wastes cap budget (§4 prompt category 3).**
The prompt asks for both "buffett" and "warren-buffett." After alias resolution, both resolve to the same canonical entity (assuming both exist as Entity rows or ALIAS_OF pointers). The deduplication via `set` in `_t2_from_search_keys` (§2.5) means the duplicate is harmless to correctness — but it consumes 2 of 10 available key slots for 1 entity. On a source with 3 named people, this pattern alone eats 6 of 10 slots, leaving only 4 for themes, variants, and fanout.

**Recommendation:** See Prompt-review block §4 below.

---

**Finding F-5: Single finance-domain example anchors LLM emissions (§4 prompt).**
The sole in-prompt example uses Buffett/Munger/value-investing — 10 keys, all finance-domain. For a vault with 23 domain vocabs including `ai-ml`, `philosophy-ethics`, `arts-design`, `military-strategy`, `biology-evolution`, this creates systematic anchoring bias. The LLM will over-index on person-name patterns (categories 3's surname/full-name trick) and under-represent concept-slug patterns for non-finance domains.

**Recommendation:** See Prompt-review block §4 below.

---

**Observation O-1: `candidate_slugs` exclusion of T1 slugs prevents double-counting correctly.**
Verified in `build_context_snapshot` (line ~57): `t2_slugs = _t2_slug_in_text(source_text, slug_set - t1_slugs)`. The new `_t2_from_search_keys` receives the same `candidate_slugs = active_slugs - t1_slugs`. An entity_search_key that resolves to a T1 entity is correctly filtered out. This is sound.

---

**Observation O-2: `_resolve_to_canonical_slug` needs a defensive `strip()` despite the prompt's format guidance.**
The schema (`pass1_schema.py` line ~87) validates `entity_search_keys` as `{"type": "array", "items": {"type": "string"}, "maxItems": 10}` — no format regex. The comment explicitly notes: "A strict regex caused real LLM emissions like 'see's-candies' to reject the whole envelope." The prompt asks for "lowercase, hyphens between words, no spaces" but prompt discipline is not a schema guarantee. A leading/trailing whitespace strip in `_resolve_to_canonical_slug` is cheap insurance.

---

**Observation O-3: Benchmark mode-switching via env var is safe against false-positive deltas.**
Each `kdb-compile` invocation is a fresh process. `KDB_T2_MODE` is read once at `build_jobs` entry. No state leakage between benchmark runs as long as each run is a separate process invocation (which the benchmark harness would do naturally). No finding here — just confirming §7.1's mechanism is sound.

---

## 3. Recommendations — Open Questions & Decisions

### OQ-90-1: `entity_search_keys=[]` semantics

**Position: Respect the LLM's "no graph anchors" signal; emit empty T2.**

Treating `[]` as "fall back to legacy" conflates two distinct states: (a) the LLM explicitly found nothing worth looking up, vs. (b) the source was never enriched. The branch selector (§6.1) already distinguishes "no frontmatter" (pre-Pass-1) from "frontmatter with empty keys" (Pass-1 said nothing). Conflating them means a well-tuned LLM that correctly identifies a source as having zero graph-relevant content still gets the regex heuristic — which may produce false-positive T2 hits that hurt Pass-2 context quality.

The fallback is conservative (regex might find something useful) but dishonest (overrides the LLM's explicit judgment). For v1, honest semantics are preferable: if the LLM says zero keys, ship zero T2. If telemetry shows this is wrong (sources with `[]` that *do* have graph anchors), the fix is a prompt adjustment, not a silent fallback.

---

### OQ-90-2: Zero-hit fallback threshold (5%)

**Position: 5% raw rate is acceptable for v1; add a secondary precision metric for post-NW-9 analysis.**

The 5% raw rate is a reasonable tripwire. But raw rate conflates two failure modes: (a) LLM emitted slugs that don't exist in the graph (orthographic drift — fixable via prompt tuning), and (b) LLM emitted valid slugs but the graph genuinely lacks the entities (coverage gap — fixable via more compile runs). The §10 telemetry watch-for #4 ("fraction of resolutions via direct PK vs canonical_id vs ALIAS_OF") partially captures this, but a dedicated "drift vs. coverage" breakdown would be more actionable. Recommend adding this to §10 as watch-for #6.

---

### OQ-90-3: Kuzu Cypher batch query

**Position: Fallback to two simple queries should be the documented default, not the exception.**

Per Finding F-1, no existing codebase query uses UNWIND/OPTIONAL-MATCH/CASE. The aspirational single-query form is nice-to-have; the two-query fallback (direct+canonical_id via MATCH WHERE IN, then ALIAS_OF via MATCH→ALIAS_OF→ WHERE IN) should be the implementation target for v1, with the single-query optimization deferred to the algorithm-details task or post-v1. This is consistent with `[[feedback_no_imaginary_risk]]` — don't invest in a complex query shape when a simple one works.

---

### OQ-90-4: Pass-1 prompt review

**See dedicated §4 block below.**

---

### OQ-90-5: Frontmatter plumbing

**Position: Confirm option (i) — double-parse — with the implementation gap noted in F-2.**

Double-parse is correct per `[[feedback_no_imaginary_risk]]`. YAML parse cost is negligible. `CompileJob` schema stays unchanged. But the planner needs a shared `parse_source_file` helper (see F-2 recommendation) — `_read_source_text` alone is insufficient.

---

### OQ-90-6: Mode selection mechanism

**Position: Env var `KDB_T2_MODE` is sufficient for v1.**

Consistent with existing project patterns (`KDB_CONTEXT_SOURCE`, `KDB_RESP_STATS_CAPTURE_FULL`, etc.). Config-file mechanism is over-engineering for a single enum-valued flag. A `--t2-mode` CLI flag on `kdb-compile` is a natural v1.1 addition if benchmark harness needs it.

---

### OQ-90-7: `T2Mode` enum location

**Position: Keep in `graph_context_loader.py` (current proposal).**

The enum is consumed only by `_build_t2` and `build_context_snapshot`, both in `graph_context_loader.py`. Moving to `types.py` (where `CompileJob`/`ContextSnapshot` live) would be premature generalization — `types.py` is for cross-module data shapes, not module-local control flow enums. If the planner ever needs to import `T2Mode` for its own dispatch logic, it can import from `graph_context_loader` — there's no circular-dependency risk since planner already imports from `graph_context_loader`.

---

### OQ-90-8: Legacy branch sunset trigger

**Position: Do not fix a trigger now. Revisit post-NW-9.**

The sunset condition (100% enriched + STRUCTURED > LEGACY on cold-start) is clear enough in prose. Codifying it as an automated trigger is premature — the vault's enrichment trajectory is unknown, and the benchmark hasn't run. The legacy branch is low-maintenance code (~30 lines of regex helpers). No urgency to delete.

---

### D-90-5: Cold-start title-phrase widening on legacy branch only

**Position: Defensible. Do not extend to structured branch.**

Title-phrase widening (Task #71 / D48) solves a specific problem: when T1 is empty and regex-only T2 is sparse, title matching adds seeds. On the structured branch, `entity_search_keys` IS the explicit "slugs to seed" signal — the LLM has already done the work that title-phrase matching approximates. Adding title-phrase matching on top of structured keys would be a LAYERED variant (Option B), which is what the benchmark will test. Keeping the separation clean is the right call.

---

### D-90-6: Zero-hit fallback — none in v1

**Position: Agree. No fallback in v1.**

Per `[[feedback_no_imaginary_risk]]` and my OQ-90-1 position (respect the LLM's empty signal), adding a fallback for a case that may never materialize at >5% rate is premature. The telemetry gate (§2.7) is the right mechanism.

---

### D-90-7: Frontmatter plumbing — planner double-parses

**Position: Agree, with the F-2 implementation note.**

---

## 4. Prompt-Review Block (§4 Pass-1 `entity_search_keys` prompt)

### 4.1 Anchoring

The prompt says "designed to find related existing entities in a downstream knowledge graph (where each entity is keyed by a concept slug)." This is too vague about the resolution mechanism. The LLM has no idea that:

- Slugs are resolved via `Entity.slug` PK lookup (exact match, not fuzzy).
- An alias-resolution layer exists (canonical_id + ALIAS_OF), so emitting both "buffett" and "warren-buffett" is redundant if both exist as entities/aliases.
- Only active entities are in the candidate pool.

**Suggested wording edit** — add one sentence after the first line:

> These keys are matched against entity slugs by exact string comparison (with an alias-resolution layer that maps known variant slugs to their canonical form), so emit the slug forms most likely to match existing entity records.

This gives the LLM enough information to optimize for the actual lookup mechanism without exposing implementation details.

---

### 4.2 Category boundaries

**Category 4 must be tightened.** Current wording:

> Closely-related concepts that frequently co-occur with the source's themes, even if not named explicitly (a small fanout for graph discovery).

The phrase "even if not named explicitly" is the problem — it invites the LLM to speculate about entities that may not exist in the graph. Every speculative key that misses lowers the hit rate. Replace with:

> Closely-related concepts that are substantively discussed in the source and likely to have their own entity records in the graph (e.g., a framework's foundational principle, a theory's key critic). Only include concepts you believe have dedicated entity entries — do not guess.

This preserves the fanout intent while anchoring the LLM to the "does this entity actually exist?" question.

---

### 4.3 Name disambiguation

Current wording:

> Use surname-only for well-known figures ("buffett") and/or full-name form ("warren-buffett") when ambiguity is possible.

The "and/or" is the issue — it produces redundant pairs. The alias-resolution system (§3) handles both forms, so emitting both wastes cap budget. Replace with:

> Use the shortest unambiguous slug form for well-known figures ("buffett" if no other Buffett exists in the graph; "warren-buffett" when disambiguation is needed). The graph's alias system resolves known variants, so emit one form per person — not both.

This guidance trusts the alias layer and saves cap slots.

---

### 4.4 Cap of 10

10 is acceptable for v1. The example fills all 10 slots, which is a signal that the cap is tight but workable. A realistic well-tuned hit rate should be 60–80% (6–8 alias-resolved hits per 10 emitted). Below 50% signals prompt drift or graph coverage gaps; above 80% suggests the LLM is being too conservative and could afford more fanout.

No change recommended, but the §10 telemetry watch-for #1 should publish the per-source and aggregate hit-rate distributions to validate this expectation.

---

### 4.5 Example diversity

**Must expand to ≥2 domain-diverse examples.** The single finance example anchors the LLM to person-name-heavy patterns (3 of 10 keys are person names × 2 forms). For sources in `ai-ml`, `philosophy-ethics`, or `biology-evolution`, concept slugs dominate and person names are rare.

**Suggested addition** (one more example, abbreviated to save prompt tokens):

> Example: source about transformer architectures in NLP with key_themes ["attention-mechanism", "self-supervised-learning", "scaling-laws"] → `["attention-mechanism", "self-supervised-learning", "scaling-laws", "transformer-architecture", "bert", "gpt", "vaswani", "neural-network", "tokenization", "transfer-learning"]`.

Two examples (finance + AI/ML) cover the vault's two largest domain clusters. A third (e.g., philosophy or military-strategy) would be ideal but may push prompt length past comfortable limits. Two is the minimum viable improvement.

---

## 5. Edge-Case Probes

### Probe 1: Entity has both `canonical_id` AND outgoing `ALIAS_OF` (C1-consistent state)

**Graph state:** Entity "aapl" has `canonical_id = "apple-inc"`, `status = "active"`, and an `ALIAS_OF` edge to "apple-inc" (also active).

**Input:** `entity_search_keys = ["aapl"]`

**Walk-through:** `_resolve_to_canonical_slug("aapl")` → path 1 fails (aapl exists but `canonical_id IS NOT NULL`) → path 2 fires (`canonical_id = "apple-inc"`, check active → yes) → return "apple-inc". Path 3 (ALIAS_OF) is never reached.

**Result:** Correct. `canonical_id` short-circuit wins, consistent with C1 invariant.

---

### Probe 2: Entity with `canonical_id` pointing to inactive entity

**Graph state:** Entity "old-name" has `canonical_id = "deprecated-entity"`, `status = "active"`. Entity "deprecated-entity" has `status = "inactive"`. An `ALIAS_OF` edge from "old-name" → "still-active-entity" exists.

**Input:** `entity_search_keys = ["old-name"]`

**Walk-through:** `_resolve_to_canonical_slug("old-name")` → path 1: entity exists but `canonical_id IS NOT NULL` → skip. Path 2: `canonical_id = "deprecated-entity"`, check active → **inactive** → return None. Path 3 is never reached because path 2's `canonical_id IS NOT NULL` gate in the CASE statement short-circuits before path 3 is evaluated.

**Result:** Miss. The ALIAS_OF edge to "still-active-entity" is never traversed. This is a data-consistency issue — C1 says `canonical_id IS NOT NULL` ↔ ALIAS_OF edge exists, and both should point to the same target. If they diverge, the C1 invariant is violated. But the verifier should catch this. **Recommend adding a unit test for this exact scenario** to verify the resolver degrades gracefully (returns None) rather than returning the wrong entity.

---

### Probe 3: Duplicate keys in `entity_search_keys`

**Input:** `entity_search_keys = ["value-investing", "value-investing", "buffett"]`

**Walk-through:** `_t2_from_search_keys` iterates raw keys. First "value-investing" resolves to "value-investing" (if active) → added to `resolved` set. Second "value-investing" resolves identically → `set.add` is idempotent. "buffett" resolves via ALIAS_OF to "warren-buffett" → added.

**Result:** Correct. Set semantics handle duplicates naturally. No finding.

---

### Probe 4: All keys resolve but none are in `candidate_slugs` (all already in T1)

**Graph state:** Source supports "value-investing" and "buffett" (both in T1). Entity_search_keys = `["value-investing", "buffett"]`.

**Input:** `candidate_slugs = active_slugs - t1_slugs` — neither "value-investing" nor "buffett" is in candidate_slugs.

**Walk-through:** Both resolve successfully, but `canonical in candidate_slugs` is False for both → `resolved` stays empty.

**Result:** Correct. T2 is empty because both entities are already T1. No double-counting.

---

### Probe 5: `entity_search_keys = []` on a Pass-1-enriched source

**Input:** Frontmatter present, `entity_search_keys = []`.

**Walk-through under current proposal (§6.1):** `frontmatter.entity_search_keys` is falsy (empty list) → `use_structured` is False → falls back to `_t2_legacy`.

**Walk-through under my OQ-90-1 recommendation:** Treat `[]` as explicit "no anchors" signal → T2 = empty set.

**Result:** Under current proposal, legacy regex fires on a Pass-1-enriched source, which is inconsistent — the source went through the LLM classifier, and the classifier said "nothing to look up." The regex override is dishonest. Under my recommendation, T2 is empty, which honestly reflects the LLM's judgment.

---

## 6. Open Questions

1. **`_load_active_entities` does not return `canonical_id`.** The current `_load_active_entities` (line ~107) loads `{slug: {title, page_type}}` — no `canonical_id` or alias info. The new `_resolve_to_canonical_slug` needs graph access for alias resolution. Should the active_entities dict be extended to carry canonical_id (avoiding a second query), or should alias resolution be entirely separate from the active_entities load? The former is more efficient; the latter is cleaner separation.

2. **Cold-start interaction on structured branch.** §2.6 says cold-start still triggers T3 max_hops=2 when |T2| < threshold. But on the structured branch, T2 comes from entity_search_keys. If the LLM emits 10 keys and 8 resolve, T2 = 8 (above the 5-seed threshold), so 2-hop never fires — even if the source genuinely is cold-start. Is this correct? Or should the cold-start 2-hop gate also consider T1 emptiness independently of T2 size?

3. **Pass-1 prompt version coupling.** The entity_search_keys prompt wording will evolve based on this review. Does the prompt version (`prompt_version` field in the Pass-1 envelope) need to be tracked alongside the hit-rate telemetry, so we can correlate prompt changes with hit-rate changes? If yes, this should be noted in §10.
