# Task #106 — JSON-repair + slug-coercion ladder — Qwen Review

**Reviewer:** Qwen (panel member)
**Spec under review:** `docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md`
**Codebase state:** Phase B landed (`v0.5.2`, `main` branch, 2026-06-02)

---

## Verdict: **GO-WITH-CHANGES**

The design is sound on its load-bearing decisions — conservative coercion scope, re-validation gating, pass-agnostic helpers, correct package placement. Three findings must be resolved before writing-plans: a phantom field in the propagation list, a semantic-revalidation gap vs. the real compiler flow, and the rung-1 mechanism fork needs a sharper decision. The remaining findings are low-severity tightenings.

---

## (a) Correctness / safety of the design

### F1. [High] — Phantom field `warnings[].related_slugs[]` in propagation list
**Spec §4b, bullet 7.** The spec lists `warnings[].related_slugs[]` as a slug-bearing field that propagation must cover. **This field does not exist.** In `compiled_source_response.schema.json:29-31`:

```json
"warnings": {
  "type": "array",
  "items": { "type": "string" }
}
```

`warnings` is a plain string array — no `related_slugs` subfield. The same holds in `compile_result.schema.json:29-31`. Only `log_entries` carry `related_slugs` (`compiled_source_response.schema.json:101-112`).

**Why it matters:** Implementing propagation against a nonexistent field either (a) produces dead code that scans for a field that never exists, or (b) a developer "fixes" the schema to add the field, expanding the LLM contract for no reason. Either way it's a spec bug that propagates into implementation.

**Suggested change:** Delete the `warnings[].related_slugs[]` bullet from §4b. The complete propagation list is then: `summary_slug`, `concept_slugs[]`, `article_slugs[]`, `pages[].slug`, `pages[].outgoing_links[]`, `pages[].body` (whole-`[[token]]`), `log_entries[].related_slugs[]`. Seven fields, all real.

---

### F2. [High] — Semantic re-validation gap after rung-2 repair
**Spec §5 (rung 2 at schema step):** "on any schema failure → attempt slug-collapse + propagation → **re-validate (schema + semantic)**."

The spec claims rung-2 repair re-runs semantic validation. The real compiler flow (`compiler/compiler.py`) does **not** support this:

- **Inside the attempt loop** (lines 242–341): `json.loads` → `validate()` (schema only) → break on success.
- **Outside the loop** (line 343+): `semantic_check()` runs exactly once, after the loop exits via `break`.

After rung-2's in-loop repair and schema re-validation, the code hits `break` and then runs semantic — but only once, on the repaired payload. The spec's language implies the semantic check would re-run *as part of the in-loop re-validation gate*. In practice the semantic check does run on the repaired payload (because it runs after `break`), but:

1. If semantic fails post-repair, there's **no retry path** — the code returns an error immediately (line 350). The retry mechanism is inside the loop; the semantic failure is outside it.
2. The spec's mental model ("repaired emission must pass the same `parse → schema → semantic` checks") implies semantic failure post-repair should fall to the next rung (retry). The real code doesn't do this.

**Why it matters:** A rung-2 coercion that produces a structurally valid but semantically wrong result (e.g., a coerced `summary_slug` that no longer matches a `pages[].slug` with `page_type='summary'`) would reach quarantine with no chance of retry rescue.

**Suggested change:** Writing-plans must restructure the attempt loop so semantic_check runs **inside** the loop, after schema passes, **before** the break. This makes the re-validation gate real: `parse → schema → [repair] → re-parse → re-schema → semantic → break`. On semantic failure post-repair, the loop continues to retry. This is a small structural change to `compiler.py:242-350` but it's load-bearing for the spec's safety claim.

---

### F3. [Medium] — Collision guard must cover malformed-vs-valid collisions, not just malformed-vs-malformed
**Spec §4c:** "If collapsing makes two **distinct** slugs map to the **same** new slug (e.g. `foo--bar` and `foo-bar` both present), that is a genuine conflict — do not silently merge."

The spec's example (`foo--bar` and `foo-bar`) is actually the malformed-vs-valid case — `foo-bar` is already valid, `foo--bar` is malformed. So the spec *intends* to cover this, but the framing ("two distinct slugs") is ambiguous about whether one can be already-valid.

**Why it matters:** The more realistic scenario is: the LLM emits `pages[].slug = "foo-bar"` (valid, for a different concept) AND `pages[].slug = "foo--bar"` (malformed). Collapsing the second creates a collision with the first. If the implementation only checks "do two malformed slugs collapse to the same thing," this case passes undetected.

**Suggested change:** §4c should explicitly state: the rename map must be checked against **all existing slugs in the payload** (both valid and malformed), not only against other collapsed slugs. The collision guard builds the full rename map, then verifies `set(rename_map.values()) ∩ set(unchanged_slugs) = ∅` AND `len(set(rename_map.values())) == len(rename_map)`.

---

## (b) Scope & conservatism calls

### F4. [Medium] — Rung 1: the `json-repair` vs targeted-escaping fork needs a sharper decision
**Spec §3 (⚠ Content-fidelity hole).** The spec correctly identifies that `json-repair` can silently strip a stray backslash before a non-JSON-escape character (e.g., `\(` → `(`), producing valid JSON that passes every gate while corrupting LaTeX content. The mitigation is "probe behavior + consider targeted backslash-escaping."

This is the right question to ask, but the spec defers the answer to writing-plans. I think the design should **commit** now, because:

1. The known failure class is **narrow and well-characterized**: stray `\` before a character that isn't a valid JSON escape (`"`, `\`, `/`, `b`, `f`, `n`, `r`, `t`, `u`). This is one regex: `\\(?![\"\\\/bfnrtu])`.
2. Targeted escaping (`replace \` → `\\` before non-escape chars) is ~5 lines of code, zero dependencies, and **provably content-preserving** — it never removes or transforms content, only makes the existing content parseable.
3. `json-repair` is a general-purpose fixer that can make many kinds of guesses (insert delimiters, remove trailing commas, close brackets). Every one of those guesses is a potential content-fidelity hole that schema+semantic won't catch (they check structure, not body content).

**My position:** **Targeted backslash-escaping first, `json-repair` rejected for now.** The escaping covers the only confirmed syntax-failure class (LaTeX). If a second class appears later that escaping can't fix, `json-repair` can be introduced then with a narrower trust scope. The spec's "probe then decide" is one step too many — we already know enough to decide.

**Suggested change:** §3 should specify rung 1 as: (a) targeted backslash-escaping of stray `\` before non-JSON-escape characters, (b) re-parse, (c) schema + semantic. `json-repair` moves to a "future consideration" note. `common/util/json_repair.py` becomes `common/util/json_escape_fix.py` (or similar), and the `json-repair` pip dependency is dropped from scope.

*Note: if the panel disagrees and keeps `json-repair`, the probe requirement in §9 (test plan) is non-negotiable — the LaTeX-survives assertion must be the primary acceptance gate.*

---

### F5. [Low] — Rung 2 "attempt on any schema failure" is correct but should be documented as intentional
**Spec §5:** "Do not sniff the error string to detect the slug-pattern class — just attempt the collapse and let re-validation decide."

This is the right call (cheap no-op on non-slug errors, avoids brittle error-string parsing). But it should be explicitly documented as a **deliberate design choice**, not an oversight. An implementer reading "on any schema failure → attempt slug collapse" might add error-class sniffing "for efficiency." The spec should state: this is intentionally class-agnostic; the no-op cost is negligible; the re-validation gate is what makes it safe.

---

## (c) Placement / integration with the real compiler flow

### F6. [Medium] — Rung-2 propagation and `reconcile_body_links` ordering interaction
**Spec §5** places rung 2 inside the attempt loop (at the schema step, ~line 330). **`reconcile_body_links`** runs after the loop (`compiler.py:354`).

Rung-2 propagation rewrites `[[slug]]` tokens in `pages[].body` (whole-token replacement). After the loop, `reconcile_body_links` rebuilds `outgoing_links` from `body`. This ordering is actually **correct** — rung 2 fixes the body tokens first, then the reconciler derives the correct `outgoing_links` from the fixed body. No interaction bug.

However, there's a subtle issue: `reconcile_slug_lists` (`compiler.py:359`) rebuilds `concept_slugs`/`article_slugs` from `pages[].slug`. If rung 2 has already coerced `pages[].slug` values, the reconciler derives the correct lists. This is also fine. **But** — rung 2's propagation logic also directly modifies `concept_slugs`/`article_slugs`. If rung-2's propagation and the post-loop reconciler produce different results (e.g., rung 2 propagates a rename to `concept_slugs` but the reconciler rebuilds from `pages[].slug` which was also renamed), they should converge. They will, because both derive from the same coerced slug values. But writing-plans should add a **post-reconcile re-validation** assertion (re-run schema after both reconcilers) as a belt-and-braces check, since today the reconcilers run without a final re-validation.

**Suggested change:** Writing-plans should add a final `validate()` call after `reconcile_body_links` + `reconcile_slug_lists` as a debug assertion (log-only, not gating). This catches any divergence between rung-2 propagation and the reconcilers before it reaches downstream stages silently.

---

### F7. [Low] — `_MAX_COMPILE_ATTEMPTS` semantics unchanged but naming could mislead
**Spec §5** does not change `_MAX_COMPILE_ATTEMPTS = 2`. With the ladder, the effective behavior is: emit → repair → validate → (fail?) → re-emit → repair → validate → (fail?) → quarantine. Still 2 model calls max. The repair steps don't add model calls, so the constant's meaning is preserved.

No change needed, but writing-plans should document that "attempts" counts **model calls**, not repair attempts. Repairs are free (deterministic, in-process).

---

## (d) Homes / contract

### F8. [Low] — `common/util/` home for JSON helper is correct; no issue
If rung 1 stays as `json-repair` (contra F4), `common/util/json_repair.py` is the right home: generic, stateless, stage-agnostic, `common` stays a leaf. The `compiler → common` dependency direction is legal under Phase B's contract.

If rung 1 becomes targeted escaping (per F4), the same home works: `common/util/json_escape_fix.py` is still a generic helper.

**No change needed** regardless of the F4 decision.

### F9. [Low] — `collapse_slug` in `common/paths` is the right call
`common/paths.py:51-66` is the slug-policy authority (`slugify`, `validate_slug`, `SLUG_PATTERN`). `collapse_slug` enforces the same policy — it's what `slugify` would produce for the malformed input. Placing it alongside the policy it enforces is correct ("policy not util"). No change needed.

---

## (e) Gaps / omissions

### F10. [Medium] — Measurability taxonomy should distinguish rung-1 sub-classes
**Spec §7:** `clean · repaired-syntax · coerced-slug · retried · quarantined`.

If rung 1 is `json-repair` (not targeted escaping per F4), the taxonomy should distinguish `repaired-syntax-escape` (targeted backslash fix) from `repaired-syntax-lib` (json-repair guess). This matters for observability: if `json-repair` starts over-reaching, the taxonomy lets you see it in run stats. If the F4 recommendation is adopted (targeted escaping only), the current `repaired-syntax` label is sufficient.

### F11. [Low] — Pass-1 deferral is correct
**Spec §6.** No Pass-1 syntax failures have been observed. Building rung 1 as reusable in `common/util/` but not wiring it into Pass-1 is the right data-before-principle call. Wiring it later is a one-liner. No change needed.

### F12. [Low] — No third recoverable class visible
The two live examples (LaTeX backslash, space-dash-space slug) are both instances of the LLM not applying documented formatting rules. A hypothetical third class — say, unescaped newlines in JSON strings — would be covered by the targeted-escaping approach (F4) or by `json-repair`. No separate class is visible in the current failure data. No change needed.

### F13. [Low] — Interaction with #104 retry is clean
#104 added the retry loop. #106 inserts repair steps inside that loop. No double-repair risk (repair is idempotent — collapse on an already-collapsed slug is a no-op). No masking risk (re-validation gates every repair). The interaction is correctly analyzed in the spec. No change needed.

---

## Findings summary

| # | Severity | Group | Summary |
|---|---|---|---|
| F1 | High | (a) | `warnings[].related_slugs[]` doesn't exist — delete from propagation list |
| F2 | High | (a) | Semantic re-validation must run inside the attempt loop, not after |
| F3 | Medium | (a) | Collision guard must check renamed slugs against all existing valid slugs |
| F4 | Medium | (b) | Commit to targeted backslash-escaping over `json-repair` for the known class |
| F5 | Low | (b) | Document "attempt on any schema failure" as intentional |
| F6 | Medium | (c) | Add post-reconcile debug re-validation to catch rung-2 / reconciler divergence |
| F7 | Low | (c) | Document that `_MAX_COMPILE_ATTEMPTS` counts model calls, not repairs |
| F8 | Low | (d) | `common/util/` home correct regardless of F4 decision |
| F9 | Low | (d) | `common/paths` home for `collapse_slug` correct |
| F10 | Medium | (e) | If keeping `json-repair`, add sub-class distinction to measurability taxonomy |
| F11 | Low | (e) | Pass-1 deferral correct |
| F12 | Low | (e) | No third recoverable class visible |
| F13 | Low | (e) | #104 interaction is clean |

---

## Bottom line

The design is **sound enough to turn into an implementation plan** after resolving two High and two Medium findings. The two Highs (F1, F2) are straightforward spec fixes — delete a phantom field and restructure the attempt loop so semantic validation is actually inside the re-validation gate. The two Mediums (F3, F4) are tightenings that the design already gestures toward but doesn't close.

**On the rung-1 `json-repair` vs targeted-escaping fork:** I recommend **targeted escaping**. The known failure class (stray `\` before non-JSON-escape characters) is narrow, well-characterized, and fixable in ~5 lines of content-preserving code. `json-repair` is a general-purpose tool that introduces a dependency and a content-fidelity surface area disproportionate to the problem. The spec's own analysis (§3 ⚠) already identifies the hole — the logical conclusion is to use the tool that doesn't have the hole. Keep `json-repair` as a documented future option if a second syntax-failure class appears that escaping can't cover.
