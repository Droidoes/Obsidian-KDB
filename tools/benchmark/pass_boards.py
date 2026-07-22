"""tools.benchmark.pass_boards — per-pass leaderboard boards (Task #117).

Spec v0.3.1 D-117-1..10. Per-pass processing KPIs are recomputed at score
time from each row's run_state/ (load_run_measurements_with_stats →
compute_processing), mapped onto the canonical processing KPI names, and
scored through the §6 score_models machinery. Rows failing the per-board
completeness contract (D-117-5) are excluded from Borda and rendered
unranked — never scored pro-rata on missing evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

from common.measurement import load_run_measurements_with_stats
from compiler.kpi.processing import compute_processing
from compiler.kpi.score import GRAPH_WEIGHTS, TOP_WEIGHTS, score_models

GRAPH_KPIS = tuple(GRAPH_WEIGHTS)

SRC_RECOMPUTED = "run_state_recomputed"
SRC_PARTIAL = "run_state_partial"
SRC_FALLBACK = "measurements_fallback"

_AXES = ("quarantine_rate", "recovery_rate", "latency")
_SPLIT = {p: {canon: f"{canon}_{p}" for canon in _AXES} for p in ("pass1", "pass2")}

# Bounded header/loader deserialization failures — a bad run_state marks the
# ROW unranked (D-117-5), never aborts the whole command (R5-F1).
_HEADER_ERRORS = (OSError, json.JSONDecodeError, UnicodeDecodeError,
                  TypeError, AttributeError, ValueError, KeyError)


def effective_top_weights(pass_: str) -> dict:
    """Full-precision effective composite weights for a pass board (D-117-7).

    Pass-1 has no graph term: TOP_WEIGHTS pro-rates over the processing axes
    (2/3, 1/6, 1/6). Pass-2 uses the canonical 40/40/10/10.
    """
    if pass_ == "pass2":
        return dict(TOP_WEIGHTS)
    denom = 1.0 - TOP_WEIGHTS["graph"]
    return {
        "quarantine_rate": TOP_WEIGHTS["quarantine_rate"] / denom,
        "recovery_rate": TOP_WEIGHTS["recovery_rate"] / denom,
        "latency": TOP_WEIGHTS["latency"] / denom,
        "graph": 0.0,
    }


def _completeness(
    run_state: Path, pass_: str, header, stats: dict,
) -> list[str]:
    """D-117-5 per-board completeness contract → list of violated checks
    (empty = complete). `header` is None when measurement_header.json failed
    to parse."""
    problems: list[str] = []
    if header is None:
        return ["header_unparseable"]
    if not stats[f"{pass_}_dir_exists"]:
        problems.append(f"{pass_}_dir_missing")
    if stats[f"{pass_}_malformed"]:
        problems.append(f"{pass_}_malformed_files:{stats[f'{pass_}_malformed']}")
    if pass_ == "pass1":
        if stats["pass1_identified"] != header.p1_attempted:
            problems.append(
                f"pass1_sidecars:{stats['pass1_identified']}!=p1_attempted:{header.p1_attempted}")
        if stats["pass1_unique_source_ids"] != stats["pass1_identified"]:
            problems.append("pass1_duplicate_source_id")
    else:
        if stats["pass2_records"] != header.p2_attempted:
            problems.append(
                f"pass2_records:{stats['pass2_records']}!=p2_attempted:{header.p2_attempted}")
    return problems


def _assign_competition_ranks(ranking: list[dict]) -> None:
    """D-117-9: equal composites share a rank; the next rank skips (1, 1, 3)."""
    rank = 0
    prev: float | None = None
    for i, row in enumerate(ranking, start=1):
        c = row.get("composite") or 0.0
        if prev is None or c != prev:
            rank = i
        row["rank"] = rank
        prev = c


def _valid_int(v) -> bool:
    """Non-boolean int (R7-F1: bool is an int subclass — excluded)."""
    return isinstance(v, int) and not isinstance(v, bool)


def _fallback_raw(
    fallback_diag: dict, graph_scored: dict, pass_: str, meas_header: dict,
) -> dict:
    """Best raw evidence available without (a usable) run_state: legacy
    measurements carry the quarantine/latency per-pass splits and the graph
    KPIs; the measurements header still yields the Pass-1 dispositions and
    eligibility (R6-F2). Coverage is explicitly None (unknowable without
    run_state). Every header-derived value is type-guarded BEFORE arithmetic
    (R7-F1) — a wrong-typed measurements header degrades to None, never
    aborts the command. p1_failed computes for all-zero-but-valid fields
    (0 is a real disposition count)."""
    raw = {k: v for k, v in fallback_diag.items() if k.endswith(f"_{pass_}")}
    if pass_ == "pass2":
        raw.update({k: graph_scored.get(k) for k in GRAPH_KPIS})
        p1a = meas_header.get("p1_attempted")
        sig = meas_header.get("signal")
        noi = meas_header.get("noise")
        raw["pass2_eligibility_rate"] = (
            sig / p1a if (_valid_int(p1a) and _valid_int(sig) and p1a > 0)
            else None)
        raw["pass2_measurement_coverage"] = None
        raw["p1_noise"] = noi if _valid_int(noi) else None
        raw["p1_failed"] = (
            p1a - sig - noi
            if all(_valid_int(v) for v in (p1a, sig, noi)) else None)
    return raw


def _missing_from(raw: dict, pass_: str) -> list[str]:
    """Canonical KPI names with no available evidence in `raw` (R5-F3)."""
    missing = [c for c in _AXES if raw.get(f"{c}_{pass_}") is None]
    if pass_ == "pass2":
        missing += [k for k in GRAPH_KPIS if raw.get(k) is None]
    return missing


def _build_row(
    runs_root: Path, run_dir: str, model_key: str, pass_: str,
    graph_scored: dict, fallback_diag: dict, meas_header: dict,
) -> dict:
    """Build one board row. Returns {"ranked": bool, ...}. Ranked and
    unranked rows carry the SAME raw_values evidence contract (R5-F3)."""
    split = _SPLIT[pass_]
    run_state = runs_root / run_dir / "run_state"
    if not run_state.is_dir():
        # No run_state at all → measurements fallback (D-117-5).
        raw = _fallback_raw(fallback_diag, graph_scored, pass_, meas_header)
        return {
            "ranked": False,
            "measurement_source": SRC_FALLBACK,
            "missing_kpis": _missing_from(raw, pass_),
            "completeness_errors": ["run_state_missing"],
            "raw_values": raw,
        }
    try:
        header, calls, stats = load_run_measurements_with_stats(run_state)
    except _HEADER_ERRORS:
        # run_state present but unloadable (bad header JSON, wrong top-level
        # type, missing/wrong-typed required fields, bad encoding) → partial,
        # never abort. missing_kpis reflects the actual fallback evidence —
        # an empty list is valid when a completeness violation is the reason.
        raw = _fallback_raw(fallback_diag, graph_scored, pass_, meas_header)
        return {
            "ranked": False,
            "measurement_source": SRC_PARTIAL,
            "missing_kpis": _missing_from(raw, pass_),
            "completeness_errors": ["header_unparseable"],
            "raw_values": raw,
        }
    problems = _completeness(run_state, pass_, header, stats)
    diag = compute_processing(header, calls)["diagnostic"]
    # Assemble the full raw evidence ONCE (R5-F3) — retry/cost/unknown, and
    # on pass2 the graph raws + coverage + dispositions.
    raw = {src: diag.get(src) for src in split.values()}
    raw[f"retry_load_{pass_}"] = diag.get(f"retry_load_{pass_}")
    raw[f"cost_usd_{pass_}"] = diag.get(f"cost_usd_{pass_}")
    raw[f"cost_unknown_calls_{pass_}"] = diag.get(f"cost_unknown_calls_{pass_}")
    if pass_ == "pass2":
        for k in GRAPH_KPIS:
            raw[k] = graph_scored.get(k)
        raw["pass2_eligibility_rate"] = (
            header.signal / header.p1_attempted if header.p1_attempted else None)
        raw["pass2_measurement_coverage"] = (
            stats["pass2_records"] / header.p2_attempted
            if header.p2_attempted else None)
        raw["p1_noise"] = header.noise
        raw["p1_failed"] = header.p1_attempted - header.signal - header.noise
    scored = {canon: diag.get(src) for canon, src in split.items()}
    if pass_ == "pass2":
        scored.update({k: graph_scored.get(k) for k in GRAPH_KPIS})
    pass_calls = [c for c in calls if c.pass_ == pass_]
    loaded = len(pass_calls)
    if pass_ == "pass1" and not problems:
        expected = header.p1_attempted - stats["pass1_skipped"]
        if loaded != expected:
            problems.append(f"pass1_loaded:{loaded}!=expected:{expected}")
    # D-117-5 (e): every required KPI input must be present — a count-complete
    # row with zero-token (None) axes, or a missing/None graph KPI on the
    # Pass-2 board, is unranked rather than pro-rated on partial evidence.
    required = list(_AXES) + (list(GRAPH_KPIS) if pass_ == "pass2" else [])
    missing = [k for k in required if scored.get(k) is None]
    if problems or missing:
        return {
            "ranked": False,
            "measurement_source": SRC_PARTIAL,
            "missing_kpis": missing,              # canonical KPI names only
            "completeness_errors": problems,      # contract violations, separate
            "raw_values": raw,
        }
    return {
        "ranked": True,
        "measurement_source": SRC_RECOMPUTED,
        "scored": scored,
        "raw_values": raw,
    }


def build_pass_board(
    models_to_rundir: dict[str, str],
    runs_root: Path,
    pass_: str,
    *,
    graph_scored_by_model: dict[str, dict],
    fallback_diag_by_model: dict[str, dict],
    header_by_model: dict[str, dict] | None = None,
) -> dict:
    """Build one pass board (payload shape: see plan Interfaces).

    header_by_model: measurements.json headers keyed by model row — feeds
    header-derived fallback evidence (R6-F2). The CLI always passes it;
    default None (→ {}) keeps older fixtures usable, degrading fallback
    dispositions/eligibility to None."""
    header_by_model = header_by_model or {}
    models: list[dict] = []
    unranked: list[dict] = []
    raw_by_model: dict[str, dict] = {}
    src_by_model: dict[str, str] = {}
    for model_key, run_dir in models_to_rundir.items():
        row = _build_row(runs_root, run_dir, model_key, pass_,
                         graph_scored_by_model.get(model_key, {}),
                         fallback_diag_by_model.get(model_key, {}),
                         header_by_model.get(model_key, {}))
        if row["ranked"]:
            models.append({"model": model_key, "scored": row["scored"]})
            raw_by_model[model_key] = row["raw_values"]
            src_by_model[model_key] = row["measurement_source"]
        else:
            unranked.append({
                "model": model_key,
                "run_dir": run_dir,
                "measurement_source": row["measurement_source"],
                "missing_kpis": row["missing_kpis"],
                "completeness_errors": row.get("completeness_errors", []),
                "raw_values": row["raw_values"],
            })

    result = score_models(models)
    ranking = sorted(
        (
            {
                "model": m,
                "composite": e["composite"],
                "composite_pre_penalty": e["composite_pre_penalty"],
                "penalty": e["penalty"],
                "weakest_kpi": e["weakest_kpi"],
                "graph_score": e["graph_score"],
                "per_kpi_borda": e["per_kpi_borda"],
            }
            for m, e in result["per_model"].items()
        ),
        key=lambda r: (-(r["composite"] or 0.0), r["model"]),
    )
    _assign_competition_ranks(ranking)
    for r in ranking:
        r["measurement_source"] = src_by_model[r["model"]]
        r["raw_values"] = raw_by_model[r["model"]]

    return {
        "models": dict(models_to_rundir),
        "board_scope": pass_,
        "effective_top_weights": effective_top_weights(pass_),
        "ranking": ranking,
        "unranked": unranked,
        "top_weights": result["top_weights"],
        "graph_weights": result["graph_weights"],
        "penalty_params": result["penalty_params"],
        "updated_at": "",   # injected by the caller (shared stamp, D-117-10)
    }
