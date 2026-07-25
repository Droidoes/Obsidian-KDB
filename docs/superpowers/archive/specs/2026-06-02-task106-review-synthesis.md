# Task #106 — Design Panel Review Synthesis

**Panel:** Codex · Deepseek · Qwen · Gemini · Grok (5/5 read-only, guardrail-clean). **Date:** 2026-06-02.
**Verdict: unanimous `GO-WITH-CHANGES`.** The ladder architecture, re-validation gating, conservative slug scope, and the post-Phase-B homes are all endorsed. Three load-bearing changes + several tightenings before writing-plans.

## Load-bearing (n/n or near) — must fold

### LB1 — Rung-1: targeted backslash-escaping, NOT `json-repair` **[5/5]**
Codex(High) · Deepseek(Critical) · Qwen(Med) · Gemini(High) · Grok(High). **Unanimous.** The only confirmed syntax class is a stray `\` before a non-JSON-escape char. A targeted pre-processor — double any `\` not followed by `["\\/bfnrtu]` or `u[0-9a-fA-F]{4}` → re-parse — is **content-preserving by construction, zero-dependency (~5–10 lines), and exactly fits the live class**. `json-repair` is a general fixer whose other guesses (delimiter insertion, quote/bracket fixup) are *more* content-fidelity holes the structure-only gates can't catch — the spec's own ⚠ is the argument against it. **Decision the panel says to make now, not defer to writing-plans.**
→ **Fold:** rung-1 = targeted escaping (primary); **drop the `json-repair` pip dependency** from scope (demote to a documented future fallback only if a second, escaping-resistant syntax class appears live). Rename the home `common/util/json_repair.py` → e.g. `common/util/json_escape_fix.py` (name the behavior). The §9 "LaTeX `\(n-1\)` survives intact" assertion stays the primary acceptance gate.

### LB2 — Move `semantic_check` INTO the attempt loop **[5/5]**
Codex · Deepseek · Qwen · Gemini · Grok all High. The spec's safety claim is "every repair re-validation-gated (parse→schema→**semantic**)." But in real `compiler/compiler.py`, `semantic_check` runs **after** the loop `break` (≈341), not inside. So a rung-2 coercion that passes schema but fails semantic (e.g. coerced `summary_slug` no longer matches its summary page) **breaks → fails semantic → quarantines with no retry budget left** — violating the guardrail.
→ **Fold:** restructure the loop so the per-attempt gate is `parse → [repair] → schema → semantic`, breaking only when schema_ok **and** semantic_ok; a post-repair semantic failure on a non-final attempt falls to retry. (Deepseek's lone counter — "semantic failures are unrecoverable, natural flow is fine" — is the minority read; the other 4 + the spec's stated guardrail say make the gate real. Moving semantic in-loop is also just-correct regardless of #106.)

### LB3 — Remove phantom field `warnings[].related_slugs[]` **[5/5]**
All five verified against `compiler/schemas/compiled_source_response.schema.json`: `warnings` is `array<string>`; it has **no** `related_slugs`. Only `log_entries[]` carry `related_slugs`.
→ **Fold:** strike it from §4b. Authoritative 7-field propagation list: `summary_slug` · `concept_slugs[]` · `article_slugs[]` · `pages[].slug` · `pages[].outgoing_links[]` · whole `[[…]]` tokens in `pages[].body` · `log_entries[].related_slugs[]`.

## Strong (3–4/5) — fold

- **S1 — whole-token wikilink rewrite must use a regex preserving `|display` and `#anchor` [3/5: Codex/Gemini/Grok].** A literal `[[old]]→[[new]]` misses `[[old|Text]]` and `[[old#sec]]`, leaving malformed slugs in the body → `outgoing_links` (coerced) vs body (un-coerced) mismatch, and `reconcile_body_links` (which rebuilds links from body) re-introduces the bad slug. Use a `_WIKILINK_RE`-style match (see `compiler/canonicalize.py:216`, `compiler/validate_source_response.py:115`) that rewrites only the target slug portion. Note: `body_wikilink_slugs()` only extracts *valid* slugs, so the rewrite must operate on raw body text to see malformed links.
- **S2 — collision guard checks ALL present slug values, not just malformed-vs-malformed [4/5: Codex/Deepseek/Qwen/Grok].** Realistic case: valid `foo-bar` + malformed `foo--bar` both present → collapse lands on the existing valid one. Build `would_be = collapse(v)` for every distinct slug across all bearing fields; refuse if any would-be bucket has >1 pre-image OR collides with an unchanged valid slug. (Codex's refinement — distinguish *defining* slugs `summary_slug`/`pages[].slug` from *reference-only* — is an optional nuance; the safe default is refuse-on-any-collision.)
- **S3 — compositional telemetry, not a flat enum [5/5 touched].** `clean/repaired-syntax/coerced-slug/retried/quarantined` aren't mutually exclusive (retried **and** coerced; both rungs on one emission). Replace with orthogonal facts persisted on `RespStatsRecord`: `compile_attempts:int`, `syntax_repaired:bool`, `slug_coerced:bool`, `final_status`. Keep the existing `attempts` (SDK-level retry count) separate. Real surface changes in `common/types.py`, `common/llm_telemetry.py`, `compiler/compiler.py`.

## Tightenings (fold into the plan / TDD)

- **T1 — empty-after-collapse `---`→`-`→`""` must refuse** (Gemini/Grok Low): a pure-separator slug collapses to empty; refuse the rename, let validation fail honestly.
- **T2 — reserved-slug guard** (Codex Med): `index--`→`index` could pass per-call schema but is reserved; `collapse_slug` should reject a target that fails `paths.validate_slug()` (covers reserved + length + pattern).
- **T3 — repair a candidate copy, don't mutate `state["parsed_json"]` in place** (Codex High): only assign on acceptance, so a failed-repaired payload doesn't leak into resp-stats; decide+document the failed-attempt artifact state (Grok).
- **T4 — reset stale per-attempt state each iteration** (Codex High): `parse_ok`/`parsed_json`/schema fields persist across attempts today; #106 restructures this loop, so fix the stale-state class here.
- **T5 — name the new fn distinctly from `repair(cr, findings)`** (Deepseek): the existing `compiler/repair.py:repair()` consumes `cr` (compile_result) post-semantic; the new coercion is per-source `parsed_json` in-loop — sibling, e.g. `coerce_slugs_and_propagate(parsed_json)`.
- **T6 — create `common/util/__init__.py`** (Deepseek/Grok).
- **T7 — info-log + idempotence checks**: emit a "repaired-syntax, proceeding" log when a rung rescues in-loop (not the failure warning); add a post-reconcile debug re-validate to catch rung-2/reconciler divergence (Qwen/Grok). `_MAX_COMPILE_ATTEMPTS` semantics unchanged (still 2 model calls).

## One genuine DECISION for Joseph — lowercase in the slug coercion?
**Gemini (1/5) dissents toward MORE coercion:** add `.lower()` to the transform. His argument is sharp and consistent with the spec's *own* principle: `slugify()`'s D19 rule includes `.lower()`, casing is non-semantic in kebab-slug space, so lowercasing is the **same deterministic D19 enforcement** as the hyphen-collapse — excluding it is inconsistent, and uppercase slugs (`Sleep-and-Aging`) are a common LLM artifact that would needlessly retry/quarantine.
**The other 4 + the spec + project discipline** favor conservative (collapse+strip only): uppercase-slug is **not a confirmed live class** ([[feedback_data_before_principle]]), and [[feedback_coerce_dont_reject]] reserves coercion for benign **confirmed** classes.
**The tension:** Gemini exposes a real inconsistency — if "enforce D19 post-LLM" justifies collapse, the same logic justifies lowercase. Pick one framing: (A) **strict confirmed-class** (collapse+strip only; add lowercase if/when it appears live) — my lean, per data-before-principle; or (B) **D19-formatting-class** (collapse+strip+lowercase — the full deterministic, non-semantic subset of slugify). Either way, fix §4a's wording (Deepseek: "enforce D19" → "the hyphen-run [+lowercase?] subset of D19").

## Gaps noted, no action (data-before-principle)
- Third class — trailing prose after JSON (Deepseek Med): not observed; targeted escaping or a future `trim-after-last-}` rung covers it later.
- Pass-1 deferral (Pass-2 now): unanimously endorsed correct.
- #104 retry interaction: clean (repair idempotent, re-validation-gated).

## Bottom line
Design is sound; turn it into a plan after folding **LB1–LB3** (rung-1 = targeted escaping; semantic in-loop; drop phantom field) + **S1–S3** (regex wikilink rewrite; all-values collision guard; compositional telemetry), with T1–T7 as plan/TDD detail. The single open call is **lowercase-in-coercion (A vs B)** — Joseph's. Notably the biggest change *removes* a dependency and simplifies rung-1.
