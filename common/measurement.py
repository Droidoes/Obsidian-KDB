"""
Measurement dataclasses for the KDB benchmark pipeline (B1 design).

These are *projections* over existing telemetry (Pass-2 RespStatsRecord,
Pass-1 sidecar) — not a new persistent store.  The KPI layer consumes
these structures to compute per-run scoring metrics.

`common` is a leaf package: only stdlib imports are allowed here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PassCallMeasurement:
    """Logical projection of one LLM pass-call's telemetry for KPI scoring."""

    run_id: str
    source_id: str
    pass_: str                  # "pass1" | "pass2" (trailing _ avoids keyword clash)
    provider: str
    model: str
    prompt_version: str
    final_status: str
    attempts: int
    syntax_repaired: bool
    slug_coerced: bool
    token_overrun: bool
    total_input_tokens: int
    total_output_tokens: int
    total_latency_ms: int
    call_count: int
    final_attempt_index: int
    source_words: int
    parse_ok: bool
    schema_ok: bool
    semantic_ok: bool | None
    boundary_recovered: bool = False

    @classmethod
    def from_pass1(cls, sidecar: dict, *, run_id: str) -> "PassCallMeasurement":
        """Project a Pass-1 sidecar dict into a PassCallMeasurement.

        Sidecar layout (from ingestion/enrich/replay_archive.py + enrich.py):
          sidecar["source_id"]        — vault-relative path
          sidecar["request"]["provider"]  — LLM provider (may be absent on skipped)
          sidecar["request"]["model"]     — LLM model name
          sidecar["raw_response"]["final_status"]          — "clean" | "repaired" | "quarantined" | ...
          sidecar["raw_response"]["syntax_repaired"]       — bool
          sidecar["raw_response"]["total_input_tokens"]    — int
          sidecar["raw_response"]["total_output_tokens"]   — int
          sidecar["raw_response"]["total_latency_ms"]      — int
          sidecar["raw_response"]["call_count"]            — int (0 for skipped)
          sidecar["raw_response"]["final_attempt_index"]   — int
          sidecar["parsed_envelope"]    — dict or None (None on failure/quarantine path)
          sidecar["parsed_envelope"]["prompt_version"]     — str (when envelope present)
          sidecar["parsed_envelope"]["model"]              — str (when envelope present)

        Design choices:
        - `attempts`: derived from `raw_response["call_count"]` — the ladder tracks
          attempts via call_count; there is no separate "attempts" key in the sidecar.
        - `parse_ok` / `schema_ok`: derived from final_status != "quarantined".  A
          non-quarantined Pass-1 by definition parsed and validated its envelope; a
          quarantined one failed at or before that gate.
        - `semantic_ok`: always None — Pass-1 has no semantic validation gate.
        - `slug_coerced`: always False — Pass-1 slug-coercion applies to Pass-2 only.
        - `token_overrun`: always False — not tracked in the Pass-1 sidecar.
        - `source_words`: always 0 — not stored in the sidecar (Pass-2-only diagnostic).
        - `model`: prefer `request["model"]` (present on all write paths including
          failures) over `parsed_envelope["model"]` (absent when envelope is None).
        - `prompt_version`: from `parsed_envelope["prompt_version"]` when the envelope
          is present; else "" (failure/quarantine paths have no envelope).
        """
        req = sidecar.get("request", {})
        raw = sidecar.get("raw_response", {})
        envelope = sidecar.get("parsed_envelope") or {}

        final_status = raw.get("final_status", "")
        not_quarantined = final_status != "quarantined"

        return cls(
            run_id=run_id,
            source_id=sidecar["source_id"],
            pass_="pass1",
            provider=req.get("provider", ""),
            model=req.get("model", ""),
            prompt_version=envelope.get("prompt_version", ""),
            final_status=final_status,
            # attempts: use call_count as the Pass-1 equivalent of SDK attempt count.
            # call_count is 0 for skipped sources, 1+ for real LLM calls.
            attempts=raw.get("call_count", 1),
            syntax_repaired=raw.get("syntax_repaired", False),
            slug_coerced=False,    # Pass-1 does not perform slug coercion
            token_overrun=False,   # not tracked in Pass-1 sidecar
            total_input_tokens=raw.get("total_input_tokens", 0),
            total_output_tokens=raw.get("total_output_tokens", 0),
            total_latency_ms=raw.get("total_latency_ms", 0),
            call_count=raw.get("call_count", 1),
            final_attempt_index=raw.get("final_attempt_index", 1),
            source_words=0,        # not stored in Pass-1 sidecar
            # parse_ok / schema_ok: a non-quarantined Pass-1 envelope passed both
            # parse and schema validation by definition; quarantined = failed.
            parse_ok=not_quarantined,
            schema_ok=not_quarantined,
            semantic_ok=None,      # Pass-1 has no semantic validation gate
            boundary_recovered=False,  # Pass-1 has no parse-stage boundary recovery
        )

    @classmethod
    def from_pass2(cls, rec: dict) -> "PassCallMeasurement":
        """Project a RespStatsRecord dict (from to_dict() or persisted JSON)
        into a PassCallMeasurement.

        RespStatsRecord has no prompt_version field; prompt_version is set to "".

        Back-compat: records persisted before Task #109 (missing total_input_tokens,
        total_output_tokens, total_latency_ms, call_count, final_attempt_index) fall
        back to the single-attempt per-call values so older runs still project cleanly.
        """
        return cls(
            run_id=rec["run_id"],
            source_id=rec["source_id"],
            pass_="pass2",
            provider=rec["provider"],
            model=rec["model"],
            # RespStatsRecord has no prompt_version; closest field is prompt_hash (a
            # hash, not a version string).  Emit "" so callers can fill in from
            # run-level metadata if needed.
            prompt_version="",
            final_status=rec.get("final_status") or "",
            # Fix 1 (#111 retry-telemetry): attempts reflects the compile
            # re-prompt count ONLY.  `final_attempt_index` captures every
            # content-driven re-prompt (schema/semantic retry, in-place
            # repair), so a re-prompt-only recovery (final_attempt_index==2)
            # is visible to the KPI layer.  SDK transient retries
            # (`rec["attempts"]` = model_response.attempts: 429/5xx/network
            # flakiness) are deliberately excluded — they are infrastructure
            # noise, not content/model recoveries, and the KPI layer keys
            # recovery_rate/retry_load off attempts > 1.  This matches
            # from_pass1's `call_count` and Fix 3a's compile_meta.attempts
            # (state["compile_attempts"]), which also exclude SDK retries.
            # Falls back to 1 for pre-#109 records.
            attempts=rec.get("final_attempt_index", 1),
            syntax_repaired=rec.get("syntax_repaired", False),
            slug_coerced=rec.get("slug_coerced", False),
            token_overrun=rec.get("token_overrun", False),
            # Aggregate totals — new in #109.  Fall back to single-attempt values
            # for records written before these fields existed.
            total_input_tokens=rec.get("total_input_tokens", rec.get("input_tokens", 0)),
            total_output_tokens=rec.get("total_output_tokens", rec.get("output_tokens", 0)),
            total_latency_ms=rec.get("total_latency_ms", rec.get("latency_ms", 0)),
            call_count=rec.get("call_count", 1),
            final_attempt_index=rec.get("final_attempt_index", 1),
            source_words=rec.get("source_words", 0),
            parse_ok=rec.get("parse_ok", False),
            schema_ok=rec.get("schema_ok", False),
            semantic_ok=rec.get("semantic_ok"),
            # #114 parse-stage boundary recovery; absent on pre-#114 records.
            boundary_recovered=rec.get("boundary_recovered", False),
        )


@dataclass(frozen=True)
class RunMeasurementHeader:
    """Per-run metadata projection consumed by the KPI scoring layer."""

    run_id: str
    corpus_fingerprint: str
    pass1_prompt_version: str
    pass2_prompt_version: str
    scanned: int
    to_compile: int
    signal: int
    noise: int
    p1_attempted: int
    p2_attempted: int
    release_version: str = ""


# ---------------------------------------------------------------------------
# Run-directory loader (B1 §3)
# ---------------------------------------------------------------------------

def load_run_measurements(
    run_dir: Path,
) -> tuple["RunMeasurementHeader", list["PassCallMeasurement"]]:
    """Load all measurement projections for one run.

    Actual on-disk layout (verified from orchestrator + compiler source):
      <run_dir>/measurement_header.json        — RunMeasurementHeader JSON
      <run_dir>/pass1/*.json                   — Pass-1 sidecars
      <run_dir>/pass2/*.json                   — Pass-2 RespStatsRecord JSONs

    Pass-1 sidecar identification: a file in <run_dir>/pass1/ is a sidecar iff
    it contains both "source_id" and "raw_response" keys.  This positively
    identifies sidecars and naturally excludes any future administrative files
    that might land in pass1/.

    Skip predicate: sidecars with outcome == "enrich_skipped" are excluded.
    These represent empty sources where no LLM call was made (call_count=0)
    and there is nothing to measure.  Quarantined / failed sidecars ARE
    included — they are the benchmark's primary failure-mode signal.

    Returns (header, measurements) where measurements is pass1_list +
    pass2_list (order is deterministic within each group via sorted glob).
    """
    header_path = run_dir / "measurement_header.json"
    header_data = json.loads(header_path.read_text(encoding="utf-8"))
    header = RunMeasurementHeader(**header_data)
    run_id = header.run_id

    # Pass-1: sidecars under pass1/ sub-directory.
    pass1: list[PassCallMeasurement] = []
    pass1_dir = run_dir / "pass1"
    if pass1_dir.is_dir():
        for p in sorted(pass1_dir.glob("*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            # Positive sidecar identification: must have source_id + raw_response.
            if "source_id" not in data or "raw_response" not in data:
                continue
            # Skip empty-source records — no LLM call was made.
            if data.get("outcome") == "enrich_skipped":
                continue
            pass1.append(PassCallMeasurement.from_pass1(data, run_id=run_id))

    # Pass-2: RespStatsRecord JSONs under pass2/ sub-directory.
    pass2: list[PassCallMeasurement] = []
    pass2_dir = run_dir / "pass2"
    if pass2_dir.is_dir():
        for p in sorted(pass2_dir.glob("*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            pass2.append(PassCallMeasurement.from_pass2(data))

    return header, pass1 + pass2
