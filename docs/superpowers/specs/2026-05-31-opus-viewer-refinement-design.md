# Opus GraphDB Viewer Refinement — Design Spec

**Date:** 2026-05-31
**Status:** Approved (design); pending spec review → implementation plan
**Target file:** `tools/kdb_graph_viewer-opus.py` (the Python builder that emits a single
self-contained HTML graph viewer)
**Supersedes/extends:** `docs/superpowers/specs/2026-05-30-opus-viewer-upgrade-design.md`
(the bake-off setup); this is the post-bake-off refinement that folds the chosen
winners into the official viewer.

---

## Goal

Make the official Opus viewer's constellation **packed and springy** like the Gemini/Qwen
candidates, shrink nodes to a Codex-like Obsidian scale, and give it a Qwen-style
detailed right panel — without changing the rest of the architecture.

## Context

The Opus viewer renders the GraphDB with **Cytoscape.js 3.30** + `fcose` layout +
`cytoscape-navigator` (minimap). The builder (`_render_html`) injects graph data into an
HTML template via token replacement. Four refinements were ratified after the bake-off
(Gemini / Qwen / Codex kept as references; Grok / DeepSeek dropped):

| # | Change | Borrowed from | Decision |
|---|--------|---------------|----------|
| 1 | Packed + springy constellation | own proposal (Option A) | **Cytoscape `cola`, continuous** |
| 2 | Smaller default node sizes | Codex | type-tiered + degree formula |
| 3 | Top filter/search panel | — | **no change** |
| 4 | Detailed right panel | Qwen | typed clickable neighbor list |

Bake-off finding that anchors change #1: the springy "one-big-cluster" feel = a
**continuous force layout with a centering/packing force**. `fcose` computes once and
freezes, so it structurally cannot be springy. Gemini achieves it in pure D3; Qwen drives
Cytoscape positions from a D3 sim. We chose the single-engine route (`cola`) instead.

---

## Change 1 — Layout: `fcose` → continuous `cola`

**What.** Replace the fcose layout with `cytoscape-cola` running with `infinite: true`.

- `infinite: true` → the simulation never settles, so dragging a node makes the graph
  spring/wobble (the elastic feel that fcose lacks).
- `handleDisconnected: true` (cola default) packs separate components next to each other
  instead of letting them drift into isolated islands → the "one big cluster" look.
- `fit: false` so continuous ticks don't keep re-zooming the viewport; do one explicit
  `cy.fit()` after initial layout settle.

**CDN.** `cytoscape-cola` depends on the `webcola` global. Add **both** scripts above `cy`
creation, in order:

```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/cola/3.4.0/cola.min.js"></script>
<script src="https://unpkg.com/cytoscape-cola@2.5.1/cytoscape-cola.js"></script>
```

**Registration + graceful degrade (must never blank the page).** Extend the existing
fcose→cose ladder to: **cola → fcose → built-in cose**.

```js
const HAS_COLA  = !!(window.cytoscapeCola && window.cola);
const HAS_FCOSE = !!window.cytoscapeFcose;
if (HAS_COLA)  { try { cytoscape.use(window.cytoscapeCola); } catch(e){ } }
if (HAS_FCOSE) { try { cytoscape.use(window.cytoscapeFcose); } catch(e){ } }

function layoutOpts(){
  if (HAS_COLA){
    return { name:'cola', infinite:true, fit:false, handleDisconnected:true,
             nodeSpacing: 6, edgeLength: 90, animate:true,
             maxSimulationTime: 4000, convergenceThreshold: 0.01 };
  }
  if (HAS_FCOSE){
    return { name:'fcose', quality:'default', animate:true, animationDuration:600,
             randomize:true, nodeRepulsion:6500, idealEdgeLength:75,
             nodeSeparation:80, padding:40 };
  }
  return { name:'cose', animate:false, nodeRepulsion:9000, idealEdgeLength:90, padding:40 };
}
```

`nodeSpacing` / `edgeLength` are the packing knobs — tuned against the run-3 export in the
visual gate. Initial values above are starting points, not final.

**Re-run-layout button.** The existing "re-run layout" control calls `cy.layout(layoutOpts()).run()`;
this keeps working — under cola it restarts the continuous sim.

**Risk + mitigation.** If cola's packing doesn't pull disconnected components tight enough
(the one aesthetic risk flagged during design), the fallback is the Qwen pattern — a D3
force-solver writing positions into Cytoscape. We do **not** build that now; we judge cola
on the real export first. The fcose fallback guarantees a working viewer regardless.

## Change 2 — Codex-scale nodes (type-tiered + degree)

**What.** Replace the single degree ramp `mapData(degree, 0, MAX_DEGREE, 12, 50)` with a
per-node size computed in the **Python builder** and emitted as a `size` data field, using
Codex's type-tiered + damped-degree formula.

**Codex reference formula** (its `radius`, where node degree drives a capped sqrt term):

```
base   = {Domain: 11, Source: 8, Entity: 5, Claim: 5}[label]
radius = base + min(8, sqrt(degree) * 1.8)
```

Codex draws circles, so its *visual diameter* = `2 * radius`. Cytoscape `width`/`height` are
diameters, so to match Codex's on-screen size we emit:

```python
import math
_BASE = {"Domain": 11, "Source": 8, "Entity": 5, "Claim": 5}
def _node_size(label: str, degree: int) -> float:
    base = _BASE.get(label, 5)
    radius = base + min(8.0, math.sqrt(degree) * 1.8)
    return round(2 * radius, 1)   # diameter; ~20–38 Domain, 16–32 Source, 10–26 Entity/Claim
```

Each node element gets `data: {..., size: _node_size(label, degree)}`. The Cytoscape node
style changes to:

```js
'width':  'data(size)',
'height': 'data(size)',
```

`MAX_DEGREE` is no longer needed for sizing (it may still be used elsewhere — leave it if
so, remove only if it becomes dead). The `2 *` diameter factor is the one tuning knob; if
the visual gate shows nodes too large, drop to `1.5 *` or raw radius.

## Change 3 — Top panel

No change. The top filter/search bar stays exactly as-is.

## Change 4 — Qwen-style right detail panel

**What.** Upgrade the builder's `showNode(d)` JS so the right panel shows, like Qwen's
`showDetail`:

1. **Type badge + name + degree** (already present — keep).
2. **Properties table, noise-filtered.** Skip the operational/timestamp keys Qwen skips:
   ```js
   const SKIP = new Set(['created_at','updated_at','first_run_id','last_run_id',
                         'first_seen_at','last_seen_at','last_ingested_at']);
   ```
   Long string values truncated to ~200 chars + `…`. Null → `—`.
3. **Clickable typed-neighbor list.** From `node.connectedEdges()`, build entries of
   `{ other node, edge type, direction }`:
   - direction arrow `→` (this node is source) / `←` (this node is target);
   - a color dot tinted by the neighbor's node type (reuse `NODE_COLORS`);
   - the edge type label (SUPPORTS / BELONGS_TO / LINKS_TO / ALIAS_OF / …);
   - sorted by edge type, then neighbor name;
   - capped at 40 with a "… and N more" footer;
   - clicking an entry focuses/navigates to that neighbor (reuse the existing
     focus-by-id path used by search/`focusOn`).

This requires the panel container to hold sub-elements (`p-props`, `p-neighbors`) rather
than one `innerHTML` blob; restructure `showNode` accordingly. Edge-click (`showEdge`)
behavior is unchanged.

**Ego-focus stays click-triggered** (`cy.on('tap','node', …)` → `focusOn(closedNeighborhood)`)
— hover-focus was explicitly out of scope.

---

## Out of scope (explicitly dropped this round)

- Hover-triggered ego-focus (Codex) — stays click-triggered.
- Per-type counts on filter chips (Gemini).
- Left sidebar layout (Gemini) — top panel kept.
- Color/theme reskin (Qwen).
- The D3-solver dual-engine (Qwen) — only the fallback if cola packing disappoints; not built now.

## Iteration 1 — 2026-05-31 (post-visual-gate)

First build was judged on the run-3 export. Findings + changes:

- **Layout pivot A → B.** Option A (`cola`) silently fell back to static `fcose`
  because the webcola CDN URL 404'd — so it was neither springy nor packed
  (clusters disjointed). Invoked the spec's named fallback: **the Qwen/Gemini
  pattern — a D3 `forceSimulation` (link + capped charge + `forceCenter` +
  `forceX/forceY` packing + collide) drives Cytoscape node positions on every
  tick.** Continuous = springy; centering = one packed cluster. Drag pins the
  grabbed node (`fx/fy`) and reheats (`alphaTarget(0.3)`) so neighbors follow,
  releasing on drop. Fallback if D3's CDN fails: static `fcose → cose`.
- **Colors:** Entity → blue (`#4C9AFF`), Source → green (`#57D9A3`) (swapped).
- **Node scale −50%:** `_node_size` drops the `2×` (returns the radius directly);
  Source base lowered to Entity's (`5`) so **Source is never bigger than Entity**.
- **Captions hidden by default** (`text-opacity:0`); shown only (a) on the
  hover-focused neighborhood, or (b) when zoomed in past `ZOOM_LABEL` (1.8).
- **Ego-focus is now hover-triggered** (`mouseover`/`mouseout`), not click. Click
  is reserved for pinning the right-panel detail.

## Iteration 2 — 2026-05-31 (pivot: Gemini D3 base becomes the official viewer)

After several rounds of trying to retrofit the Cytoscape/Opus builder to match
the bake-off's Gemini constellation (springiness, cohesive packing), we pivoted
the **base** rather than keep tuning. The bake-off winner (Gemini, pure D3) nails
the constellation out of the box; we adopt it as the official viewer and re-iterate
our preferences on top.

**New architecture (replaces everything above):**
- **`tools/kdb_graph_viewer.py`** — official single-command builder: reads Kuzu
  directly → neutral `{nodes,edges,summary}` (self-loops skipped) → injects into
  the template at `/*__GRAPH_DATA__*/`. `--graph-path <kuzu> [--out ...]`.
- **`tools/kdb_graph_viewer_template.html`** — the Gemini D3 template, node radius
  baked to **2/3** of the bake-off scale.
- **Cytoscape `tools/kdb_graph_viewer-opus.py` retired** (the cola/D3-on-Cytoscape
  commits are a superseded dead end in history).
- **Fallback preserved** under `tools/viewer-bakeoff/`: original `gemini_template.html`
  + `build_gemini.py` (2-stage Kuzu→JSON→HTML) + a `kdb-graph-viewer-gemini-2-3.html`
  reference copy. Per the decision, we can return to the original or the 2-stage path.

**Refinements applied to the Gemini base (the "re-iterate" list):**
- Node scale 2/3; cohesive central-seed constellation kept from Gemini.
- **Entity = blue, Source = green** (swapped at the CSS-variable level).
- **Elastic-only layout** — the "Clusters" mode + its "Layout Engine" panel section,
  `switchLayout`, and `currentLayoutMode` removed.
- **Self-loops dropped** in extraction (a node linking to itself).
- **BELONGS_TO solid**, SUPPORTS dashed, ALIAS_OF dashed.
- **Arrowheads** halved (`markerWidth/Height` 6→3) and now **dim with ego-focus**
  (the dim class uses element `opacity`, not `stroke-opacity`, so the shared
  `<marker>` composites with the path).
- **Ego-focus on hover** (Gemini default), click pins the right-panel detail.
- **Combined right panel** — the left controls panel was removed and its
  search + node/edge filters + reset folded into the top of the right panel, above
  a divider and the node-detail area (`#inspector`, which the JS still rewrites).
- **Header toggle** shows/hides the combined right panel.

**Tests** (`tools/tests/test_kdb_graph_viewer.py`, repointed to the new builder):
template has the data token + 2/3 scale; `render_html` injects data and consumes the
token; missing-token guard raises. The earlier Cytoscape-specific tests were removed
with the opus builder.

## Testing

**Unit (Python builder, `pytest -m "not live"`):**
- Emitted HTML includes the cola + webcola CDN script tags.
- The degrade ladder is present (cola → fcose → cose) in the emitted JS.
- Each node element carries a numeric `size`; spot-check `_node_size` against the formula
  (e.g. Domain deg 0 → 22.0; Entity deg 0 → 10.0; capped sqrt term).
- Node style uses `data(size)` (no `mapData(... 12, 50)` remnant).
- Panel markup contains the neighbor-list container and the SKIP set excludes the noisy
  keys (selected timestamp key absent from a rendered fixture).

**Visual gate (the real acceptance):** build the viewer from a run-3 export, open in a
browser, confirm: (a) constellation packs into one cluster and is springy on drag;
(b) nodes are small/Obsidian-like; (c) right panel lists clickable typed neighbors that
navigate. Tune cola `nodeSpacing`/`edgeLength` and the node-size diameter factor here.
This is the established viewer acceptance pattern (prior "visual gate passed" milestone).
