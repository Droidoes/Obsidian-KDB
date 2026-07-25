"""context_record — persistence + evidence types for event-time context
capture (Task #122).

One ContextRecordV1 per source per run, written by compile_source to
`state_root/runs/<run_id>/context/<safe_source_id>.json`. Two statuses:

- `complete`        — built from the builder's ContextTelemetry (observables
                      non-null; outcomes align 1:1 with keys_emitted).
- `context_failed`  — synthesized from a ContextFailureInput when the builder
                      raised (observables null; zero tiers; empty outcomes).

`.to_dict()` is the ONLY serialization path. `parse_context_record_v1` is the
strict reader — rejects, never coerces; both status-invariant sides enforced.
`compiler`'s allowed imports are {common, kdb_graph}, so this module is
importable by the orchestrator + KPI layers without inversion (P2).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from common.types import (
    ConfiguredT2Mode,
    ContextTelemetry,
    EffectiveT2Strategy,
    KeyDisposition,
    KeyOutcome,
    TierRecord,
)

CONTEXT_RECORD_SCHEMA_VERSION = 1
ContextStatus = Literal["complete", "context_failed"]     # persistence-local

_CONTEXT_STATUSES = frozenset({"complete", "context_failed"})
_CONFIGURED_T2_MODES = frozenset({"structured", "layered", "legacy"})
_EFFECTIVE_T2_STRATEGIES = frozenset(
    {"structured_keys", "explicit_empty", "legacy_regex", "layered_union"})
_KEY_DISPOSITIONS = frozenset({"unresolved", "resolved_t2_seed", "resolved_already_t1",
                               "resolved_out_of_scope", "resolved_duplicate_seed"})

_ZERO_TIER = TierRecord(candidates=0, delivered=0, slugs=[])


class ContextRecordError(ValueError):
    """Strict factory/parser rejection — invalid state combos or malformed
    persisted payloads. Never coerces."""


@dataclass(frozen=True)
class ContextRecordV1:
    schema_version: Literal[1]
    run_id: str
    source_id: str
    status: ContextStatus
    configured_t2_mode: ConfiguredT2Mode
    effective_t2_strategy: EffectiveT2Strategy
    keys_emitted: list[str]
    key_outcomes: list[KeyOutcome]
    t1: TierRecord
    t2: TierRecord
    t3: TierRecord
    candidate_universe_size: int | None
    domain_scope: str | None
    cold_start: bool | None
    max_hops: int | None
    page_cap: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ContextFailureInput:
    """What is knowable WITHOUT a graph read (the builder raised) — the
    effective strategy is derived from mode + frontmatter, pre-graph-read."""
    source_id: str
    configured_t2_mode: ConfiguredT2Mode
    effective_t2_strategy: EffectiveT2Strategy
    keys_emitted: list[str]                      # Pass-1 frontmatter keys (known pre-build)
    domain_scope: str | None
    page_cap: int


@dataclass(frozen=True)
class ContextIntegrityIssue:
    path: str
    reason: Literal["malformed", "wrong_run"]
    detail: str


@dataclass(frozen=True)
class ContextLoadResult:
    records: list[ContextRecordV1]
    issues: list[ContextIntegrityIssue]


@dataclass(frozen=True)
class ContextIntegrity:
    missing: int
    malformed: int
    duplicate: int
    unexpected: int
    wrong_run: int
    expected_count_mismatch: bool


@dataclass(frozen=True)
class ContextEvidence:
    records: list[ContextRecordV1]
    expected_ids: set[str]
    matched_ids: set[str]
    coverage: float | None           # None when expected empty
    complete: bool                   # requires bool(expected_ids) — never vacuous
    integrity: ContextIntegrity


# ---------- factory ----------


def build_context_record_v1(
    *,
    run_id: str,
    status: ContextStatus,
    telemetry: ContextTelemetry | None = None,
    failure_input: ContextFailureInput | None = None,
) -> ContextRecordV1:
    """Build one record. Invalid state combos RAISE (never guess):

    complete:        telemetry required; failure_input forbidden;
                     candidate_universe_size / cold_start / max_hops non-null.
    context_failed:  telemetry forbidden; failure_input required; observables
                     null; zero tiers; empty key_outcomes.
    """
    if status == "complete":
        if telemetry is None:
            raise ContextRecordError("status='complete' requires telemetry")
        if failure_input is not None:
            raise ContextRecordError("status='complete' forbids failure_input")
        if (telemetry.candidate_universe_size is None
                or telemetry.cold_start is None
                or telemetry.max_hops is None):
            raise ContextRecordError(
                "status='complete' requires non-null observables "
                "(candidate_universe_size / cold_start / max_hops)")
        return ContextRecordV1(
            schema_version=CONTEXT_RECORD_SCHEMA_VERSION,
            run_id=run_id,
            source_id=telemetry.source_id,
            status="complete",
            configured_t2_mode=telemetry.configured_t2_mode,
            effective_t2_strategy=telemetry.effective_t2_strategy,
            keys_emitted=list(telemetry.keys_emitted),
            key_outcomes=list(telemetry.key_outcomes),
            t1=telemetry.t1,
            t2=telemetry.t2,
            t3=telemetry.t3,
            candidate_universe_size=telemetry.candidate_universe_size,
            domain_scope=telemetry.domain_scope,
            cold_start=telemetry.cold_start,
            max_hops=telemetry.max_hops,
            page_cap=telemetry.page_cap,
        )
    if status == "context_failed":
        if failure_input is None:
            raise ContextRecordError("status='context_failed' requires failure_input")
        if telemetry is not None:
            raise ContextRecordError("status='context_failed' forbids telemetry")
        return ContextRecordV1(
            schema_version=CONTEXT_RECORD_SCHEMA_VERSION,
            run_id=run_id,
            source_id=failure_input.source_id,
            status="context_failed",
            configured_t2_mode=failure_input.configured_t2_mode,
            effective_t2_strategy=failure_input.effective_t2_strategy,
            keys_emitted=list(failure_input.keys_emitted),
            key_outcomes=[],
            t1=_ZERO_TIER,
            t2=_ZERO_TIER,
            t3=_ZERO_TIER,
            candidate_universe_size=None,
            domain_scope=failure_input.domain_scope,
            cold_start=None,
            max_hops=None,
            page_cap=failure_input.page_cap,
        )
    raise ContextRecordError(f"unknown context record status: {status!r}")


# ---------- strict parser ----------


def _err(path: str, detail: str) -> ContextRecordError:
    return ContextRecordError(f"{path}: {detail}")


def _require_str(value: object, path: str, *, non_empty: bool = True) -> str:
    if not isinstance(value, str) or (non_empty and not value):
        raise _err(path, f"expected a non-empty str, got {value!r}")
    return value


def _require_enum(value: object, allowed: frozenset[str], path: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise _err(path, f"expected one of {sorted(allowed)}, got {value!r}")
    return value


def _require_count(value: object, path: str) -> int:
    # bool-as-int rejects: True/False are ints in Python but never counts.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _err(path, f"expected a non-negative int, got {value!r}")
    return value


def _require_str_list(value: object, path: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise _err(path, f"expected a list of str, got {value!r}")
    return list(value)


def _parse_tier(raw: object, path: str) -> TierRecord:
    if not isinstance(raw, dict):
        raise _err(path, f"expected a tier dict, got {raw!r}")
    candidates = _require_count(raw.get("candidates"), f"{path}.candidates")
    delivered = _require_count(raw.get("delivered"), f"{path}.delivered")
    slugs = _require_str_list(raw.get("slugs"), f"{path}.slugs")
    if delivered != len(slugs):
        raise _err(path, f"delivered={delivered} != len(slugs)={len(slugs)}")
    if delivered > candidates:
        raise _err(path, f"delivered={delivered} > candidates={candidates}")
    return TierRecord(candidates=candidates, delivered=delivered, slugs=slugs)


def _parse_outcome(raw: object, path: str) -> KeyOutcome:
    if not isinstance(raw, dict):
        raise _err(path, f"expected an outcome dict, got {raw!r}")
    key = _require_str(raw.get("key"), f"{path}.key")
    disposition = _require_enum(raw.get("disposition"), _KEY_DISPOSITIONS,
                                f"{path}.disposition")
    resolved = raw.get("resolved")
    stamp = raw.get("target_first_run_id")
    if stamp is not None and (not isinstance(stamp, str) or not stamp):
        # null-or-nonempty-str — an EMPTY persisted stamp rejects (the resolver
        # normalizes "" → None at construction; empty must never reach disk).
        raise _err(f"{path}.target_first_run_id",
                   f"expected null or a non-empty str, got {stamp!r}")
    if disposition == "unresolved":
        if resolved is not None:
            raise _err(path, f"unresolved outcome carries a target {resolved!r}")
    else:
        if not isinstance(resolved, str) or not resolved:
            raise _err(path, f"disposition={disposition!r} without a resolved target")
    return KeyOutcome(key=key, disposition=disposition,  # type: ignore[arg-type]
                      resolved=resolved, target_first_run_id=stamp)


def parse_context_record_v1(raw: dict) -> ContextRecordV1:
    """Strict v1 parser — rejects, never coerces. Raises ContextRecordError."""
    if not isinstance(raw, dict):
        raise _err("$", f"expected a record dict, got {raw!r}")
    version = raw.get("schema_version")
    if type(version) is not int or version != CONTEXT_RECORD_SCHEMA_VERSION:
        raise _err("schema_version", f"missing/unsupported: {version!r}")

    run_id = _require_str(raw.get("run_id"), "run_id")
    source_id = _require_str(raw.get("source_id"), "source_id")
    status = _require_enum(raw.get("status"), _CONTEXT_STATUSES, "status")
    configured_t2_mode = _require_enum(raw.get("configured_t2_mode"),
                                       _CONFIGURED_T2_MODES, "configured_t2_mode")
    effective_t2_strategy = _require_enum(raw.get("effective_t2_strategy"),
                                          _EFFECTIVE_T2_STRATEGIES, "effective_t2_strategy")
    keys_emitted = _require_str_list(raw.get("keys_emitted"), "keys_emitted")
    raw_outcomes = raw.get("key_outcomes")
    if not isinstance(raw_outcomes, list):
        raise _err("key_outcomes", f"expected a list, got {raw_outcomes!r}")
    key_outcomes = [_parse_outcome(o, f"key_outcomes[{i}]")
                    for i, o in enumerate(raw_outcomes)]
    t1 = _parse_tier(raw.get("t1"), "t1")
    t2 = _parse_tier(raw.get("t2"), "t2")
    t3 = _parse_tier(raw.get("t3"), "t3")
    page_cap = _require_count(raw.get("page_cap"), "page_cap")
    if t1.delivered + t2.delivered + t3.delivered > page_cap:
        raise _err("page_cap",
                   f"sum(delivered)={t1.delivered + t2.delivered + t3.delivered} "
                   f"> page_cap={page_cap}")
    domain_scope = raw.get("domain_scope")
    if domain_scope is not None and not isinstance(domain_scope, str):
        raise _err("domain_scope", f"expected null or str, got {domain_scope!r}")

    candidate_universe_size = raw.get("candidate_universe_size")
    cold_start = raw.get("cold_start")
    max_hops = raw.get("max_hops")

    if status == "complete":
        # Outcomes align 1:1 (positionally, emission order) with keys_emitted.
        if len(key_outcomes) != len(keys_emitted) or any(
                o.key != k for o, k in zip(key_outcomes, keys_emitted)):
            raise _err("key_outcomes",
                       "complete record: outcomes do not align 1:1 with keys_emitted")
        candidate_universe_size = _require_count(
            candidate_universe_size, "candidate_universe_size")
        if not isinstance(cold_start, bool):
            raise _err("cold_start", f"expected bool, got {cold_start!r}")
        max_hops = _require_count(max_hops, "max_hops")
    else:  # context_failed — observables null, zero tiers, empty outcomes
        for name, value in (("candidate_universe_size", candidate_universe_size),
                            ("cold_start", cold_start), ("max_hops", max_hops)):
            if value is not None:
                raise _err(name, f"context_failed requires null, got {value!r}")
        if key_outcomes:
            raise _err("key_outcomes", "context_failed requires empty outcomes")
        for name, tier in (("t1", t1), ("t2", t2), ("t3", t3)):
            if tier.candidates != 0 or tier.delivered != 0 or tier.slugs:
                raise _err(name, "context_failed requires zero tiers")

    return ContextRecordV1(
        schema_version=CONTEXT_RECORD_SCHEMA_VERSION,
        run_id=run_id,
        source_id=source_id,
        status=status,  # type: ignore[arg-type]
        configured_t2_mode=configured_t2_mode,  # type: ignore[arg-type]
        effective_t2_strategy=effective_t2_strategy,  # type: ignore[arg-type]
        keys_emitted=keys_emitted,
        key_outcomes=key_outcomes,
        t1=t1,
        t2=t2,
        t3=t3,
        candidate_universe_size=candidate_universe_size,
        domain_scope=domain_scope,
        cold_start=cold_start,
        max_hops=max_hops,
        page_cap=page_cap,
    )
