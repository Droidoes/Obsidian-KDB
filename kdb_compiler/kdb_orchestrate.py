"""kdb_orchestrate — the end-to-end conductor (Task #91, Plan 5+6).

feeder → ingestion (Pass-1 enrich) → compiler (Pass-2 compile_source) → GraphDB,
driven per-source over a single shared read-write GraphDB connection.

Wires the four shipped foundations — compile_source (produce-don't-write),
detect_orphans / wire_links (deferred finalize passes), the pipeline registry,
and scan_scope — into one loop, ending in the first live run on the test sandbox.

Commit model (β, D-91-15 — graph-sync-first): per source the conductor applies
the wiki pages, graph-syncs (Kuzu txn, orphan-marking + link-wiring deferred to
finalize), then — only on graph-sync success — writes the manifest. The manifest
write is the commit boundary, so a graph-sync failure rolls back cleanly and the
manifest is never written → the source self-heals on the next run (case-a).
Finalize runs one detect_orphans() pass, the batch wire_links() pass, kdb-clean,
and writes last_orchestrate.json.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from graphdb_kdb.ingestor import (
    apply_cleanup, apply_compile_result, detect_orphans, wire_links,
)
from kdb_compiler import patch_applier, source_state_update
from kdb_compiler.atomic_io import atomic_write_json
from kdb_compiler.kdb_clean import build_cleanup_artifacts, reap_orphans_from_graph
from kdb_compiler.run_context import RunContext, now_iso

MANIFEST_NAME = "manifest.json"


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
    threads into the next source; `cr` is accumulated for the finalize passes.
    """
    next_manifest: dict | None = None
    pages_written: list[str] = field(default_factory=list)
    cr: dict | None = None
    failure_stage: str | None = None      # apply | graph_sync | manifest_post_graph
    exception_type: str | None = None
    error: str | None = None
    graph_committed: bool = False

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
    next_manifest, _ = source_state_update.build_source_state_update(
        prior_manifest, single_scan, cr, ctx)

    # 1. apply wiki pages (stage 8). Throws ⇒ case-(a), graph untouched.
    try:
        apply_res = patch_applier.apply(
            vault_root, compile_result=cr, last_scan=single_scan,
            run_ctx=ctx, write=True)
    except Exception as e:
        return CommitResult(
            failure_stage="apply", exception_type=type(e).__name__, error=str(e))

    # 2. graph-sync (Kuzu txn). detect_orphans + wire_links deferred to finalize.
    #    Throws ⇒ Kuzu rolled back clean; manifest never written ⇒ case-(a) self-heal.
    try:
        apply_compile_result(
            cr, single_scan, ctx.run_id, conn=conn,
            detect_orphans=False, wire_links=False)
    except Exception as e:
        return CommitResult(
            pages_written=apply_res.pages_written,
            failure_stage="graph_sync", exception_type=type(e).__name__, error=str(e))

    # 3. manifest write = COMMIT BOUNDARY (β). Throws here ⇒ graph committed but
    #    manifest absent ⇒ manifest_failed_after_graph_commit (self-heals on re-run).
    try:
        atomic_write_json(state_root / MANIFEST_NAME, next_manifest)
    except Exception as e:
        return CommitResult(
            pages_written=apply_res.pages_written, graph_committed=True,
            failure_stage="manifest_post_graph",
            exception_type=type(e).__name__, error=str(e))

    return CommitResult(
        next_manifest=next_manifest, pages_written=apply_res.pages_written,
        cr=cr, graph_committed=True)


# ---------- finalize: merge crs → wire_links → orphans → cleanup → summary ----------

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
    log_entries: list[dict] = []
    warnings: list[str] = []
    aliases_emitted: list[dict] = []
    for cr in crs:
        compiled_sources.extend(cr.get("compiled_sources", []))
        log_entries.extend(cr.get("log_entries", []))
        warnings.extend(cr.get("warnings", []))
        cm = cr.get("canonical_meta") or {}
        aliases_emitted.extend(cm.get("aliases_emitted") or [])
    combined: dict = {
        "run_id": run_id, "success": True,
        "compiled_sources": compiled_sources,
        "log_entries": log_entries, "errors": [], "warnings": warnings,
    }
    if aliases_emitted:
        combined["canonical_meta"] = {"aliases_emitted": aliases_emitted}
    return combined


def _finalize(
    conn, accumulated_crs: list[dict], *,
    state_root: Path, ctx: RunContext, dry_run: bool = False,
) -> dict:
    """End-of-run passes over the final graph (combined commit sequence 5-8):

      5. wire_links(combined)  — batch LINKS_TO, all entities present (C1 fix).
      6. detect_orphans()      — single deferred orphan-marking pass.
      7. kdb-clean orphans     — reap_orphans_from_graph + build_cleanup_artifacts
                                 (cleanup journal + retraction.json, m1) + apply_cleanup.
      8. write compile_result.json (combined replay payload).

    Returns finalize counts for the run summary.
    """
    combined = _combine_crs(accumulated_crs, ctx.run_id)

    wl = wire_links(combined, conn, ctx.run_id)
    orphans = detect_orphans(conn, ctx.run_id)

    report = reap_orphans_from_graph(conn)
    reaped = len(report["reaped"])
    if not dry_run and report["reaped"]:
        finished = now_iso()
        journal, retraction = build_cleanup_artifacts(
            report, ctx.run_id, ctx.started_at, finished)
        runs_root = state_root / "runs"
        sidecar_dir = runs_root / ctx.run_id
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(sidecar_dir / "retraction.json", retraction, sort_keys=True)
        atomic_write_json(runs_root / f"{ctx.run_id}.json", journal, sort_keys=True)
        apply_cleanup(retraction, ctx.run_id, conn=conn)

    if not dry_run:
        atomic_write_json(state_root / "compile_result.json", combined)

    return {
        "links_wired": wl.edges_upserted,
        "orphans_marked": len(orphans),
        "reaped": reaped,
    }


def write_last_orchestrate_json(
    state_root: Path, *, run_id: str, started_at: str, finished_at: str,
    exit_code: int, exit_reason: str, counts: dict, manifest_delta: dict,
    finalize: dict | None = None,
) -> Path:
    """Write the slim run summary (D-91-10). Written ALWAYS — success and abort —
    so a fail-fast still leaves an inspectable record of where the run stopped."""
    summary = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "exit_code": exit_code,
        "exit_reason": exit_reason,
        "counts": counts,
        "manifest_delta": manifest_delta,
    }
    if finalize is not None:
        summary["finalize"] = finalize
    path = state_root / "last_orchestrate.json"
    atomic_write_json(path, summary)
    return path
