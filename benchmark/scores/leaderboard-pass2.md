# Model leaderboard — Pass-2 (compile) — downstream outcome

_Hierarchical weighted Borda — §6 weights: quarantine 0.4 / graph 0.4 / recovery 0.1 / latency 0.1. Pass-2 downstream-outcome board: includes Pass-1 gating/failure effects — isolated per-pass attribution awaits #118. Updated 2026-07-23T00:35:48-04:00._

| rank | model | cost | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | graph_score ↑ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | $0.539 | 0.8125 | 0.75 | 0.75 | 0.8438 | 81.25 | 0.00 | 81.25 |
| 2 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | $0.542 | 0.8125 | 0.75 | 0.625 | 0.8 | 78.25 | 0.00 | 78.25 |
| 3 | deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | $0.066 | 0.8125 | 0.75 | 0.375 | 0.4938 | 63.50 | 2.50 (latency) | 61.00 |
| 4 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | $0.068 | 0.8125 | 0.75 | 0.125 | 0.4875 | 60.75 | 7.50 (latency) | 53.25 |
| 5 | openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | $0.482 | 0.5 | 0.125 | 0.25 | 0.8313 | 57.00 | 7.50 (recovery_rate) | 49.50 |
| 6 | deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | $0.053 | 0.375 | 0.75 | 0.5 | 0.3125 | 40.00 | 3.75 (graph) | 36.25 |
| 7 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | $0.153 | 0.25 | 0.25 | 1 | 0.1625 | 29.00 | 6.75 (graph) | 22.25 |
| 8 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | $0.762 | 0.125 | 0.375 | 0 | 0.4313 | 26.00 | 10.00 (latency) | 16.00 |
| 9 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | $1.720 | 0 | 0 | 0.875 | 0.1375 | 14.25 | 10.00 (quarantine_rate) | 4.25 |

## Raw measured values (per-pass recomputed at score time; graph from measurements.json)

| model | quarantine_rate_pass2 | recovery_rate_pass2 | latency_pass2 | retry_load_pass2 | cost_usd_pass2 | cost_unknown_calls_pass2 | graph_connectivity | link_density | supports_density | entity_reuse | pass2_eligibility_rate | pass2_measurement_coverage | p1_noise | p1_failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | 0 | 0 | 781,557 | 0 | 0.5394 | 0 | 0.2426 | 1.919 | 8.379 | 0.02427 | 0.8056 | 1 | 7 | 0 |
| openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0 | 0 | 782,833 | 0 | 0.5422 | 0 | 0.1923 | 1.782 | 8.379 | 0.02927 | 0.8056 | 1 | 7 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0 | 0 | 852,646 | 0 | 0.06571 | 0 | 0.1456 | 1.777 | 7.5 | 0.01685 | 0.7778 | 1 | 8 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 1,069,276 | 0 | 0.06793 | 0 | 0.181 | 1.502 | 7.862 | 0.02083 | 0.8056 | 1 | 7 | 0 |
| openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | 2.654 | 5.307 | 954,925 | 0.1034 | 0.482 | 0 | 0.2441 | 1.709 | 9.286 | 0.02655 | 0.8056 | 1 | 7 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | 2.879 | 0 | 824,689 | 0.03571 | 0.05329 | 0 | 0.1261 | 1.225 | 8.259 | 0.005128 | 0.7778 | 1 | 8 | 0 |
| alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 4.731 | 4.731 | 458,708 | 0.07143 | 0.1535 | 0 | 0.1223 | 0.8633 | 5.423 | 0.0177 | 0.7778 | 1 | 7 | 1 |
| zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 10.73 | 2.146 | 5,372,708 | 0.1724 | 0.7618 | 0 | 0.09249 | 2.191 | 7.292 | 0.01342 | 0.8056 | 1 | 7 | 0 |
| gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 15.72 | 11.79 | 630,691 | 0.7241 | 1.72 | 0 | 0.09 | 1.53 | 5.882 | 0 | 0.8056 | 1 | 6 | 1 |

> Pass-2 downstream-outcome board — includes Pass-1 gating/failure effects; isolated per-pass attribution awaits #118. Composite & graph_score are comparable ONLY within this candidate set (average-rank Borda). graph_score = weighted Borda of the 4 graph KPIs (connectivity 35 / link 30 / supports 20 / reuse 15).
