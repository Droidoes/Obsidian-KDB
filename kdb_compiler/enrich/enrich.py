# kdb_compiler/enrich/enrich.py
"""Pass-1 enrichment orchestrator. One source → enriched + audit + journal entry."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from kdb_compiler.enrich.config_loader import load_scope_config
from kdb_compiler.enrich.pass1_caller import call_pass1, Pass1CallError
from kdb_compiler.enrich.pass1_prompt import PASS1_PROMPT_VERSION
from kdb_compiler.enrich.overrides import apply_overrides, build_override_block
from kdb_compiler.enrich.pass1_schema import validate_envelope, PASS1_SCHEMA_VERSION
from kdb_compiler.enrich.frontmatter_embedder import embed_frontmatter
from common.source_io import parse_existing_frontmatter
from kdb_compiler.enrich.replay_archive import write_sidecar, SidecarPayload


@dataclass
class EnrichResult:
    source_id: str
    outcome: str  # enriched | enriched_force_overridden | enrich_failed | enrich_skipped
    parsed_envelope: dict | None
    sidecar_path: Path | None
    error: str | None
    # Task #91 egress: the orchestrator reuses these in-memory instead of
    # re-reading/re-hashing the file. `body` is the frontmatter-stripped body
    # (what Pass-2 compiles). `post_embed_hash`/`post_embed_mtime` are the
    # WHOLE-FILE hash + mtime AFTER frontmatter was embedded — what the manifest
    # must store as the current hash so the next scan sees the source as
    # UNCHANGED (else the embed itself triggers a recompile every run).
    body: str | None = None
    post_embed_hash: str | None = None
    post_embed_mtime: float | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    raw_response_available: bool = False


def _whole_file_hash(source_path: Path) -> str:
    """sha256 of the on-disk bytes (matches kdb_scan's whole-file hashing)."""
    return "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()


def enrich_one(
    *, source_path: Path, source_id: str, runs_root: Path, run_id: str,
    provider: str, model: str,
    force_signal: list[str] | None = None,
    force_noise: list[str] | None = None,
) -> EnrichResult:
    # Task #91: the orchestrator threads the PIPELINE's force_signal/force_noise
    # globs (from pipelines.json) so per-pipeline routing (e.g. Daily Notes/* →
    # noise) takes effect; falling back to the global scope-config.yaml when a
    # caller (legacy / standalone enrich) supplies neither.
    scope = load_scope_config()
    eff_force_signal = scope.force_signal if force_signal is None else force_signal
    eff_force_noise = scope.force_noise if force_noise is None else force_noise

    raw_text = source_path.read_text(encoding="utf-8")
    existing_fm, body = parse_existing_frontmatter(raw_text)
    content_hash = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()

    # Empty source short-circuit per Task #89 §5.1
    if not body.strip():
        envelope = _empty_source_envelope(model)
        sidecar = _write_sidecar_skipped(
            runs_root, run_id, source_id, source_path, content_hash, envelope
        )
        # No embed for empty sources; the on-disk file is unchanged, so the
        # whole-file hash is well-defined and lets the noise/skip commit store a
        # stable last_compiled_hash (M2 — avoids re-enriching every run).
        return EnrichResult(source_id, "enrich_skipped", envelope, sidecar, None,
                            body=body, post_embed_hash=_whole_file_hash(source_path),
                            post_embed_mtime=source_path.stat().st_mtime)

    try:
        call_result = call_pass1(
            source_text=body, source_path=str(source_path),
            provider=provider, model=model,
        )
    except Pass1CallError as e:
        sidecar = _write_sidecar_failed(
            runs_root, run_id, source_id, source_path, content_hash, e, model, provider,
        )
        # Pre-embed failure: body is known but no embed happened, so post-embed
        # fields stay None (the orchestrator fail-fasts on enrich failure anyway).
        return EnrichResult(source_id, "enrich_failed", None, sidecar, str(e),
                            body=body,
                            artifacts={"pass1_sidecar": str(sidecar),
                                       "raw_response": str(sidecar)},
                            raw_response_available=bool(e.raw_response_text))

    envelope = apply_overrides(
        call_result.parsed, source_path=source_id,
        force_signal=eff_force_signal, force_noise=eff_force_noise,
    )
    # STAGE 2 (Task #95): validate the COMPLETE assembled envelope (content +
    # stamped code-owned fields + constructed override) before it is embedded.
    try:
        validate_envelope(envelope)
    except Exception as e:
        wrapped = Pass1CallError(
            f"Pass-1 assembled envelope failed validation: {e}",
            raw_response_text=call_result.raw_response_text,
            request_prompt=call_result.request_prompt,
            request_model=call_result.request_model,
            request_provider=call_result.request_provider,
            input_tokens=call_result.input_tokens,
            output_tokens=call_result.output_tokens,
            latency_ms=call_result.latency_ms,
            attempts=call_result.attempts,
        )
        sidecar = _write_sidecar_failed(
            runs_root, run_id, source_id, source_path,
            content_hash, wrapped, model, provider,
        )
        return EnrichResult(source_id, "enrich_failed", None, sidecar, str(wrapped),
                            body=body,
                            artifacts={"pass1_sidecar": str(sidecar),
                                       "raw_response": str(sidecar)},
                            raw_response_available=bool(call_result.raw_response_text))

    embed_frontmatter(source_path, envelope)
    # Whole-file hash + mtime AFTER embed — the orchestrator stamps these into
    # the manifest so the embed doesn't look like an edit on the next scan.
    post_embed_hash = _whole_file_hash(source_path)
    post_embed_mtime = source_path.stat().st_mtime

    outcome = ("enriched_force_overridden"
               if envelope["override"]["applied"] is not None
               else "enriched")
    sidecar_payload = SidecarPayload(
        source_id=source_id,
        source_path=str(source_path),
        source_content_hash=content_hash,
        request={"prompt": call_result.request_prompt,
                 "model": call_result.request_model,
                 "provider": call_result.request_provider},
        raw_response={"body": call_result.raw_response_text,
                      "input_tokens": call_result.input_tokens,
                      "output_tokens": call_result.output_tokens,
                      "latency_ms": call_result.latency_ms,
                      "attempts": call_result.attempts},
        parsed_envelope=envelope,
        override=envelope["override"],
        user_overrides_detected=[],  # OQ-89-9 / §3.3 user-collision; v1.1+ feature
        timestamp=_local_iso(),
        outcome=outcome,
    )
    sidecar = write_sidecar(runs_root, run_id, sidecar_payload)
    return EnrichResult(source_id, outcome, envelope, sidecar, None,
                        body=body, post_embed_hash=post_embed_hash,
                        post_embed_mtime=post_embed_mtime)


def _local_iso() -> str:
    """Local time with offset per [[feedback_local_time_everywhere]]."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _empty_source_envelope(model: str) -> dict:
    """Per Task #89 §5.1: empty source → kdb_signal=noise with reason."""
    return {
        "kdb_signal": "noise",
        "domain": "undecided", "source_type": "other", "author": None,
        "summary": "", "key_themes": [], "entity_search_keys": [],
        "confidence": 1.0, "uncertainty_reason": None,
        "reject_reason": "empty source",
        "prompt_version": PASS1_PROMPT_VERSION, "model": model,
        "schema_version": PASS1_SCHEMA_VERSION,
        "override": build_override_block("noise"),
        "other_reason": "empty source — no content to classify",
    }


def _write_sidecar_skipped(runs_root, run_id, source_id, source_path,
                            content_hash, envelope):
    payload = SidecarPayload(
        source_id=source_id, source_path=str(source_path),
        source_content_hash=content_hash,
        request={"prompt": "<skipped — empty source>", "model": envelope["model"]},
        raw_response={"body": "", "input_tokens": 0, "output_tokens": 0,
                      "latency_ms": 0, "attempts": 0},
        parsed_envelope=envelope,
        override=envelope["override"],
        user_overrides_detected=[],
        timestamp=_local_iso(),
        outcome="enrich_skipped",
    )
    return write_sidecar(runs_root, run_id, payload)


def _write_sidecar_failed(runs_root, run_id, source_id, source_path,
                           content_hash, error, model, provider):
    raw_response_text = getattr(error, "raw_response_text", "")
    request_prompt = getattr(error, "request_prompt", None) or "<unavailable>"
    request_model = getattr(error, "request_model", None) or model
    request_provider = getattr(error, "request_provider", None) or provider
    payload = SidecarPayload(
        source_id=source_id, source_path=str(source_path),
        source_content_hash=content_hash,
        request={"prompt": request_prompt, "model": request_model,
                 "provider": request_provider},
        raw_response={
            "body": raw_response_text,
            "error": str(error),
            "input_tokens": getattr(error, "input_tokens", 0),
            "output_tokens": getattr(error, "output_tokens", 0),
            "latency_ms": getattr(error, "latency_ms", 0),
            "attempts": getattr(error, "attempts", 0),
        },
        parsed_envelope=None,
        override=build_override_block("?"),
        user_overrides_detected=[],
        timestamp=_local_iso(),
        outcome="enrich_failed",
    )
    return write_sidecar(runs_root, run_id, payload)
