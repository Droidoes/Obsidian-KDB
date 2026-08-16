"""context_record — persistence + evidence types for event-time context
capture (Task #122).

One ContextRecordV1 per source per run, written by compile_source to
`state_root/runs/<run_id>/context/<safe_source_id>.json`. Two statuses:

- `complete`        — built from the builder's ContextTelemetry (observables
                      non-null; outcomes align 1:1 with keys_emitted).
- `context_failed`  — synthesized from a ContextFailureInputV2 when the builder
                      raised (observables null; zero tiers; empty outcomes).

`.to_dict()` is the ONLY serialization path. `parse_context_record_v1` /
`parse_context_record_v2` are the strict readers — rejects, never coerces;
both status-invariant sides enforced. `parse_context_record` is the
version-dispatching reader (#123 P3a.3, §4.5): it pre-reads
`schema_version` and hands off to the matching parser; unknown versions
reject. `kdb_graph_compiler`'s allowed imports are
{common, kdb_graph, kdb_graph_search}, so this module is importable by the
kdb_graph_orchestrator + KPI layers without inversion (P2).

V2 (#123 P3a, §4.5) carries the V1 skeleton minus the retiring vocabulary
(configured_t2_mode / effective_t2_strategy / max_hops), the per-expression
`matched | unresolved` outcomes with a CLOSED annotation vocabulary (B11),
and the `search` section — the adapter's whole SearchSummary, populated on
every record where a search ran (abstention included), null only when no
search ran. KeyOutcomeV1 is a persistence-local retype of common's retired
KeyOutcome (identical fields ⇒ identical asdict bytes) so the historical
and current vocabularies cannot mix (A19). V2 is WIRED as of P3a.2b; the V1
factory (`build_context_record_v1`) is retired with the legacy T2 family (§7)
— V1 remains parse-only for historical records.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from common.atomic_io import atomic_write_json
from common.llm_telemetry import safe_source_id
from common.types import (
    ContextTelemetry,
    MatchRecency,
    SearchBudgetRecord,
    SearchHitSummary,
    SearchStageSplit,
    SearchSummary,
    TierRecord,
)
from kdb_graph_search.constants import MAX_RESULTS

log = logging.getLogger(__name__)

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


# V1 persistence-local vocabulary (A19): identical field shape to common's
# KeyOutcome, so asdict bytes are unchanged — but a DISTINCT type, so the
# historical V1 disposition vocabulary can never mix with KeyOutcomeV2's.
KeyDispositionV1 = Literal["unresolved", "resolved_t2_seed", "resolved_already_t1",
                           "resolved_out_of_scope", "resolved_duplicate_seed"]
ConfiguredT2ModeV1 = Literal["structured", "layered", "legacy"]
EffectiveT2StrategyV1 = Literal[
    "structured_keys", "explicit_empty", "legacy_regex", "layered_union"]


@dataclass(frozen=True)
class KeyOutcomeV1:
    key: str
    disposition: KeyDispositionV1
    resolved: str | None
    target_first_run_id: str | None


@dataclass(frozen=True)
class ContextRecordV1:
    schema_version: Literal[1]
    run_id: str
    source_id: str
    status: ContextStatus
    configured_t2_mode: ConfiguredT2ModeV1
    effective_t2_strategy: EffectiveT2StrategyV1
    keys_emitted: list[str]
    key_outcomes: list[KeyOutcomeV1]
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
class ContextIntegrityIssue:
    path: str
    reason: Literal["malformed", "wrong_run"]
    detail: str


@dataclass(frozen=True)
class ContextLoadResult:
    records: list[ContextRecordV1 | ContextRecordV2]
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
    records: list[ContextRecordV1 | ContextRecordV2]
    expected_ids: set[str]
    matched_ids: set[str]
    coverage: float | None           # None when expected empty
    complete: bool                   # requires bool(expected_ids) — never vacuous
    integrity: ContextIntegrity


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


def _parse_outcome(raw: object, path: str) -> KeyOutcomeV1:
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
    return KeyOutcomeV1(key=key, disposition=disposition,  # type: ignore[arg-type]
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
    # #131: t1 is must-see, cap-EXEMPT — the cap governs the t2+t3 tail only.
    if t2.delivered + t3.delivered > page_cap:
        raise _err("page_cap",
                   f"t2+t3 delivered={t2.delivered + t3.delivered} "
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


# =====================================================================
# V2 — #123 P3a (§4.5): the search-aware record. UNWIRED until P3a.2b.
# =====================================================================

CONTEXT_RECORD_V2_SCHEMA_VERSION = 2

KeyOutcomeStatusV2 = Literal["matched", "unresolved"]
KeyOutcomeAnnotationV2 = Literal[
    "no_match", "cap_exhausted_possible", "unattributed_possible"]

_KEY_OUTCOME_STATUSES_V2 = frozenset({"matched", "unresolved"})
_KEY_OUTCOME_ANNOTATIONS_V2 = frozenset(
    {"no_match", "cap_exhausted_possible", "unattributed_possible"})
_MATCH_RECNECIES = frozenset({"cohort", "pre_run", "age_unknown"})
_SEARCH_STATUSES = frozenset(
    {"completed", "abstain_empty_space", "budget_exceeded", "selector_failure"})
_SEARCH_EXECUTIONS = frozenset(
    {"not_executed", "thin_attempted", "two_stage_attempted"})
_SEARCH_EVIDENCE_STATUSES = frozenset({"not_applicable", "complete", "partial"})
_SEARCH_QUERY_KINDS = frozenset({"state_b", "state_c"})
_SEARCH_WATCHED = frozenset(
    {"thin_retained_zero", "domain_missing", "budget_estimation_miss"})
_BUDGET_STAGES = frozenset({"thin_selection", "fat_selection"})
_BUDGET_DETECTED = frozenset({"pre_call", "post_call"})
_BUDGET_SIDES = frozenset({"input", "output"})
_SPLIT_STAGES = frozenset({"thin", "fat"})


@dataclass(frozen=True)
class KeyOutcomeV2:
    """§4.5 — one emitted expression's search outcome. The annotation
    vocabulary is CLOSED (B11): an `unresolved` outcome carries exactly one
    annotation and no provenance; a `matched` outcome carries a null
    annotation plus the hit's provenance stamp, with
    `matched_first_run_id is None ⟺ match_recency == "age_unknown"`."""
    expression: str
    status: KeyOutcomeStatusV2
    annotation: KeyOutcomeAnnotationV2 | None
    matched_first_run_id: str | None
    match_recency: MatchRecency | None


@dataclass(frozen=True)
class ContextRecordV2:
    schema_version: Literal[2]
    run_id: str
    source_id: str
    status: ContextStatus
    keys_emitted: list[str]
    key_outcomes: list[KeyOutcomeV2]
    t1: TierRecord
    t2: TierRecord
    t3: TierRecord
    candidate_universe_size: int | None
    domain_scope: str | None
    cold_start: bool | None
    page_cap: int
    search: SearchSummary | None

    def to_dict(self) -> dict:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class ContextTelemetryV2:
    """What a successful build knows. Persistence-local (mirrors the V1
    ContextFailureInput pattern). As of P3a.2b the rewired builder produces
    common's reshaped ContextTelemetry — field-identical to this type; the
    factory accepts both (§4.3)."""
    source_id: str
    keys_emitted: list[str]
    key_outcomes: list[KeyOutcomeV2]
    t1: TierRecord
    t2: TierRecord
    t3: TierRecord
    candidate_universe_size: int
    domain_scope: str | None
    cold_start: bool
    page_cap: int
    search: SearchSummary | None


@dataclass(frozen=True)
class ContextFailureInputV2:
    """What is knowable when the builder raised (A9): frontmatter keys, no
    graph observables. `search` is the adapter's summary when the search
    completed before the failure (B8, §4.1 step 6), null otherwise."""
    source_id: str
    keys_emitted: list[str]                      # frontmatter fallback (A9)
    domain_scope: str | None
    page_cap: int
    search: SearchSummary | None


def _json_ready(value: object) -> object:
    """Recursively normalize an asdict payload to JSON-native containers —
    tuples become lists — so `to_dict()` equals the on-disk bytes exactly.
    The parser restores tuples on read."""
    if isinstance(value, dict):
        return {k: _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(v) for v in value]
    return value


# ---------- V2 factory ----------


def build_context_record_v2(
    *,
    run_id: str,
    status: ContextStatus,
    telemetry: ContextTelemetryV2 | ContextTelemetry | None = None,
    failure_input: ContextFailureInputV2 | None = None,
) -> ContextRecordV2:
    """Build one V2 record. Invalid state combos RAISE (never guess) —
    mirrors the V1 invariant depth (§4.5):

    complete:        telemetry required; failure_input forbidden;
                     candidate_universe_size / cold_start non-null.
    context_failed:  telemetry forbidden; failure_input required; observables
                     null; zero tiers; empty key_outcomes.

    `search` is unconstrained in BOTH statuses — populated whenever a search
    ran (abstention included, A10), null only when no search ran.

    The telemetry annotation is a union: P3a.2b's rewired builder produces
    common's reshaped ContextTelemetry, field-identical to ContextTelemetryV2
    (the persistence-local type predates the rewiring, §4.3) — both are
    accepted; only the fields below are read.
    """
    if status == "complete":
        if telemetry is None:
            raise ContextRecordError("status='complete' requires telemetry")
        if failure_input is not None:
            raise ContextRecordError("status='complete' forbids failure_input")
        if telemetry.candidate_universe_size is None or telemetry.cold_start is None:
            raise ContextRecordError(
                "status='complete' requires non-null observables "
                "(candidate_universe_size / cold_start)")
        return ContextRecordV2(
            schema_version=CONTEXT_RECORD_V2_SCHEMA_VERSION,
            run_id=run_id,
            source_id=telemetry.source_id,
            status="complete",
            keys_emitted=list(telemetry.keys_emitted),
            key_outcomes=list(telemetry.key_outcomes),
            t1=telemetry.t1,
            t2=telemetry.t2,
            t3=telemetry.t3,
            candidate_universe_size=telemetry.candidate_universe_size,
            domain_scope=telemetry.domain_scope,
            cold_start=telemetry.cold_start,
            page_cap=telemetry.page_cap,
            search=telemetry.search,
        )
    if status == "context_failed":
        if failure_input is None:
            raise ContextRecordError("status='context_failed' requires failure_input")
        if telemetry is not None:
            raise ContextRecordError("status='context_failed' forbids telemetry")
        return ContextRecordV2(
            schema_version=CONTEXT_RECORD_V2_SCHEMA_VERSION,
            run_id=run_id,
            source_id=failure_input.source_id,
            status="context_failed",
            keys_emitted=list(failure_input.keys_emitted),
            key_outcomes=[],
            t1=_ZERO_TIER,
            t2=_ZERO_TIER,
            t3=_ZERO_TIER,
            candidate_universe_size=None,
            domain_scope=failure_input.domain_scope,
            cold_start=None,
            page_cap=failure_input.page_cap,
            search=failure_input.search,
        )
    raise ContextRecordError(f"unknown context record status: {status!r}")


# ---------- key-outcome projection (§4.5, A6) ----------


def project_key_outcomes_v2(
    *,
    keys_emitted: tuple[str, ...] | list[str],
    rendered_expressions: tuple[str, ...] | list[str],
    unresolved_expressions: tuple[str, ...] | list[str],
    search: SearchSummary,
) -> list[KeyOutcomeV2]:
    """Derive per-expression outcomes from the adapter's SearchSummary.

    Alignment is POSITIONAL: keys_emitted carries the ORIGINAL expression
    while hits and the unresolved set name the RENDERED form (truncation
    happens upstream) — the projection aligns by index, never by string
    equality. Every expression must be in EXACTLY ONE partition — the
    unresolved set or some hit's matched_expressions — else the projection
    refuses (A6 fail-closed; never guess, never re-derive).

    The controller-level cap/attribution flags do not ride SearchSummary,
    so the unresolved annotation derives from observables: an exhausted hit
    cap (hits == MAX_RESULTS) explains EVERY unresolved expression
    (cap_exhausted_possible, precedence pinned here); otherwise unattributed
    hits only POSSIBLY do (unattributed_possible); else no_match. A matched
    stamp comes from the FIRST hit in fat-ranked order.
    """
    if len(keys_emitted) != len(rendered_expressions):
        raise ContextRecordError(
            f"rendered_expressions misaligned with keys_emitted: "
            f"{len(rendered_expressions)} rendered for {len(keys_emitted)} keys")
    unresolved = set(unresolved_expressions)
    cap_exhausted = len(search.hits) >= MAX_RESULTS
    outcomes: list[KeyOutcomeV2] = []
    for original, rendered in zip(keys_emitted, rendered_expressions):
        if rendered in unresolved:
            if cap_exhausted:
                annotation: KeyOutcomeAnnotationV2 = "cap_exhausted_possible"
            elif search.unattributed_hit_count > 0:
                annotation = "unattributed_possible"
            else:
                annotation = "no_match"
            outcomes.append(KeyOutcomeV2(
                expression=original, status="unresolved", annotation=annotation,
                matched_first_run_id=None, match_recency=None))
            continue
        for hit in search.hits:      # hits are fat-ranked: highest-ranked wins
            if rendered in hit.matched_expressions:
                outcomes.append(KeyOutcomeV2(
                    expression=original, status="matched", annotation=None,
                    matched_first_run_id=hit.first_run_id,
                    match_recency=hit.match_recency))
                break
        else:
            raise ContextRecordError(
                f"partition violation: expression {rendered!r} is in neither "
                "the unresolved set nor any hit's matched_expressions")
    return outcomes


# ---------- V2 writer ----------


def write_context_record_v2(record: ContextRecordV2, state_root: Path) -> Path | None:
    """Persist one V2 record under `runs/<run_id>/context/`. WARN-ONLY on
    write failure (V1 convention) — the record is audit evidence; it must
    never affect the source outcome. Returns the path, None on failure."""
    path = (state_root / "runs" / record.run_id / "context"
            / f"{safe_source_id(record.source_id)}.json")
    try:
        atomic_write_json(path, record.to_dict())
    except Exception as e:
        log.warning("context record write failed for %s: %s", record.source_id, e)
        return None
    return path


# ---------- V2 strict parser ----------


def _require_bool(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise _err(path, f"expected a bool, got {value!r}")
    return value


def _require_number(value: object, path: str) -> int | float:
    # bool-as-number rejects: True/False are ints in Python but never measures.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _err(path, f"expected a number, got {value!r}")
    return value


def _optional_str(value: object, path: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise _err(path, f"expected null or str, got {value!r}")
    return value  # type: ignore[return-value]


def _optional_count(value: object, path: str) -> int | None:
    if value is None:
        return None
    return _require_count(value, path)


def _optional_number(value: object, path: str) -> int | float | None:
    if value is None:
        return None
    return _require_number(value, path)


def _require_list(value: object, path: str) -> list:
    if not isinstance(value, list):
        raise _err(path, f"expected a list, got {value!r}")
    return value


def _require_enum_list(value: object, allowed: frozenset[str], path: str) -> list[str]:
    items = _require_list(value, path)
    for i, item in enumerate(items):
        _require_enum(item, allowed, f"{path}[{i}]")
    return items


def _require_int_list(value: object, path: str) -> list[int]:
    items = _require_list(value, path)
    if any(isinstance(i, bool) or not isinstance(i, int) for i in items):
        raise _err(path, f"expected a list of int, got {value!r}")
    return items


def _parse_outcome_v2(raw: object, path: str) -> KeyOutcomeV2:
    if not isinstance(raw, dict):
        raise _err(path, f"expected an outcome dict, got {raw!r}")
    expression = _require_str(raw.get("expression"), f"{path}.expression")
    status = _require_enum(raw.get("status"), _KEY_OUTCOME_STATUSES_V2,
                           f"{path}.status")
    annotation = raw.get("annotation")
    if annotation is not None:
        _require_enum(annotation, _KEY_OUTCOME_ANNOTATIONS_V2, f"{path}.annotation")
    stamp = raw.get("matched_first_run_id")
    if stamp is not None and (not isinstance(stamp, str) or not stamp):
        # null-or-nonempty-str — an EMPTY persisted stamp rejects (empty-stamp
        # normalization is upstream, never the parser's).
        raise _err(f"{path}.matched_first_run_id",
                   f"expected null or a non-empty str, got {stamp!r}")
    recency = raw.get("match_recency")
    if recency is not None:
        _require_enum(recency, _MATCH_RECNECIES, f"{path}.match_recency")
    if status == "matched":
        if annotation is not None:
            raise _err(f"{path}.annotation",
                       f"matched outcome carries an annotation {annotation!r}")
        if recency is None:
            raise _err(f"{path}.match_recency", "matched outcome requires a recency")
        if (stamp is None) != (recency == "age_unknown"):
            raise _err(f"{path}.match_recency",
                       f"stamp/recency mismatch: {stamp!r} vs {recency!r}")
    else:  # unresolved — annotation required, provenance forbidden
        if annotation is None:
            raise _err(f"{path}.annotation", "unresolved outcome requires an annotation")
        if stamp is not None or recency is not None:
            raise _err(path, "unresolved outcome carries provenance")
    return KeyOutcomeV2(
        expression=expression,
        status=status,  # type: ignore[arg-type]
        annotation=annotation,  # type: ignore[arg-type]
        matched_first_run_id=stamp,
        match_recency=recency,  # type: ignore[arg-type]
    )


def _parse_search_hit(raw: object, path: str) -> SearchHitSummary:
    if not isinstance(raw, dict):
        raise _err(path, f"expected a hit dict, got {raw!r}")
    slug = _require_str(raw.get("slug"), f"{path}.slug")
    first_run_id = raw.get("first_run_id")
    if first_run_id is not None and (not isinstance(first_run_id, str)
                                     or not first_run_id):
        raise _err(f"{path}.first_run_id",
                   f"expected null or a non-empty str, got {first_run_id!r}")
    recency = _require_enum(raw.get("match_recency"), _MATCH_RECNECIES,
                            f"{path}.match_recency")
    if (first_run_id is None) != (recency == "age_unknown"):
        raise _err(path, f"first_run_id/recency mismatch: "
                         f"{first_run_id!r} vs {recency!r}")
    matched = _require_str_list(raw.get("matched_expressions"),
                                f"{path}.matched_expressions")
    return SearchHitSummary(
        slug=slug, first_run_id=first_run_id,
        match_recency=recency,  # type: ignore[arg-type]
        matched_expressions=tuple(matched))


def _parse_budget_record_v2(raw: object, path: str) -> SearchBudgetRecord:
    if not isinstance(raw, dict):
        raise _err(path, f"expected a budget record dict, got {raw!r}")
    return SearchBudgetRecord(
        stage=_require_enum(raw.get("stage"), _BUDGET_STAGES, f"{path}.stage"),
        budget_estimate_tokens=_require_count(
            raw.get("budget_estimate_tokens"), f"{path}.budget_estimate_tokens"),
        selector_window=_require_count(
            raw.get("selector_window"), f"{path}.selector_window"),
        headroom_factor=_require_number(
            raw.get("headroom_factor"), f"{path}.headroom_factor"),
        visible_output_allowance=_require_count(
            raw.get("visible_output_allowance"), f"{path}.visible_output_allowance"),
        hidden_output_reserve=_require_count(
            raw.get("hidden_output_reserve"), f"{path}.hidden_output_reserve"),
        fits=_require_bool(raw.get("fits"), f"{path}.fits"),
        detected=_require_enum(raw.get("detected"), _BUDGET_DETECTED,
                               f"{path}.detected"),
        budget_side=_require_enum(raw.get("budget_side"), _BUDGET_SIDES,
                                  f"{path}.budget_side"),
        finish_reason_raw=_optional_str(
            raw.get("finish_reason_raw"), f"{path}.finish_reason_raw"),
        finish_reason_normalized=_optional_str(
            raw.get("finish_reason_normalized"), f"{path}.finish_reason_normalized"),
    )


def _parse_stage_split(raw: object, path: str) -> SearchStageSplit:
    if not isinstance(raw, dict):
        raise _err(path, f"expected a stage split dict, got {raw!r}")
    return SearchStageSplit(
        stage=_require_enum(raw.get("stage"), _SPLIT_STAGES, f"{path}.stage"),
        attempts=_require_count(raw.get("attempts"), f"{path}.attempts"),
        provider_input_tokens=_optional_count(
            raw.get("provider_input_tokens"), f"{path}.provider_input_tokens"),
        cost_usd=_require_number(raw.get("cost_usd"), f"{path}.cost_usd"),
    )


def _parse_search_summary(raw: object, path: str = "search") -> SearchSummary:
    """Strict reader for the embedded SearchSummary — rejects, never coerces;
    tuples are restored so dataclass equality with the built record holds."""
    if not isinstance(raw, dict):
        raise _err(path, f"expected a search section dict, got {raw!r}")
    return SearchSummary(
        search_ran=_require_bool(raw.get("search_ran"), f"{path}.search_ran"),
        query_kind=_require_enum(raw.get("query_kind"), _SEARCH_QUERY_KINDS,
                                 f"{path}.query_kind"),  # type: ignore[arg-type]
        status=_require_enum(raw.get("status"), _SEARCH_STATUSES, f"{path}.status"),
        failure_class=_optional_str(raw.get("failure_class"),
                                    f"{path}.failure_class"),
        execution=_require_enum(raw.get("execution"), _SEARCH_EXECUTIONS,
                                f"{path}.execution"),
        evidence_status=_require_enum(raw.get("evidence_status"),
                                      _SEARCH_EVIDENCE_STATUSES,
                                      f"{path}.evidence_status"),
        body_coverage=_optional_number(raw.get("body_coverage"),
                                       f"{path}.body_coverage"),
        query_truncated_indices=tuple(_require_int_list(
            raw.get("query_truncated_indices"), f"{path}.query_truncated_indices")),
        eligible_space_size=_require_count(
            raw.get("eligible_space_size"), f"{path}.eligible_space_size"),
        stage1_retained=_require_count(
            raw.get("stage1_retained"), f"{path}.stage1_retained"),
        stage2_pool_size=_require_count(
            raw.get("stage2_pool_size"), f"{path}.stage2_pool_size"),
        returned_entries=_require_count(
            raw.get("returned_entries"), f"{path}.returned_entries"),
        valid_entry_yield=_optional_number(
            raw.get("valid_entry_yield"), f"{path}.valid_entry_yield"),
        unattributed_hit_count=_require_count(
            raw.get("unattributed_hit_count"), f"{path}.unattributed_hit_count"),
        retry_attempts=_require_count(
            raw.get("retry_attempts"), f"{path}.retry_attempts"),
        watched=tuple(_require_enum_list(raw.get("watched"), _SEARCH_WATCHED,
                                         f"{path}.watched")),
        concordance=_optional_number(raw.get("concordance"), f"{path}.concordance"),
        selector_provider=_require_str(raw.get("selector_provider"),
                                       f"{path}.selector_provider"),
        selector_model=_require_str(raw.get("selector_model"),
                                    f"{path}.selector_model"),
        selector_route=_require_str(raw.get("selector_route"),
                                    f"{path}.selector_route"),
        latency_ms=_require_count(raw.get("latency_ms"), f"{path}.latency_ms"),
        cost_usd=_require_number(raw.get("cost_usd"), f"{path}.cost_usd"),
        budget_records=tuple(
            _parse_budget_record_v2(b, f"{path}.budget_records[{i}]")
            for i, b in enumerate(
                _require_list(raw.get("budget_records"), f"{path}.budget_records"))),
        stage2_budget_bound=_require_bool(
            raw.get("stage2_budget_bound"), f"{path}.stage2_budget_bound"),
        stage_splits=tuple(
            _parse_stage_split(s, f"{path}.stage_splits[{i}]")
            for i, s in enumerate(
                _require_list(raw.get("stage_splits"), f"{path}.stage_splits"))),
        artifact_path=_optional_str(raw.get("artifact_path"),
                                    f"{path}.artifact_path"),
        search_snapshot_hash=_optional_str(
            raw.get("search_snapshot_hash"), f"{path}.search_snapshot_hash"),
        space_entity_count=_require_count(
            raw.get("space_entity_count"), f"{path}.space_entity_count"),
        hits=tuple(
            _parse_search_hit(h, f"{path}.hits[{i}]")
            for i, h in enumerate(_require_list(raw.get("hits"), f"{path}.hits"))),
    )


def parse_context_record_v2(raw: dict) -> ContextRecordV2:
    """Strict v2 parser — rejects, never coerces. Raises ContextRecordError."""
    if not isinstance(raw, dict):
        raise _err("$", f"expected a record dict, got {raw!r}")
    version = raw.get("schema_version")
    if type(version) is not int or version != CONTEXT_RECORD_V2_SCHEMA_VERSION:
        raise _err("schema_version", f"missing/unsupported: {version!r}")

    run_id = _require_str(raw.get("run_id"), "run_id")
    source_id = _require_str(raw.get("source_id"), "source_id")
    status = _require_enum(raw.get("status"), _CONTEXT_STATUSES, "status")
    keys_emitted = _require_str_list(raw.get("keys_emitted"), "keys_emitted")
    raw_outcomes = raw.get("key_outcomes")
    if not isinstance(raw_outcomes, list):
        raise _err("key_outcomes", f"expected a list, got {raw_outcomes!r}")
    key_outcomes = [_parse_outcome_v2(o, f"key_outcomes[{i}]")
                    for i, o in enumerate(raw_outcomes)]
    t1 = _parse_tier(raw.get("t1"), "t1")
    t2 = _parse_tier(raw.get("t2"), "t2")
    t3 = _parse_tier(raw.get("t3"), "t3")
    page_cap = _require_count(raw.get("page_cap"), "page_cap")
    # #131: t1 is must-see, cap-EXEMPT — the cap governs the t2+t3 tail only.
    if t2.delivered + t3.delivered > page_cap:
        raise _err("page_cap",
                   f"t2+t3 delivered={t2.delivered + t3.delivered} "
                   f"> page_cap={page_cap}")
    domain_scope = raw.get("domain_scope")
    if domain_scope is not None and not isinstance(domain_scope, str):
        raise _err("domain_scope", f"expected null or str, got {domain_scope!r}")
    search_raw = raw.get("search")
    search = None if search_raw is None else _parse_search_summary(search_raw)

    candidate_universe_size = raw.get("candidate_universe_size")
    cold_start = raw.get("cold_start")

    if status == "complete":
        # Outcomes align 1:1 (positionally, emission order) with keys_emitted.
        if len(key_outcomes) != len(keys_emitted) or any(
                o.expression != k for o, k in zip(key_outcomes, keys_emitted)):
            raise _err("key_outcomes",
                       "complete record: outcomes do not align 1:1 with keys_emitted")
        candidate_universe_size = _require_count(
            candidate_universe_size, "candidate_universe_size")
        if not isinstance(cold_start, bool):
            raise _err("cold_start", f"expected bool, got {cold_start!r}")
    else:  # context_failed — observables null, zero tiers, empty outcomes
        for name, value in (("candidate_universe_size", candidate_universe_size),
                            ("cold_start", cold_start)):
            if value is not None:
                raise _err(name, f"context_failed requires null, got {value!r}")
        if key_outcomes:
            raise _err("key_outcomes", "context_failed requires empty outcomes")
        for name, tier in (("t1", t1), ("t2", t2), ("t3", t3)):
            if tier.candidates != 0 or tier.delivered != 0 or tier.slugs:
                raise _err(name, "context_failed requires zero tiers")

    return ContextRecordV2(
        schema_version=CONTEXT_RECORD_V2_SCHEMA_VERSION,
        run_id=run_id,
        source_id=source_id,
        status=status,  # type: ignore[arg-type]
        keys_emitted=keys_emitted,
        key_outcomes=key_outcomes,
        t1=t1,
        t2=t2,
        t3=t3,
        candidate_universe_size=candidate_universe_size,
        domain_scope=domain_scope,
        cold_start=cold_start,
        page_cap=page_cap,
        search=search,
    )


# ---------- dispatching reader (§4.5, #123 P3a.3) ----------


def parse_context_record(raw: dict) -> ContextRecordV1 | ContextRecordV2:
    """Version-dispatching strict reader — pre-reads `schema_version` and
    hands off to the matching parser (1 → v1, 2 → v2). Any other value
    (missing, non-int, unknown version) raises ContextRecordError; never
    coerces, never guesses."""
    if not isinstance(raw, dict):
        raise _err("$", f"expected a record dict, got {raw!r}")
    version = raw.get("schema_version")
    if version == CONTEXT_RECORD_SCHEMA_VERSION:
        return parse_context_record_v1(raw)
    if version == CONTEXT_RECORD_V2_SCHEMA_VERSION:
        return parse_context_record_v2(raw)
    raise _err("schema_version", f"missing/unsupported: {version!r}")
