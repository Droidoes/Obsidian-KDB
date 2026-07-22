# Model leaderboard — Pass-2 (compile) — downstream outcome

_Hierarchical weighted Borda — §6 weights: quarantine 0.4 / graph 0.4 / recovery 0.1 / latency 0.1. Pass-2 downstream-outcome board: includes Pass-1 gating/failure effects — isolated per-pass attribution awaits #118. Updated 2026-07-22T13:32:42-04:00._

| rank | model | cost | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | graph_score ↑ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | $0.542 | 0.875 | 0.875 | 0.5 | 0.925 | 85.75 | 0.00 | 85.75 |
| 2 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | $0.068 | 0.875 | 0.875 | 0.25 | 0.6 | 70.25 | 5.00 (latency) | 65.25 |
| 3 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | $0.153 | 0.5 | 0.25 | 1 | 0.25 | 42.50 | 5.00 (recovery_rate) | 37.50 |
| 4 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | $0.762 | 0.25 | 0.5 | 0 | 0.525 | 36.00 | 10.00 (latency) | 26.00 |
| 5 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | $1.720 | 0 | 0 | 0.75 | 0.2 | 15.50 | 10.00 (quarantine_rate) | 5.50 |

## Raw measured values (per-pass recomputed at score time; graph from measurements.json)

| model | quarantine_rate_pass2 | recovery_rate_pass2 | latency_pass2 | retry_load_pass2 | cost_usd_pass2 | cost_unknown_calls_pass2 | graph_connectivity | link_density | supports_density | entity_reuse | pass2_eligibility_rate | pass2_measurement_coverage | p1_noise | p1_failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0 | 0 | 782,833 | 0 | 0.5422 | 0 | 0.1923 | 1.782 | 8.379 | 0.02927 | 0.8056 | 1 | 7 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 1,069,276 | 0 | 0.06793 | 0 | 0.181 | 1.502 | 7.862 | 0.02083 | 0.8056 | 1 | 7 | 0 |
| alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 4.731 | 4.731 | 458,708 | 0.07143 | 0.1535 | 0 | 0.1223 | 0.8633 | 5.423 | 0.0177 | 0.7778 | 1 | 7 | 1 |
| zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 10.73 | 2.146 | 5,372,708 | 0.1724 | 0.7618 | 0 | 0.09249 | 2.191 | 7.292 | 0.01342 | 0.8056 | 1 | 7 | 0 |
| gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 15.72 | 11.79 | 630,691 | 0.7241 | 1.72 | 0 | 0.09 | 1.53 | 5.882 | 0 | 0.8056 | 1 | 6 | 1 |

> Pass-2 downstream-outcome board — includes Pass-1 gating/failure effects; isolated per-pass attribution awaits #118. Composite & graph_score are comparable ONLY within this candidate set (average-rank Borda). graph_score = weighted Borda of the 4 graph KPIs (connectivity 35 / link 30 / supports 20 / reuse 15).
