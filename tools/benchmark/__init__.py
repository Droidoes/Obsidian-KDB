"""tools.benchmark — cross-model KPI leaderboard for the KDB compiler.

Separate from the production packages by design: imports from common (types,
call_model, llm_telemetry) and compiler (kpi) but is never imported by them,
so the production compile path stays benchmark-free.

Entry point: `cli.py` (`kdb-benchmark score <run_dirs…>`) — an incremental
model leaderboard over kdb-orchestrate --emit-kpis runs. Task #109.
"""
