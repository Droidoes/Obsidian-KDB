"""Path resolution for the MCP server. Package-provided, app-owned defaults."""
from __future__ import annotations

import os
from pathlib import Path

from common import paths

_DEFAULT_GRAPH_DIR = Path.home() / "Droidoes" / "GraphDB-KDB"


def default_graph_path() -> Path:
    """GraphDB directory: KDB_GRAPH_PATH env, else ~/Droidoes/GraphDB-KDB."""
    env = os.environ.get("KDB_GRAPH_PATH")
    return Path(env) if env else _DEFAULT_GRAPH_DIR


def default_vault_root() -> Path:
    """Vault root (contains KDB/wiki/). Delegates to common.paths."""
    return paths.vault_root()
