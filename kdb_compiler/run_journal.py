"""run_journal — v2 runs journal builder + schema version.

The v2 journal is a queryable, stage-aware diagnostic record assembled by
the orchestrator (`kdb_compile.compile`). It is written on EVERY run —
success, failure, or dry-run — so workflow optimization has a complete
history to query against. Deep artifacts (full prompts/responses) stay in
`state/llm_resp/<run_id>/<safe_source_id>.json` and are referenced from
the journal via `resp_stats_ref` pointers rather than duplicated inline.

Top-level shape:
    schema_version, run_id, compiler_version, dry_run, vault_root,
    started_at, finished_at, duration_ms,
    success, compile_success, journal_written, manifest_written,
    terminated_at_stage, failure_stage_name, failure_type, failure_message,
    config, artifacts,
    stages[], summary{}

`stages[]` contains only stages that actually started. No synthesized
future entries after a failure.

The builder is single-run, single-thread, call-order-sensitive. The
orchestrator's eight stages each bracket with `start_stage()` and
`finish_stage()`. `finalize()` collapses accumulated state into the final
dict written to `state/runs/<run_id>.json`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kdb_compiler.run_context import RunContext, now_iso

JOURNAL_SCHEMA_VERSION = "2.0"


# Stage names mirror kdb_compile._STAGES (1-based). Kept here so
# downstream tools can introspect the journal without importing the
# orchestrator module.
STAGE_NAMES: tuple[str, ...] = (
    "scan",
    "validate scan",
    "compile",
    "validate compile_result",
    "reconcile compile_result",
    "build manifest update",
    "apply pages",
    "persist state",
)


@dataclass
class _OpenStage:
    """A stage that has started but not yet finished."""
    index: int
    name: str
    started_at: str
    t0: float  # time.perf_counter() baseline


class RunJournalBuilder:
    """Incrementally assembles a v2 run journal.

    Wire-up pattern:
        b = RunJournalBuilder(ctx, provider="anthropic", model="...",
                              max_tokens=32768, state_root=state_root)
        b.start_stage(1, "scan")
        ...
        b.finish_stage(1, ok=True, scan_summary=..., files_total=..., ...)
        ...
        b.record_source({...})                  # stage 3, once per job
        b.set_apply_stage_payload(payload_dict)  # stage 6
        b.mark_failure(idx, name, "ValidationError", "..."  # on failure
        journal = b.finalize(
            success=True, compile_success=True,
            journal_written=True, manifest_written=True,
        )
    """

    def __init__(
        self,
        ctx: RunContext,
        *,
        provider: str,
        model: str,
        max_tokens: int,
        state_root: Path,
        resp_stats_capture_full: bool = False,
    ) -> None:
        self._ctx = ctx
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens
        self._state_root = Path(state_root)
        self._capture_full = resp_stats_capture_full

        self._stages: list[dict[str, Any]] = []
        self._sources: list[dict[str, Any]] = []

        # Stage-specific payloads the orchestrator supplies separately.
        self._manifest_stage_payload: dict[str, Any] | None = None
        self._apply_stage_payload: dict[str, Any] | None = None

        # Failure metadata (set only when mark_failure fires).
        self._failure: dict[str, Any] | None = None

        # Summary inputs surfaced by orchestrator.
        self._summary_inputs: dict[str, Any] = {}

        # The one stage currently open (None between stages).
        self._open: _OpenStage | None = None

    # ---------- stage lifecycle ----------

    def start_stage(self, index: int, name: str) -> None:
        if self._open is not None:
            raise RuntimeError(
                f"start_stage({index}) called while stage "
                f"{self._open.index} is still open"
            )
        self._open = _OpenStage(
            index=index, name=name, started_at=now_iso(),
            t0=time.perf_counter(),
        )

    def finish_stage(
        self,
        index: int,
        *,
        ok: bool,
        note: str | None = None,
        **payload: Any,
    ) -> None:
        if self._open is None or self._open.index != index:
            raise RuntimeError(
                f"finish_stage({index}) called without matching start_stage"
            )
        finished_at = now_iso()
        duration_ms = int((time.perf_counter() - self._open.t0) * 1000)
        entry: dict[str, Any] = {
            "index": self._open.index,
            "name": self._open.name,
            "started_at": self._open.started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "ok": ok,
            "note": note,
        }
        entry.update(payload)
        self._stages.append(entry)
        self._open = None

    def last_stage_duration_ms(self) -> int:
        """Duration of the most recently finished stage. -1 if no stages yet."""
        if not self._stages:
            return -1
        return int(self._stages[-1].get("duration_ms", 0))

    # ---------- per-source telemetry (stage 3) ----------

    def record_source(self, record: dict[str, Any]) -> None:
        """Append one per-source compile stats record.

        In replay mode, live-call fields (provider/model/tokens/hashes/
        resp_stats_ref) may be None or omitted. Caller is responsible for
        constructing the right shape.
        """
        self._sources.append(dict(record))

    # ---------- stage-specific payload setters ----------

    def set_manifest_stage_payload(self, payload: dict[str, Any]) -> None:
        """Supplied by build_manifest_update; folded into stage 5 entry."""
        self._manifest_stage_payload = dict(payload) if payload else None

    def set_apply_stage_payload(self, payload: dict[str, Any]) -> None:
        """Supplied by patch_applier; folded into stage 6 entry."""
        self._apply_stage_payload = dict(payload) if payload else None

    # ---------- summary contributions ----------

    def set_summary_inputs(self, **kv: Any) -> None:
        self._summary_inputs.update(kv)

    # ---------- failure marking ----------

    def mark_failure(
        self,
        stage_index: int,
        stage_name: str,
        failure_type: str,
        failure_message: str,
    ) -> None:
        """Record end-of-run failure metadata. Idempotent first-write-wins."""
        if self._failure is not None:
            return
        self._failure = {
            "terminated_at_stage": stage_index,
            "failure_stage_name": stage_name,
            "failure_type": failure_type,
            "failure_message": failure_message,
        }

    # ---------- finalize ----------

    def finalize(
        self,
        *,
        success: bool,
        compile_success: bool | None = None,
        journal_written: bool,
        manifest_written: bool,
        compile_result: dict | None = None,
        next_manifest: dict | None = None,
        apply_result: dict | None = None,
        journal_path: str | None = None,
    ) -> dict[str, Any]:
        """Collapse accumulated state into the final journal dict."""
        if self._open is not None:
            # Orchestrator bug: stage still open at finalize. Close it as
            # failed so the journal is still internally consistent.
            self.finish_stage(
                self._open.index, ok=False,
                note="stage still open at finalize (orchestrator bug)",
            )

        finished_at = now_iso()
        duration_ms = self._duration_ms(finished_at)

        # Fold manifest-stage payload into stage 6 entry if present.
        if self._manifest_stage_payload is not None:
            for entry in self._stages:
                if entry["index"] == 6:
                    entry.update(self._manifest_stage_payload)
                    break

        # Fold apply-stage payload into stage 7 entry if present.
        if self._apply_stage_payload is not None:
            for entry in self._stages:
                if entry["index"] == 7:
                    entry.update(self._apply_stage_payload)
                    break

        # Attach sources[] to stage 3 entry, if stage 3 was reached.
        for entry in self._stages:
            if entry["index"] == 3:
                entry.setdefault("sources", [])
                entry["sources"] = list(self._sources)
                # Aggregate totals across live sources. Sums over None
                # tokens (replay mode) skip Nones.
                agg = _aggregate_sources(self._sources)
                entry.setdefault("aggregate", agg)
                break

        failure = self._failure or {
            "terminated_at_stage": None,
            "failure_stage_name": None,
            "failure_type": None,
            "failure_message": None,
        }

        state_root_posix = self._state_root.as_posix()
        artifacts = {
            "last_scan_path": f"{state_root_posix}/last_scan.json",
            "compile_result_path": f"{state_root_posix}/compile_result.json",
            "manifest_path": f"{state_root_posix}/manifest.json",
            "journal_path": journal_path
                or f"{state_root_posix}/runs/{self._ctx.run_id}.json",
            "resp_stats_dir": f"{state_root_posix}/llm_resp/{self._ctx.run_id}/",
        }

        summary = self._build_summary(
            compile_result=compile_result,
            next_manifest=next_manifest,
            apply_result=apply_result,
        )

        return {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "run_id": self._ctx.run_id,
            "compiler_version": self._ctx.compiler_version,
            "dry_run": self._ctx.dry_run,
            "vault_root": str(self._ctx.vault_root),
            "started_at": self._ctx.started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "success": success,
            "compile_success": compile_success,
            "journal_written": journal_written,
            "manifest_written": manifest_written,
            **failure,
            "config": {
                "provider": self._provider,
                "model": self._model,
                "max_tokens": self._max_tokens,
                "resp_stats_capture_full": self._capture_full,
            },
            "artifacts": artifacts,
            "stages": list(self._stages),
            "summary": summary,
        }

    # ---------- helpers ----------

    def _duration_ms(self, finished_at: str) -> int:
        """ISO-8601 subtraction for the top-level duration. Stage-level
        durations use perf_counter for accuracy; the top-level is
        wall-clock to match started_at/finished_at."""
        try:
            from datetime import datetime
            dt_s = datetime.fromisoformat(self._ctx.started_at)
            dt_f = datetime.fromisoformat(finished_at)
            return int((dt_f - dt_s).total_seconds() * 1000)
        except Exception:
            return 0

    def _build_summary(
        self,
        *,
        compile_result: dict | None,
        next_manifest: dict | None,
        apply_result: dict | None,
    ) -> dict[str, Any]:
        # Delta fields default to empty and are filled from the stage-5
        # payload when present.
        deltas_default = {
            "sources_added": [], "sources_removed": [],
            "sources_moved": [], "sources_changed": [],
            "pages_created": [], "pages_updated": [],
            "orphans_flagged": [], "orphans_cleared": [],
        }
        deltas = deltas_default
        if self._manifest_stage_payload:
            payload_deltas = self._manifest_stage_payload.get("deltas")
            if payload_deltas:
                deltas = dict(deltas_default)
                deltas.update(payload_deltas)

        cr = compile_result or {}
        compiled_sources = cr.get("compiled_sources") or []
        sources_failed = len(cr.get("errors") or [])
        sources_compiled = len(compiled_sources)
        sources_attempted = sources_compiled + sources_failed

        pages_written_count = 0
        if apply_result and "pages_written" in apply_result:
            pages_written_count = len(apply_result["pages_written"])

        # Token totals come from the recorded per-source entries.
        tokens_in = sum(
            (s.get("input_tokens") or 0) for s in self._sources
        )
        tokens_out = sum(
            (s.get("output_tokens") or 0) for s in self._sources
        )

        counts = {
            "sources_attempted": sources_attempted,
            "sources_compiled": sources_compiled,
            "sources_failed": sources_failed,
            "pages_created": len(deltas.get("pages_created") or []),
            "pages_updated": len(deltas.get("pages_updated") or []),
            "pages_written": pages_written_count,
            "orphans_flagged": len(deltas.get("orphans_flagged") or []),
            "orphans_cleared": len(deltas.get("orphans_cleared") or []),
        }

        inputs = dict(self._summary_inputs)
        inputs.setdefault("compile_sources_processed", sources_compiled)

        log_entries = list(self._ctx.log_entries)
        warnings = list(cr.get("warnings") or [])
        errors = list(cr.get("errors") or [])

        return {
            "inputs": inputs,
            "counts": counts,
            "deltas": deltas,
            "tokens": {"input": tokens_in, "output": tokens_out},
            "log_entries": log_entries,
            "warnings": warnings,
            "errors": errors,
        }


def _aggregate_sources(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum tokens/latency/attempts across sources, ignoring None (replay)."""
    def _s(field_name: str) -> int:
        total = 0
        for s in sources:
            v = s.get(field_name)
            if isinstance(v, int):
                total += v
        return total

    providers = sorted({
        s["provider"] for s in sources
        if isinstance(s.get("provider"), str) and s["provider"]
    })
    models = sorted({
        s["model"] for s in sources
        if isinstance(s.get("model"), str) and s["model"]
    })
    return {
        "total_input_tokens": _s("input_tokens"),
        "total_output_tokens": _s("output_tokens"),
        "total_latency_ms": _s("latency_ms"),
        "total_attempts": _s("attempts"),
        "providers": providers,
        "models": models,
    }
