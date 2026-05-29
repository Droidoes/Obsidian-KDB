"""kdb_scan — deterministic scan of KDB/raw/, emits state/last_scan.json.

Pipeline position:
    [kdb_scan] -> planner -> compiler -> validate -> patch_applier -> source_state_update

Contract:
    Input:  KDB/raw/** + KDB/state/manifest.json (prior state; may be empty)
    Output: KDB/state/last_scan.json — the run's authoritative change ledger

Behavior (Option A — single-pass walker + in-memory diff):
    1. Walk KDB/raw/ with os.walk(followlinks=False).
    2. Per file: sha256 + mtime + size + ext/NUL-sniff binary flag.
    3. Symlinks -> skipped_symlinks[]. Read/stat errors -> errors[].
    4. Load manifest sources{} (missing/empty -> first-run, treat as {}).
    5. Phase B intersection: UNCHANGED (hash eq) or CHANGED (hash differ).
    6. Phase C rename pass: current-only ∩ manifest-only, match by hash -> MOVED.
    7. Phase D leftover: current-only -> NEW; manifest-only -> DELETED reconcile op.
    8. Sort everything by path for deterministic output.
    9. Atomic write via atomic_io.atomic_write_json.

DELETED entries live ONLY in to_reconcile[] (not in files[]).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kdb_compiler import atomic_io
from kdb_compiler.run_context import RunContext
from kdb_compiler.types import (
    ErrorEntry,
    FileType,
    ReconcileOp,
    ScanEntry,
    ScanResult,
    ScanSummary,
    SettingsSnapshot,
    SkippedSymlinkEntry,
)

# -------- scanner policy (captured into settings_snapshot) --------

_MARKDOWN_EXTS: frozenset[str] = frozenset({".md", ".markdown", ".txt"})
_BINARY_SNIFF_BYTES = 4096
_HASH_CHUNK_BYTES = 65536

_DEFAULT_SETTINGS = SettingsSnapshot(
    rename_detection=True,
    symlink_policy="skip",
    scan_binary_files=True,
    binary_compile_mode="metadata_only",
)


# -------- internal row type --------

@dataclass(slots=True)
class _RawFile:
    """A file physically present in KDB/raw/ at scan time."""
    rel_path: str          # "KDB/raw/..." POSIX
    hash: str              # "sha256:<64-hex>"
    mtime: float
    size_bytes: int
    file_type: FileType
    is_binary: bool


# -------- hashing + classification helpers --------

def _sha256_file(abs_path: Path) -> str:
    h = hashlib.sha256()
    with abs_path.open("rb") as f:
        while True:
            chunk = f.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _classify_file(abs_path: Path) -> tuple[FileType, bool]:
    """Extension hint + first-chunk NUL sniff to decide markdown/binary."""
    ext = abs_path.suffix.lower()
    try:
        with abs_path.open("rb") as f:
            head = f.read(_BINARY_SNIFF_BYTES)
    except OSError:
        head = b""
    has_nul = b"\x00" in head
    if has_nul:
        return "binary", True
    if ext in _MARKDOWN_EXTS:
        return "markdown", False
    if ext == "":
        return "unknown", False
    return "unknown", False


# -------- phase A: walk a pipeline scope --------

def walk_scope(
    root_abs: Path,
    vault_root: Path,
    *,
    file_types: "frozenset[str] | set[str] | None" = None,
    excludes: "list[str] | None" = None,
    prune_hidden: bool = True,
) -> tuple[list[_RawFile], list[SkippedSymlinkEntry], list[ErrorEntry]]:
    """os.walk root_abs; return (files, skipped_symlinks, errors), all sorted by
    vault-relative path (Task #91).

    - source_ids are vault-relative (abs.relative_to(vault_root)).
    - prune_hidden: skip dot-dirs (.*) — default True; the legacy raw walk opts
      out for exact back-compat.
    - excludes: directory names (trailing '/' tolerated) pruned at walk time.
    - file_types: when given, only files with these suffixes are recorded;
      None = record all (legacy raw behavior — binary files included).
    """
    files: list[_RawFile] = []
    symlinks: list[SkippedSymlinkEntry] = []
    errors: list[ErrorEntry] = []

    if not root_abs.exists():
        return files, symlinks, errors

    root_abs = root_abs.resolve()
    vault_root = vault_root.resolve()
    exclude_names = {e.rstrip("/") for e in (excludes or [])}

    for dirpath, dirnames, filenames in os.walk(root_abs, followlinks=False):
        # Stable traversal order; prune hidden/excluded; filter symlinked subdirs.
        dirnames.sort()
        pruned: list[str] = []
        for d in dirnames:
            if prune_hidden and d.startswith("."):
                continue
            if d in exclude_names:
                continue
            dp = Path(dirpath) / d
            if dp.is_symlink():
                rel = _rel_to_vault(dp, vault_root)
                target = _readlink_target(dp)
                symlinks.append(SkippedSymlinkEntry(path=rel, link_target=target))
            else:
                pruned.append(d)
        dirnames[:] = pruned

        for name in sorted(filenames):
            p = Path(dirpath) / name
            rel = _rel_to_vault(p, vault_root)

            if p.is_symlink():
                target = _readlink_target(p)
                symlinks.append(SkippedSymlinkEntry(path=rel, link_target=target))
                continue

            if file_types is not None and p.suffix not in file_types:
                continue

            try:
                st = p.stat()
                hash_str = _sha256_file(p)
            except OSError as e:
                errors.append(ErrorEntry(path=rel, error=f"{type(e).__name__}: {e}"))
                continue

            file_type, is_binary = _classify_file(p)
            files.append(_RawFile(
                rel_path=rel,
                hash=hash_str,
                mtime=st.st_mtime,
                size_bytes=st.st_size,
                file_type=file_type,
                is_binary=is_binary,
            ))

    files.sort(key=lambda f: f.rel_path)
    symlinks.sort(key=lambda s: s.path)
    errors.sort(key=lambda e: e.path)
    return files, symlinks, errors


def walk_raw(raw_abs: Path) -> tuple[list[_RawFile], list[SkippedSymlinkEntry], list[ErrorEntry]]:
    """Back-compat wrapper for the legacy KDB/raw/ scan. Delegates to walk_scope
    with vault_root = raw_abs.parent.parent, no suffix filter, and no
    hidden-pruning — preserving the original behavior exactly (binary files
    recorded; dot-dirs walked). The .md-only restriction (D-91-2) is applied
    per-pipeline via scan_scope's file_types, not here."""
    return walk_scope(
        raw_abs, raw_abs.parent.parent,
        file_types=None, excludes=[], prune_hidden=False,
    )


def _rel_to_vault(abs_path: Path, vault_root: Path) -> str:
    """Return POSIX vault-relative path for abs_path under vault_root."""
    return abs_path.relative_to(vault_root).as_posix()


def _readlink_target(p: Path) -> str | None:
    try:
        return os.readlink(p)
    except OSError:
        return None


# -------- manifest loading --------

def load_manifest_sources(manifest_abs: Path) -> dict[str, dict]:
    """Return {source_id: {hash, mtime, size_bytes, file_type, is_binary}}.

    Missing file or empty-sources -> {}. Malformed manifest -> {} (first-run behavior).
    """
    if not manifest_abs.exists():
        return {}
    try:
        data = json.loads(manifest_abs.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    sources = data.get("sources") or {}
    if not isinstance(sources, dict):
        return {}
    out: dict[str, dict] = {}
    for sid, rec in sources.items():
        if not isinstance(rec, dict):
            continue
        out[sid] = {
            "hash": rec.get("hash"),
            "mtime": rec.get("mtime"),
            "size_bytes": rec.get("size_bytes"),
            "file_type": rec.get("file_type"),
            "is_binary": rec.get("is_binary"),
            "last_compiled_hash": rec.get("last_compiled_hash"),
        }
    return out


# -------- phase B/C/D: classify + reconcile --------

def classify(
    current: list[_RawFile],
    prior: dict[str, dict],
) -> tuple[list[ScanEntry], list[ReconcileOp]]:
    """Build files[] and to_reconcile[] by set-diff + hash-match rename pass."""
    current_by_path: dict[str, _RawFile] = {f.rel_path: f for f in current}
    current_paths = set(current_by_path)
    prior_paths = set(prior)

    files: list[ScanEntry] = []
    ops: list[ReconcileOp] = []

    # Phase B — paths in both: UNCHANGED or CHANGED
    for path in current_paths & prior_paths:
        cur = current_by_path[path]
        prev = prior[path]
        prev_hash = prev.get("hash")
        prev_mtime = prev.get("mtime")
        if prev_hash == cur.hash:
            files.append(_entry_from(cur, "UNCHANGED", prev_hash, prev_mtime, prev.get("last_compiled_hash")))
        else:
            files.append(_entry_from(cur, "CHANGED", prev_hash, prev_mtime, prev.get("last_compiled_hash")))

    # Phase C — rename pass on disjoint sets: match by hash
    current_only = current_paths - prior_paths
    prior_only = prior_paths - current_paths

    prior_hash_buckets: dict[str, list[str]] = {}
    for p in prior_only:
        h = prior[p].get("hash")
        if isinstance(h, str):
            prior_hash_buckets.setdefault(h, []).append(p)
    for bucket in prior_hash_buckets.values():
        bucket.sort()  # deterministic pairing

    matched_current: set[str] = set()
    matched_prior: set[str] = set()
    for new_path in sorted(current_only):
        cur = current_by_path[new_path]
        bucket = prior_hash_buckets.get(cur.hash)
        if not bucket:
            continue
        old_path = next((p for p in bucket if p not in matched_prior), None)
        if old_path is None:
            continue
        matched_current.add(new_path)
        matched_prior.add(old_path)
        prev = prior[old_path]
        files.append(_entry_from(
            cur, "MOVED",
            prev.get("hash"), prev.get("mtime"),
            prev.get("last_compiled_hash"),
            previous_path=old_path,
        ))
        ops.append(ReconcileOp(
            type="MOVED", from_path=old_path, to_path=new_path, hash=cur.hash,
        ))

    # Phase D — leftovers
    for new_path in sorted(current_only - matched_current):
        cur = current_by_path[new_path]
        files.append(_entry_from(cur, "NEW", None, None, None))

    for old_path in sorted(prior_only - matched_prior):
        prev = prior[old_path]
        hash_val = prev.get("hash")
        ops.append(ReconcileOp(
            type="DELETED",
            path=old_path,
            hash=hash_val if isinstance(hash_val, str) else None,
        ))

    files.sort(key=lambda e: e.path)
    ops.sort(key=_op_sort_key)
    return files, ops


def _entry_from(
    cur: _RawFile,
    action: str,
    prev_hash: Any,
    prev_mtime: Any,
    compiled_hash: str | None,
    *,
    previous_path: str | None = None,
) -> ScanEntry:
    return ScanEntry(
        path=cur.rel_path,
        action=action,  # type: ignore[arg-type]
        current_hash=cur.hash,
        current_mtime=cur.mtime,
        size_bytes=cur.size_bytes,
        file_type=cur.file_type,
        is_binary=cur.is_binary,
        compiled_hash=compiled_hash if isinstance(compiled_hash, str) else None,
        previous_hash=prev_hash if isinstance(prev_hash, str) else None,
        previous_mtime=float(prev_mtime) if isinstance(prev_mtime, (int, float)) else None,
        previous_path=previous_path,
    )


def _op_sort_key(op: ReconcileOp) -> tuple[str, str]:
    if op.type == "MOVED":
        return ("MOVED", op.from_path or "")
    return ("DELETED", op.path or "")


# -------- phase E: assemble + write --------

def build_scan_result(
    *,
    run_ctx: RunContext,
    raw_root_rel: str,
    files: list[ScanEntry],
    reconcile_ops: list[ReconcileOp],
    errors: list[ErrorEntry],
    skipped_symlinks: list[SkippedSymlinkEntry],
    settings: SettingsSnapshot,
) -> ScanResult:
    # Task #66 (D46): compile eligibility is one honest comparison.
    # A file compiles iff its current content hash differs from the hash
    # last successfully compiled. compile_state plays no part.
    to_compile = sorted(e.path for e in files if e.current_hash != e.compiled_hash)
    to_skip = sorted(e.path for e in files if e.current_hash == e.compiled_hash)

    counts = {"NEW": 0, "CHANGED": 0, "UNCHANGED": 0, "MOVED": 0}
    for e in files:
        counts[e.action] += 1
    deleted_count = sum(1 for op in reconcile_ops if op.type == "DELETED")

    summary = ScanSummary(
        new=counts["NEW"],
        changed=counts["CHANGED"],
        unchanged=counts["UNCHANGED"],
        moved=counts["MOVED"],
        deleted=deleted_count,
        error=len(errors),
        skipped_symlink=len(skipped_symlinks),
    )

    return ScanResult(
        schema_version=run_ctx.schema_version,
        run_id=run_ctx.run_id,
        scanned_at=run_ctx.started_at,
        vault_root=str(run_ctx.vault_root),
        raw_root=raw_root_rel,
        settings_snapshot=settings,
        summary=summary,
        files=files,
        to_compile=to_compile,
        to_reconcile=reconcile_ops,
        to_skip=to_skip,
        errors=errors,
        skipped_symlinks=skipped_symlinks,
    )


def write_scan_result(result: ScanResult, out_path: Path) -> None:
    atomic_io.atomic_write_json(out_path, result.to_dict())


# -------- orchestrator --------

def scan(
    vault_root: Path,
    *,
    settings: SettingsSnapshot | None = None,
    run_ctx: RunContext | None = None,
    write: bool = True,
) -> ScanResult:
    """Run a full scan. Returns the ScanResult; writes last_scan.json if write=True."""
    vault_root = Path(vault_root).resolve()
    kdb_root = vault_root / "KDB"
    raw_abs = kdb_root / "raw"
    manifest_abs = kdb_root / "state" / "manifest.json"
    out_path = kdb_root / "state" / "last_scan.json"

    run_ctx = run_ctx if run_ctx is not None else RunContext.new(vault_root=vault_root)
    settings = settings if settings is not None else _DEFAULT_SETTINGS

    current, skipped_symlinks, errors = walk_raw(raw_abs)
    prior = load_manifest_sources(manifest_abs)
    files, reconcile_ops = classify(current, prior)

    result = build_scan_result(
        run_ctx=run_ctx,
        raw_root_rel="KDB/raw",
        files=files,
        reconcile_ops=reconcile_ops,
        errors=errors,
        skipped_symlinks=skipped_symlinks,
        settings=settings,
    )
    if write:
        write_scan_result(result, out_path)
    return result


def scan_scope(
    root_abs: Path,
    vault_root: Path,
    *,
    pipeline_id: str,
    prior: dict[str, dict],
    run_ctx: RunContext,
    excludes: "list[str] | None" = None,
    file_types: "frozenset[str] | set[str] | None" = None,
    settings: SettingsSnapshot | None = None,
) -> ScanResult:
    """Scope-driven scan for one ingestion pipeline (Task #91).

    Walks root_abs (vault-relative source_ids), classifies against `prior`
    FILTERED to this pipeline's sources (by pipeline_id) — so the DELETED pass
    only flags this pipeline's absent sources and MOVED only matches within the
    pipeline (D-91-9). Stamps pipeline_id on every emitted entry. Does NOT write;
    the orchestrator owns persistence.
    """
    settings = settings if settings is not None else _DEFAULT_SETTINGS
    root_abs = Path(root_abs).resolve()
    vault_root = Path(vault_root).resolve()

    current, skipped_symlinks, errors = walk_scope(
        root_abs, vault_root,
        file_types=file_types, excludes=excludes, prune_hidden=True,
    )
    prior_scoped = {
        p: r for p, r in prior.items() if r.get("pipeline_id") == pipeline_id
    }
    files, reconcile_ops = classify(current, prior_scoped)
    for e in files:
        e.pipeline_id = pipeline_id

    return build_scan_result(
        run_ctx=run_ctx,
        raw_root_rel=_rel_to_vault(root_abs, vault_root) if root_abs != vault_root else ".",
        files=files,
        reconcile_ops=reconcile_ops,
        errors=errors,
        skipped_symlinks=skipped_symlinks,
        settings=settings,
    )


# -------- CLI --------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kdb-scan", description="Scan KDB/raw/ and emit last_scan.json.")
    parser.add_argument("--vault-root", type=Path, required=True,
                        help="Absolute path to the Obsidian vault containing KDB/.")
    args = parser.parse_args(argv)

    result = scan(args.vault_root)
    s = result.summary
    print(
        f"scanned {len(result.files)} files | "
        f"new={s.new} changed={s.changed} unchanged={s.unchanged} "
        f"moved={s.moved} deleted={s.deleted} "
        f"errors={s.error} symlinks={s.skipped_symlink}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
