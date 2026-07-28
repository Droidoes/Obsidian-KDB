"""#123 P2.1a — the selector prompt loader, message assembly and D10 ordering.

Three things here are oracles rather than restatements, and they are the reason
this file is worth its length:

  * **The schema example printed in each SYSTEM block is driven through the real
    validator.** `response.validate_response` / `validate_thin_retention` decide
    whether the example the model is shown is an example of a response we would
    actually accept. Every other way of testing a prompt's schema block restates
    it, which pins nothing. This also puts a floor under the owner's prose
    review: an example edited wrongly fails a test instead of reaching a paid
    call.
  * **D10 is asserted on the rendered USER message, twice** — once with content
    sentinels (the slot order, immune to what the content happens to contain) and
    once with the unindented section headers (the order the model reads). A
    template can reorder at render time; the claim is about what is received.
  * **The byte budget is measured, not declared.** `SYSTEM_TEMPLATE_BUDGET_BYTES`
    was a reserve until this file; the assertions here are what convert
    `budget.fat_worst_case_request_bytes()` from part-declared to measured.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from kdb_search import prompts
from kdb_search.artifact import RenderedMessages, sha256_digest
from kdb_search.budget import (
    fat_static_guarantee_tokens,
    fat_worst_case_request_bytes,
    reserved_output_tokens,
    worst_case_input_tokens,
)
from kdb_search.constants import (
    EXCERPT_BLOCK_CEILING_BYTES,
    M,
    MAX_RESULTS,
    QUERY_BLOCK_CEILING_BYTES,
    SMALLEST_POOL_BUDGET_TOKENS,
    SYSTEM_TEMPLATE_BUDGET_BYTES,
    expression_labels,
)
from kdb_search.prompts import (
    PromptTemplateError,
    load_template,
    render_fat_messages,
    render_thin_messages,
    template_overhead_bytes,
)
from kdb_search.response import validate_response, validate_thin_retention
from kdb_search.types import SearchConfigError, SpaceEntity

STAGES = ("thin", "fat")
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPT_DIR = _REPO_ROOT / "kdb_search" / "prompts"

E_SENTINEL = "<<<evidence-goes-here>>>"
Q_SENTINEL = "<<<query-goes-here>>>"


def _render(stage: str, *, evidence: str, query: str) -> RenderedMessages:
    if stage == "thin":
        return render_thin_messages(evidence=evidence, query=query)
    return render_fat_messages(evidence=evidence, query=query, max_results=MAX_RESULTS)


@pytest.fixture(autouse=True)
def _isolate_template_cache():
    """`load_template` is cached, and several tests below point `_PROMPT_DIR` at a
    tmp directory. Clearing around every test is structural: a leaked cache entry
    would poison whichever test ran next, which is exactly the kind of failure
    that gets misdiagnosed as flakiness."""
    load_template.cache_clear()
    yield
    load_template.cache_clear()


def _schema_example(system: str) -> str:
    """The one JSON-object line in a SYSTEM block — the example the model copies.

    Deliberately strict at exactly one: a second example is a second contract for
    the model to choose between, and only one of them would be under test here. If
    the prose review wants two, that is a decision to make explicitly, not
    something this helper should absorb.
    """
    lines = [line for line in system.splitlines() if line.startswith("{") and line.endswith("}")]
    assert len(lines) == 1, f"expected exactly one schema example line, found {len(lines)}"
    return lines[0]


# ---------------------------------------------------------------------------
# loading + provenance
# ---------------------------------------------------------------------------


def test_the_prompts_MODULE_wins_over_the_prompts_DATA_directory():
    """`kdb_search/prompts.py` and `kdb_search/prompts/` share a name, so the
    import system's precedence is load-bearing: a regular module beats a
    namespace-package directory, and adding `prompts/__init__.py` would shadow
    the module and break every import in this file at once."""
    assert Path(prompts.__file__).name == "prompts.py"
    assert not (_PROMPT_DIR / "__init__.py").exists()


@pytest.mark.parametrize("stage", STAGES)
def test_version_comes_from_the_filename(stage):
    template = load_template(stage)
    assert template.ref.version == "1"
    assert template.ref.repo_path.endswith(f"_v{template.ref.version}.txt")


def test_the_version_TRACKS_the_filename_rather_than_matching_it_by_coincidence(
    monkeypatch, tmp_path
):
    """`version == "1"` is satisfied by a hardcoded `"1"` too, so the derivation
    is only pinned by a filename that says something else. Renaming the file is
    the act that bumps the prompt version — there is no second place to edit."""
    (tmp_path / "selector_thin_v9.txt").write_text("s\n<<<USER>>>\n{{EVIDENCE}}\n")
    monkeypatch.setitem(prompts._FILENAMES, "thin", "selector_thin_v9.txt")
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    assert load_template("thin").ref.version == "9"


def test_the_spec_named_version_constants_derive_from_the_same_filenames():
    assert prompts.SELECTOR_THIN_PROMPT_VERSION == load_template("thin").ref.version
    assert prompts.SELECTOR_FAT_PROMPT_VERSION == load_template("fat").ref.version


@pytest.mark.parametrize("stage", STAGES)
def test_sha256_is_over_the_loaded_template_text(stage):
    path = _PROMPT_DIR / prompts._FILENAMES[stage]
    assert load_template(stage).ref.sha256 == sha256_digest(path.read_text(encoding="utf-8"))


def test_the_two_stages_hash_differently():
    """Cheap, and it is the assertion that fails if the loader ever returns one
    stage's text for the other."""
    assert load_template("thin").ref.sha256 != load_template("fat").ref.sha256


@pytest.mark.parametrize("stage", STAGES)
def test_repo_path_is_the_literal_package_path(stage):
    assert load_template(stage).ref.repo_path == f"kdb_search/prompts/{prompts._FILENAMES[stage]}"


@pytest.mark.parametrize("stage", STAGES)
def test_git_commit_is_a_short_sha_or_the_unknown_sentinel(stage):
    commit = load_template(stage).ref.git_commit
    assert commit == "unknown" or re.fullmatch(r"[0-9a-f]{7,40}", commit), commit


@pytest.mark.parametrize("stage", STAGES)
def test_load_template_is_cached(stage):
    assert load_template(stage) is load_template(stage)


def test_an_unversioned_filename_raises_rather_than_stamping_no_provenance(monkeypatch):
    monkeypatch.setitem(prompts._FILENAMES, "thin", "selector_thin.txt")
    with pytest.raises(PromptTemplateError, match="version suffix"):
        load_template("thin")


@pytest.mark.parametrize("bad", ["selector_thin.txt", "selector_thin_v.txt", "selector_thin_vX.txt",
                                 "selector_thin_v1.md", "selector_thin_v1.txt.bak"])
def test_the_version_parser_itself_is_typed_on_every_malformed_name(bad):
    """Tested directly, not only through `load_template` (codex F4): the module
    constants are computed at IMPORT, so on the real import path a malformed name
    fails before any test can monkeypatch anything. Asserting the parser is typed
    is the only way to cover the failure the constants would actually hit."""
    with pytest.raises(PromptTemplateError, match="version suffix"):
        prompts._version_of(bad)


def test_the_version_parser_is_the_ONE_parser():
    """`load_template` and the module constants must not each parse the name —
    that was the drift F4 found."""
    for stage, filename in prompts._FILENAMES.items():
        assert load_template(stage).ref.version == prompts._version_of(filename)


def test_a_missing_template_raises_a_packaging_fault(monkeypatch):
    monkeypatch.setitem(prompts._FILENAMES, "fat", "selector_absent_v1.txt")
    with pytest.raises(PromptTemplateError, match="packaging or install fault"):
        load_template("fat")


def test_prompt_template_error_is_a_search_config_error():
    """So a template fault fails hard at the same boundary as an unresolvable
    selector route, before any rendering, body read or call (§2.1)."""
    assert issubclass(PromptTemplateError, SearchConfigError)


# ---------------------------------------------------------------------------
# template hygiene — the P2.1f pins depend on every one of these
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", STAGES)
def test_no_carriage_returns_in_the_template(stage):
    """A CRLF checkout would move the sha256 AND the rendered bytes. The loader
    reads in text mode so the digest survives it; this asserts the file is LF in
    the repo, which is the half text mode cannot fix."""
    raw = (_PROMPT_DIR / prompts._FILENAMES[stage]).read_bytes()
    assert b"\r" not in raw


@pytest.mark.parametrize("stage", STAGES)
def test_no_trailing_whitespace_on_any_template_line(stage):
    """Invisible bytes that would silently move the digest and the pins."""
    text = (_PROMPT_DIR / prompts._FILENAMES[stage]).read_text(encoding="utf-8")
    offenders = [i for i, line in enumerate(text.splitlines(), 1) if line != line.rstrip()]
    assert offenders == []


@pytest.mark.parametrize("stage", STAGES)
def test_section_marker_appears_exactly_once(stage):
    text = (_PROMPT_DIR / prompts._FILENAMES[stage]).read_text(encoding="utf-8")
    assert text.count(prompts.SECTION_MARKER) == 1


@pytest.mark.parametrize("stage", STAGES)
def test_no_substitution_slot_survives_into_either_rendered_half(stage):
    """The system half has no slots by contract, and the user half is fully
    filled — so a literal `{{...}}` can never reach the model."""
    messages = _render(stage, evidence="e", query="q")
    assert prompts._SLOT.findall(messages.system) == []
    assert prompts._SLOT.findall(messages.user) == []


def test_a_slot_in_the_system_half_raises(monkeypatch, tmp_path):
    bad = tmp_path / "selector_thin_v1.txt"
    bad.write_text("system says {{EVIDENCE}}\n<<<USER>>>\nEVIDENCE:\n{{EVIDENCE}}\n")
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    with pytest.raises(PromptTemplateError, match="SYSTEM half"):
        load_template("thin")


def test_a_missing_section_marker_raises(monkeypatch, tmp_path):
    bad = tmp_path / "selector_thin_v1.txt"
    bad.write_text("no marker at all\n")
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    with pytest.raises(PromptTemplateError, match="section marker exactly once"):
        load_template("thin")


def test_a_CRLF_checkout_moves_neither_the_digest_nor_the_rendered_bytes(monkeypatch, tmp_path):
    """The oracle behind module rule 3. The digest is taken over the loaded TEXT,
    which text mode has already newline-translated, so a CRLF working copy hashes
    and renders identically to the LF original — and P2.1f's pins survive it.
    `read_bytes()` would make both the hash and the prompt platform-dependent."""
    lf = "system JSON\n<<<USER>>>\nEVIDENCE:\n{{EVIDENCE}}\n{{RETENTION_CAP}}\nQUERY:\n{{QUERY}}\n"
    (tmp_path / "selector_thin_v1.txt").write_bytes(lf.replace("\n", "\r\n").encode())
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)

    template = load_template("thin")
    assert "\r" not in template.system and "\r" not in template.user_template
    assert template.ref.sha256 == sha256_digest(lf)
    assert "\r" not in render_thin_messages(evidence="e", query="q").user


# ---------------------------------------------------------------------------
# D10 — asserted on the RENDERED user message, both stages
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", STAGES)
def test_D10_evidence_slot_precedes_query_slot_in_the_rendered_message(stage):
    """The slot-order form: immune to whatever the content happens to contain."""
    user = _render(stage, evidence=E_SENTINEL, query=Q_SENTINEL).user
    assert user.count(E_SENTINEL) == 1 and user.count(Q_SENTINEL) == 1
    assert user.index(E_SENTINEL) < user.index(Q_SENTINEL)


@pytest.mark.parametrize("stage", STAGES)
def test_D10_evidence_header_precedes_query_header_as_the_model_reads_them(stage):
    """The header form, on realistic content. Anchored to line starts because
    every evidence and query continuation line is indented, so an unindented
    `EVIDENCE:`/`QUERY:` line can only come from the template."""
    user = _render(
        stage,
        evidence="- slug: owner-earnings  title: Owner Earnings  type: concept",
        query="- query:\n  domain: investing",
    ).user
    headers = re.findall(r"^(EVIDENCE|QUERY):$", user, flags=re.MULTILINE)
    assert headers == ["EVIDENCE", "QUERY"]


@pytest.mark.parametrize("stage", STAGES)
def test_the_query_is_the_LAST_block_in_the_user_message(stage):
    """D10's attention-position half: the per-source query sits adjacent to the
    generation point, so nothing follows it."""
    assert _render(stage, evidence=E_SENTINEL, query=Q_SENTINEL).user.endswith(Q_SENTINEL)


@pytest.mark.parametrize("stage", STAGES)
def test_the_system_block_is_invariant_across_requests(stage):
    """The whole basis of D10's prefix-reuse argument: only the user message
    varies per source."""
    a = _render(stage, evidence="e1", query="q1").system
    b = _render(stage, evidence="e2", query="q2").system
    assert a == b == load_template(stage).system


@pytest.mark.parametrize("stage", STAGES)
def test_returns_the_artifact_RenderedMessages_type(stage):
    """So a `StageRecord` takes the rendered bytes directly — no second shape."""
    assert isinstance(_render(stage, evidence="e", query="q"), RenderedMessages)


# ---------------------------------------------------------------------------
# substitution — P10 injection, and the two silent-failure guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", STAGES)
def test_a_slot_marker_INSIDE_evidence_is_inert(stage):
    """P10: sequential `str.replace` would substitute the query block into an
    excerpt that contains the literal `{{QUERY}}`. Single-pass substitution
    leaves it as the text it is — and the real query still renders, last."""
    user = _render(stage, evidence="{{QUERY}} {{EVIDENCE}}", query=Q_SENTINEL).user
    assert "{{QUERY}} {{EVIDENCE}}" in user
    assert user.endswith(Q_SENTINEL)
    assert user.count(Q_SENTINEL) == 1


def test_an_unknown_slot_in_the_user_template_raises(monkeypatch, tmp_path):
    """A typo'd `{{EVIDENC}}` must fail, not ship a brace pair to the model."""
    (tmp_path / "selector_thin_v1.txt").write_text(
        "system\n<<<USER>>>\nEVIDENCE:\n{{EVIDENC}}\nQUERY:\n{{QUERY}}\n"
    )
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    with pytest.raises(PromptTemplateError, match="unknown slot"):
        render_thin_messages(evidence="e", query="q")


def test_a_value_with_no_slot_raises_rather_than_dropping_silently(monkeypatch, tmp_path):
    """The failure this guards is specific: drop `{{MAX_RESULTS}}` from the fat
    template and the result cap silently leaves the prompt while the selector is
    still measured against it (`over_cap` violations)."""
    (tmp_path / "selector_fat_v1.txt").write_text(
        "system\n<<<USER>>>\nEVIDENCE:\n{{EVIDENCE}}\nQUERY:\n{{QUERY}}\n"
    )
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    with pytest.raises(PromptTemplateError, match=r"no slot for \['MAX_RESULTS'\]"):
        render_fat_messages(evidence="e", query="q", max_results=MAX_RESULTS)


def test_a_repeated_slot_raises(monkeypatch, tmp_path):
    """Rendering the evidence twice would double the largest block in the request
    and break every byte figure downstream."""
    (tmp_path / "selector_thin_v1.txt").write_text(
        "system\n<<<USER>>>\n{{EVIDENCE}}\n{{EVIDENCE}}\n{{RETENTION_CAP}}\n{{QUERY}}\n"
    )
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    with pytest.raises(PromptTemplateError, match=r"repeats the slot\(s\) \['EVIDENCE'\]"):
        render_thin_messages(evidence="e", query="q")


# ---------------------------------------------------------------------------
# what the prompt actually states — validated, not restated
# ---------------------------------------------------------------------------


def test_the_fat_schema_example_is_accepted_by_the_REAL_validator():
    """The strongest oracle available for prompt prose: the example the model is
    told to copy is driven through `validate_response` against a space that
    contains its slug. If a prose edit breaks the example, this fails here rather
    than at a paid call."""
    example = _schema_example(load_template("fat").system)
    document = json.loads(example)
    slug = document["selections"][0]["slug"]
    space = (SpaceEntity(slug=slug, title="Example", page_type="concept"),)
    expressions = ("first key", "second key", "third key")

    validated = validate_response(
        example, space=space, expressions=expressions, max_results=MAX_RESULTS
    )
    assert validated.classification == "usable"
    assert [hit.slug for hit in validated.hits] == [slug]
    # Every label in the example decodes — no unknown-expression coercion.
    assert validated.attempted_violations.unknown_expression == 0
    assert validated.hits[0].matched_expressions != ()
    assert validated.advisory_unresolved != ()


def test_the_fat_example_carries_exactly_the_two_wire_fields_per_selection():
    """D8's compact wire: `slug` + `matched`, and no reinstated `evidence` field."""
    document = json.loads(_schema_example(load_template("fat").system))
    assert set(document) == {"selections", "unresolved"}
    assert set(document["selections"][0]) == {"slug", "matched"}


def test_the_fat_example_addresses_expressions_by_LETTER_label():
    """D11: every identifier on the wire is a verbatim echo of a printed marker,
    so the example must show letters — an integer here would re-open the
    0-vs-1 base ambiguity the decision removed."""
    document = json.loads(_schema_example(load_template("fat").system))
    labels = set(expression_labels(10))
    shown = set(document["selections"][0]["matched"]) | set(document["unresolved"])
    assert shown and shown <= labels


def test_the_thin_schema_example_is_accepted_by_the_REAL_thin_validator():
    example = _schema_example(load_template("thin").system)
    document = json.loads(example)
    assert set(document) == {"retained"}
    slugs = document["retained"]
    space = tuple(SpaceEntity(slug=s, title=s, page_type="concept") for s in slugs)

    retained, violations = validate_thin_retention(slugs, space=space, cap=M)
    assert retained == tuple(slugs)
    assert violations.foreign_slug == 0 and violations.malformed_entry == 0
    assert violations.duplicate_slug == 0


@pytest.mark.parametrize("stage", STAGES)
def test_the_rendered_prompt_contains_the_literal_word_JSON(stage):
    """openai-compat 400s on `response_format: {"type": "json_object"}` unless the
    word appears in the messages — asserted, never trusted. It lives in the
    SYSTEM half, which counts, and this pins that it stays somewhere."""
    messages = _render(stage, evidence="e", query="q")
    assert "JSON" in messages.system + messages.user


@pytest.mark.parametrize("stage", STAGES)
def test_the_system_block_states_instruction_precedence(stage):
    """P10's mechanics (spec §2.1): the precedence clause must name BOTH untrusted
    blocks — the query-side half is opus5 F5b and is easy to lose in an edit."""
    system = load_template(stage).system
    assert "EVIDENCE or QUERY" in system
    assert "never a directive" in system


def test_the_fat_prompt_renders_the_result_cap_it_will_be_measured_against():
    user = render_fat_messages(evidence="e", query="q", max_results=7).user
    assert "7" in user
    assert str(MAX_RESULTS) in render_fat_messages(
        evidence="e", query="q", max_results=MAX_RESULTS
    ).user


def test_the_thin_prompt_renders_the_retention_cap_and_defaults_to_M():
    assert str(M) in render_thin_messages(evidence="e", query="q").user
    assert "42" in render_thin_messages(evidence="e", query="q", retention_cap=42).user


# ---------------------------------------------------------------------------
# the SYSTEM_TEMPLATE_BUDGET_BYTES obligation (constants.py:170-176)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", STAGES)
def test_template_overhead_fits_the_declared_reserve(stage):
    """What converts `SYSTEM_TEMPLATE_BUDGET_BYTES` from a declared reserve into a
    measurement. Bytes, not characters — this prose is em-dash-dense and an
    em-dash is 3 bytes.

    The **fat** case is the normative one: `fat_worst_case_request_bytes()` is the
    constant's only consumer, and it is fat's static guarantee that rests on it.
    Thin is budgeted by estimate with a typed `budget_estimation_miss`, so thin's
    assertion is a bonus rather than a proof — but an overrun there is still a
    finding for the owner, not grounds to widen a ratified figure.
    """
    measured = template_overhead_bytes(stage)
    assert measured <= SYSTEM_TEMPLATE_BUDGET_BYTES, (
        f"{stage} template overhead {measured} B exceeds the declared "
        f"{SYSTEM_TEMPLATE_BUDGET_BYTES} B — raising the constant is a blueprint "
        "v0.15 amendment, not a test fix"
    )


@pytest.mark.parametrize("stage", STAGES)
def test_template_overhead_is_measured_with_the_WIDEST_cap_value(stage):
    """The figure has to be the stage's maximum, not a sample: a 2-digit
    `max_results` must not understate a 3-digit retention cap."""
    narrow = (
        render_thin_messages(evidence="", query="", retention_cap=1)
        if stage == "thin"
        else render_fat_messages(evidence="", query="", max_results=1)
    )
    assert template_overhead_bytes(stage) >= len(narrow.system.encode()) + len(
        narrow.user.encode()
    )


def test_overhead_is_measured_in_BYTES_not_characters(monkeypatch, tmp_path):
    """Stated over a synthetic template rather than the real one so the assertion
    has no premise about today's prose. It is not hypothetical, though: the thin
    template already carries an em-dash, and the whole budget is a byte budget."""
    (tmp_path / "selector_thin_v1.txt").write_text(
        "em—dash\n<<<USER>>>\n{{EVIDENCE}}{{RETENTION_CAP}}{{QUERY}}\n", encoding="utf-8"
    )
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    # "em—dash" = 7 characters, 9 bytes; the wrapper renders to "100" = 3 bytes.
    assert template_overhead_bytes("thin") == 12


def test_the_fat_stage_2_bound_holds_with_the_MEASURED_template():
    """Blueprint §11's P2 row: fat's worst case stops being part-declared.

    Real worst case = M x the policy-v2 block ceiling + the query ceiling + the
    measured wrapper; `tokens_lte_bytes` turns bytes into a token bound, and the
    provider-total reserved output is added on top.
    """
    real = (
        M * EXCERPT_BLOCK_CEILING_BYTES
        + QUERY_BLOCK_CEILING_BYTES
        + template_overhead_bytes("fat")
    )
    assert real <= fat_worst_case_request_bytes()
    total = worst_case_input_tokens(real) + reserved_output_tokens("fat")
    assert total <= fat_static_guarantee_tokens() < SMALLEST_POOL_BUDGET_TOKENS


# ---------------------------------------------------------------------------
# packaging + installed-layout access (blueprint §1)
# ---------------------------------------------------------------------------


def test_package_data_declares_every_non_python_file_the_loader_opens():
    """Derived from the DECLARATION, not from a copy of it: the globs in
    `[tool.setuptools.package-data]` are expanded against the package directory
    and must cover both templates. This is the half that catches a new prompt
    file added without a packaging update."""
    config = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    globs = config["tool"]["setuptools"]["package-data"]["kdb_search"]
    package_dir = _REPO_ROOT / "kdb_search"
    declared = {p.relative_to(package_dir).as_posix() for g in globs for p in package_dir.glob(g)}
    assert {f"prompts/{name}" for name in prompts._FILENAMES.values()} <= declared


def test_templates_load_with_the_working_directory_OUTSIDE_the_repo(tmp_path):
    """The property a wheel install actually exercises: resolution is relative to
    the module, never to cwd or a repo-relative path.

    A true built-wheel test is not available offline — this `.venv` has no
    `setuptools`, `build` or `wheel`, so building one needs a network install.
    Recorded rather than substituted silently; the packaging DECLARATION is
    covered by the test above, and the resolution behaviour by this one.
    """
    script = (
        "from kdb_search.prompts import load_template, template_overhead_bytes;"
        "t = load_template('fat');"
        "print(t.ref.sha256);"
        "print(template_overhead_bytes('fat'))"
    )
    out = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={"PYTHONPATH": str(_REPO_ROOT), "PATH": "", "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    sha, overhead = out.stdout.split()
    assert sha == load_template("fat").ref.sha256
    assert int(overhead) == template_overhead_bytes("fat")


def test_git_commit_degrades_to_unknown_when_git_is_unavailable(tmp_path):
    """The installed-wheel case: no `.git`, often no `git` binary. `PromptRef`
    must still be constructible — content fidelity rests on the sha256, and
    `git_commit` is provenance colour."""
    out = subprocess.run(
        [sys.executable, "-c", "from kdb_search.prompts import load_template;"
         "print(load_template('thin').ref.git_commit)"],
        cwd=tmp_path,
        env={"PYTHONPATH": str(_REPO_ROOT), "PATH": "", "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "unknown"
