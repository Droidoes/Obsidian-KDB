# Task #90 v0.1 Review — Codex

## Convergence

The core shape holds: Option A gives a clean production default, `T2Mode` preserves the A/B comparison path, and alias-aware structured lookup is the right consumer for D-89-20. Keeping `ContextSnapshot` unchanged is also the right boundary: Pass-2 should see better context, not a new contract.

I tested the proposed §3.3 query shape against local Kuzu `0.11.3`; `UNWIND $raw_slugs`, chained `OPTIONAL MATCH`, `WITH`, and `CASE` all parsed and returned expected rows in a small temp graph. Kuzu compatibility is therefore not the main risk.

## Findings

**Finding F-1:** §6.2's preferred plumbing path has a likely import-cycle trap.

> `planner.build_jobs` calls `source_text_for(job)` (already returns `(SourceFrontmatter | None, body)`)

`compiler.py` imports `planner` at module import time, so `planner.py` should not import `compiler.source_text_for` directly. A lazy import might avoid immediate failure but would encode the wrong ownership boundary. If planner needs Pass-1 frontmatter, move `SourceFrontmatter` + `source_text_for` or a narrower `read_source_frontmatter_and_body` helper into a neutral module, or duplicate parsing in planner explicitly. Option (i) is still fine; the blueprint should amend the helper location.

**Finding F-2:** Empty `entity_search_keys` and missing `entity_search_keys` are currently collapsed before Task #90 can decide OQ-90-1.

`SourceFrontmatter.from_dict()` defaults missing `entity_search_keys` to `[]`, and §6.1 treats empty as legacy fallback. That makes three cases indistinguishable: no Pass-1 frontmatter, pre-v0.2.2 Pass-1 frontmatter missing the field, and v0.2.2 Pass-1 frontmatter explicitly saying `entity_search_keys: []`. OQ-90-1 cannot be implemented honestly without preserving field presence.

**Finding F-3:** The §3.3 batch query does not itself enforce the helper contract for `canonical_id` targets.

§3.2 says the helper returns a canonical active entity or `None`, but the query branch `WHEN e.canonical_id IS NOT NULL THEN e.canonical_id` does not verify that the target entity exists and is active. `_t2_from_search_keys` later filters by `candidate_slugs`, so the production T2 set is protected, but the helper contract and alias-path telemetry would be cleaner if canonical_id resolution joined the target entity and returned only active canonical slugs.

**Finding F-4:** The current prompt encourages speculative fanout that can reduce lookup precision.

> `Closely-related concepts that frequently co-occur with the source's themes, even if not named explicitly`

Because the consumer is exact PK/alias lookup, unmentioned co-occurrence guesses are the highest miss-rate category. This is not fatal, but it should be capped and deprioritized in the prompt.

**Finding F-5:** §7.1 should preserve the existing purity boundary: `graph_context_loader` should not read env vars.

The current loader docstring says planner selects context behavior and the loader does not read env vars. Keep that invariant: `KDB_T2_MODE` can be a v1 mechanism, but parse it in `planner`, pass an explicit `T2Mode` into `build_context_snapshot`, and let benchmark harnesses pass mode directly to avoid env leakage across runs.

## Recommendations / OQ Positions

**OQ-90-1:** Distinguish absent from explicit empty. Fallback to legacy only when frontmatter is absent or the field is missing from older enriched files. Treat explicit `entity_search_keys: []` as empty T2. That is the more honest interpretation of a current Pass-1 signal.

**OQ-90-2:** Use 5% raw zero-hit rate as an alert, not the only trigger. Track denominator as enriched `kdb_signal=signal` sources with non-empty keys, plus a separate cold-start/T1-empty zero-hit rate. A 2-3% cold-start zero-hit rate is already worth investigating because those are the sources most dependent on T2.

**OQ-90-3:** The batch query shape is sane on Kuzu `0.11.3`. Amend the query to validate `canonical_id` targets as active, or document that candidate-pool filtering is the final active check.

**OQ-90-4:** See prompt block below.

**OQ-90-5 / D-90-7:** Prefer double-parse for v1, but not via a planner import from `compiler.py`. Use a neutral helper module. Do not attach frontmatter to `CompileJob` yet.

**OQ-90-6:** Env var is sufficient for v1 if planner owns parsing and tests clear/parameterize it. No config file yet.

**OQ-90-7:** Keep `T2Mode` in `graph_context_loader`. It is an algorithm knob, not a persisted cross-module data type. Export a small parser if planner needs it.

**OQ-90-8:** Define the sunset trigger now but do not schedule deletion: legacy branch deletable only after 100% enriched corpus, NW-9 says structured/layered dominates legacy on cold-start, and at least one full compile cycle has no legacy-path invocations.

**D-90-5:** Defensible as written: title-phrase widening should survive only on legacy/LAYERED paths. Adding it to STRUCTURED would make Option A less clean and blur NW-9.

**D-90-6:** Agree: no zero-hit fallback in v1. Add telemetry and tests, not fallback logic.

**D-90-7:** Agree on no `CompileJob` schema change, subject to F-1's helper-location amendment.

## Prompt Review

**Anchoring:** Strengthen the consumer mechanism. Suggested wording:

> These keys are looked up against existing graph `Entity.slug` values, with alias resolution. Prefer slugs that are likely to already exist as durable graph entities; do not invent narrow one-off phrases unless the source names them explicitly.

**Category boundaries:** Keep categories 1-3. Rewrite category 4 to:

> Optionally include 0-2 closely related canonical concepts not named explicitly, only when they are central to the source's argument and likely to already exist as graph entities.

**Name disambiguation:** Full-name should be default for people. Surname-only should be optional for globally recognizable or commonly slugged figures, not automatic `and/or`. Otherwise the Buffett/Munger example spends four of ten slots on two people.

**Cap of 10:** Keep schema max 10, but prompt for 4-8 normally. A healthy average hit rate should be above ~50% initially and trend toward 70%+ as aliases mature. Filling to 10 is less valuable than preserving precision.

**Example diversity:** Add 2 compact examples, not long exemplars. One finance example is currently too anchoring. Include one `ai-ml` and one `philosophy-ethics` or `arts-design` example to demonstrate that names/frameworks/themes generalize across domains.

## Edge-Case Probes

1. `["aapl", "apple-inc"]`; graph has `aapl -ALIAS_OF-> apple-inc`, both keys resolve to `apple-inc`; set semantics produce one T2 hit. Good.

2. `["see's-candies"]`; graph has `sees-candies` only; current exact lookup misses. This is acceptable for v1 but should be classified as orthography drift in telemetry, not semantic zero-hit.

3. Explicit `entity_search_keys: []`; graph and body contain many legacy slug/title matches. My recommendation: STRUCTURED returns empty T2 because Pass-1 made a current explicit no-anchor call. LAYERED/LEGACY can recover matches for benchmark comparison.

4. `["buffett", "warren-buffett", "intrinsic-value"]`; graph has no Buffett alias but has `warren-buffett` and `intrinsic-value`. Produces two hits; redundant surname costs one slot but does no structural harm.

5. `["old-alias"]`; graph row has `canonical_id="retired-canon"` but target is inactive/missing. Production T2 should exclude it through candidate filtering; resolver contract should still return `None`.

## Open Questions

1. Should `SourceFrontmatter` carry a boolean like `has_entity_search_keys` so OQ-90-1 remains observable without changing `CompileJob`?

2. Should NW-9 stratify by T1 state (`T1=0` vs `T1>0`) in addition to domain/source_type? That axis is more directly tied to T2 value than domain coverage alone.

3. Should telemetry count duplicate raw keys separately for prompt quality, even though T2 set semantics correctly deduplicate resolved slugs?
