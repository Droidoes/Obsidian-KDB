"""GraphDB-KDB: Kuzu-backed multi-source knowledge-graph ontology layer.

Design surface: docs/task-graphdb-kdb-blueprint.md (D32-D40).
Module shape: schema.py (DDL), graphdb.py (connection + bootstrap),
types.py (Page/Source dataclasses), cli.py (graphdb-kdb subcommands).
Ingestion / queries / analytics / verify / rebuild land in later sub-tasks.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphdb_kdb.graphdb import GraphDB, GraphDBSchemaError
from graphdb_kdb.ingestor import apply_compile_result
from graphdb_kdb.schema import SCHEMA_VERSION
from graphdb_kdb.types import Page, Source, SyncResult
from graphdb_kdb.verifier import Divergence, VerifyResult

__all__ = [
    "GraphDB",
    "GraphDBSchemaError",
    "Page",
    "Source",
    "SyncResult",
    "VerifyResult",
    "Divergence",
    "SCHEMA_VERSION",
    "apply_compile_result",
    "default_graph_path",
]


def default_graph_path() -> Path:
    """Default location for the Kuzu GraphDB-KDB directory.

    D35: sibling to Obsidian-KDB under the active projects root, not OneDrive-synced.
    Override via the `KDB_GRAPH_PATH` environment variable.
    """
    env = os.environ.get("KDB_GRAPH_PATH")
    if env:
        return Path(env)
    return Path.home() / "Droidoes" / "GraphDB-KDB"
