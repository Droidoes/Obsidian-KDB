"""kdb_benchmark.runner — Task #30 isolation-contract orchestrator.

Per docs/task19-kpi-design.md § Phase 3 § 1 + Task #30 ledger entry:

  * Invokes `compile_one` directly (NOT the production kdb-compile pipeline).
    This is structural isolation — the runner cannot call manifest_update,
    patch_applier, or any vault-write stage because it doesn't import them.
  * Uses an EMPTY ContextSnapshot for every source (Round 4 [3]:
    every benchmark source compiled cold for determinism).
  * benchmark state_root resolves under `<runs_root>/<run_id>/state/` —
    never touches the user's live vault state.
  * run_id format `<model_id>-<local-ISO-timestamp_TZ>` so multi-model
    sessions in the same runs_root sort cleanly and identify the model
    in filenames.
  * Sets `KDB_RESP_STATS_CAPTURE_FULL=1` before calling compile_one so the
    scorer's M1/M2/M3/S3 path (which needs parsed_json) is satisfied.
  * Snapshots the KDB-Compiler-System-Prompt.md into the per-run vault
    stub so prompt_builder can read it without depending on the live
    vault — and re-runnable years later if the live vault changes.

The output of `run_benchmark` is consumed by `kdb_benchmark.scorer.score_run`.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from kdb_benchmark.paths import MODELS_JSON
from kdb_benchmark.registry import ModelEntry, load_registry
from kdb_compiler import __version__ as _COMPILER_VERSION
from kdb_compiler.compiler import compile_one
from kdb_compiler.resp_stats_writer import safe_source_id
from kdb_compiler.run_context import (
    MANIFEST_SCHEMA_VERSION,
    RunContext,
    now_iso,
    run_id_from_timestamp,
)
from kdb_compiler.types import CompileJob, ContextSnapshot


def _resolve_model_entry(model_id: str, registry_path: Path) -> ModelEntry:
    """Look up `model_id` in the registry. Raises if not found."""
    registry = load_registry(registry_path)
    for entry in registry:
        if entry.id == model_id:
            return entry
    raise ValueError(
        f"model_id '{model_id}' not found in registry at {registry_path}"
    )


def _derive_source_id_prefix(sources_dir: Path) -> str:
    """Build the path-prefix used when constructing source_ids for sources
    in `sources_dir`. After Task #41 the schema no longer constrains
    source_id format (the LLM emits source_name only), so this prefix is
    a runner-side convention for the persisted compile_result artifact.

    `--sources benchmark/sources/`     → `benchmark/sources`
    `--sources /tmp/kdb-smoke/`        → `tmp/kdb-smoke`
    `--sources ./benchmark/sources`    → `benchmark/sources`

    POSIX-normalized; leading `/` and trailing `/` stripped; relative
    `.` segments collapsed. Falls back to `"."` only for empty input
    (which the runner never produces).
    """
    s = Path(sources_dir).as_posix().lstrip("/").rstrip("/")
    if s.startswith("./"):
        s = s[2:]
    return s or "."


def run_benchmark(
    *,
    sources_dir: Path,
    model_id: str,
    runs_root: Path,
    system_prompt_path: Path,
    max_tokens: int = 32768,
    registry_path: Path = MODELS_JSON,
) -> tuple[str, Path, dict]:
    """Run `compile_one` against `model_id` for every .md file in
    `sources_dir`. Returns (run_id, state_root, compile_metrics).

    `state_root` is rooted at `runs_root/<run_id>/state/` so the scorer
    can subsequently call `score_run(state_root, run_id, model_id)`.

    `compile_metrics` (Task #46) is a dict with: compile_seconds (wall
    clock for the source loop), n_sources, n_source_words (sum of
    per-source word counts read from the just-written RespStatsRecord
    files; 0 if any record is missing).

    Per-source progress (Task #46): after each compile_one returns, prints
    a single line to stdout — `[{model_id}]   N/M  filename  XX.Xs
    in=NNNNN  out=NNNNN  [⚠ stop=length]`. The truncation warning fires
    when `stop_reason in ('length', 'max_tokens')`. Best-effort: if the
    record file isn't readable, the line is skipped (compile still runs).

    Side effects:
      * Creates `runs_root/<run_id>/state/llm_resp/<run_id>/*.json`
        (one RespStatsRecord per source).
      * Creates `runs_root/<run_id>/vault/KDB/KDB-Compiler-System-Prompt.md`
        (frozen copy of the system prompt for re-runnability).
      * Sets `KDB_RESP_STATS_CAPTURE_FULL=1` in os.environ.

    Raises:
      FileNotFoundError — `sources_dir` does not exist or is not a directory.
      ValueError — `model_id` not found in registry at `registry_path`,
        or `sources_dir` contains no `.md` files.
    """
    # Task #40: validate sources_dir up front, before any side effects
    # (run dir creation, prompt snapshot, env var). A missing or empty
    # sources_dir would otherwise silently produce zero records and only
    # surface as a misleading "no records found" downstream in the scorer.
    if not sources_dir.is_dir():
        raise FileNotFoundError(
            f"sources_dir does not exist or is not a directory: {sources_dir}"
        )
    source_files = sorted(p for p in sources_dir.glob("*.md"))
    if not source_files:
        raise ValueError(
            f"sources_dir contains no .md files: {sources_dir}"
        )

    entry = _resolve_model_entry(model_id, registry_path)

    # Generate run_id: <model_id>-<filename-safe local ISO timestamp_TZ>
    timestamp = now_iso()
    base_run_id = run_id_from_timestamp(timestamp)
    run_id = f"{model_id}-{base_run_id}"

    # Set up isolated run dirs
    run_dir = Path(runs_root) / run_id
    state_root = run_dir / "state"
    vault_root = run_dir / "vault"
    state_root.mkdir(parents=True, exist_ok=True)
    vault_kdb = vault_root / "KDB"
    vault_kdb.mkdir(parents=True, exist_ok=True)

    # Snapshot the system prompt into the benchmark vault stub
    shutil.copy2(system_prompt_path, vault_kdb / "KDB-Compiler-System-Prompt.md")

    # Build a custom RunContext (RunContext.new() generates its own
    # run_id; we want the model_id-prefixed one so resp_stats records
    # carry it consistently).
    ctx = RunContext(
        run_id=run_id,
        started_at=timestamp,
        compiler_version=_COMPILER_VERSION,
        schema_version=MANIFEST_SCHEMA_VERSION,
        dry_run=False,
        vault_root=vault_root,
        kdb_root=vault_kdb,
    )

    # Capture-full mode is mandatory for benchmark scoring (§ 3).
    os.environ["KDB_RESP_STATS_CAPTURE_FULL"] = "1"

    # Construct source_ids for the persisted compile_result artifact using
    # a path-prefix derived from `sources_dir`. After Task #41 the schema
    # no longer constrains source_id format (the LLM emits source_name only,
    # the runner injects source_id post-parse), so this prefix is a
    # runner-side convention for downstream artifacts and is not threaded
    # through to validation.
    source_id_prefix = _derive_source_id_prefix(sources_dir)

    n_sources = len(source_files)
    n_source_words = 0
    t_compile_start = time.monotonic()

    for i, src_path in enumerate(source_files, start=1):
        source_id = f"{source_id_prefix}/{src_path.name}"
        job = CompileJob(
            source_id=source_id,
            abs_path=str(src_path.absolute()),
            context_snapshot=ContextSnapshot(source_id=source_id, pages=[]),
        )
        compile_one(
            job,
            vault_root=vault_root,
            state_root=state_root,
            ctx=ctx,
            provider=entry.provider,
            model=entry.model,
            max_tokens=max_tokens,
            use_completion_tokens=entry.use_completion_tokens,
            extra_body=entry.extra_body,
        )

        # Task #46: per-source progress line. Read the just-written
        # RespStatsRecord (compile_one writes in `finally`, so it exists
        # even on failure) for tokens/latency/stop_reason. Best-effort —
        # if the file is unreadable we skip the line and the word count.
        rec_path = state_root / "llm_resp" / run_id / f"{safe_source_id(source_id)}.json"
        try:
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        in_tok = rec.get("input_tokens") or 0
        out_tok = rec.get("output_tokens") or 0
        latency_ms = rec.get("latency_ms") or 0
        stop_reason = rec.get("stop_reason") or ""
        n_source_words += rec.get("source_words") or 0
        warning = f"  ⚠ stop={stop_reason}" if stop_reason in ("length", "max_tokens") else ""
        print(
            f"[{model_id}]   {i}/{n_sources}  "
            f"{src_path.name:<35}  "
            f"{latency_ms / 1000:>5.1f}s  "
            f"in={in_tok:>6}  out={out_tok:>6}{warning}",
            flush=True,
        )

    compile_seconds = time.monotonic() - t_compile_start
    compile_metrics = {
        "compile_seconds": round(compile_seconds, 2),
        "n_sources": n_sources,
        "n_source_words": n_source_words,
    }
    return run_id, state_root, compile_metrics
