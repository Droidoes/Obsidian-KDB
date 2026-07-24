# Model leaderboard — Pass-1 (enrich) only

_Pass-1-only weighted Borda — effective weights: quarantine 0.667 / recovery 0.167 / latency 0.167 (graph inactive). Updated 2026-07-24T17:57:32-04:00._

| rank | model | cost | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|
| 1 | gemini/gemini-3.6-flash@v0.5.7-67-g9156033-dirty | $0.613 | 0.6071 | 0.6071 | 0.9286 | 66.07 | 0.00 | 66.07 |
| 2 | deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | $0.050 | 0.6071 | 0.6071 | 0.7857 | 63.69 | 0.00 | 63.69 |
| 3 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | $0.306 | 0.6071 | 0.6071 | 0.7143 | 62.50 | 0.00 | 62.50 |
| 4 | deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | $0.050 | 0.6071 | 0.6071 | 0.6429 | 61.31 | 0.00 | 61.31 |
| 5 | deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | $0.050 | 0.6071 | 0.6071 | 0.5714 | 60.12 | 0.00 | 60.12 |
| 6 | openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | $0.307 | 0.6071 | 0.6071 | 0.5 | 58.93 | 0.00 | 58.93 |
| 7 | deepseek/deepseek-v4-flash@v0.5.7-66-gb597a21 | $0.050 | 0.6071 | 0.6071 | 0.4286 | 57.74 | 1.43 (latency) | 56.31 |
| 8 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | $0.050 | 0.6071 | 0.6071 | 0.3571 | 56.55 | 2.86 (latency) | 53.69 |
| 9 | openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | $0.306 | 0.6071 | 0.6071 | 0.2857 | 55.36 | 4.29 (latency) | 51.07 |
| 10 | openai/gpt-5.4-mini@v0.5.7-66-gb597a21-dirty | $0.303 | 0.6071 | 0.6071 | 0.2143 | 54.17 | 5.71 (latency) | 48.45 |
| 11 | openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | $0.310 | 0.6071 | 0.07143 | 0.07143 | 42.86 | 8.57 (recovery_rate) | 34.29 |
| 12 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | $0.457 | 0.6071 | 0.1429 | 0 | 42.86 | 10.00 (latency) | 32.86 |
| 13 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | $0.097 | 0.07143 | 0.6071 | 1 | 31.55 | 8.57 (quarantine_rate) | 22.98 |
| 14 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | ≥$0.712 (+1 unknown) | 0.1429 | 0 | 0.8571 | 23.81 | 10.00 (recovery_rate) | 13.81 |
| 15 | alibaba/qwen3.6-flash@v0.5.7-70-g7dd5f8a | $0.097 | 0 | 0.6071 | 0.1429 | 12.50 | 10.00 (quarantine_rate) | 2.50 |

## Raw measured values (per-pass recomputed at score time; graph from measurements.json)

| model | quarantine_rate_pass1 | recovery_rate_pass1 | latency_pass1 | retry_load_pass1 | cost_usd_pass1 | cost_unknown_calls_pass1 |
|---|---|---|---|---|---|---|
| gemini/gemini-3.6-flash@v0.5.7-67-g9156033-dirty | 0 | 0 | 192,323 | 0 | 0.6128 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0 | 0 | 253,327 | 0 | 0.05044 | 0 |
| openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0 | 0 | 258,687 | 0 | 0.306 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | 0 | 0 | 264,532 | 0 | 0.05045 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | 0 | 0 | 267,414 | 0 | 0.0504 | 0 |
| openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | 0 | 0 | 279,697 | 0 | 0.3073 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-66-gb597a21 | 0 | 0 | 292,412 | 0 | 0.0504 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 300,597 | 0 | 0.0504 | 0 |
| openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | 0 | 0 | 306,125 | 0 | 0.3062 | 0 |
| openai/gpt-5.4-mini@v0.5.7-66-gb597a21-dirty | 0 | 0 | 306,358 | 0 | 0.3029 | 0 |
| openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | 0 | 2.82 | 510,151 | 0.02778 | 0.3097 | 0 |
| zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 0 | 2.778 | 1,391,510 | 0.02778 | 0.4572 | 0 |
| alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 2.918 | 0 | 177,397 | 0 | 0.09716 | 0 |
| gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 2.377 | 16.64 | 222,468 | 0.2222 | 0.712 | 1 |
| alibaba/qwen3.6-flash@v0.5.7-70-g7dd5f8a | 2.92 | 0 | 311,380 | 0 | 0.0968 | 0 |

> Composite is comparable ONLY within this candidate set (average-rank Borda — adding/removing a model shifts ranks). Cost = model-pool pricing × tokens (cohort-comparable, not an invoice).
