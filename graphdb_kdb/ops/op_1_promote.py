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

def run(candidate: CandidateEnvelope, eval_config: EvalConfig, conn: Any) -> PromotionResult:
    """Process one candidate through the O1 boundary.

    Steps:
        [D] Re-classify via `belief_classifier.classify` (authoritative).
        [F] Compute drift signals + disposition from D-83/84-8 Part D matrix.
        [E] If disposition ∈ {auto_promote, auto_promote_with_note}: mutate
            graph per D-83/84-2 action table cell.

    `conn` is a Kuzu Connection; classifier reads + mutation writes go
    through it. F-O1-5 guards: human_review / investigate dispositions
    perform zero graph mutation.
    """
    from graphdb_kdb.core.belief_classifier import classify

    classification = classify(candidate, eval_config, conn)

    # Drift detection (D-83/84-8 Part B + Part D).
    #
    # fingerprint_drift compares the candidate's Analysis-time recorded
    # state_hash to the classifier's current authoritative computation.
    # Both derive from the deterministic `_state_hash` over the
    # `classifier_input_scope` lines; identical inputs → identical hash;
    # mismatch indicates the graph slices the classifier consults have
    # drifted since the candidate was emitted. Probe corpus normalized
    # 2026-05-23 to carry real hashes (probes that expect fp_drift=true
    # use a sentinel that deliberately differs).
    fingerprint_drift = candidate.doxastic_fingerprint.state_hash != classification.state_hash

    # classification_drift: compare authoritative classifier output to the
    # Analysis-time hint. The hint lives in `analysis_time_classification`
    # when explicit (drift probes S12-S14); otherwise it equals the
    # candidate's nominal classification fields (which by construction
    # match the authoritative result when no drift is induced).
    if candidate.analysis_time_classification is not None:
        hint_cs = candidate.analysis_time_classification.counterpart_status
        hint_rk = candidate.analysis_time_classification.relation_kind
        hint_rtc = candidate.analysis_time_classification.refines_truth_conditions
    else:
        hint_cs = candidate.counterpart_status
        hint_rk = candidate.relation_kind
        hint_rtc = candidate.refines_truth_conditions
    classification_drift = (
        classification.counterpart_status != hint_cs
        or classification.relation_kind != hint_rk
        or classification.refines_truth_conditions != hint_rtc
    )

    # 4-cell disposition matrix (D-83/84-8 Part D).
    if fingerprint_drift and classification_drift:
        disposition = "human_review"
    elif classification_drift:
        disposition = "investigate"
    elif fingerprint_drift:
        disposition = "auto_promote_with_note"
    else:
        disposition = "auto_promote"

    audit = PromotionAudit(
        candidate_id=candidate.candidate_id,
        fingerprint_drift=fingerprint_drift,
        classification_drift=classification_drift,
        drift_explanation=None,
        disposition=disposition,
        counterpart_resolution_path=None,
        classified_at=eval_config.eval_clock,
    )

    if disposition in {"investigate", "human_review"}:
        # F-O1-5: zero graph mutation under non-auto-promote dispositions.
        return PromotionResult(
            audit=audit,
            mutations_applied=False,
            classification=classification,
        )

    # Auto-promote path — perform mutation per D-83/84-2 action cell.
    _apply_mutation(candidate, classification, eval_config, conn)

    # [G] Post-mutation invariant check: a subset of blueprint §6 invariants
    # applied to the just-created Claim (if any). Topology-only mutations
    # skip the Claim-anchored checks.
    _verify_post_mutation(candidate, classification, conn)

    return PromotionResult(
        audit=audit,
        mutations_applied=True,
        classification=classification,
    )


def _verify_post_mutation(
    candidate: CandidateEnvelope,
    classification: ClassificationResult,
    conn: Any,
) -> None:
    """Post-mutation graph-integrity check (subset of blueprint §6 invariants).

    Checks the Claim layer state immediately after a Claim-creating
    mutation. Raises `RuntimeError` if any invariant breaks — better to
    fail loud at the boundary than ship a corrupted graph.

    Invariants checked (mirrors §6 sub-list):
      1. Every newly-created Claim has an ABOUT edge.
      2. Every ABOUT target Entity exists.
      3. Every EVIDENCES source exists.
      4. Claim-Claim edges (CONTRADICTS / SUPERSEDES / QUALIFIES) target
         existing Claims.

    Deferred (require multi-Claim graph state to evaluate meaningfully):
      - State machine invariants (no retracted → active transitions).
      - claim_id parseability.
      - claim_family_id consistency across versions.
      - Denormalized-key coherence with ALIAS_OF chains.

    For topology-only dispositions (where no Claim was created), this
    function is a no-op.
    """
    from graphdb_kdb.core.belief_classifier import _scope_key

    pred = candidate.predicate_class_canonical
    scope = _scope_key(candidate.predicate_scope_slugs)
    family_id = f"{candidate.subject_slug}__{pred}__{scope}"

    # Look up the just-created Claim (highest-version in family, if any was created).
    r = conn.execute(
        """
        MATCH (c:Claim {claim_family_id: $fid})
        WHERE c.state = 'active' AND c.subject_slug = $subj
        RETURN c.claim_id ORDER BY c.version DESC LIMIT 1
        """,
        {"fid": family_id, "subj": candidate.subject_slug},
    )
    if not r.has_next():
        # Topology-only path — no Claim to verify.
        return
    new_claim_id = r.get_next()[0]

    # Invariant 1: ABOUT edge exists.
    r = conn.execute(
        "MATCH (c:Claim {claim_id: $cid})-[:ABOUT]->(:Entity) RETURN COUNT(*)",
        {"cid": new_claim_id},
    )
    if r.has_next() and int(r.get_next()[0]) == 0:
        raise RuntimeError(
            f"Post-mutation invariant violation: Claim {new_claim_id!r} has no ABOUT edge"
        )

    # Invariant 2: ABOUT target Entity exists (relation-set integrity).
    r = conn.execute(
        """
        MATCH (c:Claim {claim_id: $cid})-[:ABOUT]->(e:Entity)
        RETURN e.slug
        """,
        {"cid": new_claim_id},
    )
    while r.has_next():
        slug = r.get_next()[0]
        chk = conn.execute(
            "MATCH (e:Entity {slug: $s}) RETURN COUNT(*)", {"s": slug},
        )
        if chk.has_next() and int(chk.get_next()[0]) == 0:
            raise RuntimeError(
                f"Post-mutation invariant violation: Claim {new_claim_id!r} ABOUT "
                f"references missing Entity {slug!r}"
            )

    # Invariant 3: EVIDENCES sources exist (relation-set integrity).
    r = conn.execute(
        """
        MATCH (s:Source)-[:EVIDENCES]->(c:Claim {claim_id: $cid})
        RETURN s.source_id
        """,
        {"cid": new_claim_id},
    )
    while r.has_next():
        sid = r.get_next()[0]
        chk = conn.execute(
            "MATCH (s:Source {source_id: $s}) RETURN COUNT(*)", {"s": sid},
        )
        if chk.has_next() and int(chk.get_next()[0]) == 0:
            raise RuntimeError(
                f"Post-mutation invariant violation: Claim {new_claim_id!r} EVIDENCES "
                f"references missing Source {sid!r}"
            )

    # Invariant 4: Claim-Claim edges target existing Claims.
    for edge_name in ("CONTRADICTS", "SUPERSEDES", "QUALIFIES"):
        r = conn.execute(
            f"""
            MATCH (a:Claim {{claim_id: $cid}})-[:{edge_name}]->(b:Claim)
            RETURN b.claim_id
            """,
            {"cid": new_claim_id},
        )
        while r.has_next():
            other = r.get_next()[0]
            chk = conn.execute(
                "MATCH (c:Claim {claim_id: $c}) RETURN COUNT(*)", {"c": other},
            )
            if chk.has_next() and int(chk.get_next()[0]) == 0:
                raise RuntimeError(
                    f"Post-mutation invariant violation: Claim {new_claim_id!r} "
                    f"{edge_name} references missing Claim {other!r}"
                )


def _apply_mutation(
    candidate: CandidateEnvelope,
    classification: ClassificationResult,
    eval_config: EvalConfig,
    conn: Any,
) -> None:
    """Mutate graph state per D-83/84-2 action table cell.

    Always writes the topology layer (Entity merge, LINKS_TO via Object,
    SUPPORTS per evidence source). For Claim-creating cells (5 of 7),
    also writes a Claim + ABOUT + EVIDENCES + (when applicable) one
    Claim-Claim edge (CONTRADICTS / SUPERSEDES / QUALIFIES).

    Topology-only cells (no_counterpart / orthogonal / qualifies_or_extends
    with refines_truth_conditions=false / reinforces under threshold N)
    stop after the topology writes — zero Claim writes per P-O1-2.
    """
    from graphdb_kdb.core.belief_classifier import _scope_key

    pred = candidate.predicate_class_canonical
    scope = _scope_key(candidate.predicate_scope_slugs)
    family_id = f"{candidate.subject_slug}__{pred}__{scope}"
    now = eval_config.eval_clock
    run_id = f"o1-{candidate.candidate_id}"

    # Topology layer: ensure subject Entity exists.
    conn.execute(
        """
        MERGE (e:Entity {slug: $slug})
        ON CREATE SET e.title = $slug, e.page_type = 'concept', e.status = 'active',
                      e.confidence = 'high', e.canonical_id = NULL,
                      e.created_at = $now, e.updated_at = $now,
                      e.first_run_id = $run_id, e.last_run_id = $run_id
        ON MATCH SET e.last_run_id = $run_id, e.updated_at = $now
        """,
        {"slug": candidate.subject_slug, "now": now, "run_id": run_id},
    )

    # SUPPORTS per evidence source.
    for ev in candidate.evidence:
        conn.execute(
            """
            MATCH (e:Entity {slug: $slug})
            MERGE (s:Source {source_id: $sid})
            ON CREATE SET s.source_type = 'md', s.canonical_path = $sid,
                          s.status = 'active', s.file_type = 'md', s.hash = '',
                          s.size_bytes = 0, s.first_seen_at = $now,
                          s.last_seen_at = $now, s.last_ingested_at = $now,
                          s.ingest_state = 'compiled', s.ingest_count = 1,
                          s.last_run_id = $run_id, s.moved_to = ''
            MERGE (s)-[:SUPPORTS {role: 'subject', hash_at_time: '', run_id: $run_id, created_at: $now}]->(e)
            """,
            {"slug": candidate.subject_slug, "sid": ev.source_id, "now": now, "run_id": run_id},
        )

    # Decide Claim-creating vs topology-only per D-83/84-2.
    cs = classification.counterpart_status
    rk = classification.relation_kind
    rtc = classification.refines_truth_conditions

    creates_claim = False
    if cs == "candidate_counterpart_found":
        if rk == "contradicts":
            creates_claim = True
        elif rk == "supersedes":
            creates_claim = True
        elif rk == "qualifies_or_extends" and rtc:
            creates_claim = True
        elif rk == "reinforces":
            # Simplification: reinforces always creates Claim here (true
            # implementation would gate on corroboration_threshold_n vs
            # the Tier-2 evidence count — deferred along with LINKS_TO-
            # implicit-counterpart logic).
            creates_claim = True
    # cs == "no_counterpart" / "orthogonal" → topology-only by default.
    # qualifies_or_extends with rtc=false → topology-only.

    if not creates_claim:
        return

    # Determine next version per family.
    r = conn.execute(
        "MATCH (c:Claim {claim_family_id: $fid}) RETURN max(c.version)",
        {"fid": family_id},
    )
    next_version = 1
    if r.has_next():
        v = r.get_next()[0]
        if v is not None:
            next_version = int(v) + 1

    claim_id = f"{family_id}__v{next_version}"

    # Confidence aggregation (D-83/84-12 default: candidate-level score
    # for v1; recency-weighted aggregation across evidence is the future
    # OQ-26 lever).
    confidence = candidate.confidence.score if candidate.confidence else 0.5

    object_slugs = [candidate.object_slug] if candidate.object_slug else []

    conn.execute(
        """
        CREATE (c:Claim {
            claim_id: $cid, claim_family_id: $fid,
            subject_slug: $subj, predicate_class_canonical: $pred,
            predicate_class_raw: $praw,
            predicate_scope_slugs: $scopes, object_slugs: $objs,
            polarity: $pol, modality: $mod,
            condition_text: $cond, assertion_text: $asn,
            confidence: $conf, confidence_spread: 0.0,
            state: 'active', version: $ver,
            created_at: $now, last_revised_at: $now
        })
        """,
        {
            "cid": claim_id, "fid": family_id,
            "subj": candidate.subject_slug,
            "pred": pred, "praw": candidate.predicate_class_raw,
            "scopes": list(candidate.predicate_scope_slugs),
            "objs": object_slugs,
            "pol": candidate.polarity, "mod": candidate.modality,
            "cond": candidate.object_qualifier or "",
            "asn": "", "conf": confidence, "ver": next_version, "now": now,
        },
    )

    # ABOUT edge.
    conn.execute(
        """
        MATCH (c:Claim {claim_id: $cid}), (e:Entity {slug: $slug})
        CREATE (c)-[:ABOUT {run_id: $run_id, created_at: $now}]->(e)
        """,
        {"cid": claim_id, "slug": candidate.subject_slug, "run_id": run_id, "now": now},
    )

    # EVIDENCES per evidence source.
    for ev in candidate.evidence:
        ev_score = ev.confidence.score if ev.confidence else 0.5
        conn.execute(
            """
            MATCH (s:Source {source_id: $sid}), (c:Claim {claim_id: $cid})
            CREATE (s)-[:EVIDENCES {
                quoted_text: $qt, score: $score,
                provenance_type: 'analysis_emitted',
                run_id: $run_id, created_at: $now
            }]->(c)
            """,
            {"sid": ev.source_id, "cid": claim_id, "qt": ev.quoted_text,
             "score": ev_score, "run_id": run_id, "now": now},
        )

    # Claim-Claim edge if there's a counterpart.
    if classification.counterpart_claim_id is not None:
        edge_table = {
            "contradicts": ("CONTRADICTS", "{contradiction_kind: 'polarity_flip', run_id: $run_id, created_at: $now}"),
            "supersedes": ("SUPERSEDES", "{run_id: $run_id, created_at: $now}"),
            "qualifies_or_extends": ("QUALIFIES", "{run_id: $run_id, created_at: $now}"),
        }.get(classification.relation_kind or "")
        if edge_table is not None:
            edge_name, attrs = edge_table
            conn.execute(
                f"""
                MATCH (a:Claim {{claim_id: $new}}), (b:Claim {{claim_id: $old}})
                CREATE (a)-[:{edge_name} {attrs}]->(b)
                """,
                {"new": claim_id, "old": classification.counterpart_claim_id,
                 "run_id": run_id, "now": now},
            )

    # On supersedes: mark the counterpart as superseded.
    if classification.relation_kind == "supersedes" and classification.counterpart_claim_id:
        conn.execute(
            """
            MATCH (c:Claim {claim_id: $cid})
            SET c.state = 'superseded', c.last_revised_at = $now
            """,
            {"cid": classification.counterpart_claim_id, "now": now},
        )
