# Task #89 — Additional Properties Multi-Model Survey Prompt

**Purpose:** Sibling artifact to `docs/task89-component1-enrichment-blueprint.md` v0.1. A one-shot prompt fired at all five reviewers (Codex + Qwen CLI/qwen3.7-max + Grok Build + Deepseek + Gemini Pro Deep Research) asking each model to suggest **additional Pass-1 enrichment properties** the locked v0.1 schema is missing.

**Filed:** 2026-05-25 (Joseph 2026-05-25: "develop a prompt to ask all the llm models for suggestions").

**Methodology:** Parallel survey, NOT a review. Each model receives the same prompt + the same anchor docs. Responses come back independently. Synthesizer (Claude) folds suggestions into v0.2 of the v0.1 blueprint.

**Distinguishes from the v0.1 panel review:** the v0.1 review evaluates the blueprint architecture; this survey is open-ended "what else?" Both can fire in the same panel cycle.

---

## Prompt to each model

```
You are participating in a multi-model design survey for Task #89 — Component #1
(Enrichment) of the KDB Ingestion System. This is NOT a review. It is an open-ended
design contribution from you, as one of five independent models being asked the
same question.

CONTEXT (please read first):
- docs/task89-component1-enrichment-blueprint.md v0.1 (this is the blueprint
  you're augmenting, not reviewing)
- docs/task88-ingestion-pipeline-blueprint.md v0.2 (parent blueprint)
- docs/task88-nw4-domain-list-v0.4.md (the `domain` controlled vocabulary)

THE LOCKED PROPERTY SET (v0.1 §2):

Substantive properties (7):
  - kdb_signal: signal | noise        (the gate)
  - domain: <23 NW-4 v0.4 ids>        (substantive classification)
  - source_type: <NW-7 placeholder>   (source form)
  - author: <string or null>          (attribution)
  - summary: <1-3 sentences>          (prose distillation)
  - key_entities: list[string]        (raw mentions, unresolved)
  - key_themes: list[string]          (2-5 themes, free-form)

Audit fields (6):
  - confidence, uncertainty_reason, reject_reason
  - prompt_version, model, schema_version

Plus an optional `override` block if post-Pass-1 deterministic override fires.

PROPERTIES EXPLICITLY DROPPED in v0.1 (you may revive with reasoning):
  - time_period
  - language
  - property_tags (merged into key_themes for v0.1)

THE QUESTION:

The blueprint says the LLM is making one single call per source (per D-88-10
single-call discipline + bias to inclusion). The LLM has the source text + the
optional corpus_index in scope. While we have the LLM's attention on the source,
what ADDITIONAL properties would justify being added to the same single call?

Justification criteria for a proposed addition:
1. The property carries information ONLY the LLM can produce (heuristic / regex
   alternatives would be brittle).
2. The property is reusable downstream (Pass-2 / compile / queries / human
   navigation in Obsidian).
3. The marginal LLM-attention cost of including it does NOT degrade the locked
   property quality (the predeclared split trigger from D-88-10 applies).
4. The property doesn't duplicate something compile already produces.

Suggest 2-5 additional properties. For each one:

  ## <property_name>
  
  **Type:** <YAML type>
  **Required / Optional:** <stance>
  **One-line purpose:** <what it represents>
  **Why the LLM is the right tool:** <vs heuristic / regex / compile>
  **Downstream consumer:** <Pass-2 / compile / query layer / human Obsidian UX>
  **Cost concern:** <attention dilution risk, prompt-budget impact>
  **Tier (your call):** ★★★ (must) / ★★ (strong) / ★ (stretch)

REPO-MODIFICATION GUARDRAIL (CRITICAL — applies to all reviewers; esp. critical
because agy/gemini-3.5-flash-high is on a one-strike re-trial after previous
overreach):

Create EXACTLY ONE file in this CLI session. Your output file path depends on
your reviewer identity:

  - Codex:        docs/task89-additional-properties-survey-codex.md
  - Qwen CLI:     docs/task89-additional-properties-survey-qwen.md
  - Grok Build:   docs/task89-additional-properties-survey-grok.md
  - deepcode CLI: docs/task89-additional-properties-survey-deepseek.md
  - agy:          docs/task89-additional-properties-survey-gemini.md

Do NOT modify, create, or delete any other files in the repository.
Do NOT propose code patches, modify schemas, or change any other docs.
Your entire CLI session output must be confined to producing that one file.
Per docs/external-review-panel.md one-strike rule: implementation actions or
repo modifications outside the output file are grounds for de-selection from
future review cycles.

CONTENT GUARDRAILS:

- Stick to the question. Do NOT propose architectural changes to the blueprint
  outside the property set. Do NOT redesign Component #1.
- Do NOT propose properties that violate ratified discipline:
  - No edge / cross-cut declarations (per D-NW4-5)
  - No provenance / location / file-metadata properties the LLM would have to
    reason about (these belong to the deterministic post-LLM layer per
    feedback_post_llm_deterministic_override)
  - No "shape" language; describe what the property IS (per
    feedback_drop_the_word_shape)
- Do NOT propose properties that duplicate already-locked properties.

OUTPUT FORMAT:

  # Additional Properties Survey — <Your Model Name>

  ## Summary
  <1-2 sentences: how many you propose, your overall stance>

  ## Proposals
  <use the per-property block format above for each suggestion>

  ## Considerations
  <optional: cross-cutting observations on the property set as a whole,
   patterns you noticed, or risks the locked set hasn't addressed>

END OF PROMPT.
```

---

## Output collection

Each model's response lands at:

- `docs/task89-additional-properties-survey-<model>.md`
  - e.g., `task89-additional-properties-survey-codex.md`, `task89-additional-properties-survey-qwen.md`, etc.

Synthesizer (Claude) folds across all five responses in v0.2 of the v0.1 blueprint, applying the same convergence-pattern analysis used for NW-4 v0.2 panel (U/S/M/G/B labels).

---

## Firing sequence

Survey can fire **at the same time** as the v0.1 blueprint review — they ask different questions of the same models, on the same artifact set. One panel cycle, two outputs per reviewer.

Alternative sequence (if simpler for the user): survey first, fold results, then fire v0.1 review with the updated property set. Joseph's call.

---

**END OF SURVEY PROMPT ARTIFACT**
