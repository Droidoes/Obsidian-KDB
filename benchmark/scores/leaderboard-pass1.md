# Model leaderboard — Pass-1 (enrich) only

_Pass-1-only weighted Borda — effective weights: quarantine 0.667 / recovery 0.167 / latency 0.167 (graph inactive). Updated 2026-07-22T14:28:08-04:00._

| rank | model | cost | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|
| 1 | deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | $0.050 | 0.7 | 0.7 | 0.6 | 68.33 | 0.00 | 68.33 |
| 2 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | $0.306 | 0.7 | 0.7 | 0.4 | 65.00 | 2.00 (latency) | 63.00 |
| 3 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | $0.050 | 0.7 | 0.7 | 0.2 | 61.67 | 6.00 (latency) | 55.67 |
| 4 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | $0.457 | 0.7 | 0.2 | 0 | 50.00 | 10.00 (latency) | 40.00 |
| 5 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | $0.097 | 0 | 0.7 | 1 | 28.33 | 10.00 (quarantine_rate) | 18.33 |
| 6 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | ≥$0.712 (+1 unknown) | 0.2 | 0 | 0.8 | 26.67 | 10.00 (recovery_rate) | 16.67 |

## Raw measured values (per-pass recomputed at score time; graph from measurements.json)

| model | quarantine_rate_pass1 | recovery_rate_pass1 | latency_pass1 | retry_load_pass1 | cost_usd_pass1 | cost_unknown_calls_pass1 |
|---|---|---|---|---|---|---|
| deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0 | 0 | 253,327 | 0 | 0.05044 | 0 |
| openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0 | 0 | 258,687 | 0 | 0.306 | 0 |
| deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 300,597 | 0 | 0.0504 | 0 |
| zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 0 | 2.778 | 1,391,510 | 0.02778 | 0.4572 | 0 |
| alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 2.918 | 0 | 177,397 | 0 | 0.09716 | 0 |
| gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 2.377 | 16.64 | 222,468 | 0.2222 | 0.712 | 1 |

> Composite is comparable ONLY within this candidate set (average-rank Borda — adding/removing a model shifts ranks). Cost = model-pool pricing × tokens (cohort-comparable, not an invoice).
