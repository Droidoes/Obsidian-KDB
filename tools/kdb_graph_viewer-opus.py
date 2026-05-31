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
import math
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
    "Entity": "#4C9AFF",
    "Source": "#57D9A3",
    "Domain": "#FFC400",
    "Claim": "#FF7452",
}
# Per-relationship edge colors (anything unmapped falls back to grey).
EDGE_COLORS = {
    "LINKS_TO": "#58a6ff",
    "SUPPORTS": "#3fb950",
    "BELONGS_TO": "#d29922",
    "ALIAS_OF": "#db6d28",
}


def _node_key(nid: dict) -> str:
    return f"{nid['table']}:{nid['offset']}"


# Small Obsidian-like nodes: type-tiered base + damped degree, used as the
# Cytoscape diameter. Source is capped at Entity's base (Source must not be
# bigger than Entity). Overall scale is half the earlier Codex-radius*2.
_SIZE_BASE = {"Domain": 11, "Source": 5, "Entity": 5, "Claim": 5}


def _node_size(label: str, degree: int) -> float:
    base = _SIZE_BASE.get(label, 5)
    radius = base + min(8.0, math.sqrt(degree) * 1.8)
    return round(radius, 1)


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

    # Degree precompute — drives node sizing (hubs render larger).
    degree: dict[str, int] = {}
    for e in edges:
        degree[e["data"]["source"]] = degree.get(e["data"]["source"], 0) + 1
        degree[e["data"]["target"]] = degree.get(e["data"]["target"], 0) + 1
    max_degree = 0
    for n in nodes:
        d = degree.get(n["data"]["id"], 0)
        n["data"]["degree"] = d
        n["data"]["size"] = _node_size(n["data"]["label"], d)
        max_degree = max(max_degree, d)

    summary = {"labels": label_counts, "rels": rel_counts, "max_degree": max_degree}
    Path(out_path).write_text(
        _render_html(nodes, edges, graph_path, summary), encoding="utf-8"
    )
    return len(nodes), len(edges), summary


def _render_html(nodes, edges, graph_path, summary) -> str:
    """Inject graph data into the viewer template via token replacement.

    A plain template (no f-string) keeps the CSS/JS braces literal; only the
    __TOKENS__ below are substituted.
    """
    repl = {
        "__ELEMENTS__": json.dumps(nodes + edges, default=str, separators=(",", ":")),
        "__NODE_COLORS__": json.dumps(LABEL_COLORS),
        "__EDGE_COLORS__": json.dumps(EDGE_COLORS),
        "__NODE_TYPES__": json.dumps(list(summary["labels"].keys())),
        "__EDGE_TYPES__": json.dumps(list(summary["rels"].keys())),
        "__MAX_DEGREE__": str(max(summary.get("max_degree", 1), 1)),
        "__COUNTS_LINE__": " · ".join(
            f"{k}: {v}" for k, v in {**summary["labels"], **summary["rels"]}.items()
        ),
        "__GRAPH_PATH__": str(graph_path),
    }
    html = _HTML_TEMPLATE
    for token, value in repl.items():
        html = html.replace(token, value)
    return html


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>KDB GraphDB Viewer</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.30.2/cytoscape.min.js"></script>
<script src="https://unpkg.com/layout-base@2.0.1/layout-base.js"></script>
<script src="https://unpkg.com/cose-base@2.2.0/cose-base.js"></script>
<script src="https://unpkg.com/cytoscape-fcose@2.2.0/cytoscape-fcose.js"></script>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script src="https://unpkg.com/cytoscape-navigator@2.0.2/cytoscape-navigator.js"></script>
<link href="https://unpkg.com/cytoscape-navigator@2.0.2/cytoscape.js-navigator.css" rel="stylesheet"/>
<style>
  :root{
    --bg:#1b1f23; --bar:#161a1e; --panel:#161a1e; --border:#30363d;
    --fg:#e6edf3; --muted:#8b949e; --faint:#6e7681; --accent:#58a6ff;
    --label:#e6edf3; --edgelabel:#8b949e;
  }
  body.light{
    --bg:#f6f8fa; --bar:#fff; --panel:#fff; --border:#d0d7de;
    --fg:#1f2328; --muted:#57606a; --faint:#8c959f; --accent:#0969da;
    --label:#1f2328; --edgelabel:#57606a;
  }
  html,body{margin:0;height:100%;font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--fg)}
  #bar{position:absolute;top:0;left:0;right:0;padding:8px 14px;background:var(--bar);border-bottom:1px solid var(--border);font-size:13px;z-index:20}
  #bar b{color:var(--fg)} #bar .src{color:var(--muted);font-size:11px;margin:2px 0 6px}
  .row{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px}
  .chip{display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border:1px solid var(--border);border-radius:12px;cursor:pointer;font-size:11px;user-select:none;background:transparent;color:var(--fg)}
  .chip i{display:inline-block;width:10px;height:10px;border-radius:50%}
  .chip.edge i{width:14px;height:3px;border-radius:2px}
  .chip.off{opacity:.35;text-decoration:line-through}
  .group-label{color:var(--faint);font-size:10px;text-transform:uppercase;letter-spacing:.04em;margin-right:2px}
  #search{background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--fg);padding:3px 8px;font-size:12px;width:180px}
  .btn{background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--fg);padding:3px 9px;font-size:11px;cursor:pointer}
  .btn:hover{border-color:var(--accent)}
  #hud{color:var(--muted);font-size:11px;margin-left:auto}
  #cy{position:absolute;top:96px;bottom:0;left:0;right:340px;background:var(--bg)}
  #panel{position:absolute;top:96px;bottom:0;right:0;width:340px;background:var(--panel);border-left:1px solid var(--border);overflow:auto;padding:12px;font-size:12px}
  #panel h3{margin:.2em 0;color:var(--accent)} #panel .k{color:var(--muted)}
  #panel pre{white-space:pre-wrap;word-break:break-word;margin:0;font-family:inherit}
  #panel .badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:10px;font-weight:600;color:#0d1117;margin-bottom:6px}
  #panel .nbr-head{color:var(--faint);font-size:10px;text-transform:uppercase;letter-spacing:.04em;margin:10px 0 4px}
  .neighbor-item{display:flex;align-items:center;gap:6px;padding:3px 4px;border-radius:5px;cursor:pointer;font-size:11px}
  .neighbor-item:hover{background:rgba(127,127,127,.15)}
  .neighbor-item .dot{display:inline-block;width:9px;height:9px;border-radius:50%;flex:none}
  .neighbor-item .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .neighbor-item .et{color:var(--faint);font-size:9px}
  .hint{color:var(--faint)}
  #minimap{position:absolute;right:352px;bottom:12px;width:210px;height:140px;z-index:15}
  /* override cytoscape-navigator's hardcoded 400px white corner box */
  .cytoscape-navigator{position:absolute !important;left:auto !important;top:auto !important;
    right:352px !important;bottom:12px !important;width:210px !important;height:140px !important;
    background:var(--bar) !important;border:1px solid var(--border) !important;border-radius:6px}
  .cytoscape-navigatorView{background:var(--accent) !important;opacity:.22 !important}
</style>
</head>
<body>
<div id="bar">
  <div class="row">
    <b>KDB GraphDB Viewer</b>
    <span class="src">__COUNTS_LINE__</span>
    <span id="hud"></span>
  </div>
  <div class="src">__GRAPH_PATH__</div>
  <div class="row">
    <input id="search" placeholder="Search node name… (Enter)"/>
    <span class="group-label">nodes</span><span id="nodeFilters"></span>
    <span class="group-label">edges</span><span id="edgeFilters"></span>
    <button class="btn" id="relayout">Re-run layout</button>
    <button class="btn" id="reset">Reset view</button>
    <button class="btn" id="theme">Light</button>
  </div>
</div>
<div id="cy"></div>
<div id="minimap"></div>
<div id="panel"><p class="hint">Hover a node to focus its neighbors; click for properties.<br/>Captions appear on hover or when you zoom in. Toggle chips to filter.</p></div>
<script>
  const ELEMENTS = __ELEMENTS__;
  const NODE_COLORS = __NODE_COLORS__;
  const EDGE_COLORS = __EDGE_COLORS__;
  const NODE_TYPES = __NODE_TYPES__;
  const EDGE_TYPES = __EDGE_TYPES__;
  const MAX_DEGREE = __MAX_DEGREE__;
  const NODE_FALLBACK = "#998DD9";
  const EDGE_FALLBACK = "#6e7681";

  // Layout: a D3 force simulation drives node positions (springy + packed,
  // Gemini-style) while Cytoscape renders. If D3's CDN fails, fall back to a
  // static fcose -> built-in cose layout. Never blank the page.
  const HAS_D3    = !!window.d3;
  const HAS_FCOSE = !!window.cytoscapeFcose;
  if(HAS_FCOSE){ try { cytoscape.use(window.cytoscapeFcose); } catch(e){} }

  const cy = cytoscape({
    container: document.getElementById('cy'),
    elements: ELEMENTS,
    wheelSensitivity: 0.3,
    style: [
      {selector:'node', style:{
        'background-color': ele => NODE_COLORS[ele.data('label')] || NODE_FALLBACK,
        'label':'data(name)','color':'#e6edf3','font-size':'9px','text-opacity':0,
        'text-wrap':'wrap','text-max-width':'120px','text-valign':'bottom','text-margin-y':'3px',
        'width':'data(size)',
        'height':'data(size)',
        'border-width':0}},
      {selector:'edge', style:{
        'width':1.3,
        'line-color': ele => EDGE_COLORS[ele.data('label')] || EDGE_FALLBACK,
        'target-arrow-color': ele => EDGE_COLORS[ele.data('label')] || EDGE_FALLBACK,
        'target-arrow-shape':'triangle','arrow-scale':0.8,'curve-style':'bezier',
        'label':'data(label)','font-size':'7px','color':'#8b949e','text-rotation':'autorotate',
        'text-opacity':0,'opacity':0.55}},
      {selector:'node.lbl', style:{'text-opacity':1}},
      {selector:'.dim', style:{'opacity':0.08,'text-opacity':0}},
      {selector:'node.found', style:{'border-width':4,'border-color':'#f0883e'}},
      {selector:':selected', style:{'border-width':4,'border-color':'#f0883e','line-color':'#f0883e','target-arrow-color':'#f0883e'}}
    ],
    layout: initialLayout()
  });

  function initialLayout(){
    if(HAS_D3){ return {name:'random'}; }   // D3 sim repositions immediately after
    if(HAS_FCOSE){
      return {name:'fcose', quality:'default', animate:true, animationDuration:600,
              randomize:true, nodeRepulsion:6500, idealEdgeLength:75, nodeSeparation:80, padding:40};
    }
    return {name:'cose', animate:false, nodeRepulsion:9000, idealEdgeLength:90, padding:40};
  }

  // ---- D3 force layout: springy physics + central packing; Cytoscape renders ----
  let sim = null, dN = [], dById = {};
  function sizeById(id){ const n = cy.getElementById(id); return n.nonempty() ? (n.data('size')||10) : 10; }
  function startSimulation(){
    const W = cy.width()||800, H = cy.height()||600;
    dN = cy.nodes().map(n => { const p = n.position(); return {id:n.id(), x:p.x, y:p.y}; });
    dById = {}; dN.forEach(d => dById[d.id] = d);
    const dE = cy.edges().map(e => ({source:e.source().id(), target:e.target().id()}));
    // Strong central gravity (forceX/Y) pulls every disconnected component into
    // one dense mass; short-range charge keeps nodes apart WITHIN a cluster
    // without shoving separate clusters across the canvas; collide stops overlap.
    sim = d3.forceSimulation(dN)
      .force('link', d3.forceLink(dE).id(d=>d.id).distance(42).strength(0.6))
      .force('charge', d3.forceManyBody().strength(-130).distanceMax(200))
      .force('center', d3.forceCenter(W/2, H/2))
      .force('x', d3.forceX(W/2).strength(0.22))
      .force('y', d3.forceY(H/2).strength(0.22))
      .force('collide', d3.forceCollide().radius(d => sizeById(d.id)/2 + 5))
      .alphaDecay(0.018)
      .on('tick', () => {
        for(const d of dN){ const n = cy.getElementById(d.id);
          if(n.nonempty() && !n.grabbed()) n.position({x:d.x, y:d.y}); }
      });
    setTimeout(() => cy.fit(cy.elements(':visible'), 40), 600);
    // springy drag: pin the grabbed node, reheat so neighbors follow, release on drop
    cy.on('grab','node', e => { const d = dById[e.target.id()]; if(d){ d.fx=d.x; d.fy=d.y; } sim.alphaTarget(0.3).restart(); });
    cy.on('drag','node', e => { const d = dById[e.target.id()]; if(d){ const p=e.target.position(); d.fx=p.x; d.fy=p.y; } });
    cy.on('free','node', e => { const d = dById[e.target.id()]; if(d){ d.fx=null; d.fy=null; } sim.alphaTarget(0); });
  }
  function reheat(){
    if(!sim){ return; }
    for(const d of dN){ const p = cy.getElementById(d.id).position(); d.x=p.x; d.y=p.y; }
    sim.alpha(0.9).restart();
  }
  if(HAS_D3){ startSimulation(); }

  // ---- minimap (degrade gracefully if plugin missing) ----
  try { cy.navigator({container: document.getElementById('minimap')}); }
  catch(err){ document.getElementById('minimap').style.display='none'; }

  // ---- detail panel ----
  const panel = document.getElementById('panel');
  const SKIP_PROPS = new Set(['created_at','updated_at','first_run_id','last_run_id',
                              'first_seen_at','last_seen_at','last_ingested_at']);
  function esc(s){ return String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

  function showNode(node){
    const d = node.data();
    const color = NODE_COLORS[d.label] || NODE_FALLBACK;
    let h = `<span class="badge" style="background:${color}">${esc(d.label)}</span>`;
    h += `<h3>${esc(d.name)}</h3>`;
    h += `<div><span class="k">degree:</span> ${d.degree}</div>`;
    const props = d.props || {};
    for(const [k,v] of Object.entries(props)){
      if(SKIP_PROPS.has(k)) continue;
      let disp = v===null ? '—' : String(v);
      if(disp.length > 200) disp = disp.slice(0,200)+'…';
      h += `<div><span class="k">${esc(k)}:</span> <pre style="display:inline">${esc(disp)}</pre></div>`;
    }

    // typed, clickable neighbor list
    const nbrs = [];
    node.connectedEdges().forEach(e => {
      const other = e.source().id() === node.id() ? e.target() : e.source();
      const dir = e.source().id() === node.id() ? '→' : '←';
      nbrs.push({id: other.id(), name: other.data('name'),
                 ntype: other.data('label'), etype: e.data('label'), dir});
    });
    nbrs.sort((a,b)=> a.etype.localeCompare(b.etype) || (a.name||'').localeCompare(b.name||''));
    if(nbrs.length){
      h += `<div class="nbr-head">links (${nbrs.length})</div>`;
      nbrs.slice(0,40).forEach(n => {
        const dot = NODE_COLORS[n.ntype] || NODE_FALLBACK;
        h += `<div class="neighbor-item" data-id="${esc(n.id)}">`+
             `<span class="dot" style="background:${dot}"></span>`+
             `<span class="nm">${n.dir} ${esc(n.name)}</span>`+
             `<span class="et">${esc(n.etype)}</span></div>`;
      });
      if(nbrs.length > 40) h += `<div class="hint" style="padding:4px 4px">… and ${nbrs.length-40} more</div>`;
    }
    panel.innerHTML = h;
    panel.querySelectorAll('.neighbor-item').forEach(item => {
      item.addEventListener('click', () => focusNodeById(item.dataset.id));
    });
  }

  function focusNodeById(id){
    const n = cy.getElementById(id);
    if(!n || n.empty()) return;
    clickNode = n;
    focusOn(n.closedNeighborhood());
    showNode(n);
    refreshLabels();
    cy.animate({fit:{eles:n.closedNeighborhood(), padding:80}}, {duration:400});
  }
  function showEdge(d){
    panel.innerHTML = `<span class="badge" style="background:${EDGE_COLORS[d.label]||EDGE_FALLBACK}">${d.label}</span>`+
      `<div><span class="k">source:</span> ${d.source}</div><div><span class="k">target:</span> ${d.target}</div>`;
  }

  // ---- ego-network focus + captions ----
  // [5] a node's caption shows ONLY when it is the hover- or click-selected node
  //     AND the zoom is past ZOOM_LABEL. Never otherwise.
  const ZOOM_LABEL = 1.8;
  let hoverNode = null, clickNode = null;
  function focusOn(eles){ cy.elements().addClass('dim'); eles.removeClass('dim'); }
  function clearFocus(){ cy.elements().removeClass('dim'); }
  function refreshLabels(){
    const ln = hoverNode || clickNode;
    cy.batch(() => {
      cy.nodes().removeClass('lbl');
      if(ln && ln.nonempty() && cy.zoom() >= ZOOM_LABEL){ ln.addClass('lbl'); }
    });
  }
  cy.on('zoom', refreshLabels);

  // [7] auto ego-focus on hover (not click)
  cy.on('mouseover','node', e => { hoverNode = e.target; focusOn(e.target.closedNeighborhood()); refreshLabels(); });
  cy.on('mouseout','node',  e => { hoverNode = null; clearFocus(); refreshLabels(); });

  // click pins details in the right panel
  cy.on('tap','node', e => { clickNode = e.target; showNode(e.target); refreshLabels(); });
  cy.on('tap','edge', e => showEdge(e.target.data()));
  cy.on('tap', e => { if(e.target === cy){ clickNode = null; cy.nodes().removeClass('found'); refreshLabels(); } });

  // ---- search ----
  const search = document.getElementById('search');
  search.addEventListener('keydown',e=>{
    if(e.key!=='Enter') return;
    const term = search.value.trim().toLowerCase();
    cy.nodes().removeClass('found');
    if(!term){ clearFocus(); refreshLabels(); return; }
    const hits = cy.nodes().filter(n => (n.data('name')||'').toLowerCase().includes(term));
    if(hits.length===0){ return; }
    hits.addClass('found');
    focusOn(hits.closedNeighborhood());
    refreshLabels();
    cy.animate({fit:{eles:hits.closedNeighborhood(), padding:80}}, {duration:400});
  });

  // ---- filters ----
  const hiddenNodeTypes = new Set();
  const hiddenEdgeTypes = new Set();
  function applyFilters(){
    cy.batch(()=>{
      cy.nodes().forEach(n => n.style('display', hiddenNodeTypes.has(n.data('label')) ? 'none':'element'));
      cy.edges().forEach(ed => ed.style('display', hiddenEdgeTypes.has(ed.data('label')) ? 'none':'element'));
    });
    updateHud();
  }
  function makeChip(container, label, color, isEdge, hiddenSet){
    const chip = document.createElement('span');
    chip.className = 'chip' + (isEdge?' edge':'');
    chip.innerHTML = `<i style="background:${color}"></i>${label}`;
    chip.onclick = ()=>{
      if(hiddenSet.has(label)){ hiddenSet.delete(label); chip.classList.remove('off'); }
      else { hiddenSet.add(label); chip.classList.add('off'); }
      applyFilters();
    };
    container.appendChild(chip);
  }
  const nf = document.getElementById('nodeFilters');
  NODE_TYPES.forEach(t => makeChip(nf, t, NODE_COLORS[t]||NODE_FALLBACK, false, hiddenNodeTypes));
  const ef = document.getElementById('edgeFilters');
  EDGE_TYPES.forEach(t => makeChip(ef, t, EDGE_COLORS[t]||EDGE_FALLBACK, true, hiddenEdgeTypes));

  // ---- HUD ----
  const hud = document.getElementById('hud');
  function updateHud(){
    hud.textContent = `visible: ${cy.nodes(':visible').length} nodes / ${cy.edges(':visible').length} edges`;
  }
  updateHud();

  // ---- buttons ----
  document.getElementById('relayout').onclick = ()=>{
    if(HAS_D3){ cy.layout({name:'random'}).run(); reheat(); }
    else { cy.layout(initialLayout()).run(); }
  };
  document.getElementById('reset').onclick = ()=>{
    hoverNode=null; clickNode=null; clearFocus(); cy.nodes().removeClass('found'); search.value=''; refreshLabels();
    cy.animate({fit:{eles:cy.elements(':visible'), padding:40}}, {duration:400});
  };
  const themeBtn = document.getElementById('theme');
  function applyCyTheme(light){
    cy.nodes().style('color', light ? '#1f2328' : '#e6edf3');
    cy.edges().style('color', light ? '#57606a' : '#8b949e');
  }
  themeBtn.onclick = ()=>{
    const light = document.body.classList.toggle('light');
    themeBtn.textContent = light ? 'Dark' : 'Light';
    applyCyTheme(light);
  };
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
