"""Task #91 Plan 5+6 — kdb_orchestrate conductor tests.

All non-live: the Pass-2 model is faked via monkeypatch (test_compile_source
pattern). Run: python -m pytest kdb_compiler/tests/test_kdb_orchestrate.py -m "not live"
"""
import json
from pathlib import Path

import pytest

from kdb_compiler import compiler, kdb_orchestrate, prompt_builder
from kdb_compiler.call_model import ModelResponse
from kdb_compiler.canonicalize import load_or_empty
from kdb_compiler.run_context import RunContext
from kdb_compiler.source_io import SourceFrontmatter
from graphdb_kdb.graphdb import GraphDB


@pytest.fixture(autouse=True)
def _clear_prompt_caches():
    prompt_builder.load_system_prompt.cache_clear()
    prompt_builder.load_response_schema_text.cache_clear()


def _fm() -> SourceFrontmatter:
    return SourceFrontmatter(
        kdb_signal="signal", domain="value-investing", source_type="essay",
        author="Test", summary="A summary.", key_themes=["a"],
        entity_search_keys=["value-investing"],
    )


def _vault(tmp_path: Path) -> Path:
    (tmp_path / "KDB").mkdir(parents=True, exist_ok=True)
    (tmp_path / "KDB" / "KDB-Compiler-System-Prompt.md").write_text(
        "# KDB invariants\n", encoding="utf-8")
    (tmp_path / "KDB" / "state").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _two_page_response() -> dict:
    # Summary page wikilinks a concept → reconcile_body_links keeps the edge in
    # outgoing_links. Both pages live in one source, so a LINKS_TO edge is
    # wireable — proving _commit_source's wire_links=False genuinely skips it.
    return {
        "source_name": "s.md", "summary_slug": "summary-foo",
        "concept_slugs": ["concept-b"], "article_slugs": [],
        "pages": [
            {"slug": "summary-foo", "page_type": "summary", "title": "Foo",
             "body": "See [[concept-b]].", "status": "active",
             "outgoing_links": ["concept-b"], "confidence": "medium"},
            {"slug": "concept-b", "page_type": "concept", "title": "B",
             "body": "Body.", "status": "active",
             "outgoing_links": [], "confidence": "medium"},
        ],
        "log_entries": [], "warnings": [],
    }


def _fake_model(response: dict):
    def fake(req):
        return ModelResponse(
            text=json.dumps(response), input_tokens=100, output_tokens=50,
            latency_ms=10, model="m", provider="p", attempts=1)
    return fake


def _scan_entry(source_id: str, *, pipeline_id="vault-test") -> dict:
    return {
        "path": source_id, "action": "NEW",
        "current_hash": "sha256:" + "0" * 64,   # pre-embed; _commit_source overrides
        "current_mtime": 1.0, "size_bytes": 42,
        "file_type": "markdown", "is_binary": False, "pipeline_id": pipeline_id,
    }


def _count(g, query: str) -> int:
    r = g.conn.execute(query)
    return int(r.get_next()[0]) if r.has_next() else 0


def test_commit_source_beta_apply_graphsync_manifest(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    source_id = "AIML/s.md"
    post_embed_hash = "sha256:" + "a" * 64
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_model(_two_page_response()))

    with GraphDB(tmp_path / "graph") as g:
        produced = compiler.compile_source(
            source_id=source_id, body="A note. See [[concept-b]].",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096)
        assert produced.ok, (produced.failure_stage, produced.error)

        result = kdb_orchestrate._commit_source(
            cr=produced.cr, source_id=source_id,
            post_embed_hash=post_embed_hash, post_embed_mtime=2.0,
            scan_entry=_scan_entry(source_id),
            prior_manifest={}, vault_root=vault, state_root=state_root,
            conn=g.conn, ctx=ctx)

        n_supports = _count(g, "MATCH (:Source)-[r:SUPPORTS]->() RETURN COUNT(r)")
        n_links = _count(g, "MATCH ()-[r:LINKS_TO]->() RETURN COUNT(r)")

    assert result.ok and result.graph_committed
    # wiki pages written (stage 8)
    assert list((vault / "KDB").rglob("summary-foo.md")), "summary page not written"
    assert list((vault / "KDB").rglob("concept-b.md")), "concept page not written"
    # graph: SUPPORTS wired per-source; LINKS_TO deferred (wire_links=False)
    assert n_supports == 2
    assert n_links == 0
    # manifest committed with the POST-embed hash (not the scan's pre-embed hash)
    manifest = json.loads((state_root / "manifest.json").read_text(encoding="utf-8"))
    rec = manifest["sources"][source_id]
    assert rec["last_compiled_hash"] == post_embed_hash
    assert rec["hash"] == post_embed_hash
    assert rec["pipeline_id"] == "vault-test"
    # cr accumulated for the finalize passes
    assert result.cr is produced.cr
