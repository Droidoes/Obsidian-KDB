# Task #19 — KDB Benchmark KPI Design

**Status:** Phase 2 + **Round 3** (Codex-driven corrections) **CLOSED** 2026-05-04 — page-spam exploit closed, formulas hardened, M5/telemetry implementation tracked as Task #28 / #29 → ready for Phase 3 (detailed spec) once #28 + #29 land
**Date:** 2026-04-30 (Phase 1 landed; Phase 2 Tier 2 Quality Core restructured same day) → 2026-05-02 (Phase 2 Tier 2 Output/Cost/Efficiency walkthrough complete; 11 → 9 measures) → 2026-05-03 (Phase 2 closed: Q2/Q4/Q5/Q6 resolved, intra-bucket weights allocated) → 2026-05-04 (Round 3: Codex hostile review surfaced M6/M7 page-spam exploit, M2/M3 math defects, M5 versioning ambiguity, doc contradictions; corrections landed — source-words denominator, Jaccard formulas, M5 symmetric + impl-first, M8/M9 demoted to diagnostic-only, weights re-allocated S0=20 / Quality=30 / Integrity=20 / Cost=30 / Efficiency=0)
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
- **`scorecard_version` and `pricing_version` explicitly NOT added.** Per user's "rank latest, pick best" workflow — no cross-version comparison plan, so Codex's candidate-set-dependence critique is defused. Cost is computed at run time and persisted as `cost_usd` (no re-derivation). Versioning ceremony has no payoff for this single-user, infrequent workload (per `feedback_no_imaginary_risk`).

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
| **M6** | `cost_per_1k_source_words` | Total LLM cost per 1K source words — input + output billing combined, normalized to a model-independent denominator. Captures the full economic dimension. | `(Σ resp_stats.cost_usd_i ÷ Σ source_words_i) × 1000`, where `cost_usd_i = (input_tokens_i × price_in + output_tokens_i × price_out) / 1_000_000` computed at call time using `kdb_benchmark/models.json` (the per-model `price_in` / `price_out` registry). `cost_usd` is persisted in `RespStatsRecord` (Task #29). | **15%** |
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
- ✅ **Telemetry plumbing tracked as Task #29** — extend `RespStatsRecord` with `cost_usd`, `stop_reason`, `token_overrun`; surface per-source `source_words` from corpus metadata.
- ✅ **`scorecard_version` / `pricing_version` explicitly NOT added** — user's "rank latest, pick best" workflow has no cross-version compare plan; cost computed and frozen at run time.
- ✅ **Doc contradictions resolved:** D2 dropped "Tier 2 diagnostic measure" wording; D3 + D5 clarified `RespStatsRecord` as scorer authority (not `compile_result`); Q4 closing language scoped honestly to "deterministic structural telemetry."
- ✅ **Codex review #6 (Borda pathologies) reckoned with:** candidate-set dependence defused by user workflow; magnitude erasure acknowledged but accepted; tie handling deferred to Phase 3 spec.
- ✅ **Codex review #12 (D1 blind spot) acknowledged:** Q4 resolution now states the benchmark cannot detect semantic-correctness failures (hallucinations, wrong definitions, near-duplicates) under D1 without ground truth. Task #20 territory.

**Round 3 → Phase 3 Pivot.** Phase 3 is gated on **Task #28 (M5 implementation)** and **Task #29 (telemetry plumbing)** landing first. Once those complete, Phase 3 will:

1. Convert the locked design into code-ready spec — exact computation formulas with function signatures and expected input/output shapes for the future benchmark scorer module.
2. Define edge cases per measure: zero-denominator policy (M1, M2, M3, M5, M6, M7 — all need explicit handling for empty sets / no-link sources / all-failed corpus), tie handling for Borda normalization, missing-telemetry handling (older models without `cost_usd`).
3. Land the result as a single commit; this doc becomes the source-of-truth blueprint.

Phase 5 will then move the agreed architecture into `docs/CODEBASE_OVERVIEW.md` and close Task #19 in `docs/TASKS.md` with a pointer back to this file as the historical design record.
