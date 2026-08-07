"""Task #91 Plan 5+6 — kdb_orchestrate conductor tests.

All non-live: the Pass-2 model is faked via monkeypatch (test_compile_source
pattern). Run: python -m pytest orchestrator/tests/test_kdb_orchestrate.py -m "not live"
"""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from compiler import compiler, prompt_builder
from orchestrator import kdb_orchestrate
import orchestrator.emit_kpis as _emit_kpis_mod
from common.call_model import ModelResponse
from common.model_route import ModelRoute
from compiler.canonicalize import load_or_empty
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
    # proving _commit_source's per-source wiring lands it in-txn (#136).
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


def _selector_spec():
    """#123 P3a.2b: compile_source requires a run-level selector seat (empty
    graph ⇒ the core abstains; the seam never fires)."""
    from common.model_pool import ModelSpec
    return ModelSpec(
        id="test-selector", provider="deepseek", model="test",
        route=ModelRoute("openai_compat", "https://example.invalid", "DEEPSEEK_API_KEY"),
        ctx_window=400_000, max_output_tokens=65_536, tokens_lte_bytes=True)


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
            provider="p", model="m", max_tokens=4096,
            selector=_selector_spec())
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
    # graph (#136): SUPPORTS + LINKS_TO both wired in the commit txn
    assert n_supports == 2
    assert n_links == 1
    assert result.links_wired == 1
    assert result.links_pended == 0 and result.links_drained == 0
    # manifest committed with the POST-embed hash (not the scan's pre-embed hash)
    manifest = json.loads((state_root / "manifest.json").read_text(encoding="utf-8"))
    rec = manifest["sources"][source_id]
    assert rec["last_compiled_hash"] == post_embed_hash
    assert rec["hash"] == post_embed_hash
    assert rec["pipeline_id"] == "vault-test"
    # cr accumulated for the finalize archive
    assert result.cr is produced.cr


# ---------- Task 4+5: finalize (convergence fixpoint + archive + summary) ----------

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


def test_finalize_has_no_wiring_role(tmp_path):
    """#136: wiring is per-commit — the cross-source edge exists BEFORE
    finalize (pended at crA, drained at crB's commit). Finalize only archives
    compile_result.json and carries the loop's accumulated totals through."""
    state_root = tmp_path / "state"
    state_root.mkdir()
    ctx = RunContext.new(vault_root=tmp_path)
    crA = _cr("a.md", [_page("ent-a", outgoing=["ent-b"])])
    crB = _cr("b.md", [_page("ent-b")])
    edge_q = ("MATCH (:Entity {slug: 'ent-a'})-[r:LINKS_TO]->(:Entity {slug: 'ent-b'}) "
              "RETURN COUNT(r)")
    with GraphDB(tmp_path / "graph") as g:
        resA = g.apply_compile_result(crA, _scan_files("a.md"), ctx.run_id)
        assert _count(g, edge_q) == 0            # pended (ent-b absent)
        assert resA.links_pended == 1
        resB = g.apply_compile_result(crB, _scan_files("b.md"), ctx.run_id)
        before = _count(g, edge_q)
        wiring = {
            "links_wired": (resA.edges_upserted + resA.links_drained)
                           + (resB.edges_upserted + resB.links_drained),
            "links_pended": resA.links_pended + resB.links_pended,
            "links_drained": resA.links_drained + resB.links_drained,
            "deprecated": 0,
        }
        stats = kdb_orchestrate._finalize(
            g.conn, [crA, crB], state_root=state_root, ctx=ctx, wiring=wiring)
        after = _count(g, edge_q)
    assert before == 1 and after == 1        # wired at crB's commit, not finalize
    assert resB.links_drained == 1
    assert stats["links_wired"] == wiring["links_wired"]   # totals carried through
    assert stats["links_pended"] == 1 and stats["links_drained"] == 1
    assert stats["links_pended_open"] == 0   # ledger drained
    assert stats["deprecated"] == 0          # both entities supported
    cr_json = json.loads((state_root / "compile_result.json").read_text(encoding="utf-8"))
    assert len(cr_json["compiled_sources"]) == 2


def _forward_response(source_id: str) -> dict:
    # Summary links [[x-late]] — a page NO source has minted yet (#136 pend).
    from compiler.summary_slug import expected_summary_slug
    return {
        "pages": [
            {"slug": expected_summary_slug(source_id), "page_type": "summary",
             "title": "Foo", "body": "See [[x-late]]."},
        ],
    }


def _late_response(source_id: str) -> dict:
    # Mints x-late (plus the source's summary) — drains the earlier pend.
    from compiler.summary_slug import expected_summary_slug
    return {
        "pages": [
            {"slug": expected_summary_slug(source_id), "page_type": "summary",
             "title": "S", "body": "Sum."},
            {"slug": "x-late", "page_type": "concept", "title": "X",
             "body": "Late."},
        ],
    }


def test_commit_accumulates_wiring_counts(tmp_path, monkeypatch):
    """#136: _commit_source exposes its in-txn wiring effects (pend/drain) so
    the loop's run-total accumulation can roll them up."""
    from compiler.summary_slug import expected_summary_slug
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    h = "sha256:" + "b" * 64

    def _compile(source_id, response):
        monkeypatch.setattr(
            "compiler.compiler.call_model_with_retry",
            _fake_model(response))
        produced = compiler.compile_source(
            source_id=source_id, body="A note.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_selector_spec())
        assert produced.ok, (produced.failure_stage, produced.error)
        return produced

    with GraphDB(tmp_path / "graph") as g:
        # Source A: summary links x-late, which no source has minted → pends.
        produced_a = _compile("AIML/a.md", _forward_response("AIML/a.md"))
        commit_a = kdb_orchestrate._commit_source(
            cr=produced_a.cr, source_id="AIML/a.md",
            post_embed_hash=h, post_embed_mtime=2.0,
            scan_entry=_scan_entry("AIML/a.md"),
            prior_manifest={}, vault_root=vault, state_root=state_root,
            conn=g.conn, ctx=ctx)
        assert commit_a.ok
        assert commit_a.links_pended == 1
        assert commit_a.links_wired == 0 and commit_a.links_drained == 0
        assert _count(g, "MATCH (p:PendingLink) RETURN COUNT(p)") == 1

        # Source B: mints x-late → drains A's pend inside B's commit txn.
        produced_b = _compile("AIML/b.md", _late_response("AIML/b.md"))
        commit_b = kdb_orchestrate._commit_source(
            cr=produced_b.cr, source_id="AIML/b.md",
            post_embed_hash=h, post_embed_mtime=2.0,
            scan_entry=_scan_entry("AIML/b.md"),
            prior_manifest=commit_a.next_manifest, vault_root=vault,
            state_root=state_root, conn=g.conn, ctx=ctx)
        assert commit_b.ok
        assert commit_b.links_drained == 1
        assert commit_b.links_wired == 1      # drained edge counted in wired
        slug_a = expected_summary_slug("AIML/a.md")
        edge_q = (f"MATCH (:Entity {{slug: '{slug_a}'}})-[r:LINKS_TO]->"
                  "(:Entity {slug: 'x-late'}) RETURN COUNT(r)")
        assert _count(g, edge_q) == 1
        assert _count(g, "MATCH (p:PendingLink) RETURN COUNT(p)") == 0

    # The loop's run-total arithmetic over the two commits.
    totals = {
        "links_wired": commit_a.links_wired + commit_b.links_wired,
        "links_pended": commit_a.links_pended + commit_b.links_pended,
        "links_drained": commit_a.links_drained + commit_b.links_drained,
    }
    assert totals == {"links_wired": 1, "links_pended": 1, "links_drained": 1}


def test_abort_mid_run_resume_drains(tmp_path):
    """#136 abort story (integration): a run dying between commits loses
    nothing — committed sources' pendings are durable across a close/reopen,
    and the next run's commits keep draining. Final edge set == an
    uninterrupted control. #94's strand is deleted by construction."""
    from kdb_graph.testing import (
        make_compile_result, make_compiled_source, make_page,
        make_scan, make_scan_entry,
    )
    crA = make_compile_result([
        make_compiled_source("a.md", [make_page("a", outgoing_links=["x"])])])
    crB = make_compile_result([
        make_compiled_source("b.md", [make_page("x")])])
    scanA = make_scan([make_scan_entry("a.md")])
    scanB = make_scan([make_scan_entry("b.md")])

    def edge_set(path):
        with GraphDB(path) as g:
            rows = g.conn.execute(
                "MATCH (a:Entity)-[r:LINKS_TO]->(b:Entity) RETURN a.slug, b.slug")
            edges = set()
            while rows.has_next():
                edges.add(tuple(rows.get_next()))
            pend = g.conn.execute("MATCH (p:PendingLink) RETURN COUNT(p)")
            return edges, int(pend.get_next()[0])

    aborted = tmp_path / "aborted"
    with GraphDB(aborted) as g:              # "run 1" — dies after A's commit
        g.apply_compile_result(crA, scanA, "r1")
    with GraphDB(aborted) as g:              # "run 2" — resume: B's commit drains
        g.apply_compile_result(crB, scanB, "r2")

    control = tmp_path / "control"           # uninterrupted
    with GraphDB(control) as g:
        g.apply_compile_result(crA, scanA, "r1")
        g.apply_compile_result(crB, scanB, "r2")

    assert edge_set(aborted) == edge_set(control) == ({("a", "x")}, 0)


def test_finalize_deprecates_dropped_pages_in_graph_and_on_disk(tmp_path):
    """#130+#136: a page dropped by its source's recompile is DEPRECATED in the
    commit txn — graph node flipped per-source; the file frontmatter flip is
    the finalize convergence fixpoint's job (no retraction.json, no cleanup
    journal — the old reap is gone)."""
    state_root = tmp_path / "state"
    state_root.mkdir()
    ctx = RunContext.new(vault_root=tmp_path)
    scan = _scan_files("a.md")
    cr1 = _cr("a.md", [_page("ent-a"), _page("ent-b")])
    cr2 = _cr("a.md", [_page("ent-a")])
    f = tmp_path / "KDB/wiki/concepts/ent-b.md"
    f.parent.mkdir(parents=True)
    f.write_text(
        "---\ntitle: B\nslug: ent-b\npage_type: concept\nstatus: active\n---\nbody\n",
        encoding="utf-8")
    with GraphDB(tmp_path / "graph") as g:
        g.apply_compile_result(cr1, scan, ctx.run_id)
        res2 = g.apply_compile_result(cr2, scan, ctx.run_id)
        ent_b_pre_finalize = g.get_entity("ent-b")
        # Commit-txn flip already landed; the file awaits the fixpoint.
        assert ent_b_pre_finalize.status == "deprecated"
        assert "status: active" in f.read_text(encoding="utf-8")
        wiring = {
            "links_wired": res2.edges_upserted + res2.links_drained,
            "links_pended": res2.links_pended,
            "links_drained": res2.links_drained,
            "deprecated": len(res2.deprecations_detected),
        }
        stats = kdb_orchestrate._finalize(
            g.conn, [cr2], state_root=state_root, ctx=ctx, wiring=wiring)
        ent_b = g.get_entity("ent-b")
    assert res2.deprecations_detected == [{"slug": "ent-b", "page_type": "concept"}]
    assert ent_b is not None and ent_b.status == "deprecated"   # node kept, flipped
    assert stats["deprecated"] == 1
    assert stats["deprecated_files"] == 1
    assert "status: deprecated" in f.read_text(encoding="utf-8")
    # _finalize itself writes no run-level artifacts: retraction journals are
    # gone post-#130, and the #132 replay journal/sidecars are archived by
    # run()'s finally block, not here (see the #132 run()-level pins below).
    assert not (state_root / "runs" / ctx.run_id / "retraction.json").exists()
    assert not (state_root / "runs" / f"{ctx.run_id}.json").exists()


def test_commit_reconcile_deleted_erases_pages_and_files(tmp_path):
    """#130 R-130-4: source deletion is total erasure — node DETACH DELETEd in
    the graph layer, file unlinked by the conductor, tombstone written."""
    from types import SimpleNamespace
    state_root = tmp_path / "state"
    state_root.mkdir()
    ctx = RunContext.new(vault_root=tmp_path)
    scan = _scan_files("gone.md")
    cr = _cr("gone.md", [_page("ent-z")])
    f = tmp_path / "KDB/wiki/concepts/ent-z.md"
    f.parent.mkdir(parents=True)
    f.write_text("---\nstatus: active\n---\nbody\n", encoding="utf-8")
    op = SimpleNamespace(
        type="DELETED", path="gone.md",
        to_dict=lambda: {"type": "DELETED", "source_id": "gone.md",
                         "path": "gone.md"})
    with GraphDB(tmp_path / "graph") as g:
        g.apply_compile_result(cr, scan, ctx.run_id)
        assert g.get_entity("ent-z") is not None
        next_manifest = kdb_orchestrate._commit_reconcile_op(
            op, moved_entry=None, prior_manifest={}, conn=g.conn,
            state_root=state_root, ctx=ctx)
        assert g.get_entity("ent-z") is None                    # node erased
    assert not f.exists()                                       # file erased
    assert next_manifest["tombstones"]["gone.md"]["status"] == "deleted"


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


def _capture_pass_leaves(monkeypatch, captured: dict) -> None:
    """#121 P2 §6: capture the LEAF ModelRequest of BOTH passes — Pass-1 inside
    call_pass1 (real call_pass1 runs; only the engine call is faked) and
    Pass-2 inside compile_one — without altering behavior."""
    def pass1_leaf(req):
        captured["pass1_req"] = req
        return ModelResponse(
            text=json.dumps({
                "kdb_signal": "signal", "domain": "value-investing",
                "source_type": "paper", "author": None, "summary": "A note.",
                "key_themes": ["a"], "entity_search_keys": ["a"],
                "confidence": 0.9, "uncertainty_reason": None,
                "reject_reason": None, "other_reason": None,
            }),
            input_tokens=1, output_tokens=1, latency_ms=1,
            model="m", provider="p", attempts=1)

    def pass2_leaf(req):
        captured["pass2_req"] = req
        return _fake_model(_compiled_response("a.md", "summary-a"))(req)

    monkeypatch.setattr("ingestion.enrich.pass1_caller.call_model", pass1_leaf)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", pass2_leaf)


def test_run_threads_route_to_both_pass_leaves(tmp_path, monkeypatch):
    """#121 P2 §6 both-pass leaf forwarding pin: the SAME ModelRoute object
    reaches the leaf ModelRequest in Pass-1 (run → enrich_one → call_pass1 →
    ModelRequest) and Pass-2 (run → compile_source → compile_one →
    ModelRequest)."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nValue investing note.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    captured: dict = {}
    _capture_pass_leaves(monkeypatch, captured)

    route = ModelRoute("openai_compat", "https://api.deepseek.com", "DEEPSEEK_API_KEY")
    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="deepseek", model="deepseek-v4-flash",
        max_tokens=4096, route=route)

    assert res.ok, res.exit_reason
    assert captured["pass1_req"].route is route
    assert captured["pass2_req"].route is route


def test_main_escape_hatch_route_none_reaches_both_leaves(tmp_path, monkeypatch):
    """#121 P2 §6 escape-hatch pin: unknown id + --provider → route=None
    reaches BOTH pass leaves → the Class-B registry path."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nValue investing note.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    captured: dict = {}
    _capture_pass_leaves(monkeypatch, captured)

    exit_code = kdb_orchestrate.main([
        "--vault-root", str(vault), "--pipeline", "vt",
        "--provider", "acme", "--model", "raw-acme-1",
    ])

    assert exit_code == 0
    assert captured["pass1_req"].route is None
    assert captured["pass2_req"].route is None


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


def test_main_known_id_threads_spec_route_to_run(tmp_path, monkeypatch):
    """#121 P2 §6 positive CLI pin: a known pool id's pre-validated ModelRoute
    (spec.route) reaches run()."""
    from common.model_pool import resolve_models_json
    captured: dict = {}

    def _sentinel(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("reached_run")
    monkeypatch.setattr(kdb_orchestrate, "run", _sentinel)
    with pytest.raises(RuntimeError, match="reached_run"):
        kdb_orchestrate.main([
            "--vault-root", str(tmp_path), "--pipeline", "p",
            "--model", "deepseek-v4-flash",
        ])
    assert captured["route"] == ModelRoute(
        "openai_compat", "https://api.deepseek.com", "DEEPSEEK_API_KEY")
    assert captured["route"] == resolve_models_json("deepseek-v4-flash").route


def test_main_escape_hatch_threads_none_route_to_run(tmp_path, monkeypatch):
    """#121 P2 §6: the escape hatch passes route=None into run (Class-B
    registry path — no pool metadata for a raw model string)."""
    captured: dict = {}

    def _sentinel(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("reached_run")
    monkeypatch.setattr(kdb_orchestrate, "run", _sentinel)
    with pytest.raises(RuntimeError, match="reached_run"):
        kdb_orchestrate.main([
            "--vault-root", str(tmp_path), "--pipeline", "p",
            "--provider", "alibaba", "--model", "qwen-flash-us",
        ])
    assert captured["route"] is None


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
    # #119 Phase 3 (Codex PR2 F6): pin the proposal-contract stamp —
    # version AND the loaded-prompt SHA, verified through a real dry run
    assert hdr["pass2_prompt_version"] == prompt_builder.PASS2_PROMPT_VERSION == "4.1.0"
    # post-#115 stamp: SHA-256 of the loaded (packaged) Pass-2 system prompt
    assert hdr["pass2_system_prompt_sha256"] == hashlib.sha256(
        prompt_builder.load_system_prompt().encode("utf-8")
    ).hexdigest()
    # #123 P3a.4 (§4.7): the one signal source ran pass-1.5 (empty-graph
    # abstain) and its envelope write succeeded; the noise source never
    # reached compile_source.
    assert hdr["searches_attempted"] == 1
    assert hdr["searches_written"] == 1


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


def test_emit_kpis_no_finalize_emits_audit_artifact(tmp_path, monkeypatch):
    """§7: Pass-1 produced a signal source but all Pass-2 calls failed (no
    finalize) — an auditable measurements.json is STILL written, recording
    finalize_ran: false, graph scored fields None, Task-122 fields retained
    (context records exist — the context build succeeded per source)."""
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

    # Run still OK (quarantined) — finalize was skipped, but the audit
    # artifact IS emitted (expected signal IDs exist).
    assert res.ok, res.exit_reason
    assert res.finalize is None
    matches = list(bench_runs.rglob("measurements.json"))
    assert len(matches) == 1, "§7: audit measurements.json must be written"
    m = json.loads(matches[0].read_text(encoding="utf-8"))
    assert m["header"]["finalize_ran"] is False
    assert m["graph"]["scored"]["entity_reuse"] is None
    assert m["graph"]["watched"]["deprecation_rate"] is None
    assert m["graph"]["watched"]["entity_search_key_resolution"] is None
    # Task-122 event-time fields: the context build succeeded per source
    # (empty graph → complete records).
    assert m["graph"]["watched"]["context_build_success_rate"] == 1.0
    assert m["graph"]["watched"]["context_record_coverage"] == 1.0


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


# ---------- #123 P3a.4: header search counters (§4.7) ----------

def test_run_header_search_counters_envelope_write_failure(tmp_path, monkeypatch):
    """§4.7 reconciliation: an envelope write failure (warn-only, B9) splits
    the counters — searches_attempted=1, searches_written=0 — and the run
    still completes ok."""
    vault, state_root = _setup_single_signal_vault(tmp_path, monkeypatch)

    def disk_full(*_args, **_kwargs):
        raise OSError("disk full")
    monkeypatch.setattr("compiler.search_adapter.atomic_write_json", disk_full)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)

    assert res.ok, res.exit_reason
    hdr = json.loads(
        (state_root / "runs" / res.run_id / "measurement_header.json")
        .read_text(encoding="utf-8"))
    assert hdr["searches_attempted"] == 1
    assert hdr["searches_written"] == 0


# ============================================================================
# #132: replay journal + sidecar archival (D39 for the orchestrator era)
# ============================================================================

def _journal_paths(state_root: Path, run_id: str) -> tuple[Path, Path]:
    return (state_root / "runs" / f"{run_id}.json",
            state_root / "runs" / run_id)


def _rows(conn, query: str) -> list:
    r = conn.execute(query)
    out = []
    while r.has_next():
        out.append(list(r.get_next()))
    return out


def test_run_archives_replay_journal_and_sidecars(tmp_path, monkeypatch):
    """#132 happy path: one signal source + one noise source ⇒ journal with
    2.3 eligibility fields, archived compile_result byte-equal to the flat
    baton, and a last_scan union containing ONLY the committed source's
    post-embed entry (noise never reached intake → never archived)."""
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

    journal_path, sidecar = _journal_paths(state_root, res.run_id)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["schema_version"] == "2.3"
    assert journal["producer"] == "kdb-orchestrate"
    assert journal["run_id"] == res.run_id
    assert journal["started_at"] and journal["finished_at"]
    assert journal["dry_run"] is False
    assert journal["success"] is True
    assert journal["replayable_payload"] is True
    assert journal["finalize_progress"] == "complete"   # #136: slim finalize ran
    assert set(journal["counts"]) == {
        "sources_scanned", "sources_compiled", "sources_noise",
        "sources_failed", "sources_moved", "sources_deleted"}
    assert journal["counts"]["sources_compiled"] == 1
    assert journal["counts"]["sources_noise"] == 1

    archived = json.loads((sidecar / "compile_result.json").read_text(encoding="utf-8"))
    baton = json.loads((state_root / "compile_result.json").read_text(encoding="utf-8"))
    assert archived == baton                       # byte-identical payloads
    assert [cs["source_id"] for cs in archived["compiled_sources"]] == ["AIML/a.md"]

    scan = json.loads((sidecar / "last_scan.json").read_text(encoding="utf-8"))
    assert [f["path"] for f in scan["files"]] == ["AIML/a.md"]
    assert scan["to_compile"] == ["AIML/a.md"]
    assert scan["moved_files"] == [] and scan["to_reconcile"] == []
    # Post-embed override: the archived hash is the file's hash AFTER the
    # Pass-1 frontmatter embed — the same value the manifest recorded.
    manifest = json.loads((state_root / "manifest.json").read_text(encoding="utf-8"))
    assert scan["files"][0]["current_hash"] == manifest["sources"]["AIML/a.md"]["hash"]
    assert not (sidecar / "retraction.json").exists()   # still gone post-#130


def test_run_archives_partial_journal_on_manifest_post_graph_abort(tmp_path, monkeypatch):
    """#132 β residual: graph COMMITTED but manifest write threw ⇒ run aborts
    (success=false), yet the archived payload INCLUDES the graph-committed
    source — replay rebuilds the graph, and the graph has these pages."""
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
                failure_stage="manifest_post_graph", graph_committed=True,
                exception_type="OSError", error="disk full",
                scan_entry_used={"path": "AIML/a.md", "current_hash": "h-post-embed"})
        return original_commit_source(*args, **kwargs)

    monkeypatch.setattr(kdb_orchestrate, "_commit_source", flaky_commit)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)
    assert res.exit_code == 1 and res.exit_reason.startswith("manifest_post_graph")

    journal_path, sidecar = _journal_paths(state_root, res.run_id)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["success"] is False
    assert journal["replayable_payload"] is True      # D50 amendment leg
    assert journal["finalize_progress"] == "none"     # finalize never ran
    archived = json.loads((sidecar / "compile_result.json").read_text(encoding="utf-8"))
    assert [cs["source_id"] for cs in archived["compiled_sources"]] == ["AIML/a.md"]
    scan = json.loads((sidecar / "last_scan.json").read_text(encoding="utf-8"))
    assert scan["files"] == [{"path": "AIML/a.md", "current_hash": "h-post-embed"}]
    assert scan["to_compile"] == ["AIML/a.md"]


def test_run_archives_applied_moved_op_only(tmp_path, monkeypatch):
    """#132 reconcile phase: run 2 renames m.md → m2.md (content unchanged) ⇒
    the journal archives the APPLIED MOVED op + moved entry, with empty
    commits phase and finalize_progress='none' (finalize skipped)."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "m.md").write_text("# M\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        _fake_model(_compiled_response("m.md", "summary-m")))

    res1 = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)
    assert res1.ok, res1.exit_reason
    (vault / "AIML" / "m.md").rename(vault / "AIML" / "m2.md")

    res2 = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)
    assert res2.ok, res2.exit_reason
    assert res2.counts["sources_moved"] == 1

    journal_path, sidecar = _journal_paths(state_root, res2.run_id)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["success"] is True
    assert journal["finalize_progress"] == "none"
    assert journal["counts"]["sources_moved"] == 1
    archived = json.loads((sidecar / "compile_result.json").read_text(encoding="utf-8"))
    assert archived["compiled_sources"] == []
    scan = json.loads((sidecar / "last_scan.json").read_text(encoding="utf-8"))
    assert scan["files"] == [] and scan["to_compile"] == []
    assert [f["path"] for f in scan["moved_files"]] == ["AIML/m2.md"]
    assert len(scan["to_reconcile"]) == 1
    op = scan["to_reconcile"][0]
    assert op["type"] == "MOVED"
    assert "AIML/m.md" in json.dumps(op) and "AIML/m2.md" in json.dumps(op)


def test_run_dry_run_archives_journal_marked_dry_run(tmp_path, monkeypatch):
    """#132: dry runs early-return before the graph opens — no payload exists
    — but still archive a journal (empty sidecars) marked dry_run=true; the
    adapter's eligibility gate skips it on replay."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096,
        dry_run=True)
    assert res.ok and res.exit_reason == "dry-run"

    journal_path, sidecar = _journal_paths(state_root, res.run_id)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["dry_run"] is True
    assert journal["success"] is True
    assert journal["finalize_progress"] == "none"
    archived = json.loads((sidecar / "compile_result.json").read_text(encoding="utf-8"))
    assert archived["compiled_sources"] == []
    scan = json.loads((sidecar / "last_scan.json").read_text(encoding="utf-8"))
    assert scan == {"files": [], "to_compile": [],
                    "moved_files": [], "to_reconcile": []}


def test_journal_archive_failure_sets_replayable_false(tmp_path, monkeypatch):
    """#132 warn-only archival: sidecar writes failing ⇒ journal still written
    with replayable_payload=false (the adapter skips it), run unaffected."""
    from orchestrator import journal_writer

    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        _fake_model(_compiled_response("a.md", "summary-a")))

    real_write = journal_writer.atomic_write_json

    def disk_full(path, payload):
        p = str(path)
        if "/runs/" in p and p.endswith(("compile_result.json", "last_scan.json")):
            raise OSError("disk full")
        return real_write(path, payload)

    monkeypatch.setattr(journal_writer, "atomic_write_json", disk_full)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m", max_tokens=4096)
    assert res.ok, res.exit_reason

    journal_path, _ = _journal_paths(state_root, res.run_id)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["success"] is True
    assert journal["replayable_payload"] is False


def test_run_journals_rebuild_identical_graph_e2e(tmp_path, monkeypatch):
    """#132 E2E (D39 restored): three orchestrator runs — cold (3 sources),
    warm no-op, then an edit (page dropped) + a source deletion — each
    archiving 2.3 journals. `rebuild` from those journals alone must produce
    a graph IDENTICAL to the live one (entities, sources, SUPPORTS, LINKS_TO,
    domains), with zero LLM calls on the replay side."""
    from kdb_graph.adapters.obsidian_runs import ObsidianRunsAdapter
    from kdb_graph.rebuilder import rebuild

    def _page(slug, ptype="concept", body="Body."):
        return {"slug": slug, "page_type": ptype, "title": slug, "body": body}

    def model(req):
        p = req.prompt
        if "a.md" in p:
            if "Version two" in p:
                return _fake_model({"pages": [
                    _page("summary-a", "summary", "Overview a v2."),
                    _page("concept-x2", body="Fresh.")]})(req)
            return _fake_model({"pages": [
                _page("summary-a", "summary", "Overview a."),
                _page("concept-x", body="Links [[concept-y]].")]})(req)
        if "b.md" in p:
            return _fake_model({"pages": [
                _page("summary-b", "summary", "Overview b."),
                _page("concept-y", body="Deep y.")]})(req)
        return _fake_model({"pages": [
            _page("summary-c", "summary", "Overview c.")]})(req)

    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    graph_path = tmp_path / "graph"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nVersion one.\n", encoding="utf-8")
    (vault / "AIML" / "b.md").write_text("# B\n\nNote b.\n", encoding="utf-8")
    (vault / "AIML" / "c.md").write_text("# C\n\nNote c.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", model)
    # Distinct run_ids: RunContext.new mints from now_iso() at second precision
    # — three runs inside one second would collide and overwrite journals.
    from datetime import datetime, timedelta, timezone
    base = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc).astimezone()
    tick = {"n": 0}

    def fake_now_iso():
        tick["n"] += 1
        return (base + timedelta(seconds=tick["n"])).replace(microsecond=0).isoformat()

    monkeypatch.setattr("common.run_context.now_iso", fake_now_iso)
    # The package conftest scripts ONE selector reply; this test compiles 4
    # times (3 cold + 1 warm-edit), so the selector (non-empty graph) fires 3
    # times — script enough honest-empty replies for all of them.
    from kdb_search.tests import fakes
    monkeypatch.setattr(
        "compiler.search_adapter.call_model",
        fakes.FakeSelector(*[
            fakes.ScriptedReply(fakes.retained_empty_document())
            for _ in range(4)]))

    def _run():
        res = kdb_orchestrate.run(
            pipeline_id="vt", vault_root=vault, state_root=state_root,
            graph_path=graph_path, provider="p", model="m", max_tokens=4096)
        assert res.ok, res.exit_reason
        return res

    res1 = _run()                                    # cold: 3 sources
    assert res1.counts["sources_compiled"] == 3
    res2 = _run()                                    # warm no-op
    assert res2.counts["sources_compiled"] == 0
    (vault / "AIML" / "a.md").write_text("# A\n\nVersion two.\n", encoding="utf-8")
    (vault / "AIML" / "c.md").unlink()
    res3 = _run()                                    # edit + deletion
    assert res3.counts["sources_compiled"] == 1
    assert res3.counts["sources_deleted"] == 1

    journals = state_root / "runs"
    assert len(list(journals.glob("*.json"))) == 3   # one journal per run
    result = rebuild(graph_dir=tmp_path / "rebuilt",
                     adapter=ObsidianRunsAdapter(),
                     journals_dir=journals, confirm=False)
    assert result.replayed == 3 and result.failed == 0

    queries = [
        ("MATCH (e:Entity) RETURN e.slug, e.page_type, e.status, "
         "e.canonical_id, e.first_run_id, e.last_run_id ORDER BY e.slug"),
        ("MATCH (s:Source) RETURN s.source_id, s.status, s.hash, "
         "s.ingest_state, s.ingest_count, s.last_run_id, s.moved_to "
         "ORDER BY s.source_id"),
        ("MATCH (s:Source)-[r:SUPPORTS]->(e:Entity) "
         "RETURN s.source_id, e.slug, r.role ORDER BY s.source_id, e.slug"),
        ("MATCH (a:Entity)-[:LINKS_TO]->(b:Entity) "
         "RETURN a.slug, b.slug ORDER BY a.slug, b.slug"),
        ("MATCH (d:Domain) RETURN d.name ORDER BY d.name"),
        ("MATCH (s:Source)-[:BELONGS_TO]->(d:Domain) "
         "RETURN s.source_id, d.name ORDER BY s.source_id, d.name"),
    ]
    with GraphDB(graph_path) as live, GraphDB(tmp_path / "rebuilt") as reb:
        for q in queries:
            assert _rows(reb.conn, q) == _rows(live.conn, q), q
        statuses = {r[0]: r[1] for r in _rows(
            live.conn, "MATCH (e:Entity) RETURN e.slug, e.status")}
        src_status = {r[0]: r[1] for r in _rows(
            live.conn, "MATCH (s:Source) RETURN s.source_id, s.status")}
    # Semantic spots: dropped page deprecated (not erased), deleted source's
    # sole-supported page ERASED, source row marked deleted.
    assert statuses["concept-x"] == "deprecated"
    assert statuses["concept-x2"] == "active"
    assert "summary-c" not in statuses
    assert src_status["AIML/c.md"] == "deleted"


# ---------- #138: --wipe (decoupled from the run; absorbs #137) ----------

def _seed_derived_state(vault: Path, state_root: Path, graph_path: Path) -> None:
    """Seed the four derived-state targets --wipe must erase, the config
    artifact it must preserve, and the journal history it must archive."""
    (vault / "KDB" / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
    (vault / "KDB" / "wiki" / "concepts" / "stale-ghost.md").write_text(
        "---\nstatus: active\n---\nGhost.\n", encoding="utf-8")
    (vault / "KDB" / "wiki" / "articles").mkdir(parents=True, exist_ok=True)
    (vault / "KDB" / "wiki" / "articles" / "stale-two.md").write_text(
        "---\nstatus: active\n---\nGhost 2.\n", encoding="utf-8")
    graph_path.mkdir(parents=True, exist_ok=True)
    (graph_path / "marker").write_text("old graph", encoding="utf-8")
    (state_root / "manifest.json").write_text(
        json.dumps({"sources": {"ghost.md": {"run_state": "compiled"}}}),
        encoding="utf-8")
    (state_root / "canonicalization").mkdir(parents=True, exist_ok=True)
    (state_root / "canonicalization" / "aliases.json").write_text(
        json.dumps({"bogus-alias": "bogus-canonical"}), encoding="utf-8")
    # preserved: config + per-run outputs; archived: the journal history
    _write_pipelines(state_root, vault)
    (state_root / "runs").mkdir(parents=True, exist_ok=True)
    (state_root / "runs" / "2026-01-01T00-00-00_EDT.json").write_text(
        "{}", encoding="utf-8")
    (state_root / "last_orchestrate.json").write_text("{}", encoding="utf-8")


def test_wipe_removes_derived_state_and_archives_journals(tmp_path):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    graph_path = tmp_path / "graph"
    _seed_derived_state(vault, state_root, graph_path)

    stats = kdb_orchestrate._wipe_derived_state(
        vault_root=vault, state_root=state_root, graph_path=graph_path)

    assert stats["wiki_files_removed"] == 2
    assert stats["graph_removed"] is True
    assert stats["manifest_removed"] is True
    assert stats["alias_ledger_removed"] is True
    assert stats["run_dirs_archived"] == 1
    assert stats["dry_run"] is False
    # journals archived out of the replay root, not deleted (#137)
    archive_dir = Path(stats["archive_dir"])
    assert archive_dir.parent == state_root / "pre-wipe-runs"
    assert (archive_dir / "2026-01-01T00-00-00_EDT.json").exists()
    assert list((state_root / "runs").iterdir()) == []
    # erased
    assert not (vault / "KDB" / "wiki").exists()
    assert not graph_path.exists()
    assert not (state_root / "manifest.json").exists()
    assert not (state_root / "canonicalization" / "aliases.json").exists()
    # preserved
    assert (state_root / "pipelines.json").exists()
    assert (state_root / "last_orchestrate.json").exists()
    # the wipe has no run to journal into — the ledger is the audit trail
    lines = (state_root / "wipes.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["archive_dir"] == str(archive_dir)
    assert rec["wiki_files_removed"] == 2
    assert rec["run_dirs_archived"] == 1
    assert rec["ts"]


def test_wipe_removes_single_file_graph(tmp_path):
    """Kuzu's single-file layout: KDB/graph is a FILE, not a directory —
    the wipe must unlink it, not rmtree it (live defect 2026-08-06: the
    first real --cold run crashed NotADirectoryError mid-wipe, after the
    wiki tree was already gone; every test had seeded a directory graph)."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    graph_path = tmp_path / "graph"
    _seed_derived_state(vault, state_root, graph_path)
    shutil.rmtree(graph_path)  # replace the dir seed with a file seed
    graph_path.write_text("old graph", encoding="utf-8")

    stats = kdb_orchestrate._wipe_derived_state(
        vault_root=vault, state_root=state_root, graph_path=graph_path)

    assert stats["graph_removed"] is True
    assert not graph_path.exists()
    assert not (vault / "KDB" / "wiki").exists()
    assert not (state_root / "manifest.json").exists()
    assert not (state_root / "canonicalization" / "aliases.json").exists()


def test_wipe_dry_run_reports_without_touching(tmp_path):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    graph_path = tmp_path / "graph"
    _seed_derived_state(vault, state_root, graph_path)

    stats = kdb_orchestrate._wipe_derived_state(
        vault_root=vault, state_root=state_root, graph_path=graph_path,
        dry_run=True)

    assert stats["dry_run"] is True
    assert stats["wiki_files_removed"] == 2
    assert stats["graph_removed"] is True
    assert stats["manifest_removed"] is True
    assert stats["alias_ledger_removed"] is True
    # the archive plan is reported (internal preview — the confirmation
    # gate's only consumer)...
    assert stats["run_dirs_archived"] == 1
    assert stats["archive_dir"] is not None
    # ...but nothing is touched: no deletions, no archive, no ledger
    assert (vault / "KDB" / "wiki" / "concepts" / "stale-ghost.md").exists()
    assert (graph_path / "marker").exists()
    assert (state_root / "manifest.json").exists()
    assert (state_root / "canonicalization" / "aliases.json").exists()
    assert (state_root / "runs" / "2026-01-01T00-00-00_EDT.json").exists()
    assert not (state_root / "pre-wipe-runs").exists()
    assert not (state_root / "wipes.jsonl").exists()


def test_wipe_idempotent_on_missing(tmp_path):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    stats = kdb_orchestrate._wipe_derived_state(
        vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph")
    assert stats == {"wiki_files_removed": 0, "graph_removed": False,
                     "manifest_removed": False, "alias_ledger_removed": False,
                     "run_dirs_archived": 0, "archive_dir": None,
                     "dry_run": False}
    # even a nothing-to-wipe wipe is ledgered (archive_dir null)
    lines = (state_root / "wipes.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["archive_dir"] is None


def test_wipe_then_run_rebuilds_from_sources(tmp_path, monkeypatch):
    """End-to-end: a stale wiki file with no graph node (the #134-measured
    class) is erased by the decoupled wipe; the plain run then rebuilds from
    sources — the run itself knows nothing about wiping (#138)."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    graph_path = tmp_path / "graph"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nValue investing note.\n",
                                         encoding="utf-8")
    _seed_derived_state(vault, state_root, graph_path)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        _fake_model(_compiled_response("a.md", "summary-a")))

    kdb_orchestrate._wipe_derived_state(
        vault_root=vault, state_root=state_root, graph_path=graph_path)
    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=graph_path, provider="p", model="m", max_tokens=4096)

    assert res.ok, res.exit_reason
    assert res.counts["sources_compiled"] == 1
    assert not (vault / "KDB" / "wiki" / "concepts" / "stale-ghost.md").exists()
    assert not (graph_path / "marker").exists()
    assert list((vault / "KDB" / "wiki").rglob("summary-a.md"))
    # the run's event log carries no wipe event — the wipe is not the run's
    # business anymore; its audit trail is state/wipes.jsonl. (The log file
    # may not exist at all: nothing warning-level fires on a clean run.)
    log = Path(res.event_log_path)
    if log.exists():
        rows = _event_rows(log)
        assert [r for r in rows if r.get("event_type") == "cold_wipe"] == []


def test_run_signature_has_no_cold():
    """D-138-1: the run has no modes — `cold` is gone from run()'s contract."""
    import inspect
    assert "cold" not in inspect.signature(kdb_orchestrate.run).parameters


# ---------- #138: --wipe confirmation gate (unbypassable) ----------

def _main_wipe_vault(tmp_path: Path) -> tuple[Path, Path, Path]:
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    graph_path = tmp_path / "graph"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nValue investing note.\n",
                                         encoding="utf-8")
    _seed_derived_state(vault, state_root, graph_path)
    return vault, state_root, graph_path


def test_main_wipe_prompts_and_decline_aborts(tmp_path, monkeypatch, capsys):
    vault, state_root, graph_path = _main_wipe_vault(tmp_path)
    monkeypatch.setattr("builtins.input", lambda prompt="": "no")

    exit_code = kdb_orchestrate.main([
        "--vault-root", str(vault), "--wipe",
        "--graph-path", str(graph_path), "--state-root", str(state_root),
    ])

    assert exit_code == 1
    out, err = capsys.readouterr()
    assert "PERMANENTLY DELETE" in out
    assert str(vault / "KDB" / "wiki") in out and "2 files" in out
    assert str(graph_path) in out
    assert "pre-wipe-runs" in out               # the archive plan is shown
    assert "declined" in err
    assert (vault / "KDB" / "wiki" / "concepts" / "stale-ghost.md").exists()
    assert (graph_path / "marker").exists()
    assert (state_root / "manifest.json").exists()
    assert (state_root / "runs" / "2026-01-01T00-00-00_EDT.json").exists()
    assert not (state_root / "pre-wipe-runs").exists()
    assert not (state_root / "wipes.jsonl").exists()


def test_main_wipe_yes_proceeds_needs_neither_pipeline_nor_model(
        tmp_path, monkeypatch):
    """D-138-2: --wipe is wipe-and-exit — no pipeline run, no model
    resolution (works with no API keys), no --pipeline required."""
    vault, state_root, graph_path = _main_wipe_vault(tmp_path)
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")

    def _explode(*a, **k):
        raise AssertionError("must not be called under --wipe")
    monkeypatch.setattr(kdb_orchestrate, "resolve_models_json", _explode)
    monkeypatch.setattr(kdb_orchestrate, "run", _explode)

    exit_code = kdb_orchestrate.main([
        "--vault-root", str(vault), "--wipe",
        "--graph-path", str(graph_path), "--state-root", str(state_root),
    ])

    assert exit_code == 0
    assert not (vault / "KDB" / "wiki" / "concepts" / "stale-ghost.md").exists()
    assert not graph_path.exists()
    # journals archived, not deleted; the wipe is ledgered
    archive = list((state_root / "pre-wipe-runs").iterdir())
    assert len(archive) == 1
    assert (archive[0] / "2026-01-01T00-00-00_EDT.json").exists()
    assert list((state_root / "runs").iterdir()) == []
    assert len((state_root / "wipes.jsonl").read_text(
        encoding="utf-8").strip().splitlines()) == 1
    # ...and no run happened: the per-run summary is the stale seeded one
    assert (state_root / "last_orchestrate.json").read_text(
        encoding="utf-8") == "{}"


def test_main_wipe_noninteractive_refuses(tmp_path, monkeypatch, capsys):
    """D-138-3: confirmation is unbypassable — EOF on stdin refuses loudly,
    and the guidance names no bypass (there is none)."""
    vault, state_root, graph_path = _main_wipe_vault(tmp_path)
    def _eof(prompt=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", _eof)

    exit_code = kdb_orchestrate.main([
        "--vault-root", str(vault), "--wipe",
        "--graph-path", str(graph_path), "--state-root", str(state_root),
    ])

    assert exit_code == 1
    _, err = capsys.readouterr()
    assert "--yes" not in err
    assert "interactive" in err
    assert (vault / "KDB" / "wiki" / "concepts" / "stale-ghost.md").exists()
    assert (state_root / "runs" / "2026-01-01T00-00-00_EDT.json").exists()
    assert not (state_root / "wipes.jsonl").exists()


def test_retired_and_redundant_wipe_flags_rejected(tmp_path):
    """D-138-1/3/5: --cold and --yes no longer exist; --wipe --dry-run is a
    redundant second preview surface (the confirmation gate previews)."""
    vault = _vault(tmp_path)
    base = ["--vault-root", str(vault)]
    for bad in (["--wipe", "--dry-run"], ["--cold"], ["--yes"]):
        with pytest.raises(SystemExit):
            kdb_orchestrate.main(base + bad)


def test_wipe_then_rerun_replay_matches_live_137(tmp_path, monkeypatch):
    """#137 regression: pre-wipe journals are archived out of the replay
    root, so rebuild over state/runs/ after a wipe + fresh run matches live
    exactly (pre-#138: 561 missing_in_live from replaying pre-wipe history
    against the post-wipe graph)."""
    from kdb_graph.adapters.obsidian_runs import ObsidianRunsAdapter
    from kdb_graph.rebuilder import rebuild

    def _page(slug, ptype="concept", body="Body."):
        return {"slug": slug, "page_type": ptype, "title": slug, "body": body}

    def model(req):
        p = req.prompt
        if "a.md" in p:
            return _fake_model({"pages": [
                _page("summary-a", "summary", "Overview a."),
                _page("concept-x", body="Links [[concept-y]].")]})(req)
        if "b.md" in p:
            return _fake_model({"pages": [
                _page("summary-b", "summary", "Overview b."),
                _page("concept-y", body="Deep y.")]})(req)
        return _fake_model({"pages": [
            _page("summary-c", "summary", "Overview c.")]})(req)

    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    graph_path = tmp_path / "graph"
    (vault / "AIML").mkdir()
    for name in ("a.md", "b.md", "c.md"):
        (vault / "AIML" / name).write_text(f"# {name}\n\nNote.\n",
                                           encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", model)
    # Distinct timestamps: run ids mint from now_iso() at second precision —
    # two runs inside one second would collide and overwrite journals.
    from datetime import datetime, timedelta, timezone
    base = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc).astimezone()
    tick = {"n": 0}

    def fake_now_iso():
        tick["n"] += 1
        return (base + timedelta(seconds=tick["n"])).replace(microsecond=0).isoformat()

    monkeypatch.setattr("common.run_context.now_iso", fake_now_iso)
    # The selector fires once per compile after the very first (which sees an
    # empty graph): 2 per run × 2 runs = 4 honest-empty replies.
    from kdb_search.tests import fakes
    monkeypatch.setattr(
        "compiler.search_adapter.call_model",
        fakes.FakeSelector(*[
            fakes.ScriptedReply(fakes.retained_empty_document())
            for _ in range(4)]))

    def _run():
        res = kdb_orchestrate.run(
            pipeline_id="vt", vault_root=vault, state_root=state_root,
            graph_path=graph_path, provider="p", model="m", max_tokens=4096)
        assert res.ok, res.exit_reason
        return res

    res_a = _run()                                   # run A: 3 sources
    assert res_a.counts["sources_compiled"] == 3

    stats = kdb_orchestrate._wipe_derived_state(
        vault_root=vault, state_root=state_root, graph_path=graph_path)
    # run A's journal + its run dir left the replay root
    assert stats["run_dirs_archived"] == 2
    assert stats["archive_dir"] is not None

    res_b = _run()                                   # fresh world: all recompile
    assert res_b.counts["sources_compiled"] == 3

    # the replay root now holds ONLY run B's journal — no scoping needed
    journals = list((state_root / "runs").glob("*.json"))
    assert len(journals) == 1
    result = rebuild(graph_dir=tmp_path / "rebuilt",
                     adapter=ObsidianRunsAdapter(),
                     journals_dir=state_root / "runs", confirm=False)
    assert result.replayed == 1 and result.failed == 0

    queries = [
        ("MATCH (e:Entity) RETURN e.slug, e.page_type, e.status, "
         "e.canonical_id, e.first_run_id, e.last_run_id ORDER BY e.slug"),
        ("MATCH (s:Source) RETURN s.source_id, s.status, s.hash, "
         "s.ingest_state, s.ingest_count, s.last_run_id, s.moved_to "
         "ORDER BY s.source_id"),
        ("MATCH (s:Source)-[r:SUPPORTS]->(e:Entity) "
         "RETURN s.source_id, e.slug, r.role ORDER BY s.source_id, e.slug"),
        ("MATCH (a:Entity)-[:LINKS_TO]->(b:Entity) "
         "RETURN a.slug, b.slug ORDER BY a.slug, b.slug"),
        ("MATCH (d:Domain) RETURN d.name ORDER BY d.name"),
        ("MATCH (s:Source)-[:BELONGS_TO]->(d:Domain) "
         "RETURN s.source_id, d.name ORDER BY s.source_id, d.name"),
    ]
    with GraphDB(graph_path) as live, GraphDB(tmp_path / "rebuilt") as reb:
        for q in queries:
            assert _rows(reb.conn, q) == _rows(live.conn, q), q


def test_count_deprecated_wiki_files(tmp_path):
    wiki = tmp_path / "KDB" / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "a.md").write_text(
        "---\nslug: a\nstatus: deprecated\n---\nbody\n", encoding="utf-8")
    (wiki / "concepts" / "b.md").write_text(
        "---\nslug: b\nstatus: active\n---\nbody\n", encoding="utf-8")
    (wiki / "articles").mkdir()
    (wiki / "articles" / "c.md").write_text(
        "---\nslug: c\nstatus: deprecated\n---\nbody\n", encoding="utf-8")
    (wiki / "articles" / "no-fm.md").write_text("plain body\n", encoding="utf-8")

    assert kdb_orchestrate._count_deprecated_wiki_files(tmp_path) == 2
    assert kdb_orchestrate._count_deprecated_wiki_files(
        tmp_path / "empty-vault") == 0


def test_finalize_reports_deprecated_pages_total(tmp_path):
    """#135: the standing deprecated-wiki total lands in the finalize stats —
    the operator-visible #134 tripwire, post-convergence."""
    state_root = tmp_path / "state"
    state_root.mkdir()
    ctx = RunContext.new(vault_root=tmp_path)
    scan = _scan_files("a.md")
    cr1 = _cr("a.md", [_page("ent-a"), _page("ent-b")])
    cr2 = _cr("a.md", [_page("ent-a")])
    f = tmp_path / "KDB/wiki/concepts/ent-b.md"
    f.parent.mkdir(parents=True)
    f.write_text(
        "---\ntitle: B\nslug: ent-b\npage_type: concept\nstatus: active\n---\nbody\n",
        encoding="utf-8")
    with GraphDB(tmp_path / "graph") as g:
        g.apply_compile_result(cr1, scan, ctx.run_id)
        res2 = g.apply_compile_result(cr2, scan, ctx.run_id)
        wiring = {
            "links_wired": res2.edges_upserted + res2.links_drained,
            "links_pended": res2.links_pended,
            "links_drained": res2.links_drained,
            "deprecated": len(res2.deprecations_detected),
        }
        stats = kdb_orchestrate._finalize(
            g.conn, [cr2], state_root=state_root, ctx=ctx, wiring=wiring)
    assert stats["deprecated"] == 1
    assert stats["deprecated_pages_total"] == 1
