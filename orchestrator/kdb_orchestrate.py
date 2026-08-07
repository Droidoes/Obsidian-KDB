"""kdb_orchestrate — the end-to-end conductor (Task #91, Plan 5+6).

feeder → ingestion (Pass-1 enrich) → compiler (Pass-2 compile_source) → GraphDB,
driven per-source over a single shared read-write GraphDB connection.

Wires the shipped foundations — compile_source (produce-don't-write), per-source
graph intake (#136 drain-as-you-go: LINKS_TO wiring + deprecation marking inside
each commit txn, unresolved targets pended durably in the PendingLink ledger),
the pipeline registry, and scan_scope — into one loop.

Commit model (β, D-91-15 — graph-sync-first): per source the conductor applies
the wiki pages, graph-syncs (Kuzu txn — wiring + deprecation land in-txn), then —
only on graph-sync success — writes the manifest. The manifest write is the
commit boundary, so a graph-sync failure rolls back cleanly and the manifest is
never written → the source self-heals on the next run (case-a). Finalize no
longer wires or deprecates (#136 — the Task #91 deferred passes are deleted);
it keeps the frontmatter convergence fixpoint (#130 — every deprecated node gets
a deprecated file; idempotent crash/dry-run heal), writes compile_result.json +
last_orchestrate.json, and reports the accumulated per-commit wiring/deprecation
totals plus the open-pending count.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from kdb_graph.graphdb import GraphDB
from kdb_graph.intake import apply_compile_result
from kdb_graph.queries import deprecated_entities
from orchestrator import journal_writer, manifest_writer
from compiler import page_writer
from ingestion.config import pipeline_registry
from common.atomic_io import atomic_write_json
from compiler.canonicalize import load_or_empty
from compiler.compiler import compile_source
from ingestion.enrich.enrich import enrich_one
from ingestion.kdb_scan import scan_scope
from orchestrator.orchestrator_events import (
    EventRecorder,
    OrchestratorInvariantError,
    OrchestratorLogLevel,
    check_orchestrator_invariant,
)
from common.measurement import RunMeasurementHeader
from common.model_pool import resolve_models_json, UnknownModelError, PoolError
from common.model_route import ModelRoute
from common.run_context import RunContext, now_iso
from common.version import release_version
from orchestrator.emit_kpis import maybe_emit_kpis
from common.source_io import SourceFrontmatter, parse_existing_frontmatter
from ingestion.enrich.pass1_prompt import PASS1_PROMPT_VERSION
from compiler.prompt_builder import PASS2_PROMPT_VERSION, load_system_prompt

MANIFEST_NAME = "manifest.json"

#: #123 P3a.2b — the pass-1.5 selector seat fallback (R-P3a-5; settled
#: 2026-08-03 in docs/TASKS.md #123). Used only when run() gets no
#: selector_model_id — the CLI passes --selector-model, or --model when that
#: is absent (single-model default, Joseph 2026-08-04). Resolved ONCE per
#: run() and threaded into every compile_source call; the adapter itself is
#: seat-agnostic.
PASS15_SELECTOR_MODEL_ID = "qwen3.7-flash"


@dataclass
class CommitResult:
    """Outcome of a single per-source commit (β ordering).

    The failure contract is load-bearing: Task 3's fail-fast and Task 5's
    last_orchestrate.json route on `failure_stage`, and `graph_committed`
    distinguishes the two β failure classes:

      * failure_stage="apply"           — wiki write threw; graph untouched (case-a, clean).
      * failure_stage="graph_sync"      — Kuzu txn threw + rolled back; manifest never
                                          written (case-a, clean self-heal).
      * failure_stage="manifest_post_graph" — graph COMMITTED but manifest write threw
                                          (`graph_committed=True`); the β residual
                                          Codex named — self-heals via idempotency on
                                          re-run, but is a distinct, surfaced class.

    On success `next_manifest` is the advanced full v3.0 manifest dict the caller
    threads into the next source; `cr` is accumulated for the finalize archive.
    `scan_entry_used` is the post-embed scan entry handed to intake (#132: the
    replay archive records the exact intake inputs, including when the manifest
    leg failed after the graph committed).

    #136 wiring/deprecation counts (from the commit's IntakeResult, zero when
    the graph txn rolled back): `links_wired` = edges present after
    replacement + drained pendings; `links_pended` = NEW ledger rows;
    `links_drained` = ledger rows resolved into edges; `deprecations` = the
    newly-deprecated [{slug, page_type}] flipped in this commit.
    """
    next_manifest: dict | None = None
    pages_written: list[str] = field(default_factory=list)
    cr: dict | None = None
    failure_stage: str | None = None      # apply | graph_sync | manifest_post_graph
    exception_type: str | None = None
    error: str | None = None
    graph_committed: bool = False
    scan_entry_used: dict | None = None
    links_wired: int = 0
    links_pended: int = 0
    links_drained: int = 0
    deprecations: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failure_stage is None


def _commit_source(
    *,
    cr: dict,
    source_id: str,
    post_embed_hash: str,
    post_embed_mtime: float,
    scan_entry: dict,
    prior_manifest: dict,
    vault_root: Path,
    state_root: Path,
    conn,
    ctx: RunContext,
) -> CommitResult:
    """Commit one compiled source with β (graph-sync-first) ordering.

    `scan_entry` is the scanner's ScanEntry.to_dict(); its current_hash/mtime are
    overridden with the POST-embed values so the manifest records the file as it
    sits on disk after Pass-1 embedded frontmatter (else the embed itself looks
    like an edit on the next scan → spurious recompile).
    """
    entry = dict(scan_entry)
    entry["current_hash"] = post_embed_hash
    entry["current_mtime"] = post_embed_mtime
    single_scan = {"files": [entry], "to_compile": [source_id], "to_reconcile": []}

    # Pure (no I/O): compute the advanced manifest now; write it last (β boundary).
    next_manifest, _ = manifest_writer.build_source_state_update(
        prior_manifest, single_scan, cr, ctx)

    # 1. apply wiki pages (stage 8). Throws ⇒ case-(a), graph untouched.
    try:
        apply_res = page_writer.apply(
            vault_root, compile_result=cr, last_scan=single_scan,
            run_ctx=ctx, write=True)
    except Exception as e:
        return CommitResult(
            failure_stage="apply", exception_type=type(e).__name__, error=str(e),
            scan_entry_used=entry)

    # 2. graph-sync (Kuzu txn; #136: LINKS_TO wiring + per-source deprecation
    #    land IN this txn — unresolved targets pend durably in the ledger).
    #    Throws ⇒ Kuzu rolled back clean; manifest never written ⇒ case-(a) self-heal.
    try:
        intake_res = apply_compile_result(cr, single_scan, ctx.run_id, conn=conn)
    except Exception as e:
        return CommitResult(
            pages_written=apply_res.pages_written,
            failure_stage="graph_sync", exception_type=type(e).__name__, error=str(e),
            scan_entry_used=entry)

    # 2b. Frontmatter convergence at commit (#136): pages this commit just
    #     deprecated get deprecated files immediately — finalize's fixpoint is
    #     the backstop, not the only marker. Revivals need no file work
    #     (re-support ⇒ re-emit ⇒ page_writer writes fresh active frontmatter).
    if intake_res.deprecations_detected:
        page_writer.mark_deprecated(ctx.vault_root, intake_res.deprecations_detected)

    # 3. manifest write = COMMIT BOUNDARY (β). Throws here ⇒ graph committed but
    #    manifest absent ⇒ manifest_failed_after_graph_commit (self-heals on re-run).
    try:
        atomic_write_json(state_root / MANIFEST_NAME, next_manifest)
    except Exception as e:
        return CommitResult(
            pages_written=apply_res.pages_written, graph_committed=True,
            failure_stage="manifest_post_graph",
            exception_type=type(e).__name__, error=str(e),
            scan_entry_used=entry,
            links_wired=intake_res.edges_upserted + intake_res.links_drained,
            links_pended=intake_res.links_pended,
            links_drained=intake_res.links_drained,
            deprecations=intake_res.deprecations_detected)

    return CommitResult(
        next_manifest=next_manifest, pages_written=apply_res.pages_written,
        cr=cr, graph_committed=True, scan_entry_used=entry,
        links_wired=intake_res.edges_upserted + intake_res.links_drained,
        links_pended=intake_res.links_pended,
        links_drained=intake_res.links_drained,
        deprecations=intake_res.deprecations_detected)


# ---------- finalize: convergence fixpoint + archive + summary ----------

def _combine_crs(crs: list[dict], run_id: str) -> dict:
    """Merge the per-source compile_results accumulated over the loop into one
    batch compile_result (the replay payload → compile_result.json).

    Entities/SUPPORTS/LINKS_TO/domains all live in compiled_sources[].pages[],
    but alias Entities + ALIAS_OF edges live ONLY in canonical_meta.aliases_emitted
    — the one per-source graph effect outside compiled_sources. Dropping it would
    make the replayed compile_result fail to recreate aliases → live≢replay. So
    the union of aliases_emitted is load-bearing, not cosmetic.
    """
    compiled_sources: list[dict] = []
    compilation_notes: list[str] = []
    aliases_emitted: list[dict] = []
    for cr in crs:
        compiled_sources.extend(cr.get("compiled_sources", []))
        # #115: the aggregate field is compilation_notes (was warnings);
        # log_entries left the contract.
        compilation_notes.extend(cr.get("compilation_notes", []))
        cm = cr.get("canonical_meta") or {}
        aliases_emitted.extend(cm.get("aliases_emitted") or [])
    combined: dict = {
        "run_id": run_id, "success": True,
        "compiled_sources": compiled_sources,
        "compilation_notes": compilation_notes, "errors": [],
    }
    if aliases_emitted:
        combined["canonical_meta"] = {"aliases_emitted": aliases_emitted}
    return combined


def _finalize(
    conn, accumulated_crs: list[dict], *,
    state_root: Path, ctx: RunContext, dry_run: bool = False,
    progress: dict | None = None, wiring: dict | None = None,
) -> dict:
    """End-of-run tail (#136 slim shape — wiring/deprecation are per-commit now,
    so nothing correctness-critical sits behind the end-of-run gate anymore):

      7. mark_deprecated(files) — frontmatter CONVERGENCE: every deprecated graph
                                  node gets a deprecated file (idempotent — heals
                                  dry-run/crash divergence, not just this run's
                                  new flips). This is the zombie invariant,
                                  enforced as a fixpoint every run. Commits
                                  already marked their own new flips (#136 §3.4);
                                  this is the backstop.
      8. write compile_result.json (combined replay payload).

    `progress` (#132): optional mutable holder; `progress["stage"]` advances to
    "complete" once the fixpoint + archive landed (the journal's
    finalize_progress field is parse-tolerated audit metadata post-#136 —
    replay ignores its value).

    `wiring` (#136): the loop's accumulated per-commit totals —
    {"links_wired", "links_pended", "links_drained", "deprecated"} — carried
    into the summary verbatim (None ⇒ zeros, e.g. direct test calls).

    Returns finalize counts for the run summary, adding `links_pended_open`
    (the standing PendingLink ledger depth — the durable dangling-link metric).
    """
    combined = _combine_crs(accumulated_crs, ctx.run_id)
    totals = dict(wiring or {})

    flipped: list = []
    if not dry_run:
        all_deprecated = [
            {"slug": e.slug, "page_type": e.page_type}
            for e in deprecated_entities(conn)
        ]
        flipped = page_writer.mark_deprecated(ctx.vault_root, all_deprecated)
        atomic_write_json(state_root / "compile_result.json", combined)
    if progress is not None:
        progress["stage"] = "complete"

    r = conn.execute("MATCH (p:PendingLink) RETURN COUNT(p)")
    links_pended_open = int(r.get_next()[0]) if r.has_next() else 0

    return {
        "links_wired": totals.get("links_wired", 0),
        "links_pended": totals.get("links_pended", 0),
        "links_drained": totals.get("links_drained", 0),
        "links_pended_open": links_pended_open,
        "deprecated": totals.get("deprecated", 0),
        "deprecated_files": len(flipped),
        "deprecated_pages_total": _count_deprecated_wiki_files(ctx.vault_root),
    }


def write_last_orchestrate_json(
    state_root: Path, *, run_id: str, started_at: str, finished_at: str,
    exit_code: int, exit_reason: str, counts: dict, manifest_delta: dict,
    finalize: dict | None = None, event_log_path: Path | str | None = None,
    event_log_failed: bool = False, warnings: int = 0,
    sources_quarantined: int = 0, invariant_violations: int = 0,
    quarantined_sources: list[dict] | None = None,
) -> Path:
    """Write the slim run summary (D-91-10). Written ALWAYS — success and abort —
    so a fail-fast still leaves an inspectable record of where the run stopped."""
    summary_counts = dict(counts)
    summary_counts["warnings"] = warnings
    summary_counts["sources_quarantined"] = sources_quarantined
    summary_counts["invariant_violations"] = invariant_violations
    summary = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "exit_code": exit_code,
        "exit_reason": exit_reason,
        "counts": summary_counts,
        "manifest_delta": manifest_delta,
        "event_log_path": str(event_log_path) if event_log_path is not None else None,
        "event_log_failed": event_log_failed,
        "quarantined_sources": list(quarantined_sources or []),
    }
    if finalize is not None:
        summary["finalize"] = finalize
    path = state_root / "last_orchestrate.json"
    atomic_write_json(path, summary)
    return path


# ---------- manifest loading (full v3.0 dict for build_source_state_update) ----------

def _load_full_manifest(manifest_path: Path) -> dict:
    """Load the full v3.0 manifest dict (sources{}/tombstones{}/runs{}). Missing
    or malformed → {} (first-run). v1.0 manifests auto-migrate to v3.0."""
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if data:
        data = manifest_writer.migrate_manifest_to_source_state(data)
    return data


def _stamp_legacy_pipeline_id(manifest: dict, pipeline_id: str) -> dict:
    """T0a: stamp pipeline_id on legacy records lacking it so scan_scope's
    per-pipeline prior filter sees them this run (else they'd be filtered out →
    spurious whole-vault recompile). Fresh sandbox: no-op."""
    for rec in manifest.get("sources", {}).values():
        if rec.get("pipeline_id") is None:
            rec["pipeline_id"] = pipeline_id
    return manifest


def _flat_prior(manifest: dict) -> dict:
    """Project the full v3.0 manifest to the flat {source_id: {...}} view
    scan_scope/classify consume (mirrors kdb_scan.load_manifest_sources, but from
    the in-memory legacy-stamped dict so this run's scan sees the stamps)."""
    out: dict = {}
    for sid, rec in manifest.get("sources", {}).items():
        out[sid] = {
            "hash": rec.get("hash"), "mtime": rec.get("mtime"),
            "size_bytes": rec.get("size_bytes"), "file_type": rec.get("file_type"),
            "is_binary": rec.get("is_binary"),
            "last_compiled_hash": rec.get("last_compiled_hash"),
            "pipeline_id": rec.get("pipeline_id"),
        }
    return out


def _manifest_delta(prior: dict, final: dict) -> dict:
    p = prior.get("sources", {}) if prior else {}
    f = final.get("sources", {}) if final else {}
    pk, fk = set(p), set(f)
    return {
        "added": sorted(fk - pk),
        "removed": sorted(pk - fk),
        "changed": sorted(s for s in (pk & fk) if p[s].get("hash") != f[s].get("hash")),
    }


# ---------- noise + reconcile commits ----------

def _commit_noise_source(
    *, source_id: str, post_embed_hash: str, post_embed_mtime: float,
    scan_entry: dict, prior_manifest: dict, state_root: Path, ctx: RunContext,
) -> dict:
    """Commit a noise source: manifest no_graph_db, NO graph, NO wiki. M2:
    last_compiled_hash = post_embed_hash so the embed doesn't re-trigger enrich
    next run. to_compile=[] so apply_compile_sources doesn't error-mark it."""
    entry = dict(scan_entry)
    entry["current_hash"] = post_embed_hash
    entry["current_mtime"] = post_embed_mtime
    single_scan = {"files": [entry], "to_compile": [], "to_reconcile": []}
    next_manifest, _ = manifest_writer.build_source_state_update(
        prior_manifest, single_scan, {"compiled_sources": [], "success": True}, ctx)
    rec = next_manifest["sources"][source_id]
    rec["run_state"] = manifest_writer.RUN_STATE_NO_GRAPH_DB
    rec["last_compiled_hash"] = post_embed_hash
    rec["last_failure"] = None
    atomic_write_json(state_root / MANIFEST_NAME, next_manifest)
    return next_manifest


def _json_safe_artifacts(artifacts: dict | None) -> dict:
    return {str(k): str(v) for k, v in (artifacts or {}).items()}


def _last_failure(
    *,
    ctx: RunContext,
    stage: str,
    error: str | None,
    exception_type: str | None = None,
    artifacts: dict | None = None,
) -> dict:
    failure = {
        "stage": stage,
        "run_id": ctx.run_id,
        "at": ctx.started_at,
        "error": error,
        "artifacts": _json_safe_artifacts(artifacts),
    }
    if exception_type is not None:
        failure["exception_type"] = exception_type
    return failure


def _commit_source_failure(
    *,
    source_id: str,
    run_state: str,
    failure: dict,
    scan_entry: dict,
    prior_manifest: dict,
    state_root: Path,
    ctx: RunContext,
    current_hash: str | None = None,
    current_mtime: float | None = None,
) -> dict:
    """Commit source-local failure state; never advances last_compiled_hash."""
    entry = dict(scan_entry)
    if current_hash is not None:
        entry["current_hash"] = current_hash
    if current_mtime is not None:
        entry["current_mtime"] = current_mtime
    single_scan = {"files": [entry], "to_compile": [], "to_reconcile": []}
    next_manifest, _ = manifest_writer.build_source_failure_update(
        prior_manifest,
        single_scan,
        ctx,
        source_id=source_id,
        run_state=run_state,
        last_failure=failure,
    )
    atomic_write_json(state_root / MANIFEST_NAME, next_manifest)
    return next_manifest


def _commit_reconcile_op(
    op, *, moved_entry, prior_manifest: dict, conn, state_root: Path, ctx: RunContext,
) -> dict:
    """Commit a MOVED/DELETED reconcile op. Graph handles both via to_reconcile
    (Phase 2); manifest handles MOVED via files[] + DELETED via to_reconcile[].

    #130 R-130-4: DELETED is total erasure — the graph layer already removed
    the sole-supported pages (IntakeResult.erased_pages); their wiki files are
    deleted here (no archive). Surviving pages linking to erased slugs are
    reported to the run log, never rewritten."""
    op_dict = op.to_dict()
    files = [moved_entry.to_dict()] if (op.type == "MOVED" and moved_entry) else []
    single_scan = {"files": files, "to_compile": [], "to_reconcile": [op_dict]}
    intake_res = apply_compile_result(
        {"compiled_sources": []}, single_scan, ctx.run_id, conn=conn)
    if op.type == "DELETED" and intake_res.erased_pages and not ctx.dry_run:
        deleted_files = page_writer.delete_page_files(
            ctx.vault_root, intake_res.erased_pages)
        ctx.append_log(
            "info",
            f"source deletion erased {len(deleted_files)} page file(s): "
            + ", ".join(sorted(e["slug"] for e in intake_res.erased_pages)))
        for dl in intake_res.erased_dead_links:
            ctx.append_log(
                "warning",
                f"dead link — {dl['from_slug']} -> {dl['to_slug']} (erased page)")
    next_manifest, _ = manifest_writer.build_source_state_update(
        prior_manifest, single_scan, {"compiled_sources": [], "success": True}, ctx)
    atomic_write_json(state_root / MANIFEST_NAME, next_manifest)
    return next_manifest


# ---------- the conductor ----------

@dataclass
class OrchestrateResult:
    run_id: str
    exit_code: int                 # 0 success, 1 abort/crash
    exit_reason: str               # "ok" | "<stage>:<source_id>" | "unexpected:<Exc>"
    counts: dict
    manifest_delta: dict
    finalize: dict | None = None
    failed_source: str | None = None
    failure_stage: str | None = None
    summary_path: Path | None = None
    event_log_path: Path | None = None
    event_log_failed: bool = False
    quarantined_sources: list[dict] = field(default_factory=list)
    planned: dict | None = None     # dry-run plan preview

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _empty_counts() -> dict:
    return {
        "sources_scanned": 0, "sources_enriched": 0, "sources_compiled": 0,
        "sources_noise": 0, "sources_moved": 0, "sources_deleted": 0,
        "sources_failed": 0,
        "warnings": 0, "sources_quarantined": 0, "invariant_violations": 0,
    }


def _quarantined_sources(recorder: EventRecorder) -> list[dict]:
    rows: list[dict] = []
    for event in recorder.recorded_events:
        if event.severity != "source_quarantine":
            continue
        row = {"source_id": event.source_id, "stage": event.stage}
        if event.exception_type is not None:
            row["exception_type"] = event.exception_type
        rows.append(row)
    return rows


def _event_alarm_counts(recorder: EventRecorder) -> dict:
    return {
        "warnings": recorder.count("warning"),
        "sources_quarantined": recorder.count("source_quarantine"),
        "invariant_violations": recorder.count("invariant_violation"),
    }


def _corpus_fingerprint(scan_files) -> str:
    """sha256 of the sorted {source_id: content_hash} mapping.

    Covers all scanned files (not just to_compile) so corpus identity
    reflects the full pipeline scope, including unchanged sources.
    """
    mapping = {e.path: e.current_hash for e in scan_files}
    payload = json.dumps(sorted(mapping.items())).encode()
    return hashlib.sha256(payload).hexdigest()


def _check_invariant(
    condition: bool,
    *,
    recorder: EventRecorder,
    code: str,
    stage: str,
    message: str,
    source_id: str | None = None,
    context: dict | None = None,
) -> None:
    check_orchestrator_invariant(
        condition,
        recorder=recorder,
        code=code,
        stage=stage,
        message=message,
        source_id=source_id,
        context=context,
    )


def _count_deprecated_wiki_files(vault_root: Path) -> int:
    """#135: standing total of deprecated pages on disk in KDB/wiki — the
    operator-visible #134 tripwire (graph and files move in lockstep
    post-#130; this counts what the operator sees in the vault)."""
    wiki_root = Path(vault_root) / "KDB" / "wiki"
    if not wiki_root.exists():
        return 0
    n = 0
    for p in wiki_root.rglob("*.md"):
        try:
            fm, _ = parse_existing_frontmatter(p.read_text(encoding="utf-8"))
        except OSError:
            continue
        if fm.get("status") == "deprecated":
            n += 1
    return n


def _cold_wipe(
    *, vault_root: Path, state_root: Path, graph_path: Path,
    dry_run: bool = False,
) -> dict:
    """#135: erase derived state so the run re-plans from sources alone.

    Targets (derived, fully rebuildable): the KDB/wiki tree, the graph
    database (single file or directory, depending on the Kuzu layout),
    manifest.json, and the canonicalization alias ledger (whose
    entries reference graph entities that no longer exist post-wipe).
    Preserved: pipelines.json (config, not derived), state/runs/ (audit
    trail / #132 replay journals), and per-run outputs
    (last_orchestrate.json / compile_result.json — overwritten by the run).
    Idempotent: missing targets are reported as absent, never an error.
    """
    wiki_root = Path(vault_root) / "KDB" / "wiki"
    graph_path = Path(graph_path)
    manifest_path = Path(state_root) / MANIFEST_NAME
    alias_ledger = Path(state_root) / "canonicalization" / "aliases.json"
    stats = {
        "wiki_files_removed": (
            sum(1 for p in wiki_root.rglob("*") if p.is_file())
            if wiki_root.exists() else 0),
        "graph_removed": graph_path.exists(),
        "manifest_removed": manifest_path.exists(),
        "alias_ledger_removed": alias_ledger.exists(),
        "dry_run": dry_run,
    }
    if dry_run:
        return stats
    if wiki_root.exists():
        shutil.rmtree(wiki_root)
    # Kuzu's layout is a single FILE in current versions (older layouts used
    # a directory) — remove whichever is present.
    if graph_path.is_dir():
        shutil.rmtree(graph_path)
    elif graph_path.exists():
        graph_path.unlink()
    for p in (manifest_path, alias_ledger):
        if p.exists():
            p.unlink()
    return stats


def run(
    *, pipeline_id: str, vault_root: Path, state_root: Path, graph_path: Path,
    provider: str, model: str, max_tokens: int = 32768, dry_run: bool = False,
    cold: bool = False,
    limit: int | None = None, log_level: OrchestratorLogLevel = "warning",
    quiet: bool = False, emit_kpis: bool = False,
    use_completion_tokens: bool = False, extra_body: dict | None = None,
    temperature: float | None = 0.0,
    ctx_window: int | None = None, price_in: float = 0.0, price_out: float = 0.0,
    route: ModelRoute | None = None,
    selector_model_id: str | None = None,
) -> OrchestrateResult:
    """End-to-end conductor for one pipeline: scan → per-source enrich/compile/
    commit (β) → reconcile → finalize. Source-local failures are quarantined
    into source-state and the loop continues; run_fatal / invariant failures
    still abort. Already-committed sources stay committed (β makes each commit
    self-contained). The run summary
    (last_orchestrate.json) is written ALWAYS — success, abort, or crash.

    `limit`: if set, stop compiling after this many signal sources have been
    successfully compiled (noise sources are free and do not count). Reconcile
    and finalize still run over the compiled batch — this is a clean stop, not
    an abort. Remainder is picked up on the next run (unchanged hashes skip).

    `cold` (#135): if set, erase derived state (KDB/wiki tree, graph dir,
    manifest, alias ledger) BEFORE the manifest load/scan so the run re-plans
    from sources alone — the cold-run-orphaned wiki files measured in #134
    have no graph node and are invisible to every in-loop lifecycle mechanism,
    so the wipe is the only thing that removes them. Config (pipelines.json)
    and the audit trail (state/runs/) are preserved. With dry_run, the wipe
    is previewed in the event log only.
    """
    vault_root = Path(vault_root)
    state_root = Path(state_root)
    graph_path = Path(graph_path)
    # #135: the wipe must precede the manifest load so prior state is empty
    # and every source recompiles.
    cold_stats = (_cold_wipe(vault_root=vault_root, state_root=state_root,
                             graph_path=graph_path, dry_run=dry_run)
                  if cold else None)
    manifest_path = state_root / MANIFEST_NAME

    pipeline = pipeline_registry.get_pipeline(state_root, pipeline_id)
    prior_full = _stamp_legacy_pipeline_id(_load_full_manifest(manifest_path), pipeline_id)
    prior_flat = _flat_prior(prior_full)
    ctx = RunContext.new(dry_run=dry_run, vault_root=vault_root)
    # Live progress streams to stdout by default; --quiet silences it. The
    # JSONL verbosity is governed independently by log_level.
    progress_console = None if quiet else sys.stdout
    recorder = EventRecorder.for_state_root(
        state_root=state_root, run_id=ctx.run_id, log_level=log_level,
        console=progress_console)
    recorder.record(
        stage="run", event_type="run_started", severity="info",
        message="orchestrator run started",
        context={"pipeline_id": pipeline_id, "dry_run": dry_run, "limit": limit})
    if cold_stats is not None:
        recorder.record(
            stage="run", event_type="cold_wipe",
            severity="info" if dry_run else "warning",
            message=("cold-start wipe preview (dry-run, nothing deleted)"
                     if dry_run else
                     "cold-start wipe: derived state erased (wiki tree, "
                     "graph, manifest, alias ledger)"),
            context=cold_stats)
    ledger = load_or_empty(state_root / "canonicalization" / "aliases.json")
    runs_root = state_root / "runs"

    full_manifest = prior_full
    accumulated_crs: list[dict] = []
    # #132 (D39): replay-archive accumulators — the EXACT intake inputs of this
    # run, archived as sidecars at the end (committed post-embed scan entries
    # vs applied reconcile ops, split by live phase; nothing else reaches the
    # graph, so nothing else is archived).
    replay_files: list[dict] = []
    replay_to_compile: list[str] = []
    replay_moved_files: list[dict] = []
    replay_reconcile_ops: list[dict] = []
    finalize_progress: dict = {"stage": "none"}
    # #136: per-commit wiring/deprecation totals — wiring + deprecation happen
    # inside each commit txn now; the run summary reports their accumulation.
    wiring_totals = {"links_wired": 0, "links_pended": 0,
                     "links_drained": 0, "deprecated": 0}
    counts = _empty_counts()
    finalize_stats: dict | None = None
    planned: dict | None = None
    abort: tuple[str, str, str | None] | None = None   # (stage, source_id, error)
    crashed_reason: str | None = None
    limit_reached: bool = False
    p1_attempted: int = 0    # sources that entered the Pass-1 enrich step
    # #123 P3a.4 (§4.7): pass-1.5 counting channel — accumulated from each
    # compile_source result; attempted − written == envelope write failures.
    searches_attempted: int = 0
    searches_written: int = 0

    # Scan needs no graph — do it first so --dry-run can preview without opening
    # (or mutating) the graph and without firing any API call.
    scan = scan_scope(
        Path(pipeline.root), vault_root, pipeline_id=pipeline_id,
        prior=prior_flat, run_ctx=ctx,
        excludes=pipeline.excludes, file_types=set(pipeline.file_types))
    counts["sources_scanned"] = len(scan.files)
    recorder.record(
        stage="scan", event_type="scan_completed", severity="info",
        message="pipeline scan completed",
        context={
            "pipeline_id": pipeline_id,
            "files": len(scan.files),
            "to_compile": len(scan.to_compile),
            "to_reconcile": len(scan.to_reconcile),
        })
    recorder.set_progress_plan(
        total=len(scan.to_compile),
        skipped=max(0, len(scan.files) - len(scan.to_compile)),
    )

    if dry_run:
        planned = {
            "to_compile": list(scan.to_compile),
            "deleted": [op.to_dict() for op in scan.to_reconcile if op.type == "DELETED"],
            "moved": [op.to_dict() for op in scan.to_reconcile if op.type == "MOVED"],
        }
        recorder.record(
            stage="dry_run", event_type="dry_run_planned", severity="info",
            message="dry-run plan generated",
            context={
                "to_compile": len(planned["to_compile"]),
                "deleted": len(planned["deleted"]),
                "moved": len(planned["moved"]),
            })
        finished_at = now_iso()
        recorder.record(
            stage="run", event_type="run_finished", severity="info",
            message="orchestrator run finished",
            context={"exit_code": 0, "exit_reason": "dry-run"})
        summary_path = write_last_orchestrate_json(
            state_root, run_id=ctx.run_id, started_at=ctx.started_at,
            finished_at=finished_at, exit_code=0, exit_reason="dry-run",
            counts=counts, manifest_delta={"added": [], "removed": [], "changed": []},
            event_log_path=recorder.events_path,
            event_log_failed=recorder.event_log_failed,
            quarantined_sources=_quarantined_sources(recorder),
            **_event_alarm_counts(recorder))
        alarm_counts = _event_alarm_counts(recorder)
        counts.update(alarm_counts)
        # #132 (D39): dry runs archive a journal too (empty payloads — a dry
        # run ingests nothing; the adapter's dry_run gate skips it on replay).
        journal_writer.archive_replay_artifacts(
            runs_root, run_id=ctx.run_id, started_at=ctx.started_at,
            finished_at=finished_at, dry_run=True, success=True,
            finalize_progress="none", counts=counts,
            quarantined_sources=_quarantined_sources(recorder),
            compile_result=_combine_crs([], ctx.run_id),
            last_scan={"files": [], "to_compile": [],
                       "moved_files": [], "to_reconcile": []})
        return OrchestrateResult(
            run_id=ctx.run_id, exit_code=0, exit_reason="dry-run", counts=counts,
            manifest_delta={"added": [], "removed": [], "changed": []},
            summary_path=summary_path, event_log_path=recorder.events_path,
            event_log_failed=recorder.event_log_failed,
            quarantined_sources=_quarantined_sources(recorder), planned=planned)

    # --- #123 P3a.2b: resolve + validate the pass-1.5 selector seat ONCE,
    # after the dry-run early return, before the graph opens (§4.4). An
    # unknown seat, a seat without a ctx_window (cannot budget), or a
    # max_tokens exceeding the seat's output envelope are run-level config
    # defects — fail-hard before any source is processed. Per-run override
    # (selector_model_id) beats the module fallback (single-model default:
    # the CLI passes --model when --selector-model is absent).
    seat_id = selector_model_id or PASS15_SELECTOR_MODEL_ID
    selector = resolve_models_json(seat_id)
    if selector.ctx_window is None:
        raise PoolError(
            f"pass-1.5 selector seat {seat_id!r} has no "
            "ctx_window — the selector cannot be budgeted")
    if max_tokens > selector.max_output_tokens:
        raise ValueError(
            f"max_tokens={max_tokens} exceeds the pass-1.5 selector seat "
            f"{seat_id!r} output envelope "
            f"({selector.max_output_tokens})")

    try:
        with GraphDB(graph_path) as g:
            files_by_id = {e.path: e for e in scan.files}

            # --- compile queue: NEW/CHANGED (+ MOVED+CHANGED) ---
            for intra_run_order, source_id in enumerate(scan.to_compile):
                p1_attempted += 1
                scan_entry = files_by_id[source_id]
                recorder.record(
                    stage="source", event_type="source_started", severity="info",
                    message="source processing started", source_id=source_id,
                    context={"action": scan_entry.action})
                recorder.record(
                    stage="pass1_enrich", event_type="pass1_enrich_started",
                    severity="info", message="Pass-1 enrich started",
                    source_id=source_id)
                enrich = enrich_one(
                    source_path=vault_root / source_id, source_id=source_id,
                    runs_root=runs_root, run_id=ctx.run_id,
                    provider=provider, model=model,
                    force_signal=pipeline.force_signal, force_noise=pipeline.force_noise,
                    price_in=price_in, price_out=price_out, ctx_window=ctx_window,
                    use_completion_tokens=use_completion_tokens, extra_body=extra_body,
                    temperature=temperature, route=route)
                if enrich.outcome == "enrich_failed":
                    failure = _last_failure(
                        ctx=ctx,
                        stage="pass1_enrich",
                        exception_type="Pass1EnrichError",
                        error=enrich.error,
                        artifacts=enrich.artifacts,
                    )
                    recorder.record(
                        stage="pass1_enrich", event_type="source_quarantined",
                        severity="source_quarantine",
                        message="Pass-1 enrich failed",
                        source_id=source_id,
                        exception_type="Pass1EnrichError",
                        error=enrich.error,
                        artifacts=enrich.artifacts)
                    if not enrich.raw_response_available:
                        recorder.record(
                            stage="pass1_enrich",
                            event_type="raw_response_unavailable",
                            severity="warning",
                            message="Pass-1 raw response unavailable for failure",
                            source_id=source_id,
                            context={"reason": "model call failed before a response "
                                      "body was captured"})
                    full_manifest = _commit_source_failure(
                        source_id=source_id,
                        run_state=manifest_writer.RUN_STATE_ERROR_INGEST,
                        failure=failure,
                        scan_entry=scan_entry.to_dict(),
                        prior_manifest=full_manifest,
                        state_root=state_root,
                        ctx=ctx,
                    )
                    counts["sources_failed"] += 1
                    continue
                _check_invariant(
                    enrich.parsed_envelope is not None
                    and enrich.body is not None
                    and bool(enrich.post_embed_hash)
                    and enrich.post_embed_mtime is not None,
                    recorder=recorder,
                    code="pass1_success_payload_complete",
                    stage="pass1_enrich",
                    source_id=source_id,
                    message="Pass-1 success must return envelope, body, post-embed hash, and mtime.",
                    context={"outcome": enrich.outcome},
                )
                counts["sources_enriched"] += 1
                recorder.record(
                    stage="pass1_enrich", event_type="pass1_enrich_completed",
                    severity="info",
                    message="Pass-1 enrich completed",
                    source_id=source_id,
                    context={"outcome": enrich.outcome,
                             "in_tokens": enrich.total_input_tokens,
                             "out_tokens": enrich.total_output_tokens})

                if enrich.parsed_envelope["kdb_signal"] == "noise":
                    recorder.record(
                        stage="pass1_gate", event_type="pass1_gate_noise",
                        severity="info",
                        message="source gated as noise",
                        source_id=source_id)
                    full_manifest = _commit_noise_source(
                        source_id=source_id, post_embed_hash=enrich.post_embed_hash,
                        post_embed_mtime=enrich.post_embed_mtime,
                        scan_entry=scan_entry.to_dict(), prior_manifest=full_manifest,
                        state_root=state_root, ctx=ctx)
                    counts["sources_noise"] += 1
                    continue
                recorder.record(
                    stage="pass1_gate", event_type="pass1_gate_signal",
                    severity="debug",
                    message="source gated as signal",
                    source_id=source_id)

                recorder.record(
                    stage="pass2_compile", event_type="pass2_compile_started",
                    severity="info", message="Pass-2 compile started",
                    source_id=source_id)
                result = compile_source(
                    source_id=source_id, body=enrich.body,
                    frontmatter=SourceFrontmatter.from_dict(enrich.parsed_envelope),
                    conn=g.conn, vault_root=vault_root, state_root=state_root, ctx=ctx,
                    ledger=ledger, provider=provider, model=model, max_tokens=max_tokens,
                    price_in=price_in, price_out=price_out, ctx_window=ctx_window,
                    use_completion_tokens=use_completion_tokens, extra_body=extra_body,
                    temperature=temperature, route=route,
                    selector=selector, intra_run_order=intra_run_order)
                searches_attempted += 1 if result.search_attempted else 0
                searches_written += 1 if result.search_envelope_written else 0
                if not result.ok:
                    _check_invariant(
                        bool(result.failure_stage) and bool(result.error),
                        recorder=recorder,
                        code="compile_failure_payload_complete",
                        stage=result.failure_stage or "pass2_compile",
                        source_id=source_id,
                        message="Failed compile_source result must expose failure_stage and error.",
                        context={
                            "failure_stage": result.failure_stage,
                            "exception_type": result.exception_type,
                        },
                    )
                    recorder.record(
                        stage=result.failure_stage or "pass2_compile",
                        event_type="source_quarantined",
                        severity="source_quarantine",
                        message="Pass-2 compile failed",
                        source_id=source_id,
                        exception_type=result.exception_type,
                        error=result.error,
                        context={"failure_stage": result.failure_stage},
                        artifacts=result.artifacts)
                    if "raw_response" not in result.artifacts:
                        recorder.record(
                            stage=result.failure_stage or "pass2_compile",
                            event_type="raw_response_unavailable",
                            severity="warning",
                            message="Pass-2 raw response unavailable for failure",
                            source_id=source_id,
                            context={
                                "failure_stage": result.failure_stage,
                                "reason": "failure occurred before a response body "
                                          "was captured or the lower layer exposed "
                                          "only metadata",
                            },
                            artifacts=result.artifacts)
                    full_manifest = _commit_source_failure(
                        source_id=source_id,
                        run_state=manifest_writer.RUN_STATE_ERROR_COMPILE,
                        failure=_last_failure(
                            ctx=ctx,
                            stage=result.failure_stage or "pass2_compile",
                            exception_type=result.exception_type,
                            error=result.error,
                            artifacts=result.artifacts,
                        ),
                        scan_entry=scan_entry.to_dict(),
                        prior_manifest=full_manifest,
                        state_root=state_root,
                        ctx=ctx,
                        current_hash=enrich.post_embed_hash,
                        current_mtime=enrich.post_embed_mtime,
                    )
                    counts["sources_failed"] += 1
                    continue
                _check_invariant(
                    result.cr is not None
                    and len(result.cr.get("compiled_sources", [])) == 1
                    and result.cr["compiled_sources"][0].get("source_id") == source_id,
                    recorder=recorder,
                    code="compile_success_single_source_cr",
                    stage="pass2_compile",
                    source_id=source_id,
                    message="Successful compile_source must return exactly one compiled source for the current source_id.",
                    context={
                        "compiled_source_count": (
                            len(result.cr.get("compiled_sources", []))
                            if result.cr is not None else None
                        ),
                    },
                )
                # Fix 3b (#111 retry-telemetry): thread compile_meta.attempts into
                # the event context so the recorder can surface "(N attempts)"
                # when the compile loop re-prompted (attempts>1 via Fix 3a).
                _cm = (result.cr or {}).get("compiled_sources", [{}])[0].get("compile_meta") or {}
                _compile_attempts = _cm.get("attempts", 1)
                # #111 display-only: thread per-source compile tokens onto the
                # event so the recorder renders "· in N / out N" on pass-2 ✓.
                _ctx = {"in_tokens": _cm.get("input_tokens", 0),
                        "out_tokens": _cm.get("output_tokens", 0)}
                if _compile_attempts > 1:
                    _ctx["attempts"] = _compile_attempts
                recorder.record(
                    stage="pass2_compile", event_type="pass2_compile_completed",
                    severity="info",
                    message="Pass-2 compile completed",
                    source_id=source_id,
                    context=_ctx)

                commit = _commit_source(
                    cr=result.cr, source_id=source_id,
                    post_embed_hash=enrich.post_embed_hash,
                    post_embed_mtime=enrich.post_embed_mtime,
                    scan_entry=scan_entry.to_dict(), prior_manifest=full_manifest,
                    vault_root=vault_root, state_root=state_root, conn=g.conn, ctx=ctx)
                if not commit.ok:
                    severity = ("run_fatal" if commit.failure_stage == "manifest_post_graph"
                                else "source_quarantine")
                    recorder.record(
                        stage=commit.failure_stage or "commit",
                        event_type=("run_fatal" if severity == "run_fatal"
                                    else "source_quarantined"),
                        severity=severity,
                        message="source commit failed",
                        source_id=source_id,
                        exception_type=commit.exception_type,
                        error=commit.error,
                        context={"failure_stage": commit.failure_stage,
                                 "graph_committed": commit.graph_committed})
                    if commit.graph_committed:
                        # #132: manifest_post_graph — the graph HAS this source's
                        # pages (the manifest leg failed after the graph commit),
                        # so the replay archive must include what was ingested.
                        replay_files.append(commit.scan_entry_used)
                        replay_to_compile.append(source_id)
                        accumulated_crs.append(result.cr)
                        # #136: the graph commit landed — its wiring/deprecation
                        # effects count toward the run totals too.
                        wiring_totals["links_wired"] += commit.links_wired
                        wiring_totals["links_pended"] += commit.links_pended
                        wiring_totals["links_drained"] += commit.links_drained
                        wiring_totals["deprecated"] += len(commit.deprecations)
                    if severity == "run_fatal":
                        abort = (commit.failure_stage or "commit", source_id, commit.error)
                        break
                    full_manifest = _commit_source_failure(
                        source_id=source_id,
                        run_state=manifest_writer.RUN_STATE_ERROR_COMMIT,
                        failure=_last_failure(
                            ctx=ctx,
                            stage=commit.failure_stage or "commit",
                            exception_type=commit.exception_type,
                            error=commit.error,
                            artifacts={},
                        ),
                        scan_entry=scan_entry.to_dict(),
                        prior_manifest=full_manifest,
                        state_root=state_root,
                        ctx=ctx,
                        current_hash=enrich.post_embed_hash,
                        current_mtime=enrich.post_embed_mtime,
                    )
                    counts["sources_failed"] += 1
                    continue
                _check_invariant(
                    commit.graph_committed
                    and commit.next_manifest is not None
                    and commit.cr is not None,
                    recorder=recorder,
                    code="commit_success_payload_complete",
                    stage="commit",
                    source_id=source_id,
                    message="Successful source commit must expose graph_committed, next_manifest, and cr.",
                    context={"pages_written": len(commit.pages_written)},
                )
                full_manifest = commit.next_manifest
                accumulated_crs.append(commit.cr)
                # #132: archive the exact intake scan input for replay.
                replay_files.append(commit.scan_entry_used)
                replay_to_compile.append(source_id)
                # #136: accumulate this commit's in-txn wiring/deprecation effects.
                wiring_totals["links_wired"] += commit.links_wired
                wiring_totals["links_pended"] += commit.links_pended
                wiring_totals["links_drained"] += commit.links_drained
                wiring_totals["deprecated"] += len(commit.deprecations)
                counts["sources_compiled"] += 1
                recorder.record(
                    stage="commit", event_type="source_commit_completed",
                    severity="info",
                    message="source commit completed",
                    source_id=source_id,
                    context={"pages_written": len(commit.pages_written)})
                if limit is not None and counts["sources_compiled"] >= limit:
                    limit_reached = True
                    break

            # --- reconcile queue: MOVED + DELETED (skipped on abort) ---
            if abort is None:
                for op in scan.to_reconcile:
                    # MOVED+CHANGED (OQ-91-8): the file is in BOTH queues; the
                    # compile path already recompiled it at the new path → skip here.
                    if op.type == "MOVED" and op.to_path in scan.to_compile:
                        continue
                    moved_entry = (files_by_id.get(op.to_path)
                                   if op.type == "MOVED" else None)
                    full_manifest = _commit_reconcile_op(
                        op, moved_entry=moved_entry, prior_manifest=full_manifest,
                        conn=g.conn, state_root=state_root, ctx=ctx)
                    # #132: archive APPLIED ops only (MOVED+CHANGED skips above
                    # never reached intake and are never archived).
                    replay_reconcile_ops.append(op.to_dict())
                    if op.type == "MOVED" and moved_entry is not None:
                        replay_moved_files.append(moved_entry.to_dict())
                    recorder.record(
                        stage="reconcile", event_type="reconcile_completed",
                        severity="info",
                        message="source reconcile op completed",
                        source_id=(op.to_path if op.type == "MOVED" else op.path),
                        context={"op": op.to_dict()})
                    if op.type == "MOVED":
                        counts["sources_moved"] += 1
                    else:
                        counts["sources_deleted"] += 1

                if accumulated_crs:
                    finalize_stats = _finalize(
                        g.conn, accumulated_crs, state_root=state_root, ctx=ctx,
                        dry_run=dry_run, progress=finalize_progress,
                        wiring=wiring_totals)
                    recorder.record(
                        stage="finalize", event_type="finalize_completed",
                        severity="info",
                        message="finalize completed",
                        context=finalize_stats)
                else:
                    recorder.record(
                        stage="finalize", event_type="finalize_skipped",
                        severity="warning",
                        message="finalize skipped because no sources committed",
                        context={"committed_sources": 0})
    except OrchestratorInvariantError as e:
        crashed_reason = f"invariant:{e.code}"
    except Exception as e:  # unexpected — still write the summary, then propagate
        crashed_reason = f"unexpected:{type(e).__name__}"
        recorder.record(
            stage="unexpected", event_type="run_fatal", severity="run_fatal",
            message="unexpected orchestrator exception",
            exception_type=type(e).__name__, error=str(e))
        raise
    finally:
        finished_at = now_iso()
        if crashed_reason is not None:
            exit_code, exit_reason = 1, crashed_reason
            counts["sources_failed"] = max(counts["sources_failed"], 1)
            failed_source = None
            failure_stage = (
                "invariant_violation"
                if crashed_reason.startswith("invariant:")
                else "unexpected"
            )
        elif abort is not None:
            stage, sid, _err = abort
            exit_code, exit_reason = 1, f"{stage}:{sid}"
            counts["sources_failed"] = max(counts["sources_failed"], 1)
            failed_source, failure_stage = sid, stage
        elif limit_reached:
            exit_code = 0
            exit_reason = (
                "limit-reached-with-quarantines"
                if counts["sources_failed"] > 0
                else "limit-reached"
            )
            failed_source, failure_stage = None, None
        elif counts["sources_failed"] > 0:
            exit_code, exit_reason = 0, "completed_with_quarantines"
            failed_source, failure_stage = None, None
        else:
            exit_code, exit_reason = 0, "ok"
            failed_source, failure_stage = None, None
        delta = _manifest_delta(prior_full, full_manifest)
        recorder.record(
            stage="run", event_type="run_finished", severity="info",
            message="orchestrator run finished",
            context={"exit_code": exit_code, "exit_reason": exit_reason})
        alarm_counts = _event_alarm_counts(recorder)
        counts.update(alarm_counts)
        quarantined_sources = _quarantined_sources(recorder)
        summary_path = write_last_orchestrate_json(
            state_root, run_id=ctx.run_id, started_at=ctx.started_at,
            finished_at=finished_at, exit_code=exit_code, exit_reason=exit_reason,
            counts=counts, manifest_delta=delta, finalize=finalize_stats,
            event_log_path=recorder.events_path,
            event_log_failed=recorder.event_log_failed,
            quarantined_sources=quarantined_sources,
            **alarm_counts)
        # B1 delta #3 — write measurement_header.json to the run dir.
        # Post-#115 (D-115-13): pass2 stamps come from the code-owned
        # PASS2_PROMPT_VERSION constant + the loaded prompt text's SHA-256 —
        # content, version, and hash can never drift apart.
        signal = counts["sources_enriched"] - counts["sources_noise"]
        header = RunMeasurementHeader(
            run_id=ctx.run_id,
            release_version=release_version(),
            corpus_fingerprint=_corpus_fingerprint(scan.files),
            pass1_prompt_version=PASS1_PROMPT_VERSION,
            pass2_prompt_version=PASS2_PROMPT_VERSION,
            pass2_system_prompt_sha256=hashlib.sha256(
                load_system_prompt().encode("utf-8")
            ).hexdigest(),
            scanned=counts["sources_scanned"],
            to_compile=len(scan.to_compile),
            signal=signal,
            noise=counts["sources_noise"],
            p1_attempted=p1_attempted,
            p2_attempted=signal,
            searches_attempted=searches_attempted,
            searches_written=searches_written,
            # Task #122 §7.4: False = the run did not complete the finalize
            # boundary (audit-only measurements; score-skipped at the §7c gate).
            finalize_ran=finalize_stats is not None,
        )
        run_dir = runs_root / ctx.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(run_dir / "measurement_header.json", dataclasses.asdict(header))
        # #132 (D39): archive the run journal + replay sidecars — the exact
        # intake inputs accumulated above — so graphdb-kdb rebuild can
        # re-derive an orchestrator-era graph. Partial on abort/crash
        # (faithful by construction: only committed inputs were accumulated).
        # Audit infrastructure — never masks a propagating exception.
        try:
            journal_writer.archive_replay_artifacts(
                runs_root, run_id=ctx.run_id, started_at=ctx.started_at,
                finished_at=finished_at, dry_run=dry_run,
                success=(exit_code == 0),
                finalize_progress=finalize_progress["stage"], counts=counts,
                quarantined_sources=quarantined_sources,
                compile_result=_combine_crs(accumulated_crs, ctx.run_id),
                last_scan={
                    "files": replay_files, "to_compile": replay_to_compile,
                    "moved_files": replay_moved_files,
                    "to_reconcile": replay_reconcile_ops,
                })
        except Exception as e:
            recorder.record(
                stage="run", event_type="journal_archive_failed",
                severity="warning",
                message="replay journal archival failed",
                exception_type=type(e).__name__, error=str(e))
        # --emit-kpis: compute + write benchmark/runs/<run_id>/measurements.json.
        # Gated: finalize must have run (compile_result.json exists); wrapped in
        # try/except inside maybe_emit_kpis so a failure NEVER aborts the run.
        maybe_emit_kpis(
            emit_kpis=emit_kpis,
            run_id=ctx.run_id,
            run_dir=run_dir,
            graph_path=graph_path,
            state_root=state_root,
            vault_root=vault_root,
            provider=provider,
            model=model,
            header=header,
            finalize_ran=finalize_stats is not None,
            console_text=recorder.console_text() if not quiet else None,
        )

    return OrchestrateResult(
        run_id=ctx.run_id, exit_code=exit_code, exit_reason=exit_reason,
        counts=counts, manifest_delta=delta, finalize=finalize_stats,
        failed_source=failed_source, failure_stage=failure_stage,
        summary_path=summary_path, event_log_path=recorder.events_path,
        event_log_failed=recorder.event_log_failed,
        quarantined_sources=quarantined_sources)


# ---------- CLI ----------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kdb-orchestrate",
        description=(
            "End-to-end KDB conductor: scan one pipeline → per-source "
            "Pass-1 enrich → Pass-2 compile → GraphDB sync → finalize."))
    p.add_argument("--pipeline", help="pipeline id from <state-root>/pipelines.json "
                                      "(omit to list available pipelines)")
    p.add_argument("--vault-root", required=True, help="absolute vault root path")
    p.add_argument("--state-root", help="defaults to <vault-root>/KDB/state")
    p.add_argument("--graph-path", help="defaults to <vault-root>/KDB/graph "
                                        "(KDB_GRAPH_PATH env also honored by callers)")
    p.add_argument("--model", default="deepseek-v4-flash",
                   help="model id from common/models.json (resolves provider + knobs)")
    p.add_argument("--provider", default=None,
                   help="escape hatch: required only when --model is NOT a pool id "
                        "(then --model is treated as a raw SDK model string)")
    p.add_argument("--max-tokens", type=int, default=32768)
    p.add_argument("--selector-model", default=None, metavar="POOL_ID",
                   help="pass-1.5 selector seat; defaults to --model (single-model "
                        "runs). Pass a pool id to pin a different seat.")
    p.add_argument("--dry-run", action="store_true",
                   help="scan + print the plan; no enrich/compile/graph writes, no API")
    p.add_argument("--cold", action="store_true",
                   help="cold start (#135): erase derived state — KDB/wiki tree, "
                        "graph dir, manifest, alias ledger — before the scan, "
                        "then rebuild from sources alone. pipelines.json and "
                        "state/runs/ journals are preserved. With --dry-run, "
                        "previews the wipe without deleting. Prompts for "
                        "confirmation unless --yes.")
    p.add_argument("--yes", action="store_true",
                   help="skip the --cold confirmation prompt (scripts, "
                        "non-interactive use)")
    p.add_argument("--limit", type=int, default=None, metavar="N",
                   help="stop after N signal sources have been compiled; "
                        "noise is free and does not count. Finalize still runs "
                        "over the compiled batch. Remainder is picked up next run.")
    p.add_argument("--log-level", choices=["warning", "info", "debug"],
                   help="operator-visible logging level; explicit value wins "
                        "over --verbose/--debug aliases")
    p.add_argument("--verbose", action="store_true",
                   help="alias for --log-level info when --log-level is omitted")
    p.add_argument("--debug", action="store_true",
                   help="alias for --log-level debug when --log-level is omitted")
    p.add_argument("--quiet", action="store_true",
                   help="suppress the live stdout progress narrative "
                        "(the final report and event log are unaffected)")
    p.add_argument("--emit-kpis", action="store_true",
                   help="benchmark mode: after the run finalizes, compute KPIs and "
                        "write benchmark/runs/<run_id>/measurements.json. "
                        "Normal runs are unaffected when this flag is absent.")
    return p


def _resolve_log_level(args: argparse.Namespace) -> OrchestratorLogLevel:
    if args.log_level is not None:
        return args.log_level
    if args.debug:
        return "debug"
    if args.verbose:
        return "info"
    return "warning"


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    vault_root = Path(args.vault_root).resolve()
    state_root = (Path(args.state_root).resolve() if args.state_root
                  else vault_root / "KDB" / "state")
    graph_path = (Path(args.graph_path).resolve() if args.graph_path
                  else vault_root / "KDB" / "graph")

    if not args.pipeline:
        ids = pipeline_registry.list_pipelines(state_root)
        print("available pipelines: " + (", ".join(ids) if ids else "(none)"))
        return 0

    try:
        spec = resolve_models_json(args.model)
        # spec §4: a KNOWN pool id pins its provider. If --provider is also passed
        # and CONFLICTS with the pool's provider, error (catch the mistake) rather
        # than silently ignoring --provider. Same provider / absent → no error.
        if args.provider is not None and args.provider != spec.provider:
            raise PoolError(
                f"--provider {args.provider!r} conflicts with pool model "
                f"{args.model!r} (provider {spec.provider!r}). Omit --provider "
                f"for known pool ids, or pass the matching provider.")
        provider, model = spec.provider, spec.model
        route = spec.route
        use_completion_tokens = spec.use_completion_tokens
        extra_body = spec.extra_body
        temperature = spec.temperature
        ctx_window = spec.ctx_window
        price_in, price_out = spec.price_in, spec.price_out
        # Single-model default (Joseph 2026-08-04): the pass-1.5 selector
        # seat follows --model unless --selector-model pins a different one.
        selector_model_id = args.selector_model or args.model
    except UnknownModelError:
        # A dropped id is now simply not in the active pool (archived to
        # models_dropped.json), so it arrives here as UnknownModelError. The
        # escape hatch is only for ids not in the pool at all.
        if args.provider is None:
            raise  # unknown id + no override → surface the UnknownModelError
        # one-off escape hatch: raw model string, no pool metadata — the
        # route-less registry path (Class B) resolves routing from `provider`.
        provider, model = args.provider, args.model
        route = None
        use_completion_tokens, extra_body, ctx_window = False, None, None
        temperature = 0.0
        price_in, price_out = 0.0, 0.0
        # Escape-hatch runs have no pool id to follow; the selector seat
        # stays on the module fallback unless --selector-model pins one.
        selector_model_id = args.selector_model

    if args.cold and not args.dry_run and not args.yes:
        # #135 destructive-op gate: show exactly what dies, then require an
        # explicit "yes". Skipped entirely by --dry-run (nothing is deleted)
        # and --yes (scripts). EOF (non-interactive stdin) aborts with
        # guidance rather than proceeding silently.
        preview = _cold_wipe(vault_root=vault_root, state_root=state_root,
                             graph_path=graph_path, dry_run=True)
        print("*** --cold will PERMANENTLY DELETE derived KDB state:")
        print(f"    - wiki tree:    {vault_root / 'KDB' / 'wiki'} "
              f"({preview['wiki_files_removed']} files)")
        print(f"    - graph DB:     {graph_path} "
              f"({'present' if preview['graph_removed'] else 'absent'})")
        print(f"    - manifest:     {state_root / MANIFEST_NAME} "
              f"({'present' if preview['manifest_removed'] else 'absent'})")
        print(f"    - alias ledger: "
              f"{state_root / 'canonicalization' / 'aliases.json'} "
              f"({'present' if preview['alias_ledger_removed'] else 'absent'})")
        print("    pipelines.json (config) and state/runs/ journals are kept.")
        try:
            answer = input('Type "yes" to proceed: ')
        except EOFError:
            answer = ""
        if answer.strip().lower() != "yes":
            print("cold wipe declined — aborting (pass --yes to skip this "
                  "prompt in scripts).", file=sys.stderr)
            return 1

    res = run(
        pipeline_id=args.pipeline, vault_root=vault_root, state_root=state_root,
        graph_path=graph_path, provider=provider, model=model,
        max_tokens=args.max_tokens, dry_run=args.dry_run, cold=args.cold,
        limit=args.limit,
        log_level=_resolve_log_level(args), quiet=args.quiet,
        emit_kpis=args.emit_kpis,
        use_completion_tokens=use_completion_tokens, extra_body=extra_body,
        temperature=temperature, route=route,
        ctx_window=ctx_window, price_in=price_in, price_out=price_out,
        selector_model_id=selector_model_id)

    print(f"kdb-orchestrate: run_id={res.run_id} exit={res.exit_code} "
          f"reason={res.exit_reason}")
    c = res.counts
    print(f"  scanned={c['sources_scanned']} compiled={c['sources_compiled']} "
          f"noise={c['sources_noise']} moved={c['sources_moved']} "
          f"deleted={c['sources_deleted']} failed={c['sources_failed']}")
    if res.planned is not None:
        print(f"  plan: {len(res.planned['to_compile'])} to compile, "
              f"{len(res.planned['deleted'])} to delete, "
              f"{len(res.planned['moved'])} to move")
    if res.finalize is not None:
        print(f"  finalize: {res.finalize}")
    if res.summary_path is not None:
        print(f"  summary: {res.summary_path}")
    if res.event_log_path is not None:
        print(f"  event_log: {res.event_log_path}")
    if c.get("sources_quarantined", 0) > 0:
        source_ids = ", ".join(
            str(row.get("source_id")) for row in res.quarantined_sources
            if row.get("source_id") is not None)
        detail = f" ({source_ids})" if source_ids else ""
        print(f"  alarm: quarantined={c['sources_quarantined']}{detail}",
              file=sys.stderr)
    return res.exit_code


if __name__ == "__main__":
    sys.exit(main())
