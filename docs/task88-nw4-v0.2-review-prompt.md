# Task #88 NW-4 v0.2 — External Review Fire-Prompt

**Purpose:** Fire the v0.2 domain-canonicalization-list draft (`docs/task88-nw4-domain-list-v0.2.md`) at a 5-reviewer external panel for structural review of the **flat 24-domain controlled vocabulary** that Pass-1 enrichment LLM will classify against. This precedes Component #1 (Enrichment) deep-design, which depends on NW-4 content.

**Dispatched:** 2026-05-25 (to be fired by Joseph)
**Target panel:** Codex + Deepseek + Qwen + Gemini Pro Deep Research + Grok (5 reviewers)
**Response files (one per reviewer):**
- `docs/task88-nw4-v0.2-review-codex.md`
- `docs/task88-nw4-v0.2-review-deepseek.md`
- `docs/task88-nw4-v0.2-review-qwen.md`
- `docs/task88-nw4-v0.2-review-gemini.md`
- `docs/task88-nw4-v0.2-review-grok.md`

---

## ─── Prompt body ───

You are one of five reviewers consulted on **v0.2 of the NW-4 domain canonicalization list** for the Obsidian-KDB project. The list to review is at `docs/task88-nw4-domain-list-v0.2.md`. It is a **24-entry flat controlled vocabulary** that the Pass-1 enrichment LLM in the project's ingestion pipeline will classify every ingested source against.

This is a **substantive-content review** (does the list capture the user's empirical knowledge organization?) AND a **framework review** (are the upstream structural decisions defensible?). Both dimensions matter — please address each.

### Project context (brief)

**The system.** Obsidian-KDB compiles Joseph's raw markdown sources into a knowledge graph (Kuzu GraphDB). The pipeline has two ends: end A = compile pipeline (mature, frozen as Producer Contract v1.0); end B = ingestion pipeline (Task #88, being designed now — the pipeline that produces what end A consumes).

**Where NW-4 fits.** Pass-1 of the ingestion-side enrichment LLM emits a `domain` field on every ingested source. NW-4 is the controlled-vocabulary list of allowed `domain` values. Path 0 (a real-corpus fire 2026-05-23) found the `domain` field dormant in production — **root cause: KDB-Compiler-System-Prompt never instructs the LLM what `domain` values to pick from**. NW-4 fixes that by establishing a canonical, scope-explicit, config-driven list.

**Source inventory.** v0.2 was synthesized from 5 sources of Joseph's empirical organization: Alexandria book classification (~2,000 books read, 13-category controlled vocab); Obsidian vault top-level dirs (~19, present interests); OneNote-migrated content (~3 top-level dirs, past interests); X bookmarks (14 curated tags); Facebook collections (10 curated). Cross-source convergence was the primary signal weight.

**What the 24 list is for.** Pass-1 LLM gets the list (with scope descriptions) in its prompt; emits exactly one `domain` value per source; downstream consumers (Pass-2 in compile, GraphDB property indexing, query layer) read from a config file holding the same list. Adding a domain = editing the config; cost must stay low.

### Framework decisions to validate (D-NW4-1 / 2 / 3 / 4)

The 24-list rests on four upstream design decisions made in a 2026-05-25 deliberation. Reviewers should weigh in on each:

1. **D-NW4-1 — Flat list, no sub-domains.** Pass-1 picks one domain from ~24 entries. No `sub_domain` field. Finer-grained refinement lives in a separate `tags` field. *(Alternative considered: hierarchical domain+sub_domain mirroring Obsidian's empirical 2-level structure; rejected for D-88-10 single-call cognitive-load reasons.)*

2. **D-NW4-2 — AI/ML cross-cutting via graph edges only.** `ai-ml` is a technical/foundational domain. AI applied to other domains → primary domain is what the content fundamentally IS; cross-cutting captured via entity-overlap edges in the GraphDB at compile time. *(Alternatives considered: multi-domain field; explicit `connects_to: [domain]` field; rejected for schema simplicity + alignment with project's graph-over-vector philosophy.)*

3. **D-NW4-3 — Quotes is its own first-class domain.** Not a `content_type` field, not a `sub_domain`. Cross-section to substantive topics (Buffett quote → Value Investing) captured via graph edges. *(Alternatives considered: Shape Y two-axis with `content_type: quote`; tag-only; rejected because 3 of 5 sources organize quotes as first-class.)*

4. **D-NW4-4 — Domain list is config-driven and must scale cheaply.** Adding a domain = editing JSON; all downstream consumers read from it. Pass-2 ontology hooks must be per-domain optional config blocks, not domain-specific code branches.

### What to review

Read the full NW-4 v0.2 document end-to-end. Then stress-test along these axes:

1. **Flat vs hierarchical (D-NW4-1, OQ-NW4-1).** Does the flat structure honor Joseph's empirical 2-level Obsidian organization, or does it discard a load-bearing signal? Specifically: would the LLM benefit from a 2-step classify (broad → narrow), even at D-88-10 cognitive-load cost?

2. **Quotes-as-first-class-domain (D-NW4-3, OQ-NW4-2).** Defensible? Or should quotes be a separate axis (`content_type` field) or a tag? Concrete pressure test: where does a Charlie Munger speech essay (quote-rich but argumentative content) classify? Where does a quoted aphorism from Charlie Munger's *Poor Charlie's Almanack* (whose dominant nature is *the book*, but which is *content-wise* a quote) classify?

3. **AI/ML cross-cutting via graph only (D-NW4-2).** Is graph-edges-only sufficient, or does losing a metadata-level cross-cut signal harm queryability? Concrete pressure test: "show me all content where AI/ML is a load-bearing topic, even when not the primary domain" — can this query be answered cleanly via graph walks alone, or does the user need a metadata-level signal?

4. **The 24-domain list itself.** Walk the list. For each domain, ask:
   - Is the scope description tight enough to enable consistent Pass-1 classification?
   - Are there overlaps with adjacent domains that the boundary conventions (§4) don't resolve?
   - Are there entries that should merge with another?
   - Are there entries that should split into two?

5. **`science-technology` catch-all (#8, OQ-NW4-3).** Slippery slope risk. Does this give Pass-1 an easy escape that cannibalizes the more specific S&T domains (#1–7)? Is the guardrail in §4 sufficient, or does it need stronger enforcement (e.g., a Pass-1 instruction "only use `science-technology` when you can articulate why no other S&T domain fits")?

6. **`logics` as math+logic superset (OQ-NW4-4).** Joseph chose `logics` (plural) and treats math as a form of logic. Is this productive, or does it conflate fields that should be separate? Specifically: applied statistics (which is closer to economics-modeling) vs formal logic vs pure mathematics — are they really one domain?

7. **`spirituality` as religion superset (OQ-NW4-5).** Religion treated as a form of spirituality. Defensible, or does it lose distinctions important for classification (comparative theology vs personal meditation vs religious history)?

8. **Missing domains (OQ-NW4-6).** What's missing? Candidates to probe: Education, Sociology, Law, Environment / Sustainability, Sports, Crafts / Making, Language Learning, News / Current Events (vs Geopolitics), Cooking-as-skill (vs Food & Drinks). Apply the curation rule: a candidate needs evidence of cross-source organization OR enough empirical density in Joseph's content.

9. **Over-included domains (OQ-NW4-7).** Conversely, any of the 24 you'd drop or merge? `arts` and `food-drinks` are low-frequency; `science-technology` catch-all may be redundant; `others` is a residual that may be unnecessary if the list is exhaustive.

10. **S&T granularity (OQ-NW4-8).** The 8-domain S&T cluster is the largest. Is `software` + `hardware` the right cut (vs a unified `computing`)? Is `brain-consciousness` cleanly separable from `biology` + `psychology`, or is it really a sub-area of one of them and should fold? Is `physics` (which absorbs chemistry-at-fundamental-level) over-loaded?

11. **Boundary conventions completeness (OQ-NW4-9).** §4 lists 6 boundaries. Genuine confusion-risk boundaries missing? Specifically NOT including routine application-angle pairings (those are handled uniformly by D-NW4-2's "primary = what the content IS" rule).

12. **Naming conventions (OQ-NW4-10).** Any IDs that are confusing, ambiguous, or would benefit from rename? Flagged candidates: `logics` (plural unusual); `brain-consciousness` (compound — but content-faithful); `science-technology` (looks like cluster name); `health-wellbeing` (compound); `economy-markets` (compound).

13. **Empirical-density check (OQ-NW4-11).** Joseph has read 2,000+ books with categorical density skewed toward Investing-Finance, History, Science & Technology, Health & Wellbeing, Literature, Philosophy. Does the 24-domain distribution honor that historical content, or is it over-shaped for present-interest content (AI/ML, brain-consciousness)? A list optimized for the present interest distribution can mis-classify or under-classify the bulk of historical content.

14. **`quotes` cross-section fragility (OQ-NW4-12).** A quote's substantive connections depend on Pass-1 entity extraction. If "Buffett" isn't extracted from a Buffett quote, the cross-section to Value Investing is lost. Is this fragility acceptable, or does it justify a fallback metadata field (e.g., `mentioned_domains` or `topic_hints`)?

15. **Architecture-scalability (D-NW4-4).** v0.2 ships 24 domains; growth is expected. What downstream consumers / coupling points should be flagged now to keep "add a domain" cost low? Pass-2 ontology hooks per domain are flagged in v0.2; what else needs surfacing?

### Out of scope for this review

- **Pass-1 prompt wording itself** — that's Component #1 (Enrichment) deep-design; NW-4 only specifies the controlled vocabulary content.
- **Entity-extraction quality** — Pass-1 entity extraction is part of Component #1; not NW-4 scope.
- **Tag controlled vocabulary** — separate work item (NW-1 territory); NW-4 only specifies that tags exist as a complementary axis.
- **Re-litigating the strategic pivot** (compile-pause + ingestion-focus). Joseph-ratified 2026-05-23.
- **Re-litigating the D-88-* decisions** in the parent v0.2 blueprint (`task88-ingestion-pipeline-blueprint.md`). NW-4 inherits them; this review is scoped to NW-4 content.
- **Pass-2 ontology design** (compile-side). Out of NW-4 scope.

### Output format

Standard review format. Suggested structure:

1. **Convergence** — what holds together cleanly across the framework + list (don't dwell; just note)
2. **Findings** — concrete issues, ambiguities, contradictions, missed considerations. Prefix substantive findings as `**Finding F-N:**` and minor / nice-to-have observations as `**Observation O-N:**`.
3. **Recommendations** — proposed amendments to specific decisions / scopes / boundary conventions / list entries. Prefix as `**Recommendation:**` or `**Proposal:**`.
4. **Concrete classification probes** — give 3–5 concrete content examples (titles or descriptions) and propose how each should classify under v0.2. Flag any that the list can't classify cleanly.
5. **Open questions** — additional questions raised but not resolvable in review.

**Length:** under 2500 words. Cite specific section anchors (e.g., "§3.1", "D-NW4-3", "OQ-NW4-7") where possible. Quote the v0.2 doc with `> …` blockquotes where raising an issue with specific wording.

### The artifact to review

Attached: `docs/task88-nw4-domain-list-v0.2.md` (full file).

For project context, reference as needed:
- `docs/task88-ingestion-pipeline-blueprint.md` v0.2 — the parent blueprint NW-4 plugs into
- `docs/graphdb-kdb-producer-contract.md` v1.0 — end A's input contract (NW-4 ultimately feeds this via Pass-1 → enriched source → compile)
- `docs/CODEBASE_OVERVIEW.md` — current architectural state + Milestone Changelog
- `docs/external-review-panel.md` — reviewer panel composition + flow context
