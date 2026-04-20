"""End-to-end orchestrator: scan → validate → apply → write (M1.7)."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from kdb_compiler import (
    compiler,
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
    sources_attempted: int = 0
    sources_compiled: int = 0
    sources_failed: int = 0
    compile_errors: list[str] = field(default_factory=list)


def compile(
    vault_root: Path,
    *,
    dry_run: bool = False,
    run_ctx: RunContext | None = None,
    progress: Callable[..., None] | None = None,
) -> CompileRunResult:
    vault_root = Path(vault_root).resolve()
    kdb_root = vault_root / "KDB"
    state_root = kdb_root / "state"

    ctx = run_ctx if run_ctx is not None else RunContext.new(dry_run=dry_run, vault_root=vault_root)
    dry_run = ctx.dry_run  # ctx is authoritative; reconcile if run_ctx was injected
    run_id = ctx.run_id

    def _emit(event: str, **fields: Any) -> None:
        if progress is None:
            return
        try:
            progress(event, **fields)
        except Exception:
            pass

    scan_result = kdb_scan.scan(vault_root, run_ctx=ctx, write=not dry_run)
    scan_dict = scan_result.to_dict()
    scan_counts = scan_dict.get("summary", {})
    _emit(
        "scan_done",
        total=len(scan_result.files),
        to_compile=len(scan_result.to_compile),
        to_skip=len(scan_result.to_skip),
    )

    def _fail(errs: list[str]) -> CompileRunResult:
        return CompileRunResult(
            run_id=run_id, success=False, scan_counts=scan_counts,
            dry_run=dry_run, errors=errs,
        )

    scan_errors = validate_last_scan.validate(scan_dict)
    if scan_errors:
        return _fail(scan_errors)

    # Branch 1 — fixture-backed — activates only when compile_result.json
    # exists AND its run_id matches the fresh scan's run_id. That's the
    # "operator explicitly staged this CR for replay" case. Any other file
    # on disk is a stale artifact from a previous run and is ignored —
    # we fall through to Branch 2 (live compile) which will overwrite it.
    cr: dict | None = None
    cr_path = state_root / "compile_result.json"
    if cr_path.exists():
        try:
            staged = json.loads(cr_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return _fail([f"compile_result.json unreadable: {exc}"])
        if staged.get("run_id") == scan_result.run_id:
            cr = staged

    if cr is None:
        # Branch 2 — live compile. Covers (a) no file, (b) stale file,
        # (c) empty-plan no-op (compiler.run_compile synthesises a
        # successful empty CompileResult with a single info log entry
        # when the job list is empty).
        try:
            cr_obj = compiler.run_compile(
                vault_root,
                state_root=state_root,
                scan=scan_dict,
                ctx=ctx,
                write=not dry_run,
                progress=progress,
            )
        except Exception as exc:
            return _fail(
                [f"compiler.run_compile failed: {type(exc).__name__}: {exc}"]
            )
        cr = cr_obj.to_dict()

    compile_errors = list(cr.get("errors") or [])
    sources_compiled = len(cr.get("compiled_sources") or [])
    sources_failed = len(compile_errors)
    sources_attempted = sources_compiled + sources_failed

    cr_errors = validate_compile_result.validate(cr)
    if cr_errors:
        return _fail(cr_errors)

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

    deltas = (journal or {}).get("deltas") or {}
    _emit(
        "pages_done",
        created=len(deltas.get("pages_created") or []),
        updated=len(deltas.get("pages_updated") or []),
        written=len(apply_result.pages_written),
        dry_run=dry_run,
    )

    return CompileRunResult(
        run_id=run_id,
        success=bool(cr.get("success", True)),
        scan_counts=scan_counts,
        pages_written=apply_result.pages_written if not dry_run else [],
        manifest_written=not dry_run,
        journal_written=not dry_run,
        dry_run=dry_run,
        errors=compile_errors,
        sources_attempted=sources_attempted,
        sources_compiled=sources_compiled,
        sources_failed=sources_failed,
        compile_errors=compile_errors,
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kdb-compile",
        description="KDB end-to-end orchestrator: scan → validate → apply → write.",
    )
    p.add_argument("--vault-root", required=True, help="Absolute path to Obsidian vault root")
    p.add_argument("--dry-run", action="store_true", help="Scan and validate but write nothing")
    return p


def _short_source(source_id: str) -> str:
    """Strip KDB/raw/ prefix and trim overlong names for terminal readability."""
    sid = source_id.removeprefix("KDB/raw/")
    if len(sid) > 52:
        sid = sid[:49] + "..."
    return sid


def _make_stdout_progress(dry_run: bool) -> Callable[..., None]:
    """Build a progress callback that streams one line per event to stdout.

    Every print uses flush=True so WSL/tees/non-TTY wrappers render in
    real time rather than at process exit. Job lines are written in two
    halves — the 'start' half ends without a newline so the 'done' half
    appends the mark + latency on the same line.
    """
    def _progress(event: str, **f: Any) -> None:
        if event == "scan_done":
            print(
                f"  scan     : ✓  {f['total']} raw files "
                f"({f['to_compile']} to compile, {f['to_skip']} to skip)",
                flush=True,
            )
        elif event == "job_start":
            print(
                f"  compile  : [{f['i']}/{f['n']}] {_short_source(f['source_id'])} ...",
                end="", flush=True,
            )
        elif event == "job_done":
            mark = "✓" if f["ok"] else "✗"
            dur = f"{f['latency_ms'] / 1000:.1f}s"
            if f["ok"]:
                print(f" {mark} {dur}", flush=True)
            else:
                # Trim "KDB/raw/<name>: " prefix from error — we already
                # printed the source_id above.
                err = (f.get("error") or "").split(": ", 1)
                err_tail = err[1] if len(err) == 2 else (err[0] if err else "")
                print(f" {mark} {dur} — {err_tail}", flush=True)
        elif event == "pages_done":
            if dry_run:
                print("  pages    : dry-run (no writes)", flush=True)
            else:
                print(
                    f"  pages    : {f['created']} created · "
                    f"{f['updated']} updated ({f['written']} written)",
                    flush=True,
                )
    return _progress


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    vault_root = Path(args.vault_root).resolve()

    if not (vault_root / "KDB").is_dir():
        print(f"kdb_compile: error — no KDB/ directory under {vault_root}", file=sys.stderr)
        return 1

    # Print the header BEFORE calling compile() so the user sees the run
    # has started even during the (potentially multi-minute) LLM pass.
    ctx = RunContext.new(dry_run=args.dry_run, vault_root=vault_root)
    suffix = " (dry-run)" if args.dry_run else ""
    print(f"kdb_compile: run_id={ctx.run_id}{suffix}", flush=True)

    progress = _make_stdout_progress(dry_run=args.dry_run)
    result = compile(vault_root, dry_run=args.dry_run, run_ctx=ctx, progress=progress)

    compile_ok = "✓" if result.sources_failed == 0 else "✗"
    print(
        f"  totals   : {compile_ok}  {result.sources_attempted} attempted · "
        f"{result.sources_compiled} ok · {result.sources_failed} failed",
        flush=True,
    )

    if result.compile_errors:
        print("  errors:", file=sys.stderr)
        for err in result.compile_errors:
            print(f"    - {err}", file=sys.stderr)

    if not result.success:
        for err in result.errors:
            if err not in result.compile_errors:
                print(f"  pipeline error: {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
