# Model leaderboard

_Hierarchical weighted Borda — §6 starting weights: quarantine 0.4 / graph 0.4 / recovery 0.1 / latency 0.1. Updated 2026-07-24T12:23:55-04:00._

| rank | model | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | graph_score ↑ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|
| 1 | openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | 0.75 | 0.75 | 0.5 | 0.855 | 76.70 | 0.00 | 76.70 |
| 2 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0.75 | 0.75 | 0.6 | 0.82 | 76.30 | 0.00 | 76.30 |
| 3 | deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0.75 | 0.75 | 0.4 | 0.555 | 63.70 | 2.00 (latency) | 61.70 |
| 4 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0.75 | 0.75 | 0.2 | 0.52 | 60.30 | 6.00 (latency) | 54.30 |
| 5 | openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | 0.75 | 0.4 | 0.1 | 0.5 | 55.00 | 8.00 (latency) | 47.00 |
| 6 | openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | 0.4 | 0.1 | 0.3 | 0.865 | 54.60 | 8.00 (recovery_rate) | 46.60 |
| 7 | deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | 0.75 | 0.75 | 0.8 | 0.16 | 51.90 | 6.80 (graph) | 45.10 |
| 8 | deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | 0.3 | 0.75 | 0.7 | 0.37 | 41.30 | 4.00 (quarantine_rate) | 37.30 |
| 9 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 0.2 | 0.2 | 1 | 0.225 | 29.00 | 6.00 (quarantine_rate) | 23.00 |
| 10 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 0.1 | 0.3 | 0 | 0.455 | 25.20 | 10.00 (latency) | 15.20 |
| 11 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 0.9 | 0.175 | 16.00 | 10.00 (quarantine_rate) | 6.00 |

## Raw measured values (scored KPIs + diagnostics / watched)

| model | quarantine_rate | recovery_rate | latency | entity_reuse | graph_connectivity | link_density | supports_density | retry_load | token_overrun_rate | repair_rung_rate | semantic_pass_rate | signal_noise_ratio | quarantine_rate_pass1 | quarantine_rate_pass2 | latency_pass1 | latency_pass2 | orphan_rate | entity_search_key_resolution | belongs_to_coverage | domain_null_rate | domain_breadth | recovery_rate_pass1 | recovery_rate_pass2 | retry_load_pass1 | retry_load_pass2 | cost_usd_pass1 | cost_usd_pass2 | cost_unknown_calls_pass1 | cost_unknown_calls_pass2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | 0 | 0 | 567,760 | 0.02427 | 0.2426 | 1.919 | 8.379 | 0 | 0 | 0 | 1 | 0.8056 | 0 | 0 | 306,125 | 781,557 | 0 | 0.3636 | 1 | 0 | 0.4348 | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0 | 0 | 547,297 | 0.02927 | 0.1923 | 1.782 | 8.379 | 0 | 0 | 0 | 1 | 0.8056 | 0 | 0 | 258,687 | 782,833 | 0 | 0.406 | 1 | 0 | 0.4783 | — | — | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0 | 0 | 579,154 | 0.01685 | 0.1456 | 1.777 | 7.5 | 0 | 0 | 0 | 1 | 0.7778 | 0 | 0 | 253,327 | 852,646 | 0 | 0.2705 | 1 | 0 | 0.4348 | — | — | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 723,787 | 0.02083 | 0.181 | 1.502 | 7.862 | 0 | 0 | 0 | 1 | 0.8056 | 0 | 0 | 300,597 | 1,069,276 | 0 | 0.2816 | 1 | 0 | 0.4348 | — | — | — | — | — | — | — | — |
| openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | 0 | 1.429 | 848,985 | 0.01299 | 0.1231 | 1.538 | 9.103 | 0.01538 | 0 | 0 | 1 | 0.8056 | 0 | 0 | 510,151 | 1,197,277 | 0 | 0.4073 | 1 | 0 | 0.4783 | 2.82 | 0 | 0.02778 | 0 | 0.3097 | 0.4353 | 0 | 0 |
| openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | 1.376 | 2.752 | 629,876 | 0.02655 | 0.2441 | 1.709 | 9.286 | 0.04615 | 0 | 0 | 0.9655 | 0.8056 | 0 | 2.654 | 279,697 | 954,925 | 0 | 0.3684 | 1 | 0 | 0.4348 | — | — | — | — | — | — | — | — |
| deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | 0 | 0 | 529,297 | 0.01554 | 0.07692 | 0.6787 | 8 | 0 | 0 | 0 | 1 | 0.7778 | 0 | 0 | 264,532 | 811,384 | 0 | 0.2077 | 1 | 0 | 0.4348 | 0 | 0 | 0 | 0 | 0.05045 | 0.05073 | 0 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | 1.429 | 0 | 544,039 | 0.005128 | 0.1261 | 1.225 | 8.259 | 0.01562 | 0 | 0 | 0.9643 | 0.7778 | 0 | 2.879 | 267,414 | 824,689 | 0 | 0.2164 | 1 | 0 | 0.4348 | — | — | — | — | — | — | — | — |
| alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 3.92 | 2.613 | 332,763 | 0.0177 | 0.1223 | 0.8633 | 5.423 | 0.03125 | 0 | 2.613 | 0.9286 | 0.7778 | 2.918 | 4.731 | 177,397 | 458,708 | 0 | 0.1786 | 1 | 0 | 0.3913 | — | — | — | — | — | — | — | — |
| zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 6.054 | 2.421 | 3,637,507 | 0.01342 | 0.09249 | 2.191 | 7.292 | 0.09231 | 0 | 0 | 0.8276 | 0.8056 | 0 | 10.73 | 1,391,510 | 5,372,708 | 0 | 0.2347 | 1 | 0 | 0.4348 | — | — | — | — | — | — | — | — |
| gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 10.98 | 13.51 | 485,670 | 0 | 0.09 | 1.53 | 5.882 | 0.4462 | 0 | 0 | 0.5862 | 0.8056 | 2.377 | 15.72 | 222,468 | 630,691 | 0 | 0.1324 | 1 | 0 | 0.3913 | — | — | — | — | — | — | — | — |

> Composite & graph_score are comparable ONLY within this candidate set (average-rank Borda — adding/removing a model shifts ranks). graph_score = weighted Borda of the 4 graph KPIs (connectivity 35 / link 30 / supports 20 / reuse 15).
