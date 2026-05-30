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
from kdb_compiler.ingestion.pass1_caller import Pass1CallResult
from kdb_compiler.run_context import RunContext
from kdb_compiler.source_io import SourceFrontmatter
from graphdb_kdb.graphdb import GraphDB


@pytest.fixture(autouse=True)
def _clear_prompt_caches():
    prompt_builder.load_system_prompt.cache_clear()
    prompt_builder.load_response_schema_text.cache_clear()


def _fm() -> SourceFrontmatter:
    return SourceFrontmatter(
        kdb_signal="signal", domain="value-investing", source_type="paper",
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


# ---------- Task 4+5: finalize (merge → wire_links → orphans → cleanup → summary) ----------

def _page(slug: str, *, page_type="concept", outgoing=None) -> dict:
    return {"slug": slug, "page_type": page_type, "title": slug.title(),
            "body": "Body.", "status": "active",
            "outgoing_links": outgoing or [], "confidence": "medium"}


def _cr(source_id: str, pages: list[dict], *, aliases=None) -> dict:
    cs = {"source_id": source_id, "summary_slug": pages[0]["slug"],
          "pages": pages, "concept_slugs": [], "article_slugs": [],
          "compile_meta": {"provider": "p", "model": "m"}, "source_meta": None}
    cr = {"run_id": "r1", "success": True, "compiled_sources": [cs],
          "log_entries": [], "errors": [], "warnings": []}
    if aliases:
        cr["canonical_meta"] = {"aliases_emitted": aliases}
    return cr


def _scan_files(source_id: str) -> dict:
    return {"files": [{"path": source_id, "action": "NEW",
                       "current_hash": "sha256:" + "1" * 64, "current_mtime": 1.0,
                       "size_bytes": 1, "file_type": "markdown", "is_binary": False}],
            "to_compile": [source_id], "to_reconcile": []}


def test_combine_crs_unions_aliases_emitted():
    # Load-bearing for live≡replay: aliases live ONLY in canonical_meta, outside
    # compiled_sources — the merge must union them or replay loses ALIAS_OF edges.
    crA = _cr("a.md", [_page("ent-a")],
              aliases=[{"alias_slug": "al-a", "canonical_slug": "ent-a", "algorithm": "ledger"}])
    crB = _cr("b.md", [_page("ent-b")],
              aliases=[{"alias_slug": "al-b", "canonical_slug": "ent-b", "algorithm": "ledger"}])
    combined = kdb_orchestrate._combine_crs([crA, crB], "r1")
    assert len(combined["compiled_sources"]) == 2
    emitted = combined["canonical_meta"]["aliases_emitted"]
    assert {e["alias_slug"] for e in emitted} == {"al-a", "al-b"}


def test_finalize_wires_links_and_writes_compile_result(tmp_path):
    state_root = tmp_path / "state"
    state_root.mkdir()
    ctx = RunContext.new(vault_root=tmp_path)
    crA = _cr("a.md", [_page("ent-a", outgoing=["ent-b"])])
    crB = _cr("b.md", [_page("ent-b")])
    edge_q = ("MATCH (:Entity {slug: 'ent-a'})-[r:LINKS_TO]->(:Entity {slug: 'ent-b'}) "
              "RETURN COUNT(r)")
    with GraphDB(tmp_path / "graph") as g:
        # Per-source sync with links deferred (mirrors the orchestrator loop).
        g.apply_compile_result(crA, _scan_files("a.md"), ctx.run_id,
                               detect_orphans=False, wire_links=False)
        g.apply_compile_result(crB, _scan_files("b.md"), ctx.run_id,
                               detect_orphans=False, wire_links=False)
        before = _count(g, edge_q)
        stats = kdb_orchestrate._finalize(
            g.conn, [crA, crB], state_root=state_root, ctx=ctx)
        after = _count(g, edge_q)
    assert before == 0 and after == 1          # finalize wire_links wired the edge
    assert stats["links_wired"] >= 1
    assert stats["reaped"] == 0                # both entities supported → no orphans
    cr_json = json.loads((state_root / "compile_result.json").read_text(encoding="utf-8"))
    assert len(cr_json["compiled_sources"]) == 2


def test_write_last_orchestrate_json_fields(tmp_path):
    state_root = tmp_path / "state"
    state_root.mkdir()
    path = kdb_orchestrate.write_last_orchestrate_json(
        state_root, run_id="r1", started_at="t0", finished_at="t1",
        exit_code=0, exit_reason="ok",
        counts={"sources_scanned": 2, "sources_compiled": 1, "sources_failed": 0},
        manifest_delta={"added": ["a.md"], "removed": [], "changed": []},
        finalize={"links_wired": 1, "orphans_marked": 0, "reaped": 0})
    d = json.loads(path.read_text(encoding="utf-8"))
    assert d["run_id"] == "r1" and d["exit_code"] == 0 and d["exit_reason"] == "ok"
    assert d["counts"]["sources_compiled"] == 1
    assert d["finalize"]["links_wired"] == 1
    assert d["manifest_delta"]["added"] == ["a.md"]


# ---------- Task 3: run() loop — routing + fail-fast ----------

def _pass1_signal_envelope(model: str = "m") -> dict:
    return {
        "kdb_signal": "signal", "domain": "value-investing", "source_type": "paper",
        "author": "T", "summary": "S.", "key_themes": ["a"],
        "entity_search_keys": ["value-investing"],
        "confidence": 0.9, "uncertainty_reason": None, "reject_reason": None,
        "prompt_version": "p1", "model": model, "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": "signal", "reject_reason_cleared": None},
        "other_reason": None,
    }


def _compiled_response(source_name: str, summary_slug: str) -> dict:
    return {
        "source_name": source_name, "summary_slug": summary_slug,
        "concept_slugs": [], "article_slugs": [],
        "pages": [{"slug": summary_slug, "page_type": "summary", "title": "T",
                   "body": "Body.", "status": "active", "outgoing_links": [],
                   "confidence": "medium"}],
        "log_entries": [], "warnings": [],
    }


def _fake_pass1(**kwargs):
    return Pass1CallResult(
        parsed=_pass1_signal_envelope(kwargs["model"]), raw_response_text="{}",
        request_prompt="p", request_model=kwargs["model"],
        request_provider=kwargs["provider"], input_tokens=1, output_tokens=1,
        latency_ms=1, attempts=1)


def _write_pipelines(state_root: Path, vault_root: Path) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "pipelines.json").write_text(json.dumps({"pipelines": [
        {"id": "vt", "type": "in-place", "root": str(vault_root),
         "excludes": ["KDB/"], "force_noise": ["noise/*"], "file_types": [".md"]}
    ]}), encoding="utf-8")


def test_run_routes_signal_and_noise(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nValue investing note.\n", encoding="utf-8")
    (vault / "noise").mkdir()
    (vault / "noise" / "b.md").write_text("# B\n\nStandup notes.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("kdb_compiler.ingestion.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("kdb_compiler.compiler.call_model_with_retry",
                        _fake_model(_compiled_response("a.md", "summary-a")))

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    assert res.ok, res.exit_reason
    assert res.counts["sources_compiled"] == 1
    assert res.counts["sources_noise"] == 1
    with GraphDB(tmp_path / "graph") as g:
        assert _count(g, "MATCH (:Source {source_id: 'AIML/a.md'})-[r:SUPPORTS]->() "
                         "RETURN COUNT(r)") == 1            # signal graphed
        assert _count(g, "MATCH (s:Source {source_id: 'noise/b.md'}) "
                         "RETURN COUNT(s)") == 0            # noise NOT in graph
    assert list((vault / "KDB").rglob("summary-a.md"))      # signal wiki page
    manifest = json.loads((state_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sources"]["noise/b.md"]["compile_state"] == "metadata_only"
    assert manifest["sources"]["noise/b.md"]["last_compiled_hash"] is not None  # M2
    assert manifest["sources"]["AIML/a.md"]["pipeline_id"] == "vt"
    assert res.summary_path.exists()


def test_run_fail_fast_on_compile_error(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("kdb_compiler.ingestion.enrich.call_pass1", _fake_pass1)

    def boom(req):
        raise RuntimeError("model down")
    monkeypatch.setattr("kdb_compiler.compiler.call_model_with_retry", boom)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    assert not res.ok and res.exit_code == 1
    assert res.failure_stage == "compile"
    assert res.failed_source == "AIML/a.md"
    assert res.counts["sources_failed"] == 1
    assert res.summary_path.exists()       # summary written on abort (advisor #1)


# ---------- Task 6: CLI ----------

def test_cli_dry_run_smoke(tmp_path, capsys):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)

    rc = kdb_orchestrate.main(
        ["--pipeline", "vt", "--vault-root", str(vault), "--dry-run"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "dry-run" in out and "to compile" in out
    # dry-run fires no API and mutates nothing: no graph, no manifest
    assert not (vault / "KDB" / "graph").exists()
    assert not (state_root / "manifest.json").exists()
    assert (state_root / "last_orchestrate.json").exists()


def test_cli_lists_pipelines_when_omitted(tmp_path, capsys):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    _write_pipelines(state_root, vault)

    rc = kdb_orchestrate.main(["--vault-root", str(vault)])

    assert rc == 0
    assert "vt" in capsys.readouterr().out


# ---------- Task #99: --limit N ----------

def test_run_limit_stops_after_n_compiled(tmp_path, monkeypatch):
    """--limit N stops after N compiled (signal) sources; noise is free and
    does not count. Finalize still runs over the compiled batch (clean stop,
    not abort). Second source is left unprocessed — picked up on next run."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    # Two signal sources; limit=1 should compile only the first.
    (vault / "AIML" / "a.md").write_text("# A\n\nFirst.\n", encoding="utf-8")
    (vault / "AIML" / "b.md").write_text("# B\n\nSecond.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("kdb_compiler.ingestion.enrich.call_pass1", _fake_pass1)
    # Scan is alphabetical → AIML/a.md compiles first. limit=1 stops before b.md.
    compile_count = {"n": 0}

    def fake_model_counting(req):
        compile_count["n"] += 1
        # a.md is always first; return matching source_name
        return _fake_model(_compiled_response("a.md", "summary-a"))(req)

    monkeypatch.setattr("kdb_compiler.compiler.call_model_with_retry",
                        fake_model_counting)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096,
        limit=1)

    # clean stop: exit_code=0, reason=limit-reached
    assert res.ok, res.exit_reason
    assert res.exit_reason == "limit-reached"
    assert res.exit_code == 0
    # exactly 1 compiled, finalize ran (summary exists, no abort)
    assert res.counts["sources_compiled"] == 1
    assert res.counts["sources_failed"] == 0
    assert res.finalize is not None        # finalize ran over the 1-source batch
    assert res.summary_path.exists()
    # Pass-2 fired exactly once (second source never reached)
    assert compile_count["n"] == 1
    # manifest: only 1 of 2 sources is committed (second still has no record)
    manifest = json.loads((state_root / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest.get("sources", {})) == 1
