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
class AnalysisTimeClassification:
    """The classification that Analysis recorded when the candidate was emitted.

    O1 re-classifies authoritatively at promotion time; mismatch between
    this recorded hint and the authoritative result = classification_drift
    per D-83/84-8 Part B. Carries only the three mutation-relevant fields
    (not the full ClassificationResult, which is the authoritative output).
    """
    counterpart_status: str
    relation_kind: Optional[str]
    refines_truth_conditions: bool


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
    # First-class fields (promoted from extras 2026-05-23 — #11 v1.1
    # normalization). Used by [E] (object_slug → Claim.object_slugs cell
    # for the `supersedes` action) and [F] (analysis_time_classification →
    # classification_drift computation per D-83/84-8 Part B).
    object_slug: Optional[str] = None
    object_qualifier: Optional[str] = None
    analysis_time_classification: Optional[AnalysisTimeClassification] = None
    # Reserved for any future probe-specific fields not yet promoted.
    extras: dict = field(default_factory=dict)


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

def _scope_key(predicate_scope_slugs: list[str]) -> str:
    """Deterministic scope serialization (D-83/84-6 F1): sort + join with `+`,
    empty set → `<none>` sentinel."""
    if not predicate_scope_slugs:
        return "<none>"
    return "+".join(sorted(predicate_scope_slugs))


def _state_hash(scope_lines: list[str]) -> str:
    """Deterministic SHA256 over the classifier_input_scope list."""
    import hashlib
    h = hashlib.sha256()
    for line in scope_lines:
        h.update(line.encode("utf-8"))
        h.update(b"\n")
    return f"sha256:{h.hexdigest()[:32]}"  # 16-byte prefix for compactness


def classify(
    candidate: CandidateEnvelope, eval_config: EvalConfig, conn: Any
) -> ClassificationResult:
    """Deterministically classify a candidate against live graph state.

    Implements the D-83/84-2 3-way counterpart enum + relation_kind
    derivation. Reads only:
      * Existence of subject Entity in the graph
      * Active Claims in the same family
        (subject_slug, predicate_class_canonical, predicate_scope_slugs)
        excluding retracted; superseded handled per P-O1-8.

    Output drives O1's dispatch into the D-83/84-2 action table per [E].
    Pure function: identical (candidate, conn-state, eval_config) →
    identical ClassificationResult (P-O1-1 determinism).

    `conn` is a Kuzu Connection (or anything with .execute returning a
    result-set with .has_next() / .get_next()). The classifier reads via
    Cypher; the harness passes a populated test connection.

    Scope coverage (LINKS_TO-implicit-counterpart for "reinforces"
    threshold-crossing cases per blueprint §6.7 Tier-2/Tier-3 evidence
    reconstruction) is **NOT** implemented in this pass — probes that
    rely on it (S05-S07, S16, S19's-first-candidate) will report
    classification_drift in [F] because the authoritative classifier
    won't see the LINKS_TO-only counterparts. Filed as follow-up beyond
    the current GREEN scope.
    """
    pred = candidate.predicate_class_canonical
    scope = _scope_key(candidate.predicate_scope_slugs)
    family_id = f"{candidate.subject_slug}__{pred}__{scope}"
    context_key = f"{pred}__{scope}"

    # 1. Subject existence check.
    entity_exists = False
    r = conn.execute(
        "MATCH (e:Entity {slug: $slug}) RETURN COUNT(*)",
        {"slug": candidate.subject_slug},
    )
    if r.has_next():
        entity_exists = int(r.get_next()[0]) > 0

    # 2. Find active counterpart Claims.
    #
    # Two lookup paths:
    #   (a) Candidate carries an explicit `counterpart_claim_id` — direct
    #       lookup. Honors probes whose corpus modeling diverges from
    #       implementation's family_id construction (e.g., S08's
    #       `__apple` family vs the spec's full-scope family).
    #   (b) No explicit pointer — search by computed family_id.
    counterpart_claims: list[dict] = []
    retracted_family_id: Optional[str] = None
    if candidate.counterpart_claim_id is not None:
        r = conn.execute(
            """
            MATCH (c:Claim {claim_id: $cid})
            RETURN c.claim_id, c.polarity, c.state, c.version,
                   c.object_slugs, c.condition_text, c.claim_family_id
            """,
            {"cid": candidate.counterpart_claim_id},
        )
        while r.has_next():
            row = r.get_next()
            entry = {
                "claim_id": row[0], "polarity": row[1], "state": row[2],
                "version": row[3],
                "object_slugs": list(row[4]) if row[4] is not None else [],
                "condition_text": row[5] or "",
            }
            if entry["state"] == "retracted":
                # P-O1-8 OQ-18: walk to active sibling in same family.
                retracted_family_id = row[6]
            else:
                counterpart_claims.append(entry)
        retracted_entry: Optional[dict] = None
        if retracted_family_id is not None:
            # Look up the retracted Claim's full record for fallback use.
            rret = conn.execute(
                """
                MATCH (c:Claim {claim_id: $cid})
                RETURN c.claim_id, c.polarity, c.state, c.version,
                       c.object_slugs, c.condition_text
                """,
                {"cid": candidate.counterpart_claim_id},
            )
            if rret.has_next():
                row = rret.get_next()
                retracted_entry = {
                    "claim_id": row[0], "polarity": row[1], "state": row[2],
                    "version": row[3],
                    "object_slugs": list(row[4]) if row[4] is not None else [],
                    "condition_text": row[5] or "",
                }
            # Walk to active sibling (S17 path per P-O1-8 default branch A).
            r2 = conn.execute(
                """
                MATCH (c:Claim {claim_family_id: $fid})
                WHERE c.state = 'active'
                RETURN c.claim_id, c.polarity, c.state, c.version,
                       c.object_slugs, c.condition_text
                ORDER BY c.version DESC
                """,
                {"fid": retracted_family_id},
            )
            while r2.has_next():
                row = r2.get_next()
                counterpart_claims.append({
                    "claim_id": row[0], "polarity": row[1], "state": row[2],
                    "version": row[3],
                    "object_slugs": list(row[4]) if row[4] is not None else [],
                    "condition_text": row[5] or "",
                })
            # No active sibling → per P-O1-8 OQ-18 default branch B
            # (ratified via #87.1 probe S18), do NOT engage the retracted
            # member as a counterpart for relation_kind dispatch. Fall
            # through with `counterpart_claims` empty so the no_counterpart
            # path fires below. `retracted_family_id` remains set, which
            # the no_counterpart branch consults to short-circuit the
            # orthogonal-vs-no_counterpart distinction.
    else:
        r = conn.execute(
            """
            MATCH (c:Claim {claim_family_id: $fid})
            WHERE c.state IN ['active', 'superseded']
            RETURN c.claim_id, c.polarity, c.state, c.version,
                   c.object_slugs, c.condition_text
            ORDER BY c.version DESC
            """,
            {"fid": family_id},
        )
        while r.has_next():
            row = r.get_next()
            counterpart_claims.append({
                "claim_id": row[0], "polarity": row[1], "state": row[2],
                "version": row[3],
                "object_slugs": list(row[4]) if row[4] is not None else [],
                "condition_text": row[5] or "",
            })

    scope_lines = [
        "subject_existence_check",
        f"context_key: {context_key}",
        f"counterpart_count: {len(counterpart_claims)}",
    ]

    # 3. Counterpart-status dispatch (D-83/84-2).
    # Treat both active and (when no active option exists) retracted as
    # engageable counterparts; pure 'superseded' is engageable too.
    active_counterparts = [c for c in counterpart_claims if c["state"] in {"active", "retracted", "superseded"}]

    # 3a. LINKS_TO-implicit-counterpart fallback. Distinct from blueprint
    # §6.7 Tier-1/2/3 provenance reconstruction (which lives in the
    # mutator). When no Claim exists in the family AND the candidate
    # carries `counterpart_links_to_ref` pointing to a real LINKS_TO
    # edge in the graph, treat that edge as the implicit counterpart for
    # relation_kind dispatch. Polarity / predicate-class fidelity on
    # LINKS_TO is currently trust-the-hint: schema v2.2's LINKS_TO carries
    # only (run_id, created_at) per graphdb_kdb/schema.py:115-119, so we
    # can't filter by predicate or polarity at this layer. Tracked as OQ
    # alongside the verifier-strictness arc.
    #
    # Gated off when `retracted_family_id` is set: per OQ-18 branch B
    # (S18 path), retracted-no-sibling takes precedence — the candidate
    # gets a fresh start as `no_counterpart`, ignoring any LINKS_TO
    # history that may coexist with the retracted Claim.
    ref = candidate.counterpart_links_to_ref
    if (
        not active_counterparts
        and retracted_family_id is None
        and isinstance(ref, dict)
        and ref.get("from_slug")
        and ref.get("to_slug")
    ):
        rl = conn.execute(
            "MATCH (a:Entity {slug: $f})-[l:LINKS_TO]->(b:Entity {slug: $t}) RETURN COUNT(l)",
            {"f": ref["from_slug"], "t": ref["to_slug"]},
        )
        n_links = int(rl.get_next()[0]) if rl.has_next() else 0
        if n_links > 0:
            scope_lines.append(f"links_to_corroboration_count: {n_links}")
            return ClassificationResult(
                counterpart_status="candidate_counterpart_found",
                relation_kind="reinforces",
                refines_truth_conditions=candidate.refines_truth_conditions,
                counterpart_claim_id=None,
                counterpart_links_to_ref=ref,
                classifier_input_scope=scope_lines,
                state_hash=_state_hash(scope_lines),
            )

    if not active_counterparts:
        # Distinguish no_counterpart vs orthogonal per D-83/84-2:
        #   * no_counterpart — nothing engaging the candidate. Either the
        #     subject doesn't exist, or it exists but has no claims about
        #     it at all in any family.
        #   * orthogonal — subject exists with claims in OTHER families,
        #     but none in this family.
        #   * retracted-counterpart-no-active-sibling — explicit
        #     no_counterpart per P-O1-8 OQ-18 default branch B.
        if retracted_family_id is not None:
            cs_result = "no_counterpart"
        elif entity_exists:
            # Check if subject has any other claims (in different families).
            r2 = conn.execute(
                "MATCH (c:Claim)-[:ABOUT]->(e:Entity {slug: $slug}) "
                "WHERE c.state = 'active' RETURN COUNT(*)",
                {"slug": candidate.subject_slug},
            )
            other_claims = int(r2.get_next()[0]) if r2.has_next() else 0
            cs_result = "orthogonal" if other_claims > 0 else "no_counterpart"
        else:
            cs_result = "no_counterpart"
        return ClassificationResult(
            counterpart_status=cs_result,
            relation_kind=None,
            refines_truth_conditions=candidate.refines_truth_conditions,
            counterpart_claim_id=None,
            counterpart_links_to_ref=None,
            classifier_input_scope=scope_lines,
            state_hash=_state_hash(scope_lines),
        )

    # 4. candidate_counterpart_found — derive relation_kind structurally.
    counterpart = active_counterparts[0]  # highest version
    counterpart_claim_id = counterpart["claim_id"]

    if counterpart["polarity"] != candidate.polarity:
        relation_kind = "contradicts"
    elif candidate.refines_truth_conditions:
        relation_kind = "qualifies_or_extends"
    else:
        # Same polarity, no truth refinement — three structural sub-cases
        # per D-83/84-2 default action table:
        #   * different object_slug → qualifies_or_extends (extending the
        #     entity surface; refines_truth=false routes to topology-only)
        #   * same object_slug + different qualifier → supersedes (state
        #     transition on the same axis, e.g. stake percentage change)
        #   * same object_slug + same qualifier → reinforces (additional
        #     evidence for an identical assertion)
        cand_qual = candidate.object_qualifier or ""
        cp_qual = counterpart["condition_text"]
        cand_obj_in_cp = (
            candidate.object_slug is None
            or candidate.object_slug in counterpart["object_slugs"]
        )
        if not cand_obj_in_cp:
            relation_kind = "qualifies_or_extends"
        elif cand_qual == cp_qual:
            relation_kind = "reinforces"
        else:
            relation_kind = "supersedes"

    return ClassificationResult(
        counterpart_status="candidate_counterpart_found",
        relation_kind=relation_kind,
        refines_truth_conditions=candidate.refines_truth_conditions,
        counterpart_claim_id=counterpart_claim_id,
        counterpart_links_to_ref=None,
        classifier_input_scope=scope_lines,
        state_hash=_state_hash(scope_lines),
    )
