#!/usr/bin/env python3
"""kdb_graph_viewer — export a Kuzu GraphDB to a self-contained interactive HTML.

Read-only. Dumps every node + relationship table and embeds the result in a
single HTML file rendered with Cytoscape.js (loaded from CDN). Double-click the
HTML in a browser to explore the graph visually — no server required.

This is a SNAPSHOT viewer (Option B per the 2026-05-29 design discussion): it
captures the graph at export time. Re-run to refresh after a new compile.

Usage:
    python tools/kdb_graph_viewer.py --graph-path <kuzu-db-file> [--out graph-view.html]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running directly from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from graphdb_kdb.graphdb import GraphDB  # noqa: E402

SKIP_NODE_TABLES = {"_SchemaMeta"}
# Field preference order when choosing a node's on-screen display name.
DISPLAY_FIELDS = ("title", "name", "slug", "source_id", "id", "text", "label")
# Per-label node colors (anything unmapped falls back to grey).
LABEL_COLORS = {
    "Source": "#4C9AFF",
    "Entity": "#57D9A3",
    "Domain": "#FFC400",
    "Claim": "#FF7452",
}


def _node_key(nid: dict) -> str:
    return f"{nid['table']}:{nid['offset']}"


def _display_name(label: str, props: dict) -> str:
    if label == "Source":
        sid = props.get("source_id") or ""
        return sid.split("/")[-1] or sid or label
    for field in DISPLAY_FIELDS:
        val = props.get(field)
        if val:
            return str(val)
    return label


def export(graph_path: str, out_path: str) -> tuple[int, int, dict]:
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
                    "data": {
                        "id": _node_key(nid),
                        "label": lbl,
                        "name": _display_name(lbl, props),
                        "props": props,
                    }
                })
                label_counts[lbl] = label_counts.get(lbl, 0) + 1

        for tbl in rel_tables:
            try:
                res = conn.execute(f"MATCH (a)-[e:`{tbl}`]->(b) RETURN a, b")
            except Exception:
                continue
            while res.has_next():
                a, b = res.get_next()
                edges.append({
                    "data": {
                        "id": f"{tbl}:{_node_key(a['_id'])}->{_node_key(b['_id'])}",
                        "source": _node_key(a["_id"]),
                        "target": _node_key(b["_id"]),
                        "label": tbl,
                    }
                })
                rel_counts[tbl] = rel_counts.get(tbl, 0) + 1

    summary = {"labels": label_counts, "rels": rel_counts}
    Path(out_path).write_text(
        _render_html(nodes, edges, graph_path, summary), encoding="utf-8"
    )
    return len(nodes), len(edges), summary


def _render_html(nodes, edges, graph_path, summary) -> str:
    elements = json.dumps(nodes + edges, default=str)
    colors = json.dumps(LABEL_COLORS)
    counts_line = " · ".join(
        f"{k}: {v}" for k, v in {**summary["labels"], **summary["rels"]}.items()
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>KDB GraphDB Viewer</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.30.2/cytoscape.min.js"></script>
<style>
  html,body{{margin:0;height:100%;font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#1b1f23;color:#e6edf3}}
  #bar{{padding:8px 14px;background:#161a1e;border-bottom:1px solid #30363d;font-size:13px}}
  #bar b{{color:#fff}} #bar .src{{color:#8b949e;font-size:11px}}
  #legend span{{display:inline-block;margin-right:12px}}
  #legend i{{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:4px;vertical-align:middle}}
  #cy{{position:absolute;top:74px;bottom:0;left:0;right:340px}}
  #panel{{position:absolute;top:74px;bottom:0;right:0;width:340px;background:#161a1e;border-left:1px solid #30363d;overflow:auto;padding:12px;font-size:12px}}
  #panel h3{{margin:.2em 0;color:#58a6ff}} #panel .k{{color:#8b949e}} #panel pre{{white-space:pre-wrap;word-break:break-word}}
  .hint{{color:#6e7681}}
</style>
</head>
<body>
<div id="bar">
  <b>KDB GraphDB Viewer</b> &nbsp; {counts_line}
  <div class="src">{graph_path}</div>
  <div id="legend"></div>
</div>
<div id="cy"></div>
<div id="panel"><p class="hint">Click a node or edge to inspect its properties.<br/>Scroll to zoom, drag to pan.</p></div>
<script>
  const ELEMENTS = {elements};
  const COLORS = {colors};
  const fallback = "#998DD9";
  const legend = document.getElementById('legend');
  Object.entries(COLORS).forEach(([k,v])=>{{
    const s=document.createElement('span');s.innerHTML=`<i style="background:${{v}}"></i>${{k}}`;legend.appendChild(s);
  }});
  const cy = cytoscape({{
    container: document.getElementById('cy'),
    elements: ELEMENTS,
    style: [
      {{selector:'node', style:{{
        'background-color': ele => COLORS[ele.data('label')] || fallback,
        'label':'data(name)','color':'#e6edf3','font-size':'9px',
        'text-wrap':'wrap','text-max-width':'110px','text-valign':'bottom','text-margin-y':'3px',
        'width':18,'height':18}}}},
      {{selector:'edge', style:{{
        'width':1.3,'line-color':'#444c56','target-arrow-color':'#444c56',
        'target-arrow-shape':'triangle','curve-style':'bezier',
        'label':'data(label)','font-size':'7px','color':'#6e7681','text-rotation':'autorotate'}}}},
      {{selector:':selected', style:{{'background-color':'#f0883e','line-color':'#f0883e','target-arrow-color':'#f0883e'}}}}
    ],
    layout: {{name:'cose', animate:false, nodeRepulsion:9000, idealEdgeLength:90, padding:30}}
  }});
  const panel = document.getElementById('panel');
  function show(title, data){{
    let h=`<h3>${{title}}</h3>`;
    for(const [k,v] of Object.entries(data)){{
      h+=`<div><span class="k">${{k}}:</span> <pre style="display:inline">${{v===null?'null':v}}</pre></div>`;
    }}
    panel.innerHTML=h;
  }}
  cy.on('tap','node',e=>{{const d=e.target.data();show(`${{d.label}} — ${{d.name}}`, d.props||{{}});}});
  cy.on('tap','edge',e=>{{const d=e.target.data();show(`Edge: ${{d.label}}`, {{source:d.source,target:d.target}});}});
</script>
</body>
</html>
"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Export a Kuzu GraphDB to interactive HTML.")
    p.add_argument("--graph-path", required=True, help="Path to the Kuzu database file")
    p.add_argument("--out", default=None, help="Output HTML path (default: <graph>-view.html)")
    args = p.parse_args(argv)
    out = args.out or (str(Path(args.graph_path).with_suffix("")) + "-view.html")
    n, e, summary = export(args.graph_path, out)
    print(f"Wrote {out}")
    print(f"  {n} nodes, {e} edges")
    print(f"  labels: {summary['labels']}")
    print(f"  rels:   {summary['rels']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
