"""Tests for json_tail_fix — root-preserving boundary-decode."""
from common.util.json_tail_fix import parse_document_prefix


def test_clean_object_decodes_with_zero_counts():
    assert parse_document_prefix('{"a": 1}') == ({"a": 1}, 0, 0)


def test_lone_brace_tail():
    assert parse_document_prefix('{"a": 1}\n}') == ({"a": 1}, 0, 2)


def test_fragment_tail():
    assert parse_document_prefix('{"a": []}\n  "warnings": []') == ({"a": []}, 0, 17)


def test_leading_prose_counts_prefix():
    assert parse_document_prefix('Here is JSON:\n{"a": 1}') == ({"a": 1}, 14, 0)


def test_prose_and_tail():
    assert parse_document_prefix('note: {"a": 1} trailing') == ({"a": 1}, 6, 9)


def test_no_brace_returns_none():
    assert parse_document_prefix("no json here") is None


def test_unterminated_object_returns_none():
    assert parse_document_prefix('{"a": [1, 2') is None


def test_first_brace_only_no_scanning():
    assert parse_document_prefix('{bad} {"a": 1}') is None


def test_nested_object_value_decodes():
    assert parse_document_prefix('{"a": {"b": [1, 2]}} junk') == ({"a": {"b": [1, 2]}}, 0, 5)


# --- root preservation (v1.2 / Codex round 2) ---

def test_array_root_with_tail_returns_whole_array():
    hit = parse_document_prefix('[{"a": 1}]\njunk')
    assert hit == ([{"a": 1}], 0, 5)


def test_truncated_array_never_lifts_nested_object():
    # the root is an array; it fails to decode → None. The nested {"a": 1}
    # must NOT be carved out and returned.
    assert parse_document_prefix('[{"a": 1}') is None


def test_scalar_root_null_decodes():
    assert parse_document_prefix('null') == (None, 0, 0)


def test_scalar_root_string_with_tail():
    assert parse_document_prefix('"hello" tail') == ("hello", 0, 5)


def test_truncated_literal_returns_none():
    # 'nul' is an attempted root (prefix of 'null'); raw_decode fails →
    # None — it does NOT fall through to the prose branch
    assert parse_document_prefix('nul') is None


def test_complete_literal_with_adjacent_noise_decodes_at_root():
    # 'nulljunk': token starts with the literal 'null' → root decodes at
    # offset 0; the noise is tail, NOT a prose fallback to the later object
    assert parse_document_prefix('nulljunk {"a": 1}') == (None, 0, 13)


def test_true_with_tail_decodes_at_root():
    assert parse_document_prefix('trueTAIL {"a": 1}') == (True, 0, 13)


def test_falsehood_decodes_at_root():
    assert parse_document_prefix('falsehood') == (False, 0, 4)


def test_prose_leading_with_n_word_still_recovers():
    # 'note:' starts with 'n' but is NOT a prefix of 'null' → prose fallback
    assert parse_document_prefix('note: {"a": 1} trailing') == ({"a": 1}, 6, 9)


def test_truncated_literal_nul_is_attempted_root_never_scanned():
    # 'nul' is a proper prefix of 'null' → attempted root; decode fails →
    # None, and the later object is NEVER reached (strict root preservation)
    assert parse_document_prefix('nul {"a": 1}') is None


def test_truncated_literal_tru_is_attempted_root_never_scanned():
    assert parse_document_prefix('tru {"a": 1}') is None


def test_truncated_literal_fals_is_attempted_root_never_scanned():
    assert parse_document_prefix('fals {"a": 1}') is None


def test_prose_then_object_still_recovers():
    # prose leading: first non-ws char cannot start a JSON value → first-'{' fallback
    assert parse_document_prefix('Output:\n{"a": 1}') == ({"a": 1}, 8, 0)
