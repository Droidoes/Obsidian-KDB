# Model leaderboard — Pass-1 (enrich) only

_Pass-1-only weighted Borda — effective weights: quarantine 0.667 / recovery 0.167 / latency 0.167 (graph inactive). Updated 2026-07-25T09:48:39-04:00._

| rank | model | cost | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|
| 1 | gemini/gemini-3.6-flash@v0.5.7-84-gee37407 | $0.613 | 0.6176 | 0.5882 | 1 | 67.65 | 0.00 | 67.65 |
| 2 | gemini/gemini-3.6-flash@v0.5.7-67-g9156033-dirty | $0.613 | 0.6176 | 0.5882 | 0.8824 | 65.69 | 0.00 | 65.69 |
| 3 | deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | $0.050 | 0.6176 | 0.5882 | 0.7647 | 63.73 | 0.00 | 63.73 |
| 4 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | $0.306 | 0.6176 | 0.5882 | 0.6471 | 61.76 | 0.00 | 61.76 |
| 5 | deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | $0.050 | 0.6176 | 0.5882 | 0.5882 | 60.78 | 0.00 | 60.78 |
| 6 | deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | $0.050 | 0.6176 | 0.5882 | 0.5294 | 59.80 | 0.00 | 59.80 |
| 7 | openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | $0.307 | 0.6176 | 0.5882 | 0.4706 | 58.82 | 0.59 (latency) | 58.24 |
| 8 | deepseek/deepseek-v4-flash@v0.5.7-66-gb597a21 | $0.050 | 0.6176 | 0.5882 | 0.4118 | 57.84 | 1.76 (latency) | 56.08 |
| 9 | deepseek/deepseek-v4-flash@v0.5.7-84-gee37407 | $0.050 | 0.6176 | 0.5882 | 0.3529 | 56.86 | 2.94 (latency) | 53.92 |
| 10 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | $0.050 | 0.6176 | 0.5882 | 0.2941 | 55.88 | 4.12 (latency) | 51.76 |
| 11 | openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | $0.306 | 0.6176 | 0.5882 | 0.2353 | 54.90 | 5.29 (latency) | 49.61 |
| 12 | openai/gpt-5.4-mini@v0.5.7-66-gb597a21-dirty | $0.303 | 0.6176 | 0.5882 | 0.1765 | 53.92 | 6.47 (latency) | 47.45 |
| 13 | openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | $0.310 | 0.6176 | 0.05882 | 0.05882 | 43.14 | 8.82 (recovery_rate) | 34.31 |
| 14 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | $0.457 | 0.6176 | 0.1176 | 0 | 43.14 | 10.00 (latency) | 33.14 |
| 15 | openai/gpt-5.4-mini@v0.5.7-84-gee37407 | ≥$0.299 (+1 unknown) | 0.1176 | 0.5882 | 0.7059 | 29.41 | 7.65 (quarantine_rate) | 21.76 |
| 16 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | $0.097 | 0.05882 | 0.5882 | 0.9412 | 29.41 | 8.82 (quarantine_rate) | 20.59 |
| 17 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | ≥$0.712 (+1 unknown) | 0.1765 | 0 | 0.8235 | 25.49 | 10.00 (recovery_rate) | 15.49 |
| 18 | alibaba/qwen3.6-flash@v0.5.7-70-g7dd5f8a | $0.097 | 0 | 0.5882 | 0.1176 | 11.76 | 10.00 (quarantine_rate) | 1.76 |

## Raw measured values (per-pass recomputed at score time; graph from measurements.json)

| model | quarantine_rate_pass1 | recovery_rate_pass1 | latency_pass1 | retry_load_pass1 | cost_usd_pass1 | cost_unknown_calls_pass1 | context_record_coverage | context_integrity_ok | context_missing_record_count | context_malformed_record_count | context_duplicate_record_count | context_unexpected_record_count | context_wrong_run_record_count | context_expected_count_mismatch | search_key_resolved_at_load_rate | search_key_late_resolution_rate | search_key_never_resolved_rate | search_key_resolved_pre_run_rate | search_key_resolved_cohort_rate | search_key_resolved_age_unknown_rate | search_key_t2_seed_rate | context_build_success_rate | context_explicit_empty_count | context_t1_candidates_mean | context_t1_delivered_mean | context_t2_candidates_mean | context_t2_delivered_mean | context_t3_candidates_mean | context_t3_delivered_mean |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini/gemini-3.6-flash@v0.5.7-84-gee37407 | 0 | 0 | 170,847 | 0 | 0.6126 | 0 | 1 | True | 0 | 0 | 0 | 0 | 0 | False | 0.02991 | 0.2265 | 0.7436 | 0 | 0.02991 | 0 | 0.02991 | 1 | 0 | 0 | 0 | 0.2414 | 0.2414 | 0 | 0 |
| gemini/gemini-3.6-flash@v0.5.7-67-g9156033-dirty | 0 | 0 | 192,323 | 0 | 0.6128 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0 | 0 | 253,327 | 0 | 0.05044 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0 | 0 | 258,687 | 0 | 0.306 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | 0 | 0 | 264,532 | 0 | 0.05045 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | 0 | 0 | 267,414 | 0 | 0.0504 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | 0 | 0 | 279,697 | 0 | 0.3073 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-66-gb597a21 | 0 | 0 | 292,412 | 0 | 0.0504 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-84-gee37407 | 0 | 0 | 297,653 | 0 | 0.05041 | 0 | 1 | True | 0 | 0 | 0 | 0 | 0 | False | 0.0354 | 0.2965 | 0.6681 | 0 | 0.0354 | 0 | 0.03097 | 1 | 0 | 0 | 0 | 0.25 | 0.25 | 0 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 300,597 | 0 | 0.0504 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | 0 | 0 | 306,125 | 0 | 0.3062 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-66-gb597a21-dirty | 0 | 0 | 306,358 | 0 | 0.3029 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | 0 | 2.82 | 510,151 | 0.02778 | 0.3097 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 0 | 2.778 | 1,391,510 | 0.02778 | 0.4572 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-84-gee37407 | 2.819 | 0 | 257,553 | 0.02778 | 0.2988 | 1 | 1 | True | 0 | 0 | 0 | 0 | 0 | False | 0.0241 | 0.4056 | 0.5703 | 0 | 0.0241 | 0 | 0.01606 | 1 | 0 | 0 | 0 | 0.1429 | 0.1429 | 0 | 0 |
| alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 2.918 | 0 | 177,397 | 0 | 0.09716 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 2.377 | 16.64 | 222,468 | 0.2222 | 0.712 | 1 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| alibaba/qwen3.6-flash@v0.5.7-70-g7dd5f8a | 2.92 | 0 | 311,380 | 0 | 0.0968 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |

> Composite is comparable ONLY within this candidate set (average-rank Borda — adding/removing a model shifts ranks). Cost = model-pool pricing × tokens (cohort-comparable, not an invoice).
