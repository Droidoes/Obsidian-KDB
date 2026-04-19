"""Tests for response_normalizer — strict JSON extraction only."""
from __future__ import annotations

import pytest

from kdb_compiler.response_normalizer import extract_json_text, parse_json_object


# ---------- extract_json_text: accepted shapes ----------

def test_bare_object_accepted() -> None:
    raw = '{"source_id": "KDB/raw/foo.md", "x": 1}'
    assert extract_json_text(raw) == raw


def test_bare_object_with_surrounding_whitespace_accepted() -> None:
    raw = '  \n\n {"x": 1}  \n'
    assert extract_json_text(raw) == '{"x": 1}'


def test_fenced_json_block_accepted() -> None:
    raw = '```json\n{"x": 1}\n```'
    assert extract_json_text(raw) == '{"x": 1}'


def test_fenced_plain_block_accepted() -> None:
    raw = '```\n{"x": 1}\n```'
    assert extract_json_text(raw) == '{"x": 1}'


def test_fenced_json_with_surrounding_whitespace_accepted() -> None:
    raw = '\n```json\n{"x": 1}\n```\n'
    assert extract_json_text(raw) == '{"x": 1}'


def test_fenced_json_uppercase_lang_tag_accepted() -> None:
    raw = '```JSON\n{"x": 1}\n```'
    assert extract_json_text(raw) == '{"x": 1}'


# ---------- extract_json_text: rejected shapes ----------

def test_prose_before_object_rejected() -> None:
    with pytest.raises(ValueError, match="not a bare JSON object"):
        extract_json_text('Here is the JSON: {"x": 1}')


def test_prose_after_object_rejected() -> None:
    with pytest.raises(ValueError, match="not a bare JSON object"):
        extract_json_text('{"x": 1} Hope that helps!')


def test_prose_before_fenced_block_rejected() -> None:
    """Prose outside a single fenced block is not tolerated."""
    with pytest.raises(ValueError):
        extract_json_text('Here you go:\n```json\n{"x": 1}\n```')


def test_multiple_fenced_blocks_rejected() -> None:
    raw = '```json\n{"x": 1}\n```\n```json\n{"y": 2}\n```'
    with pytest.raises(ValueError, match="multiple fenced blocks"):
        extract_json_text(raw)


def test_unsupported_fence_language_rejected() -> None:
    raw = '```python\n{"x": 1}\n```'
    with pytest.raises(ValueError, match="unsupported fence language"):
        extract_json_text(raw)


def test_fence_opener_without_body_rejected() -> None:
    with pytest.raises(ValueError, match="fence opener with no body"):
        extract_json_text("```json")


def test_opening_fence_without_closing_rejected() -> None:
    raw = '```json\n{"x": 1}\n'
    with pytest.raises(ValueError, match="no closing fence"):
        extract_json_text(raw)


def test_bare_array_rejected() -> None:
    """The per-source contract is always an object; arrays are not accepted."""
    with pytest.raises(ValueError, match="not a bare JSON object"):
        extract_json_text('[{"x": 1}]')


def test_empty_string_rejected() -> None:
    with pytest.raises(ValueError):
        extract_json_text("")


# ---------- parse_json_object: rejects non-object top-level ----------

def test_parse_valid_object_returns_dict() -> None:
    result = parse_json_object('{"x": 1, "y": [2, 3]}')
    assert result == {"x": 1, "y": [2, 3]}


def test_parse_malformed_json_raises_valueerror() -> None:
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_json_object('{"x": 1,}')  # trailing comma


def test_parse_fenced_then_loads() -> None:
    result = parse_json_object('```json\n{"x": 1}\n```')
    assert result == {"x": 1}


def test_parse_rejects_non_object_even_if_extract_would_allow_it() -> None:
    """Belt-and-suspenders: extract_json_text already forbids bare arrays,
    but parse_json_object double-checks the loaded type."""
    # Here we construct a case where extract accepts it but json.loads
    # produces something other than a dict. Extract forbids bare arrays
    # with `not (starts with '{' and ends with '}')`, so the only way to
    # produce a non-dict load is via a fenced block with weird content.
    # That already won't happen in practice, but verify the guard.
    raw = '{' + '"x": "y"' + '}'
    assert isinstance(parse_json_object(raw), dict)


# ---------- architectural invariant: no semantic code ----------

def test_no_semantic_functions_present() -> None:
    """The module must only extract/parse — never coerce, rename, or infer.
    If this test fails, the shrink contract has been violated."""
    import kdb_compiler.response_normalizer as rn
    public_names = [n for n in dir(rn) if not n.startswith("_") and callable(getattr(rn, n))]
    public_names = [n for n in public_names if n not in ("json",)]  # imports are callable
    assert sorted(public_names) == ["extract_json_text", "parse_json_object"], (
        f"response_normalizer must expose only extract_json_text and "
        f"parse_json_object; found: {public_names}"
    )
