"""Tests for the `score` subcommand of tools.benchmark.cli (Task #109).

Covers:
- Happy-path: 3 synthetic measurements.json → score command → assert JSON output
  has per-model composites + per-kpi Borda.
- Mismatched corpus_fingerprint → rejected with non-zero exit code.
- Latest-per-group_key selection when two runs share a group_key.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.benchmark import cli


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_measurements(
    *,
    run_id: str,
    group_key: str,
    corpus_fingerprint: str,
    quarantine_rate: float | None,
    intervention_burden: float | None,
    latency: float | None,
    dangling_link_rate: float | None,
    entity_reuse: float | None = None,
    graph_connectivity: float | None = None,
    runs_root: Path,
) -> None:
    """Write a synthetic measurements.json to <runs_root>/<run_id>/."""
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "header": {
            "run_id": run_id,
            "group_key": group_key,
            "corpus_fingerprint": corpus_fingerprint,
            "pass1_prompt_version": "1.0",
            "pass2_prompt_version": "2.0",
            "scanned": 10,
            "to_compile": 8,
            "signal": 8,
            "noise": 2,
            "p1_attempted": 8,
            "p2_attempted": 8,
        },
        "processing": {
            "scored": {
                "quarantine_rate": quarantine_rate,
                "intervention_burden": intervention_burden,
                "latency": latency,
            },
            "diagnostic": {
                "retry_load": 0.05,
                "token_overrun_rate": 0.01,
                "repair_rung_rate": 0.02,
                "semantic_pass_rate": 0.95,
                "signal_noise_ratio": 0.8,
                "quarantine_rate_pass1": 0.01,
                "quarantine_rate_pass2": 0.02,
            },
        },
        "graph": {
            "scored": {
                "dangling_link_rate": dangling_link_rate,
            },
            "watched": {
                "entity_reuse": entity_reuse,
                "graph_connectivity": graph_connectivity,
                "orphan_rate": 0.05,
                "entity_search_key_resolution": None,
            },
            "diagnostic": {
                "belongs_to_coverage": 0.9,
                "domain_null_rate": 0.1,
                "link_density": 3.2,
                "supports_density": 2.1,
                "domain_breadth": 0.65,
            },
        },
    }
    (run_dir / "measurements.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestScoreHappyPath:
    """3 synthetic runs → score → valid scorecard JSON."""

    def test_scorecard_written_with_per_model_composites_and_kpi_borda(
        self, tmp_path
    ):
        runs_root = tmp_path / "benchmark" / "runs"
        scores_dir = tmp_path / "benchmark" / "scores"

        _make_measurements(
            run_id="2026-06-01T10-00-00_EDT-model-a",
            group_key="provider-a:model-a:1.0/2.0",
            corpus_fingerprint="abc123",
            quarantine_rate=0.01,
            intervention_burden=0.05,
            latency=1500.0,
            dangling_link_rate=0.10,
            runs_root=runs_root,
        )
        _make_measurements(
            run_id="2026-06-01T10-00-01_EDT-model-b",
            group_key="provider-b:model-b:1.0/2.0",
            corpus_fingerprint="abc123",
            quarantine_rate=0.05,
            intervention_burden=0.10,
            latency=2000.0,
            dangling_link_rate=0.20,
            runs_root=runs_root,
        )
        _make_measurements(
            run_id="2026-06-01T10-00-02_EDT-model-c",
            group_key="provider-c:model-c:1.0/2.0",
            corpus_fingerprint="abc123",
            quarantine_rate=0.02,
            intervention_burden=0.07,
            latency=1800.0,
            dangling_link_rate=0.15,
            runs_root=runs_root,
        )

        rc = cli.main([
            "score",
            "2026-06-01T10-00-00_EDT-model-a",
            "2026-06-01T10-00-01_EDT-model-b",
            "2026-06-01T10-00-02_EDT-model-c",
            "--runs-root", str(runs_root),
            "--scores-dir", str(scores_dir),
        ])

        assert rc == 0, f"expected exit code 0, got {rc}"

        scorecard_files = list(scores_dir.glob("*.json"))
        assert len(scorecard_files) == 1, "expected exactly one scorecard file"

        data = json.loads(scorecard_files[0].read_text(encoding="utf-8"))

        # Top-level structure
        assert "borda" in data
        assert "candidate_set" in data
        assert sorted(data["candidate_set"]) == sorted([
            "provider-a:model-a:1.0/2.0",
            "provider-b:model-b:1.0/2.0",
            "provider-c:model-c:1.0/2.0",
        ])

        # Per-model composite + per-kpi Borda
        per_model = data["borda"]["per_model"]
        assert len(per_model) == 3

        for gk, entry in per_model.items():
            assert "composite" in entry, f"missing 'composite' for {gk}"
            assert isinstance(entry["composite"], float), f"composite not float for {gk}"
            assert "per_kpi_borda" in entry, f"missing 'per_kpi_borda' for {gk}"
            # All four scored KPIs should be present
            for kpi in ("quarantine_rate", "intervention_burden", "latency",
                        "dangling_link_rate"):
                assert kpi in entry["per_kpi_borda"], (
                    f"missing KPI '{kpi}' in per_kpi_borda for {gk}"
                )

        # Weights present
        assert "weights" in data["borda"]

        # corpus_fingerprint carried
        assert data["corpus_fingerprint"] == "abc123"

    def test_scorecard_has_diagnostics_by_model(self, tmp_path):
        """Scorecard carries diagnostics/watched for human inspection."""
        runs_root = tmp_path / "runs"
        scores_dir = tmp_path / "scores"

        _make_measurements(
            run_id="2026-06-02T09-00-00_EDT-ma",
            group_key="prov:ma:1/2",
            corpus_fingerprint="fp1",
            quarantine_rate=0.01,
            intervention_burden=0.05,
            latency=1500.0,
            dangling_link_rate=0.10,
            runs_root=runs_root,
        )
        _make_measurements(
            run_id="2026-06-02T09-00-01_EDT-mb",
            group_key="prov:mb:1/2",
            corpus_fingerprint="fp1",
            quarantine_rate=0.03,
            intervention_burden=0.07,
            latency=1700.0,
            dangling_link_rate=0.12,
            runs_root=runs_root,
        )

        rc = cli.main([
            "score",
            "2026-06-02T09-00-00_EDT-ma",
            "2026-06-02T09-00-01_EDT-mb",
            "--runs-root", str(runs_root),
            "--scores-dir", str(scores_dir),
        ])
        assert rc == 0

        data = json.loads(list(scores_dir.glob("*.json"))[0].read_text())
        assert "diagnostics_by_model" in data
        assert "prov:ma:1/2" in data["diagnostics_by_model"]
        assert "prov:mb:1/2" in data["diagnostics_by_model"]


class TestScoreFingerprintMismatch:
    """Two runs with different corpus_fingerprints → rejected."""

    def test_mismatched_fingerprint_returns_nonzero(self, tmp_path, capsys):
        runs_root = tmp_path / "runs"
        scores_dir = tmp_path / "scores"

        _make_measurements(
            run_id="2026-06-01T10-00-00_EDT-ma",
            group_key="prov:ma:1/2",
            corpus_fingerprint="fingerprint-X",
            quarantine_rate=0.01,
            intervention_burden=0.05,
            latency=1500.0,
            dangling_link_rate=0.10,
            runs_root=runs_root,
        )
        _make_measurements(
            run_id="2026-06-01T10-00-01_EDT-mb",
            group_key="prov:mb:1/2",
            corpus_fingerprint="fingerprint-Y-DIFFERENT",
            quarantine_rate=0.02,
            intervention_burden=0.06,
            latency=1600.0,
            dangling_link_rate=0.11,
            runs_root=runs_root,
        )

        rc = cli.main([
            "score",
            "2026-06-01T10-00-00_EDT-ma",
            "2026-06-01T10-00-01_EDT-mb",
            "--runs-root", str(runs_root),
            "--scores-dir", str(scores_dir),
        ])

        assert rc != 0, "expected non-zero exit for fingerprint mismatch"
        err = capsys.readouterr().err
        assert "corpus_fingerprint" in err.lower() or "mismatch" in err.lower(), (
            f"expected fingerprint mismatch message in stderr, got: {err!r}"
        )

        # No scorecard should have been written
        assert not list(scores_dir.glob("*.json"))


class TestScoreLatestPerGroupKey:
    """When two run_ids share a group_key, the lexically-latest run_id wins."""

    def test_later_run_id_supersedes_earlier(self, tmp_path, capsys):
        runs_root = tmp_path / "runs"
        scores_dir = tmp_path / "scores"

        # Earlier run for model-a
        _make_measurements(
            run_id="2026-06-01T08-00-00_EDT-ma",
            group_key="prov:ma:1/2",
            corpus_fingerprint="fp_same",
            quarantine_rate=0.10,  # worse
            intervention_burden=0.20,
            latency=3000.0,
            dangling_link_rate=0.40,
            runs_root=runs_root,
        )
        # Later run for model-a (same group_key, should win)
        _make_measurements(
            run_id="2026-06-01T12-00-00_EDT-ma",
            group_key="prov:ma:1/2",
            corpus_fingerprint="fp_same",
            quarantine_rate=0.01,  # better
            intervention_burden=0.05,
            latency=1500.0,
            dangling_link_rate=0.10,
            runs_root=runs_root,
        )
        # Different model
        _make_measurements(
            run_id="2026-06-01T10-00-00_EDT-mb",
            group_key="prov:mb:1/2",
            corpus_fingerprint="fp_same",
            quarantine_rate=0.03,
            intervention_burden=0.08,
            latency=1700.0,
            dangling_link_rate=0.15,
            runs_root=runs_root,
        )

        rc = cli.main([
            "score",
            "2026-06-01T08-00-00_EDT-ma",   # earlier
            "2026-06-01T12-00-00_EDT-ma",   # later — should win
            "2026-06-01T10-00-00_EDT-mb",
            "--runs-root", str(runs_root),
            "--scores-dir", str(scores_dir),
        ])

        assert rc == 0
        out = capsys.readouterr().out

        scorecard_files = list(scores_dir.glob("*.json"))
        assert len(scorecard_files) == 1

        data = json.loads(scorecard_files[0].read_text())

        # Only two unique group_keys should be in the scorecard
        assert len(data["borda"]["per_model"]) == 2

        # The run_ids_used dict should point at the LATER run for prov:ma:1/2
        run_ids_used = data["run_ids_used"]
        assert run_ids_used["prov:ma:1/2"] == "2026-06-01T12-00-00_EDT-ma", (
            f"expected later run to be selected, got: {run_ids_used['prov:ma:1/2']!r}"
        )

        # Score should confirm it skipped the earlier run
        assert "skipped" in out.lower() or "superseded" in out.lower(), (
            f"expected a 'skipped/superseded' message in stdout, got: {out!r}"
        )

    def test_group_key_deduplication_reduces_candidate_set(self, tmp_path):
        """Two runs for the same group_key → only ONE model entry in scorecard."""
        runs_root = tmp_path / "runs"
        scores_dir = tmp_path / "scores"

        for ts in ("2026-06-03T10-00-00_EDT", "2026-06-03T11-00-00_EDT"):
            _make_measurements(
                run_id=f"{ts}-mx",
                group_key="prov:mx:1/2",
                corpus_fingerprint="fp_dedup",
                quarantine_rate=0.02,
                intervention_burden=0.05,
                latency=1500.0,
                dangling_link_rate=0.10,
                runs_root=runs_root,
            )

        rc = cli.main([
            "score",
            "2026-06-03T10-00-00_EDT-mx",
            "2026-06-03T11-00-00_EDT-mx",
            "--runs-root", str(runs_root),
            "--scores-dir", str(scores_dir),
        ])
        assert rc == 0

        data = json.loads(list(scores_dir.glob("*.json"))[0].read_text())
        assert len(data["borda"]["per_model"]) == 1
        assert list(data["borda"]["per_model"].keys()) == ["prov:mx:1/2"]


class TestScoreExistingCLIUnchanged:
    """The legacy --models path must still work after score dispatch was added."""

    def test_legacy_path_reached_with_models_flag(self, tmp_path, monkeypatch):
        """Verify that passing --models still hits _main_run (not score).

        We confirm this by monkeypatching _main_run to track calls.
        """
        calls = []

        def fake_main_run(argv):
            calls.append(argv)
            return 0

        monkeypatch.setattr("tools.benchmark.cli._main_run", fake_main_run)

        rc = cli.main(["--models", "some-model"])
        assert rc == 0
        assert calls, "expected _main_run to be called"
        assert "--models" in calls[0]
