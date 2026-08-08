# Model leaderboard — Pass-1 (enrich) only

_Pass-1-only weighted Borda — effective weights: quarantine 0.667 / recovery 0.167 / latency 0.167 (graph inactive). Updated 2026-08-03T23:02:42-04:00._

| rank | model | cost | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|
| 1 | gemini/gemini-3.6-flash@v0.5.7-84-gee37407 | $0.613 | 0.6389 | 0.5833 | 1 | 68.98 | 0.00 | 68.98 |
| 2 | gemini/gemini-3.6-flash@v0.5.7-67-g9156033-dirty | $0.613 | 0.6389 | 0.5833 | 0.8889 | 67.13 | 0.00 | 67.13 |
| 3 | deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | $0.050 | 0.6389 | 0.5833 | 0.7778 | 65.28 | 0.00 | 65.28 |
| 4 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | $0.306 | 0.6389 | 0.5833 | 0.6667 | 63.43 | 0.00 | 63.43 |
| 5 | deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | $0.050 | 0.6389 | 0.5833 | 0.6111 | 62.50 | 0.00 | 62.50 |
| 6 | deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | $0.050 | 0.6389 | 0.5833 | 0.5556 | 61.57 | 0.00 | 61.57 |
| 7 | openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | $0.307 | 0.6389 | 0.5833 | 0.5 | 60.65 | 0.00 | 60.65 |
| 8 | deepseek/deepseek-v4-flash@v0.5.7-66-gb597a21 | $0.050 | 0.6389 | 0.5833 | 0.4444 | 59.72 | 1.11 (latency) | 58.61 |
| 9 | deepseek/deepseek-v4-flash@v0.5.7-84-gee37407 | $0.050 | 0.6389 | 0.5833 | 0.3889 | 58.80 | 2.22 (latency) | 56.57 |
| 10 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | $0.050 | 0.6389 | 0.5833 | 0.3333 | 57.87 | 3.33 (latency) | 54.54 |
| 11 | openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | $0.306 | 0.6389 | 0.5833 | 0.2778 | 56.94 | 4.44 (latency) | 52.50 |
| 12 | openai/gpt-5.4-mini@v0.5.7-66-gb597a21-dirty | $0.303 | 0.6389 | 0.5833 | 0.2222 | 56.02 | 5.56 (latency) | 50.46 |
| 13 | openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | $0.310 | 0.6389 | 0.05556 | 0.05556 | 44.44 | 8.89 (recovery_rate) | 35.56 |
| 14 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | $0.457 | 0.6389 | 0.1111 | 0 | 44.44 | 10.00 (latency) | 34.44 |
| 15 | openai/gpt-5.4-mini@v0.5.7-84-gee37407 | ≥$0.299 (+1 unknown) | 0.1667 | 0.5833 | 0.7222 | 32.87 | 6.67 (quarantine_rate) | 26.20 |
| 16 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | $0.097 | 0.05556 | 0.5833 | 0.9444 | 29.17 | 8.89 (quarantine_rate) | 20.28 |
| 17 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | ≥$0.712 (+1 unknown) | 0.2222 | 0 | 0.8333 | 28.70 | 10.00 (recovery_rate) | 18.70 |
| 18 | alibaba-sgp/qwen3.7-flash@v0.5.7-155-g9cbf95c | $0.011 | 0.1111 | 0.5833 | 0.1111 | 18.98 | 7.78 (quarantine_rate) | 11.20 |
| 19 | alibaba/qwen3.6-flash@v0.5.7-70-g7dd5f8a | $0.097 | 0 | 0.5833 | 0.1667 | 12.50 | 10.00 (quarantine_rate) | 2.50 |

## Raw measured values (per-pass recomputed at score time; graph from measurements.json)

| model | quarantine_rate_pass1 | recovery_rate_pass1 | latency_pass1 | retry_load_pass1 | cost_usd_pass1 | cost_unknown_calls_pass1 | calls_pass1_5 | attempts_pass1_5 | retries_pass1_5 | cost_usd_pass1_5 | cost_unknown_calls_pass1_5 | input_tokens_pass1_5 | input_token_unknown_attempts_pass1_5 | latency_pass1_5 | context_record_coverage | context_integrity_ok | context_missing_record_count | context_malformed_record_count | context_duplicate_record_count | context_unexpected_record_count | context_wrong_run_record_count | context_expected_count_mismatch | search_key_resolved_at_load_rate | search_key_late_resolution_rate | search_key_never_resolved_rate | search_key_resolved_pre_run_rate | search_key_resolved_cohort_rate | search_key_resolved_age_unknown_rate | search_key_t2_seed_rate | context_build_success_rate | context_explicit_empty_count | context_t1_candidates_mean | context_t1_delivered_mean | context_t2_candidates_mean | context_t2_delivered_mean | context_t3_candidates_mean | context_t3_delivered_mean | search_expression_matched_rate | search_expression_unresolved_rate | search_hit_recency_pre_run_rate | search_hit_recency_cohort_rate | search_hit_recency_age_unknown_rate | search_stage2_budget_bound_rate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini/gemini-3.6-flash@v0.5.7-84-gee37407 | 0 | 0 | 170,847 | 0 | 0.6126 | 0 | — | — | — | — | — | — | — | — | 1 | True | 0 | 0 | 0 | 0 | 0 | False | 0.02991 | 0.2265 | 0.7436 | 0 | 0.02991 | 0 | 0.02991 | 1 | 0 | 0 | 0 | 0.2414 | 0.2414 | 0 | 0 | — | — | — | — | — | — |
| gemini/gemini-3.6-flash@v0.5.7-67-g9156033-dirty | 0 | 0 | 192,323 | 0 | 0.6128 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0 | 0 | 253,327 | 0 | 0.05044 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0 | 0 | 258,687 | 0 | 0.306 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | 0 | 0 | 264,532 | 0 | 0.05045 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | 0 | 0 | 267,414 | 0 | 0.0504 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | 0 | 0 | 279,697 | 0 | 0.3073 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-66-gb597a21 | 0 | 0 | 292,412 | 0 | 0.0504 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-84-gee37407 | 0 | 0 | 297,653 | 0 | 0.05041 | 0 | — | — | — | — | — | — | — | — | 1 | True | 0 | 0 | 0 | 0 | 0 | False | 0.0354 | 0.2965 | 0.6681 | 0 | 0.0354 | 0 | 0.03097 | 1 | 0 | 0 | 0 | 0.25 | 0.25 | 0 | 0 | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 300,597 | 0 | 0.0504 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | 0 | 0 | 306,125 | 0 | 0.3062 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-66-gb597a21-dirty | 0 | 0 | 306,358 | 0 | 0.3029 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | 0 | 2.82 | 510,151 | 0.02778 | 0.3097 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 0 | 2.778 | 1,391,510 | 0.02778 | 0.4572 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-84-gee37407 | 2.819 | 0 | 257,553 | 0.02778 | 0.2988 | 1 | — | — | — | — | — | — | — | — | 1 | True | 0 | 0 | 0 | 0 | 0 | False | 0.0241 | 0.4056 | 0.5703 | 0 | 0.0241 | 0 | 0.01606 | 1 | 0 | 0 | 0 | 0.1429 | 0.1429 | 0 | 0 | — | — | — | — | — | — |
| alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 2.918 | 0 | 177,397 | 0 | 0.09716 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 2.377 | 16.64 | 222,468 | 0.2222 | 0.712 | 1 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| alibaba-sgp/qwen3.7-flash@v0.5.7-155-g9cbf95c | 2.878 | 0 | 455,567 | 0 | 0.01127 | 0 | 27 | 28 | 1 | 0.001791 | 0 | 49208 | 0 | 2,046 | 1 | True | 0 | 0 | 0 | 0 | 0 | False | — | — | — | — | — | — | — | 1 | 0 | 0 | 0 | 1.556 | 1.556 | 0 | 0 | 0.08333 | 0.9167 | 0 | 1 | 0 | 0 |
| alibaba/qwen3.6-flash@v0.5.7-70-g7dd5f8a | 2.92 | 0 | 311,380 | 0 | 0.0968 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |

> Composite is comparable ONLY within this candidate set (average-rank Borda — adding/removing a model shifts ranks). Cost = model-pool pricing × tokens (cohort-comparable, not an invoice).
