"""#123 P3a.1 — the pass-1.5 search adapter, UNWIRED (blueprint §4.1, §5.1, §9).

The graph side is a real temp Kuzu graph (no mocks); the model side is the
shared FakeSelector (`kdb_search/tests/fakes.py`) patched into the adapter's
module-level `call_model` seam; vault and state roots are real tmp dirs, so the
envelope sink and the body_reader binding are exercised end to end.

Reference topology (domain "value-investing", source "KDB/raw/src-1.md"):

- charlie-munger   concept  active   first_run_id "run-1"   -> space, cohort hit
- owner-earnings   article  active   first_run_id ""        -> space, age_unknown hit
- warren-buffett   concept  active   first_run_id "r-old"   -> space, pre_run hit
- already-supported concept active   SUPPORTS'd by src-1    -> T1, excluded pre-selector
- retracted-support concept INACTIVE SUPPORTS'd by src-1    -> raw T1 only, scoped out
- bad-type         page_type "essay" (non-vocabulary)       -> dropped, counted (#128)
- other-domain-entity concept active, domain "ai-ml"        -> out of scope

Eligible space, slug-ascending: charlie-munger, owner-earnings, warren-buffett.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from common.llm_telemetry import safe_source_id
from common.model_pool import ModelRoute, ModelSpec
from common.paths import slug_to_abspath
from common.types import SourceFrontmatter
from kdb_graph import queries
from kdb_graph.graphdb import GraphDB
from kdb_search import artifact
from kdb_search.tests import fakes
from kdb_search.types import InvalidGraphSearchRequest, SpaceEntity

from compiler import search_adapter

SOURCE_ID = "KDB/raw/src-1.md"
DOMAIN = "value-investing"

#: The eligible space, slug-ascending — the tuple canned documents are built
#: from (fakes module docstring: documents are built FROM a space).
SPACE = tuple(
    SpaceEntity(slug=slug, title=slug, page_type=page_type)
    for slug, page_type in (
        ("charlie-munger", "concept"),
        ("owner-earnings", "article"),
        ("warren-buffett", "concept"),
    )
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def graph(tmp_path: Path):
    """Temp GraphDB with the reference topology (module docstring)."""
    with GraphDB(tmp_path / "graph") as g:
        conn = g.conn
        for slug, ptype, status, first_run_id in [
            ("charlie-munger", "concept", "active", "run-1"),
            ("owner-earnings", "article", "active", ""),
            ("warren-buffett", "concept", "active", "r-old"),
            ("already-supported", "concept", "active", "r-t1"),
            ("retracted-support", "concept", "inactive", "r-t1b"),
            ("bad-type", "essay", "active", "r-bad"),
            ("other-domain-entity", "concept", "active", "r-other"),
        ]:
            conn.execute(
                "CREATE (e:Entity {slug: $s, title: $s, page_type: $pt, "
                "status: $st, confidence: 'medium', "
                "created_at: '2026-01-01', updated_at: '2026-01-01', "
                "first_run_id: $fr, last_run_id: 'r1'})",
                {"s": slug, "pt": ptype, "st": status, "fr": first_run_id},
            )
        for name in [DOMAIN, "ai-ml"]:
            conn.execute(
                "CREATE (d:Domain {name: $n, created_at: '2026-01-01', "
                "first_run_id: 'r1'})", {"n": name})
        for slug, domain in [
            ("charlie-munger", DOMAIN),
            ("owner-earnings", DOMAIN),
            ("warren-buffett", DOMAIN),
            ("already-supported", DOMAIN),
            ("retracted-support", DOMAIN),
            ("bad-type", DOMAIN),
            ("other-domain-entity", "ai-ml"),
        ]:
            conn.execute(
                "MATCH (e:Entity {slug: $s}), (d:Domain {name: $d}) "
                "CREATE (e)-[:BELONGS_TO {run_id: 'r1'}]->(d)",
                {"s": slug, "d": domain})
        conn.execute(
            "CREATE (s:Source {source_id: $sid, source_type: 'raw', "
            "canonical_path: $sid, status: 'active', file_type: 'markdown', "
            "hash: 'sha256:aaa', size_bytes: 100, "
            "first_seen_at: '2026-01-01', last_seen_at: '2026-01-01', "
            "last_ingested_at: '2026-01-01', ingest_state: 'compiled', "
            "ingest_count: 1, last_run_id: 'r1', moved_to: ''})",
            {"sid": SOURCE_ID},
        )
        for slug in ["already-supported", "retracted-support"]:
            conn.execute(
                "MATCH (s:Source {source_id: $sid}), (e:Entity {slug: $slug}) "
                "CREATE (s)-[:SUPPORTS {run_id: 'r1'}]->(e)",
                {"sid": SOURCE_ID, "slug": slug},
            )
        yield g


def _write_body(root: Path, slug: str, page_type: str, text: str) -> None:
    path = slug_to_abspath(slug, page_type, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Vault root holding a body page for each space entity."""
    root = tmp_path / "vault"
    for entity in SPACE:
        _write_body(root, entity.slug, entity.page_type, f"Body of {entity.slug}.")
    return root


@pytest.fixture
def state_root(tmp_path: Path) -> Path:
    return tmp_path / "state"


def _spec(**overrides) -> ModelSpec:
    """A route satisfying every §8 B10 selector precondition."""
    base = dict(
        id="test-selector",
        provider="deepseek",
        model="test",
        route=ModelRoute("openai_compat", "https://example.invalid", "DEEPSEEK_API_KEY"),
        ctx_window=400_000,
        max_output_tokens=128_000,
        tokens_lte_bytes=True,
    )
    return ModelSpec(**{**base, **overrides})


def _frontmatter(**overrides) -> SourceFrontmatter:
    base = dict(
        kdb_signal="worth_compiling",
        domain=DOMAIN,
        source_type="raw",
        author="Test Author",
        summary="A lecture on moats and management.",
        key_themes=["moats"],
        entity_search_keys=["moats", "management"],
    )
    return SourceFrontmatter(**{**base, **overrides})


def _completed_script(**usable_kwargs) -> fakes.FakeSelector:
    """Thin retains the whole space; fat selects per `usable_kwargs`."""
    kwargs = {"count": 3, "matched": ("A",), "unresolved": ("B",), **usable_kwargs}
    return fakes.FakeSelector(
        fakes.ScriptedReply(fakes.retained_document(SPACE)),
        fakes.ScriptedReply(fakes.usable_document(SPACE, **kwargs)),
    )


_UNSET = object()


def _invoke(graph, vault, state_root, monkeypatch, script=None, *, frontmatter=_UNSET,
            selector=None, run_id="run-1", source_id=SOURCE_ID, intra_run_order=0):
    """Patch the call seam and run the adapter with test defaults."""
    monkeypatch.setattr(
        search_adapter, "call_model", script if script is not None else _completed_script())
    return search_adapter.run_pass15(
        graph.conn,
        frontmatter=_frontmatter() if frontmatter is _UNSET else frontmatter,
        selector=selector or _spec(),
        vault_root=vault,
        state_root=state_root,
        run_id=run_id,
        source_id=source_id,
        intra_run_order=intra_run_order,
    )


def _envelope_path(state_root: Path, run_id: str = "run-1", source_id: str = SOURCE_ID) -> Path:
    return state_root / "runs" / run_id / "search" / f"{safe_source_id(source_id)}.json"


def _read_raw_envelope(state_root: Path, run_id: str = "run-1", source_id: str = SOURCE_ID) -> dict:
    return json.loads(_envelope_path(state_root, run_id, source_id).read_text("utf-8"))


def _parse_envelope(state_root: Path, run_id: str = "run-1", source_id: str = SOURCE_ID):
    return artifact.parse_search_envelope(_read_raw_envelope(state_root, run_id, source_id))


# ---------------------------------------------------------------------------
# SD-1 query payload
# ---------------------------------------------------------------------------


def test_sd1_query_payload_carries_author_domain_summary(graph, vault, state_root, monkeypatch):
    script = _completed_script()
    _invoke(graph, vault, state_root, monkeypatch, script)
    thin_prompt = script.requests[0].prompt
    assert "author: Test Author" in thin_prompt
    assert f"domain: {DOMAIN}" in thin_prompt
    assert "summary:" in thin_prompt
    assert "A lecture on moats and management." in thin_prompt


# ---------------------------------------------------------------------------
# space materialization
# ---------------------------------------------------------------------------


def test_space_slug_ascending_and_t1_excluded_pre_selector(graph, vault, state_root, monkeypatch):
    script = _completed_script()
    _invoke(graph, vault, state_root, monkeypatch, script)
    thin_prompt = script.requests[0].prompt
    positions = [thin_prompt.find(f"- slug: {e.slug}") for e in SPACE]
    assert all(p != -1 for p in positions)
    assert positions == sorted(positions), "the materializer owes slug-ascending order"
    for excluded in ("already-supported", "retracted-support", "other-domain-entity"):
        assert excluded not in thin_prompt


def test_non_vocabulary_page_type_dropped_and_counted(graph, vault, state_root, monkeypatch, caplog):
    """#128: vocabulary membership is enforced at the materializer boundary."""
    script = _completed_script()
    with caplog.at_level(logging.WARNING, logger="compiler.search_adapter"):
        _invoke(graph, vault, state_root, monkeypatch, script)
    thin_prompt = script.requests[0].prompt
    assert "bad-type" not in thin_prompt
    assert "non-vocabulary page_type" in caplog.text
    assert " 1 " in caplog.text or "1 " in caplog.text  # the count is carried


def test_space_fingerprint_deterministic_and_space_sensitive(graph, vault, state_root, monkeypatch):
    _invoke(graph, vault, state_root, monkeypatch, run_id="run-1")
    _invoke(graph, vault, state_root, monkeypatch, run_id="run-2")
    fp_1 = _parse_envelope(state_root, "run-1").receipt.graph_ref.space_fingerprint
    fp_2 = _parse_envelope(state_root, "run-2").receipt.graph_ref.space_fingerprint
    assert fp_1 == fp_2, "same graph + same source ⇒ same space ⇒ same fingerprint"

    # A source with no SUPPORTS edges searches a larger space (already-supported
    # re-enters) — the fingerprint must move with the space.
    other_source = "KDB/raw/src-2.md"
    space2 = tuple(
        [SpaceEntity(slug="already-supported", title="already-supported", page_type="concept")]
        + list(SPACE)
    )
    script = fakes.FakeSelector(
        fakes.ScriptedReply(fakes.retained_document(space2)),
        fakes.ScriptedReply(fakes.usable_document(space2, count=1, matched=("A",))),
    )
    _invoke(graph, vault, state_root, monkeypatch, script,
            run_id="run-3", source_id=other_source)
    fp_3 = _parse_envelope(state_root, "run-3", other_source).receipt.graph_ref.space_fingerprint
    assert fp_3 != fp_1


def test_t1_slugs_passthrough_scoped_to_active(graph, vault, state_root, monkeypatch):
    """B1: the raw SUPPORTS set carries retracted-support (inactive); the
    pass-through is scoped to active entities — no KeyError downstream."""
    outcome = _invoke(graph, vault, state_root, monkeypatch)
    assert outcome.t1_slugs == frozenset({"already-supported"})


def test_single_shared_t1_read(graph, vault, state_root, monkeypatch):
    """The T1 read is single and shared with the context builder (A1)."""
    calls = 0
    real = queries.source_supported_slugs

    def counting(conn, source_id):
        nonlocal calls
        calls += 1
        return real(conn, source_id)

    monkeypatch.setattr(queries, "source_supported_slugs", counting)
    _invoke(graph, vault, state_root, monkeypatch)
    assert calls == 1


# ---------------------------------------------------------------------------
# abstention / gate paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", [None, ""])
def test_missing_domain_abstains_zero_calls_summary_populated(
        graph, vault, state_root, monkeypatch, domain):
    """§4.1 step 3: the core abstains the reason-stamped empty space; the
    search section is populated, not null (A10); `call` is never invoked."""
    outcome = _invoke(graph, vault, state_root, monkeypatch, fakes.NeverCalled(),
                      frontmatter=_frontmatter(domain=domain))
    assert outcome.search_ran is True
    assert outcome.t2_selection == []
    summary = outcome.search_summary
    assert summary is not None
    assert summary.status == "abstain_empty_space"
    assert "domain_missing" in summary.watched
    assert summary.eligible_space_size == 0
    assert outcome.envelope_written is True
    receipt = _parse_envelope(state_root).receipt
    assert receipt.result.status == "abstain_empty_space"
    assert receipt.stages == ()


def test_empty_domain_cluster_abstains_without_domain_missing_class(
        graph, vault, state_root, monkeypatch):
    """domain set but empty: same terminal, NO watched class — the record's
    `domain` field carries the distinction (search.py:_empty_space_watched)."""
    outcome = _invoke(graph, vault, state_root, monkeypatch, fakes.NeverCalled(),
                      frontmatter=_frontmatter(domain="no-such-domain"))
    summary = outcome.search_summary
    assert summary.status == "abstain_empty_space"
    assert summary.watched == ()
    receipt = _parse_envelope(state_root).receipt
    assert set(receipt.result.unresolved_expressions) == {"moats", "management"}


def test_state_c_runs_with_empty_expressions(graph, vault, state_root, monkeypatch):
    """State C RUNS: zero Pass-1 keys ⇒ expressions [], query_kind state_c,
    and the selector is still invoked (§3.1)."""
    script = fakes.FakeSelector(
        fakes.ScriptedReply(fakes.retained_document(SPACE)),
        fakes.ScriptedReply(fakes.usable_document(SPACE, count=2, matched=())),
    )
    outcome = _invoke(graph, vault, state_root, monkeypatch, script,
                      frontmatter=_frontmatter(entity_search_keys=[]))
    assert script.calls == 2
    assert outcome.search_summary.query_kind == "state_c"
    assert len(outcome.t2_selection) == 2
    receipt = _parse_envelope(state_root).receipt
    assert receipt.query.expressions == ()


def test_pre_pass1_frontmatter_means_no_search(graph, vault, state_root, monkeypatch):
    """§4.1 step 1 gate (R-P3a-3): pre-Pass-1 sources do not search."""
    outcome = _invoke(graph, vault, state_root, monkeypatch, fakes.NeverCalled(),
                      frontmatter=None)
    assert outcome.search_ran is False
    assert outcome.t2_selection is None
    assert outcome.search_summary is None
    assert outcome.envelope_written is False
    assert outcome.t1_slugs is None
    assert not _envelope_path(state_root).exists()


# ---------------------------------------------------------------------------
# warn-only / warn-and-continue post-search steps (B4 scope)
# ---------------------------------------------------------------------------


def test_envelope_write_failure_is_warn_only(graph, vault, state_root, monkeypatch, caplog):
    """§4.1 step 7: an OSError from the atomic write is a counted warning —
    artifact_path null, the source outcome never affected."""
    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(search_adapter, "atomic_write_json", _boom)
    with caplog.at_level(logging.WARNING, logger="compiler.search_adapter"):
        outcome = _invoke(graph, vault, state_root, monkeypatch)
    assert outcome.search_ran is True
    assert outcome.envelope_written is False           # attempted − written > 0 (A17)
    assert outcome.search_summary.artifact_path is None
    assert outcome.t2_selection == [e.slug for e in SPACE]
    assert "envelope write failed" in caplog.text


def test_provenance_read_failure_warn_and_continue(graph, vault, state_root, monkeypatch, caplog):
    """§4.1 step 8 [v0.2]: entity_first_run_ids raising ⇒ warning,
    provenance=None ⇒ every hit lands in age_unknown; compile continues."""
    def _boom(conn, slugs):
        raise RuntimeError("kuzu exploded")

    monkeypatch.setattr(queries, "entity_first_run_ids", _boom)
    with caplog.at_level(logging.WARNING, logger="compiler.search_adapter"):
        outcome = _invoke(graph, vault, state_root, monkeypatch)
    assert outcome.envelope_written is True  # the envelope precedes provenance
    assert outcome.t2_selection == [e.slug for e in SPACE]
    for hit in outcome.search_summary.hits:
        assert hit.first_run_id is None
        assert hit.match_recency == "age_unknown"
    assert "provenance read failed" in caplog.text


# ---------------------------------------------------------------------------
# provenance + recency
# ---------------------------------------------------------------------------


def test_hit_provenance_recency_and_resolver_never_invoked(graph, vault, state_root, monkeypatch):
    """§4.1 step 8: per-hit {slug, first_run_id, match_recency} via the batched
    read — cohort / pre_run / age_unknown. No alias/exact resolver participates
    (codex c-2): the #122 resolver family is rigged to explode."""
    for name in (
        "resolve_to_canonical_slugs",
        "resolve_to_canonical_slugs_batch",
        "resolve_to_canonical_slugs_with_provenance",
        "resolve_to_canonical_slugs_with_provenance_batch",
    ):
        monkeypatch.setattr(
            queries, name,
            lambda *a, **k: (_ for _ in ()).throw(AssertionError(f"{name} invoked")))
    outcome = _invoke(graph, vault, state_root, monkeypatch)
    hits = {h.slug: h for h in outcome.search_summary.hits}
    assert hits["charlie-munger"].first_run_id == "run-1"
    assert hits["charlie-munger"].match_recency == "cohort"
    assert hits["warren-buffett"].first_run_id == "r-old"
    assert hits["warren-buffett"].match_recency == "pre_run"
    assert hits["owner-earnings"].first_run_id is None
    assert hits["owner-earnings"].match_recency == "age_unknown"
    for hit in hits.values():
        assert hit.matched_expressions == ("moats",)


# ---------------------------------------------------------------------------
# request-validity fail-hard (B4: propagates, never a status)
# ---------------------------------------------------------------------------


def test_invalid_request_propagates_zero_calls_no_envelope(graph, vault, state_root, monkeypatch):
    """len(expressions) > MAX_EXPRESSIONS ⇒ InvalidGraphSearchRequest —
    zero rendering beyond the query block, zero calls, zero StageRecords."""
    keys = [f"key-{i}" for i in range(11)]  # MAX_EXPRESSIONS = 10
    with pytest.raises(InvalidGraphSearchRequest) as exc_info:
        _invoke(graph, vault, state_root, monkeypatch, fakes.NeverCalled(),
                frontmatter=_frontmatter(entity_search_keys=keys))
    assert exc_info.value.code == "max_expressions_exceeded"
    assert not _envelope_path(state_root).exists()


# ---------------------------------------------------------------------------
# body_reader binding (§6)
# ---------------------------------------------------------------------------


def test_two_vault_roots_evidence_binding(graph, state_root, monkeypatch, tmp_path):
    """get_body is bound to the CALLER's vault_root — the same search over two
    roots presents each root's body bytes as fat evidence."""
    prompts = []
    for marker in ("ALPHA-BODY-TEXT", "BETA-BODY-TEXT"):
        root = tmp_path / f"vault-{marker}"
        for entity in SPACE:
            _write_body(root, entity.slug, entity.page_type, f"{marker} {entity.slug}")
        script = _completed_script()
        _invoke(graph, root, state_root, monkeypatch, script)
        prompts.append(script.requests[1].prompt)  # the fat request
    assert "ALPHA-BODY-TEXT" in prompts[0] and "BETA-BODY-TEXT" not in prompts[0]
    assert "BETA-BODY-TEXT" in prompts[1] and "ALPHA-BODY-TEXT" not in prompts[1]


# ---------------------------------------------------------------------------
# envelope schema (§5.1 B9): discrimination, retention predicate, strict parser
# ---------------------------------------------------------------------------


def test_completed_persists_compact_receipt_with_sent_bytes(graph, vault, state_root, monkeypatch):
    """COMPACT for completed searches: per-stage sent_bytes, and none of the
    heavy full-receipt fields (rendered messages / raw response / parsed output
    / evidence bodies)."""
    outcome = _invoke(graph, vault, state_root, monkeypatch, intra_run_order=7)
    assert outcome.envelope_written is True

    raw = _read_raw_envelope(state_root)
    assert raw["receipt_kind"] == "compact"
    assert raw["schema_version"] == artifact.SEARCH_ENVELOPE_SCHEMA_VERSION
    assert raw["intra_run_order"] == 7
    assert len(raw["receipt"]["stages"]) == 2
    for stage in raw["receipt"]["stages"]:
        assert isinstance(stage["sent_bytes"], int) and stage["sent_bytes"] > 0
        for dropped in ("rendered_messages", "raw_response_text", "parsed_output", "evidence"):
            assert dropped not in stage

    envelope = _parse_envelope(state_root)
    assert envelope.run_id == "run-1"
    assert envelope.source_id == SOURCE_ID
    assert envelope.intra_run_order == 7
    assert envelope.receipt_kind == "compact"
    receipt = envelope.receipt
    assert isinstance(receipt, artifact.CompactSearchReceipt)
    assert receipt.schema_version == artifact.ARTIFACT_SCHEMA_VERSION
    assert receipt.result.status == "completed"
    assert [e.slug for e in receipt.eligible_space_manifest] == [e.slug for e in SPACE]
    assert receipt.query.expressions == ("moats", "management")
    assert [s.stage for s in receipt.stages] == ["thin_selection", "fat_selection"]
    assert outcome.search_summary.search_snapshot_hash == receipt.search_snapshot_hash


def test_selector_failure_persists_full_receipt(graph, vault, state_root, monkeypatch):
    """FULL for selector_failure: thin exhausted twice (D-123-G: thin fails ⇒
    no fat), the full stage bytes retained."""
    script = fakes.FakeSelector(
        fakes.ScriptedReply(fakes.thin_structurally_unusable_document()),
        fakes.ScriptedReply(fakes.thin_structurally_unusable_document()),
    )
    outcome = _invoke(graph, vault, state_root, monkeypatch, script)
    assert outcome.search_summary.status == "selector_failure"
    assert outcome.search_summary.failure_class is not None
    assert outcome.t2_selection == []  # honest empty T2, compile continues

    raw = _read_raw_envelope(state_root)
    assert raw["receipt_kind"] == "full"
    assert len(raw["receipt"]["stages"]) == 2
    for stage in raw["receipt"]["stages"]:
        assert "rendered_messages" in stage
        assert "raw_response_text" in stage

    receipt = _parse_envelope(state_root).receipt
    assert isinstance(receipt, artifact.SearchAuditPayload)
    assert receipt.result.status == "selector_failure"


def test_precall_budget_exceeded_persists_full_receipt(graph, vault, state_root, monkeypatch):
    """FULL for a pre-call budget_exceeded — zero calls, audit still exists."""
    outcome = _invoke(graph, vault, state_root, monkeypatch, fakes.NeverCalled(),
                      selector=_spec(ctx_window=100))
    assert outcome.search_summary.status == "budget_exceeded"
    raw = _read_raw_envelope(state_root)
    assert raw["receipt_kind"] == "full"
    receipt = _parse_envelope(state_root).receipt
    assert isinstance(receipt, artifact.SearchAuditPayload)
    assert receipt.stages == ()


def test_retention_predicate_is_closed():
    """§5.1's closed retention predicate, pinned as a pure function."""
    assert artifact.receipt_kind_for("completed") == "compact"
    assert artifact.receipt_kind_for("abstain_empty_space") == "compact"
    assert artifact.receipt_kind_for("selector_failure") == "full"
    assert artifact.receipt_kind_for("budget_exceeded") == "full"
    # Thrown exceptions for which an audit exists retain the full receipt.
    assert artifact.receipt_kind_for("completed", raised_with_audit=True) == "full"
    # Warn-and-continue cases never escalate the receipt (envelope-write and
    # provenance warnings are not inputs to the predicate at all).
    assert artifact.receipt_kind_for("completed", raised_with_audit=False) == "compact"


def test_strict_parser_rejects_malformed_envelopes(graph, vault, state_root, monkeypatch):
    _invoke(graph, vault, state_root, monkeypatch)
    raw = _read_raw_envelope(state_root)

    bad_kind = {**raw, "receipt_kind": "thorough"}
    with pytest.raises(artifact.SearchEnvelopeError):
        artifact.parse_search_envelope(bad_kind)

    bad_version = {**raw, "schema_version": 999}
    with pytest.raises(artifact.SearchEnvelopeError):
        artifact.parse_search_envelope(bad_version)

    # A compact stage missing its required sent_bytes rejects.
    missing_bytes = json.loads(json.dumps(raw))
    del missing_bytes["receipt"]["stages"][0]["sent_bytes"]
    with pytest.raises(artifact.SearchEnvelopeError):
        artifact.parse_search_envelope(missing_bytes)


# ---------------------------------------------------------------------------
# expression accounting (A6)
# ---------------------------------------------------------------------------


def test_expression_accounting_partition_invariant(graph, vault, state_root, monkeypatch):
    """unresolved_expressions ∪ (union of hit.matched_expressions) partitions
    query.expressions — unresolved is never re-derived from absence of hits."""
    _invoke(graph, vault, state_root, monkeypatch)
    receipt = _parse_envelope(state_root).receipt
    unresolved = set(receipt.result.unresolved_expressions)
    matched = set()
    for hit in receipt.result.hits:
        matched |= set(hit.matched_expressions)
    assert unresolved | matched == set(receipt.query.expressions)
    assert not unresolved & matched
    assert unresolved == {"management"}
    assert matched == {"moats"}


# ---------------------------------------------------------------------------
# key-outcome projection (P3a.2b wiring — §4.5 A6)
# ---------------------------------------------------------------------------


def test_outcome_carries_keys_emitted_and_key_outcomes(graph, vault, state_root, monkeypatch):
    """The adapter owns the projection inputs (keys, rendered expressions,
    unresolved set, summary) — so the outcome carries keys_emitted (ORIGINALS)
    plus the §4.5 positional KeyOutcomeV2 projection for the builder/record."""
    outcome = _invoke(graph, vault, state_root, monkeypatch)
    assert outcome.keys_emitted == ["moats", "management"]
    outcomes = {o.expression: o for o in outcome.key_outcomes}
    assert list(outcomes) == ["moats", "management"]
    moats = outcomes["moats"]
    assert moats.status == "matched"
    assert moats.annotation is None
    # First hit in fat-ranked order is charlie-munger (first_run_id "run-1").
    assert moats.matched_first_run_id == "run-1"
    assert moats.match_recency == "cohort"
    management = outcomes["management"]
    assert management.status == "unresolved"
    assert management.annotation == "no_match"
    assert management.matched_first_run_id is None
    assert management.match_recency is None


def test_pre_pass1_outcome_carries_empty_keys_and_null_outcomes(
        graph, vault, state_root, monkeypatch):
    """Pre-Pass-1 gate: no search ⇒ keys_emitted empty, key_outcomes None
    (distinct from a searched-but-keyless State C)."""
    outcome = _invoke(graph, vault, state_root, monkeypatch, fakes.NeverCalled(),
                      frontmatter=None)
    assert outcome.keys_emitted == []
    assert outcome.key_outcomes is None


# ---------------------------------------------------------------------------
# B9 — raised-with-audit: the FULL receipt survives a post-search raise
# ---------------------------------------------------------------------------


def test_post_search_raise_still_sinks_full_receipt(graph, vault, state_root, monkeypatch):
    """B9: an unexpected raise AFTER the audit exists (here: compact_receipt
    blows up) must not lose the failure bytes — the envelope lands as receipt
    kind "full" with the audit's stage bytes, the ORIGINAL exception
    propagates, and it carries the built summary for compile_source's B8."""
    def _boom(audit):
        raise RuntimeError("compactor exploded")

    monkeypatch.setattr(search_adapter, "compact_receipt", _boom)
    with pytest.raises(RuntimeError, match="compactor exploded") as exc_info:
        _invoke(graph, vault, state_root, monkeypatch)

    raw = _read_raw_envelope(state_root)
    assert raw["receipt_kind"] == "full"
    assert len(raw["receipt"]["stages"]) == 2
    for stage in raw["receipt"]["stages"]:
        assert "rendered_messages" in stage
        assert "raw_response_text" in stage
    receipt = _parse_envelope(state_root).receipt
    assert isinstance(receipt, artifact.SearchAuditPayload)

    summary = getattr(exc_info.value, "_kdb_search_summary", None)
    assert summary is not None
    assert summary.status == "completed"


def test_summary_build_raise_sinks_full_receipt_without_summary_attr(
        graph, vault, state_root, monkeypatch):
    """A raise BEFORE the summary exists: the FULL envelope still sinks (the
    audit precedes the summary), but the exception carries no summary attr."""
    def _boom(**kwargs):
        raise RuntimeError("summary build exploded")

    monkeypatch.setattr(search_adapter, "_build_summary", _boom)
    with pytest.raises(RuntimeError, match="summary build exploded") as exc_info:
        _invoke(graph, vault, state_root, monkeypatch)

    raw = _read_raw_envelope(state_root)
    assert raw["receipt_kind"] == "full"
    assert getattr(exc_info.value, "_kdb_search_summary", None) is None


# ---------------------------------------------------------------------------
# #123 P3a.4 (§4.7) — SearchPassMeasurement computed at run time, persisted
# as the additive "measurement" key of the search/*.json envelope file
# ---------------------------------------------------------------------------

from common.measurement import parse_search_measurement


def test_measurement_embedded_in_envelope_and_envelope_still_parses(
        graph, vault, state_root, monkeypatch):
    """The measurement is computed from the in-memory result/audit (never
    re-parsed from envelope bytes) and rides the same search/*.json file;
    the strict envelope parser tolerates the additive key."""
    outcome = _invoke(graph, vault, state_root, monkeypatch)
    assert outcome.envelope_written is True
    raw = _read_raw_envelope(state_root)
    m = parse_search_measurement(raw["measurement"])
    assert m.pass_ == "pass1_5"
    assert (m.run_id, m.source_id) == ("run-1", SOURCE_ID)
    spec = _spec()
    assert (m.provider, m.model) == (spec.provider, spec.model)
    assert m.status == "completed"
    assert m.execution == "two_stage_attempted"
    assert m.calls == 1                    # logical — one per source search
    assert m.attempts == 2                 # thin + fat StageRecords
    assert m.total_input_tokens == 2000    # scripted 1000 + 1000
    assert m.input_token_unknown_attempts == 0
    assert m.prompt_versions["thin"] and m.prompt_versions["fat"]
    assert [s.stage for s in m.stage_splits] == ["thin", "fat"]
    thin, fat = m.stage_splits
    assert (thin.attempts, thin.provider_input_tokens) == (1, 1000)
    assert (fat.attempts, fat.provider_input_tokens) == (1, 1000)
    assert thin.sent_bytes > 0 and fat.sent_bytes > 0
    assert m.cost_usd == pytest.approx(thin.cost_usd + fat.cost_usd)
    assert m.total_latency_ms == 24
    assert m.search_snapshot_hash
    # The strict envelope parser tolerates the additive sibling key.
    env = _parse_envelope(state_root)
    assert env.source_id == SOURCE_ID


def test_measurement_attempts_include_no_response_and_tokens_null(
        graph, vault, state_root, monkeypatch):
    """B10: a transport failure mid-stage produces a StageRecord with NO
    provider response — attempts counts it, total_input_tokens goes null
    (never zero-coerced), input_token_unknown_attempts carries the count."""
    script = fakes.FakeSelector(
        fakes.ScriptedReply(fakes.retained_document(SPACE)),
        fakes.transport_failure(),
        fakes.ScriptedReply(fakes.usable_document(SPACE, count=1, matched=("A",))),
    )
    _invoke(graph, vault, state_root, monkeypatch, script)
    m = parse_search_measurement(_read_raw_envelope(state_root)["measurement"])
    assert m.calls == 1
    assert m.attempts == 3                 # thin + fat-transport-fail + fat-retry
    assert m.total_input_tokens is None    # ANY unknown ⇒ null (B10)
    assert m.input_token_unknown_attempts == 1
    thin, fat = m.stage_splits
    assert thin.provider_input_tokens == 1000
    assert fat.attempts == 2
    assert fat.provider_input_tokens is None


def test_measurement_abstain_zero_attempts(graph, vault, state_root, monkeypatch):
    """abstain_empty_space (missing domain): the search ran (audit exists,
    envelope written) with ZERO selector attempts — calls is still the
    logical 1; prompt versions are null for stages that never ran."""
    _invoke(graph, vault, state_root, monkeypatch, fakes.NeverCalled(),
            frontmatter=_frontmatter(domain=None))
    m = parse_search_measurement(_read_raw_envelope(state_root)["measurement"])
    assert m.status == "abstain_empty_space"
    assert m.execution == "not_executed"
    assert m.calls == 1
    assert m.attempts == 0
    assert m.total_input_tokens == 0       # empty sum — nothing unknown
    assert m.input_token_unknown_attempts == 0
    assert m.cost_usd == 0.0 and m.total_latency_ms == 0
    assert m.prompt_versions == {"thin": None, "fat": None}
    assert all(s.attempts == 0 and s.sent_bytes == 0 for s in m.stage_splits)


def test_b9_envelope_carries_measurement_and_written_flag(
        graph, vault, state_root, monkeypatch):
    """The raised-with-audit sink persists the measurement too, and the
    exception carries the counting channel for compile_source: attempted +
    envelope_written."""
    def _boom(audit):
        raise RuntimeError("compactor exploded")

    monkeypatch.setattr(search_adapter, "compact_receipt", _boom)
    with pytest.raises(RuntimeError, match="compactor exploded") as exc_info:
        _invoke(graph, vault, state_root, monkeypatch)
    raw = _read_raw_envelope(state_root)
    assert raw["receipt_kind"] == "full"
    m = parse_search_measurement(raw["measurement"])
    assert m.status == "completed" and m.attempts == 2
    assert getattr(exc_info.value, "_kdb_search_attempted", None) is True
    assert getattr(exc_info.value, "_kdb_search_envelope_written", None) is True
