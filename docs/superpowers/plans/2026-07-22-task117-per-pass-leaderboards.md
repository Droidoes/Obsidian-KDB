# Task #117 — Per-Pass Leaderboards Implementation Plan

**Version:** v1.4 (2026-07-22) — **RATIFIED by Joseph 2026-07-22.** v1.0 + author self-review (5) + Codex R4 (7/7) + R5 (4/4) + R6 (4/4) + R7 (3/3) folds; R8: no blocking findings

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `kdb-benchmark score` writes Pass-1 and Pass-2 split leaderboards alongside the untouched combined board, rebuilt from existing run data.

**Architecture:** Per-pass processing KPIs are recomputed at score time from each row's `run_state/` (`load_run_measurements_with_stats` → `compute_processing`), mapped onto canonical KPI names, and scored through the existing §6 `score_models` machinery; graph KPIs come from `measurements.json`. Rows failing the per-board completeness contract render `unranked`, never pro-rata on missing evidence. Spec: `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md` (v0.3.1 ratified).

**Tech Stack:** Python 3.10+, pytest. No new dependencies.

## Global Constraints

- Branch: `feat/117-per-pass-leaderboards` (off `main` @ `6a5b9a1`). Do not edit the `feat/115-pass2-contract` branch. **File overlap is expected:** #115 (`e9ca323`) also modified `common/measurement.py` + `common/tests/test_measurement.py` (pass2 stamp fields + setdefault normalization). Whichever branch merges second reconciles: preserve #115's `pass2_system_prompt_sha256` field + historical-header defaults AND #117's forward-compat header filtering, `cost_usd` field, and stats loader; run the combined measurement + orchestrator suites after the rebase/merge.
- No pipeline behavior changes: only `common/measurement.py`, `compiler/kpi/processing.py`, and `tools/benchmark/*` are modified. The production loader `load_run_measurements` stays strict (Task 2 keeps malformed=raise on the production path; tolerance exists only in the opt-in stats loader used at score time).
- Main board byte-identical (D-117-1): `_render_leaderboard_md`/`_render_score_table` default paths unchanged; existing `tools/benchmark/tests/test_score.py` passes unmodified.
- Conventional commits with task ref, e.g. `feat(benchmark): #117 — …`. **Every commit requires Joseph's explicit approval.**
- Tests run via `.venv/bin/python -m pytest <path> -v`; full-suite counts via bare `pytest`.
- Spec decisions D-117-1..D-117-10 (v0.3.1) are the contract; where this plan and the spec disagree, the spec wins and the plan is fixed.

---

### Task 1: `cost_usd` on `PassCallMeasurement` + header-key filtering

**Files:**
- Modify: `common/measurement.py:41` (dataclass field), `:84-110` (`from_pass1`), `:123-163` (`from_pass2`), `:210-212` (header construction)
- Test: `common/tests/test_measurement.py`

**Interfaces:**
- Produces: `PassCallMeasurement.cost_usd: float | None` (default `None`). `from_pass1` reads sidecar top-level `cost_usd`; `from_pass2` reads record `cost_usd`; absent → `None`. `load_run_measurements` tolerates unknown header keys (forward-compat with the #115 stamp fields on baseline-run headers).

- [ ] **Step 1: Write the failing tests** (append to `common/tests/test_measurement.py`)

```python
def test_from_pass1_projects_cost_usd():
    sidecar = {
        "source_id": "KDB/raw/a.md",
        "outcome": "enriched",
        "request": {"provider": "p", "model": "m"},
        "raw_response": {"final_status": "clean", "call_count": 1,
                         "total_input_tokens": 10, "total_output_tokens": 5,
                         "total_latency_ms": 3},
        "parsed_envelope": {"prompt_version": "1.2.0"},
        "cost_usd": 0.0123,
    }
    m = PassCallMeasurement.from_pass1(sidecar, run_id="r1")
    assert m.cost_usd == pytest.approx(0.0123)


def test_from_pass1_missing_cost_projects_none():
    sidecar = {
        "source_id": "KDB/raw/a.md",
        "outcome": "enriched",
        "request": {"provider": "p", "model": "m"},
        "raw_response": {"final_status": "clean"},
    }
    m = PassCallMeasurement.from_pass1(sidecar, run_id="r1")
    assert m.cost_usd is None


def test_from_pass2_projects_cost_usd():
    rec = {"run_id": "r1", "source_id": "s", "provider": "p", "model": "m",
           "final_status": "clean", "cost_usd": 0.5}
    m = PassCallMeasurement.from_pass2(rec)
    assert m.cost_usd == pytest.approx(0.5)


def test_load_run_measurements_tolerates_unknown_header_keys(tmp_path):
    (tmp_path / "measurement_header.json").write_text(json.dumps({
        "run_id": "r1", "corpus_fingerprint": "fp",
        "pass1_prompt_version": "1", "pass2_prompt_version": "2.0.0",
        "scanned": 1, "to_compile": 1, "signal": 1, "noise": 0,
        "p1_attempted": 1, "p2_attempted": 1,
        "pass2_system_prompt_sha256": "abc123",   # #115 stamp — unknown pre-merge
    }))
    header, calls = load_run_measurements(tmp_path)
    assert header.run_id == "r1"
    assert calls == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest common/tests/test_measurement.py -v -k "cost_usd or unknown_header"`
Expected: FAIL (`TypeError: __init__() got an unexpected keyword argument 'cost_usd'` / `RunMeasurementHeader` rejects the unknown key).

- [ ] **Step 3: Implement**

In `common/measurement.py`:
- Add after `boundary_recovered: bool = False` (line 41):
```python
    cost_usd: float | None = None
```
- In `from_pass1` return, add `cost_usd=sidecar.get("cost_usd"),` and extend the docstring bullet list with: `- cost_usd: sidecar top-level; absent (or #110-deferred failed-source 0.0) projects as-is — the KPI layer decides what zero means.`
- In `from_pass2` return, add `cost_usd=rec.get("cost_usd"),`.
- Replace header construction (lines 210-212):
```python
    header_path = run_dir / "measurement_header.json"
    header_data = json.loads(header_path.read_text(encoding="utf-8"))
    # Forward-compat: tolerate header keys newer than this dataclass (e.g. the
    # #115 pass2 stamp fields) so score-time recompute works across releases.
    known = {f.name for f in dataclasses.fields(RunMeasurementHeader)}
    header = RunMeasurementHeader(
        **{k: v for k, v in header_data.items() if k in known})
```
  Add `import dataclasses` to the module imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest common/tests/test_measurement.py -v`
Expected: all PASS (new + existing).

- [ ] **Step 5: Commit (Joseph's gate)**

```bash
git add common/measurement.py common/tests/test_measurement.py
git commit -m "feat(common): #117 — PassCallMeasurement.cost_usd + forward-compat header loading"
```

---

### Task 2: `load_run_measurements_with_stats` (completeness evidence)

**Files:**
- Modify: `common/measurement.py:187-237` (loader)
- Test: `common/tests/test_measurement.py`

**Interfaces:**
- Consumes: Task 1's filtered header construction.
- Produces: `load_run_measurements_with_stats(run_dir) -> (RunMeasurementHeader, list[PassCallMeasurement], dict)` with stats keys `pass1_dir_exists, pass2_dir_exists, pass1_identified, pass1_skipped, pass1_unique_source_ids, pass1_malformed, pass2_records, pass2_malformed`. `load_run_measurements` becomes a thin wrapper (same return shape as today).

- [ ] **Step 1: Write the failing tests** (add `load_run_measurements_with_stats` to the test module's imports from `common.measurement`)

```python
def _write_sidecar(d, source_id, outcome="enriched"):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{source_id.replace('/', '_')}.json").write_text(json.dumps({
        "source_id": source_id, "outcome": outcome,
        "request": {"provider": "p", "model": "m"},
        "raw_response": {"final_status": "clean", "call_count": 1},
    }))


def _write_header(tmp_path, **over):
    h = {"run_id": "r", "corpus_fingerprint": "fp", "pass1_prompt_version": "1",
         "pass2_prompt_version": "", "scanned": 3, "to_compile": 3, "signal": 2,
         "noise": 1, "p1_attempted": 3, "p2_attempted": 2}
    h.update(over)
    (tmp_path / "measurement_header.json").write_text(json.dumps(h))


def test_stats_count_identified_skipped_unique(tmp_path):
    _write_header(tmp_path)
    _write_sidecar(tmp_path / "pass1", "a.md")
    _write_sidecar(tmp_path / "pass1", "b.md", outcome="enrich_skipped")
    _write_sidecar(tmp_path / "pass1", "c.md")
    header, calls, stats = load_run_measurements_with_stats(tmp_path)
    assert stats["pass1_identified"] == 3
    assert stats["pass1_skipped"] == 1
    assert stats["pass1_unique_source_ids"] == 3
    assert len([c for c in calls if c.pass_ == "pass1"]) == 2


def test_stats_count_malformed_and_missing_dirs(tmp_path):
    _write_header(tmp_path)
    (tmp_path / "pass1").mkdir()
    (tmp_path / "pass1" / "broken.json").write_text("{not json")
    _h, _c, stats = load_run_measurements_with_stats(tmp_path)
    assert stats["pass1_malformed"] == 1
    assert stats["pass1_dir_exists"] is True
    assert stats["pass2_dir_exists"] is False
    assert stats["pass2_records"] == 0


def test_stats_count_structurally_invalid_record_as_malformed(tmp_path):
    """Valid JSON, invalid record shape → malformed in the tolerant loader,
    not a crash that aborts all three boards."""
    _write_header(tmp_path)
    d = tmp_path / "pass1"
    d.mkdir()
    (d / "bad.json").write_text(json.dumps({
        "source_id": "a.md", "raw_response": "not-a-dict"}))  # from_pass1 raises
    _h, calls, stats = load_run_measurements_with_stats(tmp_path)
    assert stats["pass1_malformed"] == 1
    assert calls == []


def test_production_loader_stays_strict_on_malformed(tmp_path):
    """Regression guard: the production path (emit_run_kpis) must keep
    failing safely — malformed files raise, never silently skipped."""
    _write_header(tmp_path)
    (tmp_path / "pass1").mkdir()
    (tmp_path / "pass1" / "broken.json").write_text("{not json")
    with pytest.raises(json.JSONDecodeError):
        load_run_measurements(tmp_path)


def test_production_loader_stays_strict_on_invalid_record(tmp_path):
    _write_header(tmp_path)
    d = tmp_path / "pass1"
    d.mkdir()
    (d / "bad.json").write_text(json.dumps({
        "source_id": "a.md", "raw_response": "not-a-dict"}))
    with pytest.raises((AttributeError, TypeError, KeyError, ValueError)):
        load_run_measurements(tmp_path)


def test_load_run_measurements_wrapper_unchanged_shape(tmp_path):
    _write_header(tmp_path)
    header, calls = load_run_measurements(tmp_path)   # 2-tuple, as today
    assert header.run_id == "r" and calls == []


def test_stats_loader_rejects_wrong_typed_header_field(tmp_path):
    """R6-F1: a string where an int belongs → TypeError at load time, so the
    board builder marks ONLY this row unranked."""
    _write_header(tmp_path, p1_attempted="36")
    with pytest.raises(TypeError):
        load_run_measurements_with_stats(tmp_path)


def test_stats_loader_counts_wrong_typed_sidecar_field(tmp_path):
    """R6-F1: string token count → counted malformed, not a mid-board crash."""
    _write_header(tmp_path)
    d = tmp_path / "pass1"
    d.mkdir()
    (d / "a.json").write_text(json.dumps({
        "source_id": "a.md", "outcome": "enriched",
        "request": {"provider": "p", "model": "m"},
        "raw_response": {"final_status": "clean", "call_count": 1,
                         "total_input_tokens": "100"}}))   # string, not int
    _h, calls, stats = load_run_measurements_with_stats(tmp_path)
    assert stats["pass1_malformed"] == 1
    assert calls == []


def test_strict_loader_raises_on_wrong_typed_header(tmp_path):
    """R7-F2: the production path fails safely on wrong-typed header fields —
    same exception class emit would hit today, never a silent pass-through."""
    _write_header(tmp_path, scanned="4")
    with pytest.raises(TypeError):
        load_run_measurements(tmp_path)


def test_strict_loader_raises_on_wrong_typed_measurement(tmp_path):
    """R7-F2: wrong-typed record fields raise on the strict path too."""
    _write_header(tmp_path)
    d = tmp_path / "pass1"
    d.mkdir()
    (d / "a.json").write_text(json.dumps({
        "source_id": "a.md", "outcome": "enriched",
        "request": {"provider": "p", "model": "m"},
        "raw_response": {"final_status": "clean", "call_count": 1,
                         "total_latency_ms": "fast"}}))
    with pytest.raises(TypeError):
        load_run_measurements(tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest common/tests/test_measurement.py -v -k "stats or wrapper or strict"`
Expected: FAIL (`ImportError` — `load_run_measurements_with_stats` does not exist).

- [ ] **Step 3: Implement** — replace the loader section in `common/measurement.py`. **The production path stays strict**: tolerance exists only behind the stats loader, and only score-time pass-board building opts in.

```python
_HEADER_INT_FIELDS = ("scanned", "to_compile", "signal", "noise",
                      "p1_attempted", "p2_attempted")


def _validate_header_types(header: "RunMeasurementHeader") -> None:
    """Type guard (R6-F1/R7-F2, BOTH loader paths): header numeric fields
    must be real ints (bool excluded) — else KPI computation fails mid-board
    outside every guard. Strict path: raises (emit fails safely, as today).
    Tolerant path: raises so the board builder marks the row unranked."""
    for f in _HEADER_INT_FIELDS:
        v = getattr(header, f)
        if not isinstance(v, int) or isinstance(v, bool):
            raise TypeError(
                f"header field {f!r} must be int, got {type(v).__name__}")


_MEASUREMENT_INT_FIELDS = ("attempts", "call_count", "total_input_tokens",
                           "total_output_tokens", "total_latency_ms")


def _valid_measurement(m: "PassCallMeasurement") -> bool:
    """Type guard (R6-F1/R7-F2, BOTH loader paths): KPI-relevant numeric
    fields must be real ints; cost_usd None or numeric. Strict path raises
    TypeError on False; tolerant path counts the record malformed."""
    for f in _MEASUREMENT_INT_FIELDS:
        v = getattr(m, f)
        if not isinstance(v, int) or isinstance(v, bool):
            return False
    return m.cost_usd is None or isinstance(m.cost_usd, (int, float))


def _load_run_measurements(
    run_dir: Path,
    *,
    tolerate_malformed: bool,
    collect_stats: bool,
) -> tuple["RunMeasurementHeader", list["PassCallMeasurement"], dict]:
    """Shared loader core.

    tolerate_malformed=False (production): any malformed/unloadable file
    raises, exactly as the pre-#117 loader did — emit_run_kpis fails safely
    rather than emitting KPIs from partial evidence.
    tolerate_malformed=True (score-time stats loader): bad files are counted
    in stats["*_malformed"] and skipped, so the #117 completeness contract
    can mark the row unranked instead of aborting all three boards.
    "Malformed" covers unparseable JSON AND structurally valid records that
    fail projection (KeyError/TypeError/AttributeError/ValueError).
    """
    header_path = run_dir / "measurement_header.json"
    header_data = json.loads(header_path.read_text(encoding="utf-8"))
    # Forward-compat: tolerate header keys newer than this dataclass (e.g. the
    # #115 pass2 stamp fields) so score-time recompute works across releases.
    known = {f.name for f in dataclasses.fields(RunMeasurementHeader)}
    header = RunMeasurementHeader(
        **{k: v for k, v in header_data.items() if k in known})
    run_id = header.run_id
    # R6-F1/R7-F2: dataclass construction does NOT validate types — a
    # wrong-typed numeric header field would fail later inside KPI
    # computation, outside every guard. Validated on BOTH paths: strict
    # raises TypeError (same exception class emit would hit today — the
    # "fails safely" contract is preserved), tolerant marks the row unranked.
    _validate_header_types(header)

    stats = {
        "pass1_dir_exists": (run_dir / "pass1").is_dir(),
        "pass2_dir_exists": (run_dir / "pass2").is_dir(),
        "pass1_identified": 0, "pass1_skipped": 0,
        "pass1_unique_source_ids": 0, "pass1_malformed": 0,
        "pass2_records": 0, "pass2_malformed": 0,
    }
    _PROJECTION_ERRORS = (json.JSONDecodeError, UnicodeDecodeError,
                          KeyError, TypeError, AttributeError, ValueError)

    pass1: list[PassCallMeasurement] = []
    source_ids: set[str] = set()
    pass1_dir = run_dir / "pass1"
    if pass1_dir.is_dir():
        for p in sorted(pass1_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                identified = "source_id" in data and "raw_response" in data
                if identified:
                    stats["pass1_identified"] += 1
                    source_ids.add(data["source_id"])
            except _PROJECTION_ERRORS:
                if not tolerate_malformed:
                    raise
                stats["pass1_malformed"] += 1
                continue
            if not identified:
                continue
            if data.get("outcome") == "enrich_skipped":
                stats["pass1_skipped"] += 1
                continue
            try:
                m = PassCallMeasurement.from_pass1(data, run_id=run_id)
            except _PROJECTION_ERRORS:
                if not tolerate_malformed:
                    raise
                stats["pass1_malformed"] += 1
                continue
            if not _valid_measurement(m):           # R6-F1: wrong-typed fields
                if not tolerate_malformed:          # R7-F2: strict raises too
                    raise TypeError(
                        f"pass1 measurement for {m.source_id!r} has "
                        "wrong-typed numeric fields")
                stats["pass1_malformed"] += 1
                continue
            pass1.append(m)
    stats["pass1_unique_source_ids"] = len(source_ids)

    pass2: list[PassCallMeasurement] = []
    pass2_dir = run_dir / "pass2"
    if pass2_dir.is_dir():
        for p in sorted(pass2_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                m = PassCallMeasurement.from_pass2(data)
            except _PROJECTION_ERRORS:
                if not tolerate_malformed:
                    raise
                stats["pass2_malformed"] += 1
                continue
            if not _valid_measurement(m):           # R6-F1 / R7-F2
                if not tolerate_malformed:
                    raise TypeError(
                        f"pass2 measurement for {m.source_id!r} has "
                        "wrong-typed numeric fields")
                stats["pass2_malformed"] += 1
                continue
            stats["pass2_records"] += 1
            pass2.append(m)

    if not collect_stats:
        stats = {}
    return header, pass1 + pass2, stats


def load_run_measurements(
    run_dir: Path,
) -> tuple["RunMeasurementHeader", list["PassCallMeasurement"]]:
    """Load all measurement projections for one run — STRICT (production
    path): malformed files raise, as before #117."""
    header, measurements, _ = _load_run_measurements(
        run_dir, tolerate_malformed=False, collect_stats=False)
    return header, measurements


def load_run_measurements_with_stats(
    run_dir: Path,
) -> tuple["RunMeasurementHeader", list["PassCallMeasurement"], dict]:
    """Score-time variant (Task #117): tolerant of malformed files (counted
    in stats) and returns per-pass load statistics for the D-117-5
    completeness contract. Stats keys: pass1_dir_exists, pass2_dir_exists,
    pass1_identified, pass1_skipped, pass1_unique_source_ids,
    pass1_malformed, pass2_records, pass2_malformed."""
    return _load_run_measurements(
        run_dir, tolerate_malformed=True, collect_stats=True)
```

Note: the strict path's malformed-JSON behavior intentionally raises the same `json.JSONDecodeError` the pre-#117 loader raised — no production behavior change.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest common/tests/test_measurement.py orchestrator/tests -v`
Expected: PASS (orchestrator emit tests exercise the wrapper).

- [ ] **Step 5: Commit (Joseph's gate)**

```bash
git add common/measurement.py common/tests/test_measurement.py
git commit -m "feat(common): #117 — load_run_measurements_with_stats for the completeness contract"
```

---

### Task 3: Per-pass splits + cost diagnostics in `compute_processing`

**Files:**
- Modify: `compiler/kpi/processing.py:82-132` (diagnostic section)
- Test: `compiler/tests/test_kpi_processing.py`

**Interfaces:**
- Consumes: `PassCallMeasurement.cost_usd` (Task 1).
- Produces: eight new diagnostic keys — `recovery_rate_pass1/2`, `retry_load_pass1/2`, `cost_usd_pass1/2`, `cost_unknown_calls_pass1/2`. Existing keys unchanged. Diagnostic tier grows 9 → 17 keys.

- [ ] **Step 1: Write the failing tests** (fixture header/calls pattern per the file's existing `_call` helper and the `HEADER` / `ALL_CALLS` module fixtures; values computed as literals from the module docstring fixture C1–C5)

First, extend the file's `_call` helper with a cost kwarg (needed by the cost tests):

```python
def _call(
    *,
    pass_: str,
    # ... existing kwargs unchanged ...
    semantic_ok: bool | None = None,
    cost_usd: float | None = None,          # NEW — passed to the constructor
) -> PassCallMeasurement:
```

Then the new tests:

```python
class TestPerPassSplits:
    # Fixture math (C1..C5 from the module docstring):
    #   pass1: C1 clean (T=700), C2 repaired+retried (T=900)   → T_pass1=1600
    #   pass2: C3 clean (T=500), C4 quarantined (T=450),
    #          C5 slug_coerced+overrun (T=300)                  → T_pass2=1250
    def test_recovery_rate_pass1(self):
        r = compute_processing(HEADER, ALL_CALLS)["diagnostic"]
        # C2 only: 1 * 1e6 / 1600
        assert r["recovery_rate_pass1"] == pytest.approx(1e6 / 1600)

    def test_recovery_rate_pass2(self):
        r = compute_processing(HEADER, ALL_CALLS)["diagnostic"]
        # C5 only (C4 quarantined-excluded): 1 * 1e6 / 1250
        assert r["recovery_rate_pass2"] == pytest.approx(1e6 / 1250)

    def test_token_weighted_recombination(self):
        r = compute_processing(HEADER, ALL_CALLS)
        combined = r["scored"]["recovery_rate"]          # scored tier, not diagnostic
        d = r["diagnostic"]
        recombined = (d["recovery_rate_pass1"] * 1600
                      + d["recovery_rate_pass2"] * 1250) / (1600 + 1250)
        assert combined == pytest.approx(recombined)

    def test_retry_load_pass_split_and_recombination(self):
        d = compute_processing(HEADER, ALL_CALLS)["diagnostic"]
        assert d["retry_load_pass1"] == pytest.approx(1 / 2)   # C2: 1 extra / 2 calls
        assert d["retry_load_pass2"] == pytest.approx(0.0)
        assert d["retry_load"] == pytest.approx(
            (d["retry_load_pass1"] * 2 + d["retry_load_pass2"] * 3) / 5)

    def test_empty_pass_yields_none(self):
        d = compute_processing(HEADER, [c for c in ALL_CALLS
                                        if c.pass_ == "pass1"])["diagnostic"]
        assert d["recovery_rate_pass2"] is None
        assert d["retry_load_pass2"] is None
        assert d["cost_usd_pass2"] is None
        assert d["cost_unknown_calls_pass2"] is None


class TestCostDiagnostics:
    def _calls_with_cost(self):
        return [
            _call(pass_="pass1", total_input_tokens=100, total_output_tokens=50,
                  total_latency_ms=10, cost_usd=0.01),   # priced
            _call(pass_="pass1", total_input_tokens=100, total_output_tokens=50,
                  total_latency_ms=10, cost_usd=0.0),    # tokens, no cost → unknown
            _call(pass_="pass1", total_input_tokens=100, total_output_tokens=50,
                  total_latency_ms=10, cost_usd=None),   # absent → unknown
            _call(pass_="pass1", total_input_tokens=0, total_output_tokens=0,
                  total_latency_ms=0, cost_usd=None),    # no tokens → not unknown
            _call(pass_="pass2", total_input_tokens=200, total_output_tokens=100,
                  total_latency_ms=10, cost_usd=0.30),
        ]

    def test_cost_sums_priced_calls_only(self):
        d = compute_processing(HEADER, self._calls_with_cost())["diagnostic"]
        assert d["cost_usd_pass1"] == pytest.approx(0.01)
        assert d["cost_usd_pass2"] == pytest.approx(0.30)

    def test_unknown_counts_unpriced_token_calls(self):
        d = compute_processing(HEADER, self._calls_with_cost())["diagnostic"]
        assert d["cost_unknown_calls_pass1"] == 2      # 0.0-with-tokens + None
        assert d["cost_unknown_calls_pass2"] == 0

    def test_diagnostic_has_exactly_seventeen_keys(self):
        d = compute_processing(HEADER, ALL_CALLS)["diagnostic"]
        assert set(d) == {
            "retry_load", "token_overrun_rate", "repair_rung_rate",
            "semantic_pass_rate", "signal_noise_ratio",
            "quarantine_rate_pass1", "quarantine_rate_pass2",
            "latency_pass1", "latency_pass2",
            "recovery_rate_pass1", "recovery_rate_pass2",
            "retry_load_pass1", "retry_load_pass2",
            "cost_usd_pass1", "cost_usd_pass2",
            "cost_unknown_calls_pass1", "cost_unknown_calls_pass2",
        }
```

(`test_diagnostic_has_exactly_nine_keys` at line 133 is **replaced** by the seventeen-key test above — 9 existing + 8 new = 17.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest compiler/tests/test_kpi_processing.py -v`
Expected: FAIL (`KeyError: 'recovery_rate_pass1'`, nine-keys assertion mismatch).

- [ ] **Step 3: Implement** — in `compiler/kpi/processing.py`, after the existing per-pass quarantine block (line 117), add:

```python
    # Per-pass recovery split — same survivor-retry/repair predicate as the
    # combined recovery_rate, partitioned by pass (#117).
    n_recovery_pass1 = sum(
        1 for c in pass1_calls
        if c.final_status != "quarantined"
        and (c.syntax_repaired or c.slug_coerced or c.boundary_recovered or c.attempts > 1)
    )
    n_recovery_pass2 = sum(
        1 for c in pass2_calls
        if c.final_status != "quarantined"
        and (c.syntax_repaired or c.slug_coerced or c.boundary_recovered or c.attempts > 1)
    )

    retry_load_pass1: float | None = (
        sum(max(0, c.attempts - 1) for c in pass1_calls) / len(pass1_calls)
        if pass1_calls else None
    )
    retry_load_pass2: float | None = (
        sum(max(0, c.attempts - 1) for c in pass2_calls) / len(pass2_calls)
        if pass2_calls else None
    )

    # Cost split (#117 D-117-3/D-117-8): sums over PRICED calls only; calls
    # with token usage but no positive cost attribution (unpriced, or
    # failed-before-attribution — the #110 deferred item) count as unknown,
    # never as $0.
    def _cost_split(calls: list[PassCallMeasurement]) -> tuple[float | None, int | None]:
        if not calls:
            return None, None
        priced = sum(c.cost_usd for c in calls if c.cost_usd and c.cost_usd > 0)
        unknown = sum(
            1 for c in calls
            if (c.total_input_tokens + c.total_output_tokens) > 0
            and not (c.cost_usd and c.cost_usd > 0)
        )
        return priced, unknown

    cost_pass1, unknown_pass1 = _cost_split(pass1_calls)
    cost_pass2, unknown_pass2 = _cost_split(pass2_calls)
```

and extend the `diagnostic` dict with:

```python
        "recovery_rate_pass1": _rate(n_recovery_pass1, T_pass1),
        "recovery_rate_pass2": _rate(n_recovery_pass2, T_pass2),
        "retry_load_pass1": retry_load_pass1,
        "retry_load_pass2": retry_load_pass2,
        "cost_usd_pass1": cost_pass1,
        "cost_usd_pass2": cost_pass2,
        "cost_unknown_calls_pass1": unknown_pass1,
        "cost_unknown_calls_pass2": unknown_pass2,
```

Also update the module docstring's diagnostic key list.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest compiler/tests/test_kpi_processing.py compiler/tests -v`
Expected: PASS.

- [ ] **Step 5: Commit (Joseph's gate)**

```bash
git add compiler/kpi/processing.py compiler/tests/test_kpi_processing.py
git commit -m "feat(compiler): #117 — per-pass recovery/retry/cost diagnostics in compute_processing"
```

---

### Task 4: `tools/benchmark/pass_boards.py` — board builder

**Files:**
- Create: `tools/benchmark/pass_boards.py`
- Test: `tools/benchmark/tests/test_pass_boards.py` (new)

**Interfaces:**
- Consumes: `load_run_measurements_with_stats` (Task 2), `compute_processing` splits (Task 3), `score_models`/`TOP_WEIGHTS`/`GRAPH_WEIGHTS` (existing).
- Produces (consumed by Task 6):
  - `build_pass_board(models_to_rundir: dict[str, str], runs_root: Path, pass_: str, *, graph_scored_by_model: dict, fallback_diag_by_model: dict, header_by_model: dict | None = None) -> dict`
  - Board payload: `{models, board_scope, effective_top_weights, ranking, unranked, top_weights, graph_weights, penalty_params, updated_at}` (`updated_at` injected by caller).
  - Ranking row: `{model, rank, composite, composite_pre_penalty, penalty, weakest_kpi, graph_score, per_kpi_borda, measurement_source, raw_values}`.
  - Unranked row: `{model, run_dir, measurement_source, missing_kpis, completeness_errors, raw_values}` — `missing_kpis` holds canonical KPI names only; contract violations live in `completeness_errors`.
  - `effective_top_weights(pass_) -> dict`; constants `SRC_RECOMPUTED="run_state_recomputed"`, `SRC_PARTIAL="run_state_partial"`, `SRC_FALLBACK="measurements_fallback"`.

- [ ] **Step 1: Write the failing tests** (`tools/benchmark/tests/test_pass_boards.py`)

Fixture helper (used by every test; mirrors real sidecar/record shapes):

```python
"""Tests for tools.benchmark.pass_boards (Task #117, spec v0.3.1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.benchmark.pass_boards import (
    SRC_FALLBACK, SRC_PARTIAL, SRC_RECOMPUTED,
    build_pass_board, effective_top_weights,
)


def _write_run(runs_root: Path, run_dir: str, *, model: str, provider: str = "prov",
               release: str = "", p1: int = 4, signal: int = 3, noise: int = 1,
               failed_p1: int = 0, pass2_records: int | None = None,
               cost_p1: float = 0.01, latency_ms_p1: int = 100,
               tokens_p1: int = 100,
               quarantine_p2: bool = False, graph: dict | None = None,
               skip_sidecar: int | None = None, malformed_p1: bool = False,
               dup_source: bool = False, no_run_state: bool = False):
    """Write measurements.json + run_state/ for one synthetic run.

    p1 sources: s0..s{p1-1} (first `noise` get outcome enriched+noise is
    irrelevant here — disposition comes from the header counts; sidecars just
    need to exist and load). pass2 records default to `signal`.
    """
    d = runs_root / run_dir
    d.mkdir(parents=True, exist_ok=True)
    p2 = signal if pass2_records is None else pass2_records
    (d / "measurements.json").write_text(json.dumps({
        "header": {"run_id": run_dir, "provider": provider, "model": model,
                   "release_version": release, "corpus_fingerprint": "fp",
                   "pass1_prompt_version": "1", "pass2_prompt_version": "",
                   "scanned": p1, "to_compile": p1, "signal": signal,
                   "noise": noise, "p1_attempted": p1, "p2_attempted": signal},
        "processing": {"scored": {}, "diagnostic": {
            "quarantine_rate_pass1": 0.0, "latency_pass1": 111.0,
            "quarantine_rate_pass2": 0.0, "latency_pass2": 222.0}},
        "graph": {"scored": graph or {"entity_reuse": 0.1, "graph_connectivity": 0.2,
                                      "link_density": 2.0, "supports_density": 5.0},
                  "watched": {}, "diagnostic": {}},
    }))
    if no_run_state:
        return
    rs = d / "run_state"
    (rs / "pass1").mkdir(parents=True)
    (rs / "pass2").mkdir(parents=True)
    (rs / "measurement_header.json").write_text(json.dumps({
        "run_id": run_dir, "corpus_fingerprint": "fp", "pass1_prompt_version": "1",
        "pass2_prompt_version": "", "scanned": p1, "to_compile": p1,
        "signal": signal, "noise": noise, "p1_attempted": p1,
        "p2_attempted": signal}))
    n_sidecars = p1 if skip_sidecar is None else skip_sidecar
    for i in range(n_sidecars):
        sid = "src0.md" if (dup_source and i > 0) else f"src{i}.md"
        (rs / "pass1" / f"s{i}.json").write_text(json.dumps({
            "source_id": sid,
            "outcome": "enriched",
            "request": {"provider": provider, "model": model},
            "raw_response": {"final_status": "quarantined" if i < failed_p1 else "clean",
                             "call_count": 1, "total_input_tokens": tokens_p1,
                             "total_output_tokens": tokens_p1 // 2,
                             "total_latency_ms": latency_ms_p1},
            "parsed_envelope": {"prompt_version": "1"},
            "cost_usd": cost_p1,
        }))
    if malformed_p1:
        (rs / "pass1" / "broken.json").write_text("{not json")
    for i in range(p2):
        (rs / "pass2" / f"c{i}.json").write_text(json.dumps({
            "run_id": run_dir, "source_id": f"c{i}.md", "provider": provider,
            "model": model,
            "final_status": "quarantined" if (quarantine_p2 and i == 0) else "clean",
            "total_input_tokens": 200, "total_output_tokens": 100,
            "total_latency_ms": 300, "cost_usd": 0.30}))
```

Tests:

```python
class TestEffectiveWeights:
    def test_pass1_full_precision_pro_rata(self):
        w = effective_top_weights("pass1")
        assert w["quarantine_rate"] == pytest.approx(2 / 3)
        assert w["recovery_rate"] == pytest.approx(1 / 6)
        assert w["latency"] == pytest.approx(1 / 6)
        assert w["graph"] == 0.0
        assert sum(w.values()) == pytest.approx(1.0)

    def test_pass2_canonical(self):
        assert effective_top_weights("pass2") == {
            "quarantine_rate": 0.40, "recovery_rate": 0.10,
            "latency": 0.10, "graph": 0.40}


class TestRankedBoard:
    def test_pass1_board_scores_and_carries_raw_values(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", latency_ms_p1=100, cost_p1=0.01)
        _write_run(rr, "b-T1", model="b", latency_ms_p1=900, cost_p1=0.30)
        m2r = {"prov/a@unversioned": "a-T1", "prov/b@unversioned": "b-T1"}
        board = build_pass_board(m2r, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["board_scope"] == "pass1"
        assert len(board["ranking"]) == 2 and board["unranked"] == []
        rows = {r["model"]: r for r in board["ranking"]}
        a = rows["prov/a@unversioned"]
        assert a["rank"] == 1                       # lower latency wins (all else tied)
        assert a["graph_score"] is None             # graph inactive on pass-1
        assert a["measurement_source"] == SRC_RECOMPUTED
        assert a["raw_values"]["cost_usd_pass1"] == pytest.approx(4 * 0.01)
        assert a["raw_values"]["cost_unknown_calls_pass1"] == 0
        assert a["raw_values"]["latency_pass1"] is not None
        assert board["effective_top_weights"]["quarantine_rate"] == pytest.approx(2 / 3)

    def test_pass2_board_has_graph_score_and_coverage_columns(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", signal=3, noise=1)
        _write_run(rr, "b-T1", model="b", signal=2, noise=1, failed_p1=0)
        # b: p1=4, signal=2, noise=1 → p1_failed = 1; eligibility 2/4
        m2r = {"prov/a@unversioned": "a-T1", "prov/b@unversioned": "b-T1"}
        gsbm = {"prov/a@unversioned": {"entity_reuse": 0.5, "graph_connectivity": 0.5,
                                       "link_density": 0.5, "supports_density": 0.5},
                "prov/b@unversioned": {"entity_reuse": 0.1, "graph_connectivity": 0.1,
                                       "link_density": 0.1, "supports_density": 0.1}}
        board = build_pass_board(m2r, rr, "pass2",
                                 graph_scored_by_model=gsbm, fallback_diag_by_model={})
        rows = {r["model"]: r for r in board["ranking"]}
        b = rows["prov/b@unversioned"]
        assert b["graph_score"] is not None
        assert b["raw_values"]["pass2_eligibility_rate"] == pytest.approx(2 / 4)
        assert b["raw_values"]["pass2_measurement_coverage"] == pytest.approx(1.0)
        assert b["raw_values"]["p1_noise"] == 1
        assert b["raw_values"]["p1_failed"] == 4 - 2 - 1
        a = rows["prov/a@unversioned"]
        assert a["raw_values"]["pass2_eligibility_rate"] == pytest.approx(3 / 4)

    def test_tied_models_share_competition_rank(self, tmp_path):
        """D-117-9: two identical leaders tie at rank 1; the next row SKIPS to
        rank 3 (competition ranking, not dense). Payload assertion here; the
        rendered-Markdown half lives in Task 5 (board-aware renderer lands
        there — R7-F3)."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a")                    # tied leader
        _write_run(rr, "b-T1", model="b")                    # tied leader
        _write_run(rr, "c-T1", model="c", latency_ms_p1=900) # lower row
        m2r = {f"prov/{m}@unversioned": f"{m}-T1" for m in "abc"}
        board = build_pass_board(m2r, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert [r["rank"] for r in board["ranking"]] == [1, 1, 3]

    def test_wrong_typed_sidecar_field_unranked(self, tmp_path):
        """R6-F1: type-invalid telemetry counts as malformed → row unranked,
        board still builds (no mid-board TypeError)."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a")
        bad = rr / "a-T1" / "run_state" / "pass1" / "s0.json"
        d = json.loads(bad.read_text())
        d["raw_response"]["total_input_tokens"] = "100"      # string, not int
        bad.write_text(json.dumps(d))
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["ranking"] == []
        assert any("malformed" in e
                   for e in board["unranked"][0]["completeness_errors"])

    def test_fallback_row_carries_header_derived_evidence(self, tmp_path):
        """R6-F2: a no-run_state row on the Pass-2 board still shows the
        measurements-header dispositions + eligibility; coverage is None."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", no_run_state=True)
        hdr = {"p1_attempted": 4, "signal": 3, "noise": 1}
        gsbm = {"prov/a@unversioned": {"entity_reuse": 0.5, "graph_connectivity": 0.5,
                                       "link_density": 0.5, "supports_density": 0.5}}
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass2",
                                 graph_scored_by_model=gsbm,
                                 fallback_diag_by_model={},
                                 header_by_model={"prov/a@unversioned": hdr})
        u = board["unranked"][0]
        assert u["raw_values"]["pass2_eligibility_rate"] == pytest.approx(3 / 4)
        assert u["raw_values"]["pass2_measurement_coverage"] is None
        assert u["raw_values"]["p1_noise"] == 1
        assert u["raw_values"]["p1_failed"] == 0

    def test_fallback_wrong_typed_header_degrades_not_aborts(self, tmp_path):
        """R7-F1: a wrong-typed measurements header yields None dispositions —
        the board still builds; and all-zero valid fields give p1_failed=0."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", no_run_state=True)
        bad = {"p1_attempted": "4", "signal": 3, "noise": 1}
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass2",
                                 graph_scored_by_model={},
                                 fallback_diag_by_model={},
                                 header_by_model={"prov/a@unversioned": bad})
        u = board["unranked"][0]
        assert u["raw_values"]["pass2_eligibility_rate"] is None
        assert u["raw_values"]["p1_failed"] is None
        zero = {"p1_attempted": 0, "signal": 0, "noise": 0}
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass2",
                                 graph_scored_by_model={},
                                 fallback_diag_by_model={},
                                 header_by_model={"prov/a@unversioned": zero})
        assert board["unranked"][0]["raw_values"]["p1_failed"] == 0


class TestCompleteness:
    def test_missing_run_state_unranked_fallback(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", no_run_state=True)
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={},
                                 fallback_diag_by_model={"prov/a@unversioned": {
                                     "quarantine_rate_pass1": 0.0, "latency_pass1": 111.0}})
        assert board["ranking"] == []
        u = board["unranked"][0]
        assert u["measurement_source"] == SRC_FALLBACK
        assert "recovery_rate" in u["missing_kpis"]
        assert u["raw_values"]["latency_pass1"] == 111.0

    def test_missing_pass1_sidecar_unranked(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", skip_sidecar=3)   # p1_attempted=4, only 3 sidecars
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["ranking"] == []
        assert board["unranked"][0]["measurement_source"] == SRC_PARTIAL

    def test_malformed_sidecar_unranked(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", malformed_p1=True)
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["unranked"][0]["measurement_source"] == SRC_PARTIAL

    def test_duplicate_source_id_unranked(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", dup_source=True)
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["unranked"][0]["measurement_source"] == SRC_PARTIAL

    def test_short_pass2_records_unranked_on_pass2_only(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", pass2_records=2)   # signal=3, only 2 records
        m2r = {"prov/a@unversioned": "a-T1"}
        # all four graph KPIs present — the short record count is the ONLY
        # failure condition (R5-F2: not masked by missing graph evidence)
        gsbm = {"prov/a@unversioned": {"entity_reuse": 0.5, "graph_connectivity": 0.5,
                                       "link_density": 0.5, "supports_density": 0.5}}
        b2 = build_pass_board(m2r, rr, "pass2", graph_scored_by_model=gsbm,
                              fallback_diag_by_model={})
        assert b2["ranking"] == [] and len(b2["unranked"]) == 1
        assert any("pass2_records" in e
                   for e in b2["unranked"][0]["completeness_errors"])
        b1 = build_pass_board(m2r, rr, "pass1", graph_scored_by_model={},
                              fallback_diag_by_model={})
        assert len(b1["ranking"]) == 1        # same row still ranks on pass-1

    def test_malformed_header_json_unranked_not_abort(self, tmp_path):
        """R5-F1: bad header JSON marks the row unranked; the board still builds."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a")
        (rr / "a-T1" / "run_state" / "measurement_header.json").write_text("{not json")
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["ranking"] == []
        assert board["unranked"][0]["completeness_errors"] == ["header_unparseable"]

    def test_structurally_invalid_header_unranked_not_abort(self, tmp_path):
        """R5-F1: valid JSON missing required header fields → TypeError caught
        the same way (row unranked, board builds)."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a")
        (rr / "a-T1" / "run_state" / "measurement_header.json").write_text(
            json.dumps({"run_id": "a-T1"}))       # missing required fields
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["ranking"] == []
        assert board["unranked"][0]["completeness_errors"] == ["header_unparseable"]

    def test_zero_token_pass1_unranked_despite_complete_counts(self, tmp_path):
        """Count-complete but zero-token pass → all rates None → unranked
        (never pro-rated on missing evidence, D-117-5e)."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", tokens_p1=0)
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["ranking"] == []
        u = board["unranked"][0]
        assert set(u["missing_kpis"]) == {"quarantine_rate", "recovery_rate", "latency"}
        assert u["completeness_errors"] == []

    def test_pass2_unranked_when_graph_kpi_absent(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a")
        gsbm = {"prov/a@unversioned": {"entity_reuse": 0.5, "graph_connectivity": 0.5,
                                       "link_density": 0.5}}   # supports_density absent
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass2",
                                 graph_scored_by_model=gsbm, fallback_diag_by_model={})
        assert board["ranking"] == []
        assert "supports_density" in board["unranked"][0]["missing_kpis"]

    def test_pass2_unranked_when_graph_kpi_none(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a")
        gsbm = {"prov/a@unversioned": {"entity_reuse": 0.5, "graph_connectivity": None,
                                       "link_density": 0.5, "supports_density": 0.5}}
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass2",
                                 graph_scored_by_model=gsbm, fallback_diag_by_model={})
        assert board["ranking"] == []
        assert "graph_connectivity" in board["unranked"][0]["missing_kpis"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tools/benchmark/tests/test_pass_boards.py -v`
Expected: FAIL (`ModuleNotFoundError: tools.benchmark.pass_boards`).

- [ ] **Step 3: Implement** — create `tools/benchmark/pass_boards.py`:

```python
"""tools.benchmark.pass_boards — per-pass leaderboard boards (Task #117).

Spec v0.3.1 D-117-1..10. Per-pass processing KPIs are recomputed at score
time from each row's run_state/ (load_run_measurements_with_stats →
compute_processing), mapped onto the canonical processing KPI names, and
scored through the §6 score_models machinery. Rows failing the per-board
completeness contract (D-117-5) are excluded from Borda and rendered
unranked — never scored pro-rata on missing evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

from common.measurement import load_run_measurements_with_stats
from compiler.kpi.processing import compute_processing
from compiler.kpi.score import GRAPH_WEIGHTS, TOP_WEIGHTS, score_models

GRAPH_KPIS = tuple(GRAPH_WEIGHTS)

SRC_RECOMPUTED = "run_state_recomputed"
SRC_PARTIAL = "run_state_partial"
SRC_FALLBACK = "measurements_fallback"

_AXES = ("quarantine_rate", "recovery_rate", "latency")
_SPLIT = {p: {canon: f"{canon}_{p}" for canon in _AXES} for p in ("pass1", "pass2")}


def effective_top_weights(pass_: str) -> dict:
    """Full-precision effective composite weights for a pass board (D-117-7).

    Pass-1 has no graph term: TOP_WEIGHTS pro-rates over the processing axes
    (2/3, 1/6, 1/6). Pass-2 uses the canonical 40/40/10/10.
    """
    if pass_ == "pass2":
        return dict(TOP_WEIGHTS)
    denom = 1.0 - TOP_WEIGHTS["graph"]
    return {
        "quarantine_rate": TOP_WEIGHTS["quarantine_rate"] / denom,
        "recovery_rate": TOP_WEIGHTS["recovery_rate"] / denom,
        "latency": TOP_WEIGHTS["latency"] / denom,
        "graph": 0.0,
    }


def _completeness(
    run_state: Path, pass_: str, header, stats: dict,
) -> list[str]:
    """D-117-5 per-board completeness contract → list of violated checks
    (empty = complete). `header` is None when measurement_header.json failed
    to parse."""
    problems: list[str] = []
    if header is None:
        return ["header_unparseable"]
    if not stats[f"{pass_}_dir_exists"]:
        problems.append(f"{pass_}_dir_missing")
    if stats[f"{pass_}_malformed"]:
        problems.append(f"{pass_}_malformed_files:{stats[f'{pass_}_malformed']}")
    if pass_ == "pass1":
        if stats["pass1_identified"] != header.p1_attempted:
            problems.append(
                f"pass1_sidecars:{stats['pass1_identified']}!=p1_attempted:{header.p1_attempted}")
        if stats["pass1_unique_source_ids"] != stats["pass1_identified"]:
            problems.append("pass1_duplicate_source_id")
    else:
        if stats["pass2_records"] != header.p2_attempted:
            problems.append(
                f"pass2_records:{stats['pass2_records']}!=p2_attempted:{header.p2_attempted}")
    return problems


def _assign_competition_ranks(ranking: list[dict]) -> None:
    """D-117-9: equal composites share a rank; the next rank skips (1, 1, 3)."""
    rank = 0
    prev: float | None = None
    for i, row in enumerate(ranking, start=1):
        c = row.get("composite") or 0.0
        if prev is None or c != prev:
            rank = i
        row["rank"] = rank
        prev = c


# Bounded header/loader deserialization failures — a bad run_state marks the
# ROW unranked (D-117-5), never aborts the whole command (R5-F1).
_HEADER_ERRORS = (OSError, json.JSONDecodeError, UnicodeDecodeError,
                  TypeError, AttributeError, ValueError, KeyError)


def _valid_int(v) -> bool:
    """Non-boolean int (R7-F1: bool is an int subclass — excluded)."""
    return isinstance(v, int) and not isinstance(v, bool)


def _fallback_raw(
    fallback_diag: dict, graph_scored: dict, pass_: str, meas_header: dict,
) -> dict:
    """Best raw evidence available without (a usable) run_state: legacy
    measurements carry the quarantine/latency per-pass splits and the graph
    KPIs; the measurements header still yields the Pass-1 dispositions and
    eligibility (R6-F2). Coverage is explicitly None (unknowable without
    run_state). Every header-derived value is type-guarded BEFORE arithmetic
    (R7-F1) — a wrong-typed measurements header degrades to None, never
    aborts the command. p1_failed computes for all-zero-but-valid fields
    (0 is a real disposition count)."""
    raw = {k: v for k, v in fallback_diag.items() if k.endswith(f"_{pass_}")}
    if pass_ == "pass2":
        raw.update({k: graph_scored.get(k) for k in GRAPH_KPIS})
        p1a = meas_header.get("p1_attempted")
        sig = meas_header.get("signal")
        noi = meas_header.get("noise")
        raw["pass2_eligibility_rate"] = (
            sig / p1a if (_valid_int(p1a) and _valid_int(sig) and p1a > 0)
            else None)
        raw["pass2_measurement_coverage"] = None
        raw["p1_noise"] = noi if _valid_int(noi) else None
        raw["p1_failed"] = (
            p1a - sig - noi
            if all(_valid_int(v) for v in (p1a, sig, noi)) else None)
    return raw


def _missing_from(raw: dict, pass_: str) -> list[str]:
    """Canonical KPI names with no available evidence in `raw` (R5-F3)."""
    missing = [c for c in _AXES if raw.get(f"{c}_{pass_}") is None]
    if pass_ == "pass2":
        missing += [k for k in GRAPH_KPIS if raw.get(k) is None]
    return missing


def _build_row(
    runs_root: Path, run_dir: str, model_key: str, pass_: str,
    graph_scored: dict, fallback_diag: dict, meas_header: dict,
) -> dict:
    """Build one board row. Returns {"ranked": bool, ...}. Ranked and
    unranked rows carry the SAME raw_values evidence contract (R5-F3)."""
    split = _SPLIT[pass_]
    run_state = runs_root / run_dir / "run_state"
    if not run_state.is_dir():
        # No run_state at all → measurements fallback (D-117-5).
        raw = _fallback_raw(fallback_diag, graph_scored, pass_, meas_header)
        return {
            "ranked": False,
            "measurement_source": SRC_FALLBACK,
            "missing_kpis": _missing_from(raw, pass_),
            "completeness_errors": ["run_state_missing"],
            "raw_values": raw,
        }
    try:
        header, calls, stats = load_run_measurements_with_stats(run_state)
    except _HEADER_ERRORS:
        # run_state present but unloadable (bad header JSON, wrong top-level
        # type, missing/wrong-typed required fields, bad encoding) → partial,
        # never abort. missing_kpis reflects the actual fallback evidence —
        # an empty list is valid when a completeness violation is the reason.
        raw = _fallback_raw(fallback_diag, graph_scored, pass_, meas_header)
        return {
            "ranked": False,
            "measurement_source": SRC_PARTIAL,
            "missing_kpis": _missing_from(raw, pass_),
            "completeness_errors": ["header_unparseable"],
            "raw_values": raw,
        }
    problems = _completeness(run_state, pass_, header, stats)
    diag = compute_processing(header, calls)["diagnostic"]
    # Assemble the full raw evidence ONCE (R5-F3) — retry/cost/unknown, and
    # on pass2 the graph raws + coverage + dispositions.
    raw = {src: diag.get(src) for src in split.values()}
    raw[f"retry_load_{pass_}"] = diag.get(f"retry_load_{pass_}")
    raw[f"cost_usd_{pass_}"] = diag.get(f"cost_usd_{pass_}")
    raw[f"cost_unknown_calls_{pass_}"] = diag.get(f"cost_unknown_calls_{pass_}")
    if pass_ == "pass2":
        for k in GRAPH_KPIS:
            raw[k] = graph_scored.get(k)
        raw["pass2_eligibility_rate"] = (
            header.signal / header.p1_attempted if header.p1_attempted else None)
        raw["pass2_measurement_coverage"] = (
            stats["pass2_records"] / header.p2_attempted
            if header.p2_attempted else None)
        raw["p1_noise"] = header.noise
        raw["p1_failed"] = header.p1_attempted - header.signal - header.noise
    scored = {canon: diag.get(src) for canon, src in split.items()}
    if pass_ == "pass2":
        scored.update({k: graph_scored.get(k) for k in GRAPH_KPIS})
    pass_calls = [c for c in calls if c.pass_ == pass_]
    loaded = len(pass_calls)
    if pass_ == "pass1" and not problems:
        expected = header.p1_attempted - stats["pass1_skipped"]
        if loaded != expected:
            problems.append(f"pass1_loaded:{loaded}!=expected:{expected}")
    # D-117-5 (e): every required KPI input must be present — a count-complete
    # row with zero-token (None) axes, or a missing/None graph KPI on the
    # Pass-2 board, is unranked rather than pro-rated on partial evidence.
    required = list(_AXES) + (list(GRAPH_KPIS) if pass_ == "pass2" else [])
    missing = [k for k in required if scored.get(k) is None]
    if problems or missing:
        return {
            "ranked": False,
            "measurement_source": SRC_PARTIAL,
            "missing_kpis": missing,              # canonical KPI names only
            "completeness_errors": problems,      # contract violations, separate
            "raw_values": raw,
        }
    return {
        "ranked": True,
        "measurement_source": SRC_RECOMPUTED,
        "scored": scored,
        "raw_values": raw,
    }


def build_pass_board(
    models_to_rundir: dict[str, str],
    runs_root: Path,
    pass_: str,
    *,
    graph_scored_by_model: dict[str, dict],
    fallback_diag_by_model: dict[str, dict],
    header_by_model: dict[str, dict] | None = None,
) -> dict:
    """Build one pass board (payload shape: see plan Interfaces).

    header_by_model: measurements.json headers keyed by model row — feeds
    header-derived fallback evidence (R6-F2). The CLI always passes it;
    default None (→ {}) keeps older fixtures usable, degrading fallback
    dispositions/eligibility to None."""
    models: list[dict] = []
    unranked: list[dict] = []
    raw_by_model: dict[str, dict] = {}
    src_by_model: dict[str, str] = {}
    header_by_model = header_by_model or {}
    for model_key, run_dir in models_to_rundir.items():
        row = _build_row(runs_root, run_dir, model_key, pass_,
                         graph_scored_by_model.get(model_key, {}),
                         fallback_diag_by_model.get(model_key, {}),
                         header_by_model.get(model_key, {}))
        if row["ranked"]:
            models.append({"model": model_key, "scored": row["scored"]})
            raw_by_model[model_key] = row["raw_values"]
            src_by_model[model_key] = row["measurement_source"]
        else:
            unranked.append({
                "model": model_key,
                "run_dir": run_dir,
                "measurement_source": row["measurement_source"],
                "missing_kpis": row["missing_kpis"],
                "completeness_errors": row.get("completeness_errors", []),
                "raw_values": row["raw_values"],
            })

    result = score_models(models)
    ranking = sorted(
        (
            {
                "model": m,
                "composite": e["composite"],
                "composite_pre_penalty": e["composite_pre_penalty"],
                "penalty": e["penalty"],
                "weakest_kpi": e["weakest_kpi"],
                "graph_score": e["graph_score"],
                "per_kpi_borda": e["per_kpi_borda"],
            }
            for m, e in result["per_model"].items()
        ),
        key=lambda r: (-(r["composite"] or 0.0), r["model"]),
    )
    _assign_competition_ranks(ranking)
    for r in ranking:
        r["measurement_source"] = src_by_model[r["model"]]
        r["raw_values"] = raw_by_model[r["model"]]

    return {
        "models": dict(models_to_rundir),
        "board_scope": pass_,
        "effective_top_weights": effective_top_weights(pass_),
        "ranking": ranking,
        "unranked": unranked,
        "top_weights": result["top_weights"],
        "graph_weights": result["graph_weights"],
        "penalty_params": result["penalty_params"],
        "updated_at": "",   # injected by the caller (shared stamp, D-117-10)
    }
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tools/benchmark/tests/test_pass_boards.py -v`
Expected: PASS.

- [ ] **Step 5: Commit (Joseph's gate)**

```bash
git add tools/benchmark/pass_boards.py tools/benchmark/tests/test_pass_boards.py
git commit -m "feat(benchmark): #117 — pass-board builder with fail-closed completeness contract"
```

---

### Task 5: Board-aware rendering (`_render_leaderboard_md` / `_render_score_table`)

**Files:**
- Modify: `tools/benchmark/cli.py:26-226`
- Test: `tools/benchmark/tests/test_score.py` (append; existing tests must pass unmodified)

**Interfaces:**
- Consumes: board payload from Task 4.
- Produces: `_render_leaderboard_md(ranking, scored_by_model, diagnostics_by_model, top_weights, updated_at, *, board=None) -> str` where `board=None` is byte-identical to today; `board={"scope": "pass1"|"pass2", "unranked": [...], "effective_top_weights": {...}}` renders the pass board. `_render_score_table(ranking, diagnostics_by_model, *, note=None)` — `note=None` keeps today's trailing NOTE.

- [ ] **Step 1: Write the failing tests** (append to `tools/benchmark/tests/test_score.py`; also add `from pathlib import Path` if not already imported)

First, the golden-fixture input (module level, single source for the generator and the test):

```python
_GOLDEN_INPUT = {
    "ranking": [
        {"model": "prov/a@unversioned", "rank": 1, "composite": 80.0,
         "composite_pre_penalty": 82.0, "penalty": 2.0, "weakest_kpi": "latency",
         "graph_score": 1.0,
         "per_kpi_borda": {"quarantine_rate": 1.0, "recovery_rate": 1.0,
                           "latency": 0.5, "entity_reuse": 1.0,
                           "graph_connectivity": 1.0, "link_density": 1.0,
                           "supports_density": 1.0}},
        {"model": "prov/b@unversioned", "rank": 2, "composite": 40.0,
         "composite_pre_penalty": 50.0, "penalty": 10.0, "weakest_kpi": "graph",
         "graph_score": 0.0,
         "per_kpi_borda": {"quarantine_rate": 0.0, "recovery_rate": 0.0,
                           "latency": 1.0, "entity_reuse": 0.0,
                           "graph_connectivity": 0.0, "link_density": 0.0,
                           "supports_density": 0.0}},
    ],
    "scored_by_model": {
        "prov/a@unversioned": {"quarantine_rate": 0.0, "recovery_rate": 0.0,
                               "latency": 100.0, "entity_reuse": 0.1,
                               "graph_connectivity": 0.2, "link_density": 2.0,
                               "supports_density": 5.0},
        "prov/b@unversioned": {"quarantine_rate": 5.0, "recovery_rate": 3.0,
                               "latency": 900.0, "entity_reuse": 0.3,
                               "graph_connectivity": 0.1, "link_density": 1.0,
                               "supports_density": 3.0}},
    "diagnostics_by_model": {"prov/a@unversioned": {"signal_noise_ratio": 0.8},
                             "prov/b@unversioned": {"signal_noise_ratio": 0.7}},
    "top_weights": {"quarantine_rate": 0.4, "graph": 0.4,
                    "recovery_rate": 0.1, "latency": 0.1},
    "updated_at": "2026-07-22T00:00:00",
}
```

Generate the golden fixture **from the pre-#117 renderer, before modifying `cli.py`**:

```bash
mkdir -p tools/benchmark/tests/fixtures
.venv/bin/python -c "
from tools.benchmark import cli
from tools.benchmark.tests.test_score import _GOLDEN_INPUT
md = cli._render_leaderboard_md(**_GOLDEN_INPUT)
open('tools/benchmark/tests/fixtures/leaderboard_main_golden.md', 'w').write(md)
"
```

Then the new test class:

```python
class TestPassBoardRendering:
    def _board_rows(self):
        return [
            {"model": "prov/a@unversioned", "rank": 1, "composite": 80.0,
             "composite_pre_penalty": 80.0, "penalty": 0.0, "weakest_kpi": "latency",
             "graph_score": None,
             "per_kpi_borda": {"quarantine_rate": 1.0, "recovery_rate": 1.0,
                               "latency": 0.5},
             "measurement_source": "run_state_recomputed",
             "raw_values": {"quarantine_rate_pass1": 0.0, "recovery_rate_pass1": 0.0,
                            "latency_pass1": 100.0, "retry_load_pass1": 0.0,
                            "cost_usd_pass1": 0.05, "cost_unknown_calls_pass1": 0}},
            {"model": "prov/b@unversioned", "rank": 2, "composite": 40.0,
             "composite_pre_penalty": 50.0, "penalty": 10.0, "weakest_kpi": "latency",
             "graph_score": None,
             "per_kpi_borda": {"quarantine_rate": 0.0, "recovery_rate": 0.0,
                               "latency": 1.0},
             "measurement_source": "run_state_recomputed",
             "raw_values": {"quarantine_rate_pass1": 1.0, "recovery_rate_pass1": 2.0,
                            "latency_pass1": 900.0, "retry_load_pass1": 0.5,
                            "cost_usd_pass1": 0.30, "cost_unknown_calls_pass1": 1}},
        ]

    def _render(self, scope="pass1", unranked=None):
        ranking = self._board_rows()
        return cli._render_leaderboard_md(
            ranking,
            {},                                     # pass boards: raw table from
            {r["model"]: r["raw_values"] for r in ranking},   # raw_values only
            {"quarantine_rate": 2 / 3, "recovery_rate": 1 / 6, "latency": 1 / 6,
             "graph": 0.0},
            "2026-07-22T00:00:00",
            board={"scope": scope, "unranked": unranked or [],
                   "effective_top_weights": {"quarantine_rate": 2 / 3,
                                             "recovery_rate": 1 / 6,
                                             "latency": 1 / 6, "graph": 0.0}},
        )

    def test_pass1_render_suppresses_graph_and_titles_board(self):
        md = self._render()
        assert md.startswith("# Model leaderboard — Pass-1 (enrich)")
        assert "graph_score" not in md
        assert "graph KPIs" not in md
        assert "≥" in md and "unknown" in md          # cost honesty for row b
        assert "| rank | model | cost |" in md

    def test_competition_ranks_rendered_in_markdown(self):
        """D-117-9 display half (R7-F3: lives in Task 5 because board-aware
        rendering lands here): tied leaders share rank 1; next row shows 3."""
        rows = [
            {"model": "prov/a@unversioned", "rank": 1, "composite": 66.7,
             "composite_pre_penalty": 66.7, "penalty": 0.0, "weakest_kpi": "latency",
             "graph_score": None,
             "per_kpi_borda": {"quarantine_rate": 0.5, "recovery_rate": 0.5,
                               "latency": 1.0},
             "measurement_source": "run_state_recomputed",
             "raw_values": {"latency_pass1": 100.0, "cost_usd_pass1": 0.04,
                            "cost_unknown_calls_pass1": 0}},
            {"model": "prov/b@unversioned", "rank": 1, "composite": 66.7,
             "composite_pre_penalty": 66.7, "penalty": 0.0, "weakest_kpi": "latency",
             "graph_score": None,
             "per_kpi_borda": {"quarantine_rate": 0.5, "recovery_rate": 0.5,
                               "latency": 1.0},
             "measurement_source": "run_state_recomputed",
             "raw_values": {"latency_pass1": 100.0, "cost_usd_pass1": 0.04,
                            "cost_unknown_calls_pass1": 0}},
            {"model": "prov/c@unversioned", "rank": 3, "composite": 40.0,
             "composite_pre_penalty": 50.0, "penalty": 10.0, "weakest_kpi": "latency",
             "graph_score": None,
             "per_kpi_borda": {"quarantine_rate": 0.5, "recovery_rate": 0.5,
                               "latency": 0.0},
             "measurement_source": "run_state_recomputed",
             "raw_values": {"latency_pass1": 900.0, "cost_usd_pass1": 0.36,
                            "cost_unknown_calls_pass1": 0}},
        ]
        md = cli._render_leaderboard_md(
            rows, {},
            {r["model"]: r["raw_values"] for r in rows},
            {"quarantine_rate": 2 / 3, "recovery_rate": 1 / 6, "latency": 1 / 6,
             "graph": 0.0},
            "2026-07-22T00:00:00",
            board={"scope": "pass1", "unranked": [],
                   "effective_top_weights": {"quarantine_rate": 2 / 3,
                                             "recovery_rate": 1 / 6,
                                             "latency": 1 / 6, "graph": 0.0}},
        )
        rank_cells = [ln.split("|")[1].strip() for ln in md.splitlines()
                      if ln.startswith("| ") and "prov/" in ln
                      and ln.split("|")[1].strip().isdigit()]
        assert rank_cells == ["1", "1", "3"]

    def test_raw_table_shows_measured_values_not_borda(self):
        """P-F4 guard: the raw section must contain measured values
        (latency 100 ms, cost 0.05), never the row's Borda scores."""
        md = self._render()
        raw_section = md.split("## Raw measured values", 1)[1]
        header_line = next(ln for ln in raw_section.splitlines()
                           if ln.startswith("| model |"))
        # raw columns are the suffixed measured KPIs, not canonical Borda axes
        assert "latency_pass1" in header_line
        assert "cost_usd_pass1" in header_line
        assert "| quarantine_rate |" not in header_line   # no bare Borda axis column
        # measured values present in the body
        assert "100" in raw_section                     # measured latency
        assert "0.05" in raw_section                    # measured cost (model a)

    def test_unranked_section_rendered(self):
        md = self._render(unranked=[{
            "model": "prov/c@unversioned", "run_dir": "c-T1",
            "measurement_source": "measurements_fallback",
            "missing_kpis": ["recovery_rate"], "raw_values": {}}])
        assert "## Unranked" in md
        assert "prov/c@unversioned" in md
        assert "measurements_fallback" in md

    def test_pass2_render_keeps_graph_and_states_caveat(self):
        rows = [
            {"model": "prov/a@unversioned", "rank": 1, "composite": 80.0,
             "composite_pre_penalty": 80.0, "penalty": 0.0, "weakest_kpi": "latency",
             "graph_score": 0.85,
             "per_kpi_borda": {"quarantine_rate": 1.0, "recovery_rate": 1.0,
                               "latency": 0.5, "entity_reuse": 1.0,
                               "graph_connectivity": 1.0, "link_density": 1.0,
                               "supports_density": 1.0},
             "measurement_source": "run_state_recomputed",
             "raw_values": {"quarantine_rate_pass2": 0.0, "recovery_rate_pass2": 0.0,
                            "latency_pass2": 300.0, "retry_load_pass2": 0.0,
                            "cost_usd_pass2": 0.54, "cost_unknown_calls_pass2": 0,
                            "entity_reuse": 0.1, "graph_connectivity": 0.2,
                            "link_density": 2.0, "supports_density": 5.0,
                            "pass2_eligibility_rate": 0.75,
                            "pass2_measurement_coverage": 1.0,
                            "p1_noise": 1, "p1_failed": 0}},
        ]
        md = cli._render_leaderboard_md(
            rows,
            {},                                     # pass boards: no scored raw cols
            {r["model"]: r["raw_values"] for r in rows},
            {"quarantine_rate": 0.4, "graph": 0.4, "recovery_rate": 0.1,
             "latency": 0.1},
            "2026-07-22T00:00:00",
            board={"scope": "pass2", "unranked": [],
                   "effective_top_weights": {"quarantine_rate": 0.4, "graph": 0.4,
                                             "recovery_rate": 0.1, "latency": 0.1}},
        )
        assert "Pass-2" in md and "downstream" in md
        assert "#118" in md
        assert "graph_score" in md                   # graph column retained
        assert "0.85" in md                          # populated graph_score shown
        raw_section = md.split("## Raw measured values", 1)[1]
        assert "pass2_eligibility_rate" in raw_section
        assert "p1_failed" in raw_section

    def test_main_board_render_byte_identical_golden(self):
        """Full-byte guard (P-F6): board=None output must equal the golden
        fixture generated from the pre-#117 renderer (characterization test —
        green before AND after the renderer change)."""
        golden = (Path(__file__).parent / "fixtures"
                  / "leaderboard_main_golden.md").read_text(encoding="utf-8")
        md = cli._render_leaderboard_md(**_GOLDEN_INPUT)
        assert md == golden
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tools/benchmark/tests/test_score.py -v -k PassBoard`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'board'`).

- [ ] **Step 3: Implement** — in `tools/benchmark/cli.py`:

Signature change (defaults preserve every current caller):

```python
def _render_leaderboard_md(
    ranking: list[dict],
    scored_by_model: dict,
    diagnostics_by_model: dict,
    top_weights: dict,
    updated_at: str,
    *,
    board: dict | None = None,
) -> str:
```

Inside, branch on `board`:

- `board is None` → the exact current body, unmodified (title `# Model leaderboard`, weights prose, graph_score column always, current footer).
- `board` set → same table machinery with these deltas:
  - Title: `"# Model leaderboard — Pass-1 (enrich) only"` or `"# Model leaderboard — Pass-2 (compile) — downstream outcome"`.
  - Intro line from `board["effective_top_weights"]`: Pass-1 renders `_Pass-1-only weighted Borda — effective weights: quarantine 0.667 / recovery 0.167 / latency 0.167 (graph inactive). Updated {updated_at}._`; Pass-2 renders the canonical 0.4/0.4/0.1/0.1 line plus `_Pass-2 downstream-outcome board: includes Pass-1 gating/failure effects — isolated per-pass attribution awaits #118._`
  - Ranking table gains a `cost` column after `model`, formatted from the row's `raw_values` via:
    ```python
    def _fmt_cost(raw: dict, scope: str) -> str:
        v = raw.get(f"cost_usd_{scope}")
        u = raw.get(f"cost_unknown_calls_{scope}")
        if v is None:
            return "—"
        base = f"${v:.3f}"
        return f"≥{base} (+{u} unknown)" if u else base
    ```
  - `graph_score` column omitted when every ranked row's `graph_score` is None (the Pass-1 case; D-117-7 — pass-board renders only).
  - **Raw section = measured values only (P-F4).** For pass boards the caller passes `scored_by_model={}` and `diagnostics_by_model=raw_by_model`, so the raw table's columns come solely from each row's `raw_values` (suffixed per-pass measurements + graph raws + coverage/dispositions). `per_kpi_borda` feeds ONLY the ranking table. The board branch titles the section `## Raw measured values (per-pass recomputed at score time; graph from measurements.json)`.
  - Footer: Pass-1 suppresses the graph-KPI explanatory text entirely and appends `Cost = model-pool pricing × tokens (cohort-comparable, not an invoice).`; Pass-2 keeps the graph note and prepends the downstream caveat.
  - Unranked section when `board["unranked"]` non-empty:
    ```
    ## Unranked (incomplete evidence — excluded from Borda, D-117-5)

    | model | run_dir | measurement_source | missing_kpis |
    |---|---|---|---|
    | prov/c@unversioned | c-T1 | measurements_fallback | recovery_rate |
    ```

And `_render_score_table(ranking, diagnostics_by_model, *, note=None)`: replace the fixed trailing NOTE with `note if note is not None else <current NOTE text>`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tools/benchmark/tests -v`
Expected: PASS — including every pre-existing test unmodified (D-117-1 guard).

- [ ] **Step 5: Commit (Joseph's gate)**

```bash
git add tools/benchmark/cli.py tools/benchmark/tests/test_score.py
git commit -m "feat(benchmark): #117 — board-aware leaderboard rendering (main board byte-identical)"
```

---

### Task 6: CLI integration — three boards, one stamp, atomic writes

**Files:**
- Modify: `tools/benchmark/cli.py:316-468` (`_score_command`)
- Test: `tools/benchmark/tests/test_score.py` (append)

**Interfaces:**
- Consumes: `build_pass_board`/`GRAPH_KPIS` (Task 4), board-aware renderers (Task 5), `common.atomic_io.atomic_write_json/atomic_write_text`.
- Produces: `_pass_paths(leaderboard_path, pass_) -> tuple[Path, Path]`; six artifacts per invocation sharing one `updated_at`.

- [ ] **Step 1: Write the failing tests**

```python
class TestThreeBoards:
    def test_pass_files_written_next_to_main(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="a-T1", model="a", runs_root=runs_root)
        rc = cli.main(["score", "a-T1", "--runs-root", str(runs_root),
                       "--leaderboard", str(lb)])
        assert rc == 0
        for p in ("pass1", "pass2"):
            assert (tmp_path / f"leaderboard-{p}.json").exists()
            assert (tmp_path / f"leaderboard-{p}.md").exists()
        # fixture has no run_state → the row is unranked on both pass boards
        b1 = _load(tmp_path / "leaderboard-pass1.json")
        assert b1["board_scope"] == "pass1"
        assert b1["ranking"] == [] and len(b1["unranked"]) == 1
        assert b1["unranked"][0]["measurement_source"] == "measurements_fallback"

    def test_all_three_payloads_share_updated_at(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="a-T1", model="a", runs_root=runs_root)
        cli.main(["score", "a-T1", "--runs-root", str(runs_root),
                  "--leaderboard", str(lb)])
        stamps = {_load(tmp_path / n)["updated_at"] for n in
                  ("leaderboard.json", "leaderboard-pass1.json",
                   "leaderboard-pass2.json")}
        assert len(stamps) == 1

    def test_custom_leaderboard_stem_derives_pass_filenames(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "deep" / "my-board.json"
        _make_measurements(run_dir="a-T1", model="a", runs_root=runs_root)
        cli.main(["score", "a-T1", "--runs-root", str(runs_root),
                  "--leaderboard", str(lb)])
        assert (tmp_path / "deep" / "my-board-pass1.json").exists()

    def test_pre_write_failure_leaves_prior_artifacts_untouched(self, tmp_path, monkeypatch):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="a-T1", model="a", runs_root=runs_root)
        cli.main(["score", "a-T1", "--runs-root", str(runs_root),
                  "--leaderboard", str(lb)])
        before = {p.name: p.read_bytes() for p in tmp_path.glob("leaderboard*")}
        def boom(*a, **k):
            raise RuntimeError("simulated build failure")
        # cli imports build_pass_board by name → patch the cli-bound reference
        monkeypatch.setattr(cli, "build_pass_board", boom)
        rc = cli.main(["score", "a-T1", "--runs-root", str(runs_root),
                       "--leaderboard", str(lb)])
        assert rc != 0
        after = {p.name: p.read_bytes() for p in tmp_path.glob("leaderboard*")}
        assert before == after

    def test_mid_commit_failure_then_rerun_heals(self, tmp_path, monkeypatch):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="a-T1", model="a", runs_root=runs_root)
        calls = {"n": 0}
        real = cli.atomic_write_text
        def flaky(path, text, **kw):
            calls["n"] += 1
            if calls["n"] == 2:          # fail the 2nd write (main .md)
                raise OSError("simulated mid-commit failure")
            return real(path, text, **kw)
        monkeypatch.setattr(cli, "atomic_write_text", flaky)
        with pytest.raises(OSError):
            cli.main(["score", "a-T1", "--runs-root", str(runs_root),
                      "--leaderboard", str(lb)])
        monkeypatch.setattr(cli, "atomic_write_text", real)
        rc = cli.main(["score", "a-T1", "--runs-root", str(runs_root),
                       "--leaderboard", str(lb)])
        assert rc == 0
        stamps = {_load(tmp_path / n)["updated_at"] for n in
                  ("leaderboard.json", "leaderboard-pass1.json",
                   "leaderboard-pass2.json")}
        assert len(stamps) == 1          # healed to one generation

    def test_non_serializable_payload_aborts_before_any_write(self, tmp_path, monkeypatch):
        """P-F3: serialization happens BEFORE the first write — a bad value
        in a pass-board payload leaves all prior artifacts byte-identical."""
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="a-T1", model="a", runs_root=runs_root)
        cli.main(["score", "a-T1", "--runs-root", str(runs_root),
                  "--leaderboard", str(lb)])
        before = {p.name: p.read_bytes() for p in tmp_path.glob("leaderboard*")}
        real = cli.build_pass_board
        def poisoned(*a, **k):
            b = real(*a, **k)
            b["penalty_params"] = {"threshold": {0.5}, "cap": 0.10}  # set: not JSON-serializable
            return b
        monkeypatch.setattr(cli, "build_pass_board", poisoned)
        with pytest.raises(TypeError):
            cli.main(["score", "a-T1", "--runs-root", str(runs_root),
                      "--leaderboard", str(lb)])
        after = {p.name: p.read_bytes() for p in tmp_path.glob("leaderboard*")}
        assert before == after

    def test_future_shaped_measurements_add_only_raw_columns(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="a-T1", model="a", runs_root=runs_root)
        # inject #117 diagnostics into the fixture's processing.diagnostic
        mpath = runs_root / "a-T1" / "measurements.json"
        m = json.loads(mpath.read_text())
        m["processing"]["diagnostic"].update({
            "recovery_rate_pass1": 0.0, "cost_usd_pass1": 0.05})
        mpath.write_text(json.dumps(m))
        rc = cli.main(["score", "a-T1", "--runs-root", str(runs_root),
                       "--leaderboard", str(lb)])
        assert rc == 0
        md = (tmp_path / "leaderboard.md").read_text()
        data = _load(lb)
        assert "cost_usd_pass1" in md                     # raw table passthrough
        assert "cost_usd_pass1" not in data["ranking"][0]["per_kpi_borda"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tools/benchmark/tests/test_score.py -v -k ThreeBoards`
Expected: FAIL (no pass files written today).

- [ ] **Step 3: Implement** — in `tools/benchmark/cli.py`:

Imports at top: `from common.atomic_io import atomic_write_text` (all six writes go through it after pre-serialization) and `from tools.benchmark.pass_boards import GRAPH_KPIS, build_pass_board`.

Add helper:

```python
def _pass_paths(leaderboard_path: Path, pass_: str) -> tuple[Path, Path]:
    """Pass-board artifact paths derived from the --leaderboard stem (D-117-10)."""
    stem = leaderboard_path.with_suffix("")
    return (stem.parent / f"{stem.name}-{pass_}.json",
            stem.parent / f"{stem.name}-{pass_}.md")
```

In `_score_command`, after `result = score_models(models)` and the main `ranking` build, restructure the tail:

```python
    # --- Pass boards (#117): recompute per-pass KPIs from run_state/ ---
    graph_scored_by_model = {
        m["model"]: {k: m["scored"].get(k) for k in GRAPH_KPIS} for m in models
    }
    # measurements.json headers (already parsed above) feed header-derived
    # fallback evidence for rows without a usable run_state/ (R6-F2).
    header_by_model = {}
    for key, run_dir in models_to_rundir.items():
        data = _read_measurements(runs_root / run_dir / "measurements.json") or {}
        header_by_model[key] = data.get("header", {}) or {}
    try:
        pass_boards = {
            p: build_pass_board(
                models_to_rundir, runs_root, p,
                graph_scored_by_model=graph_scored_by_model,
                fallback_diag_by_model=diagnostics_by_model,
                header_by_model=header_by_model)
            for p in ("pass1", "pass2")
        }
    except Exception as exc:   # pre-write failure: every artifact untouched
        print(f"error: pass-board build failed: {exc}", file=sys.stderr)
        return 1

    # --- One shared generation stamp across all three boards (D-117-10) ---
    stamp = now_iso()
    for b in pass_boards.values():
        b["updated_at"] = stamp

    payload: dict = {
        "models": models_to_rundir,
        "ranking": ranking,
        "top_weights": result["top_weights"],
        "graph_weights": result["graph_weights"],
        "penalty_params": result["penalty_params"],
        "updated_at": stamp,
    }

    # --- Render everything before writing anything (D-117-10) ---
    scored_by_model = {m["model"]: m["scored"] for m in models}
    main_md = _render_leaderboard_md(
        ranking, scored_by_model, diagnostics_by_model,
        result["top_weights"], stamp)
    pass_md = {
        p: _render_leaderboard_md(
            b["ranking"],
            {},                                  # pass boards: raw table from
            {r["model"]: r["raw_values"] for r in b["ranking"]},   # raw_values only
            b["effective_top_weights"], stamp,
            board={"scope": p, "unranked": b["unranked"],
                   "effective_top_weights": b["effective_top_weights"]})
        for p, b in pass_boards.items()
    }

    # --- Pre-serialize EVERY payload before the first write (D-117-10):
    # a serialization failure here is a pre-write failure and leaves every
    # existing artifact untouched. _dump matches atomic_write_json's
    # serialization, so the main board's bytes are unchanged.
    def _dump(obj: dict) -> str:
        return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"

    writes: list[tuple[Path, str]] = [
        (leaderboard_path, _dump(payload)),
        (leaderboard_path.with_suffix(".md"), main_md),
    ]
    for p in ("pass1", "pass2"):
        pj, pm = _pass_paths(leaderboard_path, p)
        writes.append((pj, _dump(pass_boards[p])))
        writes.append((pm, pass_md[p]))

    # --- Individually-atomic writes; a mid-commit failure may leave a mixed
    # generation (detectable via updated_at; rerun heals) ---
    for path, text in writes:
        atomic_write_text(path, text)

    # --- Terminal output: main table + pass-board summaries ---
    table = _render_score_table(ranking, diagnostics_by_model)
    print(table)
    for p in ("pass1", "pass2"):
        b = pass_boards[p]
        if b["ranking"]:
            print(_render_score_table(
                b["ranking"],
                {r["model"]: r["raw_values"] for r in b["ranking"]},
                note=f"NOTE: {p} board — composite comparable ONLY within this "
                     f"candidate set. See {leaderboard_path.with_suffix('').name}-{p}.md"))
        else:
            print(f"{p} board: 0 ranked, {len(b['unranked'])} unranked")
    pj1, pm1 = _pass_paths(leaderboard_path, "pass1")
    pj2, pm2 = _pass_paths(leaderboard_path, "pass2")
    print(
        f"leaderboards updated: {leaderboard_path} (+ .md, {pj1.name}+.md, "
        f"{pj2.name}+.md)  ({len(models)} models)"
    )
    return 0
```

Delete the old non-atomic `leaderboard_path.write_text(...)` / `md_path.write_text(...)` block it replaces. (`atomic_write_json` serializes with `indent=2, ensure_ascii=False` + trailing newline — byte-identical to the old dump.)

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tools/benchmark/tests compiler/tests common/tests orchestrator/tests -v`
Expected: PASS.

- [ ] **Step 5: Full suite**

Run: `pytest`
Expected: full suite green (was 1386 + new tests; no regressions).

- [ ] **Step 6: Commit (Joseph's gate)**

```bash
git add tools/benchmark/cli.py tools/benchmark/tests/test_score.py
git commit -m "feat(benchmark): #117 — three-board score command with shared-stamp atomic writes"
```

---

### Task 7: Live regeneration + close-out

**Files:**
- Data: `benchmark/scores/leaderboard{,-pass1,-pass2}.{json,md}` (tracked)
- Modify: `docs/CODEBASE_OVERVIEW.md` (Milestone Changelog), `docs/TASKS.md` (#117 → Closed)

- [ ] **Step 1: Regenerate the real boards from the existing 5-row leaderboard**

Run: `kdb-benchmark score deepseek-v4-flash-2026-07-21T00-20-32_EDT gemini-3.5-flash-2026-07-21T01-46-20_EDT gpt-5.4-mini-2026-07-20T23-52-49_EDT qwen3.6-flash-us-2026-07-21T00-51-24_EDT glm-5-turbo-2026-07-21T10-45-04_EDT`
(Any single recent run-id works — the leaderboard accumulates from its pointers; listing all five is explicit.)
Expected: `leaderboard.json` ranking unchanged (same order/composites as before); `leaderboard-pass1.{json,md}` + `leaderboard-pass2.{json,md}` created with all 5 rows ranked (`run_state_recomputed`).

- [ ] **Step 2: Eyeball the boards with Joseph** — verify: main board diff shows only `updated_at`; Pass-1 board shows the DeepSeek-vs-GPT cost column ($0.050 vs $0.306) and any `≥` unknown-cost annotations; Pass-2 board shows Qwen's `p1_failed=1` and eligibility 28/36.

- [ ] **Step 3: Milestone Changelog entry** in `docs/CODEBASE_OVERVIEW.md` (top section) summarizing #117 + move the #117 row in `docs/TASKS.md` from Open to Closed with commit SHAs.

- [ ] **Step 4: Commit (Joseph's gate)**

```bash
git add benchmark/scores docs/CODEBASE_OVERVIEW.md docs/TASKS.md
git commit -m "feat(benchmark): #117 — per-pass leaderboards live; task closed"
```

---

## Self-Review Notes (completed by the plan author)

- **Codex plan review (R4, 2026-07-22) folded:** (1) required-KPI gate closed — missing required axes (incl. graph four on Pass-2) render unranked, with `missing_kpis` (canonical) separated from `completeness_errors`; (2) production loader stays strict — tolerance exists only in the opt-in stats loader, with projection errors counted as malformed; (3) all JSON is pre-serialized before the first write; (4) pass-board raw tables render measured `raw_values` only, `per_kpi_borda` confined to the ranking table; (5) test-plan defects fixed (scored-vs-diagnostic lookup, 17-key count, imports, `-k` quoting); (6) renderer tests strengthened (full-byte golden fixture, genuine Pass-2 rows); (7) branch-overlap reconciliation with #115 recorded in Global Constraints.
- **Codex plan review (R5, 2026-07-22) folded:** (1) `_build_row` catches the bounded header-deserialization set and returns `completeness_errors=["header_unparseable"]` (was: escaped exceptions + discarded `problems` key) — malformed-JSON and structurally-invalid header tests added; (2) short-Pass-2 test unmasked with a full graph map; (3) `raw_values` assembled once for ranked AND unranked rows, `missing_kpis` derived from available evidence (fallback no longer hardcodes); (4) renderer test helper passes `{}` for `scored_by_model` per the contract, and the raw-header lookup finds the `| model |` line.
- **Codex plan review (R6, 2026-07-22) folded:** (1) type validation at the projection boundary — `_validate_header_types` (raises → row unranked) + `_valid_measurement` (counts `*_malformed`), tolerant loader only, strict production path untouched; wrong-typed header/sidecar tests at loader AND board level; (2) fallback rows now carry measurements-header-derived evidence (`pass2_eligibility_rate`, `p1_noise`, `p1_failed`; coverage explicitly `None`) via `header_by_model` threaded from the CLI; (3) the `or list(_AXES)` false-missing crutch removed — empty `missing_kpis` is valid alongside a completeness violation; (4) competition-ranking test now proves `[1, 1, 3]` in the payload AND the rendered Markdown.
- **Codex plan review (R7, 2026-07-22) folded:** (1) `_fallback_raw` header arithmetic fully type-guarded (`_valid_int`, bool-excluded) — wrong-typed measurements headers degrade to `None`, never abort; all-zero valid fields correctly give `p1_failed=0`; (2) type validation now runs on BOTH loader paths — strict raises `TypeError` (same failure class emit has today; "fails safely" contract preserved), tolerant counts malformed; strict-path tests added; (3) the rendered-Markdown `[1, 1, 3]` assertion moved from Task 4 to Task 5, where the board-aware renderer actually exists — Task 4's green gate is reachable again.
- **Codex plan review (R8, 2026-07-22): no blocking findings — plan ready for ratification.** The one non-blocking hardening idea (semantic domain checks in `_valid_measurement`: negative tokens/latency, non-finite or boolean `cost_usd`) is **deliberately deferred** — Codex itself notes the ratified v0.3.1 contract doesn't require it, and it can land as a follow-up if real telemetry ever produces such values.
- **Spec coverage:** D-117-1 → Tasks 5–6 (+ byte-identical golden test). D-117-2 → Tasks 2, 4. D-117-3 → Tasks 1, 3. D-117-4 → Task 4 (axes mapping, coverage/disposition columns). D-117-5 → Tasks 2, 4 (invariants + unranked JSON). D-117-6 → Task 6 (same map/keys, no new flags). D-117-7 → Tasks 4, 5. D-117-8 → Tasks 3, 5 (cost columns, ≥ rendering). D-117-9 → Task 4 (competition ranks) + display test. D-117-10 → Task 6 (shared stamp, pre-serialization, atomic writes, pre-write/mid-commit/non-serializable tests).
- **Type consistency:** board payload keys, `raw_values` suffix keys (`*_pass1/2`), stats keys, and renderer params are used identically across Tasks 2–6.
- **Known intentional behavior notes:** the production loader `load_run_measurements` stays strict; only the opt-in `load_run_measurements_with_stats` tolerates+counts malformed files; main-board JSON/MD writes become atomic (bytes unchanged); existing tests are the D-117-1 guard.
