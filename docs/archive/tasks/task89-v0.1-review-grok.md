# Task #89 v0.1 Blueprint Review — Grok Build

## Convergence

I agree with the core architectural discipline running through v0.1:

- Pass-1 as a pure content-substance judgment (NW-1) with deterministic post-LLM handling for all location/provenance decisions (§4, §8, D-89-3, D-89-7).
- In-place YAML frontmatter on the source itself as the single source of truth for enrichment state (§3, D-89-5). This is the right filesystem-native choice and aligns with the producer contract's emphasis on artifact emission rather than direct mutation.
- The strict separation in §10: Pass-1 does not write GraphDB in v1. Compile remains the sole producer. This is the correct application of [[feedback_no_parallel_storage_to_authority]] and the manifest.json → GraphDB-context-loader lesson (JOURNEY.md).
- Deferral of the second-producer contract for enrichment data to v1.1+ (D-89-6, §10.3) under a concrete-first posture. The four-artifact taxonomy in §10.2 correctly mirrors the Producer Contract v1.0 structure without forcing premature GraphDB coupling.
- The all-CLI reviewer panel composition and the explicit repo-modification guardrail in §16 / the review prompt header. This is a clean methodological improvement over chat-heavy prior panels.

The blueprint is unusually clear on boundaries, replay mechanics, and re-enrichment merge behavior. The decision log (§12) and explicit OQ list (§13) are models of transparency.

## Findings

**F-1 — §6 Option C lean is sound but under-specifies the wikilink_suggestions schema shape**

The blueprint's narrow lean toward Option C (corpus_index + frontmatter-only wikilinks) is the right engineering trade-off for this vault. Body modification (Option A) introduces re-enrichment merge complexity and OneDrive sync conflict surfaces that are real operational risks given the documented sync-conflict handling in §5.1. Option B sacrifices too much of the "LLM-grounded discovery" value that helps justify the Pass-1 cost.

**Recommendation:** Adopt Option C (or C' below) for v0.2. The frontmatter-only approach keeps the source body pristine, simplifies the re-enrichment merge path (§3.3), and still delivers grounded suggestions to compile as a high-quality input (exactly the producer/adapter separation pattern in the Producer Contract v1.0).

**F-2 — §6 lacks a minimal viable wikilink_suggestions schema for Option C**

Option C describes the intent ("grounded_in_corpus", "occurrences_in_corpus") but does not define the exact YAML shape that will be emitted. This is material for the prompt template, schema validation, and replay archive.

**Recommendation:** Add a concrete example (even if provisional) of the `wikilink_suggestions` array shape in §6.4 before v0.2. This also gives NW-5 a stable target for the wikilink quality surface.

**F-3 — §4.4 "blacklist wins ties" is presented as a watch item but the rationale is defensive rather than principled**

The current default (force_noise wins over force_signal on overlap) is labeled defensive. This is reasonable, but the operational semantics (most-specific-glob wins? last-listed wins? explicit user intent always wins?) are not fully articulated for future users who will edit scope-config.yaml.

**Recommendation:** Promote OQ-89-3 to a D-89-x decision in v0.2 with a short decision table (overlap cases + chosen rule + audit-field impact). The current "defensive" framing is fine as a starting point but should be explicit.

**F-4 — §10.3 v1.1+ second-producer deferral is correct in direction but the future contract surface is underspecified**

The blueprint correctly defers GraphDB writes from Pass-1 until the enrichment shape is proven. However, when that second producer contract (`graphdb-kdb-enrichment-producer-contract.md`) is eventually written, it will need to define how the enriched frontmatter properties (especially the new ones from the round-1 survey) map to Source node properties vs. being treated purely as compile inputs.

**Recommendation:** In the v0.2 synthesis, add a one-paragraph "future second-producer surface" note in §10.3 that names the key tension (enrichment data as Source metadata vs. as compile-time context only) without pre-deciding it.

**F-5 — OQ-89-6 (multi-source re-enrichment batching) has a hidden corpus-snapshot consistency implication for Option C**

If Component #3 fires a batch of N sources in one run and Pass-1 processes them sequentially (the current lean), each source after the first will see its own freshly-written frontmatter in the corpus_index. This is desirable for grounding but creates a non-deterministic ordering dependency inside a single "run."

**Recommendation:** Document the chosen batching strategy (sequential vs. snapshot) as a D-89-x in v0.2 and reflect the chosen behavior in the run journal (§5.4) and replay sidecar so NW-5 and later audits can reproduce exact corpus_index state.

## Open questions

**OQ-1 — Cold-start strategy for corpus_index (gated on §6)**

When the first N sources are enriched under Option C, the corpus_index will be empty or extremely sparse. The blueprint leans toward (a) "run anyway, accept weak wikilinks, re-enrich later." This matches the #71 cold-start widening precedent, but it means early sources will carry low-quality `wikilink_suggestions` that later re-enrichment must clean up. Is there a simple "bootstrap batch" marker that compile can use to ignore or down-weight early wikilink suggestions?

**OQ-2 — Re-enrichment merge behavior when user has added their own YAML keys**

§3.3 describes preserving user-added keys. This is correct, but the exact merge precedence (Pass-1 values always win for schema keys? user keys never touched?) and conflict detection (user added a key that now collides with a new Pass-1 schema field) is not spelled out. This will matter once the round-1 survey properties land.

**OQ-3 — Whether the `override` block should be emitted even on non-overridden runs for audit consistency**

Currently the `override` block is absent unless an override actually fired. For downstream consumers (compile, NW-5 probes, human inspection) it may be cleaner to always emit the block with `applied: null` or a parallel `llm_verdict` field so the audit shape is stable.

**OQ-4 — Interaction between force_noise defaults and Daily Notes that contain substantive content**

The v0.1 default puts `Daily Notes/**` and `Projects/**` on force_noise. The LLM still runs and can emit `signal` (which is then overridden). This is good for audit, but it means every Daily Note that happens to contain a good investment thesis or technical insight will still burn a Pass-1 call. Is the cost of these "false positive LLM calls" acceptable, or should there be a cheap pre-filter before the LLM for the default force_noise paths?

## Wikilink + corpus_index decision (§6)

**Recommendation: Option C (frontmatter wikilinks + corpus_index), with one small refinement (C').**

**Reasoning:**

- Option A (body wikilinks) carries unacceptable merge and sync risk in a OneDrive-synced vault. The re-enrichment logic in §3.3 already has to be careful; appending a block that the user (or Obsidian plugins) might edit below creates a durable source of subtle corruption. The UX benefit (native Obsidian graph view) is real but secondary — Joseph's primary navigation is already through the compiled wiki output.
- Option B (no corpus, no wikilinks from Pass-1) gives up one of the clearest value propositions that justifies the marginal LLM cost of Pass-1. `key_entities` alone is useful but weak; grounded suggestions that compile can consume as high-quality input are a material differentiator.
- Option C preserves the grounding benefit while keeping the source body completely untouched. This is the cleanest separation: Pass-1 suggests (with evidence), compile disposes (via its existing entity/LINKS_TO machinery). It also aligns with the producer contract philosophy (emit artifacts; let the adapter/consumer decide what to do with them).

**Proposed C' refinement:** Add an explicit `wikilink_suggestions` array (as sketched in §6.4) with a required `grounded_in_corpus: boolean` field and an optional `occurrences_in_corpus` integer. This gives compile a clear signal for how much weight to give each suggestion and gives NW-5 a measurable surface. Cold-start (OQ-89-1) should use the "run anyway + re-enrich later" strategy (a) with an additional `corpus_maturity` field in the replay sidecar so later analysis can correlate suggestion quality with corpus size at the time of the call.

This is a narrow but material improvement over the current C lean.

## Concerns on post-LLM override (§4)

The mechanism itself (path-expression lists applied after the LLM, LLM never sees the lists) is correctly aligned with [[feedback_post_llm_deterministic_override]].

The main operational concern is the current "blacklist wins" tie-breaker (OQ-89-3). In a vault where users will actively maintain `scope-config.yaml`, an explicit documented rule (with examples of overlap) is necessary before v1. I would also like to see the override block always emitted (even when `applied: null`) for shape stability, as noted in OQ-3 above.

No fundamental misalignment with the feedback memory or with the producer contract (overrides are purely local filesystem decisions before anything reaches compile).

## Concerns on no-GraphDB-writes stance (§10)

Strong agreement. This is one of the cleanest applications of the hard lessons in JOURNEY.md (the manifest.json removal arc, D49/D50/D51) and [[feedback_no_parallel_storage_to_authority]].

Pass-1 is still a "feeder" in the new ingestion system language, not yet a full producer. Letting it emit only filesystem artifacts (enriched markdown + journal + sidecars) while compile remains the sole GraphDB writer in v1 is the right sequencing. The deferred v1.1+ second-producer path (§10.3) is the correct escape hatch once the enrichment shape has telemetry behind it.

The only mild concern is that the future enrichment producer contract will need to be very careful not to re-introduce the "parallel authority" problem the project just spent significant effort eliminating. The blueprint already flags this risk; I would simply like the v0.2 synthesis to make the "prove the shape on disk first" principle even more explicit as a standing constraint on that future contract.

No other material concerns. The stance is consistent with the Producer Contract v1.0 frozen boundary and with the overall "tunnel from both ends" discipline.