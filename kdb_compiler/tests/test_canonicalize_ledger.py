"""Tests for compiler.canonicalize ledger loader (Task #74.2).

Anchors:
- docs/task74-canonicalization-blueprint.md §6.3 (error semantics) + D-R5-8
- Blueprint §10 calls for ~6 tests on "Ledger load — happy path +
  missing-file warning + malformed + sha snapshot"; this file ships 11
  to cover the corner cases enumerated in load_or_empty.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from compiler.canonicalize import (
    EMPTY_LEDGER_SHA,
    AliasEntry,
    AliasLedger,
    LedgerLoadError,
    load_or_empty,
)


def _write(path: Path, payload) -> None:
    """Write `payload` (a dict or a raw string) to `path` as JSON for dict,
    or directly for string (used to construct malformed-JSON test cases)."""
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")


def test_missing_file_returns_empty_ledger_with_warning(tmp_path: Path):
    """D-R5-8: missing file is non-fatal — emit a UserWarning and return
    an empty ledger with sha == 'empty'."""
    missing = tmp_path / "no-such-ledger.json"
    with pytest.warns(UserWarning, match="empty ledger"):
        ledger = load_or_empty(missing)
    assert ledger.is_empty
    assert ledger.entries == ()
    assert ledger.snapshot_sha256 == EMPTY_LEDGER_SHA
    assert ledger.path == missing


def test_happy_path_loads_entries_and_sha(tmp_path: Path):
    """Valid ledger produces parsed entries and a sha matching the raw bytes."""
    f = tmp_path / "aliases.json"
    payload = {
        "aliases": [
            {"surface": "AAPL", "canonical": "apple-inc", "note": "ticker symbol"},
            {"surface": "Apple Inc.", "canonical": "apple-inc"},
        ]
    }
    _write(f, payload)
    expected_sha = hashlib.sha256(f.read_bytes()).hexdigest()

    ledger = load_or_empty(f)

    assert not ledger.is_empty
    assert ledger.entries == (
        AliasEntry(surface="AAPL", canonical="apple-inc", note="ticker symbol"),
        AliasEntry(surface="Apple Inc.", canonical="apple-inc", note=None),
    )
    assert ledger.snapshot_sha256 == expected_sha
    assert ledger.path == f


def test_empty_aliases_array_is_valid(tmp_path: Path):
    """A ledger with `{"aliases": []}` is a valid empty ledger — different
    from the missing-file case in that sha is computed (not 'empty')."""
    f = tmp_path / "aliases.json"
    _write(f, {"aliases": []})

    ledger = load_or_empty(f)

    assert ledger.is_empty
    assert ledger.entries == ()
    assert ledger.snapshot_sha256 != EMPTY_LEDGER_SHA  # real file → real sha
    assert ledger.snapshot_sha256 == hashlib.sha256(f.read_bytes()).hexdigest()


def test_missing_aliases_key_defaults_to_empty(tmp_path: Path):
    """`{}` (root object with no `aliases` key) is treated as zero aliases.
    Reasonable for a freshly-initialized ledger before any entries exist."""
    f = tmp_path / "aliases.json"
    _write(f, {})

    ledger = load_or_empty(f)

    assert ledger.is_empty
    assert ledger.snapshot_sha256 != EMPTY_LEDGER_SHA


def test_malformed_json_raises(tmp_path: Path):
    """Bad JSON syntax → LedgerLoadError (fatal per D-R5-9)."""
    f = tmp_path / "aliases.json"
    _write(f, "{not valid json")
    with pytest.raises(LedgerLoadError, match="malformed JSON"):
        load_or_empty(f)


def test_root_must_be_object(tmp_path: Path):
    """A bare JSON list at the root is invalid — root must be an object."""
    f = tmp_path / "aliases.json"
    _write(f, [{"surface": "a", "canonical": "b"}])
    with pytest.raises(LedgerLoadError, match="must be a JSON object"):
        load_or_empty(f)


def test_aliases_must_be_a_list(tmp_path: Path):
    f = tmp_path / "aliases.json"
    _write(f, {"aliases": {"surface": "a", "canonical": "b"}})  # dict, not list
    with pytest.raises(LedgerLoadError, match="must be a list"):
        load_or_empty(f)


def test_entry_missing_surface_raises(tmp_path: Path):
    f = tmp_path / "aliases.json"
    _write(f, {"aliases": [{"canonical": "apple-inc"}]})
    with pytest.raises(LedgerLoadError, match="'surface'"):
        load_or_empty(f)


def test_entry_missing_canonical_raises(tmp_path: Path):
    f = tmp_path / "aliases.json"
    _write(f, {"aliases": [{"surface": "AAPL"}]})
    with pytest.raises(LedgerLoadError, match="'canonical'"):
        load_or_empty(f)


def test_entry_empty_string_surface_raises(tmp_path: Path):
    """Empty string is treated the same as missing — both fail validation."""
    f = tmp_path / "aliases.json"
    _write(f, {"aliases": [{"surface": "", "canonical": "apple-inc"}]})
    with pytest.raises(LedgerLoadError, match="'surface'"):
        load_or_empty(f)


def test_note_must_be_string_if_present(tmp_path: Path):
    f = tmp_path / "aliases.json"
    _write(f, {"aliases": [
        {"surface": "AAPL", "canonical": "apple-inc", "note": 42}
    ]})
    with pytest.raises(LedgerLoadError, match="'note' must be a string"):
        load_or_empty(f)


def test_duplicate_surface_raises(tmp_path: Path):
    """Same surface appearing twice — even to the same canonical — is
    rejected at load time. Forces the user to clean up aliases.json
    rather than letting ambiguity propagate silently into compile_meta."""
    f = tmp_path / "aliases.json"
    _write(f, {"aliases": [
        {"surface": "AAPL", "canonical": "apple-inc"},
        {"surface": "AAPL", "canonical": "apple-inc"},  # exact dup
    ]})
    with pytest.raises(LedgerLoadError, match="appears more than once"):
        load_or_empty(f)


def test_duplicate_surface_different_canonical_raises(tmp_path: Path):
    """Duplicate surface with conflicting canonicals — same rule, same
    error. Surface ambiguity is rejected at the ledger door."""
    f = tmp_path / "aliases.json"
    _write(f, {"aliases": [
        {"surface": "AAPL", "canonical": "apple-inc"},
        {"surface": "AAPL", "canonical": "alphabet-inc"},
    ]})
    with pytest.raises(LedgerLoadError, match="appears more than once"):
        load_or_empty(f)


def test_by_surface_returns_dict_keyed_by_surface(tmp_path: Path):
    """The by_surface() helper exposes O(1) lookup for the algorithm
    (#74.3 canonicalize.run will use this after normalizing slugs)."""
    f = tmp_path / "aliases.json"
    _write(f, {"aliases": [
        {"surface": "AAPL", "canonical": "apple-inc"},
        {"surface": "GOOG", "canonical": "alphabet-inc"},
    ]})
    ledger = load_or_empty(f)

    by_sf = ledger.by_surface()
    assert set(by_sf.keys()) == {"AAPL", "GOOG"}
    assert by_sf["AAPL"].canonical == "apple-inc"
    assert by_sf["GOOG"].canonical == "alphabet-inc"


def test_sha_is_deterministic_across_loads(tmp_path: Path):
    """Same bytes → same sha. Two loads of the unchanged file produce the
    same snapshot_sha256 — required for D-R5-7 replay parity."""
    f = tmp_path / "aliases.json"
    _write(f, {"aliases": [{"surface": "AAPL", "canonical": "apple-inc"}]})

    l1 = load_or_empty(f)
    l2 = load_or_empty(f)

    assert l1.snapshot_sha256 == l2.snapshot_sha256
    assert l1.snapshot_sha256 != EMPTY_LEDGER_SHA


def test_load_or_empty_accepts_str_path(tmp_path: Path):
    """The signature accepts `Path | str`; verify str works the same as Path."""
    f = tmp_path / "aliases.json"
    _write(f, {"aliases": []})
    ledger = load_or_empty(str(f))
    assert ledger.path == f  # normalized to Path
