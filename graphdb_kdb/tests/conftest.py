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
) -> dict:
    """Construct a minimal compile_result page dict."""
    return {
        "slug": slug,
        "page_type": page_type,
        "title": title if title is not None else f"Title for {slug}",
        "status": status,
        "confidence": confidence,
        "outgoing_links": outgoing_links or [],
        "body": body,
    }


def make_compiled_source(
    source_id: str,
    pages: list[dict],
    *,
    compile_state: str = "compiled",
    source_hash: str = "sha256:abc",
) -> dict:
    """Construct a minimal compile_result.compiled_sources[i] dict."""
    return {
        "source_id": source_id,
        "pages": pages,
        "compile_meta": {
            "compile_state": compile_state,
            "hash": source_hash,
        },
    }


def make_compile_result(compiled_sources: list[dict], *, run_id: str = "test-run") -> dict:
    """Construct a minimal compile_result dict."""
    return {
        "run_id": run_id,
        "success": True,
        "compiled_sources": compiled_sources,
        "errors": [],
        "warnings": [],
    }


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
