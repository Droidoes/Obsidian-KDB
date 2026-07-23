"""Task #91 Plan 5+6 — kdb_orchestrate conductor tests.

All non-live: the Pass-2 model is faked via monkeypatch (test_compile_source
pattern). Run: python -m pytest orchestrator/tests/test_kdb_orchestrate.py -m "not live"
"""
import hashlib
import json
from pathlib import Path

import pytest

from compiler import compiler, prompt_builder
from orchestrator import kdb_orchestrate
import orchestrator.emit_kpis as _emit_kpis_mod
from common.call_model import ModelResponse
from compiler.canonicalize import load_or_empty
from compiler.prompt_builder import PASS2_PROMPT_VERSION, load_system_prompt
from ingestion.enrich.pass1_caller import Pass1CallError, Pass1CallResult
from ingestion.enrich.pass1_prompt import PASS1_PROMPT_VERSION
from common.run_context import RunContext
from common.source_io import SourceFrontmatter
from common.types import CompileSourceResult
from kdb_graph.graphdb import GraphDB


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
    # The system prompt is repo-packaged (post-#115) — no vault prompt file.
    (tmp_path / "KDB").mkdir(parents=True, exist_ok=True)
    (tmp_path / "KDB" / "state").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _two_page_response(source_id: str) -> dict:
    # New #115 shape: 4-field pages; the summary slug derives from the source;
    # the summary body wikilinks a concept so a LINKS_TO edge is wireable —
    # proving _commit_source's wire_links=False genuinely skips it (T2.4
    # derives edges from bodies).
    from compiler.summary_slug import expected_summary_slug
    return {
        "pages": [
            {"slug": expected_summary_slug(source_id), "page_type": "summary",
             "title": "Foo", "body": "See [[concept-b]]."},
            {"slug": "concept-b", "page_type": "concept", "title": "B",
             "body": "Body."},
        ],
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


def _event_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_commit_source_beta_apply_graphsync_manifest(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    source_id = "AIML/s.md"
    post_embed_hash = "sha256:" + "a" * 64
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        _fake_model(_two_page_response(source_id)))

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
    assert list((vault / "KDB").rglob("summary-s.md")), "summary page not written"
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
    event_log = state_root / "runs" / "r1" / "orchestrator_events.jsonl"
    path = kdb_orchestrate.write_last_orchestrate_json(
        state_root, run_id="r1", started_at="t0", finished_at="t1",
        exit_code=0, exit_reason="ok",
        counts={"sources_scanned": 2, "sources_compiled": 1, "sources_failed": 0},
        manifest_delta={"added": ["a.md"], "removed": [], "changed": []},
        finalize={"links_wired": 1, "orphans_marked": 0, "reaped": 0},
        event_log_path=event_log,
        warnings=2,
        sources_quarantined=1,
        invariant_violations=0,
        quarantined_sources=[{"source_id": "a.md", "stage": "compile"}])
    d = json.loads(path.read_text(encoding="utf-8"))
    assert d["run_id"] == "r1" and d["exit_code"] == 0 and d["exit_reason"] == "ok"
    assert d["counts"]["sources_compiled"] == 1
    assert d["finalize"]["links_wired"] == 1
    assert d["manifest_delta"]["added"] == ["a.md"]
    assert d["event_log_path"] == str(event_log)
    assert d["event_log_failed"] is False
    assert d["counts"]["warnings"] == 2
    assert d["counts"]["sources_quarantined"] == 1
    assert d["counts"]["invariant_violations"] == 0
    assert d["quarantined_sources"] == [{"source_id": "a.md", "stage": "compile"}]


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
    # New #115 shape: 4-field pages only. (summary_slug arg retained so each
    # caller pins the derived slug for its source.)
    return {
        "pages": [{"slug": summary_slug, "page_type": "summary", "title": "T",
                   "body": "Body."}],
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
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
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
    assert manifest["sources"]["noise/b.md"]["run_state"] == "no_graph_db"
    assert manifest["sources"]["noise/b.md"]["last_compiled_hash"] is not None  # M2
    assert manifest["sources"]["AIML/a.md"]["pipeline_id"] == "vt"
    assert res.summary_path.exists()


def test_default_run_streams_progress_to_stdout(tmp_path, monkeypatch, capsys):
    # Default run streams the live per-stage narrative to stdout (no flag needed).
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nValue investing note.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        _fake_model(_compiled_response("a.md", "summary-a")))

    kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    out = capsys.readouterr().out
    assert "kdb-orchestrate · run " in out      # header
    assert "to process" in out
    assert "▸ " in out                          # a per-source line
    assert "pass-1 enrich…" in out              # stage-start marker
    assert "pass-2 compile…" in out


def test_quiet_suppresses_progress_but_keeps_jsonl(tmp_path, monkeypatch, capsys):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nValue investing note.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        _fake_model(_compiled_response("a.md", "summary-a")))

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096,
        log_level="info", quiet=True)

    out = capsys.readouterr().out
    assert "pass-1 enrich…" not in out
    assert "▸ " not in out
    assert res.event_log_path.exists()          # JSONL still written


def test_successful_run_writes_stage_and_source_events(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nValue investing note.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        _fake_model(_compiled_response("a.md", "summary-a")))

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096,
        log_level="debug")

    rows = _event_rows(res.event_log_path)
    event_types = [row["event_type"] for row in rows]
    assert res.ok
    assert "run_started" in event_types
    assert "scan_completed" in event_types
    assert "source_started" in event_types
    assert "pass1_enrich_started" in event_types
    assert "pass1_enrich_completed" in event_types
    assert "pass1_gate_signal" in event_types
    assert "pass2_compile_started" in event_types
    assert "pass2_compile_completed" in event_types
    assert "source_commit_completed" in event_types
    assert "finalize_completed" in event_types
    assert event_types[-1] == "run_finished"
    assert any(row["source_id"] == "AIML/a.md" for row in rows)
    summary = json.loads(res.summary_path.read_text(encoding="utf-8"))
    assert summary["counts"]["warnings"] == 0
    assert summary["counts"]["sources_quarantined"] == 0
    assert summary["counts"]["invariant_violations"] == 0
    assert summary["quarantined_sources"] == []


def test_run_quarantines_compile_error_and_continues(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    (vault / "AIML" / "b.md").write_text("# B\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    def boom(req):
        if "a.md" in req.prompt:
            raise RuntimeError("model down")
        return _fake_model(_compiled_response("b.md", "summary-b"))(req)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", boom)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    assert res.ok and res.exit_reason == "completed_with_quarantines"
    assert res.failed_source is None
    assert res.counts["sources_failed"] == 1
    assert res.counts["sources_compiled"] == 1
    assert res.counts["sources_quarantined"] == 1
    assert res.quarantined_sources == [{
        "source_id": "AIML/a.md",
        "stage": "compile",
        "exception_type": "RuntimeError",
    }]
    assert res.summary_path.exists()
    summary = json.loads(res.summary_path.read_text(encoding="utf-8"))
    assert summary["exit_reason"] == "completed_with_quarantines"
    assert summary["finalize"] == res.finalize
    assert summary["counts"]["sources_quarantined"] == 1
    assert summary["quarantined_sources"] == res.quarantined_sources
    cr_json = json.loads((state_root / "compile_result.json").read_text(encoding="utf-8"))
    assert [cs["source_id"] for cs in cr_json["compiled_sources"]] == ["AIML/b.md"]
    manifest = json.loads((state_root / "manifest.json").read_text(encoding="utf-8"))
    failed = manifest["sources"]["AIML/a.md"]
    assert failed["run_state"] == "error_compile"
    assert failed["last_compiled_hash"] is None
    assert failed["last_failure"]["stage"] == "compile"
    assert failed["last_failure"]["exception_type"] == "RuntimeError"
    assert manifest["sources"]["AIML/b.md"]["run_state"] == "in_graph_db"
    rows = _event_rows(res.event_log_path)
    assert any(
        row["event_type"] == "source_quarantined"
        and row["severity"] == "source_quarantine"
        and row["stage"] == "compile"
        and row["source_id"] == "AIML/a.md"
        for row in rows
    )


def test_event_log_failure_is_surfaced_in_summary(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    def boom(req):
        raise RuntimeError("model down")
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", boom)

    def broken_recorder(cls, *, state_root, run_id, log_level="warning", console=None):
        return cls(run_id=run_id, events_path=Path(state_root), log_level=log_level,
                   console=console)

    monkeypatch.setattr(
        kdb_orchestrate.EventRecorder,
        "for_state_root",
        classmethod(broken_recorder),
    )

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    summary = json.loads(res.summary_path.read_text(encoding="utf-8"))
    assert res.event_log_failed is True
    assert summary["event_log_failed"] is True
    assert summary["counts"]["sources_quarantined"] == 1


def test_pass1_failure_event_references_raw_response_sidecar(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    (vault / "AIML" / "b.md").write_text("# B\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)

    def bad_pass1(**kwargs):
        if str(kwargs["source_path"]).endswith("b.md"):
            return _fake_pass1(**kwargs)
        raise Pass1CallError(
            "bad pass1",
            raw_response_text="{bad json",
            request_prompt="prompt",
            request_model="m",
            request_provider="p",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            attempts=1,
        )

    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", bad_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        _fake_model(_compiled_response("b.md", "summary-b")))

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    assert res.ok and res.exit_reason == "completed_with_quarantines"
    assert res.counts["sources_failed"] == 1
    assert res.counts["sources_compiled"] == 1
    manifest = json.loads((state_root / "manifest.json").read_text(encoding="utf-8"))
    failed = manifest["sources"]["AIML/a.md"]
    assert failed["run_state"] == "error_ingest"
    assert failed["last_compiled_hash"] is None
    assert failed["last_failure"]["stage"] == "pass1_enrich"
    assert failed["last_failure"]["exception_type"] == "Pass1EnrichError"
    assert failed["last_failure"]["artifacts"]["raw_response"].endswith("AIML__a.md.json")
    assert manifest["sources"]["AIML/b.md"]["run_state"] == "in_graph_db"
    rows = _event_rows(res.event_log_path)
    event = next(row for row in rows if row["event_type"] == "source_quarantined")
    assert event["stage"] == "pass1_enrich"
    assert event["artifacts"]["raw_response"].endswith("AIML__a.md.json")
    sidecar = json.loads(Path(event["artifacts"]["raw_response"]).read_text(encoding="utf-8"))
    assert sidecar["raw_response"]["body"] == "{bad json"
    assert not any(row["event_type"] == "raw_response_unavailable" for row in rows)


def test_pass2_invalid_response_event_references_raw_resp_stats(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    def bad_json(req):
        return ModelResponse(
            text='{"source_name": "a.md",,}',
            input_tokens=10,
            output_tokens=5,
            latency_ms=10,
            model="m",
            provider="p",
            attempts=1,
        )

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", bad_json)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    assert res.ok and res.exit_reason == "completed_with_quarantines"
    manifest = json.loads((state_root / "manifest.json").read_text(encoding="utf-8"))
    failed = manifest["sources"]["AIML/a.md"]
    assert failed["run_state"] == "error_compile"
    assert failed["last_compiled_hash"] is None
    assert failed["last_failure"]["stage"] == "compile"
    assert failed["last_failure"]["artifacts"]["raw_response"].endswith(".json")
    assert not (state_root / "compile_result.json").exists()
    assert res.finalize is None
    rows = _event_rows(res.event_log_path)
    event = next(row for row in rows if row["event_type"] == "source_quarantined")
    assert event["stage"] == "compile"
    assert "raw_response" in event["artifacts"]
    record = json.loads(Path(event["artifacts"]["raw_response"]).read_text(encoding="utf-8"))
    assert record["raw_response_text"] == '{"source_name": "a.md",,}'
    assert not any(row["event_type"] == "raw_response_unavailable" for row in rows)


def test_finalize_runs_after_later_source_quarantine_and_wires_committed_links(
    tmp_path, monkeypatch
):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    (vault / "AIML" / "b.md").write_text("# B\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    calls = {"n": 0}

    def model(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return _fake_model(_two_page_response("AIML/a.md"))(req)
        raise RuntimeError("model down")

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", model)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    assert res.ok and res.exit_reason == "completed_with_quarantines"
    assert res.counts["sources_compiled"] == 1
    assert res.counts["sources_failed"] == 1
    assert res.finalize is not None
    assert res.finalize["links_wired"] >= 1
    with GraphDB(tmp_path / "graph") as g:
        assert _count(
            g,
            "MATCH (:Entity {slug: 'summary-a'})-[r:LINKS_TO]->"
            "(:Entity {slug: 'concept-b'}) RETURN COUNT(r)",
        ) == 1
    cr_json = json.loads((state_root / "compile_result.json").read_text(encoding="utf-8"))
    assert [cs["source_id"] for cs in cr_json["compiled_sources"]] == ["AIML/a.md"]
    manifest = json.loads((state_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sources"]["AIML/a.md"]["run_state"] == "in_graph_db"
    assert manifest["sources"]["AIML/b.md"]["run_state"] == "error_compile"


def test_all_quarantined_skips_finalize_but_writes_summary_and_event_log(
    tmp_path, monkeypatch
):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    def boom(req):
        raise RuntimeError("model down")

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", boom)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    assert res.ok and res.exit_reason == "completed_with_quarantines"
    assert res.finalize is None
    assert res.summary_path.exists()
    assert res.event_log_path.exists()
    assert not (state_root / "compile_result.json").exists()
    rows = _event_rows(res.event_log_path)
    assert any(row["event_type"] == "finalize_skipped" for row in rows)


def test_source_local_commit_failure_marks_error_commit_and_continues(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    (vault / "AIML" / "b.md").write_text("# B\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    def model(req):
        if "a.md" in req.prompt:
            return _fake_model(_compiled_response("a.md", "summary-a"))(req)
        return _fake_model(_compiled_response("b.md", "summary-b"))(req)

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", model)
    original_commit_source = kdb_orchestrate._commit_source

    def flaky_commit(*args, **kwargs):
        if kwargs["source_id"] == "AIML/a.md":
            return kdb_orchestrate.CommitResult(
                failure_stage="apply",
                exception_type="RuntimeError",
                error="apply down",
            )
        return original_commit_source(*args, **kwargs)

    monkeypatch.setattr(kdb_orchestrate, "_commit_source", flaky_commit)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    assert res.ok and res.exit_reason == "completed_with_quarantines"
    assert res.counts["sources_failed"] == 1
    assert res.counts["sources_compiled"] == 1
    manifest = json.loads((state_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sources"]["AIML/a.md"]["run_state"] == "error_commit"
    assert manifest["sources"]["AIML/a.md"]["last_failure"]["stage"] == "apply"
    assert manifest["sources"]["AIML/b.md"]["run_state"] == "in_graph_db"


def test_missing_raw_response_emits_unavailable_event(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    def boom(req):
        raise RuntimeError("model down")

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", boom)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    rows = _event_rows(res.event_log_path)
    event = next(row for row in rows if row["event_type"] == "raw_response_unavailable")
    assert event["severity"] == "warning"
    assert event["source_id"] == "AIML/a.md"
    assert event["artifacts"]["resp_stats"].endswith(".json")


def test_unexpected_exception_writes_run_fatal_event_and_summary(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nValue investing note.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        _fake_model(_compiled_response("a.md", "summary-a")))

    def boom_finalize(*_args, **_kwargs):
        raise RuntimeError("finalize down")

    monkeypatch.setattr(kdb_orchestrate, "_finalize", boom_finalize)

    with pytest.raises(RuntimeError, match="finalize down"):
        kdb_orchestrate.run(
            pipeline_id="vt", vault_root=vault, state_root=state_root,
            graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    summary = json.loads((state_root / "last_orchestrate.json").read_text(encoding="utf-8"))
    assert summary["exit_reason"] == "unexpected:RuntimeError"
    event_logs = list((state_root / "runs").glob("*/orchestrator_events.jsonl"))
    assert len(event_logs) == 1
    rows = _event_rows(event_logs[0])
    assert any(
        row["event_type"] == "run_fatal"
        and row["severity"] == "run_fatal"
        and row["exception_type"] == "RuntimeError"
        and row["error"] == "finalize down"
        for row in rows
    )


def test_orchestrator_invariant_violation_writes_event_and_summary(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nValue investing note.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    def malformed_compile_source(*_args, **_kwargs):
        return CompileSourceResult(cr={
            "run_id": "bad",
            "success": True,
            "compiled_sources": [],
            "log_entries": [],
            "errors": [],
            "warnings": [],
        })

    monkeypatch.setattr(kdb_orchestrate, "compile_source", malformed_compile_source)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    assert res.exit_code == 1
    assert res.exit_reason == "invariant:compile_success_single_source_cr"
    assert res.failure_stage == "invariant_violation"
    assert res.counts["invariant_violations"] == 1
    summary = json.loads(res.summary_path.read_text(encoding="utf-8"))
    assert summary["exit_reason"] == "invariant:compile_success_single_source_cr"
    assert summary["counts"]["invariant_violations"] == 1
    rows = _event_rows(res.event_log_path)
    assert any(
        row["event_type"] == "invariant_violation"
        and row["severity"] == "invariant_violation"
        and row["stage"] == "pass2_compile"
        and row["source_id"] == "AIML/a.md"
        for row in rows
    )


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
    assert "event_log:" in out
    # dry-run fires no API and mutates nothing: no graph, no manifest
    assert not (vault / "KDB" / "graph").exists()
    assert not (state_root / "manifest.json").exists()
    assert (state_root / "last_orchestrate.json").exists()


def test_cli_makes_quarantine_alarm_visible(tmp_path, monkeypatch, capsys):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    def boom(req):
        raise RuntimeError("model down")
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", boom)

    rc = kdb_orchestrate.main([
        "--pipeline", "vt", "--vault-root", str(vault),
        "--graph-path", str(tmp_path / "graph"),
        "--provider", "p", "--model", "m",
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert "reason=completed_with_quarantines" in captured.out
    assert "alarm: quarantined=1" in captured.err
    assert "AIML/a.md" in captured.err


def test_cli_log_level_warning_default(tmp_path):
    args = kdb_orchestrate._build_parser().parse_args(
        ["--vault-root", str(tmp_path)])

    assert kdb_orchestrate._resolve_log_level(args) == "warning"


def test_cli_verbose_sets_info(tmp_path):
    args = kdb_orchestrate._build_parser().parse_args(
        ["--vault-root", str(tmp_path), "--verbose"])

    assert kdb_orchestrate._resolve_log_level(args) == "info"


def test_cli_debug_sets_debug(tmp_path):
    args = kdb_orchestrate._build_parser().parse_args(
        ["--vault-root", str(tmp_path), "--debug"])

    assert kdb_orchestrate._resolve_log_level(args) == "debug"


def test_cli_explicit_log_level_wins_over_alias(tmp_path):
    args = kdb_orchestrate._build_parser().parse_args(
        ["--vault-root", str(tmp_path), "--debug", "--log-level", "warning"])

    assert kdb_orchestrate._resolve_log_level(args) == "warning"


def test_provider_default_is_none_escape_hatch():
    # --provider demoted to an escape hatch; default must be None so the pool
    # supplies the provider for known ids. (Fail-first driver: current default is "deepseek".)
    # The --model default STRING is unchanged ("deepseek-v4-flash") — Task 1.1's rename
    # makes that same string resolve to the ACTIVE direct entry.
    parser = kdb_orchestrate._build_parser()
    args = parser.parse_args(["--vault-root", "/tmp/x", "--pipeline", "p"])
    assert args.provider is None
    assert args.model == "deepseek-v4-flash"


def test_default_model_resolves_to_active_deepseek():
    from common.model_pool import resolve_models_json
    parser = kdb_orchestrate._build_parser()
    args = parser.parse_args(["--vault-root", "/tmp/x", "--pipeline", "p"])
    spec = resolve_models_json(args.model)
    assert spec.provider == "deepseek"
    assert spec.model == "deepseek-v4-flash"


def test_main_rejects_unknown_model_without_provider(tmp_path):
    import common.model_pool
    with pytest.raises(common.model_pool.PoolError):  # UnknownModelError is fine too
        kdb_orchestrate.main(
            ["--vault-root", str(tmp_path), "--pipeline", "p", "--model", "bogus-id"])


def test_main_archived_model_without_provider_raises_unknown(tmp_path):
    # An archived (formerly-dropped) id is no longer in the active pool: with no
    # --provider override it surfaces UnknownModelError.
    import common.model_pool
    with pytest.raises(common.model_pool.UnknownModelError):
        kdb_orchestrate.main([
            "--vault-root", str(tmp_path), "--pipeline", "p",
            "--model", "qwen-flash-us",
        ])


def test_main_archived_model_with_provider_uses_escape_hatch(tmp_path, monkeypatch):
    # With --provider the escape hatch activates (raw passthrough) — assert run(...)
    # is reached with the override provider + the raw model string.
    def _sentinel(**kwargs):
        assert kwargs["provider"] == "alibaba"
        assert kwargs["model"] == "qwen-flash-us"
        raise RuntimeError("reached_run")
    monkeypatch.setattr(kdb_orchestrate, "run", _sentinel)
    with pytest.raises(RuntimeError, match="reached_run"):
        kdb_orchestrate.main([
            "--vault-root", str(tmp_path), "--pipeline", "p",
            "--provider", "alibaba", "--model", "qwen-flash-us",
        ])


def test_main_known_id_conflicting_provider_errors(tmp_path):
    # #110 spec §4: a KNOWN pool id pins its provider. If --provider is also
    # passed and CONFLICTS, error (catch the mistake) rather than silently
    # ignoring --provider. deepseek-v4-flash resolves to provider 'deepseek';
    # --provider openai conflicts → PoolError before run().
    import common.model_pool
    with pytest.raises(common.model_pool.PoolError):
        kdb_orchestrate.main([
            "--vault-root", str(tmp_path), "--pipeline", "p",
            "--provider", "openai", "--model", "deepseek-v4-flash",
        ])


def test_main_known_id_matching_provider_does_not_error(tmp_path, monkeypatch):
    # Non-conflicting --provider (same as the pool's) must NOT error: it sails
    # past the guard into run(). Sentinel-raise run() to prove we got past the
    # resolve block without firing the real pipeline (or the model).
    def _sentinel(**kwargs):
        raise RuntimeError("reached_run")
    monkeypatch.setattr(kdb_orchestrate, "run", _sentinel)
    with pytest.raises(RuntimeError, match="reached_run"):
        kdb_orchestrate.main([
            "--vault-root", str(tmp_path), "--pipeline", "p",
            "--provider", "deepseek", "--model", "deepseek-v4-flash",
        ])


def test_run_writes_event_log_path_to_summary(tmp_path):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096,
        dry_run=True, log_level="debug")

    summary = json.loads(res.summary_path.read_text(encoding="utf-8"))
    assert res.event_log_path == state_root / "runs" / res.run_id / "orchestrator_events.jsonl"
    assert summary["event_log_path"] == str(res.event_log_path)
    assert summary["event_log_failed"] is False


def test_dry_run_writes_plan_events_when_info_enabled(tmp_path):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096,
        dry_run=True, log_level="info")

    rows = _event_rows(res.event_log_path)
    event_types = [row["event_type"] for row in rows]
    assert event_types == [
        "run_started",
        "scan_completed",
        "dry_run_planned",
        "run_finished",
    ]


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
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    # Scan is alphabetical → AIML/a.md compiles first. limit=1 stops before b.md.
    compile_count = {"n": 0}

    def fake_model_counting(req):
        compile_count["n"] += 1
        # a.md is always first; return matching source_name
        return _fake_model(_compiled_response("a.md", "summary-a"))(req)

    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
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


# ---------- Task #109 B1 delta #3: measurement_header.json at finalize ----------

def test_run_writes_measurement_header_at_finalize(tmp_path, monkeypatch):
    """run() writes measurement_header.json to the run dir at finalize.

    Setup: 1 signal source (AIML/a.md) + 1 noise source (noise/b.md via
    force_noise pipeline rule).  Expected header:
        scanned=2, to_compile=2, signal=1, noise=1,
        p1_attempted=2, p2_attempted=1,
        corpus_fingerprint = 64-hex sha256,
        pass1_prompt_version = PASS1_PROMPT_VERSION,
        pass2_prompt_version = PASS2_PROMPT_VERSION,
        pass2_system_prompt_sha256 = sha256 of the packaged prompt (post-#115).
    """
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nValue investing note.\n", encoding="utf-8")
    (vault / "noise").mkdir()
    (vault / "noise" / "b.md").write_text("# B\n\nStandup notes.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        _fake_model(_compiled_response("a.md", "summary-a")))

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    assert res.ok, res.exit_reason

    header_path = state_root / "runs" / res.run_id / "measurement_header.json"
    assert header_path.exists(), f"measurement_header.json not found at {header_path}"

    hdr = json.loads(header_path.read_text(encoding="utf-8"))
    assert hdr["run_id"] == res.run_id
    assert hdr["scanned"] == 2
    assert hdr["to_compile"] == 2
    assert hdr["signal"] == 1
    assert hdr["noise"] == 1
    assert hdr["p1_attempted"] == 2
    assert hdr["p2_attempted"] == 1
    # corpus_fingerprint: 64-char lowercase hex
    fp = hdr["corpus_fingerprint"]
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)
    # prompt versions
    assert hdr["pass1_prompt_version"] == PASS1_PROMPT_VERSION
    assert hdr["pass2_prompt_version"] == PASS2_PROMPT_VERSION
    # post-#115 stamp: SHA-256 of the loaded (packaged) Pass-2 system prompt
    assert hdr["pass2_system_prompt_sha256"] == hashlib.sha256(
        load_system_prompt().encode("utf-8")
    ).hexdigest()


# ---------- Task #111 Phase 0 Task 2: release_version recorded in header ----------

def test_run_records_release_version_in_header(tmp_path, monkeypatch):
    """run() populates measurement_header.json["release_version"] (non-empty)."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nValue investing note.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        _fake_model(_compiled_response("a.md", "summary-a")))

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    assert res.ok, res.exit_reason
    header_path = state_root / "runs" / res.run_id / "measurement_header.json"
    hdr = json.loads(header_path.read_text(encoding="utf-8"))
    assert hdr["release_version"], "release_version must be non-empty"


# ---------- Task #109: --emit-kpis writes benchmark/runs/<id>/measurements.json ----------

def _setup_single_signal_vault(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Set up a vault with one signal source and monkeypatched LLM calls.

    Returns (vault, state_root).
    """
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nValue investing note.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        _fake_model(_compiled_response("a.md", "summary-a")))
    return vault, state_root


def test_emit_kpis_writes_measurements_json(tmp_path, monkeypatch):
    """--emit-kpis writes benchmark/runs/<model>-<run_id>/measurements.json +
    report.md, with header (+ group_key), processing.scored, and graph.scored.
    Redirected to tmp_path/benchmark/runs so it doesn't touch the real repo.
    """
    vault, state_root = _setup_single_signal_vault(tmp_path, monkeypatch)

    # Redirect benchmark/runs/ to tmp_path so no real repo files are written.
    bench_runs = tmp_path / "benchmark" / "runs"
    monkeypatch.setattr(_emit_kpis_mod, "get_benchmark_runs_dir", lambda: bench_runs)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="testprovider", model="testmodel",
        max_tokens=4096, emit_kpis=True)

    assert res.ok, res.exit_reason

    # Dir name is model-prefixed (restores the pre-refactor convention).
    out_dir = bench_runs / f"testmodel-{res.run_id}"
    mpath = out_dir / "measurements.json"
    assert mpath.exists(), f"measurements.json not found at {mpath}"

    # Rendered human-readable report lands alongside the machine payload.
    report_path = out_dir / "report.md"
    assert report_path.exists(), f"report.md not found at {report_path}"
    assert report_path.read_text(encoding="utf-8").startswith("# Benchmark run")

    m = json.loads(mpath.read_text(encoding="utf-8"))

    # Top-level keys
    assert "header" in m
    assert "processing" in m
    assert "graph" in m

    # header carries provider + model explicitly (group_key removed 2026-06-06;
    # the leaderboard keys on model).
    hdr = m["header"]
    assert hdr["provider"] == "testprovider"
    assert hdr["model"] == "testmodel"
    assert "group_key" not in hdr
    # header.run_id stays the bare timestamp (the link back to state/runs/<id>/).
    assert hdr["run_id"] == res.run_id

    # processing must have scored sub-key
    assert "scored" in m["processing"]

    # graph scored is now entity_reuse (dangling_link_rate deleted 2026-06-06).
    assert "scored" in m["graph"]
    assert "entity_reuse" in m["graph"]["scored"]
    assert "dangling_link_rate" not in m["graph"]["scored"]

    # run_state/ is a self-contained copy of state/runs/<run_id>/.
    run_state_dir = out_dir / "run_state"
    assert run_state_dir.is_dir(), f"run_state/ not found at {run_state_dir}"
    assert (run_state_dir / "measurement_header.json").exists()
    assert (run_state_dir / "pass1").is_dir()
    assert (run_state_dir / "pass2").is_dir()

    # compile_result.json and wiki/ are copied for full self-contained record.
    assert (out_dir / "compile_result.json").exists()
    assert (out_dir / "wiki").is_dir()

    # system_prompt.md — the packaged Pass-2 prompt snapshotted for the
    # record (post-#115; Task #30 re-runnability).
    prompt_snap = out_dir / "system_prompt.md"
    assert prompt_snap.exists(), f"system_prompt.md not found at {prompt_snap}"
    from compiler.prompt_builder import load_system_prompt
    assert prompt_snap.read_text(encoding="utf-8") == load_system_prompt()


def test_emit_kpis_absent_does_not_write_measurements_json(tmp_path, monkeypatch):
    """Without --emit-kpis, no measurements.json is written anywhere."""
    vault, state_root = _setup_single_signal_vault(tmp_path, monkeypatch)

    # Redirect so if anything is accidentally written we can detect it.
    bench_runs = tmp_path / "benchmark" / "runs"
    monkeypatch.setattr(_emit_kpis_mod, "get_benchmark_runs_dir", lambda: bench_runs)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m",
        max_tokens=4096, emit_kpis=False)

    assert res.ok, res.exit_reason

    assert not any(bench_runs.rglob("measurements.json")), (
        "measurements.json must NOT be written without --emit-kpis"
    )


# ---------- Task #111 Phase 0 Task 2: console.log saved alongside measurements ----------

def test_emit_kpis_writes_console_log(tmp_path, monkeypatch):
    """A non-quiet --emit-kpis run saves the progress narrative as console.log
    in the benchmark run dir (alongside measurements.json)."""
    vault, state_root = _setup_single_signal_vault(tmp_path, monkeypatch)
    bench_runs = tmp_path / "benchmark" / "runs"
    monkeypatch.setattr(_emit_kpis_mod, "get_benchmark_runs_dir", lambda: bench_runs)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="testprovider", model="testmodel",
        max_tokens=4096, emit_kpis=True, quiet=False)

    assert res.ok, res.exit_reason
    out_dir = bench_runs / f"testmodel-{res.run_id}"
    log_path = out_dir / "console.log"
    assert log_path.exists(), f"console.log not found at {log_path}"
    text = log_path.read_text(encoding="utf-8")
    assert text, "console.log must be non-empty"
    assert "▸" in text, "console.log must contain the rendered progress narrative"


def test_emit_kpis_quiet_skips_console_log(tmp_path, monkeypatch):
    """A quiet --emit-kpis run writes measurements.json but NO console.log
    (no progress narrative was captured)."""
    vault, state_root = _setup_single_signal_vault(tmp_path, monkeypatch)
    bench_runs = tmp_path / "benchmark" / "runs"
    monkeypatch.setattr(_emit_kpis_mod, "get_benchmark_runs_dir", lambda: bench_runs)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="testprovider", model="testmodel",
        max_tokens=4096, emit_kpis=True, quiet=True)

    assert res.ok, res.exit_reason
    out_dir = bench_runs / f"testmodel-{res.run_id}"
    assert (out_dir / "measurements.json").exists(), "measurements.json must still be written"
    assert not (out_dir / "console.log").exists(), "console.log must NOT be written in quiet mode"


def test_emit_kpis_no_compiled_sources_skips_gracefully(tmp_path, monkeypatch):
    """When all sources are quarantined (finalize skipped), emit-kpis does not crash."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        lambda req: (_ for _ in ()).throw(RuntimeError("model down")))

    bench_runs = tmp_path / "benchmark" / "runs"
    monkeypatch.setattr(_emit_kpis_mod, "get_benchmark_runs_dir", lambda: bench_runs)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m",
        max_tokens=4096, emit_kpis=True)

    # Run still OK (quarantined) — emit-kpis gracefully skipped, no file
    assert res.ok, res.exit_reason
    assert res.finalize is None   # finalize was skipped
    assert not any(bench_runs.rglob("measurements.json"))


def test_cli_emit_kpis_flag_parsed(tmp_path):
    """--emit-kpis is parsed as True by the CLI argument parser."""
    args = kdb_orchestrate._build_parser().parse_args([
        "--vault-root", str(tmp_path), "--emit-kpis",
    ])
    assert args.emit_kpis is True


def test_cli_emit_kpis_default_false(tmp_path):
    """--emit-kpis defaults to False (opt-in, normal runs unaffected)."""
    args = kdb_orchestrate._build_parser().parse_args([
        "--vault-root", str(tmp_path),
    ])
    assert args.emit_kpis is False
