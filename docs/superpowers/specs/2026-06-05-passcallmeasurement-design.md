# `PassCallMeasurement` — shared per-call measurement projection (B1)

**Date:** 2026-06-05 · **Status:** 🟢 ratified design (Joseph approved 2026-06-05)
**Serves:** #108 (Pass-1 outcome telemetry) + #109 (benchmark per-run KPI source). The shared core both depend on — designed once.
**Companion:** `2026-06-05-benchmark-kpi-enumeration-brief.md` (v0.2 KPI list) · `2026-06-03-benchmark-redesign-directions.md` (architecture).

---

## 1. Purpose & key decision

#108 needs a Pass-1 outcome record; #109 needs to read Pass-1 + Pass-2 robustness uniformly for the scored KPIs (`quarantine_rate`, `intervention_burden`, `token-overrun`, `latency`). Both want the *same* per-call shape across both passes. That shape is `PassCallMeasurement`.

**Decision (ratified): `PassCallMeasurement` is a logical *projection*, not a new stored record.** The vocabulary lock says *measurement* ≠ *telemetry*. The telemetry already exists and is authoritative:
- **Pass-2** — `RespStatsRecord` (`common/types.py`), persisted to `state/runs/<run_id>/llm_resp/<run_id>/<sid>.json`.
- **Pass-1** — the sidecar `raw_response` block (`ingestion/enrich/enrich.py:139`), persisted to `state/runs/<run_id>/enrich/<run_id>/<sid>.json`.

So `PassCallMeasurement` is a **dataclass + adapter** that projects both into one shape — *no new file*. This honors [[feedback_no_parallel_storage_to_authority]]: we don't duplicate what the sidecar / `RespStatsRecord` already hold; we read them.

Producers get **minimal deltas** only to capture the three things the projection needs that aren't recorded today (§4).

## 2. The shape

```python
# common/measurement.py  (leaf — ingestion + compiler may populate; tools/benchmark + compiler/kpi read)
@dataclass(frozen=True)
class PassCallMeasurement:
    # identity
    run_id: str
    source_id: str
    pass_: str            # "pass1" | "pass2"
    provider: str
    model: str
    prompt_version: str
    # outcome — unified across both passes
    final_status: str     # "clean" | "repaired" | "retried-and-repaired" | "quarantined"
    # robustness
    attempts: int
    syntax_repaired: bool
    slug_coerced: bool     # P2-only; P1 always False until a P1 rung exists
    token_overrun: bool
    # cost / throughput — aggregated across ALL attempts (not just the winner)
    total_input_tokens: int
    total_output_tokens: int
    total_latency_ms: int
    call_count: int        # number of LLM calls made (= attempts that reached the model)
    final_attempt_index: int
    # volume
    source_words: int
    # gate breakdown (diagnostic)
    parse_ok: bool
    schema_ok: bool
    semantic_ok: bool | None   # None for pass1 (no semantic gate)
```

**Run-level header** (one per run; carries the denominators + corpus identity the per-call records can't):

```python
@dataclass(frozen=True)
class RunMeasurementHeader:
    run_id: str
    corpus_fingerprint: str     # hash of the source set — asserts same-corpus cohort
    pass1_prompt_version: str
    pass2_prompt_version: str
    scanned: int
    to_compile: int
    signal: int                 # sources gated signal → reach Pass-2
    noise: int                  # sources gated noise → no Pass-2
    p1_attempted: int
    p2_attempted: int
```

## 3. The adapter

```python
# common/measurement.py
def from_pass2(rec: RespStatsRecord) -> PassCallMeasurement: ...
def from_pass1(sidecar: dict) -> PassCallMeasurement: ...
def load_run_measurements(run_dir: Path) -> tuple[RunMeasurementHeader, list[PassCallMeasurement]]: ...
```

`load_run_measurements` reads both telemetry trees under `state/runs/<run_id>/` (`llm_resp/` for P2, `enrich/` for P1) + the run header, returns the projected list. This is the single entry point #109's `compiler/kpi/processing.py` and #108's consumers call.

## 4. Producer deltas (the only code that changes)

The adapter can project everything **except** three things not recorded today. These are the framework prerequisites, scoped minimally:

1. **Discarded-attempt aggregation** *(codex g-High)* — both producers persist only the *winning* attempt's tokens/latency.
   - **P2:** `compile_one()` overwrites `model_response` each attempt (`compiler/compiler.py` loop @247). Delta: accumulate `total_input_tokens` / `total_output_tokens` / `total_latency_ms` / `call_count` across attempts into `RespStatsRecord` (additive fields; existing single-attempt fields untouched for back-compat).
   - **P1:** `call_pass1()` already loops (`pass1_caller.py:78`) but `Pass1CallResult` keeps only the last attempt's tokens. Delta: sum across attempts; persist the totals into the sidecar `raw_response` block.
2. **Pass-1 `final_status`** — P1 has no outcome field. Delta: derive in `enrich`/`call_pass1` (`clean` / `repaired` once `json_escape_fix` fires [#108] / `retried-and-repaired` / `quarantined`), mirroring #106's P2 derivation; persist into the sidecar. *(This is #108's piece-1.)*
3. **Run-level denominators** — Delta: the orchestrator writes `RunMeasurementHeader` into the run dir (it already counts scanned/signal/noise via `orchestrator_events`; this persists them as a header).

Everything else (`final_status` P2, `syntax_repaired`, `slug_coerced`, `token_overrun`, `attempts`, `source_words`, gate flags) is already in `RespStatsRecord` and projects directly.

## 5. Home

`common/measurement.py` — a leaf module. Rationale: it's cross-pass (ingestion + compiler both populate) and cross-consumer (`tools/benchmark` + `compiler/kpi` both read); `common` is the only package all four may depend on (B.3 contract). The dataclass + adapter live together.

## 6. Test plan (TDD)
- `from_pass2` projects a known `RespStatsRecord` fixture → expected `PassCallMeasurement` (incl. aggregated totals).
- `from_pass1` projects a known sidecar fixture → expected (incl. `final_status` derivation, `semantic_ok=None`, `slug_coerced=False`).
- discarded-attempt aggregation: 2-attempt P2 fixture → `total_*` = sum of both, `call_count=2`, `final_attempt_index=2`.
- `load_run_measurements` over a captured sandbox run dir → header denominators correct, N records, pass split correct.
- back-compat: existing `RespStatsRecord` consumers unaffected (additive fields only).

## 7. Consumers
- **#108** owns producer-delta #2 (P1 `final_status`) + the json_escape_fix wiring; reads `from_pass1` to verify.
- **#109** `compiler/kpi/processing.py` calls `load_run_measurements` → computes the scored processing KPIs + diagnostics over the projected list.
