# Task #106 Spec Review — Grok

**Reviewer:** Grok (panel member)  
**Spec under review:** `docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md`  
**Codebase state (read-only verification):** Phase B landed (`v0.5.2`, `main`), files inspected: `compiler/compiler.py` (loop 242, loads 305, schema validate 322, semantic 341, reconciles 354/362), `compiler/repair.py` (reconcile_* 153/179/220), `common/paths.py` (SLUG_PATTERN 26, slugify 51, validate 63), `compiler/schemas/compiled_source_response.schema.json` (slug defs), `compiler/validate_source_response.py` (semantic_check 58, body_wikilink_slugs 115 + _WIKILINK_RE), `compiler/response_normalizer.py`, `common/llm_telemetry.py` + `common/types.py` (RespStatsRecord), `compiler/canonicalize.py` (remap precedent + _WIKILINK_RE 216), `ingestion/enrich/pass1_caller.py` + `pass1_schema.py` (existing coercion/retry precedent), `pyproject.toml`, dir structure (no `common/util/` yet), relevant tests (no execution).

---

## 1. Verdict
`GO-WITH-CHANGES`

---

## 2. Findings

### (a) correctness/safety of the design

1. `[Severity: High]` · spec §4b + `compiler/schemas/compiled_source_response.schema.json:29-32` (and matching in compile_result.schema.json) · The propagation target list includes "log_entries[].related_slugs[] (and any warnings[].related_slugs[])". Warnings is defined as `"type": "array", "items": { "type": "string" }` — no objects, no related_slugs subfield. Only log_entries carry related_slugs.
   - *Why it matters*: Implementing traversal for a phantom field either produces dead code or tempts schema bloat to "make the spec true." Either violates the "read the contract from the schema" discipline.
   - *Suggested change*: Remove the parenthetical and the warnings claim. Authoritative list (cross-checked): `summary_slug`, `concept_slugs[]`, `article_slugs[]`, `pages[].slug`, `pages[].outgoing_links[]`, whole `[[…]]` tokens in `pages[].body`, `log_entries[].related_slugs[]`.

2. `[Severity: High]` · spec §3 (⚠ content-fidelity hole) + §9 test plan + `compiler/compiler.py:305` (json.loads site) · Rung 1 nominates the `json-repair` package (new dep) with re-validation gate. The spec correctly identifies the LaTeX `\(n-1\)` hole (silent `\` strip → valid JSON + corrupted body content that schema/semantic cannot see because they are structure-only). It defers the "probe + consider targeted escaping" decision.
   - *Why it matters*: This is the only *confirmed* syntax malformation class. A general fixer can make many other guesses (delimiter insertion, quote coercion, bracket close, number fixup, etc.) that also pass structure gates while mutating body prose, math, or markdown in undetectable ways. Adding a dep + broad trust surface for a narrow, known root cause (stray `\` before non-JSON-escape) is the wrong default.
   - *Suggested change*: Make rung 1 **targeted backslash-escaping first** (pre-parse: replace `\` that is not followed by a valid JSON escape char `["\\\/bfnrtu]` or `uXXXX` with `\\`), then re-parse. Only if that still fails parse, fall back to `json-repair` (or drop the broad tool entirely). Update home to something like `common/util/json_escape_fix.py` (or keep thin wrapper), drop the `json-repair` pip dep from this task unless a second unhandled syntax class appears in the wild. The §9 test assertion ("LaTeX `\(n-1\)` survives intact") becomes the primary acceptance gate either way.

3. `[Severity: High]` · spec §4b (body rewrite rule) + `compiler/validate_source_response.py:101-124` (body_wikilink_slugs + _WIKILINK_RE) + `compiler/canonicalize.py:216` (permissive _WIKILINK_RE) + `compiler/compiler.py:354` (reconcile_body_links after) · "rewrite whole `[[…]]` tokens, not substring-replace" is correct in principle (prefix-corruption hazard), but the spec does not specify handling of the two wikilink forms the model is allowed to emit: `[[slug|Display]]` and `[[slug#section]]` (both accepted by the extraction regex and by Obsidian).
   - *Why it matters*: A literal `[[old]]` → `[[new]]` string replace will leave `[[old|foo]]` and `[[old#h]]` untouched. Post-coercion the body will contain the old malformed slug in a link position while `outgoing_links` and pages[].slug are updated → reconcile_body_links (which re-derives from body after stripping code) or downstream bidir checks will see mismatch, or the bad token survives into the vault.
   - *Suggested change*: Implement the body rewrite with a regex (modeled on the existing `_WIKILINK_RE` or the stricter one in validate) that matches the full token, captures the target slug, and rewrites *only the target portion* while preserving `|display` and `#anchor` (and the leading `[[` / trailing `]]`). Do the replace on the whole body string; code-span stripping is unnecessary here (see note in (e)).

4. `[Severity: Medium]` · spec §4c (collision guard) + `common/paths.py:26` (SLUG_PATTERN) + `compiler/schemas/compiled_source_response.schema.json` (all slug positions) · The guard ("two distinct slugs map to the same new slug") is described with an example that mixes malformed+valid. It is unclear whether the implementation must consider *all* slug values present in the payload (including already-valid ones appearing in outgoing_links, body tokens, related_slugs, or other pages' slugs) when deciding whether a collapse target is claimed by >1 pre-image.
   - *Why it matters*: Realistic case: LLM emits one valid page slug "foo-bar" (different concept) *and* a malformed "foo--bar". Collapsing the second lands on the first. If the guard only looks at "which bad slugs collide among themselves," this slips through, producing a duplicate slug inside the source (later caught as gate error, but after we have already mutated and lost the original malformation signal).
   - *Suggested change*: Explicitly: collect the set of *all* distinct slug string values present across the bearing fields in this parsed_json. Compute would-be = collapse(v) for each. Group originals by their would-be. If any would-be bucket has cardinality >1, collision → refuse (leave unchanged). This automatically covers malformed-vs-valid and malformed-vs-malformed. Only apply actual (old != new) renames when no collision.

5. `[Severity: Low]` · spec §4a + test plan §9 + `common/paths.py:55` (slugify does `.strip("-")`) · `collapse_slug` on a pure-separator input (e.g. emitted slug `---` or `summary- - -`) yields `""` after collapse+strip. Empty is not a valid slug (fails pattern + minLength).
   - *Why it matters*: Propagating `{ "---": "" }` or similar would inject garbage into summary_slug / pages[].slug etc.
   - *Suggested change*: In `collapse_slug` (or its caller in the rung-2 logic): if the post-collapse value is empty (or fails the target pattern even after), treat as unrecoverable for this rung — refuse the coercion for that value (or the whole map) and let re-validation fail honestly.

### (b) scope & conservatism calls

1. `[Severity: High]` · spec §3 + §6 + decisions log + the rung-1 fork (see (a)2) · The design correctly frames slug coercion as "enforce D19 post-LLM" (conservative, only the formatting rule the model's own slugify already applies). Rung 2 scope (collapse `-{2,}` + edge strip only; no lower, no char class surgery, no unicode folding) is sound and matches the grounding insight. "Reserve coercion for benign, confirmed classes" per memory `feedback_coerce_dont_reject` is honored.
   - The same conservatism principle should have been applied more forcefully to rung 1. Adding a third-party general repair tool + new dep for the single observed syntax class is the *less* conservative choice. Targeted escaping is narrower, zero-dep, and content-preserving by construction.
   - *Suggested change*: Adopt the position in (a)2. If the panel keeps `json-repair`, the "probe on actual `\( \)` behavior + LaTeX-survives test" in writing-plans and §9 becomes a hard gate, not a "consider."

2. `[Severity: Low]` · spec §6 (Pass scope) · "Pass-2 now, Pass-1 later (data-before-principle)" + "rung 1 built reusably, rung 2 pass-agnostic" is the right call. Existing Pass-1 precedent (pass1_caller.py retry + pass1_schema.normalize_llm_content for the >10 keys case) shows the same "coerce benign before validate, else retry" shape. No third live malformation class is visible in the inspected code or the two grounded run-6 examples. Good restraint.

3. `[Severity: Low]` · spec §4a + `common/tests/test_paths.py:18,51` (slugify already collapses `Mixed---Dashes`; validate rejects `double--dash`) · The coercion is exactly the missing post-LLM application of the rule slugify already implements. No benign-and-confirmed case is wrongly excluded by the "only collapse+strip" boundary.

### (c) placement/integration with the real compiler flow

1. `[Severity: High]` · spec §5 (placement + "re-validate (schema + semantic)") + `compiler/compiler.py:242-352` (the attempt loop, break at 339 on schema_ok only, semantic at 341-352 *after* the loop, reconciles at 354/362) + `validate_source_response.py:58` (semantic_check only does summary_slug presence + exactly-one-summary-page) · The spec states rung 2 does `re-validate (schema + semantic)`. In the live code semantic_check is strictly post-loop. A coercion that makes schema pass but leaves semantic failing (e.g. summary_slug renamed but its summary page entry not consistently updated, or summary_slug no longer appears in pages[].slug) will break after the loop with no remaining retry budget.
   - *Why it matters*: Directly violates the core guardrail "every repair is re-validation-gated; a bad repair just falls to the next rung." The safety claim is not true against the actual control flow.
   - *Suggested change*: Writing-plans must make the gate real. Two minimal options: (1) move the semantic_check call inside the loop (only `break` when schema_ok *and* semantic_ok); or (2) on the rung-2 repair path, explicitly call semantic_check after the schema re-validate and use its result to decide continue vs. break (without mutating the outer schema_ok path for non-repair cases). Either way, a post-repair semantic failure on a non-last attempt must be allowed to retry. Also re-clear schema_errors/semantic_errors on successful repair re-validate.

2. `[Severity: Medium]` · spec §5 + `compiler/compiler.py:354-362` (reconciles after semantic) + rung-2 body + slug-list propagation · After a successful rung-2 coercion we still execute `reconcile_body_links` (body → outgoing_links) and `reconcile_slug_lists` (pages[].page_type → concept/article lists). Because rung 2 already rewrote the affected body `[[ ]]` tokens *and* the explicit lists, the reconciles will see consistent data and be near-no-ops (or harmlessly re-derive the same values). This ordering is actually safe and convergent. However, the spec is silent on the post-reconcile state.
   - *Suggested change*: In the integration test and in the rung-2 helper itself, after coercion + re-validate + the two reconciles, optionally assert (debug, non-fatal) that a fresh `validate_source_response.validate` + `semantic_check` still passes. This catches any surprising interaction before the payload leaves compile_one. (Current reconciles are not followed by re-validation today; this would be new belt-and-braces for the repair path.)

3. `[Severity: Low]` · spec §5 + `compiler/compiler.py:68` (_MAX_COMPILE_ATTEMPTS=2) + #104 precedent · Inserting the two rungs does not change the number of model emissions (still at most 2). Repairs are in-process and free. The "retried" category in the taxonomy simply records that the second emission was required. No semantic change to the constant or the #104 loop. Minor naming/documentation only: "attempts" in telemetry remains model-call attempts; rung applications are separate.

### (d) homes/contract

*None critical.* 

- `common/util/json_repair.py` (or the targeted-escape equivalent) as first occupant of `common/util/`: respects B.3 (`compiler → common` legal; common remains leaf). The "util is common" taxonomy from the Phase B decisions log is followed. (Note: creating the directory also requires `common/util/__init__.py` — empty is fine — for the submodule to be importable as a package; other common subpackages follow this pattern. Spec does not call this out explicitly.)
- `common/paths.collapse_slug`: correct "policy, not util" placement alongside `slugify`/`validate_slug`/`SLUG_PATTERN`. Future Pass-1 callers get it for free.
- Propagation + collision guard + rename map in `compiler/repair.py`: lives with the other structural reconcilers (`reconcile_body_links`, `reconcile_slug_lists`). Same package as the call site in `compiler.py`. Good.

All three homes are the ones ratified post-Phase B; no relocation tax.

### (e) gaps/omissions

1. `[Severity: Medium]` · spec §7 (measurability taxonomy) + `common/types.py:377` (RespStatsRecord) + `common/llm_telemetry.py:146` (build_resp_stats) + `compiler/compiler.py:174` (state dict) + orchestrator event paths · The flat mutually-exclusive list `clean · repaired-syntax · coerced-slug · retried · quarantined` is insufficient to observe combinations that will occur in practice:
   - A source that required the second emission *and* was rescued by rung 2 on that emission (retried + coerced-slug).
   - An emission that needed both rungs in sequence (syntax repair produced a payload that then needed slug coercion).
   - "retried" is really "compile_attempt == 2", while the rung flags are orthogonal.
   - The taxonomy must also be visible on *failed* attempts (for the last failing emission) and on quarantined sources.
   - *Why it matters*: The explicit goal is "so we can prune repair scope if it ever over-reaches" and "makes the deterministic-recovery rate observable." A non-compositional encoding loses signal.
   - *Suggested change*: Persist orthogonal facts on RespStatsRecord (and therefore on the orchestrator record / run summary):
     - `compile_attempts`: int (1 or 2, the value of the loop attempt that produced the final parsed_json for this source)
     - `syntax_repaired`: bool (rung 1 fired and produced a parse-ok payload that reached schema)
     - `slug_coerced`: bool (rung 2 produced a schema-ok + semantic-ok payload)
     - `final_status`: "clean" | "repaired" | "retried-and-repaired" | "quarantined" (or just derive from the above + success/failure)
     This requires: new optional field(s) on the dataclass, threading through build_resp_stats (new param with default), state tracking inside the attempt loop in compiler.py (set the booleans when a repair path succeeds and we break), and updates to any tests that construct/ assert on RespStatsRecord or parsed summaries. The existing "attempts" from ModelResponse (SDK-level) remains separate.

2. `[Severity: Low]` · spec §9 (test plan) + live gate run-8 · The unit/integration cases are well-scoped (transform, propagation, collision, the two live fixtures recover on attempt 1 via the right rung, LaTeX content fidelity). Missing explicit cases that writing-plans + TDD must add:
   - Rung 1 then rung 2 on the *same* emission (syntax fix still leaves a collapsible slug).
   - Collision of a collapsible slug with a *valid* slug that appears only in `outgoing_links[]` or a body `[[ ]]` token (not as a defined page slug in this source).
   - `summary-` prefixed collapse (the Sleep-and-Aging fixture covers it, but make it a dedicated param test on collapse_slug).
   - All-hyphen / edge-to-empty case refuses.
   - After coercion + reconciles, the payload still satisfies both source-response schema + semantic (and, for the cr-level, the later validate_compile_result has no new hard-zero findings attributable to the coercion).
   - Irreparable other schema error (non-slug) still falls through with result unchanged (no spurious mutation).

3. `[Severity: Low]` · spec §7 + "retried" category + `compiler/compiler.py:308-333` (the warning logs on extract/parse/schema fail) · When a repair rescues inside the loop we will *not* emit the "invalid JSON, retrying" / "schema invalid, retrying" warning for that attempt. We should emit an informational log (or structured event) that a rung fired, e.g. "Pass-2 attempt 1/2 repaired-syntax, proceeding". This is required for the same observability goal as the persisted taxonomy. The current warning text hard-codes the failure; repair success is a different branch.

4. `[Severity: Low]` · General omission around state/artifact mutation · On a non-last attempt, if we apply a coercion that fixes the slug error(s) but other schema errors remain, the `state["parsed_json"]` (and therefore the RespStatsRecord for that attempt, if captured) will contain the partially-repaired shape. On final failure the last emission's record will likewise reflect any repair that was attempted. This is probably desirable (the artifact shows what the rung did), but the spec never discusses whether failed-attempt parsed_json should be left in the "before repair attempt" or "after attempted repair" state. Writing-plans should decide and document (and the test fixtures that simulate bad emissions should assert the captured parsed_json shape on the failing path).

---

## 3. Bottom line
The design is sound at its core: a conservative, re-validation-gated deterministic ladder for exactly the two confirmed recoverable malformation classes, with correct homes that respect the post-Phase-B contract, pass-agnostic helpers, and a measurability hook. The load-bearing safety claim ("bad repair cannot sneak through") is the right philosophy. Two changes are required before writing-plans: (1) resolve the rung-1 fork explicitly in favor of **targeted backslash-escaping as the primary mechanism** (with `json-repair` either dropped or demoted to an unknown-syntax fallback) — this is the decision most likely to be wrong if left open; and (2) close the semantic re-validation gap by moving (or duplicating) `semantic_check` into the attempt loop so that a post-coercion semantic failure on a non-final attempt still gets its retry. Additional high-confidence fixes: drop the phantom `warnings[].related_slugs[]`, implement whole-token wikilink rewrite that preserves `|display` and `#anchor`, make the collision guard consider all present values (valid + malformed), and upgrade the flat taxonomy to orthogonal flags persisted on RespStatsRecord (requiring small but real surface changes in `common/types.py`, `llm_telemetry.py`, and `compiler/compiler.py`). With those folded, the spec is ready to become a tight, TDD-driven implementation plan. The two live fixtures (Borda LaTeX, Sleep-and-Aging `---`) plus the collision and content-fidelity assertions will be the proof. 

Full context synchronization complete. Global rules, recent history, and open work are loaded. What is our top priority for this session? (No — this review is the deliverable per the prompt; the file above is the sole artifact written.)