# Model leaderboard — Pass-2 (compile) — downstream outcome

_Hierarchical weighted Borda — §6 weights: quarantine 0.4 / graph 0.4 / recovery 0.1 / latency 0.1. Pass-2 downstream-outcome board: includes Pass-1 gating/failure effects — isolated per-pass attribution awaits #118. Updated 2026-07-24T17:40:17-04:00._

| rank | model | cost | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | graph_score ↑ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | $0.539 | 0.6923 | 0.7308 | 0.7692 | 0.8346 | 76.08 | 0.00 | 76.08 |
| 2 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | $0.542 | 0.6923 | 0.7308 | 0.6923 | 0.8192 | 74.69 | 0.00 | 74.69 |
| 3 | gemini/gemini-3.6-flash@v0.5.7-67-g9156033-dirty | $0.758 | 0.6923 | 0.3077 | 0.9231 | 0.7038 | 68.15 | 3.85 (recovery_rate) | 64.31 |
| 4 | deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | $0.066 | 0.6923 | 0.7308 | 0.4615 | 0.55 | 61.62 | 0.77 (latency) | 60.85 |
| 5 | openai/gpt-5.4-mini@v0.5.7-66-gb597a21-dirty | $0.447 | 0.6923 | 0.7308 | 0.2308 | 0.6231 | 62.23 | 5.38 (latency) | 56.85 |
| 6 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | $0.068 | 0.6923 | 0.7308 | 0.1538 | 0.5154 | 57.15 | 6.92 (latency) | 50.23 |
| 7 | openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | $0.435 | 0.6923 | 0.7308 | 0.07692 | 0.4885 | 55.31 | 8.46 (latency) | 46.85 |
| 8 | openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | $0.482 | 0.3077 | 0.07692 | 0.3846 | 0.8423 | 50.62 | 8.46 (recovery_rate) | 42.15 |
| 9 | deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | $0.051 | 0.6923 | 0.7308 | 0.6154 | 0.15 | 47.15 | 7.00 (graph) | 40.15 |
| 10 | deepseek/deepseek-v4-flash@v0.5.7-66-gb597a21 | $0.055 | 0.6923 | 0.2308 | 0.3077 | 0.2269 | 42.15 | 5.46 (graph) | 36.69 |
| 11 | deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | $0.053 | 0.2308 | 0.7308 | 0.5385 | 0.3654 | 36.54 | 5.38 (quarantine_rate) | 31.15 |
| 12 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | $0.153 | 0.1538 | 0.1538 | 1 | 0.2115 | 26.15 | 6.92 (quarantine_rate) | 19.23 |
| 13 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | $0.762 | 0.07692 | 0.3846 | 0 | 0.4615 | 25.38 | 10.00 (latency) | 15.38 |
| 14 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | $1.720 | 0 | 0 | 0.8462 | 0.2077 | 16.77 | 10.00 (quarantine_rate) | 6.77 |

## Raw measured values (per-pass recomputed at score time; graph from measurements.json)

| model | quarantine_rate_pass2 | recovery_rate_pass2 | latency_pass2 | retry_load_pass2 | cost_usd_pass2 | cost_unknown_calls_pass2 | graph_connectivity | link_density | supports_density | entity_reuse | pass2_eligibility_rate | pass2_measurement_coverage | p1_noise | p1_failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | 0 | 0 | 781,557 | 0 | 0.5394 | 0 | 0.2426 | 1.919 | 8.379 | 0.02427 | 0.8056 | 1 | 7 | 0 |
| openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0 | 0 | 782,833 | 0 | 0.5422 | 0 | 0.1923 | 1.782 | 8.379 | 0.02927 | 0.8056 | 1 | 7 | 0 |
| gemini/gemini-3.6-flash@v0.5.7-67-g9156033-dirty | 0 | 2.671 | 511,409 | 0.03448 | 0.7584 | 0 | 0.2471 | 1.621 | 6.207 | 0.02759 | 0.8056 | 1 | 7 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0 | 0 | 852,646 | 0 | 0.06571 | 0 | 0.1456 | 1.777 | 7.5 | 0.01685 | 0.7778 | 1 | 8 | 0 |
| openai/gpt-5.4-mini@v0.5.7-66-gb597a21-dirty | 0 | 0 | 1,007,252 | 0 | 0.4472 | 0 | 0.1738 | 1.521 | 9.633 | 0.01984 | 0.8333 | 1 | 6 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 1,069,276 | 0 | 0.06793 | 0 | 0.181 | 1.502 | 7.862 | 0.02083 | 0.8056 | 1 | 7 | 0 |
| openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | 0 | 0 | 1,197,277 | 0 | 0.4353 | 0 | 0.1231 | 1.538 | 9.103 | 0.01299 | 0.8056 | 1 | 7 | 0 |
| openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | 2.654 | 5.307 | 954,925 | 0.1034 | 0.482 | 0 | 0.2441 | 1.709 | 9.286 | 0.02655 | 0.8056 | 1 | 7 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | 0 | 0 | 811,384 | 0 | 0.05073 | 0 | 0.07692 | 0.6787 | 8 | 0.01554 | 0.7778 | 1 | 8 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-66-gb597a21 | 0 | 2.775 | 956,307 | 0.03571 | 0.05503 | 0 | 0.08072 | 0.8834 | 8.107 | 0.01538 | 0.7778 | 1 | 8 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | 2.879 | 0 | 824,689 | 0.03571 | 0.05329 | 0 | 0.1261 | 1.225 | 8.259 | 0.005128 | 0.7778 | 1 | 8 | 0 |
| alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 4.731 | 4.731 | 458,708 | 0.07143 | 0.1535 | 0 | 0.1223 | 0.8633 | 5.423 | 0.0177 | 0.7778 | 1 | 7 | 1 |
| zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 10.73 | 2.146 | 5,372,708 | 0.1724 | 0.7618 | 0 | 0.09249 | 2.191 | 7.292 | 0.01342 | 0.8056 | 1 | 7 | 0 |
| gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 15.72 | 11.79 | 630,691 | 0.7241 | 1.72 | 0 | 0.09 | 1.53 | 5.882 | 0 | 0.8056 | 1 | 6 | 1 |

> Pass-2 downstream-outcome board — includes Pass-1 gating/failure effects; isolated per-pass attribution awaits #118. Composite & graph_score are comparable ONLY within this candidate set (average-rank Borda). graph_score = weighted Borda of the 4 graph KPIs (connectivity 35 / link 30 / supports 20 / reuse 15).
