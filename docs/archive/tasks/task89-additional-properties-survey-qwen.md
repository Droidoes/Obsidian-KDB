# Additional Properties Survey — Qwen CLI (qwen3.7-max)

## Summary

I propose **3 additional properties** that fill a structural gap in the locked v0.1 set: the locked properties cover **what** the source contains (entities, themes, summary) and **where** it classifies (domain, source_type), but leave the **rhetorical dimension** — how the source makes its case and on what epistemic grounds — entirely to downstream inference. All three proposals target LLM-only semantic work that no heuristic, regex, or compile-side logic can replicate, and all three are categorical (enum-typed) to match the project's established pattern of LLM-emits-enum → system-maps-float (see D-83/84-8 confidence representation precedent). I deliberately stop at 3 — the single-call attention budget is real, and the v0.1 locked set already demands significant LLM cognitive load across 7 substantive + 6 audit fields.

## Proposals

### argument_stance

**Type:** enum — `argues | explains | reports | surveys | narrates`
**Required / Optional:** Required
**One-line purpose:** The rhetorical mode of the source — what the source is *doing* with its content.
**Why the LLM is the right tool:** Rhetorical mode is a holistic semantic judgment. No regex or heuristic can distinguish "this source argues that X is true" from "this source explains how X works" from "this source surveys the landscape of X." Keyword-density heuristics (e.g., counting "therefore" vs "here is") are brittle across genres and writing styles. The LLM naturally apprehends rhetorical purpose as part of reading for `summary` and `kdb_signal`.
**Downstream consumer:**
- **Pass-2** — an `argues` source's central claim needs strength evaluation; a `reports` source's factual assertions need verification framing; a `surveys` source contributes landscape mapping rather than individual claims. Pass-2's ontology-contribution judgment (D-88-8) benefits from knowing the rhetorical mode before evaluating contribution.
- **Query layer** — enables "show me all sources that *argue* for X" vs "show me sources that *explain* X" vs "show me factual reports on X." This is a distinct filter axis from `domain` (topic) and `source_type` (format).
- **Human Obsidian UX** — browsing a source list, knowing whether a piece is an argument or a factual report is an immediate orientation signal. Obsidian's Dataview can filter/sort on this enum natively.
**Cost concern:** Low. Rhetorical-mode judgment is a natural by-product of the reading the LLM already performs for `summary` and `kdb_signal`. Emitting one enum tag is negligible prompt-budget overhead. Five values keep the classification task crisp.
**Tier (your call):** ★★★ (must)

**Additional note:** `argument_stance` is orthogonal to both `source_type` and `domain`. A `letter` can `argue` (Buffett shareholder letter) or `report` (regulatory filing). A `paper` can `argue` (position paper) or `survey` (literature review). A `blog` post in `value-investing` can `argue` (buy thesis) or `explain` (how DCF works). No existing property captures this dimension.

**Enum value rationale:**
- `argues` — takes a position, advances claims (combines for/against; direction is content-specific, not a classification axis)
- `explains` — teaches, clarifies concepts, describes mechanisms without advocating a position
- `reports` — presents facts, events, data without interpretive framing or position-taking
- `surveys` — covers a landscape, reviews multiple positions, maps a field
- `narrates` — tells a story, biographical or historical, with narrative arc

---

### epistemic_basis

**Type:** enum — `empirical | theoretical | experiential | authoritative | mixed | opinion`
**Required / Optional:** Required
**One-line purpose:** The type of evidence or reasoning that primarily grounds the source's claims.
**Why the LLM is the right tool:** Evidence-type classification requires reading comprehension — understanding whether claims rest on cited data (`empirical`), logical derivation (`theoretical`), personal experience (`experiential`), expert authority (`authoritative`), a combination (`mixed`), or personal judgment without structured evidence (`opinion`). No heuristic can reliably make this distinction. A word-count approach (looking for "study," "data," "experiment") fails on sources that reference data rhetorically without actually being empirical, and succeeds poorly on experiential sources that use precise language about subjective experience.
**Downstream consumer:**
- **Pass-2** — Pass-2's ontology-contribution judgment (D-88-8) benefits from knowing the evidence basis. An `empirical` source's claims carry different ontological weight than an `opinion` source's claims. This is particularly relevant for the belief-revision pipeline (#83/#84): a new `empirical` claim contradicting an existing `opinion`-grounded claim has asymmetric revision weight.
- **Query layer** — "show me empirical sources on X" vs "show me opinion pieces on X" is a high-value filter for knowledge work.
- **Human Obsidian UX** — evidence-basis is a reliability cue for browsing. When scanning a domain's source list, knowing which pieces are data-grounded vs opinion-grounded accelerates triage.
**Cost concern:** Low-to-moderate. Evidence-type judgment is a natural extension of the reading required for `kdb_signal` and `summary`, but it does ask the LLM to reason about the *basis* of claims rather than just their *content*. This is a slightly deeper semantic layer. Six values are manageable. Empirical risk: sources that mix evidence types may see inconsistent classification — the `mixed` value absorbs this, and inter-rater reliability should be measured in NW-5.
**Tier (your call):** ★★ (strong)

**Relationship to `confidence`:** These are orthogonal dimensions. `confidence` is the LLM's self-assessed certainty about its `kdb_signal` judgment (meta-cognitive). `epistemic_basis` is the source's own evidentiary grounding (object-level). The LLM can be highly confident that a source is signal while classifying it as `opinion` (a well-reasoned opinion piece by a domain expert). Or the LLM can have low confidence about a source whose evidence basis is `mixed` and hard to categorize. Conflating these would be a design error.

**Alignment with project pattern:** Matches the established LLM-emits-enum → system-maps-value pattern (D-83/84-8 confidence representation). If Pass-2 needs a numeric evidence-weight score, the system maps `empirical → 0.9`, `theoretical → 0.7`, `experiential → 0.6`, `authoritative → 0.6`, `mixed → 0.7`, `opinion → 0.4` (configurable). The LLM does not emit floats for evidence strength directly.

---

### audience_level

**Type:** enum — `expert | practitioner | general | introductory`
**Required / Optional:** Optional
**One-line purpose:** The expertise level the source is written for.
**Why the LLM is the right tool:** Audience targeting is a holistic judgment involving domain-specific terminology density, assumed background knowledge, conceptual sophistication, and explanatory depth. Flesch-Kincaid and similar readability metrics measure sentence/word complexity — which is not the same as audience level. A source written in simple English can still target experts (e.g., a memo by Munger using plain language but assuming deep investing knowledge). Conversely, a verbose popular science article may score "difficult" on readability metrics while targeting a general audience.
**Downstream consumer:**
- **Pass-2** — `introductory` sources may contribute fewer novel claims to the ontology; `expert` sources may carry more weight for technical domains.
- **Query layer** — "show me expert-level sources on ai-ml" vs "show me introductory material on ai-ml" is high-value for knowledge navigation.
- **Human Obsidian UX** — expertise level aids browsing decisions. "Do I want to read this now?" often depends on whether you have the background for it.
**Cost concern:** Low. Audience-level is a holistic judgment that emerges from the same reading the LLM does for all other properties. Making it optional provides a safety valve: if attention-dilution concerns materialize in NW-5 testing, it can be dropped without schema breakage. Four values keep the classification task crisp.
**Tier (your call):** ★ (stretch)

**Why optional:** This property's downstream value depends on corpus composition. If the vault is predominantly one audience level (likely `general` or `practitioner` for a personal knowledge base), the property has low discriminative value. NW-5 should measure value-of-information before promoting to required.

---

## Considerations

### 1. The rhetorical gap

The locked v0.1 set has a structural asymmetry. It answers **what** (summary, key_entities, key_themes), **where** (domain, source_type), **who** (author), and **how certain** (confidence, uncertainty_reason). But it does not answer **how the source makes its case** (rhetorical mode) or **on what grounds** (epistemic basis). These are the dimensions where the LLM's semantic understanding most exceeds what heuristic alternatives can achieve. The three proposals above target this gap specifically.

### 2. Reader-profile sub-structure

The three proposals together form a coherent "reader profile" describing how a source communicates:
- `argument_stance` — how it argues (rhetorical mode)
- `epistemic_basis` — what it grounds claims in (evidence type)
- `audience_level` — who it addresses (expertise target)

These are orthogonal to each other and to the locked set. A source can be `argues` + `empirical` + `expert` (a research paper advancing a data-backed thesis) or `explains` + `theoretical` + `introductory` (a textbook chapter). No pair of these collapses into redundancy. If v0.2 adopts all three, they could be grouped under a `reader_profile` conceptual heading in documentation (not in schema — flat frontmatter keys are simpler per Obsidian Dataview compatibility).

### 3. Deliberate exclusions

I considered and rejected several candidates:

**`key_claims`** (list of 1-3 central propositions) — Tempting. Extracting central claims is a classic LLM task. But a well-written `summary` already captures the central thesis, and `key_themes` captures the topical scope. Adding explicit claim extraction creates a third prose-emission surface in the same call, which risks the split-trigger quality concern from D-88-10. More importantly, Pass-2's ontology-contribution analysis (D-88-8) already performs claim-level evaluation with richer graph context — Pass-1 claims would either duplicate Pass-2's work or create a weaker parallel. **Recommendation: defer to Pass-2 where graph context makes claim extraction higher quality.**

**`temporal_anchor`** (timeless / time-bound / period-specific) — The v0.1 brainstorm already dropped `time_period` as ★ tier. My proposed `temporal_anchor` is related but distinct (character rather than date). However, explicit dates can be extracted deterministically by the post-LLM layer (regex on publication metadata), and "timeless vs time-bound" is a judgment that overlaps with `summary` and `key_themes` content. The marginal information over what the locked set already conveys is thin. **Recommendation: defer; revisit if NW-5 testing reveals temporal-classification gaps.**

**`sentiment`** (positive / negative / neutral) — Too simplistic for the corpus. Most substantive KDB sources are analytical, not emotive. And sentiment doesn't distinguish "this source argues X is good" from "this source argues X is well-understood." **Recommendation: reject — not load-bearing for this corpus.**

**`novelty`** (novel / incremental / standard) — Interesting but extremely subjective. Cross-model reliability would be poor; even the same model on the same source might vary run-to-run. NW-5 would struggle to define ground truth. **Recommendation: reject — too low reliability for schema-gated property.**

**`controversy_potential`** (contested / mainstream / settled) — Overlaps with `argument_stance: argues` plus `epistemic_basis: opinion`. A contested source is usually one that argues a minority position on experiential or theoretical grounds. The compound of my two required proposals captures this information without adding a third dimension. **Recommendation: reject — derivable from `argument_stance` + `epistemic_basis` composition.**

### 4. Enum-typed throughout — matching project pattern

All three proposals are enum-typed. This aligns with the project's established LLM-emits-categorical pattern (D-83/84-8 confidence bucketing, D-NW4-4 domain config, NW-7 source_type placeholder). The LLM is reliably good at picking from a short list; it is unreliable at producing calibrated floats. Any downstream need for numeric scoring (e.g., evidence-weight for Pass-2's belief-revision pipeline) should use system-mapped values — configurable, tunable post-hoc, and not subject to LLM calibration drift.

### 5. Attention-dilution hedge

The locked v0.1 set already demands 7 substantive extractions + 6 audit fields from a single LLM call. Adding 2 required + 1 optional property brings the total to 9 substantive + 6 audit + 1 optional = 16 fields. This is within modern LLM capability for structured output, but NW-5 should explicitly test for **cross-property quality degradation**: compare locked-property quality (especially `summary` coherence and `key_entities` recall) with vs without the additional properties in the prompt. If degradation is measurable, `audience_level` (the ★-tier optional property) is the first to drop.

### 6. `confidence` representation note

The locked v0.1 schema specifies `confidence: 0.0-1.0` (float). The project's established pattern from D-83/84-8 uses bucketed enums (low | medium | high) with system-mapped floats. If v0.2 reconciles this tension by moving `confidence` to a bucketed enum, my three proposals are already aligned — they are enum-typed and need no reconciliation. If `confidence` stays as a raw float, the contrast with the enum-typed proposals is architecturally inconsistent but operationally harmless. Flagging for v0.2 synthesis awareness.

**END OF SURVEY RESPONSE**
