# Pass-1 Prompt Review — Deepseek (2026-05-29)

## Summary

This prompt is **followable at a structural level** — all 20 successful responses produced valid JSON with correct field names, the signal/noise gate worked correctly, and domain/source_type selections are mostly defensible. However, the prompt has two clear gaps that degrade output consistency: (1) `key_themes` has **no format specification**, causing format divergence across responses (natural-language phrases vs kebab-case); (2) three **system-owned boilerplate fields** (`override`, `model`, `prompt_version`) are asked of the model unnecessarily, wasting tokens and causing the one observed failure (`override.llm_original: null` in response #21). The boundary rules and entity_search_keys instructions are thorough but contain anthropomorphic reasoning gates the model cannot execute.

---

## Findings

### 1. `key_themes` has no format specification — causes output divergence

- **Severity:** high
- **Lines:** 119-120 ("list of 2-5 strings. Finer-grained themes than `domain` capturing substantive sub-topics within the source.")
- **Problem:** The prompt never specifies a format for `key_themes` strings. Unlike `entity_search_keys` (which has explicit kebab-case formatting rules at lines 146-150), `key_themes` is left as untyped "strings." The model guesses.
- **Evidence from responses:**
  - Response #2: `"key_themes": ["Claude Desktop Cowork VM troubleshooting", "Hyper-V repair", "MSIX cleanup", ...]` — natural-language phrases with spaces, Title Case, inconsistent capitalization.
  - Response #4: `"key_themes": ["qualitative investment research", "knowledge graphs", "large language models", ...]` — natural-language phrases.
  - Response #20: `"key_themes": ["behavior-change", "identity-transformation", "goal-setting", ...]` — kebab-case, matching entity_search_keys style.
  - 12 of 20 responses use natural-language key_themes; 8 use kebab-case or mixed.
- **Why this matters:** `key_themes` is mechanically appended to `summary` as `"Themes: X, Y, Z."` (D-89-19) — if half your sources have natural-language themes and half have kebab-case slugs, the summary text sent to Pass-2 is inconsistent. Also, the prompt's own examples (lines 154-172) show kebab-case themes inside the entity_search_keys examples, which implicitly suggests kebab-case but never states it.
- **Fix:** Add explicit format spec: `"Format: lowercase, hyphen-separated (kebab-case), e.g. \"value-investing\", \"attention-mechanism\". Prefer slug-style concise terms. Avoid natural-language phrases."` Place it immediately after line 120, before the entity_search_keys section.

---

### 2. `override` block is system-owned boilerplate the model shouldn't emit

- **Severity:** high (caused the only observed failure)
- **Lines:** 185-187 ("emit `{\"applied\": null, \"rule\": null, \"match\": null, \"llm_original\": <your kdb_signal>, \"reject_reason_cleared\": null}`. The deterministic post-processor will overwrite this block if an override fires.")
- **Problem:** The model is asked to emit a 5-field JSON object where 4 fields are always `null` literals and only `llm_original` carries a real value (the model's own `kdb_signal`, which is already present elsewhere in the output). This is wasteful (tokens spent on boilerplate) and fragile — the model can emit `null` for `llm_original` even when the instruction is clear.
- **Evidence:** Response #21 (`How Not to Age`) failed with: `"override.llm_original: None is not one of ['signal', 'noise']"` — the only failure in 21 calls was on this field. The model emitted `null` instead of its `kdb_signal` value. Even though the instruction `<your kdb_signal>` is unambiguous, it's a self-referential instruction (the model must copy its own output value into a nested object) — inherently more error-prone than emitting a single value.
- **Fix:** Remove `override` from the prompt entirely. The deterministic post-processor already constructs the override block from the model's `kdb_signal` plus its own override logic. The system knows the model's `kdb_signal` — it's in the parsed envelope. No need to ask the model to echo it. This saves ~30 tokens per response and eliminates the #21 failure class.
- **If removal is too invasive for this review round:** At minimum, rephrase as a simpler instruction: `"llm_original": "<copy your kdb_signal value here>"` — the current `<your kdb_signal>` syntax looks like a template variable the model might interpret as a placeholder rather than a copy instruction.

---

### 3. `model` and `prompt_version` are system-owned placeholders

- **Severity:** medium
- **Lines:** 181 ("`prompt_version`: \"1.1.0\"") and 182-183 ("`model`: the model name will be filled in by the deterministic layer. Emit \"model_to_be_filled\" here.")
- **Problem:** The model emits two literal-string placeholders that the calling system knows at call time. `prompt_version` is a system constant; `model` is literally known to the caller (it chose the model). These are pure token waste — the system should stamp them after the LLM call.
- **Evidence:** All 20 successful responses emit the exact literals correctly. This is not a correctness issue, but it's unnecessary complexity in the prompt contract and wastes tokens.
- **Fix:** Move both to the system's post-processing step. Remove from prompt output schema. If the schema validator requires them, have the deterministic layer inject them before validation. This also eliminates the coordination risk: if `prompt_version` changes, only one place (the code constant) needs updating, not the prompt text too.

---

### 4. Domain boundary rules use undefined notation (↑, ↓, ↔, ⇄)

- **Severity:** medium
- **Lines:** 85-97 (boundary disambiguation rules)
- **Problem:** The boundary rules use arrow symbols without definition:
  - `ai-ml ↑ software ↑ hardware` (line 87) — does ↑ mean "prefer over"? "operates above"? "is a parent of"?
  - `neuroscience-cognition ↑ biology` (line 88) — same ambiguity.
  - `psychology ↑ neuroscience-cognition` (line 89).
  - `value-investing ↔ economy-markets` (line 92) — ↔ vs ⇄ on line 96 (`geopolitics ⇄ history`). Are these different?
  - `literature ↔ philosophy` (line 93).
- **Risk:** The model might interpret these as domain hierarchy, preference ordering, or something else entirely. In practice, the model's domain selections are mostly correct, suggesting it either ignores the notation or correctly infers "prefer the first domain over the second in ambiguous cases." But the notation is the author's shorthand, not a defined instruction.
- **Fix:** Replace symbols with explicit prose. Example: `"ai-ml ↑ software ↑ hardware"` → `"When content spans the compute stack, classify by its primary layer: AI algorithms/models → ai-ml; OS/dev tools/programming → software; chips/silicon/electronics → hardware."` This is already partially done in the prose on each line — just drop the symbols and keep the prose.

---

### 5. Anthropomorphic reasoning gates ("articulate in one sentence," "believe likely have entity records")

- **Severity:** medium
- **Lines:** 35 ("Use ONLY when you can articulate in one sentence why none of #1–7 applies. If you cannot articulate that reason, re-examine #1–7 first."), 77 (same pattern for `other` source_type), 141-145 ("concepts that are substantively referenced or load-bearing to the source's core argument, and that you believe likely have their own entity records in a well-populated graph")
- **Problem:** These instructions ask the model to perform introspective reasoning as a gating condition ("articulate in one sentence") or to make judgments based on knowledge it doesn't have ("believe likely have their own entity records in a well-populated graph"). An LLM in a single forward pass cannot "first try to articulate, then re-examine if it fails" — it either emits the catch-all or doesn't. The "believe likely have entity records" instruction asks the model to guess at the contents of a graph it has never seen.
- **Evidence:** These instructions don't appear to cause harm in the observed responses (no inappropriate `undecided` or `other` uses driven by gate failure). But they add noise and false precision to the prompt. Response #19 uses `source_type=other` with a legitimate reason, which the gate instruction correctly permits.
- **Fix for lines 35/77:** Simplify to: `"Use only as a last resort when no other domain applies."` or `"Prefer any specific domain over undecided. Use undecided only when genuinely unclassifiable."`
- **Fix for lines 141-145:** Replace with: `"Closely-related concepts that are substantively referenced in the source."` Drop the speculation about graph contents.

---

### 6. `entity_search_keys` rule #1 is circular — causes confusion about key_themes relationship

- **Severity:** low
- **Lines:** 130 ("Each item in `key_themes` (themes themselves are often already entity slugs)")
- **Problem:** Rule #1 says to include each `key_themes` item in `entity_search_keys`. But if `key_themes` items are natural-language phrases (as many responses produce), including them verbatim in `entity_search_keys` produces non-kebab-case slugs that won't match any entity. This rule only works when `key_themes` uses kebab-case format — which the prompt doesn't require. The parenthetical "(themes themselves are often already entity slugs)" is system-design context the model can't verify.
- **Evidence:** In responses where key_themes uses natural language (e.g., #2: "Claude Desktop Cowork VM troubleshooting"), the entity_search_keys list does NOT include those phrases verbatim — the model correctly converts to kebab-case slugs. The model is ignoring rule #1 in practice because it contradicts the kebab-case format requirement.
- **Fix:** After fixing finding #1 (key_themes format spec), rule #1 becomes coherent: "Include each key_theme (they are already in kebab-case slug format)." Or drop rule #1 entirely — the entity_search_keys generation is richer than just echoing key_themes, and the model doesn't need the reminder.

---

### 7. `source_type` for instructional/how-to content has no dedicated category

- **Severity:** low
- **Lines:** 52-77 (source_type list)
- **Problem:** The source_type vocabulary has `documentation` ("product/instructional reference — reader does") and `blog` ("personal blog post"). But a personal how-to guide or tutorial sits ambiguously between them. `documentation` is defined as product/API reference in a navigable format; `blog` is defined by publication venue. A user-authored breathing-exercise guide or CLI tutorial isn't clearly either.
- **Evidence:** Response #1 (Claude Code Buddy System) → `blog`. Response #6 (Archiving Claude Conv) → `blog`. Response #9 (Obsidian CLI Skills) → `blog`. Response #2 (Cowork VM Fix) → `documentation`. Response #7 (Callouts reference) → `documentation`. Response #19 (Breath Method) → `other`. The boundary between `blog` and `documentation` for instructional content is blurry.
- **Fix:** Add a boundary rule: `"documentation ↔ blog: documentation = product/API/tool reference (technical, lookup-oriented); blog = personal instructional writing (narrative how-to, guide, tutorial). When the source is a personal how-to guide that reads like a tutorial, prefer blog."`

---

### 8. Domain misclassification: Borda/Condorcet voting theory → `software`

- **Severity:** low (single instance, prompt could improve)
- **Evidence:** Response #10 classifies a source about Borda count and Condorcet methods as `domain: "software"`. The source is purely mathematical — voting theory, preference aggregation, social choice. The `math-statistics-logic` domain description includes "decision theory" which covers voting/social-choice theory. The model likely defaulted to `software` because the source describes algorithms (Borda, Condorcet are named methods) and the model associated "algorithm" with software.
- **Problem:** The prompt lacks a boundary rule for `math-statistics-logic ↔ software`, and the `math-statistics-logic` description ("Pure and applied mathematics, probability, statistics, formal logic, decision theory, computational theory foundations") doesn't explicitly mention voting theory or social choice, which are classic decision-theory topics. The model may not map "voting methods" → "decision theory."
- **Fix:** Add to domain boundaries: `"math-statistics-logic ↔ software: algorithmic descriptions of mathematical methods (voting, optimization, graph algorithms) → math-statistics-logic when the contribution is mathematical; → software when the contribution is implementation/engineering."`

---

### 9. Unclear instruction: "Do not include the source body in your output"

- **Severity:** low
- **Lines:** 12-13 ("Do not include the source body in your output. Do not include any explanatory text outside the JSON.")
- **Observation:** This instruction is clear and well-followed (all responses are pure JSON). However, the instruction is redundant with structured-output behavior — the model naturally wouldn't re-emit the source body. Not harmful, but could be removed to tighten the prompt. Keep the second sentence ("no explanatory text outside JSON") — that's load-bearing.

---

### 10. Confidence values lack calibration guidance

- **Severity:** low
- **Lines:** 176 ("0.0 to 1.0. Your confidence in the kdb_signal call.")
- **Problem:** The prompt asks for a confidence score but gives no calibration rubric. Responses show: 1.0 for clear cases, 0.9-0.95 for most others, 0.9 for the one `other` source_type case. The model is guessing at a numeric confidence scale without guidance on what 0.7 vs 0.9 means.
- **Evidence:** All 20 responses use either 1.0 (4 cases) or 0.9-0.95 (16 cases). No response uses 0.5-0.85. This suggests the model defaults to a narrow high-confidence band regardless of actual uncertainty.
- **Fix (optional, low-priority):** Add a brief calibration hint: `"0.9+: clear-cut classification; 0.7-0.9: reasonable but with some ambiguity; 0.5-0.7: genuine uncertainty between two categories; <0.5: you are guessing."` Or drop the field if it isn't used downstream.

---

## What I checked and found sound

1. **Signal/noise gate works.** All 3 daily notes classified as `noise` (correct), the health report as `noise` (correct), all substantive sources as `signal` (correct). The "bias to signal when uncertain" instruction appears to be followed.
2. **JSON structure compliance.** All 20 successful responses have correct key names, correct types, correct nesting. The output schema is well-specified.
3. **`author` extraction.** Response #20 correctly extracts "Dan Koe" from content. All others correctly use `null` when unattributable.
4. **`summary` quality.** 1-3 sentence summaries are competent and substantive across all 20 responses. No hallucinations observed.
5. **Domain boundary rules (prose portions).** The prose descriptions (lines 87-97 right of the arrows) are clear and useful. The model's domain choices are mostly defensible.
6. **Source_type boundary rules.** Well-specified and the model follows them (e.g., response #11 correctly classifies a chat log as `chat-log`).
7. **entity_search_keys overall quality.** Strong entity extraction across domains — response #20's "dan-koe", "naval-ravikant", "alfred-adler" are precise; response #5's "warren-buffett", "charlie-munger", "philip-fisher" are well-chosen.
8. **The "Path: Example/Some Note.md" stub** (line 194) correctly doesn't leak file metadata to the model.
9. **The prompt's overall structure** (role → output schema → domain list → source_type list → boundary rules → other fields → source content) is logical and scannable.

---

## Cuts and additions

### What to remove

| Priority | Item | Reason |
|----------|------|--------|
| **High** | `override` block instruction (lines 185-187) | System-owned boilerplate; caused the only observed failure. System constructs it. |
| **Medium** | `model` field (lines 182-183) | System stamps it. Remove literal placeholder. |
| **Medium** | `prompt_version` field (line 181) | System stamps it. Coordination risk if changed. |
| **Medium** | Arrow symbols in boundary rules (lines 85-97) | Replace ↑/↓/↔/⇄ with explicit prose. |
| **Low** | Anthropomorphic gates (lines 35, 77) | "articulate in one sentence" → "use as last resort." |
| **Low** | entity_search_keys rule #4 (lines 140-145) | "believe likely have entity records" → drop speculation. |
| **Low** | "Do not include source body" (line 12) | Redundant; keep "no explanatory text outside JSON." |

### Single highest-value addition

**`key_themes` format specification.** Currently the single biggest gap between prompt intent and output consistency. Add after line 120:

> Format: lowercase, hyphen-separated (kebab-case), e.g. `"value-investing"`, `"attention-mechanism"`, `"breathing-exercises"`. Prefer concise slug-style terms. Avoid natural-language phrases with spaces.

This one addition would eliminate the format divergence across 12 of 20 responses.
