# Model leaderboard — Pass-1 (enrich) only

_Pass-1-only weighted Borda — effective weights: quarantine 0.667 / recovery 0.167 / latency 0.167 (graph inactive). Updated 2026-07-24T12:23:55-04:00._

| rank | model | cost | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|
| 1 | deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | $0.050 | 0.6 | 0.65 | 0.8 | 64.17 | 0.00 | 64.17 |
| 2 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | $0.306 | 0.6 | 0.65 | 0.7 | 62.50 | 0.00 | 62.50 |
| 3 | deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | $0.050 | 0.6 | 0.65 | 0.6 | 60.83 | 0.00 | 60.83 |
| 4 | deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | $0.050 | 0.6 | 0.65 | 0.5 | 59.17 | 0.00 | 59.17 |
| 5 | openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | $0.307 | 0.6 | 0.65 | 0.4 | 57.50 | 2.00 (latency) | 55.50 |
| 6 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | $0.050 | 0.6 | 0.65 | 0.3 | 55.83 | 4.00 (latency) | 51.83 |
| 7 | openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | $0.306 | 0.6 | 0.65 | 0.2 | 54.17 | 6.00 (latency) | 48.17 |
| 8 | openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | $0.310 | 0.6 | 0.1 | 0.1 | 43.33 | 8.00 (recovery_rate) | 35.33 |
| 9 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | $0.457 | 0.6 | 0.2 | 0 | 43.33 | 10.00 (latency) | 33.33 |
| 10 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | $0.097 | 0 | 0.65 | 1 | 27.50 | 10.00 (quarantine_rate) | 17.50 |
| 11 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | ≥$0.712 (+1 unknown) | 0.1 | 0 | 0.9 | 21.67 | 10.00 (recovery_rate) | 11.67 |

## Raw measured values (per-pass recomputed at score time; graph from measurements.json)

| model | quarantine_rate_pass1 | recovery_rate_pass1 | latency_pass1 | retry_load_pass1 | cost_usd_pass1 | cost_unknown_calls_pass1 |
|---|---|---|---|---|---|---|
| deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0 | 0 | 253,327 | 0 | 0.05044 | 0 |
| openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0 | 0 | 258,687 | 0 | 0.306 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | 0 | 0 | 264,532 | 0 | 0.05045 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | 0 | 0 | 267,414 | 0 | 0.0504 | 0 |
| openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | 0 | 0 | 279,697 | 0 | 0.3073 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 300,597 | 0 | 0.0504 | 0 |
| openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | 0 | 0 | 306,125 | 0 | 0.3062 | 0 |
| openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | 0 | 2.82 | 510,151 | 0.02778 | 0.3097 | 0 |
| zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 0 | 2.778 | 1,391,510 | 0.02778 | 0.4572 | 0 |
| alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 2.918 | 0 | 177,397 | 0 | 0.09716 | 0 |
| gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 2.377 | 16.64 | 222,468 | 0.2222 | 0.712 | 1 |

> Composite is comparable ONLY within this candidate set (average-rank Borda — adding/removing a model shifts ranks). Cost = model-pool pricing × tokens (cohort-comparable, not an invoice).
