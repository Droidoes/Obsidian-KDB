# Task #88 NW-4 — Domain Canonicalization List v0.4

**Status:** v0.4 draft (Joseph-ratified 2026-05-25) — folds Joseph's v0.3 review feedback: arts→arts-design, ai-ml scope expansion, equity-research→personal-finance rename + scope expansion, economy-markets data/stats, retirement-lifestyle + food-drinks → lifestyle merger, NEW boundary-axis framework (D-NW4-6)
**Parent:** Task #88 (Ingestion System) blueprint v0.2 (sub_domain bug fixed in v0.3 commit)
**Predecessor:** `docs/task88-nw4-domain-list-v0.3.md`
**Author:** Joseph + Claude (Coding Alter Ego)
**Date:** 2026-05-25

---

## 0. Changes from v0.3

### Renames (3)
| Old ID | New ID | Reason |
|---|---|---|
| `arts` | `arts-design` | Per Joseph [1] — broaden scope to include design (graphic, industrial, interaction, residential) alongside visual arts, architecture, music |
| `equity-research` | `personal-finance` | Per Joseph [3] — scope is empirically applied-personal-investor finance (not academic equity research); the new name captures sector / company analysis + retirement financial planning + tax strategies + portfolio construction |

### Scope expansions (3)
- **`ai-ml`** — add knowledge graphs / GraphDB as AI harness + ontology engineering for AI/LLM systems (per Joseph [2]; GraphDB and ontology are emerging as dominant AI infrastructure)
- **`economy-markets`** — add economic data and statistics (GDP series, unemployment, inflation, central bank data, market indicators) per Joseph [4]
- **`personal-finance`** — covered by rename above; absorbs retirement financial planning + tax strategies + portfolio construction beyond v0.3 `equity-research` scope

### Mergers (1)
- **`retirement-lifestyle` + `food-drinks` → `lifestyle`** per Joseph [5]. Broadens to include travel, collections, food and drinks, retirement activities and goals, home design choices. The financial side of retirement now lives in `personal-finance`; lifestyle covers the experiential / personal-living dimension.

### New framework decision: D-NW4-6
**Boundaries have an axis** — vertical (abstraction stack), horizontal (lens / substrate / form), or temporal (current vs completed period). Each §4 boundary is tagged with its axis to make the classification question explicit for Pass-1.

### §4 restructured by axis
Boundaries grouped into Vertical / Horizontal / Temporal / Usage Guardrail sections. New boundaries added: `personal-finance` ↑ `value-investing` (vertical, per Joseph [3]); `lifestyle` ↔ `personal-finance` (horizontal); `lifestyle` ↔ `health-wellbeing` (horizontal). Three-layer compute stack now expressed as single entry: `ai-ml` ↑ `software` ↑ `hardware`.

### §7 config clarification (per Joseph [1])
The config is **owned by Pass-1**. Everything downstream (Pass-2, GraphDB, query layer) reads the resulting `domain` string value; only Pass-1 needs the scope descriptions for prompt-context rendering.

### Net count change
23 domains (down from v0.3's 24, due to the lifestyle merge).

---

## 1. Source inventory (unchanged from v0.2/v0.3)

5 sources synthesized; Amazon explicitly dropped. See v0.2 §1 for the full table.

---

## 2. Settled framework (v0.4 — 6 decisions)

### D-NW4-1 — Flat domain list, no sub-domains
Pass-1 LLM classifies each source into exactly **one** domain from the flat list. No `sub_domain` field anywhere in the system. Finer-grained refinement lives in `tags`.

### D-NW4-2 — Cross-cutting concerns are not pre-declared
The system does NOT pre-declare or encode how domains connect to one another. Cross-cuts emerge from the LLM operating on the GraphDB architecture, not from static schema declarations or scope hints.

### D-NW4-3 — Quotes is its own first-class domain
First-class domain in the flat list. Scope restricted to standalone quotes only; quote-rich essays / speeches / books classify by substantive subject.

**Curation rule:** A content-type becomes a domain only when ≥2 sources organize it that way. Otherwise it lives under subject + `tags`.

### D-NW4-4 — Domain list is config-driven (Pass-1 owned)
JSON config consumed by Pass-1 prompt rendering, Pass-1 output schema validation, GraphDB property indexing, and query-layer alias resolution. Adding / renaming / deprecating a domain = editing JSON. No domain-specific code branches. Config schema per entry: `id` + `display` + `scope` + `aliases` (see §7).

### D-NW4-5 — No pre-declaration of edges, cross-cut hints, or example connections
Scope descriptions describe **what content lives in a domain** — they do NOT describe how that domain connects to others, do NOT use "for example..." hinting, do NOT enumerate cross-cut targets. Classification-disambiguation boundaries (§4) are rules, not edges, and are permitted.

### D-NW4-6 — Boundaries have an axis (NEW in v0.4)
Boundary conventions in §4 are characterized by their **axis** — which makes the classification question explicit for Pass-1:

- **Vertical (↑)** — abstraction-stack relationship; one domain sits *above* the other (applied / harness / behavior above substrate / foundation / mechanism). Classification question: *"at what abstraction level is this content operating?"*
- **Horizontal (↔)** — different lens, substrate, or form at similar abstraction levels. Classification question: *"which lens does this content adopt?"*
- **Temporal (⇄)** — one domain is current / recent, the other is a completed historical period. Classification question: *"what is the content's primary temporal frame?"*

**Why this matters:** vertical boundaries are usually clearer for the LLM (abstraction level is a recognizable feature of writing). Horizontal boundaries are closer to judgment calls. Tagging the axis tells the LLM what kind of question it is answering.

**For future boundary additions:** if you cannot articulate the axis cleanly, the boundary probably isn't load-bearing — don't add it.

---

## 3. The list — 23 domains

Cluster groupings below are **for human readability of this document only**. The Pass-1 LLM sees a flat list, not grouped.

### 3.1 Science & Technology cluster (8)

| # | ID | Display | Scope |
|---|---|---|---|
| 1 | `ai-ml` | AI & Machine Learning | LLMs, prompt engineering, RAG, models, MLOps, AI tools, knowledge graphs / GraphDB as AI harness, ontology engineering for AI/LLM systems. Technical and foundational content about how AI/ML systems work. |
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
| 10 | `personal-finance` | Personal Finance | Applied personal-investor finance: sector analysis (mining, oil & gas, software, semis as industry), company analysis, equity research methodology, retirement financial planning, tax strategies, portfolio construction. |
| 11 | `economy-markets` | Economy & Markets | Macro, monetary policy, currency, bonds, interest rates, gold, commodities, market structure, economic data and statistics (GDP series, unemployment, inflation, central bank data, market indicators). |
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
| 20 | `arts-design` | Arts & Design | Visual arts, architecture, design (graphic, industrial, interaction, residential), music — aesthetic and creative disciplines. |

### 3.5 Lifestyle cluster (1)

| # | ID | Display | Scope |
|---|---|---|---|
| 21 | `lifestyle` | Lifestyle | Travel, collections, food and drinks, retirement activities and goals, home design choices, and other content about how to live well — the personal-experience-of-living dimension. |

### 3.6 Content-type & residual (2)

| # | ID | Display | Scope |
|---|---|---|---|
| 22 | `quotes` | Quotes | Standalone quotes — attributable one-liners, wisdom snippets, aphorisms. Use ONLY when the source's primary unit is a standalone quotation or quote collection. Quote-rich essays, speeches, or books classify by substantive subject. |
| 23 | `undecided` | Undecided | Residual catch-all for genuinely uncategorizable content. Use ONLY when no other domain in this list describes the content's primary nature. High `undecided` rates indicate the domain list needs expansion. |

---

## 4. Classification boundaries — axis-tagged (D-NW4-6)

Boundaries are classification disambiguation rules. They tell Pass-1 which domain wins when content sits at a domain edge. They are NOT graph edges (per D-NW4-5).

### 4.1 Vertical boundaries (↑) — abstraction-stack

**Classification question:** *"At what abstraction level is this content operating?"*

- **`ai-ml` ↑ `software` ↑ `hardware`** — the compute stack. AI algorithms / models that *use* hardware and software → `ai-ml`; OS / dev tools / cloud infrastructure / programming → `software`; chip architecture / silicon / electronics → `hardware`. Content classifies at the layer it primarily operates on.
- **`neuroscience-cognition` ↑ `biology`** — brain-specific mechanisms, cognition, perception (above) vs cellular / genetic / evolutionary / organism-level (below).
- **`psychology` ↑ `neuroscience-cognition`** — behavior / self-improvement / applied (above) vs mechanism-level empirical brain science (below).
- **`health-wellbeing` ↑ `biology`** — applied personal health decisions (nutrition advice, fitness protocols, supplement evidence) above vs biological mechanisms without personal-application framing (below).
- **`personal-finance` ↑ `value-investing`** — applied / situational (sector analysis, portfolio construction, retirement planning, tax strategy) above vs investment philosophy / methods / mental models (below). Theory below; practice above.

### 4.2 Horizontal boundaries (↔) — lens / substrate / form

**Classification question:** *"Which lens does this content adopt?"*

- **`neuroscience-cognition` ↔ `ai-ml`** — biological substrate vs artificial substrate. Brain-modeling content → `neuroscience-cognition`; content primarily about how LLMs / AI systems work → `ai-ml`. Same level of inquiry, different object of study.
- **`value-investing` ↔ `economy-markets`** — investment-decision lens vs market-mechanism lens. Content primarily about *what to buy / sell / hold* and valuation frameworks → `value-investing`; content primarily about *how markets or economies function* → `economy-markets`. The primary purpose (teach investing vs explain economics) is the tiebreaker.
- **`literature` ↔ `philosophy`** — narrative form vs argumentative form. Fiction / poetry / literary criticism → `literature`; argumentative / systematic thought → `philosophy`. Philosophical novels judgment-called per piece.
- **`lifestyle` ↔ `personal-finance`** — experiential / personal-living focus vs resource-management focus. Travel / hobbies / retirement *activities* / home design → `lifestyle`; retirement financial *planning* / tax strategy / portfolio construction → `personal-finance`.
- **`lifestyle` ↔ `health-wellbeing`** — living-experiential focus vs health-focused. Food enjoyment / wine appreciation / travel → `lifestyle`; nutrition for longevity / fitness protocols / sleep science → `health-wellbeing`.

### 4.3 Temporal boundaries (⇄)

**Classification question:** *"What is the content's primary temporal frame?"*

- **`geopolitics` ⇄ `history`** — current / recent past (post-Cold War, contemporary power dynamics) → `geopolitics`; completed historical period → `history`. Historical analysis with explicit contemporary application → `geopolitics`.

### 4.4 Usage guardrails (not boundaries — included for completeness)

- **`science-technology` catch-all** — use ONLY when none of #1–7 in the S&T cluster fits cleanly AND you can articulate in one sentence why no specific S&T domain applies. The catch-all is a fallback, not a first choice.

---

## 5. Explicit drops (inheriting from v0.2 + v0.3, plus v0.4 additions)

| Candidate | Why dropped |
|---|---|
| **Biography** | Per D-NW4-3 curation rule. Lives as `tags: [biography]` under subject domain. |
| **Howto** | Per D-NW4-3 curation rule. Lives as `tags: [howto]`. |
| **Good to Know** | Catch-all; handled by `undecided` + tags. |
| **World Map / Geography** | Folds under `history` or `geopolitics`. |
| **Beauty** (Facebook) | Folds under `health-wellbeing` or `arts-design`. |
| **Career / Jobs** | Administrivia, excluded from KDB scope at ingestion gate. |
| **Games** | Leisure, excluded from KDB scope. |
| **Sub-domain entries from OneNote** (Alibaba, Barrick Gold, Buffett-Munger, Pabrai, etc.) | These are *entities*, not domains. |
| **Amazon book categories** | Commercial taxonomy with leisure-fiction noise. |
| **`societal-systems-law`** (Gemini Rec 5) | Per Joseph [10] v0.3 — present interest covered by `geopolitics` + `economy-markets` + `history`. Revisit if telemetry shows density. |
| **`topic_hints` / `secondary_domains` field** (Codex / Deepseek / Qwen / Gemini Rec 1) | Per Joseph + D-NW4-5. Pre-declared cross-cuts contaminate the substrate. |
| **Cluster-grouped prompt presentation** (Codex O-1 + Grok R-4) | Per Joseph + D-NW4-1. Smuggles hierarchy back through the prompt. |
| **`spirituality` revert to `religion-spirituality`** (Gemini Rec 7) | Per Joseph v0.3 — D-NW4 v0.2 call holds. |
| **`quotes` disband + `format_type` field** (Gemini Rec 2) | Per Joseph v0.3 — D-NW4-3 stays. Quotes is a first-class domain. |
| **`applied-sciences-residual`** rename (Gemini Rec 6) | Per Joseph v0.3 — `science-technology` name retained. |
| **`uncategorized-residual`** rename (Gemini Rec 8) | Per Joseph v0.3 — `undecided` chosen. |
| **`equity-research` standalone** (v0.4 retire) | Per Joseph [3] v0.4 — renamed to `personal-finance` with broader scope absorbing retirement-financial-planning + tax + portfolio. The narrower "academic equity research" framing didn't match empirical content patterns. |
| **`retirement-lifestyle` + `food-drinks` standalone** (v0.4 merge) | Per Joseph [5] v0.4 — both folded into `lifestyle`. Financial side of retirement absorbed by `personal-finance`. |

---

## 6. Open questions remaining (v0.4)

Most v0.2 panel-raised OQs are now closed (see §8). The remaining open items are operational / telemetry-driven:

- **OQ-NW4-13** — `undecided` rate KPI threshold (Qwen suggested <5% per rolling 100-source window). Deferred to NW-5 benchmark.
- **OQ-NW4-14** — `science-technology` catch-all rate KPI threshold. Deferred to NW-5.
- **OQ-NW4-15** — Empirical monitoring set: low-frequency domains (`arts-design`, `lifestyle`, `quotes`) — verify or merge / drop after 2-3 months of live ingestion telemetry. Watch also for social-institutions density (could re-open the `societal-systems-law` question).
- **OQ-NW4-16** — `societal-systems` deferred-add trigger: density signal in `geopolitics` / `economy-markets` / `history` `undecided` co-occurrence.
- **OQ-NW4-17 (NEW v0.4)** — `personal-finance` ↔ `value-investing` boundary stress test: when applied content cites the underlying theory at length (e.g., a Pabrai portfolio analysis that spends half its words explaining mental models), which domain wins? The vertical-axis rule says "operating layer" — the operating layer of such a piece is `personal-finance` (it's making investment decisions), with the theory references being scaffolding. Monitor classification consistency in early ingestion.

---

## 7. Config schema (D-NW4-4 extension; Pass-1 owned)

### Ownership clarification (per Joseph [1] v0.4)
The config is the **Pass-1 source of truth for the controlled vocabulary**. Everything downstream (Pass-2, GraphDB property indexing, query layer) reads the resulting `domain` string value — only Pass-1 needs the scope descriptions for prompt-context rendering.

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
| `scope` | string, prose paragraph | Content-only description of what classifies here. **No "for example" hints. No edge declarations.** (Enforces D-NW4-5.) |
| `aliases` | array of strings, optional | Historical IDs that resolve to this current ID at query time. Enables rename migration without backfill. |

### What the config does NOT hold (anti-pattern per D-NW4-5)
- ❌ Inclusion / exclusion examples
- ❌ Boundary-pair declarations (those live in §4 of this doc, not in the LLM-consumed config)
- ❌ Expected-rollup-cluster (smuggles hierarchy)
- ❌ Prompt-rendering text (the prompt template is its own artifact; the config feeds it raw scopes)
- ❌ Cross-cut hints / `connects_to` / `topic_hints`

### Consumed by (Pass-1 only owns; downstream reads values)
- **Pass-1 LLM prompt rendering** — scope descriptions injected into the classification prompt
- **Pass-1 output schema** — `domain` field validated as enum over current IDs (aliases NOT accepted on write; only on read)
- **GraphDB property indexing** — `domain` indexed for query (no semantic interpretation needed — just string property)
- **Query layer** — alias resolution at read time so historical sources resolve to current IDs
- **Pass-2** — reads `domain` as a string property like any other consumer; does not require config scope descriptions for its ontology operations

### Aliases needed for v0.4 renames

```json
[
  { "id": "math-statistics-logic", "aliases": ["logics"] },
  { "id": "neuroscience-cognition", "aliases": ["brain-consciousness"] },
  { "id": "undecided", "aliases": ["others", "misc"] },
  { "id": "arts-design", "aliases": ["arts"] },
  { "id": "personal-finance", "aliases": ["equity-research"] },
  { "id": "lifestyle", "aliases": ["retirement-lifestyle", "food-drinks"] }
]
```

### File location (v1)
`kdb_compiler/config/domains.json` — single source of truth; all consumers read from it.

---

## 8. Disposition of v0.2 panel findings + v0.3→v0.4 Joseph-driven changes

### Panel findings disposition (carried from v0.3 + v0.4 confirmation)

Convergence labels: **U** = 5/5 unanimous, **S** = 4/5 strong, **M** = 3/5 majority, **G** = 2/5 split, **B** = 1/5 unique.

| Finding | Convergence | v0.3 disposition (carried into v0.4) |
|---|---|---|
| U1: `science-technology` catch-all sinkhole | 5/5 | ✓ Self-check clause in scope (§3.1 #8); name retained |
| U2: `logics` rename + scope conflation | 5/5 | ✓ Renamed `math-statistics-logic` |
| U3: `quotes` boundary needs tightening | 5/5 | ✓ Scope tightened to standalone-only (§3.6 #22) |
| S1: Add `topic_hints` fallback | 4/5 | ✗ Rejected per D-NW4-5; Grok's dissent prevails |
| M1: Operationalize `undecided` | 3/5 + Gemini | ✓ Scope updated; KPI deferred (OQ-NW4-13) |
| M2: NW-5 evaluation counters / KPIs | 3/5 | ✓ Inputs flagged to NW-5 (OQ-NW4-13/14) |
| M3: `societal-systems-law` / education domain | 3/5 | ✗ Deferred — geopolitics + economy-markets + history cover for now |
| G1: 🐛 sub_domain in parent blueprint | 2/5 | ✓ Fixed in parent blueprint (v0.3 commit) |
| G2: Cluster-grouped prompt presentation | 2/5 | ✗ Rejected — smuggles hierarchy |
| G3: Config schema beyond IDs | 2/5 | ✓ Partial — minimal 4-field schema (§7) |
| G4: `brain-consciousness` rename | 2/5 | ✓ Renamed `neuroscience-cognition` |
| G5: `retirement-lifestyle` singleton risk | 2/5 | ✓ Resolved in v0.4 via lifestyle merge (no longer a singleton) |
| B1-B4: 4 missing boundaries (Deepseek + Qwen) | 1/5 each | ✓ Added to §4 (v0.3) + re-axed by D-NW4-6 (v0.4) |
| Gemini Rec 7: `spirituality` revert | 1/5 | ✗ Joseph holds v0.2 call |
| Gemini Rec 8: `others` → `uncategorized-residual` | 1/5 | ✗ Joseph chose `undecided` |
| Gemini Rec 6: `science-technology` → `applied-sciences-residual` | 1/5 | ✗ Joseph retained name |
| Gemini Rec 2: disband `quotes` | 1/5 | ✗ Joseph kept domain |

### v0.3 → v0.4 Joseph-driven changes (no panel input on these)

| Change | Trigger | v0.4 disposition |
|---|---|---|
| `arts` → `arts-design` + scope broaden | Joseph [1] (v0.4 review) | ✓ Renamed; scope adds graphic/industrial/interaction/residential design |
| `ai-ml` scope expansion (GraphDB + ontology) | Joseph [2] (v0.4 review) | ✓ Added "knowledge graphs / GraphDB as AI harness, ontology engineering for AI/LLM systems" |
| `equity-research` → `personal-finance` + scope expansion | Joseph [3] (v0.4 review) | ✓ Renamed; scope absorbs retirement financial planning + tax + portfolio construction |
| `economy-markets` scope expansion (data + stats) | Joseph [4] (v0.4 review) | ✓ Added economic data and statistics (GDP, unemployment, inflation, etc.) |
| `retirement-lifestyle` + `food-drinks` → `lifestyle` | Joseph [5] (v0.4 review) | ✓ Merged into single `lifestyle` domain; financial-retirement absorbed by `personal-finance` |
| NEW: Boundary axis framework (D-NW4-6) | Joseph [2] (v0.4 follow-up review) | ✓ §4 restructured into Vertical / Horizontal / Temporal sections |
| Config schema Pass-1-ownership clarification | Joseph [1] (v0.4 review) | ✓ §7 explicit on Pass-1 ownership; downstream reads values |

---

## 9. Versioning

- **v0.1** — initial 23-domain draft (within-session; not externally reviewed)
- **v0.2** — Joseph-ratified 24-domain list with `brain-consciousness` + `science-technology` added; `arts` merged. External panel: Codex + Deepseek + Qwen + Gemini Pro Deep Research + Grok.
- **v0.3** — folds 5-reviewer panel feedback + Joseph's no-pre-declaration philosophical correction (D-NW4-5). 3 renames, 2 scope tightenings, 4 new boundaries, parent blueprint sub_domain bug fixed, config schema specified
- **v0.4** — folds Joseph's v0.3 review feedback (this document). `arts` → `arts-design`; `equity-research` → `personal-finance`; `retirement-lifestyle` + `food-drinks` → `lifestyle`; ai-ml + economy-markets scope expansions; NEW D-NW4-6 (boundary axis framework); §4 restructured by axis; config schema Pass-1-ownership clarified
- **v0.5+** — pending. Operational telemetry-driven (OQ-NW4-13 through 17) once Component #1 ships and live ingestion produces real distribution data. No external panel re-review planned; v0.4 ratified as the production-ready vocabulary.
