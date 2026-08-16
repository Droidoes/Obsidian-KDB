"""response_replay — run stored model responses through the era-correct
compile validator stack and compare the observed flags against each
fixture's expected flags (#119, D-BQ-1):

    3.x  → legacy stack: recover → schema → semantic
    4.x  → new stack:    recover → proposal validate → normalization bridge
    else → fail closed:  all flags False + "unsupported prompt_version"

Complements the live resp-stats records written by `compile_one` (blueprint
§7). Replay fixtures pin down regressions in the extractor, schema, and
semantic layers without burning API budget: you edit a validator, run
`kdb-replay --replay tests/fixtures/response_replay/`, and see every
known-good and known-bad case re-scored.

Each fixture directory contains:
    source.md            — raw input (informational, not replayed)
    stored_response.txt  — verbatim model output (may include fences/prose)
    case.json            — { source_id, expected_extract_ok,
                             expected_parse_ok, expected_schema_ok,
                             expected_semantic_ok, notes,
                             prompt_version? (default "3.0.0") }

`main` exits 0 iff every case's observed flags match expected; 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from kdb_graph_compiler import validate_source_response
from kdb_graph_compiler.response_recovery import recover_json_response


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
    # #119 (D-BQ-1): contract era of the stored response; the default covers
    # all pre-#119 fixtures. Placed last (dataclass defaults after non-defaults).
    prompt_version: str = "3.0.0"


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
                # #115 T2.2: fixtures key on source_id (source_name tolerated
                # for unmigrated historical cases)
                source_id=meta.get("source_id") or meta["source_name"],
                stored_response_text=response_txt.read_text(encoding="utf-8"),
                expected_extract_ok=bool(meta["expected_extract_ok"]),
                expected_parse_ok=bool(meta["expected_parse_ok"]),
                expected_schema_ok=bool(meta["expected_schema_ok"]),
                expected_semantic_ok=bool(meta["expected_semantic_ok"]),
                notes=meta.get("notes", ""),
                # #119: absent on pre-#119 case.json files → legacy 3.x era.
                prompt_version=str(meta.get("prompt_version", "3.0.0")),
            )
        )
    return cases


def replay_case(fixture: ReplayFixture) -> ReplayResult:
    """Dispatch one fixture through the era-correct validator stack (#119,
    D-BQ-1). Unknown eras fail CLOSED — all flags False, matches_expected
    False, error_detail set — so a misstamped fixture can never pass."""
    if fixture.prompt_version.startswith("3."):
        return _replay_case_v3(fixture)   # today's body, moved verbatim
    if fixture.prompt_version.startswith("4."):
        return _replay_case_v4(fixture)
    return ReplayResult(case_id=fixture.case_id, extract_ok=False,
                        parse_ok=False, schema_ok=False, semantic_ok=False,
                        matches_expected=False,
                        error_detail=(
                            f"unsupported prompt_version "
                            f"{fixture.prompt_version!r}"))


def _replay_case_v3(fixture: ReplayFixture) -> ReplayResult:
    """Run one fixture through the full validator stack.

    Uses the shared recovery ladder (#114) so a captured response yields
    ONE verdict across compile_one and replay. Short-circuits on first
    failure (mirroring compile_one): a recovery-fail yields
    parse=schema=semantic=False. The first failure's message is captured
    in error_detail for the report.
    """
    extract_ok = False
    parse_ok = False
    schema_ok = False
    semantic_ok = False
    error_detail: str | None = None

    result = recover_json_response(fixture.stored_response_text)
    extract_ok = result.extract_ok
    if not result.recovered:
        error_detail = f"parse: {result.error}"
        return _result(fixture, extract_ok, parse_ok, schema_ok, semantic_ok, error_detail)

    parse_ok = True
    parsed = result.parsed

    schema_errors = validate_source_response.validate(parsed)
    schema_ok = schema_errors == []
    if not schema_ok:
        error_detail = f"schema: {schema_errors[0]}"
        return _result(fixture, extract_ok, parse_ok, schema_ok, semantic_ok, error_detail)

    if not isinstance(parsed, dict):
        # Shouldn't happen (schema would have caught), but guard anyway.
        error_detail = "semantic: payload is not an object"
        return _result(fixture, extract_ok, parse_ok, schema_ok, semantic_ok, error_detail)

    # #115 T2.2: the expected summary slug is derived from the source id,
    # never taken from the payload. Codex Gate-2 F5: an underivable stem
    # fails CLOSED (semantic_ok=False) instead of aborting the replay run.
    from kdb_graph_compiler.summary_slug import expected_summary_slug
    from common.paths import PathError
    try:
        expected_slug = expected_summary_slug(fixture.source_id)
    except PathError as e:
        error_detail = f"semantic: cannot derive expected summary slug: {e}"
        return _result(fixture, extract_ok, parse_ok, schema_ok, False, error_detail)
    semantic_errors = validate_source_response.semantic_check(
        parsed,
        expected_summary_slug=expected_slug,
    )
    semantic_ok = semantic_errors == []
    if not semantic_ok:
        error_detail = f"semantic: {semantic_errors[0]}"

    return _result(fixture, extract_ok, parse_ok, schema_ok, semantic_ok, error_detail)


def _flag_result(fixture: ReplayFixture, *, extract_ok: bool, parse_ok: bool,
                 schema_ok: bool = False, semantic_ok: bool = False,
                 error_detail: str | None) -> ReplayResult:
    observed = (extract_ok, parse_ok, schema_ok, semantic_ok)
    expected = (fixture.expected_extract_ok, fixture.expected_parse_ok,
                fixture.expected_schema_ok, fixture.expected_semantic_ok)
    return ReplayResult(case_id=fixture.case_id, extract_ok=extract_ok,
                        parse_ok=parse_ok, schema_ok=schema_ok,
                        semantic_ok=semantic_ok,
                        matches_expected=observed == expected,
                        error_detail=error_detail)


def _replay_case_v4(fixture: ReplayFixture) -> ReplayResult:
    from common.paths import PathError
    from kdb_graph_compiler import proposal_bridge, validate_proposal_response
    result = recover_json_response(fixture.stored_response_text)
    if not result.recovered:
        return _flag_result(fixture, extract_ok=result.extract_ok,
                            parse_ok=False, error_detail=result.error)
    schema_errors = validate_proposal_response.validate(result.parsed)
    if schema_errors:
        return _flag_result(fixture, extract_ok=result.extract_ok,
                            parse_ok=True, schema_ok=False,
                            error_detail=schema_errors[0])
    try:
        bridge = proposal_bridge.normalize_proposal(
            result.parsed, source_id=fixture.source_id)
    except proposal_bridge.CanonicalInvariantError as e:
        return _flag_result(fixture, extract_ok=result.extract_ok,
                            parse_ok=True, schema_ok=True, semantic_ok=False,
                            error_detail=f"CanonicalInvariantError: {e}")
    except PathError as e:  # underivable source_id — case error, not a defect
        return _flag_result(fixture, extract_ok=result.extract_ok,
                            parse_ok=True, schema_ok=True, semantic_ok=False,
                            error_detail=f"cannot derive expected summary slug: {e}")
    if isinstance(bridge, proposal_bridge.BridgeReject):
        return _flag_result(
            fixture, extract_ok=result.extract_ok, parse_ok=True,
            schema_ok=True, semantic_ok=False,
            error_detail=f"{bridge.reject_class.value}: {bridge.detail}")
    return _flag_result(fixture, extract_ok=result.extract_ok, parse_ok=True,
                        schema_ok=True, semantic_ok=True, error_detail=None)


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
    print(f"\nkdb-replay: {passed}/{total} case(s) matched expectations")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kdb-replay",
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
        print(f"kdb-replay: {exc}", file=sys.stderr)
        return 1

    if not fixtures:
        print(f"kdb-replay: no cases found under {fixtures_dir}", file=sys.stderr)
        return 1

    results = [replay_case(f) for f in fixtures]
    print_report(results)
    return 0 if all(r.matches_expected for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
