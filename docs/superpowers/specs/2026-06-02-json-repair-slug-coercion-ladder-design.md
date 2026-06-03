# Task #106 — JSON-escape + slug-coercion robustness ladder (design v0.2)

> **Status:** **v0.2 — panel-ratified** (5-model design panel 2026-06-02, unanimous GO-WITH-CHANGES; synthesis `docs/superpowers/specs/2026-06-02-task106-review-synthesis.md`). All load-bearing changes folded (rung-1 = targeted backslash-escaping not `json-repair`; semantic check moves into the attempt loop; phantom `warnings[].related_slugs[]` removed; regex wikilink rewrite; all-values collision guard; compositional telemetry; lowercase added to the coercion — Joseph's call B). **Ready for `writing-plans`.**
> **Codebase:** Phase B / `v0.5.2` has landed — the homes below are REAL (`common/paths.py`, `compiler/repair.py`, `compiler/compiler.py`, `compiler/schemas/`; `common/util/` is created by this task). **No new pip dependency** (the `json-repair` package is dropped — see §3).
> **Sequence:** writing-plans → TDD → run-8 (validate robustness), before 0.6.

---

## 1. Problem

Two recurring **recoverable** LLM-emission malformation classes in Pass-2 (compile), both currently rescued **only by the stochastic retry** (#104) — recovery rides on a lucky re-emission, not anything deterministic. #106 makes recovery deterministic so neither class reaches quarantine when it is in fact recoverable. Both are confirmed live (run-5 **and** run-6):

| # | Class | Live case (run-6) | Error | Root cause |
|---|---|---|---|---|
| 1 | **JSON-syntax** (bytes don't parse) | `Relative Ranking Methods - Borda, …` | `Pass-2 attempt 1/2 invalid JSON, retrying: Expecting ',' delimiter` | unescaped LaTeX (e.g. `\(n-1\)`) inside a JSON string — a stray `\` before a non-JSON-escape char |
| 2 | **Schema/slug** (parses, a slug violates the pattern) | `Sleep and Aging - Research on Aging.md` | `[$.summary_slug] 'summary-…aging---research-on-aging' does not match '^summary-[a-z0-9]+(?:-[a-z0-9]+)*$'` | the title's `" - "` slugified to `---`; the model didn't collapse the run |

**Grounding insight (covers both rungs).** The canonical `slugify()` (`common/paths.py:51`) is `re.sub(r"[^a-zA-Z0-9]+", "-", ascii).strip("-").lower()` — it **collapses any run of non-alphanumerics to one hyphen, strips the edges, and lowercases**. The model simply failed to apply rules it was supposed to. Slug coercion (§4) is therefore **enforcing the existing D19 slug policy deterministically, post-LLM** — not inventing a rule (cf. `feedback_post_llm_deterministic_override`). Rung 1 (§3) is the analogous enforcement of valid JSON string-escaping.

---

## 2. The ladder

Per source, per pass (extends #104's retry):

```
emit → repair/normalize → validate(parse, schema, semantic)
   ├─ valid → proceed
   └─ invalid → retry (1 fresh emission) → repair/normalize → validate
          ├─ valid → proceed
          └─ invalid → quarantine
```

i.e. **`emit → repair/normalize → retry → repair/normalize → quarantine`**. Repair runs on **both** emissions (the retry can re-emit the same malformation). **Guardrail:** every repair is **re-validation-gated** — a repaired emission must pass the same `parse → schema → semantic` it would without repair (and per LB2 below, *all three* are now checked inside the attempt loop). A wrong/over-reaching repair cannot sneak through; it falls to the next rung. `_MAX_COMPILE_ATTEMPTS` is unchanged (2 model calls); repairs are in-process and free.

---

## 3. Rung 1 — targeted JSON backslash-escaping  *(panel LB1 — was `json-repair`)*

- **Mechanism:** a **targeted, deterministic, content-preserving pre-processor** — NOT a general repair library. On the raw emission text, double any backslash that is **not** a valid JSON escape: `\` not followed by one of `["\\/bfnrtu]` or by `u[0-9a-fA-F]{4}` → `\\`. Re-parse. (~10 lines, zero dependencies.)
- **Why not `json-repair`** (the panel was unanimous, 5/5): the only confirmed syntax class is the stray-backslash case, and targeted escaping is **content-preserving by construction** — the backslash survives in the parsed string exactly as the model intended, so the LaTeX `\(n-1\)` is preserved. A general fixer (`json-repair`) can "resolve" the same input by *silently stripping* the backslash → valid JSON that passes every structure gate while corrupting body content (the schema/semantic checks validate structure, not body prose). Its other guesses (delimiter insertion, quote/bracket fixup) are the same class of undetectable content-fidelity hole. The original spec flagged this as a ⚠; targeted escaping **closes it by construction**. **The `json-repair` pip dependency is dropped from scope** — reconsider only if a second, escaping-resistant syntax class appears live (data-before-principle).
- **Trigger / flow:** fires only when `json.loads` (the parse step) raises → escape → re-parse → schema → semantic. If still unparseable (or parses but fails schema/semantic), fall to retry.
- **Home:** `common/util/json_escape_fix.py` — a generic, stateless, stage-agnostic helper (named for the behavior). First occupant of `common/util/` (this task also creates `common/util/__init__.py`). *("util is common.")* Must **not** live in `response_normalizer` (its contract is "strict extraction, NO repair").

---

## 4. Rung 2 — slug coercion

### 4a. The per-slug transform — `common/paths.collapse_slug()`
- **Lowercase, then collapse** consecutive hyphens `-{2,}` → `-`, then **strip** leading/trailing `-`. This is exactly the deterministic, non-semantic subset of what `slugify()` applies. *(Decision B, Joseph 2026-06-02: lowercase is included — it is the same deterministic D19 rule as the collapse, casing is non-semantic in kebab-slug space, and wrong-case is a common LLM artifact; including it is consistent with the "enforce D19" justification.)*
- **Deliberately NOT coerced:** space-stripping, invalid-character removal, unicode folding. A slug with a **space** (`Bayes Theorem`) or other non-`[a-zA-Z0-9-]` content is a *structural* extraction failure → still **fail → retry → quarantine**. Lowercase + hyphen-collapse + edge-strip are unambiguous formatting; removing spaces/chars would be guessing intent and could mask a real failure (`feedback_coerce_dont_reject`).
- **Empty result → refuse:** a pure-separator slug (e.g. `---`) collapses to `""`. `collapse_slug` must **refuse** (return the input unchanged / signal no-coercion) when the result is empty or still fails `paths.validate_slug()` — never propagate `{old: ""}`.
- **Reserved/length guard:** the coerced target must pass `paths.validate_slug()` (rejects reserved `index`/`log`, over-length, and any residual pattern violation). E.g. `index--` → `index` is a **reserved** slug → refuse the coercion (don't let it slip past the per-call gate to fail later at aggregate validation).
- **Home:** `common/paths` — slug **policy**, sibling to `slugify`/`validate_slug`/`SLUG_PATTERN`, **not** `common/util`. Pass-agnostic, so future Pass-1 slugs reuse it.

### 4b. Reference propagation
A slug is an **identifier**; coercing one value must propagate to **every** reference in the same `parsed_json`, or the result is internally inconsistent. Build a rename map `{old: new}` (only for values that actually change) and apply across the **7 real** slug-bearing fields (cross-checked against `compiler/schemas/compiled_source_response.schema.json` — `warnings` is `array<string>`, it has **no** `related_slugs`):

`summary_slug` · `concept_slugs[]` · `article_slugs[]` · `pages[].slug` · `pages[].outgoing_links[]` · whole `[[…]]` tokens in `pages[].body` · `log_entries[].related_slugs[]`.

- **Body wikilink rewrite (panel S1):** use a **regex** (modeled on the existing `_WIKILINK_RE` in `compiler/validate_source_response.py:115` / `compiler/canonicalize.py:216`) that matches the whole `[[…]]` token, rewrites **only the target-slug portion** through the rename map, and **preserves `|display` and `#anchor`** (`[[old|Text]]` → `[[new|Text]]`, `[[old#sec]]` → `[[new#sec]]`). Operate on the **raw body string** (not `body_wikilink_slugs()`, which only extracts *valid* slugs and would skip the malformed link). A literal `[[old]]→[[new]]` substring replace is wrong (misses alias/anchor forms; risks prefix corruption).

### 4c. Collision guard
Build `would_be = collapse_slug(v)` for **every distinct slug value present across all 7 bearing fields** (valid AND malformed). **Refuse the entire coercion** (leave `parsed_json` unchanged → fall to retry/quarantine) if either: any `would_be` bucket has **>1 distinct pre-image**, OR a `would_be` **collides with an unchanged already-valid slug**. This covers malformed-vs-malformed *and* the realistic malformed-vs-valid case (valid `foo-bar` + malformed `foo--bar` → collapse lands on the valid one). Only apply renames when there is no collision.
- *(Optional refinement, Codex — defer unless needed: distinguish defining slugs `summary_slug`/`pages[].slug` from reference-only fields; a malformed reference collapsing onto an existing definition can be benign. The safe default above — refuse on any collision — is the writing-plans baseline.)*

### 4d. Home for the orchestration
The rename-map + propagation + collision-guard live in **`compiler/repair.py`** as a **sibling** to the existing `reconcile_body_links`/`reconcile_slug_lists`/`repair(cr, findings)` — a **distinctly named** new function operating on per-source `parsed_json` in-loop (e.g. `coerce_slugs_and_propagate(parsed_json) -> bool`), NOT a modification of `repair(cr, findings)` (which consumes the post-semantic compile_result `cr`). It calls `common/paths.collapse_slug()` for the per-value transform. `compiler → common` is legal under the B.3 contract.

---

## 5. Placement in `compile_one`'s attempt loop  *(incl. panel LB2)*

Real flow in `compiler/compiler.py`: attempt loop @242; `json.loads` @305; `validate_source_response.validate` (schema) @322; today `break` on schema-ok @~339 then `semantic_check` @341 **after** the loop; reconcilers @354/362.

**LB2 — make the re-validation gate real (semantic moves INTO the loop).** Today semantic runs post-loop, so a rung-2 coercion that passes schema but fails semantic would `break` → fail → quarantine with **no retry budget**, violating the guardrail. Restructure the per-attempt gate to:

```
call → extract → parse(+rung-1 escape on parse-fail) → schema(+rung-2 coerce on schema-fail) → semantic
   break ONLY when schema_ok AND semantic_ok ; otherwise (non-final attempt) → retry
```

Insertion points, both **inside the loop, before the retry/break decision**:
- **Rung 1** at the **parse** step (`compiler.py:305`): on `json.loads` failure → `json_escape_fix` → re-parse → continue to schema; only then decide retry/fail.
- **Rung 2** at the **schema** step (`compiler.py:322`): on **any** schema failure → `coerce_slugs_and_propagate(parsed_json)` → re-validate. **Do not sniff the error string** — attempt the coercion and let re-validation decide (non-slug failures → no-op → fall through). *(Deliberate: class-agnostic; the no-op cost is negligible; the re-validation gate is the safety.)*

**Mutation discipline (panel T3/T4):** repair a **candidate copy**, not `state["parsed_json"]` in place; assign to `state` only on acceptance (so a failed-repaired payload doesn't leak into resp-stats). **Reset attempt-local gate state** (`parse_ok`/`parsed_json`/`schema_errors`/…) at the top of each iteration so a final parse-fail can't read a prior attempt's stale `parsed_json`.

After acceptance, the existing `reconcile_body_links`/`reconcile_slug_lists` run as today; because rung-2 already rewrote the body tokens and slug lists consistently, they are convergent near-no-ops. Writing-plans adds a debug (non-fatal) re-validate after the reconcilers to catch any divergence.

---

## 6. Pass scope
- **Pass-2 gets both rungs now** — both confirmed live failures are Pass-2.
- **Rung 1 (`json_escape_fix`)** is built reusably in `common/util/`; Pass-1 adopts it only when a live Pass-1 syntax failure appears (data-before-principle).
- **Rung 2 (`collapse_slug`)** is pass-agnostic by construction.

---

## 7. Measurability  *(panel S3 — compositional, not a flat enum)*

The flat `clean/repaired-syntax/coerced-slug/retried/quarantined` enum is **not** mutually exclusive (a source can be retried **and** slug-coerced; one emission can need both rungs). Persist **orthogonal facts** on `RespStatsRecord` (and thence the orchestrator/run summary):
- `compile_attempts: int` (1 or 2 — the loop attempt that produced the final `parsed_json`)
- `syntax_repaired: bool` (rung 1 produced a parse-ok payload that reached schema)
- `slug_coerced: bool` (rung 2 produced a schema-ok + semantic-ok payload)
- `final_status` (derive: `clean` | `repaired` | `retried-and-repaired` | `quarantined`)

Keep the existing `attempts` (SDK-level retry count) **separate** — don't overload it. Surface these on **failed/quarantined** sources too. Emit an info log when a rung rescues in-loop (e.g. `Pass-2 attempt 1/2 syntax-repaired, proceeding`) distinct from the existing failure-retry warning. Goal: make the deterministic-recovery rate observable and any over-reach detectable (`feedback_measurability_over_defensive_complexity`). Touches `common/types.py`, `common/llm_telemetry.py`, `compiler/compiler.py` (+ tests that build/assert `RespStatsRecord`).

---

## 8. Homes summary

| Piece | Home | Notes |
|---|---|---|
| targeted JSON escape (rung 1) | `common/util/json_escape_fix.py` (+ `common/util/__init__.py`) | generic leaf; *util is common*; **no pip dep** |
| slug transform `collapse_slug` (lowercase+collapse+strip) | `common/paths` | slug **policy**, sibling of `slugify`/`validate_slug` |
| rename + propagation + collision guard | `compiler/repair.py` (new `coerce_slugs_and_propagate`, sibling to `repair(cr,…)`) | per-source `parsed_json`, in-loop; `compiler → common` legal |
| compositional telemetry fields | `common/types.py` + `common/llm_telemetry.py` | `compile_attempts`/`syntax_repaired`/`slug_coerced`/`final_status` |

---

## 9. Test plan (TDD)

- **Rung 1:** `json_escape_fix` on the Borda-class input (unescaped `\(n-1\)`) → parseable JSON **with the `\(n-1\)` intact** (content-fidelity is the primary gate, not "it parses"); valid escapes (`\n`, `\\`, `\"`, `\uXXXX`) untouched; irreparable garbage still fails parse (falls through).
- **Rung 2 transform:** `collapse_slug('summary-Sleep-and-Aging---Research')` → `'summary-sleep-and-aging-research'` (lowercase + collapse + strip, decision B); no-op on already-valid; **refuses** empty-result (`---`), reserved (`index--`→`index`), and space-bearing (`Bayes Theorem`) — those fall through.
- **Rung 2 propagation:** a `---`/mixed-case `summary_slug` referenced in `pages[].slug`, `outgoing_links`, body `[[…]]` (incl. `[[old|Text]]` and `[[old#sec]]` forms), and `related_slugs` → after coercion all 7 fields consistent; schema + semantic pass.
- **Rung 2 collision:** valid `foo-bar` + malformed `foo--bar` both present → coercion refuses, `parsed_json` unchanged, falls through. Same for two malformed slugs colliding.
- **Semantic-in-loop (LB2):** a coercion that passes schema but fails semantic on a non-final attempt → **retries** (not immediate quarantine).
- **Both rungs, one emission:** a syntax fix that still leaves a collapsible slug → both fire, source recovers.
- **Ladder integration:** the two live fixtures (Borda, Sleep-and-Aging) recover deterministically on attempt 1 via the right rung (telemetry: `syntax_repaired`/`slug_coerced` true, `compile_attempts==1`); an irreparable case still quarantines; a non-slug schema error falls through with `parsed_json` unmutated.
- **Live gate — run-8** (sandbox vault): `exit_reason=ok`, 0 quarantined, the two recurring cases resolve via repair (not retry), links wired, 0 orphans.

---

## 10. Decisions log

- **Ladder + re-validation gate** — `emit → repair/normalize → retry → repair/normalize → quarantine`; conservative; re-validation-gated (now parse+schema+semantic in-loop, LB2).
- **Rung 1 = targeted backslash-escaping, `json-repair` DROPPED** — panel-unanimous (5/5); content-preserving by construction; no new dependency.
- **Rung 2 = lowercase + collapse `-{2,}` + edge-strip (decision B, Joseph 2026-06-02)** — the deterministic non-semantic subset of `slugify`; space/char-removal/unicode-folding excluded; empty/reserved → refuse.
- **Collision guard over ALL present slug values** (valid + malformed); refuse on any collision.
- **Body wikilink rewrite via regex preserving `|display`/`#anchor`** on raw body.
- **Compositional telemetry flags** (not a flat enum); `attempts` kept separate.
- **Homes:** `common/util/json_escape_fix` · `common/paths.collapse_slug` · `compiler/repair.coerce_slugs_and_propagate` (sibling to `repair(cr,…)`).
- **Sequence:** Phase B shipped (`v0.5.2`); #106 next (panel-ratified v0.2 → writing-plans → run-8).

---

## 11. References
- Memory: `project_json_repair_coerce_ladder`, `feedback_coerce_dont_reject`, `feedback_post_llm_deterministic_override`, `feedback_measurability_over_defensive_complexity`, `project_codebase_realignment`.
- Panel review + synthesis: `docs/superpowers/specs/2026-06-02-task106-review-{codex,deepseek,qwen,gemini,grok}.md` + `…-review-synthesis.md`.
- Slug policy (D19): `common/paths.py` (`slugify`, `validate_slug`, `SLUG_PATTERN`).
- Pass-2 contract: `compiler/schemas/compiled_source_response.schema.json`.
- Compile flow: `compiler/compiler.py` (`compile_one` attempt loop) + reconcilers `compiler/repair.py`; wikilink regex `compiler/validate_source_response.py` / `compiler/canonicalize.py`.
