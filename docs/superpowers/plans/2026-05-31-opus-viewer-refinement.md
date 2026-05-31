# Opus GraphDB Viewer Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the official Opus viewer's constellation packed + springy (continuous Cytoscape `cola`), shrink nodes to a Codex-like scale, and add a Qwen-style clickable typed-neighbor detail panel.

**Architecture:** Single-file Python builder `tools/kdb_graph_viewer-opus.py` emits a self-contained Cytoscape.js HTML via token replacement. Changes are: (1) a pure `_node_size()` helper + a per-node `size` data field computed in `export()`; (2) layout engine swap `fcose → cola` with a cola→fcose→cose degrade ladder; (3) a richer `showNode()` JS in the embedded template. No new modules.

**Tech Stack:** Python 3 stdlib, Cytoscape.js 3.30, cytoscape-cola + webcola (CDN), cytoscape-navigator, pytest.

**Spec:** `docs/superpowers/specs/2026-05-31-opus-viewer-refinement-design.md`

**Note on testing:** the builder reads a live Kuzu DB, so end-to-end runs need a real graph (manual visual gate). The only pure unit-testable logic is `_node_size()`; it lives in a hyphenated module loaded via `importlib`. Everything else (template strings) is verified by substring assertions on `_render_html()` output and by the browser visual gate.

---

### Task 1: Node-size helper + per-node `size` field

**Files:**
- Modify: `tools/kdb_graph_viewer-opus.py` (add `_node_size`, attach `size` in `export()`)
- Test: `tools/tests/test_kdb_graph_viewer.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tools/tests/test_kdb_graph_viewer.py`:

```python
import importlib.util
from pathlib import Path

# Hyphenated module name -> load via importlib.
_VIEWER = Path(__file__).resolve().parent.parent / "kdb_graph_viewer-opus.py"
_spec = importlib.util.spec_from_file_location("kdb_graph_viewer_opus", _VIEWER)
viewer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(viewer)


def test_node_size_codex_scale():
    # diameter = 2 * (base + min(8, sqrt(deg)*1.8))
    assert viewer._node_size("Domain", 0) == 22.0   # 2*11
    assert viewer._node_size("Source", 0) == 16.0   # 2*8
    assert viewer._node_size("Entity", 0) == 10.0   # 2*5
    assert viewer._node_size("Claim", 0) == 10.0    # 2*5
    # unknown label falls back to base 5
    assert viewer._node_size("Mystery", 0) == 10.0


def test_node_size_degree_term_capped():
    # sqrt(100)*1.8 = 18 -> capped at 8 -> radius 5+8=13 -> diameter 26
    assert viewer._node_size("Entity", 100) == 26.0
    # small degree grows below the cap: deg 4 -> sqrt=2 *1.8=3.6 -> r=8.6 -> d=17.2
    assert viewer._node_size("Entity", 4) == 17.2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_kdb_graph_viewer.py -m "not live" -q`
Expected: FAIL — `AttributeError: module ... has no attribute '_node_size'`

- [ ] **Step 3: Add the helper and an import**

In `tools/kdb_graph_viewer-opus.py`, add `import math` near the top imports (after `import json`), and add this helper right above `def export(`:

```python
# Codex-scale node sizing: small Obsidian-like nodes, type-tiered + damped degree.
# Returns a *diameter* (Cytoscape width/height); Codex's value is a radius, so 2x.
_SIZE_BASE = {"Domain": 11, "Source": 8, "Entity": 5, "Claim": 5}


def _node_size(label: str, degree: int) -> float:
    base = _SIZE_BASE.get(label, 5)
    radius = base + min(8.0, math.sqrt(degree) * 1.8)
    return round(2 * radius, 1)
```

- [ ] **Step 4: Attach `size` to each node in `export()`**

In `export()`, the degree loop currently is:

```python
    max_degree = 0
    for n in nodes:
        d = degree.get(n["data"]["id"], 0)
        n["data"]["degree"] = d
        max_degree = max(max_degree, d)
```

Replace it with (adds the `size` field):

```python
    max_degree = 0
    for n in nodes:
        d = degree.get(n["data"]["id"], 0)
        n["data"]["degree"] = d
        n["data"]["size"] = _node_size(n["data"]["label"], d)
        max_degree = max(max_degree, d)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tools/tests/test_kdb_graph_viewer.py -m "not live" -q`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add "tools/kdb_graph_viewer-opus.py" tools/tests/test_kdb_graph_viewer.py
git commit -m "feat(viewer): Codex-scale per-node size field"
```

---

### Task 2: Use `data(size)` in the node style

**Files:**
- Modify: `tools/kdb_graph_viewer-opus.py` (template node style)
- Test: `tools/tests/test_kdb_graph_viewer.py`

- [ ] **Step 1: Write the failing test**

Append to `tools/tests/test_kdb_graph_viewer.py`:

```python
def _render_min():
    nodes = [{"data": {"id": "Entity:0", "label": "Entity", "name": "x",
                       "props": {}, "degree": 0, "size": 10.0}}]
    edges = []
    summary = {"labels": {"Entity": 1}, "rels": {}, "max_degree": 0}
    return viewer._render_html(nodes, edges, "g.kuzu", summary)


def test_node_style_uses_data_size():
    html = _render_min()
    assert "data(size)" in html
    assert "mapData(degree, 0," not in html  # old ramp gone
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_kdb_graph_viewer.py::test_node_style_uses_data_size -m "not live" -q`
Expected: FAIL — `data(size)` absent, `mapData(degree, 0,` still present.

- [ ] **Step 3: Edit the node style in `_HTML_TEMPLATE`**

Find:

```javascript
        'width':`mapData(degree, 0, ${MAX_DEGREE}, 12, 50)`,
        'height':`mapData(degree, 0, ${MAX_DEGREE}, 12, 50)`,
```

Replace with:

```javascript
        'width':'data(size)',
        'height':'data(size)',
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tools/tests/test_kdb_graph_viewer.py -m "not live" -q`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add "tools/kdb_graph_viewer-opus.py" tools/tests/test_kdb_graph_viewer.py
git commit -m "feat(viewer): drive node size from data(size)"
```

---

### Task 3: Continuous `cola` layout with degrade ladder

**Files:**
- Modify: `tools/kdb_graph_viewer-opus.py` (CDN scripts, registration, `layoutOpts`)
- Test: `tools/tests/test_kdb_graph_viewer.py`

- [ ] **Step 1: Write the failing test**

Append to `tools/tests/test_kdb_graph_viewer.py`:

```python
def test_cola_layout_and_degrade_ladder():
    html = _render_min()
    # CDN scripts present
    assert "cytoscape-cola" in html
    assert "cola.min.js" in html
    # continuous physics + packing
    assert "infinite:true" in html
    assert "handleDisconnected:true" in html
    # degrade ladder: cola -> fcose -> cose
    assert "HAS_COLA" in html
    assert "name:'cola'" in html
    assert "name:'fcose'" in html
    assert "name:'cose'" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_kdb_graph_viewer.py::test_cola_layout_and_degrade_ladder -m "not live" -q`
Expected: FAIL — cola tokens absent.

- [ ] **Step 3: Add the cola CDN scripts**

In `_HTML_TEMPLATE` `<head>`, find:

```html
<script src="https://unpkg.com/cytoscape-fcose@2.2.0/cytoscape-fcose.js"></script>
```

Add the two cola scripts immediately after it:

```html
<script src="https://unpkg.com/cytoscape-fcose@2.2.0/cytoscape-fcose.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/cola/3.4.0/cola.min.js"></script>
<script src="https://unpkg.com/cytoscape-cola@2.5.1/cytoscape-cola.js"></script>
```

- [ ] **Step 4: Register cola and rewrite `layoutOpts`**

Find:

```javascript
  // fcose is the preferred layout; degrade to built-in cose if its CDN fails
  // (must never blank the page — it sits above cy creation).
  const HAS_FCOSE = !!window.cytoscapeFcose;
  if(HAS_FCOSE){ try { cytoscape.use(window.cytoscapeFcose); } catch(e){} }
```

Replace with:

```javascript
  // Layout preference: continuous cola (springy + packed) -> fcose -> built-in cose.
  // Never blank the page if a CDN fails — this sits above cy creation.
  const HAS_COLA  = !!(window.cytoscapeCola && window.cola);
  const HAS_FCOSE = !!window.cytoscapeFcose;
  if(HAS_COLA){  try { cytoscape.use(window.cytoscapeCola);  } catch(e){} }
  if(HAS_FCOSE){ try { cytoscape.use(window.cytoscapeFcose); } catch(e){} }
```

Then find:

```javascript
  function layoutOpts(){
    if(!HAS_FCOSE){
      return {name:'cose', animate:false, nodeRepulsion:9000, idealEdgeLength:90, padding:40};
    }
    return {name:'fcose', quality:'default', animate:true, animationDuration:600,
            randomize:true, nodeRepulsion:6500, idealEdgeLength:75, nodeSeparation:80, padding:40};
  }
```

Replace with:

```javascript
  function layoutOpts(){
    if(HAS_COLA){
      return {name:'cola', infinite:true, fit:false, handleDisconnected:true,
              animate:true, nodeSpacing:6, edgeLength:90,
              maxSimulationTime:4000, convergenceThreshold:0.01};
    }
    if(HAS_FCOSE){
      return {name:'fcose', quality:'default', animate:true, animationDuration:600,
              randomize:true, nodeRepulsion:6500, idealEdgeLength:75, nodeSeparation:80, padding:40};
    }
    return {name:'cose', animate:false, nodeRepulsion:9000, idealEdgeLength:90, padding:40};
  }
```

- [ ] **Step 5: Fit once after layout starts (cola has `fit:false`)**

`cola` runs continuously with `fit:false`, so add an explicit one-time fit after `cy` is created. Find the minimap block:

```javascript
  // ---- minimap (degrade gracefully if plugin missing) ----
  try { cy.navigator({container: document.getElementById('minimap')}); }
  catch(err){ document.getElementById('minimap').style.display='none'; }
```

Insert immediately BEFORE it:

```javascript
  // cola runs with fit:false (continuous) — fit the viewport once after it spreads out.
  if(HAS_COLA){ setTimeout(() => cy.fit(cy.elements(':visible'), 40), 800); }

```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tools/tests/test_kdb_graph_viewer.py -m "not live" -q`
Expected: PASS (all tests).

- [ ] **Step 7: Commit**

```bash
git add "tools/kdb_graph_viewer-opus.py" tools/tests/test_kdb_graph_viewer.py
git commit -m "feat(viewer): continuous cola layout with fcose/cose degrade ladder"
```

---

### Task 4: Qwen-style detail panel (typed clickable neighbors)

**Files:**
- Modify: `tools/kdb_graph_viewer-opus.py` (CSS for neighbor items; `showNode` rewrite; tap handler; focus-by-id helper)
- Test: `tools/tests/test_kdb_graph_viewer.py`

- [ ] **Step 1: Write the failing test**

Append to `tools/tests/test_kdb_graph_viewer.py`:

```python
def test_panel_neighbor_list_and_skip_set():
    html = _render_min()
    # noisy operational props are filtered out of the panel
    assert "SKIP_PROPS" in html
    assert "last_run_id" in html  # named in the skip set
    # neighbor list rendering + click-to-navigate helper
    assert "neighbor-item" in html
    assert "focusNodeById" in html
    assert "connectedEdges" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_kdb_graph_viewer.py::test_panel_neighbor_list_and_skip_set -m "not live" -q`
Expected: FAIL — neighbor tokens absent.

- [ ] **Step 3: Add neighbor-item CSS**

In the `<style>` block, find:

```css
  #panel .badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:10px;font-weight:600;color:#0d1117;margin-bottom:6px}
```

Add directly after it:

```css
  #panel .nbr-head{color:var(--faint);font-size:10px;text-transform:uppercase;letter-spacing:.04em;margin:10px 0 4px}
  .neighbor-item{display:flex;align-items:center;gap:6px;padding:3px 4px;border-radius:5px;cursor:pointer;font-size:11px}
  .neighbor-item:hover{background:rgba(127,127,127,.15)}
  .neighbor-item .dot{display:inline-block;width:9px;height:9px;border-radius:50%;flex:none}
  .neighbor-item .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .neighbor-item .et{color:var(--faint);font-size:9px}
```

- [ ] **Step 4: Rewrite `showNode` to accept the node element and render neighbors**

Find the whole current `showNode` function:

```javascript
  function showNode(d){
    const color = NODE_COLORS[d.label] || NODE_FALLBACK;
    let h = `<span class="badge" style="background:${color}">${d.label}</span>`;
    h += `<h3>${d.name}</h3>`;
    h += `<div><span class="k">degree:</span> ${d.degree}</div>`;
    const props = d.props || {};
    for(const [k,v] of Object.entries(props)){
      h += `<div><span class="k">${k}:</span> <pre style="display:inline">${v===null?'null':v}</pre></div>`;
    }
    panel.innerHTML = h;
  }
```

Replace it with (accepts the cy node; filters noisy props; builds a clickable neighbor list):

```javascript
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
    focusOn(n.closedNeighborhood());
    showNode(n);
    cy.animate({fit:{eles:n.closedNeighborhood(), padding:80}}, {duration:400});
  }
```

- [ ] **Step 5: Update the node tap handler to pass the element**

Find:

```javascript
  cy.on('tap','node',e=>{
    const n = e.target;
    focusOn(n.closedNeighborhood());
    showNode(n.data());
  });
```

Replace with (pass the element, not `.data()`):

```javascript
  cy.on('tap','node',e=>{
    const n = e.target;
    focusOn(n.closedNeighborhood());
    showNode(n);
  });
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tools/tests/test_kdb_graph_viewer.py -m "not live" -q`
Expected: PASS (all tests).

- [ ] **Step 7: Commit**

```bash
git add "tools/kdb_graph_viewer-opus.py" tools/tests/test_kdb_graph_viewer.py
git commit -m "feat(viewer): Qwen-style detail panel with clickable typed neighbors"
```

---

### Task 5: Visual gate on a real export

**Files:** none (manual verification + tuning)

- [ ] **Step 1: Build the viewer from a real graph**

The graph path is the live Kuzu DB used by run-3 (the same one the bake-off exported). Locate it, then:

Run: `python "tools/kdb_graph_viewer-opus.py" --graph-path <kuzu-db> --out /tmp/kdb-view-refined.html`
Expected: prints `Wrote /tmp/kdb-view-refined.html`, node/edge counts, labels, rels.

- [ ] **Step 2: Open in a browser and verify the spec acceptance**

Confirm:
- Constellation packs into one cluster (not scattered islands) and is **springy** — drag a node and the graph wobbles/settles.
- Nodes are small / Obsidian-like; Domain > Source > Entity visually.
- Clicking a node shows properties (no `created_at`/`*_run_id` noise) and a clickable typed-neighbor list; clicking a neighbor navigates to it.

- [ ] **Step 3: Tune if needed**

If clusters don't pack tightly enough or nodes feel wrong, adjust in `layoutOpts` (`nodeSpacing`, `edgeLength`) and `_node_size` (the `2 *` diameter factor). Re-build and re-check. Commit any tuning:

```bash
git add "tools/kdb_graph_viewer-opus.py"
git commit -m "tune(viewer): cola spacing / node scale from visual gate"
```

---

## Self-Review

**Spec coverage:**
- Change 1 (cola + springy + degrade) → Task 3 ✓
- Change 2 (Codex node sizes) → Tasks 1–2 ✓
- Change 3 (top panel no change) → no task needed (correctly untouched) ✓
- Change 4 (Qwen detail panel) → Task 4 ✓
- Testing (unit + visual gate) → unit in Tasks 1–4, visual in Task 5 ✓

**Type consistency:** `_node_size(label, degree)` defined Task 1, used same signature in Task 1 export loop and Task 1 tests. `showNode(node)` (element) rewritten Task 4 and the only caller (tap handler) updated same task; `focusNodeById(id)` defined and called within Task 4. `data(size)` (Task 2) matches the `size` field written in Task 1. `SKIP_PROPS` defined and referenced only in Task 4.

**Placeholder scan:** none — every code step shows complete code; `<kuzu-db>` in Task 5 is a real runtime path the operator supplies, not a code placeholder.
