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


def test_panel_neighbor_list_and_skip_set():
    html = _render_min()
    # noisy operational props are filtered out of the panel
    assert "SKIP_PROPS" in html
    assert "last_run_id" in html  # named in the skip set
    # neighbor list rendering + click-to-navigate helper
    assert "neighbor-item" in html
    assert "focusNodeById" in html
    assert "connectedEdges" in html
