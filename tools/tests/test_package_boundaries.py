import ast, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
INTERNAL = {"common", "ingestion", "compiler", "kdb_graph", "orchestrator", "tools",
            "kdb_compiler", "kdb_graph"}

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
    "kdb_graph":    {"common"},
    "ingestion":    {"common"},
    "compiler":     {"common", "kdb_graph"},
    "orchestrator": {"common", "kdb_graph", "ingestion", "compiler", "tools"},  # 'tools' = documented cleanup edge
    "tools":        {"common", "kdb_graph", "ingestion", "compiler"},
}


@pytest.mark.parametrize("pkg,allowed", list(ALLOWED.items()))
def test_package_dependency_contract(pkg, allowed):
    actual = _top_level_imports(pkg)
    illegal = actual - allowed
    assert not illegal, f"{pkg} imports outside its contract: {illegal}"


def test_nothing_depends_on_tools_except_orchestrator_cleanup():
    # 'nothing depends on tools' holds EXCEPT orchestrator->tools.cleanup
    # (orchestrate.finalize calls cleanup inline; decoupling is deferred, out of Phase B move-scope).
    for pkg in ("common", "ingestion", "compiler", "kdb_graph"):
        assert "tools" not in _top_level_imports(pkg), f"{pkg} must not depend on tools"
