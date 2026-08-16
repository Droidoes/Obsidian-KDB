import ast, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
INTERNAL = {"common", "ingestion", "kdb_graph_compiler", "kdb_graph", "kdb_graph_orchestrator", "tools", "kdb_mcp",
            "kdb_graph_search", "kdb_fts",
            # removed package roots — kept here so a future stale import of one
            # surfaces as an illegal edge rather than being silently ignored:
            "kdb_compiler", "graphdb_kdb", "kdb_benchmark"}

def _top_level_imports(pkg: str) -> set[str]:
    """All internal top-level packages imported anywhere under ROOT/pkg (non-test .py)."""
    out: set[str] = set()
    for path in (ROOT / pkg).rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text())
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module:
                root = n.module.split(".")[0]
                if root in INTERNAL and root != pkg:
                    out.add(root)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    root = a.name.split(".")[0]
                    if root in INTERNAL and root != pkg:
                        out.add(root)
    return out

def test_common_is_a_leaf():
    assert _top_level_imports("common") == set(), \
        f"common must import no internal package, found: {_top_level_imports('common')}"


import pytest

ALLOWED = {
    "common":       set(),
    "kdb_graph":    set(),  # zero internal imports — stricter than the doc contract; enforced here
    # #123 B1: the search core is consumer-neutral — it imports `common` only. The caller
    # materializes the space, so no kdb_graph edge; the P5b MCP edge waits for a named
    # materialization owner.
    "kdb_graph_search":   {"common"},
    "ingestion":    {"common"},
    "kdb_graph_compiler":     {"common", "kdb_graph", "kdb_graph_search"},  # #123 P3a: search_adapter
    "kdb_graph_orchestrator": {"common", "kdb_graph", "ingestion", "kdb_graph_compiler"},  # #133: cleanup edge removed
    "tools":        {"common", "kdb_graph", "ingestion", "kdb_graph_compiler", "kdb_graph_search"},  # #123 P4 harness
    "kdb_mcp":      {"common", "kdb_graph"},
    "kdb_fts":      {"common"},  # #145: parallel extraction system; leaf producer over common only
}


@pytest.mark.parametrize("pkg,allowed", list(ALLOWED.items()))
def test_package_dependency_contract(pkg, allowed):
    actual = _top_level_imports(pkg)
    illegal = actual - allowed
    assert not illegal, f"{pkg} imports outside its contract: {illegal}"


def test_nothing_depends_on_tools():
    # 'nothing depends on tools' holds without exception since #133 (the
    # kdb_graph_orchestrator->tools.cleanup edge — finalize calling cleanup inline — was
    # retired in #130 and its allowance removed in #133).
    for pkg in ("common", "ingestion", "kdb_graph_compiler", "kdb_graph", "kdb_graph_orchestrator"):
        assert "tools" not in _top_level_imports(pkg), f"{pkg} must not depend on tools"


def test_nothing_imports_kdb_fts():
    """v1: kdb_fts is a leaf producer — no internal package may import it (D2)."""
    for pkg in sorted(INTERNAL - {"kdb_fts"}):
        if not (ROOT / pkg).is_dir():
            continue
        offenders = _top_level_imports(pkg) & {"kdb_fts"}
        assert not offenders, f"{pkg} must not import kdb_fts (reads exports instead)"
