# Round 5 External Review Prompt

Reusable prompt for soliciting independent second opinions from external LLM
agents (Codex CLI, Gemini CLI, etc.) on the Round 5 resolution of the kernel
question (`docs/what-is-the-ontology-for.md` §7).

## How to use

1. **Run the external agent from the repo root** (`~/Droidoes/Obsidian-KDB`) so
   the relative path `docs/what-is-the-ontology-for.md` resolves.
2. **Paste the prompt below** into the agent's session.
3. **(Optional for Gemini)** append: *"Where relevant, ground your assessment
   in the GraphRAG / HippoRAG / LazyGraphRAG / Pan et al. literature the doc
   references."*
4. **Fold the response back** into the deliberation as either §7.4
   (annotations on Round 5) or §8 / Exchange 6 (if the response pushes
   deliberation forward).

## Prompt

```
You are being asked for an INDEPENDENT SECOND OPINION on a multi-round
architectural deliberation between Joseph (project owner) and Claude on a
personal knowledge-graph project called "Obsidian-KDB". The full deliberation
lives at:

    docs/what-is-the-ontology-for.md

Please read the entire document. The key sections are:
- §5 — the kernel question restated
- §6 — Exchange 4 / Round 4 (Joseph's framing, research grounding,
        Claude's synthesis, and where Round 4 landed)
- §7 — Exchange 5 / Round 5 (Joseph's 8-point challenge, Claude's response,
        and where Round 5 landed) — this is the focus of your review

CONTEXT (so you know what's being deliberated):

  Philosophy A — humans curate signal at the door; graph RECORDS
                 pre-conferred meaning.
  Philosophy B — ingest broadly; meaning EMERGES from LLM extraction +
                 graph operations (GraphRAG community detection,
                 HippoRAG Personalized PageRank).

  Round 4 resolved the door-level question to B + X6 (mechanical exclusion
  only — drop .venv, node_modules, generated artifacts).

  Round 5 surfaced that Claude's closing Round 4 statement smuggled
  Philosophy A back in at the STRUCTURAL tier (typed schema, controlled
  vocabulary). Claude conceded. Position landed at "B with two
  calibrations":
    (C1) LLM-extracted, not human-defined — no controlled vocabulary;
         entities/relations/domain produced by the compiler.
    (C2) Domain as coordinate, not gate — LLM-tagged at compile output,
         queryable at runtime, never an ingestion filter.

  But Joseph and Claude DID NOT CONVERGE. Joseph holds a strong B-claim
  ("LLM + graph turn chaos into order"). Claude holds B-viable-hypothesis
  with empirical hedges (scale, cross-domain density). Joseph's [8] is
  load-bearing: "if A is right, no reason to do this project."

YOUR TASK — answer the following with specific paragraph citations from the
doc. State your OVERALL POSITION (B-strong / B-viable / some-other-stance)
at the top, then work through the questions. Be willing to disagree with
both Joseph AND Claude. Do not flatter the deliberation.

1. Is the latent-Philosophy-A diagnosis (Round 5) CORRECT? Claude conceded
   that the Round 4 §6.3 ¶419 claim — "everything powerful draws its power
   from structured extraction = schema = power" — was A smuggled in at the
   structural tier. Do you agree this is A? Or is it a defensible
   refinement of B that Joseph mis-attacked?

2. Are calibrations C1 and C2 actually B, or A-IN-DISGUISE?
   - C1: is "LLM-extracted, no controlled vocabulary" actually schemaless,
     or is the LLM acting as a human-curator-by-proxy?
   - C2: does "domain as coordinate at compile, not gate at ingest" hold
     operationally, or is "the LLM decides domain" effectively a gate by
     another name?

3. Is the schema reframe in §7.2 sound? Claude argues HippoRAG is
   schemaless, GraphRAG is schemaless-ish, and KDB's justifying operations
   don't need a typed schema. 10x's typed schema (supplies / is_bottleneck_for
   / competes_with) buys *domain-specific algorithms* — a different
   operation class than GraphRAG/HippoRAG. Is this distinction sound, or is
   Claude under-claiming what schemaless graphs can do (or over-claiming
   what 10x's schema is for)?

4. Is the 10x recalibration sound? Round 5 walks back the prior framing
   ("10x is already a complete answer for the domain of investing") and
   reframes 10x as a parallel deliberation-stage project, not a finished
   blueprint. Right call?

5. Are the empirical hedges the RIGHT ones? Claude's two hedges:
   (i)  scale gap — KDB ~70 entities vs. GraphRAG/HippoRAG benchmarks at
        1M+ tokens, hundreds of thousands of entities;
   (ii) cross-domain density — heterogeneous corpus may produce
        theme-clusters (B's promise) or degenerate domain-rediscovery
        clusters (failure).
   What hedges did Claude miss? Are these even the right two?

6. Is the §7.2 path forward sound — "unblock ingestion → build harvesters →
   run operations → re-open A/B if operations degenerate"? Or is this
   deferring a decision that should be made NOW, before more code lands?

7. Is Joseph's [8] claim load-bearing AND correct? "If A is right, no
   reason to do this project." Claude agreed. Are there defensible
   A-flavored projects worth building (automated curation, high-recall
   personal search, etc.) that this dismisses too quickly?

8. What major issues, blind spots, or contradictions in the deliberation
   did neither Joseph nor Claude surface?

Format: structured response, bullets fine. Cite paragraph or section numbers
when you disagree with specific claims. If your overall position is closer to
Joseph's B-strong than to Claude's B-viable-hypothesis, say so explicitly —
and vice versa.
```

## Notes for future rounds

- This prompt template works for any future kernel-question round that lands
  in `docs/what-is-the-ontology-for.md`. Replace the §7 reference and the
  "context" block with the current round's specifics; keep the structured-
  questions pattern and the explicit "do not flatter" framing.
- Past prompts asking external agents for general feedback tended to produce
  agreement-by-default. The structured-question + explicit-disagreement-
  invited pattern was added in Round 5 specifically to break that.
