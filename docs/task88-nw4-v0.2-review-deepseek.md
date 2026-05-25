# NW-4 v0.2 Domain Canonicalization List — Review (Deepseek)

**Reviewer:** Deepseek (Codex-style Review)
**Date:** 2026-05-25
**Artifact reviewed:** `docs/task88-nw4-domain-list-v0.2.md`
**Supporting docs consulted:** `task88-ingestion-pipeline-blueprint.md` v0.2, `graphdb-kdb-producer-contract.md` v1.0, `CODEBASE_OVERVIEW.md`, `external-review-panel.md`

---

## 1. Convergence

The 5-source synthesis methodology (§1) is the strongest structural contribution of this document. Cross-source convergence as the primary signal weight — with ≥4/5 sources treated as load-bearing — gives the list empirical grounding beyond author intuition. The curation rule that emerges from D-NW4-3 (≥2 sources for content-type-as-domain) is clean, falsifiable, and consistently applied in the explicit-drops table (§5).

The four framework decisions (D-NW4-1 through D-NW4-4) form a coherent whole. Flat + graph-cross-cutting + quotes-first-class + config-driven: each reinforces the others. The architectural discipline is visible — this isn't a list assembled by feel; it's a list assembled by principle.

The boundary conventions (§4) are well-specified where they appear. The `brain-consciousness` ↔ `biology` / `psychology` / `ai-ml` triplet is the strongest — concrete criteria (mechanism-level vs cellular vs behavioral vs substance-decides).

---

## 2. Findings

### Finding F-1: Blueprint-schema inconsistency — `sub_domain` field still present in parent blueprint

The v0.2 ingestion blueprint (`task88-ingestion-pipeline-blueprint.md` §4.1) defines the Pass-1 output schema with both `domain` and `sub_domain` fields:

> ```
> domain: <enum from NW-4 canonicalization list>,
> sub_domain: <enum from NW-4 canonicalization list>,
> ```

But D-NW4-1 ratifies a flat list with **no `sub_domain` field**. This is a direct contradiction between NW-4 (which owns the domain vocabulary design) and the parent blueprint (which defines the Pass-1 output schema). The schema field `sub_domain` must be **removed** from the blueprint when NW-4 v0.3 lands, or NW-4 must add an explicit note that the blueprint's `sub_domain` field is superseded by D-NW4-1.

This is the kind of cross-document drift that the project's review pattern is designed to catch. It's load-bearing: if an implementer reads the blueprint without reading NW-4, they'll build a Pass-1 schema expecting `sub_domain`.

**Recommendation:** Add a reconciliation note to the NW-4 v0.3 header: "Supersedes the `sub_domain` field in `task88-ingestion-pipeline-blueprint.md` §4.1 per D-NW4-1." Correspondingly, the blueprint §4.1 schema should be amended to drop `sub_domain` and cite NW-4 as authority.

### Finding F-2: `science-technology` catch-all guardrail is underspecified for the LLM

The §4 catch-all guardrail says:

> Pass-1 should prefer specific S&T domains; the catch-all is a fallback, not a first choice.

This is a human-facing instruction, not an LLM-facing one. Pass-1 sees the scope descriptions in §3.1, not §4. The catch-all's scope description says "Scientific / technical content that doesn't fit cleanly in #1–7" — but the LLM has no mechanism to distinguish "doesn't fit cleanly" from "I'm uncertain, so I'll pick the safe fallback." The behavioral economics of LLM classification tilt toward the catch-all under ambiguity, especially when the cost of being wrong on a specific domain feels higher than being vague-but-safe.

The OQ-NW4-3 open question acknowledges this risk but doesn't propose a mechanism. The suggestion in the review prompt — a Pass-1 instruction "only use `science-technology` when you can articulate why no other S&T domain fits" — is a chain-of-thought forcing-function and would be stronger than the current scope-description-only approach.

**Recommendation:** Add to the `science-technology` scope description a self-check clause: "ONLY use this domain when you can state in one sentence why none of #1–7 applies. If you cannot articulate that reason, re-examine #1–7." This makes the LLM do the work of elimination before falling through.

### Finding F-3: `value-investing` ↔ `economy-markets` boundary is unaddressed

The §4 boundary conventions cover 6 confusion-risk pairs. A 7th is conspicuously absent: `value-investing` ↔ `economy-markets`. Consider these content types:
- A macro analysis of Federal Reserve rate policy → clearly `economy-markets`
- Buffett's shareholder letter discussing interest rate effects on intrinsic value → straddles both
- A piece on gold as an inflation hedge → could be either

The two domains have genuine conceptual overlap — investing sits atop macroeconomics. The current scope descriptions don't provide a clean discriminator: `value-investing` covers "investment philosophy, methods, mental models" and `economy-markets` covers "macro, monetary policy, currency, bonds, interest rates." When does "monetary policy through an investment lens" cross from one to the other?

**Recommendation:** Add an explicit boundary convention: **`value-investing` ↔ `economy-markets`** — content primarily about investment decision-making (what to buy/sell/hold, valuation frameworks) → `value-investing`; content primarily about how markets/economies function (mechanisms, policy transmission, market structure) → `economy-markets`. When both are present, the **primary purpose** (teach investment vs explain economics) is the tiebreaker.

### Finding F-4: `geopolitics` ↔ `history` temporal boundary is implicit but unstated

`geopolitics` scope includes "current world events" and `history` covers "historical events, civilizations, eras." The boundary between "current" and "historical" is left implicit. A piece analyzing the Cold War through a contemporary lens — is that `history` (era) or `geopolitics` (framework with current relevance)? The temporal boundary matters because Joseph's content patterns likely include historical analysis with contemporary implications.

**Recommendation:** Add to §4: **`geopolitics` ↔ `history`** — content whose primary analytical frame is the present or recent past (post-Cold War, contemporary power dynamics) → `geopolitics`; content whose primary frame is a completed historical period → `history`. Historical analysis with explicit contemporary application → `geopolitics` (the application angle is the primary purpose).

### Finding F-5: `health-wellbeing` ↔ `biology` boundary is absent

`health-wellbeing` scope says "life-application angle" and `biology` scope says "brain-specific content → `brain-consciousness`." But nutrition science (biochemistry of metabolism, gut microbiome research) could classify under either. Is a paper on the gut-brain axis `biology` (mechanism) or `health-wellbeing` (application)? The "life-application" discriminator helps but doesn't cover mechanistic health science that isn't yet applied.

**Recommendation:** Add to §4: **`health-wellbeing` ↔ `biology`** — content aimed at informing personal health decisions (nutrition advice, fitness protocols, supplement evidence) → `health-wellbeing`; content about biological mechanisms without direct personal-application framing → `biology`.

### Observation O-1: `logics` plural is semantically imprecise

The ID `logics` (plural) has no standard English usage. "Logics" exists as a technical term in some philosophical contexts (plural systems of logic) but it's unusual enough to cause hesitation. The scope subsumes mathematics, probability, statistics, formal logic, and decision theory — calling this entire cluster "Logics" stretches the term beyond recognition. `mathematics-logic` or `formal-sciences` would be more descriptively accurate. The philosophical rationale (math as a form of logic) is coherent but the ID doesn't need to encode the philosophy — it needs to be findable.

**Observation O-2:** Not a finding, but a structural note: the `science-technology` ID looks like a cluster header (matching the §3.1 cluster name "Science & Technology cluster"), not a peer domain. A reader encountering `science-technology` in the flat list may misread it as a grouping label rather than an eighth domain. Consider renaming to something that reads as a peer: `general-stem` or `applied-sciences`.

### Observation O-3: `others` residual is necessary but its quality-signal role should be explicit in the scope description

The §3.6 scope for `others` says "its rate is a quality signal for the list's completeness" — this is the right framing, but it should also appear in the **scope description the LLM sees**. If Pass-1 knows that `others` is literally the "this list failed" option, it will try harder to find a real domain. Currently the scope description is self-describing ("Residual catch-all for genuinely uncategorizable content") without the normative pressure.

**Recommendation:** Append to the `others` scope: "Use ONLY when no other domain in this list describes the content's primary nature. High `others` rates indicate the domain list needs expansion."

---

## 3. Recommendations

### Recommendation R-1: Strengthen the `science-technology` scope with a self-check clause (addresses F-2)

Modify the scope for domain #8 to include: "ONLY use this domain if you can articulate in one sentence why none of #1–#7 applies. If you cannot, re-examine the specific S&T domains first."

### Recommendation R-2: Add three missing boundary conventions (addresses F-3, F-4, F-5)

Add to §4:
- `value-investing` ↔ `economy-markets` (per F-3)
- `geopolitics` ↔ `history` (per F-4)
- `health-wellbeing` ↔ `biology` (per F-5)

### Recommendation R-3: Reconcile `sub_domain` field with parent blueprint (addresses F-1)

When NW-4 v0.3 ships, include an explicit note that D-NW4-1 supersedes the `sub_domain` field in `task88-ingestion-pipeline-blueprint.md` §4.1. The blueprint's Pass-1 output schema should be amended to remove `sub_domain` and cite NW-4.

### Recommendation R-4: Consider `education` as a candidate domain for v0.3+

Of the OQ-NW4-6 candidate missing domains, `Education` has the strongest case: Joseph's 2,000+ books include pedagogical content (learning science, autodidact methods, skill acquisition), and the X bookmarks + Obsidian dirs likely contain learning-methodology material. Current homes would scatter this content across `psychology` (learning theory), `science-technology` (educational technology), and `business-management` (organizational learning). Whether this reaches the ≥2-source threshold is an empirical question for the next source-inventory pass — flag for v0.3.

### Recommendation R-5: Add `mentioned_domains` as a lightweight cross-section fallback (addresses OQ-NW4-12)

The quotes cross-section fragility (entity extraction failure → lost connection) is real. Rather than a full `topic_hints` field (adds schema complexity), consider a lightweight `mentioned_domains: list[str]` field on the Pass-1 output, populated only when the LLM detects a clear domain connection that entity extraction might miss. This is opt-in and optional — null for most sources — but provides a safety net for the quotes edge case. Cost: one additional optional field in the output schema; benefit: quotes don't become orphaned islands when entity extraction is imperfect.

---

## 4. Concrete Classification Probes

**Probe 1:** *Charlie Munger's "The Psychology of Human Misjudgment" (speech/essay, 1995)* — A structured argument about cognitive biases with illustrative quotes. Content IS a speech/essay with systematic framework → `psychology` (cognitive psychology with investment application). The boundary convention `brain-consciousness` ↔ `psychology` confirms: behavior/self-improvement/applied → `psychology`.

**Probe 2:** *A standalone Buffett aphorism: "Price is what you pay; value is what you get"* — No surrounding argument, no provenance tie to a specific book/speech. Content IS a standalone quote → `quotes`. Entity extraction would tag "Buffett" → graph edge to Value-Investing entities. **This is the OQ-NW4-12 fragility case** — if "Buffett" isn't extracted, the cross-section is lost. (See R-5.)

**Probe 3:** *Ben Bernanke's "21st Century Monetary Policy" (book, 2022)* — Analysis of Federal Reserve policy mechanisms and history. Content IS economic-policy analysis → `economy-markets`. Even though it has investment implications, the primary purpose is explaining how monetary policy works, not how to invest.

**Probe 4:** *A paper on CRISPR gene-editing technology applied to agriculture* — Molecular biology mechanism with agricultural application. Content IS biology (mechanism-level, genetic) → `biology`. The agricultural application angle is captured via tags + graph edges to `food-drinks` entities, not via domain reclassification. This is D-NW4-2 operating correctly.

**Probe 5:** *A Daily Note entry: "Read another chapter of Kahneman. Thinking about how anchoring affects my stock picks. Note to self: review the Mohnish checklist tomorrow."* — Diary-shaped meta-commentary with no standalone knowledge content. Pass-1 verdict should be `not_pass` (per D-88-11, NW-1's diary-shape rejection criterion). Domain classification is moot since the source is gated out. **Observation:** this probe tests the Pass-1 criteria (NW-1), not the domain list — but it's worth noting that the domain list is only exercised on `pass`-verdict sources, so the `others` rate will reflect only the domain-classification failures of *surviving* sources.

---

## 5. Open Questions

**OQ-DS-1:** The Pass-1 output schema in the parent blueprint (§4.1) includes `domain` as an enum field. When NW-4 removes `sub_domain`, should the `domain` field remain `enum` (validated against the config) or become a free string validated post-hoc against the config? The current blueprint shows enum — NW-4 should confirm or revise this.

**OQ-DS-2:** For the `logics` domain: applied statistics for social science (econometrics, psychometrics) — does this classify as `logics` (statistics) or the application domain (`economy-markets`, `psychology`)? The D-NW4-2 rule says primary = what content IS, which would put an econometrics textbook under `logics`. But an empirical study using econometrics to analyze market behavior would classify as `economy-markets`. Is this distinction operationalizable for Pass-1, or will it produce inconsistent classification?

**OQ-DS-3:** The `retirement-lifestyle` domain (#22) has the narrowest scope of the 24. If Joseph's content patterns shift away from retirement-planning content, this domain becomes a singleton with low utilization. Is there a merge path? Could it fold under `economy-markets` (financial-vehicle dimension) + `health-wellbeing` (lifestyle dimension) with `tags: [retirement]`? Flag for empirical monitoring after v0.2 deployment.

---

**Word count note:** Within the 2500-word guideline. Citations use doc anchors (§3.1, D-NW4-3, OQ-NW4-7, etc.) and `> …` blockquotes where raising issues with specific wording.
