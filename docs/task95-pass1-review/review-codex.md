# Pass-1 Prompt Review — Codex

## Summary

The prompt is mostly followable for high-level classification, and the 20 captured responses show the model can usually produce parseable JSON. The main weakness is contract precision: several system-owned audit fields are pushed onto the model, and the prompt describes the object in prose instead of showing the exact JSON shape. The response sample also shows drift in field cardinality, slug/phrase format, and domain/source_type boundary calls.

## Findings

1. **High — deterministic audit fields are assigned to the model**

   **Quoted lines:** `prompt_version`: `"1.1.0"` (line 181), `model`: "the model name will be filled in by the deterministic layer. Emit "model_to_be_filled" here." (lines 182-183), `schema_version`: `1` (line 184), and `override`: emit `{... "llm_original": <your kdb_signal> ...}` (lines 185-188).

   **Problem:** These fields are caller-owned metadata, not content judgments. Asking the LLM to echo sentinel values and assemble an override audit object creates failure surface without adding semantic value. The known failed source demonstrates this: `How Not to Age` failed because `override.llm_original` was invalid (`None is not one of ['signal', 'noise']`) in `pass1_responses_all.md` lines 1013-1018.

   **Fix:** Remove `prompt_version`, `model`, `schema_version`, and `override` from the model-visible required output. Have the deterministic layer stamp them after parsing. If `llm_original` is needed, set it deterministically from parsed `kdb_signal`.

2. **High — exact JSON shape is not shown**

   **Quoted lines:** "Return ONLY a valid JSON object with these fields" (lines 12-13), followed by prose field descriptions rather than a complete object template.

   **Problem:** In soft JSON mode, the prompt text is the only contract. A prose list is more error-prone than a literal JSON skeleton, especially with nested `override`, nullable fields, and sentinel strings. The model succeeded 20 times, but the one captured failure is exactly in the nested audit object, not in the semantic classification.

   **Fix:** Add one complete canonical JSON object skeleton after the field descriptions, with every required key present and placeholder values of the right type. Better: if finding 1 is accepted, make the skeleton contain only semantic fields:

   ```json
   {
     "kdb_signal": "signal",
     "domain": "ai-ml",
     "source_type": "blog",
     "author": null,
     "summary": "...",
     "key_themes": ["..."],
     "entity_search_keys": ["..."],
     "confidence": 0.0,
     "uncertainty_reason": null,
     "reject_reason": null,
     "other_reason": null
   }
   ```

3. **High — `key_themes` and `entity_search_keys` format expectations conflict**

   **Quoted lines:** `key_themes`: "list of 2-5 strings" (lines 119-120). `entity_search_keys`: "Each item in `key_themes`" should be included (line 130), while entity keys must be lowercase kebab-case with no spaces (lines 146-150).

   **Problem:** The prompt does not say whether `key_themes` themselves should be prose phrases or slug strings. Examples use slug-like themes, but the actual field description allows arbitrary strings. The model oscillates: response 6 emits prose `key_themes` like `"Claude conversation archiving"` and `"Python script automation"` (lines 270-276), while its `entity_search_keys` are slugified and not exact copies (lines 277-288). Responses 4 and 5 also violate the 2-5 count with 7 `key_themes` each (`pass1_responses_all.md` lines 164-172 and 217-225).

   **Fix:** Decide ownership. If downstream wants slugs, rename to `key_theme_slugs` and require 2-5 lowercase kebab-case strings. If humans want readable phrases, state: "`key_themes` are human-readable phrases; `entity_search_keys` should include slugified equivalents of the important themes when useful, not necessarily exact copies."

4. **Medium — graph-internal language asks the model to reason about unavailable state**

   **Quoted lines:** "designed to seed a downstream context-loader" (lines 121-123), "The graph contains entities..." (lines 123-124), "matched against entity slugs by exact string comparison" (lines 125-126), and "alias-resolution layer ... ALIAS_OF edges" (lines 126-128).

   **Problem:** As the model, I do not know the actual graph contents or alias ledger. The instruction "emit the slug form most likely to match an existing entity record directly" asks me to infer private runtime state. This likely encourages broad, famous-name padding. Example: response 5 includes `warren-buffett`, `charlie-munger`, `philip-fisher`, `supabase`, `pgvector`, and `tosh-capital` (lines 226-237), mixing source-specific entities with inferred graph bait.

   **Fix:** Reframe this field as "extract/load-bearing slug candidates from this source only." Remove claims about exact graph lookup and alias internals, or say plainly: "You cannot know the graph; emit source-grounded candidates only."

5. **Medium — source type lacks a clear bucket for personal/reference notes**

   **Quoted lines:** `source_type` requires one listed ID, with `other` as last resort (lines 52-54), and `other` must name the missing publication form (lines 189-190).

   **Problem:** The vault contains user-authored notes that are neither blog posts, documentation, nor meeting/daily notes. The model uses `other` for `Andrew Weil Breath Method`, with `other_reason`: "User-created note summarizing breathing exercises from multiple sources..." (lines 918-956). That is probably a real source form in this vault, not an edge case.

   **Fix:** Add a `personal-note` / `reference-note` source_type, or add a boundary rule mapping user-created evergreen notes to an existing type. Without that, `other` will become a legitimate bucket rather than a vocabulary-expansion signal.

6. **Medium — domain boundary for formal methods vs software is under-specified**

   **Quoted lines:** `software` includes "CS algorithms" (line 29), while `math-statistics-logic` includes "decision theory" and "computational theory foundations" (line 31).

   **Problem:** This boundary is ambiguous for formal algorithmic or social-choice material. Response 10 classifies Borda/Condorcet relative ranking as `software` (lines 468-472), but by the prompt's own language it plausibly belongs in `math-statistics-logic` as voting theory / preference aggregation. The prompt does not name voting theory or social choice.

   **Fix:** Add a boundary rule: "Voting theory, ranking methods, preference aggregation, and social choice -> `math-statistics-logic` unless the source is about implementing them in software."

7. **Low — including `Path:` conflicts with the instruction not to use file location/name**

   **Quoted lines:** "Do not consider file location, file name, or any non-content metadata" (lines 6-7), but the prompt still includes `Path: Example/Some Note.md` (lines 192-195).

   **Problem:** This gives the model an attractive but forbidden signal. It is especially risky for `daily-note`, `domain`, and author/source_type decisions. The responses classify all Daily Notes as `daily-note` (lines 721-724, 771-774, 821-824, 870-873); that may be content-supported, but the prompt should not include forbidden evidence if the model is not supposed to use it.

   **Fix:** Remove `Path:` from the model prompt. If it must be present for debugging, label it outside the model-visible content or explicitly say: "The following path is for traceability only; do not use it for any field."

8. **Low — signal/noise guidance for daily logs needs a sharper distinction**

   **Quoted lines:** `noise` includes "workflow/task tracking, conversational fragments, logs" (lines 20-21), while uncertainty should bias to signal (lines 6-8).

   **Problem:** Daily notes can contain substantive architecture decisions and task logs in the same document. The model marks 2026-05-25/26/27 as `noise` (lines 721-746, 771-796, 821-845) but 2026-05-28 as `signal` (lines 870-893). That may be right, but the prompt does not define the threshold between "log with substantive decisions" and "substantive design note in daily-note form."

   **Fix:** Add one explicit rule: "For daily notes/logs, choose `signal` only if the note contains reusable concepts, design rationale, or decisions that stand alone outside the day's task tracking; otherwise choose `noise`."

## Cuts And Additions

**Cut:** Remove deterministic audit/stamping fields from the model contract: `prompt_version`, `model`, `schema_version`, and `override`.

**Single highest-value addition:** Add a complete JSON skeleton for the exact model-owned output object, immediately before "Source content to classify." This will reduce soft-JSON failures more than additional prose.
