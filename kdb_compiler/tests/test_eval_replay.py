"""Tests for eval_replay — fixture-driven replay of the validator stack.

Coverage per blueprint §10:
    - happy fixture (case01): every flag true, matches expected
    - schema-fail fixture (case02): extract+parse ok, schema/semantic false
    - semantic-fail fixture (case03): extract+parse+schema ok, semantic false
    - CLI exit 0 iff all match, 1 otherwise
    - load_fixtures ignores dirs without case.json/stored_response.txt
    - malformed-JSON response → parse_ok=False, short-circuits schema/semantic
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kdb_compiler import eval_replay
from kdb_compiler.eval_replay import (
    ReplayFixture,
    load_fixtures,
    main,
    replay_case,
)

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "eval"


# ---------- load_fixtures ----------

def test_load_fixtures_returns_three_cases_sorted() -> None:
    cases = load_fixtures(_FIXTURES_DIR)
    assert [c.case_id for c in cases] == [
        "case01_minimal_summary",
        "case02_schema_violation",
        "case03_semantic_violation",
    ]


def test_load_fixtures_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_fixtures(tmp_path / "nope")


def test_load_fixtures_ignores_incomplete_case_dirs(tmp_path: Path) -> None:
    (tmp_path / "bad_case").mkdir()
    # Has case.json but no stored_response.txt — should be skipped
    (tmp_path / "bad_case" / "case.json").write_text(
        json.dumps({
            "source_id": "KDB/raw/x.md",
            "expected_extract_ok": True,
            "expected_parse_ok": True,
            "expected_schema_ok": True,
            "expected_semantic_ok": True,
        }),
        encoding="utf-8",
    )
    assert load_fixtures(tmp_path) == []


# ---------- replay_case: seed fixtures ----------

def test_replay_case01_happy_path_all_flags_true() -> None:
    fixtures = {c.case_id: c for c in load_fixtures(_FIXTURES_DIR)}
    r = replay_case(fixtures["case01_minimal_summary"])
    assert r.extract_ok is True
    assert r.parse_ok is True
    assert r.schema_ok is True
    assert r.semantic_ok is True
    assert r.matches_expected is True
    assert r.error_detail is None


def test_replay_case02_schema_violation_flags() -> None:
    fixtures = {c.case_id: c for c in load_fixtures(_FIXTURES_DIR)}
    r = replay_case(fixtures["case02_schema_violation"])
    # Fenced block extracts; parses; slug pattern breaks schema;
    # semantic short-circuits to False.
    assert r.extract_ok is True
    assert r.parse_ok is True
    assert r.schema_ok is False
    assert r.semantic_ok is False
    assert r.matches_expected is True
    assert r.error_detail is not None
    assert "schema:" in r.error_detail


def test_replay_case03_semantic_violation_flags() -> None:
    fixtures = {c.case_id: c for c in load_fixtures(_FIXTURES_DIR)}
    r = replay_case(fixtures["case03_semantic_violation"])
    assert r.extract_ok is True
    assert r.parse_ok is True
    assert r.schema_ok is True
    assert r.semantic_ok is False
    assert r.matches_expected is True
    assert r.error_detail is not None
    assert "semantic:" in r.error_detail


# ---------- replay_case: synthetic edge cases ----------

def _synth(**overrides) -> ReplayFixture:
    base = dict(
        case_id="synth",
        source_id="KDB/raw/x.md",
        stored_response_text="{}",
        expected_extract_ok=True,
        expected_parse_ok=True,
        expected_schema_ok=True,
        expected_semantic_ok=True,
        notes="",
    )
    base.update(overrides)
    return ReplayFixture(**base)


def test_replay_extract_failure_short_circuits() -> None:
    """Prose around the object breaks extract; downstream flags stay False."""
    f = _synth(
        stored_response_text="Sure thing: {\"x\": 1} — hope that helps!",
        expected_extract_ok=False,
        expected_parse_ok=False,
        expected_schema_ok=False,
        expected_semantic_ok=False,
    )
    r = replay_case(f)
    assert (r.extract_ok, r.parse_ok, r.schema_ok, r.semantic_ok) == (False, False, False, False)
    assert r.matches_expected is True
    assert r.error_detail is not None
    assert "extract:" in r.error_detail


def test_replay_parse_failure_after_extract() -> None:
    """Passes extract (bare { ... }) but body is invalid JSON."""
    f = _synth(
        stored_response_text='{"broken" :: invalid}',
        expected_extract_ok=True,
        expected_parse_ok=False,
        expected_schema_ok=False,
        expected_semantic_ok=False,
    )
    r = replay_case(f)
    assert r.extract_ok is True
    assert r.parse_ok is False
    assert r.schema_ok is False
    assert r.semantic_ok is False
    assert r.matches_expected is True
    assert r.error_detail is not None
    assert "parse:" in r.error_detail


def test_replay_mismatch_flags_expected() -> None:
    """If the fixture says schema_ok=True but the response breaks schema,
    matches_expected must be False — guards the regression reporter."""
    f = _synth(
        stored_response_text="{\"source_id\": \"KDB/raw/x.md\"}",  # missing required fields
        expected_extract_ok=True,
        expected_parse_ok=True,
        expected_schema_ok=True,   # LIE — actual schema will fail
        expected_semantic_ok=True,
    )
    r = replay_case(f)
    assert r.schema_ok is False
    assert r.matches_expected is False


# ---------- CLI ----------

def test_cli_exits_0_on_all_matching(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--replay", str(_FIXTURES_DIR)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "3/3 case(s) matched expectations" in out


def test_cli_exits_1_when_any_case_mismatches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    case = tmp_path / "bad"
    case.mkdir()
    (case / "stored_response.txt").write_text(
        "not a json object, just prose", encoding="utf-8"
    )
    (case / "case.json").write_text(
        json.dumps({
            "source_id": "KDB/raw/x.md",
            "expected_extract_ok": True,   # wrong — extract will fail
            "expected_parse_ok": True,
            "expected_schema_ok": True,
            "expected_semantic_ok": True,
        }),
        encoding="utf-8",
    )
    rc = main(["--replay", str(tmp_path)])
    assert rc == 1
    assert "0/1 case(s) matched" in capsys.readouterr().out


def test_cli_exits_1_when_no_cases_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--replay", str(tmp_path)])
    assert rc == 1
    assert "no cases found" in capsys.readouterr().err


def test_cli_exits_1_when_dir_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--replay", str(tmp_path / "nope")])
    assert rc == 1
