# Pass-1 Prompt Review & Recommendations (Task #95)

**Reviewer:** agy (Antigravity / Gemini 3.5 Flash)
**Date:** 2026-05-30

---

## 1. Summary

The Pass-1 prompt (`rendered_pass1_prompt.txt`) is highly detailed and structurally analytical, establishing excellent guidelines for classifying knowledge graph inputs. However, its followability is severely degraded by **calling-system leakages** (forcing the model to emit static metadata, dummy placeholders, and empty post-processing structures) and **un-anchored placeholders** that confuse LLM generation engines and trigger fatal pipeline validation crashes. By stripping these system-level concerns, providing a copy-pasteable JSON output skeleton, and refining the formatting constraints for key themes, the prompt can be made 100% robust, cheaper to execute, and completely immune to validation-induced failures.

---

## 2. Findings

### **Finding F-1: Prompt-Induced Validation Crash via Un-anchored Placeholder**
*   **Severity:** Critical
*   **Quoted Line:** `Line 185: - override: emit {"applied": null, "rule": null, "match": null, "llm_original": <your kdb_signal>, "reject_reason_cleared": null}.`
*   **Problem:** The prompt instructs the model to output a JSON object containing an unquoted human-readable placeholder `<your kdb_signal>`. Since this is syntactically invalid JSON notation, it introduces severe ambiguity for LLMs attempting structured generation. In the real run, this un-anchored placeholder caused the model to emit `null` (None) for `override.llm_original` in Response 21 (`How Not to Age`), which directly violated the validation schema enum `['signal', 'noise']` and crashed the entire ingestion pipeline.
*   **Fix:** **Remove the `override` block entirely from the LLM prompt.** This block is a pure post-processing audit concern that belongs exclusively to the calling Python system (see F-2).

### **Finding F-2: Severe Leak of Calling-System Concerns (Field Ownership Violation)**
*   **Severity:** High
*   **Quoted Line(s):**
    *   `Line 181: - prompt_version: "1.1.0"`
    *   `Line 182: - model: the model name will be filled in by the deterministic layer. Emit "model_to_be_filled" here.`
    *   `Line 184: - schema_version: 1`
    *   `Line 185: - override: emit {"applied": null, "rule": null, "match": null, "llm_original": <your kdb_signal>, "reject_reason_cleared": null}.`
*   **Problem:** The prompt forces the LLM to output static version numbers (`1.1.0`, `1`), a hardcoded dummy string (`"model_to_be_filled"`), and a complex nested audit block of static `null` values. The LLM has zero agency over these fields; they are 100% owned by the calling system. Wasting input/output tokens to force the LLM to echo back static system constants increases latency, increases API costs, and introduces unnecessary validation and syntax failure surfaces.
*   **Fix:** **Prune `prompt_version`, `model`, `schema_version`, and `override` from the LLM prompt contract entirely.** The calling Python script should automatically inject these static metadata fields and the default audit block into the JSON envelope *after* receiving the LLM's clean, high-value classification payload.

### **Finding F-3: Meaningless Database Implementation Jargon**
*   **Severity:** Medium
*   **Quoted Line(s):**
    *   `Line 121: ...slug candidates designed to seed a downstream context-loader... with an alias-resolution layer that maps known variant slugs (and "ALIAS_OF" edges) to their canonical form...`
    *   `Line 187: ...The deterministic post-processor will overwrite this block if an override fires.`
*   **Problem:** Explaining downstream database mechanics (GraphDB context-loaders, `ALIAS_OF` edges, deterministic post-processors) represents pure cognitive noise for an LLM. An LLM cannot execute database lookups or post-process its own outputs; this jargon distracts the model from its operational classification task.
*   **Fix:** Simplify the description to focus purely on the operational constraint:
    > `"entity_search_keys: list of up to 10 lowercase kebab-case strings capturing notable people, organizations, concepts, frameworks, or named ideas substantively mentioned in the source. Emit the primary canonical form of each concept (e.g., 'warren-buffett', not 'buffett') and avoid speculative keywords."`

### **Finding F-4: Inconsistent Case and Format in `key_themes`**
*   **Severity:** Medium
*   **Quoted Line:** `Line 119: - key_themes: list of 2-5 strings. Finer-grained themes than domain capturing substantive sub-topics within the source.`
*   **Problem:** The prompt does not specify a formatting rule or case standard for `key_themes`. Consequently, in Response 2 (`Claude Desktop Cowork VM`), the model emitted Title Case space-separated strings (`"Windows service management"`, `"MSIX cleanup"`), whereas in Response 1 (`Claude Code Buddy System`), it emitted lowercase kebab-case slugs (`"claude-code-buddy-system"`, `"fnv-1a"`). This divergence is caused by the prompt's own ambiguity, forcing the model to guess between natural prose and slug formats.
*   **Fix:** Add a strict format instruction to the `key_themes` definition:
    > `"key_themes: list of 2-5 strings. Format: lowercase, plain English prose (e.g., 'machine learning', 'portfolio construction') or lowercase kebab-case for specific technical identifiers (e.g., 'fnv-1a')."`

### **Finding F-5: Missing Personal Note / Synthesis Source Type**
*   **Severity:** Low
*   **Quoted Line:** `Line 920: "source_type": "other"` in Response 19 (`Andrew Weil Breath Method`)
*   **Problem:** In Response 19, the model classified a user-created reading summary/note as `"other"` because none of the 21 predefined source types fit a generic personal note or synthesis. The model was forced to write `other_reason`: *"User-created note summarizing breathing exercises from multiple sources..."* This indicates a clear vocabulary gap.
*   **Fix:** Add `personal-note` or `synthesis` as a 22nd enum option in `source_types.json` for user-authored reading summaries, learning syntheses, and study guides.

### **Finding F-6: Substance Classification Inconsistency in Multi-mode Notes**
*   **Severity:** Low
*   **Quoted Line:** `Line 17: - kdb_signal: "signal" or "noise"... Pick "noise" if the source is workflow/task tracking...`
*   **Problem:** In Response 15 (`Daily Notes__2026-05-25`), the model classified the daily note as `"noise"` because it contained "deferred tasks" and "reviewer feedback". However, in Response 18 (`Daily Notes__2026-05-28`), the model classified the daily note as `"signal"` because it documented an "end-to-end design session". When a note contains a mixture of workflow tracking (noise) and high-value design decisions (signal), the model lacks a clear tie-breaker instruction.
*   **Fix:** Add a clear tie-breaker instruction to the `kdb_signal` rules:
    > `"Tie-breaker: If a source document contains both workflow/task tracking and substantive design decisions or architectural knowledge, prioritize 'signal' to ensure downstream preservation."`

### **Finding F-7: Under-utilized Uncertainty Elicitation**
*   **Severity:** Low
*   **Quoted Line:** `Line 177: - uncertainty_reason: string or null. When confidence < 0.6 OR when kdb_signal=signal but with doubt, populate with the doubt's nature.`
*   **Problem:** Across all 20 successful responses, `uncertainty_reason` was uniformly emitted as `null`, even in responses with lower confidence scores (e.g., `0.9` in Responses 1, 17, 19). The threshold `confidence < 0.6` is too low because LLMs are inherently overconfident.
*   **Fix:** Adjust the threshold and clarify the trigger condition:
    > `"uncertainty_reason: string or null. Required if confidence is less than 1.0, or if you had to resolve a close boundary call (e.g. between ai-ml and software). Detail the reason for your doubt or the boundary conflict; emit null otherwise."`

### **Finding F-8: Superfluous File Path Leakage Biasing Substance-Only Judgments**
*   **Severity:** Low
*   **Quoted Line:** `Line 194: Path: Example/Some Note.md`
*   **Problem:** The prompt instructs the model: `"Judge content substance only. Do not consider file location, file name, or any non-content metadata in your judgment."` Yet, the prompt immediately provides the full file path (e.g., `Path: Life-Health-Wellbeing__Andrew Weil Breath Method`). Providing the file path leaks folder-level metadata and heavily biases the model's domain classification (e.g., seeing `Life-Health-Wellbeing` guarantees a `health-wellbeing` domain classification).
*   **Fix:** **Omit the `Path:` line from the prompt entirely.** The raw markdown body is more than sufficient for substance-only classification.

---

## 3. What Was Checked and Found Sound

*   **Substantive Signal Filtering:** The model successfully distinguished between mundane task lists (Response 15, 16, 17) and rich architectural design logs in Daily Notes (Response 18), showing that the core definition of `kdb_signal` is conceptually robust.
*   **Domain Disambiguation:** Domain selections (e.g., classifying `Dan Koe` as `psychology` and `Borda/Condorcet` as `software`) were highly coherent and aligned perfectly with the boundary guidelines.
*   **JSON Syntax Validity:** Across all 20 successful runs, the JSON structure was syntactically perfect, proving the model is highly capable of structured generation even without strict JSON schema enforcement at the API layer.

---

## 4. Recommended Prompt Restructure (The Concrete Fix)

To establish a bulletproof, zero-leak contract, we should provide the model with a **blank JSON skeleton** showing exactly the expected fields and omitting all calling-system variables.

**Recommended final section for the prompt:**

```markdown
## Output Format

Return ONLY a valid JSON object matching the following structure. Do not include markdown code block backticks (```json) or any text outside the JSON.

{
  "kdb_signal": "signal" | "noise",
  "domain": "ai-ml" | "software" | ... (select one ID),
  "source_type": "blog" | "article" | ... (select one ID),
  "author": string or null,
  "summary": "1-3 sentences plain prose distilling the core substance",
  "key_themes": [string, ...],
  "entity_search_keys": [string, ...],
  "confidence": float (0.0 to 1.0),
  "uncertainty_reason": string or null,
  "reject_reason": string or null (required if kdb_signal is "noise"),
  "other_reason": string or null (required if source_type is "other")
}
```
