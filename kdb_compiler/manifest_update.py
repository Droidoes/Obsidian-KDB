"""manifest_update — applies compile_result.json + last_scan.json to manifest.json.

Pipeline position:
    kdb_scan -> planner -> compiler -> validate -> patch_applier -> [manifest_update]

Responsibilities:
    * Read manifest.json, last_scan.json, compile_result.json.
    * Apply scan reconciliation (NEW/CHANGED/UNCHANGED/MOVED + DELETED tombstones).
    * Apply compiled_sources[] payloads (page upserts, source outputs/provenance/links).
    * Mark orphan_candidate pages whose supports_page_existence becomes empty;
      reactivate previously-orphaned pages whose support returns.
    * Preserve previous_versions[] per source (cap 20).
    * Recompute stats, run pointers, updated_at.
    * Journal-then-pointer: write runs/<run_id>.json FIRST, then manifest.json.

Design (D22): pure-core / I/O-shell. `build_manifest_update()` is pure and
testable; `write_outputs()` is the only function that touches disk.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import atomic_io, paths
from .run_context import SCHEMA_VERSION, RunContext, now_iso
from . import __version__

DEFAULT_KB_ID = "joseph-kdb"
PREV_VERSIONS_CAP = 20

# Settings echoed into a bootstrapped manifest (derived from paths module defaults).
_DEFAULT_SETTINGS: dict[str, Any] = {
    "raw_root": "KDB/raw",
    "wiki_root": "KDB/wiki",
    "summaries_root": "KDB/wiki/summaries",
    "concepts_root": "KDB/wiki/concepts",
    "articles_root": "KDB/wiki/articles",
    "hash_algorithm": "sha256",
    "rename_detection": True,
    "delete_policy": "mark_orphan_candidate",
    "removed_link_policy": "soft_remove",
    "full_rebuild_supported": True,
}


class ManifestInvariantError(AssertionError):
    """Raised when assert_manifest_invariants() finds structural damage."""


# ---------- I/O: load ----------

def load_inputs(state_root: Path) -> tuple[dict, dict, dict]:
    """Load (prior_manifest, last_scan, compile_result) from state_root/.

    prior_manifest is {} if manifest.json does not exist (bootstrap case).
    last_scan.json and compile_result.json are required.
    """
    state_root = Path(state_root)
    manifest_path = state_root / "manifest.json"
    scan_path = state_root / "last_scan.json"
    compile_path = state_root / "compile_result.json"

    prior: dict = {}
    if manifest_path.exists():
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))

    if not scan_path.exists():
        raise FileNotFoundError(f"missing last_scan.json at {scan_path}")
    if not compile_path.exists():
        raise FileNotFoundError(f"missing compile_result.json at {compile_path}")

    last_scan = json.loads(scan_path.read_text(encoding="utf-8"))
    compile_result = json.loads(compile_path.read_text(encoding="utf-8"))

    if compile_result.get("run_id") != last_scan.get("run_id"):
        raise ValueError(
            f"run_id mismatch: last_scan={last_scan.get('run_id')!r} "
            f"compile_result={compile_result.get('run_id')!r}"
        )
    return prior, last_scan, compile_result


# ---------- run context bootstrap ----------

@dataclass
class _InputPaths:
    scan_path: str
    compile_path: str


def build_run_ctx(
    state_root: Path,
    compile_result: dict,
    *,
    vault_root: Path | None = None,
    dry_run: bool = False,
) -> RunContext:
    """Construct a RunContext pinned to compile_result.run_id."""
    run_id = compile_result["run_id"]
    now = now_iso()
    root = vault_root if vault_root is not None else paths.vault_root()
    return RunContext(
        run_id=run_id,
        started_at=now,
        compiler_version=__version__,
        schema_version=SCHEMA_VERSION,
        dry_run=dry_run,
        vault_root=root,
        kdb_root=paths.kdb_root(root),
    )


# ---------- pure core ----------

def ensure_manifest_shape(manifest: dict, *, ctx: RunContext, kb_id: str = DEFAULT_KB_ID) -> dict:
    """Seed top-level keys on a bootstrap (empty) manifest. Idempotent."""
    if not manifest:
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "kb_id": kb_id,
            "created_at": ctx.started_at,
            "updated_at": ctx.started_at,
            "settings": dict(_DEFAULT_SETTINGS),
            "stats": {
                "total_raw_files": 0,
                "total_pages": 0,
                "total_summary_pages": 0,
                "total_concept_pages": 0,
                "total_article_pages": 0,
                "total_runs": 0,
            },
            "runs": {"last_run_id": None, "last_successful_run_id": None},
            "sources": {},
            "pages": {},
            "orphans": {},
            "tombstones": {},
        }
        return manifest

    manifest.setdefault("schema_version", SCHEMA_VERSION)
    manifest.setdefault("kb_id", kb_id)
    manifest.setdefault("created_at", ctx.started_at)
    manifest.setdefault("updated_at", ctx.started_at)
    manifest.setdefault("settings", dict(_DEFAULT_SETTINGS))
    manifest.setdefault("stats", {
        "total_raw_files": 0, "total_pages": 0, "total_summary_pages": 0,
        "total_concept_pages": 0, "total_article_pages": 0, "total_runs": 0,
    })
    manifest.setdefault("runs", {"last_run_id": None, "last_successful_run_id": None})
    for key in ("sources", "pages", "orphans", "tombstones"):
        manifest.setdefault(key, {})
    return manifest


def _append_prev_version(source_record: dict, *, hash_: str, mtime: float,
                         size_bytes: int, compiled_at: str | None, run_id: str) -> None:
    """Append to previous_versions[], cap to PREV_VERSIONS_CAP (FIFO)."""
    entry = {
        "hash": hash_,
        "mtime": mtime,
        "size_bytes": size_bytes,
        "compiled_at": compiled_at,
        "run_id": run_id,
    }
    history = source_record.setdefault("previous_versions", [])
    history.append(entry)
    if len(history) > PREV_VERSIONS_CAP:
        del history[: len(history) - PREV_VERSIONS_CAP]


def _seed_source_record(file_entry: dict, ctx: RunContext) -> dict:
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
        "compile_state": "metadata_only" if file_entry.get("is_binary") else "compiled",
        "compile_count": 0,
        "summary_page": None,
        "outputs_created": [],
        "outputs_touched": [],
        "concept_ids": [],
        "link_operations": {"links_added": 0, "links_removed": 0, "backlink_edits": 0},
        "provenance": {},
        "previous_versions": [],
    }


def _write_tombstone_moved(manifest: dict, *, old_path: str, new_path: str,
                           hash_: str, ctx: RunContext) -> None:
    manifest["tombstones"][old_path] = {
        "source_id": old_path,
        "status": "moved",
        "moved_to": new_path,
        "hash": hash_,
        "recorded_at": ctx.started_at,
        "last_run_id": ctx.run_id,
    }


def _write_tombstone_deleted(manifest: dict, *, path: str, hash_: str | None,
                             ctx: RunContext) -> None:
    manifest["tombstones"][path] = {
        "source_id": path,
        "status": "deleted",
        "hash": hash_,
        "recorded_at": ctx.started_at,
        "last_run_id": ctx.run_id,
    }


def _purge_source_from_pages(manifest: dict, source_id: str, *, also_from_support: bool) -> None:
    """Remove a source_id from every page's source_refs (and optionally support)."""
    for page in manifest["pages"].values():
        refs = page.get("source_refs", [])
        page["source_refs"] = [r for r in refs if r.get("source_id") != source_id]
        if also_from_support:
            support = page.get("supports_page_existence", [])
            page["supports_page_existence"] = [s for s in support if s != source_id]


def _rekey_source_in_pages(manifest: dict, *, old_id: str, new_id: str) -> None:
    """Rewrite source_id references on MOVED."""
    for page in manifest["pages"].values():
        for ref in page.get("source_refs", []):
            if ref.get("source_id") == old_id:
                ref["source_id"] = new_id
        page["supports_page_existence"] = [
            new_id if s == old_id else s for s in page.get("supports_page_existence", [])
        ]


def apply_scan_reconciliation(manifest: dict, last_scan: dict, ctx: RunContext) -> dict:
    """Apply NEW/CHANGED/UNCHANGED/MOVED files + DELETED reconcile ops to sources{}."""
    sources: dict = manifest["sources"]

    for fe in last_scan.get("files", []):
        path = fe["path"]
        action = fe["action"]

        if action == "NEW":
            sources[path] = _seed_source_record(fe, ctx)

        elif action == "CHANGED":
            rec = sources.get(path)
            if rec is None:
                # Defensive: treat as NEW if prior not present.
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

        elif action == "UNCHANGED":
            rec = sources.get(path)
            if rec is None:
                sources[path] = _seed_source_record(fe, ctx)
                continue
            rec["last_seen_at"] = ctx.started_at
            # NOTE: do NOT bump last_run_id / last_compiled_at / compile_count.

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
                manifest, old_path=prev_path, new_path=path,
                hash_=fe["current_hash"], ctx=ctx,
            )
            _rekey_source_in_pages(manifest, old_id=prev_path, new_id=path)

        else:
            ctx.append_log("warning", f"unknown scan action {action!r} for {path}")

    for op in last_scan.get("to_reconcile", []):
        if op.get("type") == "DELETED":
            path = op["path"]
            removed = sources.pop(path, None)
            tomb_hash = op.get("hash") or (removed.get("hash") if removed else None)
            _write_tombstone_deleted(manifest, path=path, hash_=tomb_hash, ctx=ctx)
            _purge_source_from_pages(manifest, path, also_from_support=True)

    return manifest


def _resolve_source_hash(manifest: dict, last_scan: dict, source_id: str) -> str | None:
    """Look up a source's current hash from manifest first, then last_scan files[]."""
    rec = manifest["sources"].get(source_id)
    if rec:
        return rec.get("hash")
    for fe in last_scan.get("files", []):
        if fe["path"] == source_id:
            return fe.get("current_hash")
    return None


def _merge_source_refs(existing: list[dict], new_ref: dict) -> list[dict]:
    """Dedupe by (source_id, role); refreshes hash on match."""
    seen_key = (new_ref["source_id"], new_ref["role"])
    merged: list[dict] = []
    replaced = False
    for ref in existing:
        key = (ref.get("source_id"), ref.get("role"))
        if key == seen_key:
            merged.append(dict(new_ref))
            replaced = True
        else:
            merged.append(ref)
    if not replaced:
        merged.append(dict(new_ref))
    return merged


def _ensure_page(manifest: dict, *, page_key: str, slug: str, page_type: str,
                 intent: dict, source_id: str, role: str, source_hash: str | None,
                 ctx: RunContext) -> tuple[dict, bool]:
    """Upsert a page record. Returns (record, created_flag)."""
    existing = manifest["pages"].get(page_key)
    new_ref = {"source_id": source_id, "hash": source_hash, "role": role}

    if existing is None:
        rec = {
            "page_id": page_key,
            "slug": slug,
            "page_type": page_type,
            "status": "active",
            "title": intent["title"],
            "created_at": ctx.started_at,
            "updated_at": ctx.started_at,
            "last_run_id": ctx.run_id,
            "source_refs": [new_ref],
            "supports_page_existence": sorted(set([source_id] + list(intent.get("supports_page_existence", [])))),
            "outgoing_links": list(intent.get("outgoing_links", [])),
            "incoming_links_known": [],
            "last_link_reconciled_at": ctx.started_at,
            "confidence": intent.get("confidence", "medium"),
            "orphan_candidate": False,
        }
        manifest["pages"][page_key] = rec
        return rec, True

    rec = existing
    rec["title"] = intent["title"]
    rec["outgoing_links"] = list(intent.get("outgoing_links", []))
    rec["confidence"] = intent.get("confidence", rec.get("confidence", "medium"))
    rec["source_refs"] = _merge_source_refs(rec.get("source_refs", []), new_ref)
    union = set(rec.get("supports_page_existence", []))
    union.add(source_id)
    union.update(intent.get("supports_page_existence", []))
    rec["supports_page_existence"] = sorted(union)
    rec["status"] = "active"
    rec["orphan_candidate"] = False
    rec["updated_at"] = ctx.started_at
    rec["last_run_id"] = ctx.run_id
    return rec, False


def _diff_link_counts(prev: list[str], curr: list[str]) -> dict[str, int]:
    p, c = set(prev), set(curr)
    return {
        "links_added": len(c - p),
        "links_removed": len(p - c),
        "backlink_edits": len(p.symmetric_difference(c)),
    }


def apply_compile_result(manifest: dict, compile_result: dict, last_scan: dict,
                         ctx: RunContext) -> dict:
    """Apply compiled_sources[] to pages{} and source output fields."""
    expected = set(last_scan.get("to_compile", []))
    present: set[str] = set()

    for cs in compile_result.get("compiled_sources", []):
        source_id = cs["source_id"]
        present.add(source_id)
        summary_slug = cs["summary_slug"]
        source_hash = _resolve_source_hash(manifest, last_scan, source_id)

        created_keys: list[str] = []
        touched_keys: list[str] = []
        prev_outgoing_union: list[str] = []
        curr_outgoing_union: list[str] = []

        for intent in cs.get("pages", []):
            slug = intent["slug"]
            ptype = intent["page_type"]
            page_key = paths.slug_to_relpath(slug, ptype)
            role = "primary" if slug == summary_slug else "supporting"

            existing = manifest["pages"].get(page_key)
            if existing is not None:
                prev_outgoing_union.extend(existing.get("outgoing_links", []))

            _, created = _ensure_page(
                manifest,
                page_key=page_key, slug=slug, page_type=ptype,
                intent=intent, source_id=source_id, role=role,
                source_hash=source_hash, ctx=ctx,
            )
            if created:
                created_keys.append(page_key)
            touched_keys.append(page_key)
            curr_outgoing_union.extend(intent.get("outgoing_links", []))

        summary_key = paths.slug_to_relpath(summary_slug, "summary")

        rec = manifest["sources"].get(source_id)
        if rec is None:
            # Shouldn't normally happen — scan missed this source. Seed a stub.
            rec = {
                "source_id": source_id, "canonical_path": source_id, "status": "active",
                "file_type": "markdown", "hash": source_hash, "mtime": None,
                "size_bytes": None, "first_seen_at": ctx.started_at,
                "last_seen_at": ctx.started_at, "last_compiled_at": None,
                "last_run_id": ctx.run_id, "compile_state": "compiled",
                "compile_count": 0, "summary_page": None, "outputs_created": [],
                "outputs_touched": [], "concept_ids": [],
                "link_operations": {"links_added": 0, "links_removed": 0, "backlink_edits": 0},
                "provenance": {}, "previous_versions": [],
            }
            manifest["sources"][source_id] = rec

        rec["compile_state"] = "recompiled" if rec.get("compile_count", 0) > 0 else "compiled"
        rec["compile_count"] = int(rec.get("compile_count", 0)) + 1
        rec["last_compiled_at"] = ctx.started_at
        rec["last_run_id"] = ctx.run_id
        rec["summary_page"] = summary_key
        rec["outputs_created"] = sorted(set(created_keys))
        rec["outputs_touched"] = sorted(set(touched_keys))
        rec["concept_ids"] = list(cs.get("concept_slugs", []))
        rec["link_operations"] = _diff_link_counts(prev_outgoing_union, curr_outgoing_union)

        summary_title = next(
            (p["title"] for p in cs.get("pages", []) if p["slug"] == summary_slug),
            None,
        )
        rec["provenance"] = {
            "title": summary_title,
            "parser": "markdown-basic",
            "compiler_version": ctx.compiler_version,
            "schema_version_used": ctx.schema_version,
        }

    # Error-mark sources that should have compiled but didn't.
    missing = expected - present
    for path in sorted(missing):
        rec = manifest["sources"].get(path)
        if rec is not None:
            rec["compile_state"] = "error"
            rec["last_run_id"] = ctx.run_id
        ctx.append_log("warning", f"missing compile output for {path}", path=path)

    # Orphan-flag / reactivate pass.
    for page_key, page in manifest["pages"].items():
        support = page.get("supports_page_existence", [])
        if not support:
            page["status"] = "orphan_candidate"
            page["orphan_candidate"] = True
            manifest["orphans"].setdefault(page_key, {
                "page_id": page_key,
                "flagged_at": ctx.started_at,
                "reason": "supports_page_existence empty",
                "previous_supporting_sources": [],
                "recommended_action": "review_manually",
                "last_run_id": ctx.run_id,
            })
        else:
            if page_key in manifest["orphans"]:
                del manifest["orphans"][page_key]
            if page.get("status") == "orphan_candidate":
                page["status"] = "active"
            page["orphan_candidate"] = False

    return manifest


def reconcile_incoming_links(manifest: dict, ctx: RunContext) -> dict:
    """Derive incoming_links_known from every page's outgoing_links (by slug)."""
    slug_to_key: dict[str, str] = {
        page["slug"]: key for key, page in manifest["pages"].items()
    }
    incoming: dict[str, set[str]] = defaultdict(set)
    for key, page in manifest["pages"].items():
        for target_slug in page.get("outgoing_links", []):
            target_key = slug_to_key.get(target_slug)
            if target_key is None:
                continue  # Unknown target — skip silently (D12 flag-don't-nuke).
            incoming[target_key].add(page["slug"])
    for key, page in manifest["pages"].items():
        page["incoming_links_known"] = sorted(incoming[key])
        page["last_link_reconciled_at"] = ctx.started_at
    return manifest


def recompute_stats(manifest: dict, compile_result: dict, ctx: RunContext,
                    *, prior_runs: dict) -> dict:
    """Recompute stats{} and runs{} pointers; bump updated_at."""
    pages = manifest["pages"]
    manifest["stats"] = {
        "total_raw_files": len(manifest["sources"]),
        "total_pages": len(pages),
        "total_summary_pages": sum(1 for p in pages.values() if p["page_type"] == "summary"),
        "total_concept_pages": sum(1 for p in pages.values() if p["page_type"] == "concept"),
        "total_article_pages": sum(1 for p in pages.values() if p["page_type"] == "article"),
        "total_runs": int(prior_runs.get("total_runs", 0)),
    }
    prior_last = prior_runs.get("last_run_id")
    if ctx.run_id != prior_last:
        manifest["stats"]["total_runs"] += 1

    manifest["runs"]["last_run_id"] = ctx.run_id
    if compile_result.get("success"):
        manifest["runs"]["last_successful_run_id"] = ctx.run_id
    else:
        manifest["runs"]["last_successful_run_id"] = prior_runs.get("last_successful_run_id")
    manifest["updated_at"] = ctx.started_at
    return manifest


def assert_manifest_invariants(manifest: dict) -> None:
    """Structural sanity checks. Raises ManifestInvariantError."""
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestInvariantError(
            f"schema_version mismatch: got {manifest.get('schema_version')!r}"
        )
    known_sources = set(manifest.get("sources", {}).keys())
    known_tombstones = set(manifest.get("tombstones", {}).keys())

    for key, page in manifest.get("pages", {}).items():
        refs = page.get("source_refs", [])
        if len(refs) < 1:
            raise ManifestInvariantError(f"page {key} has empty source_refs")
        for ref in refs:
            sid = ref.get("source_id")
            if sid not in known_sources and sid not in known_tombstones:
                raise ManifestInvariantError(
                    f"page {key} references unknown source_id {sid!r}"
                )

    for key in manifest.get("orphans", {}):
        page = manifest.get("pages", {}).get(key)
        if page is None:
            raise ManifestInvariantError(f"orphan {key} missing from pages{{}}")
        if page.get("status") != "orphan_candidate":
            raise ManifestInvariantError(
                f"orphan {key} status={page.get('status')!r} (expected 'orphan_candidate')"
            )

    for sid, rec in manifest.get("sources", {}).items():
        tomb = manifest.get("tombstones", {}).get(sid)
        if tomb and tomb.get("status") == "deleted":
            raise ManifestInvariantError(
                f"source {sid} appears in both sources{{}} and deleted-tombstones"
            )
        history = rec.get("previous_versions", [])
        if len(history) > PREV_VERSIONS_CAP:
            raise ManifestInvariantError(
                f"source {sid} previous_versions exceeds cap ({len(history)})"
            )

    for key, page in manifest.get("pages", {}).items():
        created = page.get("created_at")
        updated = page.get("updated_at")
        if created and updated and created > updated:
            raise ManifestInvariantError(
                f"page {key} created_at > updated_at ({created!r} > {updated!r})"
            )


# ---------- journal ----------

def build_journal(prior: dict, next_manifest: dict, last_scan: dict,
                  compile_result: dict, ctx: RunContext,
                  *, scan_path: str, compile_path: str,
                  finished_at: str | None = None) -> dict:
    prior_sources = set(prior.get("sources", {}).keys()) if prior else set()
    next_sources = set(next_manifest.get("sources", {}).keys())
    prior_pages = set(prior.get("pages", {}).keys()) if prior else set()
    next_pages = set(next_manifest.get("pages", {}).keys())

    moved_pairs: list[dict] = []
    for op in last_scan.get("to_reconcile", []):
        if op.get("type") == "MOVED":
            moved_pairs.append({"from": op.get("from"), "to": op.get("to")})

    scan_summary = last_scan.get("summary", {})
    prior_orphans = set(prior.get("orphans", {}).keys()) if prior else set()
    next_orphans = set(next_manifest.get("orphans", {}).keys())

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": ctx.run_id,
        "started_at": ctx.started_at,
        "finished_at": finished_at or now_iso(),
        "success": bool(compile_result.get("success")),
        "compiler_version": ctx.compiler_version,
        "manifest_updated_at": next_manifest.get("updated_at"),
        "last_scan_path": scan_path,
        "compile_result_path": compile_path,
        "inputs": {
            "scan_run_id": last_scan.get("run_id"),
            "scan_summary": scan_summary,
            "compile_sources_processed": len(compile_result.get("compiled_sources", [])),
        },
        "deltas": {
            "sources_added": sorted(next_sources - prior_sources),
            "sources_removed": sorted(prior_sources - next_sources),
            "sources_moved": moved_pairs,
            "sources_changed": sorted(
                s for s in (prior_sources & next_sources)
                if prior["sources"][s].get("hash") != next_manifest["sources"][s].get("hash")
            ),
            "pages_created": sorted(next_pages - prior_pages),
            "pages_updated": sorted(prior_pages & next_pages),
            "orphans_flagged": sorted(next_orphans - prior_orphans),
            "orphans_cleared": sorted(prior_orphans - next_orphans),
        },
        "log_entries": list(ctx.log_entries),
        "warnings": list(compile_result.get("warnings", [])),
        "errors": list(compile_result.get("errors", [])),
    }


# ---------- pure orchestrator ----------

def build_manifest_update(prior: dict, last_scan: dict, compile_result: dict,
                          ctx: RunContext, *, scan_path: str = "state/last_scan.json",
                          compile_path: str = "state/compile_result.json",
                          kb_id: str = DEFAULT_KB_ID) -> tuple[dict, dict]:
    """Pure. Returns (next_manifest, journal). Performs no I/O."""
    next_manifest = copy.deepcopy(prior) if prior else {}
    prior_runs_snapshot = dict(next_manifest.get("runs", {})) if next_manifest else {}
    prior_runs_snapshot["total_runs"] = next_manifest.get("stats", {}).get("total_runs", 0) if next_manifest else 0

    next_manifest = ensure_manifest_shape(next_manifest, ctx=ctx, kb_id=kb_id)
    next_manifest = apply_scan_reconciliation(next_manifest, last_scan, ctx)
    next_manifest = apply_compile_result(next_manifest, compile_result, last_scan, ctx)
    next_manifest = reconcile_incoming_links(next_manifest, ctx)
    next_manifest = recompute_stats(
        next_manifest, compile_result, ctx, prior_runs=prior_runs_snapshot,
    )
    assert_manifest_invariants(next_manifest)

    journal = build_journal(
        prior, next_manifest, last_scan, compile_result, ctx,
        scan_path=scan_path, compile_path=compile_path,
    )
    return next_manifest, journal


# ---------- I/O shell: write ----------

def write_outputs(next_manifest: dict, journal: dict, state_root: Path,
                  ctx: RunContext) -> None:
    """Journal-then-pointer write (D15). Both files use sorted keys."""
    state_root = Path(state_root)
    runs_dir = state_root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    journal_path = runs_dir / f"{ctx.run_id}.json"
    manifest_path = state_root / "manifest.json"

    atomic_io.atomic_write_json(journal_path, journal, sort_keys=True)
    atomic_io.atomic_write_json(manifest_path, next_manifest, sort_keys=True)


# ---------- public entry ----------

def update(state_root: Path, *, run_ctx: RunContext | None = None,
           write: bool = True, kb_id: str = DEFAULT_KB_ID) -> tuple[dict, dict]:
    """Load → build → (optionally) write. Returns (next_manifest, journal)."""
    state_root = Path(state_root)
    prior, last_scan, compile_result = load_inputs(state_root)
    ctx = run_ctx or build_run_ctx(state_root, compile_result)

    scan_path = str((state_root / "last_scan.json").as_posix())
    compile_path = str((state_root / "compile_result.json").as_posix())

    next_manifest, journal = build_manifest_update(
        prior, last_scan, compile_result, ctx,
        scan_path=scan_path, compile_path=compile_path, kb_id=kb_id,
    )

    if write and not ctx.dry_run:
        write_outputs(next_manifest, journal, state_root, ctx)
    return next_manifest, journal


# ---------- CLI ----------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="manifest_update",
                                     description="Apply compile_result.json to manifest.json.")
    parser.add_argument("--state-root", required=True, type=Path,
                        help="Directory containing manifest.json / last_scan.json / compile_result.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build in-memory only; skip writing outputs.")
    parser.add_argument("--kb-id", default=DEFAULT_KB_ID,
                        help="kb_id used when bootstrapping an empty manifest.")
    args = parser.parse_args(argv)

    try:
        prior, last_scan, compile_result = load_inputs(args.state_root)
    except FileNotFoundError as exc:
        print(f"manifest_update: {exc}", file=sys.stderr)
        return 2
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"manifest_update: input error: {exc}", file=sys.stderr)
        return 2

    ctx = build_run_ctx(args.state_root, compile_result, dry_run=args.dry_run)

    scan_path = str((args.state_root / "last_scan.json").as_posix())
    compile_path = str((args.state_root / "compile_result.json").as_posix())

    try:
        next_manifest, journal = build_manifest_update(
            prior, last_scan, compile_result, ctx,
            scan_path=scan_path, compile_path=compile_path, kb_id=args.kb_id,
        )
    except ManifestInvariantError as exc:
        print(f"manifest_update: invariant violation: {exc}", file=sys.stderr)
        return 1

    if not args.dry_run:
        write_outputs(next_manifest, journal, args.state_root, ctx)

    print(f"manifest_update: run_id={ctx.run_id} "
          f"sources={len(next_manifest['sources'])} "
          f"pages={len(next_manifest['pages'])} "
          f"orphans={len(next_manifest['orphans'])} "
          f"tombstones={len(next_manifest['tombstones'])}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
