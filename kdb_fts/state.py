"""state — kdb_fts state-root resolution (D4).

One self-contained subtree: <vault>/KDB/fts/ (or $KDB_FTS_PATH). Mirrors the
KDB_GRAPH_PATH pattern so tests isolate via env (root conftest does this).
"""
from __future__ import annotations

import os
from pathlib import Path

from common import paths

ENV_VAR = "KDB_FTS_PATH"


def state_root() -> Path:
    """Resolve the kdb_fts state root: $KDB_FTS_PATH else <vault>/KDB/fts."""
    env = os.environ.get(ENV_VAR)
    root = Path(env).expanduser() if env else paths.kdb_root() / "fts"
    return root.resolve()
