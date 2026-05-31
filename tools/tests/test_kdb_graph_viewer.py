import importlib.util
from pathlib import Path

# Hyphenated module name -> load via importlib.
_VIEWER = Path(__file__).resolve().parent.parent / "kdb_graph_viewer-opus.py"
_spec = importlib.util.spec_from_file_location("kdb_graph_viewer_opus", _VIEWER)
viewer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(viewer)


def test_node_size_small_scale():
    # diameter = base + min(8, sqrt(deg)*1.8)
    assert viewer._node_size("Domain", 0) == 11.0
    assert viewer._node_size("Source", 0) == 5.0
    assert viewer._node_size("Entity", 0) == 5.0
    assert viewer._node_size("Claim", 0) == 5.0
    # unknown label falls back to base 5
    assert viewer._node_size("Mystery", 0) == 5.0


def test_source_not_bigger_than_entity():
    # at equal degree, Source must never exceed Entity
    for deg in (0, 1, 9, 50, 200):
        assert viewer._node_size("Source", deg) == viewer._node_size("Entity", deg)


def test_node_size_degree_term_capped():
    # sqrt(100)*1.8 = 18 -> capped at 8 -> 5+8 = 13
    assert viewer._node_size("Entity", 100) == 13.0
    # small degree grows below the cap: deg 4 -> sqrt=2 *1.8=3.6 -> 5+3.6 = 8.6
    assert viewer._node_size("Entity", 4) == 8.6


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


def test_d3_force_layout_and_fallback():
    html = _render_min()
    # D3 force solver drives positions
    assert "d3.v7.min.js" in html
    assert "forceSimulation" in html
    assert "forceCenter" in html      # central packing -> one cluster
    assert "alphaTarget" in html      # springy reheat on drag
    assert "n.grabbed()" in html      # cytoscape owns the dragged node
    # static fallback if D3's CDN fails
    assert "name:'fcose'" in html
    assert "name:'cose'" in html
    # cola fully removed
    assert "cytoscape-cola" not in html
    assert "name:'cola'" not in html


def test_hover_focus_and_caption_gating():
    html = _render_min()
    assert "mouseover" in html        # [7] hover-triggered ego-focus
    assert "ZOOM_LABEL" in html       # [5] captions gated by zoom
    assert "refreshLabels" in html
    assert "'text-opacity':0" in html  # captions hidden by default


def test_panel_neighbor_list_and_skip_set():
    html = _render_min()
    # noisy operational props are filtered out of the panel
    assert "SKIP_PROPS" in html
    assert "last_run_id" in html  # named in the skip set
    # neighbor list rendering + click-to-navigate helper
    assert "neighbor-item" in html
    assert "focusNodeById" in html
    assert "connectedEdges" in html
