"""eval_replay — run stored model responses through the compile validator
stack (extract → parse → schema → semantic) and compare the observed
flags against each fixture's expected flags.

Complements the live eval records written by `compile_one` (blueprint
§7). Replay fixtures pin down regressions in the extractor, schema, and
semantic layers without burning API budget: you edit a validator, run
`kdb-eval --replay kdb_compiler/tests/fixtures/eval/`, and see every
known-good and known-bad case re-scored.

Each fixture directory contains:
    source.md            — raw input (informational, not replayed)
    stored_response.txt  — verbatim model output (may include fences/prose)
    case.json            — { source_id, expected_extract_ok,
                             expected_parse_ok, expected_schema_ok,
                             expected_semantic_ok, notes }

`main` exits 0 iff every case's observed flags match expected; 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from kdb_compiler import response_normalizer, validate_compiled_source_response


@dataclass
class ReplayFixture:
    case_id: str
    source_id: str
    stored_response_text: str
    expected_extract_ok: bool
    expected_parse_ok: bool
    expected_schema_ok: bool
    expected_semantic_ok: bool
    notes: str


@dataclass
class ReplayResult:
    case_id: str
    extract_ok: bool
    parse_ok: bool
    schema_ok: bool
    semantic_ok: bool
    matches_expected: bool
    error_detail: str | None


def load_fixtures(fixtures_dir: Path) -> list[ReplayFixture]:
    """Scan fixtures_dir for case subdirectories and load each one.

    Every subdirectory with a `case.json` is treated as a case. Cases are
    returned sorted by case_id (directory name) for deterministic order.
    """
    fixtures_dir = Path(fixtures_dir)
    if not fixtures_dir.is_dir():
        raise FileNotFoundError(f"fixtures dir not found: {fixtures_dir}")

    cases: list[ReplayFixture] = []
    for entry in sorted(fixtures_dir.iterdir()):
        if not entry.is_dir():
            continue
        case_json = entry / "case.json"
        response_txt = entry / "stored_response.txt"
        if not case_json.exists() or not response_txt.exists():
            continue
        meta = json.loads(case_json.read_text(encoding="utf-8"))
        cases.append(
            ReplayFixture(
                case_id=entry.name,
                source_id=meta["source_id"],
                stored_response_text=response_txt.read_text(encoding="utf-8"),
                expected_extract_ok=bool(meta["expected_extract_ok"]),
                expected_parse_ok=bool(meta["expected_parse_ok"]),
                expected_schema_ok=bool(meta["expected_schema_ok"]),
                expected_semantic_ok=bool(meta["expected_semantic_ok"]),
                notes=meta.get("notes", ""),
            )
        )
    return cases


def replay_case(fixture: ReplayFixture) -> ReplayResult:
    """Run one fixture through the full validator stack.

    Short-circuits on first failure (mirroring compile_one): an
    extract-fail yields parse=schema=semantic=False. The first failure's
    message is captured in error_detail for the report.
    """
    extract_ok = False
    parse_ok = False
    schema_ok = False
    semantic_ok = False
    error_detail: str | None = None

    json_text: str
    try:
        json_text = response_normalizer.extract_json_text(
            fixture.stored_response_text
        )
        extract_ok = True
    except ValueError as e:
        error_detail = f"extract: {e}"
        return _result(fixture, extract_ok, parse_ok, schema_ok, semantic_ok, error_detail)

    parsed: object
    try:
        parsed = json.loads(json_text)
        parse_ok = True
    except json.JSONDecodeError as e:
        error_detail = f"parse: {e.msg} at line {e.lineno}"
        return _result(fixture, extract_ok, parse_ok, schema_ok, semantic_ok, error_detail)

    schema_errors = validate_compiled_source_response.validate(parsed)
    schema_ok = schema_errors == []
    if not schema_ok:
        error_detail = f"schema: {schema_errors[0]}"
        return _result(fixture, extract_ok, parse_ok, schema_ok, semantic_ok, error_detail)

    if not isinstance(parsed, dict):
        # Shouldn't happen (schema would have caught), but guard anyway.
        error_detail = "semantic: payload is not an object"
        return _result(fixture, extract_ok, parse_ok, schema_ok, semantic_ok, error_detail)

    semantic_errors = validate_compiled_source_response.semantic_check(
        parsed, source_id=fixture.source_id
    )
    semantic_ok = semantic_errors == []
    if not semantic_ok:
        error_detail = f"semantic: {semantic_errors[0]}"

    return _result(fixture, extract_ok, parse_ok, schema_ok, semantic_ok, error_detail)


def _result(
    fixture: ReplayFixture,
    extract_ok: bool,
    parse_ok: bool,
    schema_ok: bool,
    semantic_ok: bool,
    error_detail: str | None,
) -> ReplayResult:
    matches = (
        extract_ok == fixture.expected_extract_ok
        and parse_ok == fixture.expected_parse_ok
        and schema_ok == fixture.expected_schema_ok
        and semantic_ok == fixture.expected_semantic_ok
    )
    return ReplayResult(
        case_id=fixture.case_id,
        extract_ok=extract_ok,
        parse_ok=parse_ok,
        schema_ok=schema_ok,
        semantic_ok=semantic_ok,
        matches_expected=matches,
        error_detail=error_detail,
    )


def print_report(results: list[ReplayResult]) -> None:
    """Emit a per-case status line plus a trailing tally.

    Status glyph: 'PASS' iff matches_expected, else 'FAIL'. Flags are
    printed as a 4-char EPSM mask (e=extract, p=parse, s=schema, m=semantic)
    with lowercase meaning False and uppercase meaning True, so a
    fully-valid response prints 'EPSM' and a schema-fail prints 'EPs m'.
    """
    passed = 0
    for r in results:
        status = "PASS" if r.matches_expected else "FAIL"
        mask = (
            ("E" if r.extract_ok else "e")
            + ("P" if r.parse_ok else "p")
            + ("S" if r.schema_ok else "s")
            + ("M" if r.semantic_ok else "m")
        )
        detail = f"  — {r.error_detail}" if r.error_detail else ""
        print(f"  {status}  {r.case_id}  [{mask}]{detail}")
        if r.matches_expected:
            passed += 1
    total = len(results)
    print(f"\nkdb-eval: {passed}/{total} case(s) matched expectations")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kdb-eval",
        description=(
            "Replay stored model responses through the compile validator "
            "stack and compare against expected flags."
        ),
    )
    p.add_argument(
        "--replay",
        required=True,
        help="Directory containing case subdirectories with case.json + stored_response.txt",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    fixtures_dir = Path(args.replay)

    try:
        fixtures = load_fixtures(fixtures_dir)
    except FileNotFoundError as exc:
        print(f"kdb-eval: {exc}", file=sys.stderr)
        return 1

    if not fixtures:
        print(f"kdb-eval: no cases found under {fixtures_dir}", file=sys.stderr)
        return 1

    results = [replay_case(f) for f in fixtures]
    print_report(results)
    return 0 if all(r.matches_expected for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
