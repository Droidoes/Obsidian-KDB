# Obsidian-KDB

Karpathy-style LLM-compiled knowledge base for Obsidian vaults. Raw source documents land in `raw/`; the LLM compiles them into a richly cross-linked Markdown wiki (`wiki/`) and a Kuzu-backed knowledge graph. The LLM emits structured JSON only — deterministic Python owns every filesystem write (no hallucinated paths, no corrupt frontmatter, dry-run capable, fully auditable). The Kuzu graph is the live ontology authority; the wiki is a rendering of it.

## Packages

- `common/` — shared leaf package: types, `call_model` (+ retry/telemetry), model pool, paths, atomic I/O
- `ingestion/` — Pass-1 enrichment (LLM classifies sources: domain, source type, key entities) + `kdb_scan`
- `compiler/` — Pass-2 compile: context loader, validate, repair, canonicalize, page writer
- `orchestrator/` — `kdb-orchestrate` conductor: the end-to-end loop, manifest writer, events, KPIs
- `kdb_graph/` — KuzuDB-backed knowledge graph: schema, intake, queries, verifier, rebuilder, snapshot, CLI
- `kdb_mcp/` — read-only FastMCP stdio server (7 tools over the live graph)
- `tools/` — operational tools: cleanup, replay, benchmark engine (`tools/benchmark/`), diagnostics, viewer

## Quickstart

```bash
./setup.sh                  # one-shot bootstrap (venv + deps + .env seed + smoke test)
pip install -e ".[dev]"     # or step-by-step install
pytest                      # full test suite (skips slow bench tests by default)
```

Run the full pipeline end-to-end (the main entry point):

```bash
kdb-orchestrate
```

## Documentation

- [`docs/CODEBASE_OVERVIEW.md`](docs/CODEBASE_OVERVIEW.md) — architectural North Star (read before any code change)
- [`docs/TASKS.md`](docs/TASKS.md) — task ledger
- [`docs/RELEASES.md`](docs/RELEASES.md) — version history
