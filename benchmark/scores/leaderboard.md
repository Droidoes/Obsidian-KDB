# Model leaderboard

_Hierarchical weighted Borda — §6 starting weights: quarantine 0.4 / graph 0.4 / recovery 0.1 / latency 0.1. Updated 2026-07-22T14:58:20-04:00._

| rank | model | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | graph_score ↑ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|
| 1 | openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | 0.75 | 0.75 | 0.5 | 0.9083 | 78.83 | 0.00 | 78.83 |
| 2 | openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0.75 | 0.75 | 0.6667 | 0.825 | 77.17 | 0.00 | 77.17 |
| 3 | deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0.75 | 0.75 | 0.3333 | 0.475 | 59.83 | 3.33 (latency) | 56.50 |
| 4 | deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0.75 | 0.75 | 0.1667 | 0.5167 | 59.83 | 6.67 (latency) | 53.17 |
| 5 | alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 0.3333 | 0.1667 | 1 | 0.1917 | 32.67 | 6.67 (recovery_rate) | 26.00 |
| 6 | zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 0.1667 | 0.3333 | 0 | 0.45 | 28.00 | 10.00 (latency) | 18.00 |
| 7 | gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 0.8333 | 0.1333 | 13.67 | 10.00 (quarantine_rate) | 3.67 |

## Raw measured values (scored KPIs + diagnostics / watched)

| model | quarantine_rate | recovery_rate | latency | entity_reuse | graph_connectivity | link_density | supports_density | retry_load | token_overrun_rate | repair_rung_rate | semantic_pass_rate | signal_noise_ratio | quarantine_rate_pass1 | quarantine_rate_pass2 | latency_pass1 | latency_pass2 | orphan_rate | entity_search_key_resolution | belongs_to_coverage | domain_null_rate | domain_breadth |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-5.4-mini@v0.5.7-25-ge9ca323 | 0 | 0 | 567,760 | 0.02427 | 0.2426 | 1.919 | 8.379 | 0 | 0 | 0 | 1 | 0.8056 | 0 | 0 | 306,125 | 781,557 | 0 | 0.3636 | 1 | 0 | 0.4348 |
| openai/gpt-5.4-mini@v0.5.7-2-g718e75d-dirty | 0 | 0 | 547,297 | 0.02927 | 0.1923 | 1.782 | 8.379 | 0 | 0 | 0 | 1 | 0.8056 | 0 | 0 | 258,687 | 782,833 | 0 | 0.406 | 1 | 0 | 0.4783 |
| deepseek/deepseek-v4-flash@v0.5.7-25-ge9ca323 | 0 | 0 | 579,154 | 0.01685 | 0.1456 | 1.777 | 7.5 | 0 | 0 | 0 | 1 | 0.7778 | 0 | 0 | 253,327 | 852,646 | 0 | 0.2705 | 1 | 0 | 0.4348 |
| deepseek/deepseek-v4-flash@v0.5.7-2-g718e75d-dirty | 0 | 0 | 723,787 | 0.02083 | 0.181 | 1.502 | 7.862 | 0 | 0 | 0 | 1 | 0.8056 | 0 | 0 | 300,597 | 1,069,276 | 0 | 0.2816 | 1 | 0 | 0.4348 |
| alibaba/qwen3.6-flash-us@v0.5.7-2-g718e75d-dirty | 3.92 | 2.613 | 332,763 | 0.0177 | 0.1223 | 0.8633 | 5.423 | 0.03125 | 0 | 2.613 | 0.9286 | 0.7778 | 2.918 | 4.731 | 177,397 | 458,708 | 0 | 0.1786 | 1 | 0 | 0.3913 |
| zai/glm-5-turbo@v0.5.7-2-g718e75d-dirty | 6.054 | 2.421 | 3,637,507 | 0.01342 | 0.09249 | 2.191 | 7.292 | 0.09231 | 0 | 0 | 0.8276 | 0.8056 | 0 | 10.73 | 1,391,510 | 5,372,708 | 0 | 0.2347 | 1 | 0 | 0.4348 |
| gemini/gemini-3.5-flash@v0.5.7-2-g718e75d-dirty | 10.98 | 13.51 | 485,670 | 0 | 0.09 | 1.53 | 5.882 | 0.4462 | 0 | 0 | 0.5862 | 0.8056 | 2.377 | 15.72 | 222,468 | 630,691 | 0 | 0.1324 | 1 | 0 | 0.3913 |

> Composite & graph_score are comparable ONLY within this candidate set (average-rank Borda — adding/removing a model shifts ranks). graph_score = weighted Borda of the 4 graph KPIs (connectivity 35 / link 30 / supports 20 / reuse 15).
