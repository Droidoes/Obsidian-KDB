import json
from common.util.json_escape_fix import escape_stray_backslashes


def test_latex_backslash_is_escaped_and_content_survives():
    bad = r'{"body": "the term \(n-1\) matters"}'
    fixed = escape_stray_backslashes(bad)
    obj = json.loads(fixed)                      # must now parse
    assert obj["body"] == r"the term \(n-1\) matters"   # backslash PRESERVED (content fidelity)


def test_valid_json_escapes_are_untouched():
    good = r'{"a": "line1\nline2", "b": "a\\b", "c": "quote\"", "d": "é"}'
    fixed = escape_stray_backslashes(good)
    assert json.loads(fixed) == json.loads(good)    # unchanged semantics
    assert fixed == good                            # byte-identical: no spurious doubling


def test_irreparable_still_fails_to_parse():
    bad = r'{"a": 1 "b": 2}'
    fixed = escape_stray_backslashes(bad)
    try:
        json.loads(fixed)
        assert False, "should still be invalid JSON"
    except json.JSONDecodeError:
        pass
