# Benchmark Implementation Plan (B1 + #108 + #109)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the redesigned KDB benchmark — a per-call measurement projection (B1), Pass-1 robustness telemetry + `json_escape_fix` (#108), and the GT-free two-family KPI framework with Borda scoring (#109) — to "ready to fire," leaving only the live multi-model run and post-run-1 weight calibration.

**Architecture:** Telemetry stays authoritative (P2 `RespStatsRecord`, P1 sidecar); `PassCallMeasurement` is a logical projection over both (no new store). `compiler/kpi/` computes processing + graph KPIs (production-importable); `kdb-orchestrate --emit-kpis` writes `benchmark/runs/<id>/measurements.json`; `tools/benchmark` scores cross-model via reused Borda. Weights + final scored-set selection are parked to post-run-1 calibration.

**Tech Stack:** Python 3, dataclasses, jsonschema, Kuzu (`kdb_graph.queries`), pytest (run with `-m "not live"` — `.env` auto-loads keys).

**Specs:** B1 `docs/superpowers/specs/2026-06-05-passcallmeasurement-design.md` · B2 `…task108-pass1-robustness-design.md` · B3 `…benchmark-framework-design.md` · KPI list `…benchmark-kpi-enumeration-brief.md`.

**Test discipline:** ALWAYS run pytest with `-m "not live"` (per [[feedback_user_fires_api_cost_runs]] — bare pytest fires live API tests). Commit after each green task.

---

## File structure

| Path | Responsibility | Phase |
|---|---|---|
| `common/measurement.py` (new) | `PassCallMeasurement` + `RunMeasurementHeader` dataclasses + `from_pass1`/`from_pass2`/`load_run_measurements` adapters | 1 |
| `common/types.py` (mod) | `RespStatsRecord` += discarded-attempt aggregate fields | 1 |
| `common/llm_telemetry.py` (mod) | populate the new aggregate fields | 1 |
| `compiler/compiler.py` (mod) | accumulate per-attempt tokens/latency across the compile loop | 1 |
| `ingestion/enrich/pass1_caller.py` (mod) | `json_escape_fix` rung + per-attempt aggregation + `final_status` on `Pass1CallResult` | 2 |
| `ingestion/enrich/enrich.py` (mod) | persist `final_status`/aggregates into the sidecar | 2 |
| `orchestrator/kdb_orchestrate.py` (mod) | write `RunMeasurementHeader`; `--emit-kpis` flag | 1, 3 |
| `compiler/kpi/processing.py` (new) | processing KPIs + diagnostics from `PassCallMeasurement` list | 3 |
| `compiler/kpi/graph.py` (new) | graph KPIs + diagnostics + watched (alias-aware link-resolution) | 3 |
| `compiler/kpi/score.py` (new) | Borda composite mechanism (weights pluggable) | 3 |
| `tools/benchmark/cli.py` (mod) | `kdb-benchmark score` over measurements.json | 3 |
| `tests/common/test_measurement.py`, `tests/compiler/kpi/test_*.py`, `tests/ingestion/test_pass1_robustness.py` (new) | TDD | all |

---

# PHASE 1 — B1: `PassCallMeasurement` foundation

### Task 1: `PassCallMeasurement` + `RunMeasurementHeader` dataclasses

**Files:**
- Create: `common/measurement.py`
- Test: `tests/common/test_measurement.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/common/test_measurement.py
from common.measurement import PassCallMeasurement, RunMeasurementHeader

def test_passcallmeasurement_fields():
    m = PassCallMeasurement(
        run_id="r1", source_id="KDB/raw/a.md", pass_="pass2",
        provider="deepseek", model="deepseek-v4-flash", prompt_version="2.0",
        final_status="clean", attempts=1, syntax_repaired=False, slug_coerced=False,
        token_overrun=False, total_input_tokens=100, total_output_tokens=50,
        total_latency_ms=1200, call_count=1, final_attempt_index=1, source_words=400,
        parse_ok=True, schema_ok=True, semantic_ok=True,
    )
    assert m.pass_ == "pass2" and m.final_status == "clean"

def test_runheader_fields():
    h = RunMeasurementHeader(
        run_id="r1", corpus_fingerprint="sha", pass1_prompt_version="1.1",
        pass2_prompt_version="2.0", scanned=36, to_compile=36, signal=29,
        noise=7, p1_attempted=36, p2_attempted=29)
    assert h.signal == 29
```

- [ ] **Step 2: Run to verify it fails** — `pytest tests/common/test_measurement.py -m "not live" -v` → FAIL (module not found)
- [ ] **Step 3: Implement** the two frozen dataclasses exactly per B1 §2 (fields + types as in the test; `semantic_ok: bool | None`). Note `pass_` trailing-underscore (avoid the `pass` keyword).
- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `git add common/measurement.py tests/common/test_measurement.py && git commit -m "feat(measurement): PassCallMeasurement + RunMeasurementHeader dataclasses (B1)"`

### Task 2: P2 discarded-attempt aggregation (producer delta #1)

**Files:**
- Modify: `common/types.py` (`RespStatsRecord` — add `total_input_tokens`, `total_output_tokens`, `total_latency_ms`, `call_count`, `final_attempt_index`; default to the single-attempt values for back-compat)
- Modify: `compiler/compiler.py` (compile loop @247 — accumulate per-attempt `input_tokens`/`output_tokens`/`latency_ms` into running totals; pass to the record build)
- Modify: `common/llm_telemetry.py` (`build_resp_stats` — populate the new fields)
- Test: `tests/compiler/test_attempt_aggregation.py`

- [ ] **Step 1: Write the failing test** — a 2-attempt compile (first attempt fails parse, second clean) yields `total_input_tokens` = sum of both attempts, `call_count == 2`, `final_attempt_index == 2`. Build the fixture by stubbing `call_model` to return two responses (read `tests/` for the existing compile-loop test pattern + `_MAX_COMPILE_ATTEMPTS`).
- [ ] **Step 2: Run** → FAIL (fields absent / not summed)
- [ ] **Step 3: Implement** — add the 5 fields to `RespStatsRecord` (back-compat: a 1-attempt run sets totals = the single values, `call_count=1`); thread accumulators through the `compiler.py` loop; populate in `build_resp_stats`. **Read `common/types.py` + `common/llm_telemetry.py:70-184` first** for exact shapes.
- [ ] **Step 4: Run** → PASS; also run the existing `RespStatsRecord` tests (`pytest tests/ -m "not live" -k resp_stats`) to confirm back-compat.
- [ ] **Step 5: Commit** — `feat(telemetry): aggregate discarded-attempt tokens/latency on RespStatsRecord (B1 delta #1)`

### Task 3: `from_pass2` adapter

**Files:** Modify `common/measurement.py`; Test `tests/common/test_measurement.py`

- [ ] **Step 1: Failing test** — `from_pass2(resp_stats_dict)` over a fixture (built from a real `RespStatsRecord.to_dict()`) → `PassCallMeasurement(pass_="pass2", …)` with `final_status` echoed, `semantic_ok` carried, totals from the aggregate fields.
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** `from_pass2` — straight field map (RespStatsRecord is a superset). `slug_coerced`/`syntax_repaired`/`token_overrun`/`final_status` read directly.
- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `feat(measurement): from_pass2 adapter (B1)`

### Task 4: `RunMeasurementHeader` emission from orchestrator

**Files:** Modify `orchestrator/kdb_orchestrate.py` (write the header into the run dir at finalize — counts already exist via `orchestrator_events`); Test `tests/orchestrator/test_run_header.py`

- [ ] **Step 1: Failing test** — after a (mocked) run, `state/runs/<id>/measurement_header.json` exists with `signal`/`noise`/`scanned` matching the event counts + `corpus_fingerprint`.
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** — `corpus_fingerprint` = `sha256` of sorted `{source_id: content_hash}` from the scan; write the header at finalize. **Read `orchestrator/kdb_orchestrate.py:580-700` + `orchestrator_events.py` for the count sources.**
- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `feat(orchestrator): write RunMeasurementHeader at finalize (B1 delta #3)`

---

# PHASE 2 — #108: Pass-1 robustness (B2)

### Task 5: wire `json_escape_fix` into `call_pass1`

**Files:** Modify `ingestion/enrich/pass1_caller.py:84-94`; Test `tests/ingestion/test_pass1_robustness.py`

- [ ] **Step 1: Failing test**
```python
# a Pass-1 raw response with a stray backslash that fails json.loads but parses after escape
def test_pass1_json_escape_repair(monkeypatch):
    bad = '{"kdb_signal":"signal","summary":"uses \\( n-1 \\) notation", ...valid rest...}'
    # stub call_model to return `bad`; assert result.final_status == "repaired"
    #   and result.syntax_repaired is True and NOT Pass1CallError
```
(Fill the `...valid rest...` with a minimal valid envelope per `pass1_schema`; read `pass1_schema.py` for required fields.)
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** per B2 §2 — `try json.loads(raw_text)`; on `JSONDecodeError`, `escaped = json_escape_fix(raw_text)`, parse again; success → `syntax_repaired=True`; still failing → re-raise into the existing retry branch. Import `from common.util.json_escape_fix import json_escape_fix` (confirm the exact symbol name in that module).
- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `feat(enrich): wire shared json_escape_fix into call_pass1 (#108)`

### Task 6: Pass-1 `final_status` + flags + aggregation + sidecar persist

**Files:** Modify `ingestion/enrich/pass1_caller.py` (`Pass1CallResult` += `final_status`, `syntax_repaired`, `total_*`, `call_count`, `final_attempt_index`; derive across the attempt loop) + `ingestion/enrich/enrich.py:132-150` (persist into the sidecar `raw_response`); Test `tests/ingestion/test_pass1_robustness.py`

- [ ] **Step 1: Failing tests** — four cases: clean (1 attempt, no repair) → `final_status="clean"`; repair on attempt 1 → `"repaired"`; success only on attempt 2 → `"retried-and-repaired"`; all attempts fail → `Pass1CallError` and the sidecar (or the error path) records `"quarantined"`. Plus: 2-attempt aggregation sums `total_*`, `call_count==2`.
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** per B2 §3 — track outcome through the loop; sum tokens/latency across attempts; set `final_status`; extend `Pass1CallResult`; write the new fields into `SidecarPayload.raw_response` in `enrich.py`.
- [ ] **Step 4: Run** → PASS; run the existing enrich tests for back-compat.
- [ ] **Step 5: Commit** — `feat(enrich): Pass-1 final_status + per-attempt aggregation in sidecar (#108 / B1 delta #2)`

### Task 7: `from_pass1` adapter + `load_run_measurements`

**Files:** Modify `common/measurement.py`; Test `tests/common/test_measurement.py`

- [ ] **Step 1: Failing test** — `from_pass1(sidecar_dict)` → `PassCallMeasurement(pass_="pass1", semantic_ok=None, slug_coerced=False, …)` reading `final_status`/totals from the new sidecar shape. And `load_run_measurements(run_dir)` over a fixture run dir (with both an `enrich/` sidecar and an `llm_resp/` RespStatsRecord + a `measurement_header.json`) → `(header, [pass1_m, pass2_m])` with correct pass split.
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** `from_pass1` + `load_run_measurements` (glob `enrich/<run>/*.json` → from_pass1; `llm_resp/<run>/*.json` → from_pass2; read `measurement_header.json`). Per B1 §3.
- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `feat(measurement): from_pass1 + load_run_measurements (B1)`

---

# PHASE 3 — #109: KPI framework (B3)

### Task 8: `compiler/kpi/processing.py` — scored + diagnostics

**Files:** Create `compiler/kpi/__init__.py`, `compiler/kpi/processing.py`; Test `tests/compiler/kpi/test_processing.py`

- [ ] **Step 1: Failing test** — over a hand-built `list[PassCallMeasurement]` (mix of clean / repaired / retried / quarantined / overrun across P1+P2) assert exact values per B3 §3A:
  - `quarantine_rate` = `quarantined_count * 1e6 / total_tokens`
  - `intervention_burden` = `survivors_with_any_intervention * 1e6 / total_tokens` (survivors = non-quarantined; intervention = `syntax_repaired ∨ slug_coerced ∨ attempts>1 ∨ token_overrun`)
  - `latency` = `sum(total_latency_ms) * 1e6 / total_tokens`
  - diagnostics: `retry_load`, `token_overrun_rate`, `repair_rung_rate`, `signal_noise_ratio` (from header), `semantic_pass_rate` (P2 only)
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** `compute_processing(header, calls) -> {"scored": {...}, "diagnostic": {...}}` exactly per the formulas. `total_tokens` = Σ(`total_input_tokens + total_output_tokens`).
- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `feat(kpi): processing KPIs (quarantine, intervention_burden, latency + diagnostics) (#109)`

### Task 9: `compiler/kpi/graph.py` — alias-aware link-resolution + diagnostics + watched

**Files:** Create `compiler/kpi/graph.py`; Test `tests/compiler/kpi/test_graph.py`

- [ ] **Step 1: Failing test** — over a fixture Kuzu graph + a `compile_result`-shaped dict of emitted `outgoing_links`:
  - `dangling_link_rate`: a link to a **non-existent** slug counts dangling; a link to an **alias** slug (canonical_id set) counts **resolved** (alias-aware); zero emitted links → `None`.
  - watched: `entity_reuse` (share canonical non-summary with ≥2 SUPPORTS), `graph_connectivity` (largest component ratio), `orphan_rate` (from finalize artifacts fixture).
  - diagnostics: `belongs_to_coverage`, `domain_null_rate`, `link_density`, `domain_breadth`.
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** `compute_graph(conn, compile_result, finalize_artifacts) -> {"scored","diagnostic","watched"}`. **Alias-aware:** resolve each target via `kdb_graph.queries.resolve_to_canonical_slugs` (read `queries.py` for its signature) and check the canonical against `active_entity_slugs`. Connectivity = union-find over `links_to_edges`. Use only `kdb_graph.queries` (single door); add a new query fn there if one is missing rather than raw Cypher in `kpi/`.
- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `feat(kpi): graph KPIs — alias-aware link_resolution + watched diagnostics (#109)`

### Task 10: `compiler/kpi/score.py` — Borda mechanism (weights pluggable)

**Files:** Create `compiler/kpi/score.py`; Test `tests/compiler/kpi/test_score.py`

- [ ] **Step 1: Failing test** — given 3 models' scored-KPI dicts, `borda_score(models, weights=None)` ranks each KPI via the reused `tools.benchmark.scorer.borda_normalize` (equal weights when `weights=None`), returns per-model composite + per-KPI ranks; `None`-valued KPIs (e.g. zero-link `link_resolution`) are dropped from that KPI's ranking only.
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** — thin wrapper over `borda_normalize` (import from `tools.benchmark.scorer` — note this is a `tools→compiler`? **NO**: `compiler` must not import `tools`. So instead, the Borda primitive must be reachable from `compiler`. **Resolve in implementation:** if `borda_normalize` lives in `tools/benchmark/scorer.py`, lift the pure function into `common/` (or `compiler/kpi/`) and have `tools` import it, not vice-versa. Confirm the dependency direction against the B.3 contract before wiring.) Weights param defaults to equal; calibration sets them later.
- [ ] **Step 2a: Note** — this task may require a small refactor (lift `borda_normalize` to a leaf). Keep it pure-function; add a parity test that `tools/benchmark` still gets identical results.
- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `feat(kpi): Borda composite mechanism, weights pluggable (#109)`

### Task 11: `--emit-kpis` flag → `measurements.json`

**Files:** Modify `orchestrator/kdb_orchestrate.py` (CLI flag + post-run hook calling `compiler.kpi`); Test `tests/orchestrator/test_emit_kpis.py`

- [ ] **Step 1: Failing test** — with `--emit-kpis`, after a (mocked) run, `benchmark/runs/<run_id>/measurements.json` exists and validates against the B3 §4 shape (`header` + `processing.{scored,diagnostic}` + `graph.{scored,diagnostic,watched}`), `group_key == provider:model:prompt-version`.
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** — gate behind the flag; after finalize + graph build, call `compute_processing` (via `load_run_measurements`) + `compute_graph`; assemble + write the JSON to the repo `benchmark/runs/` dir. Read graph-KPIs from the live graph **before** any reset.
- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `feat(orchestrator): --emit-kpis writes benchmark measurements.json (#109)`

### Task 12: `kdb-benchmark score` + promotion helper

**Files:** Modify `tools/benchmark/cli.py` (new `score` subcommand); Create `tools/benchmark/promotion.py`; Tests `tests/benchmark/test_score.py`, `tests/benchmark/test_promotion.py`

- [ ] **Step 1: Failing tests** — `score` over 3 synthetic `measurements.json` (same `corpus_fingerprint`): picks latest per `group_key`, Borda-ranks scored KPIs, writes `benchmark/scores/<id>.json` + rendered table; rejects a mismatched-fingerprint run. `promotion.evaluate(watched_across_models)` promotes iff `CoV>0.2 ∧ IQR-excludes-near-zero ∧ Spearman ρ<0.7 vs scored` (B3 §6).
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** both. `score` reads measurements, calls `compiler.kpi.score.borda_score`, renders. `promotion.evaluate` is the calibration helper (pure stats).
- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `feat(benchmark): score command + watched-diagnostic promotion rule (#109)`

### Task 13: full-suite gate + docs

- [ ] **Step 1:** Run `pytest -m "not live"` — entire suite green.
- [ ] **Step 2:** Update `docs/CODEBASE_OVERVIEW.md` — add a §7 note that the benchmark was rebuilt (two-family GT-free KPIs, `compiler/kpi/`, weights pending run-1 calibration); Milestone Changelog entry.
- [ ] **Step 3:** Update `docs/TASKS.md` — #108 → closed (telemetry + json_escape_fix landed); #109 → in-progress, "framework landed; weights pending first multi-model run."
- [ ] **Step 4: Commit** — `docs: benchmark framework landed — #108 closed, #109 framework done (weights pending run-1)`

---

## Post-implementation (Joseph fires)
1. Reset sandbox → `kdb-orchestrate --pipeline vault-test --model <A> --emit-kpis` for ≥3 models.
2. `kdb-benchmark score <run-ids>` → first cross-model scorecard.
3. **Calibration** (B3 §9): read spreads → set weights → run promotion rule → finalize scored set → close #109.

## Self-review notes
- **Spec coverage:** B1 §2–§4 → Tasks 1–4,7; B2 §2–§3 → Tasks 5–6; B3 §2–§6 → Tasks 8–12. Calibration (B3 §9) is explicitly post-run, not a task.
- **Dependency risk flagged in Task 10:** `borda_normalize` must be reachable from `compiler` without `compiler→tools` (B.3 violation). Resolve by lifting the pure function to a leaf; parity-test the move.
- **Single-door discipline (Task 9):** graph reads go through `kdb_graph.queries`; add a query fn there if missing, no raw Cypher in `compiler/kpi/`.
