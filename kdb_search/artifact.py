"""#123 audit artifact + integrity hashes (spec §5.1, blueprint §6).

The payload splits into a **consumer-neutral core** (`SearchAuditPayload`) and a
pass-1.5 wrapper (`SearchRunEnvelope`), so an MCP/CLI/human search — which may have
neither `run_id` nor `source_id` — shares one type shape (codex F5, R2).

It is built on **every** path: completed, abstained, budget-exceeded and failed
alike. An audit record that exists only on success cannot answer the question the
audit exists for.

Two hashes, deliberately answering different questions:

  * `search_snapshot_hash` — **what was searched.** Over the graph identity, the
    ordered eligible manifest, the exact evidence bytes presented, and the
    projection-policy identity. It does NOT cover the result, so an identical
    snapshot across two runs means the two searches faced the same world.
  * `artifact_integrity_hash` — **what happened.** Over the query, the prompt
    references, the full stage trace and the result.

That separation is the point. A run that changes only its outcome moves the
integrity hash and leaves the snapshot hash alone, which is what makes selector
A/B over a frozen snapshot meaningful.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal

from .projection import RenderedQuery
from .types import (
    EvidenceStatus,
    Execution,
    GraphSnapshotRef,
    Hit,
    QueryPayload,
    SpaceEntity,
    Status,
)

#: Bumped 1 → 2 in P2.3, when `StageRecord` gained `stop_reason_raw`,
#: `stop_reason_normalized` and `sdk_sub_retries`, and `stop_reason` entered
#: `_stage_trace_digest`. Version 1 would otherwise name two different payload
#: shapes AND two different integrity hashes for the same trace. Nothing is
#: persisted yet — no adapter writes a file until P3 — so the bump costs nothing
#: today and would cost a migration the moment one does.
ARTIFACT_SCHEMA_VERSION = 2

StageName = Literal["thin_selection", "fat_selection"]

#: Stage-1's evidence IS the eligible manifest — recorded as a reference rather
#: than duplicated, since the manifest is already in the payload.
SPACE_MANIFEST_REF = "space_manifest_ref"

#: Marks an entity presented to the fat selector with no body (graph/disk drift).
TITLE_ONLY_MARKER = "__title_only__"


def _canonical(obj: object) -> str:
    """Canonical JSON for hashing: sorted keys, compact separators, no ASCII
    escaping. Byte-stable across runs and Python versions."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_digest(text: str) -> str:
    """Repo convention (`ingestion/kdb_scan.py`, `common/types.py`): the digest
    carries its algorithm prefix.

    Public because `prompts.py` stamps `PromptRef.sha256` with it. The digest
    convention belongs to the artifact — sharing the function is what keeps the
    prompt hash and the artifact hashes from being two conventions.
    """
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True)
class PromptRef:
    """The template is tracked in the repo; any edit bumps its version. Referenced
    rather than inlined — the exact rendered bytes are archived separately, so byte
    fidelity never depends on template lookup (codex F4)."""

    version: str
    sha256: str
    repo_path: str
    git_commit: str


@dataclass(frozen=True)
class RenderedMessages:
    """The EXACT bytes sent. Archived verbatim so fidelity survives any later
    drift in the serializer, escaping or message-assembly code."""

    system: str
    user: str


@dataclass(frozen=True)
class ModelStamp:
    provider: str
    model: str
    route: str


@dataclass(frozen=True)
class StageFailure:
    failure_class: str
    detail: str


@dataclass(frozen=True)
class StageValidation:
    dropped: dict[str, int] = field(default_factory=dict)
    coerced: dict[str, int] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class StageRecord:
    """One entry per executed CALL ATTEMPT, in order — a retried call produces two
    records, each with its own rendered messages and raw response (opus5 §2.6b).
    """

    stage: StageName
    attempt: int
    prompt: PromptRef
    rendered_messages: RenderedMessages
    model: ModelStamp
    #: Stage 2: `{slug: excerpt_text | TITLE_ONLY_MARKER}`. Stage 1:
    #: `SPACE_MANIFEST_REF`.
    evidence: dict[str, str] | str
    latency_ms: int
    cost: float
    #: The provider's OWN reported prompt-token count for this attempt. `None`
    #: when no response reached us at all (transport failure) — never 0, which
    #: would enter the calibration series as an infinitely bad ratio rather than
    #: as absent data (the rule `valid_entry_yield` follows at zero returned).
    #:
    #: **Why it is archived (Joseph, 2026-08-02, closing Fork C).** The pre-flight
    #: predicts cost as `bytes / ESTIMATOR_BYTES_PER_TOKEN`, and `BudgetRecord`
    #: claims a passing series is "exactly how the estimator's calibration is
    #: judged" — but that series carries only our own estimate, and
    #: `budget_estimation_miss` fires only when the provider REFUSES the request.
    #: An under-estimate that still fit was invisible. This is the counterpart
    #: that makes the claim checkable, and it turns every live call into a
    #: calibration data point instead of relying on a frozen synthetic gate.
    provider_input_tokens: int | None = None
    #: Verbatim, including malformed output — the malformed and timeout cases are
    #: exactly the failure-audit cases.
    raw_response_text: str | None = None
    #: None on unparseable or transport failure.
    parsed_output: object | None = None
    #: The provider's stop reason verbatim, and its normalization through the
    #: closed `api_call_type` map (D9.4). **Both**, deliberately: the raw value is
    #: the evidence and the normalized value is the decision, and an unknown raw
    #: value must never be guessed into the budget class — a claim only checkable
    #: if the raw value survives beside the verdict it produced. `None` on a
    #: transport failure, where no response reached us at all.
    stop_reason_raw: str | None = None
    stop_reason_normalized: str | None = None
    #: The provider SDK's OWN transport sub-retry allowance for this route (§8
    #: G5). Recorded because it is the difference between "the selector answered
    #: on the first try" and "the SDK quietly tried three times" — a latency and
    #: reliability reading that is invisible otherwise, and it differs per family
    #: (openai-family 2, gemini none). **Never an attempt**: `logical_call_count`
    #: counts `StageRecord`s, and this number is excluded from both sides of that
    #: identity. It is context on the attempt, not a count of them.
    sdk_sub_retries: int = 0
    failure: StageFailure | None = None
    validation: StageValidation | None = None
    #: Stage 1 only — post-validation, post-truncation.
    retained_identities: tuple[str, ...] | None = None

    @property
    def measured_bytes_per_token(self) -> float | None:
        """This attempt's REAL bytes-per-token, or `None` with no measurement.

        Derived, never stored: the bytes are already in `rendered_messages`, so
        persisting the ratio too would be a parallel store of something the
        record computes — and the two could then disagree.

        Compare against `ESTIMATOR_BYTES_PER_TOKEN`: a value BELOW it means the
        pre-flight under-estimated this request, and the 0.8 headroom is what
        absorbed the difference.
        """
        if not self.provider_input_tokens:
            return None
        sent = len(self.rendered_messages.system.encode()) + len(
            self.rendered_messages.user.encode()
        )
        return sent / self.provider_input_tokens


@dataclass(frozen=True)
class SearchResultSummary:
    hits: tuple[Hit, ...]
    unresolved_expressions: tuple[str, ...]
    status: Status
    evidence_status: EvidenceStatus = "not_applicable"
    body_coverage: float | None = None


@dataclass(frozen=True)
class SearchAuditPayload:
    schema_version: int
    graph_ref: GraphSnapshotRef
    query: QueryPayload
    eligible_space_manifest: tuple[SpaceEntity, ...]
    execution: Execution
    stages: tuple[StageRecord, ...]
    result: SearchResultSummary
    search_snapshot_hash: str
    artifact_integrity_hash: str
    #: The per-field truncation record (P1.1's option-C resolution). §3.1's
    #: "the archived QueryPayload records both original and rendered forms" is a
    #: statement about the ARTIFACT, so it lands here rather than on the ratified
    #: request type. `None` for a caller that supplied `text` directly.
    rendered_query: RenderedQuery | None = None

    @property
    def logical_call_count(self) -> int:
        """One logical call per StageRecord, by construction. SDK transport
        sub-retries are excluded from BOTH sides of this identity — they are the
        provider's business, not an attempt we made."""
        return len(self.stages)


def _manifest_digest(manifest: tuple[SpaceEntity, ...]) -> list[list[str]]:
    """Order-sensitive on purpose: the hash pins the exact space, in the exact
    order, that was presented."""
    return [[e.slug, e.title, e.page_type] for e in manifest]


def _graph_digest(graph_ref: GraphSnapshotRef) -> dict[str, object]:
    return {
        "schema_version": graph_ref.schema_version,
        "active_entity_count": graph_ref.active_entity_count,
        "space_fingerprint": graph_ref.space_fingerprint,
        "source_kind": graph_ref.source_kind,
        "source_detail": graph_ref.source_detail,
    }


def _evidence_digest(stages: tuple[StageRecord, ...]) -> list[object]:
    return [
        {"stage": s.stage, "attempt": s.attempt, "evidence": s.evidence} for s in stages
    ]


def compute_search_snapshot_hash(
    *,
    graph_ref: GraphSnapshotRef,
    manifest: tuple[SpaceEntity, ...],
    stages: tuple[StageRecord, ...],
) -> str:
    """What was searched: graph identity + ordered manifest + exact evidence bytes.
    Deliberately excludes the result.

    **`excerpt_policy_version` was a fourth term and is gone (D-123-C/§12).** It
    identified the transformation applied to bodies; with bodies delivered whole
    there is no transformation, and the evidence digest already carries the exact
    bytes the policy used to describe. Snapshot hashes move across this change
    either way — the evidence bytes themselves changed.
    """
    return sha256_digest(
        _canonical(
            {
                "graph_ref": _graph_digest(graph_ref),
                "manifest": _manifest_digest(manifest),
                "evidence": _evidence_digest(stages),
            }
        )
    )


def _stage_trace_digest(stages: tuple[StageRecord, ...]) -> list[object]:
    return [
        {
            "stage": s.stage,
            "attempt": s.attempt,
            "prompt": [s.prompt.version, s.prompt.sha256, s.prompt.repo_path, s.prompt.git_commit],
            "rendered_messages": [s.rendered_messages.system, s.rendered_messages.user],
            "raw_response_text": s.raw_response_text,
            # In the integrity hash, not the snapshot hash: the stop reason is
            # part of what HAPPENED, not of what was searched.
            "stop_reason": [s.stop_reason_raw, s.stop_reason_normalized],
            "model": [s.model.provider, s.model.model, s.model.route],
            "failure": None if s.failure is None else [s.failure.failure_class, s.failure.detail],
            "retained_identities": list(s.retained_identities or ()),
            "validation": None
            if s.validation is None
            else {
                "dropped": s.validation.dropped,
                "coerced": s.validation.coerced,
                "counts": s.validation.counts,
            },
        }
        for s in stages
    ]


def compute_artifact_integrity_hash(
    *,
    query: QueryPayload,
    stages: tuple[StageRecord, ...],
    result: SearchResultSummary,
    execution: Execution,
) -> str:
    """What happened: query + prompts + stage trace + result.

    Latency and cost are excluded — they vary run to run without the artifact
    having changed, and an integrity hash that never reproduces cannot detect
    tampering.
    """
    return sha256_digest(
        _canonical(
            {
                "query": {"text": query.text, "expressions": list(query.expressions)},
                "stages": _stage_trace_digest(stages),
                "execution": execution,
                "result": {
                    "hits": [[h.slug, h.title, h.page_type, list(h.matched_expressions)] for h in result.hits],
                    "unresolved_expressions": list(result.unresolved_expressions),
                    "status": result.status,
                    "evidence_status": result.evidence_status,
                    "body_coverage": result.body_coverage,
                },
            }
        )
    )


def build_audit_payload(
    *,
    graph_ref: GraphSnapshotRef,
    query: QueryPayload,
    manifest: tuple[SpaceEntity, ...],
    execution: Execution,
    stages: tuple[StageRecord, ...] = (),
    result: SearchResultSummary,
    rendered_query: RenderedQuery | None = None,
) -> SearchAuditPayload:
    """Build the audit payload for ANY outcome.

    `stages` defaults to empty because the zero-call paths — `abstain_empty_space`
    and a pre-flight `budget_exceeded` — are real outcomes that must still produce
    a record. Their emptiness is the finding, not a reason to skip the artifact.
    """
    return SearchAuditPayload(
        schema_version=ARTIFACT_SCHEMA_VERSION,
        graph_ref=graph_ref,
        query=query,
        eligible_space_manifest=manifest,
        execution=execution,
        stages=stages,
        result=result,
        rendered_query=rendered_query,
        search_snapshot_hash=compute_search_snapshot_hash(
            graph_ref=graph_ref, manifest=manifest, stages=stages
        ),
        artifact_integrity_hash=compute_artifact_integrity_hash(
            query=query, stages=stages, result=result, execution=execution
        ),
    )


@dataclass(frozen=True)
class SearchRunEnvelope:
    """The pass-1.5 persistence + ordering wrapper. Everything consumer-specific
    lives here so the core payload stays neutral."""

    audit: SearchAuditPayload
    run_id: str
    source_id: str
    #: Records that mid-run the space is a function of compile order — source N
    #: reads bodies written by sources 1..N-1 (opus5 B1 / §5.3).
    intra_run_order: int
    artifact_path: str | None = None


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "SPACE_MANIFEST_REF",
    "TITLE_ONLY_MARKER",
    "ModelStamp",
    "PromptRef",
    "RenderedMessages",
    "SearchAuditPayload",
    "SearchResultSummary",
    "SearchRunEnvelope",
    "StageFailure",
    "StageName",
    "StageRecord",
    "StageValidation",
    "build_audit_payload",
    "compute_artifact_integrity_hash",
    "compute_search_snapshot_hash",
    "sha256_digest",
]
