"""Guard test: common-layer modules (types, source_io) must not import upward.

types.py must not import source_io (to avoid a cycle: source_io → types → source_io).
source_io.py must not import kdb_compiler.enrich.* (leaf must not depend on a stage).
"""
import ast
import pathlib


def _imports(rel: str) -> set[str]:
    # types.py and source_io.py now live in common/ (Phase-B leaf extract).
    src = pathlib.Path(__file__).parents[2] / "common" / rel
    tree = ast.parse(src.read_text())
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
    return out


def test_types_does_not_import_source_io():
    assert "common.source_io" not in _imports("types.py")


def test_source_io_does_not_import_ingestion():
    assert not any(m.startswith("kdb_compiler.enrich") for m in _imports("source_io.py"))
