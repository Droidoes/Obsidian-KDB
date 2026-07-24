"""#119: bridge output → canonicalize with a REAL alias ledger — provenance intact."""
import json

from compiler import canonicalize
from compiler.canonicalize import AliasEntry, AliasLedger
from compiler.proposal_bridge import BridgeSuccess, normalize_proposal


def _ledger(*pairs: tuple[str, str]) -> AliasLedger:
    """In-memory ledger — same pattern as compiler/tests/test_canonicalize_algorithm.py:41."""
    return AliasLedger(
        entries=tuple(AliasEntry(surface=s, canonical=c) for s, c in pairs),
        snapshot_sha256="test-sha-" + str(len(pairs)),
    )


def test_alias_token_resolves_in_canonicalize_with_provenance():
    proposal = {"pages": [
        {"page_type": "summary", "title": "T", "body": "Alias [[apple-inc]] noted."},
        {"page_type": "concept", "slug": "real-page", "title": "RP", "body": "RP."},
    ]}
    bridge = normalize_proposal(proposal, source_id="KDB/raw/x.md")
    assert isinstance(bridge, BridgeSuccess)
    assert "[[apple-inc]]" in bridge.canonical["pages"][0]["body"]  # preserved by bridge

    cr = {"run_id": "test-run", "success": True,
          "compiled_sources": [{"source_id": "KDB/raw/x.md",
                                "pages": bridge.canonical["pages"]}],
          "compilation_notes": [], "errors": []}
    canonicalize.run(cr, _ledger(("apple-inc", "apple-canonical")), "test-run")
    body = cr["compiled_sources"][0]["pages"][0]["body"]
    assert "[[apple-canonical]]" in body
    assert "apple-inc" in str(cr["canonical_meta"]["aliases_emitted"])
    summaries = [p for p in cr["compiled_sources"][0]["pages"]
                 if p["page_type"] == "summary"]
    assert len(summaries) == 1 and summaries[0]["slug"] == "summary-x"


# --- compile_source end-to-end through the boundary (Codex PR3 F4) ---
# Local helpers per this file's local-helper convention — no cross-file
# imports, no kdb_graph.testing dependency.


class _Resp:
    def __init__(self, text):
        self.text = text
        self.provider = "test"
        self.model = "test-model"
        self.input_tokens = 1
        self.output_tokens = 1
        self.latency_ms = 1
        self.stop_reason = "stop"
        self.attempts = 1


def _ctx(tmp_path):
    from common.run_context import RunContext
    return RunContext.new(dry_run=True, vault_root=tmp_path)


def test_compile_source_end_to_end_through_boundary(tmp_path, monkeypatch):
    """compile_source: mocked model response flows recover → proposal → bridge
    → canonicalize → post-canon invariant. Deviant summary + coercible concept
    both normalize; ZERO writes escape the produce-don't-write seam."""
    payload = json.dumps({"pages": [
        {"page_type": "summary", "slug": "summary-x-deviant", "title": "T",
         "body": "See [[foo--bar]]."},
        {"page_type": "concept", "slug": "foo--bar", "title": "FB", "body": "FB."},
    ]})
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        lambda req: _Resp(payload))
    from common.types import ContextSnapshot
    from compiler.canonicalize import AliasLedger
    from compiler.compiler import compile_source
    state_root = tmp_path / "KDB" / "state"
    state_root.mkdir(parents=True)
    res = compile_source(
        "KDB/raw/x.md", "body text", None,
        None,                                     # conn=None — a prebuilt snapshot
        vault_root=tmp_path, state_root=state_root, ctx=_ctx(tmp_path),
        ledger=AliasLedger(),                     # empty ledger
        provider="test", model="test-model", max_tokens=1000,
        context_snapshot=ContextSnapshot(source_id="KDB/raw/x.md", pages=[]))
    assert res.cr is not None and res.failure_stage is None
    pages = res.cr["compiled_sources"][0]["pages"]
    by_type = {p["page_type"]: p for p in pages}
    assert by_type["summary"]["slug"] == "summary-x"
    assert by_type["concept"]["slug"] == "foo-bar"
    assert "[[foo-bar]]" in by_type["summary"]["body"]
    # produce-don't-write seam: no wiki pages, no compile_result.json, no
    # manifest — the ONLY legitimate write is per-source resp-stats telemetry
    # under state_root/runs/<run_id>/pass2/ (expected, allowed — Codex PR5 F5)
    assert not (tmp_path / "KDB" / "wiki").exists()
    assert not (state_root / "compile_result.json").exists()
    assert not (state_root / "manifest.json").exists()
    assert list((state_root / "runs").glob("*/pass2/*.json"))  # telemetry only
