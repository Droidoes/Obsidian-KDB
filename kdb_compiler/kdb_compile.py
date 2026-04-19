"""End-to-end orchestrator: scan → validate → apply → write (M1.7)."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from kdb_compiler import (
    kdb_scan,
    manifest_update,
    patch_applier,
    validate_compile_result,
    validate_last_scan,
)
from kdb_compiler.run_context import RunContext


@dataclass
class CompileRunResult:
    run_id: str
    success: bool
    scan_counts: dict = field(default_factory=dict)
    pages_written: list[str] = field(default_factory=list)
    manifest_written: bool = False
    journal_written: bool = False
    dry_run: bool = False
    errors: list[str] = field(default_factory=list)


def compile(
    vault_root: Path,
    *,
    dry_run: bool = False,
    run_ctx: RunContext | None = None,
) -> CompileRunResult:
    vault_root = Path(vault_root).resolve()
    kdb_root = vault_root / "KDB"
    state_root = kdb_root / "state"

    ctx = run_ctx if run_ctx is not None else RunContext.new(dry_run=dry_run, vault_root=vault_root)
    dry_run = ctx.dry_run  # ctx is authoritative; reconcile if run_ctx was injected
    run_id = ctx.run_id

    scan_result = kdb_scan.scan(vault_root, run_ctx=ctx, write=not dry_run)
    scan_dict = scan_result.to_dict()
    scan_counts = scan_dict.get("summary", {})

    def _fail(errs: list[str]) -> CompileRunResult:
        return CompileRunResult(
            run_id=run_id, success=False, scan_counts=scan_counts,
            dry_run=dry_run, errors=errs,
        )

    scan_errors = validate_last_scan.validate(scan_dict)
    if scan_errors:
        return _fail(scan_errors)

    cr_path = state_root / "compile_result.json"
    if not cr_path.exists():
        return _fail([
            f"compile_result.json not found at {cr_path} — "
            "M2 compile step is not implemented yet; supply a pre-made compile_result.json "
            "fixture or run planner/compiler once available"
        ])

    try:
        cr = json.loads(cr_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return _fail([f"compile_result.json unreadable: {exc}"])

    cr_errors = validate_compile_result.validate(cr)
    if cr_errors:
        return _fail(cr_errors)

    if scan_result.run_id != cr.get("run_id"):
        return _fail([
            f"run_id mismatch: scan={scan_result.run_id!r} "
            f"compile_result={cr.get('run_id')!r}"
        ])

    manifest_path = state_root / "manifest.json"
    prior: dict = {}
    if manifest_path.exists():
        try:
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return _fail([f"manifest.json unreadable: {exc}"])

    next_manifest, journal = manifest_update.build_manifest_update(prior, scan_dict, cr, ctx)

    apply_result = patch_applier.apply(
        state_root, vault_root,
        next_manifest=next_manifest,
        run_ctx=ctx,
        write=not dry_run,
    )

    if not dry_run:
        manifest_update.write_outputs(next_manifest, journal, state_root, ctx)

    return CompileRunResult(
        run_id=run_id,
        success=True,
        scan_counts=scan_counts,
        pages_written=apply_result.pages_written if not dry_run else [],
        manifest_written=not dry_run,
        journal_written=not dry_run,
        dry_run=dry_run,
        errors=[],
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kdb-compile",
        description="KDB end-to-end orchestrator: scan → validate → apply → write.",
    )
    p.add_argument("--vault-root", required=True, help="Absolute path to Obsidian vault root")
    p.add_argument("--dry-run", action="store_true", help="Scan and validate but write nothing")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    vault_root = Path(args.vault_root)

    if not (vault_root / "KDB").is_dir():
        print(f"kdb_compile: error — no KDB/ directory under {vault_root}", file=sys.stderr)
        return 1

    result = compile(vault_root, dry_run=args.dry_run)

    scan_s = result.scan_counts
    total = sum(scan_s.get(k, 0) for k in ("new", "changed", "unchanged", "moved", "deleted"))
    mode = "dry-run (no writes)" if result.dry_run else f"{len(result.pages_written)} page(s) written"
    scan_ok = "✓" if result.success or not any("scan" in e for e in result.errors) else "✗"
    cr_ok = "✓" if result.success else "✗"
    print(
        f"kdb_compile: scanned {total} raw files"
        f" · validated scan {scan_ok}"
        f" · validated compile_result {cr_ok}"
        f" · {mode}"
    )

    if not result.success:
        for err in result.errors:
            print(f"  error: {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
