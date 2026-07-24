# Model leaderboard — Pass-1 (enrich) only

_Pass-1-only weighted Borda — effective weights: quarantine 0.667 / recovery 0.167 / latency 0.167 (graph inactive). Updated 2026-07-24T17:40:17-04:00._

| rank | model | cost | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|
| 1 | gemini/gemini-3.6-flash@v0.5.7-67-g9156033-dirty | $0.613 | 0.5769 | 0.6154 | 0.9231 | 64.10 | 0.00 | 64.10 |
| 2 | deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | $0.050 | 0.5769 | 0.6154 | 0.7692 | 61.54 | 0.00 | 61.54 |
| 3 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | $0.306 | 0.5769 | 0.6154 | 0.6923 | 60.26 | 0.00 | 60.26 |
| 4 | deepseek/deepseek-v4-flash@v0.5.7-58-g0690e8b | $0.050 | 0.5769 | 0.6154 | 0.6154 | 58.97 | 0.00 | 58.97 |
| 5 | deepseek/deepseek-v4-flash@v0.5.7-28-g782120b-dirty | $0.050 | 0.5769 | 0.6154 | 0.5385 | 57.69 | 0.00 | 57.69 |
| 6 | openai/gpt-5.4-mini@v0.5.7-29-gf4233f7 | $0.307 | 0.5769 | 0.6154 | 0.4615 | 56.41 | 0.77 (latency) | 55.64 |
| 7 | deepseek/deepseek-v4-flash@v0.5.7-66-gb597a21 | $0.050 | 0.5769 | 0.6154 | 0.3846 | 55.13 | 2.31 (latency) | 52.82 |
| 8 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | $0.050 | 0.5769 | 0.6154 | 0.3077 | 53.85 | 3.85 (latency) | 50.00 |
| 9 | openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | $0.306 | 0.5769 | 0.6154 | 0.2308 | 52.56 | 5.38 (latency) | 47.18 |
| 10 | openai/gpt-5.4-mini@v0.5.7-66-gb597a21-dirty | $0.303 | 0.5769 | 0.6154 | 0.1538 | 51.28 | 6.92 (latency) | 44.36 |
| 11 | openai/gpt-5.4-mini@v0.5.7-58-g0690e8b-dirty | $0.310 | 0.5769 | 0.07692 | 0.07692 | 41.03 | 8.46 (recovery_rate) | 32.56 |
| 12 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | $0.457 | 0.5769 | 0.1538 | 0 | 41.03 | 10.00 (latency) | 31.03 |
| 13 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | $0.097 | 0 | 0.6154 | 1 | 26.92 | 10.00 (quarantine_rate) | 16.92 |
| 14 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | ≥$0.712 (+1 unknown) | 0.07692 | 0 | 0.8462 | 19.23 | 10.00 (recovery_rate) | 9.23 |

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

> Composite is comparable ONLY within this candidate set (average-rank Borda — adding/removing a model shifts ranks). Cost = model-pool pricing × tokens (cohort-comparable, not an invoice).
