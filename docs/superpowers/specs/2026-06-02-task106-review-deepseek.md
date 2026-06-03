# Task #106 — JSON-repair + slug-coercion ladder — Review (Deepseek)

**Reviewer:** Deepseek · **Date:** 2026-06-02 · **Repo:** `main` @ `v0.5.2` (Phase B landed)

---

## Verdict: `GO-WITH-CHANGES`

The ladder architecture (emit → repair/normalize → validate; retry; quarantine) is sound, re-validation-gating is the right guardrail, and the placement of both rungs inside the existing attempt loop is correct. Every home respects the B.3 dependency contract. However, **one load-bearing decision is unsettled** — the rung-1 mechanism (`json-repair` vs targeted backslash-escaping) — and there is one **phantom schema field** in the propagation list that would cause runtime errors. Fold the changes below, then proceed to writing-plans.

---

## Findings

### (a) Correctness/safety of the design

**[Severity: Critical] · spec §3 line 48 (content-fidelity hole) · Rung-1 should use targeted backslash-escaping as the primary mechanism, not `json-repair`**

The spec correctly identifies that `json-repair` may silently strip the backslash from `\(n-1)` to produce valid JSON that passes every gate while corrupting body content. The mitigation ("probe behavior + consider targeted escaping") defers the decision to writing-plans — but this is the *precise* moment to decide it.

The known failure class is narrow: a stray `\` before a character that is not a valid JSON escape (`"`, `\`, `/`, `b`, `f`, `n`, `r`, `t`, `u`). A targeted pre-processor that doubles only those backslashes (`\(` → `\\(`) is:
- **Content-preserving by construction** — the backslash survives in the parsed string exactly as the LLM intended.
- **Zero false positives** — valid escapes like `\n`, `\\`, `\"` are left untouched.
- **No external dependency** — trivial to implement (~10 lines of Python); no `json-repair` package needed at all.
- **Addresses the EXACT failure class** seen in run-5 and run-6, without the collateral risk of a general-purpose heuristic tool.

`json-repair` is a content-corrupting black box for *this* use case. The spec's own test plan (§9) asserts "the LaTeX **survives**" — but that's exactly what `json-repair` cannot guarantee. The test cannot both require content-fidelity and delegate repair to a tool that may destroy it.

**Recommended change:** Flip rung-1 to targeted backslash-escaping as the primary mechanism. Define it as: scan the raw JSON text for `\` not followed by `["\\/bfnrtu]` or a `u` + 4 hex digits → double it. Gate on re-parse + schema + semantic. If `json-repair` is still desired as a second-layer fallback for *other* JSON malformations, add it as a separate (lower-priority) rung or a fallback within rung-1, but the primary defense against the live, confirmed class should be targeted escaping **from the start**.

If the design must keep `json-repair`, then the writing-plans fork is: probe behavior → if content-destructive, targeted escaping. But that's just targeted escaping with extra steps — skip the detour.

---

**[Severity: High] · spec §4b line 70 vs `compiler/schemas/compiled_source_response.schema.json` line 30 · Phantom field: `warnings[].related_slugs[]` does not exist in the schema**

The spec lists `warnings[].related_slugs[]` as a slug-bearing field requiring propagation. The schema defines `warnings` as:

```json
"warnings": {
  "type": "array",
  "items": { "type": "string" }
}
```

There is no `related_slugs` field inside warning entries. Propagating to a non-existent field is either a no-op (if guarded) or a runtime error. Either way, including it in the propagation list is incorrect — it implies a structural coupling that doesn't exist.

**Recommended change:** Remove `warnings[].related_slugs[]` from the propagation list in §4b. If the field is planned for a future schema revision, note it as "future only — not present in v0.5.2 schema."

---

**[Severity: High] · spec §5 line 83 vs `compiler/compiler.py` lines 339-352 · Semantic re-validation after rung-2 — the spec says "re-validate (schema + semantic)" but must clarify mechanism**

The spec states rung-2 should "re-validate (schema + **semantic**)." In the real code:
- Schema validation happens inside the loop (line 322).
- Semantic check runs AFTER the loop `break` (lines 341-352).

If rung-2 coerces slugs and re-validates schema, and schema passes, the `break` at line 339 exits the loop normally, and semantic runs at line 342. This works **as long as the spec intends to rely on the natural flow** rather than adding an explicit semantic re-check inside the loop.

However, if the spec intends rung-2 to gate on semantic *before* breaking (i.e., if semantic fails after coercion, retry rather than break), the code must be changed to call `semantic_check()` inline. The spec doesn't commit to either interpretation.

The natural-flow interpretation (break → semantic runs normally) is simpler and sufficient: if semantic fails after coercion, it's a hard failure (semantic failures are unrecoverable — the LLM produced internally inconsistent slugs). But the spec should be explicit.

**Recommended change:** Clarify in §5: "re-validate schema; if schema passes, break out of the loop → semantic runs as normal (the semantic check is already outside the loop and always runs on non-quarantined emissions). Slug coercion cannot fix a semantic failure, so re-running semantic inside the loop adds no value."

---

**[Severity: Medium] · spec §4c line 74 · Collision guard: cross-field collisions between `summary_slug` and page slugs not explicitly addressed**

The collision guard says "If collapsing makes two distinct slugs map to the same new slug (e.g. `foo--bar` and `foo-bar` both present)." This covers within-namespace collisions (two page slugs colliding). But a coerced `summary_slug` like `summary-foo--bar` → `summary-foo-bar` could collide with a page slug `foo-bar`. While these are in different namespace positions (summary vs concept/article), they occupy the same slug-space in the LLM-emitted payload — the schema treats them as independent fields. A cross-field collision between `summary_slug` and `pages[].slug` (or between slugs in different pages) should also be detected and refused.

The "two distinct slugs" phrasing can be interpreted as "any two slugs across the entire compile result" — if that's the intent, make it explicit. If the intent is only within-field collision detection, the gap should be acknowledged.

**Recommended change:** Expand the collision guard to explicitly check for collisions across ALL slug-bearing fields in the compile result, not just within the same field. A renamed `summary_slug` colliding with a page slug should be caught.

---

### (b) Scope & conservatism calls

**[Severity: Low] · spec §4a lines 57-58 · "Enforce D19" framing is slightly misleading but functionally correct**

The spec frames slug coercion as "enforcing the existing D19 post-LLM." But `slugify()` (the D19 implementation) does NFKD normalization + lowercasing + character elimination — the coercion does LESS (only collapse-`-{2,}` + edge-strip). This is the **right** conservative choice (don't guess intent on uppercase/spaces), but the phrase "enforce D19" implies full re-application of `slugify()`, which the spec deliberately rejects.

**Recommended change:** Clarify wording: "enforce the *hyphen-run* subset of D19" or "normalize the one D19 rule the LLM observably violates." Not a functional issue — just prevents a reader from assuming more than the spec delivers.

---

**[Severity: Low] · spec §6 lines 89-91 · Pass-1 deferral is the right call**

Both live failures are in Pass-2. Rung-1 is built reusably (in `common/util/`) so Pass-1 can adopt it later. No Pass-1 syntax failure has been observed. This is the correct "data-before-principle" discipline.

---

### (c) Placement/integration with the real compiler flow

**[Severity: Medium] · spec §5 lines 80-83 vs `compiler/compiler.py` lines 354-362 · Post-coercion interaction with `reconcile_body_links` and `reconcile_slug_lists` is benign but should be verified**

After rung-2 coerces slugs and propagates to body `[[tokens]]`, control flows through:
1. `reconcile_body_links()` (line 355) — rebuilds `outgoing_links` from body `[[token]]` extraction.
2. `reconcile_slug_lists()` (line 362) — rebuilds `concept_slugs` and `article_slugs` from `pages[].slug`.

If rung-2 correctly propagated to body text (replacing `[[foo--bar]]` → `[[foo-bar]]`), then `reconcile_body_links` finds the coerced slug and sets `outgoing_links` accordingly — idempotent with rung-2's work. Same for `reconcile_slug_lists` — pages already have coerced slugs, so the rebuild produces the same list.

If rung-2 *didn't* propagate to body (bug), `reconcile_body_links` would find the old `[[foo--bar]]` in body and set `outgoing_links` to `foo--bar` → schema would FAIL on `outgoing_links` because `foo--bar` violates the slug pattern. This is a **safety net** — the existing reconcilers catch incomplete propagation. But it's also a silent failure mode that would show as "repaired-syntax" in the log when it should be "schema-still-invalid." The integration test (§9 "a compile-result with a `---` summary_slug referenced in … → after coercion all references updated consistently") should verify this exact chain.

**Recommended change:** Add a note in the implementation plan: "Verify that after rung-2 coercion, `reconcile_body_links` and `reconcile_slug_lists` produce no net changes (they're idempotent with correct propagation). A change count > 0 after coercion means propagation missed something — fail the compile."

---

**[Severity: Low] · spec §5 line 83 vs `compiler/compiler.py` line 68 · `_MAX_COMPILE_ATTEMPTS = 2` semantics preserved**

The ladder correctly extends the existing retry contract: each attempt now includes repair/normalize before the retry decision, but `_MAX_COMPILE_ATTEMPTS` still means "2 model calls." Repair runs on both emissions. No masking of #104's retry behavior — the `continue` paths are just gated on repair failures now.

**No change needed.**

---

**[Severity: Low] · real code `compiler/compiler.py` line 309-314, 327-333 · Retry log messages should distinguish repair failure from raw failure**

Currently, the retry warning logs read `"invalid JSON, retrying"` and `"schema invalid, retrying"`. After #106, a parse that fails → rung-1 repair → still fails should log differently from a parse that fails with no repair attempted. The measurability taxonomy (§7) logs the final resolution, but per-attempt logging (especially for debugging) should indicate whether repair was attempted.

**Recommended change:** Not a spec change — note for writing-plans: per-attempt log messages should include whether a repair rung fired before falling to retry (e.g., `"invalid JSON after repair, retrying"`).

---

### (d) Homes/contract

**[Severity: Low] · Spec §8 · All homes respect B.3 contract; `common/util/` needs `__init__.py` creation noted**

| Home | B.3 legality | Notes |
|---|---|---|
| `common/util/json_repair.py` | ✓ (common is a leaf; `util/` is new sub-package) | #106 creates dir; must also create `common/util/__init__.py` |
| `common/paths.collapse_slug()` | ✓ (common is a leaf) | Right home — slug policy, not generic utility |
| `compiler/repair` (propagation) | ✓ (`compiler → common` legal) | Alongside existing reconcilers |
| `pyproject.toml` | n/a | New dep: `json-repair` (if retained) |

The spec correctly distinguishes `util` (generic helpers) from `paths` (slug policy authority). `common/util/` does not exist today (confirmed: `ls common/` shows no `util/` subdirectory). Phase B's B.5 explicitly doesn't pre-create it.

**Recommended change:** Add to §8 or the test plan: "#106 must create `common/util/__init__.py` alongside `json_repair.py`."

---

**[Severity: Low] · `compiler/repair.py` currently operates on `cr` dicts (line 220), NOT on `parsed_json` dicts**

The existing `repair()` function at `compiler/repair.py:220` consumes `cr` (compile_result dicts with `cr["compiled_sources"]`), not the `parsed_json` dict (the LLM-emitted payload per-source). The slug-coercion propagation operates on `parsed_json` — the per-source, pre-compile_result shape. This is a different scope and insertion point (inside the attempt loop, per-source) from the existing `repair()` function (post-semantic, per-compile_result).

**Recommended change:** The spec should clarify that the slug-propagation function in `compiler/repair` is a *sibling* to the existing `repair()` function, not a modification of it. They operate on different shapes at different pipeline stages. Naming should disambiguate (e.g., `coerce_slugs_and_propagate(parsed_json)` vs the existing `repair(cr, findings)`).

---

### (e) Gaps/omissions

**[Severity: Medium] · Not in spec · Third recoverable class: trailing/garbled text after valid JSON**

A known LLM failure mode (seen in other JSON-emission pipelines, though not confirmed in KDB run-5/6): the LLM emits valid JSON followed by trailing prose or artifacts (e.g., `{...}\n\nLet me know if you need...`). `response_normalizer.extract_json_text()` handles clean markdown code fences, but trailing prose after a bare JSON object might slip through extraction or confuse `json.loads`.

The spec doesn't mention this class. It's lower priority than the two confirmed classes, but if rung-1 is doing targeted escaping, a companion rung-1b could be "strip trailing non-JSON after the last `}`" (a simple heuristic that preserves the JSON content). This is optional — not observed live — but worth logging as a known gap.

**Recommended change:** No spec change needed (data-before-principle). Note for future: if a trailing-prose failure is observed, a rung-1b that trims after the last `}` in the raw text is a trivial deterministic recovery.

---

**[Severity: Low] · spec §7 (measurability) · Attempt number should be logged alongside the rung taxonomy**

The taxonomy `clean / repaired-syntax / coerced-slug / retried / quarantined` is sufficient. But a `repaired-syntax` on attempt 1 carries different signal than `repaired-syntax` on attempt 2 (the latter means the re-emission also had the same malformation). The resp-stats record already captures attempt-level data, so this is implicitly available — but the spec should explicitly note that the rung resolution should be correlated with the attempt number in the stats output.

**Recommended change:** Add to §7: "Log the resolving rung AND the attempt number together (e.g., `repaired-syntax:attempt-1`). This distinguishes 'repair rescued a bad first emission' from 'repair rescued the retry too.'"

---

**[Severity: Low] · Not in spec · The `collapse_slug` function should also validate length (`MAX_SLUG_LEN = 120`)**

`common/paths.py` defines `MAX_SLUG_LEN = 120` (line 27). If a coerced slug exceeds this after collapse (unlikely but possible with edge hyphens), it should be caught. Since collapse only shortens or preserves length, this can't introduce a length violation — but it's worth noting in the implementation that `validate_slug()` (which checks length) is called as part of the schema re-validation gate, so length violations are caught downstream.

**No change needed — schema re-validation covers this.**

---

## Bottom line

This design is sound enough to proceed to implementation planning, with one decisive fork: **targeted backslash-escaping should replace `json-repair` as the primary rung-1 mechanism.** The known failure class (stray `\` before non-JSON-escape chars) is precisely characterized and admits a content-preserving pre-processor that `json-repair` cannot guarantee. The spec's own content-fidelity concern is correct — adding `json-repair` is adding a black box when you already know the shape of the fault. Targeted escaping is simpler, dependency-free, content-preserving by construction, and directly addresses the single live case. If broader JSON malformations appear later, `json-repair` can be added as a fallback rung — but making it the primary defense now is speculation dressed as rigor.

Beyond that fork: fix the phantom `warnings[].related_slugs[]` field (it doesn't exist in the schema), clarify the semantic-revalidation mechanism inside the loop, and expand the collision guard to cross-field collisions. Then write the plan.
