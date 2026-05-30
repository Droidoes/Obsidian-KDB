# Task #19 KPI Design — Codex Hostile Review Take 1

**Date:** 2026-05-04  
**Target:** [`task19-kpi-design.md`](task19-kpi-design.md)  
**Review posture:** senior staff engineer blocking review before Phase 3 code-spec freeze.

## Executive Verdict

I would block Phase 3 freeze.

The design is directionally coherent, but it is still gameable and not code-ready. The largest problems are:

- Some metrics are not computable from current artifacts.
- Cost/latency per page can reward bad production behavior.
- Rank-based normalization makes scores candidate-set-dependent.
- M5's conditional weight rollover creates score-version ambiguity.
- Multiple denominator and zero-case rules are still undefined.
- The benchmark cannot detect valid-but-wrong content under D1, and the doc should name that as a known blind spot rather than treating the KPI set as complete.

## Blocking Findings

### 1. `cost_per_page_per_run` is not computable from current artifacts

`docs/task19-kpi-design.md` defines:

```text
M6 = Σ resp_stats.cost_usd_i ÷ Σ pages_produced_i
```

Current `RespStatsRecord` has tokens, latency, attempts, provider, and model, but no `cost_usd`, no pricing table version, and no persisted inference of token price.

Concrete failure scenario:

- A benchmark run is scored two months later.
- Provider prices changed in the interim.
- The scorer recomputes cost from current `models.json` or current provider pricing.
- The same raw run now scores differently.

Phase 3 must define either:

- Persist `cost_usd` at run time, plus `pricing_version`.
- Or persist enough token fields and pin a versioned pricing table used by the scorer.

Without that, M6 is not reproducible.

### 2. `token_overrun_rate` is not computable from current artifacts

`M9` is defined as:

```text
Σ (1 if stop_reason_i == "max_tokens" else 0) ÷ N
```

But current `RespStatsRecord` does not persist `stop_reason`.

The compiler detects truncation via:

```python
if sr in ("max_tokens", "length"):
```

but that value is not written into the response-stats artifact.

Additional ambiguity:

- Anthropic uses `max_tokens`.
- OpenAI-compatible providers may use `length`.
- Other providers may use different stop-reason strings.

Phase 3 must define canonical overrun detection:

```text
token_overrun = stop_reason in {"max_tokens", "length", ...}
```

and persist raw `stop_reason` plus normalized `token_overrun`.

### 3. Cost/latency per page is gameable

`M6` and `M7` divide by `pages_produced`.

A model can improve both metrics by producing more pages, even if those pages are low-value, fragmented, or harmful to the KDB.

Concrete adversarial model:

- Emits valid JSON.
- Always emits one summary.
- Emits many tiny concept/article pages.
- Keeps `concept_slugs[]` and `article_slugs[]` perfectly synchronized.
- Links only to pages it just emitted, so M1 is high.
- Embeds every declared link in the body, so M5 is high.
- Never semantically reuses existing context.
- Fragments concepts into near-duplicates.

Expected score:

- High S0.
- High M1/M2/M3/M4/M5.
- Artificially good M6/M7 because denominator is inflated.
- Bad production outcome because the vault accumulates noisy, fragmented pages.

This is the biggest blind spot. Dropping `page_count_sanity` was defensible because it lacked ground truth, but then using page count as the denominator for cost and latency creates a reward for page inflation.

Preferred Phase 3 correction:

```text
cost_per_successful_source = Σ cost_usd_i ÷ successful_source_count
latency_per_successful_source = Σ latency_ms_i ÷ successful_source_count
```

Keep cost/page and latency/page as diagnostics only unless page utility is measured.

### 4. M1/M5 denominator exclusion creates link-abstinence gaming

M1:

```text
Σ resolved_outgoing_links_i ÷ Σ total_outgoing_links_i
over sources where total_outgoing_links_i > 0
```

M5:

```text
Σ body_link_matches_i ÷ Σ declared_outgoing_links_i
over sources where declared_outgoing_links_i > 0
```

If a model emits zero outgoing links, it can avoid both measures depending on how the scorer handles empty denominators.

Concrete failure scenario:

- Model emits summary + pages with no `outgoing_links`.
- It avoids unresolved links.
- It avoids body-link mismatch.
- It may still pass S0/M2/M3/M4.
- The KDB does not compound because pages are isolated.

Phase 3 must define zero-denominator behavior.

My default:

```text
If the model emits no evaluated structure and the corpus had any opportunity to emit it, score 0 for that metric.
```

If that feels too punitive, the design needs an explicit `link_production_rate` or minimum-link opportunity metric. Otherwise abstention is rewarded.

### 5. M2/M3 can go undefined or negative

Current M2:

```text
1 − (Σ concept_commission_i + Σ concept_omission_i) ÷ Σ final_concept_page_count_i
```

Problems:

- If `final_concept_page_count == 0`, division is undefined.
- If commissions exceed final count, score can go negative.
- "final = post-reconciliation" makes the denominator dependent on the repair process, not the model output.

Concrete failure scenario:

```text
concept_slugs = ["a", "b", "c", "d", "e"]
pages = []
final_concept_page_count = 0
concept_commission = 5
```

The formula is undefined.

Better formula:

```text
declared = set(concept_slugs)
emitted = set(page.slug for page in pages if page_type == "concept")
denominator = |declared ∪ emitted|
mismatches = |declared Δ emitted|
score = 1 - mismatches / denominator
```

Then define:

```text
if denominator == 0:
    score = corpus_opportunity_policy
```

This is symmetric, bounded, and does not depend on post-reconciliation state.

### 6. Rank-based Borda normalization breaks historical comparability

Q2 chooses Borda-style rank normalization for cost and latency.

Problem A: adding/removing a candidate shifts existing scores.

Example with cost, lower is better:

```text
Run A candidates: A=$0.001, B=$0.010, C=$0.100
B rank score among 3 = middle

Run B candidates: A=$0.001, B=$0.010, C=$0.100, D=$0.011
B rank score changes because D was added.
```

Model B did not change. Its score changed anyway.

Problem B: rank erases magnitude.

Example:

```text
A = $0.001/page
B = $0.002/page
C = $0.100/page
```

Rank treats A-to-B and B-to-C as adjacent steps, even though B-to-C is 50x.

Problem C: ties are undefined.

Phase 3 must define:

- Dense rank vs competition rank vs average rank.
- What happens when all candidates tie.
- What happens when cheapest or fastest has missing/undefined raw value.

Preferred mechanism:

```text
score = weight * (log(max_value) - log(value)) / (log(max_value) - log(min_value))
```

with explicit handling:

```text
if all values equal: all get full score or neutral score, chosen explicitly
if value <= 0: invalid for log-scale; define floor or error
```

Log-scale preserves order-of-magnitude economics while still avoiding absolute thresholds.

### 7. M5 conditional weight rollover creates score-version ambiguity

Current rule:

```text
M5 carries 6%; if M5 does not land before first benchmark run, its 6% rolls into M4.
```

This creates two incompatible score formulas:

```text
scorecard_v1a: M4=20, M5=0
scorecard_v1b: M4=14, M5=6
```

Same raw run, different score depending on scorer implementation date.

Cleaner options:

Option A:

```text
M5 = 0 until implemented; M4 = 20 for scorecard_v1.
M5 can only be introduced in scorecard_v2.
```

Option B:

```text
Hold the first official benchmark run until M5 lands.
Freeze scorecard_v1 as M4=14, M5=6.
```

I prefer Option A if monthly cadence matters; Option B if the first benchmark is meant to establish the durable baseline.

What should not happen: silent rollover without a score-version boundary.

### 8. Weight splits are intuition, not evidence

The current splits are plausible, but not defensible as locked engineering constants:

```text
Quality: M1=12, M2=10, M3=10
Output: M4=14, M5=6
Cost: M6=12, M7=8
Efficiency: M8=4, M9=4
```

Specific objections:

- M1 gets more than M2/M3 because it is called "most fundamental," not because observed variance or business impact supports it.
- M4 gets 14 mostly because M5 is pending, which conflates implementation readiness with metric importance.
- M6 > M7 is intuitive for batch work, but the split should be a stated policy, not an implied empirical truth.

More honest v1 allocation:

```text
Quality Core: equal split across M1/M2/M3
Output Integrity: equal split across M4/M5 if M5 lands; otherwise M4 gets whole bucket under scorecard_v1
Production Cost: equal split across cost and latency unless the user explicitly declares dollars are 1.5x as important as time
Efficiency: equal split
```

Then reweight after a pilot run using:

- Observed variance.
- Correlation/redundancy between metrics.
- Manual review of model rankings.
- Sensitivity analysis: how often does changing a metric's weight alter top-3 selection?

### 9. D3 conflicts with S0/S1 denominator language

D3 says malformed JSON failed sources are "excluded from the run aggregate."

S1 says:

```text
LLM successes / N
```

Those cannot both be true unless "run aggregate" means `compile_result` only, not benchmark denominator.

Phase 3 must state:

```text
Every attempted source contributes to benchmark denominators through resp_stats, including parse/extract/schema/semantic failures.
Failed sources may be absent from compile_result, but they are not absent from benchmark scoring.
```

Otherwise malformed-output models can be undercounted in downstream measures.

### 10. D2 says `pairing_type_mismatch_rate` is a Tier 2 diagnostic, but Q6 says diagnostic measures are not added

D2 states:

```text
pairing_type_mismatch_rate ... tracked individually as a Tier 2 diagnostic measure
```

Q6 says per-finding diagnostic measures are not added and live only in scorecard inspection.

This is a spec conflict.

Phase 3 should choose one:

- `pairing_type_mismatch_rate` is a reported diagnostic field, not a Tier 2 measure.
- Or it is a named Tier 2 diagnostic measure with no score weight.

Do not leave both phrasings.

### 11. D5 "no gates" conflicts with current compile short-circuiting unless benchmark artifacts compensate

D5 says every source completes to a recorded outcome regardless of validator findings.

Current `compile_one` returns early on:

- model call failure
- truncation
- extract failure
- parse failure
- schema failure
- semantic failure

This is operationally fine if `resp_stats` is the authoritative per-source benchmark row. But Phase 3 must not rely only on `compile_result.compiled_sources`, because failed sources are absent there.

Required scorer input rule:

```text
The benchmark scorer reads the planned source list plus resp_stats for every attempted source.
compile_result is optional success payload, not the benchmark denominator authority.
```

### 12. D1 means valid-but-wrong content is invisible

No LLM-as-judge and no ground truth means the benchmark cannot detect:

- hallucinated body text
- wrong concept definitions
- semantically duplicated near-slugs
- shallow but structurally valid pages
- wrong reuse/non-reuse of existing context

That may be acceptable for Phase 1/2, but the doc should call it a known blind spot.

Current Q4 says KPI completeness is resolved with no additions. That overstates the benchmark. Better wording:

```text
KPI completeness is resolved only for deterministic structural telemetry.
Semantic correctness remains out of scope until Task #20.
```

## Concrete Adversarial Gaming Pattern

### Schema-minimal page spammer

A model behavior pattern that scores well while being bad in production:

1. Always return parseable JSON.
2. Echo `source_id` correctly.
3. Emit exactly one summary page.
4. Emit 20 tiny concept/article pages per source.
5. Keep slug lists perfectly synchronized with page types.
6. Set `supports_page_existence` correctly.
7. Use only self-contained outgoing links to pages emitted in the same response.
8. Ensure every declared outgoing link appears as `[[slug]]` in the body.
9. Avoid existing context unless exact string match appears in the source.
10. Produce generic low-information bodies.

Likely score impact:

```text
S0 high
M1 high
M2/M3 high
M4 high
M5 high
M6/M7 artificially high because pages_produced denominator is inflated
M8/M9 normal if it avoids retries and max_tokens
```

Production outcome:

```text
Vault gets many low-value near-duplicate pages.
Existing KDB context is not compounded.
Graph looks internally valid but semantically fragmented.
Cost/page looks good while cost/useful-knowledge-unit is bad.
```

This is a real blind spot in the KPI set.

## Phase 3 Readiness Checklist

Before scorer code lands, define these explicitly:

- `N`: planned corpus size, attempted source count, or completed source count.
- Whether read/prompt-build/model-call failures count in S0/S1 denominators.
- Whether S1 means `extract_ok && parse_ok` or only `parse_ok`.
- Whether truncation counts as S1 failure, M9 overrun, or both.
- S2 denominator when `LLM-pass == 0`.
- S3 denominator when `LLM-pass == 0`.
- Whether S3 evaluates only schema-valid sources or all parseable sources.
- How malformed per-source outputs absent from `compile_result` join to `resp_stats`.
- How `pages_produced_i` is counted for failed sources.
- Whether `pages_produced_i` includes summary pages.
- Whether duplicate slugs count once or multiple times for page count.
- Whether post-reconciliation or pre-reconciliation payloads feed M1/M2/M3.
- M1 zero-denominator handling.
- M2/M3 zero-denominator handling.
- M2/M3 lower-bound clamp.
- M5 parsing rules for `[[slug]]`, `[[slug|alias]]`, `[[slug#heading]]`, duplicates, code blocks, escaped brackets, and case.
- Whether M5 requires one-way inclusion or exact set parity.
- M6 required source for `cost_usd`.
- M6 behavior when `pages_produced == 0`.
- M7 behavior when `pages_produced == 0`.
- M8 behavior when `max_retries == 0`.
- M8 behavior for pre-model failures where `attempts == 0`.
- M9 canonical provider stop-reason set.
- Missing telemetry policy: fail scorer, mark metric undefined, or assign 0.
- Score normalization policy for undefined metrics.
- Score version identifier persisted into every scorecard.
- Candidate set identifier persisted into every scorecard if rank normalization survives.
- Tie policy for rank normalization.
- All-equal policy for rank/min-max normalization.
- Whether monthly comparisons compare raw metrics, normalized scores, or both.

## Recommended Phase 3 Corrections

### Correction 1: Freeze score versions

Add:

```text
scorecard_version = "task19-kpi-v1"
```

Persist it with every emitted scorecard.

No weight changes, metric additions, denominator changes, or normalization changes inside the same scorecard version.

### Correction 2: Remove M5 rollover ambiguity

Pick one:

```text
scorecard_v1: M4=20, M5=0
scorecard_v2: M4=14, M5=6
```

or:

```text
No official run until M5 is implemented; scorecard_v1 has M4=14, M5=6.
```

### Correction 3: Replace cost/latency per page as scored metrics

Prefer:

```text
M6 = cost_per_successful_source
M7 = latency_per_successful_source
```

Keep:

```text
cost_per_page
latency_per_page
pages_per_source
```

as diagnostics.

If cost/page stays scored, add a scored anti-inflation metric or hard denominator policy. Otherwise page spam remains rewarded.

### Correction 4: Replace Borda with log-scale normalization

For lower-is-better metrics:

```text
normalized = (log(max_value) - log(value)) / (log(max_value) - log(min_value))
score = weight * normalized
```

Define:

```text
if min_value == max_value:
    normalized = 1.0
```

or another explicit policy.

This preserves 10x economic differences without absolute thresholds.

### Correction 5: Make M2/M3 set-based

Use symmetric set agreement:

```text
declared = set(concept_slugs)
emitted = set(page.slug for page in pages if page.page_type == "concept")
union = declared ∪ emitted
score = |declared ∩ emitted| / |union|
```

Equivalent:

```text
score = 1 - |declared Δ emitted| / |declared ∪ emitted|
```

This is bounded, auditable, and simpler than commission/omission over final post-reconciliation count.

### Correction 6: Make M5 exact parity

The original prompt contract says outgoing links and body wikilinks should mirror each other. M5 currently checks only declared links present in body.

Use:

```text
declared = set(page.outgoing_links)
body = set(wikilinks parsed from page.body)
score = |declared ∩ body| / |declared ∪ body|
```

This catches both:

- metadata links absent from body
- body wikilinks absent from metadata

### Correction 7: Admit the no-ground-truth blind spot

Add explicit language:

```text
This benchmark measures structural validity, graph hygiene, operational cost, and deterministic contract adherence. It does not measure semantic truth, usefulness, duplicate concept meaning, or correctness of generated prose until Task #20 introduces ground truth.
```

That makes D1 honest and prevents overclaiming.

## Comparability Against Standard Eval Architectures

### What this design has that is principled

The graph/pairing metrics are not standard benchmark metrics, but they are principled for this project because the KDB has production-specific invariants:

- page-intent JSON
- slug/page pairing
- deterministic Python-owned writes
- manifest graph integrity
- Obsidian wikilink consistency

Generic benchmarks like MMLU do not need these because they score answers, not persistent knowledge-base mutation.

### What is missing compared to HELM-style evaluation

HELM emphasizes broad scenario coverage, multi-metric measurement, standardization, reproducibility, and transparency. This design has multi-metric measurement, but it is missing:

- explicit scenario taxonomy
- confidence intervals or uncertainty reporting
- sample-level inspection format
- score-versioning
- stable candidate set semantics
- explicit missing-metric treatment
- benchmark incompleteness statement

### What is missing compared to MMLU-style harnesses

MMLU-style benchmarks are anchored on ground-truth accuracy over a fixed dataset. This design intentionally lacks ground truth under Task #19, but that means it cannot make claims about answer correctness.

For Phase 3, the doc should avoid saying the KPI set is complete in an absolute sense. It is complete only for deterministic structural telemetry.

### What is missing compared to OpenAI Evals / enterprise eval frameworks

OpenAI Evals-style systems make the data source schema and graders explicit. They support deterministic graders, model graders, string checks, similarity checks, and code graders.

This design aligns with deterministic/code-grader philosophy, but needs:

- explicit scorer input schema
- explicit per-metric grader outputs
- score versioning
- reproducible grader configuration
- persisted model/sample outputs for inspection

### What is missing compared to `lm-evaluation-harness`

`lm-evaluation-harness` emphasizes task configs, model configs, reproducibility, sample logging, metrics, aggregation functions, and decontamination hooks.

This design needs the equivalent of:

- task/corpus version
- model registry version
- prompt version
- scorer version
- metric aggregation definitions
- sample-level logging
- optional repeated runs if stochasticity becomes relevant

## Final Recommendation

Do not freeze Phase 3 code spec until these are resolved:

1. Add `scorecard_version`.
2. Remove M5 rollover ambiguity.
3. Persist or version all telemetry needed for M6/M9.
4. Replace or defend cost/page and latency/page as scored metrics.
5. Define zero-denominator behavior for every metric.
6. Replace Borda normalization or document candidate-set dependency as intentional.
7. Make M2/M3 bounded and denominator-safe.
8. State the deterministic-structural scope and semantic-correctness blind spot explicitly.

These are not polish issues. They affect whether the first monthly benchmark can be compared to the second monthly benchmark without reinterpreting the score.

## Sources Consulted

- [HELM: Holistic Evaluation of Language Models](https://crfm.stanford.edu/2022/11/17/helm.html)
- [Stanford CRFM HELM framework](https://github.com/stanford-crfm/helm)
- [OpenAI API Graders](https://platform.openai.com/docs/guides/graders/)
- [EleutherAI lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness)
