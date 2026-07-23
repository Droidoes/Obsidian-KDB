import importlib.util
from pathlib import Path

_VIEWER = Path(__file__).resolve().parent.parent / "viewer" / "kdb_graph_viewer.py"
_spec = importlib.util.spec_from_file_location("kdb_graph_viewer", _VIEWER)
viewer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(viewer)

_DATA = {
    "nodes": [
        {"id": "Entity:0", "type": "Entity", "name": "Alpha", "props": {"slug": "alpha"}},
        {"id": "Source:0", "type": "Source", "name": "src.md", "props": {}},
    ],
    "edges": [{"id": "SUPPORTS:Source:0->Entity:0", "source": "Source:0",
               "target": "Entity:0", "type": "SUPPORTS"}],
    "summary": {"node_types": {"Entity": 1, "Source": 1}, "edge_types": {"SUPPORTS": 1}},
}


def test_official_template_exists_and_two_thirds_scale():
    t = viewer.TEMPLATE_PATH.read_text(encoding="utf-8")
    assert viewer.DATA_TOKEN in t            # injection point present
    assert "* 2/3" in t                      # node radius baked to 2/3 of bake-off scale


def test_render_html_injects_data_and_consumes_token():
    html = viewer.render_html(_DATA)
    assert viewer.DATA_TOKEN not in html     # token consumed
    assert '"Entity:0"' in html              # node payload embedded
    assert '"SUPPORTS"' in html              # edge payload embedded


def test_render_html_missing_token_raises(tmp_path):
    bad = tmp_path / "no_token.html"
    bad.write_text("<html>no token here</html>", encoding="utf-8")
    try:
        viewer.render_html(_DATA, template_path=bad)
        assert False, "expected ValueError for missing token"
    except ValueError:
        pass


def test_export_omits_deprecated_entity_confidence(tmp_path):
    """Codex Gate-3 F1 (#115 D-115-12): the official viewer exporter must
    NOT return Entity.confidence in props — even when the dead Kuzu column
    still holds a legacy non-null value."""
    from kdb_graph.graphdb import GraphDB

    graph_dir = tmp_path / "graph"
    with GraphDB(graph_dir) as g:
        g.conn.execute(
            "CREATE (e:Entity {slug: 'alpha', title: 'Alpha', "
            "page_type: 'concept', status: 'active', confidence: 'high', "
            "created_at: 't', updated_at: 't', first_run_id: 'r', "
            "last_run_id: 'r'})"
        )
    data = viewer.export(str(graph_dir))
    entity_nodes = [n for n in data["nodes"] if n["type"].startswith("Entity")]
    assert entity_nodes, "seeded Entity must be exported"
    for n in entity_nodes:
        assert "confidence" not in n["props"]


def test_bakeoff_export_omits_deprecated_entity_confidence(tmp_path):
    """Same F1 contract for the preserved bake-off fallback exporter."""
    import importlib.util as _ilu

    _bo = Path(__file__).resolve().parent.parent / "viewer" / "bakeoff" / "export_graph.py"
    _spec = _ilu.spec_from_file_location("export_graph", _bo)
    bo = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(bo)

    from kdb_graph.graphdb import GraphDB

    graph_dir = tmp_path / "graph"
    with GraphDB(graph_dir) as g:
        g.conn.execute(
            "CREATE (e:Entity {slug: 'alpha', title: 'Alpha', "
            "page_type: 'concept', status: 'active', confidence: 'high', "
            "created_at: 't', updated_at: 't', first_run_id: 'r', "
            "last_run_id: 'r'})"
        )
    data = bo.export(str(graph_dir))
    entity_nodes = [n for n in data["nodes"] if n["type"] == "Entity"]
    assert entity_nodes, "seeded Entity must be exported"
    for n in entity_nodes:
        assert "confidence" not in n["props"]
