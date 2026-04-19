# Obsidian-KDB

Karpathy-style LLM-compiled knowledge base for Obsidian vaults.

**See [`docs/CODEBASE_OVERVIEW.md`](docs/CODEBASE_OVERVIEW.md) for the architectural North Star — all design rationale, decisions ledger, and roadmap live there.**

## What this project is

Obsidian vaults are great for human-curated notes but don't *compound* — concepts stay scattered across folders, links are manual, and new knowledge doesn't automatically strengthen connections to old knowledge.

This project implements Karpathy's [LLM Knowledge Base pattern](https://x.com/karpathy/status/2039805659525644595): raw source documents land in a `raw/` folder; an LLM compiler produces a richly cross-linked wiki in `wiki/` — summaries, concepts, articles, and bidirectional `[[wikilinks]]` — all as plain Markdown. Obsidian becomes the IDE; the LLM is the compiler.

## Architecture at a glance

Two completely separate filesystems:

| What | Where | Backup |
|---|---|---|
| **Code** (this repo) | `~/Droidoes/Obsidian-KDB/` — WSL, git | GitHub |
| **Vault data** | `~/Obsidian/KDB/` — Windows, OneDrive | OneDrive (30-day history) |

Pipeline (v1, controller-style — no mega-prompt):

```
kdb_scan  ->  planner  ->  compiler  ->  validate  ->  patch_applier  ->  manifest_update
  (Python)    (Python)    (LLM->JSON)   (Python)     (Python)            (Python)
```

**Key discipline:** The LLM emits structured JSON patch-ops only. Python owns every filesystem write. No hallucinated paths, no corrupt frontmatter, dry-run capable, fully auditable.

## Modules

### `kdb_compiler/`
The v1 pipeline. See module docstrings:
- `kdb_scan.py` — deterministic content-hash scan of `raw/`
- `planner.py` — chunks scan into per-source compile batches
- `compiler.py` — per-source LLM call; returns structured JSON
- `validate_compile_result.py` — JSON-Schema fail-fast gate
- `patch_applier.py` — writes markdown files from validated patches
- `manifest_update.py` — atomic ledger update with journal-then-pointer
- `call_model.py` + `call_model_retry.py` — provider abstraction (Anthropic / OpenAI / Gemini / Ollama) with retry/backoff

### `knowledge_graph/`
Auxiliary tool (pre-existing): renders a D3.js force-directed graph of the entire vault's folder/link structure. Independent of the KDB compiler.

```bash
python3 knowledge_graph/generate_knowledge_graph.py
```

## Status

**M0 (scaffolding)** — complete.
**M1 (deterministic layer)** — next.
**M2 (LLM compile)** — after M1.

See the [roadmap in the overview](docs/CODEBASE_OVERVIEW.md#9-roadmap) for details.

## Credits

Architecture reviewed by Claude Opus 4.7 (primary), GPT 5.4 (state model), Codex 5.3 (hardening + reference code), Grok Pro 4.2 (community impl survey), Gemini Pro 3.1 (academic treatise).
