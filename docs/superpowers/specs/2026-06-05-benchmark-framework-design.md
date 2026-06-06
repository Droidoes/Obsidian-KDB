# Benchmark Framework + KPI Formulas (B3 — #109)

**Date:** 2026-06-05 · **Status:** 🟢 ratified design (Joseph approved 2026-06-05)
**Depends on:** B1 `2026-06-05-passcallmeasurement-design.md` · KPI list `2026-06-05-benchmark-kpi-enumeration-brief.md` (v0.2) · architecture `2026-06-03-benchmark-redesign-directions.md`.
**Ledger:** #109.

---

## 0. Scope (what B3 builds vs parks)

**Builds now (fully testable without a live run):** measurement-compute modules (`compiler/kpi/`), exact KPI **formulas**, measurement **emission** (`measurements.json`), the scoring **mechanism** (reuse `scorer.py` Borda), and the scoring **CLI**.

**Parked to post-run-1 calibration** (data-before-principle — these need cross-model spread we can't see yet): the Borda **weights**, the **final scored-set selection**, and **which watched diagnostics get promoted**. The first multi-model run (Joseph fires) is the calibration gate; the post-run finalize is fast and evidence-based.

> **Why parked:** weights are numbers on axes whose cross-model variance is unmeasured. Setting them now would be the blind-anchoring the promote-on-data mechanism exists to avoid. The framework ships; run-1 produces spreads; calibration follows.

## 1. Architecture (recap)

```
kdb-orchestrate --pipeline vault-test --model X --emit-kpis ──┐  (opt-in flag — benchmark mode)
   run over sandbox (Vault-in-place-test-run, 36 src)         │  → builds graphDB
   └─ compiler/kpi computes processing + graph measurements   │  → benchmark/runs/<run_id>/measurements.json
                                                               ▼
kdb-benchmark score <run-id…>  (tools/benchmark — SCORING only)
   read each model's measurements.json → Borda → benchmark/scores/<id>.json
```

- `--emit-kpis` gates measurement emission behind benchmark mode → resolves the directions-doc parked nuance (preserves "always-on telemetry deferred", #8). Emission must run **inside the orchestrate invocation** because the sandbox graphDB is wiped before the next model — graph KPIs can't be computed after reset.
- Storage = **repo** `benchmark/runs/<run_id>/measurements.json` (reset-surviving; computed KPIs + metadata only, **not** raw responses — per the directions-doc storage decision).

## 2. Measurement compute — `compiler/kpi/` (production-importable; honors D25)

- **`processing.py`** — `compute_processing(header, calls: list[PassCallMeasurement]) -> dict`. Reads the B1 projection (`common.measurement.load_run_measurements`). All processing KPIs + diagnostics.
- **`graph.py`** — `compute_graph(conn, compile_result) -> dict`. Reads the resulting graph via `kdb_graph.queries` (single door) + `compile_result.json` for emitted links (hybrid link-resolution). All graph KPIs + diagnostics.
- **`score.py`** — the Borda composite **mechanism** (reuses `tools/benchmark/scorer.py` `borda_normalize`). Weights are a **pluggable parameter, unset until calibration**.

## 3. KPI formulas

Notation: `T` = Σ `total_input_tokens + total_output_tokens` over the relevant call set (per-1M = `× 1e6 / T`).

### 3A. Scored — processing (per-run, P1+P2 combined)
| KPI | formula | dir |
|---|---|---|
| **quarantine_rate** | `|{calls: final_status == 'quarantined'}| × 1e6 / T` | ↓ |
| **intervention_burden** | `|{survivors: syntax_repaired ∨ slug_coerced ∨ attempts>1 ∨ token_overrun}| × 1e6 / T` — **survivors = non-quarantined calls** (disjoint from quarantine_rate → no double-count). **Ungraded** (per-rung detail is diagnostic; severity weights would be arbitrary anchors). | ↓ |
| **latency** | `Σ total_latency_ms × 1e6 / T` (ms per 1M tokens) | ↓ |

### 3B. Scored — graph (per-run)
| KPI | formula | dir |
|---|---|---|
| **link_resolution_rate** (dangling) | `dangling / total_emitted_links` where `total_emitted_links` = Σ `pages[].outgoing_links` over `compile_result.json`; **dangling = target whose `resolve_to_canonical_slugs(target)` ∉ active canonical entity set** (alias-aware — a link to an alias slug resolves, is NOT dangling). `None` when `total_emitted_links == 0` (excluded from this KPI's Borda for that model — do NOT conflate "no links" with "all resolve"; the under-linking signal lives in the density/reuse diagnostics). | ↓ |

> **⚠️ Known limitation (drives calibration):** `link_resolution_rate` as dangling/total **rewards under-linking** — a model emitting one safe link scores 100%. It is the *only* scored graph KPI (BELONGS_TO demoted) and **must not stand alone**: at calibration it is co-interpreted with the watched **density** + **reuse** diagnostics (a clean resolution rate is only meaningful at adequate link volume). This is a primary reason scored-graph finalization is post-run-1.

### 3C. Diagnostics (emitted, not scored)
- **processing:** `retry_load` (Σ min(MAX, attempts−1) / (N·MAX), ratio) · `token_overrun_rate` (per-1M) · `repair_rung_rate` (per-1M) · `cost` ($/1k source-words) · `signal_noise_ratio` (P1) · `semantic_pass_rate` (P2 ratio)
- **graph:** `belongs_to_coverage` (ratio — ~1.0, dead) · `domain_null_rate` (ratio) · `link_density` (LINKS_TO/entity) · `supports_density` (entities/source) · `domain_breadth` (distinct domains ÷ 23)

### 3D. Watched diagnostics (emitted; promotion candidates post-run-1)
- **entity_reuse / fragmentation** — share of canonical non-summary entities with ≥2 SUPPORTS sources (↑)
- **graph_connectivity** — largest connected-component ratio over LINKS_TO (↑)
- **orphan_rate** — from finalize artifacts (`orphans_marked`/`reaped`/`retracted`), not live graph (↓)
- **entity_search_key_resolution** — P1 keys resolving to active entities ÷ keys emitted (↑)

## 4. Emission — `measurements.json`
Per run, written by the `--emit-kpis` path:
```json
{
  "header": { …RunMeasurementHeader… , "group_key": "<provider>:<model>:<p1_pv>/<p2_pv>" },
  "processing": { "scored": {…}, "diagnostic": {…} },
  "graph":      { "scored": {…}, "diagnostic": {…}, "watched": {…} }
}
```
- **group_key** (grouping for "latest run per model") = `provider:model:prompt-version` (prompt iteration is a comparison axis — lean over bare `model`).
- **corpus_fingerprint** (header) = `sha256` of the sorted `{source_id: content_hash}` set — the `score` step only ranks same-fingerprint cohorts.

## 5. Scoring — `tools/benchmark/` (scoring only)
- **`kdb-benchmark score <run-id…>`** → loads each run's `measurements.json`, takes the **latest per group_key** (no historical averaging), Borda-ranks each **scored** KPI (`borda_normalize`, reused), applies weights (**from the calibration config — empty/equal until run-1**), writes `benchmark/scores/<id>.json` + a rendered table.
- Diagnostics + watched are **carried into the scorecard for reading**, not ranked.
- The Borda/scorecard spine, run-dir layout, and `borda_normalize` are the ~20% salvage from the old engine, re-pointed at the new KPI set.

## 6. Promotion mechanism (applied at post-run-1 calibration)
A watched diagnostic promotes to scored iff, across the first ≥3-model cohort:
- **CoV > 0.2** (cross-model σ/μ) — *and* —
- **absolute-spread floor:** IQR excludes a near-zero band (guards CoV's instability as μ→0, where clean rates cluster) — *and* —
- **low redundancy:** Spearman ρ < 0.7 vs every already-scored KPI.

## 7. Test plan (TDD — all runnable now)
- `compute_processing` over a fixed `PassCallMeasurement` list → exact quarantine/intervention/latency + diagnostics; survivors-disjoint-from-quarantine asserted.
- `compute_graph`: link_resolution **alias-aware** (a link to an alias slug counts resolved, not dangling); `None` on zero-link model; density/reuse/connectivity over a fixture graph.
- emission: `--emit-kpis` writes a schema-valid `measurements.json` (header + processing + graph).
- scoring: `score` over 3 synthetic `measurements.json` → Borda ranks per KPI; same-fingerprint gate; latest-per-group_key selection.
- promotion: synthetic 3-model spreads → CoV+floor+ρ rule promotes/holds correctly.
- back-compat: `scorer.borda_normalize` reused unchanged.

## 8. Framework prerequisites (from B1 — land first)
1. discarded-attempt aggregation (P1+P2 producer delta)
2. `PassCallMeasurement` projection + `load_run_measurements` (`common/measurement.py`)
3. per-pass denominator header

## 9. Post-run-1 calibration (the parked finalize)
After Joseph fires the first ≥3-model cohort:
1. read the cross-model spreads from the scorecards;
2. set **weights** on the scored KPIs (incl. the graph/processing balance + the latency↔graph-quality correlation caveat — down-weight latency if the slowest model builds the best graph);
3. run the **promotion rule** → promote watched graph diagnostics that earn it (esp. density/reuse, which `link_resolution` needs co-interpreted);
4. finalize the scored set + write the weights config.
This is fast, evidence-based, and the only step that needs live data.
