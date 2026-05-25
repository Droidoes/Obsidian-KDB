# Task #88 NW-4 — Domain Canonicalization List v0.2

**Status:** v0.2 draft (Joseph-ratified 2026-05-25) — ready for external panel review
**Parent:** Task #88 (Ingestion System) blueprint v0.2; NW-4 was filed as a parallel-session work item during v0.2 synthesis (per session-handoff 2026-05-25)
**Purpose:** Settle the canonical `domain` controlled-vocabulary that the Pass-1 enrichment LLM classifies every ingested source against. Feeds Component #1 (Enrichment) deep-design as input. Operationalizes the #76 redemption arc (Path 0 found `domain` field dormant in production due to prompt under-instruction — root cause not a missing list, but the absence of one being load-bearing for the prompt).

**Author:** Joseph + Claude (Coding Alter Ego)
**Date:** 2026-05-25
**Predecessor:** none (this is the first NW-4 artifact)

---

## 1. Source inventory (5 sources)

NW-4 was scoped from five sources of Joseph's empirical content organization. Amazon book categories were considered and **explicitly dropped** (commercial taxonomy includes leisure-fiction categories Joseph won't accumulate KDB knowledge along).

| # | Source | Type | What it tells us |
|---|---|---|---|
| 1 | **Alexandria** book classification (2K+ books read) | Controlled vocab (13 cats) | Foundational empirical density — what Joseph has *actually read* over years |
| 2 | **Obsidian vault dir/sub-dir (present)** | ~19 top-level dirs, 2-level | Present interests; how Joseph organizes today |
| 3 | **OneNote-migrated** (`~/Obsidian/OneNote/`) | 3 top-level dirs, multi-level | Past interests (Financial / Games / Knowledge Base) |
| 4 | **X bookmarks** (Joseph's curated tags) | 14 tags | Curated topical taxonomy from active reading |
| 5 | **Facebook collections** (Joseph's collections) | 10 collections | Additional curated topical taxonomy |

### Cross-source convergence highlights

Domains where ≥4 of 5 sources independently vote yes are considered architecturally load-bearing:
- Value-Investing / Investing-Finance
- Science & Technology (multiple sub-areas)
- AI / ML (4/5 — Alexandria had it sub-S&T because it predates the LLM era)
- Biology (5/5)
- Health & Wellbeing (5/5)
- History (5/5)
- Geopolitics / NWO (4/5)

---

## 2. Settled framework (Q1 / Q2 / Q3 design discussion 2026-05-25)

Three foundational decisions were ratified before drafting any list, in deliberation:

### D-NW4-1 — Flat domain list, no sub-domains (Q1)

Pass-1 LLM classifies each source into exactly **one** domain from a flat ~20-25-entry list. No `sub_domain` field.

**Reasoning:** Simpler classifier output (one field, one decision); aligns with D-88-10's single-call quality monitor; eliminates the "is this a refinement or a content-type?" debate at maintenance time. Tags handle finer-grained refinement and cross-cutting signals.

**Trade-off accepted:** Discards the 2-level structure that Joseph's Obsidian present dirs + OneNote past dirs empirically follow. Mitigated by tags carrying the within-domain refinement.

### D-NW4-2 — AI/ML cross-cutting handled via graph edges (Q2)

`ai-ml` is a *technical/foundational* domain only. When AI/ML intersects another domain (AI applied to investing, AI for biology, AI in history research), the **primary domain is what the content fundamentally IS**; the AI/ML connection is realized as graph edges at compile time (entity overlap between AI/ML entities and the other domain's entities).

**Reasoning:** Aligns with `feedback_graph_over_vector_for_kdb` (connections live in the graph, not duplicated in metadata). Pass-1 stays single-choice. Cross-cutting AI signal can also be tagged for tag-based queries.

**Generalization:** This same rule applies to all cross-cutting concerns (not just AI/ML). Primary domain = what the content IS; cross-sections = graph layer.

### D-NW4-3 — Quotes is its own first-class domain (Q3)

Quotes is treated as a domain in the flat list (not as a `content_type` field, not as a `sub_domain`). Cross-section to substantive topics (e.g., a Buffett quote → Value-Investing) handled via graph edges to extracted entities — symmetric with D-NW4-2.

**Reasoning:** Three of the 5 sources independently treat quotes as a first-class kind (Obsidian top-dir; X bookmarks tag; Facebook collection). The empirical pattern + the structural symmetry with D-NW4-2 → first-class domain.

**Curation rule that falls out:** A content-type becomes a domain only when ≥2 sources organize it that way. Otherwise it lives under subject domain + `tags`. Applied: `biography` and `howto` are tags, not domains.

### D-NW4-4 — Architecture must scale with adding domains (Joseph's caveat, Q1)

The domain list is **config-driven**, not hardcoded. Adding a domain = editing a JSON config file; all downstream consumers (Pass-1 prompt rendering, Pass-1 output schema, GraphDB queries) read from it. Pass-2 ontology hooks should be per-domain optional config blocks, not domain-specific code branches.

**Reasoning:** v0.2 ships 24 domains; v0.3+ may grow as Joseph's interests evolve. The cost of adding a domain must stay low.

---

## 3. The list — 24 domains

Cluster groupings are for human readability only. The Pass-1 LLM sees the flat list with descriptions.

### 3.1 Science & Technology cluster (8)

| # | ID | Display | Scope |
|---|---|---|---|
| 1 | `ai-ml` | AI & Machine Learning | LLMs, prompt engineering, RAG, models, MLOps, AI tools (Claude, Ollama, etc.). **Technical/foundational only** — applications to other domains via graph edges. |
| 2 | `software` | Software | Programming languages, CS algorithms, OS / Linux / WSL, Git, dev tools, cloud infrastructure, software architecture. |
| 3 | `hardware` | Hardware | Computer architecture, chips, semiconductors as engineering, electronics, devices. |
| 4 | `logics` | Logics | Mathematics, probability, statistics, formal logic, decision theory. Math is treated as a form of logic. |
| 5 | `biology` | Biology | Life sciences, genetics, cellular biology, evolution, organisms. Brain-specific content → `brain-consciousness`. |
| 6 | `physics` | Physics | Physical sciences, astronomy, cosmology, chemistry-at-fundamental-level, materials physics. |
| 7 | `brain-consciousness` | Brain Science & Consciousness | Neuroscience, cognitive science, consciousness studies, philosophy of mind. Growing intersection with LLMs handled via graph edges to `ai-ml`. |
| 8 | `science-technology` | Science & Technology (catch-all) | Scientific / technical content that doesn't fit cleanly in #1–7 (e.g., chemistry-as-applied, materials science, climate science, engineering disciplines, generic STEM). Pass-1 should prefer specific S&T domains; fall through here only when none fits. |

### 3.2 Investing & Business cluster (4)

| # | ID | Display | Scope |
|---|---|---|---|
| 9 | `value-investing` | Value Investing | Buffett/Munger school, Li Lu, Pabrai — investment philosophy, methods, mental models. |
| 10 | `equity-research` | Equity Research | Sector analysis (mining, oil & gas, software, semis as industry), company analysis, research methodology. |
| 11 | `economy-markets` | Economy & Markets | Macro, monetary policy, currency, bonds, interest rates, gold, commodities, market structure. |
| 12 | `business-management` | Business & Management | Strategy, operations, organizational design — distinct from investment-decision-making. |

### 3.3 Human & Society cluster (5)

| # | ID | Display | Scope |
|---|---|---|---|
| 13 | `health-wellbeing` | Health & Wellbeing | Nutrition, fitness, longevity, sleep, applied medicine — life-application angle. |
| 14 | `history` | History | Historical events, civilizations, eras, historical biographies. |
| 15 | `geopolitics` | Geopolitics & World Affairs | International relations, geopolitical analysis, current world events, demographics, world powers. |
| 16 | `psychology` | Psychology & Self-Improvement | Cognitive psychology, behavior, personal development, productivity. Brain-mechanism focus → `brain-consciousness`. |
| 17 | `spirituality` | Spirituality | Major religions, theology, comparative religion, meditation, spiritual practice. Religion is treated as a form of spirituality. |

### 3.4 Humanities & Aesthetics cluster (3)

| # | ID | Display | Scope |
|---|---|---|---|
| 18 | `literature` | Literature | Fiction, poetry, literary criticism, author studies. Philosophical novels (e.g., Camus, Dostoevsky) judgment-called — see §4 boundary conventions. |
| 19 | `philosophy` | Philosophy | Western & Eastern philosophy, ethics, epistemology, metaphysics. Philosophy of mind → `brain-consciousness`. |
| 20 | `arts` | Arts | Visual arts, architecture, design, music — aesthetic and creative disciplines. |

### 3.5 Life & Personal cluster (2)

| # | ID | Display | Scope |
|---|---|---|---|
| 21 | `food-drinks` | Food & Drinks | Coffee, wine, whiskey, beer, cooking, food science. |
| 22 | `retirement-lifestyle` | Retirement & Lifestyle | Retirement planning lifestyle side (when / how to retire), income-stream design from a lifestyle lens, hobbit-hole-end goals. |

### 3.6 Content-type & residual (2)

| # | ID | Display | Scope |
|---|---|---|---|
| 23 | `quotes` | Quotes | Standalone quotes — wisdom snippets, attributable one-liners. Cross-section to substantive topics via graph edges to entities (e.g., Buffett quote → entity edge to Buffett-the-person → entity edges to Value-Investing topic). |
| 24 | `others` | Others | Residual catch-all for genuinely uncategorizable content. Should be rare in practice — its rate is a quality signal for the list's completeness. |

---

## 4. Boundary conventions

These call out **conceptual confusion risks** — places where two domains genuinely overlap in *what content lives there*. They do NOT enumerate every "domain X has an application angle to domain Y" relationship (which is just D-NW4-2's primary-domain rule applied uniformly).

- **`brain-consciousness` ↔ `biology`** — brain-specific (neuroscience, cognition, perception) → `brain-consciousness`; cellular / genetic / evolutionary / organism-level → `biology`.
- **`brain-consciousness` ↔ `ai-ml`** — substance decides: brain-modeling paper → `brain-consciousness`; LLM paper with cognitive-science references → `ai-ml`; the intersection is captured via graph edges.
- **`brain-consciousness` ↔ `psychology`** — mechanism-level / empirical brain science → `brain-consciousness`; behavior / self-improvement / applied → `psychology`.
- **`literature` ↔ `philosophy`** — fiction / poetry / criticism → `literature`; argumentative / systematic thought → `philosophy`. Philosophical novels (Camus, Dostoevsky) judgment-called per piece. *Flag for reviewer input.*
- **`retirement-lifestyle` ↔ `economy-markets` / `value-investing`** — *lifestyle dimension* (when / how to retire) → `retirement-lifestyle`; *financial-vehicle dimension* (bond ladders, dividend strategy) → `value-investing` or `economy-markets`.
- **`science-technology` catch-all guardrail** — only when none of #1–7 fits cleanly. Chemistry-as-applied / materials / climate / engineering disciplines → here. Pass-1 should prefer specific S&T domains; the catch-all is a fallback, not a first choice.

---

## 5. Explicit drops (and why)

| Candidate | Why dropped |
|---|---|
| **Biography** | Per D-NW4-3 curation rule (≥2 sources for content-type domain): Alexandria only votes yes. Biographies of investors → `value-investing`; of scientists → relevant S&T domain; of historical figures → `history`. Content-type signal lives as `tags: [biography]`. |
| **Howto** | Per D-NW4-3. No source organizes by content-type "howto" — Joseph organizes by subject (Linux howtos → PC-WSL dir). Lives as `tags: [howto]`. |
| **Good to Know** | Catch-all from X / Facebook / OneNote — handled by `others` + tags. Not informative enough to be a domain. |
| **World Map / Geography** | X bookmarks tag only. Folds under `history` (historical geography) or `geopolitics` (current world). |
| **Beauty** (Facebook collection) | Single source; folds under `health-wellbeing` (skincare / cosmetics) or `arts` (aesthetics). |
| **Career / Jobs** | OneNote / Jobs is mostly past job-hunt material — administrivia, not knowledge accumulation. Excluded from KDB scope at ingestion gate. |
| **Games** | OneNote / Games dir — leisure; excluded from KDB scope. |
| **Sub-domain entries from OneNote** (Alibaba, Barrick Gold, Buffett-Munger, Mohnish Pabrai, etc.) | These are *entities*, not domains. They live as graph nodes; their content's domain is `value-investing` / `equity-research`. |
| **Amazon book categories** | Commercial taxonomy with leisure-fiction categories that Joseph won't accumulate KDB knowledge along. Considered and explicitly dropped during source-selection (2026-05-25). |

---

## 6. Open questions for external review

Reviewers are asked to specifically weigh in on:

### OQ-NW4-1 — Flat vs hierarchical structure
D-NW4-1 ratified flat. Does a hierarchical (domain + sub_domain) structure offer benefits worth the cognitive-load and curation cost we've ruled out? Specifically, would Joseph's Obsidian 2-level organization be better honored by mirroring it as domain+sub_domain?

### OQ-NW4-2 — Quotes as first-class domain
D-NW4-3 ratified quotes-as-domain. Is this defensible, or should quotes be a `content_type` field (Shape Y from the design discussion) or just a tag? Argue for the alternative if you see a reason.

### OQ-NW4-3 — `science-technology` catch-all slippery slope
Is the catch-all justified, or does it cannibalize the more specific S&T domains by giving Pass-1 an easy escape? If kept, is the guardrail (§4 last bullet) sufficient?

### OQ-NW4-4 — `logics` as math+logic-superset
Mathematics treated as a form of logic. Is this a productive unification, or does it conflate fields that should remain separate (e.g., applied statistics vs formal logic)?

### OQ-NW4-5 — `spirituality` as religion-superset
Religion treated as a form of spirituality. Defensible, or does it lose distinctions important for content classification (e.g., comparative theology vs personal meditation)?

### OQ-NW4-6 — Missing domains
What's missing from the 24 that Joseph's content patterns would have surfaced if we'd looked harder? Candidates worth probing: Education, Sociology, Law, Environment / Sustainability, Sports, Crafts / Making, Language Learning.

### OQ-NW4-7 — Over-included domains
Conversely, any of the 24 that should be dropped or merged? `arts` and `food-drinks` are low-frequency; `science-technology` catch-all may be redundant.

### OQ-NW4-8 — Granularity calls within S&T
Within the 8-domain S&T cluster: are `software` + `hardware` the right cut (vs `computing` as one)? Is `brain-consciousness` cleanly separable from `biology` + `psychology`, or is it a sub-area of one of them?

### OQ-NW4-9 — Boundary convention completeness
The §4 list calls out 6 boundaries. Are there genuine confusion-risk boundaries we're missing? (Specifically NOT including routine application-angle pairings.)

### OQ-NW4-10 — Naming conventions
IDs are kebab-case; display names are Title Case. Any IDs that are confusing, ambiguous, or would benefit from rename? Specifically: `logics` (plural unusual in English); `brain-consciousness` (compound); `science-technology` (looks like cluster name).

### OQ-NW4-11 — Empirical-density check
Imagine Joseph's 2,000+ Alexandria books distributing across these 24 domains. Does the distribution look sensible, or is the list shaped for *current* interests at the expense of historical content?

### OQ-NW4-12 — `quotes` cross-section quality risk
A quote's substantive connections depend on entity extraction at Pass-1. If extraction fails (e.g., a Buffett quote where "Buffett" isn't extracted), the cross-section to Value-Investing is lost. Is this fragility acceptable, or does it justify a fallback (e.g., a `mentioned_domains` field)?

---

## 7. Versioning

- **v0.1** — initial 23-domain draft (within-session iteration; not externally reviewed)
- **v0.2** — Joseph-ratified 24-domain list with brain-consciousness + science-technology added; arts merged from art-architecture + music (this document)
- **v0.3+** — post-external-review fold; pending dispatch and synthesis
