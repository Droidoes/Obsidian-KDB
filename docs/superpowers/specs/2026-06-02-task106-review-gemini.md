# Task #106 Spec Review — Gemini Code-Review

## 1. Verdict
`GO-WITH-CHANGES`

---

## 2. Findings

### (a) Correctness/safety of the design

1. `[Severity: High]` · [compiled_source_response.schema.json:29-32](file:///home/ftu/Droidoes/Obsidian-KDB/compiler/schemas/compiled_source_response.schema.json#L29-L32) and spec §4b · The spec states that reference propagation must update "any `warnings[].related_slugs[]`". However, the schema defines the `warnings` property as a flat array of strings (`"items": { "type": "string" }`), not objects containing a `related_slugs` list.
   - *Why it matters*: Implementing the reference propagation exactly as described in the spec will lead to `KeyError` or schema violations during compilation, crashing the compile loop on warnings.
   - *Suggested change*: Strike the `warnings[].related_slugs[]` target from the propagation mapping. Renames should only target valid schema paths: `summary_slug`, `concept_slugs[]`, `article_slugs[]`, `pages[].slug`, `pages[].outgoing_links[]`, body `[[slug]]` tokens, and `log_entries[].related_slugs[]`.

2. `[Severity: High]` · [validate_source_response.py:101-103](file:///home/ftu/Droidoes/Obsidian-KDB/compiler/validate_source_response.py#L101-L103) and spec §4b · The spec mandates rewriting "whole `[[…]]` tokens, not substring-replace", but it fails to address how this rule handles valid Obsidian wikilink variations such as aliases (`[[slug|Display Text]]`) and anchor/section tags (`[[slug#section]]`).
   - *Why it matters*: A naive literal replacement of `[[old-slug]]` will miss links like `[[old-slug|Display Text]]` or `[[old-slug#header]]`. This leaves malformed/un-coerced slugs in page bodies, causing bidirectional-link check mismatches (since `outgoing_links` will be coerced, but body links will remain un-coerced) and leading to validation failures.
   - *Suggested change*: Use a regex matching function in [repair.py](file:///home/ftu/Droidoes/Obsidian-KDB/compiler/repair.py) (similar to `_WIKILINK_RE`) that extracts and replaces only the target slug portion within any wikilink pattern, keeping the anchor and display texts intact.

3. `[Severity: Low]` · Spec §4c · The spec does not define how the coercion transform handles a slug consisting entirely of hyphens (e.g. `---`). Under the proposed collapse-and-strip rule, `---` collapses to `-` and then strips to an empty string `""`.
   - *Why it matters*: Attempting to propagate a rename map with an empty target (`{ "---": "" }`) is invalid and can corrupt page intents or create unexpected behavior.
   - *Suggested change*: If the coercion transform results in an empty string, the coercion logic should treat it as unrecoverable, refuse to perform the rename, and allow validation to catch and fail the attempt.

---

### (b) Scope & conservatism calls

1. `[Severity: High]` · Spec §3 · The spec identifies a "content-fidelity hole" where `json-repair` might resolve invalid LaTeX delimiters (e.g., unescaped `\(n-1\)`) by silently stripping the backslash, producing parseable but corrupted math notation. The spec defers the solution to writing-plans.
   - *Why it matters*: Math expressions must be preserved perfectly. Since schema and semantic validators only check structure, corrupted LaTeX inside body text will silently pass validation and write bad data to the vault.
   - *Suggested change*: Rung-1 must incorporate a lightweight, deterministic *targeted backslash-escaping pre-processor* that runs prior to parsing (or if parsing fails). This pre-processor should find any backslash `\` that is not a valid JSON escape sequence (i.e., not followed by one of `["\\\/bfnrt]` or `u[0-9a-fA-F]{4}`) and escape it to `\\`. Only if parsing still fails after this step should `json-repair` be used as a fallback.

2. `[Severity: Medium]` · Spec §4a · The spec deliberately excludes lowercasing from the slug coercion transform to avoid guessing intent.
   - *Why it matters*: Under KDB policy D19, all slugs must be strictly lowercase. Casing mismatches (e.g., `Sleep-and-Aging` instead of `sleep-and-aging`) are extremely common LLM artifacts. Because casing carries no semantic distinction in KDB slug space, refusing to coerce casing needlessly triggers retries and quarantines.
   - *Suggested change*: Safely include lowercasing in the coercion transform. The updated slug transform should be: `slug.lower()`, collapse hyphens `-{2,}` to `-`, and strip edge hyphens. We should still reject spaces and non-alphanumeric punctuation, as those represent structural extraction failures.

---

### (c) Placement/integration with the real compiler flow

1. `[Severity: High]` · [compiler.py:341-352](file:///home/ftu/Droidoes/Obsidian-KDB/compiler/compiler.py#L341-L352) and spec §5 · The spec proposes running "re-validate (schema + semantic)" inside the compile attempt loop after coercion. However, in the real [compiler.py](file:///home/ftu/Droidoes/Obsidian-KDB/compiler/compiler.py), `semantic_check` is run *outside/after* the attempt loop.
   - *Why it matters*: If `semantic_check` is only executed outside the loop, a coerced payload that passes schema check but fails the semantic check will immediately break the loop, fail semantic checks, and quarantine without utilising the remaining retries. This breaks the spec's assertion that a bad repair will safely fall to the next rung (retry).
   - *Suggested change*: Unify the compilation validation gate by moving the `semantic_check` invocation inside the attempt loop. The loop should only break if `schema_ok and semantic_ok` are both True, allowing any semantic check failure (pre- or post-coercion) to correctly trigger the retry/quarantine flow.

---

### (d) Homes/contract

*None found.* The proposed locations (`common/util/json_repair.py` for Rung-1, `common/paths.py` for the transform, and `compiler/repair.py` for propagation) strictly respect the Phase B package split boundaries, maintaining `common` as a leaf.

---

### (e) Gaps/omissions

1. `[Severity: Low]` · Spec §7 · The spec proposes a flat mutual-exclusion taxonomy for logging resolutions: `clean · repaired-syntax · coerced-slug · retried · quarantined`.
   - *Why it matters*: These states are not mutually exclusive. A source can be retried and subsequently repaired via slug-coercion on its second attempt, which a flat logging structure cannot record cleanly.
   - *Suggested change*: Track attempts and repairs as separate variables in telemetry:
     - `attempts_run`: int (1 or 2)
     - `syntax_repaired`: bool
     - `slug_coerced`: bool
     - `final_status`: `success` | `quarantine`

---

## 3. Bottom line
The core design of a deterministic, validation-gated repair ladder is highly sound and will dramatically reduce stochastic retry waste. To proceed to implementation plans, we must address the Rung-1 fork: **we should not adopt `json-repair` as the primary resolver for unescaped LaTeX backslashes.** Instead, Rung-1 must prioritize a targeted, deterministic backslash-escaping pre-processor to ensure mathematical content fidelity, keeping `json-repair` solely as a structural fallback. Additionally, the implementation must correct the non-existent `warnings` field traversal, use regex-based wikilink replacement to handle alias/anchor links, and move `semantic_check` inside the attempt loop to prevent early quarantines.
