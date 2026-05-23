"""O1 — Hypothesis Promotion Pipeline.

The mutation boundary that mediates every Analysis → Learn state transition
per Task #83 (Promotion Contract) + Task #84 (Belief Revision). Receives a
candidate envelope, re-runs the shared deterministic classifier
authoritatively, computes drift signals against the candidate's hint,
consults the D-83/84-8 Part D drift action matrix to pick a disposition,
and (for auto-promoting dispositions) mutates the graph per the
D-83/84-2 7-cell action table.

Three classes of post-state outcome:
    * **Claim-creating cells** (5): `reinforces` over threshold N,
      `contradicts`, `qualifies_or_extends` with refines_truth=true,
      `supersedes`, and a fallback path. Writes Claim nodes + EVIDENCES +
      Claim-Claim edges (CONTRADICTS / SUPERSEDES / QUALIFIES).
    * **Topology-only cells** (2): `no_counterpart`, `orthogonal`, and
      `qualifies_or_extends` with refines_truth=false. Writes LINKS_TO +
      SUPPORTS only — zero Claim writes.
    * **Human-review dispositions**: zero graph mutation; audit-only record.

(Implementation lives in steps [E] – [G] of the kickoff plan.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from graphdb_kdb.core.belief_classifier import (
    CandidateEnvelope,
    ClassificationResult,
    EvalConfig,
)


# ---------- O1 output types ----------

@dataclass(frozen=True)
class PromotionAudit:
    """The audit record O1 emits for every candidate it processes.

    Mirrors the `promotion_audit` block in #87.1 probe `expected_post_state`.
    For human_review dispositions this is the *only* artifact (no graph
    mutation occurred). For auto_promote / auto_promote_with_note this
    accompanies the mutations.
    """
    candidate_id: str
    fingerprint_drift: bool
    classification_drift: bool
    drift_explanation: Optional[str]
    disposition: str   # 'auto_promote' | 'auto_promote_with_note' | 'investigate' | 'human_review'
    counterpart_resolution_path: Optional[str]
    classified_at: str  # ISO-8601 datetime with offset — equals eval_clock at probe time


@dataclass(frozen=True)
class PromotionResult:
    """O1's return value: the audit + a flag for whether writes occurred.

    `mutations_applied=False` for investigate / human_review dispositions
    (per F-O1-5 unauthorized-mutation guard). Callers query the live graph
    for actual post-state — this is the audit-side record only.
    """
    audit: PromotionAudit
    mutations_applied: bool
    classification: ClassificationResult


# ---------- Entry point ----------

def run(candidate: CandidateEnvelope, eval_config: EvalConfig, graph_state: Any) -> PromotionResult:
    """Process one candidate through the O1 boundary.

    Steps (per kickoff plan):
        [D] Re-classify via `belief_classifier.classify` (authoritative)
        [F] Compute drift signals + disposition from D-83/84-8 Part D matrix
        [E] If disposition ∈ {auto_promote, auto_promote_with_note}: mutate
            graph per D-83/84-2 action table cell
        [G] Run post-mutation invariant check via verifier.py

    NOTE: Skeleton stub. RED phase expects every probe to fail here with a
    clear NotImplementedError surface — proves the harness wiring is
    correctly dispatching to this function before logic lands.
    """
    raise NotImplementedError(
        "op_1_promote.run is a skeleton stub; steps [D]–[G] of the O1 "
        "kickoff plan implement classify → drift → mutate → verify."
    )
