#!/usr/bin/env python3
"""Build the GraphDB viewer HTML from a graph-export JSON file.

Usage:
    python3 tools/viewer-bakeoff/build_viewer.py \
        --data tools/viewer-bakeoff/graph-export-run3.json \
        --out tools/viewer-bakeoff/kdb-graph-viewer-deepseek.html
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build(in_path: str, out_path: str) -> None:
    raw = Path(in_path).read_text(encoding="utf-8")
    data = json.loads(raw)
    nodes_json = json.dumps(data["nodes"], default=str, separators=(",", ":"))
    edges_json = json.dumps(data["edges"], default=str, separators=(",", ":"))
    summary = data.get("summary", {})
    n_ent = summary.get("node_types", {}).get("Entity", 0)
    n_src = summary.get("node_types", {}).get("Source", 0)
    n_dom = summary.get("node_types", {}).get("Domain", 0)
    n_edges = (summary.get("edge_types", {}).get("LINKS_TO", 0) +
               summary.get("edge_types", {}).get("SUPPORTS", 0) +
               summary.get("edge_types", {}).get("BELONGS_TO", 0))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>KDB Graph Viewer</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#e6edf3;overflow:hidden;height:100vh;width:100vw}}
#canvas{{position:absolute;top:0;left:0;width:100%;height:100%}}
.link{{stroke-opacity:.22;fill:none}}
.link.LINKS_TO{{stroke:#58a6ff}}
.link.SUPPORTS{{stroke:#3fb950}}
.link.BELONGS_TO{{stroke:#d2991d}}
#tip{{position:absolute;pointer-events:none;background:rgba(13,17,23,.97);border:1px solid #30363d;border-radius:8px;padding:12px 16px;max-width:380px;font-size:12px;line-height:1.55;display:none;z-index:200;box-shadow:0 8px 30px rgba(0,0,0,.6)}}
#tip h3{{font-size:13px;font-weight:700;margin-bottom:6px;word-break:break-word}}
#tip .tag{{display:inline-block;padding:1px 7px;border-radius:10px;font-size:10px;font-weight:600;margin-right:4px;margin-top:6px}}
#panel{{position:absolute;top:0;right:0;width:340px;height:100%;background:rgba(13,17,23,.95);border-left:1px solid #30363d;overflow-y:auto;padding:16px;font-size:12px;z-index:100;transform:translateX(100%);transition:transform .25s ease}}
#panel.open{{transform:translateX(0)}}
#panel h2{{font-size:15px;font-weight:700;margin-bottom:4px;word-break:break-word}}
#panel .type-badge{{display:inline-block;padding:2px 10px;border-radius:12px;font-size:10px;font-weight:700;margin-bottom:12px}}
#panel .props-table{{width:100%;border-collapse:collapse;margin-top:8px}}
#panel .props-table td{{padding:3px 0;vertical-align:top;border-bottom:1px solid #21262d}}
#panel .props-table .pk{{color:#8b949e;width:100px;font-size:10px}}
#panel .props-table .pv{{font-size:11px;word-break:break-word}}
#panel .conns{{margin-top:14px}}
#panel .conns h4{{font-size:11px;color:#8b949e;margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em}}
#panel .conn-item{{display:block;padding:3px 6px;margin:2px 0;border-radius:4px;font-size:11px;cursor:pointer;transition:background .15s}}
#panel .conn-item:hover{{background:#1f2937}}
#panel .close-btn{{position:sticky;top:0;float:right;background:none;border:1px solid #30363d;color:#8b949e;border-radius:4px;padding:4px 10px;cursor:pointer;font-size:16px;line-height:1}}
#panel .close-btn:hover{{color:#e6edf3;border-color:#58a6ff}}
#topbar{{position:absolute;top:12px;left:12px;z-index:90;pointer-events:none}}
#topbar h1{{font-size:17px;font-weight:700;color:#e6edf3}}
#topbar .sub{{font-size:10px;color:#8b949e;margin-top:2px}}
#search-wrap{{position:absolute;top:14px;left:50%;transform:translateX(-50%);z-index:90;display:flex;align-items:center;gap:6px}}
#search{{width:280px;padding:7px 12px;background:#161b22;border:1px solid #30363d;border-radius:20px;color:#e6edf3;font-size:12px;outline:none;transition:border .2s}}
#search:focus{{border-color:#58a6ff}}
#search-clear{{background:none;border:none;color:#8b949e;cursor:pointer;font-size:16px;display:none;padding:2px 6px}}
#search-count{{font-size:10px;color:#8b949e;white-space:nowrap}}
#legend{{position:absolute;bottom:16px;left:16px;z-index:90;background:rgba(13,17,23,.92);border:1px solid #30363d;border-radius:10px;padding:12px 16px;font-size:11px}}
#legend h4{{font-size:11px;font-weight:700;margin-bottom:8px;text-transform:uppercase;letter-spacing:.05em;color:#e6edf3}}
.leg-row{{display:flex;align-items:center;gap:8px;margin-bottom:5px;color:#8b949e}}
.leg-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
.leg-line{{width:22px;height:2px;flex-shrink:0;border-radius:1px}}
#filters{{position:absolute;top:14px;right:14px;z-index:90;background:rgba(13,17,23,.92);border:1px solid #30363d;border-radius:10px;padding:12px 14px;font-size:11px}}
#filters h4{{font-size:10px;font-weight:700;margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em;color:#8b949e}}
.filter-group{{margin-bottom:8px}}
.fbtn{{display:inline-block;padding:3px 9px;margin:2px 3px 2px 0;background:#161b22;border:1px solid #30363d;border-radius:12px;color:#8b949e;cursor:pointer;font-size:10px;transition:all .15s;user-select:none}}
.fbtn.on{{border-color:#58a6ff;color:#58a6ff;background:#1f2937}}
.fbtn:hover:not(.on){{border-color:#555}}
#reset-btn{{display:block;width:100%;margin-top:8px;padding:4px 0;background:#21262d;border:1px solid #30363d;border-radius:6px;color:#8b949e;cursor:pointer;font-size:10px;transition:all .15s}}
#reset-btn:hover{{background:#30363d;color:#e6edf3}}
#minimap{{position:absolute;bottom:16px;right:16px;z-index:90;border:1px solid #30363d;border-radius:8px;overflow:hidden;opacity:.75;transition:opacity .2s;background:#0d1117}}
#minimap:hover{{opacity:1}}
#minimap canvas{{display:block}}
#stats{{position:absolute;bottom:16px;left:50%;transform:translateX(-50%);z-index:90;background:rgba(13,17,23,.92);border:1px solid #30363d;border-radius:10px;padding:8px 16px;font-size:11px;color:#8b949e;display:flex;gap:20px}}
#stats span{{font-weight:700;color:#e6edf3}}
#loading{{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);z-index:300;font-size:14px;color:#8b949e;transition:opacity .3s}}
</style>
</head>
<body>
<div id="topbar"><h1>KDB Knowledge Graph</h1><div class="sub">{n_ent + n_src + n_dom} nodes · {n_edges} edges · scroll to zoom · drag to pan</div></div>
<div id="search-wrap"><input id="search" type="text" placeholder="Search by name…"/><button id="search-clear">&times;</button><span id="search-count"></span></div>
<div id="filters"><h4>Node Types</h4><div class="filter-group" id="node-filters"></div><h4>Edge Types</h4><div class="filter-group" id="edge-filters"></div><button id="reset-btn">Reset View</button></div>
<div id="legend"><h4>Legend</h4><div class="leg-row"><div class="leg-dot" style="background:#57D9A3"></div>Entity</div><div class="leg-row"><div class="leg-dot" style="background:#4C9AFF"></div>Source</div><div class="leg-row"><div class="leg-dot" style="background:#FFC400"></div>Domain</div><div style="margin-top:8px;border-top:1px solid #21262d;padding-top:6px"><div class="leg-row"><div class="leg-line" style="background:#58a6ff"></div>LINKS_TO</div><div class="leg-row"><div class="leg-line" style="background:#3fb950"></div>SUPPORTS</div><div class="leg-row"><div class="leg-line" style="background:#d2991d"></div>BELONGS_TO</div></div></div>
<div id="stats"><div>Entities <span id="stat-entity">{n_ent}</span></div><div>Sources <span id="stat-source">{n_src}</span></div><div>Domains <span id="stat-domain">{n_dom}</span></div><div>Edges <span id="stat-edges">{n_edges}</span></div></div>
<div id="minimap"><canvas></canvas></div>
<svg id="canvas"></svg>
<div id="tip"></div>
<div id="panel"><button class="close-btn" onclick="closePanel()">&times;</button><div id="panel-content"></div></div>
<div id="loading">Building graph…</div>
<script>
const GRAPH_DATA = {{"nodes":{nodes_json},"edges":{edges_json}}};
const NODES = GRAPH_DATA.nodes;
const EDGES = GRAPH_DATA.edges;

// ── Colors ───────────────────────────────────────────────────────────────
const TC = {{Entity:"#57D9A3",Source:"#4C9AFF",Domain:"#FFC400",Claim:"#FF7452"}};
const EC = {{LINKS_TO:"#58a6ff",SUPPORTS:"#3fb950",BELONGS_TO:"#d2991d",ALIAS_OF:"#db6d28"}};
const FC = "#8b949e";

// ── Pre-process ──────────────────────────────────────────────────────────
const nodeMap = new Map();
NODES.forEach(n => {{ n._deg=0; n._out=0; n._in=0; nodeMap.set(n.id,n); }});
EDGES.forEach(e => {{
  const s=nodeMap.get(e.source), t=nodeMap.get(e.target);
  if(s){{ s._deg++; s._out++; }} if(t){{ t._deg++; t._in++; }}
}});
NODES.forEach(n => {{
  const d=n._deg||0;
  n._r=Math.max(n.type==="Source"?8:n.type==="Domain"?10:6, Math.min(32,6+Math.log(d+1)*4.2));
  n._label=n.name.length>42?n.name.slice(0,40)+"…":n.name;
}});

// ── Filter UI ────────────────────────────────────────────────────────────
const nodeTypes=[...new Set(NODES.map(n=>n.type))].sort();
const edgeTypes=[...new Set(EDGES.map(e=>e.type))].sort();
const nfDiv=document.getElementById("node-filters");
nodeTypes.forEach(nt=>{{
  const b=document.createElement("span");b.className="fbtn on";b.dataset.type=nt;
  b.style.borderColor=TC[nt]||FC;b.textContent=nt;
  b.addEventListener("click",()=>{{b.classList.toggle("on");applyFilters();}});
  nfDiv.appendChild(b);
}});
const efDiv=document.getElementById("edge-filters");
edgeTypes.forEach(et=>{{
  const b=document.createElement("span");b.className="fbtn on";b.dataset.type=et;
  b.style.borderColor=EC[et]||FC;b.textContent=et.replace(/_/g," ");
  b.addEventListener("click",()=>{{b.classList.toggle("on");applyFilters();}});
  efDiv.appendChild(b);
}});

// ── SVG + zoom + minimap ─────────────────────────────────────────────────
const W=window.innerWidth,H=window.innerHeight;
const svg=d3.select("#canvas").attr("width",W).attr("height",H);
const g=svg.append("g");
const zoom=d3.zoom().scaleExtent([0.08,8]).on("zoom",e=>{{g.attr("transform",e.transform);mmap(e.transform);}});
svg.call(zoom);

const mmCv=document.querySelector("#minimap canvas");
const mmCx=mmCv.getContext("2d");
const MW=160,MH=120;mmCv.width=MW;mmCv.height=MH;
function mmap(t){{
  mmCx.clearRect(0,0,MW,MH);mmCx.fillStyle="#0d1117";mmCx.fillRect(0,0,MW,MH);
  let mnX=1/0,mxX=-1/0,mnY=1/0,mxY=-1/0;
  NODES.forEach(n=>{{if(n.x<mnX)mnX=n.x;if(n.x>mxX)mxX=n.x;if(n.y<mnY)mnY=n.y;if(n.y>mxY)mxY=n.y;}});
  const p=20,s=Math.min(MW/(mxX-mnX+p*2),MH/(mxY-mnY+p*2));
  const ox=(MW-(mxX-mnX)*s)/2-mnX*s,oy=(MH-(mxY-mnY)*s)/2-mnY*s;
  NODES.forEach(n=>{{mmCx.fillStyle=(TC[n.type]||FC)+"88";mmCx.beginPath();mmCx.arc(n.x*s+ox,n.y*s+oy,1.5,0,6.28);mmCx.fill();}});
  if(t){{const vx=-t.x/t.k,vy=-t.y/t.k,vw=W/t.k,vh=H/t.k;mmCx.strokeStyle="#58a6ff88";mmCx.lineWidth=1;mmCx.strokeRect(vx*s+ox,vy*s+oy,vw*s,vh*s);}}
}}

// ── Arrow markers ────────────────────────────────────────────────────────
const defs=svg.append("defs");
edgeTypes.forEach(et=>defs.append("marker").attr("id","a-"+et).attr("viewBox","0 -5 10 10").attr("refX",18).attr("refY",0).attr("markerWidth",5).attr("markerHeight",5).attr("orient","auto").append("path").attr("d","M0,-4L10,0L0,4").attr("fill",EC[et]||FC));

// ── Force simulation ─────────────────────────────────────────────────────
const sim=d3.forceSimulation(NODES)
  .force("link",d3.forceLink(EDGES).id(d=>d.id).distance(d=>d.type==="SUPPORTS"?90:d.type==="BELONGS_TO"?120:70).strength(d=>d.type==="SUPPORTS"?.3:d.type==="BELONGS_TO"?.5:.6))
  .force("charge",d3.forceManyBody().strength(d=>-150-d._r*14))
  .force("center",d3.forceCenter(W/2,H/2))
  .force("collide",d3.forceCollide().radius(d=>d._r+5))
  .force("x",d3.forceX(W/2).strength(.025))
  .force("y",d3.forceY(H/2).strength(.025));

// ── Render: flat DOM — cx/cy on circles, x/y on text ────────────────────
const nodeLayer=g.append("g").attr("class","nodes-layer");

const linkSel=g.append("g").selectAll("line").data(EDGES).join("line")
  .attr("class",d=>"link "+d.type)
  .attr("marker-end",d=>"url(#a-"+d.type+")")
  .attr("stroke-width",d=>d.type==="SUPPORTS"?1.2:d.type==="LINKS_TO"?1.6:1.4);

const nodeC=nodeLayer.selectAll("circle.nc").data(NODES).join("circle")
  .attr("class",d=>"nc node-"+d.type).attr("r",d=>d._r)
  .attr("fill",d=>(TC[d.type]||FC)+"88")
  .attr("stroke",d=>TC[d.type]||FC)
  .attr("stroke-width",d=>d.type==="Domain"?3:d.type==="Source"?2:1.8)
  .style("cursor","pointer")
  .call(d3.drag()
    .on("start",(e,d)=>{{if(!e.active)sim.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y;}})
    .on("drag",(e,d)=>{{d.fx=e.x;d.fy=e.y;}})
    .on("end",(e,d)=>{{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}}));

const nodeD=nodeLayer.selectAll("circle.nd").data(NODES.filter(d=>d._r>=8)).join("circle")
  .attr("class","nd").attr("r",d=>d._r*.32)
  .attr("fill",d=>TC[d.type]||FC).attr("opacity",.85)
  .style("pointer-events","none");

const nodeL=nodeLayer.selectAll("text.nl").data(NODES).join("text")
  .attr("class",d=>"nl node-"+d.type).text(d=>d._label)
  .attr("text-anchor","middle")
  .attr("font-size",d=>d._r>22?"10px":d._r>14?"8px":"7px")
  .attr("fill","#c9d1d9").style("pointer-events","none");

// ── Interaction ──────────────────────────────────────────────────────────
const tip=document.getElementById("tip");
const panel=document.getElementById("panel");
const panelContent=document.getElementById("panel-content");

nodeC.on("mouseover",function(e,d){{
  const c=TC[d.type]||FC;
  tip.innerHTML=`<h3 style="color:${{c}}">${{d._label}}</h3><div style="margin-bottom:4px"><span class="tag" style="background:${{c}}22;color:${{c}}">${{d.type}}</span><span style="font-size:10px;color:#8b949e">deg: ${{d._deg||0}}</span></div><div style="color:#8b949e">Click for details</div>`;
  tip.style.display="block";moveTip(e);
  d3.select(this).attr("stroke-width",(d.type==="Domain"?3:d.type==="Source"?2:1.8)+2);
}}).on("mousemove",moveTip).on("mouseout",function(e,d){{
  tip.style.display="none";
  d3.select(this).attr("stroke-width",d.type==="Domain"?3:d.type==="Source"?2:1.8);
}}).on("click",function(e,d){{showPanel(d);}});

function moveTip(e){{tip.style.left=Math.min(e.clientX+16,innerWidth-400)+"px";tip.style.top=Math.min(e.clientY-10,innerHeight-200)+"px";}}

let activeNode=null;
function showPanel(d){{
  activeNode=d;const c=TC[d.type]||FC;const props=d.props||{{}};
  let pr="";for(const[k,v]of Object.entries(props)){{let dv=v===null?"<em style='color:#555'>null</em>":Array.isArray(v)?v.join(", "):typeof v==="object"?JSON.stringify(v):String(v);pr+=`<tr><td class="pk">${{k}}</td><td class="pv">${{dv}}</td></tr>`;}}
  const conns=EDGES.filter(e=>e.source===d.id||e.target===d.id);let ch="";
  if(conns.length){{ch=`<div class="conns"><h4>Connections (${{conns.length}})</h4>`;conns.slice(0,30).forEach(e=>{{const oid=e.source===d.id?e.target:e.source;const o=nodeMap.get(oid);const ec=EC[e.type]||FC;ch+=`<div class="conn-item" style="border-left:3px solid ${{ec}};padding-left:8px" onclick="focusNode('${{oid}}')"><span style="color:${{ec}};font-size:9px">${{e.source===d.id?"→":"←"}} ${{e.type.replace(/_/g," ")}}</span> ${{o?o._label:oid}}</div>`;}});if(conns.length>30)ch+=`<div style="color:#555;font-size:10px">+${{conns.length-30}} more…</div>`;ch+="</div>";}}
  panelContent.innerHTML=`<h2 style="color:${{c}}">${{d._label}}</h2><div class="type-badge" style="background:${{c}}22;color:${{c}}">${{d.type}}</div><div style="font-size:10px;color:#8b949e;margin-bottom:8px">Degree: ${{d._deg||0}} (out:${{d._out||0}} in:${{d._in||0}})</div><table class="props-table">${{pr}}</table>${{ch}}<button onclick="focusNode('${{d.id}}')" style="margin-top:12px;padding:5px 14px;background:#1f6feb22;border:1px solid #1f6feb;border-radius:14px;color:#58a6ff;cursor:pointer;font-size:11px">Ego Network</button>`;
  panel.classList.add("open");ego(d);
}}
function focusNode(id){{const d=nodeMap.get(id);if(d)showPanel(d);}}
function closePanel(){{panel.classList.remove("open");activeNode=null;ego(null);}}

let hilite=null;
function ego(d){{
  if(!d){{hilite=null;nodeC.attr("opacity",1);nodeD.attr("opacity",.85);nodeL.attr("opacity",1);linkSel.attr("opacity",1);return;}}
  const nb=new Set([d.id]);EDGES.forEach(e=>{{if(e.source===d.id)nb.add(e.target);if(e.target===d.id)nb.add(e.source);}});hilite=nb;
  nodeC.attr("opacity",n=>nb.has(n.id)?1:.06);
  nodeD.attr("opacity",n=>nb.has(n.id)?.85:.06);
  nodeL.attr("opacity",n=>nb.has(n.id)?1:.06);
  linkSel.attr("opacity",e=>nb.has(e.source)&&nb.has(e.target)?1:.02);
}}

// ── Filters ──────────────────────────────────────────────────────────────
function applyFilters(){{
  const aNT=new Set(),aET=new Set();
  document.querySelectorAll("#node-filters .fbtn.on").forEach(b=>aNT.add(b.dataset.type));
  document.querySelectorAll("#edge-filters .fbtn.on").forEach(b=>aET.add(b.dataset.type));
  if(aNT.size===nodeTypes.length&&aET.size===edgeTypes.length){{
    nodeC.attr("opacity",1).attr("display",null);nodeD.attr("opacity",.85).attr("display",null);
    nodeL.attr("opacity",1).attr("display",null);linkSel.attr("opacity",1).attr("display",null);
  }}else{{
    const vN=new Set();NODES.forEach(n=>{{if(aNT.has(n.type))vN.add(n.id);}});
    nodeC.attr("opacity",n=>vN.has(n.id)?1:.06).attr("display",n=>vN.has(n.id)?null:"none");
    nodeD.attr("opacity",n=>vN.has(n.id)?.85:.06).attr("display",n=>vN.has(n.id)?null:"none");
    nodeL.attr("opacity",n=>vN.has(n.id)?1:.06).attr("display",n=>vN.has(n.id)?null:"none");
    linkSel.attr("opacity",e=>aET.has(e.type)&&vN.has(e.source)&&vN.has(e.target)?1:.02)
           .attr("display",e=>aET.has(e.type)&&vN.has(e.source)&&vN.has(e.target)?null:"none");
  }}hilite=null;
}}

// ── Search ───────────────────────────────────────────────────────────────
const si=document.getElementById("search"),sc=document.getElementById("search-clear"),sct=document.getElementById("search-count");
si.addEventListener("input",()=>{{
  const q=si.value.trim().toLowerCase();sc.style.display=q?"inline":"none";
  if(!q){{sct.textContent="";nodeC.attr("opacity",1);nodeD.attr("opacity",.85);nodeL.attr("opacity",1);linkSel.attr("opacity",1);return;}}
  const ms=NODES.filter(n=>n.name.toLowerCase().includes(q));sct.textContent=ms.length+" found";
  if(!ms.length){{nodeC.attr("opacity",.08);nodeD.attr("opacity",.08);nodeL.attr("opacity",.08);linkSel.attr("opacity",.02);return;}}
  const mSet=new Set(ms.map(n=>n.id)),nb2=new Set(mSet);
  EDGES.forEach(e=>{{if(mSet.has(e.source))nb2.add(e.target);if(mSet.has(e.target))nb2.add(e.source);}});
  nodeC.attr("opacity",n=>mSet.has(n.id)?1:nb2.has(n.id)?.35:.04);
  nodeD.attr("opacity",n=>mSet.has(n.id)?.85:nb2.has(n.id)?.35:.04);
  nodeL.attr("opacity",n=>mSet.has(n.id)?1:nb2.has(n.id)?.35:.04);
  linkSel.attr("opacity",e=>nb2.has(e.source)&&nb2.has(e.target)?(mSet.has(e.source)||mSet.has(e.target)?.6:.15):.01);
  if(ms[0]){{const m=ms[0];svg.transition().duration(400).call(zoom.transform,d3.zoomIdentity.translate(W/2-m.x*1.6,H/2-m.y*1.6).scale(1.6));}}
}});
sc.addEventListener("click",()=>{{si.value="";si.dispatchEvent(new Event("input"));si.focus();}});

// ── Reset ────────────────────────────────────────────────────────────────
document.getElementById("reset-btn").addEventListener("click",()=>{{
  si.value="";si.dispatchEvent(new Event("input"));
  document.querySelectorAll("#node-filters .fbtn,#edge-filters .fbtn").forEach(b=>b.classList.add("on"));
  applyFilters();ego(null);closePanel();
  svg.transition().duration(400).call(zoom.transform,d3.zoomIdentity);
}});
document.addEventListener("keydown",e=>{{
  if(e.key==="Escape"){{closePanel();ego(null);si.value="";si.dispatchEvent(new Event("input"));}}
  if((e.ctrlKey||e.metaKey)&&e.key==="f"){{e.preventDefault();si.focus();}}
  if(e.key==="/"&&document.activeElement!==si){{e.preventDefault();si.focus();}}
}});

// ── Tick ─────────────────────────────────────────────────────────────────
sim.on("tick",()=>{{
  linkSel.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y).attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
  nodeC.attr("cx",d=>d.x).attr("cy",d=>d.y);
  nodeD.attr("cx",d=>d.x).attr("cy",d=>d.y);
  nodeL.attr("x",d=>d.x).attr("y",d=>d.y+d._r+12);
}});

// ── End ──────────────────────────────────────────────────────────────────
let mmTimer;
sim.on("end",()=>{{
  console.log("END — "+NODES.length+" nodes. pos:["+(NODES[0].x||0).toFixed(0)+","+(NODES[0].y||0).toFixed(0)+"] W="+W+" H="+H);
  mmap(d3.zoomTransform(svg.node()));
  document.getElementById("loading").style.opacity="0";
  setTimeout(()=>document.getElementById("loading").style.display="none",400);
  mmTimer=setInterval(()=>mmap(d3.zoomTransform(svg.node())),2000);
}});

window.addEventListener("resize",()=>{{
  const w=innerWidth,h=innerHeight;svg.attr("width",w).attr("height",h);
  sim.force("center",d3.forceCenter(w/2,h/2)).alpha(.05).restart();
}});
</script>
</body>
</html>"""

    Path(out_path).write_text(html, encoding="utf-8")
    print(f"Written {out_path} ({len(html):,} bytes)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    build(args.data, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
