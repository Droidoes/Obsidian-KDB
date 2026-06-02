"""Split-gate tests: verifies common/llm_telemetry + compiler/resp_summary
exist with the right API, and that llm_telemetry is a leaf (no compiler
imports).
"""


def test_llm_telemetry_has_generic_helpers():
    from common.llm_telemetry import safe_source_id, build_resp_stats, write_resp_stats
    assert callable(safe_source_id) and callable(build_resp_stats) and callable(write_resp_stats)


def test_resp_summary_has_compiler_builder():
    from compiler.resp_summary import build_parsed_summary
    summary = build_parsed_summary({"pages": [], "summary_slug": "summary-x",
                                    "concept_slugs": [], "article_slugs": []})
    assert summary is not None


def test_llm_telemetry_is_leaf_no_compiler_import():
    import ast, pathlib, common
    src = pathlib.Path(common.__file__).parent / "llm_telemetry.py"
    tree = ast.parse(src.read_text())
    bad = set()
    for n in ast.walk(tree):
        mod = (n.module if isinstance(n, ast.ImportFrom) else None) or \
              (n.names[0].name if isinstance(n, ast.Import) else None)
        if mod and mod.split(".")[0] in {"compiler", "ingestion", "orchestrator", "tools", "kdb_compiler"}:
            bad.add(mod)
    assert not bad, f"common/llm_telemetry must not import non-common packages: {bad}"
