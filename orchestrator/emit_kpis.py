"""emit_kpis — helper that assembles and writes benchmark/runs/<run_id>/measurements.json.

Called by kdb_orchestrate.run() when --emit-kpis is set, AFTER measurement_header.json
is written to the run dir and AFTER the Kuzu graph context manager has exited.

Design notes:
- The Kuzu connection is reopened read-only (the with-block has closed it by the
  time finalize artifacts and the header are written in `finally`).
- finalize_artifacts is read from state_root/runs/<run_id>/retraction.json when it
  exists (written by _finalize when cleanup ran). Re-running reap on the post-cleanup
  graph would return [] because the orphans are already retracted.
- The benchmark path (benchmark/runs/<run_id>/) is computed from the repo root
  (two parents up from this file) and is monkeypatchable in tests via
  `get_benchmark_runs_dir`.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import warnings
from pathlib import Path

from common.atomic_io import atomic_write_json
from common.measurement import RunMeasurementHeader, load_run_measurements
from compiler.kpi.processing import compute_processing
from compiler.kpi.graph import compute_graph
from compiler.kpi.report import render_report
from kdb_graph.graphdb import GraphDB

log = logging.getLogger(__name__)


def get_benchmark_runs_dir() -> Path:
    """Return the canonical benchmark/runs/ directory (repo root / benchmark / runs).

    Monkeypatch this in tests to redirect output to tmp_path.
    """
    return Path(__file__).resolve().parent.parent / "benchmark" / "runs"


def _gather_pass1_search_keys(run_dir: Path) -> list[str]:
    """Gather entity_search_keys from all Pass-1 sidecars in run_dir.

    Sidecar identification: flat *.json files in run_dir with both
    "source_id" and "raw_response" keys (same predicate as load_run_measurements).
    Returns the concatenated list (not deduplicated, order-preserving).
    None parsed_envelope on failure sidecars is guarded.
    """
    keys: list[str] = []
    for p in sorted(run_dir.glob("*.json")):
        if p.name == "measurement_header.json":
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "source_id" not in data or "raw_response" not in data:
            continue
        if data.get("outcome") == "enrich_skipped":
            continue
        envelope = data.get("parsed_envelope") or {}
        esks = envelope.get("entity_search_keys") or []
        if isinstance(esks, list):
            keys.extend(str(k) for k in esks if k)
    return keys


def _load_finalize_artifacts(state_root: Path, run_id: str) -> dict:
    """Load finalize artifacts from retraction.json if it exists.

    Using the persisted retraction.json is critical: by the time we reopen the
    graph, apply_cleanup has already retracted orphans from GraphDB, so
    reap_orphans_from_graph() would return [] — silently zeroing orphan_rate.
    """
    retraction_path = state_root / "runs" / run_id / "retraction.json"
    if retraction_path.exists():
        try:
            return json.loads(retraction_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"reaped": []}


def emit_run_kpis(
    *,
    run_id: str,
    run_dir: Path,
    graph_path: Path,
    state_root: Path,
    provider: str,
    model: str,
    header: RunMeasurementHeader,
) -> Path:
    """Compute and write benchmark/runs/<run_id>/measurements.json.

    The Kuzu graph is reopened read-only here (the main run's context manager
    has already closed it). compile_result.json must exist (finalize wrote it).

    Returns the path written.
    """
    # Load measurements (header already computed; pass it directly, reload calls)
    _hdr, calls = load_run_measurements(run_dir)

    # Compute PROCESSING KPIs
    proc = compute_processing(header, calls)

    # Load finalize artifacts (from persisted retraction.json, not re-running reap)
    finalize_artifacts = _load_finalize_artifacts(state_root, run_id)

    # Gather Pass-1 entity_search_keys
    pass1_search_keys = _gather_pass1_search_keys(run_dir) or None

    # Compute GRAPH KPIs (reopen read-only after the context manager exited)
    with GraphDB(graph_path, read_only=True) as gdb:
        graph = compute_graph(
            gdb.conn, finalize_artifacts,
            pass1_search_keys=pass1_search_keys,
        )

    # Emit provider + model explicitly in the header. `model` is the unique
    # slug the leaderboard keys on (one row per model — no group_key/grouping).
    payload = {
        "header": {**dataclasses.asdict(header), "provider": provider, "model": model},
        "processing": proc,
        "graph": graph,
    }

    # Write to benchmark/runs/<model>-<run_id>/ — model-prefixed dir restores the
    # pre-refactor naming convention (human-browsable); header.run_id stays the
    # bare timestamp (the link back to the operational state/runs/<run_id>/).
    benchmark_runs_dir = get_benchmark_runs_dir()
    out_dir = benchmark_runs_dir / f"{model}-{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "measurements.json"
    atomic_write_json(out_path, payload)
    # Rendered human-readable report alongside the machine payload.
    (out_dir / "report.md").write_text(render_report(payload), encoding="utf-8")
    return out_path


def maybe_emit_kpis(
    *,
    emit_kpis: bool,
    run_id: str,
    run_dir: Path,
    graph_path: Path,
    state_root: Path,
    provider: str,
    model: str,
    header: RunMeasurementHeader,
    finalize_ran: bool,
) -> None:
    """Gate: emit KPIs only when --emit-kpis set AND finalize ran (compile_result exists).

    Wraps emit_run_kpis in a try/except so a KPI emission failure never breaks
    the run. Logs a warning on failure.
    """
    if not emit_kpis:
        return
    if not finalize_ran:
        warnings.warn(
            "emit-kpis: finalize did not run (no compiled sources) — "
            "skipping KPI emission",
            stacklevel=2,
        )
        return
    try:
        out_path = emit_run_kpis(
            run_id=run_id,
            run_dir=run_dir,
            graph_path=graph_path,
            state_root=state_root,
            provider=provider,
            model=model,
            header=header,
        )
        log.info("emit-kpis: measurements written to %s", out_path)
    except Exception as exc:  # noqa: BLE001
        warnings.warn(
            f"emit-kpis: KPI emission failed (run unaffected): {exc!r}",
            stacklevel=2,
        )
