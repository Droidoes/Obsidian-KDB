# `KDB/wiki/` — Design Rationale

This doc explains **what the wiki is for**, **why it has exactly three page types** (`summary`, `concept`, `article`), and **how those three relate** to form an ontology that compounds over time rather than fossilizing.

For the mechanical side (schema, frontmatter, apply pipeline), see:
- `docs/CODEBASE_OVERVIEW.md` — full system architecture
- `docs/compile_result.md` — the LLM's JSON output contract
- `KDB/KDB-Compiler-System-Prompt.md` — the LLM's runtime semantic contract

---

## 1. Purpose — why the wiki exists at all

The wiki is not a pretty graph. It's the **substrate that lets knowledge compound** instead of fossilizing one-source-at-a-time.

| Without the wiki | With the wiki |
|---|---|
| Each source is a silo. "Attention mechanism" is explained ten times, once per paper that mentions it. | One `concepts/attention-mechanism.md` grows stronger each time a new source references it. |
| Reading a second source on the same topic produces duplicate notes, not integrated understanding. | New sources contribute `source_refs` and strengthen the concept's surrounding link graph. |
| The KB's value is O(N) — linear in sources read. | The KB's value is superlinear — every new source enriches existing concepts and reveals cross-source relationships. |

This is the **Karpathy LLM-KB thesis** in one line: *the LLM acts as a compiler that distills many raw sources into a reusable ontology.* The wiki folder *is* that ontology.

**Secondary payoff (deferred to Track 2 — `llm-linker`):** once the ontology exists, we can go back into the Human Side of the vault and inject `[[wikilinks]]` into your own notes pointing to KDB concepts. The KB starts *fertilizing your own writing* rather than sitting in a silo labeled "machine stuff."

---

## 2. The Three Page Types

### `summary` — one per raw source (1:1)

- **Scope:** exactly one summary page per file in `KDB/raw/`.
- **Slug:** derived from the source file's stem, kebab-cased.
- **Role:** the "TL;DR entry point" for that source. Links out to every concept/article the source contributed to.
- **Lifecycle:** overwritten every time the source is recompiled (D18, full-body replacement).

Think of a summary as the **bookmark** for a source: short abstract + fan-out of `[[concept-slug]]` links. You reach for it when you want to re-engage with a specific source.

### `concept` — atomic idea, reused across sources (N:1 from sources → 1 concept)

- **Scope:** one page per distinct idea (e.g., `attention-mechanism`, `ruling-by-law`, `margin-of-safety`).
- **Slug:** semantic, hyphen-separated, kebab-cased.
- **Role:** **the reusable building block of the ontology.** One concept may be supported by many sources; `supports_page_existence[]` tracks which ones.
- **Lifecycle:** grows over time. Each new compile that references the concept adds to `source_refs[]` and may enrich body content.

Concepts are where knowledge actually compounds. A concept page isn't "what source X says about attention" — it's "what the KB as a whole knows about attention, grounded in every source that's contributed."

### `article` — narrative synthesis across concepts (M:N)

- **Scope:** one per *emergent narrative thread*. Emitted only when source content warrants multi-concept synthesis.
- **Slug:** topical, often longer-form (`evolution-of-chinese-political-philosophy`).
- **Role:** weaves concepts into a connected story. The "here's how all these pieces fit" layer.
- **Lifecycle:** rarer than concepts; emitted selectively by the LLM when a single source (or, later, a cross-source synthesis) genuinely needs narrative glue.

Articles are bridges. They answer "how do `ruling-by-law`, `confucianism`, and `dynastic-legitimacy` connect?" — something no single concept page should try to do on its own.

---

## 3. How They Relate

```
KDB/raw/<source>.md
        │
        │  1:1
        ▼
  wiki/summaries/<source-stem>.md ────links to────┐
                                                   │
                                                   ▼
                                        wiki/concepts/<concept>.md  ◀──links from──┐
                                                   ▲                                │
                                                   │  many-to-many                  │
                                                   │                                │
                                        wiki/articles/<topic>.md ──────────────────┘
```

- **Source → Summary:** strict 1:1 compilation.
- **Source → Concepts:** one source contributes to many concepts; one concept is supported by many sources (N:M).
- **Summary → Concepts:** summary links out to every concept it contains.
- **Article → Concepts:** article links to every concept it synthesizes.
- **Concept ← everything else:** concepts are hub-shaped. Python reconciles `incoming_links_known` from the outgoing links of all summaries/articles — the concept itself doesn't track who links to it.

The key property: **no concept is owned by a single source.** The concept is an independent entity whose support accrues. That's what makes the wiki an ontology rather than a stack of abstracts.

---

## 4. Why Three — and Not Fewer, and Not More

### Rejected: one type (flat)

> "Just make everything a page."

Collapses the distinction between *this-source-in-particular* and *idea-reused-across-sources*. No way to express "this concept was mentioned in 8 different books" because there's no concept page distinct from the 8 summaries. Graph becomes a bag of undifferentiated nodes; compounding fails.

### Rejected: two types (summary + concept, no article)

> "Summaries for sources, concepts for ideas. Synthesis is optional — let it live inside a concept page."

Doesn't hold up. Concepts want to be **atomic** (one idea = one page). Synthesis is inherently **relational** (multiple concepts woven together). Jamming synthesis into a concept page violates the atomic principle and makes concept pages sprawl. The article type is the pressure-release valve that keeps concepts disciplined.

### Rejected: many types (claim, evidence, hypothesis, method, counterexample, ...)

> "A richer ontology surfaces more structure."

Three failure modes:
1. **LLM disambiguation cost** — every new type expands the decision space the model has to get right. More types = more self-drift (the kind we already see with `concept_slugs` vs `pages[]`).
2. **Slug collision explosion** — `attention-mechanism` (concept) vs `attention-mechanism-method` vs `attention-mechanism-claim` — same idea fractured across types. Defeats the point.
3. **Graph noise** — every type adds another edge-color the human has to mentally filter. Obsidian's graph view works best with a small, stable type vocabulary.

The **three-type system is the minimum viable ontology**: atomic units (concepts), their 1:1 entry points (summaries), and their multi-concept syntheses (articles). Removing any one breaks the model. Adding a fourth has to earn its way in by solving a concrete expressive gap — which none proposed so far has.

---

## 5. Lifecycle of a Concept

A concept page isn't written once — it's grown. Here's the trajectory:

| Compile #1 | Compile #2 (later, new source) | Compile #N |
|---|---|---|
| Source A introduces "attention mechanism." | Source B also discusses it. | Source N adds a new angle. |
| LLM emits `concept/attention-mechanism.md` with body grounded in A. | LLM sees existing concept in manifest snapshot. Emits **merged** body + adds B to `supports_page_existence`. | Body continues to integrate N sources' contributions; `source_refs[]` grows. |
| `source_refs = [A]` | `source_refs = [A, B]` | `source_refs = [A, B, ..., N]` |

This is the compounding. Every new source either creates new concepts *or* strengthens existing ones — never duplicates.

**Guardrail:** D18 (full-body replacement) + D8 (LLM reads manifest snapshot) means the LLM must *read the existing concept body* and produce a coherently merged version. It can't silently overwrite — that would destroy accumulated knowledge. This is why the manifest snapshot is part of every prompt.

---

## 6. Graph Topology Intuition

When you open Obsidian's graph view, each type has a recognizable shape:

| Type | Out-degree | In-degree | Position |
|---|---|---|---|
| `summary` | **high** (links to all concepts it covers) | low (only linked by its concepts' back-graph) | **peripheral leaf** |
| `concept` | medium (cross-references to related concepts) | **high** (every summary/article that touches it) | **hub** |
| `article` | **high** (synthesizes many concepts) | medium (linked by related articles, maybe sister summaries) | **bridge** |

A healthy wiki graph, at scale, should look like **a constellation of hub-and-spoke clusters** (concepts + their source summaries), **stitched together by article bridges**. If everything is leaves or everything is hubs, something's off:

- All-leaves (every page links out, nothing links in) → concepts aren't being reused; the LLM is minting a new slug for each source. Tune the prompt.
- All-hubs (mass collapse into a few dense nodes) → concepts are too broad. Encourage finer-grained concept pages.

---

## 7. Linking Discipline

| Rule | Where enforced |
|---|---|
| `[[slug]]` only (Obsidian-flavored). No HTML, no markdown-style links. | `KDB/KDB-Compiler-System-Prompt.md` §Ground Rule 6 |
| Link aggressively within emitted page bodies — but only to slugs grounded in the source or in the manifest snapshot. | `KDB/KDB-Compiler-System-Prompt.md` §Ground Rule 3 |
| Forward links (`outgoing_links[]`) are LLM-emitted. Backlinks (`incoming_links_known[]`) are **Python-reconciled** — never LLM-emitted. | D8 boundary |
| Don't prune links to surviving concepts just because the current compile didn't mention them. Soft-remove policy (D6 / `removed_link_policy`). | `manifest.json.settings` |

The division is deliberate: the LLM decides *semantic adjacency* (which concepts belong together); Python handles the *graph bookkeeping* (who points at whom, when things were last reconciled, orphan detection).

---

## 8. Relationship to the Broader Pipeline

The wiki is the **output end** of the Track 1 compile pipeline. Everything upstream — scanning, chunking, LLM calls, validation, manifest updates — exists to produce and maintain these three page types correctly.

- **`KDB/raw/`** is the input: unprocessed source documents.
- **`KDB/wiki/`** is the output: the compiled ontology (this doc's subject).
- **`KDB/state/`** is the bookkeeping: `manifest.json` (authoritative ledger), `runs/<run_id>.json` (per-compile journal), `llm_resp/<run_id>/*.json` (call telemetry). The wiki is *derived from* state but also independently inspectable — every page carries its own frontmatter provenance.

No `index.md` or `log.md` lives in `wiki/` (D23, D24). Obsidian's file explorer is the TOC; `state/runs/<run_id>.json` is the run journal.

---

## 9. Decisions Referenced

- **D1** — Two-Sided Vault (KDB/ = Machine Side)
- **D8** — LLM emits semantic intent, Python owns mechanics
- **D18** — Full-body replacement (not patch-ops) for LLM-authored pages
- **D19** — Page-ownership split (only summary / concept / article are LLM-authored)
- **D23** — No `index.md`
- **D24** — No `log.md`

Full ledger: `docs/CODEBASE_OVERVIEW.md` §7.
