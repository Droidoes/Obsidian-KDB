# Pass-1 Prompt Review — Qwen CLI (qwen3.7-max)

**Reviewer:** Qwen CLI / qwen3.7-max  
**Date:** 2026-05-27  
**Guardrail compliance:** Single review file; no repo files modified.

---

## Summary

The prompt is **followable but under-specified in critical areas**. The JSON schema is clear enough to reproduce the structure, but several fields ask the model to produce values it has no visibility into (`entity_search_keys` requires guessing what entities exist in an unknown graph; `model`/`schema_version`/`prompt_version` are clearly not the model's job). The `entity_search_keys` instruction is the prompt's most ambitious ask and its weakest point — the model is told to "emit the slug form most likely to match an existing entity record" but has zero information about what entities exist. Responses show this gap: models emit plausible-sounding slugs but violate the "avoid emitting multiple variants" rule (Response 1 emits both `pet-reroll` and `buddy-reroll`). Daily-note classification is inconsistent (Responses 15-17 = noise, Response 18 = signal), suggesting the signal/noise boundary needs sharper examples.

---

## Findings

### F-1: `entity_search_keys` asks the model to optimize for an invisible target (critical)

**Severity:** critical  
**Quoted lines:** "These keys are matched against entity slugs by exact string comparison, with an alias-resolution layer that maps known variant slugs (and 'ALIAS_OF' edges) to their canonical form — so emit the slug form most likely to match an existing entity record directly"

**Problem:** The model has no visibility into:
1. What entities exist in the graph
2. What slug forms those entities use
3. What variants the alias-resolution layer handles

The instruction "emit the slug form most likely to match" is unactionable — the model is optimizing for an unknown target. The prompt provides examples but no guidance on the graph's coverage or naming conventions.

**Evidence from responses:**
- Response 1 (`Claude Code Buddy System`) emits `["pet-reroll", "buddy-reroll", "any-buddy", "cc-buddy"]` — four variants of the same concept, violating "avoid emitting multiple variants of the same entity." The model doesn't know whether `pet-reroll` or `buddy-reroll` exists in the graph, so it hedges by emitting both.
- Response 4 (`GraphRAG for Adaptive KB - GPT5.2`) emits `["synthetic-analyst-engine"]` — a specific system name that may or may not exist as an entity. The model is guessing.
- Response 15 (`Daily Notes__2026-05-25`) emits `["codex", "deepseek", "qwen", "gemini", "grok"]` — model names that are unlikely to be entities in a personal knowledge graph about value-investing and AI/ML concepts.

**Concrete fix:** Either:
- **(a)** Provide a sample of existing entity slugs (top 20-50 by support count) so the model can calibrate its emissions to actual graph coverage. This is the highest-value addition.
- **(b)** Reframe the instruction from "match existing entities" to "emit plausible entity candidates that a well-populated graph *might* contain." This is honest about the model's epistemic position and reduces the pressure to hedge with variants.
- **(c)** Drop the alias-resolution explanation entirely. The model doesn't need to know about `ALIAS_OF` edges — that's implementation detail. Just say: "Emit kebab-case slugs for concepts, people, and frameworks mentioned substantively. Prefer full names over surnames. Avoid emitting multiple variants of the same concept."

---

### F-2: `model`, `schema_version`, `prompt_version` are not the model's job (high)

**Severity:** high  
**Quoted lines:**
- "`model`: the model name will be filled in by the deterministic layer. Emit 'model_to_be_filled' here."
- "`prompt_version`: '1.1.0'"
- "`schema_version`: 1"

**Problem:** These fields are clearly owned by the calling system, not the model. Asking the model to emit hardcoded placeholder values is:
1. Wasted tokens (the model generates text that will be overwritten)
2. Confusing (why am I emitting a placeholder? what does "model_to_be_filled" mean to me?)
3. Fragile (if the model hallucinates a different placeholder, validation fails)

**Evidence from responses:** All 20 responses correctly emit `"model": "model_to_be_filled"`, `"prompt_version": "1.1.0"`, `"schema_version": 1`. This is good compliance but bad design — the model is doing clerical work.

**Concrete fix:** Remove these fields from the prompt's output schema. The deterministic post-processor should stamp them after validation. If the schema requires them for structural reasons, emit them in the post-processor before validation, not in the LLM output.

---

### F-3: `override` block structure is confusing (high)

**Severity:** high  
**Quoted lines:** "`override`: emit `{"applied": null, "rule": null, "match": null, "llm_original": <your kdb_signal>, "reject_reason_cleared": null}`. The deterministic post-processor will overwrite this block if an override fires."

**Problem:** The model is asked to emit a 5-field object where 4 fields are always null and 1 field (`llm_original`) duplicates the `kdb_signal` it already emitted. The prompt explains the post-processor will overwrite this, so why emit it at all? This is the model doing bookkeeping for a downstream system.

**Evidence from responses:** All 20 responses emit the override block correctly. Response 15 (daily note, kdb_signal=noise) emits:
```json
"override": {
  "applied": null,
  "rule": null,
  "match": null,
  "llm_original": "noise",
  "reject_reason_cleared": null
}
```
This is 100% predictable and 100% redundant.

**Concrete fix:** Remove the `override` block from the model's output. The post-processor should construct it from the model's `kdb_signal` + any override logic. If the schema requires the field, the post-processor adds it before validation.

---

### F-4: `key_themes` format is unspecified (medium)

**Severity:** medium  
**Quoted lines:** "`key_themes`: list of 2-5 strings. Finer-grained themes than `domain` capturing substantive sub-topics within the source."

**Problem:** The prompt doesn't specify whether `key_themes` should be:
- Plain prose strings ("Claude Desktop Cowork VM troubleshooting")
- Kebab-case slugs ("claude-desktop-cowork-vm-troubleshooting")
- Something else

`entity_search_keys` explicitly requires kebab-case, but `key_themes` is silent. This creates inconsistency.

**Evidence from responses:**
- Response 1: `"key_themes": ["claude-code-buddy-system", "deterministic-generation", ...]` — kebab-case
- Response 2: `"key_themes": ["Claude Desktop Cowork VM troubleshooting", "Hyper-V repair", ...]` — plain prose with spaces and capitalization
- Response 15: `"key_themes": ["pipeline architecture", "domain classification", ...]` — plain prose

The model is inconsistent because the prompt is ambiguous.

**Concrete fix:** Add explicit format guidance. Either:
- "Format: plain prose strings (e.g., 'Claude Desktop troubleshooting')" — if themes are for human readability
- "Format: kebab-case slugs (e.g., 'claude-desktop-troubleshooting')" — if themes feed into entity_search_keys or downstream slug-based systems

Given that `entity_search_keys` instruction #1 says "Each item in `key_themes` (themes themselves are often already entity slugs)," kebab-case is likely the intended format. Make this explicit.

---

### F-5: Daily-note signal/noise classification is inconsistent (medium)

**Severity:** medium  
**Quoted lines:** "Pick 'noise' if the source is workflow/task tracking, conversational fragments, logs, empty content, or meta-commentary without substantive content."

**Problem:** The boundary between "workflow/task tracking" and "substantive knowledge content" is fuzzy for daily notes that document architectural decisions. Responses 15-17 (daily notes from 2026-05-25 to 2026-05-27) are classified as `noise` with reject_reasons like "Workflow/task tracking and meta-commentary without substantive knowledge content." Response 18 (daily note from 2026-05-28) is classified as `signal` with summary "This source documents an end-to-end design session for the kdb-orchestrate pipeline, settling component architecture..."

All four are daily notes documenting software development work. The difference: Response 18's content is more architecturally substantive (settling component contracts, explicit pipeline membership via pipeline_id tag), while 15-17 are more task-tracking oriented. But the prompt's rule doesn't distinguish these — "workflow/task tracking" could apply to all four.

**Evidence from responses:** The model is applying judgment (Response 18 *is* more substantive), but the prompt doesn't give it tools to make this distinction consistently. A different model might classify all four as noise (strict reading) or all four as signal (lenient reading).

**Concrete fix:** Add a clarifying example in the signal/noise section:
- "Daily notes documenting architectural decisions, settled contracts, or design rationale → signal (substantive knowledge content)"
- "Daily notes that are pure task-tracking (what I did today, bugs fixed, commits made) → noise (workflow tracking)"

This gives the model a decision procedure for the ambiguous case.

---

### F-6: `confidence` has no calibration guidance (low)

**Severity:** low  
**Quoted lines:** "`confidence`: 0.0 to 1.0. Your confidence in the kdb_signal call."

**Problem:** The prompt doesn't specify what confidence values mean. Is 0.5 "unsure"? Is 0.7 "moderately confident"? Is 0.9 "very confident"? Without calibration, the model defaults to high confidence (almost all responses are 0.9-1.0), which makes the field uninformative.

**Evidence from responses:**
- 18/20 responses have confidence ≥ 0.9
- Response 3 (daily note, noise) has confidence 1.0 — very confident it's noise
- Response 1 (Claude Code Buddy System, signal) has confidence 0.9 — very confident it's signal

No response has confidence < 0.9, which suggests the model is not using the field as intended.

**Concrete fix:** Add calibration anchors:
- "0.9-1.0: very confident (clear signal/noise, unambiguous domain/source_type)"
- "0.7-0.89: moderately confident (some ambiguity, but best choice is clear)"
- "0.5-0.69: uncertain (multiple plausible classifications, picked the best)"
- "<0.5: very uncertain (genuinely ambiguous, consider flagging for human review)"

This gives the model a decision procedure and makes the field informative.

---

### F-7: "GraphDB-input section" and "Audit section" are meaningless to the model (low)

**Severity:** low  
**Quoted lines:** "### GraphDB-input section" and "### Audit section"

**Problem:** These section headers use internal vocabulary ("GraphDB", "Audit") that gives the model no actionable signal. The model doesn't know what GraphDB is, what "input" means in this context, or what the audit section audits. The headers are organizational scaffolding for the human author, not instructions for the model.

**Concrete fix:** Remove the section headers or replace with model-actionable labels:
- "### Classification fields" (for kdb_signal, domain, source_type)
- "### Content description fields" (for author, summary, key_themes, entity_search_keys)
- "### Confidence and metadata fields" (for confidence, uncertainty_reason, reject_reason)

Or just remove the headers entirely — the field descriptions are self-contained.

---

### F-8: Domain catch-all disambiguation is unclear (low)

**Severity:** low  
**Quoted lines:**
- "`science-technology` — Science & Technology (catch-all): ...Use ONLY when you can articulate in one sentence why none of #1–7 applies."
- "`undecided` — Undecided: Residual catch-all for genuinely uncategorizable content. Use ONLY when no other domain in this list describes the content's primary nature."

**Problem:** Both `science-technology` and `undecided` are catch-alls, but the prompt doesn't clarify when to use which. The boundary rule says:
- `science-technology`: "use ONLY when no specific S&T domain (#1-7) fits AND you can articulate why"
- `undecided`: "use ONLY when no other domain in this list describes the content's primary nature"

But what if content is scientific/technical but doesn't fit #1-7? Is that `science-technology` or `undecided`? The prompt implies `science-technology` is for S&T content that doesn't fit the specific S&T domains, while `undecided` is for non-S&T content that doesn't fit any domain. But this is not explicit.

**Concrete fix:** Add a clarifying sentence:
- "`science-technology`: for scientific or technical content that doesn't fit domains #1-7 (ai-ml through physics)"
- "`undecided`: for non-scientific content that doesn't fit domains #9-22 (value-investing through lifestyle)"

This makes the two catch-alls mutually exclusive.

---

## Cuts and additions

### What to remove (noise/bloat):

1. **`model`, `schema_version`, `prompt_version` fields** (F-2) — not the model's job
2. **`override` block** (F-3) — redundant bookkeeping
3. **"GraphDB-input section" and "Audit section" headers** (F-7) — meaningless to the model
4. **Alias-resolution explanation in `entity_search_keys`** (F-1) — implementation detail the model doesn't need

### Single highest-value addition:

**Provide a sample of existing entity slugs** (F-1, option a). Show the model the top 20-50 entity slugs by support count (or a representative sample across domains). This transforms `entity_search_keys` from "guess what might exist" to "pick from what does exist," dramatically improving hit rate and reducing variant emissions.

If this is not feasible (graph is too large, slugs change too frequently), then reframe the instruction (F-1, option b) to be honest about the model's epistemic position: "Emit plausible entity candidates — concepts, people, frameworks that a well-populated knowledge graph might contain. Don't worry about exact matches; the system handles alias resolution."
