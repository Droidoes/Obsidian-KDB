# Task #62 — Outlier Penalty for FINAL Score

**Status:** Design — awaiting user review before implementation.
**Date:** 2026-05-10.
**Reference:** [`docs/TASKS.md`](TASKS.md) → Task #62 (`in-progress`).
**Companion docs:** [`docs/CODEBASE_OVERVIEW.md` §7](CODEBASE_OVERVIEW.md) — North Star (will gain a new §7.7 + §7.5 amendment); [`docs/task59-m5-replacement-design.md`](task59-m5-replacement-design.md) — context for M5 swap that surfaced this need; D30 ledger entry — companion reweight that addresses a *different* failure mode.
**Memory notes:** `feedback_no_imaginary_risk.md` (single-user, no over-engineering); `feedback_apples_to_apples_within_session.md` (cross-generation FINAL invalidation doctrine D29.9).

---

## 1. Why this exists

**The problem #61 didn't solve.** Task #61 (D30) bumped M5 weight 5%→15% to make body-content quality more impactful in FINAL. That addressed *systemic weight balance*. But it doesn't address *single-axis outliers*: a model that's healthy on 5 out of 6 in-scope measures and catastrophic on 1 still gets a high FINAL because the weighted sum averages everything together.

**The qwen-flash-us pattern.** In the post-#60 regression scorecard (2026-05-10T12:08), qwen-flash-us had M5=0.111 (declares concepts but barely integrates them via wikilinks) — way below the 0.95+ that every other in-scope model achieved. Yet it topped FINAL=0.934 because:
1. M1–M4 = 1.000 (perfect on the other quality measures)
2. M6/M7 Borda dominance (cheap + fast → max Borda ranks)
3. M5 contribution at 5% (D27) was: `0.111 × 0.05 = 0.0056`, vs hypothetical `1.0 × 0.05 = 0.05` — only 4.4 points of FINAL difference

Even after D30's reweight (M5 to 15%), the M5 contribution gap is `(1.0 − 0.111) × 0.15 = 0.133` — still wouldn't dethrone qwen-flash-us at 0.934 → ~0.846.

**The user's stance**: *"if other models can do it, why can't you?"* When a model's measure is far below the candidate-set norm, that's evidence of a real capability gap. The penalty should make this gap drag FINAL down sharply, not be averaged away.

This task adds a per-measure norm-based penalty on top of the weighted sum, surfacing single-axis outliers in the FINAL ranking.

---

## 2. The penalty formula

For each model in the active candidate set, and each in-scope measure (S0, M1, M2, M3, M4, M5):

```
norm           = mean(measure.rate across active models, excluding rate=None)
deviation_pct  = max(0, (norm − value) / norm × 100)        # one-sided: only below-norm penalized
penalty_units  = floor(deviation_pct / 10)                   # 0–9% → 0, 10–19% → 1, 20–29% → 2, ...
```

Per-measure penalty units are summed across in-scope measures for each model:

```
total_penalty_units(model) = Σ over (S0, M1, M2, M3, M4, M5) of penalty_units
```

Final FINAL with penalty applied:

```
FINAL_with_penalty = max(0.0, FINAL_pre_penalty − 0.05 × total_penalty_units)
```

### Worked example — qwen-flash-us in the post-#60 active 8-model scorecard (hypothetical, since qwen-flash-us is now dropped)

| Measure | qwen-flash-us | Norm of others | Deviation | Units |
|---|---|---|---|---|
| S0 | 1.000 | 0.875 | (0.875−1.0)/0.875 < 0 → 0% | 0 |
| M1 | 1.000 | 0.957 | < 0 → 0% | 0 |
| M2 | 1.000 | 0.997 | < 0 → 0% | 0 |
| M3 | 1.000 | 1.000 | 0% | 0 |
| M4 | 1.000 | 0.875 | < 0 → 0% | 0 |
| M5 | **0.111** | 0.954 | (0.954−0.111)/0.954 = **88.4%** | **8** |
| **Total** | | | | **8** |

Effect:
```
FINAL_pre_penalty   = 0.934   (under D30 weights)
total_penalty_units = 8
FINAL_with_penalty  = max(0, 0.934 − 8 × 0.05) = max(0, 0.534) = 0.534
```

qwen-flash-us drops from #1 to last. Healthy models (all measures ≤ 10% below norm) get 0 penalty, no FINAL change.

---

## 3. Locked decisions

| ID | Decision | Rationale |
|---|---|---|
| **D31.1** | Norm = mean of measure rates across active candidate set, excluding `rate=None` | Penalty is a *cross-model* signal — what matters is "how far is this model below what the others achieved." Excluded models (dropped) shouldn't anchor the norm. |
| **D31.2** | One-sided penalty (only when value < norm) | Being above norm is a positive signal, not negative. Exceeding the field shouldn't trigger anything. |
| **D31.3** | Penalty units = `floor(deviation_pct / 10)` | Fixed 10% deviation bands. 0–9% gives no penalty (within-noise tolerance); 10–19% = 1 unit; etc. Discrete bands keep the math interpretable in the trace. |
| **D31.4** | Per-unit penalty = −0.05 from FINAL | User's call (Q1.a from the design conversation). Predictable linear effect; 8 units = −0.40 ≈ enough to dethrone a #1 with one bad measure. |
| **D31.5** | Scope = S0 + M1 + M2 + M3 + M4 + M5 (excludes M6 and M7) | M6/M7 are Borda-normalized within the candidate set already — penalizing being below the Borda mean would double-penalize cost/latency outliers. Quality measures use raw rates and are direct candidates for outlier detection. |
| **D31.6** | Cumulative across measures, no cap | A model far below norm on multiple measures has compounding evidence of capability gaps. User's stance: "if other models can do it, why can't you?" — every band of deviation on every measure represents a real gap. |
| **D31.7** | Floor FINAL at 0.0 | Negative FINAL adds no information. A model with FINAL=0 means "every quality measure is far below the norm" — already maximum signal. |
| **D31.8** | norm = 0 → 0 penalty for everyone on that measure | Avoids divide-by-zero. Semantically: when everyone is equally bad, no one is an outlier. |
| **D31.9** | rate=None on a measure → that (model, measure) skipped from norm computation AND gets 0 penalty for that measure | No data → no signal in either direction. Doesn't unfairly punish a model that legitimately couldn't compute (e.g. corpus-controlled zero-denom). For in-scope measures (S0, M1–M5), this is essentially a defensive case — Round 4 MF6 routes model-controlled zero-denom to `rate=0.0` not `None`, so this branch should rarely fire. |
| **D31.10** | Penalty applies ONLY to active models (`dropped=false`) | Dropped models are already excluded from the ranking; their FINAL values in the scorecard are audit-trail-only. |
| **D31.11** | Output: new `PENALTY` column in scorecard rendered table, between M7_b and FINAL. The displayed FINAL is post-penalty. Pre-penalty value preserved on `RunScore.final_score_pre_penalty` for inspection | Visibility — user sees WHY a model dropped in rank. Pre-penalty preserved for audit. |
| **D31.12** | Cross-generation FINAL comparison invalidated again per D29.9 doctrine | Yet another FINAL formula change in a 24-hour span (#59 measure swap → #61 reweight → #62 penalty). Pre-#62 scorecards' FINALs aren't comparable to post-#62 on any model that has below-norm measures. |

---

## 4. Implementation surface

### 4.1 Data model

`RunScore` (in `kdb_benchmark/scorer.py`) gains:
- `final_score_pre_penalty: Optional[float]` — what `final_score()` returns under D30 weights, before penalty applied
- `penalty: float` — total penalty applied to FINAL (i.e. `0.05 × total_penalty_units`); 0.0 if no units triggered
- `final_score: Optional[float]` — KEPT as the post-penalty value (the canonical FINAL — what gets ranked, what shows in tables)

This preserves backwards-readability: code that reads `run.final_score` continues to get "the rank-this-by" value. New audit fields are additive.

### 4.2 Files touched

| File | Change |
|---|---|
| `kdb_benchmark/scorer.py` | Add `_compute_outlier_penalty(runs)` helper that computes per-model penalty given the active candidate set's measure values. Wire into `score_runs()` immediately after Borda normalization, before final_score assignment. Update `RunScore` dataclass with new fields. Update `final_score()` (or rename to `_pre_penalty_score()`) to compute the pre-penalty value. |
| `kdb_benchmark/scorecard.py` | Update `render_terminal()` table layout: insert `PENALTY` column between `M7_b` and `FINAL`. Update column widths. |
| `kdb_benchmark/tests/test_scorer.py` | Add `TestOutlierPenalty` class (~8 unit tests covering formula, edge cases, integration with score_runs). |
| `kdb_benchmark/tests/test_scorecard.py` | Update render-table tests for new PENALTY column. |
| `docs/CODEBASE_OVERVIEW.md` | Append §7.7 "Outlier penalty" with formula + locked decisions summary. Amend §7.5 to mention penalty as a step in FINAL composition. Add D31 ledger entry. |
| `docs/TASKS.md` | Move #62 to Closed on landing. |

### 4.3 Helper signature (provisional)

```python
def _compute_outlier_penalty(runs: list[RunScore]) -> dict[str, float]:
    """Per-model total penalty (in FINAL units, i.e. units × 0.05).

    For each in-scope measure (S0, M1, M2, M3, M4, M5):
      1. Compute norm = mean of measure.rate across runs (excluding rate=None).
      2. For each run: if value < norm and norm > 0, deviation_pct =
         (norm - value) / norm × 100; units = floor(deviation_pct / 10).
      3. Sum units per run across in-scope measures.

    Returns: dict mapping run.model_id → total penalty (e.g., 0.40 for 8 units).

    Penalty is one-sided (only below-norm); excluded measures are M6/M7
    (Borda-normalized); rate=None skipped from norm AND gets 0 penalty
    for that (model, measure).
    """
```

### 4.4 Scorecard column rendering

Pre-#62:
```
rank  model_id           S0    M1    M2    M3    M4    M5  M6_b  M7_b   FINAL  RAN_AT
```

Post-#62:
```
rank  model_id           S0    M1    M2    M3    M4    M5  M6_b  M7_b   PENALTY   FINAL  RAN_AT
```

`PENALTY` column shows the penalty *deduction* (e.g. `-0.40` or just `-` for zero penalty). FINAL is post-penalty. Rendered example:

```
   1  gemini-3.1-flash-lite  1.000 1.000 0.967 1.000 1.000 1.000 0.429 1.000      -    0.941   ...
   2  qwen-flash-us       1.000 1.000 1.000 1.000 1.000 0.111 0.875 1.000  -0.40    0.534   ...   (hypothetical)
```

---

## 5. Test surface (provisional — finalize in plan)

`TestOutlierPenalty` class in `kdb_benchmark/tests/test_scorer.py`:

1. `test_no_outlier_zero_penalty` — All measures within 10% of norm → all models get 0 penalty.
2. `test_single_axis_outlier_qwen_pattern` — One model 88% below norm on M5, all others healthy → that model gets 8 units = -0.40 penalty; others 0.
3. `test_multiple_axes_outlier_cumulative` — Same model 30% below norm on M3 AND 50% below on M5 → units accumulate (3 + 5 = 8).
4. `test_one_sided_above_norm_no_penalty` — A model significantly *above* norm → 0 penalty (one-sided).
5. `test_norm_zero_no_penalty` — All models score 0 on a measure → norm=0; no penalty (avoids divide-by-zero).
6. `test_rate_none_excluded_from_norm` — A model with rate=None on a measure → that (model, measure) excluded; doesn't anchor norm; gets 0 penalty for that measure.
7. `test_penalty_floors_final_at_zero` — Pre-penalty 0.3, units=10, raw arithmetic gives -0.20 → clamped to 0.0.
8. `test_dropped_models_ignored` — Penalty calculation operates only on active models; dropped models' values don't enter the norm.
9. `test_score_runs_integration` — Full integration: score_runs() produces RunScores with `final_score_pre_penalty`, `penalty`, and `final_score` (post-penalty) all populated.

---

## 6. Documentation amendments

### 6.1 §7.5 (cross-model normalization) — amendment

After the existing bullet about `final_score`, add:

> - **Outlier penalty** (D31, Task #62). After the weighted sum + pro-rata redistribution, an outlier penalty is applied: for each in-scope measure (S0 + M1–M5), models more than 10% below the candidate-set norm receive `−0.05` per 10%-band of deviation. Penalty units accumulate across measures; FINAL is floored at 0. Surfaces single-axis outliers that the weighted sum would otherwise average away.

### 6.2 §7.7 — new section

```markdown
### 7.7 Outlier penalty (D31)

The weighted sum + pro-rata redistribution produces a "balanced average" FINAL that
treats each measure equally up to its weight. This dilutes single-axis outliers — a
model with one catastrophic measure but five healthy ones still ranks high. The
outlier penalty addresses this directly.

**Formula.** For each model and each in-scope measure (S0, M1, M2, M3, M4, M5):

  norm           = mean(measure.rate across active models, excluding rate=None)
  deviation_pct  = max(0, (norm − value) / norm × 100)
  penalty_units  = floor(deviation_pct / 10)

Per-model total: Σ penalty_units across in-scope measures × 0.05 → penalty deduction.
FINAL_with_penalty = max(0.0, FINAL_pre_penalty − total_penalty).

**Properties.**
- One-sided: only below-norm penalized.
- M6/M7 excluded: already Borda-normalized; penalizing them again would double-count.
- Cumulative, no cap: multi-axis underperformance compounds.
- Floor at 0: FINAL ∈ [0, 1] preserved.

**Visibility.** A `PENALTY` column in the rendered scorecard sits between M7_b and
FINAL, showing the deduction (e.g. `-0.40` or `-` for zero). The pre-penalty value
is preserved on `RunScore.final_score_pre_penalty` for audit.

See `docs/task62-outlier-penalty-design.md` for the worked example and full
locked-decision set (D31.1–D31.12).
```

### 6.3 D31 ledger entry

```markdown
| D31 | 2026-05-10 | Outlier penalty added to FINAL composition. For each model and each in-scope measure (S0, M1, M2, M3, M4, M5), units = floor(((norm − value)/norm × 100) / 10) when value < norm; total = Σ units across measures; FINAL_post = max(0, FINAL_pre − 0.05 × total). M6/M7 excluded (Borda-relative). Surfaces single-axis outliers that the weighted sum would average away (e.g. qwen-flash-us with M5=0.111 dethroned). Cross-generation FINAL comparison invalidated again per D29.9 doctrine. See `docs/task62-outlier-penalty-design.md` (D31.1–D31.12 sub-decisions). |
```

---

## 7. Sequencing

1. **This spec** lands at `docs/task62-outlier-penalty-design.md` (committed, user-reviewed).
2. **Implementation** (one combined task — small enough to skip a separate plan doc):
   - Edit scorer.py: add helper, update RunScore, wire into score_runs.
   - Edit scorecard.py: add PENALTY column.
   - Add tests (TestOutlierPenalty).
   - Edit CODEBASE_OVERVIEW.md: §7.5 amendment, new §7.7, D31 ledger entry.
3. **Live verification**: a single cheap merge fire (e.g. gemma4 free) recomputes the post-#62 FINAL across the active 8-model set. The PENALTY column will show 0 for healthy models. Confirms no behavior regressions for in-norm models.
4. **Close #62** in TASKS.md.

---

## 8. Known limitations

| # | Limitation | Severity | Notes |
|---|---|---|---|
| L1 | Single-fire candidate sets (n=1) get penalty=0 because norm = self for every measure | None | Trivially correct: with one model, there's nothing to outlier against. The penalty surfaces meaningful signal only when comparing across ≥2 models. |
| L2 | Norm-based: a sweep where everyone is mediocre raises the bar for "outlier" | Acceptable | If all models score 0.5 on a measure, no one is penalized for being at 0.5 — that's correct behavior. The penalty surfaces deviation from peers, not from absolute quality. |
| L3 | The 10% threshold + −0.05/unit are calibration constants chosen by user spec, not derived from data | Low | If the calibration feels off after live use (e.g. all models routinely get 1+ units, or no model ever gets >0), revisit in a follow-up task. |
| L4 | Penalty doesn't distinguish "almost passes 10% bar" (12% deviation, 1 unit) from "barely passes" (10.001%, also 1 unit) | Low | Discrete bands are simpler; finer-grained continuous scaling could come later if needed. |

---

## 9. Verification criteria for closure

- [ ] All test files updated; full kdb_benchmark suite green (190 → ~199 expected).
- [ ] CODEBASE_OVERVIEW.md §7.5 mentions penalty; new §7.7 present; D31 ledger entry added.
- [ ] One real benchmark fire produces a scorecard with PENALTY column rendering correctly. Healthy models (all measures within 10% of norm) show penalty = `-` (zero).
- [ ] `RunScore.final_score_pre_penalty` and `RunScore.penalty` populated for every active model.
- [ ] No regression on existing scoring logic — pre-existing tests (M1–M7, S0, final_score) all still pass.
- [ ] TASKS.md entry for #62 closed with commit SHA.
