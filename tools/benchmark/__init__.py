"""tools.benchmark — cross-model benchmarking engine for the KDB compiler.

Separate from the production packages by design: imports from common (types,
call_model, llm_telemetry) and compiler (validators) but is never imported
by them, so the production compile path stays benchmark-free.

Scope lives in `docs/TASKS.md` Task #5 (parent) and #18–#23 (sub-tasks).
This package currently holds only the skeleton (#18); behavioral modules
(runner, scorer, scorecard) land with their respective tasks.
"""
