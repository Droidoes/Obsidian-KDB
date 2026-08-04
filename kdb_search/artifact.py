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
from dataclasses import asdict, dataclass, field
from typing import Literal

from common.paths import PAGE_TYPES

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


# ---------------------------------------------------------------------------
# #123 P3a §5.1 (B9) — the discriminated envelope union + compact success receipt
# ---------------------------------------------------------------------------

#: The OUTER envelope's own version — the inner audit's ARTIFACT_SCHEMA_VERSION
#: is not a substitute for versioning the union (codex r2-2).
SEARCH_ENVELOPE_SCHEMA_VERSION = 1

ReceiptKind = Literal["compact", "full"]


@dataclass(frozen=True)
class CompactStageRecord:
    """The success-path projection of StageRecord (§5.1): stage/attempt, prompt
    ref, model stamp, token usage, cost, stop reason, validation counts,
    retained_identities, sent_bytes — and NOTHING else. No rendered_messages,
    raw_response_text, parsed_output, or evidence bodies (the ratified logging
    policy: full bytes retained only on failure).

    `sent_bytes` is REQUIRED, not optional (B2): measured_bytes_per_token is a
    derived property computed from the rendered-message bytes this form drops —
    persisting the bytes is not persisting the ratio, so "derived, never
    stored" stays intact while the bytes-per-token series keeps a success-path
    input."""

    stage: StageName
    attempt: int
    prompt: PromptRef
    model: ModelStamp
    latency_ms: int
    cost: float
    provider_input_tokens: int | None
    stop_reason_raw: str | None
    stop_reason_normalized: str | None
    sdk_sub_retries: int
    sent_bytes: int
    failure: StageFailure | None = None
    validation: StageValidation | None = None
    retained_identities: tuple[str, ...] | None = None


@dataclass(frozen=True)
class CompactSearchReceipt:
    """§5.1's compact success receipt — the SearchAuditPayload's payload-level
    fields (graph ref, query, identity manifest, result, both hashes, rendered
    query) over CompactStageRecords. The manifest is identity lines, not an
    evidence body, and it is what makes the persisted search_snapshot_hash
    checkable."""

    schema_version: int
    graph_ref: GraphSnapshotRef
    query: QueryPayload
    eligible_space_manifest: tuple[SpaceEntity, ...]
    execution: Execution
    stages: tuple[CompactStageRecord, ...]
    result: SearchResultSummary
    search_snapshot_hash: str
    artifact_integrity_hash: str
    rendered_query: RenderedQuery | None = None


def compact_receipt(audit: SearchAuditPayload) -> CompactSearchReceipt:
    """Project a full audit to its compact success form (§5.1). sent_bytes is
    measured HERE, from the rendered messages the compact form drops."""

    def _compact(stage: StageRecord) -> CompactStageRecord:
        return CompactStageRecord(
            stage=stage.stage,
            attempt=stage.attempt,
            prompt=stage.prompt,
            model=stage.model,
            latency_ms=stage.latency_ms,
            cost=stage.cost,
            provider_input_tokens=stage.provider_input_tokens,
            stop_reason_raw=stage.stop_reason_raw,
            stop_reason_normalized=stage.stop_reason_normalized,
            sdk_sub_retries=stage.sdk_sub_retries,
            sent_bytes=len(stage.rendered_messages.system.encode())
            + len(stage.rendered_messages.user.encode()),
            failure=stage.failure,
            validation=stage.validation,
            retained_identities=stage.retained_identities,
        )

    return CompactSearchReceipt(
        schema_version=audit.schema_version,
        graph_ref=audit.graph_ref,
        query=audit.query,
        eligible_space_manifest=audit.eligible_space_manifest,
        execution=audit.execution,
        stages=tuple(_compact(stage) for stage in audit.stages),
        result=audit.result,
        search_snapshot_hash=audit.search_snapshot_hash,
        artifact_integrity_hash=audit.artifact_integrity_hash,
        rendered_query=audit.rendered_query,
    )


def receipt_kind_for(status: Status | None, *, raised_with_audit: bool = False) -> ReceiptKind:
    """§5.1's CLOSED retention predicate (codex r2-5), per the ratified logging
    policy (full bytes retained only on failure):

    - FULL for selector_failure, pre-call or post-call budget_exceeded, and
      thrown exceptions for which an audit exists (`raised_with_audit`).
    - COMPACT for completed searches — INCLUDING warn-and-continue cases:
      envelope-write / provenance warnings never escalate the receipt.
    """
    if raised_with_audit or status in ("selector_failure", "budget_exceeded"):
        return "full"
    return "compact"


def space_fingerprint(manifest: tuple[SpaceEntity, ...]) -> str:
    """sha256 over canonical JSON of the ordered manifest (spec §5.1's
    fingerprint convention) — order-sensitive on purpose: it pins the exact
    space, in the exact order, that was materialized."""
    return sha256_digest(_canonical(_manifest_digest(manifest)))


@dataclass(frozen=True)
class SearchRunEnvelope:
    """The pass-1.5 persistence + ordering wrapper — the discriminated receipt
    union (#123 P3a §5.1, B9). Everything consumer-specific lives here so the
    core payload stays neutral.

    The OUTER envelope carries its own `schema_version` — the inner audit's
    version is no substitute for versioning the union (codex r2-2)."""

    schema_version: int
    run_id: str
    source_id: str
    #: Records that mid-run the space is a function of compile order — source N
    #: reads bodies written by sources 1..N-1 (opus5 B1 / §5.3).
    intra_run_order: int
    receipt_kind: ReceiptKind
    receipt: CompactSearchReceipt | SearchAuditPayload
    #: Null until the write succeeds — warn-only sink (§4.1 step 7).
    artifact_path: str | None = None


# ---------------------------------------------------------------------------
# §5.1 serialization + strict parser (codex r2-2)
#
# `search_envelope_to_dict` is the ONLY write-side shape; `parse_search_envelope`
# is the strict reader — rejects, never coerces (house convention:
# compiler/context_record.py's parse_context_record_v1), and additionally pins
# the exact key sets so the two receipt kinds cannot silently trade fields.
# Neither function does I/O — the caller owns the bytes.
# ---------------------------------------------------------------------------


class SearchEnvelopeError(ValueError):
    """Strict envelope parser rejection — malformed persisted payloads."""


def search_envelope_to_dict(envelope: SearchRunEnvelope) -> dict:
    """The on-disk envelope shape (`state/runs/<run_id>/search/<safe>.json`)."""
    return {
        "schema_version": envelope.schema_version,
        "run_id": envelope.run_id,
        "source_id": envelope.source_id,
        "intra_run_order": envelope.intra_run_order,
        "artifact_path": envelope.artifact_path,
        "receipt_kind": envelope.receipt_kind,
        "receipt": asdict(envelope.receipt),
    }


_ENVELOPE_KEYS = frozenset({
    "schema_version", "run_id", "source_id", "intra_run_order",
    "artifact_path", "receipt_kind", "receipt",
})
_RECEIPT_KEYS = frozenset({
    "schema_version", "graph_ref", "query", "eligible_space_manifest",
    "execution", "stages", "result", "search_snapshot_hash",
    "artifact_integrity_hash", "rendered_query",
})
_GRAPH_REF_KEYS = frozenset({
    "schema_version", "active_entity_count", "space_fingerprint",
    "source_kind", "source_detail",
})
_QUERY_KEYS = frozenset({"text", "expressions"})
_SPACE_ENTITY_KEYS = frozenset({"slug", "title", "page_type"})
_RESULT_KEYS = frozenset({
    "hits", "unresolved_expressions", "status", "evidence_status", "body_coverage",
})
_HIT_KEYS = frozenset({"slug", "title", "page_type", "matched_expressions"})
_PROMPT_REF_KEYS = frozenset({"version", "sha256", "repo_path", "git_commit"})
_MODEL_STAMP_KEYS = frozenset({"provider", "model", "route"})
_RENDERED_MESSAGES_KEYS = frozenset({"system", "user"})
_STAGE_FAILURE_KEYS = frozenset({"failure_class", "detail"})
_STAGE_VALIDATION_KEYS = frozenset({"dropped", "coerced", "counts"})
_RENDERED_QUERY_KEYS = frozenset({
    "text", "rendered_expressions", "query_truncated", "original_fields",
    "rendered_fields", "delimiter_collision_guard",
})
_COMPACT_STAGE_KEYS = frozenset({
    "stage", "attempt", "prompt", "model", "latency_ms", "cost",
    "provider_input_tokens", "stop_reason_raw", "stop_reason_normalized",
    "sdk_sub_retries", "sent_bytes", "failure", "validation", "retained_identities",
})
_FULL_STAGE_KEYS = frozenset({
    "stage", "attempt", "prompt", "rendered_messages", "model", "evidence",
    "latency_ms", "cost", "provider_input_tokens", "raw_response_text",
    "parsed_output", "stop_reason_raw", "stop_reason_normalized",
    "sdk_sub_retries", "failure", "validation", "retained_identities",
})

_RECEIPT_KINDS = frozenset({"compact", "full"})
_EXECUTIONS = frozenset({"not_executed", "thin_attempted", "two_stage_attempted"})
_STATUSES = frozenset({"completed", "abstain_empty_space", "budget_exceeded", "selector_failure"})
_EVIDENCE_STATUSES = frozenset({"not_applicable", "complete", "partial"})
_STAGE_NAMES = frozenset({"thin_selection", "fat_selection"})
_PAGE_TYPES = frozenset(PAGE_TYPES)


def _err(path: str, detail: str) -> SearchEnvelopeError:
    return SearchEnvelopeError(f"{path}: {detail}")


def _req_dict(value: object, path: str, keys: frozenset[str]) -> dict:
    if not isinstance(value, dict):
        raise _err(path, f"expected a dict, got {value!r}")
    if set(value) != set(keys):
        raise _err(path, f"keys {sorted(value)} != expected {sorted(keys)}")
    return value


def _req_str(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise _err(path, f"expected a str, got {value!r}")
    return value


def _req_str_or_none(value: object, path: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise _err(path, f"expected null or a str, got {value!r}")
    return value


def _req_int(value: object, path: str) -> int:
    # bool-as-int rejects: True/False are ints in Python but never counts.
    if isinstance(value, bool) or not isinstance(value, int):
        raise _err(path, f"expected an int, got {value!r}")
    return value


def _req_int_or_none(value: object, path: str) -> int | None:
    if value is None:
        return None
    return _req_int(value, path)


def _req_num(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _err(path, f"expected a number, got {value!r}")
    return float(value)


def _req_num_or_none(value: object, path: str) -> float | None:
    if value is None:
        return None
    return _req_num(value, path)


def _req_enum(value: object, allowed: frozenset[str], path: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise _err(path, f"expected one of {sorted(allowed)}, got {value!r}")
    return value


def _req_str_tuple(value: object, path: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise _err(path, f"expected a list of str, got {value!r}")
    return tuple(value)


def _parse_prompt_ref(raw: object, path: str) -> PromptRef:
    d = _req_dict(raw, path, _PROMPT_REF_KEYS)
    return PromptRef(
        version=_req_str(d["version"], f"{path}.version"),
        sha256=_req_str(d["sha256"], f"{path}.sha256"),
        repo_path=_req_str(d["repo_path"], f"{path}.repo_path"),
        git_commit=_req_str(d["git_commit"], f"{path}.git_commit"),
    )


def _parse_model_stamp(raw: object, path: str) -> ModelStamp:
    d = _req_dict(raw, path, _MODEL_STAMP_KEYS)
    return ModelStamp(
        provider=_req_str(d["provider"], f"{path}.provider"),
        model=_req_str(d["model"], f"{path}.model"),
        route=_req_str(d["route"], f"{path}.route"),
    )


def _parse_stage_failure(raw: object, path: str) -> StageFailure | None:
    if raw is None:
        return None
    d = _req_dict(raw, path, _STAGE_FAILURE_KEYS)
    return StageFailure(
        failure_class=_req_str(d["failure_class"], f"{path}.failure_class"),
        detail=_req_str(d["detail"], f"{path}.detail"),
    )


def _parse_stage_validation(raw: object, path: str) -> StageValidation | None:
    if raw is None:
        return None
    d = _req_dict(raw, path, _STAGE_VALIDATION_KEYS)
    for name in ("dropped", "coerced", "counts"):
        value = d[name]
        if not isinstance(value, dict) or any(
                not isinstance(k, str) or not isinstance(v, int) or isinstance(v, bool)
                for k, v in value.items()):
            raise _err(f"{path}.{name}", f"expected a str->int map, got {value!r}")
    return StageValidation(dropped=d["dropped"], coerced=d["coerced"], counts=d["counts"])


def _parse_rendered_messages(raw: object, path: str) -> RenderedMessages:
    d = _req_dict(raw, path, _RENDERED_MESSAGES_KEYS)
    return RenderedMessages(
        system=_req_str(d["system"], f"{path}.system"),
        user=_req_str(d["user"], f"{path}.user"),
    )


def _parse_query_payload(raw: object, path: str) -> QueryPayload:
    d = _req_dict(raw, path, _QUERY_KEYS)
    return QueryPayload(
        text=_req_str(d["text"], f"{path}.text"),
        expressions=_req_str_tuple(d["expressions"], f"{path}.expressions"),
    )


def _parse_space_entity(raw: object, path: str) -> SpaceEntity:
    d = _req_dict(raw, path, _SPACE_ENTITY_KEYS)
    return SpaceEntity(
        slug=_req_str(d["slug"], f"{path}.slug"),
        title=_req_str(d["title"], f"{path}.title"),
        page_type=_req_enum(d["page_type"], _PAGE_TYPES, f"{path}.page_type"),  # type: ignore[arg-type]
    )


def _parse_graph_ref(raw: object, path: str) -> GraphSnapshotRef:
    d = _req_dict(raw, path, _GRAPH_REF_KEYS)
    return GraphSnapshotRef(
        schema_version=_req_str(d["schema_version"], f"{path}.schema_version"),
        active_entity_count=_req_int(d["active_entity_count"], f"{path}.active_entity_count"),
        space_fingerprint=_req_str(d["space_fingerprint"], f"{path}.space_fingerprint"),
        source_kind=_req_str(d["source_kind"], f"{path}.source_kind"),
        source_detail=_req_str_or_none(d["source_detail"], f"{path}.source_detail"),
    )


def _parse_hit(raw: object, path: str) -> Hit:
    d = _req_dict(raw, path, _HIT_KEYS)
    return Hit(
        slug=_req_str(d["slug"], f"{path}.slug"),
        title=_req_str(d["title"], f"{path}.title"),
        page_type=_req_enum(d["page_type"], _PAGE_TYPES, f"{path}.page_type"),  # type: ignore[arg-type]
        matched_expressions=_req_str_tuple(d["matched_expressions"], f"{path}.matched_expressions"),
    )


def _parse_result_summary(raw: object, path: str) -> SearchResultSummary:
    d = _req_dict(raw, path, _RESULT_KEYS)
    hits = d["hits"]
    if not isinstance(hits, list):
        raise _err(f"{path}.hits", f"expected a list, got {hits!r}")
    return SearchResultSummary(
        hits=tuple(_parse_hit(h, f"{path}.hits[{i}]") for i, h in enumerate(hits)),
        unresolved_expressions=_req_str_tuple(
            d["unresolved_expressions"], f"{path}.unresolved_expressions"),
        status=_req_enum(d["status"], _STATUSES, f"{path}.status"),  # type: ignore[arg-type]
        evidence_status=_req_enum(  # type: ignore[arg-type]
            d["evidence_status"], _EVIDENCE_STATUSES, f"{path}.evidence_status"),
        body_coverage=_req_num_or_none(d["body_coverage"], f"{path}.body_coverage"),
    )


def _parse_rendered_query(raw: object, path: str) -> RenderedQuery | None:
    if raw is None:
        return None
    d = _req_dict(raw, path, _RENDERED_QUERY_KEYS)
    # original_fields / rendered_fields are the archival "both forms" — values
    # are caller data (str | [str]), validated as JSON by the write side.
    query_truncated = d["query_truncated"]
    if not isinstance(query_truncated, dict) or any(
            not isinstance(k, str) or not isinstance(v, int) or isinstance(v, bool)
            for k, v in query_truncated.items()):
        raise _err(f"{path}.query_truncated", f"expected a str->int map, got {query_truncated!r}")
    for name in ("original_fields", "rendered_fields"):
        if not isinstance(d[name], dict):
            raise _err(f"{path}.{name}", f"expected a dict, got {d[name]!r}")
    return RenderedQuery(
        text=_req_str(d["text"], f"{path}.text"),
        rendered_expressions=_req_str_tuple(
            d["rendered_expressions"], f"{path}.rendered_expressions"),
        query_truncated=query_truncated,
        original_fields=d["original_fields"],
        rendered_fields=d["rendered_fields"],
        delimiter_collision_guard=_req_int(
            d["delimiter_collision_guard"], f"{path}.delimiter_collision_guard"),
    )


def _parse_compact_stage(raw: object, path: str) -> CompactStageRecord:
    d = _req_dict(raw, path, _COMPACT_STAGE_KEYS)
    retained = d["retained_identities"]
    return CompactStageRecord(
        stage=_req_enum(d["stage"], _STAGE_NAMES, f"{path}.stage"),  # type: ignore[arg-type]
        attempt=_req_int(d["attempt"], f"{path}.attempt"),
        prompt=_parse_prompt_ref(d["prompt"], f"{path}.prompt"),
        model=_parse_model_stamp(d["model"], f"{path}.model"),
        latency_ms=_req_int(d["latency_ms"], f"{path}.latency_ms"),
        cost=_req_num(d["cost"], f"{path}.cost"),
        provider_input_tokens=_req_int_or_none(
            d["provider_input_tokens"], f"{path}.provider_input_tokens"),
        stop_reason_raw=_req_str_or_none(d["stop_reason_raw"], f"{path}.stop_reason_raw"),
        stop_reason_normalized=_req_str_or_none(
            d["stop_reason_normalized"], f"{path}.stop_reason_normalized"),
        sdk_sub_retries=_req_int(d["sdk_sub_retries"], f"{path}.sdk_sub_retries"),
        sent_bytes=_req_int(d["sent_bytes"], f"{path}.sent_bytes"),
        failure=_parse_stage_failure(d["failure"], f"{path}.failure"),
        validation=_parse_stage_validation(d["validation"], f"{path}.validation"),
        retained_identities=(
            None if retained is None else _req_str_tuple(retained, f"{path}.retained_identities")),
    )


def _parse_full_stage(raw: object, path: str) -> StageRecord:
    d = _req_dict(raw, path, _FULL_STAGE_KEYS)
    evidence = d["evidence"]
    if isinstance(evidence, dict):
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in evidence.items()):
            raise _err(f"{path}.evidence", f"expected a str->str map, got {evidence!r}")
    elif not isinstance(evidence, str):
        raise _err(f"{path}.evidence", f"expected a str or str->str map, got {evidence!r}")
    retained = d["retained_identities"]
    return StageRecord(
        stage=_req_enum(d["stage"], _STAGE_NAMES, f"{path}.stage"),  # type: ignore[arg-type]
        attempt=_req_int(d["attempt"], f"{path}.attempt"),
        prompt=_parse_prompt_ref(d["prompt"], f"{path}.prompt"),
        rendered_messages=_parse_rendered_messages(
            d["rendered_messages"], f"{path}.rendered_messages"),
        model=_parse_model_stamp(d["model"], f"{path}.model"),
        evidence=evidence,
        latency_ms=_req_int(d["latency_ms"], f"{path}.latency_ms"),
        cost=_req_num(d["cost"], f"{path}.cost"),
        provider_input_tokens=_req_int_or_none(
            d["provider_input_tokens"], f"{path}.provider_input_tokens"),
        raw_response_text=_req_str_or_none(d["raw_response_text"], f"{path}.raw_response_text"),
        parsed_output=d["parsed_output"],  # arbitrary JSON, archived verbatim
        stop_reason_raw=_req_str_or_none(d["stop_reason_raw"], f"{path}.stop_reason_raw"),
        stop_reason_normalized=_req_str_or_none(
            d["stop_reason_normalized"], f"{path}.stop_reason_normalized"),
        sdk_sub_retries=_req_int(d["sdk_sub_retries"], f"{path}.sdk_sub_retries"),
        failure=_parse_stage_failure(d["failure"], f"{path}.failure"),
        validation=_parse_stage_validation(d["validation"], f"{path}.validation"),
        retained_identities=(
            None if retained is None else _req_str_tuple(retained, f"{path}.retained_identities")),
    )


def _parse_receipt_common(d: dict, path: str) -> dict[str, object]:
    """The payload-level fields both receipt kinds share."""
    manifest = d["eligible_space_manifest"]
    if not isinstance(manifest, list):
        raise _err(f"{path}.eligible_space_manifest", f"expected a list, got {manifest!r}")
    return {
        "schema_version": _req_int(d["schema_version"], f"{path}.schema_version"),
        "graph_ref": _parse_graph_ref(d["graph_ref"], f"{path}.graph_ref"),
        "query": _parse_query_payload(d["query"], f"{path}.query"),
        "eligible_space_manifest": tuple(
            _parse_space_entity(e, f"{path}.eligible_space_manifest[{i}]")
            for i, e in enumerate(manifest)),
        "execution": _req_enum(d["execution"], _EXECUTIONS, f"{path}.execution"),
        "result": _parse_result_summary(d["result"], f"{path}.result"),
        "search_snapshot_hash": _req_str(d["search_snapshot_hash"], f"{path}.search_snapshot_hash"),
        "artifact_integrity_hash": _req_str(
            d["artifact_integrity_hash"], f"{path}.artifact_integrity_hash"),
        "rendered_query": _parse_rendered_query(d["rendered_query"], f"{path}.rendered_query"),
    }


def _parse_stages(raw: object, path: str, stage_parser) -> tuple:
    if not isinstance(raw, list):
        raise _err(path, f"expected a list, got {raw!r}")
    return tuple(stage_parser(s, f"{path}[{i}]") for i, s in enumerate(raw))


def parse_search_envelope(raw: object) -> SearchRunEnvelope:
    """Strict parser over the discriminated receipt_kind union (§5.1 B9).
    Rejects, never coerces. Raises SearchEnvelopeError.

    #123 P3a.4: the adapter persists the run-time SearchPassMeasurement as an
    additive `measurement` sibling key in the same file — tolerated (and
    ignored) here; `common.measurement`'s strict loader owns that channel."""
    if not isinstance(raw, dict):
        raise _err("$", f"expected an envelope dict, got {raw!r}")
    keys = set(_ENVELOPE_KEYS)
    if "measurement" in raw:
        keys.add("measurement")
    d = _req_dict(raw, "$", frozenset(keys))
    version = d["schema_version"]
    if isinstance(version, bool) or version != SEARCH_ENVELOPE_SCHEMA_VERSION:
        raise _err("$.schema_version", f"missing/unsupported: {version!r}")
    kind = _req_enum(d["receipt_kind"], _RECEIPT_KINDS, "$.receipt_kind")
    receipt_raw = _req_dict(d["receipt"], "$.receipt", _RECEIPT_KEYS)
    common = _parse_receipt_common(receipt_raw, "$.receipt")
    if kind == "compact":
        receipt: CompactSearchReceipt | SearchAuditPayload = CompactSearchReceipt(
            **common,  # type: ignore[arg-type]
            stages=_parse_stages(receipt_raw["stages"], "$.receipt.stages", _parse_compact_stage),
        )
    else:
        receipt = SearchAuditPayload(
            **common,  # type: ignore[arg-type]
            stages=_parse_stages(receipt_raw["stages"], "$.receipt.stages", _parse_full_stage),
        )
    artifact_path = d["artifact_path"]
    if artifact_path is not None and not isinstance(artifact_path, str):
        raise _err("$.artifact_path", f"expected null or a str, got {artifact_path!r}")
    return SearchRunEnvelope(
        schema_version=SEARCH_ENVELOPE_SCHEMA_VERSION,
        run_id=_req_str(d["run_id"], "$.run_id"),
        source_id=_req_str(d["source_id"], "$.source_id"),
        intra_run_order=_req_int(d["intra_run_order"], "$.intra_run_order"),
        artifact_path=artifact_path,
        receipt_kind=kind,  # type: ignore[arg-type]
        receipt=receipt,
    )


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "SEARCH_ENVELOPE_SCHEMA_VERSION",
    "SPACE_MANIFEST_REF",
    "TITLE_ONLY_MARKER",
    "CompactSearchReceipt",
    "CompactStageRecord",
    "ModelStamp",
    "PromptRef",
    "ReceiptKind",
    "RenderedMessages",
    "SearchAuditPayload",
    "SearchEnvelopeError",
    "SearchResultSummary",
    "SearchRunEnvelope",
    "StageFailure",
    "StageName",
    "StageRecord",
    "StageValidation",
    "build_audit_payload",
    "compact_receipt",
    "compute_artifact_integrity_hash",
    "compute_search_snapshot_hash",
    "parse_search_envelope",
    "receipt_kind_for",
    "search_envelope_to_dict",
    "sha256_digest",
    "space_fingerprint",
]
