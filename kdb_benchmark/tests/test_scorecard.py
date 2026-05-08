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
