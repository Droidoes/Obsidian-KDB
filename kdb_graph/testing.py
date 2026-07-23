"""Public, shippable test-support factories for kdb_graph consumers.

Synthetic compile_result / scan dicts for exercising graph intake/read code
without a live producer. Lives in the package (not tests/) so cross-package
test suites import a stable surface instead of reaching into kdb_graph.tests.conftest.
"""
from __future__ import annotations


def make_page(
    slug: str,
    *,
    page_type: str = "concept",
    title: str | None = None,
    status: str = "active",
    outgoing_links: list[str] | None = None,
    body: str = "",
) -> dict:
    """Construct a minimal compile_result page dict.

    #115 Phase 3 (D-115-12): no `confidence` key — Entity confidence is
    logically deprecated; new fixtures never emit it.
    """
    return {
        "slug": slug,
        "page_type": page_type,
        "title": title if title is not None else f"Title for {slug}",
        "status": status,
        "outgoing_links": outgoing_links or [],
        "body": body,
    }


def make_compiled_source(
    source_id: str,
    pages: list[dict],
    *,
    run_state: str = "in_graph_db",
    source_hash: str = "sha256:abc",
    source_meta: dict | None = None,
) -> dict:
    """Construct a minimal compile_result.compiled_sources[i] dict.

    `source_meta` (D-89-17 amended by D-89-19/D-89-20, v0.2.2): optional Pass-1
    frontmatter projection; included verbatim when provided. Keys: summary
    (already carries key_themes appended per D-89-19), author, domain,
    source_type.
    """
    d: dict = {
        "source_id": source_id,
        "pages": pages,
        "compile_meta": {
            "run_state": run_state,
            "hash": source_hash,
        },
    }
    if source_meta is not None:
        d["source_meta"] = source_meta
    return d


def make_compile_result(
    compiled_sources: list[dict],
    *,
    run_id: str = "test-run",
    canonical_meta: dict | None = None,
) -> dict:
    """Construct a minimal compile_result dict.

    `canonical_meta` (#74.5) is included verbatim when provided. Pass a
    full dict shaped like Stage 6's emit: {algorithm_version,
    ledger_snapshot_sha256, aliases_emitted, outgoing_link_remaps,
    merged_pages}.
    """
    cr = {
        "run_id": run_id,
        "success": True,
        "compiled_sources": compiled_sources,
        "errors": [],
        "warnings": [],
    }
    if canonical_meta is not None:
        cr["canonical_meta"] = canonical_meta
    return cr


def make_scan_entry(
    source_id: str,
    *,
    hash_: str = "sha256:abc",
    size_bytes: int = 100,
    file_type: str = "markdown",
) -> dict:
    """Construct a minimal last_scan.files[i] dict."""
    return {
        "path": source_id,
        "action": "CHANGED",
        "current_hash": hash_,
        "size_bytes": size_bytes,
        "file_type": file_type,
        "is_binary": False,
    }


def make_scan(files: list[dict], *, to_reconcile: list[dict] | None = None) -> dict:
    """Construct a minimal last_scan dict."""
    return {
        "files": files,
        "to_reconcile": to_reconcile or [],
    }
