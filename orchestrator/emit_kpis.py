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
- Task #122 §7: the emit gate is EVIDENCE-driven, not finalize-driven — an
  auditable measurements.json is written whenever Pass-1 produced expected
  signal IDs, even when the run never crossed the finalize boundary
  (finalize_ran: false artifact; score-skipped at the §7c gate). Per-source
  context records (runs/<run_id>/context/*.json) are strictly loaded and
  reconciled against the Pass-1 sidecar signal set (§5).
"""
from __future__ import annotations

import dataclasses
import json
import logging
import shutil
import warnings
from pathlib import Path

from common.atomic_io import atomic_write_json
from common.measurement import (
    RunMeasurementHeader,
    load_run_measurements,
    load_search_measurements,
)
from compiler.context_record import (
    ContextEvidence,
    ContextIntegrity,
    ContextIntegrityIssue,
    ContextLoadResult,
    ContextRecordV1,
    ContextRecordV2,
    parse_context_record,
)
from compiler.kpi.processing import compute_processing, compute_search_diagnostics
from compiler.kpi.graph import compute_graph
from compiler.kpi.report import render_report
from compiler.prompt_builder import system_prompt_path
from kdb_graph.graphdb import GraphDB

log = logging.getLogger(__name__)


def get_benchmark_runs_dir() -> Path:
    """Return the canonical benchmark/runs/ directory (repo root / benchmark / runs).

    Monkeypatch this in tests to redirect output to tmp_path.
    """
    return Path(__file__).resolve().parent.parent / "benchmark" / "runs"


def _gather_pass1_search_keys(run_dir: Path) -> list[str]:
    """Gather entity_search_keys from all Pass-1 sidecars in run_dir/pass1/.

    Sidecar identification: *.json files in run_dir/pass1/ with both
    "source_id" and "raw_response" keys (same predicate as load_run_measurements).
    Returns the concatenated list (not deduplicated, order-preserving).
    None parsed_envelope on failure sidecars is guarded.
    """
    keys: list[str] = []
    pass1_dir = run_dir / "pass1"
    if not pass1_dir.is_dir():
        return keys
    for p in sorted(pass1_dir.glob("*.json")):
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


def _gather_expected_signal_ids(run_dir: Path) -> set[str]:
    """Authoritative expected signal source IDs from Pass-1 sidecars — the
    FINAL (post-override) envelope's kdb_signal == 'signal' (Task #122 §5).
    Same sidecar identification + skip predicate as _gather_pass1_search_keys."""
    ids: set[str] = set()
    pass1_dir = run_dir / "pass1"
    if not pass1_dir.is_dir():
        return ids
    for p in sorted(pass1_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "source_id" not in data or "raw_response" not in data:
            continue
        if data.get("outcome") == "enrich_skipped":
            continue
        envelope = data.get("parsed_envelope") or {}
        if envelope.get("kdb_signal") == "signal":
            ids.add(data["source_id"])
    return ids


# ---------- Task #122 §5: context-record loading + reconciliation ----------


def load_context_records(context_dir: Path, expected_run_id: str) -> ContextLoadResult:
    """Filesystem walk of <context_dir>/*.json — every file is strictly parsed
    (parse_context_record — the version-dispatching reader, #123 P3a.3 §4.5:
    V1 history and V2 current records load through one loader). Rejections
    (bad JSON, any strict-parse failure) become `malformed` issues; a record
    that parses but carries another run_id becomes a `wrong_run` issue.
    Issues survive — a rejected file never enters the records list. A
    missing/empty dir is an empty result."""
    records: list[ContextRecordV1 | ContextRecordV2] = []
    issues: list[ContextIntegrityIssue] = []
    if context_dir.is_dir():
        for p in sorted(context_dir.glob("*.json")):
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                rec = parse_context_record(raw)
            except Exception as e:
                issues.append(ContextIntegrityIssue(
                    path=str(p), reason="malformed",
                    detail=f"{type(e).__name__}: {e}"))
                continue
            if rec.run_id != expected_run_id:
                issues.append(ContextIntegrityIssue(
                    path=str(p), reason="wrong_run",
                    detail=f"run_id {rec.run_id!r} != expected {expected_run_id!r}"))
                continue
            records.append(rec)
    return ContextLoadResult(records=records, issues=issues)


def reconcile_context_records(
    load_result: ContextLoadResult,
    expected_ids: set[str],
    p2_attempted: int,
) -> ContextEvidence:
    """Typed reconciliation (Task #122 §5, pinned order): expected signal IDs
    (derived upstream from Pass-1 sidecars) → load+validate (already applied)
    → duplicate/unexpected detection → matched set + coverage (None when
    expected empty) → count cross-check vs header.p2_attempted (mismatch →
    integrity flag only; expected_ids WIN) → evidence.

    evidence_complete := bool(expected_ids) AND matched == expected AND zero
    integrity errors — never vacuous.
    """
    malformed = sum(1 for i in load_result.issues if i.reason == "malformed")
    wrong_run = sum(1 for i in load_result.issues if i.reason == "wrong_run")

    per_source: dict[str, int] = {}
    for rec in load_result.records:
        per_source[rec.source_id] = per_source.get(rec.source_id, 0) + 1
    duplicate = sum(n - 1 for n in per_source.values() if n > 1)
    unexpected = sum(1 for rec in load_result.records
                     if rec.source_id not in expected_ids)

    record_ids = set(per_source)
    matched_ids = expected_ids & record_ids
    missing = len(expected_ids - record_ids)
    coverage = (len(matched_ids) / len(expected_ids)) if expected_ids else None
    expected_count_mismatch = len(expected_ids) != p2_attempted

    integrity = ContextIntegrity(
        missing=missing,
        malformed=malformed,
        duplicate=duplicate,
        unexpected=unexpected,
        wrong_run=wrong_run,
        expected_count_mismatch=expected_count_mismatch,
    )
    integrity_errors = (
        missing + malformed + duplicate + unexpected + wrong_run
        + (1 if expected_count_mismatch else 0)
    )
    complete = (bool(expected_ids)
                and matched_ids == expected_ids
                and integrity_errors == 0)
    return ContextEvidence(
        records=load_result.records,
        expected_ids=set(expected_ids),
        matched_ids=matched_ids,
        coverage=coverage,
        complete=complete,
        integrity=integrity,
    )


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
    vault_root: Path,
    provider: str,
    model: str,
    header: RunMeasurementHeader,
    finalize_ran: bool = True,
    expected_signal_ids: set[str] | None = None,
    console_text: str | None = None,
) -> Path:
    """Compute and write benchmark/runs/<run_id>/measurements.json.

    The Kuzu graph is reopened read-only here (the main run's context manager
    has already closed it). Task #122 §7: an auditable artifact is written
    whenever Pass-1 produced expected signal IDs — even when the run never
    crossed the finalize boundary (finalize_ran=False: graph scored fields
    and finalize-dependent watched fields emit None; Task-122 event-time
    fields + integrity are retained; the deterministic post-run resolver read
    for late/never classification always runs over the actual post-run graph
    state). On the finalize path compile_result.json must exist.

    Returns the path written.
    """
    # Load measurements (header already computed; pass it directly, reload calls)
    _hdr, calls = load_run_measurements(run_dir)

    # Compute PROCESSING KPIs
    proc = compute_processing(header, calls)

    # #123 P3a.4 (§4.7): pass-1.5 search diagnostics + envelope reconciliation.
    # The STRICT loader backs emit (B10): a malformed search measurement
    # aborts the emission (→ maybe_emit_kpis' warning) rather than emitting
    # KPIs from partial evidence. Reconciliation is envelope-file count vs
    # header.searches_written — a mismatch is warned, never silent.
    search_measurements = load_search_measurements(run_dir)
    search_dir = run_dir / "search"
    envelope_count = (len(list(search_dir.glob("*.json")))
                      if search_dir.is_dir() else 0)
    reconciled = envelope_count == header.searches_written
    if not reconciled:
        warnings.warn(
            f"search envelope reconciliation mismatch: {envelope_count} "
            f"envelope file(s) under {search_dir} vs header.searches_written="
            f"{header.searches_written} — incomplete measurement state",
            stacklevel=2,
        )
    search_section = {
        **compute_search_diagnostics(search_measurements),
        "envelope_count": envelope_count,
        "reconciled": reconciled,
    }

    # Load finalize artifacts (from persisted retraction.json, not re-running reap)
    finalize_artifacts = _load_finalize_artifacts(state_root, run_id)

    # Gather Pass-1 entity_search_keys
    pass1_search_keys = _gather_pass1_search_keys(run_dir) or None

    # Task #122 §5: strictly load the per-source context records written at
    # event time and reconcile them against the Pass-1 sidecar signal set.
    if expected_signal_ids is None:
        expected_signal_ids = _gather_expected_signal_ids(run_dir)
    context_load = load_context_records(run_dir / "context", run_id)
    context_evidence = reconcile_context_records(
        context_load, expected_signal_ids, header.p2_attempted)

    # Compute GRAPH KPIs (reopen read-only after the context manager exited)
    with GraphDB(graph_path, read_only=True) as gdb:
        graph = compute_graph(
            gdb.conn, finalize_artifacts,
            finalize_ran=finalize_ran,
            pass1_search_keys=pass1_search_keys,
            context_evidence=context_evidence,
        )

    # Emit provider + model explicitly in the header. `model` is the unique
    # slug the leaderboard keys on (one row per model — no group_key/grouping).
    payload = {
        "header": {**dataclasses.asdict(header), "provider": provider, "model": model},
        "processing": proc,
        "graph": graph,
        "search": search_section,
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
    # The live progress narrative (orchestrate stdout), saved verbatim. Its own
    # try/except: a console.log failure must not be reported as "KPI emission
    # failed" — measurements.json/report.md are already on disk by now.
    if console_text:
        try:
            (out_dir / "console.log").write_text(console_text, encoding="utf-8")
        except OSError:
            log.warning("emit-kpis: could not write console.log for run %s", run_id)
    # Copy operational run state (pass1/, pass2/, context/, measurement_header.json)
    # so each benchmark record is self-contained without the live state/ tree.
    try:
        shutil.copytree(run_dir, out_dir / "run_state")
    except OSError:
        log.warning("emit-kpis: could not copy run_state for run %s", run_id)
    # system_prompt.md — the repo-packaged Pass-2 system prompt (post-#115), so
    # each benchmark record preserves the exact prompt text (Task #30
    # re-runnability); complements the header's pass2_system_prompt_sha256 stamp.
    try:
        shutil.copy2(system_prompt_path(), out_dir / "system_prompt.md")
    except OSError:
        log.warning("emit-kpis: could not copy system prompt for run %s", run_id)
    # §7b: finalized output is packaged ONLY when the run actually finalized —
    # compile_result.json is written solely by _finalize and is stable
    # top-level state (a no-finalize run would package a PREVIOUS run's
    # payload); the live wiki/ tree is not this run's finalized output either.
    if finalize_ran:
        # compile_result.json — full page-level compile output (bodies, slugs, links).
        try:
            shutil.copy2(state_root / "compile_result.json", out_dir / "compile_result.json")
        except OSError:
            log.warning("emit-kpis: could not copy compile_result.json for run %s", run_id)
        # wiki/ — rendered Markdown pages (same data as compile_result, human-browsable).
        try:
            shutil.copytree(vault_root / "KDB" / "wiki", out_dir / "wiki")
        except OSError:
            log.warning("emit-kpis: could not copy wiki/ for run %s", run_id)
    return out_path


def maybe_emit_kpis(
    *,
    emit_kpis: bool,
    run_id: str,
    run_dir: Path,
    graph_path: Path,
    state_root: Path,
    vault_root: Path,
    provider: str,
    model: str,
    header: RunMeasurementHeader,
    finalize_ran: bool,
    console_text: str | None = None,
) -> None:
    """Gate (Task #122 §7): emit an auditable measurements.json when
    --emit-kpis is set AND there is evidence to audit — i.e. finalize ran
    (compile_result exists) OR Pass-1 produced expected signal IDs (event-time
    context evidence exists even without finalize; the artifact records
    finalize_ran: false and is score-skipped at the §7c gate).

    Wraps emit_run_kpis in a try/except so a KPI emission failure never breaks
    the run. Logs a warning on failure.
    """
    if not emit_kpis:
        return
    expected_signal_ids = _gather_expected_signal_ids(run_dir)
    if not finalize_ran and not expected_signal_ids:
        warnings.warn(
            "emit-kpis: finalize did not run and Pass-1 produced no signal "
            "sources — no context evidence to audit, skipping KPI emission",
            stacklevel=2,
        )
        return
    try:
        out_path = emit_run_kpis(
            run_id=run_id,
            run_dir=run_dir,
            graph_path=graph_path,
            state_root=state_root,
            vault_root=vault_root,
            provider=provider,
            model=model,
            header=header,
            finalize_ran=finalize_ran,
            expected_signal_ids=expected_signal_ids,
            console_text=console_text,
        )
        log.info("emit-kpis: measurements written to %s", out_path)
    except Exception as exc:  # noqa: BLE001
        warnings.warn(
            f"emit-kpis: KPI emission failed (run unaffected): {exc!r}",
            stacklevel=2,
        )
