"""kdb_benchmark.scorer — Phase 3 spec implementation.

Implements docs/task19-kpi-design.md § Phase 3 — Detailed Spec § 5–§ 9:
  * MeasureScore + RunScore dataclasses
  * Per-measure functions (S0/S1/S2/S3, M1–M7, 3 diagnostics)
  * Average-rank Borda normalization for M6/M7
  * Final-score formula with pro-rata redistribution
  * score_run() + score_runs() + borda_normalize()

Boundary contract (Task #18 / 5825d0f): imports from kdb_compiler are read-only;
this module is never imported by kdb_compiler.

Input contract (§2): consumes dict-shaped RespStatsRecord JSON files written
by compile_one's `finally` block under <state_root>/llm_resp/<run_id>/. Capture-
full mode required (§3) — the scorer raises if parse_ok=True records have
parsed_json=None.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

from kdb_benchmark.paths import MODELS_JSON
from kdb_benchmark.registry import ModelEntry, load_registry
from kdb_compiler.call_model_retry import MAX_RETRIES
from kdb_compiler.validate_compile_result import (
    check_compiled_source,
    check_compiled_source_findings,
)
from kdb_compiler.validate_compiled_source_response import body_wikilink_slugs


# ---------------------------------------------------------------------------
# §5 — Dataclass shapes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MeasureScore:
    """One measure's contribution to a model's run score.

    `rate` always carries the RAW measurement (set ratios in [0,1] for
    S0/S1/S2/S3/M1–M5; raw $/ms-per-1K-words for M6/M7). Borda-normalized
    [0,1] forms for M6/M7 live separately on RunScore.{m6_borda,m7_borda}.
    """
    name: str
    numerator: float
    denominator: float
    rate: Optional[float]
    weight: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "rate": self.rate,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MeasureScore":
        """Reverse of to_dict — used when reconstructing a RunScore from a
        prior scorecard JSON for cross-run merge (Task #42)."""
        return cls(
            name=d["name"],
            numerator=d["numerator"],
            denominator=d["denominator"],
            rate=d["rate"],
            weight=d["weight"],
        )


@dataclass(frozen=True)
class RunScore:
    """Per-(model_id, run_id) full scorecard. Single-model view; M6/M7
    rates inside `measures` are RAW ($/1K source-words, ms/1K source-words);
    Borda-normalized [0,1] versions live in `m6_borda` / `m7_borda` and
    are populated by score_runs() across the candidate set.

    D31 (Task #62): `final_score_pre_penalty` is the weighted sum before the
    outlier penalty is applied; `penalty` is the total deduction (units × 0.05);
    `final_score` is the post-penalty value (the canonical rank-by field).
    """
    run_id: str
    model_id: str
    provider: str
    model: str
    n_attempted: int
    s0: MeasureScore
    s1: MeasureScore
    s2: MeasureScore
    s3: MeasureScore
    measures: dict[str, MeasureScore]      # keys: M1..M7; M6/M7 rates RAW
    diagnostics: dict[str, MeasureScore]   # retry_load, token_overrun_rate, pages_per_1k_source_words
    m6_borda: Optional[float]
    m7_borda: Optional[float]
    final_score_pre_penalty: Optional[float]   # D31: weighted sum, pre-penalty
    penalty: float                             # D31: total deduction (units × 0.05); 0.0 if none
    final_score: Optional[float]               # post-penalty; the canonical rank-by value

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "model_id": self.model_id,
            "provider": self.provider,
            "model": self.model,
            "n_attempted": self.n_attempted,
            "s0": self.s0.to_dict(),
            "s1": self.s1.to_dict(),
            "s2": self.s2.to_dict(),
            "s3": self.s3.to_dict(),
            "measures": {k: v.to_dict() for k, v in self.measures.items()},
            "diagnostics": {k: v.to_dict() for k, v in self.diagnostics.items()},
            "m6_borda": self.m6_borda,
            "m7_borda": self.m7_borda,
            "final_score_pre_penalty": self.final_score_pre_penalty,
            "penalty": self.penalty,
            "final_score": self.final_score,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RunScore":
        """Reverse of to_dict — reconstructs a RunScore from a prior
        scorecard JSON entry. Tolerates extra keys (e.g. `ran_at`,
        `source_scorecard_id` that the scorecard layer adds for archival)
        by reading only the fields RunScore owns. Used by the merge step
        (Task #42).

        Backwards-compat: pre-D31 JSONs lack final_score_pre_penalty and
        penalty; defaults to None / 0.0 respectively (D29.9 doctrine —
        cross-generation FINAL comparison is already invalidated)."""
        return cls(
            run_id=d["run_id"],
            model_id=d["model_id"],
            provider=d["provider"],
            model=d["model"],
            n_attempted=d["n_attempted"],
            s0=MeasureScore.from_dict(d["s0"]),
            s1=MeasureScore.from_dict(d["s1"]),
            s2=MeasureScore.from_dict(d["s2"]),
            s3=MeasureScore.from_dict(d["s3"]),
            measures={k: MeasureScore.from_dict(v) for k, v in d["measures"].items()},
            diagnostics={k: MeasureScore.from_dict(v) for k, v in d["diagnostics"].items()},
            m6_borda=d.get("m6_borda"),
            m7_borda=d.get("m7_borda"),
            final_score_pre_penalty=d.get("final_score_pre_penalty"),
            penalty=d.get("penalty", 0.0),
            final_score=d.get("final_score"),
        )


# ---------------------------------------------------------------------------
# §6 — Per-measure functions
# ---------------------------------------------------------------------------

def _is_parse_pass(r: dict) -> bool:
    """R_p membership: parse_ok ∧ isinstance(parsed_json, dict). Round 4 MF4."""
    return bool(r.get("parse_ok")) and isinstance(r.get("parsed_json"), dict)


def s0(records: list[dict]) -> MeasureScore:
    """S0 — pipeline_success_rate (weight 20%).

    Per § 6: numerator = sources where parse_ok ∧ schema_ok ∧
    isinstance(parsed_json, dict) ∧ no_hard_zero(parsed_json).
    Denominator = |R|. Rate = num/denom (None iff |R| == 0).
    """
    n_pass = 0
    for r in records:
        if not (r.get("parse_ok") and r.get("schema_ok")):
            continue
        parsed = r.get("parsed_json")
        if not isinstance(parsed, dict):
            continue                              # § 4 MF4 — non-dict guard
        if check_compiled_source(parsed) != []:
            continue                              # hard-zero finding present
        n_pass += 1
    n_total = len(records)
    rate = (n_pass / n_total) if n_total else None
    return MeasureScore(
        name="S0",
        numerator=n_pass,
        denominator=n_total,
        rate=rate,
        weight=0.20,
    )


def s1(records: list[dict]) -> MeasureScore:
    """S1 — llm_resp_success_rate (diagnostic, weight 0). |R_p| / |R|."""
    n_total = len(records)
    n_parse = sum(1 for r in records if _is_parse_pass(r))
    rate = (n_parse / n_total) if n_total else None
    return MeasureScore(name="S1", numerator=n_parse, denominator=n_total, rate=rate, weight=0.0)


def s2(records: list[dict]) -> MeasureScore:
    """S2 — validator_schema_pass_rate (diagnostic, weight 0; conditional on S1).

    |{r ∈ R_p : r.schema_ok}| / |R_p|. None if |R_p| == 0.
    """
    parse_pass = [r for r in records if _is_parse_pass(r)]
    n_schema = sum(1 for r in parse_pass if r.get("schema_ok"))
    n_parse = len(parse_pass)
    rate = (n_schema / n_parse) if n_parse else None
    return MeasureScore(name="S2", numerator=n_schema, denominator=n_parse, rate=rate, weight=0.0)


def _iter_pages(parsed_json: dict) -> list[dict]:
    """Defensive: return only dict pages from parsed_json["pages"]; empty if
    the field is missing or wrong-shape. Round 4 MF4 / CW2 protection."""
    pages = parsed_json.get("pages")
    if not isinstance(pages, list):
        return []
    return [p for p in pages if isinstance(p, dict)]


def m1(records: list[dict]) -> MeasureScore:
    """M1 — link_target_resolution (weight 20%, Quality Core).

    Per § 6: target_set = union of slugs from all R_ps records;
    for each r in R_p, count outgoing_links values that hit target_set
    (LIST semantics — duplicates count separately, Round 4 CW3).
    Zero-denominator → 0.0 (model-controlled, Round 4 MF6).
    """
    target_set: set[str] = set()
    for r in records:
        if not (_is_parse_pass(r) and r.get("schema_ok")):
            continue
        for p in _iter_pages(r["parsed_json"]):
            slug = p.get("slug")
            if isinstance(slug, str):
                target_set.add(slug)

    numerator = 0
    denominator = 0
    for r in records:
        if not _is_parse_pass(r):
            continue
        for p in _iter_pages(r["parsed_json"]):
            links = p.get("outgoing_links")
            if not isinstance(links, list):
                continue
            for link in links:
                if not isinstance(link, str):
                    continue
                denominator += 1
                if link in target_set:
                    numerator += 1

    rate = (numerator / denominator) if denominator else 0.0
    return MeasureScore(name="M1", numerator=numerator, denominator=denominator, rate=rate, weight=0.20)


def _slug_jaccard(records: list[dict], slug_field: str, page_type: str) -> tuple[int, int]:
    """Per-source Jaccard sums for M2/M3. Returns (Σ |D ∩ E|, Σ |D ∪ E|).

    `slug_field` is "concept_slugs" or "article_slugs"; `page_type` is the
    matching page_type. Round 4 CW2: non-list slug fields are coerced to
    empty (`set("foo")` would otherwise produce char-slugs). Non-string
    members are dropped.
    """
    intersection_total = 0
    union_total = 0
    for r in records:
        if not _is_parse_pass(r):
            continue
        pj = r["parsed_json"]

        raw_slugs = pj.get(slug_field)
        if isinstance(raw_slugs, list):
            d = {s for s in raw_slugs if isinstance(s, str)}
        else:
            d = set()

        e: set[str] = set()
        for p in _iter_pages(pj):
            if p.get("page_type") == page_type and isinstance(p.get("slug"), str):
                e.add(p["slug"])

        intersection_total += len(d & e)
        union_total       += len(d | e)
    return intersection_total, union_total


def m2(records: list[dict]) -> MeasureScore:
    """M2 — concept_slugs_coverage Jaccard (weight 5%, Quality Core).

    Per § 6: per-source |D ∩ E| / |D ∪ E| with D = declared concept_slugs,
    E = emitted concept-typed page slugs. Micro-aggregated. Round 4 MF6:
    zero-denominator → 0.0 (model-controlled).
    """
    num, denom = _slug_jaccard(records, "concept_slugs", "concept")
    rate = (num / denom) if denom else 0.0
    return MeasureScore(name="M2", numerator=num, denominator=denom, rate=rate, weight=0.05)


def m3(records: list[dict]) -> MeasureScore:
    """M3 — article_slugs_coverage Jaccard (weight 5%, Quality Core).
    Identical to M2 with concept→article."""
    num, denom = _slug_jaccard(records, "article_slugs", "article")
    rate = (num / denom) if denom else 0.0
    return MeasureScore(name="M3", numerator=num, denominator=denom, rate=rate, weight=0.05)


def s3(records: list[dict]) -> MeasureScore:
    """S3 — validator_hard_zero_pass_rate (diagnostic, weight 0; conditional on S1).

    |{r ∈ R_p : check_compiled_source(parsed_json) == []}| / |R_p|.
    """
    parse_pass = [r for r in records if _is_parse_pass(r)]
    n_clean = sum(1 for r in parse_pass if check_compiled_source(r["parsed_json"]) == [])
    n_parse = len(parse_pass)
    rate = (n_clean / n_parse) if n_parse else None
    return MeasureScore(name="S3", numerator=n_clean, denominator=n_parse, rate=rate, weight=0.0)


def _emit_set_components(parsed_json: dict) -> tuple[set[str], set[str]]:
    """Per-source `(declared_emit_set, body_emit_links)` for M5
    computations.

      declared_emit_set = set(concept_slugs) ∪ set(article_slugs)
      body_emit_links   = ⋃_p (body_wikilink_slugs(p.body) − {p.slug})

    Self-links excluded per page (Task #59 D29.7 + Codex review). The
    body_emit_links set is the union across pages with each page's own
    slug subtracted from its body-wikilink contribution before the union.

    Tolerant — never raises (per Task #59 §10.2 conventions):
      * concept_slugs / article_slugs non-list → empty set
      * non-string slug members → dropped
      * pages non-list → no body links contribute
      * non-string body → page contributes zero links
      * non-string page slug → no self-link subtraction for that page
    """
    def _slugs(field) -> set[str]:
        if not isinstance(field, list):
            return set()
        return {s for s in field if isinstance(s, str)}

    declared = _slugs(parsed_json.get("concept_slugs")) | _slugs(parsed_json.get("article_slugs"))

    body_emit_links: set[str] = set()
    pages = parsed_json.get("pages")
    if not isinstance(pages, list):
        return (declared, body_emit_links)

    for p in pages:
        if not isinstance(p, dict):
            continue
        body = p.get("body")
        if not isinstance(body, str):
            continue
        page_slug = p.get("slug")
        page_links = body_wikilink_slugs(body)
        if isinstance(page_slug, str):
            page_links = page_links - {page_slug}
        body_emit_links |= page_links

    return (declared, body_emit_links)


def _compute_body_emit_set_coverage(parsed_json: dict) -> tuple[int, int]:
    """Per-source `(numerator, denominator)` for M5 body_emit_set_coverage.

    numerator   = |⋃_p (body_wikilink_slugs(p.body) − {p.slug})| ∩ declared_emit_set
    denominator = |declared_emit_set|

    where declared_emit_set = set(concept_slugs) ∪ set(article_slugs).

    Self-links excluded per page (Codex 2026-05-10 review): a page that
    references its own slug isn't "integrating" the concept — it's a
    tautology. Subtraction rewards cross-page integration only.

    Set extraction delegated to `_emit_set_components`.
    """
    declared, body_emit_links = _emit_set_components(parsed_json)
    return (len(body_emit_links & declared), len(declared))


def m4(records: list[dict]) -> MeasureScore:
    """M4 — semantic_pass_rate (weight 15%, Output Integrity).

    Per § 6: |{r ∈ R : r.semantic_ok}| / |R|. Binary per source; failed
    parses naturally have semantic_ok=False (compile_one's state init).
    """
    n_total = len(records)
    n_pass = sum(1 for r in records if r.get("semantic_ok"))
    rate = (n_pass / n_total) if n_total else None
    return MeasureScore(name="M4", numerator=n_pass, denominator=n_total, rate=rate, weight=0.15)


def m5(records: list[dict]) -> MeasureScore:
    """M5 — body_emit_set_coverage (weight 15%, Output Integrity).

    Per §7.3 + Task #59 design: per-source coverage of declared
    `concept_slugs ∪ article_slugs` by body wikilinks across other pages
    (self-links excluded). Micro-aggregated:

      Σ |⋃_p (body_wikilink_slugs(p.body) − {p.slug})| ∩ declared_emit_set
      ────────────────────────────────────────────────────────────────────
      Σ |declared_emit_set|

    over parse-pass records (matches M2/M3 `_is_parse_pass` gate; §10.1).
    Round 4 MF6: zero-denom → 0.0 (model-controlled penalty).
    """
    num_total = 0
    denom_total = 0
    for r in records:
        if not _is_parse_pass(r):
            continue
        pj = r.get("parsed_json")
        if not isinstance(pj, dict):
            continue
        n, d = _compute_body_emit_set_coverage(pj)
        num_total += n
        denom_total += d
    rate = (num_total / denom_total) if denom_total else 0.0
    return MeasureScore(name="M5", numerator=num_total, denominator=denom_total, rate=rate, weight=0.15)


def m6(records: list[dict], *, price_in: float, price_out: float) -> MeasureScore:
    """M6 — cost_per_1k_source_words (weight 10%, Production Cost; raw $).

    Per § 6: cost_usd_i = (input_tokens × price_in + output_tokens × price_out) / 1_000_000.
    Aggregated over records with source_words > 0 (Round 4 MF1: parse-fail
    records still bill cost). rate = (Σ cost_usd / Σ source_words) × 1000.
    Round 4 MF6: zero-denom → None (corpus-controlled — pro-rata redistribute).
    """
    num = 0.0
    denom = 0
    for r in records:
        sw = int(r.get("source_words", 0))
        if sw <= 0:
            continue
        cost = (
            int(r.get("input_tokens", 0)) * price_in
            + int(r.get("output_tokens", 0)) * price_out
        ) / 1_000_000
        num   += cost
        denom += sw
    rate = (num / denom) * 1000 if denom else None
    return MeasureScore(name="M6", numerator=num, denominator=denom, rate=rate, weight=0.10)


def m7(records: list[dict]) -> MeasureScore:
    """M7 — latency_per_1k_source_words (weight 10%, Production Cost; raw ms).

    rate = (Σ latency_ms / Σ source_words) × 1000 over records where
    source_words > 0. Round 4 MF6: zero-denom → None (corpus-controlled).
    """
    num = 0
    denom = 0
    for r in records:
        sw = int(r.get("source_words", 0))
        if sw <= 0:
            continue
        num   += int(r.get("latency_ms", 0))
        denom += sw
    rate = (num / denom) * 1000 if denom else None
    return MeasureScore(name="M7", numerator=num, denominator=denom, rate=rate, weight=0.10)


def retry_load(records: list[dict]) -> MeasureScore:
    """Diagnostic: cap-normalized fraction of retry budget consumed.

    Per § 6: Σ min(MAX_RETRIES, max(0, attempts − 1)) / (|R| × MAX_RETRIES).
    Round 4 MF8: per-record contribution clamped at MAX_RETRIES so overridden
    `max_attempts` cannot push the diagnostic above 1.0.
    """
    n_total = len(records)
    num = sum(min(MAX_RETRIES, max(0, int(r.get("attempts", 0)) - 1)) for r in records)
    denom = n_total * MAX_RETRIES
    rate = (num / denom) if denom else None
    return MeasureScore(name="retry_load", numerator=num, denominator=denom, rate=rate, weight=0.0)


def token_overrun_rate(records: list[dict]) -> MeasureScore:
    """Diagnostic: |{r : r.token_overrun}| / |R|."""
    n_total = len(records)
    n_overrun = sum(1 for r in records if r.get("token_overrun"))
    rate = (n_overrun / n_total) if n_total else None
    return MeasureScore(name="token_overrun_rate", numerator=n_overrun, denominator=n_total, rate=rate, weight=0.0)


# ---------------------------------------------------------------------------
# §9 — Top-level entry points
# ---------------------------------------------------------------------------

def _load_records(state_root: Path, run_id: str) -> list[dict]:
    """Read every *.json file under <state_root>/llm_resp/<run_id>/.

    Returns the list of parsed dicts. Raises ValueError if no files match
    or if duplicate (run_id, source_id) records are found.
    """
    run_dir = Path(state_root) / "llm_resp" / run_id
    files = sorted(run_dir.glob("*.json")) if run_dir.exists() else []
    if not files:
        raise ValueError(f"score_run: no records found under {run_dir}")

    records: list[dict] = []
    seen_source_ids: set[str] = set()
    for path in files:
        record = json.loads(path.read_text(encoding="utf-8"))
        sid = record.get("source_id")
        if sid in seen_source_ids:
            raise ValueError(f"score_run: duplicate (run_id, source_id) — '{sid}' in {run_id}")
        seen_source_ids.add(sid)
        records.append(record)
    return records


def _verify_capture_full(records: list[dict]) -> None:
    """Round 4 / Phase 3 § 3: parse_ok=True ∧ parsed_json=None means the
    runner didn't set KDB_RESP_STATS_CAPTURE_FULL=1. Scorer cannot derive
    M1/M2/M3/S3 without parsed_json. Fail loud."""
    for r in records:
        if r.get("parse_ok") and r.get("parsed_json") is None:
            raise RuntimeError(
                "benchmark mode requires KDB_RESP_STATS_CAPTURE_FULL=1 "
                "(parse_ok=True records found with parsed_json=None)"
            )


def _resolve_model_entry(model_id: str, registry: list[ModelEntry]) -> ModelEntry:
    for entry in registry:
        if entry.id == model_id:
            return entry
    raise ValueError(f"model_id '{model_id}' not found in registry")


def score_run(
    state_root: Path,
    run_id: str,
    model_id: str,
    *,
    registry_path: Path = MODELS_JSON,
    trace_sink: list[str] | None = None,
) -> RunScore:
    """Phase 3 § 9 entry point.

    Reads every RespStatsRecord JSON under <state_root>/llm_resp/<run_id>/,
    verifies (provider, model) consistency against the registry's ModelEntry
    for `model_id`, runs all measures + diagnostics, returns a RunScore with
    raw rates. m6_borda / m7_borda / final_score are None on the returned
    object — populated only by score_runs() across peers.

    `trace_sink`: when a list is provided, append per-measure trace lines
    (numerator, denominator, rate, weight, plus per-source evidence for S0
    and derivation snippets for M1/M6/M7). The CLI uses this to surface
    `--verbose` output after the scorecard render rather than mid-flight.
    Pass `None` to disable tracing entirely.
    """
    registry = load_registry(registry_path)
    entry = _resolve_model_entry(model_id, registry)

    records = _load_records(state_root, run_id)

    # Verify every record's persisted (provider, model) matches the
    # ModelEntry derived from model_id (Round 4 MF2 + DC2 contract).
    for r in records:
        if r.get("provider") != entry.provider or r.get("model") != entry.model:
            raise ValueError(
                f"score_run: provider/model mismatch — record has "
                f"({r.get('provider')!r}, {r.get('model')!r}); "
                f"registry expects ({entry.provider!r}, {entry.model!r}) for {model_id!r}"
            )

    _verify_capture_full(records)

    rs = RunScore(
        run_id=run_id,
        model_id=model_id,
        provider=entry.provider,
        model=entry.model,
        n_attempted=len(records),
        s0=s0(records),
        s1=s1(records),
        s2=s2(records),
        s3=s3(records),
        measures={
            "M1": m1(records),
            "M2": m2(records),
            "M3": m3(records),
            "M4": m4(records),
            "M5": m5(records),
            "M6": m6(records, price_in=entry.price_in, price_out=entry.price_out),
            "M7": m7(records),
        },
        diagnostics={
            "retry_load":              retry_load(records),
            "token_overrun_rate":      token_overrun_rate(records),
            "pages_per_1k_source_words": pages_per_1k_source_words(records),
        },
        m6_borda=None,
        m7_borda=None,
        final_score_pre_penalty=None,
        penalty=0.0,
        final_score=None,
    )

    if trace_sink is not None:
        _emit_verbose_trace(records, rs, trace_sink)

    return rs


# ---------------------------------------------------------------------------
# §9b — verbose trace (CLI --verbose hook, no schema impact)
# ---------------------------------------------------------------------------

_MEASURE_LABELS: dict[str, str] = {
    "S0": "pipeline_success_rate",
    "S1": "llm_resp_success_rate           (diagnostic)",
    "S2": "validator_schema_pass_rate       (diagnostic)",
    "S3": "validator_hard_zero_pass_rate    (diagnostic)",
    "M1": "link_target_resolution",
    "M2": "concept_slugs_jaccard",
    "M3": "article_slugs_jaccard",
    "M4": "semantic_pass_rate",
    "M5": "body_emit_set_coverage",
    "M6": "cost_per_1k_source_words",
    "M7": "latency_per_1k_source_words",
}


def _fmt_score(label: str, ms: MeasureScore) -> str:
    """Format one MeasureScore as a single trace line."""
    rate_str = "None" if ms.rate is None else f"{ms.rate:.4f}"
    weight_str = f"{int(round(ms.weight * 100))}/100"
    return (
        f"[verbose] {ms.name:<3} {_MEASURE_LABELS.get(ms.name, label):<48}"
        f" {ms.numerator}/{ms.denominator}  rate={rate_str}  weight={weight_str}"
    )


def _s0_per_source_lines(records: list[dict]) -> list[str]:
    """One block per source showing the S0 gate chain as numbered KPIs:
        [1] parse_ok        [2] schema_ok        [3] parsed_json shape
        [4] hard-zero findings
    Followed by → S0 PASS / FAIL. Always emitted under --verbose so passing
    sources are visible too."""
    lines: list[str] = []
    for r in records:
        sid = r.get("source_id", "<unknown>")
        lines.append(f"[verbose]   {sid}")

        if not r.get("parse_ok"):
            lines.append(f"[verbose]     [1] parse_ok=False")
            lines.append(f"[verbose]     → S0 FAIL")
            continue
        lines.append(f"[verbose]     [1] parse_ok=True")

        if not r.get("schema_ok"):
            errs = r.get("schema_errors") or []
            head = errs[0] if errs else "(no error captured)"
            lines.append(f"[verbose]     [2] schema_ok=False")
            lines.append(f"[verbose]         schema_error: {head}")
            lines.append(f"[verbose]     → S0 FAIL")
            continue
        lines.append(f"[verbose]     [2] schema_ok=True")

        parsed = r.get("parsed_json")
        if not isinstance(parsed, dict):
            lines.append(f"[verbose]     [3] parsed_json=NOT_DICT")
            lines.append(f"[verbose]     → S0 FAIL")
            continue
        lines.append(f"[verbose]     [3] parsed_json=dict")

        findings = check_compiled_source_findings(parsed)
        if findings:
            lines.append(f"[verbose]     [4] hard-zero findings:")
            for f in findings:
                lines.append(f"[verbose]         - {f.type}: {f.detail}")
            lines.append(f"[verbose]     → S0 FAIL")
        else:
            lines.append(f"[verbose]     [4] hard-zero=none")
            lines.append(f"[verbose]     → S0 PASS")
    return lines


def _m5_per_source_coverage_lines(records: list[dict]) -> list[str]:
    """Per-source coverage detail under the M5 line, emitted only when M5
    rate < 1.0 (Task #59, replaces the retired per-page asymmetry helper).

    For each parse-pass record with denom > 0 and num < denom, list the
    source_id, the integrated count vs declared count, and the sorted set
    of declared emit-set slugs that did NOT appear as body wikilinks in
    any other page. Self-links are already excluded by
    `_emit_set_components`. Returns empty list (caller emits nothing —
    not even a header) when no source falls below 100%.
    """
    body: list[str] = []
    for r in records:
        if not _is_parse_pass(r):
            continue
        parsed = r.get("parsed_json")
        if not isinstance(parsed, dict):
            continue
        declared, body_emit_links = _emit_set_components(parsed)
        n = len(body_emit_links & declared)
        d = len(declared)
        if d == 0 or n == d:
            continue
        missing = sorted(declared - body_emit_links)
        sid = r.get("source_id", "<unknown>")
        body.append(f"[verbose]     {sid}: {n}/{d} integrated, missing: {missing}")

    if not body:
        return []
    return ["[verbose]   per-source M5 coverage:"] + body


def _emit_verbose_trace(records: list[dict], rs: RunScore, sink: list[str]) -> None:
    """Append per-measure trace for one RunScore to `sink`. Called from
    score_run when a trace_sink list is provided. Output is best-effort
    for human inspection; not a stable contract."""
    sink.append(
        f"[verbose] ── score_run: {rs.model_id}  (n_attempted={rs.n_attempted}) ──"
    )
    sink.append(_fmt_score(rs.s0.name, rs.s0))
    sink.append("[verbose]   per-source S0 breakdown:")
    sink.extend(_s0_per_source_lines(records))

    for ms in (rs.s1, rs.s2, rs.s3):
        sink.append(_fmt_score(ms.name, ms))

    for key in ("M1", "M2", "M3", "M4", "M5", "M6", "M7"):
        ms = rs.measures[key]
        sink.append(_fmt_score(ms.name, ms))
        if key == "M1":
            target = {
                p.get("slug")
                for r in records
                if _is_parse_pass(r) and r.get("schema_ok")
                for p in _iter_pages(r["parsed_json"])
                if isinstance(p.get("slug"), str)
            }
            sink.append(f"[verbose]   └─ target_set: {len(target)} unique slugs")
        elif key == "M5" and ms.rate is not None and ms.rate < 1.0:
            sink.extend(_m5_per_source_coverage_lines(records))
        elif key == "M6":
            sink.append(
                f"[verbose]   └─ ${ms.numerator:.4f} cost / {ms.denominator} source-words"
            )
        elif key == "M7":
            sink.append(
                f"[verbose]   └─ {ms.numerator}ms latency / {ms.denominator} source-words"
            )

    sink.append("[verbose] diagnostics:")
    for ms in rs.diagnostics.values():
        rate_str = "None" if ms.rate is None else f"{ms.rate:.4f}"
        sink.append(
            f"[verbose]   {ms.name:<28} {ms.numerator}/{ms.denominator}"
            f"  rate={rate_str}"
        )


def score_runs(
    runs: list[RunScore],
    *,
    trace_sink: list[str] | None = None,
) -> list[RunScore]:
    """Cross-model enrichment per § 9. Borda-normalizes M6 / M7 across the
    candidate set and computes final_score for each run. Returns NEW frozen
    RunScore objects — input list is not mutated.

    `trace_sink`: when a list is provided, append the raw → Borda →
    final_score derivation lines for each candidate. The CLI accumulates
    this with score_run's trace and prints once after the scorecard render.
    """
    if not runs:
        raise ValueError("score_runs: empty input")

    m6_scores = borda_normalize(runs, "M6", lower_is_better=True)
    m7_scores = borda_normalize(runs, "M7", lower_is_better=True)

    if trace_sink is not None:
        trace_sink.append(
            f"[verbose] ── score_runs: candidate_set={[r.model_id for r in runs]} ──"
        )
        trace_sink.append("[verbose] M6 raw rates → Borda:")
        for run in runs:
            raw = run.measures["M6"].rate
            raw_str = "None" if raw is None else f"{raw:.6f}"
            b = m6_scores.get(run.model_id)
            b_str = "None" if b is None else f"{b:.4f}"
            trace_sink.append(
                f"[verbose]   {run.model_id:<16} raw={raw_str}  →  borda={b_str}"
            )
        trace_sink.append("[verbose] M7 raw rates → Borda:")
        for run in runs:
            raw = run.measures["M7"].rate
            raw_str = "None" if raw is None else f"{raw:.2f}"
            b = m7_scores.get(run.model_id)
            b_str = "None" if b is None else f"{b:.4f}"
            trace_sink.append(
                f"[verbose]   {run.model_id:<16} raw={raw_str}ms  →  borda={b_str}"
            )

    # Pass 1: Borda + pre-penalty final
    provisional: list[RunScore] = []
    for run in runs:
        m6_b = m6_scores.get(run.model_id)
        m7_b = m7_scores.get(run.model_id)
        p = replace(run, m6_borda=m6_b, m7_borda=m7_b)
        try:
            pre = final_score(p)
        except ValueError:
            pre = None
        # Initialize new fields; final_score will be set in pass 3
        p = replace(p, final_score_pre_penalty=pre, penalty=0.0, final_score=None)
        provisional.append(p)
        if trace_sink is not None:
            pre_str = "None" if pre is None else f"{pre:.4f}"
            trace_sink.append(
                f"[verbose] {run.model_id:<16} final_score_pre_penalty={pre_str}"
            )

    # Pass 2: compute outlier penalty across the candidate set (D31)
    penalty_map = _compute_outlier_penalty(provisional)

    if trace_sink is not None:
        trace_sink.append("[verbose] outlier penalty (D31, in-scope: S0+M1..M5):")
        for run in provisional:
            if penalty_map.get(run.model_id, 0.0) > 0.0:
                pen = penalty_map[run.model_id]
                units = round(pen / 0.05)
                trace_sink.append(
                    f"[verbose]   {run.model_id:<16} units={units}  penalty={-pen:.2f}"
                )
            else:
                trace_sink.append(
                    f"[verbose]   {run.model_id:<16} units=0  penalty=  -"
                )

    # Pass 3: apply penalty
    enriched: list[RunScore] = []
    for run in provisional:
        pen = penalty_map.get(run.model_id, 0.0)
        if run.final_score_pre_penalty is None:
            post = None
        else:
            post = max(0.0, run.final_score_pre_penalty - pen)
        enriched.append(replace(run, penalty=pen, final_score=post))

    return enriched


def borda_normalize(
    runs: list[RunScore],
    measure: str,
    *,
    lower_is_better: bool,
) -> dict[str, float]:
    """Average-rank (fractional rank) Borda normalization across candidates.

    Per § 7:
      1. Drop RunScores where measures[measure].rate is None.
      2. Sort the remaining N runs by raw rate (asc if lower_is_better else desc).
      3. Assign fractional ranks (tied candidates share the average of their
         tied ordinal positions).
      4. Convert rank → score in [0, 1]:
            score = (N − rank) / (N − 1)         if N ≥ 2
            score = 1.0                          if N == 1
         All-equal candidates → 0.5 each (no signal).

    Returns {model_id → normalized score in [0, 1]}.
    """
    eligible = [
        (r.model_id, r.measures[measure].rate)
        for r in runs
        if r.measures[measure].rate is not None
    ]
    n = len(eligible)
    if n == 0:
        return {}
    if n == 1:
        return {eligible[0][0]: 1.0}

    # Sort by raw rate (best first). For ties, ordinal position is deterministic
    # by stable sort but the fractional-rank-with-averaging will give all
    # tied entries the same value, so the within-tie order doesn't matter.
    sorted_pairs = sorted(eligible, key=lambda mr: mr[1], reverse=not lower_is_better)

    # Assign fractional ranks: for each group of ties, all members get the
    # average of their consecutive ordinal positions (1-indexed).
    ranks: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sorted_pairs[j + 1][1] == sorted_pairs[i][1]:
            j += 1
        # tied span [i, j] inclusive — ordinal positions i+1 .. j+1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[sorted_pairs[k][0]] = avg_rank
        i = j + 1

    # All-equal special case: every candidate shares the central rank → score 0.5
    distinct_rates = {rate for _, rate in eligible}
    if len(distinct_rates) == 1:
        return {model_id: 0.5 for model_id, _ in eligible}

    # Convert ranks to scores
    return {
        model_id: (n - rank) / (n - 1)
        for model_id, rank in ranks.items()
    }


# In-scope measures for outlier penalty (D31.5): S0 + M1..M5; M6/M7 excluded
# (already Borda-relative).
_PENALTY_IN_SCOPE_MEASURES = ("S0", "M1", "M2", "M3", "M4", "M5")


def _compute_outlier_penalty(runs: list["RunScore"]) -> dict[str, float]:
    """Per-model penalty deduction for FINAL (D31, Task #62).

    For each in-scope measure (S0, M1, M2, M3, M4, M5):
      norm           = mean(measure.rate across runs, excluding rate=None)
      deviation_pct  = max(0, (norm - value) / norm * 100)   when value < norm and norm > 0
      penalty_units  = floor(deviation_pct / 10)

    Per-run total: Σ penalty_units across in-scope measures × 0.05.

    Returns: dict mapping run.model_id → penalty deduction (always >= 0).

    Properties:
      - One-sided: only below-norm penalized (D31.2)
      - Excludes rate=None from norm; that (run, measure) gets 0 penalty (D31.9)
      - norm == 0 → 0 penalty for all on that measure (D31.8, avoids div-by-zero)
      - Cumulative no cap (D31.6)
    """
    def _rate_for(run: "RunScore", key: str) -> Optional[float]:
        if key == "S0":
            return run.s0.rate
        return run.measures[key].rate

    penalty_per_model: dict[str, float] = {r.model_id: 0.0 for r in runs}

    for measure_key in _PENALTY_IN_SCOPE_MEASURES:
        # Compute norm: mean of rates, excluding None
        rates = [_rate_for(r, measure_key) for r in runs]
        valid = [v for v in rates if v is not None]
        if not valid:
            continue  # all None; skip this measure entirely
        norm = sum(valid) / len(valid)
        if norm <= 0.0:
            continue  # avoid div-by-zero (D31.8); also handles all-zero case

        for run in runs:
            value = _rate_for(run, measure_key)
            if value is None:
                continue  # this (run, measure) gets 0 penalty (D31.9)
            if value >= norm:
                continue  # at-or-above norm: 0 penalty (D31.2)
            deviation_pct = (norm - value) / norm * 100.0
            units = math.floor(deviation_pct / 10.0)
            penalty_per_model[run.model_id] += units * 0.05

    return penalty_per_model


def final_score(run: RunScore) -> Optional[float]:
    """Weighted sum of S0 + M1..M7 with pro-rata redistribution if any
    component rate is None. Returns None for fully-degenerate runs.

    Reads M6/M7 from `run.m6_borda` / `run.m7_borda` (post-Borda); reads
    other components' rates from `run.s0` / `run.measures`. Weights are
    sourced from the MeasureScore objects themselves (single source of
    truth — eliminates the duplicate-weight-table drift bug fixed
    post-#61). Raises ValueError if every component is None (degenerate
    corpus).
    """
    components: list[tuple[str, float, Optional[float]]] = [
        ("S0", run.s0.weight,                run.s0.rate),
        ("M1", run.measures["M1"].weight,    run.measures["M1"].rate),
        ("M2", run.measures["M2"].weight,    run.measures["M2"].rate),
        ("M3", run.measures["M3"].weight,    run.measures["M3"].rate),
        ("M4", run.measures["M4"].weight,    run.measures["M4"].rate),
        ("M5", run.measures["M5"].weight,    run.measures["M5"].rate),
        ("M6", run.measures["M6"].weight,    run.m6_borda),
        ("M7", run.measures["M7"].weight,    run.m7_borda),
    ]
    score_sum = 0.0
    present_weights = 0.0
    for _, weight, rate in components:
        if rate is None:
            continue
        score_sum       += weight * rate
        present_weights += weight
    if present_weights == 0.0:
        raise ValueError("degenerate run: every scored component is None")
    return score_sum / present_weights


def pages_per_1k_source_words(records: list[dict]) -> MeasureScore:
    """Diagnostic: (Σ pages_produced / Σ source_words) × 1000.

    `pages_produced_i` = parsed_summary.page_count when parse_ok, else 0.
    Records with source_words == 0 are skipped entirely.
    """
    num = 0
    denom = 0
    for r in records:
        sw = int(r.get("source_words", 0))
        if sw <= 0:
            continue
        if r.get("parse_ok") and isinstance(r.get("parsed_summary"), dict):
            pages_i = int(r["parsed_summary"].get("page_count", 0))
        else:
            pages_i = 0
        num   += pages_i
        denom += sw
    rate = (num / denom) * 1000 if denom else None
    return MeasureScore(name="pages_per_1k_source_words", numerator=num, denominator=denom, rate=rate, weight=0.0)
