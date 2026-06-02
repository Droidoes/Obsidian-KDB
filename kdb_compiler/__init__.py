"""kdb_compiler — transitional package root (Phase-B split in progress).

Leaf modules (atomic_io, call_model, call_model_retry, run_context, types,
source_io, paths, config.settings) have moved to `common`.  Remaining
modules (compiler, canonicalize, kdb_orchestrate, kdb_scan, kdb_clean,
page_writer, manifest_writer, context_loader, enrich, etc.) will migrate in
subsequent Phase-B tasks.

See docs/CODEBASE_OVERVIEW.md §5 for architecture.
"""
