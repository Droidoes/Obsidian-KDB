# Model leaderboard — Pass-1 (enrich) only

_Pass-1-only weighted Borda — effective weights: quarantine 0.667 / recovery 0.167 / latency 0.167 (graph inactive). Updated 2026-07-23T00:35:48-04:00._

| rank | model | cost | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|
| 1 | deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | $0.050 | 0.625 | 0.625 | 0.75 | 64.58 | 0.00 | 64.58 |
| 2 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | $0.306 | 0.625 | 0.625 | 0.625 | 62.50 | 0.00 | 62.50 |
| 3 | deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | $0.050 | 0.625 | 0.625 | 0.5 | 60.42 | 0.00 | 60.42 |
| 4 | openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | $0.307 | 0.625 | 0.625 | 0.375 | 58.33 | 2.50 (latency) | 55.83 |
| 5 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | $0.050 | 0.625 | 0.625 | 0.25 | 56.25 | 5.00 (latency) | 51.25 |
| 6 | openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | $0.306 | 0.625 | 0.625 | 0.125 | 54.17 | 7.50 (latency) | 46.67 |
| 7 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | $0.457 | 0.625 | 0.125 | 0 | 43.75 | 10.00 (latency) | 33.75 |
| 8 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | $0.097 | 0 | 0.625 | 1 | 27.08 | 10.00 (quarantine_rate) | 17.08 |
| 9 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | ≥$0.712 (+1 unknown) | 0.125 | 0 | 0.875 | 22.92 | 10.00 (recovery_rate) | 12.92 |

## Raw measured values (per-pass recomputed at score time; graph from measurements.json)

| model | quarantine_rate_pass1 | recovery_rate_pass1 | latency_pass1 | retry_load_pass1 | cost_usd_pass1 | cost_unknown_calls_pass1 |
|---|---|---|---|---|---|---|
| deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0 | 0 | 253,327 | 0 | 0.05044 | 0 |
| openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0 | 0 | 258,687 | 0 | 0.306 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | 0 | 0 | 267,414 | 0 | 0.0504 | 0 |
| openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | 0 | 0 | 279,697 | 0 | 0.3073 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 300,597 | 0 | 0.0504 | 0 |
| openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | 0 | 0 | 306,125 | 0 | 0.3062 | 0 |
| zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 0 | 2.778 | 1,391,510 | 0.02778 | 0.4572 | 0 |
| alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 2.918 | 0 | 177,397 | 0 | 0.09716 | 0 |
| gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 2.377 | 16.64 | 222,468 | 0.2222 | 0.712 | 1 |

> Composite is comparable ONLY within this candidate set (average-rank Borda — adding/removing a model shifts ranks). Cost = model-pool pricing × tokens (cohort-comparable, not an invoice).
