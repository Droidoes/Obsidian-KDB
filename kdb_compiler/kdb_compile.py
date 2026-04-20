"""End-to-end orchestrator: scan → validate → apply → write (M1.7)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
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

# Stage names mirror the manifest.md §5 pipeline narrative. Indices are
# 1-based and rendered as `[i/N]` banners so operators can see which stage
# is active during a multi-minute live compile.
_STAGES = (
    "scan",
    "validate scan",
    "compile",
    "validate compile_result",
    "build manifest update",
    "apply pages",
    "persist state",
)
_STAGE_TOTAL = len(_STAGES)


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

    def _stage(index: int) -> float:
        _emit("stage_start", index=index, total=_STAGE_TOTAL, name=_STAGES[index - 1])
        return time.perf_counter()

    def _stage_done(index: int, t0: float, *, ok: bool = True, note: str | None = None) -> None:
        ms = int((time.perf_counter() - t0) * 1000)
        _emit(
            "stage_done", index=index, total=_STAGE_TOTAL,
            name=_STAGES[index - 1], ok=ok, latency_ms=ms, note=note,
        )

    scan_counts: dict = {}

    def _fail(errs: list[str]) -> CompileRunResult:
        return CompileRunResult(
            run_id=run_id, success=False, scan_counts=scan_counts,
            dry_run=dry_run, errors=errs,
        )

    # [1] scan
    t0 = _stage(1)
    scan_result = kdb_scan.scan(vault_root, run_ctx=ctx, write=not dry_run)
    scan_dict = scan_result.to_dict()
    scan_counts = scan_dict.get("summary", {})
    _stage_done(1, t0)
    _emit(
        "scan_done",
        total=len(scan_result.files),
        to_compile=len(scan_result.to_compile),
        to_skip=len(scan_result.to_skip),
    )

    # [2] validate scan
    t0 = _stage(2)
    scan_errors = validate_last_scan.validate(scan_dict)
    _stage_done(
        2, t0, ok=not scan_errors,
        note=(scan_errors[0] if scan_errors else None),
    )
    if scan_errors:
        return _fail(scan_errors)

    # [3] compile — Branch 1 (fixture replay when compile_result.json exists
    # AND its run_id matches the fresh scan) or Branch 2 (live compile).
    # Any stale compile_result.json is ignored and overwritten by Branch 2.
    t0 = _stage(3)
    cr: dict | None = None
    cr_note: str | None = None
    cr_path = state_root / "compile_result.json"
    if cr_path.exists():
        try:
            staged = json.loads(cr_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _stage_done(3, t0, ok=False, note=f"compile_result.json unreadable: {exc}")
            return _fail([f"compile_result.json unreadable: {exc}"])
        if staged.get("run_id") == scan_result.run_id:
            cr = staged
            cr_note = "replay from fixture"

    if cr is None:
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
            _stage_done(3, t0, ok=False, note=f"{type(exc).__name__}: {exc}")
            return _fail(
                [f"compiler.run_compile failed: {type(exc).__name__}: {exc}"]
            )
        cr = cr_obj.to_dict()
    _stage_done(3, t0, note=cr_note)

    compile_errors = list(cr.get("errors") or [])
    sources_compiled = len(cr.get("compiled_sources") or [])
    sources_failed = len(compile_errors)
    sources_attempted = sources_compiled + sources_failed

    # [4] validate compile_result
    t0 = _stage(4)
    cr_errors = validate_compile_result.validate(cr)
    _stage_done(
        4, t0, ok=not cr_errors,
        note=(cr_errors[0] if cr_errors else None),
    )
    if cr_errors:
        return _fail(cr_errors)

    # [5] build manifest update (also loads prior manifest for the diff)
    t0 = _stage(5)
    manifest_path = state_root / "manifest.json"
    prior: dict = {}
    if manifest_path.exists():
        try:
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _stage_done(5, t0, ok=False, note=f"manifest.json unreadable: {exc}")
            return _fail([f"manifest.json unreadable: {exc}"])
    next_manifest, journal = manifest_update.build_manifest_update(prior, scan_dict, cr, ctx)
    _stage_done(5, t0)

    # [6] apply pages
    t0 = _stage(6)
    apply_result = patch_applier.apply(
        state_root, vault_root,
        next_manifest=next_manifest,
        run_ctx=ctx,
        write=not dry_run,
    )
    _stage_done(6, t0)
    deltas = (journal or {}).get("deltas") or {}
    _emit(
        "pages_done",
        created=len(deltas.get("pages_created") or []),
        updated=len(deltas.get("pages_updated") or []),
        written=len(apply_result.pages_written),
        dry_run=dry_run,
    )

    # [7] persist state — manifest + journal (skipped under dry-run)
    t0 = _stage(7)
    if not dry_run:
        manifest_update.write_outputs(next_manifest, journal, state_root, ctx)
        _stage_done(7, t0)
    else:
        _stage_done(7, t0, note="skipped (dry-run)")

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


_BANNER_WIDTH = 50


def _banner_stem(index: int, total: int, name: str) -> str:
    """Left half of a stage banner: `[i/N] name .........  ` (trailing space)."""
    head = f"[{index}/{total}] {name} "
    pad = max(2, _BANNER_WIDTH - len(head) - 1)
    return head + ("." * pad) + " "


def _make_stdout_progress() -> Callable[..., None]:
    """Progress callback that streams stage banners + indented detail to stdout.

    Every print uses flush=True so WSL/tees/non-TTY wrappers render in real
    time rather than at process exit.

    Visual model:
      [i/N] name ........................................ ✓ 0.3s
        └─ optional detail line
    Live sub-events (job_start/job_done during compile) break the open
    banner and the renderer re-prints it alongside stage_done.
    """
    state = {"line_broken": False, "last_banner": ("", 0, 0, "")}

    def _progress(event: str, **f: Any) -> None:
        if event == "stage_start":
            stem = _banner_stem(f["index"], f["total"], f["name"])
            print(stem, end="", flush=True)
            state["line_broken"] = False
            state["last_banner"] = (stem, f["index"], f["total"], f["name"])
        elif event == "stage_done":
            if state["line_broken"]:
                stem, _, _, _ = state["last_banner"]
                print(stem, end="", flush=True)
            note = f.get("note") or ""
            if note == "skipped (dry-run)":
                print(f"⊘ {note}", flush=True)
            else:
                mark = "✓" if f.get("ok", True) else "✗"
                dur = f"{f['latency_ms'] / 1000:.1f}s"
                tail = f" — {note}" if note else ""
                print(f"{mark} {dur}{tail}", flush=True)
            state["line_broken"] = False
        elif event == "scan_done":
            print(
                f"  └─ {f['total']} raw files "
                f"({f['to_compile']} to compile, {f['to_skip']} to skip)",
                flush=True,
            )
        elif event == "pages_done":
            if f.get("dry_run"):
                print("  └─ dry-run (no writes)", flush=True)
            else:
                print(
                    f"  └─ {f['created']} created · "
                    f"{f['updated']} updated ({f['written']} written)",
                    flush=True,
                )
        elif event == "job_start":
            if not state["line_broken"]:
                print(flush=True)
                state["line_broken"] = True
            print(
                f"  [{f['i']}/{f['n']}] {_short_source(f['source_id'])} ...",
                end="", flush=True,
            )
        elif event == "job_done":
            mark = "✓" if f["ok"] else "✗"
            dur = f"{f['latency_ms'] / 1000:.1f}s"
            if f["ok"]:
                print(f" {mark} {dur}", flush=True)
            else:
                err = (f.get("error") or "").split(": ", 1)
                err_tail = err[1] if len(err) == 2 else (err[0] if err else "")
                print(f" {mark} {dur} — {err_tail}", flush=True)
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
    # started_at is local; the header also names the TZ abbreviation.
    ctx = RunContext.new(dry_run=args.dry_run, vault_root=vault_root)
    suffix = " (dry-run)" if args.dry_run else ""
    tz_name = datetime.fromisoformat(ctx.started_at).strftime("%Z").strip()
    print(
        f"kdb_compile: run_id={ctx.run_id}{suffix}  ({tz_name})",
        flush=True,
    )

    progress = _make_stdout_progress()
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
