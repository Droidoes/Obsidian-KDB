"""kdb_fts — parallel extraction/ranking system over raw source corpora (#145).

Substrate-parallel to kdb_graph: reads KDB/raw trees, keeps its own state
under <vault>/KDB/fts/ (ledger.sqlite + FTS5), writes nothing else (D3/D4).
Imports `common` only; nothing internal imports this package in v1.
"""
from __future__ import annotations
