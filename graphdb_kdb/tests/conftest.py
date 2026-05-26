"""Shared pytest fixtures + synthetic factories for graphdb_kdb tests."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def graph_dir(tmp_path: Path) -> Path:
    """Per-test ephemeral Kuzu directory path. Kuzu creates the directory itself."""
    return tmp_path / "GraphDB-KDB"


# ---------- synthetic factories ----------


def make_page(
    slug: str,
    *,
    page_type: str = "concept",
    title: str | None = None,
    status: str = "active",
    confidence: str = "medium",
    outgoing_links: list[str] | None = None,
    body: str = "",
    domain: str | list[str] | None = None,
    sub_domain: str | None = None,
) -> dict:
    """Construct a minimal compile_result page dict.

    `domain` accepts either a single string or a list of strings (#76 R5).
    `sub_domain` is set verbatim only when provided; the ingestor's
    omit-when-plural rule still applies at write time.
    """
    page = {
        "slug": slug,
        "page_type": page_type,
        "title": title if title is not None else f"Title for {slug}",
        "status": status,
        "confidence": confidence,
        "outgoing_links": outgoing_links or [],
        "body": body,
    }
    if domain is not None:
        page["domain"] = domain
    if sub_domain is not None:
        page["sub_domain"] = sub_domain
    return page


def make_compiled_source(
    source_id: str,
    pages: list[dict],
    *,
    compile_state: str = "compiled",
    source_hash: str = "sha256:abc",
    source_meta: dict | None = None,
) -> dict:
    """Construct a minimal compile_result.compiled_sources[i] dict.

    `source_meta` (D-89-17): optional Pass-1 frontmatter projection;
    included verbatim when provided. Keys: summary, author, domain,
    source_type, key_entities, key_themes.
    """
    d: dict = {
        "source_id": source_id,
        "pages": pages,
        "compile_meta": {
            "compile_state": compile_state,
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
