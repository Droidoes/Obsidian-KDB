# Task #19 — KDB Benchmark KPI Design

> **HISTORICAL RECORD (Phase 5 closed 2026-05-08).** The architectural summary now lives in [`docs/CODEBASE_OVERVIEW.md` §7 — Benchmark Architecture](CODEBASE_OVERVIEW.md). This document remains as the historical record of how the design was reached (rounds 1–4 + Phase 3 spec + Round 4 corrections). The locked weights and bucket structure are unchanged; this file is no longer the source of truth for new code — refer to CODEBASE_OVERVIEW §7 first, drill into this file for spec mechanics or design-round provenance.

**Status:** **Phase 3 + Round 4 CLOSED 2026-05-06** — code-ready spec locked (function signatures, dataclass shapes, per-measure formulas, edge-case policies, average-rank tie handling, final-score formula). Round 4 followed Codex hostile review take 2 (`task19-kpi-design-codex-feedback-take-2.md`): all 8 must-fixes addressed (parse-fail / M6-M7 contradiction; pre-response provider/model fallback in telemetry; cost-persistence wording corrected to Option ε; non-dict parsed_json guards; Borda algorithm renamed to average-rank with all-equal policy; zero-denominator policy split into model-controlled (= 0.0 penalty) vs corpus-controlled (= None pro-rata); RunScore shape gains separate `m6_borda` / `m7_borda` fields; `retry_load` clamped). **Phase 5 (CODEBASE_OVERVIEW promotion) closed 2026-05-08.** Earlier: Phase 2 + **Round 3** (Codex-driven corrections) **CLOSED** 2026-05-04 — page-spam exploit closed, formulas hardened, M5/telemetry implementation tracked as Task #28 / #29 (both closed 2026-05-05). See § *Phase 3 — Detailed Spec* below for the locked spec, and § *Round 4 Corrections* at its tail for the delta from take-2.
**Date:** 2026-04-30 (Phase 1 landed; Phase 2 Tier 2 Quality Core restructured same day) → 2026-05-02 (Phase 2 Tier 2 Output/Cost/Efficiency walkthrough complete; 11 → 9 measures) → 2026-05-03 (Phase 2 closed: Q2/Q4/Q5/Q6 resolved, intra-bucket weights allocated) → 2026-05-04 (Round 3: Codex hostile review surfaced M6/M7 page-spam exploit, M2/M3 math defects, M5 versioning ambiguity, doc contradictions; corrections landed — source-words denominator, Jaccard formulas, M5 symmetric + impl-first, M8/M9 demoted to diagnostic-only, weights re-allocated S0=20 / Quality=30 / Integrity=20 / Cost=30 / Efficiency=0) → 2026-05-05 (Tasks #28 + #29 closed: M5 body-link symmetric Jaccard `validate_compiled_source_response.body_link_check` + RespStatsRecord telemetry plumbing) → 2026-05-06 (Phase 3 closed: detailed scorer spec) → **2026-05-06 Round 4 (Codex take 2: 8 must-fixes + 4 design-calls + 4 cheap-wins all landed; 1 small telemetry code fix + 7 new tests folded in)**
**Reference:** [`docs/TASKS.md`](TASKS.md) → Task #19 (`open`, parent: Task #5 LLM benchmarking); Task #28 (M5 impl) and Task #29 (telemetry plumbing) gate Phase 3.
**Companion docs:** [`post-gap-recall-2026-04-30.md`](post-gap-recall-2026-04-30.md) · [`session-handoff-2026-04-21.md`](session-handoff-2026-04-21.md) · [`task19-kpi-design-codex-feedback-take-1.md`](task19-kpi-design-codex-feedback-take-1.md) — adversarial review that drove Round 3

## Lifecycle of this document

| Phase | What this doc is |
|---|---|
| **Phase 1** (now) | The KPI proposal — full set of metrics, computation methods, proposed weights, open calibration questions |
| **Phase 2** | The user picks/refines from the proposal. Edits land here as the spec converges. |
| **Phase 3** | The detailed spec (exact thresholds, exact formulas, exact normalization choices). Edits land here. |
| **Phase 5** | The agreed architecture is **moved into `docs/CODEBASE_OVERVIEW.md`** as the North Star benchmark section. This file remains as historical record of how the design was reached. |

This doc is **mutable during Phases 1–3** — both parties edit it as the design converges. Once promoted to `CODEBASE_OVERVIEW.md`, this becomes a frozen artifact.

---

## Anchor Decisions (already locked — NOT open for re-litigation)

These were settled in prior sessions and reaffirmed at the start of Phase 1 (2026-04-30). Listed here so they survive future gaps and don't get accidentally re-opened.

### D1 — No LLM-as-Judge

The benchmark scorer is a **static, deterministic, weight-based script**. Every KPI in this doc reduces to arithmetic over existing telemetry (`resp_stats`) or validator findings. No model is in the scoring loop.

**Why:**
- Determinism: re-running the same benchmark yields identical scores — essential for tracking model regressions over time.
- Auditability: every score traces back to a numeric source the user can inspect (`runs/<run_id>.json`, `llm_resp/<run_id>/*.json`).
- Cost: an LLM-as-judge layer would cost as much per benchmark as the runs themselves.
- Avoids circularity: scoring an LLM's output with another LLM introduces correlated failure modes (both judges pattern-match the same prompt artifacts).

**Implication for KPI design:** every proposed metric must be computable from existing or near-trivial new instrumentation. Ground-truth-required KPIs (e.g., "is this concept *correct*?") are out of Phase 1 scope and live in Task #20 (ground-truth source).

### D2 — Pairing Invariant is a First-Class KPI

The `concept_slugs[]` ⟷ concept-typed pages and `article_slugs[]` ⟷ article-typed pages pairing invariants — the same drift that motivated the 2026-04-21 reconciler stage — are explicitly tracked in the benchmark across three complementary KPIs:

- **`concept_slugs_coverage` (Tier 2 measure M2)** — auto-reconcilable error density for concept slugs only: `(commission + omission) / final_concept_page_count`. Lower scores indicate more reconciler work, not model unusability.
- **`article_slugs_coverage` (Tier 2 measure M3)** — auto-reconcilable error density for article slugs only, same formula structure. Tracked separately so concept-vs-article failure patterns are diagnosable.
- **`pairing_type_mismatch_rate`** — unreconcilable mismatch (slug declared as concept, page emitted as article, or vice versa). Contributes to **S3** (`validator_hard_zero_pass_rate`) as one of five "hard-zero" finding types. **Round 3 update (2026-05-03):** per Q6 resolution, NOT separately tracked as a Tier 2 diagnostic measure — per-finding diagnosis lives in `runs/<run_id>.json` payload inspection, not as a scored or weighted KPI.

**Why:**
- The pairing-invariant fight is well-documented (see `MEMORY.md` → `project_patch_applier_intent_vs_record.md`, `project_milestone_validator_reconciler_live.md`). Two consecutive real-vault compiles on 2026-04-21 each hit `pairing_omission` on different slugs, proving the defect class is probabilistic and recurring.
- A model that produces clean output without needing the reconciler is more efficient (less downstream computation) and signals stronger prompt-following.
- The validator already emits the raw counts — the benchmark just aggregates them.

### D3 — Malformed JSON Fails Hard (No JSON Retry)

The retry mechanism in `kdb_compiler/call_model_retry.py` retries ONLY on transient SDK errors (rate-limit, network timeout, retryable HTTP status codes with `Retry-After` honored). **Malformed JSON output from the LLM is NOT retried** — `response_normalizer.parse_json_object` raises `ValueError` on parse failure, which bubbles up and is caught at the source level by `compile_one`. The failed source is excluded from the run aggregate; the run continues processing other sources.

**Why:**
- Retrying malformed JSON wastes tokens — if the LLM produces unparseable output, the chance a retry succeeds is no better than chance, and is a model-quality signal that should be measured, not papered over.
- Confounds telemetry — JSON-retry would inflate `cost_per_page` without a clear quality benefit and obscure model differences.
- Aligns with the `feedback_measurability_over_defensive_complexity.md` memory note — invest in measuring quality, not in elaborate retry machinery.

**Implication for KPI design:** **S1** (`llm_resp_success_rate`) measures *first-and-only-attempt* JSON success per source. Transient SDK retries are operationally invisible to the model's quality signal (they affect latency and possibly cost, but never count against S1). Only model-fault failures (unparseable output) drive S1 down.

**Round 3 clarification (2026-05-04):** "excluded from the run aggregate" means excluded from `compile_result.compiled_sources` (the success-payload artifact) — it does **NOT** mean excluded from benchmark scoring denominators. The benchmark scorer reads `RespStatsRecord` for **every attempted source**, including parse-failed ones (the `RespStatsRecord` is written in a `finally` block at `compiler.py:154` regardless of which stage failed). So in S1's `(LLM successes) / N` formula, `N` is the **planned corpus size** (every attempted source contributes to the denominator), not the count of successfully-completed sources.

### D4 — Per-Source Counts, Per-Run Statistics

The benchmark engine records ONE TRIAL per source. Each trial = one `compile_one` invocation on one corpus source. Per-trial outcomes (LLM success, validator findings, telemetry) are recorded individually so they can be inspected for diagnosis.

**All run-level statistics are computed by micro-aggregation:** accumulate per-source numerators and denominators across all trials in the run, then evaluate the rate.

**Why:**
- One LLM call → one source → one outcome. Per-source is the natural atomic unit of LLM evaluation.
- Production pipeline's run-level all-or-nothing semantics (validator gate-finding aborts the whole run, vault writes nothing) is a deployment policy required for vault coherence — it is *not* a property of model quality.
- Decoupling benchmark unit from production unit means production-side gate semantics don't constrain benchmark scoring. Same validator code runs in both contexts; different invocation patterns and consequences.

**Methodology note (statistical fact, not a separate decision):** Macro-averaging — i.e. computing per-source rates and then averaging them — is mathematically wrong for failure rates and weighted measures. It silently weighs every source equally regardless of denominator size, which distorts results for any source with disproportionate event counts (more outgoing_links, more candidate slugs, more pages, etc.).

Formally: `rate = Σ numerator_i / Σ denominator_i`, NOT `rate = mean(numerator_i / denominator_i)`.

This isn't a design decision (it's a statistical fact, like 1+1=2) — it's surfaced here as a methodology note because the per-source language in this anchor would otherwise be misread as endorsing macro-averaging.

**Implication for KPI design:** all stage success rates (S0/S1/S2/S3) and all measures aggregate per-source counts into per-run rates via micro-aggregation. Corpus size is N (set by Task #20). For binary per-source outcomes (S0/S1/S2/S3), micro-aggregate equals macro-average numerically; for rate-valued metrics (M1–M11), they differ.

### D5 — Benchmark Has No Gates — Only Rates

Unlike production (where validator gate-severity findings abort the whole run), the **benchmark engine has no gates**. Every source completes to a recorded outcome regardless of any validator findings. Models are not "disqualified" — they are scored, and lower scores rank lower. There is no minimum threshold.

**Why:**
- The benchmark's purpose is to *rank* models for production use, not to *filter* them. Filtering happens later, by humans, after benchmark scores are reviewed.
- Threshold-based gates require corpus-size calibration, which would couple Task #19 to Task #20 unnecessarily.
- Per-source rates are mathematically continuous; pretending they're binary gates loses information.

**Implication for KPI design:** S1, S2, S3 are stage success rates, not pass/fail gates. The end-to-end success rate **S0** = direct joint count of fully-succeeded sources. All four (S0/S1/S2/S3) are scored or reported, none act as filters.

**Round 3 addition (2026-05-04) — `RespStatsRecord` is the scorer authority.** Because `compile_one` returns early on multiple failure stages (source-read, prompt-build, model-call, truncation, extract, parse, schema, semantic — see `kdb_compiler/compiler.py:140+`), the `compile_result.compiled_sources` array excludes failed sources. The `RespStatsRecord` writer guarantees one record per attempted source via the `finally` block — so the benchmark scorer reads `resp_stats` (full corpus coverage), NOT `compile_result` (success-only payload). This makes D5 ("every source completes to a recorded outcome") operationally true via the resp_stats layer, not the compile_result layer.

---

## The KPI Architecture

The KPIs split into three groups (post-Round 3):

1. **Stage Success Rates (S0–S3)** — the headline rate (S0) plus its diagnostic decomposition (S1/S2/S3). No thresholds, no gating. Per D5, these are scores, not filters.
2. **Tier 2 — Measures (scored)** — **seven** weighted KPIs across three buckets: Quality Core (M1/M2/M3), Output Integrity (M4/M5), Production Cost (M6/M7). Sum with S0 to 100%.
3. **Diagnostic-only Telemetry (unscored)** — captured in `RespStatsRecord` and surfaced in scorecards for inspection but not contributing to the score: `retry_load`, `token_overrun_rate`, `pages_per_1k_source_words`.

The final per-model score combines S0 (20%) with the seven Tier 2 measures (80%). Bucket-level allocation: Quality Core 30% / Output Integrity 20% / Production Cost 30% / [Efficiency Proxies dissolved into diagnostic-only telemetry, 0%].

---

### Stage Success Rates (S0–S3)

These four metrics decompose the per-source success path through the pipeline. **S0** is the headline KPI; **S1 / S2 / S3** are diagnostic decompositions that explain *where* a model fails when it does.

#### Definitions

| ID | Name | Definition | Computation |
|---|---|---|---|
| **S0** | `end_to_end_success_rate` | Fraction of corpus sources that passed all three downstream checks (LLM → schema → hard-zero) | **Direct joint count:** `(sources where S1=PASS AND S2=PASS AND S3=PASS) / N` |
| **S1** | `llm_resp_success_rate` | Fraction of sources where the LLM call returned parseable JSON | `(LLM successes) / N` — unconditional |
| **S2** | `validator_schema_pass_rate` | Of LLM-passing sources, fraction with no `schema_violation` finding | `(no schema_violation among LLM-pass) / (LLM-pass)` — conditional on S1 |
| **S3** | `validator_hard_zero_pass_rate` | Of LLM-passing sources, fraction with **none** of the five "hard-zero" finding types | `(no hard-zero among LLM-pass) / (LLM-pass)` — conditional on S1 |

**The five hard-zero finding types contributing to S3:**
1. `duplicate_slug` — same slug appears more than once in `pages[]`
2. `summary_slug_missing` — declared `summary_slug` not in `pages[]`
3. `summary_slug_wrong_type` — `summary_slug`'s page has `page_type ≠ "summary"`
4. `pairing_type_mismatch` — slug + page both present, page has wrong `page_type` (the unreconcilable case from D2)
5. `reserved_slug` — output uses a reserved slug name

`schema_violation` is its own dimension via **S2** and is intentionally separated from the S3 set. All six are emitted as `severity="gate"` by the validator in production (and trigger run-abort there), but the benchmark partitions schema separately because it is a fundamentally different failure mode (structural contract violation vs. graph-topology corruption).

#### Role in scoring

| Metric | Used in score formula? | Reported in scorecard? |
|---|---|---|
| **S0** | **Yes — high weight (proposed ~20%, locked in Tier 2 rebalance step)** | Yes — the headline number |
| S1 | No (would double-count S0) | Yes — diagnostic decomposition |
| S2 | No | Yes — diagnostic, conditional on S1 |
| S3 | No | Yes — diagnostic, conditional on S1 |

S1/S2/S3 are reported alongside S0 for diagnosis but are NOT separately weighted in the score. A model with poor S1 already scores low on S0 — penalizing it again via a separate S1 weight would double-count.

#### Why S0 is computed directly, not as S1 × S2 × S3

The multiplication `S0 ≈ S1 × S2 × S3` is a useful approximation, but it is **not exact** because:
- Stage failures are not statistically independent (a model that fails schema may or may not also fail hard-zero on the same source).
- The marginal vs. conditional rate distinction creates ambiguity in how to compute the multiplication.

**Worked example** showing the discrepancy (5 sources):

| Source | S1 | S2 | S3 | Fully passed? |
|---|---|---|---|---|
| 1 | ✓ | ✓ | ✓ | **✓** |
| 2 | ✓ | ✓ | ✓ | **✓** |
| 3 | ✗ | — | — | ✗ |
| 4 | ✓ | ✓ | ✗ (`duplicate_slug`) | ✗ |
| 5 | ✓ | ✗ (`schema_violation`) | ✓ | ✗ |

- **Direct S0 = 2/5 = 40%** (sources 1 and 2 fully succeeded)
- Multiplication using marginal rates: 0.80 × 0.60 × 0.60 = **28.8%** — undershoots
- Multiplication using conditional rates: 0.80 × 0.75 × 0.75 = **45%** — overshoots

The direct count is exact and requires no independence assumption. **Compute S0 directly. Use multiplication only as a rough estimator when only aggregated stagewise rates are available** (e.g., comparing externally-reported model metrics).

#### Diagnostic value of stagewise decomposition

S1, S2, S3 reported alongside S0 tell the story of *where* a model fails:

- **High S1, low S2, normal S3** → model produces JSON well but schema-drifts often → prompt tweaks or schema-strictness adjustments may help.
- **Low S1, high S2/S3** → model has trouble producing JSON at all; when it does, the output is clean → may be a context-length or sampling issue more than a quality issue.
- **High S1, normal S2, low S3** → model writes valid output but tends to corrupt graph topology (duplicate slugs, type-mismatches) → harder to mitigate, more concerning for production use.

These diagnostic patterns matter for picking *between* models with similar S0 scores — a model failing predominantly at S1 (LLM call) is easier to mitigate than one failing at S3 (graph corruption).

### Tier 2 — MEASURES (weighted; weights locked Round 3 2026-05-04)

Continuous-valued KPIs that contribute to model ranking. Higher = better (after each measure's "good direction" is fixed; raw rates whose natural direction is "lower = better" are inverted at scoring time, not at definition time). **All measures use micro-aggregation** per D4: per-source numerators and denominators accumulated across the corpus, then the rate is computed once. Per-source values are retained for diagnostic drill-down but never averaged into per-model rates.

**Restructure note (Phase 2 + Round 3 reviews, 2026-04-30 → 2026-05-04):**

*Round 1 (2026-04-30, Quality Core):*
- Removed: original M1 `pairing_integrity` (replaced by per-type M2/M3 below).
- Removed: original M2 `existing_context_reuse_rate` (M2 measured the wrong thing — see Task #26 stub. To be revisited only after #26 defines "effective context list" objectively).
- Restructured: original M4 `concept_slugs_coverage` reformulated as error-density and renumbered as M2.
- Added: `article_slugs_coverage` as M3 — same formula structure as M2, scoped to article slugs.
- Renumbered: original M5–M12 → M4–M11.

*Round 2 (2026-05-02, Output / Cost / Efficiency walkthrough):*
- M4 (`semantic_pass_rate`): description corrected to the four contract rules actually enforced by `validate_compiled_source_response.semantic_check`. Prior wording ("no fenced wrappers, no architecture jargon") described tests that don't exist in code.
- M5 (`body_link_syntax_match`): retained; flagged **implementation pending** (~30 LOC validator extension — current validator does not check body-text occurrences of declared `outgoing_links`).
- M6 (`page_count_sanity`): **removed.** The 500-words-per-concept heuristic was an unsupported guess; "right amount of concepts" is not measurable without ground truth (Task #20 territory).
- M7 (`cost_per_page`) → renamed `cost_per_page_per_run`. Definition is the raw rate only. Cross-model rank-normalization moves out of the KPI definition into the scorecard / ranking step (Phase 3 / Task #22).
- M8: `p50_latency` → replaced by `latency_per_page_per_run`. Median latency is meaningless when sources have heterogeneous lengths (one short source's median doesn't compare to one long source's median). Volume-normalized rate `Σ latency_ms_i ÷ Σ pages_produced_i` mirrors cost-per-page and is the right unit for cross-model comparison.
- M9 (`p95_latency`): **removed.** Same heterogeneity problem — a corpus mixing 1K-word, 5K-word, and 50K-word sources cannot produce an interpretable p95 of per-call latencies. (User analogy: not 100 people running 5K — 20 run 1K, 30 run 5K, 50 run a marathon.)
- M10 (`retry_rate`) → renamed `retry_load`. Cap-normalized formula `Σ (attempts_i − 1) ÷ (N × max_retries)` so the metric scales with effort, not with binary "retried at least once" coin-flips.
- M11 (`token_overrun_rate`): unchanged.
- Renumbered: M7 → M6, M8 → M7, M10 → M8, M11 → M9.

*Round 3 (2026-05-04, Codex hostile review corrections — see [`task19-kpi-design-codex-feedback-take-1.md`](task19-kpi-design-codex-feedback-take-1.md)):*
- **M2/M3 formula → Jaccard.** Replaced `1 − (commission + omission) / final_count` (math defects: undefined when `final_count==0`, can go negative when `commission > final_count`, depends on post-reconciliation state) with bounded symmetric Jaccard `|declared ∩ emitted| / |declared ∪ emitted|`. Reconciliation-independent; bounded `[0, 1]`.
- **M5 → symmetric Jaccard.** Replaced one-way "declared ⊆ body" check with symmetric Jaccard `|declared ∩ body| / |declared ∪ body|`. Catches BOTH metadata-promised-but-not-embedded AND body-wikilinks-not-declared-in-metadata. **M5 implementation must land before first benchmark run** — tracked as Task #28; "rolls into M4 if M5 doesn't land" rule deleted.
- **M6/M7 denominator → source-words.** Replaced "per page produced" with "per 1K source words." Closes the page-spam exploit (Codex finding #3): a model fragmenting concepts into many tiny pages would game cost/latency by inflating the page-count denominator. Source words are model-independent (corpus-controlled), apple-to-apple across providers and tokenizers.
- **NEW diagnostic** `pages_per_1k_source_words` — tracks fragmentation tendency without scoring it. Visible in scorecards as a "model behavior signature" but no weight.
- **M8/M9 demoted to diagnostic-only.** Efficiency proxies were already partially absorbed by M6/M7 (retries inflate cost; overruns extend latency). Zero weight; raw values still captured in `RespStatsRecord`. The Efficiency Proxies bucket dissolves entirely.
- **Tier 2 reduces 9 measures / 4 buckets → 7 measures / 3 buckets** (Quality Core, Output Integrity, Production Cost).
- **Weights re-allocated:** S0=20, M1=20, M2=5, M3=5, M4=15, M5=5, M6=15, M7=15. Total=100%. M1 dominant in Quality Core (graph integrity is the most fundamental KB-compounding signal); M6=M7 (batch workload values $/source-word and ms/source-word equally); Production Cost bucket bumped 20→30% to match Quality Core's importance.
- **Doc contradictions resolved:** D2 dropped "Tier 2 diagnostic measure" wording (conflicted with Q6); D3 + D5 clarified that `RespStatsRecord` is the scorer's denominator authority (not `compile_result`); Q4 closing language scoped honestly to "deterministic structural telemetry" only.
- **`scorecard_version` and `pricing_version` explicitly NOT added.** Per user's "rank latest, pick best" workflow — no cross-version comparison plan, so Codex's candidate-set-dependence critique is defused. Cost is **derived at score time** by the benchmark scorer from `(input_tokens, output_tokens) × ModelEntry.price_in/price_out` (Option ε from 2026-05-05 — the boundary-respecting alternative; `cost_usd` is intentionally **not** persisted on `RespStatsRecord`). Re-priceability falls out for free: change `models.json`, re-score, no record migration. Versioning ceremony has no payoff for this single-user, infrequent workload (per `feedback_no_imaginary_risk`).

**7 scored measures** (was 9 after Round 2, 11 after Round 1, 12 in Phase 1). Weights locked alongside Round 3 closure.

#### Quality Core — KB-Compounding Signals (3 measures)

These measure the things that determine whether the KDB actually *compounds* knowledge over time or just accumulates noise. The reason this project exists.

| ID | KPI | What it measures | How to compute (micro-aggregate) | Weight |
|---|---|---|---|---|
| **M1** | `link_target_resolution` | `outgoing_links` that resolve to a real page (in `pages[]` or existing manifest) | `Σ resolved_outgoing_links_i ÷ Σ total_outgoing_links_i` (over sources where `total_outgoing_links_i > 0`) | **20%** |
| **M2** | `concept_slugs_coverage` | Symmetric agreement (Jaccard) between **declared concept slugs** and **emitted concept-typed pages**. Catches both commissions (slug declared, no page) AND omissions (page exists, slug missing) without depending on reconciliation state. | `Σ \|declared_concept_slugs_i ∩ emitted_concept_page_slugs_i\| ÷ Σ \|declared_concept_slugs_i ∪ emitted_concept_page_slugs_i\|`. Bounded `[0,1]`; reconciliation-independent (no "final" count needed). | **5%** |
| **M3** | `article_slugs_coverage` | Same as M2 but for article slugs / article-typed pages — separate measure so concept-vs-article failure patterns are diagnosable. | `Σ \|declared_article_slugs_i ∩ emitted_article_page_slugs_i\| ÷ Σ \|declared_article_slugs_i ∪ emitted_article_page_slugs_i\|`. Bounded `[0,1]`. | **5%** |

**M1 vs M2/M3 distinction:** M1 measures **graph integrity** (do declared links resolve?). M2/M3 measure **slug-page alignment integrity** (do slug lists match emitted pages?). These are independent dimensions of KB-compounding quality — a model can be perfect on M1 (every link resolves) but bad on M2 (slug lists don't match its own page emissions), and vice versa.

#### Output Integrity — Semantic + Structural Correctness (2 measures)

These measure whether the output is *clean* — even when the output isn't tripping S2/S3 at the validator level (i.e., the run can proceed), the output can still drift on per-source contract rules or on body-text wiring.

| ID | KPI | What it measures | How to compute (micro-aggregate) | Weight |
|---|---|---|---|---|
| **M4** | `semantic_pass_rate` | Per-source contract rules enforced by `validate_compiled_source_response.semantic_check`: (1) `payload['source_id']` echoes the input `source_id` verbatim; (2) declared `summary_slug` appears in `pages[].slug`; (3) **exactly one** page has `page_type == 'summary'` AND its slug equals `summary_slug`; (4) every page's `supports_page_existence[]` contains the input `source_id`. A source passes iff all four rules hold (`semantic_ok == True`). | `Σ semantic_ok_i ÷ N` (binary per source — micro = macro for binary) | **15%** |
| **M5** | `body_link_syntax_match` | **Symmetric Jaccard** between per-page `outgoing_links[]` (declared metadata) and `[[slug]]` wikilinks parsed from the page body. Catches BOTH metadata-promised-but-not-embedded AND body-wikilinks-not-declared-in-metadata. **Implementation pending — must land before first benchmark run (Task #28).** ~30 LOC extension to `validate_compiled_source_response` to scan body for `[[<slug>]]` tokens, build the body wikilink set, and emit per-page `\|declared ∩ body\|` and `\|declared ∪ body\|` counts. | `Σ \|declared_outgoing_links_p ∩ body_wikilinks_p\| ÷ Σ \|declared_outgoing_links_p ∪ body_wikilinks_p\|` aggregated over all pages `p` (where the union is non-empty). Bounded `[0,1]`. | **5%** |

#### Production Cost (2 measures)

Both rates are **definitions only** — raw per-run aggregates. Cross-model normalization for ranking happens in the scorecard step (Phase 3 / Task #22), not in the KPI definition. Keeping the KPI as the raw rate preserves dimensional meaning ($ / 1K source words; ms / 1K source words).

**Round 3 denominator change (2026-05-04):** The denominator is **source words**, NOT pages produced. Source words are corpus-controlled (model-independent) and apple-to-apple across providers and tokenizers — the only invariant unit available without ground truth. The earlier `per-page` denominator was gameable: a model fragmenting concepts into many tiny pages could inflate `pages_produced` and look artificially cheap/fast (Codex review #3). Source-words closes this exploit because the model cannot influence the input corpus. Tokenizer differences across providers don't show up either (a 5K-word source is 5K source words for everyone, regardless of how each model tokenizes it).

| ID | KPI | What it measures | How to compute (micro-aggregate) | Weight |
|---|---|---|---|---|
| **M6** | `cost_per_1k_source_words` | Total LLM cost per 1K source words — input + output billing combined, normalized to a model-independent denominator. Captures the full economic dimension. | `(Σ cost_usd_i ÷ Σ source_words_i) × 1000`, where `cost_usd_i = (input_tokens_i × price_in + output_tokens_i × price_out) / 1_000_000` is **derived at score time** by the benchmark scorer (Option ε): `RespStatsRecord` carries the always-on `input_tokens` / `output_tokens` / `source_words`; the scorer multiplies through `kdb_benchmark/models.json`'s per-model `price_in` / `price_out`. Not persisted — re-priceable historical runs. | **15%** |
| **M7** | `latency_per_1k_source_words` | Wall-clock latency per 1K source words. Mirrors M6's denominator for cross-model comparability. | `(Σ resp_stats.latency_ms_i ÷ Σ source_words_i) × 1000` | **15%** |

### Diagnostic-only Telemetry (no weight; tracked for inspection)

These fields are captured in `RespStatsRecord` (or derived at scorer time from corpus metadata) and surfaced in the scorecard alongside scored measures, but they do **not** contribute to the score.

**Round 3 rationale (2026-05-04):** the original Efficiency Proxies bucket (M8 retry_load, M9 token_overrun_rate, weighted 4% each) was demoted because retries already inflate cost (M6) and overruns extend latency (M7) — separately scoring them double-counts. They remain valuable for *diagnosis* ("why is Model X expensive?") but not for *ranking*. Joined by the new `pages_per_1k_source_words` to track fragmentation tendency without rewarding or penalizing it (the underlying page-spam exploit is closed at M6/M7's denominator level).

| ID | Field | What it tracks | How to compute (micro-aggregate) | Weight |
|---|---|---|---|---|
| — | `retry_load` (was M8) | Cap-normalized retry effort — fraction of the maximum possible retry budget the run actually consumed. | `Σ (attempts_i − 1) ÷ (N × max_retries)` where `max_retries` is the per-call cap (currently 2 additional attempts per `kdb_compiler/call_model_retry.py`). | **0% (diagnostic)** |
| — | `token_overrun_rate` (was M9) | Fraction of calls that hit the `max_tokens` ceiling. High values signal systematic prompt-budget mismatch or runaway output. | `Σ token_overrun_i ÷ N` where `token_overrun_i = stop_reason_i in {"max_tokens", "length"}` (canonical set per `compiler.py:223`; persisted in `RespStatsRecord` via Task #29). | **0% (diagnostic)** |
| — | `pages_per_1k_source_words` (new) | Pages emitted per 1K source words — surfaces fragmentation tendency. Model A producing 1 page / 1K words is concise; Model B producing 4+ is fragmenting. Useful signature even though M6/M7's source-word denominator already removes the gameability incentive. | `(Σ pages_produced_i ÷ Σ source_words_i) × 1000` | **0% (diagnostic)** |

**Final weight totals (locked Round 3 2026-05-04):** S0 (20%) + Tier 2 scored measures (80%, broken into Quality Core 30% / Output Integrity 20% / Production Cost 30%) sum to 100%. Three diagnostic-only fields tracked unweighted. Full intra-bucket breakdown in the Weight Philosophy → *Final weight allocation* table below.

---

## Weight Philosophy

The score formula combines **S0 (end-to-end success rate)** with the **Tier 2 measure buckets**. Bucket allocations reflect a deliberate emphasis on the irreducible reasons the project exists.

| Bucket | Total weight | Bucket-relative | Rationale |
|---|---|---|---|
| **End-to-end success (S0)** | **20%** | — | Headline usability KPI. Computed directly from per-source data. Captures *"how often does this model actually work end-to-end?"* — the single most important question about model viability. |
| **Tier 2 — Quality Core (KB-compounding)** | **30%** | 37.5% of Tier 2 | The reason the project exists. A model that's cheap and fast but mints duplicate slugs every run is *worse than useless* — it actively poisons the vault. Highest weight inside Tier 2 (tied with Production Cost — see below). |
| **Tier 2 — Output Integrity** | **20%** | 25% of Tier 2 | Secondary correctness. Cleaner output reduces downstream maintenance burden but doesn't break compounding. |
| **Tier 2 — Production Cost** | **30%** | 37.5% of Tier 2 | **Round 3 reweight (2026-05-04):** bumped from 20% to match Quality Core. Rationale: a model that produces beautiful KB output at unaffordable cost is no better than one that fails — production benchmark must clear both dimensions. |
| **Tier 2 — Efficiency Proxies** | **0%** (dissolved) | — | **Round 3 (2026-05-04):** dissolved into diagnostic-only telemetry. Retries already absorbed by cost (M6); overruns already absorbed by latency (M7). Separately weighting them double-counted. M8/M9 raw values still captured in `RespStatsRecord` for inspection — just not scored. |

**Bucket → measure mapping (post-Round 3):**

| Bucket | Measures | Count |
|---|---|---|
| Quality Core | M1 `link_target_resolution`, M2 `concept_slugs_coverage`, M3 `article_slugs_coverage` | 3 |
| Output Integrity | M4 `semantic_pass_rate`, M5 `body_link_syntax_match` | 2 |
| Production Cost | M6 `cost_per_1k_source_words`, M7 `latency_per_1k_source_words` | 2 |
| Diagnostic-only telemetry (unscored) | `retry_load`, `token_overrun_rate`, `pages_per_1k_source_words` | 3 |

**Final weight allocation (locked Round 3 2026-05-04):**

| Component | Weight | Rationale for sub-weight |
|---|---|---|
| **S0** `end_to_end_success_rate` | **20%** | Headline usability KPI per Q5 resolution — high enough to anchor the score, low enough that Tier 2 dimensions still differentiate among S0-similar models. |
| **M1** `link_target_resolution` | **20%** | Most fundamental graph-integrity signal — declared `outgoing_links` resolving to real pages is the load-bearing requirement for KB-compounding. Receives the largest sub-weight in Quality Core (4× M2 / 4× M3). |
| **M2** `concept_slugs_coverage` (Jaccard) | **5%** | Pairing invariant (concept side) — co-equal with M3. Bounded `[0,1]` symmetric set agreement. |
| **M3** `article_slugs_coverage` (Jaccard) | **5%** | Pairing invariant (article side) — co-equal with M2. |
| **M4** `semantic_pass_rate` | **15%** | Active, broad per-source contract enforcement (4 rules); the structural-correctness anchor of Output Integrity. |
| **M5** `body_link_syntax_match` (symmetric Jaccard) | **5%** | Body↔metadata link parity. **Implementation tracked as Task #28**, must land before first benchmark run; no rollover, no version ambiguity. |
| **M6** `cost_per_1k_source_words` | **15%** | $/1K source words — direct economic dimension, model-independent denominator (closes page-spam exploit). |
| **M7** `latency_per_1k_source_words` | **15%** | ms/1K source words — same denominator pattern as M6 for cross-model comparability. Equal weight to M6 (batch workload values cost and throughput equally). |
| **Total** | **100%** ✓ | |

**Diagnostic-only (unweighted, tracked in scorecard):** `retry_load`, `token_overrun_rate`, `pages_per_1k_source_words`.

**Caveats captured at lock-time:**
- **S0=20%** is "at least for now" per the user; revisit after the first real benchmark run if model spreads cluster oddly (e.g., too many at S0=100%, dimension stops differentiating).
- **M1 / Quality Core ratio** (M1=20 vs M2=5 vs M3=5) is a stated **policy** — graph integrity dominates pairing-invariant measures. Codex review #8 flagged that intra-bucket weights are intuition rather than evidence; this is acknowledged. Reweight criterion for v2 of the design: if a ±50% perturbation on any sub-weight flips the top-3 model rankings on the first benchmark, revisit.
- **No `scorecard_version` field.** Per user workflow ("rank latest, pick best — no cross-version compare"). If the workflow ever changes (e.g., tracking model performance over time as part of a regression suite), versioning becomes necessary and the doc has to revisit this decision.

---

## Phase 2 — Open Calibration Questions

These are the calibration knobs to resolve **before Phase 3** (detailed spec). The Stage Success Rates, Tier 2 measures, and bucket philosophy above are the architecture; the questions below are the dials.

### Q1 — Gate Thresholds **[RESOLVED by D5]**

The original Q1 asked for calibration of gate thresholds (G1-G4 bars). **This question is fully resolved by D5: the benchmark has no gates, only rates.** The original four gates have been restructured into **S0/S1/S2/S3 stage success rates** (Stage Success Rates section above), which are scored continuously without thresholds.

Historical artifact only — no calibration needed.

### Q2 — Cost / Latency Normalization **[RESOLVED 2026-05-03 — Option A; Round 3 update 2026-05-04]**

For M6/M7 (`cost_per_1k_source_words`, `latency_per_1k_source_words`), how raw values normalize into the 0–weight scoring scale at the **scorecard step** (KPI definitions themselves remain raw rates per Round 2 + Round 3):

- **Option A — Rank-based (Borda-style)** ✅ **chosen.** Cheapest / fastest model gets full marks, most expensive / slowest gets 0, others linear in between. Robust to outliers; reflects the real decision question ("which of these models is the best for us?"); easier to maintain than absolute thresholds since model prices and latencies shift frequently.
- ~~Option B — Absolute thresholds~~ Not adopted. Absolute thresholds may re-emerge in Task #20 for ground-truth-anchored evaluation but are out of scope for the cross-model ranking benchmark.

**Implementation note:** rank-based normalization happens in the scorecard layer (Phase 3 / Task #22), not in M6/M7 KPI computation. M6/M7 store the raw rate; the scorecard converts to rank-based scores at score-emission time. This separation lets alternative ranking schemes feed off the same raw measurement layer without redefining the KPIs.

**Round 3 reckoning with Codex review #6.** Codex flagged three pathologies of Borda normalization:
1. **Candidate-set dependence** — adding/removing a candidate shifts existing scores. **Defused** by user workflow: no cross-version comparison plan. Each scorecard ranks the candidates *at that moment*; we never compare scorecard_t1 to scorecard_t2 across different candidate sets.
2. **Magnitude erasure** — rank treats $0.001 → $0.002 (2× difference) and $0.002 → $0.100 (50× difference) as adjacent steps. **Acknowledged but accepted** under the same workflow logic: within a single scorecard, the rank ordering is what drives the model-selection decision; raw rates remain visible in the scorecard for human inspection of magnitude.
3. **Tie handling undefined** — must be specified in Phase 3 spec. Default proposal: dense rank with averaging (tied candidates share the average of their tied positions).

If the user workflow ever shifts to cross-version comparison, this decision should be revisited — log-scale or min-max with a fixed reference set would close the magnitude-erasure gap.

### Q3 — Instrumentation for `existing_context_reuse_rate` **[RESOLVED — measure dropped]**

The original Q3 asked whether to invest ~30–50 LOC in `planner.py` instrumentation to enable an `existing_context_reuse_rate` measure. **This question is fully resolved by removing the measure entirely** (2026-04-30 Phase 2 Tier 2 review): the metric measured the wrong thing — it implicitly assumed "more reuse = better," which is false in cases where the source legitimately introduces new specializations distinct from existing context concepts.

The deeper design problem this exposed (the EXISTING CONTEXT list's rationale and effectiveness criteria are undocumented) is now tracked as **Task #26** — *Systematic review of EXISTING CONTEXT list design.* Once #26 defines "effective context list" objectively, a measure equivalent to the original M2 may be reintroduced — but only with proper grounding.

Historical artifact only — no calibration or instrumentation work needed for Task #19.

### Q4 — KPI Set Completeness **[RESOLVED 2026-05-03 — no additions]**

Things considered but not included — table retained as historical record of what was reviewed and ruled out:

| Considered | Status | Why |
|---|---|---|
| LLM-as-judge / semantic similarity scoring | **Out** | D1 — no model in the scoring loop |
| Embedding-based slug-similarity to detect near-duplicates | **Out** | LLM-as-judge adjacent (depends on an embedding model's quality) |
| Human-labeled ground-truth | **Deferred** | Task #20 territory — not a per-run static KPI |
| Output diversity (variance across re-runs of the same source) | **Deferred** | Interesting but secondary; Task #21+ candidate |
| Vault-graph metrics (centrality, clustering) | **Deferred** | Too downstream — graph properties depend on accumulated runs, not single-run quality |
| Round-trip stability (compare two runs on identical input) | **Deferred** | Same as diversity — multi-run analysis, not per-run |

**Resolution:** nothing from the things-considered list adopted. **Round 3 honesty update (2026-05-04):** the resulting KPI set is complete only for **deterministic structural telemetry** — graph hygiene, slug-page pairing, body-link parity, contract enforcement, cost, latency. It does **NOT** measure semantic correctness — hallucinated body text, wrong concept definitions, semantically duplicated near-slugs, shallow but structurally valid pages, or wrong reuse of existing context are **invisible** to this benchmark under D1 (no LLM-as-judge) and the absence of ground truth. That blind spot is real and should be named, not papered over by claiming "completeness." Semantic correctness measurement waits on Task #20 (ground truth source). Items in the **Deferred** column remain candidates for future-task ownership (Task #20 / #21+).

### Q5 — S0 Weight Calibration + Intra-bucket Allocation **[RESOLVED 2026-05-03; reweighted Round 3 2026-05-04]**

Final weight for **S0** in the combined score formula: **20%.**

**Rationale:** once a model's S0 reaches ~70–80%, distinguishing models depends on quality and cost — not on squeezing more reliability. 20% is high enough to anchor the score (any model with bad S0 falls fast) without crowding out the Tier 2 dimensions that differentiate among S0-similar models.

**User caveat at lock-time:** "at least for now" — the 20% number is locked for the first benchmark run; revisit after first real model spreads land if the dimension is mis-weighted (e.g., if too many models cluster at S0=100% and the dimension stops differentiating).

**Round 3 reweighting (2026-05-04 — bucket-level + intra-bucket):**

*Bucket-level changes:*
- Quality Core: 32% → **30%** (small reduction; intra-bucket M1 emphasis preserves overall graph-integrity weight)
- Output Integrity: 20% → **20%** (unchanged)
- Production Cost: 20% → **30%** (bumped to match Quality Core; cost is now first-class alongside KB-compounding)
- Efficiency Proxies: 8% → **0%** (bucket dissolved; M8/M9 demoted to diagnostic-only telemetry)

*Intra-bucket allocation:*
- Quality Core 30%: **M1=20**, M2=5, M3=5 — graph integrity dominant; pairing-invariant measures co-equal in supporting role
- Output Integrity 20%: **M4=15**, M5=5 — semantic_pass_rate (4 contract rules) dominates; body-link parity narrower scope
- Production Cost 30%: **M6=15, M7=15** — equal split; batch workload values $/source-word and ms/source-word equally
- Efficiency Proxies dissolved (M8=0, M9=0; tracked as diagnostics)

Final total: S0 + M1 + M2 + M3 + M4 + M5 + M6 + M7 = 20 + 20 + 5 + 5 + 15 + 5 + 15 + 15 = **100%** ✓

### Q6 — Diagnostic per-finding-type measures **[RESOLVED 2026-05-03 — not adding]**

The original proposal would have added six low-weight (1–3% each) diagnostic measures (`duplicate_slug_rate`, `summary_slug_missing_rate`, `summary_slug_wrong_type_rate`, `pairing_type_mismatch_rate`, `reserved_slug_rate`, `schema_violation_rate`) to expose individual failure modes underlying S3 (and S2 in `schema_violation`'s case).

**Resolution: NOT added.** Tier 2 stays at 9 measures, not 15 (further reduced to **7 scored measures** in Round 3 via M8/M9 demotion to diagnostic-only telemetry — see the *Round 3* entry in the restructure note). Rationale: longer KPI list and more weight-allocation complexity are not worth the diagnostic granularity, given that S3 already aggregates the five hard-zero types and the underlying per-finding counts are preserved in `runs/<run_id>.json`. A scorecard reader can drill into individual finding types by inspecting the validator-finding payload directly — no need to elevate them to scored KPIs.

**Implication:** S3 remains a single rolled-up rate. Per-finding-type diagnosis is a **scorecard inspection feature**, not a **scoring feature**. Principle worth keeping for future KPI proposals: granular diagnostics belong in scorecard *inspection*, not scorecard *scoring*; KPI elevation has real cost (weight allocation, list length, presentation noise) that raw payload preservation avoids.

---

## Out of Scope for Phase 1

To keep the design tight, these are **explicitly out of scope** for Task #19 — they belong to sibling/downstream tasks:

| Concern | Owner |
|---|---|
| Ground-truth source decision (where does "correct" come from?) | Task #20 |
| Models registry expansion (the 21-model `models.json` shape) | Task #21 |
| Scorecard format (how scores are presented) | Task #22 |
| Architecture documentation in `CODEBASE_OVERVIEW.md` | Task #23 (partially advanced by this doc) |
| The benchmark **runner** (CLI, harness, parallel execution) | Future task — depends on #19/#20 |
| The benchmark **scorer** module (the actual code that reads runs and computes scores) | Future task — depends on #19 |
| EXISTING CONTEXT list design rationale + effectiveness criteria | Task #26 — surfaced from Phase 2 dialogue when M2 was found to measure the wrong thing |
| Manifest scalability assessment + industry-standard review | Task #27 — surfaced from Phase 2 dialogue ([3.1] question) |

---

## Phase 2 — Status & remaining work

> ⚠️ **Historical record. Superseded by Round 3 (2026-05-04) and Phase 3 / Round 4 (2026-05-06) below.** The intra-bucket weights, measure names, and per-page denominators recorded in this section reflect the pre-Round-3 state and do **not** match the locked Phase 3 spec. They are kept here for design-history continuity. For the current scorer contract, jump to *Phase 3 — Detailed Spec*.

**Resolved in Phase 2** (2026-04-30 → 2026-05-03):
- ✅ Q1 — Gate thresholds: dropped (D5: no gates).
- ✅ Q3 — M2 instrumentation: dropped (M2 measure removed; rationale in Q3 below; Task #26 owns the deeper redesign).
- ✅ Stage Success Rates structure (S0/S1/S2/S3) + computation method locked.
- ✅ Anchor decisions D3, D4 (with embedded micro-aggregation methodology note), D5 added.
- ✅ Tier 2 Round 1 (Quality Core, 2026-04-30): M1 (`pairing_integrity`) and M2 (`existing_context_reuse_rate`) removed; M2/M3 (`concept_slugs_coverage` / `article_slugs_coverage`) introduced; renumber M5–M12 → M4–M11.
- ✅ Tier 2 Round 2 (Output / Cost / Efficiency, 2026-05-02):
    - M4 description corrected to the 4 actual `semantic_check` contract rules.
    - M5 retained, flagged implementation-pending (~30 LOC validator extension).
    - M6 `page_count_sanity` removed (heuristic was unsupported; "right number of concepts" needs ground truth).
    - M7 → M6 `cost_per_page_per_run` — definition is raw rate; rank-normalization moves to scorecard step.
    - M8 (`p50_latency`) → M7 `latency_per_page_per_run` — volume-normalized, mirrors cost-per-page (heterogeneous source sizes invalidate percentile latency).
    - M9 (`p95_latency`) removed (same heterogeneity problem).
    - M10 (`retry_rate`) → M8 `retry_load` — cap-normalized formula `Σ (attempts_i − 1) ÷ (N × max_retries)`.
    - M11 → M9 `token_overrun_rate` — unchanged.
    - **Total: 11 → 9 measures.**
- ✅ Spawned Task #26 (EXISTING CONTEXT list design review) and Task #27 (manifest scalability review).
- ✅ **Q2 — Cost/latency normalization (2026-05-03):** Option A (rank-based, Borda-style) at the scorecard step; KPI definitions remain raw rates.
- ✅ **Q4 — KPI completeness (2026-05-03):** no additions; 9-measure Tier 2 set is final.
- ✅ **Q5 — S0 weight + intra-bucket allocation (2026-05-03):** S0 = 20%; bucket weights 32% / 20% / 20% / 8% (Quality Core / Output Integrity / Production Cost / Efficiency Proxies); intra-bucket sub-weights M1=12, M2=10, M3=10, M4=14, M5=6, M6=12, M7=8, M8=4, M9=4. All sum to 100%. See Weight Philosophy → *Final weight allocation* table.
- ✅ **Q6 — Diagnostic per-finding-type measures (2026-05-03):** not added; S3 stays as a single rolled-up rate; per-finding diagnosis lives in `runs/<run_id>.json` inspection.

**Phase 2 status: CLOSED 2026-05-03.** All open calibration knobs resolved; weights locked; this doc was the agreed architecture for the benchmark scorer at that point.

**Round 3 status: CLOSED 2026-05-04** following Codex hostile review (`task19-kpi-design-codex-feedback-take-1.md`). Round 3 corrections:
- ✅ **M2/M3 formula → Jaccard** (math defects of `1 − (commission + omission) / final_count` resolved; bounded `[0,1]`; reconciliation-independent).
- ✅ **M5 → symmetric Jaccard** + implementation tracked as **Task #28** (must land before first benchmark run; rollover rule deleted, no version ambiguity).
- ✅ **M6/M7 denominator → source-words** (page-spam exploit closed; model-independent denominator).
- ✅ **M8/M9 demoted to diagnostic-only telemetry** + new diagnostic `pages_per_1k_source_words`. Tier 2: 9 measures / 4 buckets → 7 measures / 3 buckets.
- ✅ **Weights re-allocated:** S0=20, M1=20, M2=5, M3=5, M4=15, M5=5, M6=15, M7=15. Bucket-level: 20/30/20/30/0.
- ✅ **Telemetry plumbing tracked as Task #29** — extend `RespStatsRecord` with `stop_reason`, `token_overrun`; surface per-source `source_words` from corpus metadata; require `price_in` / `price_out` on `ModelEntry`. **Note:** the original Round 3 plan also called for persisting `cost_usd` on `RespStatsRecord`, but that was abandoned during Task #29 implementation when it was found to violate the `kdb_compiler -/-> kdb_benchmark` import boundary from Task #18 (`5825d0f`). Replaced with **Option ε** — scorer derives cost at score time from token counts × registry. Cleaner, smaller diff, and yields free re-priceability of historical runs.
- ✅ **`scorecard_version` / `pricing_version` explicitly NOT added** — user's "rank latest, pick best" workflow has no cross-version compare plan; cost computed and frozen at run time.
- ✅ **Doc contradictions resolved:** D2 dropped "Tier 2 diagnostic measure" wording; D3 + D5 clarified `RespStatsRecord` as scorer authority (not `compile_result`); Q4 closing language scoped honestly to "deterministic structural telemetry."
- ✅ **Codex review #6 (Borda pathologies) reckoned with:** candidate-set dependence defused by user workflow; magnitude erasure acknowledged but accepted; tie handling deferred to Phase 3 spec.
- ✅ **Codex review #12 (D1 blind spot) acknowledged:** Q4 resolution now states the benchmark cannot detect semantic-correctness failures (hallucinations, wrong definitions, near-duplicates) under D1 without ground truth. Task #20 territory.

**Round 3 → Phase 3 Pivot.** Phase 3 was gated on **Task #28 (M5 implementation)** and **Task #29 (telemetry plumbing)** landing first; both closed 2026-05-05 (`0bcc2b6`, `26b345a`). Phase 3 then converted the locked design into the code-ready scorer spec below.

**Phase 3 status: CLOSED 2026-05-06.** All deliverables landed in this doc as the *Phase 3 — Detailed Spec* section: function signatures, dataclass shapes, per-measure formulas with explicit edge-case policies, Borda tie handling, and the final-score formula (with pro-rata redistribution). Two small housekeeping changes folded into the Phase 3 commit: `MAX_RETRIES = 2` exported from `kdb_compiler/call_model_retry.py` (so the scorer's `retry_load` formula doesn't re-derive the cap); and a public `check_compiled_source(parsed_json) -> list[str]` wrapper added to `kdb_compiler/validate_compile_result.py` (so the scorer can derive S3 hard-zero findings from a parsed-source dict without re-shaping it as an aggregate `compile_result`). Tests: full suite at 455 passed / 1 skipped (unchanged baseline).

Phase 5 will then move the agreed architecture into `docs/CODEBASE_OVERVIEW.md` and close Task #19 in `docs/TASKS.md` with a pointer back to this file as the historical design record. Phase 5 trigger conditions are listed at the end of the Phase 3 spec below.

---

## Phase 3 — Detailed Spec (locked 2026-05-06)

This section converts the locked Round 3 design into code-ready function signatures, dataclass shapes, and per-measure computation rules. The future scorer-impl task (sibling of Tasks #20–#23, depends on #19) lands the actual code; this spec is the contract that code must satisfy.

### 1. Module layout & boundaries

The benchmark scorer lives at `kdb_benchmark/scorer.py` (new file in the existing engine package from Task #18, commit `5825d0f`). It imports from `kdb_compiler` (types + validators) but is never imported by it — preserving the one-way `kdb_benchmark → kdb_compiler` boundary.

**Imports allowed:**
- `kdb_compiler.types.RespStatsRecord` (data shape)
- `kdb_compiler.validate_compile_result.check_compiled_source` (added in this commit) and `HARD_ZERO_FINDING_TYPES`
- `kdb_compiler.call_model_retry.MAX_RETRIES` (added in this commit; for `retry_load` cap)
- `kdb_benchmark.registry.{ModelEntry, load_registry}` (for cost prices)
- `kdb_benchmark.paths` constants

**Imports forbidden:**
- `kdb_compiler.compiler` (compile-time logic — scorer is read-only)
- `kdb_compiler.run_journal` (journal is the runner's concern, not scorer's)

### 2. Input contract

The scorer reads exactly one source of truth: the `RespStatsRecord` JSON files written by `compile_one`'s finally block, located at:

    <state_root>/llm_resp/<run_id>/<safe_source_id>.json

One file per attempted source. Full corpus coverage (D5 Round 3 — `RespStatsRecord` is the scorer's denominator authority because `compile_result.compiled_sources` excludes failed sources via `compile_one`'s early returns at `compiler.py:185`/`200`/`219`/`231`/`241`/`251`/`262`/`275`).

The aggregate `compile_result.json` is **not** read. Its compiled-sources list is success-only; the parse-failed sources the scorer needs are absent from it.

For benchmark mode, `state_root` resolves under `benchmark/runs/<run_id>/` (exact layout owned by the future runner task; the scorer accepts `state_root` as a parameter and does not assume any specific layout).

### 3. Operational requirement: capture-full mode

Three measures (M1, M2, M3) and the S3 hard-zero derivation require `RespStatsRecord.parsed_json` to be populated. That field is env-gated by `KDB_RESP_STATS_CAPTURE_FULL=1` (`resp_stats_writer.py:42`). The always-on `parsed_summary` carries a *count*-style digest (`page_count`, `page_types: dict[str, int]` histogram, `slugs: list[str]`, `outgoing_link_count: int`) — but **not** per-page `outgoing_links` values nor a per-page `(slug → page_type)` mapping. M1/M2/M3/S3 need both.

**Benchmark mode therefore mandates `KDB_RESP_STATS_CAPTURE_FULL=1`.** The runner sets it; the scorer asserts it. If `score_run()` encounters a matching record where `parse_ok=True` but `parsed_json is None`, it raises `RuntimeError("benchmark mode requires KDB_RESP_STATS_CAPTURE_FULL=1")`.

Production runs (which don't score) can leave the env var unset — bodies stay slim in the steady state. The constraint is purely a benchmark-time operational one; the on-disk record schema is unchanged.

### 4. Edge-case policies (locked)

| Case | Policy | Rationale |
|---|---|---|
| **Source with `parse_ok=False`** | Contributes `(0, 0)` to M1/M2/M3/M5 numerator + denominator. Counts as `semantic_ok=False` in M4 (binary 0 to numerator, 1 to N). **Included in M6/M7 if `source_words > 0`** — failed calls still bill cost and latency. Counts in N for S0/S1/M4 and `token_overrun_rate`. | Failure already captured by S0/S1; including it in M1–M5 again would double-count. M6/M7 ARE expected to bill the cost / latency of failed calls — those are economically real (truncation, extract failure, parse failure, schema failure, semantic failure all happen *after* the model call). The `source_words > 0` filter (not `parse_ok=True`) is the right gate. **Round 4 MF1 fix.** |
| **Source with `parse_ok=True` but non-dict `parsed_json`** | `json.loads()` succeeded but produced a list or scalar (`["foo", "bar"]`, `42`, `null`). Treat as if `parse_ok=False` for M1/M2/M3/M5/S3 derivation: contribute `(0, 0)`. The record is still counted in M4's denominator (`semantic_ok` will be False). The scorer guards every `parsed_json` access with `if not isinstance(r.parsed_json, dict): continue` before dereferencing `["pages"]`, `["concept_slugs"]`, etc. | `parse_ok=True` only proves the JSON parsed; it does NOT prove dict shape. M1/M2/M3 formulas would crash on a list. `check_compiled_source` likewise needs the same guard. **Round 4 MF4 fix.** |
| **Source with dict `parsed_json` but wrong field types** (e.g., `concept_slugs` is a string, `pages` is `null`, `outgoing_links` not a list) | Treat the offending field as empty for that measure. `D = set(r.parsed_json.get("concept_slugs", []))` becomes `D = set(value) if isinstance(value, list) else set()`. Same defensive coercion `body_link_check` and `build_parsed_summary` already use. | Schema validation (S2) catches these as failures, but the measure formulas still need deterministic behavior. `set("abc")` would otherwise produce `{"a","b","c"}` — three character-slugs that score against the model. **Round 4 CW2 fix.** |
| **Run-level zero denominator** — distinguish source by who controls it | **Model-controlled denominators (M1/M2/M3/M5):** zero-denominator scores `0.0`, NOT `None`. This prevents abstention from removing a scored dimension — a model emitting zero outgoing-links cannot dodge M1, a model emitting zero concept slugs cannot dodge M2, etc. **Corpus-controlled denominators (M6/M7 source_words):** zero-denominator stays `None` and triggers pro-rata weight redistribution; only true empty-corpus / invalid-corpus pathologies hit this. | Take-1 review's link-abstinence concern, raised again in take-2. The previous "all zero-denom = None" rule rewarded models that produced no structure to evaluate. The split policy keeps the empty-corpus failure mode honest while closing the abstention loophole. **Round 4 MF6 fix.** Reference wording: *"For scored measures whose denominator is model-controlled (M1/M2/M3/M5), a run-level zero denominator scores 0.0, not None. This prevents abstention from removing a scored dimension. Corpus-controlled zero denominators such as M6/M7 source_words remain None and trigger pro-rata redistribution only for true empty/invalid-corpus pathologies."* |
| **Tie handling — M6/M7 average-rank normalization** | Tied candidates share the **average of their tied ordinal positions** (fractional rank). All-equal-candidates case (every model has the same raw rate): every candidate gets score `0.5` (no signal). | Cleanest mathematically; works for any tie pattern at any position. Worked example in § 7. **Round 4 MF5 fix** — the algorithm is "average-rank / fractional rank," not "dense rank with averaging" (the term used in earlier drafts described a different scheme). |
| **`source_words = 0`** (empty-source pathology — corpus-side bug) | Source excluded from BOTH numerator and denominator of M6, M7, and `pages_per_1k_source_words`. Scorer logs a warning. | `(cost_usd, 0)` and `(latency_ms, 0)` are meaningless per-source contributions; corpus curation should prevent the case from arising. |
| **`token_overrun=True` source** | No exclusion. Counts toward cost (M6) and latency (M7) like any other call. Surfaced separately in the unweighted `token_overrun_rate` diagnostic. | M8/M9 demotion's whole point: cost and latency naturally absorb overrun effort. Separate scoring would double-count. |
| **`attempts` corner cases** for `retry_load` | Per-source contribution is `min(MAX_RETRIES, max(0, attempts_i − 1))` — clamped at `MAX_RETRIES` so overridden `max_attempts` cannot push the diagnostic above 1.0; floor-clamped at 0 so pre-call failures (where `attempts=0`) don't subtract. | `call_model_with_retry` accepts `max_attempts` as a parameter and nothing forbids `attempts > MAX_RETRIES + 1` in research/override modes. Clamping is permissive. **Round 4 MF8 fix.** |
| **M1 link-resolution target set** (no Task #20 ground truth yet) | Resolution set = union of `parsed_summary.slugs` from all `parse_ok=True ∧ schema_ok=True ∧ isinstance(parsed_json, dict)` records in this run. When Task #20 ships, the truth manifest joins this union. | Without ground truth, the run's own emitted slugs are the only valid resolution corpus. Within-run cross-source resolution is meaningful (sources can legitimately link to each other's pages). |
| **M1 duplicate outgoing links** in one page (`outgoing_links: ["bar", "bar"]`) | **List semantics**: each occurrence counts separately. `denominator += 2`; `numerator` increments once if `"bar"` is in `target_set`, twice if both occurrences are. | Matches the on-disk shape (no implicit dedup). M5 explicitly uses set semantics in `body_link_check`; M1 explicitly uses list semantics. The two contracts are complementary and both deliberate. **Round 4 CW3 fix** — undefined in Phase 3 take-1; locked here. |
| **Multiple records for the same `source_id`** in one run | Scorer raises `ValueError("duplicate (run_id, source_id)")`. Do not silently dedupe. | `compile_one` writes one record per source per run by design. Duplication signals a bug. |
| **`provider` / `model` field on pre-response failures** | The on-disk record now persists the **requested** provider/model (from the runner's call site) when `model_response is None`, not empty strings. The scorer's filter contract `(run_id, provider, model)` therefore holds for parse-failed and source-read-failed records too. | Earlier RespStatsRecord persisted `provider=""` / `model=""` when no `ModelResponse` existed (`resp_stats_writer.py:147-149` pre-Round-4) — pre-response failures vanished from the scorer's denominator. Telemetry code fix (one line) folded into this commit. **Round 4 MF2 fix.** |

### 5. Dataclass shapes

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass(frozen=True)
class MeasureScore:
    """One measure's contribution to a model's run score."""
    name: str                # "S0", "M1", ..., "M7", "retry_load", ...
    numerator: float         # raw aggregate; semantic per measure
    denominator: float       # raw aggregate; semantic per measure
    rate: Optional[float]    # numerator / denominator; None if denominator == 0
    weight: float            # 0.20, 0.05, ... or 0.0 for diagnostics

    def to_dict(self) -> dict: ...


@dataclass(frozen=True)
class RunScore:
    """Per-(model, run) full scorecard. Single-model view.

    `MeasureScore.rate` always carries the **raw** measurement (set ratios
    in [0, 1] for S0/S1/S2/S3/M1–M5; raw $/ms-per-1K-words for M6/M7).
    The Borda-normalized [0, 1] scores for M6/M7 live separately in
    `m6_borda` / `m7_borda` so the underlying MeasureScore stays
    immutable and unit-stable. `final_score` is None until normalization
    has been applied across the candidate set via `score_runs()`.
    """
    run_id: str
    model_id: str                          # ModelEntry.id — stable scorecard key
    provider: str                          # ModelEntry.provider — derived for billing
    model: str                             # ModelEntry.model — derived for billing
    n_attempted: int                       # = len(matching RespStatsRecords)
    s0: MeasureScore                       # weight = 0.20 (only S* with weight)
    s1: MeasureScore                       # diagnostic, weight = 0.0
    s2: MeasureScore                       # diagnostic, weight = 0.0
    s3: MeasureScore                       # diagnostic, weight = 0.0
    measures: dict[str, MeasureScore]      # keys: "M1", "M2", "M3", "M4", "M5", "M6", "M7"; M6/M7 rates are RAW
    diagnostics: dict[str, MeasureScore]   # keys: "retry_load", "token_overrun_rate", "pages_per_1k_source_words"
    m6_borda: Optional[float]              # M6 Borda-normalized score in [0, 1]; None until score_runs() applied
    m7_borda: Optional[float]              # M7 Borda-normalized score in [0, 1]; None until score_runs() applied
    final_score: Optional[float]           # populated by score_runs(); None on raw RunScore

    def to_dict(self) -> dict: ...
```

`MeasureScore` carries both raw `(numerator, denominator)` and the derived `rate` so a scorecard reader can drill into the underlying counts without re-deriving. `weight` is stored on the score (not on a separate weight table) so the dataclass is self-describing. **MeasureScore is immutable and unit-stable** — `rate` for M6/M7 always denotes the raw $/ms-per-1K-words; the Borda-normalized [0, 1] form lives on `RunScore.m6_borda` / `m7_borda` instead. **Round 4 MF7 fix** — earlier draft proposed replacing M6/M7 rates in-place during `score_runs()`, which would have produced inconsistent shapes (raw numerator/denominator + normalized rate inside one `MeasureScore`). The split-field design preserves immutability and makes the scorecard layer's responsibilities clearer.

### 6. Per-measure computation rules

**Notation throughout:**
- `R` = list of all `RespStatsRecord` matching `(run_id, provider, model)` derived from `model_id` lookup (see § 9 — score_run takes `model_id`, looks up the registry's `(provider, model)`, and filters records on those).
- `R_p`  = `{ r ∈ R : r.parse_ok ∧ isinstance(r.parsed_json, dict) }` (parse-pass with dict shape).
- `R_ps` = `{ r ∈ R_p : r.schema_ok }` (parse + schema pass).
- `r.parsed_json` is the always-present parsed dict (capture-full mode required — see § 3). **Every dereference of `r.parsed_json["pages"]`, `r.parsed_json["concept_slugs"]`, etc. is guarded by `isinstance(r.parsed_json, dict)` first** (Round 4 MF4) — non-dict parsed values (parse succeeded into a list/scalar) contribute `(0, 0)` to per-page measures.
- **Defensive field coercion:** for any field expected to be `list[str]`, the scorer treats non-list or non-string-element values as empty (Round 4 CW2). `D = set(value) if isinstance(value, list) else set()` — never `set(maybe_a_string)`, which would produce char-slugs.
- All measures use **micro-aggregation** per D4: per-source numerators and denominators accumulate across the corpus; the rate is computed once over the sums.

#### S0 — `pipeline_success_rate` (weight 20%)

```
numerator   = |{ r ∈ R : r.parse_ok ∧ r.schema_ok ∧ isinstance(r.parsed_json, dict)
                         ∧ no_hard_zero(r.parsed_json) }|
denominator = |R|
rate        = numerator / denominator   (None iff |R| == 0)
```

where `no_hard_zero(parsed_json) := check_compiled_source(parsed_json) == []`.

**Round 4 rename (MF5/DC1):** previously `end_to_end_success_rate`. The honest name is `pipeline_success_rate` — S0 = S1 ∧ S2 ∧ S3 covers parse + schema + hard-zero but **not** `semantic_ok`. Calling it "end-to-end" overclaimed against production semantics, where a source must also pass `semantic_check` to land in `compile_result.compiled_sources`. The locked Round 3 formula is preserved (no Round 3 reopening); only the name changes. Production behavior remains a slightly stronger condition than S0 PASS — the gap is captured by M4 at 15% weight, and a model with high S0 + low M4 is a recognizable failure pattern.

#### S1 — `llm_resp_success_rate` (diagnostic, weight 0)

```
numerator   = |R_p|       # parse_ok == True ∧ isinstance(parsed_json, dict)
denominator = |R|
```

#### S2 — `validator_schema_pass_rate` (diagnostic, weight 0; conditional on S1)

```
numerator   = |{ r ∈ R_p : r.schema_ok }|
denominator = |R_p|
```

`schema_ok` is from the *per-source* validator (`validate_compiled_source_response.validate`), not the aggregate one. Maps 1:1 because the aggregate `schema_violation` finding type and the per-source schema-validation result both express "the JSON does not satisfy the response schema."

#### S3 — `validator_hard_zero_pass_rate` (diagnostic, weight 0; conditional on S1)

```
numerator   = |{ r ∈ R_p : check_compiled_source(r.parsed_json) == [] }|
denominator = |R_p|
```

The 5 hard-zero finding types live in `HARD_ZERO_FINDING_TYPES` (`kdb_compiler/validate_compile_result.py`) and are: `duplicate_slug`, `summary_slug_missing`, `summary_slug_wrong_type`, `pairing_type_mismatch`, `reserved_slug`. Measure-severity findings (`pairing_commission`, `pairing_omission`) are intentionally excluded — they are reconcilable, not hard-zero.

#### M1 — `link_target_resolution` (weight 20%, Quality Core)

```
target_set = set()
for r in R_ps:
  pages = r.parsed_json.get("pages")
  if isinstance(pages, list):
    for p in pages:
      if isinstance(p, dict) and isinstance(p.get("slug"), str):
        target_set.add(p["slug"])

numerator   = 0
denominator = 0
for r in R_p:
  pages = r.parsed_json.get("pages")
  if not isinstance(pages, list):
    continue
  for p in pages:
    if not isinstance(p, dict):
      continue
    links = p.get("outgoing_links")
    if not isinstance(links, list):
      continue
    for link in links:                      # LIST SEMANTICS — duplicates count
      if not isinstance(link, str):
        continue
      denominator += 1
      if link in target_set:
        numerator += 1

rate = numerator / denominator   (0.0 if denominator == 0 — see § 4 zero-denom row)
```

**List semantics for outgoing_links** (Round 4 CW3): duplicates within a single page's `outgoing_links` (`["bar", "bar"]`) count separately. M5 explicitly uses set semantics (in `body_link_check`); M1 uses list semantics. Both are deliberate — M1 measures graph-resolution rate per *declaration*, M5 measures parity per *unique slug*.

**Zero-denominator policy** (Round 4 MF6): a model emitting zero outgoing_links across the corpus scores M1 = 0.0 (model-controlled denominator → abstention is penalized, not redistributed).

**Self-link semantics:** if a page declares an outgoing link to its own slug, that counts as resolved (the slug is in `target_set` because the page is in `pages[]`). Production behavior agrees.

**Cross-source semantics:** if source A's page X has `outgoing_links: ["Y"]` and slug "Y" is a page in source B (also parse-pass + schema-pass), it counts as resolved. Within-run cross-source resolution is the intended behavior — the run's emitted slugs collectively form the link target manifest in benchmark mode.

#### M2 — `concept_slugs_coverage` (weight 5%, Quality Core, Jaccard)

```
numerator   = 0
denominator = 0
for r in R_p:
  raw_slugs = r.parsed_json.get("concept_slugs")
  D = set(raw_slugs) if isinstance(raw_slugs, list) else set()      # CW2 coercion
  D = {s for s in D if isinstance(s, str)}
  pages = r.parsed_json.get("pages")
  E = set()
  if isinstance(pages, list):
    for p in pages:
      if isinstance(p, dict) and p.get("page_type") == "concept" and isinstance(p.get("slug"), str):
        E.add(p["slug"])
  numerator   += | D ∩ E |
  denominator += | D ∪ E |

rate = numerator / denominator   (0.0 if denominator == 0 — see § 4 zero-denom row)
```

Per-source contribution `(0, 0)` when both `D` and `E` are empty does not affect the rate. The coercion guard (Round 4 CW2) protects against `concept_slugs` being something other than `list[str]` — `set("foo")` would otherwise produce `{"f", "o"}`.

**Zero-denominator policy** (Round 4 MF6): a model emitting zero concept_slugs AND zero concept-typed pages across the corpus scores M2 = 0.0 (model-controlled denominator → abstention penalized).

#### M3 — `article_slugs_coverage` (weight 5%, Quality Core, Jaccard)

Identical to M2 with `concept_slugs` → `article_slugs` and `"concept"` → `"article"`. Same CW2 coercion guard, same MF6 zero-denominator policy (= 0.0 if a model emits no article structure).

#### M4 — `semantic_pass_rate` (weight 15%, Output Integrity)

```
numerator   = |{ r ∈ R : r.semantic_ok }|
denominator = |R|
```

`semantic_ok` is False whenever `parse_ok` is False (by `compile_one`'s state initialization at `compiler.py:168`), so M4 naturally captures parse failures without a separate clause. M4's 15% weight already absorbs the four semantic-contract rules enforced by `validate_compiled_source_response.semantic_check`.

#### M5 — `body_link_syntax_match` (weight 5%, Output Integrity, symmetric Jaccard)

```
numerator   = Σ_{r ∈ R} r.body_link_intersection
denominator = Σ_{r ∈ R} r.body_link_union

rate = numerator / denominator   (0.0 if denominator == 0 — see § 4 zero-denom row)
```

Both fields are always-on (Task #28, commit `0bcc2b6`). They default to 0 when `parse_ok=False`, so failed sources contribute `(0, 0)` naturally.

**Zero-denominator policy** (Round 4 MF6): a model emitting zero declared outgoing_links AND zero body wikilinks across the corpus scores M5 = 0.0 (model-controlled denominator → abstention penalized).

#### M6 — `cost_per_1k_source_words` (weight 15%, Production Cost; raw $ rate, lower-is-better)

```
Look up (price_in, price_out) from load_registry() by model_id.

numerator   = 0.0
denominator = 0
for r in R where r.source_words > 0:                  # parse_ok IRRELEVANT — failed calls bill too
  cost_usd_i  = (r.input_tokens × price_in + r.output_tokens × price_out) / 1_000_000
  numerator   += cost_usd_i
  denominator += r.source_words

rate = (numerator / denominator) × 1000   (raw $ / 1K source-words)
       (None iff denominator == 0 — corpus-controlled, redistributed pro-rata in § 8)
```

**Round 4 MF1 clarification:** the filter is `source_words > 0`, **not** `parse_ok=True`. Truncation, extract failure, parse failure, schema failure, semantic failure — all happen *after* the model call (`compiler.py:203-321`); their token costs are economically real and should bill. The earlier "exclude parse-failed from M6/M7" rule was wrong (and contradicted the rationale column of the same edge-case table).

Local/Ollama models have `price_in = price_out = 0.0` (Task #29 schema lock) so `cost_usd_i = 0` for them by construction — no special-casing needed in the scorer.

The raw rate is preserved here per Q2's resolution. Cross-model rank-normalization happens at scorecard time via average-rank Borda (§ 7).

**Zero-denominator policy** (Round 4 MF6): M6's denominator is **corpus-controlled** (every benchmark source has source_words > 0 by construction). Zero-denom is a degenerate empty/invalid-corpus pathology only — `rate = None` and the M6 weight redistributes pro-rata (§ 8). NOT the model-controlled abstention case.

#### M7 — `latency_per_1k_source_words` (weight 15%, Production Cost; raw ms rate, lower-is-better)

```
numerator   = 0
denominator = 0
for r in R where r.source_words > 0:                  # parse_ok IRRELEVANT — failed calls take time too
  numerator   += r.latency_ms
  denominator += r.source_words

rate = (numerator / denominator) × 1000   (raw ms / 1K source-words)
       (None iff denominator == 0 — corpus-controlled, redistributed pro-rata in § 8)
```

Same rationale as M6: failed calls still take wall-clock time (`r.latency_ms` is set by `call_model_with_retry`), so they belong in the latency-per-1K-source-words rate. Same corpus-controlled MF6 zero-denom policy.

#### Diagnostic — `retry_load` (weight 0)

```
numerator   = Σ_{r ∈ R} min(MAX_RETRIES, max(0, r.attempts − 1))
denominator = |R| × MAX_RETRIES         # MAX_RETRIES from kdb_compiler.call_model_retry

rate = numerator / denominator   (None iff |R| == 0; bounded [0.0, 1.0] always)
```

Cap-normalized — fraction of the maximum possible retry budget the run actually consumed. Sources with `attempts = 0` (pre-call failures, no model_response set) clamp to 0 (floor); sources where production code overrides `max_attempts > MAX_RETRIES + 1` (research mode) clamp at `MAX_RETRIES` (ceiling). **Round 4 MF8 fix** — without the upper clamp, an overridden `max_attempts` could push the diagnostic above 1.0, breaking the cap-normalized contract.

#### Diagnostic — `token_overrun_rate` (weight 0)

```
numerator   = |{ r ∈ R : r.token_overrun }|
denominator = |R|
```

`token_overrun` is the boolean from Task #29 telemetry plumbing (`stop_reason in {"max_tokens", "length"}`).

#### Diagnostic — `pages_per_1k_source_words` (weight 0)

```
For each r ∈ R where r.source_words > 0:
  pages_i      = r.parsed_summary.page_count if r.parse_ok else 0
  numerator   += pages_i
  denominator += r.source_words

rate = (numerator / denominator) × 1000   (pages / 1K source-words)
       (None iff denominator == 0)
```

Surfaces fragmentation tendency without scoring it. `parsed_summary.page_count` is always present when `parse_ok=True` (resp_stats_writer always builds it on parse-pass).

### 7. Average-rank normalization (M6, M7)

**Round 4 rename (MF5):** previously called "Borda rank-normalization, dense rank with averaging." The algorithm we actually run is **fractional rank** (a.k.a. average-rank): tied candidates share the average of their tied ordinal positions. Dense rank, standard competition rank, and modified competition rank are all distinct schemes that this algorithm is NOT. The function name `borda_normalize` is preserved for continuity but the algorithm-name in prose is now honest.

```python
def borda_normalize(
    runs: list[RunScore],
    measure: str,                # "M6" or "M7"
    *,
    lower_is_better: bool,
) -> dict[str, float]:
    """
    Returns {model_id → normalized score in [0, 1]}.

    Algorithm (fractional rank / average-rank):
      1. Drop any RunScore where measures[measure].rate is None
         (no data on this measure → no Borda value; that model gets
         no entry in the returned dict).
      2. Sort the remaining N runs by raw rate
         (ascending if lower_is_better else descending).
      3. Assign FRACTIONAL RANKS — for each candidate, its rank is
         the AVERAGE of the consecutive ordinal positions it shares
         with any tied peers (e.g., 3 candidates tied at sorted
         positions 1, 2, 3 → all three get rank (1+2+3)/3 = 2.0).
      4. Convert rank → score:
            score = (N − rank) / (N − 1)            if N ≥ 2
            score = 1.0                              if N == 1
            score = 0.5  (every candidate)           if all rates equal       <-- all-equal policy
         Strict best gets 1.0; strict worst gets 0.0; ties share the
         interior value implied by their averaged rank. When *every*
         rate is equal the all-equal-candidates policy returns 0.5
         for every candidate (no signal in this dimension).
    """
```

**Tie-handling worked example (5 candidates, lower-is-better, raw rates `[0.001, 0.001, 0.002, 0.005, 0.005]`):**

| Candidate | Raw rate | Sorted ordinal positions | Fractional rank | Borda score |
|---|---|---|---|---|
| A | 0.001 | tied at 1st & 2nd | (1+2)/2 = 1.5 | (5−1.5)/4 = **0.875** |
| B | 0.001 | tied at 1st & 2nd | 1.5 | **0.875** |
| C | 0.002 | 3rd | 3 | (5−3)/4 = **0.5** |
| D | 0.005 | tied at 4th & 5th | (4+5)/2 = 4.5 | (5−4.5)/4 = **0.125** |
| E | 0.005 | tied at 4th & 5th | 4.5 | **0.125** |

Strict best (no tie at top) would get 1.0; strict worst (no tie at bottom) would get 0.0. Here both extremes are tied, so the shared scores are interior (0.875 and 0.125 respectively) — by design. The "best gets 1.0, worst gets 0.0" prose holds for *strict* extremes only; tied extremes share the average-rank value, which is interior. **Round 4 MF5 fix** — earlier draft prose oversimplified to "best gets 1.0; worst gets 0.0" without qualifying for tied extremes.

**All-equal policy (Round 4 MF5):** if every candidate has the same raw rate, the algorithm returns 0.5 for every candidate (no signal). Mathematically the natural behavior of fractional rank — when all N candidates tie at positions 1..N, each gets rank `(N+1)/2`, and `(N − (N+1)/2) / (N − 1)` simplifies to `0.5`.

**Codex review #6 reckoning** (carried forward from Round 3, still applies):
- *Candidate-set dependence* — adding/removing a candidate shifts other scores. **Defused** by user workflow ("rank latest, pick best", no cross-version compare).
- *Magnitude erasure* — rank treats $0.001 → $0.002 (2×) and $0.002 → $0.100 (50×) as adjacent steps. **Acknowledged but accepted** under same workflow logic; raw rates remain visible in the scorecard for human magnitude inspection.
- *Tie handling undefined* — **resolved here** as fractional rank (average ordinal) with explicit all-equal policy.

### 8. Final-score formula (post-Borda)

For each `RunScore` after average-rank normalization of M6 and M7:

```python
components = [
    ("S0", 0.20, run.s0.rate),                        # always present (rate is 0.0/[0,1] never None for non-empty R)
    ("M1", 0.20, run.measures["M1"].rate),            # 0.0 on model-controlled zero-denom (MF6) — never None
    ("M2", 0.05, run.measures["M2"].rate),            # 0.0 on model-controlled zero-denom (MF6)
    ("M3", 0.05, run.measures["M3"].rate),            # 0.0 on model-controlled zero-denom (MF6)
    ("M4", 0.15, run.measures["M4"].rate),            # always present (binary over corpus N)
    ("M5", 0.05, run.measures["M5"].rate),            # 0.0 on model-controlled zero-denom (MF6)
    ("M6", 0.15, run.m6_borda),                       # None iff M6 corpus-controlled zero-denom — pro-rata redistributes
    ("M7", 0.15, run.m7_borda),                       # None iff M7 corpus-controlled zero-denom — pro-rata redistributes
]

score_sum       = 0.0
present_weights = 0.0
for _, weight, rate in components:
    if rate is not None:
        score_sum       += weight * rate
        present_weights += weight

if present_weights == 0:
    raise ValueError("degenerate run: every scored component is None")

final_score = score_sum / present_weights   # always in [0, 1]
```

**Round 4 split-policy mechanics (MF6):**

- **S0/M1/M2/M3/M5** (model-controlled denominator) never become `None` due to model abstention — they score `0.0` and stay weighted. Pro-rata redistribution does NOT save a model that produces no structure.
- **M6/M7** (corpus-controlled denominator) become `None` only if the entire corpus has `source_words = 0` everywhere — a corpus-curation pathology, not a model behavior. Their weight redistributes pro-rata to the model-controlled measures and S0.
- When all 8 components are present, `present_weights == 1.0` and `final_score` is the simple weighted sum. When M6 or M7 is `None` (corpus pathology), the remaining weights renormalize so `final_score` stays in `[0, 1]`. If every component is `None` (every measure missing — degenerate corpus), `score_runs` raises rather than producing a meaningless score.

**Worth naming explicitly** (Round 4 design-call carried forward): this benchmark assumes the corpus contains opportunities for each scored dimension. If a future corpus is intentionally constructed without (say) any reason to emit outgoing links, M1's "0.0 on zero-denom" rule will mis-score model behavior; that scenario will need a corpus-aware policy. v1 chooses simplicity over corpus introspection.

### 9. Function signatures

```python
from pathlib import Path
from kdb_benchmark.paths import MODELS_JSON
from kdb_benchmark.registry import ModelEntry


def score_run(
    state_root: Path,
    run_id: str,
    model_id: str,                              # ModelEntry.id — stable scorecard key
    *,
    registry_path: Path = MODELS_JSON,
) -> RunScore:
    """Single-model entry point.

    Identity contract (Round 4 DC2): the scorer is parameterized by
    `model_id` (ModelEntry.id), not by raw (provider, model). The scorer
    looks up the matching ModelEntry in the registry, derives the
    expected (provider, model) for billing-and-filter purposes, and
    reads every RespStatsRecord JSON file under
    <state_root>/llm_resp/<run_id>/. Each record's persisted
    (provider, model) — including pre-response-failure records, which
    now carry the requested values per Round 4 MF2 — must match the
    expected (provider, model); otherwise ValueError.

    The runner contract is **one run_id per ModelEntry.id** — if a single
    benchmark run spans multiple models, each gets its own run_id. The
    scorer enforces this by raising on any provider/model mismatch.

    Returns: RunScore with raw rates (M6/M7 are raw $ / ms per 1K source
    words). `m6_borda`, `m7_borda`, and `final_score` are all None on
    the returned object — populated only by score_runs() across peers.

    Raises:
      ValueError    — no records match (run_id) in this state_root
      ValueError    — duplicate (run_id, source_id) records found
      ValueError    — record's (provider, model) doesn't match the
                      ModelEntry derived from `model_id`
      ValueError    — `model_id` not present in the registry
      RuntimeError  — capture-full mode required (parse_ok=True records
                      found with parsed_json=None)
    """


def score_runs(runs: list[RunScore]) -> list[RunScore]:
    """Cross-model enrichment. Runs average-rank normalization on M6 and
    M7 across the given runs, computes final_score for each, returns a
    NEW list of RunScore objects with `m6_borda`, `m7_borda`, and
    `final_score` populated. Raw `measures["M6"]` and `measures["M7"]`
    rates are preserved unchanged on every returned RunScore — the
    Borda values live in the dedicated `m6_borda` / `m7_borda` fields
    so MeasureScore stays unit-stable (Round 4 MF7).

    Original `runs` list is not mutated.

    Raises ValueError if `runs` is empty or if every component on every
    run is None (degenerate corpus / impossible scoring)."""


def borda_normalize(
    runs: list[RunScore],
    measure: str,
    *,
    lower_is_better: bool,
) -> dict[str, float]:
    """See § 7. Returns {model_id → normalized score in [0, 1]}.
    Public for testability and future scorecard reuse."""
```

**Loader contract (Round 4 DC3):** `score_run()` reads the raw JSON files via dict access. `RespStatsRecord` is reconstructed only as far as needed for the scorer's contract — at minimum, fields `run_id`, `source_id`, `provider`, `model`, `attempts`, `latency_ms`, `input_tokens`, `output_tokens`, `parse_ok`, `schema_ok`, `semantic_ok`, `parsed_json`, `parsed_summary`, `source_words`, `body_link_intersection`, `body_link_union`, `stop_reason`, `token_overrun` are required. Missing fields raise `ValueError`. The scorer uses dict access internally; the §6 pseudocode notation `r.attempts` etc. is shorthand for `record_dict["attempts"]`. (Round 4 doesn't mandate full dataclass reconstruction — that's a scorer-impl-task choice; the input contract is dict-shaped JSON.)

### 10. Housekeeping changes folded into the Phase 3 + Round 4 commits

Three Phase 3 refactors landed in commit (a) so the future scorer-impl task can import what it needs without re-touching `kdb_compiler` for ergonomic reasons; one Round 4 telemetry fix landed in commit (b) so the scorer's filter contract holds for pre-response failures:

1. **`MAX_RETRIES = 2` exported from `kdb_compiler/call_model_retry.py`** (Phase 3). The function default `max_attempts=MAX_RETRIES + 1` so behavior is unchanged. `retry_load` cap derivation now imports the constant rather than re-deriving from the function default.

2. **`check_compiled_source(parsed_json) -> list[str]` added to `kdb_compiler/validate_compile_result.py`** (Phase 3). A thin wrapper around the existing private `_check_source` that returns just the list of HARD-ZERO finding type strings (filtered against `HARD_ZERO_FINDING_TYPES`, also exposed). The existing `_check_source` API (in-place mutation of `ValidationResult`) is preserved for `validate()`'s use; the wrapper exists because the scorer needs a clean list-of-strings contract, not a result object to inspect. Measure-severity findings (`pairing_commission`, `pairing_omission`) are intentionally excluded by the wrapper — they are reconcilable, not hard-zero.

3. **Round 4 MF2 telemetry fix.** `build_resp_stats` in `kdb_compiler/resp_stats_writer.py` gained optional `provider`/`model` keyword arguments (defaulting to `""` for backward compatibility) and uses them as fallback when `model_response is None`. `compile_one` now passes the requested `provider`/`model` to `build_resp_stats` so pre-response failures (source-read fail, prompt-build fail, model-call fail) persist the **requested** provider/model on `RespStatsRecord` — not empty strings. Without this fix, those records would vanish from the scorer's `(provider, model)` filter and skew S0/S1/M4 denominators.

4. **CW1 tests added** (Round 4). Three small targeted tests cover the new exports and the MF2 fallback: `MAX_RETRIES == 2`, `HARD_ZERO_FINDING_TYPES` set membership, `check_compiled_source` clean-vs-hard-zero behavior, and `check_compiled_source` filtering of measure-severity findings (no `pairing_commission` leakage). Plus `build_resp_stats` correctly persisting the requested provider/model on pre-response failures and preferring `model_response`-derived values when present.

**Stub at `kdb_compiler/validate_compile_result.score_response`** (returns None) is **NOT** removed in either commit. It is load-bearing-zero — called from `kdb_compiler/kdb_compile.py:314` and its None result is written into the run journal as `response_score`. Removing it would cascade into journal consumers and is out of Phase 3 / Round 4 scope. Marked for removal at Phase 5 (CODEBASE_OVERVIEW promotion) or with the future scorer-impl task, whichever lands first.

### 11. Out of scope for Phase 3 (deferred)

| Concern | Owner |
|---|---|
| Implementation of `kdb_benchmark/scorer.py` itself (the actual code) | Future scorer-impl task |
| Unit tests per measure + integration test against a fixture corpus | Same task |
| Scorecard rendering — column order, JSON shape, terminal pretty-print | Task #22 |
| Multi-run aggregation (averaging scores across N runs of the same model) | Future runner task |
| Weight-perturbation sensitivity analysis (the v2-trigger condition from the Weight Philosophy section) | Outside the static scorer; deferred until first benchmark spreads land |
| Ground-truth-anchored evaluation (semantic correctness, hallucinations, near-duplicate slugs) | Task #20 |
| Removing the dead `score_response` stub | Phase 5 / scorer-impl task |
| Scorecard versioning (`scorecard_version` / `pricing_version`) | **NOT planned** per locked Round 3 decision; user workflow has no cross-version compare |
| **Comparability disclaimer in scorecard output** (Round 4 DC4) | **Task #22 is responsible for emitting one.** The scorecard format must include explicit text that *final_score is comparable only within the candidate set emitted in the same scorecard*; raw rates remain the cross-run inspection surface. Without this disclaimer, the average-rank candidate-set dependence will be misread as historical comparability. Phase 3 spec calls it out here so #22 can't drop it. |
| **Corpus-aware zero-denominator policy** (Round 4 MF6 design-call) | Future task / Task #20 territory. v1 chose simplicity: M1/M2/M3/M5 zero-denominator scores 0.0 (assumes corpus has opportunity for each dimension). If a future corpus is intentionally constructed without (say) any reason to emit outgoing links, M1's "0.0 on zero-denom" rule will mis-score model behavior. That scenario will need a corpus-aware policy. |

### 12. Phase 5 trigger conditions

This spec graduates to `docs/CODEBASE_OVERVIEW.md` once **all** of the following hold:

1. The future scorer-impl task lands a working `kdb_benchmark/scorer.py` matching the contract in § 9.
2. Unit tests covering each measure's edge-case policies from § 4 are green.
3. At least one real benchmark run produces a `RunScore` that survives manual inspection — the rates are within plausible ranges and the diagnostic fields agree with raw `RespStatsRecord` counts.

At that point Phase 5:
- Promotes the *architecture* (the locked weights, the bucket structure, the input-contract / boundary rules) into the North Star doc.
- Leaves the *spec mechanics* (the Phase 3 + Round 4 sections above) here as historical record.
- Removes the dead `score_response` stub and its test.
- Closes Task #19 in `docs/TASKS.md` with a pointer back to this file.

---

## Round 4 Corrections (locked 2026-05-06)

**Trigger:** `task19-kpi-design-codex-feedback-take-2.md` — adversarial review of the Phase 3 spec landed earlier the same day. Review surfaced 8 must-fixes, 4 design-calls, 4 cheap-wins, and 3 defensible findings. All 8 must-fixes accepted; all 4 design-calls accepted with simple-policy leans (model_id-as-identity, dict-access loader, comparability disclaimer, S0 rename); all 4 cheap-wins folded in.

**Outcome:** Phase 3 spec amended in-place above; this section is the change-log.

### Round 4 corrections delta from Phase 3 take-1

| ID (codex) | Issue | Fix landed in §… | Code change? |
|---|---|---|---|
| **MF1** | Edge-case table claimed "exclude parse-fail from M6/M7" while rationale + §6 pseudocode included via `source_words > 0`. Self-contradiction. | §4 row rewritten — failed calls bill cost/latency naturally; `source_words > 0` is the right gate. §6 M6/M7 pseudocode + prose clarified. | Doc only |
| **MF2** | Pre-response failures persisted `provider=""`/`model=""` on `RespStatsRecord` → vanished from scorer's `(provider, model)` filter, skewing S0/S1/M4 denominators. | §4 new row "provider/model field on pre-response failures." §10 housekeeping point 3. | **Code:** `resp_stats_writer.py` + `compile_one` — `build_resp_stats` accepts requested provider/model as fallback when `model_response is None`. |
| **MF3** | Three Round-3-era spec lines claimed `cost_usd` is persisted on `RespStatsRecord` — false (Option ε from 05-05 deliberately drops the field; scorer derives at score time). | Lines 207, 240, 435 (early-section text) rewritten to match Option ε. | Doc only |
| **MF4** | `parse_ok=True` only proves JSON parsed; non-dict `parsed_json` (a list, scalar, null) crashed M1/M2/M3/S3. | §4 new row "Source with `parse_ok=True` but non-dict `parsed_json`." §6 notation block adds `R_p` definition with `isinstance(parsed_json, dict)` guard. Pseudocode for M1/M2/M3 explicitly guards every dereference. | Doc only (scorer-impl task implements) |
| **MF5** | Borda algorithm called "dense rank with averaging" but worked example showed *fractional rank* (average ordinal). All-equal-candidates case was undefined. Tied-worst case got an interior score, contradicting "worst gets 0.0" prose. | §7 retitled "Average-rank normalization." Algorithm renamed; worked example annotation reworded; all-equal policy added (every candidate gets 0.5); tied-extremes prose qualified. | Doc only |
| **MF6** | Zero-denominator redistribution rewarded link abstention — a model emitting zero outgoing_links could remove M1 from final score via pro-rata. | §4 row split — model-controlled denominators (M1/M2/M3/M5) score 0.0 on zero-denom (penalty); corpus-controlled (M6/M7 source_words) stay None for empty-corpus pathologies (pro-rata). §6 per-measure prose updated. §8 final-score formula updated. §11 adds "corpus-aware policy" deferral. | Doc only |
| **MF7** | `score_runs()` proposed replacing `MeasureScore.rate` with normalized [0,1] values, leaving raw `(numerator, denominator)` paired with a unit-different rate. Inconsistent shape. | §5 RunScore gains separate `m6_borda` / `m7_borda` fields. MeasureScore stays unit-stable and immutable. §9 score_runs contract clarified. §8 final-score reads `run.m6_borda` / `run.m7_borda`. | Doc only |
| **MF8** | `retry_load` could exceed 1.0 if `call_model_with_retry` was invoked with `max_attempts > MAX_RETRIES + 1` (research/override). | §4 retry-corner-cases row + §6 retry_load formula clamped: `min(MAX_RETRIES, max(0, attempts − 1))`. Bounded [0, 1]. | Doc only |
| **DC1** | S0 named `end_to_end_success_rate` but excluded `semantic_ok` (locked Round 3 formula = S1 ∧ S2 ∧ S3). Production semantics is strictly stronger. | S0 renamed `pipeline_success_rate` everywhere in §6 + notation. Locked formula preserved (no Round 3 reopening). | Doc only |
| **DC2** | Scoring by `(provider, model)` ignored ModelEntry's stable `id`; load_registry doesn't enforce `(provider, model)` uniqueness. | §9 score_run signature changed to take `model_id`. Scorer derives (provider, model) from registry lookup. RunScore gains `model_id` field (§5). One-run-per-model_id runner contract documented. | Doc only |
| **DC3** | JSON loader shape underspecified (dataclass reconstruction vs dict access). | §9 loader contract: dict access; required field list explicit. §6 pseudocode `r.field` is shorthand for `record_dict["field"]`. | Doc only |
| **DC4** | Scorecard candidate-set dependence not explicitly disclaimed in scorecard output. | §11 row added — Task #22's scorecard format MUST include "comparable only within candidate set" disclaimer. | Doc only (Task #22 implements) |
| **CW1** | New exports (MAX_RETRIES, HARD_ZERO_FINDING_TYPES, check_compiled_source) had no dedicated tests. | §10 housekeeping point 4. | **Tests:** 7 new tests in `test_call_model_retry.py`, `test_validate_compile_result.py`, `test_resp_stats_writer.py` |
| **CW2** | M2/M3 slug-list coercion: `set("foo")` produces char-slugs if `concept_slugs` is a string. | §4 row added. §6 M2 pseudocode coerces non-list to empty set. | Doc only |
| **CW3** | M1 duplicate outgoing-link semantics undefined. | §4 row added — list semantics for M1 (matches on-disk shape). §6 M1 pseudocode loops with explicit list semantics. | Doc only |
| **CW4** | Old Phase 2 status text close to live status text — easy to misread. | "Superseded by Round 3 / Phase 3 / Round 4 below" callout added to top of *Phase 2 — Status & remaining work*. | Doc only |
| **Defensible #1, #2, #3** | M2/M3 Jaccard works; within-source vs cross-source duplicate semantics are separable; partial capture-full runs fail loud — codex agrees. | No change. | — |
| **Continuity item: candidate-set comparability** | Acknowledged but accepted under user's "rank latest" workflow, with the now-required scorecard disclaimer (DC4) making this honest. | §11 row + §7 reckoning. | — |

### Round 4 commit shape

Single bundled commit:
- This doc (`docs/task19-kpi-design.md`) — ~150 net-new lines; in-place fixes throughout.
- `kdb_compiler/resp_stats_writer.py` — MF2 fallback (~6 lines).
- `kdb_compiler/compiler.py` — MF2 call-site update (1 line).
- `kdb_compiler/tests/test_resp_stats_writer.py` — 2 new tests (MF2 fallback + override).
- `kdb_compiler/tests/test_validate_compile_result.py` — 4 new tests (CW1).
- `kdb_compiler/tests/test_call_model_retry.py` — 1 new test (CW1).
- `docs/TASKS.md` — Task #19 row notes updated.

**Tests baseline post-commit:** 462 passed / 1 skipped (was 455 / 1 skipped after Phase 3; +7 new tests).

### Open after Round 4 (still unresolved by design)

- **Corpus-aware zero-denominator policy** — v1 chose simplicity (M1/M2/M3/M5 zero-denom = 0.0 penalty). If a future corpus is intentionally zero-opportunity for any dimension, that policy will need refinement. Tracked in §11 Out-of-Scope. (Design-call accepted in v1, deferred for v2.)
- **`score_response` stub removal** — still load-bearing-zero in `kdb_compile.py:314`; planned for Phase 5 / scorer-impl future task.
- **Comparability disclaimer text** — Phase 3 spec says Task #22 must emit one in the scorecard format; the literal disclaimer wording lives in Task #22's design.

This subsection is the **final amendment** to the Phase 3 spec ahead of Phase 5 promotion. If take-3 review surfaces further must-fixes, a Round 5 subsection follows the same shape; otherwise the next milestone is the scorer-impl future task implementing § 5–§ 9.
