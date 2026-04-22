"""kdb_benchmark — cross-model benchmarking engine for the KDB compiler.

Separate from `kdb_compiler` by design: imports from it (types, call_model,
validators, resp_stats_writer) but is never imported by it, so the
production compile path stays benchmark-free.

Scope lives in `docs/TASKS.md` Task #5 (parent) and #18–#23 (sub-tasks).
This package currently holds only the skeleton (#18); behavioral modules
(runner, scorer, scorecard) land with their respective tasks.
"""
