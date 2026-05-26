# Task #89 — v0.1 Blueprint Architecture Review Prompt

**Purpose:** Round-2 panel prompt for the Task #89 v0.1 blueprint architecture review. Asks reviewers to assess the v0.1 architecture (esp. the §6 wikilinks + corpus_index open decision), surface findings + OQs, and flag concerns on the post-LLM override mechanism (§4) and the no-GraphDB-writes-from-Pass-1 stance (§10).

**Filed:** 2026-05-25 (extracted from blueprint §16 as a standalone artifact for firing, parallel to the round-1 survey prompt).

**Methodology:** Same 5-CLI panel as round-1 (Codex + Qwen CLI/qwen3.7-max + Grok Build + deepcode CLI + agy/gemini-3.5-flash-high). agy remains on explicit one-strike trial — round-1 (property survey) passed cleanly; this round is the continuation of the same trial under a different (more substantive) prompt.

**Distinguishes from the round-1 property survey** (`docs/task89-additional-properties-survey-prompt.md`): the survey asked for property-additions only; this prompt asks for blueprint-architecture review. Property suggestions are explicitly OUT of scope for this round — round-1 collected them and they will be folded into v0.2 separately.

---

## Prompt to each model

```
You are reviewing Task #89 — Component #1 (Enrichment) v0.1 blueprint for the
KDB Ingestion System.

CONTEXT (please read first):
- docs/task89-component1-enrichment-blueprint.md — the blueprint under review
- docs/task88-ingestion-pipeline-blueprint.md v0.2 — parent blueprint
- docs/task88-nw4-domain-list-v0.4.md — the domain controlled vocabulary
- docs/graphdb-kdb-producer-contract.md v1.0 — existing producer contract
  (relevant to §10 alignment)
- docs/JOURNEY.md — three-iteration retrospective; the manifest.json →
  GraphDB-context-loader arc is relevant to the §10 no-GraphDB-writes stance

NOTE (round-1 already conducted): An additional-properties survey was
conducted in round-1 of this panel. Round-1 responses are at
docs/task89-additional-properties-survey-{codex,deepseek,gemini,grok,qwen}.md.
Property suggestions are OUT of scope for this round — round-1 collected them
and they fold into v0.2 separately. Focus this review on the v0.1 blueprint's
ARCHITECTURE.

1. REPO-MODIFICATION GUARDRAIL (CRITICAL — read first)

   Create EXACTLY ONE file in this CLI session. Your output file path depends
   on your reviewer identity:

     - Codex:        docs/task89-v0.1-review-codex.md
     - Qwen CLI:     docs/task89-v0.1-review-qwen.md
     - Grok Build:   docs/task89-v0.1-review-grok.md
     - deepcode CLI: docs/task89-v0.1-review-deepseek.md
     - agy:          docs/task89-v0.1-review-gemini.md

   Do NOT modify, create, or delete any other files in the repository.
   Do NOT modify code, schemas, configuration, blueprints, or other docs.
   Do NOT propose implementation patches or write code.

   Your entire CLI session output must be confined to producing your single
   review file. Violating this guardrail (e.g., editing other files,
   committing changes, modifying code) results in de-selection from future
   review cycles per the one-strike rule (docs/external-review-panel.md).

   Three of five reviewers are new to the panel: Qwen CLI (qwen3.7-max),
   Grok Build, deepcode CLI. agy/gemini-3.5-flash-high is on an explicit
   re-trial after previously being dropped for overreach; round-1 passed
   cleanly — this round is the continuation of the same trial.

2. REVIEWER ROLE

   - Identify factual errors, contradictions, scope gaps, missing OQs in the
     v0.1 blueprint
   - Recommend a path for the OPEN decision in §6 (Options A / B / C),
     with reasoning
   - Flag concerns about the post-LLM override mechanism (§4)
   - Flag concerns about the no-GraphDB-writes-from-Pass-1 stance (§10)
   - Cross-check the blueprint against the parent blueprint and the producer
     contract (anchors in §15 of the blueprint)
   - Cite specific section / decision IDs (e.g., "D-89-3", "§4.4") when
     raising findings

3. SCOPE BOUNDARIES (CRITICAL)

   - Do NOT propose new properties for the Pass-1 schema (out of scope this
     round per the round-1 note above)
   - Do NOT propose architectural changes to the parent blueprint (#88)
     outside of where #89 explicitly conflicts with it
   - Do NOT pre-lock decisions (D-89-X) you have not been asked to make
   - Do NOT use forbidden words in heading or assertion form: "Locked",
     "Ratified", "Final", "Complete", "Settled", "Approved" (review-only
     discipline per the hard-cap prompt precedent)
   - Do NOT self-elevate to project-team roles ("our review", "we should",
     "the team should"); use reviewer-external register

4. OUTPUT FORMAT (mirrors NW-4 v0.2 panel pattern)

   In your single review file, include these sections (use the headings):

   ## Convergence
   Where you agree with the v0.1 blueprint as-is.

   ## Findings
   F-1, F-2, ... each with section reference + recommendation.
   Use the **Recommendation:** or **Proposal:** prefix for any forward-looking
   statement. Do NOT use bare assertions.

   ## Open questions
   OQ-1, OQ-2, ... gaps you would want closed before implementation lands.

   ## Wikilink + corpus_index decision (§6)
   Your pick from Options A / B / C in §6 of the blueprint, with reasoning.
   You may propose A' / B' / C' variations if you see a useful refinement.

   ## Concerns on post-LLM override (§4)
   Anything misaligned with feedback_post_llm_deterministic_override or
   operational risks (precedence, audit trail, override semantics).

   ## Concerns on no-GraphDB-writes stance (§10)
   Anything misaligned with feedback_no_parallel_storage_to_authority or the
   manifest.json → GraphDB-context-loader arc lesson (per JOURNEY.md).
   Reach: does the deferral to v1.1+ as a second producer make sense, or
   should Pass-1 write GraphDB Source-level data in v1?

END OF PROMPT.
```

---

## Output collection

Each reviewer creates exactly one file at the path corresponding to their identity (see GUARDRAIL section above). The 5 responses are then synthesized by Claude into v0.2 of the blueprint, folding alongside the round-1 property-survey suggestions.

---

## Firing sequence

Fire after round-1 survey responses are committed (already done in commit `6eb793f`). Reviewers will see the round-1 survey files in the repo; the prompt above explicitly puts property suggestions OUT of scope for this round so they don't pattern-match.

---

**END OF PROMPT ARTIFACT**
