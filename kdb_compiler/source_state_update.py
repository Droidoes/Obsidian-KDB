"""source_state_update — source-meta-only ledger (D50 Phase D).

Extracted from manifest_update.py as a make-before-break replacement.
Owns the source lifecycle (sources{}, tombstones{}, runs{}, stats{}) with
NO dependency on pages, orphans, links, or any ontology concept. GraphDB
owns all ontology state; this module owns source-file metadata only.

Source record shape:
    Identity:   source_id, canonical_path, status
    File meta:  file_type, hash, mtime, size_bytes
    Lifecycle:  first_seen_at, last_seen_at, last_compiled_at, last_run_id,
                compile_state, compile_count, last_compiled_hash
    Compile:    summary_slug, compiled_title, parser, compiler_version,
                schema_version_used
    History:    previous_versions[]

Wired into the orchestrator in Phase F. Until then, tested in parallel
with manifest_update.py which continues to own production writes.
"""
from __future__ import annotations

import copy
from typing import Any

from .run_context import SCHEMA_VERSION, RunContext


PREV_VERSIONS_CAP = 20


# ---- shape bootstrap ----

def ensure_source_state_shape(state: dict, *, ctx: RunContext) -> dict:
    """Seed top-level keys on a bootstrap (empty) state dict. Idempotent."""
    if not state:
        return {
            "schema_version": SCHEMA_VERSION,
            "updated_at": ctx.started_at,
            "sources": {},
            "tombstones": {},
            "runs": {"last_run_id": None, "last_successful_run_id": None},
            "stats": {"total_raw_files": 0, "total_runs": 0},
        }
    state.setdefault("schema_version", SCHEMA_VERSION)
    state.setdefault("updated_at", ctx.started_at)
    state.setdefault("sources", {})
    state.setdefault("tombstones", {})
    state.setdefault("runs", {"last_run_id": None, "last_successful_run_id": None})
    state.setdefault("stats", {"total_raw_files": 0, "total_runs": 0})
    return state


# ---- source record seeding ----

def _seed_source_record(file_entry: dict, ctx: RunContext) -> dict:
    is_binary = file_entry.get("is_binary", False)
    return {
        "source_id": file_entry["path"],
        "canonical_path": file_entry["path"],
        "status": "active",
        "file_type": file_entry["file_type"],
        "hash": file_entry["current_hash"],
        "mtime": file_entry["current_mtime"],
        "size_bytes": file_entry["size_bytes"],
        "first_seen_at": ctx.started_at,
        "last_seen_at": ctx.started_at,
        "last_compiled_at": None,
        "last_run_id": ctx.run_id,
        "compile_state": "metadata_only" if is_binary else "pending",
        "compile_count": 0,
        "last_compiled_hash": file_entry["current_hash"] if is_binary else None,
        "summary_slug": None,
        "compiled_title": None,
        "parser": None,
        "compiler_version": None,
        "schema_version_used": None,
        "previous_versions": [],
    }


# ---- previous_versions management ----

def _append_prev_version(rec: dict, *, hash_: str | None, mtime: float | None,
                         size_bytes: int | None, compiled_at: str | None,
                         run_id: str | None) -> None:
    entry = {
        "hash": hash_,
        "mtime": mtime,
        "size_bytes": size_bytes,
        "compiled_at": compiled_at,
        "run_id": run_id,
    }
    history = rec.setdefault("previous_versions", [])
    history.append(entry)
    if len(history) > PREV_VERSIONS_CAP:
        del history[: len(history) - PREV_VERSIONS_CAP]


# ---- tombstones ----

def _write_tombstone_moved(state: dict, *, old_path: str, new_path: str,
                           hash_: str, ctx: RunContext) -> None:
    state["tombstones"][old_path] = {
        "source_id": old_path,
        "status": "moved",
        "moved_to": new_path,
        "hash": hash_,
        "recorded_at": ctx.started_at,
        "last_run_id": ctx.run_id,
    }


def _write_tombstone_deleted(state: dict, *, path: str, hash_: str | None,
                             ctx: RunContext) -> None:
    state["tombstones"][path] = {
        "source_id": path,
        "status": "deleted",
        "hash": hash_,
        "recorded_at": ctx.started_at,
        "last_run_id": ctx.run_id,
    }


# ---- scan reconciliation (source-only) ----

def apply_scan_reconciliation(state: dict, last_scan: dict, ctx: RunContext) -> dict:
    """Apply NEW/CHANGED/UNCHANGED/MOVED + DELETED to sources{} and tombstones{}.

    Unlike manifest_update's version, this does NOT touch pages or orphans.
    """
    sources = state["sources"]

    for fe in last_scan.get("files", []):
        path = fe["path"]
        action = fe["action"]

        if action == "NEW":
            sources[path] = _seed_source_record(fe, ctx)

        elif action == "CHANGED":
            rec = sources.get(path)
            if rec is None:
                sources[path] = _seed_source_record(fe, ctx)
                continue
            _append_prev_version(
                rec,
                hash_=rec.get("hash"),
                mtime=rec.get("mtime"),
                size_bytes=rec.get("size_bytes"),
                compiled_at=rec.get("last_compiled_at"),
                run_id=rec.get("last_run_id"),
            )
            rec["hash"] = fe["current_hash"]
            rec["mtime"] = fe["current_mtime"]
            rec["size_bytes"] = fe["size_bytes"]
            rec["file_type"] = fe["file_type"]
            rec["status"] = "active"
            rec["last_seen_at"] = ctx.started_at
            rec["last_run_id"] = ctx.run_id
            if fe.get("is_binary"):
                rec["last_compiled_hash"] = fe["current_hash"]

        elif action == "UNCHANGED":
            rec = sources.get(path)
            if rec is None:
                sources[path] = _seed_source_record(fe, ctx)
                continue
            rec["last_seen_at"] = ctx.started_at

        elif action == "MOVED":
            prev_path = fe.get("previous_path") or path
            rec = sources.pop(prev_path, None)
            if rec is None:
                rec = _seed_source_record(fe, ctx)
            rec["source_id"] = path
            rec["canonical_path"] = path
            rec["hash"] = fe["current_hash"]
            rec["mtime"] = fe["current_mtime"]
            rec["size_bytes"] = fe["size_bytes"]
            rec["file_type"] = fe["file_type"]
            rec["status"] = "active"
            rec["last_seen_at"] = ctx.started_at
            rec["last_run_id"] = ctx.run_id
            sources[path] = rec
            _write_tombstone_moved(
                state, old_path=prev_path, new_path=path,
                hash_=fe["current_hash"], ctx=ctx,
            )

        else:
            ctx.append_log("warning", f"unknown scan action {action!r} for {path}")

    for op in last_scan.get("to_reconcile", []):
        if op.get("type") == "DELETED":
            path = op["path"]
            removed = sources.pop(path, None)
            tomb_hash = op.get("hash") or (removed.get("hash") if removed else None)
            _write_tombstone_deleted(state, path=path, hash_=tomb_hash, ctx=ctx)

    return state


# ---- compile-source application ----

def _resolve_source_hash(state: dict, last_scan: dict, source_id: str) -> str | None:
    rec = state["sources"].get(source_id)
    if rec:
        return rec.get("hash")
    for fe in last_scan.get("files", []):
        if fe["path"] == source_id:
            return fe.get("current_hash")
    return None


def apply_compile_sources(state: dict, compile_result: dict,
                          last_scan: dict, ctx: RunContext) -> dict:
    """Apply compiled_sources[] to source records. No page upserts."""
    expected = set(last_scan.get("to_compile", []))
    present: set[str] = set()

    for cs in compile_result.get("compiled_sources", []):
        source_id = cs["source_id"]
        present.add(source_id)
        summary_slug = cs["summary_slug"]
        source_hash = _resolve_source_hash(state, last_scan, source_id)

        summary_title = next(
            (p["title"] for p in cs.get("pages", []) if p["slug"] == summary_slug),
            None,
        )

        rec = state["sources"].get(source_id)
        if rec is None:
            rec = {
                "source_id": source_id, "canonical_path": source_id,
                "status": "active", "file_type": "markdown",
                "hash": source_hash, "mtime": None, "size_bytes": None,
                "first_seen_at": ctx.started_at, "last_seen_at": ctx.started_at,
                "last_compiled_at": None, "last_run_id": ctx.run_id,
                "compile_state": "pending", "compile_count": 0,
                "last_compiled_hash": None,
                "summary_slug": None, "compiled_title": None,
                "parser": None, "compiler_version": None,
                "schema_version_used": None,
                "previous_versions": [],
            }
            state["sources"][source_id] = rec

        rec["compile_state"] = "recompiled" if rec.get("compile_count", 0) > 0 else "compiled"
        rec["compile_count"] = int(rec.get("compile_count", 0)) + 1
        rec["last_compiled_at"] = ctx.started_at
        rec["last_run_id"] = ctx.run_id
        rec["last_compiled_hash"] = source_hash
        rec["summary_slug"] = summary_slug
        rec["compiled_title"] = summary_title
        rec["parser"] = "markdown-basic"
        rec["compiler_version"] = ctx.compiler_version
        rec["schema_version_used"] = ctx.schema_version

    # Error-mark sources that should have compiled but didn't.
    missing = expected - present
    for path in sorted(missing):
        rec = state["sources"].get(path)
        if rec is not None:
            rec["compile_state"] = "error"
            rec["last_run_id"] = ctx.run_id
        ctx.append_log("warning", f"missing compile output for {path}", path=path)

    return state


# ---- stats + runs pointer ----

def recompute_source_stats(state: dict, compile_result: dict, ctx: RunContext,
                           *, prior_runs: dict) -> dict:
    """Recompute source-only stats and runs pointers."""
    state["stats"] = {
        "total_raw_files": len(state["sources"]),
        "total_runs": int(prior_runs.get("total_runs", 0)),
    }
    prior_last = prior_runs.get("last_run_id")
    if ctx.run_id != prior_last:
        state["stats"]["total_runs"] += 1

    state["runs"]["last_run_id"] = ctx.run_id
    if compile_result.get("success"):
        state["runs"]["last_successful_run_id"] = ctx.run_id
    else:
        state["runs"]["last_successful_run_id"] = prior_runs.get("last_successful_run_id")
    state["updated_at"] = ctx.started_at
    return state


# ---- stage payload (for journal integration) ----

def _build_stage_payload(prior: dict, next_state: dict, last_scan: dict) -> dict:
    """Compute delta payload for the run journal.

    Flat shape (no nested deltas/counts). Phase F must reconcile with
    RunJournalBuilder._build_summary which reads the old nested format.
    """
    prior_sources = set(prior.get("sources", {}).keys()) if prior else set()
    next_sources = set(next_state.get("sources", {}).keys())

    moved_pairs: list[dict] = []
    for op in last_scan.get("to_reconcile", []):
        if op.get("type") == "MOVED":
            moved_pairs.append({"from": op.get("from"), "to": op.get("to")})

    sources_changed: list[str] = []
    if prior:
        sources_changed = sorted(
            s for s in (prior_sources & next_sources)
            if prior["sources"][s].get("hash") != next_state["sources"][s].get("hash")
        )

    return {
        "sources_added": sorted(next_sources - prior_sources),
        "sources_removed": sorted(prior_sources - next_sources),
        "sources_moved": moved_pairs,
        "sources_changed": sources_changed,
        "sources_after": len(next_state["sources"]),
        "tombstones_after": len(next_state["tombstones"]),
    }


# ---- public orchestrator ----

def build_source_state_update(
    prior: dict, last_scan: dict, compile_result: dict, ctx: RunContext,
) -> tuple[dict, dict]:
    """Pure. Returns (next_state, stage_payload). No I/O.

    Applies scan reconciliation + compile-source advancement to produce a
    source-meta-only state dict. No pages, no orphans, no links.
    """
    next_state = copy.deepcopy(prior) if prior else {}
    prior_runs_snapshot: dict[str, Any] = {}
    if next_state:
        prior_runs_snapshot = dict(next_state.get("runs", {}))
        prior_runs_snapshot["total_runs"] = next_state.get("stats", {}).get("total_runs", 0)

    next_state = ensure_source_state_shape(next_state, ctx=ctx)
    next_state = apply_scan_reconciliation(next_state, last_scan, ctx)
    next_state = apply_compile_sources(next_state, compile_result, last_scan, ctx)
    next_state = recompute_source_stats(
        next_state, compile_result, ctx, prior_runs=prior_runs_snapshot,
    )

    payload = _build_stage_payload(prior, next_state, last_scan)
    return next_state, payload
