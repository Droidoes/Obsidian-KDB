"""Split-gate tests: verifies common/llm_telemetry + kdb_graph_compiler/resp_summary
exist with the right API, and that llm_telemetry is a leaf (no kdb_graph_compiler
imports).

#119 (Codex PR3 F2): build_parsed_summary's 4.0 semantics — `page_count`
counts well-formed page DICTS (a slugless 4.0 summary page still counts);
`slugs` / `summary_slug` are raw model-supplied slug evidence (None/absent
for compliant 4.0 proposals).
"""


def test_llm_telemetry_has_generic_helpers():
    from common.llm_telemetry import safe_source_id, build_resp_stats, write_resp_stats
    assert callable(safe_source_id) and callable(build_resp_stats) and callable(write_resp_stats)


def test_resp_summary_has_compiler_builder():
    from kdb_graph_compiler.resp_summary import build_parsed_summary
    summary = build_parsed_summary({"pages": [], "summary_slug": "summary-x",
                                    "concept_slugs": [], "article_slugs": []})
    assert summary is not None


# ---------- #119 4.0 summary-slug evidence variants (Codex PR3 F2) ----------

def test_absent_summary_slug_counts_page_dicts():
    """Compliant 4.0 proposal: the summary page carries NO slug — it must
    still count in page_count; summary_slug/slugs carry no evidence."""
    from kdb_graph_compiler.resp_summary import build_parsed_summary
    s = build_parsed_summary({"pages": [
        {"page_type": "summary", "title": "T", "body": "B."},
        {"page_type": "concept", "slug": "a", "title": "A", "body": "A."},
    ]})
    assert s.page_count == 2          # page DICTS, not slug-bearing pages
    assert s.summary_slug is None     # no model-supplied evidence
    assert s.slugs == ["a"]


def test_stray_string_summary_slug_is_raw_evidence():
    """A stray-string summary slug (bridge would ignore it) still surfaces
    as raw evidence in summary_slug/slugs; page_count counts the dict."""
    from kdb_graph_compiler.resp_summary import build_parsed_summary
    s = build_parsed_summary({"pages": [
        {"page_type": "summary", "slug": "summary-x-deviant",
         "title": "T", "body": "B."},
    ]})
    assert s.page_count == 1
    assert s.summary_slug == "summary-x-deviant"   # raw evidence, not validation
    assert s.slugs == ["summary-x-deviant"]


def test_nonstring_summary_slug_is_no_evidence():
    """A non-string summary slug is not well-formed evidence: summary_slug
    None, excluded from slugs — but the page dict still counts."""
    from kdb_graph_compiler.resp_summary import build_parsed_summary
    s = build_parsed_summary({"pages": [
        {"page_type": "summary", "slug": {"x": 1}, "title": "T", "body": "B."},
    ]})
    assert s.page_count == 1
    assert s.summary_slug is None
    assert s.slugs == []


def test_llm_telemetry_is_leaf_no_compiler_import():
    import ast, pathlib, common
    src = pathlib.Path(common.__file__).parent / "llm_telemetry.py"
    tree = ast.parse(src.read_text())
    bad = set()
    for n in ast.walk(tree):
        mod = (n.module if isinstance(n, ast.ImportFrom) else None) or \
              (n.names[0].name if isinstance(n, ast.Import) else None)
        if mod and mod.split(".")[0] in {"kdb_graph_compiler", "ingestion", "kdb_graph_orchestrator", "tools", "kdb_compiler"}:
            bad.add(mod)
    assert not bad, f"common/llm_telemetry must not import non-common packages: {bad}"
