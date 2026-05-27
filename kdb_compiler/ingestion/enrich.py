# kdb_compiler/ingestion/enrich.py
"""Pass-1 enrichment orchestrator. One source → enriched + audit + journal entry."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kdb_compiler.ingestion.config_loader import load_scope_config
from kdb_compiler.ingestion.pass1_caller import call_pass1, Pass1CallError
from kdb_compiler.ingestion.overrides import apply_overrides
from kdb_compiler.ingestion.frontmatter_embedder import (
    embed_frontmatter, parse_existing_frontmatter,
)
from kdb_compiler.ingestion.replay_archive import write_sidecar, SidecarPayload


@dataclass
class EnrichResult:
    source_id: str
    outcome: str  # enriched | enriched_force_overridden | enrich_failed | enrich_skipped
    parsed_envelope: dict | None
    sidecar_path: Path | None
    error: str | None


def enrich_one(
    *, source_path: Path, source_id: str, runs_root: Path, run_id: str,
    provider: str, model: str,
) -> EnrichResult:
    scope = load_scope_config()

    raw_text = source_path.read_text(encoding="utf-8")
    existing_fm, body = parse_existing_frontmatter(raw_text)
    content_hash = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()

    # Empty source short-circuit per Task #89 §5.1
    if not body.strip():
        envelope = _empty_source_envelope(model)
        sidecar = _write_sidecar_skipped(
            runs_root, run_id, source_id, source_path, content_hash, envelope
        )
        return EnrichResult(source_id, "enrich_skipped", envelope, sidecar, None)

    try:
        call_result = call_pass1(
            source_text=body, source_path=str(source_path),
            provider=provider, model=model,
        )
    except Pass1CallError as e:
        sidecar = _write_sidecar_failed(
            runs_root, run_id, source_id, source_path, content_hash, str(e), model,
        )
        return EnrichResult(source_id, "enrich_failed", None, sidecar, str(e))

    envelope = apply_overrides(
        call_result.parsed, source_path=source_id,
        force_signal=scope.force_signal, force_noise=scope.force_noise,
    )

    embed_frontmatter(source_path, envelope)

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
    return EnrichResult(source_id, outcome, envelope, sidecar, None)


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
        "prompt_version": "1.0.0", "model": model, "schema_version": 1,
        "override": {"applied": None, "rule": None, "match": None,
                     "llm_original": "noise", "reject_reason_cleared": None},
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
                           content_hash, error_msg, model):
    payload = SidecarPayload(
        source_id=source_id, source_path=str(source_path),
        source_content_hash=content_hash,
        request={"prompt": "<see error>", "model": model},
        raw_response={"body": "", "error": error_msg},
        parsed_envelope=None,
        override={"applied": None, "rule": None, "match": None,
                  "llm_original": "?", "reject_reason_cleared": None},
        user_overrides_detected=[],
        timestamp=_local_iso(),
        outcome="enrich_failed",
    )
    return write_sidecar(runs_root, run_id, payload)
