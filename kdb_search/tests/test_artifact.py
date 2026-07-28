"""P1.4 — audit artifact + integrity hashes (#123 spec §5.1, blueprint §6).

The load-bearing property is the SEPARATION of the two hashes. `search_snapshot_hash`
answers "what was searched"; `artifact_integrity_hash` answers "what happened". If
the snapshot hash moved with the result, selector A/B over a frozen snapshot would
be meaningless — so most of this file is about what each hash does and does not
cover.

The second property is that a payload exists on EVERY path. An audit record that
appears only on success cannot answer the question an audit exists for.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from kdb_search.artifact import (
    ARTIFACT_SCHEMA_VERSION,
    SPACE_MANIFEST_REF,
    TITLE_ONLY_MARKER,
    ModelStamp,
    PromptRef,
    RenderedMessages,
    SearchResultSummary,
    SearchRunEnvelope,
    StageFailure,
    StageRecord,
    StageValidation,
    build_audit_payload,
    compute_artifact_integrity_hash,
    compute_search_snapshot_hash,
)
from kdb_search.constants import EXCERPT_POLICY_VERSION
from kdb_search.projection import render_query_block
from kdb_search.types import GraphSnapshotRef, Hit, QueryPayload, SpaceEntity

GRAPH = GraphSnapshotRef(
    schema_version="2.4",
    active_entity_count=163,
    space_fingerprint="fp-abc",
    source_kind="kuzu",
    source_detail="/graph/kdb",
)
MANIFEST = (
    SpaceEntity(slug="warren-buffett", title="Warren Buffett", page_type="concept"),
    SpaceEntity(slug="owner-earnings", title="Owner Earnings", page_type="concept"),
)
QUERY = QueryPayload(text="value investing", expressions=("warren-buffett", "moats"))
HIT = Hit(slug="warren-buffett", title="Warren Buffett", page_type="concept",
          matched_expressions=("warren-buffett",))
PROMPT = PromptRef(version="1", sha256="sha256:deadbeef", repo_path="kdb_search/prompts/fat.txt",
                   git_commit="abc1234")


def _stage(**overrides) -> StageRecord:
    base = dict(
        stage="fat_selection",
        attempt=1,
        prompt=PROMPT,
        rendered_messages=RenderedMessages(system="SYS", user="USER"),
        model=ModelStamp(provider="deepseek", model="deepseek-v4-flash", route="openai_compat"),
        evidence={"warren-buffett": "an excerpt", "owner-earnings": TITLE_ONLY_MARKER},
        latency_ms=1_200,
        cost=0.0004,
        excerpt_policy_version=EXCERPT_POLICY_VERSION,
        raw_response_text='{"selections":[{"slug":"warren-buffett","matched":["A"]}]}',
        parsed_output={"selections": [{"slug": "warren-buffett", "matched": ["A"]}]},
        validation=StageValidation(dropped={"foreign_slug": 0}, coerced={}, counts={"returned": 1}),
    )
    return StageRecord(**{**base, **overrides})


def _result(**overrides) -> SearchResultSummary:
    base = dict(hits=(HIT,), unresolved_expressions=("moats",), status="completed",
                evidence_status="complete", body_coverage=0.5)
    return SearchResultSummary(**{**base, **overrides})


def _payload(**overrides):
    base = dict(graph_ref=GRAPH, query=QUERY, manifest=MANIFEST,
                execution="two_stage_attempted", stages=(_stage(),), result=_result())
    return build_audit_payload(**{**base, **overrides})


# --------------------------------------------------------------------------
# built on every path
# --------------------------------------------------------------------------

def test_a_completed_search_produces_a_payload():
    p = _payload()
    assert p.schema_version == ARTIFACT_SCHEMA_VERSION
    assert p.result.status == "completed"
    assert p.logical_call_count == 1


def test_an_abstention_produces_a_payload_with_no_stages():
    """Zero calls is a real outcome. The emptiness is the finding, not a reason to
    skip the record."""
    p = _payload(
        execution="not_executed", stages=(), manifest=(),
        result=_result(hits=(), unresolved_expressions=("warren-buffett", "moats"),
                       status="abstain_empty_space", evidence_status="not_applicable",
                       body_coverage=None),
    )
    assert p.logical_call_count == 0
    assert p.search_snapshot_hash.startswith("sha256:")
    assert p.artifact_integrity_hash.startswith("sha256:")


def test_a_preflight_budget_exceeded_produces_a_payload_with_no_stages():
    p = _payload(
        execution="not_executed", stages=(),
        result=_result(hits=(), status="budget_exceeded", evidence_status="not_applicable",
                       body_coverage=None),
    )
    assert p.logical_call_count == 0
    assert p.result.status == "budget_exceeded"


def test_a_selector_failure_produces_a_payload_carrying_the_failed_attempts():
    """Both attempts are archived, each with its own bytes — the failure audit IS
    the case this exists for."""
    p = _payload(
        execution="thin_attempted",
        stages=(
            _stage(stage="thin_selection", attempt=1, raw_response_text="{ truncated",
                   parsed_output=None, failure=StageFailure("unparseable_response", "no document"),
                   evidence=SPACE_MANIFEST_REF, excerpt_policy_version=None),
            _stage(stage="thin_selection", attempt=2, raw_response_text="also bad",
                   parsed_output=None, failure=StageFailure("unparseable_response", "no document"),
                   evidence=SPACE_MANIFEST_REF, excerpt_policy_version=None),
        ),
        result=_result(hits=(), status="selector_failure", evidence_status="not_applicable",
                       body_coverage=None),
    )
    assert p.logical_call_count == 2
    assert [s.attempt for s in p.stages] == [1, 2]
    assert all(s.parsed_output is None for s in p.stages)
    assert p.stages[0].raw_response_text != p.stages[1].raw_response_text


def test_logical_call_count_equals_the_stage_record_count():
    """The invariant. SDK transport sub-retries are excluded from BOTH sides — they
    are the provider's business, not an attempt we made."""
    for count in range(4):
        stages = tuple(_stage(attempt=i + 1) for i in range(count))
        assert _payload(stages=stages).logical_call_count == count == len(stages)


# --------------------------------------------------------------------------
# byte fidelity
# --------------------------------------------------------------------------

def test_the_exact_rendered_system_and_user_bytes_are_archived():
    stage = _stage(rendered_messages=RenderedMessages(system="S\n  édge", user="U\ttab"))
    p = _payload(stages=(stage,))
    assert p.stages[0].rendered_messages.system == "S\n  édge"
    assert p.stages[0].rendered_messages.user == "U\ttab"


def test_malformed_raw_response_text_is_archived_verbatim():
    """The malformed and timeout cases are exactly the failure-audit cases, so the
    raw text must survive unnormalized."""
    malformed = '{"selections": [{"slug": "war\x01ren"'
    p = _payload(stages=(_stage(raw_response_text=malformed, parsed_output=None),))
    assert p.stages[0].raw_response_text == malformed


def test_stage_one_records_the_manifest_reference_not_a_copy_of_the_evidence():
    stage = _stage(stage="thin_selection", evidence=SPACE_MANIFEST_REF,
                   excerpt_policy_version=None, retained_identities=("warren-buffett",))
    p = _payload(stages=(stage,))
    assert p.stages[0].evidence == SPACE_MANIFEST_REF
    assert p.stages[0].retained_identities == ("warren-buffett",)
    assert p.stages[0].excerpt_policy_version is None


def test_a_title_only_entity_is_marked_in_the_evidence():
    p = _payload()
    assert p.stages[0].evidence["owner-earnings"] == TITLE_ONLY_MARKER


def test_the_rendered_query_record_is_carried_when_truncation_fired():
    rendered = render_query_block(author="A" * 4_000, summary="S" * 20_000)
    p = _payload(rendered_query=rendered)
    assert p.rendered_query is not None
    assert "author" in p.rendered_query.query_truncated
    assert "author" in p.rendered_query.original_fields
    assert "author" in p.rendered_query.rendered_fields


def test_the_rendered_query_record_is_optional_for_a_direct_text_caller():
    assert _payload().rendered_query is None


# --------------------------------------------------------------------------
# the two hashes — what each one covers
# --------------------------------------------------------------------------

def test_both_hashes_are_deterministic():
    assert _payload().search_snapshot_hash == _payload().search_snapshot_hash
    assert _payload().artifact_integrity_hash == _payload().artifact_integrity_hash


def test_the_two_hashes_are_not_the_same_value():
    p = _payload()
    assert p.search_snapshot_hash != p.artifact_integrity_hash


def test_the_snapshot_hash_ignores_the_result_which_is_what_makes_ab_meaningful():
    """THE load-bearing property: two selectors run over one frozen snapshot must
    produce the same snapshot hash and different integrity hashes. If the snapshot
    hash moved with the result, selector A/B over a frozen snapshot would compare
    nothing."""
    a = _payload(result=_result(hits=(HIT,)))
    b = _payload(result=_result(hits=(), status="completed", unresolved_expressions=("warren-buffett", "moats")))
    assert a.search_snapshot_hash == b.search_snapshot_hash
    assert a.artifact_integrity_hash != b.artifact_integrity_hash


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema_version": "2.5"},
        {"active_entity_count": 164},
        {"space_fingerprint": "fp-xyz"},
        {"source_kind": "fixture"},
        {"source_detail": "/other"},
    ],
)
def test_every_graph_identity_field_moves_the_snapshot_hash(mutation):
    baseline = compute_search_snapshot_hash(graph_ref=GRAPH, manifest=MANIFEST, stages=(_stage(),))
    moved = compute_search_snapshot_hash(
        graph_ref=replace(GRAPH, **mutation), manifest=MANIFEST, stages=(_stage(),)
    )
    assert baseline != moved, f"{mutation} did not move the snapshot hash"


def test_manifest_order_moves_the_snapshot_hash():
    """Order-sensitive on purpose: the hash pins the exact space, in the exact
    order, that was presented to the selector."""
    forward = compute_search_snapshot_hash(graph_ref=GRAPH, manifest=MANIFEST, stages=())
    backward = compute_search_snapshot_hash(graph_ref=GRAPH, manifest=MANIFEST[::-1], stages=())
    assert forward != backward


def test_manifest_membership_moves_the_snapshot_hash():
    trimmed = compute_search_snapshot_hash(graph_ref=GRAPH, manifest=MANIFEST[:1], stages=())
    assert trimmed != compute_search_snapshot_hash(graph_ref=GRAPH, manifest=MANIFEST, stages=())


def test_a_single_evidence_byte_moves_the_snapshot_hash():
    """Byte fidelity of what the selector actually saw."""
    baseline = compute_search_snapshot_hash(graph_ref=GRAPH, manifest=MANIFEST, stages=(_stage(),))
    nudged = compute_search_snapshot_hash(
        graph_ref=GRAPH, manifest=MANIFEST,
        stages=(_stage(evidence={"warren-buffett": "an excerpt.", "owner-earnings": TITLE_ONLY_MARKER}),),
    )
    assert baseline != nudged


def test_the_projection_policy_identity_moves_the_snapshot_hash():
    """Policy v1 and v2 can produce identical bytes on a corpus the ceiling does
    not bind — so the policy must be hashed explicitly, or a re-projection under
    new rules would look like the same snapshot."""
    v2 = compute_search_snapshot_hash(graph_ref=GRAPH, manifest=MANIFEST, stages=(_stage(),))
    v1 = compute_search_snapshot_hash(
        graph_ref=GRAPH, manifest=MANIFEST, stages=(_stage(),), excerpt_policy_version="1"
    )
    assert v2 != v1


@pytest.mark.parametrize(
    "mutation",
    [
        {"hits": ()},
        {"unresolved_expressions": ()},
        {"status": "selector_failure"},
        {"evidence_status": "partial"},
        {"body_coverage": 1.0},
    ],
)
def test_every_result_field_moves_the_integrity_hash(mutation):
    baseline = compute_artifact_integrity_hash(
        query=QUERY, stages=(_stage(),), result=_result(), execution="two_stage_attempted"
    )
    moved = compute_artifact_integrity_hash(
        query=QUERY, stages=(_stage(),), result=_result(**mutation), execution="two_stage_attempted"
    )
    assert baseline != moved, f"{mutation} did not move the integrity hash"


@pytest.mark.parametrize(
    "mutation",
    [
        {"rendered_messages": RenderedMessages(system="OTHER", user="USER")},
        {"rendered_messages": RenderedMessages(system="SYS", user="OTHER")},
        {"raw_response_text": "something else"},
        {"prompt": replace(PROMPT, version="2")},
        {"prompt": replace(PROMPT, sha256="sha256:0000")},
        {"prompt": replace(PROMPT, git_commit="ffff")},
        {"model": ModelStamp(provider="openai", model="gpt-5.4-mini", route="openai_compat")},
        {"attempt": 2},
        {"failure": StageFailure("all_entries_dropped", "every entry foreign")},
        {"validation": StageValidation(dropped={"foreign_slug": 3})},
    ],
)
def test_every_stage_trace_field_moves_the_integrity_hash(mutation):
    baseline = compute_artifact_integrity_hash(
        query=QUERY, stages=(_stage(),), result=_result(), execution="two_stage_attempted"
    )
    moved = compute_artifact_integrity_hash(
        query=QUERY, stages=(_stage(**mutation),), result=_result(), execution="two_stage_attempted"
    )
    assert baseline != moved, f"{mutation} did not move the integrity hash"


def test_the_query_moves_the_integrity_hash():
    baseline = compute_artifact_integrity_hash(
        query=QUERY, stages=(), result=_result(), execution="not_executed"
    )
    for other in (QueryPayload(text="other", expressions=QUERY.expressions),
                  QueryPayload(text=QUERY.text, expressions=("different",))):
        assert compute_artifact_integrity_hash(
            query=other, stages=(), result=_result(), execution="not_executed"
        ) != baseline


def test_execution_moves_the_integrity_hash():
    """`fat_after_thin_failure` and `two_stage_attempted` can carry identical
    stages and results while describing different journeys."""
    a = compute_artifact_integrity_hash(query=QUERY, stages=(_stage(),), result=_result(),
                                        execution="two_stage_attempted")
    b = compute_artifact_integrity_hash(query=QUERY, stages=(_stage(),), result=_result(),
                                        execution="fat_after_thin_failure")
    assert a != b


def test_latency_and_cost_are_excluded_from_the_integrity_hash():
    """They vary run to run without the artifact having changed. An integrity hash
    that never reproduces cannot detect tampering."""
    baseline = compute_artifact_integrity_hash(
        query=QUERY, stages=(_stage(),), result=_result(), execution="two_stage_attempted"
    )
    jittered = compute_artifact_integrity_hash(
        query=QUERY, stages=(_stage(latency_ms=9_999, cost=1.23),), result=_result(),
        execution="two_stage_attempted",
    )
    assert baseline == jittered


def test_attempt_order_moves_the_integrity_hash():
    first = (_stage(attempt=1), _stage(attempt=2))
    swapped = (_stage(attempt=2), _stage(attempt=1))
    assert compute_artifact_integrity_hash(
        query=QUERY, stages=first, result=_result(), execution="thin_attempted"
    ) != compute_artifact_integrity_hash(
        query=QUERY, stages=swapped, result=_result(), execution="thin_attempted"
    )


def test_hashes_carry_their_algorithm_prefix_per_repo_convention():
    p = _payload()
    for digest in (p.search_snapshot_hash, p.artifact_integrity_hash):
        algorithm, _, hexdigest = digest.partition(":")
        assert algorithm == "sha256"
        assert len(hexdigest) == 64 and set(hexdigest) <= set("0123456789abcdef")


def test_non_ascii_evidence_hashes_stably():
    stage = _stage(evidence={"warren-buffett": "café — 漢字", "owner-earnings": TITLE_ONLY_MARKER})
    first = compute_search_snapshot_hash(graph_ref=GRAPH, manifest=MANIFEST, stages=(stage,))
    second = compute_search_snapshot_hash(graph_ref=GRAPH, manifest=MANIFEST, stages=(stage,))
    assert first == second


# --------------------------------------------------------------------------
# the consumer-neutral core / pass-1.5 envelope split (codex F5, R2)
# --------------------------------------------------------------------------

def test_the_core_payload_carries_nothing_consumer_specific():
    """An MCP/CLI/human search has neither run_id nor source_id. If either leaked
    into the core, every consumer would need its own type."""
    fields = set(_payload().__dataclass_fields__)
    assert not fields & {"run_id", "source_id", "intra_run_order", "artifact_path"}


def test_the_envelope_adds_the_pass_1_5_specifics_around_the_same_core():
    envelope = SearchRunEnvelope(
        audit=_payload(), run_id="run-1", source_id="src-1", intra_run_order=3,
    )
    assert envelope.audit.schema_version == ARTIFACT_SCHEMA_VERSION
    assert envelope.artifact_path is None, "null until the write succeeds — warn-only sink"
    assert envelope.intra_run_order == 3


# --------------------------------------------------------------------------
# gaps found by mutating the module (2026-07-26) — each of these passed the
# suite before the assertion below existed
# --------------------------------------------------------------------------

def test_the_snapshot_hash_ignores_everything_the_selector_produced():
    """Stronger than the result-only version above: a frozen-snapshot A/B varies
    the raw response, the parsed output AND the result. If any of those reached the
    snapshot digest, two selectors compared over one snapshot would report two
    different snapshots — and the comparison would be meaningless.
    """
    selector_a = _payload(
        stages=(_stage(raw_response_text='{"selections":[]}', parsed_output={"selections": []}),),
        result=_result(hits=(), unresolved_expressions=("warren-buffett", "moats")),
    )
    selector_b = _payload(
        stages=(_stage(raw_response_text='{"selections":[{"slug":"warren-buffett"}]}',
                       parsed_output={"selections": [{"slug": "warren-buffett"}]}),),
        result=_result(hits=(HIT,)),
    )
    assert selector_a.search_snapshot_hash == selector_b.search_snapshot_hash
    assert selector_a.artifact_integrity_hash != selector_b.artifact_integrity_hash


def test_dict_key_insertion_order_never_changes_a_digest():
    """Canonical JSON must sort keys. Without it, a `validation` mapping that P2
    happens to assemble in a different order hashes differently — an integrity
    hash that reports tampering because a dict was built by another code path."""
    forward = StageValidation(
        dropped={"foreign_slug": 1, "malformed_entry": 2},
        coerced={"duplicate_slug": 3, "unknown_expression": 4},
        counts={"returned": 5, "valid": 6},
    )
    reordered = StageValidation(
        dropped={"malformed_entry": 2, "foreign_slug": 1},
        coerced={"unknown_expression": 4, "duplicate_slug": 3},
        counts={"valid": 6, "returned": 5},
    )
    assert compute_artifact_integrity_hash(
        query=QUERY, stages=(_stage(validation=forward),), result=_result(),
        execution="two_stage_attempted",
    ) == compute_artifact_integrity_hash(
        query=QUERY, stages=(_stage(validation=reordered),), result=_result(),
        execution="two_stage_attempted",
    )


def test_evidence_key_insertion_order_never_changes_the_snapshot_hash():
    forward = {"warren-buffett": "excerpt", "owner-earnings": TITLE_ONLY_MARKER}
    reordered = {"owner-earnings": TITLE_ONLY_MARKER, "warren-buffett": "excerpt"}
    assert compute_search_snapshot_hash(
        graph_ref=GRAPH, manifest=MANIFEST, stages=(_stage(evidence=forward),)
    ) == compute_search_snapshot_hash(
        graph_ref=GRAPH, manifest=MANIFEST, stages=(_stage(evidence=reordered),)
    )


@pytest.mark.parametrize("mutation", [{"title": "Different Title"}, {"page_type": "article"}])
def test_manifest_title_and_page_type_move_the_snapshot_hash(mutation):
    """Not just slugs: the THIN stage's entire evidence is
    `- slug: … title: … type: …`. Two spaces with identical slugs but different
    titles present the selector with genuinely different evidence, so hashing slugs
    alone would call two different searches the same snapshot."""
    altered = (replace(MANIFEST[0], **mutation),) + MANIFEST[1:]
    assert compute_search_snapshot_hash(
        graph_ref=GRAPH, manifest=MANIFEST, stages=()
    ) != compute_search_snapshot_hash(graph_ref=GRAPH, manifest=altered, stages=())
