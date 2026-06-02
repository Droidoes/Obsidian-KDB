"""Tests for page_writer — emitter + pure core + I/O shell + CLI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler import page_writer
from compiler.page_writer import (
    ApplyResult,
    PagePatch,
    PagePatchError,
    apply,
    build_page_patches,
    emit_frontmatter,
    render_page,
)
from common.run_context import SCHEMA_VERSION, RunContext

H1 = "sha256:" + "1" * 64
H2 = "sha256:" + "2" * 64
H3 = "sha256:" + "3" * 64


def _ctx(run_id: str = "2026-04-19T14-00-00Z",
         started_at: str = "2026-04-19T14:00:00Z",
         vault_root: Path | None = None,
         dry_run: bool = False) -> RunContext:
    vr = vault_root or Path("/tmp/vault")
    return RunContext(
        run_id=run_id,
        started_at=started_at,
        compiler_version="0.0.0-test",
        schema_version=SCHEMA_VERSION,
        dry_run=dry_run,
        vault_root=vr,
        kdb_root=vr / "KDB",
    )



# ===========================================================================
# YAML emitter (tests 1–7)
# ===========================================================================

def test_emit_frontmatter_fixed_key_order_bare_strings() -> None:
    fm = {
        "title": "Paper", "slug": "paper", "page_type": "summary",
        "status": "active",
        "raw_path": "KDB/raw/p.md", "raw_hash": H1, "raw_mtime": 1700000000.0,
        "compiled_at": "2026-04-19T14:00:00Z", "compiler_version": "0.0.0",
        "schema_version_used": "1.0",
        "source_refs": [{"source_id": "KDB/raw/p.md", "hash": H1, "role": "primary"}],
    }
    out = emit_frontmatter(fm)
    lines = out.splitlines()
    assert lines[0] == "---"
    assert lines[-2] == "---"
    # title appears before slug, slug before page_type, etc.
    key_lines = [ln for ln in lines if ln and ":" in ln and not ln.startswith(" ")
                 and not ln.startswith("-")]
    keys = [ln.split(":", 1)[0] for ln in key_lines]
    assert keys == ["title", "slug", "page_type", "status",
                    "raw_path", "raw_hash", "raw_mtime",
                    "compiled_at", "compiler_version", "schema_version_used",
                    "source_refs"]


def test_emit_frontmatter_string_with_colon_is_quoted() -> None:
    out = emit_frontmatter({"title": "Attention: A Survey", "slug": "a",
                            "page_type": "summary", "status": "active",
                            "raw_path": "KDB/raw/a.md", "raw_hash": H1,
                            "raw_mtime": 1.0, "compiled_at": "x",
                            "compiler_version": "v", "schema_version_used": "1.0",
                            "source_refs": []})
    assert 'title: "Attention: A Survey"' in out


def test_emit_frontmatter_escapes_double_quotes_and_backslash() -> None:
    out = emit_frontmatter({"title": 'She said "hi" \\', "slug": "a",
                            "page_type": "summary", "status": "active",
                            "raw_path": "KDB/raw/a.md", "raw_hash": H1,
                            "raw_mtime": 1.0, "compiled_at": "x",
                            "compiler_version": "v", "schema_version_used": "1.0",
                            "source_refs": []})
    assert r'title: "She said \"hi\" \\"' in out


def test_emit_frontmatter_float_mtime_preserved() -> None:
    out = emit_frontmatter({"title": "T", "slug": "a", "page_type": "summary",
                            "status": "active", "raw_path": "KDB/raw/a.md",
                            "raw_hash": H1, "raw_mtime": 1700000000.5,
                            "compiled_at": "x", "compiler_version": "v",
                            "schema_version_used": "1.0", "source_refs": []})
    assert "raw_mtime: 1700000000.5" in out


def test_emit_frontmatter_source_refs_block_style() -> None:
    refs = [
        {"source_id": "KDB/raw/a.md", "hash": H1, "role": "primary"},
        {"source_id": "KDB/raw/b.md", "hash": H2, "role": "supporting"},
    ]
    out = emit_frontmatter({"title": "T", "slug": "a", "page_type": "summary",
                            "status": "active", "raw_path": "KDB/raw/a.md",
                            "raw_hash": H1, "raw_mtime": 1.0,
                            "compiled_at": "x", "compiler_version": "v",
                            "schema_version_used": "1.0",
                            "source_refs": refs})
    # Block style: "  - source_id: ..." then "    hash: ..." then "    role: ..."
    assert "source_refs:\n  - source_id: KDB/raw/a.md\n    hash:" in out
    assert "  - source_id: KDB/raw/b.md\n    hash:" in out
    assert "role: supporting" in out


def test_emit_frontmatter_newline_in_string_raises() -> None:
    with pytest.raises(PagePatchError, match="newline"):
        emit_frontmatter({"title": "line1\nline2", "slug": "a",
                          "page_type": "summary", "status": "active",
                          "raw_path": "KDB/raw/a.md", "raw_hash": H1,
                          "raw_mtime": 1.0, "compiled_at": "x",
                          "compiler_version": "v", "schema_version_used": "1.0",
                          "source_refs": []})


def test_emit_frontmatter_null_and_bool_scalars() -> None:
    # None & bool scalars are valid outputs from the helpers; use a synthetic fm.
    from compiler.page_writer import _yaml_scalar
    assert _yaml_scalar(None) == "null"
    assert _yaml_scalar(True) == "true"
    assert _yaml_scalar(False) == "false"


# ===========================================================================
# build_page_patches (tests 8–13) — updated for D50 Phase C (scan-based)
# ===========================================================================

def test_build_page_patches_new_page_body_and_fm() -> None:
    ctx = _ctx()
    scan = _scan(files=[_scan_file("KDB/raw/x.md", h=H1, mtime=1700000000.0)])
    cr = {"compiled_sources": [{
        "source_id": "KDB/raw/x.md", "summary_slug": "paper",
        "pages": [{"slug": "paper", "page_type": "summary", "title": "A Paper",
                   "body": "hello", "status": "active",
                   "supports_page_existence": ["KDB/raw/x.md"],
                   "outgoing_links": [], "confidence": "medium"}],
        "concept_slugs": [], "article_slugs": [],
    }]}
    patches = build_page_patches(cr, scan, ctx)
    assert len(patches) == 1
    p = patches[0]
    assert p.page_key == "KDB/wiki/summaries/paper.md"
    assert p.abs_path == ctx.vault_root / "KDB/wiki/summaries/paper.md"
    assert p.body.endswith("\n")
    assert p.frontmatter["title"] == "A Paper"
    assert p.frontmatter["raw_path"] == "KDB/raw/x.md"
    assert p.frontmatter["raw_hash"] == H1


def test_build_page_patches_same_slug_from_two_sources_emits_two_patches() -> None:
    ctx = _ctx()
    scan = _scan(files=[
        _scan_file("KDB/raw/a.md", h=H1, mtime=1700000000.0),
        _scan_file("KDB/raw/b.md", h=H2, mtime=1700000001.0),
    ])
    cr = {"compiled_sources": [
        {"source_id": "KDB/raw/a.md", "summary_slug": "a",
         "pages": [{"slug": "idea", "page_type": "concept", "title": "Idea",
                    "body": "b1", "status": "active",
                    "supports_page_existence": [], "outgoing_links": [],
                    "confidence": "medium"}],
         "concept_slugs": [], "article_slugs": []},
        {"source_id": "KDB/raw/b.md", "summary_slug": "b",
         "pages": [{"slug": "idea", "page_type": "concept", "title": "Idea",
                    "body": "b2", "status": "active",
                    "supports_page_existence": [], "outgoing_links": [],
                    "confidence": "medium"}],
         "concept_slugs": [], "article_slugs": []},
    ]}
    patches = build_page_patches(cr, scan, ctx)
    assert len(patches) == 2
    assert {p.body.strip() for p in patches} == {"b1", "b2"}


def test_build_page_patches_summary_has_primary_role() -> None:
    """Source's summary page gets role=primary; only that source's ref appears."""
    ctx = _ctx()
    scan = _scan(files=[_scan_file("KDB/raw/main.md", h=H1, mtime=1700000000.0)])
    cr = {"compiled_sources": [{
        "source_id": "KDB/raw/main.md", "summary_slug": "paper",
        "pages": [{"slug": "paper", "page_type": "summary", "title": "P",
                   "body": "b", "status": "active",
                   "supports_page_existence": [], "outgoing_links": [],
                   "confidence": "medium"}],
        "concept_slugs": [], "article_slugs": [],
    }]}
    patches = build_page_patches(cr, scan, ctx)
    fm_refs = patches[0].frontmatter["source_refs"]
    assert len(fm_refs) == 1
    assert fm_refs[0]["role"] == "primary"
    assert patches[0].frontmatter["raw_path"] == "KDB/raw/main.md"


def test_build_page_patches_orphan_status_propagates() -> None:
    ctx = _ctx()
    scan = _scan(files=[_scan_file("KDB/raw/x.md")])
    cr = {"compiled_sources": [{
        "source_id": "KDB/raw/x.md", "summary_slug": "p",
        "pages": [{"slug": "p", "page_type": "summary", "title": "P",
                   "body": "b", "status": "orphan_candidate",
                   "supports_page_existence": [], "outgoing_links": [],
                   "confidence": "low"}],
        "concept_slugs": [], "article_slugs": [],
    }]}
    patches = build_page_patches(cr, scan, ctx)
    assert patches[0].frontmatter["status"] == "orphan_candidate"


def test_build_page_patches_source_missing_raises() -> None:
    """Source in compile_result but not in scan → error."""
    ctx = _ctx()
    scan = _scan(files=[])
    cr = {"compiled_sources": [{
        "source_id": "KDB/raw/x.md", "summary_slug": "ghost",
        "pages": [{"slug": "ghost", "page_type": "summary", "title": "?",
                   "body": "b", "status": "active",
                   "supports_page_existence": [], "outgoing_links": [],
                   "confidence": "medium"}],
        "concept_slugs": [], "article_slugs": [],
    }]}
    with pytest.raises(PagePatchError, match="missing from scan"):
        build_page_patches(cr, scan, ctx)


def test_build_page_patches_concept_with_supporting_only_uses_first_ref() -> None:
    """Concept pages have no role=primary ref; alphabetically first source wins."""
    ctx = _ctx()
    scan = _scan(files=[
        _scan_file("KDB/raw/zeta.md", h=H2, mtime=1700000000.0),
        _scan_file("KDB/raw/alpha.md", h=H1, mtime=1700000001.0),
    ])
    cr = {"compiled_sources": [
        {"source_id": "KDB/raw/zeta.md", "summary_slug": "zeta_summary",
         "pages": [{"slug": "idea", "page_type": "concept", "title": "Idea",
                    "body": "b", "status": "active",
                    "supports_page_existence": [], "outgoing_links": [],
                    "confidence": "medium"}],
         "concept_slugs": ["idea"], "article_slugs": []},
        {"source_id": "KDB/raw/alpha.md", "summary_slug": "alpha_summary",
         "pages": [{"slug": "idea", "page_type": "concept", "title": "Idea",
                    "body": "b", "status": "active",
                    "supports_page_existence": [], "outgoing_links": [],
                    "confidence": "medium"}],
         "concept_slugs": ["idea"], "article_slugs": []},
    ]}
    patches = build_page_patches(cr, scan, ctx)
    # Alphabetically first source_id wins as the singular raw_* primary.
    assert patches[0].frontmatter["raw_path"] == "KDB/raw/alpha.md"
    assert patches[0].frontmatter["raw_hash"] == H1


# ===========================================================================
# build_page_patches — Phase C (D50): derive from compile_result + scan
# ===========================================================================

def _scan(files: list[dict] | None = None) -> dict:
    """Minimal last_scan dict with files[]."""
    return {
        "schema_version": "1.0", "run_id": "2026-04-19T14-00-00Z",
        "scanned_at": "2026-04-19T14:00:00Z",
        "files": files or [],
        "to_compile": [], "to_reconcile": [], "to_skip": [],
    }


def _scan_file(path: str, *, h: str = H1, mtime: float = 1700000000.0) -> dict:
    return {
        "path": path, "action": "NEW",
        "current_hash": h, "current_mtime": mtime,
        "size_bytes": 100, "file_type": "markdown", "is_binary": False,
    }


def test_build_page_patches_derives_fm_from_compile_and_scan() -> None:
    """Phase C: frontmatter derived from compile_result + scan, no manifest.pages."""
    ctx = _ctx()
    scan = _scan(files=[_scan_file("KDB/raw/x.md", h=H1, mtime=1700000000.0)])
    cr = {"compiled_sources": [{
        "source_id": "KDB/raw/x.md", "summary_slug": "paper",
        "pages": [{"slug": "paper", "page_type": "summary", "title": "A Paper",
                   "body": "hello", "status": "active",
                   "supports_page_existence": ["KDB/raw/x.md"],
                   "outgoing_links": [], "confidence": "medium"}],
        "concept_slugs": [], "article_slugs": [],
    }]}
    patches = build_page_patches(cr, scan, ctx)
    assert len(patches) == 1
    p = patches[0]
    assert p.page_key == "KDB/wiki/summaries/paper.md"
    assert p.frontmatter["title"] == "A Paper"
    assert p.frontmatter["slug"] == "paper"
    assert p.frontmatter["page_type"] == "summary"
    assert p.frontmatter["status"] == "active"
    assert p.frontmatter["raw_path"] == "KDB/raw/x.md"
    assert p.frontmatter["raw_hash"] == H1
    assert p.frontmatter["raw_mtime"] == 1700000000.0
    assert p.frontmatter["source_refs"] == [
        {"source_id": "KDB/raw/x.md", "hash": H1, "role": "primary"},
    ]


def test_build_page_patches_concept_from_two_sources_accumulates_refs() -> None:
    """Phase C: concept emitted by two sources in same run → both refs in frontmatter."""
    ctx = _ctx()
    scan = _scan(files=[
        _scan_file("KDB/raw/a.md", h=H1, mtime=1700000000.0),
        _scan_file("KDB/raw/b.md", h=H2, mtime=1700000001.0),
    ])
    cr = {"compiled_sources": [
        {"source_id": "KDB/raw/a.md", "summary_slug": "a_summary",
         "pages": [{"slug": "idea", "page_type": "concept", "title": "Idea",
                    "body": "b1", "status": "active",
                    "supports_page_existence": [], "outgoing_links": [],
                    "confidence": "medium"}],
         "concept_slugs": ["idea"], "article_slugs": []},
        {"source_id": "KDB/raw/b.md", "summary_slug": "b_summary",
         "pages": [{"slug": "idea", "page_type": "concept", "title": "Idea",
                    "body": "b2", "status": "active",
                    "supports_page_existence": [], "outgoing_links": [],
                    "confidence": "medium"}],
         "concept_slugs": ["idea"], "article_slugs": []},
    ]}
    patches = build_page_patches(cr, scan, ctx)
    assert len(patches) == 2
    # Both patches for the same concept page carry both source_refs
    for p in patches:
        refs = p.frontmatter["source_refs"]
        assert len(refs) == 2
        source_ids = {r["source_id"] for r in refs}
        assert source_ids == {"KDB/raw/a.md", "KDB/raw/b.md"}
        # Both are "supporting" (neither source's summary_slug == "idea")
        assert all(r["role"] == "supporting" for r in refs)
    # Primary ref (for raw_path/raw_hash) falls back to alphabetically first
    assert patches[0].frontmatter["raw_path"] == "KDB/raw/a.md"
    assert patches[0].frontmatter["raw_hash"] == H1



# ===========================================================================
# apply (tests 21–24)
# ===========================================================================

def _seed_state(state_root: Path, compile_result: dict, last_scan: dict | None = None) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "compile_result.json").write_text(json.dumps(compile_result), encoding="utf-8")
    if last_scan is not None:
        (state_root / "last_scan.json").write_text(json.dumps(last_scan), encoding="utf-8")


def _basic_cr() -> dict:
    return {
        "run_id": "2026-04-19T14-00-00Z", "success": True,
        "compiled_sources": [{
            "source_id": "KDB/raw/x.md", "summary_slug": "paper",
            "pages": [{"slug": "paper", "page_type": "summary", "title": "Paper",
                       "body": "Body text.", "status": "active",
                       "supports_page_existence": ["KDB/raw/x.md"],
                       "outgoing_links": [], "confidence": "medium"}],
            "concept_slugs": [], "article_slugs": [],
        }],
        "log_entries": [], "errors": [], "warnings": [],
    }


def _basic_scan() -> dict:
    return _scan(files=[_scan_file("KDB/raw/x.md", h=H1, mtime=1700000000.0)])


def test_apply_writes_page_only(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    ctx = _ctx(vault_root=vault)
    r = apply(
        vault,
        compile_result=_basic_cr(),
        last_scan=_basic_scan(),
        run_ctx=ctx,
    )
    assert r.pages_written == ["KDB/wiki/summaries/paper.md"]
    assert not r.dry_run
    page_path = vault / "KDB/wiki/summaries/paper.md"
    assert page_path.exists()
    text = page_path.read_text()
    assert text.startswith("---\n")
    assert "slug: paper" in text
    assert "Body text." in text
    assert not (vault / "KDB/wiki/index.md").exists()
    assert not (vault / "KDB/wiki/log.md").exists()


def test_apply_dry_run_writes_nothing(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    ctx = _ctx(vault_root=vault, dry_run=True)
    r = apply(
        vault,
        compile_result=_basic_cr(),
        last_scan=_basic_scan(),
        run_ctx=ctx,
    )
    assert r.dry_run is True
    assert r.pages_written == []
    assert not (vault / "KDB/wiki/summaries/paper.md").exists()
    assert not (vault / "KDB/wiki/index.md").exists()


def test_apply_normalizes_trailing_newline(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    cr = _basic_cr()
    cr["compiled_sources"][0]["pages"][0]["body"] = "multi\nline\n\n\n"
    ctx = _ctx(vault_root=vault)
    apply(
        vault,
        compile_result=cr,
        last_scan=_basic_scan(),
        run_ctx=ctx,
    )
    text = (vault / "KDB/wiki/summaries/paper.md").read_text()
    # Exactly one trailing newline after the normalized body.
    assert text.endswith("multi\nline\n")


# ===========================================================================
# Integration: render_page round-trip (test 28)
# ===========================================================================

def _parse_mini_frontmatter(text: str) -> dict:
    """Tiny parser matching page_writer's emitter output (not a general YAML)."""
    assert text.startswith("---\n")
    end = text.index("\n---\n", 4)
    block = text[4:end]
    out: dict = {}
    cur_list: list[dict] | None = None
    cur_dict: dict | None = None
    for line in block.splitlines():
        if line.startswith("  - "):
            cur_dict = {}
            cur_list.append(cur_dict)  # type: ignore[union-attr]
            k, _, v = line[4:].partition(": ")
            cur_dict[k] = _unquote(v)
        elif line.startswith("    "):
            k, _, v = line.strip().partition(": ")
            cur_dict[k] = _unquote(v)  # type: ignore[index]
        else:
            k, _, v = line.partition(": ")
            if k.endswith(":"):
                k = k[:-1]
            if v == "":
                cur_list = []
                out[k] = cur_list
                cur_dict = None
            else:
                out[k] = _unquote(v)
    return out


def _unquote(v: str) -> object:
    if v.startswith('"') and v.endswith('"'):
        return v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if v == "null":
        return None
    if v == "true":
        return True
    if v == "false":
        return False
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        return v


def test_render_page_roundtrip_frontmatter() -> None:
    from compiler.page_writer import _scan_source_meta
    intent = {"slug": "paper", "page_type": "summary", "title": "A: Paper",
              "status": "active"}
    source_refs = [{"source_id": "KDB/raw/x.md", "hash": H1, "role": "primary"}]
    scan = _scan(files=[_scan_file("KDB/raw/x.md", h=H1, mtime=1700000000.5)])
    scan_meta = _scan_source_meta(scan)
    ctx = _ctx()
    page_text = render_page(intent, "Body.\n", source_refs, scan_meta, ctx)
    fm = _parse_mini_frontmatter(page_text)
    assert fm["title"] == "A: Paper"
    assert fm["slug"] == "paper"
    assert fm["raw_mtime"] == 1700000000.5
    assert fm["source_refs"] == [
        {"source_id": "KDB/raw/x.md", "hash": H1, "role": "primary"},
    ]
