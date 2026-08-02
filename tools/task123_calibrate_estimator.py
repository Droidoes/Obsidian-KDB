"""#123 D5 — the estimator calibration gate (spec §0 D5, blueprint §7).

**What D5 asks for, exactly:** one non-comparative real call per screening
candidate (hard 3-call ceiling) over the exact rendered fixture thin block,
reading the provider-reported input-token count `call_model` already surfaces,
persisted per candidate to a **sibling** artifact — the checksummed fixture
manifest is never mutated.

The number this produces is what `ESTIMATOR_BYTES_PER_TOKEN` (the ÷4) is
judged against forever. Three things follow from that, and they are why this file
is shaped the way it is:

**1. It measures the quantity the estimator estimates, not a proxy.**
`search.py:219` computes `rendered_bytes = len(system) + len(user)` and hands it
to `budget.preflight`. This harness hashes and measures the identical pair. A
calibration over the evidence block alone would calibrate a number nothing
consumes.

**2. Dry run is the default; spending requires `--fire`.** Joseph fires paid
runs, and the mode you get by typing the command wrong should be the free one.
Dry run renders the exact bytes, reports the estimate and the pre-flight verdict
per candidate, and calls nothing.

**3. The 3-call ceiling is enforced by a counter that raises, not by a loop that
happens to run three times.** A retry added later cannot turn 3 into 6.

**Why `tools/` and not `scripts/`, where the fixture builder lives.**
`scripts/` is outside `testpaths` (pyproject `:53`) — nothing there is covered.
For a one-shot builder of a checked-in artifact that is an acceptable trade; for
a runner that spends money it is not, so this sits where `tools/tests/` can reach
it. No `[project.scripts]` entry either: a paid one-off gate does not belong in
the shipped `kdb-*` CLI surface.

Run:

    .venv/bin/python -m tools.task123_calibrate_estimator            # dry run
    .venv/bin/python -m tools.task123_calibrate_estimator --fire     # 3 paid calls
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from datetime import datetime

from common.call_model import ModelRequest, ModelResponse, call_model
from common.model_pool import ModelSpec, resolve_models_json
from kdb_search import budget
from kdb_search.artifact import RenderedMessages
from kdb_search.constants import ESTIMATOR_BYTES_PER_TOKEN, M
from kdb_search.projection import render_query_block, render_thin_line
from kdb_search.prompts import load_template, render_thin_messages
from kdb_search.types import SpaceEntity

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "benchmark" / "truth" / "task123_search_snapshot_v1"
ARTIFACT_PATH = REPO_ROOT / "benchmark" / "truth" / "task123_search_calibration_v1.json"

#: The files D5 says are never mutated. Hashed before and after the run and
#: asserted identical — "never mutated" becomes true by check rather than by
#: intention, and this harness writes to the same directory.
IMMUTABLE_FIXTURE_FILES = ("manifest.json", "checksums.sha256", "identities.json")

#: The D4 screening cohort, in the order the blueprint names them
#: (gemini-3.6-flash is the interim default selector).
D4_COHORT: tuple[str, ...] = ("gemini-3.6-flash", "gpt-5.4-mini", "deepseek-v4-flash")

#: D5's hard ceiling. Not a suggestion — `CallCeiling` raises past it.
CALL_CEILING = 3

#: Output cap for the calibration call. The measurement reads `input_tokens`,
#: which is settled before a single output token exists — so there is no reason
#: to buy a full 13,000-token thin selection three times. Deliberately NOT
#: `provider_max_tokens("thin")`: that figure is the production envelope (D9),
#: and reserving it here would let each candidate generate a complete selection
#: and bill for it. Everything else about the request is production-identical,
#: which `tools/tests/test_task123_calibrate_estimator.py` pins field by field.
CALIBRATION_MAX_TOKENS = 32

COUNTING_SOURCE = "provider_reported_usage"


class CalibrationError(RuntimeError):
    """Something about the run's preconditions is wrong. Raised before spending."""


class CallCeiling:
    """D5's 3-call ceiling, as an object that refuses rather than a convention.

    Counts *attempts*, not successes: a candidate that errors has still been
    billed for whatever the provider did before failing, and a ceiling that only
    counted successes would let three failures fund three more calls.
    """

    def __init__(self, limit: int = CALL_CEILING) -> None:
        self.limit = limit
        self.used = 0

    def charge(self, model_id: str) -> None:
        if self.used >= self.limit:
            raise CalibrationError(
                f"D5's {self.limit}-call ceiling is spent; refusing a call for "
                f"{model_id!r}. The ceiling counts attempts, including failed ones — "
                "a failed candidate is re-run in a separate, deliberate invocation, "
                "not by widening the ceiling."
            )
        self.used += 1


# ---------------------------------------------------------------------------
# the rendered input — the exact bytes, built once and shared by all candidates
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationInput:
    """One rendered thin request, plus the provenance the artifact records.

    Built once and reused across candidates: D5 says *fixed prompt*, and
    re-rendering per candidate would make that a property of this loop rather
    than of the data.
    """

    messages: RenderedMessages
    rendered_bytes: int
    input_sha256: str
    query_source: str
    entity_count: int
    prompt_version: str
    fixture_version: str


def _fixture_version() -> str:
    """The fixture version, derived from the directory name.

    The manifest declares `excerpt_policy_version`, which is a *different*
    quantity — reading it into a field named `fixture_version` would be the
    name-matching-contents defect. The directory is the fixture's identity, and
    `_v1` → `_v2` is how a new fixture is minted.
    """
    return FIXTURE_DIR.name.rsplit("_v", 1)[-1]


def _fixture_entities() -> tuple[SpaceEntity, ...]:
    """The 163 frozen identities, in the fixture's own order.

    Thin needs no bodies — `render_thin_line` reads slug/title/page_type only —
    so this reads `identities.json` and never opens an excerpt. That is also why
    a calibration run cannot accidentally depend on the excerpt policy.
    """
    rows = json.loads((FIXTURE_DIR / "identities.json").read_text())
    return tuple(
        SpaceEntity(slug=r["slug"], title=r["title"], page_type=r["page_type"])
        for r in rows
    )


def _hash_input(messages: RenderedMessages) -> str:
    """sha256 over the pair, NUL-separated.

    The separator is load-bearing: hashing `system + user` concatenated would
    give identical digests for a byte moved from the end of the system block to
    the start of the user block — two different requests, one hash.
    """
    digest = hashlib.sha256(
        messages.system.encode() + b"\x00" + messages.user.encode()
    ).hexdigest()
    return f"sha256:{digest}"


def _query_text(query_file: pathlib.Path | None) -> tuple[str, str]:
    """The query block and a name for it.

    **Default: the empty query slot**, which is what makes this measurement
    reproducible from the fixture alone. The thin request the estimator guards is
    dominated by the evidence block — 163 slug-heavy identity lines — and that
    is precisely the density the ÷4 is being judged on. A query adds a few
    hundred bytes of ordinary prose, whose density differs from slug text, and
    pins the measurement to a query that would then need its own fixture.

    `--query-file` takes a JSON object of `render_query_block` keyword arguments
    for the case where the owner wants a real query in the measured bytes. The
    name is recorded in the artifact: an input hash tells a later reader that the
    bytes differed, not what they were.
    """
    if query_file is None:
        return "", "empty_query_slot"
    kwargs = json.loads(query_file.read_text())
    rendered = render_query_block(**kwargs)
    return rendered.text, f"query_file:{query_file.name}"


def build_input(query_file: pathlib.Path | None = None) -> CalibrationInput:
    entities = _fixture_entities()
    evidence = "\n".join(render_thin_line(e) for e in entities)
    query, query_source = _query_text(query_file)
    messages = render_thin_messages(evidence=evidence, query=query, retention_cap=M)
    return CalibrationInput(
        messages=messages,
        rendered_bytes=len(messages.system.encode()) + len(messages.user.encode()),
        input_sha256=_hash_input(messages),
        query_source=query_source,
        entity_count=len(entities),
        prompt_version=load_template("thin").ref.version,
        fixture_version=_fixture_version(),
    )


# ---------------------------------------------------------------------------
# the request
# ---------------------------------------------------------------------------


def calibration_request(spec: ModelSpec, messages: RenderedMessages) -> ModelRequest:
    """The production thin request, with output capped to near-nothing.

    Mirrors `stage._model_request("thin", ...)` field for field — `json_mode`,
    `temperature`, `use_completion_tokens`, `extra_body`, `route` — because the
    point of calibrating is to measure the request the system actually sends. The
    single deliberate divergence is `max_tokens`, and the test suite asserts it is
    the only one, so a future change to the production request cannot silently
    leave the calibrated request behind.
    """
    return ModelRequest(
        provider=spec.provider,
        model=spec.model,
        prompt=messages.user,
        system=messages.system,
        json_mode=True,
        temperature=spec.temperature,
        max_tokens=CALIBRATION_MAX_TOKENS,
        use_completion_tokens=spec.use_completion_tokens,
        extra_body=spec.extra_body,
        route=spec.route,
    )


# ---------------------------------------------------------------------------
# measurement
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Measurement:
    """One candidate's D5 row — exactly the fields D5 enumerates, nothing added.

    Self-describing on purpose: this artifact is a series, and a row that carries
    its own fixture version, input hash and prompt version can be compared
    against a row written months later without consulting a header.
    """

    counting_source: str
    fixture_version: str
    input_sha256: str
    prompt_version: str
    model_id: str
    input_tokens: int
    bytes_per_token: float

    def as_json(self) -> dict[str, object]:
        return {
            "counting_source": self.counting_source,
            "fixture_version": self.fixture_version,
            "input_sha256": self.input_sha256,
            "prompt_version": self.prompt_version,
            "model_id": self.model_id,
            "input_tokens": self.input_tokens,
            "bytes_per_token": self.bytes_per_token,
        }


def measure(
    spec: ModelSpec, calibration: CalibrationInput, response: ModelResponse
) -> Measurement:
    if response.input_tokens <= 0:
        raise CalibrationError(
            f"{spec.id} reported {response.input_tokens} input tokens — the provider "
            "did not surface a usable count, so there is no measurement to record. "
            "The call was still billed; do not re-run it inside the same ceiling."
        )
    return Measurement(
        counting_source=COUNTING_SOURCE,
        fixture_version=calibration.fixture_version,
        input_sha256=calibration.input_sha256,
        prompt_version=calibration.prompt_version,
        model_id=spec.id,
        input_tokens=response.input_tokens,
        bytes_per_token=round(calibration.rendered_bytes / response.input_tokens, 4),
    )


# ---------------------------------------------------------------------------
# the artifact — written incrementally
# ---------------------------------------------------------------------------


def _artifact_json(
    calibration: CalibrationInput,
    measurements: list[Measurement],
    failures: list[dict[str, str]],
) -> dict[str, object]:
    return {
        "artifact": ARTIFACT_PATH.stem,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "decision": "D5 — estimator calibration contract (spec §0, blueprint §7)",
        "counting_source": COUNTING_SOURCE,
        "query_source": calibration.query_source,
        "entity_count": calibration.entity_count,
        "rendered_bytes": calibration.rendered_bytes,
        "estimator_bytes_per_token_under_test": ESTIMATOR_BYTES_PER_TOKEN,
        "measurements": [m.as_json() for m in measurements],
        "failures": failures,
    }


def write_artifact(
    calibration: CalibrationInput,
    measurements: list[Measurement],
    failures: list[dict[str, str]],
    *,
    path: pathlib.Path | None = None,
) -> None:
    """Rewritten after every candidate, successful or not.

    Written incrementally rather than once at the end because the money is spent
    at the call, not at the write: a third candidate that raises must not take the
    first two paid measurements with it.

    `path` resolves at call time rather than as a default argument value, so a
    test can redirect the write by setting the module attribute — a default bound
    at import would send every test's write to the real artifact.
    """
    target = path or ARTIFACT_PATH
    target.write_text(
        json.dumps(_artifact_json(calibration, measurements, failures), indent=2) + "\n"
    )


def _display(path: pathlib.Path) -> str:
    """Repo-relative when it is inside the repo, absolute otherwise."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _fixture_fingerprint() -> dict[str, str]:
    return {
        name: hashlib.sha256((FIXTURE_DIR / name).read_bytes()).hexdigest()
        for name in IMMUTABLE_FIXTURE_FILES
    }


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _resolve(model_id: str) -> ModelSpec:
    """Resolve through `budget.resolve_selector_route`, the same gate a live
    search goes through — `tokens_lte_bytes`, `ctx_window` and the D9 output
    envelope are all asserted there. A candidate that could not legally be a
    selector must not be calibrated as one."""
    return budget.resolve_selector_route(resolve_models_json(model_id))


def dry_run(calibration: CalibrationInput, cohort: tuple[str, ...]) -> int:
    print(f"D5 calibration — DRY RUN (no calls, no spend)\n")
    print(f"  fixture            : {FIXTURE_DIR.name} ({calibration.entity_count} entities)")
    print(f"  query              : {calibration.query_source}")
    print(f"  thin prompt version: v{calibration.prompt_version}")
    print(f"  rendered bytes     : {calibration.rendered_bytes:,} "
          f"(system {len(calibration.messages.system.encode()):,} + "
          f"user {len(calibration.messages.user.encode()):,})")
    print(f"  input sha256       : {calibration.input_sha256}")
    estimate = budget.estimate_input_tokens(calibration.rendered_bytes)
    print(f"  estimate (÷{ESTIMATOR_BYTES_PER_TOKEN})        : {estimate:,} tokens")
    print(f"  reserved output    : {budget.reserved_output_tokens('thin'):,} tokens")
    print(f"  calibration cap    : max_tokens={CALIBRATION_MAX_TOKENS}\n")
    for model_id in cohort:
        spec = _resolve(model_id)
        verdict = budget.preflight(
            "thin", rendered_bytes=calibration.rendered_bytes, spec=spec
        )
        fits = "fits" if verdict.fits else "OVER BUDGET"
        print(
            f"  {model_id:<20} window {spec.ctx_window:>9,}  "
            f"budget {verdict.context_budget_tokens:>9,}  {fits}"
        )
    print(f"\n  would write: {_display(ARTIFACT_PATH)}")
    print(f"  to spend {len(cohort)} calls, re-run with --fire")
    return 0


def fire(calibration: CalibrationInput, cohort: tuple[str, ...]) -> int:
    if len(cohort) > CALL_CEILING:
        raise CalibrationError(
            f"{len(cohort)} candidates against a {CALL_CEILING}-call ceiling (D5)"
        )
    before = _fixture_fingerprint()
    ceiling = CallCeiling()
    measurements: list[Measurement] = []
    failures: list[dict[str, str]] = []

    for model_id in cohort:
        spec = _resolve(model_id)
        verdict = budget.preflight(
            "thin", rendered_bytes=calibration.rendered_bytes, spec=spec
        )
        if not verdict.fits:
            # Not a paid failure — the ceiling is untouched and the run goes on.
            failures.append(
                {"model_id": model_id, "stage": "preflight", "error": "budget_exceeded"}
            )
            print(f"  {model_id:<20} SKIPPED — pre-flight budget_exceeded (no call)")
            write_artifact(calibration, measurements, failures)
            continue
        ceiling.charge(model_id)
        try:
            response = call_model(calibration_request(spec, calibration.messages))
            measurement = measure(spec, calibration, response)
        except Exception as exc:  # noqa: BLE001 — one candidate must not end the run
            failures.append(
                {"model_id": model_id, "stage": "call", "error": f"{type(exc).__name__}: {exc}"}
            )
            print(f"  {model_id:<20} FAILED — {type(exc).__name__}: {exc}")
            write_artifact(calibration, measurements, failures)
            continue
        measurements.append(measurement)
        print(
            f"  {model_id:<20} {measurement.input_tokens:>8,} tokens  "
            f"{measurement.bytes_per_token:>6.3f} B/token"
        )
        # After every candidate: the spend already happened.
        write_artifact(calibration, measurements, failures)

    after = _fixture_fingerprint()
    if before != after:
        raise CalibrationError(
            "the checksummed fixture changed during the run — D5 says the manifest "
            f"is never mutated (before {before}, after {after})"
        )
    print(f"\n  calls spent: {ceiling.used}/{ceiling.limit}")
    print(f"  written    : {_display(ARTIFACT_PATH)}")
    return 0 if measurements and not failures else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="task123_calibrate_estimator",
        description="#123 D5 estimator calibration — dry run unless --fire is given.",
    )
    parser.add_argument(
        "--fire",
        action="store_true",
        help="actually call the providers (PAID — one call per candidate, 3 max)",
    )
    parser.add_argument(
        "--query-file",
        type=pathlib.Path,
        default=None,
        help="JSON object of render_query_block kwargs; default is an empty query slot",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(D4_COHORT),
        help=f"candidates to calibrate (default: the D4 cohort {' '.join(D4_COHORT)})",
    )
    args = parser.parse_args(argv)

    calibration = build_input(args.query_file)
    cohort = tuple(args.models)
    try:
        return fire(calibration, cohort) if args.fire else dry_run(calibration, cohort)
    except CalibrationError as exc:
        print(f"calibration refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
