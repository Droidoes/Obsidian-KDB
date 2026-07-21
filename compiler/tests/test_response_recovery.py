"""Tests for response_recovery — the #114 shared recovery contract."""
from compiler.response_recovery import recover_json_response


def test_clean_json_parses_no_flags():
    r = recover_json_response('{"pages": []}')
    assert r.recovered and r.parsed == {"pages": []}
    assert r.extract_ok and not r.boundary_recovered and not r.syntax_repaired
    assert (r.prefix_discarded_chars, r.tail_discarded_chars) == (0, 0)
    assert r.error is None


def test_lone_brace_tail_boundary_recovered_strict_conformant():
    r = recover_json_response('{"pages": []}\n}')
    assert r.recovered and r.parsed == {"pages": []}
    assert r.boundary_recovered and not r.syntax_repaired
    assert r.tail_discarded_chars == 2
    assert r.extract_ok is True


def test_prose_tail_boundary_recovered_strict_nonconformant():
    r = recover_json_response('{"pages": []}\n  "warnings": []')
    assert r.recovered and r.parsed == {"pages": []}
    assert r.boundary_recovered and not r.syntax_repaired
    assert r.tail_discarded_chars == 17
    assert r.extract_ok is False


def test_leading_prose_boundary_recovered_with_prefix():
    r = recover_json_response('Here is JSON:\n{"pages": []}')
    assert r.recovered and r.parsed == {"pages": []}
    assert r.boundary_recovered
    assert r.prefix_discarded_chars == 14 and r.tail_discarded_chars == 0
    assert r.extract_ok is False


def test_fenced_json_parses_clean():
    r = recover_json_response('```json\n{"pages": []}\n```')
    assert r.recovered and r.parsed == {"pages": []}
    assert r.extract_ok and not r.boundary_recovered


def test_fenced_plus_tail_boundary_recovered():
    r = recover_json_response('```json\n{"pages": []}\n```\n}')
    assert r.recovered and r.parsed == {"pages": []} and r.boundary_recovered


def test_escape_fix_still_works_step4():
    r = recover_json_response('{"body": "math \\(x\\) here"}')
    assert r.recovered and r.parsed == {"body": "math \\(x\\) here"}
    assert r.syntax_repaired and not r.boundary_recovered


def test_escape_plus_tail_composed_step5():
    r = recover_json_response('{"body": "math \\(x\\)"}\n}')
    assert r.recovered and r.parsed == {"body": "math \\(x\\)"}
    assert r.syntax_repaired and r.boundary_recovered
    assert r.tail_discarded_chars == 2


def test_unterminated_returns_not_recovered_with_error():
    r = recover_json_response('{"pages": [1, 2')
    assert not r.recovered and r.parsed is None and r.error
    # #114 final-review: error carries the terminal decoder error, not a
    # static string (pre-#114 format, spec §3.2).
    assert r.error == "Expecting ',' delimiter at line 1"
    assert not r.boundary_recovered and not r.syntax_repaired


def test_json_null_is_recovered_not_failure():
    # json.loads("null") is None — must NOT collide with the failure sentinel
    r = recover_json_response('null')
    assert r.recovered and r.parsed is None and r.error is None


def test_non_dict_top_level_returned_for_schema_gate():
    r = recover_json_response('[1, 2, 3]')
    assert r.recovered and r.parsed == [1, 2, 3]
    assert r.error is None and not r.boundary_recovered


def test_truncated_array_never_lifts_nested_object():
    r = recover_json_response('[{"pages": []}')
    assert not r.recovered
    assert r.error == "Expecting ',' delimiter at line 1"


def test_first_brace_only_no_scanning():
    r = recover_json_response('{bad} {"pages": []}')
    assert not r.recovered
    assert "no complete" not in r.error and "at line 1" in r.error


def test_selection_first_no_unneeded_edit():
    r = recover_json_response('{"a": "no backslashes"}\n}')
    assert r.recovered and r.boundary_recovered and not r.syntax_repaired
