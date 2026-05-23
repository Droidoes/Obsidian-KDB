"""Stateless deterministic classifier for candidate envelopes.

Per Task #83/#84 D-83/84-3 + D-83/84-4 Option 2: one shared, deterministic
classifier is the single source of truth for both Analysis-time hint
classification and promotion-time authoritative classification. **No LLM
at classification time** — the classifier reads only the candidate
envelope + live graph state and dispatches according to the D-83/84-2
action table.

Canonical 3-way counterpart enum (per #83/#84 ratified vocabulary):
    no_counterpart            — no existing edge or Claim engages the candidate
    candidate_counterpart_found — existing edge or Claim engages the candidate
    orthogonal                — entities present, no claims engaged

When counterpart_status == candidate_counterpart_found, relation_kind is one of:
    reinforces · contradicts · qualifies_or_extends · supersedes

(The classifier's output drives O1's dispatch into the D-83/84-2 action
table. Implementation lives in step [D] of the kickoff plan.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------- Shared value objects (input shape from #87.1 probe YAML) ----------

@dataclass(frozen=True)
class ConfidenceValue:
    """Confidence reading on a candidate or evidence item.

    `bucket` is the discretized rating (low|medium|high); `score` is the
    numeric score per the confidence_map (D-83/84 §4 confidence pipeline).
    """
    bucket: str
    score: float
    score_source: Optional[str] = None
    map_version: Optional[str] = None


@dataclass(frozen=True)
class Evidence:
    """One piece of supporting evidence attached to a candidate.

    `confidence` defaults to None — late-batch expansion probes
    (S15+) omit per-evidence confidence and rely on the candidate-level
    confidence + aggregation formula. Pending #87.1 v1.1 normalization.
    """
    source_id: str
    quoted_text: str
    confidence: Optional[ConfidenceValue] = None


@dataclass(frozen=True)
class DoxasticFingerprint:
    """Audit-trail fingerprint of the state the classifier saw.

    `state_hash` is the deterministic hash of the classifier's input scope;
    `classifier_input_scope` lists the named graph-state slices the
    classifier consulted (D-83/84-8 Part A). Late-batch expansion probes
    (S08, S15–S19) omit the scope list — defaulted to empty list here
    pending #87.1 v1.1 corpus normalization.
    """
    state_hash: str
    classifier_input_scope: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CandidateEnvelope:
    """The candidate proposed by Analysis for promotion through the O1 boundary.

    Pre-classified by an Analysis-time hint; the field values here are the
    HINT — O1 re-runs the classifier authoritatively before mutating.
    Mismatch between hint and authoritative result = classification_drift
    (D-83/84-8 Part B + Part D).
    """
    candidate_id: str
    subject_slug: str
    predicate_class_raw: str
    predicate_class_canonical: str
    predicate_scope_slugs: list[str]
    polarity: str        # 'affirms' | 'denies'
    counterpart_status: str  # canonical 3-way enum (see module docstring)
    refines_truth_conditions: bool
    doxastic_fingerprint: DoxasticFingerprint
    confidence: ConfidenceValue
    evidence: list[Evidence]
    # Below: spike-vs-expansion schema variance accommodation — defaulted
    # so probes that omit these (#87.1 v1.0 spike scenarios) construct
    # cleanly. Future v1.1 corpus normalization pass should align all
    # probes on the full schema.
    modality: str = "declarative"
    relation_kind: Optional[str] = None
    counterpart_claim_id: Optional[str] = None
    counterpart_links_to_ref: Optional[str] = None   # O2 dispatch signal per memory `project_task87_87_1_ratified`
    extras: dict = field(default_factory=dict)       # holds probe-specific fields not in v1 universal schema (object_slug, object_qualifier, analysis_time_classification, etc.)


@dataclass(frozen=True)
class EvalConfig:
    """Per-call configuration pinned by the eval harness.

    Mirrors #87 v2 §7.2 `eval_config` block. Deterministic dispatch
    depends on `eval_clock`, `corroboration_threshold_n`,
    `confidence_decay_tau_days`, etc. — pin these per-probe so probe
    outputs are reproducible regardless of wall-clock or default tuning.
    """
    eval_clock: str             # ISO-8601 datetime with offset
    corroboration_threshold_n: int
    confidence_decay_tau_days: float
    default_read_confidence_threshold_t: float
    confidence_map_version: str
    read_mode: str = "default"  # 'default' | 'aliased' | ... (O3-specific; O1 uses 'default'; defaulted because O1-only expansion probes omit it)


# ---------- Classifier output ----------

@dataclass(frozen=True)
class ClassificationResult:
    """Authoritative classification produced by `classify()`.

    All four mutation-relevant fields (counterpart_status / relation_kind /
    refines_truth_conditions / counterpart_claim_id) are emitted here. O1
    compares this against the candidate's hint to detect classification
    drift and dispatch per the D-83/84-2 action table.
    """
    counterpart_status: str
    relation_kind: Optional[str]
    refines_truth_conditions: bool
    counterpart_claim_id: Optional[str]
    counterpart_links_to_ref: Optional[str]
    classifier_input_scope: list[str]
    state_hash: str


# ---------- Stateless classify function ----------

def classify(candidate: CandidateEnvelope, eval_config: EvalConfig, graph_state: Any) -> ClassificationResult:
    """Deterministically classify a candidate against live graph state.

    Reads only the candidate envelope + graph state slices named in
    `classifier_input_scope`. Pure function: identical inputs → identical
    output (P-O1-1 determinism criterion).

    `graph_state` is held abstract here; the harness will pass either a
    live Kuzu connection wrapper or a fixture-built state object.

    NOTE: Skeleton stub — step [D] of the O1 kickoff plan implements the
    actual D-83/84-2 dispatch logic. Tests against this stub should fail
    in the RED phase with a clear NotImplementedError surface.
    """
    raise NotImplementedError(
        "belief_classifier.classify is a skeleton stub; step [D] of the O1 "
        "kickoff plan implements the D-83/84-2 action-table dispatch."
    )
