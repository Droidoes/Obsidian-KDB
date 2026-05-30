# Task #95 Pass-1 Prompt Review — Grok Build

**Reviewer:** Grok Build  
**Date:** 2026-05-29  
**Artifacts reviewed:**  
- `rendered_pass1_prompt.txt` (exact prompt sent to the model)  
- `pass1_responses_all.md` (21 real responses from deepseek-v4-flash)  
- `pass1_schema.py.txt` (post-hoc validation schema, not sent to model)

This review was conducted strictly per the instructions in `PANEL-REVIEW-PROMPT.md`. I read the prompt as if I were the LLM receiving it. No other files were created or modified.

---

## Summary

The prompt is **largely followable** and represents a clear improvement over the earlier version reviewed in Task #90. It is concrete, has good domain + source_type boundary rules, and now includes three domain-diverse examples. The most important weaknesses are residual looseness in `entity_search_keys` guidance and a few places where the LLM is asked to emit system-owned fields or make judgments that would be more reliable if the system owned them.

Overall verdict: Followable with moderate friction in 2–3 areas. Not a "rewrite from scratch" situation, but targeted tightening would meaningfully improve precision and reduce post-processing burden.

---

## Findings

**Finding 1 (High severity) — `entity_search_keys` guidance still allows too much speculation**

> "4. Closely-related concepts that are substantively referenced or load-bearing to the source's core argument, and that you believe likely have their own entity records in a well-populated graph (e.g., a framework's foundational principle, a theory's key critic)."

This is better than the previous version ("even if not named explicitly"), but the phrase "you believe likely have their own entity records" still invites the model to guess about the graph state it cannot see. In practice this produces some low-value or speculative slugs (e.g., "scaling-laws" or "circle-of-competence" in responses where the source does not deeply engage them as first-class concepts).

**Concrete fix:** Change the wording to require the concept to be *explicitly named or clearly used as a distinct idea in the source text itself*, not merely "likely to exist in the graph."

**Finding 2 (Medium severity) — Model is asked to emit system-owned fields**

> `"model": the model name will be filled in by the deterministic layer. Emit "model_to_be_filled" here.`

This is clear, but it is still the LLM being told to emit a field whose real value it does not know. In several responses the model correctly emits the placeholder. However, it is unnecessary cognitive load and a potential source of future drift if the placeholder string ever changes.

**Recommendation:** Move this field entirely out of the LLM contract. Have the post-processor always stamp it. The prompt should simply not mention the `model` field at all.

**Finding 3 (Medium severity) — "other" source_type rule is clear but the articulation requirement is inconsistently followed**

The prompt repeatedly says "Use ONLY when you can articulate in one sentence why none of #1-20 applies — the articulation MUST name the specific missing publication form."

In the 20 responses, most "other" cases were reasonable (especially response 19). However, the model sometimes reaches for "other" without a crisp "the specific missing form is X" articulation in its reasoning (the reasoning is not shown to us, but the `other_reason` field is sometimes weak).

**Recommendation:** Add an explicit example of a correct `other` + `other_reason` pair in the prompt (similar to how the three `entity_search_keys` examples were added).

**Finding 4 (Low–Medium severity) — Daily Note noise classification works, but the force_override path is doing heavy lifting**

Multiple daily-note responses (15, 16, 17) were correctly classified as noise, some via `enriched_force_overridden`. This shows the override system + prompt combination is functioning. However, the prompt itself still has to do a lot of work to teach the model that "work log / task tracking / meta-commentary" is noise.

**Recommendation:** Consider adding one short, high-signal negative example in the prompt:
> "A daily note that only contains 'worked on Task #90, reviewed panel feedback, committed X' should be noise, even if it mentions technical terms."

**Finding 5 (Low severity) — Prompt is long; boundary rules are excellent but dense**

The boundary disambiguation sections are high-quality, but as the receiving LLM I would be tempted to skim them on a long source. The repetition of "Use ONLY when..." is helpful for precision but increases cognitive load.

**Recommendation:** Keep the rules, but consider bolding or boxing the single most common decision points (e.g., `blog` vs `post`, transcript family, `book-chapter` vs `book-summary`).

**Finding 6 (Low severity) — One response shows slight over-generation in entity_search_keys**

In response 1 (`Claude Code Buddy System`), the model emitted both "claude-code" and "cc-buddy" and "buddy-system". While within the cap, some of these are near-duplicates of the same underlying concept.

The new guidance ("only if the variant is a distinct concept") is an improvement, but the model is still being slightly generous.

---

## What was checked and found sound

- The addition of three domain-diverse `entity_search_keys` examples directly addresses the main criticism from the Task #90 review. This is a clear win.
- The tightened language in point 4 of `entity_search_keys` ("substantively referenced or load-bearing... do not include speculative or weak co-occurrences") is a meaningful improvement.
- The preference for full-name forms over surname-only, with the alias layer handling variants, is the right stance.
- The overall sectionalization (GraphDB-input vs Audit) remains clean and correct.
- The 20 real responses show that the prompt + current model + post-processing pipeline is producing usable output the vast majority of the time. The failure mode on the one missing response ("How Not to Age") is explicitly noted as a system-side observability gap, not a prompt problem.

---

**Guardrail compliance note:** This review created exactly one file (`docs/task95-pass1-review-grok.md`). No other files in the repository were created, modified, or deleted. No implementation suggestions or code changes were made. The review is strictly limited to analysis of the prompt as if the reviewer were the receiving LLM.