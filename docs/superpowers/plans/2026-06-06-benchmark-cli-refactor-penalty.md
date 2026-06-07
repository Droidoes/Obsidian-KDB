# kdb-benchmark CLI Refactor + Weak-Spot Penalty Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the legacy Task #5 benchmark engine and add a weakest-link penalty (rendered on a 0–100 scale) to the #109 leaderboard.

**Architecture:** `tools/benchmark/cli.py` currently carries two disjoint engines — the legacy `--models` run engine (`runner`/`scorer`/`scorecard`/`registry`, ~1,900 LOC) and the #109 `score` leaderboard. We delete the legacy island (it is self-contained — nothing outside its own modules/tests imports it), make `score` a real argparse subcommand, then add a penalty to `compiler/kpi/score.py` that punishes a model's single weakest composite axis, and scale the headline composite to 0–100.

**Tech Stack:** Python 3.12, `argparse`, `pytest`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-06-benchmark-cli-refactor-penalty-design.md`

**Pre-flight:** All commands run from repo root `/home/ftu/Droidoes/Obsidian-KDB`. Run pytest as `pytest -m "not live"` ALWAYS — `.env` auto-loads API keys and a bare `pytest` fires live, API-billing tests. Baseline before starting: `pytest -m "not live" -q` should be green (~1358 tests).

---

## Task 1: Retire the legacy engine + make `score` a real subcommand

**Files:**
- Modify: `tools/benchmark/cli.py` (remove `_main_run`, `_build_parser`, `_merge_with_prior_final`, legacy imports; restructure `main` into subparser dispatch; change `_score_command` to take a parsed `Namespace`)
- Modify: `tools/benchmark/paths.py:27` (remove the `MODELS_JSON` export)
- Modify: `tools/benchmark/tests/test_score.py` (delete `TestScoreExistingCLIUnchanged`; the rest of the file calls `cli.main(["score", ...])` and keeps working)
- Modify: `tools/benchmark/tests/test_cli.py` (delete legacy `--models`/`_main_run` cases; keep only surviving-CLI cases — see Step 4)
- Modify: `tools/benchmark/tests/test_paths.py` (remove any assertion referencing `MODELS_JSON`)
- Delete: `tools/benchmark/runner.py`, `tools/benchmark/scorer.py`, `tools/benchmark/scorecard.py`, `tools/benchmark/registry.py`, `tools/benchmark/models.json`
- Delete: `tools/benchmark/tests/test_runner.py`, `test_scorer.py`, `test_scorecard.py`, `test_registry.py`

- [ ] **Step 1: Confirm the legacy island has no external importers (safety gate)**

Run:
```bash
grep -rn --include="*.py" -E "tools\.benchmark\.(runner|scorer|scorecard|registry)" . | grep -v "/tools/benchmark/" | grep -vE "/\.venv/|/venv/"
```
Expected: **no output**. (Confirms only `tools/benchmark/` modules+tests import the legacy engine, including the `borda_normalize` re-export in `scorer.py`. `compiler/kpi/score.py` is the real home of `borda_normalize` and imports nothing from `tools`.) If there IS output, stop and report — a hidden dependency must be resolved first.

- [ ] **Step 2: Delete the legacy modules and their tests**

```bash
git rm tools/benchmark/runner.py tools/benchmark/scorer.py \
       tools/benchmark/scorecard.py tools/benchmark/registry.py \
       tools/benchmark/models.json \
       tools/benchmark/tests/test_runner.py tools/benchmark/tests/test_scorer.py \
       tools/benchmark/tests/test_scorecard.py tools/benchmark/tests/test_registry.py
```

- [ ] **Step 3: Restructure `cli.py` to a subcommand dispatcher**

Replace the entire imports-through-`main` region. The new top of `tools/benchmark/cli.py` (module docstring may be trimmed to describe only `score`) keeps exactly these imports:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.benchmark.paths import RUNS_DIR, SCORES_DIR
from common.run_context import now_iso
```

Delete `_main_run`, `_build_parser`, `_merge_with_prior_final`, and the `_DEFAULT_SYSTEM_PROMPT` constant entirely. Keep `_render_leaderboard_md`, `_render_score_table`, `_read_measurements`, `_scored_and_diag` unchanged for now (Tasks 3–4 modify them). Replace `_build_score_parser`, `main`, and `_score_command`'s signature with:

```python
def _add_score_args(p: argparse.ArgumentParser) -> None:
    """Register the `score` subcommand's arguments on its subparser."""
    p.add_argument(
        "run_dirs", nargs="+", metavar="RUN_DIR",
        help="One or more run-dir names (under --runs-root) to incorporate.",
    )
    p.add_argument(
        "--runs-root", type=Path, default=RUNS_DIR,
        help=f"Where per-run benchmark outputs land (default: {RUNS_DIR})",
    )
    p.add_argument(
        "--leaderboard", type=Path, default=SCORES_DIR / "leaderboard.json",
        help=(
            f"Persistent leaderboard file (default: {SCORES_DIR / 'leaderboard.json'}). "
            "Delete it to reset the ranking."
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point — kdb-benchmark dispatches to its subcommands."""
    effective = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="kdb-benchmark",
        description="Cross-model KPI leaderboard from kdb-orchestrate --emit-kpis runs.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    score_p = sub.add_parser(
        "score",
        help="Update the model leaderboard from --emit-kpis runs.",
        description=(
            "Incrementally update a model leaderboard by hierarchically Borda-"
            "ranking the scored KPIs from kdb-orchestrate --emit-kpis runs. Each "
            "run dir contributes one row keyed by its header.model (latest run per "
            "model wins); the leaderboard accumulates across invocations. No "
            "corpus_fingerprint gate — comparability is the user's judgment. Reset "
            "by deleting the --leaderboard file."
        ),
    )
    _add_score_args(score_p)
    args = parser.parse_args(effective)
    if args.command == "score":
        return _score_command(args)
    return 2  # unreachable: subparsers required=True


def _score_command(args: argparse.Namespace) -> int:
    runs_root: Path = args.runs_root
    leaderboard_path: Path = args.leaderboard
    # ... remainder of the existing _score_command body UNCHANGED, starting from
    #     the "models_to_rundir: dict[str, str] = {}" line ...
```

The remainder of `_score_command` (from `models_to_rundir = {}` onward) is unchanged — only its signature changes from `(argv: list[str])` to `(args: argparse.Namespace)`, and the two lines that read `args.run_dirs`/`args.runs_root`/`args.leaderboard` already match `argparse.Namespace`. Remove the old `parser = _build_score_parser(); args = parser.parse_args(argv)` lines at the top of `_score_command`.

- [ ] **Step 4: Prune the test files**

In `tools/benchmark/tests/test_score.py`, delete the `TestScoreExistingCLIUnchanged` class (the `--models` legacy-path test at ~line 318).

In `tools/benchmark/tests/test_cli.py`, delete every test that invokes the legacy run path (`--models`, `run_benchmark`, `score_run`, `build_*_scorecard`, registry-dropped checks). If NOTHING remains, delete the file with `git rm tools/benchmark/tests/test_cli.py`. Verify what it imports/exercises first:
```bash
grep -nE "def test|--models|run_benchmark|score_run|scorecard|registry" tools/benchmark/tests/test_cli.py
```

In `tools/benchmark/tests/test_paths.py`, remove any line asserting on `MODELS_JSON`:
```bash
grep -n "MODELS_JSON" tools/benchmark/tests/test_paths.py
```

- [ ] **Step 5: Drop the dead `MODELS_JSON` export**

Edit `tools/benchmark/paths.py` — delete line 27 (`MODELS_JSON = ...`). Leave `TRUTH_DIR` in place (flagged out-of-scope in the spec; harmless).

- [ ] **Step 6: Add a retirement guard test**

Create `tools/benchmark/tests/test_legacy_retired.py`:

```python
"""Guards that the legacy #5 run engine stays retired (spec 2026-06-06)."""
from __future__ import annotations

import importlib

import pytest

from tools.benchmark import cli


@pytest.mark.parametrize("mod", ["runner", "scorer", "scorecard", "registry"])
def test_legacy_modules_are_gone(mod):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"tools.benchmark.{mod}")


def test_score_subcommand_is_documented():
    parser_help = _capture_help(["--help"])
    assert "score" in parser_help


def test_models_flag_is_rejected():
    # The legacy --models entry point no longer exists; argparse rejects it.
    with pytest.raises(SystemExit):
        cli.main(["--models", "anything"])


def _capture_help(argv):
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        cli.main(argv)
    return buf.getvalue()
```

- [ ] **Step 7: Run the retirement guard + score tests**

Run:
```bash
pytest -m "not live" tools/benchmark/tests/test_legacy_retired.py tools/benchmark/tests/test_score.py tools/benchmark/tests/test_paths.py -q
```
Expected: PASS (legacy modules gone, `score` still works end-to-end, help lists `score`).

- [ ] **Step 8: Full suite + manual help check**

Run:
```bash
pytest -m "not live" -q
kdb-benchmark --help
kdb-benchmark score --help
```
Expected: suite green (legacy tests removed, no import errors). `kdb-benchmark --help` lists the `score` subcommand; `kdb-benchmark score --help` shows `run_dirs`/`--runs-root`/`--leaderboard`.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor(benchmark): retire legacy #5 run engine; score becomes a real subcommand

Delete runner/scorer/scorecard/registry + models.json (~1,900 LOC, self-
contained island) and their tests. main() now dispatches an argparse 'score'
subcommand so --help is honest. paths.py drops the dead MODELS_JSON export.
Per spec 2026-06-06-benchmark-cli-refactor-penalty-design."
```

---

## Task 2: Weak-spot penalty + 0–100 scaling in `score_models`

**Files:**
- Modify: `compiler/kpi/score.py` (add constants + `weak_spot_penalty`; extend `score_models`)
- Modify: `compiler/tests/test_kpi_score.py` (new `TestWeakSpotPenalty`; update `TestScoreModelsHierarchical` for the new scale + fields)

- [ ] **Step 1: Write the failing penalty unit tests**

Add to `compiler/tests/test_kpi_score.py`. First extend the import block at the top (currently `from compiler.kpi.score import (...)`) to also import:
```python
from compiler.kpi.score import (
    weak_spot_penalty,
    WEAK_SPOT_THRESHOLD,
    WEAK_SPOT_PENALTY_CAP,
    COMPOSITE_SCALE,
)
```
Then append:

```python
class TestWeakSpotPenalty:
    def test_balanced_model_no_penalty(self):
        # all four axes at/above tau=0.5 -> no glaring weak spot
        pkb = {"quarantine_rate": 0.6, "recovery_rate": 0.7, "latency": 0.5}
        penalty, weakest = weak_spot_penalty(pkb, graph_score=0.9)
        assert penalty == 0.0
        assert weakest == "latency"  # the min, but it is AT tau -> no penalty

    def test_weakest_zero_hits_cap(self):
        pkb = {"quarantine_rate": 1.0, "recovery_rate": 1.0, "latency": 1.0}
        penalty, weakest = weak_spot_penalty(pkb, graph_score=0.0)
        assert penalty == pytest.approx(WEAK_SPOT_PENALTY_CAP)  # 0.10
        assert weakest == "graph"

    def test_partial_weak_spot_linear(self):
        # weakest=0.15, tau=0.5 -> 0.10 * (0.5-0.15)/0.5 = 0.07
        pkb = {"quarantine_rate": 0.9, "recovery_rate": 0.9, "latency": 0.9}
        penalty, weakest = weak_spot_penalty(pkb, graph_score=0.15)
        assert penalty == pytest.approx(0.07)
        assert weakest == "graph"

    def test_threshold_boundary_is_zero(self):
        pkb = {"quarantine_rate": 0.5, "recovery_rate": 0.9, "latency": 0.9}
        penalty, _ = weak_spot_penalty(pkb, graph_score=0.9)
        assert penalty == 0.0  # weakest == tau exactly -> deadband

    def test_none_axes_skipped(self):
        # graph_score None and one processing KPI None -> min over present axes
        pkb = {"quarantine_rate": 0.1, "recovery_rate": None, "latency": 0.8}
        penalty, weakest = weak_spot_penalty(pkb, graph_score=None)
        assert weakest == "quarantine_rate"
        assert penalty == pytest.approx(0.10 * (0.5 - 0.1) / 0.5)  # 0.08

    def test_no_present_axis_returns_zero_none(self):
        penalty, weakest = weak_spot_penalty({}, graph_score=None)
        assert penalty == 0.0
        assert weakest is None
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest -m "not live" compiler/tests/test_kpi_score.py::TestWeakSpotPenalty -q`
Expected: FAIL with `ImportError: cannot import name 'weak_spot_penalty'`.

- [ ] **Step 3: Implement constants + `weak_spot_penalty` in `compiler/kpi/score.py`**

After the `GRAPH_WEIGHTS` block (line ~74) and before `_PROCESSING_KPIS`, add:

```python
# Weak-spot penalty (spec 2026-06-06): punish a lopsided model with a glaring
# weak spot. Range over the four COMPOSITE axes (3 processing Borda values +
# the combined graph_score) — NOT the 7 raw KPIs — at equal treatment.
WEAK_SPOT_THRESHOLD = 0.5    # tau: below mid-field => "glaring". PARKED for calibration.
WEAK_SPOT_PENALTY_CAP = 0.10  # lambda: max deduction (10 pts on the 0-100 scale). PINNED.

# Headline composite is rendered 0-100; components (per_kpi_borda, graph_score)
# stay Borda-native [0,1].
COMPOSITE_SCALE = 100
```

Then add the function (next to `_hierarchical_composite`):

```python
def weak_spot_penalty(
    per_kpi_borda: dict, graph_score: float | None
) -> tuple[float, str | None]:
    """Penalty for a model's single weakest composite axis (spec 2026-06-06).

    Axes = the three processing Borda values (quarantine_rate / recovery_rate /
    latency, from ``per_kpi_borda``) plus the combined ``graph_score`` — four
    axes, each in [0,1], equal treatment. graph counts as ONE axis (its four
    sub-KPIs are already blended in graph_score).

    ``weakest`` = min over the *present* (non-None) axes. Penalty rises linearly
    from 0 at the deadband (weakest >= WEAK_SPOT_THRESHOLD) to WEAK_SPOT_PENALTY_CAP
    at weakest == 0. Returns ``(penalty in [0, CAP], weakest_axis_label | None)``.
    No present axis -> ``(0.0, None)``.
    """
    axes: dict[str, float | None] = {
        "quarantine_rate": per_kpi_borda.get("quarantine_rate"),
        "recovery_rate":   per_kpi_borda.get("recovery_rate"),
        "latency":         per_kpi_borda.get("latency"),
        "graph":           graph_score,
    }
    present = {k: v for k, v in axes.items() if v is not None}
    if not present:
        return 0.0, None
    weakest_kpi = min(present, key=lambda k: present[k])
    weakest = present[weakest_kpi]
    tau = WEAK_SPOT_THRESHOLD
    penalty = WEAK_SPOT_PENALTY_CAP * max(0.0, (tau - weakest) / tau)
    return penalty, weakest_kpi
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest -m "not live" compiler/tests/test_kpi_score.py::TestWeakSpotPenalty -q`
Expected: PASS.

- [ ] **Step 5: Extend `score_models` to apply the penalty + scale, with updated tests first**

Update `TestScoreModelsHierarchical` in `compiler/tests/test_kpi_score.py` for the new contract. Replace `test_missing_graph_kpi_keeps_graph_at_40_percent`'s composite asserts and `test_result_shape`:

```python
    def test_missing_graph_kpi_keeps_graph_at_40_percent(self):
        models = [
            {"model": "X", "scored": {
                "quarantine_rate": 0.0, "recovery_rate": 0.0, "latency": 100.0,
                "graph_connectivity": 0.5, "link_density": 5.0,
                "supports_density": 8.0, "entity_reuse": None}},
            {"model": "Y", "scored": {
                "quarantine_rate": 0.0, "recovery_rate": 0.0, "latency": 100.0,
                "graph_connectivity": 0.1, "link_density": 1.0,
                "supports_density": 2.0, "entity_reuse": 0.3}},
        ]
        pm = score_models(models)["per_model"]
        # graph_score unchanged ([0,1] component): X=1.0, Y=0.15
        assert pm["X"]["graph_score"] == pytest.approx(1.0)
        assert pm["Y"]["graph_score"] == pytest.approx(0.15)
        # X: processing tied (0.5 each), graph 1.0 -> pre = 0.70.
        #    weakest axis = 0.5 (processing) == tau -> penalty 0. composite = 70.0
        assert pm["X"]["composite_pre_penalty"] == pytest.approx(70.0)
        assert pm["X"]["penalty"] == pytest.approx(0.0)
        assert pm["X"]["composite"] == pytest.approx(70.0)
        # Y: pre = 0.30 + 0.40*0.15 = 0.36. weakest = graph 0.15 -> penalty
        #    0.10*(0.5-0.15)/0.5 = 0.07. composite = 0.29. Scaled: pre 36, pen 7, comp 29
        assert pm["Y"]["composite_pre_penalty"] == pytest.approx(36.0)
        assert pm["Y"]["penalty"] == pytest.approx(7.0)
        assert pm["Y"]["weakest_kpi"] == "graph"
        assert pm["Y"]["composite"] == pytest.approx(29.0)

    def test_result_shape(self):
        models = [
            {"model": "A", "scored": {"quarantine_rate": 0.0, "recovery_rate": 0.0,
                                      "latency": 1.0, "graph_connectivity": 0.2,
                                      "link_density": 2.0, "supports_density": 5.0,
                                      "entity_reuse": 0.1}},
        ]
        res = score_models(models)
        assert set(res) == {"per_model", "top_weights", "graph_weights", "penalty_params"}
        assert set(res["per_model"]["A"]) == {
            "composite", "composite_pre_penalty", "penalty", "weakest_kpi",
            "graph_score", "per_kpi_borda",
        }
        assert res["penalty_params"] == {
            "threshold": WEAK_SPOT_THRESHOLD, "cap": WEAK_SPOT_PENALTY_CAP}
        # single model -> every KPI borda 1.0 -> pre 1.0, no penalty -> 100.0
        assert res["per_model"]["A"]["composite"] == pytest.approx(100.0)
```

Run: `pytest -m "not live" compiler/tests/test_kpi_score.py::TestScoreModelsHierarchical -q`
Expected: FAIL (`KeyError: 'composite_pre_penalty'` / shape mismatch).

- [ ] **Step 6: Implement the `score_models` change**

In `compiler/kpi/score.py`, replace the `score_models` per-model loop body and return:

```python
    base = borda_score(models)  # only per_kpi_borda is used (weight-independent)
    per_model: dict[str, dict] = {}
    for m in models:
        slug = m["model"]
        pkb = base["per_model"][slug]["per_kpi_borda"]
        gscore = combined_graph_score(pkb)
        pre = _hierarchical_composite(pkb, gscore)
        penalty, weakest_kpi = weak_spot_penalty(pkb, gscore)
        post = max(0.0, pre - penalty)
        per_model[slug] = {
            "composite": post * COMPOSITE_SCALE,
            "composite_pre_penalty": pre * COMPOSITE_SCALE,
            "penalty": penalty * COMPOSITE_SCALE,
            "weakest_kpi": weakest_kpi,
            "graph_score": gscore,
            "per_kpi_borda": pkb,
        }
    return {
        "per_model": per_model,
        "top_weights": dict(TOP_WEIGHTS),
        "graph_weights": dict(GRAPH_WEIGHTS),
        "penalty_params": {
            "threshold": WEAK_SPOT_THRESHOLD,
            "cap": WEAK_SPOT_PENALTY_CAP,
        },
    }
```

Also update the `score_models` docstring's "Returns" block to list the new fields (`composite_pre_penalty`, `penalty`, `weakest_kpi`) and `penalty_params`.

- [ ] **Step 7: Run to verify pass**

Run: `pytest -m "not live" compiler/tests/test_kpi_score.py -q`
Expected: PASS (penalty units + updated hierarchical tests).

- [ ] **Step 8: Commit**

```bash
git add compiler/kpi/score.py compiler/tests/test_kpi_score.py
git commit -m "feat(kpi): weak-spot penalty + 0-100 composite scale in score_models

min over the 4 composite axes (3 processing Borda + combined graph_score),
equal treatment; penalty = 0.10*max(0, 0.5-weakest)/0.5 (cap 0.10), subtracted
from the composite. Headline composite/pre/penalty scaled x100. Per spec
2026-06-06; tau=0.5 parked, lambda=0.10 pinned."
```

---

## Task 3: Surface penalty fields in the leaderboard JSON

**Files:**
- Modify: `tools/benchmark/cli.py` (`_score_command` — extend `ranking` rows + persisted payload)
- Modify: `tools/benchmark/tests/test_score.py` (assert new fields + 0–100 scale)

- [ ] **Step 1: Write the failing leaderboard-field test**

Add to `tools/benchmark/tests/test_score.py`. Reuse the existing module-level `_make_measurements(...)` helper (defined at the top of the file). Two models with tied processing KPIs and opposite graph KPIs: model-a wins every graph KPI (graph_score Borda → 1.0), model-b loses them all (graph_score → 0.0, weakest axis = `graph` = 0.0 → penalty hits the cap):

```python
class TestPenaltyFieldsPersisted:
    def test_ranking_rows_carry_penalty_fields(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="model-a-T1", model="model-a", runs_root=runs_root,
                           entity_reuse=0.9, graph_connectivity=0.9,
                           link_density=9.0, supports_density=9.0)
        _make_measurements(run_dir="model-b-T1", model="model-b", runs_root=runs_root,
                           entity_reuse=0.1, graph_connectivity=0.1,
                           link_density=1.0, supports_density=1.0)
        rc = cli.main(["score", "model-a-T1", "model-b-T1",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        payload = _load(lb)
        assert payload["penalty_params"] == {"threshold": 0.5, "cap": 0.10}
        for row in payload["ranking"]:
            assert set(row) >= {
                "model", "rank", "composite", "composite_pre_penalty",
                "penalty", "weakest_kpi", "graph_score", "per_kpi_borda",
            }
            assert 0.0 <= row["composite"] <= 100.0     # 0-100 scale
            assert 0.0 <= row["penalty"] <= 10.0
        by = {r["model"]: r for r in payload["ranking"]}
        # model-b is lopsided on graph (graph_score Borda 0.0) -> capped penalty
        assert by["model-b"]["weakest_kpi"] == "graph"
        assert by["model-b"]["penalty"] == pytest.approx(10.0)
        assert by["model-a"]["penalty"] == pytest.approx(0.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest -m "not live" tools/benchmark/tests/test_score.py::TestPenaltyFieldsPersisted -q`
Expected: FAIL (`KeyError`/`assert` on missing `penalty`, `composite_pre_penalty`, or `penalty_params`).

- [ ] **Step 3: Extend `ranking` rows + payload in `_score_command`**

In `tools/benchmark/cli.py`, replace the `ranking = sorted(...)` comprehension and the `payload` dict:

```python
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
        key=lambda r: -(r["composite"] or 0.0),
    )
    for i, row in enumerate(ranking, start=1):
        row["rank"] = i

    payload: dict = {
        "models": models_to_rundir,
        "ranking": ranking,
        "top_weights": result["top_weights"],
        "graph_weights": result["graph_weights"],
        "penalty_params": result["penalty_params"],
        "updated_at": now_iso(),
    }
```

- [ ] **Step 4: Run to verify pass + regression**

Run: `pytest -m "not live" tools/benchmark/tests/test_score.py -q`
Expected: PASS. If a pre-existing test asserts an exact composite value in [0,1] (e.g. `0.82`), update it to the ×100 value (`82.0`, ± any penalty) — re-derive from the test's inputs, do not guess.

- [ ] **Step 5: Commit**

```bash
git add tools/benchmark/cli.py tools/benchmark/tests/test_score.py
git commit -m "feat(benchmark): persist penalty fields + penalty_params in leaderboard.json"
```

---

## Task 4: Render the PENALTY column (terminal + Markdown)

**Files:**
- Modify: `tools/benchmark/cli.py` (`_render_score_table`, `_render_leaderboard_md`)
- Modify: `tools/benchmark/tests/test_score.py` (assert the rendered column appears)

- [ ] **Step 1: Write the failing render test**

Add to `tools/benchmark/tests/test_score.py` (the `.md` is written to `leaderboard_path.with_suffix(".md")`, i.e. `tmp_path/leaderboard.md`):

```python
class TestPenaltyRendered:
    def test_md_shows_penalty_column(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="model-a-T1", model="model-a", runs_root=runs_root,
                           entity_reuse=0.9, graph_connectivity=0.9,
                           link_density=9.0, supports_density=9.0)
        _make_measurements(run_dir="model-b-T1", model="model-b", runs_root=runs_root,
                           entity_reuse=0.1, graph_connectivity=0.1,
                           link_density=1.0, supports_density=1.0)
        rc = cli.main(["score", "model-a-T1", "model-b-T1",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        md = (tmp_path / "leaderboard.md").read_text()
        assert "PENALTY" in md
        assert "score (0-100)" in md
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest -m "not live" tools/benchmark/tests/test_score.py::TestPenaltyRendered -q`
Expected: FAIL (no penalty column in the Markdown).

- [ ] **Step 3: Add the PENALTY column to `_render_leaderboard_md`**

In `_render_leaderboard_md`, replace the ranking-table header and rows (the `head = [...]` / `for r in ranking:` block). Show processing Borda (`[0,1]`), `graph_score` (`[0,1]`), then the three scaled columns:

```python
    def fmt2(v) -> str:
        return "—" if v is None else f"{v:.2f}"

    # --- ranking (Borda) ---
    head = (["rank", "model"] + [f"{k} ↓" for k in proc_kpis]
            + ["graph_score ↑", "pre-pen", "PENALTY", "score (0-100)"])
    lines.append(row(head))
    lines.append(sep(len(head)))
    for r in ranking:
        pkb = r.get("per_kpi_borda", {})
        cells = [str(r.get("rank", "")), str(r.get("model", ""))]
        cells += [fmt(pkb.get(k)) for k in proc_kpis]
        cells.append(fmt(r.get("graph_score")))
        cells.append(fmt2(r.get("composite_pre_penalty")))
        pen = r.get("penalty") or 0.0
        wk = r.get("weakest_kpi")
        cells.append(f"{fmt2(r.get('penalty'))} ({wk})" if pen > 0 and wk else fmt2(r.get("penalty")))
        cells.append(fmt2(r.get("composite")))
        lines.append(row(cells))
    lines.append("")
```

- [ ] **Step 4: Add the PENALTY column to `_render_score_table` (terminal)**

In `_render_score_table`, after the existing `cols = proc_kpis + ["graph_score"]` header/row logic, extend each ranking row to append the three scaled values. Replace the `for row in ranking:` loop body:

```python
    for row in ranking:
        pkb = row.get("per_kpi_borda", {})
        cells = [_cell(pkb.get(k)) for k in proc_kpis]
        cells.append(_cell(row.get("graph_score")))
        cellstr = "  ".join(f"{c:>20}" for c in cells)
        pre = row.get("composite_pre_penalty")
        pen = row.get("penalty")
        comp = row.get("composite")
        wk = row.get("weakest_kpi")
        pen_str = f"{pen:.2f}" if isinstance(pen, (int, float)) else "n/a"
        if isinstance(pen, (int, float)) and pen > 0 and wk:
            pen_str = f"{pen:.2f}({wk})"
        lines.append(
            f"{row.get('rank', 0):>4}  {row.get('model', ''):<32}  {cellstr}  "
            f"{(f'{pre:.2f}' if isinstance(pre,(int,float)) else 'n/a'):>9}  "
            f"{pen_str:>14}  {(f'{comp:.2f}' if isinstance(comp,(int,float)) else 'n/a'):>9}"
        )
```

Also update the header line above the loop to include `pre-pen`, `PENALTY`, `score`:
```python
    lines.append(
        f"{'rank':>4}  {'model':<32}  {header}  "
        f"{'pre-pen':>9}  {'PENALTY':>14}  {'score':>9}"
    )
```
(The footer NOTE about "composite & graph_score comparable only within this set" stays; you may append "— score is post-penalty, 0-100.")

- [ ] **Step 5: Run to verify pass**

Run: `pytest -m "not live" tools/benchmark/tests/test_score.py -q`
Expected: PASS.

- [ ] **Step 6: Regenerate the live leaderboard as a smoke check (free — no API)**

The two existing run dirs from the §6 cohort are under `benchmark/runs/`. Re-score them to eyeball the new columns:
```bash
ls benchmark/runs/   # find the two <model>-<run_id> dirs
kdb-benchmark score <gemini-dir> <deepseek-dir>
cat benchmark/scores/leaderboard.md
```
Expected: terminal table + `leaderboard.md` show `PENALTY` and 0–100 scores; deepseek still ranks #1. (Leaderboard files are gitignored — this is a visual check, nothing to commit.)

- [ ] **Step 7: Commit**

```bash
git add tools/benchmark/cli.py tools/benchmark/tests/test_score.py
git commit -m "feat(benchmark): render PENALTY column + 0-100 score (terminal + leaderboard.md)"
```

---

## Task 5: Docs close-out

**Files:**
- Modify: `docs/TASKS.md` (#109 narrative: legacy engine retired + penalty added)

- [ ] **Step 1: Update the #109 ledger entry**

In `docs/TASKS.md`, extend the #109 entry: note the legacy #5 engine retirement (single-purpose `kdb-benchmark score`) and the weakest-link penalty (4 axes, cap 0.10, τ=0.5 parked, 0–100 score). Keep it to 2–3 lines consistent with the surrounding entries. Do NOT add a `CODEBASE_OVERVIEW.md` Milestone Changelog entry yet — that lands when #109 fully closes after weight calibration (per the project's milestone-closure rule).

- [ ] **Step 2: Full suite green + commit**

Run: `pytest -m "not live" -q`
Expected: green.
```bash
git add docs/TASKS.md
git commit -m "docs(tasks): #109 — legacy engine retired + weak-spot penalty shipped"
```

---

## Final verification (after all tasks)

Run:
```bash
pytest -m "not live" -q
kdb-benchmark --help
grep -rn --include="*.py" -E "tools\.benchmark\.(runner|scorer|scorecard|registry)" . | grep -v "/\.venv/" | grep -v "/venv/"
```
Expected: suite green; `--help` lists `score`; the grep returns nothing (legacy fully gone). Then use `superpowers:finishing-a-development-branch`.
