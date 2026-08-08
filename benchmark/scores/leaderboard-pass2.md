# Model leaderboard — Pass-2 (compile) — downstream outcome

_Hierarchical weighted Borda — §6 weights: quarantine 0.4 / graph 0.4 / recovery 0.1 / latency 0.1. Pass-2 downstream-outcome board: includes Pass-1 gating/failure effects — isolated per-pass attribution awaits #118. Updated 2026-08-03T23:02:42-04:00._

| rank | model | cost | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | graph_score ↑ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | $0.539 | 0.6389 | 0.6944 | 0.7222 | 0.8528 | 73.83 | 0.00 | 73.83 |
| 2 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | $0.542 | 0.6389 | 0.6944 | 0.6667 | 0.85 | 73.17 | 0.00 | 73.17 |
| 3 | openai/gpt-5.4-mini@v0.5.7-84-gee37407 | $0.428 | 0.6389 | 0.6944 | 0.5556 | 0.7194 | 66.83 | 0.00 | 66.83 |
| 4 | gemini/gemini-3.6-flash@v0.5.7-67-g9156033-dirty | $0.758 | 0.6389 | 0.2778 | 0.8889 | 0.7 | 65.22 | 4.44 (recovery_rate) | 60.78 |
| 5 | deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | $0.066 | 0.6389 | 0.6944 | 0.4444 | 0.5889 | 60.50 | 1.11 (latency) | 59.39 |
| 6 | openai/gpt-5.4-mini@v0.5.7-66-gb597a21-dirty | $0.447 | 0.6389 | 0.6944 | 0.2778 | 0.6694 | 62.06 | 4.44 (latency) | 57.61 |
| 7 | gemini/gemini-3.6-flash@v0.5.7-84-gee37407 | $0.706 | 0.6389 | 0.1667 | 0.9444 | 0.6111 | 61.11 | 6.67 (recovery_rate) | 54.44 |
| 8 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | $0.068 | 0.6389 | 0.6944 | 0.1667 | 0.5778 | 57.28 | 6.67 (latency) | 50.61 |
| 9 | openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | $0.435 | 0.6389 | 0.6944 | 0.05556 | 0.5222 | 53.94 | 8.89 (latency) | 45.06 |
| 10 | deepseek/deepseek-v4-flash@v0.5.7-84-gee37407 | $0.052 | 0.6389 | 0.6944 | 0.2222 | 0.3917 | 50.39 | 5.56 (latency) | 44.83 |
| 11 | deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | $0.051 | 0.6389 | 0.6944 | 0.6111 | 0.2306 | 47.83 | 5.39 (graph) | 42.44 |
| 12 | openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | $0.482 | 0.2222 | 0.05556 | 0.3889 | 0.8667 | 48.00 | 8.89 (recovery_rate) | 39.11 |
| 13 | deepseek/deepseek-v4-flash@v0.5.7-66-gb597a21 | $0.055 | 0.6389 | 0.2222 | 0.3333 | 0.3028 | 43.22 | 5.56 (recovery_rate) | 37.67 |
| 14 | alibaba/qwen3.6-flash@v0.5.7-70-g7dd5f8a | $0.119 | 0.6389 | 0.6944 | 0.7778 | 0.06944 | 43.06 | 8.61 (graph) | 34.44 |
| 15 | deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | $0.053 | 0.1667 | 0.6944 | 0.5 | 0.4222 | 35.50 | 6.67 (quarantine_rate) | 28.83 |
| 16 | alibaba-sgp/qwen3.7-flash@v0.5.7-155-g9cbf95c | $0.013 | 0.6389 | 0.6944 | 0.1111 | 0.08333 | 36.94 | 8.33 (graph) | 28.61 |
| 17 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | $0.153 | 0.1111 | 0.1111 | 1 | 0.2778 | 26.67 | 7.78 (quarantine_rate) | 18.89 |
| 18 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | $0.762 | 0.05556 | 0.3333 | 0 | 0.5056 | 25.78 | 10.00 (latency) | 15.78 |
| 19 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | $1.720 | 0 | 0 | 0.8333 | 0.2583 | 18.67 | 10.00 (quarantine_rate) | 8.67 |

## Raw measured values (per-pass recomputed at score time; graph from measurements.json)

| model | quarantine_rate_pass2 | recovery_rate_pass2 | latency_pass2 | retry_load_pass2 | cost_usd_pass2 | cost_unknown_calls_pass2 | calls_pass1_5 | attempts_pass1_5 | retries_pass1_5 | cost_usd_pass1_5 | cost_unknown_calls_pass1_5 | input_tokens_pass1_5 | input_token_unknown_attempts_pass1_5 | latency_pass1_5 | graph_connectivity | link_density | supports_density | entity_reuse | pass2_eligibility_rate | pass2_measurement_coverage | p1_noise | p1_failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | 0 | 0 | 781,557 | 0 | 0.5394 | 0 | — | — | — | — | — | — | — | — | 0.2426 | 1.919 | 8.379 | 0.02427 | 0.8056 | 1 | 7 | 0 |
| openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0 | 0 | 782,833 | 0 | 0.5422 | 0 | — | — | — | — | — | — | — | — | 0.1923 | 1.782 | 8.379 | 0.02927 | 0.8056 | 1 | 7 | 0 |
| openai/gpt-5.4-mini@v0.5.7-84-gee37407 | 0 | 0 | 821,092 | 0 | 0.4279 | 0 | — | — | — | — | — | — | — | — | 0.166 | 1.68 | 9.464 | 0.02597 | 0.7778 | 1 | 7 | 1 |
| gemini/gemini-3.6-flash@v0.5.7-67-g9156033-dirty | 0 | 2.671 | 511,409 | 0.03448 | 0.7584 | 0 | — | — | — | — | — | — | — | — | 0.2471 | 1.621 | 6.207 | 0.02759 | 0.8056 | 1 | 7 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0 | 0 | 852,646 | 0 | 0.06571 | 0 | — | — | — | — | — | — | — | — | 0.1456 | 1.777 | 7.5 | 0.01685 | 0.7778 | 1 | 8 | 0 |
| openai/gpt-5.4-mini@v0.5.7-66-gb597a21-dirty | 0 | 0 | 1,007,252 | 0 | 0.4472 | 0 | — | — | — | — | — | — | — | — | 0.1738 | 1.521 | 9.633 | 0.01984 | 0.8333 | 1 | 6 | 0 |
| gemini/gemini-3.6-flash@v0.5.7-84-gee37407 | 0 | 2.804 | 461,716 | 0.03448 | 0.7062 | 0 | — | — | — | — | — | — | — | — | 0.1718 | 1.681 | 5.793 | 0.03731 | 0.8056 | 1 | 7 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 1,069,276 | 0 | 0.06793 | 0 | — | — | — | — | — | — | — | — | 0.181 | 1.502 | 7.862 | 0.02083 | 0.8056 | 1 | 7 | 0 |
| openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | 0 | 0 | 1,197,277 | 0 | 0.4353 | 0 | — | — | — | — | — | — | — | — | 0.1231 | 1.538 | 9.103 | 0.01299 | 0.8056 | 1 | 7 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-84-gee37407 | 0 | 0 | 1,044,930 | 0 | 0.05159 | 0 | — | — | — | — | — | — | — | — | 0.1004 | 0.8603 | 8.321 | 0.0199 | 0.7778 | 1 | 8 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | 0 | 0 | 811,384 | 0 | 0.05073 | 0 | — | — | — | — | — | — | — | — | 0.07692 | 0.6787 | 8 | 0.01554 | 0.7778 | 1 | 8 | 0 |
| openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | 2.654 | 5.307 | 954,925 | 0.1034 | 0.482 | 0 | — | — | — | — | — | — | — | — | 0.2441 | 1.709 | 9.286 | 0.02655 | 0.8056 | 1 | 7 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-66-gb597a21 | 0 | 2.775 | 956,307 | 0.03571 | 0.05503 | 0 | — | — | — | — | — | — | — | — | 0.08072 | 0.8834 | 8.107 | 0.01538 | 0.7778 | 1 | 8 | 0 |
| alibaba/qwen3.6-flash@v0.5.7-70-g7dd5f8a | 0 | 0 | 661,793 | 0 | 0.1187 | 0 | — | — | — | — | — | — | — | — | 0.03448 | 0.3678 | 6.214 | 0 | 0.7778 | 1 | 7 | 1 |
| deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | 2.879 | 0 | 824,689 | 0.03571 | 0.05329 | 0 | — | — | — | — | — | — | — | — | 0.1261 | 1.225 | 8.259 | 0.005128 | 0.7778 | 1 | 8 | 0 |
| alibaba-sgp/qwen3.7-flash@v0.5.7-155-g9cbf95c | 0 | 0 | 1,111,908 | 0 | 0.01286 | 0 | 27 | 28 | 1 | 0.001791 | 0 | 49208 | 0 | 2,046 | 0.03825 | 0.3552 | 6.778 | 0 | 0.75 | 1 | 8 | 1 |
| alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 4.731 | 4.731 | 458,708 | 0.07143 | 0.1535 | 0 | — | — | — | — | — | — | — | — | 0.1223 | 0.8633 | 5.423 | 0.0177 | 0.7778 | 1 | 7 | 1 |
| zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 10.73 | 2.146 | 5,372,708 | 0.1724 | 0.7618 | 0 | — | — | — | — | — | — | — | — | 0.09249 | 2.191 | 7.292 | 0.01342 | 0.8056 | 1 | 7 | 0 |
| gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 15.72 | 11.79 | 630,691 | 0.7241 | 1.72 | 0 | — | — | — | — | — | — | — | — | 0.09 | 1.53 | 5.882 | 0 | 0.8056 | 1 | 6 | 1 |

> Pass-2 downstream-outcome board — includes Pass-1 gating/failure effects; isolated per-pass attribution awaits #118. Composite & graph_score are comparable ONLY within this candidate set (average-rank Borda). graph_score = weighted Borda of the 4 graph KPIs (connectivity 35 / link 30 / supports 20 / reuse 15).
