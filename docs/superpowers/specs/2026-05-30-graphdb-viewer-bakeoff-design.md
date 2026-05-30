# GraphDB Viewer Bake-off — Dispatch Spec (#97)

**Date:** 2026-05-30 · **Type:** multi-model CREATE bake-off (render-only) ·
**Winner becomes the official `kdb-graph-view` tool.**

## For the orchestrator (us)

Each panel model independently produces ONE self-contained HTML viewer for the
KDB knowledge graph. We own the data export (`tools/viewer-bakeoff/export_graph.py`
→ library-neutral JSON); the panel competes purely on **visualization + UX**, so
versions are directly comparable on the same data. Free library choice (A).

- **Reference baseline:** `tools/kdb_graph_viewer-opus.py` (Cytoscape.js snapshot).
- **Test data:** `tools/viewer-bakeoff/graph-export-run3.json` — the real run-3
  graph: **211 nodes** (178 Entity · 29 Source · 4 Domain) / **653 edges**
  (439 LINKS_TO · 185 SUPPORTS · 29 BELONGS_TO).
- **Submissions land in:** `tools/viewer-bakeoff/kdb-graph-viewer-<model>.html`.
- Panel per `docs/external-review-panel.md` (Codex · Deepseek · Qwen · Grok ·
  Gemini/agy). Each fired independently; outputs withheld until all in, then compared.

---

## The brief (hand this + `graph-export-run3.json` to each model)

> **Build a single-file, interactive HTML viewer for a knowledge graph.**
>
> You are given a JSON file, `graph-export-run3.json`, with this shape:
> ```json
> { "nodes": [{"id": "...", "type": "Source|Entity|Domain|Claim",
>              "name": "display name", "props": { ... } }],
>   "edges": [{"id": "...", "source": "<node id>", "target": "<node id>",
>              "type": "LINKS_TO|SUPPORTS|BELONGS_TO|ALIAS_OF|..." }] }
> ```
> It is a knowledge graph built from a personal note vault: **Source** notes link
> to **Entity** concepts (LINKS_TO), Entities SUPPORT each other, and Sources
> BELONG_TO Domains. ~211 nodes / ~653 edges in this sample; design for graphs up
> to a few thousand nodes.
>
> **Deliver ONE self-contained `.html` file** that embeds this data and renders an
> interactive explorer. Pick whatever visualization library/approach you think is
> best.
>
> **Required (must-have floor):**
> 1. Render all nodes + edges, **color-coded by node type**, with a **legend**.
> 2. **Zoom / pan** + a sensible default **layout** that reveals structure.
> 3. **Click a node → detail panel** showing its `name`, `type`, and `props`.
> 4. **Search by name** — locate/highlight a node.
> 5. **Filter by node type AND edge type** (toggle Source/Entity/Domain,
>    LINKS_TO/SUPPORTS/BELONGS_TO). *(Most important — the graph is dense.)*
> 6. **Distinguish edge types** visually and show **direction** (arrows).
> 7. **Smooth performance** at a few thousand nodes.
>
> **Go beyond the floor — surprise us.** Apply current best-in-class
> graph-visualization techniques: WebGL/GPU rendering for scale (e.g. sigma.js v3,
> cosmograph, regraph), semantic zoom / level-of-detail, community-cluster layouts
> (e.g. Louvain), focus+context / fisheye, ego-network highlight on click,
> degree/importance node sizing, edge bundling for dense regions, minimap,
> light/dark. Use your latest knowledge.
>
> **Hard constraints:**
> - A **single `.html` file**, opened by double-click — **no server, no build step**.
> - External libraries via **CDN `<script>`** only.
> - The graph data must be **embedded** in the file (read it from
>   `graph-export-run3.json` and inline it).
> - **Degrade gracefully** if a `prop` or field is missing.
>
> **Output guardrail (strict):** produce **ONLY** the single file
> `kdb-graph-viewer-<your-name>.html`. Do **not** modify, create, or delete any
> other file in the repository.

---

## Judging rubric (us, after all submissions land)

Score on the run-3 graph: **(1)** required floor present and working well ·
**(2)** quality of differentiators / state-of-the-art techniques · **(3)**
single-file robustness (opens clean, no console errors, handles missing fields) ·
**(4)** clarity + usefulness for actually *exploring* an ontology ·
**(5)** plausible scaling to thousands of nodes. Pick the winner; promote to a
`kdb-graph-view` CLI wired behind `export_graph.py`. Losers archived for ideas.

## Data producer

`tools/viewer-bakeoff/export_graph.py --graph-path <vault>/KDB/graph --out graph-export-run3.json`
— read-only Kuzu dump → neutral `{nodes, edges, summary}` JSON. Re-run to refresh
against any graph.
