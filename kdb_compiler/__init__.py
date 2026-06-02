"""KDB Compiler — Karpathy-style LLM knowledge-base compiler for Obsidian.

Pipeline:
    kdb_scan  ->  planner  ->  compiler  ->  validate_compile_result  ->  page_writer  ->  source_state_update

LLM produces structured JSON patch-ops; Python owns every filesystem write.

See docs/CODEBASE_OVERVIEW.md for architecture.
"""

__version__ = "0.1.0-m0"
