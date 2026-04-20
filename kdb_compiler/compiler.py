"""compiler — per-source LLM compile orchestration.

Pipeline position:
    kdb_scan -> planner -> [compiler] -> validate -> patch_applier -> manifest_update

Contract (per blueprint §5.7 / §9):

  * `compile_one` runs the scaffold-and-fill pattern: a mutable `state`
    dict is initialised at entry, each stage updates it, and a single
    `finally` block writes the EvalRecord. This guarantees the invariant
    "exactly one eval record per compile_one call" — including the
    source-read and prompt-build failure paths. Every early return flows
    through the same finally.

  * `run_compile` plans, runs `compile_one` per job, aggregates, and
    optionally writes `compile_result.json`. An empty job list is a
    successful no-op (single info log entry, `success=True`). Run-level
    success is `len(errors) == 0` — not `len(compiled_sources) > 0`.

  * Eval records are written in every case, including `dry_run` (no
    `compile_result.json` on disk), because the records are the debug
    artifacts you run the pipeline *to* collect.

`call_model_with_retry` is imported at module level so tests can
monkeypatch `kdb_compiler.compiler.call_model_with_retry` as a clean
seam without touching `call_model_retry` itself.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

from kdb_compiler import (
    planner,
    prompt_builder,
    response_normalizer,
    validate_compiled_source_response,
)
from kdb_compiler.atomic_io import atomic_write_json
from kdb_compiler.call_model import ModelRequest
from kdb_compiler.call_model_retry import call_model_with_retry
from kdb_compiler.eval_writer import build_eval_record, write_eval_record
from kdb_compiler.run_context import RunContext
from kdb_compiler.types import (
    CompiledSource,
    CompileJob,
    CompileMeta,
    CompileResult,
    LogEntry,
    PageIntent,
)


def source_text_for(job: CompileJob) -> str:
    """Read job.abs_path as UTF-8. Propagates OSError / UnicodeDecodeError
    so compile_one's scaffold-and-fill can classify the failure."""
    return Path(job.abs_path).read_text(encoding="utf-8")


def compile_one(
    job: CompileJob,
    *,
    vault_root: Path,
    state_root: Path,
    ctx: RunContext,
    provider: str,
    model: str,
    max_tokens: int,
) -> tuple[CompiledSource | None, list[dict], list[str], str | None]:
    """Execute one per-source compile call. See blueprint §9.

    Returns (compiled_source | None, log_entries, warnings, error | None).
    Always writes exactly one EvalRecord in the finally block, regardless
    of which stage (if any) failed.
    """
    source_id = job.source_id

    state: dict = {
        "prompt": None,
        "raw_response_text": "",
        "model_response": None,
        "extract_ok": False,
        "parse_ok": False,
        "parsed_json": None,
        "schema_ok": False,
        "schema_errors": [],
        "semantic_ok": False,
        "semantic_errors": [],
        "error": None,
        "compiled_source": None,
        "log_entries": [],
        "warnings": [],
    }

    try:
        # --- read source ---
        try:
            source_text = source_text_for(job)
        except (OSError, UnicodeDecodeError) as e:
            state["error"] = (
                f"{source_id}: source read failed: {type(e).__name__}: {e}"
            )
            return (None, [], [], state["error"])

        # --- build prompt ---
        try:
            state["prompt"] = prompt_builder.build_prompt(
                vault_root=vault_root,
                source_id=source_id,
                source_text=source_text,
                context_snapshot=job.context_snapshot,
            )
        except Exception as e:
            state["error"] = (
                f"{source_id}: prompt build failed: {type(e).__name__}: {e}"
            )
            return (None, [], [], state["error"])

        # --- model call ---
        try:
            state["model_response"] = call_model_with_retry(
                ModelRequest(
                    provider=provider,
                    model=model,
                    system=state["prompt"].system,
                    prompt=state["prompt"].user,
                    temperature=0.0,
                    max_tokens=max_tokens,
                )
            )
            state["raw_response_text"] = state["model_response"].text
        except Exception as e:
            state["error"] = (
                f"{source_id}: model call failed: {type(e).__name__}: {e}"
            )
            return (None, [], [], state["error"])

        # --- truncation guard ---
        # Anthropic: stop_reason == "max_tokens"; OpenAI-compat: "length".
        # If the model hit the output ceiling, extract will fail on an
        # unclosed JSON fence — surface the real cause instead.
        sr = state["model_response"].stop_reason
        if sr in ("max_tokens", "length"):
            state["error"] = (
                f"{source_id}: truncated at max_tokens={max_tokens} "
                f"(stop_reason={sr!r}); raise --max-tokens or shorten source"
            )
            return (None, [], [], state["error"])

        # --- extract ---
        try:
            json_text = response_normalizer.extract_json_text(
                state["raw_response_text"]
            )
            state["extract_ok"] = True
        except ValueError as e:
            state["error"] = f"{source_id}: extract failed: {e}"
            return (None, [], [], state["error"])

        # --- parse ---
        try:
            state["parsed_json"] = json.loads(json_text)
            state["parse_ok"] = True
        except json.JSONDecodeError as e:
            state["error"] = (
                f"{source_id}: invalid JSON: {e.msg} at line {e.lineno}"
            )
            return (None, [], [], state["error"])

        # --- schema ---
        state["schema_errors"] = validate_compiled_source_response.validate(
            state["parsed_json"]
        )
        state["schema_ok"] = state["schema_errors"] == []
        if not state["schema_ok"]:
            state["error"] = (
                f"{source_id}: schema validation failed: {state['schema_errors'][0]}"
            )
            return (None, [], [], state["error"])

        # --- semantic ---
        state["semantic_errors"] = (
            validate_compiled_source_response.semantic_check(
                state["parsed_json"], source_id=source_id
            )
        )
        state["semantic_ok"] = state["semantic_errors"] == []
        if not state["semantic_ok"]:
            state["error"] = (
                f"{source_id}: semantic check failed: {state['semantic_errors'][0]}"
            )
            return (None, [], [], state["error"])

        # --- success ---
        parsed = state["parsed_json"]
        mr = state["model_response"]
        state["compiled_source"] = CompiledSource(
            source_id=parsed["source_id"],
            summary_slug=parsed["summary_slug"],
            pages=[PageIntent(**p) for p in parsed["pages"]],
            concept_slugs=list(parsed.get("concept_slugs", [])),
            article_slugs=list(parsed.get("article_slugs", [])),
            compile_meta=CompileMeta(
                provider=mr.provider,
                model=mr.model,
                input_tokens=mr.input_tokens,
                output_tokens=mr.output_tokens,
                latency_ms=mr.latency_ms,
                attempts=mr.attempts,
                ok=True,
                error=None,
            ),
        )
        state["log_entries"] = list(parsed.get("log_entries", []))
        state["warnings"] = list(parsed.get("warnings", []))
        return (
            state["compiled_source"],
            state["log_entries"],
            state["warnings"],
            None,
        )

    finally:
        record = build_eval_record(
            ctx=ctx,
            source_id=source_id,
            prompt=state["prompt"],
            raw_response_text=state["raw_response_text"],
            model_response=state["model_response"],
            extract_ok=state["extract_ok"],
            parse_ok=state["parse_ok"],
            parsed_json=state["parsed_json"],
            schema_ok=state["schema_ok"],
            schema_errors=state["schema_errors"],
            semantic_ok=state["semantic_ok"],
            semantic_errors=state["semantic_errors"],
        )
        write_eval_record(record, state_root)


def run_compile(
    vault_root: Path,
    *,
    state_root: Path,
    scan: dict,
    ctx: RunContext,
    provider: str = "anthropic",
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 32768,
    write: bool = True,
    progress: Callable[..., None] | None = None,
) -> CompileResult:
    """Plan -> per-source compile -> aggregate -> optionally write
    compile_result.json. Eval records are written regardless of `write` —
    they're debug artifacts and suppressing them would hide the very
    behaviour a dry run exists to inspect."""
    vault_root = Path(vault_root)
    state_root = Path(state_root)

    jobs = planner.plan(
        vault_root, scan=scan, state_root=state_root
    )

    compiled_sources: list[CompiledSource] = []
    log_dicts: list[dict] = []
    all_warnings: list[str] = []
    errors: list[str] = []

    if not jobs:
        log_dicts.append(
            {
                "level": "info",
                "message": (
                    "no eligible sources to compile "
                    "(empty to_compile or all filtered)"
                ),
                "related_slugs": [],
                "related_source_ids": [],
            }
        )

    def _emit(event: str, **fields: Any) -> None:
        if progress is None:
            return
        try:
            progress(event, **fields)
        except Exception:
            # Progress callback is observational; a broken reporter must
            # not take down the compile.
            pass

    n_jobs = len(jobs)
    for i, job in enumerate(jobs, start=1):
        _emit("job_start", i=i, n=n_jobs, source_id=job.source_id)
        t0 = time.monotonic()
        cs, logs, warns, err = compile_one(
            job,
            vault_root=vault_root,
            state_root=state_root,
            ctx=ctx,
            provider=provider,
            model=model,
            max_tokens=max_tokens,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        if cs is not None:
            compiled_sources.append(cs)
            log_dicts.extend(logs)
            all_warnings.extend(warns)
        if err is not None:
            errors.append(err)
        _emit(
            "job_done",
            i=i, n=n_jobs, source_id=job.source_id,
            ok=(err is None), latency_ms=latency_ms, error=err,
        )

    result = CompileResult(
        run_id=ctx.run_id,
        success=(len(errors) == 0),
        compiled_sources=compiled_sources,
        log_entries=[LogEntry(**le) for le in log_dicts],
        errors=errors,
        warnings=all_warnings,
    )

    if write:
        write_compile_result(result, state_root)

    return result


def write_compile_result(result: CompileResult, state_root: Path) -> None:
    """Atomic write to <state_root>/compile_result.json."""
    atomic_write_json(Path(state_root) / "compile_result.json", result.to_dict())


# ---------- CLI ----------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kdb-compile-sources",
        description=(
            "Run the per-source LLM compile over last_scan.json's to_compile "
            "list. Writes compile_result.json and one eval record per job."
        ),
    )
    p.add_argument("--vault-root", required=True, help="Absolute path to Obsidian vault root")
    p.add_argument("--provider", default="anthropic")
    p.add_argument("--model", default="claude-haiku-4-5-20251001")
    p.add_argument("--max-tokens", type=int, default=32768)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip writing compile_result.json (eval records still written)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    vault_root = Path(args.vault_root)
    state_root = vault_root / "KDB" / "state"
    scan_path = state_root / "last_scan.json"

    if not scan_path.exists():
        print(
            f"kdb-compile-sources: missing last_scan.json at {scan_path}",
            file=sys.stderr,
        )
        return 1

    try:
        scan = json.loads(scan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            f"kdb-compile-sources: last_scan.json unreadable: {exc}",
            file=sys.stderr,
        )
        return 1

    ctx = RunContext.new(dry_run=args.dry_run, vault_root=vault_root)
    result = run_compile(
        vault_root,
        state_root=state_root,
        scan=scan,
        ctx=ctx,
        provider=args.provider,
        model=args.model,
        max_tokens=args.max_tokens,
        write=not args.dry_run,
    )

    print(
        f"kdb-compile-sources: run_id={result.run_id} "
        f"success={result.success} "
        f"compiled={len(result.compiled_sources)} "
        f"errors={len(result.errors)} "
        f"warnings={len(result.warnings)}"
    )
    for err in result.errors:
        print(f"  ERROR: {err}", file=sys.stderr)
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
