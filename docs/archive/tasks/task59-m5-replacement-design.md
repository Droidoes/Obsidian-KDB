# Task #59 — M5 Replacement: `body_emit_set_coverage`

**Status:** Design v2 (post-Codex review) — awaiting user review before implementation plan.
**Date:** 2026-05-10.
**Reference:** [`docs/TASKS.md`](TASKS.md) → Task #59 (`open`).
**Companion docs:** [`docs/CODEBASE_OVERVIEW.md` §7](CODEBASE_OVERVIEW.md) — North Star (table at line 168 will update); [`docs/task19-kpi-design.md`](task19-kpi-design.md) — historical KPI rationale (Phase 5 frozen).
**Memory notes:** `project_m5_retired_post_57.md` (M5 retired by construction); `feedback_name_must_match_contents.md` (name must describe what it measures); `feedback_measurability_over_defensive_complexity.md` (invest in measuring quality).

---

## 1. Why this exists

**Task #57** introduced `reconcile_body_links(parsed_json)` in [`kdb_compiler/compiler.py:290`](../kdb_compiler/compiler.py), which rewrites each page's `outgoing_links` from body wikilink slugs *before* `RespStatsRecord` is written. Consequence: by the time [`resp_stats_writer.py:176`](../kdb_compiler/resp_stats_writer.py) calls `body_link_check(parsed_json)`, both sides of the Jaccard are derived from the same body — the measure is structurally tautological. M5 reads ≈1.000 on every model on every fire.

**The retirement was correct as a system-correctness move** (the body-wikilink saga of 2026-05-09 closed with `outgoing_links == body_wikilink_slugs(body)` as a guarantee, removing a recurring defect class). But the 5% slot in the scorecard is now dead weight, and the retirement also exposed a structural gap: **after #57, no measure in the scorecard reads body text emitted by the model**. A model emitting threadbare body prose with bare slug lists scores identically to one emitting rich, integrated prose — both end up M5=1.000 by reconciler construction.

This task swaps the dead M5 slot for a *meaningful* body-content measure that the reconciler does not neutralize.

---

## 2. The replacement

### 2.1 Name

`body_link_jaccard` → **`body_emit_set_coverage`**

Per `feedback_name_must_match_contents`: the new measure includes `concept_slugs ∪ article_slugs` in its denominator (not concepts alone), so naming it after either slug-class would be misleading. `emit_set` accurately describes what we're checking coverage of.

### 2.2 Formula

Micro-aggregated across all sources in the run. **Self-links excluded per page** so that a page linking to its own slug doesn't credit itself for "integrating" a concept it merely *is*:

```
For each source's parsed_json:
  declared_emit_set = set(concept_slugs) ∪ set(article_slugs)        # excludes summary-* slugs

  For each page p in pages:
    page_links_p = body_wikilink_slugs(p.body) - {p.slug}             # SELF-LINKS EXCLUDED

  body_emit_links = (⋃_p page_links_p) ∩ declared_emit_set

  num_per_source   = |body_emit_links|
  denom_per_source = |declared_emit_set|

aggregate across run:
  rate = (Σ num_per_source) / (Σ denom_per_source)        if Σ denom_per_source > 0
  rate = 0.0                                              otherwise        (MF6 zero-denom rule)
```

**What it measures:** of the concepts and articles the model declared, what fraction did it weave into *other* pages' bodies via `[[…]]` wikilinks?

**Self-link exclusion rationale (per Codex):** a concept page named `momentum` containing `[[momentum]]` in its own body has not "integrated" the concept — it tautologically references itself. Excluding self-links rewards cross-page integration: summary→concept, concept→article, article→concept, etc. This is a stricter and more honest reading of "did the model build a connected KB graph from its declarations."

**Properties:**
- Bounded `[0, 1]` by construction; no calibration constant.
- Reconciler-orthogonal: `reconcile_body_links` only rewrites `outgoing_links` from body; it never adds wikilinks to the body, so variance survives the reconciler.
- Discriminating: 2026-05-09 data shows qwen-flash-us went 0 → 24 body wikilinks via Task #53 prompt-engineering — the underlying dimension varies meaningfully across models.
- Anti-game-able beyond trivial cases: spurious wikilinks to non-emit-set slugs don't count (intersect-with-declared-emit-set clamp); self-links don't count (per-page subtraction); spamming relevant cross-page wikilinks is the desired behavior.

### 2.3 Slot, weight, bucket

| Field | Value |
|---|---|
| Slot ID | M5 (existing slot — drop-in replacement) |
| Weight | 5% (unchanged from current M5) |
| Bucket label | "Output Integrity" (UNCHANGED — per Codex, M5 is still mechanical coverage; renaming the bucket would be churn without semantic gain) |
| Borda? | No (raw rate, like M1–M4) |
| Zero-denom rule | 0.0 (model-controlled, MF6 convention) |

### 2.4 Computation architecture (revised post-Codex)

**M5 is computed inside [`kdb_benchmark/scorer.py`](../kdb_benchmark/scorer.py) at score time, from `parsed_json` already captured on `RespStatsRecord` under the capture-full mandate.** No new persisted fields, no changes to `RespStatsRecord`, no changes to `resp_stats_writer.py`.

**Why this matters (D25 boundary):** [`kdb_compiler/types.py:317`](../kdb_compiler/types.py) explicitly documents `RespStatsRecord` as *call-telemetry fields, NOT response-quality scores*. The retired M5's `body_link_intersection`/`body_link_union` were already a layer violation — extending it would compound the smell. The benchmark is the right place for measurement; the compiler is the right place for system invariants.

**Helper layout:**
- `kdb_compiler/validate_compiled_source_response.py` — promote `_body_wikilink_slugs` → public `body_wikilink_slugs`. Body-text wikilink extraction is a parsing utility, not a measurement; it's already used by `reconcile.py:35` and lives in the compiler. Promoting (drop the underscore) lets `kdb_benchmark.scorer` import it cleanly across the one-way boundary.
- `kdb_benchmark/scorer.py` — new private helper `_compute_body_emit_set_coverage(parsed_json: dict) -> tuple[int, int]` that returns `(num_per_source, denom_per_source)`. The `m5(records)` function aggregates: `Σ num / Σ denom`.

**The retired `body_link_check` and `body_link_intersection` / `body_link_union` fields stay in place for this task.** They're orphaned after the swap (scorer no longer reads them), but resp_stats_writer keeps writing them and tests keep passing. Removing them is a follow-up cleanup, out of #59 scope (per `feedback_no_imaginary_risk` — keep this task focused; orphan-removal can happen when convenient).

---

## 3. Locked design calls

| ID | Decision | Rationale |
|---|---|---|
| **D29.1** | Replace M5, do not add a new measure. | Memory `feedback_measurability_over_defensive_complexity` — keep the scorecard surface lean; M5 slot is dead, replacing is cheaper than expanding. |
| **D29.2** | Denominator = `concept_slugs ∪ article_slugs` (exclude `summary_slug`). | Both slug-classes are valid wikilink targets; excluding either privileges one. `summary_slug` excluded because summaries are per-source artifacts, not concepts the model claims to "use." |
| **D29.3** | Weight stays at 5%. | M5 was 5% before retirement; no signal yet on whether body-content quality should be more or less weighted than the prior body-link-syntax measure. Avoid weight churn until there's evidence. |
| **D29.4** | Name = `body_emit_set_coverage`, not `body_concept_coverage`. | Codex feedback (2026-05-10): denominator includes articles, so name must reflect the union. Aligns with `feedback_name_must_match_contents`. |
| **D29.5** | Bucket label stays "Output Integrity" (NOT renamed to "Output Quality"). | Codex feedback: M4 is still structural semantic pass/fail and new M5 is still mechanical coverage. Both belong in "Output Integrity." Renaming the bucket without a semantic shift is churn. |
| **D29.6** | M5 is computed in `kdb_benchmark/scorer.py` from `parsed_json`. No new `RespStatsRecord` fields. | Codex feedback: D25 one-way boundary; `RespStatsRecord` is documented as call-telemetry, not response-quality. Capture-full mandate already provides `parsed_json`; scorer reads it directly. |
| **D29.7** | Self-links excluded from numerator: `page_links_p = body_wikilink_slugs(p.body) - {p.slug}`. | Codex feedback: a page linking to its own slug isn't "integrating" the concept — it's a tautology. Subtraction rewards cross-page integration only. |
| **D29.8** | Existing `body_link_check` helper and `body_link_intersection` / `body_link_union` fields stay in place; orphan-removal is a future cleanup task. | Keep #59 scope focused on the swap. The orphans cause no correctness issue; removing them is a one-shot follow-up when convenient. |
| **D29.9** | Scorecard-generation compatibility breaks at #59; record-replay capability is preserved. | Codex feedback: pre-#59 scorecards show retired-by-construction M5=1.000 and aren't comparable to post-#59 scorecards. But pre-#59 capture-full `RespStatsRecord` JSONs DO have `parsed_json`, so they can be **re-scored** under the new M5 — no record migration needed. The cross-generation incomparability is at the scorecard level, not the record level. |

---

## 4. Implementation surface

### 4.1 Files touched (revised — minimal vs. v1 spec)

| File | Change |
|---|---|
| `kdb_compiler/validate_compiled_source_response.py:124` | Rename `_body_wikilink_slugs` → `body_wikilink_slugs` (drop the underscore, mark public). Update internal callers in `reconcile.py:35, 136` and same-file uses at `:156, :186`. |
| `kdb_benchmark/scorer.py:320-330` (`m5()`) | Rewrite: read `parsed_json` from each record, call new local helper `_compute_body_emit_set_coverage(parsed_json)`, aggregate `Σ num / Σ denom`. Update docstring. |
| `kdb_benchmark/scorer.py` (new helper) | Add private `_compute_body_emit_set_coverage(parsed_json: dict) -> tuple[int, int]` near the other measure helpers. Imports `body_wikilink_slugs` from `kdb_compiler.validate_compiled_source_response`. Per-page iteration with self-link subtraction. |
| `kdb_benchmark/scorer.py:521` (`_MEASURE_LABELS`) | Update entry: `"M5": "body_link_jaccard"` → `"M5": "body_emit_set_coverage"`. |
| `kdb_benchmark/scorer.py:592` (`_emit_verbose_trace` per-page asymmetry) | Replace M5 per-page asymmetry trace with a per-source coverage trace (e.g., "M5: 4/7 declared concepts found in body — missing: ['x', 'y', 'z']; per-page self-links excluded"). |
| `docs/CODEBASE_OVERVIEW.md:168` | M5 row updated: name (`body_emit_set_coverage`), formula (coverage of declared emit set in body, excluding self-links), domain ("Output integrity"). |
| `docs/CODEBASE_OVERVIEW.md` Decisions ledger | Add D29 with summary referring to this design doc. |
| `docs/TASKS.md` Open/In-Progress | Add Task #59 row. |
| `kdb_compiler/tests/test_validate_compiled_source_response.py` | Update tests for the rename `_body_wikilink_slugs` → `body_wikilink_slugs`. |
| `kdb_compiler/tests/test_reconcile.py` | Update tests if they reference the private name. |
| `kdb_benchmark/tests/test_scorer.py` | Update `m5()` tests: new formula, self-link exclusion, parsed_json-driven inputs (no more reading from intersection/union fields). |

### 4.2 What does NOT change (vs. v1 spec)

- `RespStatsRecord` (in `kdb_compiler/types.py:311`): unchanged.
- `kdb_compiler/resp_stats_writer.py`: unchanged. Continues to call `body_link_check` and write `body_link_intersection`/`body_link_union` fields. These fields are orphaned (scorer ignores them) but cause no correctness issue.
- `body_link_check` helper in `kdb_compiler/validate_compiled_source_response.py:132`: unchanged. Orphaned after this task; cleanup is a future task.

### 4.3 Field-naming question (RESOLVED — moot)

V1 spec proposed renaming `body_link_intersection` / `body_link_union` to `body_emit_links_count` / `emit_set_size`. **No longer needed** — those fields are not used by the new M5 and stay as-is until a future cleanup task.

---

## 5. Migration / replay

**Three layers, three behaviors:**

| Layer | Cross-#59 compatibility | Notes |
|---|---|---|
| **Scorecards** (`benchmark/scores/runs/`, `benchmark/scores/final/`) | **Break.** | Pre-#59 scorecards record M5=1.000-by-construction. Not comparable on M5 with post-#59 scorecards. Same doctrine as D28 — "comparable only within candidate set" extends to "within scorecard generation." Pre-#59 scorecards preserved as audit trail. |
| **`RespStatsRecord` JSONs** (`benchmark/runs/<run_id>/state/llm_resp/`) | **Compatible (replay-able).** | Capture-full mandate persists `parsed_json` on every record. Pre-#59 records can be re-fed through the new M5 computation; the orphan `body_link_intersection`/`body_link_union` fields are simply ignored. |
| **Helpers/code** | **Forward-only.** | Promoted `body_wikilink_slugs` may be imported by future code paths. No backwards alias retained. |

**Practical implication:** if a user wants to retrofit the new M5 onto historical fires, they re-run `kdb_benchmark.cli` against the existing run dirs (no need to re-fire LLMs). The `final/` merge will produce a new scorecard with new-M5 values for any model whose records still live on disk.

---

## 6. Sequencing (docs-first per Codex)

1. **This spec** lands at `docs/task59-m5-replacement-design.md` (committed, user-reviewed).
2. **CODEBASE_OVERVIEW.md update** — table row at line 168 + D29 ledger entry. *Lands as the first commit of the implementation plan, not as part of the spec commit.* The North Star moves first; code follows.
3. **TASKS.md update** — add #59 to Open/In-Progress.
4. **Implementation** — files in §4.1.
5. **Live verification** — single-model fire (recommend: haiku-4.5; cheap, well-characterized) on canonical 5-source corpus. Confirm new M5 produces a meaningful non-1.000 rate; inspect per-source coverage trace.
6. **Optional re-score of historical fires** — using the on-disk `RespStatsRecord` JSONs (per §5 record-level compatibility), produce a fresh scorecard merging existing models under the new M5 — no API spend required. User judgment whether this is worth doing.
7. **Close #59** — commit SHA + close-out in TASKS.md.

---

## 7. Known limitations

| # | Limitation | Severity | Mitigation |
|---|---|---|---|
| L1 | A model can max the score with a flat `## Related: [[a]] [[b]]` list at body bottom — no requirement that wikilinks appear in main prose. | Low | Acceptable; "Related" footers are canonical KB practice. If pathological gaming surfaces, revisit with a "wikilinks-in-prose" sub-measure. |
| L2 | Doesn't measure body length, prose quality, faithfulness to source. | Medium | Out of scope. Body-content quality is broader than one mechanical measure can cover. LLM-as-a-judge content quality (deferred to future Task; see memory `project_benchmark_framework_deferred.md` E3) remains the architecturally complementary play. |
| L3 | Zero-denom edge: model emits zero `concept_slugs` and zero `article_slugs` → denominator = 0 → rate = 0.0 (model-controlled penalty, MF6). | None | Documented; tested. Correct behavior — no declared emit-set means no integration to credit. |
| L4 | Cross-generation comparison on M5 is not meaningful. | Low | Same doctrine as D28. Pre-#59 scorecards: M5=1.000. Post-#59 scorecards: variable signal. Don't merge across the boundary on M5 axis. |
| L5 | Self-link exclusion means a single-page emit (one summary-page only, no concepts/articles) could trivially score 0.0. | Low | Edge case; production corpora always emit multiple pages. Captured in zero-denom test. |

---

## 8. Open questions for plan stage

1. **Promote `_body_wikilink_slugs` → `body_wikilink_slugs`?** Lean: yes, drop the underscore, fix the few internal call sites. Alternative: leave private and have scorer import the underscored name (works mechanically, but offends the convention). My recommendation: **promote**. Plan stage to confirm.
2. **Per-source coverage trace format**: suggested "M5: X/Y declared in body, missing: ['a', 'b']; self-links excluded". Joe to call detail level.
3. **Verification model choice**: haiku-4.5 (cheapest API-priced, well-characterized) is my lean. Sonnet adds confirmation at higher quality tier; Joe to call.
4. **Optional: include the historical-replay rescore in the close-out** (see §6 step 6) — produces a "before/after" view of post-#59 M5 across the existing 8 candidates without API spend. Worth doing? Joe judgment.

---

## 9. Verification criteria for closure

- [ ] All listed test files updated; tests green.
- [ ] CODEBASE_OVERVIEW.md §7 table reflects new measure; D29 ledger entry present.
- [ ] One real benchmark fire (single model, canonical corpus) produces a non-1.000 M5 rate with a coherent per-source coverage trace.
- [ ] No grep hits for `body_link_jaccard` outside of: (a) git history, (b) historical-record docs (`task19-kpi-design.md`), (c) this design doc, (d) the orphaned `body_link_check` helper which is preserved by D29.8.
- [ ] `kdb_benchmark.scorer` imports `body_wikilink_slugs` from `kdb_compiler.validate_compiled_source_response` (one-way boundary preserved).
- [ ] No additions to `RespStatsRecord` (D29.6 verified).
- [ ] TASKS.md entry for #59 closed with commit SHA.

---

## 10. Plan-stage clarifications (Codex v2 review, 2026-05-10)

Three clarifications baked in here so they survive into the implementation plan and don't get re-litigated:

### 10.1 Record eligibility — match M2/M3

**Use `_is_parse_pass(r)` only; do NOT require `schema_ok`.** This matches the existing M2/M3 helper `_slug_jaccard` at [`kdb_benchmark/scorer.py:255-258`](../kdb_benchmark/scorer.py):

```python
for r in records:
    if not _is_parse_pass(r):
        continue
    pj = r["parsed_json"]
    ...
```

Rationale: a parseable-but-schema-invalid record still has a `parsed_json` dict whose `concept_slugs` / `article_slugs` / page bodies can be inspected. Schema-pass is a stricter gate; M5 should match M2/M3's permissiveness for consistency in record selection across measures.

### 10.2 Malformed-field coercion (Round 4 CW2 conventions)

`_compute_body_emit_set_coverage(parsed_json)` must be tolerant in the same way `_slug_jaccard` is (per its Round 4 CW2 docstring):

| Field | If malformed | Treatment |
|---|---|---|
| `concept_slugs`, `article_slugs` | Not a list | Coerce to empty set (avoids `set("foo")` → char-slugs trap) |
| Slug list members | Not a string | Drop silently |
| `pages[i].body` | Not a string | Page contributes zero links (no self-link subtraction needed) |
| `pages[i].slug` | Not a string | No self-link subtraction for that page (but body wikilinks still count, modulo emit-set intersection) |
| `pages` | Not a list | Treat as zero pages → numerator=0, denominator unchanged |

Helper never raises on malformed input — same payload-tolerance contract as `body_link_check` and `_slug_jaccard`.

### 10.3 `_body_wikilink_slugs` promotion — confirmed

Promote `_body_wikilink_slugs` → `body_wikilink_slugs` at [`kdb_compiler/validate_compiled_source_response.py:124`](../kdb_compiler/validate_compiled_source_response.py). Update internal callers:

- `kdb_compiler/reconcile.py:35` (import)
- `kdb_compiler/reconcile.py:136` (call site)
- `kdb_compiler/validate_compiled_source_response.py:156, 186` (same-file uses in `body_link_check` and the per-page asymmetry helper)

**No backwards alias.** Codex confirmed: clean rename is fine; no need for `_body_wikilink_slugs = body_wikilink_slugs` shim.
