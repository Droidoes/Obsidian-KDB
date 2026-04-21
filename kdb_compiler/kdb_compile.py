"""End-to-end orchestrator: scan → validate → apply → write (M1.7).

Owns v2 run journal assembly: the journal is always written to
`state/runs/<run_id>.json` — success, failure, or dry-run. Under dry-run
the manifest is not written but the journal still is (`dry_run: true`
flag inside). See `run_journal.py` for the journal schema.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from kdb_compiler import (
    atomic_io,
    compiler,
    kdb_scan,
    manifest_update,
    patch_applier,
    reconcile,
    validate_compile_result,
    validate_last_scan,
)
from kdb_compiler.run_context import RunContext
from kdb_compiler.run_journal import (
    JOURNAL_SCHEMA_VERSION,
    STAGE_NAMES,
    RunJournalBuilder,
)

# Stage names mirror the manifest.md §5 pipeline narrative. Indices are
# 1-based and rendered as `[i/N]` banners so operators can see which stage
# is active during a multi-minute live compile.
_STAGES = STAGE_NAMES
_STAGE_TOTAL = len(_STAGES)

_DEFAULT_PROVIDER = "anthropic"
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_MAX_TOKENS = 32768


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


def _write_journal(journal: dict, state_root: Path, run_id: str) -> Path:
    """Atomic write to <state_root>/runs/<run_id>.json."""
    runs_dir = Path(state_root) / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run_id}.json"
    atomic_io.atomic_write_json(path, journal, sort_keys=True)
    return path


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

    ctx = run_ctx if run_ctx is not None else RunContext.new(
        dry_run=dry_run, vault_root=vault_root,
    )
    dry_run = ctx.dry_run  # ctx is authoritative; reconcile if run_ctx was injected
    run_id = ctx.run_id

    builder = RunJournalBuilder(
        ctx,
        provider=_DEFAULT_PROVIDER,
        model=_DEFAULT_MODEL,
        max_tokens=_DEFAULT_MAX_TOKENS,
        state_root=state_root,
        resp_stats_capture_full=(
            os.environ.get("KDB_RESP_STATS_CAPTURE_FULL") == "1"
        ),
    )

    def _emit(event: str, **fields: Any) -> None:
        if progress is None:
            return
        try:
            progress(event, **fields)
        except Exception:
            pass

    def _stage_open(index: int) -> None:
        """Begin a stage: emit progress banner AND start builder timer."""
        _emit("stage_start", index=index, total=_STAGE_TOTAL, name=_STAGES[index - 1])
        builder.start_stage(index, _STAGES[index - 1])

    def _stage_close(index: int, *, ok: bool = True, note: str | None = None,
                     **payload: Any) -> None:
        """End a stage: close builder entry then emit stage_done progress.
        `payload` keys land on the stage's journal entry."""
        builder.finish_stage(index, ok=ok, note=note, **payload)
        _emit(
            "stage_done", index=index, total=_STAGE_TOTAL,
            name=_STAGES[index - 1], ok=ok,
            latency_ms=builder.last_stage_duration_ms(), note=note,
        )

    # State for assembly at the end.
    scan_counts: dict = {}
    cr: dict | None = None
    next_manifest: dict | None = None
    apply_result: patch_applier.ApplyResult | None = None
    compile_success: bool | None = None

    def _finalize_and_write(
        *, success: bool, manifest_written: bool, journal_written: bool,
    ) -> None:
        """Build the final journal and persist it to disk (unless told not
        to). Mutates nothing on the orchestrator state."""
        apply_payload: dict[str, Any] = {}
        if apply_result is not None:
            written = list(apply_result.pages_written)
            apply_payload = {
                "pages_written": written,
                "pages_written_count": len(written),
                "pages_created_count": len(
                    (manifest_stage.get("deltas") or {}).get("pages_created") or []
                ) if manifest_stage else 0,
                "pages_updated_count": len(
                    (manifest_stage.get("deltas") or {}).get("pages_updated") or []
                ) if manifest_stage else 0,
                "bytes_written": _bytes_written(vault_root, written),
            }
        builder.set_apply_stage_payload(apply_payload)

        journal = builder.finalize(
            success=success,
            compile_success=compile_success,
            journal_written=journal_written,
            manifest_written=manifest_written,
            compile_result=cr,
            next_manifest=next_manifest,
            apply_result=(
                {"pages_written": list(apply_result.pages_written)}
                if apply_result is not None else None
            ),
        )
        if journal_written:
            _write_journal(journal, state_root, run_id)

    manifest_stage: dict[str, Any] | None = None

    def _fail(
        errs: list[str],
        *,
        stage_index: int,
        stage_name: str,
        failure_type: str,
    ) -> CompileRunResult:
        """Record failure on the builder, write journal, return. v2 always
        writes the journal — success, failure, and dry-run alike — so
        workflow optimization has a complete history to query against."""
        msg = errs[0] if errs else ""
        builder.mark_failure(stage_index, stage_name, failure_type, msg)
        _finalize_and_write(
            success=False,
            manifest_written=False,
            journal_written=True,
        )
        return CompileRunResult(
            run_id=run_id, success=False, scan_counts=scan_counts,
            dry_run=dry_run, errors=errs,
            manifest_written=False,
            journal_written=True,
        )

    # ----- [1] scan -----
    _stage_open(1)
    try:
        scan_result = kdb_scan.scan(vault_root, run_ctx=ctx, write=not dry_run)
    except Exception as exc:
        _stage_close(1, ok=False, note=f"{type(exc).__name__}: {exc}")
        return _fail(
            [f"scan failed: {type(exc).__name__}: {exc}"],
            stage_index=1, stage_name=_STAGES[0],
            failure_type=type(exc).__name__,
        )
    scan_dict = scan_result.to_dict()
    scan_counts = scan_dict.get("summary", {})
    reconcile_counts = _count_reconcile(scan_dict.get("to_reconcile") or [])
    _stage_close(
        1, ok=True,
        scan_run_id=scan_result.run_id,
        files_total=len(scan_result.files),
        to_compile_count=len(scan_result.to_compile),
        to_skip_count=len(scan_result.to_skip),
        to_reconcile_count=len(scan_dict.get("to_reconcile") or []),
        scan_summary=scan_counts,
        reconcile_counts=reconcile_counts,
        last_scan_path=(state_root / "last_scan.json").as_posix(),
    )
    _emit(
        "scan_done",
        total=len(scan_result.files),
        to_compile=len(scan_result.to_compile),
        to_skip=len(scan_result.to_skip),
    )
    builder.set_summary_inputs(
        scan_run_id=scan_result.run_id,
        last_scan_path=(state_root / "last_scan.json").as_posix(),
        compile_result_path=(state_root / "compile_result.json").as_posix(),
    )

    # ----- [2] validate scan -----
    _stage_open(2)
    scan_errors = validate_last_scan.validate(scan_dict)
    _stage_close(
        2, ok=not scan_errors,
        note=(scan_errors[0] if scan_errors else None),
        error_count=len(scan_errors),
        errors=list(scan_errors),
    )
    if scan_errors:
        return _fail(
            scan_errors, stage_index=2, stage_name=_STAGES[1],
            failure_type="ValidationError",
        )

    # ----- [3] compile -----
    # Branch 1 (fixture replay when compile_result.json exists AND its
    # run_id matches the fresh scan) or Branch 2 (live compile).
    _stage_open(3)
    cr_note: str | None = None
    cr_mode = "live"
    cr_path = state_root / "compile_result.json"
    if cr_path.exists():
        try:
            staged = json.loads(cr_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            note = f"compile_result.json unreadable: {exc}"
            _stage_close(3, ok=False, note=note, mode="fixture",
                         jobs_planned=0, jobs_attempted=0,
                         jobs_succeeded=0, jobs_failed=0)
            return _fail(
                [note], stage_index=3, stage_name=_STAGES[2],
                failure_type=type(exc).__name__,
            )
        if staged.get("run_id") == scan_result.run_id:
            cr = staged
            cr_note = "replay from fixture"
            cr_mode = "replay"

    if cr is None:
        try:
            cr_obj = compiler.run_compile(
                vault_root,
                state_root=state_root,
                scan=scan_dict,
                ctx=ctx,
                write=not dry_run,
                progress=progress,
                source_stats_sink=builder.record_source,
            )
        except Exception as exc:
            _stage_close(3, ok=False, note=f"{type(exc).__name__}: {exc}",
                         mode=cr_mode)
            return _fail(
                [f"compiler.run_compile failed: {type(exc).__name__}: {exc}"],
                stage_index=3, stage_name=_STAGES[2],
                failure_type=type(exc).__name__,
            )
        cr = cr_obj.to_dict()

    compile_errors = list(cr.get("errors") or [])
    sources_compiled = len(cr.get("compiled_sources") or [])
    sources_failed = len(compile_errors)
    sources_attempted = sources_compiled + sources_failed
    compile_success = bool(cr.get("success", True))

    _stage_close(
        3, ok=True, note=cr_note,
        mode=cr_mode,
        jobs_planned=sources_attempted,
        jobs_attempted=sources_attempted,
        jobs_succeeded=sources_compiled,
        jobs_failed=sources_failed,
    )

    # ----- [4] validate compile_result -----
    # Stage 4 diagnoses (validator) and repairs (reconciler) in one breath.
    # Commit 6 will split this into two banner stages ([4] validate, [5]
    # reconcile); for now they share one stage entry in the journal but the
    # payload already carries the measure_findings + reconciler_actions +
    # response_score fields that future consumers (eval framework) expect.
    _stage_open(4)
    cr_result = validate_compile_result.validate(cr)
    cr_errors = [f.detail for f in cr_result.gate_errors]

    reconciler_actions: list = []
    response_score = None
    if not cr_errors:
        try:
            reconciler_actions = reconcile.reconcile(cr, cr_result.measure_findings)
        except reconcile.ReconcileError as exc:
            # Validator emitted a measure finding reconciler can't dispatch —
            # contract bug between the two modules, not a runtime condition.
            note = f"ReconcileError: {exc}"
            _stage_close(
                4, ok=False, note=note,
                error_count=1, errors=[note],
                measure_findings=[asdict(f) for f in cr_result.measure_findings],
                reconciler_actions=[],
                response_score=None,
            )
            return _fail(
                [note], stage_index=4, stage_name=_STAGES[3],
                failure_type="ReconcileError",
            )
        response_score = validate_compile_result.score_response(cr, cr_result)

    _stage_close(
        4, ok=not cr_errors,
        note=(cr_errors[0] if cr_errors else None),
        error_count=len(cr_errors),
        errors=list(cr_errors),
        measure_findings=[asdict(f) for f in cr_result.measure_findings],
        reconciler_actions=[asdict(a) for a in reconciler_actions],
        response_score=asdict(response_score) if response_score is not None else None,
    )
    if cr_errors:
        return _fail(
            cr_errors, stage_index=4, stage_name=_STAGES[3],
            failure_type="ValidationError",
        )

    # ----- [5] build manifest update -----
    _stage_open(5)
    manifest_path = state_root / "manifest.json"
    prior: dict = {}
    prior_manifest_loaded = False
    if manifest_path.exists():
        try:
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
            prior_manifest_loaded = True
        except (json.JSONDecodeError, OSError) as exc:
            note = f"manifest.json unreadable: {exc}"
            _stage_close(5, ok=False, note=note,
                         prior_manifest_loaded=False)
            return _fail(
                [note], stage_index=5, stage_name=_STAGES[4],
                failure_type=type(exc).__name__,
            )

    try:
        next_manifest, manifest_stage = manifest_update.build_manifest_update(
            prior, scan_dict, cr, ctx,
        )
    except Exception as exc:
        note = f"{type(exc).__name__}: {exc}"
        _stage_close(5, ok=False, note=note,
                     prior_manifest_loaded=prior_manifest_loaded)
        return _fail(
            [f"build_manifest_update failed: {note}"],
            stage_index=5, stage_name=_STAGES[4],
            failure_type=type(exc).__name__,
        )

    # Ensure the stage-5 payload carries prior_manifest_loaded (from a
    # real load vs an empty prior) — build_manifest_stage_payload uses
    # `bool(prior)` which agrees for empty-dict prior.
    manifest_stage["prior_manifest_loaded"] = prior_manifest_loaded
    builder.set_manifest_stage_payload(manifest_stage)
    _stage_close(5, ok=True)

    # ----- [6] apply pages -----
    _stage_open(6)
    try:
        apply_result = patch_applier.apply(
            vault_root,
            compile_result=cr,
            next_manifest=next_manifest,
            run_ctx=ctx,
            write=not dry_run,
        )
    except Exception as exc:
        note = f"{type(exc).__name__}: {exc}"
        _stage_close(6, ok=False, note=note)
        return _fail(
            [f"patch_applier.apply failed: {note}"],
            stage_index=6, stage_name=_STAGES[5],
            failure_type=type(exc).__name__,
        )
    _stage_close(6, ok=True)

    deltas = manifest_stage.get("deltas") or {}
    _emit(
        "pages_done",
        created=len(deltas.get("pages_created") or []),
        updated=len(deltas.get("pages_updated") or []),
        written=len(apply_result.pages_written),
        dry_run=dry_run,
    )

    # ----- [7] persist state -----
    # Under v2 the journal is written LAST so its stage-7 entry reflects
    # the real manifest_written outcome. This inverts the old "journal
    # then pointer" order — still atomic per-file via atomic_io.
    _stage_open(7)
    manifest_written = False
    # v2: journal is ALWAYS written (success, failure, dry-run). The file
    # itself declares `dry_run: true` when applicable; downstream tooling
    # filters on that instead of on file presence.
    journal_written = True
    skipped_reason = "dry-run" if dry_run else None

    if not dry_run:
        try:
            atomic_io.atomic_write_json(
                manifest_path, next_manifest, sort_keys=True,
            )
            manifest_written = True
        except Exception as exc:
            note = f"manifest write failed: {type(exc).__name__}: {exc}"
            _stage_close(
                7, ok=False, note=note,
                journal_written=journal_written,
                manifest_written=False,
                journal_path=(state_root / "runs" / f"{run_id}.json").as_posix(),
                manifest_path=manifest_path.as_posix(),
                skipped_manifest_write_reason="failure",
            )
            return _fail(
                [note], stage_index=7, stage_name=_STAGES[6],
                failure_type=type(exc).__name__,
            )

    note = "skipped (dry-run)" if dry_run else None
    _stage_close(
        7, ok=True, note=note,
        journal_written=journal_written,
        manifest_written=manifest_written,
        journal_path=(state_root / "runs" / f"{run_id}.json").as_posix(),
        manifest_path=manifest_path.as_posix(),
        skipped_manifest_write_reason=skipped_reason,
    )

    _finalize_and_write(
        success=True,
        manifest_written=manifest_written,
        journal_written=journal_written,
    )

    return CompileRunResult(
        run_id=run_id,
        success=True,
        scan_counts=scan_counts,
        pages_written=apply_result.pages_written if not dry_run else [],
        manifest_written=manifest_written,
        journal_written=journal_written,
        dry_run=dry_run,
        errors=compile_errors,
        sources_attempted=sources_attempted,
        sources_compiled=sources_compiled,
        sources_failed=sources_failed,
        compile_errors=compile_errors,
    )


def _bytes_written(vault_root: Path, pages_written: list[str]) -> int:
    total = 0
    for rel in pages_written:
        try:
            total += (vault_root / rel).stat().st_size
        except OSError:
            continue
    return total


def _count_reconcile(ops: list[dict]) -> dict[str, int]:
    moved = sum(1 for op in ops if op.get("type") == "MOVED")
    deleted = sum(1 for op in ops if op.get("type") == "DELETED")
    return {"moved": moved, "deleted": deleted}


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
        f"kdb_compile: run_id={ctx.run_id}  ({tz_name}){suffix}",
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
