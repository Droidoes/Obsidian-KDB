# Additional Properties Survey — Deepseek

## Summary

I propose **4 additional properties** for the v0.1 locked schema, weighted 3 strong (★★) and 1 stretch (★). The locked set covers WHAT the content is about and WHERE it sits in the taxonomy; my proposals address the HOW dimension — difficulty, perishability, rhetorical intent, and evidence posture. Each is an LLM-unique judgment a regex or heuristic would get wrong, each has clear downstream reuse, and each adds minimal cognitive overhead since the LLM has already ingested the full source.

---

## Proposals

### difficulty

**Type:** enum: `beginner | intermediate | advanced`
**Required / Optional:** Required
**One-line purpose:** How technically or conceptually demanding the content is for a reader.
**Why the LLM is the right tool:** Difficulty is a holistic judgment about vocabulary density, assumed prior knowledge, abstraction level, and conceptual depth. A word-count or syllable-count heuristic (Flesch-Kincaid style) measures sentence complexity, not conceptual difficulty — a Jim Simons quant memo written in short sentences is still `advanced`. The LLM has read the full content and can assess the conceptual floor the author assumes.
**Downstream consumer:** Human Obsidian UX (filter vault by "what can I read tonight?" vs "what needs deep focus?"); compile-side context selection (Pass-2 could weight existing entities differently based on source difficulty); query layer ("show me beginner introductions to value investing").
**Cost concern:** Low. The LLM already processed the content for domain, summary, and key_entities. Classifying difficulty is a single-enum judgment riding on the same comprehension, not a separate analysis pass. No prompt-context inflation.
**Tier (your call):** ★★ (strong)

---

### freshness_type

**Type:** enum: `evergreen | time_sensitive | periodic`
**Required / Optional:** Required
**One-line purpose:** Whether the content's value is permanent, decays with time, or is tied to a recurring cycle.
**Why the LLM is the right tool:** Assessing perishability requires understanding what the content IS doing, not just what it's about. A market commentary from 2019 may be `time_sensitive` (aged out); an essay on market psychology from 2019 is `evergreen` (the framework persists). Both could classify as `value-investing`. The LLM can distinguish framework-content from event-content; a regex on dates in the filename cannot.
**Downstream consumer:** Query layer (exclude aged content from search results); Component #3 re-enrichment scheduling (periodic content like quarterly earnings analysis might benefit from re-enrichment when new data arrives); human navigation (filter vault by "evergreen only" for long-term knowledge building).
**Cost concern:** Low — single-enum judgment on already-comprehended content. The boundary between `time_sensitive` and `periodic` requires a definition in the prompt (periodic = recurring cycle like quarterly reports, annual letters; time_sensitive = one-shot event-bound like a specific market crash analysis), but that's a prompt-design question, not a cost concern.
**Tier (your call):** ★★ (strong)

---

### primary_purpose

**Type:** enum: `inform | persuade | analyze | narrate | instruct`
**Required / Optional:** Required
**One-line purpose:** The author's primary rhetorical intent — what the content is trying to DO.
**Why the LLM is the right tool:** Distinguishing rhetorical intent from source form is a LLM-strength task. A `letter` (source_type) could `persuade` (Buffett arguing for buybacks), `inform` (Buffett explaining insurance float), or `analyze` (Buffett dissecting a specific acquisition). A `blog` (source_type) could `narrate` (a personal investing journey), `instruct` (a how-to guide), or `analyze` (a sector deep-dive). The form tells you the container; the purpose tells you what's inside. Only the LLM can make this judgment.
**Downstream consumer:** Compile-side entity extraction (instructive content may yield more actionable entity types; narrative content more biographical); query layer ("show me analytical deep-dives on semiconductors"); human navigation (intent-based browsing of the enriched vault).
**Cost concern:** Low — single-enum judgment. The 5-value enum is small enough that the LLM won't spend tokens deliberating. The distinction from `source_type` must be clear in the prompt (form ≠ intent), but that's a prompt-design concern.
**Tier (your call):** ★★ (strong)

---

### evidence_stance

**Type:** enum: `data_driven | argument_driven | experience_driven | speculative`
**Required / Optional:** Optional
**One-line purpose:** How the content supports its claims — the epistemological posture of the source.
**Why the LLM is the right tool:** This is a genuine LLM judgment about the nature of the content's evidence base, not a surface-level feature. A `data_driven` piece cites statistics, studies, empirical results. An `argument_driven` piece builds a logical case from principles. An `experience_driven` piece draws from personal practice. `speculative` content explores possibilities without committing to evidence. Regex can count citation-like patterns but can't distinguish a real data citation from a passing mention of a number, or an argument that happens to contain numbers.
**Downstream consumer:** Pass-2 worth-verdict (D-88-8) — could weight `ontology_contribution` differently by evidence stance (argument-driven and data-driven may contribute more to the ontology than speculative or purely experiential). NW-5 benchmark (audit whether evidence_stance correlates with `kdb_signal` accuracy). Human navigation.
**Cost concern:** Medium — this is the most subjective of the four proposals and has the highest risk of inconsistent classification across sources. Marked optional to give the LLM permission to omit when unclear. If NW-5 telemetry shows poor inter-source consistency, drop from the required set without schema migration (optional fields are safe to deprecate).
**Tier (your call):** ★ (stretch)

---

## Considerations

**The locked property set emphasizes ABOUTNESS.** `domain`, `key_themes`, `key_entities`, and `summary` all answer "what is this content about?" `source_type` and `author` add identity metadata. `kdb_signal` adds the gate. What's absent is the **processing dimension**: how should a downstream consumer approach this content? Is it a quick skim or a deep read (`difficulty`)? Will it still be useful in a year (`freshness_type`)? Is the author building a case or telling a story (`primary_purpose`)? Adding even one or two of these properties would make the enriched source more navigable without inflating the call.

**Cross-component synergy worth flagging.** `freshness_type` has a natural downstream consumer that doesn't exist yet: Component #3 (Trigger) could use it to schedule re-enrichment. An `evergreen` source might never need re-enrichment for freshness reasons (only content-change). A `periodic` source (quarterly earnings analysis tagged with a specific quarter) might benefit from a scheduled re-check. A `time_sensitive` source could have its `kdb_signal` automatically downgraded after N months. None of this is v0.1 scope, but emitting the property now costs nothing and enables v1.1+ automation.

**Relationship between `primary_purpose` and `source_type`.** These are orthogonal but adjacent — the prompt must make the distinction clear. The cleanest framing: `source_type` = what form the content took when it was created (letter, podcast, blog); `primary_purpose` = what the author was trying to accomplish with that form (persuade, inform, analyze). A shareholder letter (form) that argues for a policy position (purpose = persuade) vs the same form explaining insurance operations (purpose = inform). This framing avoids the LLM conflating the two.

**Ordering recommendation if the synthesizer must pick.** If the synthesizer (Claude) can only fold 1-2 of these into v0.2, my priority order is: (1) `difficulty` — highest reuse, clearest LLM-uniqueness, lowest ambiguity; (2) `freshness_type` — unique downstream automation potential; (3) `primary_purpose` — strong but adjacent to source_type; (4) `evidence_stance` — valuable but highest ambiguity risk.
