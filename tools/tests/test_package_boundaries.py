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


# --- #145 P0: kdb_fts write-boundary guard (blueprint D3) -------------------

_SQLITE_ALLOWLIST = {"ledger.py"}
_MKDIR_ALLOWLIST = {"ledger.py"}
_MUTATOR_ALLOWLIST = {"ledger.py"}


def _fts_write_violations(pkg_dir: pathlib.Path) -> list[str]:
    """AST scan of one tree for write-boundary violations. Returns messages."""
    violations: list[str] = []
    for path in pkg_dir.rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text())
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            # R1: sqlite3.connect outside the allowlist
            if (isinstance(n.func, ast.Attribute) and n.func.attr == "connect"
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "sqlite3"
                    and path.name not in _SQLITE_ALLOWLIST):
                violations.append(f"{path.name}:{n.lineno} sqlite3.connect outside ledger.py")
            # R2: open(...) — bare, Path.open, io.open — with a write-ish mode
            if (isinstance(n.func, ast.Name) and n.func.id == "open") or (
                isinstance(n.func, ast.Attribute) and n.func.attr == "open"
            ):
                mode = None
                if isinstance(n.func, ast.Attribute):
                    # Path.open(mode, ...) vs io.open(file, mode, ...) — take the
                    # first positional arg that is a pure mode string.
                    for arg in n.args[:2]:
                        if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                                and arg.value and all(c in "rwa+xbt" for c in arg.value)):
                            mode = arg.value
                            break
                elif len(n.args) >= 2 and isinstance(n.args[1], ast.Constant):
                    mode = n.args[1].value
                for kw in n.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = kw.value.value
                if isinstance(mode, str) and any(m in mode for m in "wax+"):
                    violations.append(f"{path.name}:{n.lineno} open(mode={mode!r}) — use common.atomic_io")
            # R3: mutating Path/os/shutil calls outside the allowlists
            if isinstance(n.func, ast.Attribute):
                attr = n.func.attr
                if (attr in {"write_text", "write_bytes", "unlink", "rename"}
                        and path.name not in _MUTATOR_ALLOWLIST):
                    violations.append(f"{path.name}:{n.lineno} Path.{attr} — writes go through ledger/atomic_io")
                if attr == "mkdir" and path.name not in _MKDIR_ALLOWLIST:
                    violations.append(f"{path.name}:{n.lineno} mkdir outside {_MKDIR_ALLOWLIST}")
                if (attr in {"remove", "replace"}
                        and isinstance(n.func.value, ast.Name) and n.func.value.id == "os"):
                    violations.append(f"{path.name}:{n.lineno} os.{attr}")
                if isinstance(n.func.value, ast.Name) and n.func.value.id == "shutil":
                    violations.append(f"{path.name}:{n.lineno} shutil.{attr}")
    return violations


def test_fts_write_boundary():
    assert _fts_write_violations(ROOT / "kdb_fts") == []


def test_fts_write_boundary_catches_violation(tmp_path):
    import shutil
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    shutil.copy(ROOT / "tools" / "tests" / "fixtures" / "write_boundary_violation.py",
                pkg / "bad.py")
    found = _fts_write_violations(pkg)
    assert sum("open(mode='w'" in v for v in found) == 2, found     # R2 bare + Path.open
    assert any("sqlite3.connect outside ledger.py" in v for v in found), found  # R1
    assert any("Path.unlink" in v for v in found), found            # R3
