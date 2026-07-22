# Model leaderboard — Pass-2 (compile) — downstream outcome

_Hierarchical weighted Borda — §6 weights: quarantine 0.4 / graph 0.4 / recovery 0.1 / latency 0.1. Pass-2 downstream-outcome board: includes Pass-1 gating/failure effects — isolated per-pass attribution awaits #118. Updated 2026-07-22T14:58:20-04:00._

| rank | model | cost | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | graph_score ↑ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | $0.539 | 0.75 | 0.75 | 0.6667 | 0.9083 | 80.50 | 0.00 | 80.50 |
| 2 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | $0.542 | 0.75 | 0.75 | 0.5 | 0.825 | 75.50 | 0.00 | 75.50 |
| 3 | deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | $0.066 | 0.75 | 0.75 | 0.3333 | 0.475 | 59.83 | 3.33 (latency) | 56.50 |
| 4 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | $0.068 | 0.75 | 0.75 | 0.1667 | 0.5167 | 59.83 | 6.67 (latency) | 53.17 |
| 5 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | $0.153 | 0.3333 | 0.1667 | 1 | 0.1917 | 32.67 | 6.67 (recovery_rate) | 26.00 |
| 6 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | $0.762 | 0.1667 | 0.3333 | 0 | 0.45 | 28.00 | 10.00 (latency) | 18.00 |
| 7 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | $1.720 | 0 | 0 | 0.8333 | 0.1333 | 13.67 | 10.00 (quarantine_rate) | 3.67 |

## Raw measured values (per-pass recomputed at score time; graph from measurements.json)

| model | quarantine_rate_pass2 | recovery_rate_pass2 | latency_pass2 | retry_load_pass2 | cost_usd_pass2 | cost_unknown_calls_pass2 | graph_connectivity | link_density | supports_density | entity_reuse | pass2_eligibility_rate | pass2_measurement_coverage | p1_noise | p1_failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | 0 | 0 | 781,557 | 0 | 0.5394 | 0 | 0.2426 | 1.919 | 8.379 | 0.02427 | 0.8056 | 1 | 7 | 0 |
| openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0 | 0 | 782,833 | 0 | 0.5422 | 0 | 0.1923 | 1.782 | 8.379 | 0.02927 | 0.8056 | 1 | 7 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0 | 0 | 852,646 | 0 | 0.06571 | 0 | 0.1456 | 1.777 | 7.5 | 0.01685 | 0.7778 | 1 | 8 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 1,069,276 | 0 | 0.06793 | 0 | 0.181 | 1.502 | 7.862 | 0.02083 | 0.8056 | 1 | 7 | 0 |
| alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 4.731 | 4.731 | 458,708 | 0.07143 | 0.1535 | 0 | 0.1223 | 0.8633 | 5.423 | 0.0177 | 0.7778 | 1 | 7 | 1 |
| zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 10.73 | 2.146 | 5,372,708 | 0.1724 | 0.7618 | 0 | 0.09249 | 2.191 | 7.292 | 0.01342 | 0.8056 | 1 | 7 | 0 |
| gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 15.72 | 11.79 | 630,691 | 0.7241 | 1.72 | 0 | 0.09 | 1.53 | 5.882 | 0 | 0.8056 | 1 | 6 | 1 |

> Pass-2 downstream-outcome board — includes Pass-1 gating/failure effects; isolated per-pass attribution awaits #118. Composite & graph_score are comparable ONLY within this candidate set (average-rank Borda). graph_score = weighted Borda of the 4 graph KPIs (connectivity 35 / link 30 / supports 20 / reuse 15).
