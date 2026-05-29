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

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from graphdb_kdb.graphdb import GraphDB
from graphdb_kdb.ingestor import (
    apply_cleanup, apply_compile_result, detect_orphans, wire_links,
)
from kdb_compiler import patch_applier, pipeline_registry, source_state_update
from kdb_compiler.atomic_io import atomic_write_json
from kdb_compiler.canonicalize import load_or_empty
from kdb_compiler.compiler import compile_source
from kdb_compiler.ingestion.enrich import enrich_one
from kdb_compiler.kdb_clean import build_cleanup_artifacts, reap_orphans_from_graph
from kdb_compiler.kdb_scan import scan_scope
from kdb_compiler.run_context import RunContext, now_iso
from kdb_compiler.source_io import SourceFrontmatter

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
        data = source_state_update.migrate_manifest_to_source_state(data)
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
    """Commit a noise source: manifest metadata_only, NO graph, NO wiki. M2:
    last_compiled_hash = post_embed_hash so the embed doesn't re-trigger enrich
    next run. to_compile=[] so apply_compile_sources doesn't error-mark it."""
    entry = dict(scan_entry)
    entry["current_hash"] = post_embed_hash
    entry["current_mtime"] = post_embed_mtime
    single_scan = {"files": [entry], "to_compile": [], "to_reconcile": []}
    next_manifest, _ = source_state_update.build_source_state_update(
        prior_manifest, single_scan, {"compiled_sources": [], "success": True}, ctx)
    rec = next_manifest["sources"][source_id]
    rec["compile_state"] = "metadata_only"
    rec["last_compiled_hash"] = post_embed_hash
    atomic_write_json(state_root / MANIFEST_NAME, next_manifest)
    return next_manifest


def _commit_reconcile_op(
    op, *, moved_entry, prior_manifest: dict, conn, state_root: Path, ctx: RunContext,
) -> dict:
    """Commit a MOVED/DELETED reconcile op. Graph handles both via to_reconcile
    (Phase 2); manifest handles MOVED via files[] + DELETED via to_reconcile[]."""
    op_dict = op.to_dict()
    files = [moved_entry.to_dict()] if (op.type == "MOVED" and moved_entry) else []
    single_scan = {"files": files, "to_compile": [], "to_reconcile": [op_dict]}
    apply_compile_result(
        {"compiled_sources": []}, single_scan, ctx.run_id,
        conn=conn, detect_orphans=False, wire_links=False)
    next_manifest, _ = source_state_update.build_source_state_update(
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
    planned: dict | None = None     # dry-run plan preview

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _empty_counts() -> dict:
    return {
        "sources_scanned": 0, "sources_enriched": 0, "sources_compiled": 0,
        "sources_noise": 0, "sources_moved": 0, "sources_deleted": 0,
        "sources_failed": 0,
    }


def run(
    *, pipeline_id: str, vault_root: Path, state_root: Path, graph_path: Path,
    provider: str, model: str, max_tokens: int = 32768, dry_run: bool = False,
) -> OrchestrateResult:
    """End-to-end conductor for one pipeline: scan → per-source enrich/compile/
    commit (β) → reconcile → finalize. Fail-fast (D-91-8): the first enrich/
    compile/commit failure aborts the run; already-committed sources stay
    committed (β makes each commit self-contained). The run summary
    (last_orchestrate.json) is written ALWAYS — success, abort, or crash."""
    vault_root = Path(vault_root)
    state_root = Path(state_root)
    graph_path = Path(graph_path)
    manifest_path = state_root / MANIFEST_NAME

    pipeline = pipeline_registry.get_pipeline(state_root, pipeline_id)
    prior_full = _stamp_legacy_pipeline_id(_load_full_manifest(manifest_path), pipeline_id)
    prior_flat = _flat_prior(prior_full)
    ctx = RunContext.new(dry_run=dry_run, vault_root=vault_root)
    ledger = load_or_empty(state_root / "canonicalization" / "aliases.json")
    runs_root = state_root / "runs"

    full_manifest = prior_full
    accumulated_crs: list[dict] = []
    counts = _empty_counts()
    finalize_stats: dict | None = None
    planned: dict | None = None
    abort: tuple[str, str, str | None] | None = None   # (stage, source_id, error)
    crashed_reason: str | None = None

    # Scan needs no graph — do it first so --dry-run can preview without opening
    # (or mutating) the graph and without firing any API call.
    scan = scan_scope(
        Path(pipeline.root), vault_root, pipeline_id=pipeline_id,
        prior=prior_flat, run_ctx=ctx,
        excludes=pipeline.excludes, file_types=set(pipeline.file_types))
    counts["sources_scanned"] = len(scan.files)

    if dry_run:
        planned = {
            "to_compile": list(scan.to_compile),
            "deleted": [op.to_dict() for op in scan.to_reconcile if op.type == "DELETED"],
            "moved": [op.to_dict() for op in scan.to_reconcile if op.type == "MOVED"],
        }
        finished_at = now_iso()
        summary_path = write_last_orchestrate_json(
            state_root, run_id=ctx.run_id, started_at=ctx.started_at,
            finished_at=finished_at, exit_code=0, exit_reason="dry-run",
            counts=counts, manifest_delta={"added": [], "removed": [], "changed": []})
        return OrchestrateResult(
            run_id=ctx.run_id, exit_code=0, exit_reason="dry-run", counts=counts,
            manifest_delta={"added": [], "removed": [], "changed": []},
            summary_path=summary_path, planned=planned)

    try:
        with GraphDB(graph_path) as g:
            files_by_id = {e.path: e for e in scan.files}

            # --- compile queue: NEW/CHANGED (+ MOVED+CHANGED) ---
            for source_id in scan.to_compile:
                scan_entry = files_by_id[source_id]
                enrich = enrich_one(
                    source_path=vault_root / source_id, source_id=source_id,
                    runs_root=runs_root, run_id=ctx.run_id,
                    provider=provider, model=model,
                    force_signal=pipeline.force_signal, force_noise=pipeline.force_noise)
                if enrich.outcome == "enrich_failed":
                    abort = ("enrich", source_id, enrich.error)
                    break
                counts["sources_enriched"] += 1

                if enrich.parsed_envelope["kdb_signal"] == "noise":
                    full_manifest = _commit_noise_source(
                        source_id=source_id, post_embed_hash=enrich.post_embed_hash,
                        post_embed_mtime=enrich.post_embed_mtime,
                        scan_entry=scan_entry.to_dict(), prior_manifest=full_manifest,
                        state_root=state_root, ctx=ctx)
                    counts["sources_noise"] += 1
                    continue

                result = compile_source(
                    source_id=source_id, body=enrich.body,
                    frontmatter=SourceFrontmatter.from_dict(enrich.parsed_envelope),
                    conn=g.conn, vault_root=vault_root, state_root=state_root, ctx=ctx,
                    ledger=ledger, provider=provider, model=model, max_tokens=max_tokens)
                if not result.ok:
                    abort = (result.failure_stage or "compile", source_id, result.error)
                    break

                commit = _commit_source(
                    cr=result.cr, source_id=source_id,
                    post_embed_hash=enrich.post_embed_hash,
                    post_embed_mtime=enrich.post_embed_mtime,
                    scan_entry=scan_entry.to_dict(), prior_manifest=full_manifest,
                    vault_root=vault_root, state_root=state_root, conn=g.conn, ctx=ctx)
                if not commit.ok:
                    abort = (commit.failure_stage or "commit", source_id, commit.error)
                    break
                full_manifest = commit.next_manifest
                accumulated_crs.append(commit.cr)
                counts["sources_compiled"] += 1

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
                    if op.type == "MOVED":
                        counts["sources_moved"] += 1
                    else:
                        counts["sources_deleted"] += 1

                finalize_stats = _finalize(
                    g.conn, accumulated_crs, state_root=state_root, ctx=ctx,
                    dry_run=dry_run)
    except Exception as e:  # unexpected — still write the summary, then propagate
        crashed_reason = f"unexpected:{type(e).__name__}"
        raise
    finally:
        finished_at = now_iso()
        if crashed_reason is not None:
            exit_code, exit_reason = 1, crashed_reason
            counts["sources_failed"] = 1
            failed_source, failure_stage = None, "unexpected"
        elif abort is not None:
            stage, sid, _err = abort
            exit_code, exit_reason = 1, f"{stage}:{sid}"
            counts["sources_failed"] = 1
            failed_source, failure_stage = sid, stage
        else:
            exit_code, exit_reason = 0, "ok"
            failed_source, failure_stage = None, None
        delta = _manifest_delta(prior_full, full_manifest)
        summary_path = write_last_orchestrate_json(
            state_root, run_id=ctx.run_id, started_at=ctx.started_at,
            finished_at=finished_at, exit_code=exit_code, exit_reason=exit_reason,
            counts=counts, manifest_delta=delta, finalize=finalize_stats)

    return OrchestrateResult(
        run_id=ctx.run_id, exit_code=exit_code, exit_reason=exit_reason,
        counts=counts, manifest_delta=delta, finalize=finalize_stats,
        failed_source=failed_source, failure_stage=failure_stage,
        summary_path=summary_path)


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
    p.add_argument("--provider", default="deepseek")
    p.add_argument("--model", default="deepseek-v4-flash")
    p.add_argument("--max-tokens", type=int, default=32768)
    p.add_argument("--dry-run", action="store_true",
                   help="scan + print the plan; no enrich/compile/graph writes, no API")
    return p


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

    res = run(
        pipeline_id=args.pipeline, vault_root=vault_root, state_root=state_root,
        graph_path=graph_path, provider=args.provider, model=args.model,
        max_tokens=args.max_tokens, dry_run=args.dry_run)

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
    return res.exit_code


if __name__ == "__main__":
    sys.exit(main())
