"""Eval harness for the 15 ratified O1 hypothesis-promotion probes (#87.1 v1).

This test module loads each YAML probe under `scenarios/o1/`, builds the
typed `CandidateEnvelope` + `EvalConfig` from the YAML, dispatches to
`op_1_promote.run`, and (in GREEN phase) diffs the resulting graph state
against `expected_post_state` and asserts every entry in
`exercised_criteria`.

RED phase contract (current — step [C] of the O1 kickoff plan):
    Every probe must reach `op_1_promote.run` and fail with a clear
    `NotImplementedError`. That proves the harness:
      (1) discovers all 15 probes,
      (2) parses each YAML cleanly,
      (3) constructs the dataclass-typed candidate + eval_config,
      (4) dispatches into the op_1 entry point.

GREEN-phase TODOs are tagged inline with `# TODO[GREEN]:`. The
NotImplementedError-catching `with pytest.raises(...)` block will be
flipped to actual post-state diffs in steps [E]–[G].
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest
import yaml

from graphdb_kdb.core.belief_classifier import (
    CandidateEnvelope,
    ConfidenceValue,
    DoxasticFingerprint,
    EvalConfig,
    Evidence,
)
from graphdb_kdb.ops import op_1_promote


SCENARIOS_DIR = Path(__file__).parent.parent.parent / "tests" / "eval" / "promotion" / "scenarios" / "o1"
# pytest discovery runs from repo root; the path relative to __file__ above is brittle if
# the package is installed elsewhere — recompute robustly from the test file's own location.
SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios" / "o1"


def _discover_o1_probes() -> list[Path]:
    """Return the sorted list of O1 probe YAML paths."""
    return sorted(SCENARIOS_DIR.glob("s*.yaml"))


# ---------- YAML → dataclass helpers ----------

def _filter_dict_to_fields(cls, d: dict[str, Any]) -> dict[str, Any]:
    """Drop dict keys that aren't fields on `cls` (defensive against YAML extras)."""
    names = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in d.items() if k in names}


def _build_confidence(d: dict[str, Any] | None) -> ConfidenceValue | None:
    if d is None:
        return None
    return ConfidenceValue(**_filter_dict_to_fields(ConfidenceValue, d))


def _build_evidence(d: dict[str, Any]) -> Evidence:
    return Evidence(
        source_id=d["source_id"],
        quoted_text=d.get("quoted_text", ""),
        confidence=_build_confidence(d.get("confidence")),
    )


_CANDIDATE_KNOWN_FIELDS = {
    "candidate_id", "subject_slug", "predicate_class_raw", "predicate_class_canonical",
    "predicate_scope_slugs", "polarity", "modality", "counterpart_status",
    "relation_kind", "refines_truth_conditions", "counterpart_claim_id",
    "counterpart_links_to_ref", "doxastic_fingerprint", "confidence", "evidence",
}


def _build_candidate(d: dict[str, Any]) -> CandidateEnvelope:
    """Construct a CandidateEnvelope from a YAML `input.candidate` block.

    Tolerates #87.1 v1 spike-vs-expansion schema variance:
      * modality omitted (defaults to "declarative")
      * counterpart_links_to_ref omitted on spike scenarios (defaults to None)
      * relation_kind / counterpart_claim_id null-or-omitted
      * probe-specific extras (object_slug, object_qualifier,
        analysis_time_classification) captured into `extras` for later use
        in [E]/[F].
    """
    fingerprint_d = d["doxastic_fingerprint"]
    extras = {k: v for k, v in d.items() if k not in _CANDIDATE_KNOWN_FIELDS}
    return CandidateEnvelope(
        candidate_id=d["candidate_id"],
        subject_slug=d["subject_slug"],
        predicate_class_raw=d["predicate_class_raw"],
        predicate_class_canonical=d["predicate_class_canonical"],
        predicate_scope_slugs=list(d["predicate_scope_slugs"]),
        polarity=d["polarity"],
        modality=d.get("modality", "declarative"),
        counterpart_status=d["counterpart_status"],
        relation_kind=d.get("relation_kind"),
        refines_truth_conditions=d["refines_truth_conditions"],
        counterpart_claim_id=d.get("counterpart_claim_id"),
        counterpart_links_to_ref=d.get("counterpart_links_to_ref"),
        doxastic_fingerprint=DoxasticFingerprint(
            state_hash=fingerprint_d["state_hash"],
            classifier_input_scope=list(fingerprint_d.get("classifier_input_scope", [])),
        ),
        confidence=_build_confidence(d["confidence"]),
        evidence=[_build_evidence(e) for e in d.get("evidence", [])],
        extras=extras,
    )


def _build_eval_config(d: dict[str, Any]) -> EvalConfig:
    return EvalConfig(**_filter_dict_to_fields(EvalConfig, d))


# ---------- Parametrized test ----------

PROBES = _discover_o1_probes()

assert len(PROBES) == 15, (
    f"Expected 15 O1 probes under {SCENARIOS_DIR}, found {len(PROBES)}. "
    "Re-run /tmp/extract_o1_probes_v2.py-style extraction from "
    "docs/task87.1-probe-set-curation-blueprint.md."
)


@pytest.mark.parametrize("probe_path", PROBES, ids=lambda p: p.stem)
def test_o1_probe_red_phase(probe_path: Path):
    """RED phase: every probe must dispatch into op_1_promote.run and fail there.

    This validates:
        - YAML parses cleanly
        - input.candidate constructs as a CandidateEnvelope (typed)
        - eval_config constructs as an EvalConfig (typed)
        - op_1_promote.run is reachable from the harness
        - The stub raises NotImplementedError (skeleton contract)

    The `with pytest.raises(NotImplementedError):` guard is flipped in
    step [G]: after [D]–[F] land, the harness will diff
    `expected_post_state` against the live graph and assert every
    `exercised_criteria` entry.
    """
    probe = yaml.safe_load(probe_path.read_text(encoding="utf-8"))

    # Sanity: probe targets O1 (gates against accidental cross-op pollution).
    assert probe["op_under_test"] == "O1", (
        f"{probe_path.name}: op_under_test={probe['op_under_test']!r} — expected 'O1'"
    )

    # S19 uses the sequential-multi-candidate shape (`candidates_sequential`).
    # For RED phase, dispatching the first candidate is enough to exercise the
    # wiring — GREEN phase ([E]/[F]) will loop the full sequence with state
    # carry-over per probe contract.
    input_block = probe["input"]
    if "candidates_sequential" in input_block:
        candidate_d = input_block["candidates_sequential"][0]["candidate"]
    else:
        candidate_d = input_block["candidate"]
    candidate = _build_candidate(candidate_d)
    eval_config = _build_eval_config(probe["eval_config"])

    # TODO[GREEN]: replace this stub graph_state with a fresh Kuzu test db
    # populated from probe['pre_state']. For RED phase, None is fine — the
    # stub raises NotImplementedError before touching it.
    graph_state = None

    with pytest.raises(NotImplementedError) as exc_info:
        op_1_promote.run(candidate, eval_config, graph_state)

    # Quality check: the stub message should point at the kickoff-plan
    # step that will satisfy the contract. Helps future readers follow
    # the implementation lineage from a failing test.
    assert "kickoff plan" in str(exc_info.value).lower(), (
        f"{probe_path.name}: NotImplementedError message should reference the "
        f"kickoff plan; got: {exc_info.value!r}"
    )


def test_o1_harness_discovers_all_ratified_probes():
    """The harness must see every ratified O1 scenario.

    #87.1 v1 ratified 15 O1 probes (S1, S2, S5–S9, S12–S19). This test
    locks the count so a missing or extra extraction is caught early.
    """
    assert len(PROBES) == 15
    stems = {p.stem.split("_", 1)[0] for p in PROBES}
    expected_stems = {f"s{n:02d}" for n in (1, 2, 5, 6, 7, 8, 9, 12, 13, 14, 15, 16, 17, 18, 19)}
    assert stems == expected_stems, f"missing: {expected_stems - stems}; extra: {stems - expected_stems}"
