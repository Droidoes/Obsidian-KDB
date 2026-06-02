# Task #106 — JSON-repair + slug-coercion robustness ladder (design)

> **Status:** design ratified-in-principle (this doc), **execution deferred until after Realignment Phase B**. **Gate before implementation:** this spec goes to an **external panel review** at #106 pick-up — run *after* Phase B lands, so the panel reviews it against the real `common/` + `compiler/` structure (Joseph, 2026-06-02; project-default panel per `feedback_external_review_panel_composition`, CLI reviewers under the output-file-only guardrail).
> **Sequence:** Phase B (package split) → run-7 (validate zero-behavior-change) → **#106: panel-review this spec → writing-plans → TDD → into the new homes** → run-8 (validate robustness). Both land **before 0.6**.
> **Why after B (reversal of the 2026-06-02 "#106-first" call):** #106's helpers belong in `common/` and `compiler/repair` — exactly the packages Phase B *creates*. Doing B first lets the helpers land in their final homes on the first write (zero relocation), makes the placement trivial, and turns #106 into a real-feature shakedown of B's package boundaries. Phase B is zero-behavior-change, so the recurring cases below stay retry-rescued throughout B — **no robustness gap is opened by waiting**.

---

## 1. Problem

Two recurring **recoverable** LLM-emission malformation classes in Pass-2 (compile). Both are currently rescued **only by the stochastic retry** (`attempt 1/2 … retrying` → ✓) added in #104 — recovery rides on a lucky re-emission, not on anything deterministic. #106 makes the recovery deterministic so neither class can reach quarantine when it is in fact recoverable.

Both classes are confirmed live (run-5 **and** run-6), each with a concrete example:

| # | Class | Live case (run-6) | Error | Root cause |
|---|---|---|---|---|
| 1 | **JSON-syntax** (bytes don't parse) | `Relative Ranking Methods - Borda, Condorcet, and Aggregation.md` | `Pass-2 attempt 1/2 invalid JSON, retrying: Expecting ',' delimiter at line 20` | unescaped LaTeX (e.g. `\(n-1\)`) inside a JSON string value |
| 2 | **Schema/slug** (parses, a slug field violates the pattern) | `Sleep and Aging - Research on Aging.md` | `[$.summary_slug] 'summary-sleep-and-aging---research-on-aging' does not match '^summary-[a-z0-9]+(?:-[a-z0-9]+)*$'` | the title's `" - "` (space-dash-space) slugified to `---`; the model mapped each separator to a hyphen instead of collapsing the run |

**Grounding insight for class 2:** the canonical `slugify()` (`paths.py`) is `re.sub(r"[^a-zA-Z0-9]+", "-", ascii).strip("-").lower()` — it **already collapses any run of non-alphanumerics to a single hyphen and strips the edges**. So `slugify("Sleep and Aging - Research on Aging")` → `sleep-and-aging-research-on-aging` (single hyphen). The model simply didn't apply the documented rule. The slug coercion is therefore **not a new invented rule** — it is **enforcing the existing D19 slug policy deterministically, post-LLM** (cf. memory `feedback_post_llm_deterministic_override`).

---

## 2. The ladder

Per source, per pass (mirrors and extends #104's retry):

```
emit → repair/normalize → validate
   ├─ valid → proceed
   └─ invalid → retry (1 fresh emission) → repair/normalize → validate
          ├─ valid → proceed
          └─ invalid → quarantine
```

i.e. **`emit → repair/normalize → retry → repair/normalize → quarantine`**. The repair/normalize step runs on **both** emissions — the retry can re-emit the same malformation, so normalizing its output too is what prevents the second-attempt quarantine.

**Guardrail (preserves the "strict extraction, no semantic repair" integrity intent):** every repair is **re-validation-gated** — a repaired emission must pass the same `parse → schema → semantic` checks it would have without repair. A wrong/over-reaching repair cannot sneak through; it simply falls to the next rung (retry, then quarantine). Repair never *replaces* validation; it runs *before* it.

---

## 3. Rung 1 — JSON-syntax repair

- **Mechanism:** the **`json-repair`** pip package (purpose-built, dependency-free; do **not** hand-roll). **New dependency** — `json-repair` is not currently installed; #106 adds it to `pyproject.toml`.
- **Trigger:** fires only when `json.loads` (the parse step) raises — never on already-valid JSON.
- **Flow:** `parse fails → json_repair.repair_json(text) → re-parse → schema → semantic`. If the repaired bytes still don't parse, or parse but fail schema/semantic, fall to retry.
- **Trust model:** trust the package's output **but gate it on re-parse + the existing schema + semantic validation**. `json-repair` can make aggressive guesses (e.g. inserting a delimiter); a wrong *structural* guess produces parseable-but-wrong JSON that the schema/semantic layer rejects → falls to retry/quarantine.
- **⚠ Content-fidelity hole (the schema/semantic gate does NOT close it):** schema + semantic validation check *structure* and slug/link consistency — they do **not** validate body *content*. The Borda case is an unescaped LaTeX `\(n-1\)`; depending on how `json-repair` resolves the invalid `\(` escape it may emit **valid JSON with the backslash silently stripped** → passes every gate while corrupting the LaTeX. So full-trust-gated protects structure, **not content**. **writing-plans MUST** (a) probe `json-repair`'s *actual* behavior on an invalid `\(`/`\)` escape, and (b) decide whether the correct rung-1 fix for *this class* is **targeted backslash-escaping** (escape stray `\` before re-parse) rather than trusting `json-repair`'s guess. The test plan asserts the LaTeX **survives** (§9), not merely that the bytes parse.
- **Home (post-Phase-B):** `common/util/json_repair.py` — a generic, stateless, stage-agnostic helper. *("util is common.")* This module is the **first occupant of `common/util/`**; Phase B does not pre-create the dir.
- **Contract honesty:** repair must **not** live in `response_normalizer` — that module's stated contract is "strict extraction, NO semantic repair." A sibling leaf keeps that honest.

---

## 4. Rung 2 — slug coercion

### 4a. The per-slug transform (conservative)
- **Collapse** consecutive hyphens `-{2,}` → `-`, and **strip** leading/trailing `-`. Nothing else. This is exactly what `slugify()` would do to the malformed string.
- **Deliberately NOT coerced:** lowercasing, space-stripping, invalid-character removal, unicode folding. A slug like `Bayes Theorem` (space + uppercase) or any genuinely garbled slug should still **fail → retry → quarantine**, not be silently rewritten. Collapse/edge-strip is *formatting* normalization where the model's intent is unambiguous; the rest would be us **guessing intent** and could **mask a real failure** (cf. memory `feedback_coerce_dont_reject` — reserve coercion for benign, confirmed classes; reject the unrecoverable).
- **Home (post-Phase-B):** `common/paths.collapse_slug()` — sibling to `slugify()`/`validate_slug()`. It is slug **policy**, not a generic util → it lives with the policy authority, **not** in `common/util/`. *("common may not be util.")* Pass-agnostic, so future Pass-1 slugs call the same function.

### 4b. Reference propagation (the non-trivial part)
A slug is an **identifier**. Coercing one value must propagate to **every** reference in the same compile-result, or the result is internally inconsistent (dangling links, summary not matching its page). Build a rename map `{old_slug: new_slug}` and apply across **all** slug-bearing fields (per `compiled_source_response.schema.json`):

- `summary_slug`
- `concept_slugs[]`, `article_slugs[]`
- `pages[].slug`
- `pages[].outgoing_links[]`
- the `[[slug]]` tokens inside `pages[].body` (bidirectional with `outgoing_links`) — **rewrite whole `[[…]]` tokens, not substring-replace** (a substring replace would corrupt a longer slug that contains the renamed one as a prefix)
- `log_entries[].related_slugs[]` (and any `warnings[].related_slugs[]`)

- **Home (post-Phase-B):** `compiler/repair` — this is compile-result-structural, belongs with the existing reconcilers (`reconcile_body_links`, `reconcile_slug_lists`). It **calls** `common/paths.collapse_slug()` for the per-slug transform. Dependency direction `compiler → common` is legal under Phase B's contract.

### 4c. Collision guard (correctness)
If collapsing makes two **distinct** slugs map to the **same** new slug (e.g. `foo--bar` and `foo-bar` both present), that is a genuine conflict — do **not** silently merge. The coercion must **detect the collision and refuse** (leave the result unchanged), letting it fall to retry → quarantine. Document and unit-test this case.

---

## 5. Placement in `compile_one`'s attempt loop

Current (pre-Phase-B) flow in `kdb_compiler/compiler.py` per attempt: `call → extract → parse → schema → (retry on fail) → break → semantic → reconcile_body_links/reconcile_slug_lists`. The two rungs insert **inside the attempt loop, before the retry decision**:

- **Rung 1** at the **parse** step (~`compiler.py:300–318` today): on `json.loads` failure → `json_repair` → re-parse. Only then decide retry/fail.
- **Rung 2** at the **schema** step (~`compiler.py:320–338` today): on **any** schema failure → attempt slug-collapse + propagation across all slug fields → re-validate (schema + semantic). **Do not sniff the error string** to detect the slug-pattern class — just attempt the collapse and let re-validation decide: if the failure wasn't a collapsible-slug one, the collapse is a no-op (or still-invalid) and it falls through unchanged. Only then decide retry/fail.

(Line numbers are pre-Phase-B and will shift once `compiler.py` moves into the `compiler/` package; the *insertion points* — at parse-fail and at schema-fail, before the retry branch — are stable.)

---

## 6. Pass scope

- **Pass-2 (compile) gets both rungs now** — that is where both confirmed live failures occur.
- **Rung 1 (`json_repair`) is built reusably** in `common/util/` so Pass-1 can adopt it the moment a live Pass-1 syntax failure appears — but it is **not wired into Pass-1 now** (data-before-principle; no Pass-1 syntax failure observed). Wiring it later is a one-liner.
- **Rung 2 (`paths.collapse_slug`) is pass-agnostic** by construction — ready for future Pass-1 slugs without change.

---

## 7. Measurability

**Log which rung resolved each source** so we can prune repair scope if it ever over-reaches (cf. memory `feedback_measurability_over_defensive_complexity`). Taxonomy, persisted on the resp-stats / orchestrator record:

`clean` · `repaired-syntax` (rung 1) · `coerced-slug` (rung 2) · `retried` (a 2nd emission was needed) · `quarantined`

This makes the deterministic-recovery rate observable across runs and flags any case where a repair fired but shouldn't have.

---

## 8. Homes summary (post-Phase-B)

| Piece | Home | Rationale |
|---|---|---|
| JSON-syntax repair (`json-repair` wrapper) | `common/util/json_repair.py` | generic stateless helper; *util is common*; first occupant of `common/util/` |
| slug per-value transform (`collapse_slug`) | `common/paths` | slug **policy**, sibling of `slugify`/`validate_slug`; *common but not util* |
| slug rename + propagation + collision guard | `compiler/repair` | compile-result-structural; with the existing reconcilers; `compiler → common` |
| `json-repair` dependency | `pyproject.toml` | new dependency |

---

## 9. Test plan (TDD)

- **Rung 1 unit:** `repair_json_text` on the Borda-class input (unescaped LaTeX → `Expecting ',' delimiter`) returns parseable JSON **that still contains the intact LaTeX `\(n-1\)`** (content-fidelity assertion, per §3's ⚠ — not merely "it parses"); on irreparable garbage returns something that still fails parse (so it falls through, not a false success).
- **Rung 2 unit (transform):** `collapse_slug('summary-sleep-and-aging---research-on-aging')` → `'summary-sleep-and-aging-research-on-aging'`; edge-strip cases; **no-op** on already-valid slugs; **refuses** `Bayes Theorem`-class (uppercase/space) — leaves it to fail.
- **Rung 2 unit (propagation):** a compile-result with a `---` summary_slug referenced in `pages[].slug`, `outgoing_links`, body `[[…]]`, and `related_slugs` → after coercion all references updated consistently; schema + semantic pass.
- **Rung 2 unit (collision guard):** two distinct slugs collapsing to the same value → coercion refuses, result unchanged, falls through.
- **Ladder integration:** the two live fixtures (Borda, Sleep-and-Aging) recover deterministically on attempt 1 (no retry needed); an irreparable case still quarantines; the resolving rung is logged.
- **Live gate:** **run-8** on the sandbox vault in the post-Phase-B structure. Pass criteria: `exit_reason=ok`, 0 quarantined, the two recurring cases resolve via `repaired-syntax` / `coerced-slug` (not `retried`), links wired, 0 orphans.

---

## 10. Decisions log

- **Conservative repair/normalize, re-validation-gated** — confirmed (Joseph, 2026-06-02). Ladder: `emit → repair/normalize → retry → repair/normalize → quarantine`.
- **Slug coercion = collapse + edge-strip only** (enforce D19; no intent-guessing) — confirmed.
- **`util/` inside `common/`** taxonomy — adopted (Joseph): *util is common* (→ `common/util/json_repair`), *common may not be util* (→ slug policy stays in `common/paths`). Phase B does not pre-create `common/util/`; #106 creates it.
- **Sequence: Phase B first, then #106** — confirmed (Joseph, 2026-06-02), reversing the earlier #106-first call; rationale in the header.

---

## 11. References

- Memory: `project_json_repair_coerce_ladder`, `feedback_coerce_dont_reject`, `feedback_post_llm_deterministic_override`, `feedback_measurability_over_defensive_complexity`, `project_codebase_realignment`.
- Realignment Phase-B brief: `docs/superpowers/specs/2026-06-01-codebase-realignment-panel-brief.md` (defines `common` / `tools` / `compiler` packages + dependency contract).
- Slug policy (D19): `kdb_compiler/paths.py` (`slugify`, `validate_slug`, `SLUG_PATTERN`).
- Pass-2 contract: `kdb_compiler/schemas/compiled_source_response.schema.json`.
- Compile flow: `kdb_compiler/compiler.py` (`compile_one` attempt loop).
