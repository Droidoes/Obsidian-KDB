#!/usr/bin/env python3
"""export_graph — dump a Kuzu GraphDB to a library-neutral nodes/edges JSON.

Render-only viewer bake-off (#97) data producer. Read-only. Emits:

    {"nodes": [{"id","type","name","props":{...}}],
     "edges": [{"id","source","target","type"}]}

`type` is the Kuzu table/label (Source/Entity/Domain/Claim for nodes;
LINKS_TO/SUPPORTS/BELONGS_TO/ALIAS_OF/... for edges). `name` is a
human display label chosen from the first present DISPLAY_FIELD.

Usage:
    python3 tools/viewer-bakeoff/export_graph.py --graph-path <kuzu-db> --out graph-export.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # tools/viewer/bakeoff/ -> repo root
from kdb_graph.graphdb import GraphDB  # noqa: E402

SKIP_NODE_TABLES = {"_SchemaMeta"}
DISPLAY_FIELDS = ("title", "name", "slug", "source_id", "id", "text", "label")


def _node_key(nid: dict) -> str:
    return f"{nid['table']}:{nid['offset']}"


def _display_name(props: dict, fallback: str) -> str:
    for f in DISPLAY_FIELDS:
        v = props.get(f)
        if isinstance(v, str) and v.strip():
            return v
    return fallback


def export(graph_path: str) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    label_counts: dict[str, int] = {}
    rel_counts: dict[str, int] = {}

    with GraphDB(graph_path, read_only=True) as g:
        conn = g.conn
        node_tables: list[str] = []
        rel_tables: list[str] = []
        res = conn.execute("CALL show_tables() RETURN *")
        while res.has_next():
            row = res.get_next()
            name, kind = row[1], row[2]
            if kind == "NODE" and name not in SKIP_NODE_TABLES:
                node_tables.append(name)
            elif kind == "REL":
                rel_tables.append(name)

        for tbl in node_tables:
            res = conn.execute(f"MATCH (n:`{tbl}`) RETURN n")
            while res.has_next():
                node = res.get_next()[0]
                nid = node.get("_id")
                lbl = node.get("_label", tbl)
                props = {k: v for k, v in node.items() if not k.startswith("_")}
                # #115 Phase 3 (D-115-12): Entity.confidence is logically
                # deprecated — never exported, even when the dead Kuzu
                # column still holds legacy values.
                if lbl == "Entity":
                    props.pop("confidence", None)
                nodes.append({
                    "id": _node_key(nid),
                    "type": lbl,
                    "name": _display_name(props, lbl),
                    "props": props,
                })
                label_counts[lbl] = label_counts.get(lbl, 0) + 1

        for tbl in rel_tables:
            try:
                res = conn.execute(f"MATCH (a)-[e:`{tbl}`]->(b) RETURN a, b")
            except Exception:
                continue
            while res.has_next():
                a, b = res.get_next()
                src, tgt = _node_key(a["_id"]), _node_key(b["_id"])
                edges.append({
                    "id": f"{tbl}:{src}->{tgt}",
                    "source": src,
                    "target": tgt,
                    "type": tbl,
                })
                rel_counts[tbl] = rel_counts.get(tbl, 0) + 1

    return {
        "nodes": nodes,
        "edges": edges,
        "summary": {"node_types": label_counts, "edge_types": rel_counts},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph-path", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    data = export(args.graph_path)
    Path(args.out).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    s = data["summary"]
    print(f"exported {len(data['nodes'])} nodes / {len(data['edges'])} edges → {args.out}")
    print(f"  node_types: {s['node_types']}")
    print(f"  edge_types: {s['edge_types']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
