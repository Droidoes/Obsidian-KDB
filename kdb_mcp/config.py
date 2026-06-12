"""Path resolution for the MCP server. Package-provided, app-owned defaults."""
from __future__ import annotations

import os
from pathlib import Path

from common import paths


def default_vault_root() -> Path:
    """Vault root (contains KDB/). Delegates to common.paths
    (OBSIDIAN_VAULT_PATH env, else ~/Obsidian)."""
    return paths.vault_root()


def default_graph_path() -> Path:
    """GraphDB path: KDB_GRAPH_PATH env, else `<vault_root>/KDB/graph`.

    Deriving the graph from the vault root keeps the graph and the wiki content
    on the SAME KDB instance by default — official is ~/Obsidian/KDB/graph, the
    sandbox is ~/Obsidian/Vault-in-place-test-run/KDB/graph. Set OBSIDIAN_VAULT_PATH
    to switch both at once; KDB_GRAPH_PATH overrides the graph alone.
    """
    env = os.environ.get("KDB_GRAPH_PATH")
    return Path(env) if env else default_vault_root() / "KDB" / "graph"
