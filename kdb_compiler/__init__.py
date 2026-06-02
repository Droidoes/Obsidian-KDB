"""KDB Compiler — Karpathy-style LLM knowledge-base compiler for Obsidian.

Orchestrated by `kdb_orchestrate.py`. Per-source flow:

    kdb_scan -> enrich (Pass-1) -> compile (Pass-2: entities/LINKS_TO/SUPPORTS)
             -> repair -> canonicalize -> page_writer -> graph-sync

Finalize pass: merge -> wire_links -> detect_orphans -> cleanup.

The graph (graphdb_kdb / Kuzu) is the substrate; `context_loader` reads it
via the graph query API. `manifest.json` is the source-state metadata ledger.
LLM produces structured JSON; Python owns every filesystem write.

See docs/CODEBASE_OVERVIEW.md §5 for architecture.
"""

__version__ = "0.1.0-m0"
