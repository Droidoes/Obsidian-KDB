# Round 6 Research Prompt — Operationalizing "Learn" for a Personal Knowledge Graph

**Dispatched:** 2026-05-22
**Target models:** Gemini 3.1 Pro, GPT (added by Joseph), Grok 4.3, Opus 4.7 (parallel, independent)
**Response files:** `docs/round6-research-{gemini,gpt,grok,opus}.md`
**Project:** Obsidian-KDB — a raw text → knowledge graph compiler; Kuzu GraphDB substrate; single-user, ~70 entities today.
**Doc that spawned this prompt:** `docs/what-is-the-ontology-for.md` §9.1
**Citation convention:** all references should cite source (paper title + arXiv ID / journal / venue + year). Where a claim depends on a specific system, name it (e.g., HippoRAG, GraphRAG, BioPathNet).

---

## Role cap

You are a **research synthesist**. Survey the relevant literature and
stress-test the working hypothesis below. **Do not propose implementation,
code, file changes, schema diffs, or task plans.** Implementation decisions
are explicitly out of scope; the project team will derive those from your
synthesis. Stay at the level of literature claims + design implications.

---

## Context — what is already settled

The project has resolved across Rounds 4–5
(see `docs/what-is-the-ontology-for.md` §6–§8):

1. The knowledge graph is an **executable substrate** an LLM runs operations
   over — not a static map (A) and not a hopeful soup (B), but Option C
   (§6.4). Value sits in the *operations*, not the links.
2. Selection happens **B + X6**: broad ingestion (the human's
   save-to-vault act is a sufficient filter); only mechanical role-exclusion
   at the door; no value/curation gate (§7.3).
3. Two empirical hedges + one engineering concern + one path-forward
   precondition: **scale** (current ~70 entities vs. benchmark literature
   at 1M+ tokens), **cross-domain density**, **critical density**
   (giant-component risk); **canonicalization** is a first-class
   compile-stage component (§8.2); **predeclared eval criteria** are required
   before building any new operation (§7.4(c)).
4. Stated goal for the graph (§6.1): a "second brain" that can
   **[A] remember**, **[B] learn**, **[C] create knowledge**.

What is **not** settled is **[B]**. That is the subject of this dispatch.

## The question

> **What does "learning" operationally mean for a personal knowledge graph
> meant to function as a second brain?**

Specifically:

- How does the AI / KG / cognitive-science literature working-define
  "learning" in the context of an evolving knowledge graph?
- How does that definition distinguish learning from **retrieval**
  (Remember) and from **analysis** (operations like community detection or
  link prediction on a frozen snapshot)?
- For a *personal* KG at modest scale (1K–10K entities, single-user,
  multi-domain, mixed-source-quality), which definitions are tractable in
  practice and which are research-frontier-only?
- What does the literature actually *prove* can be done — versus what is
  gestured at but not built?

## The working hypothesis to stress-test (not to ratify)

Claude proposed a 4-mechanism decomposition of "Learn" in §9.1.1 of the doc:

1. **Belief tracking** ("delta protocol") — version claims; reinforce /
   contradict / decay
2. **Connection discovery** — link prediction; structural-hole detection
3. **Pattern emergence** — community detection (Leiden / Louvain)
4. **Concept refinement** — canonicalization with temporal / contextual
   splits

It also proposed two reframes:

- *Learn ≠ Remember.* Remember = one-shot retrieval against a frozen graph;
  Learn = how the graph state evolves as the corpus grows.
- *Create is the same engine seen one step further.* Mechanisms 2+3
  *provoke* creation when surfaced to the human / LLM collaborator.

### Two internal tensions to adjudicate

- **T1 — Are Mechanisms 2 and 3 actually Learn?** Under the proposed
  definition *"Learn = state evolution,"* link prediction and community
  detection both operate on **frozen** graph snapshots — they're
  retrieval-with-novelty, not state evolution. Does the literature
  classify link prediction and community detection as **learning
  operations** (the graph learns latent structure) or **analysis
  operations** (a frozen graph is analyzed)? Cite the literature's
  actual usage.

- **T2 — Does the anti-goal sharpen the cut?** Joseph's anti-goal: *"not
  just an Obsidian graph with thousands of connections to show off."*
  Mechanisms 2 and 3 in isolation arguably produce exactly that — they
  surface structure but don't change the user's beliefs or capacity to
  think. Mechanism 1 is the one that makes the user *smarter at the next
  question*. Is this a sharp discriminator the literature supports? Or
  does the literature treat structure-surfacing as a legitimate form of
  learning regardless of belief-revision impact?

## Specifically probe these areas

Even if the working hypothesis ignores them, please cover:

1. **AGM belief revision** (Alchourrón, Gärdenfors, Makinson 1985). The
   foundational philosophical frame for "knowledge state changes under new
   input." How does it decompose (expansion / contraction / revision)?
   Is Mechanism 1 (delta protocol) an instantiation of AGM, or something
   else? Have its operationalizations into KGs been built or remain
   theoretical?

2. **Temporal / evolving knowledge graphs.** What operations does the
   literature treat as *learning* in a temporally-evolving KG?
   - TKG completion (Know-Evolve, TA-DistMult, RE-NET, TLogic, etc.)
   - Temporal embedding methods
   - KG completion under streaming updates

3. **Continual learning / catastrophic forgetting in KGs.** When does the
   literature discuss *forgetting* (decay, contraction, withdrawal of
   support)? Is forgetting an explicit operation or implicit-only? What
   distinguishes "the system forgets" from "the system never knew"?

4. **Link prediction.** Survey of methods (TransE / ComplEx / RotatE /
   BoxE; GNN-based — R-GCN, CompGCN; rule-based — AnyBURL, Neural LP).
   **Critical: is link prediction described as a learning operation, an
   inference operation, or both?** What does each framing actually buy?

5. **Community detection** (Louvain, Leiden, Infomap, label propagation,
   stochastic block models). **Same critical question:** does the
   literature treat community detection as graph *learning* or graph
   *analysis*? Where does the boundary fall, and is it a meaningful
   distinction?

6. **Compression / abstraction (instance → principle).** Mechanisms for
   extracting general principles from N concrete instances. This may be a
   slot the working hypothesis misses entirely.
   - Concept hierarchies / lattice learning
   - Schema induction
   - LLM-driven summarization across a community
   - Rule mining (AMIE, RuleN, etc.)

7. **HippoRAG / GraphRAG and the second-brain framing.** Both were anchors
   in Round 4 of the project's deliberation. Do their authors frame what
   their systems do as *learning*, as *memory*, as *retrieval*, or as a
   combination? Quote the framings; do not paraphrase the central claims.

8. **Anything we're missing.** If the literature contains a mechanism that
   meaningfully serves [B] but isn't in the working hypothesis's 4 slots
   (or in the probed slots above), flag it. The working hypothesis is a
   draft, not a fence.

## Output format

Structure your response as:

```
## Executive summary (200–400 words)

The single most important framing the literature offers; what survives
stress-test of the working hypothesis; what dies.

## Working-hypothesis adjudication

### T1 — Are Mechanisms 2 and 3 Learn or Remember?
[Literature classification + recommendation.]

### T2 — Does the anti-goal sharpen the cut?
[Literature-grounded answer.]

### Mechanism 1 (Belief tracking) — verdict
### Mechanism 2 (Connection discovery) — verdict
### Mechanism 3 (Pattern emergence) — verdict
### Mechanism 4 (Concept refinement) — verdict

(For each: keep / drop / reclassify-as-Remember / merge-with-N / refine.
State the literature basis.)

## Additional mechanisms the literature supports

(One subsection per mechanism the working hypothesis missed, if any. State
its name, what it does, what literature endorses it, and whether it is
tractable at our scale.)

## Empirical viability at personal scale

Which of the surviving mechanisms are tractable at 1K–10K entities,
single-user, multi-domain, single-machine? Which need 100K+ to behave
non-degenerately? Cite scale claims from the source literature where
available.

## Recommended decomposition for Round 6 to ratify

A single explicit answer:

- How many Learn mechanisms?
- Which ones?
- What is the definition of Learn that justifies the cut?

## References

(Standard academic citation format. Cite primary sources, not just survey
papers. If a claim is uncited, mark it as your own inference.)
```

**Target length:** 1500–3000 words.
**Honesty constraint:** where the literature is contested, name the camps.
Where it is sparse or absent on a question, say so plainly. *"No canonical
answer"* beats a confabulated answer.

---

## Out of scope

- Implementation suggestions, code, file changes, schema diffs.
- Project-execution recommendations ("first build X, then Y").
- Re-litigating Rounds 1–5 of the project's deliberation.
- Domain-specific operations (10x / investing). The question is what
  *generally* a learning operation is, not what it is for any one domain.

---

## Why the multi-model dispatch

Three parallel models reduce the risk of any one model's training
distribution dictating the cut. We will synthesize across the three,
flag where they converge, and flag where they disagree (per the precedent
of Task #11 and §7.4 of the doc). Each model should respond
**independently**, without seeing the other two responses.
