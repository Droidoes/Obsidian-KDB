"""GraphDB-KDB: Kuzu-backed multi-source knowledge-graph ontology layer.

Design surface: docs/task-graphdb-kdb-blueprint.md (D32-D40 + D-A1/A2/B1/S0-S3).
Module shape: schema.py (DDL), graphdb.py (connection + bootstrap),
types.py (Entity/Source dataclasses), cli.py (graphdb-kdb subcommands).
Ingestion / queries / analytics / verify / rebuild land in later sub-tasks.
"""
from __future__ import annotations

import os
from pathlib import Path

from kdb_graph.graphdb import GraphDB, GraphDBReadOnlyError, GraphDBSchemaError
from kdb_graph.intake import apply_compile_result
from kdb_graph.rebuilder import RebuildResult, RunOutcome, rebuild
from kdb_graph.schema import SCHEMA_VERSION
from kdb_graph.types import Entity, Source, IntakeResult
from kdb_graph.verifier import Divergence, VerifyResult

__all__ = [
    "GraphDB",
    "GraphDBSchemaError",
    "GraphDBReadOnlyError",
    "Entity",
    "Source",
    "IntakeResult",
    "VerifyResult",
    "Divergence",
    "RebuildResult",
    "RunOutcome",
    "SCHEMA_VERSION",
    "apply_compile_result",
    "rebuild",
    "default_graph_path",
]


def default_graph_path() -> Path:
    """Default location for the Kuzu GraphDB-KDB directory.

    `KDB_GRAPH_PATH` wins when set. Otherwise derives from the vault root —
    `<vault>/KDB/graph`, vault = `OBSIDIAN_VAULT_PATH` else `~/Obsidian` — so the
    graph and the wiki content live on the SAME KDB instance by default
    (official: `~/Obsidian/KDB/graph`; sandbox: `~/Obsidian/Vault-in-place-test-run/KDB/graph`).

    Supersedes the retired D35 default (`~/Droidoes/GraphDB-KDB`, a stray 2.3-era
    file) per the #113 vault-derived rule. The vault resolution is mirrored inline
    from `common/paths.py::vault_root` — do NOT import `common` here (kdb_graph's
    zero-`common` invariant).
    """
    env = os.environ.get("KDB_GRAPH_PATH")
    if env:
        return Path(env)
    vault = os.environ.get("OBSIDIAN_VAULT_PATH")
    root = Path(vault).expanduser() if vault else Path.home() / "Obsidian"
    return root.resolve() / "KDB" / "graph"
