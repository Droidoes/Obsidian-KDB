"""compiler — per-source LLM compile orchestration.

Pipeline position:
    kdb_scan -> [compiler] -> validate -> page_writer -> manifest_writer

Contract (per blueprint §5.7 / §9):

  * `compile_one` runs the scaffold-and-fill pattern: a mutable `state`
    dict is initialised at entry, each stage updates it, and a single
    `finally` block writes the RespStatsRecord. This guarantees the
    invariant "exactly one resp-stats record per compile_one call" —
    including the source-read and prompt-build failure paths. Every
    early return flows through the same finally.

  * Resp-stats records are written in every case because the records are
    the debug artifacts you run the pipeline *to* collect.

`call_model_with_retry` is imported at module level so tests can
monkeypatch `kdb_compiler.compiler.call_model_with_retry` as a clean
seam without touching `call_model_retry` itself.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Literal, NamedTuple

from kdb_compiler import (
    canonicalize,
    prompt_builder,
    repair,
    response_normalizer,
    validate_compile_result,
    validate_source_response,
)
from kdb_compiler.source_io import SourceFrontmatter, parse_source_file
from kdb_compiler.call_model import ModelRequest
from kdb_compiler.call_model_retry import call_model_with_retry
from kdb_compiler.canonicalize import AliasLedger
from kdb_compiler.context_loader import T2Mode, build_context_snapshot
from kdb_compiler.repair import reconcile_body_links, reconcile_slug_lists
from kdb_compiler.resp_stats_writer import build_resp_stats, write_resp_stats
from kdb_compiler.run_context import RunContext
from kdb_compiler.types import (
    CompiledSource,
    CompileJob,
    CompileMeta,
    CompileSourceResult,
    ContextSnapshot,
    PageIntent,
    RespStatsRecord,
)


FailureStage = Literal[
    "source_read", "prompt_build", "model_call",
    "truncation", "extract", "parse",
]

_FAILURE_MSG_CAP = 2000

log = logging.getLogger(__name__)

# Pass-2 re-calls the model on a recoverable bad-JSON emission (extract/parse/
# schema), mirroring Pass-1's call_pass1 retry. initial + 1 retry.
_MAX_COMPILE_ATTEMPTS = 2


class FailureTelemetry(NamedTuple):
    """Task #25 — pre-validation failure capture for RespStatsRecord.

    Co-presence enforced by construction: stage / exception_type / message
    are always all three populated. Schema/semantic validation failures
    use schema_errors / semantic_errors instead — they have structured
    list surfaces and are out of scope for the failure_* triplet.
    """
    stage: FailureStage
    exception_type: str
    message: str


def _truncate_msg(s: str) -> str:
    """Cap exception messages at 2000 chars + '...[truncated]' so HTTP
    error dumps don't bloat the resp-stats artifact."""
    if len(s) <= _FAILURE_MSG_CAP:
        return s
    return s[:_FAILURE_MSG_CAP] + "...[truncated]"


def _set_failure(
    state: dict,
    stage: FailureStage,
    exception_type: str,
    message: str,
) -> None:
    """Centralized failure-capture: builds the FailureTelemetry NamedTuple
    and stashes it in state['failure'] for the finally block to read."""
    state["failure"] = FailureTelemetry(
        stage=stage,
        exception_type=exception_type,
        message=_truncate_msg(message),
    )


def _build_source_summary(fm: "SourceFrontmatter") -> str:
    """D-89-19: Source.summary = Pass-1 summary + mechanical append of key_themes.

    Mechanical concat (not LLM-merge — D-89-18 retracted). Themes participate
    structurally in the graph via entity_search_keys → context_loader T2-rewrite
    (Task #90), upstream of Pass-2; Source.summary is purely descriptive.

    Empty summary or empty key_themes → verbatim Pass-1 summary (no append).
    Persisted to GraphDB Source.summary; also what Pass-2 sees in its prompt.
    """
    if not fm.key_themes or not fm.summary.strip():
        return fm.summary
    base = fm.summary.rstrip(". ")
    return base + ". Themes: " + ", ".join(fm.key_themes) + "."


def source_text_for(job: CompileJob) -> tuple[SourceFrontmatter | None, str]:
    """Thin wrapper around source_io.parse_source_file for backward-compat.

    Per D-89-17 + §10.5. Compile LLM receives only `body`; Source-node writer
    + entity extractor use `frontmatter` (Task D.2). Propagates OSError /
    UnicodeDecodeError so compile_one's scaffold-and-fill can classify failure.

    Migrated to kdb_compiler.source_io 2026-05-27 (Task #90 D-90-10) to break
    a circular-import cycle (Bug B-1, formerly in the deleted planner.py).

    Task #91: prefers the orchestrator's in-memory (source_text, frontmatter)
    when present — zero disk reads; else falls back to disk (legacy path).
    """
    if job.source_text is not None:
        return job.frontmatter, job.source_text
    return parse_source_file(Path(job.abs_path))


def compile_one(
    job: CompileJob,
    *,
    vault_root: Path,
    state_root: Path,
    ctx: RunContext,
    provider: str,
    model: str,
    max_tokens: int,
    use_completion_tokens: bool = False,
    extra_body: dict | None = None,
    resp_stats_dir: Path | None = None,
    stats_record_sink: Callable[["RespStatsRecord", Path], None] | None = None,
) -> tuple[CompiledSource | None, list[dict], list[str], str | None]:
    """Execute one per-source compile call. See blueprint §9.

    Returns (compiled_source | None, log_entries, warnings, error | None).
    Always writes exactly one RespStatsRecord in the finally block, regardless
    of which stage (if any) failed.

    Source-id-space split (Task #41): the LLM emits slug-space fields plus a
    path-free `source_name`; the runner constructs `source_id` from
    `job.source_id` and injects it into the persisted CompiledSource shape
    after parse. RespStatsRecord.parsed_json reflects the slim LLM-emitted
    payload (no source-id-space fields).
    """
    source_id = job.source_id
    # Task #91: derive from source_id, not abs_path — the in-memory orchestrator
    # path has abs_path="" (Path("").name == ""), which would fail the
    # validate_compiled_source_response source_name-echo check. Equal to
    # Path(abs_path).name for all legacy sources (same basename).
    source_name = Path(job.source_id).name

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
        "source_words": 0,
        "failure": None,
    }

    try:
        # --- read source ---
        try:
            fm, source_text = source_text_for(job)
        except (OSError, UnicodeDecodeError) as e:
            _set_failure(state, "source_read", type(e).__name__, str(e))
            state["error"] = (
                f"{source_id}: source read failed: {type(e).__name__}: {e}"
            )
            return (None, [], [], state["error"])
        state["source_words"] = len(source_text.split())

        # --- build prompt ---
        # Thread Pass-1 frontmatter through so the LLM can USE domain/source_type/
        # author directly (D-89-17). Source.summary is the Pass-1 verbatim summary
        # with key_themes mechanically appended (D-89-19); Pass-2 treats it as
        # authoritative (no merge ceremony). key_entities + key_themes are NOT
        # threaded to Pass-2 separately (D-89-20 — entity_search_keys is the
        # T2-rewrite channel; Pass-2 doesn't see those slugs at all).
        # kdb_signal excluded — signal already established by Pass-1.
        source_meta_dict: dict | None = None
        if fm is not None:
            source_meta_dict = {
                "domain": fm.domain,
                "source_type": fm.source_type,
                "author": fm.author,
                "summary": _build_source_summary(fm),  # D-89-19 mechanical append
            }
        try:
            state["prompt"] = prompt_builder.build_prompt(
                vault_root=vault_root,
                source_name=source_name,
                source_text=source_text,
                context_snapshot=job.context_snapshot,
                source_meta=source_meta_dict,
            )
        except Exception as e:
            _set_failure(state, "prompt_build", type(e).__name__, str(e))
            state["error"] = (
                f"{source_id}: prompt build failed: {type(e).__name__}: {e}"
            )
            return (None, [], [], state["error"])

        # --- model call + extract + parse + schema, with a retry on a
        # recoverable bad-JSON emission. Mirrors Pass-1's call_pass1 retry: the
        # model sometimes emits invalid JSON (e.g. unescaped LaTeX backslashes on
        # math-heavy sources, run-4 Finding 3); a re-call usually returns valid
        # JSON. Truncation and hard model-call errors are terminal (a re-call
        # won't help). SDK-transient retries already live in call_model_with_retry.
        for attempt in range(1, _MAX_COMPILE_ATTEMPTS + 1):
            last_attempt = attempt == _MAX_COMPILE_ATTEMPTS

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
                        use_completion_tokens=use_completion_tokens,
                        extra_body=extra_body,
                        # Constrain output to valid JSON, mirroring Pass-1
                        # (pass1_caller.py json_mode=True).
                        json_mode=True,
                    )
                )
                state["raw_response_text"] = state["model_response"].text
            except Exception as e:
                _set_failure(state, "model_call", type(e).__name__, str(e))
                state["error"] = (
                    f"{source_id}: model call failed: {type(e).__name__}: {e}"
                )
                return (None, [], [], state["error"])

            # --- truncation guard (terminal — a re-call won't fit a bigger output) ---
            # Anthropic: stop_reason == "max_tokens"; OpenAI-compat: "length".
            sr = state["model_response"].stop_reason
            if sr in ("max_tokens", "length"):
                _set_failure(
                    state,
                    "truncation",
                    "TokenOverrun",
                    f"stop_reason={sr!r}; max_tokens={max_tokens}",
                )
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
                if not last_attempt:
                    log.warning(
                        f"{source_id}: Pass-2 attempt {attempt}/"
                        f"{_MAX_COMPILE_ATTEMPTS} extract failed, retrying: {e}"
                    )
                    continue
                _set_failure(state, "extract", type(e).__name__, str(e))
                state["error"] = f"{source_id}: extract failed: {e}"
                return (None, [], [], state["error"])

            # --- parse ---
            try:
                state["parsed_json"] = json.loads(json_text)
                state["parse_ok"] = True
            except json.JSONDecodeError as e:
                if not last_attempt:
                    log.warning(
                        f"{source_id}: Pass-2 attempt {attempt}/"
                        f"{_MAX_COMPILE_ATTEMPTS} invalid JSON, retrying: "
                        f"{e.msg} at line {e.lineno}"
                    )
                    continue
                _set_failure(state, "parse", type(e).__name__, str(e))
                state["error"] = (
                    f"{source_id}: invalid JSON: {e.msg} at line {e.lineno}"
                )
                return (None, [], [], state["error"])

            # --- schema ---
            state["schema_errors"] = validate_source_response.validate(
                state["parsed_json"]
            )
            state["schema_ok"] = state["schema_errors"] == []
            if not state["schema_ok"]:
                if not last_attempt:
                    log.warning(
                        f"{source_id}: Pass-2 attempt {attempt}/"
                        f"{_MAX_COMPILE_ATTEMPTS} schema invalid, retrying: "
                        f"{state['schema_errors'][0]}"
                    )
                    continue
                state["error"] = (
                    f"{source_id}: schema validation failed: {state['schema_errors'][0]}"
                )
                return (None, [], [], state["error"])

            break  # extract_ok + parse_ok + schema_ok → proceed to semantic

        # --- semantic ---
        state["semantic_errors"] = (
            validate_source_response.semantic_check(
                state["parsed_json"], source_name=source_name
            )
        )
        state["semantic_ok"] = state["semantic_errors"] == []
        if not state["semantic_ok"]:
            state["error"] = (
                f"{source_id}: semantic check failed: {state['semantic_errors'][0]}"
            )
            return (None, [], [], state["error"])

        # --- body-link reconciliation ---
        reconcile_body_links(state["parsed_json"])

        # --- slug-list reconciliation (Task #65 / D45) ---
        # Rebuild concept_slugs/article_slugs from pages[].page_type so the
        # pairing-inconsistency class (commission/omission/type_mismatch)
        # cannot reach downstream validation. Pages-win, mirroring the
        # body-wins reconcile_body_links above.
        reconcile_slug_lists(state["parsed_json"])

        # --- success: enrich LLM payload with runner-injected source-id-space ---
        # Task #41: LLM emits slug-space + source_name only; runner injects
        # source_id (top-level), supports_page_existence (per page), and
        # related_source_ids (per log_entry) using job.source_id. Manifest
        # lookup for prior-support enrichment is the responsibility of
        # downstream stages (patch_applier) — here we just stamp the current
        # source_id on every page, matching the today-LLM-emitted behavior.
        parsed = state["parsed_json"]
        mr = state["model_response"]
        state["compiled_source"] = CompiledSource(
            source_id=source_id,
            summary_slug=parsed["summary_slug"],
            pages=[
                PageIntent(
                    slug=p["slug"],
                    page_type=p["page_type"],
                    title=p["title"],
                    body=p["body"],
                    status=p["status"],
                    outgoing_links=list(p.get("outgoing_links", [])),
                    confidence=p["confidence"],
                    supports_page_existence=[source_id],
                )
                for p in parsed["pages"]
            ],
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
            source_meta={
                "summary": _build_source_summary(fm),  # D-89-19 mechanical append
                "author": fm.author,
                "domain": fm.domain,
                "source_type": fm.source_type,
            } if fm is not None else None,
        )
        state["log_entries"] = [
            {**le, "related_source_ids": []}
            for le in parsed.get("log_entries", [])
        ]
        state["warnings"] = list(parsed.get("warnings", []))
        return (
            state["compiled_source"],
            state["log_entries"],
            state["warnings"],
            None,
        )

    finally:
        record = build_resp_stats(
            ctx=ctx,
            source_id=source_id,
            provider=provider,
            model=model,
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
            source_words=state["source_words"],
            failure=state["failure"],
        )
        resp_stats_path = write_resp_stats(
            record, state_root, artifact_dir=resp_stats_dir)
        if stats_record_sink is not None:
            try:
                stats_record_sink(record, resp_stats_path)
            except Exception:
                # Observational hook — must not break the compile.
                pass


def compile_source(
    source_id: str,
    body: str,
    frontmatter: SourceFrontmatter | None,
    conn,
    *,
    vault_root: Path,
    state_root: Path,
    ctx: RunContext,
    ledger: AliasLedger,
    provider: str,
    model: str,
    max_tokens: int,
    context_snapshot: ContextSnapshot | None = None,
    mode: T2Mode = T2Mode.STRUCTURED,
    resolver: str = "simple",
) -> CompileSourceResult:
    """Per-source Pass-2 PRODUCE core (spec stages 3->6) on in-memory inputs.

    Writes NOTHING. Returns the compiled `cr`; the orchestrator owns stage-8
    apply-pages, provenance, manifest commit, and graph-sync at the commit
    boundary (Task #91 produce-don't-write decision). All pre-commit failures
    return CompileSourceResult(cr=None, failure_stage=..., error=...) so the
    orchestrator routes case-(a) (D-91-13) uniformly without string-parsing.
    """
    vault_root = Path(vault_root)

    # 1. context snapshot — caller-supplied, or the only graph read
    if context_snapshot is None:
        try:
            context_snapshot = build_context_snapshot(
                conn, source_id=source_id, source_text=body,
                frontmatter=frontmatter, mode=mode, resolver=resolver,
            )
        except Exception as e:
            return CompileSourceResult(
                cr=None, failure_stage="context",
                exception_type=type(e).__name__, error=str(e))

    # 2. compile (stage 3) on an in-memory job — no disk read
    job = CompileJob(
        source_id=source_id, abs_path="",
        context_snapshot=context_snapshot, source_text=body, frontmatter=frontmatter,
    )
    captured: dict[str, Any] = {"record": None, "path": None}

    def _capture(record: RespStatsRecord, path: Path) -> None:
        captured["record"] = record
        captured["path"] = path

    cs, logs, warns, err = compile_one(
        job, vault_root=vault_root, state_root=state_root, ctx=ctx,
        provider=provider, model=model, max_tokens=max_tokens,
        resp_stats_dir=state_root / "runs" / ctx.run_id / "pass2",
        stats_record_sink=_capture,
    )
    if err is not None:
        artifacts = {}
        if captured["path"] is not None:
            artifacts["resp_stats"] = str(captured["path"])
            if getattr(captured["record"], "raw_response_text", None) is not None:
                artifacts["raw_response"] = str(captured["path"])
        return CompileSourceResult(
            cr=None, failure_stage="compile",
            exception_type=getattr(captured["record"], "failure_exception_type", None),
            error=err, artifacts=artifacts)

    cr: dict = {
        "run_id": ctx.run_id, "success": True,
        "compiled_sources": [cs.to_dict()],
        "log_entries": list(logs), "errors": [], "warnings": list(warns),
    }

    # 3. validate (stage 4) — gate
    vres = validate_compile_result.validate(cr)
    if vres.gate_errors:
        return CompileSourceResult(
            cr=None, failure_stage="validate",
            error="; ".join(f.detail for f in vres.gate_errors),
            artifacts=({"resp_stats": str(captured["path"])}
                       if captured["path"] is not None else {}))

    # 4. repair (stage 5) — mutates cr in place. Task #91 (m3): wrap so a
    # RepairError returns case-(a) failure instead of escaping the
    # CompileSourceResult contract (orchestrator routes it uniformly).
    try:
        repair.repair(cr, vres.measure_findings)
    except repair.RepairError as e:
        return CompileSourceResult(
            cr=None, failure_stage="reconcile",
            exception_type=type(e).__name__, error=str(e))

    # 5. canonicalize (stage 6) — mutates cr in place, emits canonical_meta
    try:
        canonicalize.run(cr, ledger, ctx.run_id)
    except canonicalize.CircularAliasError as e:
        return CompileSourceResult(
            cr=None, failure_stage="canonicalize",
            exception_type=type(e).__name__, error=str(e))

    return CompileSourceResult(cr=cr)


