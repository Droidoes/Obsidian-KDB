"""Tests for kdb_benchmark.scorecard — Task #22 cross-model scorecard.

Renders list[RunScore] post-Borda as JSON + terminal table. Round 4 DC4:
the scorecard MUST emit a 'comparable only within candidate set' disclaimer
to make the within-candidate-set rank semantics honest.
"""
from __future__ import annotations

import json
from pathlib import Path

from kdb_benchmark import scorecard
from kdb_benchmark.scorer import MeasureScore, RunScore


def _runscore(
    *,
    model_id: str,
    final_score: float,
    m6_borda: float,
    m7_borda: float,
    m6_rate: float,
    m7_rate: float,
    ran_at: str = "2026-05-06T14-32-15_EDT",
    penalty: float = 0.0,
) -> RunScore:
    return RunScore(
        run_id=f"{model_id}-{ran_at}",
        model_id=model_id,
        provider="anthropic",
        model="m",
        n_attempted=5,
        s0=MeasureScore("S0", 5, 5, 1.0, 0.20),
        s1=MeasureScore("S1", 5, 5, 1.0, 0.0),
        s2=MeasureScore("S2", 5, 5, 1.0, 0.0),
        s3=MeasureScore("S3", 5, 5, 1.0, 0.0),
        measures={
            "M1": MeasureScore("M1", 1, 1, 1.0, 0.20),
            "M2": MeasureScore("M2", 1, 1, 1.0, 0.05),
            "M3": MeasureScore("M3", 1, 1, 1.0, 0.05),
            "M4": MeasureScore("M4", 5, 5, 1.0, 0.15),
            "M5": MeasureScore("M5", 1, 1, 1.0, 0.05),
            "M6": MeasureScore("M6", 0.001, 1000, m6_rate, 0.15),
            "M7": MeasureScore("M7", 2000, 1000, m7_rate, 0.15),
        },
        diagnostics={
            "retry_load":              MeasureScore("retry_load", 0, 10, 0.0, 0.0),
            "token_overrun_rate":      MeasureScore("token_overrun_rate", 0, 5, 0.0, 0.0),
            "pages_per_1k_source_words": MeasureScore("pages_per_1k_source_words", 5, 5000, 1.0, 0.0),
        },
        m6_borda=m6_borda,
        m7_borda=m7_borda,
        final_score_pre_penalty=final_score,  # treat provided value as pre-penalty for test fixtures
        penalty=penalty,
        final_score=final_score,
    )


class TestScorecardJSON:
    def test_to_dict_has_expected_top_level_fields(self):
        runs = [
            _runscore(model_id="haiku-4.5",  final_score=0.85, m6_borda=1.0, m7_borda=1.0,
                      m6_rate=0.001, m7_rate=2000),
            _runscore(model_id="sonnet-4.6", final_score=0.72, m6_borda=0.0, m7_borda=0.0,
                      m6_rate=0.018, m7_rate=3500),
        ]
        sc = scorecard.build_scorecard(runs)
        d = sc.to_dict()
        assert "scorecard_id" in d
        assert "candidate_set" in d
        assert "emitted_at" in d
        assert "disclaimer" in d
        assert "models" in d
        assert sorted(d["candidate_set"]) == ["haiku-4.5", "sonnet-4.6"]

    def test_models_ordered_by_final_score_descending(self):
        """Top-ranked model first."""
        runs = [
            _runscore(model_id="loser", final_score=0.50, m6_borda=0.0, m7_borda=0.0, m6_rate=1.0, m7_rate=1.0),
            _runscore(model_id="winner", final_score=0.90, m6_borda=1.0, m7_borda=1.0, m6_rate=0.5, m7_rate=0.5),
        ]
        sc = scorecard.build_scorecard(runs)
        d = sc.to_dict()
        assert d["models"][0]["model_id"] == "winner"
        assert d["models"][1]["model_id"] == "loser"

    def test_disclaimer_mentions_candidate_set(self):
        """Round 4 DC4: must say final_score is comparable only within
        the candidate set."""
        runs = [_runscore(model_id="x", final_score=0.5, m6_borda=0.5, m7_borda=0.5, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_scorecard(runs)
        d = sc.to_dict()
        assert "candidate set" in d["disclaimer"].lower() or "candidate_set" in d["disclaimer"]
        assert "raw rates" in d["disclaimer"].lower() or "raw" in d["disclaimer"]


class TestScorecardTerminalRender:
    def test_render_includes_model_ids(self):
        runs = [
            _runscore(model_id="haiku-4.5",  final_score=0.85, m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000),
            _runscore(model_id="sonnet-4.6", final_score=0.72, m6_borda=0.0, m7_borda=0.0, m6_rate=0.018, m7_rate=3500),
        ]
        text = scorecard.render_terminal(scorecard.build_scorecard(runs))
        assert "haiku-4.5" in text
        assert "sonnet-4.6" in text

    def test_render_includes_final_score_column(self):
        runs = [_runscore(model_id="x", final_score=0.85, m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        text = scorecard.render_terminal(scorecard.build_scorecard(runs))
        assert "0.85" in text or "0.850" in text

    def test_render_includes_raw_m6_m7_for_inspection(self):
        runs = [_runscore(model_id="x", final_score=0.85, m6_borda=1.0, m7_borda=1.0, m6_rate=0.0042, m7_rate=2400)]
        text = scorecard.render_terminal(scorecard.build_scorecard(runs))
        # Raw rates surfaced beneath the table
        assert "0.0042" in text or "$" in text       # cost rate label or value
        assert "2400" in text or "ms" in text        # latency rate label or value

    def test_render_includes_disclaimer(self):
        runs = [_runscore(model_id="x", final_score=0.85, m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        text = scorecard.render_terminal(scorecard.build_scorecard(runs))
        assert "candidate" in text.lower()

    def test_render_includes_penalty_column_header(self):
        """D31 (Task #62): PENALTY column appears between M7_b and FINAL in header."""
        runs = [_runscore(model_id="x", final_score=0.85, m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        text = scorecard.render_terminal(scorecard.build_scorecard(runs))
        assert "PENALTY" in text

    def test_render_zero_penalty_shows_dash(self):
        """A run with penalty=0.0 renders '-' in the PENALTY column."""
        runs = [_runscore(model_id="x", final_score=0.85, m6_borda=1.0, m7_borda=1.0,
                          m6_rate=0.001, m7_rate=2000, penalty=0.0)]
        text = scorecard.render_terminal(scorecard.build_scorecard(runs))
        # The penalty column shows '-' for zero penalty
        assert "PENALTY" in text
        # Row should contain a dash in the penalty slot (not a deduction value)
        lines = [l for l in text.splitlines() if "x" in l and "1.000" in l]
        assert any("-" in l for l in lines)

    def test_render_nonzero_penalty_shows_deduction(self):
        """A run with penalty=0.40 renders '-0.40' in the PENALTY column."""
        runs = [_runscore(model_id="x", final_score=0.534, m6_borda=1.0, m7_borda=1.0,
                          m6_rate=0.001, m7_rate=2000, penalty=0.40)]
        text = scorecard.render_terminal(scorecard.build_scorecard(runs))
        assert "-0.40" in text


class TestScorecardWrite:
    def test_write_creates_json_file_with_iso_timestamp_filename(self, tmp_path):
        runs = [_runscore(model_id="x", final_score=0.85, m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_scorecard(runs)
        out_path = scorecard.write_scorecard(sc, scores_dir=tmp_path)
        assert out_path.exists()
        assert out_path.suffix == ".json"
        # Filename contains scorecard_id (which embeds timestamp + model ids)
        data = json.loads(out_path.read_text())
        assert data["scorecard_id"] in out_path.name

    def test_write_also_creates_sibling_txt_with_rendered_table(self, tmp_path):
        """Task #38 — write_scorecard persists both .json and .txt so users
        can `cat` the rendered table without parsing JSON."""
        runs = [
            _runscore(model_id="x", final_score=0.85, m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000),
            _runscore(model_id="y", final_score=0.40, m6_borda=0.0, m7_borda=0.0, m6_rate=0.005, m7_rate=5000),
        ]
        sc = scorecard.build_scorecard(runs)
        json_path = scorecard.write_scorecard(sc, scores_dir=tmp_path)
        txt_path = json_path.with_suffix(".txt")

        assert txt_path.exists()
        rendered = txt_path.read_text()
        # The .txt should match what render_terminal produces (single source of truth).
        assert rendered == scorecard.render_terminal(sc)
        # And it should look like a scorecard (cheap structural sanity checks).
        assert "rank" in rendered and "FINAL" in rendered
        assert "x" in rendered and "y" in rendered


# ---------------------------------------------------------------------------
# Task #42 — runs/ + final/ split, source pointers, merge primitives
# ---------------------------------------------------------------------------

class TestPerRunScorecard:
    def test_single_model_id_appended_to_filename(self):
        runs = [_runscore(model_id="gpt-5.4-mini", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_per_run_scorecard(runs, single_model_id="gpt-5.4-mini")
        assert sc.scorecard_id.endswith("-gpt-5.4-mini")
        # The timestamp portion still uses the local-ISO-with-`:`→`-`
        # substitution so the prefix is still chronologically sortable.
        assert "T" in sc.scorecard_id

    def test_multi_model_run_omits_model_names_from_filename(self):
        runs = [
            _runscore(model_id="a", final_score=0.9, m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000),
            _runscore(model_id="b", final_score=0.5, m6_borda=0.0, m7_borda=0.0, m6_rate=0.005, m7_rate=5000),
        ]
        sc = scorecard.build_per_run_scorecard(runs)
        # No model id suffix — the trailing token after the timestamp
        # offset (`-04-00`) should be empty.
        assert "-a" not in sc.scorecard_id and "-b" not in sc.scorecard_id

    def test_per_run_omits_source_scorecard_id_field(self):
        """Per-run scorecards ARE the source — entries should not carry
        a source_scorecard_id field."""
        runs = [_runscore(model_id="x", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_per_run_scorecard(runs, single_model_id="x")
        d = sc.to_dict()
        assert "source_scorecard_id" not in d["models"][0]


class TestFinalScorecard:
    def test_filename_is_timestamp_only(self):
        runs = [_runscore(model_id="x", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_final_scorecard(
            runs, source_scorecard_id_by_model={"x": "2026-01-01T00-00-00-04-00"},
        )
        # No model id suffix even when only one model is present.
        assert "-x" not in sc.scorecard_id
        assert sc.scorecard_id.endswith("-04-00") or sc.scorecard_id.endswith("Z")

    def test_each_entry_carries_source_scorecard_id(self):
        runs = [
            _runscore(model_id="a", final_score=0.9, m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000),
            _runscore(model_id="b", final_score=0.5, m6_borda=0.0, m7_borda=0.0, m6_rate=0.005, m7_rate=5000),
        ]
        source_map = {"a": "2026-01-01T00-00-00-04-00", "b": "2026-02-01T00-00-00-04-00"}
        sc = scorecard.build_final_scorecard(runs, source_scorecard_id_by_model=source_map)
        d = sc.to_dict()
        for entry in d["models"]:
            assert entry["source_scorecard_id"] == source_map[entry["model_id"]]


class TestWriteScorecardSubdirs:
    def test_runs_subdir_lands_under_runs_folder(self, tmp_path):
        runs = [_runscore(model_id="x", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_per_run_scorecard(runs, single_model_id="x")
        out = scorecard.write_scorecard(sc, scores_dir=tmp_path, subdir="runs")
        assert out.parent == tmp_path / "runs"
        assert out.exists()
        assert out.with_suffix(".txt").exists()

    def test_final_subdir_lands_under_final_folder(self, tmp_path):
        runs = [_runscore(model_id="x", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_final_scorecard(runs, source_scorecard_id_by_model={"x": "src"})
        out = scorecard.write_scorecard(sc, scores_dir=tmp_path, subdir="final")
        assert out.parent == tmp_path / "final"


class TestLatestFinalDiscovery:
    def test_returns_none_when_no_finals_yet(self, tmp_path):
        assert scorecard.latest_final_scorecard_path(tmp_path) is None

    def test_picks_lexically_latest_final(self, tmp_path):
        final_dir = tmp_path / "final"
        final_dir.mkdir(parents=True)
        # Filenames are local-ISO with `:`→`-` so lexical sort = chronological.
        for name in (
            "2026-01-01T00-00-00-04-00.json",
            "2026-05-08T14-58-08-04-00.json",
            "2026-03-15T12-00-00-04-00.json",
        ):
            (final_dir / name).write_text(json.dumps({"models": []}), encoding="utf-8")
        latest = scorecard.latest_final_scorecard_path(tmp_path)
        assert latest is not None and latest.name == "2026-05-08T14-58-08-04-00.json"


class TestLoadRunsFromScorecard:
    def test_round_trip_preserves_runs_and_source_pointers(self, tmp_path):
        runs = [
            _runscore(model_id="a", final_score=0.9, m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000),
            _runscore(model_id="b", final_score=0.5, m6_borda=0.0, m7_borda=0.0, m6_rate=0.005, m7_rate=5000),
        ]
        source_map = {"a": "2026-01-01T00-00-00-04-00", "b": "2026-02-01T00-00-00-04-00"}
        sc = scorecard.build_final_scorecard(runs, source_scorecard_id_by_model=source_map)
        out = scorecard.write_scorecard(sc, scores_dir=tmp_path, subdir="final")
        loaded_runs, loaded_map = scorecard.load_runs_from_scorecard(out)
        assert {r.model_id for r in loaded_runs} == {"a", "b"}
        assert loaded_map == source_map
        # The reconstructed RunScore carries the same final_score the
        # source did — caller is responsible for re-Borda before re-using.
        rs_by_id = {r.model_id: r for r in loaded_runs}
        assert rs_by_id["a"].final_score == 0.9
        assert rs_by_id["b"].final_score == 0.5

    def test_falls_back_to_scorecard_id_when_entries_lack_source_pointer(self, tmp_path):
        """Bootstrap case: a final written before Task #42 won't have
        per-entry `source_scorecard_id`; the loader should fall back to
        the scorecard's own id so callers get a non-empty pointer."""
        runs = [_runscore(model_id="a", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        # Build via the per-run path so the JSON has no source_scorecard_id field.
        sc = scorecard.build_per_run_scorecard(runs)
        out = scorecard.write_scorecard(sc, scores_dir=tmp_path, subdir="runs")
        _, loaded_map = scorecard.load_runs_from_scorecard(out)
        assert loaded_map["a"] == sc.scorecard_id


class TestRunScoreFromDict:
    def test_round_trip_via_to_dict_from_dict(self):
        original = _runscore(model_id="x", final_score=0.85,
                             m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)
        rebuilt = RunScore.from_dict(original.to_dict())
        assert rebuilt.model_id == original.model_id
        assert rebuilt.run_id == original.run_id
        assert rebuilt.measures["M6"].rate == original.measures["M6"].rate
        assert rebuilt.m6_borda == original.m6_borda
        assert rebuilt.final_score == original.final_score

    def test_tolerates_extra_keys_added_by_scorecard_layer(self):
        """Scorecard JSON entries carry `ran_at` and `source_scorecard_id`
        on top of RunScore's own fields — from_dict should ignore them."""
        original = _runscore(model_id="x", final_score=0.85,
                             m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)
        d = original.to_dict()
        d["ran_at"] = "anything"
        d["source_scorecard_id"] = "src"
        rebuilt = RunScore.from_dict(d)
        assert rebuilt.model_id == "x"


# ---------- Dropped Models (Task #44) ----------


def _dropped_runscore(model_id: str, *, m6_rate: float = 0.0024, m7_rate: float = 19727.0) -> RunScore:
    """Helper for dropped runs: Borda fields are None (not part of active set)."""
    return RunScore(
        run_id=f"{model_id}-dropped-fake",
        model_id=model_id,
        provider="gemini",
        model="gemini-3-flash-preview",
        n_attempted=5,
        s0=MeasureScore("S0", 1, 5, 0.20, 0.20),
        s1=MeasureScore("S1", 5, 5, 1.0, 0.0),
        s2=MeasureScore("S2", 5, 5, 1.0, 0.0),
        s3=MeasureScore("S3", 5, 5, 1.0, 0.0),
        measures={
            "M1": MeasureScore("M1", 1, 1, 1.0, 0.20),
            "M2": MeasureScore("M2", 1, 1, 1.0, 0.05),
            "M3": MeasureScore("M3", 0, 1, 0.0, 0.05),
            "M4": MeasureScore("M4", 1, 5, 0.20, 0.15),
            "M5": MeasureScore("M5", 1, 1, 1.0, 0.05),
            "M6": MeasureScore("M6", 0.001, 1000, m6_rate, 0.15),
            "M7": MeasureScore("M7", 2000, 1000, m7_rate, 0.15),
        },
        diagnostics={
            "retry_load":              MeasureScore("retry_load", 0, 5, 0.0, 0.0),
            "token_overrun_rate":      MeasureScore("token_overrun_rate", 4, 5, 0.8, 0.0),
            "pages_per_1k_source_words": MeasureScore("pages_per_1k_source_words", 1, 5000, 0.21, 0.0),
        },
        m6_borda=None,
        m7_borda=None,
        final_score_pre_penalty=None,
        penalty=0.0,
        final_score=None,
    )


class TestScorecardDroppedRuns:
    def test_default_scorecard_has_empty_dropped(self):
        runs = [_runscore(model_id="haiku-4.5", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_per_run_scorecard(runs)
        assert sc.dropped_runs == []
        assert sc.dropped_reasons == {}

    def test_build_final_scorecard_accepts_dropped_runs(self):
        active = [_runscore(model_id="haiku-4.5", final_score=0.9,
                            m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        dropped = [_dropped_runscore("gemini-3-flash-preview")]
        sc = scorecard.build_final_scorecard(
            active,
            source_scorecard_id_by_model={"haiku-4.5": "src1", "gemini-3-flash-preview": "src2"},
            dropped_runs=dropped,
            dropped_reasons={"gemini-3-flash-preview": "test reason"},
        )
        assert [r.model_id for r in sc.dropped_runs] == ["gemini-3-flash-preview"]
        assert sc.dropped_reasons == {"gemini-3-flash-preview": "test reason"}
        # candidate_set reflects active only — Borda comparison set
        assert sc.candidate_set == ["haiku-4.5"]

    def test_to_dict_emits_dropped_models_array(self):
        active = [_runscore(model_id="haiku-4.5", final_score=0.9,
                            m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        dropped = [_dropped_runscore("gemini-3-flash-preview")]
        sc = scorecard.build_final_scorecard(
            active,
            source_scorecard_id_by_model={"haiku-4.5": "src1", "gemini-3-flash-preview": "src2"},
            dropped_runs=dropped,
            dropped_reasons={"gemini-3-flash-preview": "test reason"},
        )
        d = sc.to_dict()
        assert "dropped_models" in d
        assert len(d["dropped_models"]) == 1
        entry = d["dropped_models"][0]
        assert entry["model_id"] == "gemini-3-flash-preview"
        assert entry["drop_reason"] == "test reason"
        assert entry["source_scorecard_id"] == "src2"
        # Active list excludes dropped
        assert [m["model_id"] for m in d["models"]] == ["haiku-4.5"]

    def test_to_dict_dropped_models_empty_when_none(self):
        runs = [_runscore(model_id="haiku-4.5", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_per_run_scorecard(runs)
        d = sc.to_dict()
        assert d["dropped_models"] == []


class TestScorecardDroppedRender:
    def test_render_includes_dropped_section_when_present(self):
        active = [_runscore(model_id="haiku-4.5", final_score=0.9,
                            m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        dropped = [_dropped_runscore("gemini-3-flash-preview")]
        sc = scorecard.build_final_scorecard(
            active,
            source_scorecard_id_by_model={"haiku-4.5": "s1", "gemini-3-flash-preview": "s2"},
            dropped_runs=dropped,
            dropped_reasons={"gemini-3-flash-preview": "high run-to-run variance"},
        )
        text = scorecard.render_terminal(sc)
        assert "Dropped Models" in text
        assert "gemini-3-flash-preview" in text
        assert "high run-to-run variance" in text
        # Raw $/ms format
        assert "$0.0024" in text
        assert "19727ms" in text

    def test_render_omits_dropped_section_when_empty(self):
        """Backward-compat regression: scorecards with no dropped runs
        render exactly as before #44 — no 'Dropped Models' header."""
        runs = [_runscore(model_id="haiku-4.5", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_per_run_scorecard(runs)
        text = scorecard.render_terminal(sc)
        assert "Dropped Models" not in text


class TestLoadRunsCombined:
    def test_load_runs_combines_active_and_dropped(self, tmp_path):
        """load_runs_from_scorecard returns active + dropped as one list,
        so the merge step can re-partition fresh against the current
        registry rather than honoring the prior scorecard's snapshot."""
        active = [_runscore(model_id="haiku-4.5", final_score=0.9,
                            m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        dropped = [_dropped_runscore("gemini-3-flash-preview")]
        sc = scorecard.build_final_scorecard(
            active,
            source_scorecard_id_by_model={"haiku-4.5": "s1", "gemini-3-flash-preview": "s2"},
            dropped_runs=dropped,
            dropped_reasons={"gemini-3-flash-preview": "test"},
        )
        out = scorecard.write_scorecard(sc, scores_dir=tmp_path, subdir="final")
        loaded_runs, loaded_map = scorecard.load_runs_from_scorecard(out)
        loaded_ids = {r.model_id for r in loaded_runs}
        assert loaded_ids == {"haiku-4.5", "gemini-3-flash-preview"}
        assert loaded_map == {"haiku-4.5": "s1", "gemini-3-flash-preview": "s2"}

    def test_load_runs_handles_pre_44_scorecard_without_dropped_models(self, tmp_path):
        """Backward compat: scorecards committed before #44 lack the
        `dropped_models` field. Loader defaults to empty — no crash."""
        # Synthesize a pre-#44 scorecard JSON by hand — no dropped_models field.
        legacy = {
            "scorecard_id": "2026-05-08T14-58-08-04-00",
            "candidate_set": ["haiku-4.5"],
            "emitted_at": "2026-05-08T14:58:08-04:00",
            "disclaimer": "test",
            "models": [
                _runscore(model_id="haiku-4.5", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)
                .to_dict() | {"ran_at": "haiku-4.5-fake", "source_scorecard_id": "self"},
            ],
        }
        legacy_path = tmp_path / "legacy.json"
        legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
        loaded_runs, loaded_map = scorecard.load_runs_from_scorecard(legacy_path)
        assert [r.model_id for r in loaded_runs] == ["haiku-4.5"]
        assert loaded_map == {"haiku-4.5": "self"}


# ---------- run_config / run_timing (Task #46) ----------


class TestScorecardRunMetadata:
    def test_default_per_run_scorecard_has_empty_run_config_and_timing(self):
        runs = [_runscore(model_id="haiku-4.5", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_per_run_scorecard(runs)
        assert sc.run_config == {}
        assert sc.run_timing == {}

    def test_build_per_run_scorecard_accepts_run_config_and_run_timing(self):
        runs = [_runscore(model_id="haiku-4.5", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_per_run_scorecard(
            runs,
            single_model_id="haiku-4.5",
            run_config={"max_tokens": 24000, "n_sources": 5, "n_source_words": 28607},
            run_timing={"compile_seconds": 131.4, "score_seconds": 3.2, "total_seconds": 134.6},
        )
        assert sc.run_config == {"max_tokens": 24000, "n_sources": 5, "n_source_words": 28607}
        assert sc.run_timing == {"compile_seconds": 131.4, "score_seconds": 3.2, "total_seconds": 134.6}

    def test_to_dict_emits_run_config_and_run_timing(self):
        runs = [_runscore(model_id="haiku-4.5", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_per_run_scorecard(
            runs,
            single_model_id="haiku-4.5",
            run_config={"max_tokens": 24000},
            run_timing={"total_seconds": 134.6},
        )
        d = sc.to_dict()
        assert d["run_config"] == {"max_tokens": 24000}
        assert d["run_timing"] == {"total_seconds": 134.6}

    def test_to_dict_run_metadata_empty_when_unset(self):
        """Final scorecards (no run_config / run_timing) emit empty dicts —
        keeps JSON shape deterministic without erroring on absence."""
        runs = [_runscore(model_id="haiku-4.5", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_final_scorecard(
            runs, source_scorecard_id_by_model={"haiku-4.5": "src"},
        )
        d = sc.to_dict()
        assert d["run_config"] == {}
        assert d["run_timing"] == {}


class TestScorecardRunMetadataRender:
    def test_render_includes_config_and_timing_when_populated(self):
        runs = [_runscore(model_id="haiku-4.5", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_per_run_scorecard(
            runs,
            single_model_id="haiku-4.5",
            run_config={
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "ctx_window": 200000,
                "max_tokens": 24000,
                "price_in": 1.0,
                "price_out": 5.0,
                "sources_dir": "benchmark/sources",
                "n_sources": 5,
                "n_source_words": 28607,
            },
            run_timing={"compile_seconds": 131.4, "score_seconds": 3.2, "total_seconds": 134.6},
        )
        text = scorecard.render_terminal(sc)
        # Config line (format: "Config:    provider/model   ctx=N   --max-tokens=N   prices=$X/$Y/1M-tok   sources=...")
        assert "Config:" in text
        assert "anthropic/claude-haiku-4-5-20251001" in text
        assert "ctx=200000" in text
        assert "--max-tokens=24000" in text
        assert "prices=$1.0/$5.0/1M-tok" in text
        assert "5 files, 28607 source_words" in text
        # Timing line
        assert "Timing:" in text
        assert "compile=" in text
        assert "score=" in text
        assert "total=" in text
        # 131.4s → "2m 11s" formatted
        assert "2m 11s" in text

    def test_render_skips_config_and_timing_when_empty(self):
        """Backward-compat regression: scorecards without run_config or
        run_timing render exactly as before #46 (no Config/Timing lines)."""
        runs = [_runscore(model_id="haiku-4.5", final_score=0.9,
                          m6_borda=1.0, m7_borda=1.0, m6_rate=0.001, m7_rate=2000)]
        sc = scorecard.build_final_scorecard(
            runs, source_scorecard_id_by_model={"haiku-4.5": "src"},
        )
        text = scorecard.render_terminal(sc)
        assert "Config:" not in text
        assert "Timing:" not in text


class TestFmtDuration:
    def test_under_60s_uses_decimal_seconds(self):
        assert scorecard.fmt_duration(0.0) == "0.0s"
        assert scorecard.fmt_duration(12.3) == "12.3s"
        assert scorecard.fmt_duration(59.9) == "59.9s"

    def test_60s_or_more_uses_minutes_and_seconds(self):
        assert scorecard.fmt_duration(60.0) == "1m 0s"
        assert scorecard.fmt_duration(131.4) == "2m 11s"
        assert scorecard.fmt_duration(3600.0) == "60m 0s"

    def test_none_returns_na(self):
        assert scorecard.fmt_duration(None) == "n/a"
