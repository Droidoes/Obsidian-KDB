# Opus GraphDB Viewer — Bake-off Upgrade Design

**Date:** 2026-05-30
**Task:** #97 (GraphDB viewer bake-off) — promote the Opus baseline from "minimal reference" to a competitive submission.
**Status:** Design ratified (Approach A), ready for implementation plan.

## Goal

The Opus viewer (`tools/kdb_graph_viewer-opus.py`) is currently a clean but minimal
baseline. It is missing two of the bake-off's **must-have floor** features (search,
node/edge-type filters) and lacks the interaction polish that the codex/qwen/deepseek
submissions use to tame the dense graph. This upgrade closes the floor gap and adds
the differentiators needed to win the render-only comparison — while keeping the
viewer **one self-contained HTML file** built from the live Kuzu graph.

## Approach (ratified)

**A — Supercharge Cytoscape.** Keep the proven Cytoscape render path and the
existing Python query/export logic. Add two CDN plugins and a hand-built interaction
layer. Rejected: B (Sigma.js/WebGL rewrite — scale advantage irrelevant at ~211/653
nodes, throws away working baseline) and C (Cosmograph — overkill, hard to layer
precise click-detail/filtering on).

## Scope boundary

- **All changes live in `tools/kdb_graph_viewer-opus.py`**, primarily `_render_html()`,
  plus a small per-node `degree` precompute in `export()`.
- `export()`'s graph query (node/edge dump) is otherwise **untouched** — the data is
  identical, so the run-3 invariant **211 nodes / 653 edges** (Entity 178 / Domain 4 /
  Source 29; LINKS_TO 439 / SUPPORTS 185 / BELONGS_TO 29) is preserved.
- Output remains a single double-click-to-open `.html`: CDN `<script>` tags only,
  data inlined, no server, no build step.

## Engine & layout

- Cytoscape **3.30.2** (keep).
- **`cytoscape-fcose`** (CDN, pinned) replaces the current `cose` layout — proper
  force-directed clustering that pulls communities apart instead of the current loose
  strands. Requires `layout-base` + `cose-base` dependency scripts (pinned, CDN).
- **`cytoscape-navigator`** (CDN, pinned) adds a minimap (bottom-right) + its CSS.

**CDN risk:** the plugins are the only real risk. Pin exact versions and verify each
URL resolves before building. If `cytoscape-navigator` CSS proves fiddly, the minimap
degrades to optional without affecting any floor feature.

## Visual encoding

| Channel | Encoding |
|---------|----------|
| Node color | by type — Source `#4C9AFF` · Entity `#57D9A3` · Domain `#FFC400` · Claim `#FF7452` (existing palette); unmapped `#998DD9` |
| Node size | **by degree** — `mapData(degree, …)` from ~14px (leaf) to ~48px (hub); `degree` precomputed per node in Python |
| Edge color | **by type** — LINKS_TO / SUPPORTS / BELONGS_TO / ALIAS_OF each a distinct color (today all one grey); keep `target-arrow` for direction |
| Theme | light/dark toggle, default dark |

## Controls (top bar)

- **Search** — text input; matches node `name` (case-insensitive, substring); on
  match, center + pulse-highlight the hit and emphasize its neighbors. No match → no-op.
- **Node-type filters** — legend chips become click-to-toggle (hide/show each type).
- **Edge-type filters** — one chip per relationship type, toggle.
- **Reset view** + **Re-run layout** buttons.
- **Live HUD** — "visible: N nodes / M edges", recomputed as filters apply.

## Interaction (the differentiator)

- **Click node → ego-network focus+context:** the node + its 1-hop neighbors +
  connecting edges stay full-opacity; everything else dims to ~15%. Right detail panel
  fills with name / type / all props.
- **Click edge:** highlight + panel shows source / target / type.
- **Click background:** clear focus, restore full opacity, clear panel.

## Explicitly out of scope (YAGNI)

- No Louvain / community-detection library — fcose's clustering already reveals
  structure visually; a lib is risk for marginal gain.
- No WebGL, no edge-bundling, no semantic-zoom LOD. Stretch-only if the above lands
  cleanly with time to spare.

## Verification

1. **Data invariant:** regenerate → script must still report 211 nodes / 653 edges with
   the same label/rel breakdown. Any drift = a query regression, stop.
2. **Self-contained:** the output `.html` has no local file refs (CDN `<script>` only);
   opens by double-click.
3. **Feature gate (visual, walked through with the user):** colored edges; degree-sized
   hubs; tighter fcose clustering; search centers+highlights; node-type and edge-type
   toggles add/remove elements and update the HUD; click-node ego-focus dims the rest;
   minimap present; light/dark toggles.
4. **Regression baseline:** the pre-upgrade screenshot (`~/Downloads/Screenshot
   2026-05-30 225930.png`) is the "before" reference.

## Regenerate / refresh loop

Data unchanged, so no JSON re-export. Each iteration:

```bash
python3 tools/kdb_graph_viewer-opus.py \
  --graph-path ~/Obsidian/Vault-in-place-test-run/KDB/graph \
  --out tools/viewer-bakeoff/kdb-graph-viewer-opus.html
```

then refresh the browser tab.
