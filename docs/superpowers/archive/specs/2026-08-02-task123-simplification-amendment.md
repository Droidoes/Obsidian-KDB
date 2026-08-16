# #123 — simplification amendment: dynamic stage-2 sizing, no body truncation

Date: 2026-08-02 · Task **#123** · Status: **RATIFIED 2026-08-02 (Joseph)** — D-123-A…**F** all
binding; the `excerpt` → `body` rename is **confirmed**; fat `_v3` prose **read and approved by
Joseph 2026-08-02**. **IMPLEMENTED 2026-08-02, suite 3,059 green, uncommitted.** Recorded as
blueprint **v0.16**.
Amends: spec **D3 / D7 / §3.4 / §8.5**, blueprint **§2.2 / §7 / §7.0 / §7.0a / §12** → **v0.16**
Basis: Joseph, 2026-08-02 — *"the chief objective is to simplify, simplify and simplify… by
removing complexity, we are making our architecture/design/code stronger."*

## 1. What this changes, in one paragraph

`M` rises from 100 to **150** and becomes **thin's retention ceiling only**. The stage-2 pool
becomes **dynamic — 1 to 150 entities**, filled from thin's ranked retention until the 0.8 context
budget is reached. **All body-text truncation is removed**: no word cap, no per-entity byte
ceiling, no `truncated` flag. Fat receives whole compiled bodies. D7's *static* guarantee is
withdrawn and replaced by a stronger property.

## 2. Why the removed machinery was buying nothing

Three mechanisms existed to make the fat request bounded by construction. Measured against the
data they were protecting:

| mechanism | times it has ever fired |
|---|---|
| per-entity byte ceiling (`EXCERPT_BLOCK_CEILING_BYTES` = 2,500) | **0 / 163** fixture · **0 / 83** live |
| word cap (`EXCERPT_WORD_CAP` = 250) | **2 / 163** fixture · **0 / 83** live |
| `ProjectedEntity.truncated` | computed at `projection.py:231`, **read nowhere** |

The reason is structural rather than lucky: **pass-2 writes these pages**, so their length is
governed by the compiler's own prompt contract. Body sizes on the population `get_body` actually
reads:

| population | n | median | max | over 250 w |
|---|---:|---:|---:|---:|
| compiled pages (live) | 83 | 53 w / 375 B | **129 w / 976 B** | **0 %** |
| D7 fixture | 163 | 65 w / 508 B | 262 w / 2,016 B | 2 (1.2 %) |
| raw sources — *never read by search* | 8 | 7,460 w | 13,530 w | 100 % |

The ceiling was sized for a corpus that does not exist. Worse than idle: it forced the fat prompt
to tell the model *"an excerpt is the opening of a body, so its silence is weak evidence against"* —
false for 161 of 163 entities, and the direct cause of the precision tax codex raised as HIGH.
**Deleting the mechanism deletes the defect.**

## 3. The new mechanism, and why the guarantee gets stronger

**Old D7:** assemble the entire request, then check whether it happens to fit; if not, fail with
`budget_exceeded`. Boundedness came from `M × per-entity ceiling`.

**New:** project entities in thin's ranked order, accumulating rendered bytes, and stop when the
next entity would exceed the 0.8 budget. **A request that does not fit is never constructed.**

That is a by-construction property that needs no per-entity ceiling at all — which is exactly what
lets the truncation go. It is *stronger* than what it replaces: the old guarantee held only while
the ceiling held, and the ceiling was enforced by corrupting evidence.

**The fat pre-flight and the fill are now the same operation.** One mechanism replaces two.

### §3.4 is preserved, not amended

The cut has always been made by thin's judgment and the survivors **presented in manifest order**
(`search.py:371`). §3.4's claim is about *presentation* order — "fat's judgment stays unanchored to
thin's" — not about who makes the cut. Extending the cut from "top 150" to "top K that fit" reuses
the identical mechanism. **Select by thin's rank; present in manifest order.** No amendment.

Side effect worth recording: this gives thin's `BEST FIRST` a second, load-bearing consumer beyond
the concordance diagnostic — it now decides *which* entities survive a binding budget. That closes
the question Joseph raised on 2026-08-02 about why thin ranks at all.

### When the fill actually binds — essentially never

| | 150 entities | % of gpt-5.4-mini input capacity |
|---|---:|---:|
| live compiled pages | 61.5 kB | **5.3 %** |
| D7 fixture density | 84.9 kB | **7.3 %** |

Bodies must average **7,792 B — 19× live reality** — before the fill binds at 150. It is a
fail-safe, not an active mechanism, and the design should not be read as expecting it to do work.

## 4. Decisions requiring ratification

- **D-123-A — `M` = 150, role narrowed.** Thin's retention ceiling and the small-space threshold.
  No longer an input to any guarantee. Prompt-byte-neutral: `"100"` and `"150"` are both 3
  characters, so the rendered thin block is byte-identical, `GOLDEN_DIGESTS` do not move, **there is
  no thin `_v3`**, and the paid D5 measurements stay substantively valid.
- **D-123-B — stage-2 pool is dynamic, 1–150,** filled by thin rank to the 0.8 budget, presented in
  manifest order.
- **D-123-C — no body truncation anywhere.** Bodies are delivered whole.
- **D-123-D — D7's static guarantee withdrawn,** replaced by §3's fill property. `M × ceiling`
  arithmetic retired.
- **D-123-E — fat prose `_v3`:** the body is complete, so its silence is evidence of absence. Fat
  only; invalidates no paid measurement (the calibrator renders thin only).
- **D-123-F — the advisory `unresolved` list is dropped from the fat wire.** Ratified by Joseph
  2026-08-02. **Amends D8(ii) and spec §2.3, both ratified** — recorded here rather than applied
  silently. See §11.

## 5. Explicitly NOT removed — guard against over-deletion

"Truncation" names three unrelated things in this codebase. Only the first goes:

| concept | refs | disposition |
|---|---:|---|
| **body / excerpt truncation** | 39 | **REMOVED** |
| **output truncation** — `stop_reason` normalization, `THIN`/`FAT_OUTPUT_TRUNCATION`, D9.3/D9.4 | 75 | **KEPT** — a different event entirely (the model's response was cut off) |
| **query-block truncation** — `query_truncated`, per-field allocations, `QUERY_BLOCK_CEILING_BYTES` | 47 | **KEPT for now** — see §8 |

Also kept: `delimiter_collision_guard` and `_single_line` sanitization (P10 injection containment —
unrelated to sizing), and the thin-side estimate guard.

## 6. What gets deleted

`_truncate_to_block_ceiling` (incl. its binary search) · `_excerpt_policy_v1` ·
`ProjectedEntity.truncated` · `EXCERPT_BLOCK_CEILING_BYTES` · `EXCERPT_WORD_CAP` ·
`EXCERPT_SENTENCE_EXTENSION_WORDS` · `fat_worst_case_request_bytes` ·
`fat_static_guarantee_tokens` · the fat pre-flight as a step distinct from the fill.

**Naming (open):** with no truncation, `ProjectedEntity.excerpt` holds the body. Renaming
`excerpt` → `body` follows the project's name-matches-contents rule and shortens the v3 prose;
it touches `artifact.fat_evidence`, spec §4's grammar, and P1 tests. **RATIFIED — do the rename.**

## 7. Consequences to record

1. **Two ratified contract rows narrow.** `FAT_PREFLIGHT_BUDGET` and `FAT_PREFLIGHT_BUDGET_ON_F1`
   currently mean "the assembled request was too big". Under fill-to-budget they can only fire when
   **not even one entity fits**. Still reachable; meaning narrowed.

   **Strengthened at implementation (2026-08-02; kimi concurrence review).** The narrowing is
   sharper than "not even one entity fits" states, and the difference is load-bearing for anyone
   reading the branch table: **a small context window can no longer reach these terminals at all.**
   Thin reserves 36,000 output tokens against fat's 26,000, so any route that clears thin's
   pre-flight has ~10,000 tokens (~40 kB) more fat-side room than thin's whole evidence block
   needed. The many-moderate-bodies case that used to trip it is now handled by the fill seating
   fewer and succeeding — strictly better than failing. **The only thing that still reaches these
   terminals is a single oversized body**, which is what the rebuilt §8 rows exercise (60,000-token
   window, ~120 kB body). A future reader must not hunt for a window-size row: it cannot exist.
2. **Small-space retain-all gains a qualifier.** Spec §130 / codex concurrence #3 — "when
   `eligible_space_size ≤ M`, stage 2 gets every eligible identity regardless of the thin response"
   — becomes "…**and the whole space fits the budget**".
3. **D3's threshold moves** with M: thin-retained-zero applies at N > 150.
4. **The frozen fixture becomes a historical artifact under a named policy.** Both capped
   entities are **absent from the current wiki**, so their full bodies are unrecoverable and
   re-freezing is impossible without reproducing that compile. The manifest already records
   `excerpt_policy_version: "1"` and the policy text, so this is self-documenting. Known
   divergence: 2 of 163 entities' tail text. **Checksums untouched; the 39 adjudicated D7 probes
   are not re-opened.**
5. **Cost table refresh** (spec §314): fat expected input moves from `100 × 719 B` to
   `≤150 × ~566 B`. Roughly 1.2–1.5× fat input per source; the pathological-ceiling row disappears
   with the ceiling.
6. **§8.5's reduced-M curve** re-bases on M=150.

## 8. Open candidate, deliberately not folded in

The **query-block ceiling** (4,096 B with per-field allocations: author ≤ 256, keys ≤ 10 × 128,
themes ≤ 1,024, summary ≤ remainder) is 47 references of the same *shape* of complexity this
amendment removes elsewhere. It may be equally idle — but pass-1 metadata is model-authored and
genuinely unbounded, unlike compiled bodies, which is a real difference. **Not touched here.**
It should be decided the same way this was: measure how often it binds on real pass-1 output
first. Filed as a follow-up, not assumed.

## 9. Test plan

- **Delete** the truncation/ceiling suites in `test_projection.py` and the guarantee assertions in
  `test_budget.py` — they test removed behaviour, so keeping them is not conservatism.
- **New — the fill loop:** stops at the budget; never emits a request over budget; emits ≥ 1
  entity whenever one fits; emits 0 (typed terminal) when none does; fill order is thin's rank;
  presentation order is manifest. Each asserted independently — a fill that returned everything
  would pass an order-only test.
- **New — a fill that genuinely binds**, using synthetic oversized bodies. Without it the fill is
  untested at current corpus density, since real data never reaches the bound.
- **Update** `GOLDEN_OVERHEAD_INPUTS` M 100 → 150 (the pin fires by design), the §8 branch table
  for the narrowed terminals, and the contract matrix rows in §7.1.
- **Re-run** the full suite; mutation-check the fill loop's stop condition and its ordering split.

## 10. Sequencing

Lands as its own commit **on top of** the current uncommitted work (prompts `_v2`, blueprint v0.15,
D5 calibration), not folded into it — that commit is a coherent unit and this one amends ratified
decisions.

1. ~~Ratify §4's D-123-A…E (+ the §6 naming call)~~ — **DONE 2026-08-02**
2. Blueprint **v0.16** + spec amendments recorded **first** (North Star before code, per the
   workflow and the v0.15 precedent)
3. Implement + test
4. ~~Fat `_v3` prose review~~ — **DONE 2026-08-02**: Joseph read `selector_fat_v3.txt` and approved it.
5. Panel concurrence (codex + kimi) — brief at
   `docs/superpowers/archive/specs/2026-08-02-task123-v016-concurrence-brief.md`. Informational in posture: the
   ratified decisions are not re-opened, and the bar for reopening is new evidence, not restated caution.

Landing as three commits (owner-confirmed 2026-08-02):

| | contents |
|---|---|
| **1** | `_v2` prompts · blueprint v0.15 · `SYSTEM_TEMPLATE_BUDGET_BYTES` · D5 calibration · panel absorption |
| **2** | v0.16 docs (D-123-A…F) + the Fork A code |
| **3** | `_v3` — rename + D-123-E prose + D-123-F's prompt cut — + the Fork B code |

Commit 3 is forced to stand alone by **D-115-13**: template bytes move, so the filename bump, the
golden re-pins and the prose travel together.

## 11. D-123-F — the advisory `unresolved` list leaves the wire

**Basis:** Joseph, 2026-08-02 — *"the only purpose of stage-2 (and stage-1) is to find matches for
keys we can find matches."*

### The consumer test, applied

Three distinct things share the name `unresolved`:

| | meaning | computable by |
|---|---|---|
| **(a)** | keys **the returned selections** answer nothing for | the controller — `response.py:247-251` |
| **(b)** | keys **anything in EVIDENCE** answers nothing for | only the model |
| **(c)** | keys **the graph** holds nothing for | nobody — thin already cut the space |

The wire carried **(b)**. `GraphSearchResult.unresolved_expressions` is **(a)**. Readers naturally
take it for **(c)**.

**(b) is dropped. (a) stays**, and §8.3 metric 6 with it — (a) is a pure derivation
(`expressions − attributed`), costs no wire, no prompt and no model behaviour, and has live
consumers (the public result, the `all_expressions_unresolved` branch-table contract, the artifact,
replay).

### Why (b) fails the test

`selector_accounting_delta` — the only thing (b) fed — is **computed and read nowhere**:

```
response.py:104     declared
response.py:260     assigned
test_response.py    asserted (its own unit tests)
— nothing else
```

Not in `SearchTelemetry`, not on `GraphSearchResult`, not in the artifact, not in replay, not in any
KPI. The same dead-data pattern as `ProjectedEntity.truncated`, and this one cost design effort:
D8(ii) narrowed the wire to bounded addressing and capped `unresolved` at ≤ 10 explicitly *"keeping
the `selector_accounting_delta` signal bounded"*, and opus5's v0.8 review calls it *"a watched
per-model series."* It was never watched, because it was never recorded anywhere a watcher could see.

**This field should have gone out with `evidence`.** D8(ii) dropped that one on Joseph's consumer
test — *"who's going to use it? nobody"* — and `unresolved` was standing next to it on the same wire
and was not tested.

### What it dissolves

Three open items close as a side effect, with no work of their own:

- **codex F2 (HIGH)** — the prompt-vs-controller semantic divergence has no prompt side left.
- **The `response.py:254` guard** and its docstring mismatch — the whole computation goes.
- **Half of kimi F5** — the model is no longer asked a question whose answer we then reinterpret.

### kimi F5's remainder — deliberately NOT typed

F5 asks whether the downstream consumer is typed to distinguish (c) from (a). Earlier in this review
I recommended a third annotation alongside `cap_exhausted_possible` and `unattributed_possible`.
**Withdrawn.** With (b) gone, `unresolved_expressions` means exactly one thing and says so; and
applying the consumer test again, no consumer decides differently with the annotation than without
it — §8.3 metric 6 runs over class-E probes verified 0-mention across the frozen corpus, so the
shortlist-vs-graph conflation has no measured consumer at all. **Record the reading in the spec; do
not add the annotation.**

### What gets deleted

prompt line 43 + the `"unresolved":["B"]` half of the OUTPUT example (rides `_v3`) ·
`ValidatedResponse.advisory_unresolved` and its `_bounded_labels` validation ·
`ExpressionAccounting.selector_accounting_delta` and the `claimed`/`delta` computation ·
D8/D11's `unresolved`-bounding wire clauses (recorded as superseded, not rewritten).

`VISIBLE_OUTPUT_ALLOWANCE_FAT` = 10,000 does not move — it is an upper bound and the exact maximum
only shrinks. `schema_maximum_fat_document` stays the executable authority for §7.0a;
`test_budget.py`'s literals are re-derived from it rather than hand-computed.

## 12. Two gaps this amendment did not originally cover

Both found during implementation; neither needed an owner call, both recorded because they move a
measured quantity.

**`body_coverage` re-bases.** `search.py:450` computes `hydrated / len(projected)` — the denominator
is the stage-2 pool, fixed at ≤ 100 before D-123-B and budget-dependent after it. The definition is
kept (the fraction of what fat actually received that carried a body); what changes is that its
population is no longer constant, which matters when reading the series across this change. Recorded
in §8.3 rather than left to be discovered as drift.

**`EXCERPT_POLICY_VERSION` was live, not merely a fixture field.** It is stamped on every fat
artifact (`artifact.py:137, 190, 227, 237`; `stage.py:452`), not only declared in the frozen
`manifest.json`. With no policy left it describes nothing — and the artifact already stores the
rendered evidence, so the transformation record is redundant with the data it describes. **Retired
with the policy.** The frozen manifest keeps its `"1"` as the historical record §7.4 already makes it.
