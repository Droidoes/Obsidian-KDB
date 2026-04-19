"""validate_last_scan — schema + semantic validation for last_scan.json.

Parallel to validate_compile_result.py: one module per artifact. Two layers,
both accumulating (no short-circuit):

    1. JSON-Schema (jsonschema.Draft202012Validator) against
       schemas/last_scan.schema.json — shape, types, per-action required fields.
    2. Semantic — cross-field invariants JSON-Schema can't express cleanly:
         * to_compile exactly = files[].path where action in {NEW, CHANGED}
         * to_skip   exactly = files[].path where action == UNCHANGED
         * Every MOVED in files[] has a matching MOVED reconcile op (and inverse)
         * DELETED paths in to_reconcile must NOT appear in files[]
         * summary counts equal actual array counts
         * No duplicate paths in files[], to_compile, to_skip
         * to_compile / to_skip disjoint

Public API:
    validate(payload) -> list[str]   # empty = valid
    main() -> None                   # CLI entry

CLI:
    kdb-validate-scan [path.json]    # stdin if path omitted
    exit 0 — valid; exit 1 — invalid; exit 2 — runtime/config error
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "last_scan.schema.json"


@cache
def _validator() -> Draft202012Validator:
    with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(payload: Any) -> list[str]:
    """Return list of human-readable errors. Empty list means valid."""
    errors: list[str] = []

    for err in _validator().iter_errors(payload):
        errors.append(f"[{err.json_path}] {err.message}")

    if not isinstance(payload, dict):
        return errors

    _check_semantics(payload, errors)
    return errors


def _check_semantics(payload: dict, errors: list[str]) -> None:
    files = payload.get("files") or []
    to_compile = payload.get("to_compile") or []
    to_skip = payload.get("to_skip") or []
    to_reconcile = payload.get("to_reconcile") or []
    summary = payload.get("summary") or {}
    scan_errors = payload.get("errors") or []
    skipped_symlinks = payload.get("skipped_symlinks") or []

    if not isinstance(files, list):
        return

    # --- files[] indexing + duplicate detection ---
    status_by_path: dict[str, str] = {}
    action_counter: Counter[str] = Counter()
    dup_paths: list[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        action = entry.get("action")
        if not isinstance(path, str) or not isinstance(action, str):
            continue
        if path in status_by_path:
            dup_paths.append(path)
        status_by_path[path] = action
        action_counter[action] += 1

    for p in sorted(set(dup_paths)):
        errors.append(f"[$.files] duplicate path: {p!r}")

    # --- to_compile / to_skip uniqueness + cross-ref to files[] ---
    if isinstance(to_compile, list):
        if len(to_compile) != len(set(to_compile)):
            errors.append("[$.to_compile] contains duplicate paths")
        for p in to_compile:
            if not isinstance(p, str):
                continue
            s = status_by_path.get(p)
            if s is None:
                errors.append(f"[$.to_compile] path not found in files[]: {p!r}")
            elif s not in ("NEW", "CHANGED"):
                errors.append(
                    f"[$.to_compile] {p!r} has action={s!r} (expected NEW or CHANGED)"
                )

    if isinstance(to_skip, list):
        if len(to_skip) != len(set(to_skip)):
            errors.append("[$.to_skip] contains duplicate paths")
        for p in to_skip:
            if not isinstance(p, str):
                continue
            s = status_by_path.get(p)
            if s is None:
                errors.append(f"[$.to_skip] path not found in files[]: {p!r}")
            elif s != "UNCHANGED":
                errors.append(
                    f"[$.to_skip] {p!r} has action={s!r} (expected UNCHANGED)"
                )

    # --- disjointness ---
    if isinstance(to_compile, list) and isinstance(to_skip, list):
        overlap = sorted(set(to_compile) & set(to_skip))
        if overlap:
            errors.append(f"[$] paths appear in both to_compile and to_skip: {overlap}")

    # --- to_compile / to_skip completeness (must exactly match NEW+CHANGED / UNCHANGED) ---
    expected_to_compile = sorted(p for p, s in status_by_path.items() if s in ("NEW", "CHANGED"))
    if isinstance(to_compile, list) and sorted(to_compile) != expected_to_compile:
        errors.append(
            "[$.to_compile] does not exactly match NEW+CHANGED files[] entries"
        )
    expected_to_skip = sorted(p for p, s in status_by_path.items() if s == "UNCHANGED")
    if isinstance(to_skip, list) and sorted(to_skip) != expected_to_skip:
        errors.append(
            "[$.to_skip] does not exactly match UNCHANGED files[] entries"
        )

    # --- reconcile ops ---
    moved_from_ops: set[str] = set()
    moved_to_ops: set[str] = set()
    deleted_paths_ops: set[str] = set()
    if isinstance(to_reconcile, list):
        for idx, op in enumerate(to_reconcile):
            if not isinstance(op, dict):
                continue
            t = op.get("type")
            if t == "MOVED":
                src = op.get("from")
                dst = op.get("to")
                if isinstance(src, str):
                    moved_from_ops.add(src)
                if isinstance(dst, str):
                    moved_to_ops.add(dst)
            elif t == "DELETED":
                p = op.get("path")
                if isinstance(p, str):
                    deleted_paths_ops.add(p)

        # MOVED reconcile ops: every 'to' must be a MOVED entry in files[]; 'from' must NOT appear in files[].
        for op_idx, op in enumerate(to_reconcile):
            if not isinstance(op, dict) or op.get("type") != "MOVED":
                continue
            src = op.get("from")
            dst = op.get("to")
            if isinstance(src, str) and src in status_by_path:
                errors.append(
                    f"[$.to_reconcile[{op_idx}]] MOVED 'from' path {src!r} "
                    "unexpectedly present in files[]"
                )
            if isinstance(dst, str):
                if dst not in status_by_path:
                    errors.append(
                        f"[$.to_reconcile[{op_idx}]] MOVED 'to' path {dst!r} "
                        "not found in files[]"
                    )
                elif status_by_path[dst] != "MOVED":
                    errors.append(
                        f"[$.to_reconcile[{op_idx}]] MOVED 'to' {dst!r} "
                        f"has action={status_by_path[dst]!r} (expected MOVED)"
                    )

        # DELETED reconcile ops: path must NOT appear in files[] (per our contract).
        for op_idx, op in enumerate(to_reconcile):
            if not isinstance(op, dict) or op.get("type") != "DELETED":
                continue
            p = op.get("path")
            if isinstance(p, str) and p in status_by_path:
                errors.append(
                    f"[$.to_reconcile[{op_idx}]] DELETED path {p!r} "
                    "unexpectedly present in files[]"
                )

    # Every MOVED file[] entry must have a matching reconcile op (paired by current path).
    moved_paths_files = {p for p, s in status_by_path.items() if s == "MOVED"}
    missing_ops = sorted(moved_paths_files - moved_to_ops)
    for p in missing_ops:
        errors.append(
            f"[$.files] MOVED entry {p!r} has no matching MOVED reconcile op"
        )

    # --- summary counts ---
    expected_summary = {
        "new":             action_counter["NEW"],
        "changed":         action_counter["CHANGED"],
        "unchanged":       action_counter["UNCHANGED"],
        "moved":           action_counter["MOVED"],
        "deleted":         len(deleted_paths_ops),
        "error":           len(scan_errors) if isinstance(scan_errors, list) else 0,
        "skipped_symlink": len(skipped_symlinks) if isinstance(skipped_symlinks, list) else 0,
    }
    if isinstance(summary, dict):
        for key, expected in expected_summary.items():
            actual = summary.get(key)
            if actual != expected:
                errors.append(
                    f"[$.summary.{key}] is {actual!r}, expected {expected!r}"
                )


def main() -> None:
    """CLI. argv[1] = path, else stdin. Exit 0 (valid) / 1 (invalid) / 2 (runtime)."""
    try:
        if len(sys.argv) >= 2:
            raw = Path(sys.argv[1]).read_text(encoding="utf-8")
        else:
            raw = sys.stdin.read()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    errors = validate(payload)
    if errors:
        for msg in errors:
            print(msg)
        sys.exit(1)
    print("OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
