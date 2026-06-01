#!/usr/bin/env python3
"""kdb_graph_viewer — export a Kuzu GraphDB to a self-contained interactive HTML.

Single-command builder: reads the Kuzu graph directly, emits a library-neutral
nodes/edges/summary structure, and injects it into the D3 viewer template
(`kdb_graph_viewer_template.html` — derived from the #97 bake-off winner, node
scale 2/3). Self-loops (a node linking to itself) are skipped. Read-only:
double-click the output HTML in a browser to explore the graph — no server.

The original bake-off Gemini viewer (pure form, full-scale nodes, and the
2-stage `export_graph.py` + `build_gemini.py` pipeline) is preserved under
`tools/viewer-bakeoff/` as a fallback.

Usage:
    python tools/kdb_graph_viewer.py --graph-path <kuzu-db> [--out graph-view.html]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running directly: add the repo root (tools/viewer/ -> parents[2]) to path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from graphdb_kdb.graphdb import GraphDB  # noqa: E402

SKIP_NODE_TABLES = {"_SchemaMeta"}
# Field preference order when choosing a node's on-screen display name.
DISPLAY_FIELDS = ("title", "name", "slug", "source_id", "id", "text", "label")
TEMPLATE_PATH = Path(__file__).resolve().parent / "kdb_graph_viewer_template.html"
DATA_TOKEN = "/*__GRAPH_DATA__*/"


def _node_key(nid: dict) -> str:
    return f"{nid['table']}:{nid['offset']}"


def _display_name(props: dict, fallback: str) -> str:
    for f in DISPLAY_FIELDS:
        v = props.get(f)
        if isinstance(v, str) and v.strip():
            return v
    return fallback


def export(graph_path: str) -> dict:
    """Read the Kuzu graph into the neutral viewer structure (self-loops skipped)."""
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
                if src == tgt:
                    continue  # skip self-loops (a node linking to itself renders as a loop)
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


def render_html(data: dict, template_path: Path = TEMPLATE_PATH) -> str:
    """Inject the neutral graph data into the viewer template at DATA_TOKEN."""
    template = Path(template_path).read_text(encoding="utf-8")
    if DATA_TOKEN not in template:
        raise ValueError(f"data token {DATA_TOKEN!r} not found in template {template_path}")
    graph_json = json.dumps(data, separators=(",", ":"), default=str)
    return template.replace(DATA_TOKEN, graph_json, 1)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Export a Kuzu GraphDB to interactive HTML.")
    p.add_argument("--graph-path", required=True, help="Path to the Kuzu database file")
    p.add_argument("--out", default=None, help="Output HTML path (default: <graph>-view.html)")
    args = p.parse_args(argv)
    out = args.out or (str(Path(args.graph_path).with_suffix("")) + "-view.html")
    data = export(args.graph_path)
    Path(out).write_text(render_html(data), encoding="utf-8")
    s = data["summary"]
    print(f"Wrote {out}")
    print(f"  {len(data['nodes'])} nodes, {len(data['edges'])} edges")
    print(f"  node_types: {s['node_types']}")
    print(f"  edge_types: {s['edge_types']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
