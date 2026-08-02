"""#123 D5 — tests for the calibration harness (`tools/task123_calibrate_estimator`).

This harness spends real money, exactly three times, and the figure it writes is
what `ESTIMATOR_BYTES_PER_TOKEN` gets judged against. So the tests here are not
about output formatting — every one of them defends a property that costs
something to get wrong:

  * the calibrated request **is** the production request (else the measurement
    describes a request nothing sends),
  * the ceiling refuses rather than trusts the loop,
  * dry run cannot call,
  * a late failure cannot destroy an earlier paid measurement,
  * the checksummed fixture is not mutated, and the check that says so fires.

No `@pytest.mark.live` cases: the point of the harness is that the paid path is
entered deliberately by the owner, not by a test run.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from common.call_model import ModelResponse
from kdb_search import budget
from kdb_search.constants import M
from kdb_search.prompts import render_thin_messages
from kdb_search.stage import _model_request
from tools import task123_calibrate_estimator as cal


@pytest.fixture
def calibration() -> cal.CalibrationInput:
    return cal.build_input()


@pytest.fixture
def spec():
    return cal._resolve("gemini-3.6-flash")


def _response(input_tokens: int = 5_000) -> ModelResponse:
    return ModelResponse(
        text="{}",
        input_tokens=input_tokens,
        output_tokens=1,
        latency_ms=10,
        model="m",
        provider="p",
    )


# --------------------------------------------------------------------------
# the request is the production request
# --------------------------------------------------------------------------


@pytest.mark.parametrize("model_id", cal.D4_COHORT)
def test_the_calibration_request_matches_production_in_every_field_but_max_tokens(
    model_id,
):
    """The load-bearing test in this file.

    A calibration whose request differs from the real one measures a request the
    system never sends. Compared field by field against `stage._model_request`
    rather than by eye, so a future field added to the production request fails
    here instead of silently going unmeasured.

    **Parameterized over the whole cohort, and that is not decoration** — a
    single-candidate version of this test survived a mutation sweep that dropped
    `extra_body`. gemini-3.6-flash declares none, so on that spec the mutation was
    a no-op; deepseek-v4-flash carries `{"thinking": {"type": "disabled"}}` and
    gpt-5.4-mini carries `{"reasoning_effort": "low"}`, so losing the field would
    have fired deepseek's calibration call with thinking ON — a request production
    never sends, billed.
    """
    spec = cal._resolve(model_id)
    messages = render_thin_messages(evidence="- slug: a", query="", retention_cap=M)
    production = _model_request("thin", messages, spec)
    calibrated = cal.calibration_request(spec, messages)

    diverged = {
        field
        for field in vars(production)
        if getattr(production, field) != getattr(calibrated, field)
    }
    assert diverged == {"max_tokens"}, (
        "the calibration request must differ from the production thin request in "
        f"max_tokens ALONE; it also differs in {diverged - {'max_tokens'}}"
    )


def test_the_one_divergence_is_downward_and_deliberate(spec):
    """`max_tokens` is capped low because `input_tokens` is settled before any
    output exists — buying three full thin selections to read a number that does
    not depend on them is spend for nothing. Asserted as a comparison rather than
    a literal so raising the production envelope cannot quietly make the
    calibration call the expensive one."""
    messages = render_thin_messages(evidence="", query="", retention_cap=M)
    calibrated = cal.calibration_request(spec, messages)
    assert calibrated.max_tokens == cal.CALIBRATION_MAX_TOKENS
    assert calibrated.max_tokens < budget.provider_max_tokens("thin")


def test_json_mode_is_on_because_the_production_request_has_it(spec):
    """Not cosmetic: `response_format` / `response_mime_type` is part of the
    request the provider counts. A calibration without it measures a different
    request than the one the estimator guards."""
    messages = render_thin_messages(evidence="", query="", retention_cap=M)
    assert cal.calibration_request(spec, messages).json_mode is True


# --------------------------------------------------------------------------
# what gets measured
# --------------------------------------------------------------------------


def test_rendered_bytes_is_the_quantity_search_hands_to_preflight(calibration):
    """`search.py:219` computes `len(system) + len(user)` and passes it to
    `budget.preflight`. If this harness measured anything else — the evidence
    block alone, the user message alone — it would calibrate a ratio the
    estimator never applies."""
    expected = len(calibration.messages.system.encode()) + len(
        calibration.messages.user.encode()
    )
    assert calibration.rendered_bytes == expected


def test_the_evidence_is_the_whole_frozen_manifest(calibration):
    """163 identities, one thin line each. A calibration over a subset would
    measure a density the real thin request never has."""
    assert calibration.entity_count == 163
    identity_lines = [
        line
        for line in calibration.messages.user.splitlines()
        if line.startswith("- slug: ")
    ]
    assert len(identity_lines) == 163


def test_no_excerpt_is_read_so_calibration_cannot_depend_on_the_excerpt_policy(
    calibration,
):
    """Thin lines carry no excerpt (`render_thin_line`). Asserted on the rendered
    bytes because the coupling matters: if an excerpt ever leaked into the thin
    block, the calibrated ratio would move with the excerpt policy version rather
    than with the prompt version the artifact records."""
    assert "excerpt:" not in calibration.messages.user


def test_the_input_hash_separates_the_two_halves():
    """A byte moved from the end of the system block to the start of the user
    block is a *different request*. Concatenating without a separator would give
    it the same digest — the one collision this hash exists to prevent."""
    from kdb_search.artifact import RenderedMessages

    a = cal._hash_input(RenderedMessages(system="ab", user="c"))
    b = cal._hash_input(RenderedMessages(system="a", user="bc"))
    assert a != b


def test_measure_refuses_a_nonpositive_token_count(spec, calibration):
    """A provider that returns 0 has told us nothing, and `rendered_bytes / 0`
    would either raise deep in the arithmetic or — worse — a silent 0 would be
    written as a measurement. Refused with the spend acknowledged."""
    with pytest.raises(cal.CalibrationError, match="did not surface a usable count"):
        cal.measure(spec, calibration, _response(input_tokens=0))


def test_bytes_per_token_is_bytes_over_provider_tokens(spec, calibration):
    m = cal.measure(spec, calibration, _response(input_tokens=5_000))
    assert m.bytes_per_token == round(calibration.rendered_bytes / 5_000, 4)
    assert m.counting_source == "provider_reported_usage"


def test_a_measurement_row_carries_exactly_the_fields_D5_enumerates(spec, calibration):
    """D5 lists seven fields. The row is self-describing on purpose — this
    artifact is a series, and a row that carries its own fixture version, input
    hash and prompt version can be read next to one written months later without
    consulting a header. Pinned as a set so neither a drop nor a helpful addition
    passes silently."""
    assert set(cal.measure(spec, calibration, _response()).as_json()) == {
        "counting_source",
        "fixture_version",
        "input_sha256",
        "prompt_version",
        "model_id",
        "input_tokens",
        "bytes_per_token",
    }


# --------------------------------------------------------------------------
# the ceiling
# --------------------------------------------------------------------------


def test_the_ceiling_refuses_the_fourth_attempt():
    ceiling = cal.CallCeiling()
    for model_id in ("a", "b", "c"):
        ceiling.charge(model_id)
    with pytest.raises(cal.CalibrationError, match="ceiling is spent"):
        ceiling.charge("d")


def test_the_ceiling_counts_failed_attempts_not_successes():
    """A candidate that errors was still billed for whatever the provider did.
    A ceiling counting only successes would let three failures fund three more
    calls — the exact way a 3-call budget becomes a 6-call one."""
    ceiling = cal.CallCeiling(limit=1)
    ceiling.charge("failed-anyway")
    with pytest.raises(cal.CalibrationError):
        ceiling.charge("second")


def test_a_cohort_larger_than_the_ceiling_is_refused_before_any_call(
    calibration, monkeypatch
):
    monkeypatch.setattr(
        cal, "call_model", lambda req: pytest.fail("a call was made past the ceiling")
    )
    with pytest.raises(cal.CalibrationError, match="ceiling"):
        cal.fire(calibration, cal.D4_COHORT + ("deepseek-v4-pro",))


# --------------------------------------------------------------------------
# dry run spends nothing
# --------------------------------------------------------------------------


def test_dry_run_calls_nothing(calibration, monkeypatch, capsys):
    monkeypatch.setattr(
        cal, "call_model", lambda req: pytest.fail("dry run made a provider call")
    )
    assert cal.dry_run(calibration, cal.D4_COHORT) == 0
    assert "DRY RUN" in capsys.readouterr().out


def test_dry_run_is_what_you_get_without_fire(calibration, monkeypatch, capsys):
    """The mode reached by typing the command wrong must be the free one."""
    monkeypatch.setattr(
        cal, "call_model", lambda req: pytest.fail("bare invocation made a call")
    )
    assert cal.main([]) == 0
    assert "DRY RUN" in capsys.readouterr().out


def test_dry_run_reports_the_preflight_verdict_per_candidate(calibration, capsys):
    """The owner needs to see the request fits before deciding to pay for it."""
    cal.dry_run(calibration, cal.D4_COHORT)
    out = capsys.readouterr().out
    for model_id in cal.D4_COHORT:
        assert model_id in out
    assert "fits" in out


# --------------------------------------------------------------------------
# the run: partial failure must not lose paid measurements
# --------------------------------------------------------------------------


@pytest.fixture
def artifact(tmp_path, monkeypatch) -> pathlib.Path:
    path = tmp_path / "task123_search_calibration_v1.json"
    monkeypatch.setattr(cal, "ARTIFACT_PATH", path)
    return path


def test_a_late_failure_keeps_the_earlier_paid_measurements(
    calibration, artifact, monkeypatch, capsys
):
    """The failure mode most likely to actually happen, and the one that costs
    money to recover from. Candidate 3 raising must not take candidates 1 and 2
    down with it — the spend happened at the call, not at the write."""
    calls = {"n": 0}

    def flaky(req):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("provider exploded")
        return _response(input_tokens=5_000 + calls["n"])

    monkeypatch.setattr(cal, "call_model", flaky)
    assert cal.fire(calibration, cal.D4_COHORT) == 1  # non-zero: a candidate failed
    capsys.readouterr()

    written = json.loads(artifact.read_text())
    assert [m["model_id"] for m in written["measurements"]] == list(cal.D4_COHORT[:2])
    assert written["failures"] == [
        {
            "model_id": cal.D4_COHORT[2],
            "stage": "call",
            "error": "RuntimeError: provider exploded",
        }
    ]


def test_a_clean_run_writes_every_candidate_and_returns_zero(
    calibration, artifact, monkeypatch, capsys
):
    monkeypatch.setattr(cal, "call_model", lambda req: _response(input_tokens=5_000))
    assert cal.fire(calibration, cal.D4_COHORT) == 0
    capsys.readouterr()
    written = json.loads(artifact.read_text())
    assert [m["model_id"] for m in written["measurements"]] == list(cal.D4_COHORT)
    assert written["failures"] == []
    assert written["counting_source"] == "provider_reported_usage"


def test_the_artifact_records_which_query_was_measured(
    calibration, artifact, monkeypatch, capsys
):
    """An input hash tells a later reader that the bytes differed, not what they
    were. The query is the one part of the input that is a choice rather than a
    consequence of the fixture, so it is named."""
    monkeypatch.setattr(cal, "call_model", lambda req: _response())
    cal.fire(calibration, ("gemini-3.6-flash",))
    capsys.readouterr()
    assert json.loads(artifact.read_text())["query_source"] == "empty_query_slot"


def test_a_query_file_replaces_the_empty_slot_and_is_named(tmp_path):
    query_file = tmp_path / "probe.json"
    query_file.write_text(json.dumps({"summary": "owner earnings and moats"}))
    built = cal.build_input(query_file)
    empty = cal.build_input()
    assert built.query_source == "query_file:probe.json"
    assert built.rendered_bytes > empty.rendered_bytes
    assert built.input_sha256 != empty.input_sha256


def test_a_preflight_rejection_is_recorded_without_spending_a_call(
    calibration, artifact, monkeypatch, capsys
):
    """An over-budget candidate is a `budget_exceeded` finding, not a failed
    call — the ceiling stays intact and the remaining candidates still run."""
    monkeypatch.setattr(
        budget,
        "preflight",
        lambda stage, *, rendered_bytes, spec: budget.BudgetVerdict(
            fits=False,
            stage=stage,
            estimated_input_tokens=1,
            reserved_output_tokens=1,
            context_budget_tokens=0,
        ),
    )
    monkeypatch.setattr(
        cal, "call_model", lambda req: pytest.fail("called past a failed pre-flight")
    )
    assert cal.fire(calibration, cal.D4_COHORT) == 1
    capsys.readouterr()
    written = json.loads(artifact.read_text())
    assert written["measurements"] == []
    assert [f["stage"] for f in written["failures"]] == ["preflight"] * 3


# --------------------------------------------------------------------------
# the fixture is never mutated
# --------------------------------------------------------------------------


def test_a_run_leaves_the_checksummed_fixture_byte_identical(
    calibration, artifact, monkeypatch, capsys
):
    """D5: the checksummed fixture manifest is never mutated. This harness writes
    into the same directory tree, so the claim is checked rather than assumed."""
    before = cal._fixture_fingerprint()
    monkeypatch.setattr(cal, "call_model", lambda req: _response())
    cal.fire(calibration, ("gemini-3.6-flash",))
    capsys.readouterr()
    assert cal._fixture_fingerprint() == before


def test_the_immutability_check_actually_fires(calibration, artifact, monkeypatch):
    """Proves the check above is load-bearing rather than a formality that would
    stay green whatever happened. Mutation simulated by making the fingerprint
    disagree with itself across the run — the file on disk is never touched."""
    monkeypatch.setattr(cal, "call_model", lambda req: _response())
    fingerprints = iter(({"manifest.json": "before"}, {"manifest.json": "after"}))
    monkeypatch.setattr(cal, "_fixture_fingerprint", lambda: next(fingerprints))
    with pytest.raises(cal.CalibrationError, match="never mutated"):
        cal.fire(calibration, ("gemini-3.6-flash",))


def test_the_artifact_is_a_sibling_of_the_fixture_not_a_member_of_it():
    """D5's word is *sibling*. Written inside the fixture directory it would
    invalidate `checksums.sha256` on the first run — turning "never mutated" into
    a promise the harness itself breaks."""
    assert cal.ARTIFACT_PATH.parent == cal.FIXTURE_DIR.parent
    assert cal.FIXTURE_DIR not in cal.ARTIFACT_PATH.parents


# --------------------------------------------------------------------------
# the cohort
# --------------------------------------------------------------------------


def test_every_D4_candidate_resolves_as_a_legal_selector():
    """Resolution runs through `budget.resolve_selector_route`, the same gate a
    live search uses — `tokens_lte_bytes`, `ctx_window` and the D9 output
    envelope. A candidate that could not legally be a selector must not be
    calibrated as one, or the ratio would be measured on a model the system
    cannot use."""
    for model_id in cal.D4_COHORT:
        spec = cal._resolve(model_id)
        assert spec.ctx_window is not None
        assert spec.id == model_id


def test_resolution_goes_through_the_selector_gate_not_just_the_pool(monkeypatch):
    """The check above passes for any well-formed pool entry, so on its own it
    would not notice `_resolve` dropping `resolve_selector_route` and calling
    `resolve_models_json` directly. Here the pool returns a spec that is fine as a
    model and illegal as a selector — `tokens_lte_bytes` absent, the premise the
    output allowances are proved through — and resolution must refuse it."""
    import dataclasses

    from common.model_pool import resolve_models_json

    not_a_selector = dataclasses.replace(
        resolve_models_json("gemini-3.6-flash"), tokens_lte_bytes=False
    )
    monkeypatch.setattr(cal, "resolve_models_json", lambda model_id: not_a_selector)
    with pytest.raises(Exception, match="tokens_lte_bytes"):
        cal._resolve("gemini-3.6-flash")


def test_the_cohort_is_the_three_D4_candidates():
    assert cal.D4_COHORT == ("gemini-3.6-flash", "gpt-5.4-mini", "deepseek-v4-flash")
    assert len(cal.D4_COHORT) == cal.CALL_CEILING


# --------------------------------------------------------------------------
# merging a later single-candidate run into an existing artifact
#
# The writer used to OVERWRITE. gpt-5.4-mini failed its D5 call on 2026-08-02
# (429, no credits), so the row that closes the gate has to arrive in a separate
# run — and under overwrite semantics that run would have destroyed the two
# measurements already paid for.
#
# Merging is only safe if the two runs measured the SAME THING (codex F5).
# Otherwise a later re-run silently files incomparable numbers under one header.
# --------------------------------------------------------------------------


def _row(model_id: str, tokens: int = 4_500) -> dict:
    return {
        "counting_source": cal.COUNTING_SOURCE,
        "fixture_version": "1",
        "input_sha256": "sha256:abc",
        "prompt_version": "2",
        "model_id": model_id,
        "input_tokens": tokens,
        "bytes_per_token": 3.7,
    }


def _artifact(calibration, rows, failures=(), **header) -> dict:
    doc = cal._artifact_json(calibration, [], list(failures))
    doc["measurements"] = list(rows)
    doc.update(header)
    return doc


def _write(path: pathlib.Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2) + "\n")


def test_a_later_run_KEEPS_the_rows_it_did_not_measure(tmp_path, calibration):
    """The whole point. A single-candidate re-fire must not cost the rows that
    were already paid for."""
    target = tmp_path / "cal.json"
    _write(target, _artifact(calibration, [_row("gemini-3.6-flash"), _row("deepseek-v4-flash")]))

    cal.write_artifact(calibration, [cal.Measurement(**_row("gpt-5.4-mini"))], [], path=target)

    ids = [m["model_id"] for m in json.loads(target.read_text())["measurements"]]
    assert sorted(ids) == ["deepseek-v4-flash", "gemini-3.6-flash", "gpt-5.4-mini"]


def test_a_remeasured_candidate_REPLACES_its_own_row_rather_than_doubling_it(
    tmp_path, calibration
):
    target = tmp_path / "cal.json"
    _write(target, _artifact(calibration, [_row("gemini-3.6-flash", tokens=1)]))

    cal.write_artifact(
        calibration, [cal.Measurement(**_row("gemini-3.6-flash", tokens=4_542))], [], path=target
    )

    rows = json.loads(target.read_text())["measurements"]
    assert [r["input_tokens"] for r in rows] == [4_542]


@pytest.mark.parametrize(
    "field,value",
    [
        ("rendered_bytes", 999),
        ("query_source", "query_file:something.json"),
        ("entity_count", 42),
        ("estimator_bytes_per_token_under_test", 3),
        ("counting_source", "guessed"),
    ],
)
def test_a_run_that_measured_something_ELSE_is_REFUSED_not_merged(
    tmp_path, calibration, field, value
):
    """The guard codex F5 asked for. Merging by model_id alone would file
    incomparable measurements under one header — a header that then describes
    neither of them."""
    target = tmp_path / "cal.json"
    _write(target, _artifact(calibration, [_row("gemini-3.6-flash")], **{field: value}))

    with pytest.raises(cal.CalibrationArtifactMismatch, match=field):
        cal.write_artifact(
            calibration, [cal.Measurement(**_row("gpt-5.4-mini"))], [], path=target
        )


def test_the_refusal_leaves_the_existing_artifact_UNTOUCHED(tmp_path, calibration):
    """A refusal that had already truncated the file would destroy exactly what
    the guard exists to protect."""
    target = tmp_path / "cal.json"
    _write(target, _artifact(calibration, [_row("gemini-3.6-flash")], rendered_bytes=999))
    before = target.read_text()

    with pytest.raises(cal.CalibrationArtifactMismatch):
        cal.write_artifact(
            calibration, [cal.Measurement(**_row("gpt-5.4-mini"))], [], path=target
        )

    assert target.read_text() == before


def test_a_row_that_now_SUCCEEDS_clears_its_earlier_failure(tmp_path, calibration):
    """gpt-5.4-mini's 429 must not sit in the artifact beside its own successful
    measurement, reading as though the candidate both failed and succeeded."""
    target = tmp_path / "cal.json"
    _write(
        target,
        _artifact(
            calibration,
            [_row("gemini-3.6-flash")],
            failures=[{"model_id": "gpt-5.4-mini", "stage": "call", "error": "429"}],
        ),
    )

    cal.write_artifact(calibration, [cal.Measurement(**_row("gpt-5.4-mini"))], [], path=target)

    doc = json.loads(target.read_text())
    assert doc["failures"] == []
    assert {m["model_id"] for m in doc["measurements"]} == {"gemini-3.6-flash", "gpt-5.4-mini"}


def test_writing_where_no_artifact_exists_is_still_a_plain_write(tmp_path, calibration):
    target = tmp_path / "fresh.json"
    cal.write_artifact(calibration, [cal.Measurement(**_row("gemini-3.6-flash"))], [], path=target)
    assert [m["model_id"] for m in json.loads(target.read_text())["measurements"]] == [
        "gemini-3.6-flash"
    ]
