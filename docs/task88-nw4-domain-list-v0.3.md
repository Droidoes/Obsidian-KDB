# Task #88 NW-4 — Domain Canonicalization List v0.3

**Status:** v0.3 draft (Joseph-ratified 2026-05-25) — folds 5-reviewer external panel responses + the no-pre-declaration philosophical correction
**Parent:** Task #88 (Ingestion System) blueprint v0.2
**Predecessor:** `docs/task88-nw4-domain-list-v0.2.md` (panel-reviewed)
**Author:** Joseph + Claude (Coding Alter Ego)
**Date:** 2026-05-25

---

## 0. Changes from v0.2

### Renames (3)
| Old ID | New ID | Reason |
|---|---|---|
| `logics` | `math-statistics-logic` | Joseph's preferred name. Surfaces statistics as first-class (it has cross-cuts to AI/ML and neuroscience that "logics" alone obscured). 5/5 panel convergence on rename; Joseph's name preferred over panel's `mathematics-logic` variant. |
| `brain-consciousness` | `neuroscience-cognition` | Per Joseph ([11]) + Gemini Rec 4. More scientifically idiomatic; matches established field nomenclature. |
| `others` | `undecided` | Per Joseph ([5]) — honors uncertainty without finality. Less semantically heavy than `uncategorized-residual` (Gemini) or staying with `others`. |

### Scope tightenings (2)
- **`quotes`** — restricted to standalone quotes only; quote-rich essays / speeches / books classify by substantive subject (per Codex F-2 + 4-reviewer operational consensus)
- **`science-technology`** — adds LLM-facing self-check clause ("MUST articulate why none of #1–7 applies") to mitigate sinkhole risk (5/5 panel convergence; name retained per Joseph [17])

### New framework decision: D-NW4-5
**No pre-declared edges, cross-cut hints, or example connections in scope descriptions.** The LLM decides edges based on the GraphDB architecture; pre-declaration is intellectually dishonest and contaminates the substrate we're trying to observe. Classification-disambiguation boundaries between domains are allowed (rules, not edges).

### Scope cleanup
All `"via graph edges"`, `"for example..."`, and cross-section-speculation language stripped from v0.2 scope descriptions. D-NW4-2 and D-NW4-3 reframings (§2) reflect the corrected philosophy.

### New classification boundaries (4)
Added to §4 per Deepseek + Qwen panel findings:
- `value-investing` ↔ `economy-markets`
- `geopolitics` ↔ `history` (temporal)
- `health-wellbeing` ↔ `biology` (mechanism vs application)
- `hardware` ↔ `ai-ml` (chip architecture vs algorithms)

### Schema bug fix (parent blueprint)
The parent blueprint (`task88-ingestion-pipeline-blueprint.md` §4.1) specified `sub_domain` in Pass-1 output schema, contradicting D-NW4-1. **Fixed in the same v0.3 commit** — sub_domain field removed, NW-4 cited as authority. Caught by Codex F-1 + Deepseek F-1.

### Config schema specified (D-NW4-4 extension)
Minimal 4-field per-domain config: `id` + `display` + `scope` + `aliases` (optional). See §7.

### Disposition of v0.2 review findings (audit trail)
See §8 — explicit table mapping each panel finding to its v0.3 disposition.

---

## 1. Source inventory (unchanged from v0.2)

5 sources synthesized; Amazon explicitly dropped. See v0.2 §1 for the full table. No changes in v0.3.

---

## 2. Settled framework (v0.3 — 5 decisions)

### D-NW4-1 — Flat domain list, no sub-domains
Pass-1 LLM classifies each source into exactly **one** domain from the flat list. No `sub_domain` field anywhere in the system. Finer-grained refinement lives in `tags`.

**Reasoning:** Simpler classifier output; aligns with D-88-10 single-call quality monitor; eliminates the "is this a refinement or a content-type?" debate at maintenance time.

### D-NW4-2 — Cross-cutting concerns are not pre-declared
The system does NOT pre-declare or encode how domains connect to one another. AI/ML, quotes, and other potentially cross-cutting topics are classified by what the content fundamentally IS. Whether connections emerge in the knowledge graph is determined by the LLM operating on the GraphDB architecture, not by static schema declarations or scope hints.

**Reasoning:** Pre-declaration contaminates the substrate we're trying to observe. We want to see what the system builds emergently. (See D-NW4-5 for the generalized principle.)

### D-NW4-3 — Quotes is its own first-class domain
Treated as a domain in the flat list. Scope restricted to standalone quotes only (per v0.3 tightening). Quote-rich essays, speeches, or books classify by substantive subject.

**Reasoning:** 3 of 5 sources organize quotes as first-class. Empirical pattern + the no-pre-declaration discipline → first-class domain whose substantive connections (if any) emerge from the system.

**Curation rule:** A content-type becomes a domain only when ≥2 sources organize it that way. Otherwise it lives under subject + `tags`. Applied: `biography` and `howto` are tags, not domains.

### D-NW4-4 — Domain list is config-driven; minimal config schema
The domain list is a JSON config consumed by Pass-1 prompt rendering, Pass-1 output schema validation, Pass-2 ontology hooks, and GraphDB query layers. Adding / renaming / deprecating a domain = editing JSON. No domain-specific code branches.

**Config schema per domain entry:** `id` (kebab-case unique identifier) + `display` (Title Case name) + `scope` (content-only description) + `aliases` (optional array of historical IDs for rename migration). That's it. See §7.

### D-NW4-5 — No pre-declaration of edges, cross-cut hints, or example connections (NEW in v0.3)
Scope descriptions describe **what content lives in a domain** — they do NOT describe how that domain connects to others, do NOT use "for example..." hinting, do NOT enumerate cross-cut targets. Schema fields that duplicate graph structure (`topic_hints`, `mentioned_domains`, `secondary_domains`) are anti-pattern and rejected.

Classification-disambiguation boundaries between adjacent domains (see §4) are **rules, not edges** — they say "content of type X classifies to domain A vs B" — and are permitted.

**Reasoning:** Pre-declaring edges is intellectually dishonest ("for example" framing slips in unowned suggestions). The LLM decides edges based on the GraphDB architecture; our job is to provide minimal principled scaffolding, not to seed the answer.

**Generalization beyond NW-4:** This principle applies to all KDB ontology/schema design going forward. (Memory `feedback_no_edge_predeclaration_no_hints` captures it.)

---

## 3. The list — 24 domains

Cluster groupings below are **for human readability of this document only**. The Pass-1 LLM sees a flat list, not grouped (per D-NW4-1 + Joseph's rejection of cluster-grouped prompt presentation).

### 3.1 Science & Technology cluster (8)

| # | ID | Display | Scope |
|---|---|---|---|
| 1 | `ai-ml` | AI & Machine Learning | LLMs, prompt engineering, RAG, models, MLOps, AI tools. Technical and foundational content about how AI/ML systems work. |
| 2 | `software` | Software | Programming languages, CS algorithms, operating systems (Linux / WSL), Git, dev tools, cloud infrastructure, software architecture. |
| 3 | `hardware` | Hardware | Computer architecture, chips, semiconductors as engineering, electronics, devices, silicon design. |
| 4 | `math-statistics-logic` | Math, Statistics & Logic | Pure and applied mathematics, probability, statistics, formal logic, decision theory, computational theory foundations. |
| 5 | `biology` | Biology | Life sciences, genetics, cellular biology, evolution, organisms. |
| 6 | `physics` | Physics | Physical sciences, astronomy, cosmology, chemistry at fundamental level, materials physics. |
| 7 | `neuroscience-cognition` | Neuroscience & Cognition | Brain mechanisms, cognitive science, consciousness studies, philosophy of mind. Content that maps cognitive phenomena to neurological substrates. |
| 8 | `science-technology` | Science & Technology (catch-all) | Scientific or technical content that does not fit cleanly in #1–7. Use ONLY when you can articulate in one sentence why none of #1–7 applies. If you cannot articulate that reason, re-examine #1–7 first. |

### 3.2 Investing & Business cluster (4)

| # | ID | Display | Scope |
|---|---|---|---|
| 9 | `value-investing` | Value Investing | Investment philosophy, methods, mental models in the Buffett / Munger / Li Lu / Pabrai tradition. |
| 10 | `equity-research` | Equity Research | Sector analysis (mining, oil & gas, software, semis as industry), company analysis, research methodology. |
| 11 | `economy-markets` | Economy & Markets | Macro, monetary policy, currency, bonds, interest rates, gold, commodities, market structure. |
| 12 | `business-management` | Business & Management | Strategy, operations, organizational design — distinct from investment-decision-making. |

### 3.3 Human & Society cluster (5)

| # | ID | Display | Scope |
|---|---|---|---|
| 13 | `health-wellbeing` | Health & Wellbeing | Nutrition, fitness, longevity, sleep, applied medicine — life-application angle. |
| 14 | `history` | History | Historical events, civilizations, eras, historical biographies, completed historical periods. |
| 15 | `geopolitics` | Geopolitics & World Affairs | International relations, geopolitical analysis, current world events, demographics, world powers. |
| 16 | `psychology` | Psychology & Self-Improvement | Cognitive psychology, behavior, personal development, productivity. |
| 17 | `spirituality` | Spirituality | Religions, theology, comparative religion, meditation, spiritual practice. |

### 3.4 Humanities & Aesthetics cluster (3)

| # | ID | Display | Scope |
|---|---|---|---|
| 18 | `literature` | Literature | Fiction, poetry, literary criticism, author studies. |
| 19 | `philosophy` | Philosophy | Western and Eastern philosophy, ethics, epistemology, metaphysics. |
| 20 | `arts` | Arts | Visual arts, architecture, design, music — aesthetic and creative disciplines. |

### 3.5 Life & Personal cluster (2)

| # | ID | Display | Scope |
|---|---|---|---|
| 21 | `food-drinks` | Food & Drinks | Coffee, wine, whiskey, beer, cooking, food science. |
| 22 | `retirement-lifestyle` | Retirement & Lifestyle | Retirement planning lifestyle side (when / how to retire), income-stream design from a lifestyle lens, hobbit-hole-end goals. |

### 3.6 Content-type & residual (2)

| # | ID | Display | Scope |
|---|---|---|---|
| 23 | `quotes` | Quotes | Standalone quotes — attributable one-liners, wisdom snippets, aphorisms. Use ONLY when the source's primary unit is a standalone quotation or quote collection. Quote-rich essays, speeches, or books classify by substantive subject. |
| 24 | `undecided` | Undecided | Residual catch-all for genuinely uncategorizable content. Use ONLY when no other domain in this list describes the content's primary nature. High `undecided` rates indicate the domain list needs expansion. |

---

## 4. Classification boundaries (10 conventions)

These call out **conceptual confusion risks** between adjacent domains. They are classification disambiguation rules — they tell the Pass-1 LLM which domain wins when content sits at a boundary. They are NOT edge declarations (per D-NW4-5).

### Carried from v0.2 (6)

- **`neuroscience-cognition` ↔ `biology`** — brain-specific content (mechanisms, cognition, perception) → `neuroscience-cognition`; cellular / genetic / evolutionary / organism-level → `biology`.
- **`neuroscience-cognition` ↔ `ai-ml`** — substance decides: brain-modeling content → `neuroscience-cognition`; content primarily about how LLMs / AI systems work → `ai-ml`.
- **`neuroscience-cognition` ↔ `psychology`** — mechanism-level / empirical brain science → `neuroscience-cognition`; behavior / self-improvement / applied → `psychology`.
- **`literature` ↔ `philosophy`** — fiction / poetry / criticism → `literature`; argumentative / systematic thought → `philosophy`. Philosophical novels judgment-called per piece.
- **`retirement-lifestyle` ↔ `economy-markets` / `value-investing`** — lifestyle dimension (when / how to retire) → `retirement-lifestyle`; financial-vehicle dimension (bond ladders, dividend strategy) → `value-investing` or `economy-markets`.
- **`science-technology` catch-all guardrail** — use ONLY when none of #1–7 fits cleanly AND you can articulate why in one sentence.

### Added in v0.3 (4)

- **`value-investing` ↔ `economy-markets`** — content primarily about investment decision-making (what to buy / sell / hold, valuation frameworks) → `value-investing`; content primarily about how markets or economies function (mechanisms, policy transmission, market structure) → `economy-markets`. When both are present, the primary purpose (teach investment vs explain economics) is the tiebreaker.
- **`geopolitics` ↔ `history`** — content whose primary analytical frame is the present or recent past (post-Cold War, contemporary power dynamics) → `geopolitics`; content whose primary frame is a completed historical period → `history`. Historical analysis with explicit contemporary application → `geopolitics`.
- **`health-wellbeing` ↔ `biology`** — content aimed at informing personal health decisions (nutrition advice, fitness protocols, supplement evidence) → `health-wellbeing`; content about biological mechanisms without direct personal-application framing → `biology`.
- **`hardware` ↔ `ai-ml`** — chip architecture and silicon designed for AI inference / training → `hardware`; AI algorithms and models that run on hardware → `ai-ml`.

---

## 5. Explicit drops (unchanged from v0.2 + v0.3 additions)

| Candidate | Why dropped |
|---|---|
| **Biography** | Per D-NW4-3 curation rule. Lives as `tags: [biography]` under subject domain. |
| **Howto** | Per D-NW4-3 curation rule. Lives as `tags: [howto]`. |
| **Good to Know** | Catch-all; handled by `undecided` + tags. |
| **World Map / Geography** | Folds under `history` or `geopolitics`. |
| **Beauty** (Facebook) | Folds under `health-wellbeing` or `arts`. |
| **Career / Jobs** | Administrivia, excluded from KDB scope at ingestion gate. |
| **Games** | Leisure, excluded from KDB scope. |
| **Sub-domain entries from OneNote** (Alibaba, Barrick Gold, Buffett-Munger, Pabrai, etc.) | These are *entities*, not domains. |
| **Amazon book categories** | Commercial taxonomy with leisure-fiction noise. |
| **`societal-systems-law`** (Gemini Rec 5; v0.3 new) | Per Joseph [10] [16]: present interest is covered by `geopolitics` + `economy-markets` + `history`. Revisit if telemetry shows density. |
| **`topic_hints` / `secondary_domains` field** (Codex / Deepseek / Qwen / Gemini Rec 1; v0.3 new) | Per Joseph [6] + D-NW4-5. Pre-declared cross-cuts contaminate the substrate; quote / AI-ML fragility accepted as the price of an unbiased observation layer. |
| **Cluster-grouped prompt presentation** (Codex O-1 + Grok R-4; v0.3 new) | Per Joseph [7] + D-NW4-1. Smuggles hierarchy back through the prompt after we explicitly removed sub-domain structure. |
| **`spirituality` revert to `religion-spirituality`** (Gemini Rec 7; v0.3 new) | Per Joseph [15] — D-NW4 v0.2 call holds. |
| **`quotes` disband + `format_type` field** (Gemini Rec 2; v0.3 new) | Per Joseph [13] — D-NW4-3 stays. Quotes is a first-class domain. |
| **`applied-sciences-residual`** rename (Gemini Rec 6; v0.3 new) | Per Joseph [17] — `science-technology` name retained until better option found. Stronger guardrail (self-check clause) chosen over rename. |
| **`uncategorized-residual`** rename (Gemini Rec 8; v0.3 new) | Per Joseph [5] — too heavy-handed. `undecided` chosen as honest middle ground. |

---

## 6. Open questions remaining (after v0.3 fold)

Most v0.2 OQs are closed by v0.3 decisions (see §8 disposition table). The remaining open items are operational / monitoring concerns:

### OQ-NW4-13 (NEW)
**`undecided` rate KPI:** What threshold for `undecided` rate (per rolling window) triggers a domain-list expansion review? Qwen suggested <5% per rolling 100-source window. Operational decision deferred to NW-5 benchmark.

### OQ-NW4-14 (NEW)
**`science-technology` catch-all rate KPI:** What threshold for `science-technology` rate triggers tightening of #1–7 scopes (i.e., the catch-all is cannibalizing specific domains)? Operational decision deferred to NW-5.

### OQ-NW4-15 (NEW)
**Empirical monitoring set:** `arts` and `food-drinks` low-frequency concern (Codex / Grok / Gemini); `retirement-lifestyle` singleton risk (Codex / Deepseek); social-institutions density (Codex F-6 watch). After 2-3 months of live ingestion, run an empirical scan to validate or merge / drop.

### OQ-NW4-16 (NEW)
**`societal-systems` deferred-add trigger:** What density signal in geopolitics / economy-markets / history `undecided` co-occurrence triggers the v0.4+ add of `societal-systems`? Joseph [10] [16] deferred until needed.

---

## 7. Config schema (D-NW4-4 extension)

### Per-domain entry — 4 fields

```json
{
  "id": "math-statistics-logic",
  "display": "Math, Statistics & Logic",
  "scope": "Pure and applied mathematics, probability, statistics, formal logic, decision theory, computational theory foundations.",
  "aliases": ["logics"]
}
```

| Field | Type | Purpose |
|---|---|---|
| `id` | string, kebab-case, unique | Canonical identifier used in Pass-1 output schema, GraphDB property values, query layer |
| `display` | string, Title Case | Human-facing name for UI / docs / display contexts |
| `scope` | string, prose paragraph | Content-only description of what classifies here. **No "for example" hints. No edge declarations. No cross-cut speculation.** (Enforces D-NW4-5.) |
| `aliases` | array of strings, optional | Historical IDs that resolve to this current ID at query time. Enables rename migration without backfill. |

### What the config does NOT hold (anti-pattern per D-NW4-5)
- ❌ Inclusion / exclusion examples
- ❌ Boundary-pair declarations (those live in §4 of this doc, not in the config the LLM consumes)
- ❌ Expected-rollup-cluster (smuggles hierarchy)
- ❌ Prompt-rendering text (the prompt template is its own artifact; the config feeds it raw scopes)
- ❌ Cross-cut hints / `connects_to` / `topic_hints`

### Consumed by
- **Pass-1 LLM prompt rendering** — scope descriptions injected into the classification prompt
- **Pass-1 output schema** — `domain` field validated as enum over current IDs (aliases NOT accepted on write; only on read)
- **GraphDB property indexing** — `domain` indexed for query
- **Query layer** — alias resolution at read time so historical sources resolve to current IDs

### File location (v1)
`kdb_compiler/config/domains.json` — single source of truth; all consumers read from it.

---

## 8. Disposition of v0.2 review panel findings (audit trail)

Mapping each unique panel finding to its v0.3 disposition. Convergence labels: **U** = 5/5 unanimous, **S** = 4/5 strong, **M** = 3/5 majority, **G** = 2/5 split, **B** = 1/5 unique.

| Finding | Convergence | v0.3 disposition |
|---|---|---|
| U1: `science-technology` catch-all sinkhole | 5/5 | ✓ Self-check clause added to scope (§3.1 #8); name retained per Joseph [17] |
| U2: `logics` rename + scope conflation | 5/5 | ✓ Renamed `math-statistics-logic` (Joseph variant over panel `mathematics-logic`) |
| U3: `quotes` boundary needs tightening | 5/5 | ✓ Scope tightened to standalone-only (§3.6 #23); Gemini's disband-entirely rejected per Joseph [13] |
| S1: Add `topic_hints` / `secondary_domains` fallback | 4/5 | ✗ Rejected per Joseph [6] + new D-NW4-5; Grok's principled dissent prevails |
| M1: Operationalize `undecided` (LLM-facing text + KPI) | 3/5 + Gemini variant | ✓ Scope text updated; KPI deferred to NW-5 (OQ-NW4-13) |
| M2: NW-5 evaluation counters / KPIs | 3/5 | ✓ Inputs flagged to NW-5 work item (OQ-NW4-13/14) |
| M3: `societal-systems-law` / education domain | 3/5 | ✗ Deferred per Joseph [10] [16] — geopolitics + economy-markets + history cover for now |
| G1: 🐛 sub_domain in parent blueprint contradicts D-NW4-1 | 2/5 | ✓ **Fixed** in parent blueprint same commit (line 214 + descriptive references) |
| G2: Cluster-grouped prompt presentation | 2/5 | ✗ Rejected per Joseph [7] — smuggles hierarchy after we removed it |
| G3: Config schema needs more than IDs | 2/5 | ✓ Partial — minimal extension to ID + display + scope + aliases (§7); examples / boundary-pairs / cluster rejected per D-NW4-5 |
| G4: `brain-consciousness` → methodological-vs-substantive refinement | 2/5 | ✓ Renamed `neuroscience-cognition` per Joseph [11] + Gemini Rec 4 |
| G5: `retirement-lifestyle` singleton risk | 2/5 | → OQ-NW4-15 (empirical monitoring) |
| B1: `value-investing` ↔ `economy-markets` boundary | 1/5 (Deepseek) | ✓ Added to §4 |
| B2: `geopolitics` ↔ `history` temporal boundary | 1/5 (Deepseek) | ✓ Added to §4 |
| B3: `health-wellbeing` ↔ `biology` boundary | 1/5 (Deepseek) | ✓ Added to §4 |
| B4: `hardware` ↔ `ai-ml` boundary | 1/5 (Qwen) | ✓ Added to §4 |
| Gemini Rec 7: `spirituality` revert | 1/5 | ✗ Joseph [15] holds v0.2 call |
| Gemini Rec 8: `others` → `uncategorized-residual` | 1/5 | ✗ Joseph [5] chose `undecided` instead |
| Gemini Rec 6: `science-technology` → `applied-sciences-residual` | 1/5 | ✗ Joseph [17] retained name |
| Gemini Rec 2: disband `quotes`, use `format_type` field | 1/5 | ✗ Joseph [13] kept domain |

---

## 9. Versioning

- **v0.1** — initial 23-domain draft (within-session; not externally reviewed)
- **v0.2** — Joseph-ratified 24-domain list with `brain-consciousness` + `science-technology` added; `arts` merged. External panel: Codex + Deepseek + Qwen + Gemini Pro Deep Research + Grok.
- **v0.3** — folds 5-reviewer panel feedback + Joseph's no-pre-declaration philosophical correction (D-NW4-5). 3 renames, 2 scope tightenings, 4 new boundaries, parent blueprint sub_domain bug fixed, config schema specified (this document)
- **v0.4+** — pending. Operational telemetry-driven (OQ-NW4-13/14/15/16) once Component #1 ships and live ingestion produces real distribution data.
