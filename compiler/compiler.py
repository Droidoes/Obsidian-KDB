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
monkeypatch `compiler.compiler.call_model_with_retry` as a clean
seam without touching `call_model_retry` itself.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Literal, NamedTuple

from compiler import (
    canonicalize,
    prompt_builder,
    repair,
    validate_compile_result,
    validate_source_response,
)
from common.source_io import SourceFrontmatter, parse_source_file
from common.call_model import ModelRequest
from common.call_model_retry import call_model_with_retry
from common.model_pool import estimate_prompt_tokens, fits_context
from compiler.canonicalize import AliasLedger
from compiler.context_loader import T2Mode, build_context_snapshot
from compiler.repair import coerce_slugs_and_propagate, reconcile_body_links, reconcile_slug_lists
from common.llm_telemetry import build_resp_stats, write_resp_stats
from compiler.resp_summary import build_parsed_summary
from compiler.response_recovery import recover_json_response
from common.run_context import RunContext
from common.types import (
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

    Migrated to common.source_io 2026-05-27 (Task #90 D-90-10) to break
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
    temperature: float | None = 0.0,
    price_in: float = 0.0,
    price_out: float = 0.0,
    ctx_window: int | None = None,
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
        # repair-ladder telemetry (#106)
        "compile_attempts": None,
        "syntax_repaired": False,
        "slug_coerced": False,
        # recovery telemetry (#114) — winning-attempt values
        "boundary_recovered": False,
        "prefix_discarded_chars": 0,
        "tail_discarded_chars": 0,
        # discarded-attempt aggregation (#109 Task 2)
        "_agg_input_tokens": 0,
        "_agg_output_tokens": 0,
        "_agg_latency_ms": 0,
        "_call_count": 0,
        "_final_attempt_index": 0,   # 0 = no winning attempt yet (quarantine path)
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

        # --- Task #110 §3.3: PROACTIVE input-side ctx-overrun guard ---
        # Estimate prompt tokens BEFORE any API call; if input + reserved output
        # (max_tokens) would exceed the model's ctx_window, skip-and-quarantine
        # THIS source with NO API spend. Routes through the EXISTING failure-
        # staging path (the same "truncation"/"TokenOverrun" vocabulary the
        # OUTPUT-side truncation guard below uses, ~line 353) → the finally block
        # records one RespStatsRecord; no model call → zeroed token counters →
        # no spend. The message is differentiated (ctx_window, no stop_reason) so
        # telemetry can tell input- from output-side overruns apart. ctx_window
        # is None for the ad-hoc --provider escape hatch (no pool metadata) ⇒
        # guard skipped, mirroring Pass-1 §3.2 (pass1_caller.py).
        if ctx_window is not None:
            est_in = estimate_prompt_tokens(
                state["prompt"].system, state["prompt"].user
            )
            if not fits_context(
                est_input=est_in,
                requested_output=max_tokens,
                ctx_window=ctx_window,
            ):
                _set_failure(
                    state,
                    "truncation",
                    "TokenOverrun",
                    f"Pass-2 prompt would overrun ctx_window: "
                    f"est_input={est_in} + reserved_output={max_tokens} "
                    f"> ctx_window={ctx_window}",
                )
                state["error"] = (
                    f"{source_id}: prompt would overrun ctx_window={ctx_window} "
                    f"(est_input={est_in} + reserved_output={max_tokens}); "
                    f"shorten source or raise ctx_window"
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

            # --- per-attempt state reset (LB2 #106) ---
            # Clear gate fields so a later attempt cannot read stale values from
            # a prior attempt's partial success (e.g. parse_ok=True but schema
            # failed on the same run).
            state["extract_ok"] = False
            state["parse_ok"] = False
            state["parsed_json"] = None
            state["schema_ok"] = False
            state["schema_errors"] = []
            state["semantic_ok"] = False
            state["semantic_errors"] = []
            state["syntax_repaired"] = False
            state["slug_coerced"] = False
            state["boundary_recovered"] = False
            state["prefix_discarded_chars"] = 0
            state["tail_discarded_chars"] = 0

            # --- model call ---
            try:
                state["model_response"] = call_model_with_retry(
                    ModelRequest(
                        provider=provider,
                        model=model,
                        system=state["prompt"].system,
                        prompt=state["prompt"].user,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        use_completion_tokens=use_completion_tokens,
                        extra_body=extra_body,
                        # Constrain output to valid JSON, mirroring Pass-1
                        # (pass1_caller.py json_mode=True).
                        json_mode=True,
                    )
                )
                state["raw_response_text"] = state["model_response"].text
                # Accumulate per-attempt stats (#109 Task 2): capture AFTER a
                # successful model call so a model-call exception doesn't inflate
                # the counters. The accumulator runs each attempt that reached
                # the model, whether or not the response passes later stages.
                mr = state["model_response"]
                state["_agg_input_tokens"] += mr.input_tokens
                state["_agg_output_tokens"] += mr.output_tokens
                state["_agg_latency_ms"] += mr.latency_ms
                state["_call_count"] += 1
            except Exception as e:
                _set_failure(state, "model_call", type(e).__name__, str(e))
                state["error"] = (
                    f"{source_id}: model call failed: {type(e).__name__}: {e}"
                )
                return (None, [], [], state["error"])

            # --- recovery (#114): unwrap + strict-eval + 5-step ladder ---
            result = recover_json_response(state["raw_response_text"])
            state["extract_ok"] = result.extract_ok
            if not result.recovered:
                # truncation guard — terminal only AFTER recovery fails
                # (a truncated-flagged response may still carry a complete
                # document; stop_reason is carrier metadata, not proof of
                # absence). A re-call won't fit a bigger output → no retry.
                sr = state["model_response"].stop_reason
                if sr in ("max_tokens", "length"):
                    _set_failure(
                        state, "truncation", "TokenOverrun",
                        f"stop_reason={sr!r}; max_tokens={max_tokens}",
                    )
                    state["error"] = (
                        f"{source_id}: truncated at max_tokens={max_tokens} "
                        f"(stop_reason={sr!r}); raise --max-tokens or shorten source"
                    )
                    return (None, [], [], state["error"])
                if not last_attempt:
                    log.warning(
                        f"{source_id}: Pass-2 attempt {attempt}/"
                        f"{_MAX_COMPILE_ATTEMPTS} unrecoverable JSON, retrying: "
                        f"{result.error}"
                    )
                    continue
                _set_failure(state, "parse", "JSONDecodeError",
                             result.error or "unrecoverable")
                state["error"] = f"{source_id}: invalid JSON: {result.error}"
                return (None, [], [], state["error"])

            state["parsed_json"] = result.parsed
            state["parse_ok"] = True
            state["syntax_repaired"] = result.syntax_repaired
            state["boundary_recovered"] = result.boundary_recovered
            state["prefix_discarded_chars"] = result.prefix_discarded_chars
            state["tail_discarded_chars"] = result.tail_discarded_chars

            # --- schema (+ rung-2: slug coercion on failure, #106) ---
            state["schema_errors"] = validate_source_response.validate(
                state["parsed_json"]
            )
            state["schema_ok"] = state["schema_errors"] == []
            if not state["schema_ok"]:
                # Coercion guarded (#114): non-dict payloads (list / scalar /
                # JSON null recovered by the ladder) skip coercion — the
                # schema gate alone arbitrates them, no AttributeError.
                if isinstance(state["parsed_json"], dict) and \
                        coerce_slugs_and_propagate(state["parsed_json"]):
                    state["schema_errors"] = validate_source_response.validate(
                        state["parsed_json"]
                    )
                    state["schema_ok"] = state["schema_errors"] == []
                    if state["schema_ok"]:
                        state["slug_coerced"] = True
                        log.info(
                            f"{source_id}: Pass-2 attempt {attempt} "
                            f"slug-coerced, proceeding"
                        )
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

            # --- semantic (now INSIDE the loop; LB2 #106) ---
            # Semantic runs after schema passes so a coercible schema failure
            # (rung-2, Task 6) that fixes the payload can still be re-checked
            # semantically on the same attempt.  A semantic failure on a
            # non-final attempt retries the full model call before erroring.
            state["semantic_errors"] = validate_source_response.semantic_check(
                state["parsed_json"], source_name=source_name
            )
            state["semantic_ok"] = state["semantic_errors"] == []
            if not state["semantic_ok"]:
                if not last_attempt:
                    log.warning(
                        f"{source_id}: Pass-2 attempt {attempt}/"
                        f"{_MAX_COMPILE_ATTEMPTS} semantic invalid, retrying: "
                        f"{state['semantic_errors'][0]}"
                    )
                    continue
                state["error"] = (
                    f"{source_id}: semantic check failed: {state['semantic_errors'][0]}"
                )
                return (None, [], [], state["error"])

            state["compile_attempts"] = attempt  # record winning attempt (#106)
            state["_final_attempt_index"] = attempt  # record winning index (#109)
            break  # parse_ok + schema_ok + semantic_ok → proceed

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
                # Fix 3a (#111 retry-telemetry): use the compile re-prompt count
                # (state["compile_attempts"]) not the model-API transient-retry
                # counter (mr.attempts).  compile_attempts is already set at the
                # break point above (line 459) before we reach here, so it is
                # always the winning attempt index (1 on a clean first pass, 2 on
                # a re-prompt recovery).  This makes compile_meta.attempts
                # meaningful for the orchestrator recorder (Fix 3b).
                attempts=state["compile_attempts"],
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
        parsed_summary = (
            build_parsed_summary(state["parsed_json"])
            if (state["parse_ok"] and isinstance(state["parsed_json"], dict))
            else None
        )
        # Derive final_status for repair-ladder telemetry (#106).
        _syntax_repaired = state["syntax_repaired"]
        _slug_coerced = state["slug_coerced"]
        _boundary_recovered = state["boundary_recovered"]
        _compile_attempts = state["compile_attempts"]
        if state["error"] is not None:
            _final_status = "quarantined"
        elif _syntax_repaired or _slug_coerced or _boundary_recovered:
            _final_status = (
                "retried-and-repaired" if _compile_attempts == 2 else "repaired"
            )
        elif _compile_attempts > 1:
            # Fix 2 (#111 retry-telemetry): re-prompt-only recovery (schema or
            # semantic rejection on attempt 1, no in-place repair applied,
            # attempt 2 succeeded cleanly).  Was silently labelled "clean"
            # before this fix — invisible to recovery_rate / retry_load KPIs.
            _final_status = "retried"
        else:
            _final_status = "clean"
        # Discarded-attempt aggregation (#109 Task 2): resolve final_attempt_index.
        # On the winning path _final_attempt_index was set inside the loop;
        # on the quarantine path it stays 0 — use _call_count as a proxy
        # (last attempt index that reached the model).
        # On a pre-loop failure (source_read/prompt_build), _call_count=0 and
        # we fall back to 1 so the field is never 0 on the persisted record.
        _call_count = state["_call_count"]
        _raw_final = state["_final_attempt_index"]
        _final_attempt_index = _raw_final if _raw_final > 0 else max(_call_count, 1)
        # Pass explicit aggregated totals only when at least one model call was made.
        # build_resp_stats falls back to per-call values from model_response when
        # total_* is None, preserving the zeroed sentinel path (pre-model failures).
        _has_calls = _call_count > 0
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
            parsed_summary=parsed_summary,
            source_words=state["source_words"],
            failure=state["failure"],
            compile_attempts=_compile_attempts,
            syntax_repaired=_syntax_repaired,
            slug_coerced=_slug_coerced,
            boundary_recovered=_boundary_recovered,
            prefix_discarded_chars=state["prefix_discarded_chars"],
            tail_discarded_chars=state["tail_discarded_chars"],
            final_status=_final_status,
            total_input_tokens=state["_agg_input_tokens"] if _has_calls else None,
            total_output_tokens=state["_agg_output_tokens"] if _has_calls else None,
            total_latency_ms=state["_agg_latency_ms"] if _has_calls else None,
            call_count=_call_count if _has_calls else 1,
            final_attempt_index=_final_attempt_index,
            price_in=price_in,
            price_out=price_out,
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
    price_in: float = 0.0,
    price_out: float = 0.0,
    ctx_window: int | None = None,
    use_completion_tokens: bool = False,
    extra_body: dict | None = None,
    temperature: float | None = 0.0,
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
        price_in=price_in, price_out=price_out, ctx_window=ctx_window,
        use_completion_tokens=use_completion_tokens, extra_body=extra_body,
        temperature=temperature,
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
            cr=None, failure_stage="repair",
            exception_type=type(e).__name__, error=str(e))

    # 5. canonicalize (stage 6) — mutates cr in place, emits canonical_meta
    try:
        canonicalize.run(cr, ledger, ctx.run_id)
    except canonicalize.CircularAliasError as e:
        return CompileSourceResult(
            cr=None, failure_stage="canonicalize",
            exception_type=type(e).__name__, error=str(e))

    return CompileSourceResult(cr=cr)


