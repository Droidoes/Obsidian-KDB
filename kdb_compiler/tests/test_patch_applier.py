"""Tests for patch_applier — emitter + pure core + I/O shell + CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from kdb_compiler import manifest_update, patch_applier
from kdb_compiler.patch_applier import (
    ApplyResult,
    PagePatch,
    PagePatchError,
    apply,
    build_page_patches,
    emit_frontmatter,
    render_log_prepend,
    render_page,
)
from kdb_compiler.run_context import SCHEMA_VERSION, RunContext

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


def _page_record(slug: str, page_type: str, *,
                 title: str = "T",
                 status: str = "active",
                 source_refs: list[dict] | None = None) -> dict:
    refs = source_refs if source_refs is not None else [
        {"source_id": "KDB/raw/x.md", "hash": H1, "role": "primary"},
    ]
    page_key = f"KDB/wiki/{ {'summary':'summaries','concept':'concepts','article':'articles'}[page_type] }/{slug}.md"
    return {
        "page_id": page_key, "slug": slug, "page_type": page_type,
        "status": status, "title": title,
        "created_at": "2026-04-19T01:00:00Z", "updated_at": "2026-04-19T14:00:00Z",
        "last_run_id": "r1",
        "source_refs": refs,
        "supports_page_existence": [r["source_id"] for r in refs],
        "outgoing_links": [], "incoming_links_known": [],
        "last_link_reconciled_at": "2026-04-19T14:00:00Z",
        "confidence": "medium", "orphan_candidate": False,
    }


def _source_record(source_id: str, *, h: str = H1, mtime: float = 1700000000.0) -> dict:
    return {
        "source_id": source_id, "canonical_path": source_id,
        "status": "active", "file_type": "markdown",
        "hash": h, "mtime": mtime, "size_bytes": 100,
        "first_seen_at": "x", "last_seen_at": "x",
        "last_compiled_at": None, "last_run_id": "r1",
        "compile_state": "compiled", "compile_count": 1,
        "summary_page": None, "outputs_created": [], "outputs_touched": [],
        "concept_ids": [],
        "link_operations": {"links_added": 0, "links_removed": 0, "backlink_edits": 0},
        "provenance": {}, "previous_versions": [],
    }


def _manifest(pages: dict, sources: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "kb_id": "test-kdb",
        "created_at": "x", "updated_at": "x",
        "settings": {}, "stats": {}, "runs": {"last_run_id": None, "last_successful_run_id": None},
        "sources": sources, "pages": pages, "orphans": {}, "tombstones": {},
    }


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
    from kdb_compiler.patch_applier import _yaml_scalar
    assert _yaml_scalar(None) == "null"
    assert _yaml_scalar(True) == "true"
    assert _yaml_scalar(False) == "false"


# ===========================================================================
# build_page_patches (tests 8–13)
# ===========================================================================

def test_build_page_patches_new_page_body_and_fm() -> None:
    ctx = _ctx()
    page = _page_record("paper", "summary", title="A Paper")
    m = _manifest(pages={"KDB/wiki/summaries/paper.md": page},
                  sources={"KDB/raw/x.md": _source_record("KDB/raw/x.md")})
    cr = {"compiled_sources": [{
        "source_id": "KDB/raw/x.md", "summary_slug": "paper",
        "pages": [{"slug": "paper", "page_type": "summary", "title": "A Paper",
                   "body": "hello", "status": "active",
                   "supports_page_existence": ["KDB/raw/x.md"],
                   "outgoing_links": [], "confidence": "medium"}],
        "concept_slugs": [], "article_slugs": [],
    }]}
    patches = build_page_patches(cr, m, ctx)
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
    # Shared concept page; primary is one source, second compile emits same concept.
    page = _page_record("idea", "concept", source_refs=[
        {"source_id": "KDB/raw/a.md", "hash": H1, "role": "primary"},
        {"source_id": "KDB/raw/b.md", "hash": H2, "role": "supporting"},
    ])
    m = _manifest(pages={"KDB/wiki/concepts/idea.md": page},
                  sources={"KDB/raw/a.md": _source_record("KDB/raw/a.md"),
                           "KDB/raw/b.md": _source_record("KDB/raw/b.md", h=H2)})
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
    patches = build_page_patches(cr, m, ctx)
    assert len(patches) == 2
    assert {p.body.strip() for p in patches} == {"b1", "b2"}


def test_build_page_patches_multi_source_refs_primary_first() -> None:
    ctx = _ctx()
    refs = [
        {"source_id": "KDB/raw/main.md", "hash": H1, "role": "primary"},
        {"source_id": "KDB/raw/s1.md", "hash": H2, "role": "supporting"},
        {"source_id": "KDB/raw/s2.md", "hash": H3, "role": "supporting"},
    ]
    page = _page_record("paper", "summary", source_refs=refs)
    m = _manifest(pages={"KDB/wiki/summaries/paper.md": page},
                  sources={r["source_id"]: _source_record(r["source_id"], h=r["hash"])
                           for r in refs})
    cr = {"compiled_sources": [{
        "source_id": "KDB/raw/main.md", "summary_slug": "paper",
        "pages": [{"slug": "paper", "page_type": "summary", "title": "P",
                   "body": "b", "status": "active",
                   "supports_page_existence": [], "outgoing_links": [],
                   "confidence": "medium"}],
        "concept_slugs": [], "article_slugs": [],
    }]}
    patches = build_page_patches(cr, m, ctx)
    fm_refs = patches[0].frontmatter["source_refs"]
    assert fm_refs[0]["role"] == "primary"
    assert [r["role"] for r in fm_refs[1:]] == ["supporting", "supporting"]
    assert patches[0].frontmatter["raw_path"] == "KDB/raw/main.md"


def test_build_page_patches_orphan_status_propagates() -> None:
    ctx = _ctx()
    page = _page_record("p", "summary", status="orphan_candidate")
    m = _manifest(pages={"KDB/wiki/summaries/p.md": page},
                  sources={"KDB/raw/x.md": _source_record("KDB/raw/x.md")})
    cr = {"compiled_sources": [{
        "source_id": "KDB/raw/x.md", "summary_slug": "p",
        "pages": [{"slug": "p", "page_type": "summary", "title": "P",
                   "body": "b", "status": "orphan_candidate",
                   "supports_page_existence": [], "outgoing_links": [],
                   "confidence": "low"}],
        "concept_slugs": [], "article_slugs": [],
    }]}
    patches = build_page_patches(cr, m, ctx)
    assert patches[0].frontmatter["status"] == "orphan_candidate"


def test_build_page_patches_missing_page_record_raises() -> None:
    ctx = _ctx()
    m = _manifest(pages={}, sources={"KDB/raw/x.md": _source_record("KDB/raw/x.md")})
    cr = {"compiled_sources": [{
        "source_id": "KDB/raw/x.md", "summary_slug": "ghost",
        "pages": [{"slug": "ghost", "page_type": "summary", "title": "?",
                   "body": "b", "status": "active",
                   "supports_page_existence": [], "outgoing_links": [],
                   "confidence": "medium"}],
        "concept_slugs": [], "article_slugs": [],
    }]}
    with pytest.raises(PagePatchError, match="no PageRecord"):
        build_page_patches(cr, m, ctx)


def test_build_page_patches_concept_with_supporting_only_uses_first_ref() -> None:
    # Concept pages legitimately have no role=primary ref; first-by-source_id wins.
    ctx = _ctx()
    refs = [
        {"source_id": "KDB/raw/zeta.md", "hash": H2, "role": "supporting"},
        {"source_id": "KDB/raw/alpha.md", "hash": H1, "role": "supporting"},
    ]
    page = _page_record("idea", "concept", source_refs=refs)
    m = _manifest(pages={"KDB/wiki/concepts/idea.md": page},
                  sources={r["source_id"]: _source_record(r["source_id"], h=r["hash"])
                           for r in refs})
    cr = {"compiled_sources": [{
        "source_id": "KDB/raw/alpha.md", "summary_slug": "alpha",
        "pages": [{"slug": "idea", "page_type": "concept", "title": "Idea",
                   "body": "b", "status": "active",
                   "supports_page_existence": [], "outgoing_links": [],
                   "confidence": "medium"}],
        "concept_slugs": [], "article_slugs": [],
    }]}
    patches = build_page_patches(cr, m, ctx)
    # Alphabetically first source_id wins as the singular raw_* primary.
    assert patches[0].frontmatter["raw_path"] == "KDB/raw/alpha.md"
    assert patches[0].frontmatter["raw_hash"] == H1


def test_build_page_patches_empty_source_refs_raises() -> None:
    ctx = _ctx()
    page = _page_record("p", "summary", source_refs=[])
    m = _manifest(pages={"KDB/wiki/summaries/p.md": page}, sources={})
    cr = {"compiled_sources": [{
        "source_id": "KDB/raw/x.md", "summary_slug": "p",
        "pages": [{"slug": "p", "page_type": "summary", "title": "P",
                   "body": "b", "status": "active",
                   "supports_page_existence": [], "outgoing_links": [],
                   "confidence": "medium"}],
        "concept_slugs": [], "article_slugs": [],
    }]}
    with pytest.raises(PagePatchError, match="no source_refs"):
        build_page_patches(cr, m, ctx)


# ===========================================================================
# render_log_prepend (tests 17–20)
# ===========================================================================

def test_render_log_prepend_empty_log_uses_stub_header() -> None:
    out = render_log_prepend(_ctx(), "", {"success": True, "counts": {}})
    assert "# KDB Compile Log" in out
    assert "Most recent at top." in out
    assert "## Run 2026-04-19T14-00-00Z" in out
    assert "_(none)_" in out  # log_entries empty


def test_render_log_prepend_preserves_existing_content() -> None:
    existing = (
        "# KDB Compile Log\n\n"
        "_Append-only audit trail. Each compile run appends a block below. "
        "Most recent at top._\n\n---\n\n"
        "## Run OLDER\n\n- **Result:** success\n\n---\n"
    )
    out = render_log_prepend(_ctx(run_id="NEWER"), existing,
                             {"success": True, "counts": {}})
    new_pos = out.index("## Run NEWER")
    old_pos = out.index("## Run OLDER")
    assert new_pos < old_pos
    assert "Append-only audit trail" in out


def test_render_log_prepend_formats_log_entries_as_bullets() -> None:
    ctx = _ctx()
    ctx.log_entries = [
        {"level": "info", "message": "compiled paper", "run_id": ctx.run_id},
        {"level": "warning", "message": "ambiguous title", "run_id": ctx.run_id},
    ]
    out = render_log_prepend(ctx, "", {"success": True, "counts": {}})
    assert "- `info` — compiled paper" in out
    assert "- `warning` — ambiguous title" in out


def test_render_log_prepend_no_entries_shows_none() -> None:
    out = render_log_prepend(_ctx(), "", {"success": True, "counts": {}})
    assert "### Log entries\n\n_(none)_" in out


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


def _basic_manifest() -> dict:
    return _manifest(
        pages={"KDB/wiki/summaries/paper.md": _page_record("paper", "summary", title="Paper")},
        sources={"KDB/raw/x.md": _source_record("KDB/raw/x.md")},
    )


def test_apply_writes_page_index_and_log(tmp_path: Path) -> None:
    state = tmp_path / "state"
    vault = tmp_path / "vault"
    _seed_state(state, _basic_cr())
    ctx = _ctx(vault_root=vault)
    r = apply(state, vault, next_manifest=_basic_manifest(), run_ctx=ctx)
    assert r.pages_written == ["KDB/wiki/summaries/paper.md"]
    assert r.log_appended and not r.dry_run
    page_path = vault / "KDB/wiki/summaries/paper.md"
    assert page_path.exists()
    text = page_path.read_text()
    assert text.startswith("---\n")
    assert "slug: paper" in text
    assert "Body text." in text
    assert not (vault / "KDB/wiki/index.md").exists()
    assert (vault / "KDB/wiki/log.md").exists()


def test_apply_dry_run_writes_nothing(tmp_path: Path) -> None:
    state = tmp_path / "state"
    vault = tmp_path / "vault"
    _seed_state(state, _basic_cr())
    ctx = _ctx(vault_root=vault, dry_run=True)
    r = apply(state, vault, next_manifest=_basic_manifest(), run_ctx=ctx)
    assert r.dry_run is True
    assert r.pages_written == []
    assert not (vault / "KDB/wiki/summaries/paper.md").exists()
    assert not (vault / "KDB/wiki/index.md").exists()


def test_apply_missing_compile_result_raises(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    with pytest.raises(FileNotFoundError):
        apply(state, tmp_path / "vault",
              next_manifest=_basic_manifest(), run_ctx=_ctx())


def test_apply_normalizes_trailing_newline(tmp_path: Path) -> None:
    state = tmp_path / "state"
    vault = tmp_path / "vault"
    cr = _basic_cr()
    cr["compiled_sources"][0]["pages"][0]["body"] = "multi\nline\n\n\n"
    _seed_state(state, cr)
    ctx = _ctx(vault_root=vault)
    apply(state, vault, next_manifest=_basic_manifest(), run_ctx=ctx)
    text = (vault / "KDB/wiki/summaries/paper.md").read_text()
    # Exactly one trailing newline after the normalized body.
    assert text.endswith("multi\nline\n")


# ===========================================================================
# CLI (tests 25–27)
# ===========================================================================

def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "kdb_compiler.patch_applier", *args],
        capture_output=True, text=True,
    )


def _write_full_state(state_root: Path, vault_root: Path) -> None:
    # Minimal last_scan.
    scan = {
        "schema_version": "1.0", "run_id": "2026-04-19T14-00-00Z",
        "scanned_at": "2026-04-19T14:00:00Z",
        "vault_root": str(vault_root), "raw_root": "KDB/raw",
        "settings_snapshot": {"rename_detection": True, "symlink_policy": "skip",
                              "scan_binary_files": True,
                              "binary_compile_mode": "metadata_only"},
        "summary": {"new": 1, "changed": 0, "unchanged": 0, "moved": 0,
                    "deleted": 0, "error": 0, "skipped_symlink": 0},
        "files": [{"path": "KDB/raw/x.md", "action": "NEW",
                   "current_hash": H1, "current_mtime": 1700000000.0,
                   "size_bytes": 100, "file_type": "markdown", "is_binary": False}],
        "to_compile": ["KDB/raw/x.md"], "to_reconcile": [], "to_skip": [],
        "errors": [], "skipped_symlinks": [],
    }
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "last_scan.json").write_text(json.dumps(scan), encoding="utf-8")
    (state_root / "compile_result.json").write_text(json.dumps(_basic_cr()), encoding="utf-8")


def test_cli_happy_path_writes_wiki_but_not_manifest(tmp_path: Path) -> None:
    state = tmp_path / "state"
    vault = tmp_path / "vault"
    _write_full_state(state, vault)
    r = _run_cli(["--state-root", str(state), "--vault-root", str(vault)])
    assert r.returncode == 0, r.stderr
    assert (vault / "KDB/wiki/summaries/paper.md").exists()
    assert not (vault / "KDB/wiki/index.md").exists()
    assert (vault / "KDB/wiki/log.md").exists()
    assert not (state / "manifest.json").exists()  # patch_applier does NOT write manifest


def test_cli_dry_run_writes_nothing(tmp_path: Path) -> None:
    state = tmp_path / "state"
    vault = tmp_path / "vault"
    _write_full_state(state, vault)
    r = _run_cli(["--state-root", str(state), "--vault-root", str(vault), "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert not (vault / "KDB").exists()


def test_cli_missing_input_exits_two(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    r = _run_cli(["--state-root", str(state), "--vault-root", str(tmp_path / "v")])
    assert r.returncode == 2


# ===========================================================================
# Integration: render_page round-trip (test 28)
# ===========================================================================

def _parse_mini_frontmatter(text: str) -> dict:
    """Tiny parser matching patch_applier's emitter output (not a general YAML)."""
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
    page = _page_record("paper", "summary", title="A: Paper")  # colon forces quoting
    m = _manifest(pages={"KDB/wiki/summaries/paper.md": page},
                  sources={"KDB/raw/x.md": _source_record("KDB/raw/x.md",
                                                           mtime=1700000000.5)})
    ctx = _ctx()
    page_text = render_page(page, "Body.\n", m, ctx)
    fm = _parse_mini_frontmatter(page_text)
    assert fm["title"] == "A: Paper"
    assert fm["slug"] == "paper"
    assert fm["raw_mtime"] == 1700000000.5
    assert fm["source_refs"] == [
        {"source_id": "KDB/raw/x.md", "hash": H1, "role": "primary"},
    ]
