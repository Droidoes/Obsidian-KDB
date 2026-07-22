# Model leaderboard

_Hierarchical weighted Borda — §6 starting weights: quarantine 0.4 / graph 0.4 / recovery 0.1 / latency 0.1. Updated 2026-07-22T00:00:00._

| rank | model | quarantine_rate ↓ | recovery_rate ↓ | latency ↓ | graph_score ↑ | pre-pen | PENALTY | score (0-100) |
|---|---|---|---|---|---|---|---|---|
| 1 | prov/a@unversioned | 1 | 1 | 0.5 | 1 | 82.00 | 2.00 (latency) | 80.00 |
| 2 | prov/b@unversioned | 0 | 0 | 1 | 0 | 50.00 | 10.00 (graph) | 40.00 |

## Raw measured values (scored KPIs + diagnostics / watched)

| model | quarantine_rate | recovery_rate | latency | entity_reuse | graph_connectivity | link_density | supports_density | signal_noise_ratio |
|---|---|---|---|---|---|---|---|---|
| prov/a@unversioned | 0 | 0 | 100 | 0.1 | 0.2 | 2 | 5 | 0.8 |
| prov/b@unversioned | 5 | 3 | 900 | 0.3 | 0.1 | 1 | 3 | 0.7 |

> Composite & graph_score are comparable ONLY within this candidate set (average-rank Borda — adding/removing a model shifts ranks). graph_score = weighted Borda of the 4 graph KPIs (connectivity 35 / link 30 / supports 20 / reuse 15).
