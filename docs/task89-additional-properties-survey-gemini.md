# Additional Properties Survey — Gemini

## Summary
This survey proposes three additional Pass-1 enrichment properties—`epistemic_class`, `intellectual_lineage`, and `temporal_anchor`—to maximize the semantic value extracted during the initial LLM call. These properties are structurally clean, carry high downstream utility for compilation and query operations, and impose negligible marginal token or attention costs.

## Proposals

## epistemic_class

**Type:** `enum: [empirical-data | theoretical-framework | argumentative-thesis | subjective-anecdote | reference-documentation | speculative-futurology]`
**Required / Optional:** Optional
**One-line purpose:** Categorizes the epistemological nature and justification method of the source's content.
**Why the LLM is the right tool:** Evaluating the epistemic mode (how the author warrants their assertions) is purely semantic, demanding tone analysis and structural understanding of argumentation far beyond heuristics.
**Downstream consumer:** Pass-2 / compile / query layer / human Obsidian UX
**Cost concern:** Negligible. A simple 6-way enum classification adds almost zero tokens and requires no separate reasoning pass since it's assessed concurrently with substance.
**Tier (your call):** ★★ (strong)

## intellectual_lineage

**Type:** `string or null`
**Required / Optional:** Optional
**One-line purpose:** Identifies the prominent intellectual lineage, philosophical paradigm, or school of thought the author's analysis is situated within.
**Why the LLM is the right tool:** Lineage is often implicit; authors rarely explicitly write "I am writing this from a post-Keynesian perspective." The LLM detects this via specific jargon, underlying assumptions, and referenced concepts.
**Downstream consumer:** Pass-2 / compile / query layer / human Obsidian UX
**Cost concern:** Very low. Standard open-ended text field extraction; bounded by a brief string or null value.
**Tier (your call):** ★★ (strong)

## temporal_anchor

**Type:** `string or null`
**Required / Optional:** Optional
**One-line purpose:** Specifies the primary historical period, economic era, or decade that serves as the temporal context for the source's claims.
**Why the LLM is the right tool:** Heuristic date parsers extract every mentioned year (creating massive noise from random date references). The LLM determines the *primary structural context* (e.g., "1970s stagflation", "2008 financial crisis", or "contemporary/post-2020").
**Downstream consumer:** Pass-2 / compile / query layer / human Obsidian UX
**Cost concern:** Minimal. Short text field that does not dilute attention from the primary classification.
**Tier (your call):** ★★ (strong)

## Considerations
The locked properties are clean and well-structured, but adding the three proposed fields transitions the Pass-1 frontmatter from simple search metadata to a robust epistemological foundation for belief revision. In particular, pairing `epistemic_class` with `intellectual_lineage` ensures the downstream GraphDB knows not only *what* was claimed, but the *nature of the evidence* and the *paradigm-level assumptions* backing it.
