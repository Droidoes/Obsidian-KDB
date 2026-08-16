"""
Measurement dataclasses for the KDB benchmark pipeline (B1 design).

These are *projections* over existing telemetry (Pass-2 RespStatsRecord,
Pass-1 sidecar) — not a new persistent store.  The KPI layer consumes
these structures to compute per-run scoring metrics.

`common` is a leaf package: only stdlib imports are allowed here.
"""
from __future__ import annotations

import json
import dataclasses
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PassCallMeasurement:
    """Logical projection of one LLM pass-call's telemetry for KPI scoring."""

    run_id: str
    source_id: str
    pass_: str                  # "pass1" | "pass2" (trailing _ avoids keyword clash)
    provider: str
    model: str
    prompt_version: str
    final_status: str
    attempts: int
    syntax_repaired: bool
    slug_coerced: bool
    token_overrun: bool
    total_input_tokens: int
    total_output_tokens: int
    total_latency_ms: int
    call_count: int
    final_attempt_index: int
    source_words: int
    parse_ok: bool
    schema_ok: bool
    semantic_ok: bool | None
    boundary_recovered: bool = False
    cost_usd: float | None = None
    # #119 watched diagnostics (D-BQ-3): projected from the normalization
    # boundary's telemetry; NEVER scored axes. None only for Pass-1
    # projections (no normalization data); Pass-2 records without either
    # field (pre-#119 records without decision lists) project a
    # compatibility count of 0 (the len(... or []) fallback in from_pass2).
    normalization_decision_count: int | None = None
    summary_identity_derived: bool | None = None

    @classmethod
    def from_pass1(cls, sidecar: dict, *, run_id: str) -> "PassCallMeasurement":
        """Project a Pass-1 sidecar dict into a PassCallMeasurement.

        Sidecar layout (from ingestion/enrich/replay_archive.py + enrich.py):
          sidecar["source_id"]        — vault-relative path
          sidecar["request"]["provider"]  — LLM provider (may be absent on skipped)
          sidecar["request"]["model"]     — LLM model name
          sidecar["raw_response"]["final_status"]          — "clean" | "repaired" | "quarantined" | ...
          sidecar["raw_response"]["syntax_repaired"]       — bool
          sidecar["raw_response"]["total_input_tokens"]    — int
          sidecar["raw_response"]["total_output_tokens"]   — int
          sidecar["raw_response"]["total_latency_ms"]      — int
          sidecar["raw_response"]["call_count"]            — int (0 for skipped)
          sidecar["raw_response"]["final_attempt_index"]   — int
          sidecar["parsed_envelope"]    — dict or None (None on failure/quarantine path)
          sidecar["parsed_envelope"]["prompt_version"]     — str (when envelope present)
          sidecar["parsed_envelope"]["model"]              — str (when envelope present)

        Design choices:
        - `attempts`: derived from `raw_response["call_count"]` — the ladder tracks
          attempts via call_count; there is no separate "attempts" key in the sidecar.
        - `parse_ok` / `schema_ok`: derived from final_status != "quarantined".  A
          non-quarantined Pass-1 by definition parsed and validated its envelope; a
          quarantined one failed at or before that gate.
        - `semantic_ok`: always None — Pass-1 has no semantic validation gate.
        - `slug_coerced`: always False — Pass-1 slug-coercion applies to Pass-2 only.
        - `token_overrun`: always False — not tracked in the Pass-1 sidecar.
        - `source_words`: always 0 — not stored in the sidecar (Pass-2-only diagnostic).
        - `model`: prefer `request["model"]` (present on all write paths including
          failures) over `parsed_envelope["model"]` (absent when envelope is None).
        - `prompt_version`: from `parsed_envelope["prompt_version"]` when the envelope
          is present; else "" (failure/quarantine paths have no envelope).
        - `cost_usd`: sidecar top-level; absent projects as None (#117). The
          #110-deferred failed-source 0.0 projects as-is — the KPI layer
          decides what zero means.
        - `normalization_decision_count` / `summary_identity_derived`: always
          None — the #119 normalization boundary is Pass-2-only.
        """
        req = sidecar.get("request", {})
        raw = sidecar.get("raw_response", {})
        envelope = sidecar.get("parsed_envelope") or {}

        final_status = raw.get("final_status", "")
        not_quarantined = final_status != "quarantined"

        return cls(
            run_id=run_id,
            source_id=sidecar["source_id"],
            pass_="pass1",
            provider=req.get("provider", ""),
            model=req.get("model", ""),
            prompt_version=envelope.get("prompt_version", ""),
            final_status=final_status,
            # attempts: use call_count as the Pass-1 equivalent of SDK attempt count.
            # call_count is 0 for skipped sources, 1+ for real LLM calls.
            attempts=raw.get("call_count", 1),
            syntax_repaired=raw.get("syntax_repaired", False),
            slug_coerced=False,    # Pass-1 does not perform slug coercion
            token_overrun=False,   # not tracked in Pass-1 sidecar
            total_input_tokens=raw.get("total_input_tokens", 0),
            total_output_tokens=raw.get("total_output_tokens", 0),
            total_latency_ms=raw.get("total_latency_ms", 0),
            call_count=raw.get("call_count", 1),
            final_attempt_index=raw.get("final_attempt_index", 1),
            source_words=0,        # not stored in Pass-1 sidecar
            # parse_ok / schema_ok: a non-quarantined Pass-1 envelope passed both
            # parse and schema validation by definition; quarantined = failed.
            parse_ok=not_quarantined,
            schema_ok=not_quarantined,
            semantic_ok=None,      # Pass-1 has no semantic validation gate
            boundary_recovered=False,  # Pass-1 has no parse-stage boundary recovery
            cost_usd=sidecar.get("cost_usd"),   # top-level; absent → None (#117)
        )

    @classmethod
    def from_pass2(cls, rec: dict) -> "PassCallMeasurement":
        """Project a RespStatsRecord dict (from to_dict() or persisted JSON)
        into a PassCallMeasurement.

        RespStatsRecord has no prompt_version field; prompt_version is set to "".

        Back-compat: records persisted before Task #109 (missing total_input_tokens,
        total_output_tokens, total_latency_ms, call_count, final_attempt_index) fall
        back to the single-attempt per-call values so older runs still project cleanly.

        #119 watched diagnostics (D-BQ-3, never scored axes):
        normalization_decision_count projects the PERSISTED
        RespStatsRecord.normalization_decision_count when present (the true
        total, intact even when the decision sample list is truncated at the
        50-entry cap), falling back to len(normalization_decisions or []) for
        pre-#119 records without the persisted count.
        summary_identity_derived projects the flag; both are None-tolerant.
        """
        persisted_count = rec.get("normalization_decision_count")
        return cls(
            run_id=rec["run_id"],
            source_id=rec["source_id"],
            pass_="pass2",
            provider=rec["provider"],
            model=rec["model"],
            # RespStatsRecord has no prompt_version; closest field is prompt_hash (a
            # hash, not a version string).  Emit "" so callers can fill in from
            # run-level metadata if needed.
            prompt_version="",
            final_status=rec.get("final_status") or "",
            # Fix 1 (#111 retry-telemetry): attempts reflects the compile
            # re-prompt count ONLY.  `final_attempt_index` captures every
            # content-driven re-prompt (schema/semantic retry, in-place
            # repair), so a re-prompt-only recovery (final_attempt_index==2)
            # is visible to the KPI layer.  SDK transient retries
            # (`rec["attempts"]` = model_response.attempts: 429/5xx/network
            # flakiness) are deliberately excluded — they are infrastructure
            # noise, not content/model recoveries, and the KPI layer keys
            # recovery_rate/retry_load off attempts > 1.  This matches
            # from_pass1's `call_count` and Fix 3a's compile_meta.attempts
            # (state["compile_attempts"]), which also exclude SDK retries.
            # Falls back to 1 for pre-#109 records.
            attempts=rec.get("final_attempt_index", 1),
            syntax_repaired=rec.get("syntax_repaired", False),
            slug_coerced=rec.get("slug_coerced", False),
            token_overrun=rec.get("token_overrun", False),
            # Aggregate totals — new in #109.  Fall back to single-attempt values
            # for records written before these fields existed.
            total_input_tokens=rec.get("total_input_tokens", rec.get("input_tokens", 0)),
            total_output_tokens=rec.get("total_output_tokens", rec.get("output_tokens", 0)),
            total_latency_ms=rec.get("total_latency_ms", rec.get("latency_ms", 0)),
            call_count=rec.get("call_count", 1),
            final_attempt_index=rec.get("final_attempt_index", 1),
            source_words=rec.get("source_words", 0),
            parse_ok=rec.get("parse_ok", False),
            schema_ok=rec.get("schema_ok", False),
            semantic_ok=rec.get("semantic_ok"),
            # #114 parse-stage boundary recovery; absent on pre-#114 records.
            boundary_recovered=rec.get("boundary_recovered", False),
            cost_usd=rec.get("cost_usd"),   # absent on pre-#110 records → None (#117)
            # #119 watched diagnostics: persisted count wins over the (possibly
            # capped) decision-sample list length; absent count → list length
            # (pre-#119 records); absent list too → 0. Flag projects as-is.
            normalization_decision_count=(
                persisted_count if persisted_count is not None
                else len(rec.get("normalization_decisions") or [])),
            summary_identity_derived=rec.get("summary_identity_derived"),
        )


@dataclass(frozen=True)
class RunMeasurementHeader:
    """Per-run metadata projection consumed by the KPI scoring layer."""

    run_id: str
    corpus_fingerprint: str
    pass1_prompt_version: str
    pass2_prompt_version: str
    scanned: int
    to_compile: int
    signal: int
    noise: int
    p1_attempted: int
    p2_attempted: int
    release_version: str = ""
    # SHA-256 of the loaded Pass-2 system prompt text (post-#115, D-115-13).
    # "" on historical (pre-#115) headers — see load_run_measurements.
    pass2_system_prompt_sha256: str = ""
    # Task #122 §7: False means the run did NOT complete the finalize boundary
    # (audit-only artifact — score-skipped at the §7c gate). Historical
    # headers missing the field load as True (dataclass default).
    finalize_ran: bool = True
    # #123 P3a.4 (§4.7): pass-1.5 search counters — attempted = envelope
    # writes attempted (one per search run); written = writes that succeeded.
    # Write failures = attempted − written. Historical headers load as 0.
    searches_attempted: int = 0
    searches_written: int = 0


# ---------------------------------------------------------------------------
# Run-directory loader (B1 §3)
# ---------------------------------------------------------------------------

_HEADER_INT_FIELDS = ("scanned", "to_compile", "signal", "noise",
                      "p1_attempted", "p2_attempted",
                      "searches_attempted", "searches_written")


def _validate_header_types(header: "RunMeasurementHeader") -> None:
    """Type guard (#117 R6-F1/R7-F2, BOTH loader paths): header numeric fields
    must be real ints (bool excluded) — else KPI computation fails mid-board
    outside every guard. Strict path: raises (emit fails safely, as today).
    Tolerant path: raises so the board builder marks the row unranked."""
    for f in _HEADER_INT_FIELDS:
        v = getattr(header, f)
        if not isinstance(v, int) or isinstance(v, bool):
            raise TypeError(
                f"header field {f!r} must be int, got {type(v).__name__}")
    # Task #122 §7: the finalize_ran stamp must be a real bool.
    if not isinstance(header.finalize_ran, bool):
        raise TypeError(
            f"header field 'finalize_ran' must be bool, got {type(header.finalize_ran).__name__}")


_MEASUREMENT_INT_FIELDS = ("attempts", "call_count", "total_input_tokens",
                           "total_output_tokens", "total_latency_ms")


def _valid_measurement(m: "PassCallMeasurement") -> bool:
    """Type guard (#117 R6-F1/R7-F2, BOTH loader paths): KPI-relevant numeric
    fields must be real ints; cost_usd None or numeric. Strict path raises
    TypeError on False; tolerant path counts the record malformed."""
    for f in _MEASUREMENT_INT_FIELDS:
        v = getattr(m, f)
        if not isinstance(v, int) or isinstance(v, bool):
            return False
    return m.cost_usd is None or isinstance(m.cost_usd, (int, float))


def _load_run_measurements(
    run_dir: Path,
    *,
    tolerate_malformed: bool,
    collect_stats: bool,
) -> tuple["RunMeasurementHeader", list["PassCallMeasurement"], dict]:
    """Shared loader core.

    Layout (verified from kdb_graph_orchestrator + kdb_graph_compiler source):
      <run_dir>/measurement_header.json        — RunMeasurementHeader JSON
      <run_dir>/pass1/*.json                   — Pass-1 sidecars
      <run_dir>/pass2/*.json                   — Pass-2 RespStatsRecord JSONs

    Pass-1 sidecar identification: a file is a sidecar iff it contains both
    "source_id" and "raw_response" keys. Skip predicate: outcome ==
    "enrich_skipped" (empty sources; no LLM call was made). Quarantined /
    failed sidecars ARE included — the benchmark's primary failure-mode
    signal.

    tolerate_malformed=False (production): any malformed/unloadable file
    raises, exactly as the pre-#117 loader did — emit_run_kpis fails safely
    rather than emitting KPIs from partial evidence.
    tolerate_malformed=True (score-time stats loader): bad files are counted
    in stats["*_malformed"] and skipped, so the #117 completeness contract
    can mark the row unranked instead of aborting all three boards.
    "Malformed" covers unparseable JSON AND structurally valid records that
    fail projection (KeyError/TypeError/AttributeError/ValueError) or carry
    wrong-typed numeric fields (R6-F1).
    """
    header_path = run_dir / "measurement_header.json"
    header_data = json.loads(header_path.read_text(encoding="utf-8"))
    # Forward-compat + back-fill (#117/#115): tolerate header keys newer
    # than this dataclass (e.g. future stamp fields) so score-time recompute
    # works across releases; fields absent on old headers (release_version
    # pre-#111, pass2_system_prompt_sha256 pre-#115) fall back to the
    # dataclass defaults.
    known = {f.name for f in dataclasses.fields(RunMeasurementHeader)}
    header = RunMeasurementHeader(
        **{k: v for k, v in header_data.items() if k in known})
    run_id = header.run_id
    # Type guard on BOTH paths (R7-F2): strict raises (same exception class
    # emit would hit today), tolerant lets the board builder mark the row.
    _validate_header_types(header)

    stats = {
        "pass1_dir_exists": (run_dir / "pass1").is_dir(),
        "pass2_dir_exists": (run_dir / "pass2").is_dir(),
        "pass1_identified": 0, "pass1_skipped": 0,
        "pass1_unique_source_ids": 0, "pass1_malformed": 0,
        "pass2_records": 0, "pass2_malformed": 0,
    }
    _PROJECTION_ERRORS = (json.JSONDecodeError, UnicodeDecodeError,
                          KeyError, TypeError, AttributeError, ValueError)

    pass1: list[PassCallMeasurement] = []
    source_ids: set[str] = set()
    pass1_dir = run_dir / "pass1"
    if pass1_dir.is_dir():
        for p in sorted(pass1_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                identified = "source_id" in data and "raw_response" in data
                if identified:
                    stats["pass1_identified"] += 1
                    source_ids.add(data["source_id"])
            except _PROJECTION_ERRORS:
                if not tolerate_malformed:
                    raise
                stats["pass1_malformed"] += 1
                continue
            if not identified:
                continue
            if data.get("outcome") == "enrich_skipped":
                stats["pass1_skipped"] += 1
                continue
            try:
                m = PassCallMeasurement.from_pass1(data, run_id=run_id)
            except _PROJECTION_ERRORS:
                if not tolerate_malformed:
                    raise
                stats["pass1_malformed"] += 1
                continue
            if not _valid_measurement(m):
                if not tolerate_malformed:
                    raise TypeError(
                        f"pass1 measurement for {m.source_id!r} has "
                        "wrong-typed numeric fields")
                stats["pass1_malformed"] += 1
                continue
            pass1.append(m)
    stats["pass1_unique_source_ids"] = len(source_ids)

    pass2: list[PassCallMeasurement] = []
    pass2_dir = run_dir / "pass2"
    if pass2_dir.is_dir():
        for p in sorted(pass2_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                m = PassCallMeasurement.from_pass2(data)
            except _PROJECTION_ERRORS:
                if not tolerate_malformed:
                    raise
                stats["pass2_malformed"] += 1
                continue
            if not _valid_measurement(m):
                if not tolerate_malformed:
                    raise TypeError(
                        f"pass2 measurement for {m.source_id!r} has "
                        "wrong-typed numeric fields")
                stats["pass2_malformed"] += 1
                continue
            stats["pass2_records"] += 1
            pass2.append(m)

    if not collect_stats:
        stats = {}
    return header, pass1 + pass2, stats


def load_run_measurements(
    run_dir: Path,
) -> tuple["RunMeasurementHeader", list["PassCallMeasurement"]]:
    """Load all measurement projections for one run — STRICT (production
    path): malformed files raise, as before #117.

    Returns (header, measurements) where measurements is pass1_list +
    pass2_list (order is deterministic within each group via sorted glob).
    """
    header, measurements, _ = _load_run_measurements(
        run_dir, tolerate_malformed=False, collect_stats=False)
    return header, measurements


def load_run_measurements_with_stats(
    run_dir: Path,
) -> tuple["RunMeasurementHeader", list["PassCallMeasurement"], dict]:
    """Score-time variant (Task #117): tolerant of malformed files (counted
    in stats) and returns per-pass load statistics for the D-117-5
    completeness contract. Stats keys: pass1_dir_exists, pass2_dir_exists,
    pass1_identified, pass1_skipped, pass1_unique_source_ids,
    pass1_malformed, pass2_records, pass2_malformed."""
    return _load_run_measurements(
        run_dir, tolerate_malformed=True, collect_stats=True)


# ---------------------------------------------------------------------------
# #123 P3a.4 (§4.7) — SearchPassMeasurement: the pass-1.5 channel
#
# One measurement PER SEARCH (not per stage — avoids the pass-1
# duplicate_source_id completeness collision), computed by the search adapter
# from the in-memory GraphSearchResult/audit at run time — NEVER re-parsed
# from envelope bytes — and persisted as the additive "measurement" key of
# the search/*.json envelope file. The loader below is a NEW additive API:
# the existing tuple loaders, their shapes, and their callers are untouched
# (test_load_run_measurements_wrapper_unchanged_shape pins that).
# ---------------------------------------------------------------------------


class SearchMeasurementError(ValueError):
    """Strict parser/loader rejection — malformed persisted search
    measurements. Never coerces."""


@dataclass(frozen=True)
class SearchStageMeasurement:
    """Per-stage {thin, fat} token/cost/sent_bytes split (§4.7, B2/B10).
    provider_input_tokens is None when ANY attempt's count is unknown —
    never zero-coerced."""
    stage: str                      # "thin" | "fat"
    attempts: int
    provider_input_tokens: int | None
    cost_usd: float
    sent_bytes: int


@dataclass(frozen=True)
class SearchPassMeasurement:
    """One source search's run-time measurement (§4.7).

    `calls` is LOGICAL — one per source search (B10); `attempts` is the
    StageRecord count, INCLUDING attempts that received no provider
    response. `total_input_tokens` is None when ANY attempt's
    provider_input_tokens is None, accompanied by
    `input_token_unknown_attempts` — never silently zero-coerced. A21:
    there is deliberately NO total_output_tokens (output-side truncation is
    already observable via BudgetRecord.budget_side/finish_reason)."""
    run_id: str
    source_id: str
    pass_: str                      # always "pass1_5"
    provider: str
    model: str
    prompt_versions: dict[str, str | None]      # {"thin": ..., "fat": ...} (G1.3)
    status: str
    execution: str
    calls: int
    attempts: int
    total_input_tokens: int | None
    input_token_unknown_attempts: int
    stage_splits: tuple[SearchStageMeasurement, ...]
    total_latency_ms: int
    cost_usd: float
    search_snapshot_hash: str | None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ---------- strict parser ----------


def _serr(path: str, detail: str) -> SearchMeasurementError:
    return SearchMeasurementError(f"{path}: {detail}")


def _sreq_str(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise _serr(path, f"expected a str, got {value!r}")
    return value


def _sreq_int(value: object, path: str) -> int:
    # bool-as-int rejects: True/False are ints in Python but never counts.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _serr(path, f"expected a non-negative int, got {value!r}")
    return value


def _sreq_number(value: object, path: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _serr(path, f"expected a number, got {value!r}")
    return value


_MEASUREMENT_KEYS = frozenset({
    "run_id", "source_id", "pass_", "provider", "model", "prompt_versions",
    "status", "execution", "calls", "attempts", "total_input_tokens",
    "input_token_unknown_attempts", "stage_splits", "total_latency_ms",
    "cost_usd", "search_snapshot_hash",
})
_STAGE_SPLIT_KEYS = frozenset({
    "stage", "attempts", "provider_input_tokens", "cost_usd", "sent_bytes",
})
_STAGE_NAMES = frozenset({"thin", "fat"})


def _parse_stage_split(raw: object, path: str) -> SearchStageMeasurement:
    if not isinstance(raw, dict):
        raise _serr(path, f"expected a stage split dict, got {raw!r}")
    if set(raw) != _STAGE_SPLIT_KEYS:
        raise _serr(path, f"keys {sorted(raw)} != expected {sorted(_STAGE_SPLIT_KEYS)}")
    stage = raw["stage"]
    if stage not in _STAGE_NAMES:
        raise _serr(f"{path}.stage", f"expected one of {sorted(_STAGE_NAMES)}, got {stage!r}")
    tokens = raw["provider_input_tokens"]
    if tokens is not None:
        tokens = _sreq_int(tokens, f"{path}.provider_input_tokens")
    return SearchStageMeasurement(
        stage=stage,
        attempts=_sreq_int(raw["attempts"], f"{path}.attempts"),
        provider_input_tokens=tokens,
        cost_usd=_sreq_number(raw["cost_usd"], f"{path}.cost_usd"),
        sent_bytes=_sreq_int(raw["sent_bytes"], f"{path}.sent_bytes"),
    )


def parse_search_measurement(raw: object) -> SearchPassMeasurement:
    """Strict reader for the persisted run-time-computed measurement —
    rejects, never coerces. Raises SearchMeasurementError."""
    if not isinstance(raw, dict):
        raise _serr("$", f"expected a measurement dict, got {raw!r}")
    if set(raw) != _MEASUREMENT_KEYS:
        raise _serr("$", f"keys {sorted(raw)} != expected {sorted(_MEASUREMENT_KEYS)}")
    pass_ = raw["pass_"]
    if pass_ != "pass1_5":
        raise _serr("pass_", f"expected 'pass1_5', got {pass_!r}")
    versions = raw["prompt_versions"]
    if not isinstance(versions, dict) or set(versions) != {"thin", "fat"}:
        raise _serr("prompt_versions",
                    f"expected a {{thin, fat}} dict, got {versions!r}")
    for stage, version in versions.items():
        if version is not None and not isinstance(version, str):
            raise _serr(f"prompt_versions.{stage}",
                        f"expected null or str, got {version!r}")
    tokens = raw["total_input_tokens"]
    if tokens is not None:
        tokens = _sreq_int(tokens, "total_input_tokens")
    splits_raw = raw["stage_splits"]
    if not isinstance(splits_raw, list):
        raise _serr("stage_splits", f"expected a list, got {splits_raw!r}")
    snapshot = raw["search_snapshot_hash"]
    if snapshot is not None and not isinstance(snapshot, str):
        raise _serr("search_snapshot_hash",
                    f"expected null or str, got {snapshot!r}")
    return SearchPassMeasurement(
        run_id=_sreq_str(raw["run_id"], "run_id"),
        source_id=_sreq_str(raw["source_id"], "source_id"),
        pass_="pass1_5",
        provider=_sreq_str(raw["provider"], "provider"),
        model=_sreq_str(raw["model"], "model"),
        prompt_versions=dict(versions),
        status=_sreq_str(raw["status"], "status"),
        execution=_sreq_str(raw["execution"], "execution"),
        calls=_sreq_int(raw["calls"], "calls"),
        attempts=_sreq_int(raw["attempts"], "attempts"),
        total_input_tokens=tokens,
        input_token_unknown_attempts=_sreq_int(
            raw["input_token_unknown_attempts"], "input_token_unknown_attempts"),
        stage_splits=tuple(
            _parse_stage_split(s, f"stage_splits[{i}]")
            for i, s in enumerate(splits_raw)),
        total_latency_ms=_sreq_int(raw["total_latency_ms"], "total_latency_ms"),
        cost_usd=_sreq_number(raw["cost_usd"], "cost_usd"),
        search_snapshot_hash=snapshot,
    )


# ---------- run-directory loader (NEW additive API — B3) ----------


def _load_search_measurements(
    run_dir: Path,
    *,
    tolerate_malformed: bool,
) -> tuple[list[SearchPassMeasurement], dict]:
    """Shared loader core. Globs <run_dir>/search/*.json; a file is a search
    measurement iff it carries a "measurement" key (pre-P3a.4 envelopes
    without one are skipped — never identified, never malformed). Stats keys:
    pass1_5_dir_exists, pass1_5_identified, pass1_5_malformed."""
    search_dir = run_dir / "search"
    stats = {"pass1_5_dir_exists": search_dir.is_dir(),
             "pass1_5_identified": 0,
             "pass1_5_malformed": 0}
    out: list[SearchPassMeasurement] = []
    if search_dir.is_dir():
        for p in sorted(search_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                if not tolerate_malformed:
                    raise SearchMeasurementError(f"{p}: {e}") from e
                stats["pass1_5_malformed"] += 1
                continue
            if not isinstance(data, dict) or "measurement" not in data:
                continue
            stats["pass1_5_identified"] += 1
            try:
                out.append(parse_search_measurement(data["measurement"]))
            except SearchMeasurementError:
                if not tolerate_malformed:
                    raise
                stats["pass1_5_malformed"] += 1
                continue
    return out, stats


def load_search_measurements(run_dir: Path) -> list[SearchPassMeasurement]:
    """STRICT (production path): any malformed search file raises
    SearchMeasurementError — emit fails safely rather than emitting KPIs
    from partial evidence."""
    out, _ = _load_search_measurements(run_dir, tolerate_malformed=False)
    return out


def load_search_measurements_with_stats(
    run_dir: Path,
) -> tuple[list[SearchPassMeasurement], dict]:
    """Score-time variant: tolerant of malformed files (counted in stats) so
    the D-117-5 completeness contract can mark the row unranked instead of
    aborting the boards. Stats keys: pass1_5_dir_exists, pass1_5_identified,
    pass1_5_malformed."""
    return _load_search_measurements(run_dir, tolerate_malformed=True)
