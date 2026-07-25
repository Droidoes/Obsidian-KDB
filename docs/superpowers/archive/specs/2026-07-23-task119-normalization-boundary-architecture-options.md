# Task #119 — normalization boundary: architecture options + Joseph's challenge (for Codex design feedback)

**Date:** 2026-07-23 (v1.0) · revised 2026-07-23 (v1.1, v1.2, v1.3) · **Author:** Kimi (for Joseph + Codex design review)
**Status:** **Phase-1 RATIFIED by Joseph 2026-07-23** — Option 2 + form (b) + no links-to-current-summary + fail-closed alias handling. Codex R3/R4 absorbed (v1.1/v1.2); Codex R5 (**GO with minor documentation corrections**) absorbed in v1.3. Blueprint phase next (implementation NOT started).
**Seed:** `docs/superpowers/archive/specs/2026-07-22-task119-phase5-summary-slug-failure-analysis.md` (v1.2 — governing rule + scope, Codex R1/R2 absorbed) · R1 `…-review-codex.md` · R2 `…-review-codex-v2.md`
**Reviews:** Codex R3 `…-architecture-options-review-codex.md` · Codex R4 `…-options-r3-absorption-response-review-codex.md` (F1/F2 contradictions fixed in v1.2) · Codex R5 `…-options-r3-absorption-response-review-codex-v2.md` (**GO** — no architectural blocker; two minor doc corrections in v1.3; *"Joseph can explicitly confirm: Option 2 + form (b) + no links-to-current-summary + fail-closed alias handling… close the Phase-1 decision gate… captured in the task ledger and North Star before moving into the blueprint phase."*)

---

## 1. Where enforcement sits today (verified against code)

Per-source order in `compiler/compiler.py` (verified code anchor `f8c9ad8`; current `main` is `4d60e6d` — the intervening commit is docs-only, so the analysis stands):

```
pre-call stem check (underivable → validate/PathError, zero API spend)
→ model call (json_mode) → recover_json_response (#114: carrier-only — select, never edit)
→ schema validate (strict: compiled_source_response.schema.json — pages[] × (slug, page_type, title, body) + optional compilation_notes)
→ [schema fail] coerce_slugs_and_propagate (#106 rung-2: collapse-slug rename, collision-refusing) → re-validate
→ semantic_check: exactly one page_type=="summary" AND slug == expected_summary_slug(source_id)
      ← THE QUARANTINE POINT. retry once, then quarantine (validate/SemanticCheckError)
→ CompiledSource build (runner injects source_id, supports_page_existence, status)
→ aggregate gate → canonicalize (alias-ledger registry; body-wikilink rewrite) → post-canon exact summary invariant re-check
→ page_writer → graph intake → manifest
```

Key verified facts:

- The observed failure class (`gemini31`, `whats`) is **schema-valid** kebab-case. It dies only at the exact-match semantic gate (`compiler/validate_source_response.py:78`).
- `expected_summary_slug(source_id)` is a pure deterministic derivation (`compiler/summary_slug.py`): stem → slugify → 112-char budget → `summary-` prefix. Python knows the answer with certainty before the model speaks.
- **Body-wikilink targets are ungated today** (R3 F2, verified): the schema treats `body` as an opaque nonempty string; `semantic_check` checks only summary count + exact slug; graph intake **silently skips** a LINKS_TO target when no such Entity exists (`kdb_graph/intake.py:345-373`, whose docstring's "validator catch upstream" is stale — no such gate exists; `dangling_link_rate` is a benchmark KPI, not a gate).
- The current schema artifact is the **prompt-facing model contract**: injected into the user message by `prompt_builder.load_response_schema_text` (`prompt_builder.py:36,84-92`), with `RESPONSE_CONTRACT` + the exemplar referencing the summary-slug convention (R4 F4).
- Precedent machinery already in the tree: #114 recovery (carrier tolerance), #106 rung-2 slug coercion (form normalization with collision refusal, gated by re-validation), #74 canonicalize (registry-authority resolution, fatal on ambiguity).

## 2. The audit surface (§5-item-4 preview — this sizes every option)

The entire normalization-relevant surface of the post-#115 contract:

| Field | Owner | Harmless variation? | Resolution authority |
|---|---|---|---|
| summary `slug` | **mechanical** (Python-derivable) | yes — the observed Phase-5 class. Under (a): optional unconstrained telemetry; under (b): absent from the proposal | role (`page_type=="summary"`) + provenance (`source_id`) |
| concept/article `slug` | model (semantic identity) | rare — only when registry/context yields exactly one target | alias ledger / EXISTING CONTEXT; else preserve-or-reject |
| `page_type` | model, 3-enum | none observed (case-fold is a candidate) | enum registry |
| `title` | model (content) | never — lossy | — |
| `body` prose | model (content) | never | — |
| body wikilink **targets** | references, not content | yes — same identity policy as slugs (§4 reference policy) | intra-response page slugs + registry + role |
| `compilation_notes` | model (prose; Python never acts) | none needed | — |
| `source_id`, `supports_page_existence`, `status` | **already Python-owned** | n/a | n/a |

Four model-authored fields + notes. Any option must be evaluated against THIS surface, not a hypothetical larger one.

## 3. Joseph's design challenge (2026-07-23 — first-class design input)

Restated faithfully from session dialogue:

1. **"We need to increase Python's tolerance of the semantic check."** The exact-match gate at the raw boundary is the wrong instrument.
2. **"The normalizer is fine — but normalize-then-strict-check reads as fudging the semantics first so the output *can* pass the strict Python check."** If the check were right, we wouldn't need to bend anything to satisfy it.
3. **"What we should do is not have a strict Python check that fails hard. Why should a missing dash `-` in the summary slug fail the LLM output at all?"**

Joseph's position: for the summary slug there is **no ambiguity possible** — Python derives exactly one valid value regardless of what the model emits. The model's emission on that field is at best telemetry signal, never a failure cause. This effectively **revises #115's D-115** ("the summary page stays fully model-authored *including its slug*, gate-validated") toward: the summary slug's canonical value is **Python-owned**; model authorship of the summary page means its title/body/role, not its mechanical identifier.

**Codex R3 verdict on the challenge:** "The boundary move answers Joseph's challenge correctly: Python should own the mechanical summary identity, and strictness should protect the canonical product rather than punish model punctuation."

## 4. Analysis — the boundary MOVE (v1.2: R3 F1/F2 + R4 F1/F2/F3 resolved)

The challenge and the **proposed** governing rule converge. For the summary slug, Python can do better than *map* — it can **derive**. The answer to "why should a dash fail the output" is: **it shouldn't, and under #119 it doesn't.**

The exact-match check does not get "more tolerant" (that would be the rejected similarity-gate path — seed Option C, Codex F4). It **moves off the model's raw output entirely**:

- **Raw/proposal boundary (model-facing):** no exact-match identity gate.
  - **Structural insufficiency = any violation of the proposal schema** (R4 F3 — the schema IS the structural contract; no hand-maintained error inventory). Typed categories: root (non-object payload) · pages collection (missing/invalid/non-object entries) · page fields (concept/article `slug` presence+type+form; `page_type` enum validity; `title` non-empty ≤200; `body` non-empty; undeclared fields) · `compilation_notes` shape.
  - **Semantic rejects** (separate, enumerated): zero summary pages (no interpretation — Python cannot invent the summary's title/body, which are content); two+ summary pages (ambiguity); the Python-derived summary slug colliding with another (non-summary) page in the response; **rewrite ambiguity** (see the reference policy below); information loss (a normalization step that would drop model content).
  - **The summary slug's raw value never triggers a retry or a rejection** — under EITHER form (R4 F1: form (a) as drafted in v1.1 violated this by keeping `slug` required; fixed below).
- **Reference policy — ONE coherent policy** (R4 F2: v1.1 held two conflicting dispositions for the same class — reject AND preserve-nonfatal; resolved):
  1. A model-authored body reference with **no normalization authority** → preserved verbatim as model-authored content. Dangling targets stay possible — today's behavior, KPI-visible, never fatal. No rewrite is attempted without authority.
  2. A deterministic rewrite is attempted **only** when a unique authority resolves the token (role+provenance for the summary identity; registry/context for concept references). If an attempted rewrite has **multiple plausible referents** (another response page, an EXISTING CONTEXT entry, an alias-ledger target) → **reject** (ambiguity), never silently pick.
  3. Under the recommended form (b) + links-to-summary-unnecessary: bodies never reference the current summary → **no summary-slug propagation exists at all**; the summary page links outward to concepts, as the current prompt already expects. A model that still writes a guessed `[[summary-…]]` token falls under rule 1 (preserved, dangling-tolerant) — never a failure.
- **Identity stamping:** assigning the Python-derived summary identity to the unique summary page is **always safe** and never depends on whether any reference propagation is safe (R3 F2).
- **Canonical boundary (Python-facing):** strictness stays, aimed at *our* machinery. The load-bearing invariant set (R3 answer 1): **(1) strict canonical schema, (2) exact pre-persistence summary invariant, (3) post-canonicalization invariant** — all run on the normalized object, guarding Python's derivation and the alias ledger. Canonicalize guard + post-canon invariant (`canonicalize.py:424-457`, `compiler.py:717-736`) keep their job.
- **Raw-proposal preservation:** the raw parsed proposal is preserved separately from the normalized object — an in-place mutator must not erase the model evidence normalization telemetry exists to expose. (Today `coerce_slugs_and_propagate` already mutates `parsed_json` in place; the resp-stats record keeps `raw_response_text` but not the pre-mutation parsed values. #119 fixes this properly.)

Under this framing the "fudge" objection dissolves: normalization is not bending the model's answer to satisfy a gate — it is Python taking ownership of a mechanical field. The gates that remain check *us*, not the model.

**Proposal form (the gating sub-decision):**
- **(a) ignored-and-stamped, FIXED per R4 F1:** `slug` on the summary page becomes **optional and unconstrained** in the proposal contract — telemetry-only, can never reject (required-anymore would re-gate missing/non-string slugs, the exact class Codex R1 F2 flagged). When present and deviating, recorded as a `summary_slug_deviation` measure-finding.
- **(b) slug leaves the summary proposal:** the model emits `page_type`/`title`/`body` for the summary; Python assigns identity. Consequences (R3 answer 3): revise the system prompt, response-contract block, exemplar, and checklist; bump the Pass-2 prompt version and preserve the loaded-text SHA; record `summary_identity_derived` telemetry instead of `summary_slug_deviation`; links-to-summary resolution per §6.1 (Codex: declare unnecessary — simplest; no prompt injection of the canonical slug, a #115-ratified non-goal).
- **Codex recommends (b)** both rounds: "do not require an ignored model field solely to manufacture telemetry" (R3); "Given Joseph's constraint and the ownership model, form (b) remains the coherent choice" (R4).

Concept/article slugs are **not** Python-derivable — they remain model-authored and proposal-schema-gated (normalization permitted only by registry/role/context authority, never similarity). Body wikilink targets remain model-authored **references** governed by the reference policy above: preserve without normalization authority; rewrite only with unique authority; reject attempted-rewrite ambiguity (R5 F1 — the "stay gated" wording was wrong: target existence was never gated). The challenge is scoped to the summary slug; scope discipline applies.

## 5. The three implementation options — form-coupled (v1.2: R4 F4 wording fixed)

R3 F3: the (a)/(b) form choice materially changes every option's cost and reversibility — the form decision **gates** the option pick. The 2×3 matrix:

| | **Option 1 — in-place normalizer** | **Option 2 — dual schemas + typed bridge** | **Option 3 — typed intent decoder** |
|---|---|---|---|
| **(a) ignored-and-stamped** | Lowest cost of all six cells; fully reversible (delete the stage → today's gates return); proposal structural checks still needed. | Moderate cost; proposal schema ≈ canonical validation shape with optional-unconstrained summary slug; bridge stamps. Versioned trust boundary. | Highest cost; disproportionate. |
| **(b) slug leaves summary proposal** | NOT "one module" — needs a handwritten proposal contract (the canonical validation shape requires `slug` on every page, so it cannot validate slugless summaries). **Reversibility collapses**: deleting the normalizer removes summary identity entirely. | **Natural fit**: discriminated proposal schema (summary: `page_type`/`title`/`body`; concept/article: + `slug`) becomes the prompt-facing contract; bridge stamps the derived slug; output validated against the **unchanged canonical validation shape** (R4 F4 — see re-roling note). | Highest cost; disproportionate. |

**R4 F4 — "unchanged canonical validation shape," not "unchanged schema":** the current schema artifact identifies itself as the per-call model-output contract (title/`$id`/description at `compiled_source_response.schema.json:3-5`) and is prompt-facing (`prompt_builder.py:36,84-92`). Under Option 2 its **validation shape** survives unchanged as the canonical contract, but the artifact is **re-roled**: the new proposal schema becomes prompt-facing; the existing artifact's title, description, `$id`, loader ownership, CLI routing (`kdb-validate-response`), and tests move to the canonical role.

Cross-cutting requirements under any cell: raw-proposal preservation (§4); per-rule authority + ambiguity policy + telemetry + tests; the #106 coercion rules absorbed into the normalization path (not retained as a post-schema-failure rung — that would reintroduce normalization after rejection; parity corpus + collision-refusal behavior preserved).

**Codex's recommendation (both rounds):** Option 2 + form (b) — "directly represents the missing trust boundary without Option 3's parallel domain-type hierarchy… malformed raw JSON is rejected before normalization code operates on it; every normalization decision has one typed result surface; raw permissiveness cannot leak into canonical consumers." Option 1 is materially simpler only under form (a).

## 6. Surviving questions — Codex's recommended resolutions (for Joseph's confirmation)

1. **Proposal form + links-to-summary:** **(b)**, with **links to the current summary declared unnecessary** (R4 F2's simplest resolution: no raw summary slug exists → no propagation problem; the summary body links outward to concepts as today). If links-to-summary ever prove genuinely required: a reserved proposal-local token outside the canonical slug namespace, rewritten unambiguously by the bridge — never canonical-slug prompt injection.
2. **Alias-ledger policy:** **fail-closed** — system-owned summary identities never bypass alias resolution; bypassing would conceal stale/hostile mappings. Canonicalize summary rename/merge guards keep surfacing such state as canonicalization failure.
3. **#106 slug coercion:** absorbed into the proposal→canonical bridge; not retained as a post-schema-failure rung; parity corpus + collision refusal preserved.
4. **Retry policy:** retry once **only** for model-correctable failures — structural insufficiency (malformed/incomplete proposal); zero or multiple summary pages; response-local duplicate/collision among model-authored identities; ambiguous model-authored reference. **Never** retry deterministic Python/state failures: underivable expected slug (already pre-call), normalization implementation invariant failure, canonical-contract failure after a successful bridge, alias-ledger cycle or summary-identity operation, #116-owned cross-source conflicts. **The summary slug's raw value never triggers a retry.**

## 7. Codex R3's answers to the five design questions

1. **Boundary move preserves the load-bearing strict invariant?** **Yes**, provided the normalized object passes (1) strict canonical schema, (2) exact pre-persistence summary invariant, (3) post-canonicalization invariant. The raw exact-slug check is unnecessary.
2. **"Never fail on the summary slug's value" safe?** **Yes for identity assignment** (value may be absent/malformed/different without invalidating model-authored title/body/role); **not sufficient authority for automatic body-reference rewriting** (reference policy §4).
3. **Form (a) or (b)?** **(b)** — discriminated proposal schema; bridge stamps before canonical validation; consequences in §4.
4. **Proportionate option?** **Option 2 conditionally** (rationale §5); Option 1 simpler only under (a); Option 3 disproportionate.
5. **Reopens more of #115 than the slug clause?** **Yes — contract mechanics entailed by the ownership change.** Explicit **#115 decision-delta list**: the uniform four-field raw page shape; the Pass-2 system prompt + response-contract block + exemplar + checklist; prompt version + SHA provenance; validator ordering and failure classification; #106 slug-coercion placement; parsed-response and normalization telemetry. The canonical `CompiledSource`, page writer, graph intake, manifest, run journal, replay, and wiki contracts **need not change** if the bridge restores the current canonical page shape.

## 8. Codex R3 — verification record (2026-07-23)

Every finding verified against code/docs before absorption (receiving-code-review discipline).

| Finding | Claim | Verification |
|---|---|---|
| F1 (High) | Reject taxonomy incomplete: normalization before the strict schema must also reject malformed roots, invalid `pages`, non-object entries, missing/wrong-type fields; "information loss" too broad | **Accurate** — today those classes are caught only by the strict schema gate (`compiler.py:408-411`); any pre-schema normalizer would see unvalidated structure. Taxonomy rewritten (§4), then generalized per R4 F3 |
| F2 (High) | Body-wikilink targets ungated: body = opaque string (schema), semantic_check = summary-only (`validate_source_response.py:58-85`), intake silently skips missing targets (`intake.py:345-373`); stamping ≠ propagation; reference-collision reject class missing | **Accurate on all citations** — additionally found the intake docstring's "validator catch upstream" is stale (no such gate exists post-#115; `dangling_link_rate` is a KPI, not a gate). §4 separates stamping from propagation; policy unified per R4 F2 |
| F3 (Medium) | Form (a)/(b) couples option costs: Option 1 under (b) needs a handwritten proposal contract + loses reversibility; (b) eliminates `summary_slug_deviation`; Option 2 supports (b) via discriminated schema; raw proposal must be preserved separately | **Accurate** — canonical validation shape requires `slug` on every page (`…schema.json:37-42`); `coerce_slugs_and_propagate` mutates `parsed_json` in place today. §5 rebuilt as a 2×3 matrix; preservation requirement added to §4 |
| F4 (Low) | "Ratified" governing rule is proposed, not ratified; `main @ f8c9ad8` — current main is `4d60e6d` (docs-only delta) | **Accurate** — both corrected (§1, §4). Joseph ratified the #115 *disposition*; the governing rule's ratification is a #119 blueprint item |

## 9. Codex R4 — findings + verification record (2026-07-23)

R4 verdict: REVISE BEFORE OPTION PICK — R3 correctly absorbed except two high-severity contradictions. All four verified accurate; absorbed in v1.2.

| Finding | Claim | Verification |
|---|---|---|
| F1 (High) | Form (a) keeps `slug` **required** while the design says the raw value never rejects — missing/non-string summary slugs would still fail proposal validation (Codex R1 F2's unhandled class) | **Accurate** — v1.1 §4 self-contradicted. Fixed: under (a) the summary slug is optional + unconstrained telemetry that can never reject; Codex's steady recommendation remains (b) |
| F2 (High) | Ambiguous-reference policy self-contradicts: "reject" (§4) vs "preserve dangling, nonfatal" (§4 + absorption-response lines 23-25) | **Accurate** — my error, carried in both documents. Fixed in §4: single policy — no-authority → preserve (nonfatal); attempted-rewrite ambiguity → reject; under (b) + links-to-summary-unnecessary the summary-propagation case disappears entirely. Erratum added to the absorption-response doc |
| F3 (Medium) | "Complete" structural taxonomy still omits concept/article `slug`, `page_type` enum, `title` constraints, `body` emptiness, `compilation_notes` shape; stop hand-maintaining the inventory | **Accurate** — §4 now defines structural insufficiency as **any proposal-schema violation** with typed categories; semantic rejects enumerated separately |
| F4 (Medium) | "Unchanged canonical schema" wrong: the artifact is the prompt-facing model contract (`…schema.json:3-5`; `prompt_builder.py:36,84-92`); the validation shape survives, the artifact is re-roled | **Accurate** — verified the prompt injection path + RESPONSE_CONTRACT + exemplar. §5 now says "unchanged canonical validation shape" + re-roling list (title/`$id`/description/loader/CLI/tests) |

R4's correctly-absorbed list (acknowledged, no action): form-coupled 2×3; raw-proposal preservation; fail-closed alias; #106 into the bridge; model-correctable vs deterministic retry policy; explicit #115 decision deltas; ratification + code-anchor corrections.

**R4 final disposition (on record):** "Once F1 and F2 are resolved, **Option 2 + form (b) + no links to the current summary + fail-closed alias handling** is ready for Joseph's confirmation and North-Star ratification." F1/F2 are resolved in this v1.2.

### 9.1 Codex R5 (2026-07-23) — GO with minor documentation corrections

Verdict: **GO** — "No architectural blocker remains." All four R4 findings confirmed substantively resolved. Two minor documentation corrections, both applied in v1.3: **F1 (Medium)** — §4's "body wikilink targets stay model-authored and gated" contradicted the verified ungated behavior + the reference policy (wording corrected; contract-wording fix, not an architecture change); **F2 (Low)** — the absorption response still presented v1.1 as current (labeled historical; now points at v1.2+/the converged package). R5: after correction, Joseph's explicit confirmation of **Option 2 + form (b) + no links-to-current-summary + fail-closed alias handling** closes the Phase-1 decision gate → ledger + North Star → blueprint.

## 10. What this is NOT

- Not a similarity/tolerance gate. No edit-distance, punctuation-blind comparison, or probabilistic equivalence anywhere — resolution requires deterministic authority (role, provenance, registry, context), never similarity.
- Not model-content auto-correction. Titles, bodies, concept/article slugs, and prose remain model-authored and fully gated.
- Not two dispositions for one class. The reference policy is single: preserve without authority; reject on attempted-rewrite ambiguity (§4).
- Not a change to #116's carve (cross-source reservation/lifecycle untouched).
- Not permission to gate on the summary slug's raw value — ever (Joseph's challenge, Codex-endorsed).
