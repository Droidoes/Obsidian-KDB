# Obsidian Vault Tools

A collection of utilities that read external sources and write structured markdown into the Obsidian vault.

## Tools

### `knowledge_graph/`
Scans the vault, computes folder-level relationships (wikilinks + keyword overlap), and renders an interactive D3.js force-directed graph. Serves it on localhost automatically.

```bash
python3 knowledge_graph/generate_knowledge_graph.py
```

### `sync_docs/` *(planned)*
Nuke-and-recopy sync: pulls all `.md` files from local git repos into `Obsidian Vault/Projects/` on a quarterly basis.

### `claude_to_obsidian/` *(planned)*
Archives Claude Code chat sessions (`~/.claude/projects/**/*.jsonl`) into `Obsidian Vault/Claude Sessions/` as structured markdown notes.

---

## Prerequisites

```bash
export OBSIDIAN_VAULT_PATH="/mnt/c/Users/fangq/OneDrive/Documents/Obsidian Vault"
```

Add to `~/.bashrc` (already set).
