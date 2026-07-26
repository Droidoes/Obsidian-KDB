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

from .constants import EXCERPT_POLICY_VERSION
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

ARTIFACT_SCHEMA_VERSION = 1

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


def _sha256(text: str) -> str:
    """Repo convention (`ingestion/kdb_scan.py`, `common/types.py`): the digest
    carries its algorithm prefix."""
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
    #: Stage 2 only.
    excerpt_policy_version: str | None = None
    #: Verbatim, including malformed output — the malformed and timeout cases are
    #: exactly the failure-audit cases.
    raw_response_text: str | None = None
    #: None on unparseable or transport failure.
    parsed_output: object | None = None
    failure: StageFailure | None = None
    validation: StageValidation | None = None
    #: Stage 1 only — post-validation, post-truncation.
    retained_identities: tuple[str, ...] | None = None


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
    excerpt_policy_version: str = EXCERPT_POLICY_VERSION

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
    excerpt_policy_version: str = EXCERPT_POLICY_VERSION,
) -> str:
    """What was searched: graph identity + ordered manifest + exact evidence bytes
    + projection-policy identity. Deliberately excludes the result."""
    return _sha256(
        _canonical(
            {
                "graph_ref": _graph_digest(graph_ref),
                "manifest": _manifest_digest(manifest),
                "evidence": _evidence_digest(stages),
                "excerpt_policy_version": excerpt_policy_version,
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
    return _sha256(
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
]
