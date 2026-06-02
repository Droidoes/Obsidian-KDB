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
