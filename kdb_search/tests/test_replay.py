"""#123 P2.6 — the two non-live modes (spec §5.2, blueprint §9).

**Every payload here is produced by a real `graph_search` run**, captured the way
`test_branch_table.py` captures it. Hand-building a `SearchAuditPayload` would
make these tests agree with my idea of what the orchestrator archives rather than
with what it archives — and the whole claim of replay is that the archive is
sufficient.

The two modes are tested for opposite properties, which is what §5.2's "named,
never conflated" comes down to:

  * **record replay** is tested for what it does NOT do — no call, no body read,
    nothing derived, nothing invented. Driven with `NeverCalled` and a raising
    body reader.
  * **historical re-call** is tested for what it holds FIXED — the archived bytes
    go out verbatim, the closed world is the archived one, and the outcome is
    stamped so it cannot be presented as a current search.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from common.model_pool import ModelRoute, ModelSpec
from common.paths import PageType

from kdb_search import replay, search
from kdb_search.artifact import SPACE_MANIFEST_REF, TITLE_ONLY_MARKER
from kdb_search.tests import fakes
from kdb_search.types import GraphSearchRequest, QueryPayload

SPACE = fakes.make_space(5)


def _spec(**overrides) -> ModelSpec:
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


def _body(slug: str, page_type: PageType) -> str:
    return f"Body text for {slug}, a {page_type} page with enough words to excerpt."


def _archive(*script, count: int = 5, monkeypatch, body_reader=_body, **kwargs):
    """Run a real search and return the payload it archived."""
    captured: dict = {}
    real = search.build_audit_payload

    def capture(**kw):
        payload = real(**kw)
        captured["audit"] = payload
        return payload

    monkeypatch.setattr(search, "build_audit_payload", capture)
    selector = fakes.FakeSelector(
        *(
            script
            or (
                fakes.ScriptedReply(fakes.retained_document(SPACE)),
                fakes.ScriptedReply(fakes.usable_document(SPACE, count=3)),
            )
        )
    )
    result = search.graph_search(
        GraphSearchRequest(
            query=QueryPayload(text="QUERY TEXT", expressions=("alpha", "beta")),
            search_space=fakes.make_space_ref(count),
        ),
        selector=kwargs.pop("selector", _spec()),
        call=selector,
        body_reader=body_reader,
    )
    return captured["audit"], result


# --------------------------------------------------------------------------
# record replay — the default mode
# --------------------------------------------------------------------------


def test_record_replay_returns_the_archived_selection(monkeypatch) -> None:
    audit, live = _archive(monkeypatch=monkeypatch)
    replayed = replay.replay_record(audit)
    assert replayed.hits == live.hits
    assert replayed.unresolved_expressions == live.unresolved_expressions
    assert replayed.status == live.status
    assert replayed.execution == live.execution
    assert replayed.evidence_status == live.evidence_status
    assert replayed.body_coverage == live.body_coverage


def test_record_replay_makes_NO_call_and_reads_NO_body(monkeypatch) -> None:
    """The mode's defining property, pinned structurally. `replay_record` takes
    neither a `call` nor a `body_reader`, so this is really a statement about the
    signature — which is the strongest form the claim can take: a mode that cannot
    be handed a selector cannot invoke one."""
    audit, _ = _archive(monkeypatch=monkeypatch)
    import inspect

    parameters = set(inspect.signature(replay.replay_record).parameters)
    assert parameters == {"audit"}
    replay.replay_record(audit)


def test_record_replay_is_NOT_a_GraphSearchResult(monkeypatch) -> None:
    """§5.2 says "the persisted historical selection", and that is what the
    archive holds. `telemetry` is not in the payload, and `budget_records` cannot
    be derived from it at all — pre-flight verdicts were never archived. A
    `GraphSearchResult` with empty telemetry would read as "the estimates were
    taken and were zero" and enter the D5 calibration series as a measurement."""
    audit, _ = _archive(monkeypatch=monkeypatch)
    replayed = replay.replay_record(audit)
    assert not hasattr(replayed, "telemetry")


def test_record_replay_carries_the_snapshot_hash_and_the_call_count(monkeypatch) -> None:
    """The two figures a replay reader needs that are not part of the selection:
    which world it ran against, and how many times it spent."""
    audit, _ = _archive(monkeypatch=monkeypatch)
    replayed = replay.replay_record(audit)
    assert replayed.search_snapshot_hash == audit.search_snapshot_hash
    assert replayed.logical_call_count == 2


@pytest.mark.parametrize(
    "terminal_script",
    [
        (),  # completed
        (fakes.ScriptedReply(fakes.retained_empty_document()),),  # D3 at N > M
    ],
    ids=["completed", "thin-retained-zero"],
)
def test_an_abstaining_run_replays_as_faithfully_as_a_successful_one(
    terminal_script, monkeypatch
) -> None:
    """§6 — the audit exists on every path, and its emptiness is the finding.
    A replay that only worked for successful searches would be unable to answer
    the question the record was kept for."""
    count = 5 if not terminal_script else 120
    audit, live = _archive(*terminal_script, count=count, monkeypatch=monkeypatch)
    replayed = replay.replay_record(audit)
    assert (replayed.status, replayed.execution) == (live.status, live.execution)
    assert replayed.hits == live.hits


# --------------------------------------------------------------------------
# integrity
# --------------------------------------------------------------------------


def test_a_tampered_result_fails_the_integrity_check(monkeypatch) -> None:
    """The check is what makes a replay history rather than a claim. Here the
    archived hits are edited — exactly the tamper an audit record exists to make
    impossible — and the hash no longer matches."""
    audit, _ = _archive(monkeypatch=monkeypatch)
    tampered = replace(audit, result=replace(audit.result, hits=()))
    with pytest.raises(replay.ReplayIntegrityError):
        replay.replay_record(tampered)


def test_a_tampered_STAGE_TRACE_fails_too(monkeypatch) -> None:
    """Not only the result. The integrity hash covers the query, the prompt refs,
    the full stage trace and the result — so editing what the selector was sent is
    caught as readily as editing what it returned."""
    audit, _ = _archive(monkeypatch=monkeypatch)
    first = audit.stages[0]
    tampered = replace(
        audit,
        stages=(replace(first, raw_response_text="{}"),) + audit.stages[1:],
    )
    with pytest.raises(replay.ReplayIntegrityError):
        replay.replay_record(tampered)


def test_the_integrity_check_ignores_latency_and_cost(monkeypatch) -> None:
    """Deliberately excluded from the hash: they vary run to run without the
    artifact having changed, and a hash that never reproduces cannot detect
    tampering. So a record differing only in those replays cleanly."""
    audit, _ = _archive(monkeypatch=monkeypatch)
    first = audit.stages[0]
    reclocked = replace(
        audit,
        stages=(replace(first, latency_ms=99_999, cost=42.0),) + audit.stages[1:],
    )
    assert replay.replay_record(reclocked).status == "completed"


def test_integrity_is_checked_BEFORE_any_re_call(monkeypatch) -> None:
    """Ordering that costs money if it is wrong. A tampered record must not reach
    the provider — `NeverCalled` is what proves the check ran first rather than
    alongside."""
    audit, _ = _archive(monkeypatch=monkeypatch)
    tampered = replace(audit, result=replace(audit.result, status="selector_failure"))
    with pytest.raises(replay.ReplayIntegrityError):
        replay.recall_stage(
            tampered,
            stage="fat",
            selector=_spec(),
            call=fakes.NeverCalled(),
            max_results=50,
        )


# --------------------------------------------------------------------------
# historical selector re-call — opt-in
# --------------------------------------------------------------------------


def test_the_recall_sends_the_ARCHIVED_BYTES_verbatim(monkeypatch) -> None:
    """The mode's whole purpose: hold the input fixed, vary the selector. Bytes
    re-rendered through the live projector would carry today's excerpt policy and
    template version against yesterday's data — a different experiment, silently.
    """
    audit, _ = _archive(monkeypatch=monkeypatch)
    fat_record = next(r for r in audit.stages if r.stage == "fat_selection")
    selector = fakes.FakeSelector(fakes.ScriptedReply(fakes.usable_document(SPACE, count=2)))
    replay.recall_stage(
        audit, stage="fat", selector=_spec(), call=selector, max_results=50
    )
    sent = selector.requests[0]
    assert sent.prompt == fat_record.rendered_messages.user
    assert sent.system == fat_record.rendered_messages.system


def test_the_recall_reads_NO_body(monkeypatch) -> None:
    """`recall_stage` takes no `body_reader` — the evidence is the archive's. The
    signature is the guarantee; there is nothing to hand it."""
    import inspect

    parameters = set(inspect.signature(replay.recall_stage).parameters)
    assert "body_reader" not in parameters


def test_the_recall_outcome_is_STAMPED_historical(monkeypatch) -> None:
    """§5.2 — results from this mode are never presented as current graph search.
    The stamp travels with the result rather than being remembered by whoever
    asked for it, because a bare `StageOutcome` is indistinguishable from a live
    one at exactly the point where the distinction matters."""
    audit, _ = _archive(monkeypatch=monkeypatch)
    recalled = replay.recall_stage(
        audit,
        stage="fat",
        selector=_spec(),
        call=fakes.FakeSelector(fakes.ScriptedReply(fakes.usable_document(SPACE, count=2))),
        max_results=50,
    )
    assert recalled.mode == replay.HISTORICAL_RECALL
    assert recalled.stage == "fat"


def test_a_DIFFERENT_selector_can_answer_the_same_archived_request(monkeypatch) -> None:
    """The A/B the mode exists for: same bytes, same closed world, a different
    model — and the new answer differs from the archived one."""
    audit, live = _archive(monkeypatch=monkeypatch)
    recalled = replay.recall_stage(
        audit,
        stage="fat",
        selector=_spec(id="challenger", provider="gemini", model="other-model",
                       route=ModelRoute("gemini", None, "GEMINI_API_KEY")),
        call=fakes.FakeSelector(fakes.ScriptedReply(fakes.usable_document(SPACE, count=1))),
        max_results=50,
    )
    assert len(recalled.outcome.validated.hits) == 1
    assert len(live.hits) == 3
    assert recalled.outcome.records[0].model.model == "other-model"


def test_the_recall_validates_against_the_pool_the_stage_ACTUALLY_SAW(
    monkeypatch,
) -> None:
    """Fat's closed world is the archived EVIDENCE, not the manifest. Above M the
    two differ — the fat stage only ever saw thin's retained pool — and validating
    a re-call against the full manifest would accept a slug the selector was never
    shown, quietly widening the closed-world guarantee the original run had."""
    large = fakes.make_space(120)
    audit, _ = _archive(
        fakes.ScriptedReply(fakes._dump({"retained": [e.slug for e in large[:3]]})),
        fakes.ScriptedReply(fakes.usable_document(large, count=2)),
        count=120,
        monkeypatch=monkeypatch,
    )
    # The challenger names an entity that is in the manifest but was NOT pooled.
    outside = large[50].slug
    document = fakes._dump({"selections": [{"slug": outside, "matched": ["A"]}]})
    # Two replies: naming an unpooled slug drops every entry, which is an allowed
    # retry class — so the pool rejection is visible as an EXHAUSTED stage, not
    # merely as a dropped hit.
    recalled = replay.recall_stage(
        audit,
        stage="fat",
        selector=_spec(),
        call=fakes.FakeSelector(
            fakes.ScriptedReply(document), fakes.ScriptedReply(document)
        ),
        max_results=50,
    )
    assert recalled.outcome.outcome == "exhausted"
    assert recalled.outcome.failure_class == "all_entries_dropped"
    assert recalled.outcome.attempted_violations.foreign_slug == 2


def test_the_thin_recall_validates_against_the_WHOLE_manifest(monkeypatch) -> None:
    """The counterpart: thin's closed world IS the manifest, so a re-called thin
    may legitimately retain anything in it — including entities the archived fat
    pool never contained."""
    large = fakes.make_space(120)
    audit, _ = _archive(
        fakes.ScriptedReply(fakes._dump({"retained": [e.slug for e in large[:3]]})),
        fakes.ScriptedReply(fakes.usable_document(large, count=2)),
        count=120,
        monkeypatch=monkeypatch,
    )
    outside = large[50].slug
    recalled = replay.recall_stage(
        audit,
        stage="thin",
        selector=_spec(),
        call=fakes.FakeSelector(fakes.ScriptedReply(fakes._dump({"retained": [outside]}))),
        max_results=50,
    )
    assert recalled.outcome.validated.retained == (outside,)


def test_a_fat_record_with_non_map_evidence_is_REFUSED_not_widened(monkeypatch) -> None:
    """The branch is unreachable through `search.py` — thin always archives
    `SPACE_MANIFEST_REF`, fat always archives the excerpt map — so what matters is
    which way it fails if an archive is ever corrupt. Falling back to the manifest
    (the first version) would re-call against a WIDER closed world than the run it
    claims to replay, quietly accepting slugs the selector was never shown. It
    raises instead. Reached by corrupting the record directly, since nothing in
    production can produce it."""
    audit, _ = _archive(monkeypatch=monkeypatch)
    fat_index = next(
        i for i, s in enumerate(audit.stages) if s.stage == "fat_selection"
    )
    stages = list(audit.stages)
    stages[fat_index] = replace(stages[fat_index], evidence="not-a-map")
    corrupt = replace(audit, stages=tuple(stages))
    # Re-hash so the corruption is not merely caught by the integrity check —
    # otherwise this would test that check a third time rather than the pool rule.
    from kdb_search.artifact import compute_artifact_integrity_hash

    corrupt = replace(
        corrupt,
        artifact_integrity_hash=compute_artifact_integrity_hash(
            query=corrupt.query,
            stages=corrupt.stages,
            result=corrupt.result,
            execution=corrupt.execution,
        ),
    )
    with pytest.raises(replay.ReplayIntegrityError, match="not the"):
        replay.recall_stage(
            corrupt, stage="fat", selector=_spec(), call=fakes.NeverCalled(), max_results=50
        )


def test_recalling_a_stage_the_run_never_reached_is_refused(monkeypatch) -> None:
    """A D3 run has no fat stage. Re-calling one would mean synthesizing a
    request that was never made, which is the opposite of what this mode is."""
    audit, _ = _archive(
        fakes.ScriptedReply(fakes.retained_empty_document()), count=120, monkeypatch=monkeypatch
    )
    with pytest.raises(replay.ReplayIntegrityError, match="no 'fat' stage"):
        replay.recall_stage(
            audit, stage="fat", selector=_spec(), call=fakes.NeverCalled(), max_results=50
        )


def test_the_recall_takes_NO_preflight_and_invents_no_budget_figures(
    monkeypatch,
) -> None:
    """A budget verdict is a decision about whether to BUILD a request, and this
    request was built in the past. `stage_call` requires one, so re-call passes an
    explicitly archival verdict whose figures are zeros — inert, and unable to be
    mistaken for a measurement if one ever reaches a record."""
    audit, _ = _archive(monkeypatch=monkeypatch)
    recalled = replay.recall_stage(
        audit,
        stage="fat",
        selector=_spec(),
        call=fakes.FakeSelector(
            fakes.ScriptedReply(
                fakes.truncated_text(SPACE), stop_reason=fakes.STOP_LENGTH_OPENAI
            )
        ),
        max_results=50,
    )
    record = recalled.outcome.budget_record
    assert record is not None  # a truncation still types itself
    # The ESTIMATE is zero — there was none, and inventing one is the failure this
    # guards. `selector_window` is not zeroed and should not be: it is a real
    # property of the route being called NOW, which is the variable the A/B is
    # changing, so it is the one figure on this record that means something.
    assert record.budget_estimate_tokens == 0
    assert record.selector_window == 400_000
    assert record.finish_reason_normalized == "output_cap"


def test_the_recall_still_honours_the_retry_and_stop_reason_contracts(
    monkeypatch,
) -> None:
    """Re-call goes through the SAME `stage_call`, so nothing about the attempt
    contract is special-cased for it. A second implementation would be a second
    place for D9.3 to drift."""
    audit, _ = _archive(monkeypatch=monkeypatch)
    selector = fakes.FakeSelector(
        fakes.ScriptedReply(fakes.unparseable_text()),
        fakes.ScriptedReply(fakes.usable_document(SPACE, count=2)),
    )
    recalled = replay.recall_stage(
        audit, stage="fat", selector=_spec(), call=selector, max_results=50
    )
    selector.assert_consumed()
    assert recalled.outcome.attempts == 2
    assert recalled.outcome.records[0].failure.failure_class == "unparseable_response"


def test_the_archived_evidence_travels_onto_the_new_records(monkeypatch) -> None:
    """So the re-call's own trace hashes against the same world. Thin's evidence
    is the manifest reference; fat's is the frozen excerpt map."""
    audit, _ = _archive(monkeypatch=monkeypatch)
    thin = replay.recall_stage(
        audit,
        stage="thin",
        selector=_spec(),
        call=fakes.FakeSelector(fakes.ScriptedReply(fakes.retained_document(SPACE))),
        max_results=50,
    )
    fat = replay.recall_stage(
        audit,
        stage="fat",
        selector=_spec(),
        call=fakes.FakeSelector(fakes.ScriptedReply(fakes.usable_document(SPACE, count=1))),
        max_results=50,
    )
    assert thin.outcome.records[0].evidence == SPACE_MANIFEST_REF
    assert set(fat.outcome.records[0].evidence) == {e.slug for e in SPACE}


def test_a_title_only_entity_stays_title_only_in_the_recall(monkeypatch) -> None:
    """Frozen evidence means frozen degradation. A body that has since appeared on
    disk must not hydrate the re-call — the comparison would then vary the input
    as well as the selector, which is the one thing the mode forbids."""

    def missing_first(slug: str, page_type: PageType) -> str:
        from pathlib import Path

        from common.wiki_io import ContentNotFoundError

        if slug == SPACE[0].slug:
            raise ContentNotFoundError(slug, page_type, Path("/nonexistent.md"))
        return _body(slug, page_type)

    audit, _ = _archive(monkeypatch=monkeypatch, body_reader=missing_first)
    recalled = replay.recall_stage(
        audit,
        stage="fat",
        selector=_spec(),
        call=fakes.FakeSelector(fakes.ScriptedReply(fakes.usable_document(SPACE, count=1))),
        max_results=50,
    )
    assert recalled.outcome.records[0].evidence[SPACE[0].slug] == TITLE_ONLY_MARKER


# --------------------------------------------------------------------------
# the #119 bullet, filed where it actually lives
# --------------------------------------------------------------------------


def test_the_119_context_snapshot_bullet_is_NOT_this_packages(monkeypatch) -> None:
    """Blueprint §9 carries "#119 byte-pinning survives (caller-supplied
    `context_snapshot=` writes no record)". That is `build_context_snapshot` on
    the COMPILER side (§3.2) — `kdb_search` has no `context_snapshot` parameter
    anywhere, and adding one to satisfy a misfiled bullet would invent a coupling
    R2 forbids. Asserted as an absence so the bullet's disposition is recorded in
    code rather than only in the plan.
    """
    import inspect

    surface = {
        name
        for fn in (search.graph_search, replay.replay_record, replay.recall_stage)
        for name in inspect.signature(fn).parameters
    }
    assert "context_snapshot" not in surface
