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

import os
import shutil
from pathlib import Path

from kdb_benchmark.paths import MODELS_JSON
from kdb_benchmark.registry import ModelEntry, load_registry
from kdb_compiler import __version__ as _COMPILER_VERSION
from kdb_compiler.compiler import compile_one
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
    """Build the path-prefix the schema validator expects for source_ids
    coming out of `sources_dir`.

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
) -> tuple[str, Path]:
    """Run `compile_one` against `model_id` for every .md file in
    `sources_dir`. Returns (run_id, state_root).

    `state_root` is rooted at `runs_root/<run_id>/state/` so the scorer
    can subsequently call `score_run(state_root, run_id, model_id)`.

    Side effects:
      * Creates `runs_root/<run_id>/state/llm_resp/<run_id>/*.json`
        (one RespStatsRecord per source).
      * Creates `runs_root/<run_id>/vault/KDB/KDB-Compiler-System-Prompt.md`
        (frozen copy of the system prompt for re-runnability).
      * Sets `KDB_RESP_STATS_CAPTURE_FULL=1` in os.environ.

    Raises:
      ValueError — `model_id` not found in registry at `registry_path`.
    """
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

    # Schema gate (Task #34): the validator's sourceId pattern is
    # `^<prefix>/.+`. Production prefix is "KDB/raw"; benchmark sources
    # don't live there, so derive a prefix from `sources_dir` and
    # construct each source_id as "<prefix>/<filename>" so model echo +
    # schema validation align.
    source_id_prefix = _derive_source_id_prefix(sources_dir)

    # Walk the corpus. Filter to *.md (skip *.meta.yaml companions and
    # any other non-markdown files).
    source_files = sorted(p for p in sources_dir.glob("*.md"))

    for src_path in source_files:
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
            source_id_prefix=source_id_prefix,
        )

    return run_id, state_root
