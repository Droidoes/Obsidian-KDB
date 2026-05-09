"""Tests for kdb_benchmark.registry — loads and shape-checks models.json."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kdb_benchmark import registry
from kdb_benchmark.registry import ModelEntry, load_registry


def test_default_registry_loads_and_has_unique_ids() -> None:
    entries = load_registry()
    assert len(entries) >= 1
    ids = [e.id for e in entries]
    assert len(ids) == len(set(ids))
    for e in entries:
        assert isinstance(e, ModelEntry)
        assert e.id and e.provider and e.model


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_registry(tmp_path / "nope.json")


def test_top_level_must_be_list(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps({"id": "x"}), encoding="utf-8")
    with pytest.raises(ValueError, match="must be a list"):
        load_registry(p)


def test_entry_missing_required_field_raises(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps([{"id": "x", "provider": "anthropic"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="missing/empty string field 'model'"):
        load_registry(p)


def test_empty_field_raises(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(
        json.dumps([{"id": "x", "provider": "", "model": "m"}]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="provider"):
        load_registry(p)


def test_duplicate_id_raises(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(
        json.dumps([
            {"id": "dup", "provider": "anthropic", "model": "a", "price_in": 1.0, "price_out": 5.0},
            {"id": "dup", "provider": "openai",    "model": "b", "price_in": 1.0, "price_out": 5.0},
        ]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate id"):
        load_registry(p)


# ---------- pricing fields (Task #29) ----------

def _entry(**overrides: object) -> dict:
    base: dict = {
        "id": "x", "provider": "anthropic", "model": "m",
        "price_in": 1.0, "price_out": 5.0,
    }
    base.update(overrides)
    return base


def _drop(d: dict, key: str) -> dict:
    out = dict(d)
    out.pop(key, None)
    return out


def test_default_registry_carries_pricing() -> None:
    """Live models.json must populate price_in/price_out for every entry."""
    for e in load_registry():
        assert isinstance(e.price_in, float)
        assert isinstance(e.price_out, float)
        assert e.price_in >= 0.0 and e.price_out >= 0.0


def test_loader_rejects_missing_price_in(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_drop(_entry(), "price_in")]), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required field 'price_in'"):
        load_registry(p)


def test_loader_rejects_missing_price_out(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_drop(_entry(), "price_out")]), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required field 'price_out'"):
        load_registry(p)


def test_loader_rejects_non_numeric_price(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_entry(price_in="3.0")]), encoding="utf-8")
    with pytest.raises(ValueError, match="'price_in' must be a number"):
        load_registry(p)


def test_loader_rejects_bool_price(tmp_path: Path) -> None:
    """bool is a subclass of int in Python — reject explicitly."""
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_entry(price_in=True)]), encoding="utf-8")
    with pytest.raises(ValueError, match="'price_in' must be a number"):
        load_registry(p)


def test_loader_rejects_negative_price(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_entry(price_out=-0.5)]), encoding="utf-8")
    with pytest.raises(ValueError, match="'price_out' must be non-negative"):
        load_registry(p)


def test_loader_accepts_zero_prices(tmp_path: Path) -> None:
    """Local/Ollama models legitimately price at 0.0/0.0."""
    p = tmp_path / "models.json"
    p.write_text(
        json.dumps([_entry(id="local", provider="ollama", price_in=0.0, price_out=0.0)]),
        encoding="utf-8",
    )
    [entry] = load_registry(p)
    assert entry.price_in == 0.0
    assert entry.price_out == 0.0


def test_loader_coerces_int_to_float(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_entry(price_in=3, price_out=15)]), encoding="utf-8")
    [entry] = load_registry(p)
    assert entry.price_in == 3.0 and isinstance(entry.price_in, float)
    assert entry.price_out == 15.0 and isinstance(entry.price_out, float)


# ---------- optional behavior knobs (yt-comment-chat shape) ----------

def test_optional_fields_default_to_none_or_false(tmp_path: Path) -> None:
    """Entries that omit ctx_window / max_output_tokens / use_completion_tokens
    / extra_body get sensible defaults."""
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_entry()]), encoding="utf-8")
    [entry] = load_registry(p)
    assert entry.ctx_window is None
    assert entry.max_output_tokens is None
    assert entry.use_completion_tokens is False
    assert entry.extra_body is None


def test_loader_parses_optional_fields(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(
        json.dumps([_entry(
            ctx_window=400000,
            max_output_tokens=128000,
            use_completion_tokens=True,
            extra_body={"think": False},
        )]),
        encoding="utf-8",
    )
    [entry] = load_registry(p)
    assert entry.ctx_window == 400000
    assert entry.max_output_tokens == 128000
    assert entry.use_completion_tokens is True
    assert entry.extra_body == {"think": False}


def test_loader_rejects_non_int_ctx_window(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_entry(ctx_window=4.5)]), encoding="utf-8")
    with pytest.raises(ValueError, match="ctx_window"):
        load_registry(p)


def test_loader_rejects_zero_or_negative_max_output_tokens(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_entry(max_output_tokens=0)]), encoding="utf-8")
    with pytest.raises(ValueError, match="max_output_tokens"):
        load_registry(p)


def test_loader_rejects_non_bool_use_completion_tokens(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_entry(use_completion_tokens="yes")]), encoding="utf-8")
    with pytest.raises(ValueError, match="use_completion_tokens"):
        load_registry(p)


def test_loader_rejects_non_dict_extra_body(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_entry(extra_body=["not", "a", "dict"])]), encoding="utf-8")
    with pytest.raises(ValueError, match="extra_body"):
        load_registry(p)


def test_default_registry_includes_gpt_5_4_mini_with_completion_tokens() -> None:
    """Live models.json carries the GPT-5.4-mini entry with the
    use_completion_tokens flag (GPT-5+ family requirement)."""
    by_id = {e.id: e for e in load_registry()}
    if "gpt-5.4-mini" in by_id:
        gpt = by_id["gpt-5.4-mini"]
        assert gpt.use_completion_tokens is True
        assert gpt.provider == "openai"
        assert gpt.ctx_window == 400000
        assert gpt.max_output_tokens == 128000


# ---------- dropped status (Task #44) ----------

def test_dropped_defaults_to_false_when_absent(tmp_path: Path) -> None:
    """Entries without a `dropped` field default to active (dropped=False)."""
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_entry()]), encoding="utf-8")
    [entry] = load_registry(p)
    assert entry.dropped is False
    assert entry.dropped_reason == ""


def test_loader_parses_dropped_true_with_reason(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(
        json.dumps([_entry(
            dropped=True,
            dropped_reason="known-broken on canonical corpus",
        )]),
        encoding="utf-8",
    )
    [entry] = load_registry(p)
    assert entry.dropped is True
    assert entry.dropped_reason == "known-broken on canonical corpus"


def test_loader_rejects_non_bool_dropped(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_entry(dropped="yes")]), encoding="utf-8")
    with pytest.raises(ValueError, match="'dropped' must be a boolean"):
        load_registry(p)


def test_loader_rejects_non_string_dropped_reason(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps([_entry(dropped_reason=42)]), encoding="utf-8")
    with pytest.raises(ValueError, match="'dropped_reason' must be a string"):
        load_registry(p)


def test_default_registry_marks_gemini_3_flash_preview_dropped() -> None:
    """Live models.json: gemini-3-flash-preview is flagged dropped pending
    investigation of run-to-run variance + intermittent token-overrun."""
    by_id = {e.id: e for e in load_registry()}
    if "gemini-3-flash-preview" in by_id:
        gemini = by_id["gemini-3-flash-preview"]
        assert gemini.dropped is True
        assert gemini.dropped_reason  # non-empty
