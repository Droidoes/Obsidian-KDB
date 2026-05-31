# GraphDB Viewer Bake-off — Dispatch Prompt

Hand the block below to each panel model (Codex · Deepseek · Qwen · Grok ·
agy/Gemini). Replace `<MODEL>` with the model's short name (e.g. `codex`,
`deepseek`, `qwen`, `grok`, `gemini`). Fire each independently; collect all
before comparing.

---

## PROMPT (copy from here ↓)

Build a **single self-contained HTML file** that renders an interactive viewer
for a knowledge graph.

**Input data** — read it from this repo file and embed it in your HTML:
`tools/viewer-bakeoff/graph-export-run3.json`

Its shape:
```json
{ "nodes": [{"id": "...", "type": "Source|Entity|Domain|Claim",
             "name": "display name", "props": { ... }}],
  "edges": [{"id": "...", "source": "<node id>", "target": "<node id>",
             "type": "LINKS_TO|SUPPORTS|BELONGS_TO|ALIAS_OF|..."}] }
```

It is a knowledge graph built from a personal note vault: **Source** notes
LINK_TO **Entity** concepts, Entities SUPPORT each other, and Sources BELONG_TO
**Domains**. This sample has ~211 nodes / ~653 edges; design so it stays usable
up to a few thousand nodes.

**Required (must-have floor):**
1. Render all nodes + edges, **color-coded by node type**, with a **legend**.
2. **Zoom / pan** and a sensible default **layout** that reveals structure.
3. **Click a node → detail panel** showing its `name`, `type`, and `props`.
4. **Search by name** — locate and highlight a node.
5. **Filter by node type AND edge type** (toggle Source/Entity/Domain,
   LINKS_TO/SUPPORTS/BELONGS_TO). The graph is dense — this matters most.
6. **Distinguish edge types** visually and show **direction** (arrows).
7. **Smooth performance** at a few thousand nodes.

**Go beyond the floor — surprise us.** Apply current best-in-class
graph-visualization techniques: WebGL/GPU rendering for scale (e.g. sigma.js v3,
cosmograph, regraph), semantic zoom / level-of-detail, community-cluster layouts
(e.g. Louvain), focus+context / fisheye, ego-network highlight on click,
degree/importance node sizing, edge bundling, minimap, light/dark. Pick whatever
library and approach you think is best. Use your latest knowledge.

**Hard constraints:**
- ONE `.html` file, opened by double-click — **no server, no build step**.
- External libraries via **CDN `<script>`** tags only.
- The graph data must be **embedded** in the file (read the JSON above and inline it).
- **Degrade gracefully** if a `prop` or field is missing.

**Output guardrail (strict):** produce **ONLY** the single file
`tools/viewer-bakeoff/kdb-graph-viewer-<MODEL>.html`. Do **not** modify, create,
or delete any other file in the repository.

## (end PROMPT ↑)

---

When all submissions land in `tools/viewer-bakeoff/`, we judge against the rubric
in `docs/superpowers/specs/2026-05-30-graphdb-viewer-bakeoff-design.md` plus the
Opus baseline (`tools/kdb_graph_viewer-opus.py`), then promote the winner to a
`kdb-graph-view` CLI.
