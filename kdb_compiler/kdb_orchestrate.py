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

from graphdb_kdb.ingestor import apply_compile_result
from kdb_compiler import patch_applier, source_state_update
from kdb_compiler.atomic_io import atomic_write_json
from kdb_compiler.run_context import RunContext

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
