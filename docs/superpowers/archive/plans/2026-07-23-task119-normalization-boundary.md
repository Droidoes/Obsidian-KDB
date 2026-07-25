# Task #119 — Pass-2 Normalization Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the ratified proposal → canonical normalization boundary in Pass-2 (D-119): a discriminated proposal schema + typed bridge so the summary slug's raw value never rejects/retries, while canonical strictness guards Python's work.

**Architecture:** Per blueprint **v0.4** (`docs/superpowers/archive/specs/2026-07-23-task119-normalization-boundary-blueprint.md` — **v0.4 RATIFIED by Joseph 2026-07-23**): prompt-facing **proposal schema** (summary: no `slug`, stray tolerated; concept/article: `slug` string 1–512) → **typed bridge** (`compiler/proposal_bridge.py`: count → typed pure coercion → stamp → response-local reference policy → canonical self-check + conservation invariant) → **unchanged canonical validation shape** → existing downstream untouched.

**Tech Stack:** Python 3.10+, `jsonschema` (Draft202012), pytest. Run tests as `.venv/bin/python -m pytest` (bare `pytest` is the broken system install; run bare with no extra `-q` for counts — addopts already carries `-q`).

## Global Constraints

- **Governing rule (ratified):** reject ambiguity, not harmless representational differences; normalize only by deterministic authority (role / provenance / registry / context; never string similarity).
- The summary slug's raw value — absent, malformed, non-string, deviating — **never rejects, never retries** (D-119).
- Alias-ledger resolution stays **exclusively** in `canonicalize`; the bridge never touches the ledger (R6 F3).
- `final_status` truth table (§3.5): summary stamping / stray-ignoring **never** set `slug_coerced` and never change `final_status`; only concept/article form coercion sets `slug_coerced`.
- Everything below the bridge seam is untouched: `CompiledSource` build, `validate_compile_result`, `canonicalize`, post-canon invariant, `page_writer`, intake, manifest, Pass-1, KPI definitions.
- Live API runs happen **only** in Phase 5 (Joseph-gated).
- Commits: Conventional Commits with task refs (e.g. `feat(compiler): #119 — …`); every phase gate = full suite green. **Commit gate (Joseph, per AGENTS.md): explicit approval before EVERY commit and again before any merge to `main` — the plan pauses at each gate; no commit is pre-authorized by this plan (Codex plan-review F3).**
- Code anchor: `f8c9ad8`. Branch: `feat/119-normalization-boundary` (create at execution start).

---

## Phase 0 — fixtures + audit lock

### Task 0.1: Bridge regression corpus

**Files:**
- Create: `compiler/tests/fixtures/proposal_bridge/cases.json`
- Test: `compiler/tests/test_proposal_bridge_corpus.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `load_cases() -> list[dict]` (used by Tasks 2.x); each case: `{id, source_id, proposal, expect: {kind: "success"|"reject", reject_class?, summary_slug?, decisions_include?, pages_preserved?, body_preserved?}}`.

- [ ] **Step 1: Write the corpus** — `compiler/tests/fixtures/proposal_bridge/cases.json`:

```json
[
  {"id": "phase5-gemini31-positive", "source_id": "KDB/raw/GraphRAG for Adaptive KB - Gemini3.1.md",
   "proposal": {"pages": [
     {"page_type": "summary", "title": "GraphRAG for Adaptive KB", "body": "GraphRAG adapts knowledge bases; see [[graphrag]]."},
     {"page_type": "concept", "slug": "graphrag", "title": "GraphRAG", "body": "GraphRAG overview. Links to [[unregistered-concept]]."}]},
   "expect": {"kind": "success", "summary_slug": "summary-graphrag-for-adaptive-kb-gemini3-1",
              "decisions_include": ["summary_identity_stamp"], "body_preserved": ["[[unregistered-concept]]"]}},
  {"id": "phase5-whats-positive", "source_id": "KDB/raw/what's React and Tailwind.md",
   "proposal": {"pages": [
     {"page_type": "summary", "title": "What's React and Tailwind", "body": "React + Tailwind notes; see [[react]]."},
     {"page_type": "concept", "slug": "react", "title": "React", "body": "React overview."}]},
   "expect": {"kind": "success", "summary_slug": "summary-what-s-react-and-tailwind",
              "decisions_include": ["summary_identity_stamp"]}},
  {"id": "stray-slug-deviating", "source_id": "KDB/raw/GraphRAG for Adaptive KB - Gemini3.1.md",
   "proposal": {"pages": [
     {"page_type": "summary", "slug": "summary-graphrag-for-adaptive-kb-gemini31", "title": "T", "body": "B."}]},
   "expect": {"kind": "success", "summary_slug": "summary-graphrag-for-adaptive-kb-gemini3-1",
              "decisions_include": ["summary_slug_ignored", "summary_identity_stamp"]}},
  {"id": "stray-slug-malformed", "source_id": "KDB/raw/x.md",
   "proposal": {"pages": [{"page_type": "summary", "slug": "SUMMARY--X", "title": "T", "body": "B."}]},
   "expect": {"kind": "success", "summary_slug": "summary-x", "decisions_include": ["summary_slug_ignored"]}},
  {"id": "stray-slug-nonstring", "source_id": "KDB/raw/x.md",
   "proposal": {"pages": [{"page_type": "summary", "slug": {"unexpected": "object"}, "title": "T", "body": "B."}]},
   "expect": {"kind": "success", "summary_slug": "summary-x", "decisions_include": ["summary_slug_ignored"]}},
  {"id": "raw-length-collapsible", "source_id": "KDB/raw/x.md",
   "proposal": {"pages": [
     {"page_type": "summary", "title": "T", "body": "See [[Alpha------------------------------------------------------------------------------------------------------------------------Beta]]."},
     {"page_type": "concept", "slug": "Alpha------------------------------------------------------------------------------------------------------------------------Beta", "title": "AB", "body": "AB."}]},
   "expect": {"kind": "success", "decisions_include": ["slug_form_coercion", "body_reference_rewrite"]}},
  {"id": "body-only-token-preserved", "source_id": "KDB/raw/x.md",
   "proposal": {"pages": [
     {"page_type": "summary", "title": "T", "body": "Ticker [[AAPL]] today and [[Foo--Bar]]."},
     {"page_type": "concept", "slug": "real-page", "title": "RP", "body": "RP."}]},
   "expect": {"kind": "success", "body_preserved": ["[[AAPL]]", "[[Foo--Bar]]"]}},
  {"id": "alias-token-preserved-for-canonicalize", "source_id": "KDB/raw/x.md",
   "proposal": {"pages": [
     {"page_type": "summary", "title": "T", "body": "Alias [[apple-inc]] noted."},
     {"page_type": "concept", "slug": "real-page", "title": "RP", "body": "RP."}]},
   "expect": {"kind": "success", "body_preserved": ["[[apple-inc]]"]}},
  {"id": "page-mapped-rewrite", "source_id": "KDB/raw/x.md",
   "proposal": {"pages": [
     {"page_type": "summary", "title": "T", "body": "See [[Foo--Bar#Sec|the alias]] and [[Foo Bar]]."},
     {"page_type": "concept", "slug": "Foo--Bar", "title": "FB", "body": "FB."}]},
   "expect": {"kind": "success", "decisions_include": ["slug_form_coercion", "body_reference_rewrite"],
              "body_preserved": ["[[Foo Bar]]"]}},
  {"id": "no-summary", "source_id": "KDB/raw/x.md",
   "proposal": {"pages": [{"page_type": "concept", "slug": "a", "title": "T", "body": "B."}]},
   "expect": {"kind": "reject", "reject_class": "no_summary"}},
  {"id": "two-summaries", "source_id": "KDB/raw/x.md",
   "proposal": {"pages": [
     {"page_type": "summary", "title": "T1", "body": "B."},
     {"page_type": "summary", "title": "T2", "body": "B."}]},
   "expect": {"kind": "reject", "reject_class": "multiple_summaries"}},
  {"id": "concept-slug-collapse-collision", "source_id": "KDB/raw/x.md",
   "proposal": {"pages": [
     {"page_type": "summary", "title": "T", "body": "B."},
     {"page_type": "concept", "slug": "Foo--Bar", "title": "A", "body": "B."},
     {"page_type": "concept", "slug": "foo-bar", "title": "C", "body": "B."}]},
   "expect": {"kind": "reject", "reject_class": "slug_collision"}},
  {"id": "duplicate-page-slugs", "source_id": "KDB/raw/x.md",
   "proposal": {"pages": [
     {"page_type": "summary", "title": "T", "body": "B."},
     {"page_type": "concept", "slug": "dup", "title": "A", "body": "B."},
     {"page_type": "article", "slug": "dup", "title": "C", "body": "B."}]},
   "expect": {"kind": "reject", "reject_class": "slug_collision"}},
  {"id": "derived-slug-collision", "source_id": "KDB/raw/x.md",
   "proposal": {"pages": [
     {"page_type": "summary", "title": "T", "body": "B."},
     {"page_type": "concept", "slug": "summary-x", "title": "A", "body": "B."}]},
   "expect": {"kind": "reject", "reject_class": "slug_collision"}},
  {"id": "uncoercible-slug", "source_id": "KDB/raw/x.md",
   "proposal": {"pages": [
     {"page_type": "summary", "title": "T", "body": "B."},
     {"page_type": "concept", "slug": "Foo Bar", "title": "A", "body": "B."}]},
   "expect": {"kind": "reject", "reject_class": "uncoercible_slug"}}
]
```

- [ ] **Step 2: Write the failing corpus-integrity test** — `compiler/tests/test_proposal_bridge_corpus.py`:

```python
"""Corpus integrity for the #119 bridge regression corpus."""
import json
from pathlib import Path

import pytest

from compiler.summary_slug import expected_summary_slug

CORPUS = Path(__file__).parent / "fixtures" / "proposal_bridge" / "cases.json"


def load_cases() -> list[dict]:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def test_corpus_loads_and_ids_unique():
    cases = load_cases()
    assert len(cases) >= 14
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))


def test_expected_summary_slugs_match_derivation():
    for c in load_cases():
        exp = c["expect"].get("summary_slug")
        if exp is not None:
            assert exp == expected_summary_slug(c["source_id"]), c["id"]


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
def test_case_shape(case):
    assert isinstance(case["proposal"]["pages"], list) and case["proposal"]["pages"]
    assert case["expect"]["kind"] in ("success", "reject")
    if case["expect"]["kind"] == "reject":
        assert "reject_class" in case["expect"]
```

- [ ] **Step 3: Run to verify it passes**

Run: `.venv/bin/python -m pytest compiler/tests/test_proposal_bridge_corpus.py`
Expected: PASS (3 tests)

- [ ] **Step 4: Commit**

```bash
git add compiler/tests/fixtures/proposal_bridge/cases.json compiler/tests/test_proposal_bridge_corpus.py
git commit -m "test(compiler): #119 Phase 0 — bridge regression corpus (Phase-5 positives + stray/collision negatives; REWRITE_AMBIGUITY removed from the contract per Codex R8 F3 — no fixture exists by design)"
```

---

## Phase 1 — proposal schema + re-role + CLI routing

### Task 1.1: Proposal schema + validator

**Files:**
- Create: `compiler/schemas/proposal_response.schema.json`
- Create: `compiler/validate_proposal_response.py`
- Test: `compiler/tests/test_validate_proposal_response.py`

**Interfaces:**
- Produces: `compiler.validate_proposal_response.validate(payload: Any) -> list[str]` — `[]` iff structurally sufficient. Consumed by Tasks 3.1, 4.1.

- [ ] **Step 1: Write the schema** — `compiler/schemas/proposal_response.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://obsidian-kdb.local/schemas/proposal_response.schema.json",
  "title": "KDB Pass-2 Proposal Response (per-call model output, pre-normalization)",
  "description": "The PROPOSAL contract (prompt 4.0.0+): structural sufficiency only. Python's normalization bridge converts a proposal to the canonical contract (compiled_source_response.schema.json). Summary pages carry no slug — Python owns summary identity; a stray slug is tolerated and dropped with telemetry. Concept/article pages require slug; slug FORM is the bridge's job, not this schema's.",
  "type": "object",
  "additionalProperties": false,
  "required": ["pages"],
  "properties": {
    "pages": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/pageProposal" }
    },
    "compilation_notes": {
      "type": "array",
      "description": "Optional free-text notes about this compile. Pure prose for the operator's eye; Python never acts on these.",
      "items": { "type": "string" }
    }
  },
  "$defs": {
    "pageProposal": {
      "type": "object",
      "additionalProperties": false,
      "required": ["page_type", "title", "body"],
      "properties": {
        "page_type": { "type": "string", "enum": ["summary", "concept", "article"] },
        "title": { "type": "string", "minLength": 1, "maxLength": 200 },
        "body": { "type": "string", "minLength": 1 },
        "slug": {
          "description": "concept/article: REQUIRED string (1-512, defensive raw cap — canonical 120 enforced post-coercion). summary: IGNORED — any value tolerated, dropped by the bridge with telemetry."
        }
      },
      "allOf": [
        {
          "if": {
            "properties": { "page_type": { "const": "summary" } },
            "required": ["page_type"]
          },
          "then": true,
          "else": {
            "required": ["slug"],
            "properties": {
              "slug": { "type": "string", "minLength": 1, "maxLength": 512 }
            }
          }
        }
      ]
    }
  }
}
```

- [ ] **Step 2: Write the validator** — `compiler/validate_proposal_response.py`:

```python
"""validate_proposal_response — proposal-schema gate (#119, D-119).

Structural sufficiency for the per-source PROPOSAL (prompt 4.0.0+), applied
to the recovered parse BEFORE the normalization bridge. A violation here is
`structural_insufficiency` (retriable once). Semantic classes (summary count,
collisions, coercibility) are the bridge's, not this module's.
"""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "proposal_response.schema.json"


@cache
def _validator() -> Draft202012Validator:
    with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(payload: Any) -> list[str]:
    """Proposal-schema validation. Returns [] iff structurally sufficient.

    Errors formatted as '[<json_path>] <message>' matching
    validate_compile_result's convention.
    """
    return [
        f"[{err.json_path}] {err.message}"
        for err in _validator().iter_errors(payload)
    ]
```

- [ ] **Step 3: Write the failing test matrix** — `compiler/tests/test_validate_proposal_response.py`:

```python
"""Proposal-schema matrix (#119): per-variant structural sufficiency."""
from compiler.validate_proposal_response import validate


def _page(page_type, title="T", body="B.", **kw):
    p = {"page_type": page_type, "title": title, "body": body}
    p.update(kw)
    return p


def test_summary_without_slug_valid():
    assert validate({"pages": [_page("summary")]}) == []


def test_summary_with_stray_string_slug_valid():
    assert validate({"pages": [_page("summary", slug="anything-goes")]}) == []


def test_summary_with_stray_nonstring_slug_valid():
    assert validate({"pages": [_page("summary", slug={"unexpected": "object"})]}) == []


def test_concept_without_slug_invalid():
    errs = validate({"pages": [_page("concept")]})
    assert errs and "slug" in errs[0]


def test_concept_string_slug_valid():
    assert validate({"pages": [_page("concept", slug="Foo--Bar")]}) == []


def test_concept_nonstring_slug_invalid():
    errs = validate({"pages": [_page("concept", slug=42)]})
    assert errs


def test_concept_slug_over_512_invalid():
    errs = validate({"pages": [_page("concept", slug="a" * 513)]})
    assert errs


def test_bad_page_type_invalid():
    errs = validate({"pages": [_page("Summary")]})
    assert errs


def test_missing_body_invalid():
    p = _page("summary")
    del p["body"]
    errs = validate({"pages": [p]})
    assert errs


def test_undeclared_field_invalid():
    errs = validate({"pages": [_page("summary", confidence="high")]})
    assert errs


def test_empty_pages_invalid():
    assert validate({"pages": []})


def test_root_not_object_invalid():
    assert validate([1, 2])


def test_compilation_notes_shape():
    assert validate({"pages": [_page("summary")], "compilation_notes": ["ok"]}) == []
    assert validate({"pages": [_page("summary")], "compilation_notes": "nope"})
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest compiler/tests/test_validate_proposal_response.py`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add compiler/schemas/proposal_response.schema.json compiler/validate_proposal_response.py compiler/tests/test_validate_proposal_response.py
git commit -m "feat(compiler): #119 Phase 1 — proposal schema (discriminated; stray summary slug tolerated) + validator"
```

### Task 1.2: Canonical artifact re-role + CLI routing + intake docstring

**Files:**
- Modify: `compiler/schemas/compiled_source_response.schema.json` (title/`$id`/description only — validation shape byte-identical)
- Modify: `compiler/validate_source_response.py` (module docstring + CLI routing)
- Modify: `kdb_graph/intake.py:346-348` (stale docstring line)
- Test: `compiler/tests/test_validate_source_response.py`

**Interfaces:**
- Produces: `kdb-validate-response [path.json] [--canonical] [--source-id <id>]` — proposal by default; `--canonical` selects the canonical validation shape (+ `--source-id` semantic mode). CLI consumed by operators; `validate_source_response.validate` unchanged signature.

- [ ] **Step 1: Re-role the canonical schema self-description** — in `compiled_source_response.schema.json` change ONLY lines 3–5:

```json
  "$id": "https://obsidian-kdb.local/schemas/canonical_response.schema.json",
  "title": "KDB Canonical Compile Response (post-normalization canonical contract)",
  "description": "The CANONICAL contract (#119): the only shape allowed to reach canonicalization, persistence, wiki, manifest, run journal, graph. Model output never touches this directly — the proposal bridge's output must satisfy it. Validation shape unchanged since #115; re-roled from per-call model output to canonical artifact.",
```

(the filename stays `compiled_source_response.schema.json`; no other key changes.)

- [ ] **Step 2: Route the CLI** — in `compiler/validate_source_response.py`, update the module docstring + `main` to dispatch:

```python
def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.source_id and not args.canonical:
        print("ERROR: --source-id requires --canonical "
              "(semantic mode lives on the canonical contract)", file=sys.stderr)
        return 2

    try:
        raw = Path(args.path).read_text(encoding="utf-8") if args.path else sys.stdin.read()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.canonical:
        errors = validate(payload)
        if not errors and args.source_id and isinstance(payload, dict):
            from compiler.summary_slug import expected_summary_slug
            from common.paths import PathError
            try:
                expected = expected_summary_slug(args.source_id)
            except PathError as e:
                print(f"ERROR: cannot derive expected summary slug: {e}",
                      file=sys.stderr)
                return 2
            errors.extend(semantic_check(payload, expected_summary_slug=expected))
    else:
        from compiler.validate_proposal_response import validate as validate_proposal
        errors = validate_proposal(payload)

    if errors:
        for msg in errors:
            print(msg)
        return 1
    print("OK")
    return 0
```

and in `_build_parser`, add: `p.add_argument("--canonical", action="store_true", help="Validate against the canonical contract instead of the default proposal contract")`. Update the module docstring's CLI block: `kdb-validate-response [path.json] [--canonical] [--source-id <id>]` — default = proposal; `--canonical` = canonical shape (+ `--source-id` semantic).

- [ ] **Step 3: Fix the stale intake docstring** — `kdb_graph/intake.py` `_replace_outgoing_links` docstring: replace "dangling outgoing_links are a validator catch upstream, not the intake's job." with "dangling targets are KPI-visible (`dangling_link_rate`), not gate-rejected — post-#115 no upstream gate checks body-target existence."

- [ ] **Step 4: Tests** — extend `compiler/tests/test_validate_source_response.py` with CLI routing tests:

```python
def test_cli_default_is_proposal(tmp_path, capsys):
    from compiler.validate_source_response import main
    f = tmp_path / "p.json"
    f.write_text('{"pages": [{"page_type": "summary", "title": "T", "body": "B."}]}')
    assert main([str(f)]) == 0


def test_cli_canonical_requires_summary_slug(tmp_path, capsys):
    from compiler.validate_source_response import main
    f = tmp_path / "p.json"
    f.write_text('{"pages": [{"page_type": "summary", "title": "T", "body": "B."}]}')
    assert main([str(f), "--canonical"]) == 1


def test_cli_canonical_source_id_semantic(tmp_path, capsys):
    from compiler.validate_source_response import main
    f = tmp_path / "p.json"
    f.write_text('{"pages": [{"page_type": "summary", "slug": "summary-x", "title": "T", "body": "B."}]}')
    assert main([str(f), "--canonical", "--source-id", "KDB/raw/x.md"]) == 0


def test_cli_source_id_requires_canonical(tmp_path, capsys):
    from compiler.validate_source_response import main
    f = tmp_path / "p.json"
    f.write_text('{"pages": [{"page_type": "summary", "title": "T", "body": "B."}]}')
    assert main([str(f), "--source-id", "KDB/raw/x.md"]) == 2
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest compiler/tests/test_validate_source_response.py compiler/tests/test_validate_proposal_response.py`
Expected: all PASS (existing + 4 new)

- [ ] **Step 6: Commit**

```bash
git add compiler/schemas/compiled_source_response.schema.json compiler/validate_source_response.py compiler/tests/test_validate_source_response.py kdb_graph/intake.py
git commit -m "refactor(compiler): #119 Phase 1 — canonical schema re-role (shape unchanged) + kdb-validate-response proposal/canonical routing"
```

---

## Phase 2 — the bridge

### Task 2.1: Bridge types + rule 1 (summary count)

**Files:**
- Create: `compiler/proposal_bridge.py`
- Test: `compiler/tests/test_proposal_bridge.py`

**Interfaces:**
- Produces (consumed by Tasks 2.2–2.5, 3.1, 4.1):
  - `RejectClass(StrEnum)`: `NO_SUMMARY`, `MULTIPLE_SUMMARIES`, `SLUG_COLLISION`, `UNCOERCIBLE_SLUG` (bridge semantic rejects only — all model-correctable; `STRUCTURAL_INSUFFICIENCY` is the proposal-STAGE class, not a bridge reject, and `REWRITE_AMBIGUITY` is removed as unreachable — Codex R8 F3)
  - `RETRIABLE: frozenset[RejectClass] = frozenset(RejectClass)`
  - `CanonicalInvariantError(Exception)`
  - `NormalizationDecision(NamedTuple)`: `rule, authority, location, raw_type, raw_value, raw_preview, raw_sha256, canonical_value`
  - `BridgeSuccess(NamedTuple)`: `canonical: dict, decisions: list[NormalizationDecision]`
  - `BridgeReject(NamedTuple)`: `reject_class, detail, decisions`; `.retriable -> bool` (derived)
  - `normalize_proposal(parsed: dict, *, source_id: str) -> BridgeSuccess | BridgeReject` — **pure; never mutates `parsed`**

- [ ] **Step 1: Write the failing tests** — `compiler/tests/test_proposal_bridge.py`:

```python
"""The proposal → canonical bridge (#119, D-119)."""
import pytest

from compiler.proposal_bridge import (
    BridgeReject, BridgeSuccess, CanonicalInvariantError, RejectClass,
    normalize_proposal,
)


def _summary(**kw):
    p = {"page_type": "summary", "title": "T", "body": "B."}
    p.update(kw)
    return p


def test_no_summary_rejected():
    r = normalize_proposal({"pages": [{"page_type": "concept", "slug": "a",
                                      "title": "T", "body": "B."}]},
                           source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeReject) and r.reject_class == RejectClass.NO_SUMMARY
    assert r.retriable


def test_multiple_summaries_rejected():
    r = normalize_proposal({"pages": [_summary(), _summary()]},
                           source_id="KDB/raw/x.md")
    assert (isinstance(r, BridgeReject)
            and r.reject_class == RejectClass.MULTIPLE_SUMMARIES)


def test_summary_stamped_and_raw_preserved():
    proposal = {"pages": [_summary()]}
    r = normalize_proposal(proposal, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["pages"][0]["slug"] == "summary-x"
    assert "slug" not in proposal["pages"][0]  # purity: raw untouched
    assert any(d.rule == "summary_identity_stamp" for d in r.decisions)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest compiler/tests/test_proposal_bridge.py`
Expected: FAIL — `ModuleNotFoundError: compiler.proposal_bridge`

- [ ] **Step 3: Implement the bridge skeleton + rule 1** — `compiler/proposal_bridge.py`:

```python
"""proposal_bridge — the proposal → canonical normalization boundary (#119, D-119).

Pure: the raw proposal is never mutated (raw evidence is telemetry's point).
Rules in order (blueprint §5): summary count → typed pure page-slug coercion →
summary identity stamping → response-local body-reference policy → canonical
self-check (shape + summary invariant + conservation).

The alias ledger is NOT an authority here — alias resolution stays exclusively
in canonicalize (R6 F3). No string similarity anywhere.
"""
from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any, NamedTuple

from common.paths import collapse_slug
from compiler import validate_source_response
from compiler.summary_slug import expected_summary_slug


class RejectClass(StrEnum):
    """Bridge semantic reject classes — ALL model-correctable (retriable).
    Codex R8 F3: STRUCTURAL_INSUFFICIENCY is not here — it is the
    proposal-STAGE failure class (schema gate, before the bridge), not a
    bridge reject. REWRITE_AMBIGUITY is removed — under response-local
    page-map rewriting, exact mappings are unique and collisions reject
    BEFORE rewriting, so no ambiguity can reach the rewrite stage (ledger
    ambiguity stays fail-closed in canonicalize)."""
    NO_SUMMARY = "no_summary"
    MULTIPLE_SUMMARIES = "multiple_summaries"
    SLUG_COLLISION = "slug_collision"
    UNCOERCIBLE_SLUG = "uncoercible_slug"


RETRIABLE: frozenset[RejectClass] = frozenset(RejectClass)


class CanonicalInvariantError(Exception):
    """Bridge/canonical self-check failure — a SYSTEM bug class. Never a model
    failure, never retried. Raised, not returned."""


class NormalizationDecision(NamedTuple):
    rule: str
    authority: str
    location: str
    raw_type: str
    raw_value: str | None
    raw_preview: str | None
    raw_sha256: str | None
    canonical_value: str | None


class BridgeSuccess(NamedTuple):
    canonical: dict
    decisions: list[NormalizationDecision]


class BridgeReject(NamedTuple):
    reject_class: RejectClass
    detail: str
    decisions: list[NormalizationDecision]

    @property
    def retriable(self) -> bool:
        return self.reject_class in RETRIABLE


BridgeResult = BridgeSuccess | BridgeReject


_RAW_CAP = 120
_JSON_TYPE_NAMES = {
    dict: "object", list: "array", str: "string",
    bool: "boolean", int: "number", float: "number", type(None): "null",
}


def _decision(rule: str, authority: str, location: str,
              raw: Any, canonical: Any) -> NormalizationDecision:
    """Bounded capture (Codex plan-review F7): JSON type names; strings >120
    chars and all non-strings degrade to preview + stable hash so the
    always-on decision list stays small."""
    raw_type = _JSON_TYPE_NAMES.get(type(raw), type(raw).__name__)
    if raw is None:
        raw_value, raw_preview, raw_sha = None, None, None
    elif isinstance(raw, str) and len(raw) <= _RAW_CAP:
        raw_value, raw_preview, raw_sha = raw, None, None
    else:
        text = raw if isinstance(raw, str) else json.dumps(
            raw, ensure_ascii=False, sort_keys=True)
        raw_value, raw_preview = None, text[:_RAW_CAP]
        raw_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return NormalizationDecision(
        rule=rule, authority=authority, location=location,
        raw_type=raw_type, raw_value=raw_value,
        raw_preview=raw_preview, raw_sha256=raw_sha,
        canonical_value=canonical if isinstance(canonical, str) else None,
    )


# --- the single source of truth (Codex PR3 F1 + PR4 F1): the lossless typed plan ---
ABSENT = object()   # slug-slot sentinel: distinguishes "no slug key" from JSON null


class OpKind(StrEnum):
    SLUG_FORM_COERCION = "slug_form_coercion"
    SUMMARY_IDENTITY_RESOLUTION = "summary_identity_resolution"  # stray-drop + stamp as ONE location op
    BODY_REFERENCE_REWRITE = "body_reference_rewrite"


class NormalizationOp(NamedTuple):
    """ONE lossless, exactly-located normalization step. The bridge is
    PLAN-APPLY-VERIFY (Codex PR4 F1): rules CONSTRUCT the op list and never
    mutate; `_apply_normalization_plan` constructs the canonical object FROM
    the ops (the only mutation path, raising on spurious ops); and
    `_check_conservation` independently diffs raw vs canonical and verifies a
    BIJECTION — every difference consumes exactly one op, every op is
    consumed. `raw`/`canonical` are NEVER bounded (bounded telemetry is
    derived via `_decisions_from_ops`)."""
    kind: OpKind
    authority: str
    page_index: int
    field: str            # "slug" | "body"
    occurrence: int       # body: 0-based occurrence of the raw token in the code-aware token scan of that page's body
    raw: Any              # ABSENT sentinel when the slug key is absent
    canonical: Any


def _decisions_from_ops(ops: list[NormalizationOp]) -> list[NormalizationDecision]:
    """Bounded telemetry projection (aggregate-capped at the compile_one
    boundary via `_cap_decisions`). One resolution op derives an ignore
    decision (when a stray existed) + a stamp decision."""
    out: list[NormalizationDecision] = []
    occurrence: dict[int, int] = {}
    for op in ops:
        if op.kind is OpKind.BODY_REFERENCE_REWRITE:
            occurrence[op.page_index] = occurrence.get(op.page_index, 0) + 1
            out.append(_decision(
                rule="body_reference_rewrite", authority=op.authority,
                location=f"pages[{op.page_index}].body#{occurrence[op.page_index]}",
                raw=op.raw, canonical=op.canonical))
        elif op.kind is OpKind.SLUG_FORM_COERCION:
            out.append(_decision(
                rule="slug_form_coercion", authority=op.authority,
                location=f"pages[{op.page_index}].slug",
                raw=op.raw, canonical=op.canonical))
        else:  # SUMMARY_IDENTITY_RESOLUTION
            if op.raw is not ABSENT:
                out.append(_decision(
                    rule="summary_slug_ignored", authority=op.authority,
                    location=f"pages[{op.page_index}].slug",
                    raw=op.raw, canonical=None))
            out.append(_decision(
                rule="summary_identity_stamp", authority=op.authority,
                location=f"pages[{op.page_index}].slug",
                raw=None, canonical=op.canonical))
    return out


_DECISIONS_CAP = 50


def _cap_decisions(decisions: list[NormalizationDecision]) -> tuple[list[dict], int, str | None]:
    """Aggregate telemetry bound (Codex PR4 F6): ≤50 located samples + total
    count + overflow digest of the truncated tail — the always-on persisted
    list stays small no matter how many body-link occurrences fire."""
    dicts = [d._asdict() for d in decisions]
    if len(dicts) <= _DECISIONS_CAP:
        return dicts, len(dicts), None
    tail = json.dumps(dicts[_DECISIONS_CAP:], ensure_ascii=False, sort_keys=True)
    return dicts[:_DECISIONS_CAP], len(dicts), hashlib.sha256(tail.encode("utf-8")).hexdigest()


def normalize_proposal(parsed: dict, *, source_id: str) -> BridgeResult:
    ops: list[NormalizationOp] = []
    pages = parsed.get("pages") or []

    # --- rule 1: summary count (role authority) ---
    summary_idx = [i for i, p in enumerate(pages)
                   if isinstance(p, dict) and p.get("page_type") == "summary"]
    if not summary_idx:
        return BridgeReject(RejectClass.NO_SUMMARY,
                            "no page with page_type='summary'",
                            _decisions_from_ops(ops))
    if len(summary_idx) > 1:
        return BridgeReject(RejectClass.MULTIPLE_SUMMARIES,
                            f"{len(summary_idx)} pages with page_type='summary'",
                            _decisions_from_ops(ops))

    raise NotImplementedError  # rules 2-5 land in Tasks 2.2-2.5
```

- [ ] **Step 4: Run to verify the two reject tests pass and the success test errors**

Run: `.venv/bin/python -m pytest compiler/tests/test_proposal_bridge.py`
Expected: 2 PASS (`test_no_summary_rejected`, `test_multiple_summaries_rejected`), 1 FAIL/error on `NotImplementedError` for `test_summary_stamped_and_raw_preserved` — acceptable mid-task state; do NOT commit until Task 2.5 completes the module.

(Tasks 2.2–2.5 complete the module; commit once at the end of 2.5 — the module is one deliverable. The corpus test from 0.1 keeps tracking progress.)

### Task 2.2: Rule 2 — typed pure page-slug coercion (+ token machinery)

**Files:**
- Modify: `compiler/proposal_bridge.py`
- Test: `compiler/tests/test_proposal_bridge.py`

**Interfaces:**
- Consumes: `common.paths.collapse_slug(slug: str) -> str | None`.
- Produces: `_rewrite_body(body: str, rename: dict[str, str]) -> tuple[str, list[tuple[str, str]]]` — returns (new body, per-token `(raw, canonical)` rewrites); `_COERCE_WIKILINK_RE`, `_outside_code_spans` (moved from `repair.py`; parity semantics preserved).

- [ ] **Step 1: Add failing tests**

```python
def test_page_slug_coerced_and_body_token_rewritten():
    r = normalize_proposal({"pages": [
        _summary(body="See [[Foo--Bar#Sec|the alias]] and [[Foo Bar]]."),
        {"page_type": "concept", "slug": "Foo--Bar", "title": "FB", "body": "FB."},
    ]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["pages"][1]["slug"] == "foo-bar"
    assert "[[foo-bar#Sec|the alias]]" in r.canonical["pages"][0]["body"]
    assert "[[Foo Bar]]" in r.canonical["pages"][0]["body"]  # uncoercible TOKEN preserved
    assert any(d.rule == "slug_form_coercion" for d in r.decisions)
    assert any(d.rule == "body_reference_rewrite" for d in r.decisions)


def test_body_only_tokens_preserved():
    r = normalize_proposal({"pages": [
        _summary(body="Ticker [[AAPL]] and [[Foo--Bar]] and `[[Code--Span]]`."),
        {"page_type": "concept", "slug": "real-page", "title": "RP", "body": "RP."},
    ]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    body = r.canonical["pages"][0]["body"]
    assert "[[AAPL]]" in body and "[[Foo--Bar]]" in body and "`[[Code--Span]]`" in body
    assert not any(d.rule == "body_reference_rewrite" for d in r.decisions)


def test_uncoercible_page_slug_rejected():
    r = normalize_proposal({"pages": [
        _summary(), {"page_type": "concept", "slug": "Foo Bar", "title": "T", "body": "B."},
    ]}, source_id="KDB/raw/x.md")
    assert (isinstance(r, BridgeReject)
            and r.reject_class == RejectClass.UNCOERCIBLE_SLUG)


def test_collapse_collision_rejected():
    r = normalize_proposal({"pages": [
        _summary(),
        {"page_type": "concept", "slug": "Foo--Bar", "title": "A", "body": "B."},
        {"page_type": "concept", "slug": "foo-bar", "title": "C", "body": "B."},
    ]}, source_id="KDB/raw/x.md")
    assert (isinstance(r, BridgeReject)
            and r.reject_class == RejectClass.SLUG_COLLISION)


def test_duplicate_page_slugs_rejected():
    r = normalize_proposal({"pages": [
        _summary(),
        {"page_type": "concept", "slug": "dup", "title": "A", "body": "B."},
        {"page_type": "article", "slug": "dup", "title": "C", "body": "B."},
    ]}, source_id="KDB/raw/x.md")
    assert (isinstance(r, BridgeReject)
            and r.reject_class == RejectClass.SLUG_COLLISION)
```

- [ ] **Step 2: Implement rule 2 in `normalize_proposal`** (replace the `raise NotImplementedError` as rules accumulate). Add to the module:

```python
# --- token machinery (moved from repair.py; parity semantics preserved) ---
_COERCE_WIKILINK_RE = re.compile(r"(?<!\\)\[\[([^\[\]|#]+?)(#[^\[\]|]*)?(\|[^\[\]]*)?\]\]")
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def _outside_code_spans(text: str) -> list[tuple[bool, str]]:
    parts: list[tuple[bool, str]] = []
    fpos = 0
    for fm in _FENCED_CODE_RE.finditer(text):
        seg = text[fpos:fm.start()]
        ipos = 0
        for im in _INLINE_CODE_RE.finditer(seg):
            parts.append((False, seg[ipos:im.start()]))
            parts.append((True, im.group(0)))
            ipos = im.end()
        parts.append((False, seg[ipos:]))
        parts.append((True, fm.group(0)))
        fpos = fm.end()
    tail = text[fpos:]
    ipos = 0
    for im in _INLINE_CODE_RE.finditer(tail):
        parts.append((False, tail[ipos:im.start()]))
        parts.append((True, im.group(0)))
        ipos = im.end()
    parts.append((False, tail[ipos:]))
    return parts


def _rewrite_body(body: str, rename: dict[str, str]) -> tuple[str, list[tuple[str, str]]]:
    """Rewrite ONLY wikilink targets exactly present in `rename` (raw page
    slugs), outside code spans, preserving #anchor and |display. Returns the
    new body + per-token (raw, canonical) rewrites. Unmapped tokens pass
    through byte-identical."""
    rewrites: list[tuple[str, str]] = []

    def _rw(m: re.Match) -> str:
        tgt, anchor, disp = m.group(1), m.group(2) or "", m.group(3) or ""
        if tgt in rename:
            rewrites.append((tgt, rename[tgt]))
            return f"[[{rename[tgt]}{anchor}{disp}]]"
        return m.group(0)

    return "".join(
        seg if is_code else _COERCE_WIKILINK_RE.sub(_rw, seg)
        for is_code, seg in _outside_code_spans(body)
    ), rewrites
```

and inside `normalize_proposal` after rule 1:

```python
    # --- rule 2: concept/article page-slug coercion (PLAN construction — no mutation) ---
    for i, p in enumerate(pages):
        if p["page_type"] == "summary":
            continue
        raw = p["slug"]
        coerced = collapse_slug(raw)
        if coerced is None:
            return BridgeReject(
                RejectClass.UNCOERCIBLE_SLUG,
                f"pages[{i}].slug {raw!r} cannot be coerced to a valid slug",
                _decisions_from_ops(ops))
        if coerced != raw:
            ops.append(NormalizationOp(OpKind.SLUG_FORM_COERCION,
                                       "form-rule", i, "slug", 0, raw, coerced))

    # collision detection on PLANNED final slugs (post-coercion)
    planned: dict[str, int] = {}
    for i, p in enumerate(pages):
        if p["page_type"] == "summary":
            continue
        final = next((op.canonical for op in ops
                      if op.kind is OpKind.SLUG_FORM_COERCION
                      and op.page_index == i), p["slug"])
        if final in planned:
            return BridgeReject(
                RejectClass.SLUG_COLLISION,
                f"slug {final!r} shared by pages[{planned[final]}] and pages[{i}]",
                _decisions_from_ops(ops))
        planned[final] = i
```

- [ ] **Step 3: Run**

Run: `.venv/bin/python -m pytest compiler/tests/test_proposal_bridge.py -k "coerc or collision or preserved or duplicate"`
Expected: 5 new tests PASS (success-path tests still error on unimplemented rules 3–5)

### Task 2.3: Rule 3 — summary identity stamping (+ stray drop + derived collision)

**Files:**
- Modify: `compiler/proposal_bridge.py`
- Test: `compiler/tests/test_proposal_bridge.py`

- [ ] **Step 1: Add failing tests**

```python
def test_stray_summary_slug_dropped_with_telemetry():
    r = normalize_proposal({"pages": [
        _summary(slug="summary-x-deviant", body="B.")]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["pages"][0]["slug"] == "summary-x"
    ignored = [d for d in r.decisions if d.rule == "summary_slug_ignored"]
    assert ignored and ignored[0].raw_value == "summary-x-deviant"


def test_stray_nonstring_summary_slug_bounded_capture():
    r = normalize_proposal({"pages": [
        _summary(slug={"unexpected": "object"})]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    ignored = [d for d in r.decisions if d.rule == "summary_slug_ignored"][0]
    assert ignored.raw_type == "object"
    assert ignored.raw_value is None
    assert ignored.raw_preview is not None and len(ignored.raw_preview) <= 120
    assert ignored.raw_sha256 is not None


def test_derived_slug_collision_rejected():
    r = normalize_proposal({"pages": [
        _summary(),
        {"page_type": "concept", "slug": "summary-x", "title": "A", "body": "B."},
    ]}, source_id="KDB/raw/x.md")
    assert (isinstance(r, BridgeReject)
            and r.reject_class == RejectClass.SLUG_COLLISION)
```

- [ ] **Step 2: Implement rule 3** — after rule 2's collision detection:

```python
    # --- rule 3: summary identity resolution (role + provenance; always safe) ---
    si = summary_idx[0]
    expected = expected_summary_slug(source_id)
    if expected in planned:
        return BridgeReject(
            RejectClass.SLUG_COLLISION,
            f"derived summary slug {expected!r} collides with pages[{planned[expected]}]",
            _decisions_from_ops(ops))
    stray = pages[si].get("slug", ABSENT)
    ops.append(NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION,
                               "role+source_id", si, "slug", 0, stray, expected))
```

- [ ] **Step 3: Run**

Run: `.venv/bin/python -m pytest compiler/tests/test_proposal_bridge.py -k "stray or stamped or derived"`
Expected: new tests PASS (full success tests still error on rules 4–5)

### Task 2.4: Rule 4 — response-local body-reference policy

**Files:**
- Modify: `compiler/proposal_bridge.py`
- Test: `compiler/tests/test_proposal_bridge.py`

- [ ] **Step 1: Add failing test**

```python
def test_alias_resolvable_token_preserved_for_canonicalize():
    r = normalize_proposal({"pages": [
        _summary(body="Alias [[apple-inc]] noted."),
        {"page_type": "concept", "slug": "real-page", "title": "RP", "body": "RP."},
    ]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert "[[apple-inc]]" in r.canonical["pages"][0]["body"]
```

- [ ] **Step 2: Implement rule 4** — after rule 3:

```python
    # --- rule 4: body-reference policy (response-local ONLY; ledger untouched) ---
    # rename derived from the coercion ops; every mapped token OCCURRENCE gets
    # its own exactly-located op (duplicate occurrences never collapse — PR4 F1)
    rename = {op.raw: op.canonical for op in ops
              if op.kind is OpKind.SLUG_FORM_COERCION}
    if rename:
        for i, p in enumerate(pages):
            body = p.get("body")
            if not isinstance(body, str):
                continue
            for raw_tok, canon_tok in _iter_mapped_tokens(body, rename):
                per_token_n = sum(
                    1 for op in ops
                    if op.kind is OpKind.BODY_REFERENCE_REWRITE
                    and op.page_index == i and op.raw == raw_tok)
                ops.append(NormalizationOp(
                    OpKind.BODY_REFERENCE_REWRITE, "response-local",
                    i, "body", per_token_n, raw_tok, canon_tok))
```

- [ ] **Step 3: Run**

Run: `.venv/bin/python -m pytest compiler/tests/test_proposal_bridge.py -k "alias or rewrite or preserved"`
Expected: PASS (full success tests still error on rule 5)

### Task 2.5: Rule 5 — canonical self-check + conservation invariant; module complete

**Files:**
- Modify: `compiler/proposal_bridge.py`
- Test: `compiler/tests/test_proposal_bridge.py`, `compiler/tests/test_proposal_bridge_corpus.py`

- [ ] **Step 1: Add failing tests**

```python
def test_conservation_pages_notes_prose_preserved():
    proposal = {
        "pages": [
            _summary(body="See [[Foo--Bar]]."),
            {"page_type": "concept", "slug": "Foo--Bar", "title": "FB", "body": "FB."},
        ],
        "compilation_notes": ["thin source"],
    }
    r = normalize_proposal(proposal, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["compilation_notes"] == ["thin source"]
    assert [p["page_type"] for p in r.canonical["pages"]] == ["summary", "concept"]
    assert [p["title"] for p in r.canonical["pages"]] == ["T", "FB"]
    assert r.canonical["pages"][1]["body"] == "FB."


def test_success_for_full_proposal():
    r = normalize_proposal({"pages": [
        _summary(body="See [[foo--bar]]."),
        {"page_type": "concept", "slug": "foo--bar", "title": "FB", "body": "FB."},
    ]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["pages"][0]["slug"] == "summary-x"
    assert r.canonical["pages"][1]["slug"] == "foo-bar"
    assert "[[foo-bar]]" in r.canonical["pages"][0]["body"]


# --- conservation negatives (R7 F5 + Codex PR4 F1 fault injection) ---

from compiler.proposal_bridge import (
    ABSENT, CanonicalInvariantError, NormalizationOp, OpKind,
    _apply_normalization_plan, _check_conservation,
)


def _base_proposal():
    return {"pages": [
        {"page_type": "summary", "title": "T",
         "body": "See [[foo--bar]] and [[foo--bar]] again."},
        {"page_type": "concept", "slug": "foo--bar", "title": "FB", "body": "FB."},
    ], "compilation_notes": ["note one"]}


def _good_canonical():
    return {"pages": [
        {"page_type": "summary", "slug": "summary-x", "title": "T",
         "body": "See [[foo-bar]] and [[foo-bar]] again."},
        {"page_type": "concept", "slug": "foo-bar", "title": "FB", "body": "FB."},
    ], "compilation_notes": ["note one"]}


def _ops():
    return [
        NormalizationOp(OpKind.SLUG_FORM_COERCION, "form-rule", 1, "slug", 0,
                        "foo--bar", "foo-bar"),
        NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION, "role+source_id",
                        0, "slug", 0, ABSENT, "summary-x"),
        NormalizationOp(OpKind.BODY_REFERENCE_REWRITE, "response-local", 0,
                        "body", 0, "foo--bar", "foo-bar"),
        NormalizationOp(OpKind.BODY_REFERENCE_REWRITE, "response-local", 0,
                        "body", 1, "foo--bar", "foo-bar"),
    ]


def test_conservation_clean_diff_passes():
    _check_conservation(_base_proposal(), _good_canonical(), _ops())


def test_conservation_duplicate_occurrences_each_need_their_op():
    """One op can never 'explain' two changed occurrences (PR4 F1)."""
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), _good_canonical(), _ops()[:3])


def test_conservation_detects_dropped_page():
    bad = {"pages": _good_canonical()["pages"][:1],
           "compilation_notes": ["note one"]}
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), bad, _ops())


def test_conservation_detects_notes_loss():
    bad = _good_canonical()
    bad["compilation_notes"] = []
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), bad, _ops())


def test_conservation_detects_title_mutation():
    bad = _good_canonical()
    bad["pages"][1]["title"] = "changed"
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), bad, _ops())


def test_conservation_detects_prose_edit_beyond_tokens():
    bad = _good_canonical()
    bad["pages"][0]["body"] = "Completely rewritten prose."
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), bad, _ops())


def test_conservation_requires_resolution_op_for_summary_change():
    """PR3 F1: a summary edit with no recorded resolution op is a violation."""
    bad_ops = [op for op in _ops()
               if op.kind is not OpKind.SUMMARY_IDENTITY_RESOLUTION]
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), _good_canonical(), bad_ops)


def test_conservation_explicit_null_stray():
    raw = {"pages": [{"page_type": "summary", "slug": None, "title": "T", "body": "B."}]}
    canon = {"pages": [{"page_type": "summary", "slug": "summary-x", "title": "T", "body": "B."}]}
    ops = [NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION,
                           "role+source_id", 0, "slug", 0, None, "summary-x")]
    _check_conservation(raw, canon, ops)


def test_conservation_already_canonical_stray_is_allowed_noop():
    """A stray already equal to the derived slug: no-op op, allowed + telemetered."""
    raw = {"pages": [{"page_type": "summary", "slug": "summary-x", "title": "T", "body": "B."}]}
    canon = {"pages": [{"page_type": "summary", "slug": "summary-x", "title": "T", "body": "B."}]}
    ops = [NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION,
                           "role+source_id", 0, "slug", 0, "summary-x", "summary-x")]
    _check_conservation(raw, canon, ops)


def test_conservation_rejects_unused_op():
    """Every op must be consumed by a real difference."""
    bad_ops = _ops() + [NormalizationOp(
        OpKind.SLUG_FORM_COERCION, "form-rule", 1, "slug", 0, "ghost", "ghost-x")]
    with pytest.raises(CanonicalInvariantError):
        _check_conservation(_base_proposal(), _good_canonical(), bad_ops)


def test_apply_rejects_spurious_op():
    """An op whose raw doesn't match the document at its location raises."""
    with pytest.raises(CanonicalInvariantError):
        _apply_normalization_plan(_base_proposal(), [
            NormalizationOp(OpKind.SLUG_FORM_COERCION, "form-rule", 1,
                            "slug", 0, "wrong-raw", "foo-bar")])


# --- end-to-end duplicate mapped tokens (Codex PR5 F1) ---

def test_normalize_proposal_duplicate_mapped_tokens_end_to_end():
    r = normalize_proposal({"pages": [
        _summary(body="See [[foo--bar]] and [[foo--bar]] again."),
        {"page_type": "concept", "slug": "foo--bar", "title": "FB", "body": "FB."},
    ]}, source_id="KDB/raw/x.md")
    assert isinstance(r, BridgeSuccess)
    assert r.canonical["pages"][0]["body"] == "See [[foo-bar]] and [[foo-bar]] again."
    rewrites = [d for d in r.decisions if d.rule == "body_reference_rewrite"]
    assert len(rewrites) == 2


# --- plan structural validation negatives (Codex PR5 F2) ---

from compiler.proposal_bridge import _validate_plan


def _resolution_op(raw, canon):
    return NormalizationOp(OpKind.SUMMARY_IDENTITY_RESOLUTION,
                           "role+source_id", 0, "slug", 0, raw, canon)


def test_validate_plan_requires_resolution_even_when_noop():
    with pytest.raises(CanonicalInvariantError):
        _validate_plan([], summary_index=0, page_count=1)


def test_validate_plan_rejects_unused_noop_outside_resolution():
    with pytest.raises(CanonicalInvariantError):
        _validate_plan([
            _resolution_op(ABSENT, "summary-x"),
            NormalizationOp(OpKind.SLUG_FORM_COERCION, "form-rule", 1,
                            "slug", 0, "same", "same"),
        ], summary_index=0, page_count=2)


def test_validate_plan_rejects_wrong_kind_field_combo():
    with pytest.raises(CanonicalInvariantError):
        _validate_plan([
            _resolution_op(ABSENT, "summary-x"),
            NormalizationOp(OpKind.SLUG_FORM_COERCION, "form-rule", 1,
                            "body", 0, "a", "b"),
        ], summary_index=0, page_count=2)


def test_validate_plan_rejects_wrong_authority():
    with pytest.raises(CanonicalInvariantError):
        _validate_plan([
            _resolution_op(ABSENT, "summary-x"),
            NormalizationOp(OpKind.BODY_REFERENCE_REWRITE, "similarity", 0,
                            "body", 0, "a", "b"),
        ], summary_index=0, page_count=1)


def test_validate_plan_rejects_unknown_field():
    with pytest.raises(CanonicalInvariantError):
        _validate_plan([
            _resolution_op(ABSENT, "summary-x"),
            NormalizationOp(OpKind.SLUG_FORM_COERCION, "form-rule", 1,
                            "title", 0, "a", "b"),
        ], summary_index=0, page_count=2)
```

- [ ] **Step 2: Implement rule 5** — end of `normalize_proposal`:

```python
    # --- rule 5: plan VALIDATED → canonical = plan APPLIED → shape + identity + bijection ---
    _validate_plan(ops, summary_index=si, page_count=len(pages))
    canonical = _apply_normalization_plan(parsed, ops)
    errors = validate_source_response.validate(canonical)
    if errors:
        raise CanonicalInvariantError(f"canonical shape: {errors[0]}")
    summaries = [p for p in canonical["pages"] if p["page_type"] == "summary"]
    if len(summaries) != 1 or summaries[0]["slug"] != expected:
        raise CanonicalInvariantError(
            f"summary invariant: expected exactly one summary with slug "
            f"{expected!r}, found {[p.get('slug') for p in summaries]}")
    _check_conservation(parsed, canonical, ops)
    return BridgeSuccess(canonical=canonical,
                         decisions=_decisions_from_ops(ops))
```

plus the apply/conservation machinery at module level:

```python
def _apply_normalization_plan(parsed: dict, ops: list[NormalizationOp]) -> dict:
    """Construct the canonical object FROM the ops — the ONLY mutation path.
    Slug ops apply with a raw-match check; ALL of a page's body ops apply in
    ONE scan against the ORIGINAL body (Codex PR5 F1 — sequential
    nth-occurrence rewrites on a mutating body renumber raw occurrences and
    break duplicates). Raises CanonicalInvariantError on spurious ops,
    missing occurrences, or unknown fields."""
    canonical: dict[str, Any] = {"pages": [dict(p) for p in parsed["pages"]]}
    if "compilation_notes" in parsed:
        canonical["compilation_notes"] = parsed["compilation_notes"]
    body_ops: dict[int, list[NormalizationOp]] = {}
    for op in ops:
        page = canonical["pages"][op.page_index]
        if op.field == "slug":
            current = page.get("slug", ABSENT)
            if current != op.raw:
                raise CanonicalInvariantError(
                    f"spurious op at pages[{op.page_index}].slug: "
                    f"op raw {op.raw!r} != current {current!r}")
            page["slug"] = op.canonical
        elif op.field == "body":
            body_ops.setdefault(op.page_index, []).append(op)
        else:
            raise CanonicalInvariantError(f"unknown op field: {op.field!r}")
    for i, page_ops in body_ops.items():
        body = canonical["pages"][i].get("body")
        if not isinstance(body, str):
            raise CanonicalInvariantError(
                f"body op on pages[{i}] without a string body")
        canonical["pages"][i]["body"] = _apply_body_ops(body, page_ops)
    return canonical


def _apply_body_ops(body: str, page_ops: list[NormalizationOp]) -> str:
    """Apply ALL of one page's body ops in a single code-aware scan against
    the ORIGINAL body. Each raw token's n-th occurrence is rewritten per the
    op with that occurrence; an op whose occurrence never appears raises."""
    by_token: dict[str, dict[int, str]] = {}
    for op in page_ops:
        by_token.setdefault(op.raw, {})[op.occurrence] = op.canonical
    counts: dict[str, int] = {}

    def _rw(m: re.Match) -> str:
        tgt = m.group(1)
        if tgt in by_token:
            n = counts.get(tgt, 0)
            counts[tgt] = n + 1
            if n in by_token[tgt]:
                return f"[[{by_token[tgt][n]}{m.group(2) or ''}{m.group(3) or ''}]]"
        return m.group(0)

    out = "".join(
        seg if is_code else _COERCE_WIKILINK_RE.sub(_rw, seg)
        for is_code, seg in _outside_code_spans(body))
    for tok, occs in by_token.items():
        if counts.get(tok, 0) <= max(occs):
            raise CanonicalInvariantError(
                f"occurrence {max(occs)} of {tok!r} not found in body")
    return out


def _iter_mapped_tokens(body: str, rename: dict[str, str]) -> list[tuple[str, str]]:
    """Each code-aware wikilink match whose target is in `rename`, in scan
    order (duplicates yielded per occurrence)."""
    out: list[tuple[str, str]] = []
    for is_code, seg in _outside_code_spans(body):
        if is_code:
            continue
        for m in _COERCE_WIKILINK_RE.finditer(seg):
            tgt = m.group(1)
            if tgt in rename:
                out.append((tgt, rename[tgt]))
    return out


def _prose_frame(body: str) -> str:
    """The body with every wikilink token blanked — prose + code spans must
    match byte-for-byte between raw and canonical."""
    return "".join(
        seg if is_code else _COERCE_WIKILINK_RE.sub("\x00", seg)
        for is_code, seg in _outside_code_spans(body))


def _token_scan(body: str) -> list[tuple[str, tuple[str, str]]]:
    """Code-aware wikilink scan: (target, (anchor, display)) in document order."""
    out: list[tuple[str, tuple[str, str]]] = []
    for is_code, seg in _outside_code_spans(body):
        if is_code:
            continue
        for m in _COERCE_WIKILINK_RE.finditer(seg):
            out.append((m.group(1), (m.group(2) or "", m.group(3) or "")))
    return out


def _body_diffs(page_index: int, raw_body: str, canon_body: str) -> list[tuple]:
    """Token-level body diff: prose frames must be byte-identical; token
    frames (anchor/display) position-aligned; differences emitted as
    (page, "body", occurrence-of-that-token, raw_tok, canon_tok)."""
    if _prose_frame(raw_body) != _prose_frame(canon_body):
        raise CanonicalInvariantError(
            f"pages[{page_index}].body prose/code changed")
    raw_tokens, canon_tokens = _token_scan(raw_body), _token_scan(canon_body)
    if len(raw_tokens) != len(canon_tokens):
        raise CanonicalInvariantError(
            f"pages[{page_index}].body link count changed")
    diffs: list[tuple] = []
    seen: dict[str, int] = {}
    for (rt, rf), (ct, cf) in zip(raw_tokens, canon_tokens):
        if rf != cf:
            raise CanonicalInvariantError(
                f"pages[{page_index}].body anchor/display changed")
        n = seen.get(rt, 0)
        if rt != ct:
            diffs.append((page_index, "body", n, rt, ct))
        seen[rt] = n + 1
    return diffs


_KIND_MATRIX = {
    OpKind.SLUG_FORM_COERCION: ("slug", "form-rule"),
    OpKind.SUMMARY_IDENTITY_RESOLUTION: ("slug", "role+source_id"),
    OpKind.BODY_REFERENCE_REWRITE: ("body", "response-local"),
}


def _validate_plan(ops: list[NormalizationOp], *, summary_index: int,
                   page_count: int) -> None:
    """Codex PR5 F2 — the plan's structural contract, validated independently
    of application: kind/field/authority matrix, index/occurrence ranges,
    no-op discipline (only summary identity resolution may be a no-op), and
    EXACTLY ONE summary identity resolution at the summary page — even when
    it is a no-op (an already-canonical stray), so the required resolution
    telemetry can never silently disappear."""
    for op in ops:
        expected = _KIND_MATRIX.get(op.kind)
        if expected is None or (op.field, op.authority) != expected:
            raise CanonicalInvariantError(
                f"invalid kind/field/authority: {op!r}")
        if not (0 <= op.page_index < page_count):
            raise CanonicalInvariantError(f"op page_index out of range: {op!r}")
        if op.field == "body" and op.occurrence < 0:
            raise CanonicalInvariantError(f"invalid occurrence: {op!r}")
        if op.kind is not OpKind.SUMMARY_IDENTITY_RESOLUTION \
                and op.raw == op.canonical:
            raise CanonicalInvariantError(
                f"no-op op outside summary resolution: {op!r}")
    resolutions = [op for op in ops
                   if op.kind is OpKind.SUMMARY_IDENTITY_RESOLUTION]
    if len(resolutions) != 1 or resolutions[0].page_index != summary_index:
        raise CanonicalInvariantError(
            f"exactly one SUMMARY_IDENTITY_RESOLUTION at pages[{summary_index}] "
            f"required, got {resolutions!r}")


def _multiset(items: list[tuple]) -> dict[tuple, int]:
    out: dict[tuple, int] = {}
    for it in items:
        out[it] = out.get(it, 0) + 1
    return out


def _check_conservation(raw: dict, canonical: dict,
                        ops: list[NormalizationOp]) -> None:
    """Codex PR4 F1 — BIJECTION: independently diff raw vs canonical; every
    difference must consume exactly one op and every op must be consumed.
    Page count/order, page_type, title, prose frames, compilation_notes
    byte-for-byte. No-op ops (raw == canonical — e.g. an already-canonical
    stray) are allowed and still telemetered; any other unmatched op or
    difference is a system bug."""
    rp, cp = raw.get("pages") or [], canonical["pages"]
    if len(rp) != len(cp):
        raise CanonicalInvariantError(
            f"page count changed: {len(rp)} -> {len(cp)}")

    diffs: list[tuple] = []
    for i, (r, c) in enumerate(zip(rp, cp)):
        for f in ("page_type", "title"):
            if r.get(f) != c.get(f):
                raise CanonicalInvariantError(f"pages[{i}].{f} changed")
        rs, cs = r.get("slug", ABSENT), c.get("slug", ABSENT)
        if rs != cs:
            diffs.append((i, "slug", 0, rs, cs))
        rb, cb = r.get("body"), c.get("body")
        if rb != cb:
            if not (isinstance(rb, str) and isinstance(cb, str)):
                raise CanonicalInvariantError(f"pages[{i}].body type changed")
            diffs.extend(_body_diffs(i, rb, cb))
    if raw.get("compilation_notes") != canonical.get("compilation_notes"):
        raise CanonicalInvariantError("compilation_notes changed")

    op_keys = [(op.page_index, op.field, op.occurrence, op.raw, op.canonical)
               for op in ops if op.raw != op.canonical]
    if _multiset(diffs) != _multiset(op_keys):
        raise CanonicalInvariantError(
            f"diff/op mismatch: diffs={diffs!r} ops={op_keys!r}")
```

- [ ] **Step 3: Run the full bridge suite + corpus**

Extend `test_proposal_bridge_corpus.py` with the execution test:

```python
from compiler.proposal_bridge import BridgeReject, BridgeSuccess, normalize_proposal


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
def test_corpus_execution(case):
    r = normalize_proposal(case["proposal"], source_id=case["source_id"])
    exp = case["expect"]
    if exp["kind"] == "reject":
        assert isinstance(r, BridgeReject), case["id"]
        assert r.reject_class.value == exp["reject_class"], case["id"]
        assert r.retriable
        return
    assert isinstance(r, BridgeSuccess), case["id"]
    if "summary_slug" in exp:
        summaries = [p for p in r.canonical["pages"] if p["page_type"] == "summary"]
        assert summaries[0]["slug"] == exp["summary_slug"], case["id"]
    for rule in exp.get("decisions_include", []):
        assert any(d.rule == rule for d in r.decisions), (case["id"], rule)
    for token in exp.get("body_preserved", []):
        assert any(token in p["body"] for p in r.canonical["pages"]), (case["id"], token)
```

Run: `.venv/bin/python -m pytest compiler/tests/test_proposal_bridge.py compiler/tests/test_proposal_bridge_corpus.py`
Expected: all PASS (unit + 15-case corpus)

- [ ] **Step 4: Commit**

```bash
git add compiler/proposal_bridge.py compiler/tests/test_proposal_bridge.py compiler/tests/test_proposal_bridge_corpus.py
git commit -m "feat(compiler): #119 Phase 2 — proposal bridge (typed pure normalization, stamping, response-local references, conservation self-check)"
```

---

## Phase 3 — pipeline + prompt switch (ONE integrated phase)

### Task 3.1: `compile_one` rewiring + telemetry

**Files:**
- Modify: `compiler/compiler.py:166-178` (docstring — "LLM emits pages (4 fields)" is stale post-#119), `:186-216` (state init), `:407-475` (schema/rung/semantic block → proposal/bridge/canonical), `:483-521` (success build from canonical), `:534-552` (final_status — unchanged semantics; slug_coerced now bridge-derived)
- Modify: `compiler/resp_summary.py:53-60` (**Codex PR3 F2:** `page_count` = count of well-formed page **dicts**, not `len(page_slugs)` — a slugless 4.0 summary page must still count; module docstring documents `slugs`/`summary_slug` as raw model-supplied slug evidence, None/absent for compliant 4.0 proposals)
- Modify: `common/llm_telemetry.py` + `common/types.py` (`RespStatsRecord` gains optional `normalization_decisions: list[dict] | None`, `summary_identity_derived: bool | None`; `build_resp_stats` kwargs plumbed)
- Modify: `compiler/repair.py` — retire (machinery moved to `proposal_bridge.py`; rung deleted)
- Modify: `compiler/prompt_builder.py:95-110` (exemplar docstring — "summary slug demonstrates the summary-<stem> convention" is stale post-4.0.0), `compiler/validate_source_response.py:58-65` (`semantic_check` docstring — canonical-mode wording: the invariant checks Python's stamp, "the model authors it" is stale)
- Test: `compiler/tests/test_compile_source.py`, `compiler/tests/test_compiler.py`, `compiler/tests/test_compiler_recovery.py`, `compiler/tests/test_resp_summary.py` (absent / stray-string / non-string summary-slug variants → `page_count` counts page dicts; `summary_slug` = raw evidence or None), plus new `compiler/tests/test_compile_one_boundary.py`

**Interfaces:**
- Consumes: `compiler.validate_proposal_response.validate`, `compiler.proposal_bridge.{normalize_proposal, BridgeSuccess, BridgeReject, CanonicalInvariantError, RejectClass}`.
- Produces: `RespStatsRecord.normalization_decisions` / `.summary_identity_derived` (optional, additive — old records read fine); `compile_one` behavior contract per blueprint §4/§3.5.

- [ ] **Step 1: Write the failing boundary tests** — `compiler/tests/test_compile_one_boundary.py`:

```python
"""#119 boundary behavior end-to-end inside compile_one (mocked model)."""
import json
from pathlib import Path
from unittest.mock import patch

from common.types import CompileJob, ContextSnapshot
from compiler.compiler import compile_one


class _Resp:
    def __init__(self, text):
        self.text = text
        self.provider = "test"
        self.model = "test-model"
        self.input_tokens = 1
        self.output_tokens = 1
        self.latency_ms = 1
        self.stop_reason = "stop"
        self.attempts = 1


def _job(source_id):
    return CompileJob(source_id=source_id, abs_path="",
                      context_snapshot=ContextSnapshot(source_id=source_id,
                                                       pages=[]),
                      source_text="body", frontmatter=None)


def _ctx(tmp_path):
    from common.run_context import RunContext
    return RunContext.new(dry_run=True, vault_root=tmp_path)


def _compile_with_payload(tmp_path, source_id, payload, captured):
    """One compile_one call with a mocked model + a resp-stats sink."""
    calls = {"n": 0}

    def fake_call(req):
        calls["n"] += 1
        return _Resp(payload)

    with patch("compiler.compiler.call_model_with_retry", side_effect=fake_call):
        cs, notes, err = compile_one(
            _job(source_id), vault_root=tmp_path, state_root=tmp_path,
            ctx=_ctx(tmp_path), provider="test", model="test-model", max_tokens=1000,
            stats_record_sink=lambda rec, path: captured.setdefault("rec", rec))
    return cs, err, calls["n"]


def test_punctuation_deviant_summary_never_retries_never_quarantines(
        tmp_path, monkeypatch):
    monkeypatch.setenv("KDB_RESP_STATS_CAPTURE_FULL", "1")  # parsed_json is capture-full-gated (llm_telemetry.py:196)
    captured = {}
    cs, err, n = _compile_with_payload(
        tmp_path, "KDB/raw/GraphRAG for Adaptive KB - Gemini3.1.md",
        json.dumps({"pages": [
            {"page_type": "summary",
             "slug": "summary-graphrag-for-adaptive-kb-gemini31",
             "title": "T", "body": "See [[graphrag]]."},
            {"page_type": "concept", "slug": "graphrag", "title": "G",
             "body": "G."},
        ]}), captured)
    assert err is None and n == 1  # NO retry
    assert "summary-graphrag-for-adaptive-kb-gemini3-1" in [p.slug for p in cs.pages]
    rec = captured["rec"]  # §3.5 truth table — sink-captured record
    assert rec.final_status == "clean"            # stamping is NOT a recovery
    assert rec.slug_coerced is False              # stamping/ignoring never set it
    assert rec.summary_identity_derived is True
    assert any(d["rule"] == "summary_slug_ignored"
               for d in rec.normalization_decisions)
    assert "gemini31" in json.dumps(rec.parsed_json)  # raw proposal preserved


def test_concept_coercion_sets_slug_coerced_and_repaired(tmp_path):
    captured = {}
    cs, err, n = _compile_with_payload(
        tmp_path, "KDB/raw/x.md",
        json.dumps({"pages": [
            {"page_type": "summary", "title": "T", "body": "See [[Foo--Bar]]."},
            {"page_type": "concept", "slug": "Foo--Bar", "title": "FB",
             "body": "FB."},
        ]}), captured)
    assert err is None and n == 1
    rec = captured["rec"]
    assert rec.slug_coerced is True and rec.final_status == "repaired"
    assert rec.summary_identity_derived is True


def test_zero_summaries_retries_once_then_typed_quarantine(tmp_path):
    captured = {}
    cs, err, n = _compile_with_payload(
        tmp_path, "KDB/raw/x.md",
        json.dumps({"pages": [
            {"page_type": "concept", "slug": "a", "title": "T", "body": "B."}]}),
        captured)
    assert err is not None and n == 2  # retriable once, then terminal
    rec = captured["rec"]
    assert rec.final_status == "quarantined"
    assert rec.failure_stage == "validate"
    assert rec.failure_exception_type == "ProposalReject:no_summary"


def test_partial_decisions_persist_on_terminal_reject(tmp_path):
    """Coercion decision recorded, THEN a derived-slug collision rejects —
    the terminal record must carry the partial decision list (F5)."""
    captured = {}
    cs, err, n = _compile_with_payload(
        tmp_path, "KDB/raw/x.md",
        json.dumps({"pages": [
            {"page_type": "summary", "title": "T", "body": "B."},
            {"page_type": "concept", "slug": "Summary--X", "title": "SX",
             "body": "SX."},  # coerces to "summary-x" → collides with derived
        ]}), captured)
    assert err is not None and n == 2
    rec = captured["rec"]
    assert rec.failure_exception_type == "ProposalReject:slug_collision"
    assert any(d["rule"] == "slug_form_coercion"
               for d in rec.normalization_decisions)


def test_uncoercible_slug_retries_once_then_typed_quarantine(tmp_path):
    captured = {}
    cs, err, n = _compile_with_payload(
        tmp_path, "KDB/raw/x.md",
        json.dumps({"pages": [
            {"page_type": "summary", "title": "T", "body": "B."},
            {"page_type": "concept", "slug": "Foo Bar", "title": "FB",
             "body": "FB."},
        ]}), captured)
    assert err is not None and n == 2
    rec = captured["rec"]
    assert rec.failure_exception_type == "ProposalReject:uncoercible_slug"


def test_canonical_invariant_failure_captured(tmp_path, monkeypatch):
    captured = {}
    payload = json.dumps({"pages": [{"page_type": "summary", "title": "T",
                                     "body": "B."}]})
    import compiler.proposal_bridge as pb
    monkeypatch.setattr(pb, "normalize_proposal",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            pb.CanonicalInvariantError("boom")))
    cs, err, n = _compile_with_payload(
        tmp_path, "KDB/raw/x.md", payload, captured)
    assert err is not None and n == 1  # NON-retriable — no retry
    rec = captured["rec"]
    assert rec.final_status == "quarantined"
    assert rec.failure_exception_type == "CanonicalInvariantError"
    # failed-response raw capture fires even without capture-full
    # (raw_response_text kept when failed_after_response, llm_telemetry.py:199-201)
    assert rec.raw_response_text == payload
```

import pytest


_MATRIX = [
    # (case_id, source_id, payload, expected_calls, expected_failure_type | None,
    #  expected_final_status, expected_decision_rules)
    ("proposal-schema-violation", "KDB/raw/x.md",
     {"pages": [{"page_type": "concept", "title": "T", "body": "B."}]},  # missing required slug
     2, "StructuralInsufficiency", "quarantined", []),
    ("zero-summaries", "KDB/raw/x.md",
     {"pages": [{"page_type": "concept", "slug": "a", "title": "T", "body": "B."}]},
     2, "ProposalReject:no_summary", "quarantined", []),
    ("two-summaries", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "title": "A", "body": "B."},
                {"page_type": "summary", "title": "C", "body": "B."}]},
     2, "ProposalReject:multiple_summaries", "quarantined", []),
    ("derived-slug-collision", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "title": "T", "body": "B."},
                {"page_type": "concept", "slug": "summary-x", "title": "SX", "body": "B."}]},
     2, "ProposalReject:slug_collision", "quarantined", []),
    ("uncoercible-slug", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "title": "T", "body": "B."},
                {"page_type": "concept", "slug": "Foo Bar", "title": "FB", "body": "B."}]},
     2, "ProposalReject:uncoercible_slug", "quarantined", []),
    ("absent-summary-slug", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "title": "T", "body": "B."}]},
     1, None, "clean", ["summary_identity_stamp"]),
    ("deviating-summary-slug", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "slug": "summary-x-deviant", "title": "T", "body": "B."}]},
     1, None, "clean", ["summary_slug_ignored", "summary_identity_stamp"]),
    ("malformed-summary-slug", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "slug": "SUMMARY--X", "title": "T", "body": "B."}]},
     1, None, "clean", ["summary_slug_ignored", "summary_identity_stamp"]),
    ("nonstring-summary-slug", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "slug": {"x": 1}, "title": "T", "body": "B."}]},
     1, None, "clean", ["summary_slug_ignored", "summary_identity_stamp"]),
]


@pytest.mark.parametrize(
    "case_id, source_id, payload, calls, failure, final_status, rules",
    _MATRIX, ids=[m[0] for m in _MATRIX])
def test_retry_and_tolerance_matrix(tmp_path, case_id, source_id, payload,
                                    calls, failure, final_status, rules):
    """Codex PR3 F3: the full retry/tolerance matrix through compile_one —
    call count, terminal type, decisions, final_status, all asserted."""
    captured = {}
    cs, err, n = _compile_with_payload(
        tmp_path, source_id, json.dumps(payload), captured)
    rec = captured["rec"]
    assert n == calls, case_id
    assert rec.final_status == final_status, case_id
    if failure is None:
        assert err is None and cs is not None, case_id
        from compiler.summary_slug import expected_summary_slug
        assert expected_summary_slug(source_id) in [p.slug for p in cs.pages], case_id
    else:
        assert err is not None, case_id
        assert rec.failure_exception_type == failure, case_id
    got_rules = [d["rule"] for d in (rec.normalization_decisions or [])]
    for rule in rules:
        assert rule in got_rules, (case_id, rule)
```

(The remaining rows of the retry table live in existing tests: unrecoverable-JSON retriable (`test_compiler_recovery.py`); truncation/model-call terminal (existing compiler tests); canonical-side non-retriable (`test_canonical_invariant_failure_captured` above).)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest compiler/tests/test_compile_one_boundary.py`
Expected: FAIL — the deviant summary still quarantines under the old gate.

- [ ] **Step 3: Rewire `compile_one`.** In the attempt loop, replace the schema/rung/semantic block (`compiler.py:407-471`) with:

```python
            # --- proposal validate (#119) ---
            state["schema_errors"] = validate_proposal_response.validate(
                state["parsed_json"])
            state["schema_ok"] = state["schema_errors"] == []
            if not state["schema_ok"]:
                if not last_attempt:
                    log.warning(
                        f"{source_id}: Pass-2 attempt {attempt}/"
                        f"{_MAX_COMPILE_ATTEMPTS} proposal invalid, retrying: "
                        f"{state['schema_errors'][0]}")
                    continue
                _set_failure(state, "validate", "StructuralInsufficiency",
                             state["schema_errors"][0])
                state["error"] = (
                    f"{source_id}: proposal validation failed: "
                    f"{state['schema_errors'][0]}")
                return (None, [], state["error"])

            # --- normalization bridge (#119) ---
            try:
                bridge = proposal_bridge.normalize_proposal(
                    state["parsed_json"], source_id=source_id)
            except proposal_bridge.CanonicalInvariantError as e:
                _set_failure(state, "validate", "CanonicalInvariantError", str(e))
                state["error"] = f"{source_id}: canonical invariant: {e}"
                return (None, [], state["error"])
            if isinstance(bridge, proposal_bridge.BridgeReject):
                state["semantic_errors"] = [
                    f"{bridge.reject_class.value}: {bridge.detail}"]
                # terminal-reject decisions persist too (partial telemetry —
                # Codex plan-review F5); cleared per attempt by the reset below
                (state["normalization_decisions"],
                 state["normalization_decision_count"],
                 state["normalization_decisions_overflow_sha256"]) = \
                    proposal_bridge._cap_decisions(bridge.decisions)
                if not last_attempt:
                    log.warning(
                        f"{source_id}: Pass-2 attempt {attempt}/"
                        f"{_MAX_COMPILE_ATTEMPTS} bridge reject "
                        f"({bridge.reject_class.value}), retrying")
                    continue
                _set_failure(state, "validate",
                             f"ProposalReject:{bridge.reject_class.value}",
                             bridge.detail)
                state["error"] = (
                    f"{source_id}: proposal rejected: "
                    f"{bridge.reject_class.value}: {bridge.detail}")
                return (None, [], state["error"])

            state["semantic_ok"] = True
            (state["normalization_decisions"],
             state["normalization_decision_count"],
             state["normalization_decisions_overflow_sha256"]) = \
                proposal_bridge._cap_decisions(bridge.decisions)
            state["summary_identity_derived"] = any(
                d.rule == "summary_identity_stamp" for d in bridge.decisions)
            state["slug_coerced"] = any(
                d.rule == "slug_form_coercion" for d in bridge.decisions)
            canonical = bridge.canonical
```

Imports: add `from compiler import proposal_bridge, validate_proposal_response`. State init (line ~205): add `"normalization_decisions": [], "normalization_decision_count": 0, "normalization_decisions_overflow_sha256": None, "summary_identity_derived": False,`; keep `"slug_coerced": False` (now bridge-derived). **Per-attempt reset block (lines ~322-333): reset all four** so a retry never reads stale decisions from a prior attempt. Success block: build `PageIntent`s from `canonical["pages"]` (not `parsed["pages"]`); `compilation_notes` from `canonical`. Delete the `coerce_slugs_and_propagate` import + rung; delete `compiler/repair.py`. The `finally` block: pass the three capped fields + `summary_identity_derived=state["summary_identity_derived"]` into `build_resp_stats`. In `common/types.py` add the optional fields to `RespStatsRecord` (`normalization_decisions: Optional[list] = None`, `normalization_decision_count: Optional[int] = None`, `normalization_decisions_overflow_sha256: Optional[str] = None`, `summary_identity_derived: Optional[bool] = None`); plumb through `build_resp_stats` in `common/llm_telemetry.py` (additive kwargs, same pattern as `boundary_recovered`).

- [ ] **Step 4: Migrate repair.py's test dependents, then delete it (Codex plan-review F2).** Three test modules import `coerce_slugs_and_propagate` and must be handled **in this same commit** (verified importers: `compiler/tests/test_wikilink_parity.py:18`, `compiler/tests/test_repair.py:9`, `compiler/tests/test_coerce_slugs.py:6`):
  - `compiler/tests/test_wikilink_parity.py` + `tests/fixtures/wikilink_parity/cases.json` — **migrate to a bridge projection (Codex PR4 F4 — do NOT just delete):**
    1. Keep token-parsing cases (`expected_slugs`, escaped/code-span/unclosed) and `expected_body_canonicalize` (canonicalize untouched) byte-exact.
    2. Extend `cases.json` per case with optional `response_pages: [slug, …]` (page slugs the case's response carries) and `expected_body_bridge` (string).
    3. For the six body-only cases (`escaped`, `fenced-code`, `inline-code`, `malformed-collapse`, `uppercase-alias`, `malformed-heading-display`): `expected_body_bridge` == the original `body` (**preserved verbatim** — the new authority behavior, R6 F2).
    4. For **authority-valid variants** of every shape class (escaped literal vs real link, fenced code, inline code, duplicates — both occurrences rewritten separately, unclosed syntax preserved, heading/display preserved): add `response_pages` containing the raw token (e.g. `Foo--Bar`) so the token IS mapped, with `expected_body_bridge` == the old `expected_body_coerce` output for that token (the mapped rewrite, occurrence-exact).
    5. Harness: `rename` from `response_pages` via `collapse_slug`, ops built per occurrence (`_iter_mapped_tokens`), body produced via `_apply_normalization_plan` on a synthetic one-page proposal — assert == `expected_body_bridge`.
    6. Only then remove the obsolete `expected_body_coerce` column — after every shape class has equivalent bridge coverage. Corpus description updated to document the three expectation surfaces (parsing / canonicalize / bridge).
  - `compiler/tests/test_repair.py` + `compiler/tests/test_coerce_slugs.py` — **delete both**; their authority-valid cases (page-slug collapse, collision refusal, display/anchor preservation) are subsumed by the bridge corpus + `test_proposal_bridge.py` (the body-only cases are the obsolete behavior).
  - Delete `compiler/repair.py` itself (machinery moved to `proposal_bridge.py` in Phase 2; `compiler.py` rung deleted in Step 3).

- [ ] **Step 5: Prompt 4.0.0 + exemplar + builder swap (lands in the SAME commit — atomic switch, Codex plan-review F1).** Update `compiler/tests/test_prompt_builder.py` first: pin the new contract block ("do **not** emit a `slug` for the summary page"), exemplar without summary slug, version `"4.0.0"`, and that the injected schema is the proposal schema (`"proposal_response.schema.json"` in the user message). Then apply: `_SCHEMA_PATH` → `schemas/proposal_response.schema.json`; `PASS2_PROMPT_VERSION = "4.0.0"`; `RESPONSE_CONTRACT` gains "Every response contains exactly one page with page_type \"summary\". Do NOT emit a \"slug\" for the summary page — Python assigns its identity. Concept and article pages REQUIRE a \"slug\"."; exemplar summary page without `slug`; system prompt's summary-slug convention paragraph removed for the summary page (concept/article guidance unchanged). **Also extend the authoritative prompt-stamp test — `orchestrator/tests/test_kdb_orchestrate.py::test_run_writes_measurement_header_at_finalize` (:1025, already asserts `pass2_prompt_version` + packaged-prompt SHA; stamps are orchestrator-produced, not `common.measurement` — Codex PR3 F4): assert the header stamps `pass2_prompt_version == prompt_builder.PASS2_PROMPT_VERSION == "4.0.0"` and `pass2_system_prompt_sha256 == sha256(prompt_builder.load_system_prompt().encode()).hexdigest()` after the bump (Codex PR2 F6 — the blueprint's "version/SHA stamps verified in a dry run" requirement).**

- [ ] **Step 6: Alias-provenance integration test (Codex plan-review F6)** — `compiler/tests/test_bridge_canonicalize_integration.py`:

```python
"""#119: bridge output → canonicalize with a REAL alias ledger — provenance intact."""
from compiler import canonicalize
from compiler.canonicalize import AliasEntry, AliasLedger
from compiler.proposal_bridge import BridgeSuccess, normalize_proposal


def _ledger(*pairs: tuple[str, str]) -> AliasLedger:
    """In-memory ledger — same pattern as compiler/tests/test_canonicalize_algorithm.py:41."""
    return AliasLedger(
        entries=tuple(AliasEntry(surface=s, canonical=c) for s, c in pairs),
        snapshot_sha256="test-sha-" + str(len(pairs)),
    )


def test_alias_token_resolves_in_canonicalize_with_provenance():
    proposal = {"pages": [
        {"page_type": "summary", "title": "T", "body": "Alias [[apple-inc]] noted."},
        {"page_type": "concept", "slug": "real-page", "title": "RP", "body": "RP."},
    ]}
    bridge = normalize_proposal(proposal, source_id="KDB/raw/x.md")
    assert isinstance(bridge, BridgeSuccess)
    assert "[[apple-inc]]" in bridge.canonical["pages"][0]["body"]  # preserved by bridge

    cr = {"run_id": "test-run", "success": True,
          "compiled_sources": [{"source_id": "KDB/raw/x.md",
                                "pages": bridge.canonical["pages"]}],
          "compilation_notes": [], "errors": []}
    canonicalize.run(cr, _ledger(("apple-inc", "apple-canonical")), "test-run")
    body = cr["compiled_sources"][0]["pages"][0]["body"]
    assert "[[apple-canonical]]" in body
    assert "apple-inc" in str(cr["canonical_meta"]["aliases_emitted"])
    summaries = [p for p in cr["compiled_sources"][0]["pages"]
                 if p["page_type"] == "summary"]
    assert len(summaries) == 1 and summaries[0]["slug"] == "summary-x"
```

(`canonical_meta` is top-level on the compile_result dict, per the canonicalize tests.)

Plus the `compile_source` end-to-end integration test (Codex PR3 F4 — concrete, and it mocks the **model response**, never `compile_one`, so the bridge itself is exercised):

```python
def test_compile_source_end_to_end_through_boundary(tmp_path, monkeypatch):
    """compile_source: mocked model response flows recover → proposal → bridge
    → canonicalize → post-canon invariant. Deviant summary + coercible concept
    both normalize; ZERO writes escape the produce-don't-write seam."""
    payload = json.dumps({"pages": [
        {"page_type": "summary", "slug": "summary-x-deviant", "title": "T",
         "body": "See [[foo--bar]]."},
        {"page_type": "concept", "slug": "foo--bar", "title": "FB", "body": "FB."},
    ]})
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        lambda req: _Resp(payload))
    from common.types import ContextSnapshot
    from compiler.canonicalize import AliasLedger
    from compiler.compiler import compile_source
    state_root = tmp_path / "KDB" / "state"
    state_root.mkdir(parents=True)
    res = compile_source(
        "KDB/raw/x.md", "body text", None,
        None,                                     # conn=None — a prebuilt snapshot
        vault_root=tmp_path, state_root=state_root, ctx=_ctx(tmp_path),
        ledger=AliasLedger(),                     # empty ledger
        provider="test", model="test-model", max_tokens=1000,
        context_snapshot=ContextSnapshot(source_id="KDB/raw/x.md", pages=[]))
    assert res.cr is not None and res.failure_stage is None
    pages = res.cr["compiled_sources"][0]["pages"]
    by_type = {p["page_type"]: p for p in pages}
    assert by_type["summary"]["slug"] == "summary-x"
    assert by_type["concept"]["slug"] == "foo-bar"
    assert "[[foo-bar]]" in by_type["summary"]["body"]
    # produce-don't-write seam: no wiki pages, no compile_result.json, no
    # manifest — the ONLY legitimate write is per-source resp-stats telemetry
    # under state_root/runs/<run_id>/pass2/ (expected, allowed — Codex PR5 F5)
    assert not (tmp_path / "KDB" / "wiki").exists()
    assert not (state_root / "compile_result.json").exists()
    assert not (state_root / "manifest.json").exists()
    assert list((state_root / "runs").glob("*/pass2/*.json"))  # telemetry only
```

(`conn=None` is safe because a caller-supplied `context_snapshot` skips the only graph read — `compiler/compiler.py:642-652`. `_Resp`/`_ctx` are defined locally in this test file per its local-helper convention — no cross-file imports, no `kdb_graph.testing` dependency.)

- [ ] **Step 7: Full gate (ONE gate after BOTH halves are present — atomic switch; FULL suite, not just compiler/common — Codex PR2 F6)**

Run: `.venv/bin/python -m pytest` (bare — the whole suite incl. orchestrator + tools)
Expected: all green — boundary truth-table tests, prompt 4.0.0 pins (22 existing + updated), split parity corpus, bridge corpus, alias-provenance integration, plus the **header-stamp test** added in Step 5 (orchestrator dry-run smoke passes).

- [ ] **Step 8: Commit (the ONLY commit of Phase 3 — atomic switch)**

```bash
git add compiler/compiler.py compiler/proposal_bridge.py compiler/validate_proposal_response.py compiler/validate_source_response.py compiler/resp_summary.py compiler/prompt_builder.py compiler/prompts/KDB-Compiler-System-Prompt.md compiler/repair.py compiler/tests/ common/types.py common/llm_telemetry.py common/tests/ orchestrator/tests/test_kdb_orchestrate.py tests/fixtures/wikilink_parity/
git status --short   # MUST show only staged (A/M) entries for the above — empty untracked/unstaged before proceeding
git commit -m "feat(compiler): #119 Phase 3 — atomic switch: compile_one rewired to proposal→bridge→canonical + prompt 4.0.0 + repair.py retirement"
```

(Phase 3 has no separate 3.1/3.2 commits: blueprint §9 requires rewiring + prompt/schema/version in one commit so no transient validator/prompt mismatch can exist — Codex plan-review F1.)

---

## Phase 4 — replay + measurement

### Task 4.1: Replay version dispatch (D-BQ-1)

**Files:**
- Modify: `tools/replay.py` — `ReplayFixture` (add `prompt_version: str = "3.0.0"` **after all non-default fields**, dataclass-defaults-last), `load_fixtures` (read optional `prompt_version` from case.json), `replay_case` (dispatch — **the existing seam; CLI `main` already calls it**, `tools/replay.py:91,227`)
- Modify: `tests/fixtures/response_replay/*/case.json` (no stamp needed — the `"3.0.0"` default covers all four existing cases; `case04_legacy_negative` keeps its expected schema-fail verdict)
- Test: `tools/tests/test_response_replay.py` (**the existing test file — do not create a new one**)

**Interfaces:**
- Consumes: `compiler.validate_proposal_response.validate`, `compiler.proposal_bridge.{normalize_proposal, BridgeSuccess, CanonicalInvariantError}`, `compiler.summary_slug.expected_summary_slug`.
- Produces: `replay_case(fx)` dispatches `3.x` → legacy stack (recover → schema → semantic; flags keep today's meaning), `4.x` → new stack (recover → proposal validate → bridge; `schema_ok` := proposal-schema ok, `semantic_ok` := `isinstance(result, BridgeSuccess)`), anything else → `error_detail` + all flags False (fail closed).

- [ ] **Step 1: Failing tests** — extend `tools/tests/test_response_replay.py`:

```python
def test_v4_fixture_passes_new_stack():
    # 4.x case: summary WITHOUT slug → clean pass through proposal+bridge
    import json as _json
    fx = _synth(prompt_version="4.0.0", stored_response_text=_json.dumps({
        "pages": [
            {"page_type": "summary", "title": "T", "body": "See [[a]]."},
            {"page_type": "concept", "slug": "a", "title": "A", "body": "A."},
        ]}))
    r = replay_case(fx)
    assert r.schema_ok and r.semantic_ok and r.error_detail is None


def test_v2_version_fails_closed():
    fx = _synth(prompt_version="2.0.0")
    r = replay_case(fx)
    assert "unsupported prompt_version" in (r.error_detail or "")


def test_unknown_version_fails_closed():
    fx = _synth(prompt_version="9.9.9")
    r = replay_case(fx)
    assert "unsupported prompt_version" in (r.error_detail or "")


def test_v4_underivable_source_id_is_case_error_not_traceback():
    import json as _json
    fx = _synth(prompt_version="4.0.0", source_id="KDB/raw/日本語.md",
                stored_response_text=_json.dumps(
                    {"pages": [{"page_type": "summary", "title": "T",
                                "body": "B."}]}))
    r = replay_case(fx)
    assert "summary slug" in (r.error_detail or "")


def test_v4_preserves_boundary_recovery_extract_flag():
    """Prose-wrapped 4.x payload: extract_ok=False (strict) while recovery
    succeeds — replay must propagate result.extract_ok, not hardcode True."""
    fx = _synth(prompt_version="4.0.0",
                stored_response_text='Note: {"pages": [{"page_type": "summary", "title": "T", "body": "B."}]} -- end',
                expected_extract_ok=False)
    r = replay_case(fx)
    assert r.extract_ok is False and r.parse_ok is True
```

(Uses the existing `_synth` helper at `tools/tests/test_response_replay.py:121` — do not add a new builder.)

- [ ] **Step 2: Implement dispatch in `replay_case`** (keep the function name — CLI and all 9 existing tests call it):

```python
def replay_case(fixture: ReplayFixture) -> ReplayResult:
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
    from compiler import proposal_bridge, validate_proposal_response
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
```

(No broad `except Exception` — programming defects must surface as defects, not fixture failures.)

- [ ] **Step 3: Run**

Run: `.venv/bin/python -m pytest tools/tests/test_response_replay.py`
Expected: all green — the 4 legacy cases keep era-correct verdicts via the `"3.0.0"` default; new dispatch tests pass

- [ ] **Step 4: Commit**

```bash
git add tools/replay.py tools/tests/test_response_replay.py tests/fixtures/response_replay/
git commit -m "feat(tools): #119 Phase 4a — replay prompt_version dispatch in replay_case (3.x/4.x; 2.x+unknown fail-closed)"
```

### Task 4.2: Measurement projections

**Files:**
- Modify: `common/measurement.py` (PassCallMeasurement projection: `normalization_decision_count`, `summary_identity_derived` from resp records)
- Test: `common/tests/test_measurement.py`

**Interfaces:**
- Produces: two **watched diagnostics** on the Pass-2 measurement (never scored axes; D-BQ-3).

- [ ] **Step 1: Failing tests** — `common/tests/test_measurement.py`:

```python
def test_measurement_projects_persisted_count_and_flag():
    # a record carrying the persisted fields projects them verbatim
    rec = _resp_record(normalization_decisions=[{"rule": "slug_form_coercion"}],
                       normalization_decision_count=1,
                       summary_identity_derived=True)
    m = PassCallMeasurement.from_pass2(rec)
    assert m.normalization_decision_count == 1
    assert m.summary_identity_derived is True


def test_measurement_falls_back_to_list_length_for_old_records():
    # records without the persisted count (pre-#119 or capped-write-older)
    rec = _resp_record(normalization_decisions=[{"rule": "a"}, {"rule": "b"}],
                       normalization_decision_count=None)
    assert PassCallMeasurement.from_pass2(rec).normalization_decision_count == 2


def test_measurement_uses_persisted_count_not_sample_length():
    # Codex PR5 F3: after truncation the list holds ≤50 samples but the
    # persisted count must project the TRUE total
    rec = _resp_record(normalization_decisions=[{"rule": "a"}] * 50,
                       normalization_decision_count=63,
                       normalization_decisions_overflow_sha256="f" * 64)
    assert PassCallMeasurement.from_pass2(rec).normalization_decision_count == 63
```

(`_resp_record` mirrors the record-builder helper already in `common/tests/test_measurement.py`.)

- [ ] **Step 2: Implement** — additive optional fields on the Pass-2 measurement dataclass: `normalization_decision_count` projects the **persisted** `RespStatsRecord.normalization_decision_count` when present, falling back to `len(normalization_decisions or [])` (compat for older records); `summary_identity_derived` projects the flag. None-tolerant throughout. **Also in Phase 3's boundary tests: a >50-decision case on BOTH the success path and the terminal-reject path** — assert sample length == 50, `normalization_decision_count` == true total, and a stable 64-hex `normalization_decisions_overflow_sha256` (identical payload → identical digest across two runs).

- [ ] **Step 3: Run**

Run: `.venv/bin/python -m pytest common/tests/test_measurement.py`
Expected: all green

- [ ] **Step 4: Commit**

```bash
git add common/measurement.py common/tests/test_measurement.py
git commit -m "feat(common): #119 Phase 4b — normalization watched diagnostics (decision count, summary_identity_derived)"
```

---

## Phase 5 — acceptance (LIVE, Joseph-gated)

### Task 5.1: Cohort re-fire + gate evaluation + closure

**Files:**
- Modify: `benchmark/scores/*` (leaderboard re-score outputs)
- Modify: `docs/TASKS.md` (#119 → Closed on pass), `docs/CODEBASE_OVERVIEW.md` (Milestone Changelog closure entry)

**Gate procedure (blueprint §9 Phase 5 / options doc v1.3 §5 item 9; resequenced per Codex plan-review F3 — the cohort runs ON THE BRANCH; a failed cohort must never leave acceptance-failing code on `main`):**

- [ ] Full suite green on `feat/119-normalization-boundary` (`.venv/bin/python -m pytest` — bare, trust the exit code).
- [ ] Clean anchor commit on the feature branch (all Phase 0–4 work committed; working tree clean).
- [ ] Joseph pauses Google Drive sync (manual step, per `scripts/sandbox-run.sh` prompt).
- [ ] `./scripts/sandbox-run.sh --model deepseek-v4-flash` then `--model gpt-5.4-mini` from the **branch anchor** (one cohort; stamps verified `pass2_prompt_version 4.0.0` + SHA — the same mechanics as #115's Phase-5 fire from branch anchor `782120b`).
- [ ] Evaluate vs the zero-quarantine Phase-0 baseline (`e9ca323`): quarantine/retry/recovery KPIs stable (§3.5 semantics — clean-with-stamping counts as clean); **both named sources compile without retry or quarantine** (`summary-graphrag-for-adaptive-kb-gemini3-1`, `summary-what-s-react-and-tailwind` present; `summary_identity_derived` in their records); graph-KPI deltas enumerated; any failure classified fixed-by-#119 vs stochastic.
- [ ] `kdb-benchmark score` re-fire → leaderboard rows updated on all three boards (committed on the branch).
- [ ] On PASS: **Joseph's explicit merge approval** → merge to `main` → close #119 (TASKS.md → Closed with the run ids as proof; Milestone Changelog entry; closure commit approved separately). On FAIL: file findings on the branch; `main` never carries the failing implementation; the #115 waiver state remains the production behavior.

---

## Self-review record (2026-07-23)

- **Spec coverage:** blueprint §3.1 schema → Task 1.1 · §3.2 re-role → 1.2 · §3.3 types → 2.1 · §3.4/§3.5 telemetry → 3.1/4.2 · §4 rewiring + retry table → 3.1 · §5 rules 1–5 → 2.1–2.5 · §6 prompt → 3.2 · §7 CLI/replay/intake-docstring → 1.2/4.1 · §9 phases → Phase 0–5 · §10 test plan → per-task steps + Phase 5 gate. **No gaps.**
- **Placeholder scan:** no TBD/TODO; every code step carries code. One noted real-code caveat: `ContextSnapshot` construction in Task 3.1 tests must mirror the existing mock pattern in `compiler/tests/test_compile_source.py` (implementer adjusts to the real signature — same as established tests).
- **Type consistency:** `BridgeSuccess`/`BridgeReject`/`RejectClass`/`NormalizationDecision`/`normalize_proposal` identical across Tasks 2.1–2.5, 3.1, 4.1; `validate_proposal_response.validate` consistent in 1.1/3.1/4.1; `summary_identity_derived`/`normalization_decisions` field names consistent across 3.1/4.2.

## Codex plan review (2026-07-23) — verification + absorption record

Verdict: REVISE BEFORE EXECUTION. All findings verified against code before absorption (`…-review-codex.md` beside this plan).

| Finding | Claim | Verification → fix |
|---|---|---|
| 1 (High) | Separate 3.1/3.2 commits break the ratified atomic-switch (blueprint §9) | **Accurate** — Phase 3 restructured: ONE commit + ONE gate after rewiring AND prompt 4.0.0 both present (Step 8) |
| 2 (High) | Deleting `repair.py` breaks 3 test importers | **Accurate** — verified `test_wikilink_parity.py:18`, `test_repair.py:9`, `test_coerce_slugs.py:6` (+`compiler.py:41`). Fixed: Step 4 migrates/splits/deletes the test modules in the same commit; body-only coerce expectations removed per R7 F3 |
| 3 (High) | Per-task commits lack a Joseph checkpoint; Phase 5 merged to `main` before the cohort | **Accurate** — fixed: commit gate added to Global Constraints; Phase 5 runs the cohort from the branch anchor, merge only after PASS + explicit approval |
| 4 (Medium) | ">120" fixture slug was ~103 chars; body token didn't exactly match the raw slug; ambiguity coverage falsely claimed while `REWRITE_AMBIGUITY` is unreachable | **Accurate** (counted 103; token mismatch by case+hyphens) — fixed: slug now 129 chars with the exact-matching body token; coverage claim removed, class documented reserved/unreachable |
| 5 (Medium) | Truth-table coverage asserted not implemented; terminal `BridgeReject.decisions` never persisted | **Accurate** — fixed: sink-captured record assertions (`stats_record_sink`) for final_status/slug_coerced/raw preservation; decisions copied on the reject path + per-attempt reset; retry matrix enumerated |
| 6 (Medium) | Alias provenance never actually tested through canonicalize | **Accurate** — fixed: Step 6 bridge→canonicalize integration test with a real ledger + `canonical_meta.aliases_emitted` assertion + compile_source dry-run smoke |
| 7 (Medium) | `_decision` used Python type names ("dict") not JSON names ("object"); string raw values unbounded | **Accurate** — fixed: `_JSON_TYPE_NAMES` mapping + 120-char bound with preview+sha256 degradation for oversized strings and non-strings |
| 8 (Medium) | Replay migration invented `run_case`/`test_replay.py`; real seam is `replay_case` in `tools/replay.py:91` with tests in `tools/tests/test_response_replay.py` | **Accurate** — verified by grep. Fixed: dispatch inside `replay_case` (CLI already calls it), existing test file extended, `prompt_version` placed after non-default dataclass fields, 2.x/unknown/underivable tests added |
| Minor | `ContextSnapshot(existing=[], recent_runs=[])` vs real `ContextSnapshot(source_id, pages=[])` (`common/types.py:322`) | **Accurate** — fixed in all test samples |

## Codex plan review v2 (2026-07-23) — verification + absorption record

Verdict: REVISE BEFORE EXECUTION — prior eight "correctly absorbed in intent"; revised details introduced two new blockers + test gaps (`…-review-codex-v2.md` beside this plan). All verified against code before absorption.

| Finding | Claim | Verification → fix |
|---|---|---|
| 1 (High) | Bounded `_decision()` (raw_value=None for >120-char strings) breaks `_check_conservation`, which reconstructed from `raw_value` — the 129-char fixture would always `CanonicalInvariantError` | **Accurate** by construction. Fixed: conservation consumes the full-fidelity internal plan (`rename` + `body_ops`), never the bounded telemetry decisions (Task 2.4/2.5 code) |
| 2 (High) | New Phase-3 tests not executable: `RunContext` needs 7 fields (use `RunContext.new` — `common/run_context.py:62-85`); `_make_ledger` undefined; `test_canonicalize.py` nonexistent (real helper `test_canonicalize_algorithm.py:41`) | **Accurate** — verified both. Fixed: `RunContext.new(dry_run=True, vault_root=tmp_path)`; alias test uses the verified `AliasEntry`/`AliasLedger` pattern with `cr["canonical_meta"]` asserted directly |
| 3 (Medium) | Conservation-negative tests absent (blueprint §10 requires simulated page/notes/prose loss → `CanonicalInvariantError`) | **Accurate** — fixed: 4 fault-injection tests calling `_check_conservation` directly (dropped page, notes loss, title mutation, prose edit) |
| 4 (Medium) | `parsed_json` asserted without capture-full (`llm_telemetry.py:196`); no_summary's empty decisions can't prove partial persistence; no collision/uncoercible boundary test; invariant test lacks raw-capture assertion | **Accurate** — fixed: capture-full monkeypatched where `parsed_json` is asserted; partial-persistence proven via coerce-then-collide reject; `ProposalReject:uncoercible_slug` boundary test added; `raw_response_text` asserted on invariant failure (kept via `failed_after_response`, no env needed — `:199-201`); retry-matrix prose de-conflated (structural = schema, no_summary = semantic) |
| 5 (Medium) | Replay tests used nonexistent `_write_case` (real helper `_synth`, `test_response_replay.py:121`); `_flag_result` unimplemented; v4 path hardcoded `extract_ok=True` (boundary recovery legitimately yields False); broad `except Exception` hides defects | **Accurate** — verified `_synth` + the extract_ok=False/parse_ok=True precedent in the same file. Fixed: `_synth` used, `_flag_result` implemented, `result.extract_ok` propagated, `PathError` caught explicitly, `BridgeReject` emits `reject_class: detail` |
| 6 (Medium) | Phase-3 gate missed the blueprint's version/SHA dry-run verification; gate command ran only compiler/common, not the promised full suite | **Accurate** — fixed: Step 5 extends `common/tests/test_measurement.py` stamp tests (`pass2_prompt_version == "4.0.0"`, SHA of loaded prompt); Step 7 gate = bare `.venv/bin/python -m pytest` (full suite) |
| 7 (Low) | `--source-id` silently ignored in proposal mode — falsely implies semantic validation | **Accurate** — fixed: CLI exits 2 unless `--canonical` present + CLI test |

## Codex plan review v3 (2026-07-23) — verification + absorption record

Verdict: REVISE BEFORE EXECUTION — R2 "largely absorbed correctly"; one load-bearing architecture mismatch + verification gaps (`…-review-codex-v3.md` beside this plan). All findings verified against code before absorption. **Blueprint amended** (§3.3 bounded location/raw-value wording; §5 rule 5 "fully explained by the decision list" → "fully explained by the normalization plan — the lossless typed `NormalizationOp` list from which transformations, the bounded decision list, and the conservation check all derive") — a precision clarification within the ratified architecture, flagged for Joseph's re-confirm.

| Finding | Claim | Verification → fix |
|---|---|---|
| 1 (High) | PR2's fix divorced conservation from the ratified "explained by the decision list" contract — two sources of truth (`rename`/`body_ops` vs decisions) that can drift; summary changes could pass conservation with no recorded stamp/ignore | **Accurate** — the PR2 fix solved the bounded-value bug but created the drift Codex names. Fixed: single lossless typed `NormalizationOp` plan — transformations applied from ops, bounded decisions DERIVED from ops, conservation checked against ops; summary slug change without stamp/ignore ops is now an invariant violation (negative test included). Blueprint §5 rule 5 amended accordingly |
| 2 (Medium) | `resp_summary.py:56` computes `page_count=len(page_slugs)` — a slugless 4.0 summary page undercounts; `parsed_summary` is always-on acceptance evidence | **Accurate** — verified at `compiler/resp_summary.py:32-60`. Fixed: `page_count` counts well-formed page dicts; `slugs`/`summary_slug` documented as raw model-supplied evidence; absent/stray-string/non-string tests added to Task 3 |
| 3 (Medium) | Retry-matrix coverage claimed but the tests don't exist (structural-insufficiency case, stray-slug clean-compile zero-retry cases) | **Accurate** — fixed: 9-case parametrized `test_retry_and_tolerance_matrix` through `compile_one` asserting call count, terminal exception type, decision rules, and `final_status` per case |
| 4 (Medium) | Phase-3 dry-run gate assigned to `common/tests/test_measurement.py`, but stamps are orchestrator-produced (authoritative test: `orchestrator/tests/test_kdb_orchestrate.py:1025`); `compile_source` integration test was prose, and must mock the model response, not `compile_one` | **Accurate** — verified the orchestrator test asserts version + packaged-prompt SHA. Fixed: stamp assertions target that test; concrete `test_compile_source_end_to_end_through_boundary` added, mocking `call_model_with_retry` so the bridge is exercised |
| 5 (Medium) | Body-rewrite decision `location` embeds the full raw token (bypasses the 120 bound — the 129-char case!); blueprint §3.3 still says strings stay in `raw_value` while the plan hashes oversized | **Accurate** — fixed: bounded locations (`pages[i].slug` / `pages[i].body#<occurrence>`); blueprint §3.3 amended (raw_value = strings ≤120; oversized → preview + hash) |
| 6 (Low) | CLI validates `--source-id`/`--canonical` relationship only after reading input (stdin can block); three stale contract docstrings (`compile_one`, `prompt_builder` exemplar, `semantic_check`); "3 new" vs four CLI tests; "Task 2.5 and Phase 4 headings duplicated" | First three **accurate** — guard moved before input read; docstring sweep added to Task 3 Files; count fixed to "+ 4 new". **Headings claim NOT REPRODUCED** — grep shows `### Task 2.5` once (line 946) and `## Phase 4` once (line 1444); no change made (false positive) |

## Codex plan review v4 (2026-07-23) — verification + absorption record

Verdict: REVISE BEFORE EXECUTION — "previous findings absorbed in direction, but one load-bearing conservation defect remains"; blueprint needs explicit re-ratification (`…-review-codex-v4.md` beside this plan). All findings verified against the plan text + code before absorption. **Blueprint versioned v0.4 — amendment PENDING Joseph's explicit re-ratification (F2); implementation blocked until then.**

| Finding | Claim | Verification → fix |
|---|---|---|
| 1 (High) | `NormalizationOp` still not the true source: rules mutated directly while recording ops; conservation one-directional — duplicate occurrences collapse, absent-vs-null conflated, already-canonical stray bypasses, unused/spurious ops unrejected | **Accurate** — all four mechanisms real in my PR3 code. Fixed: bridge is now PLAN-APPLY-VERIFY — rules only CONSTRUCT exactly-located ops (field + occurrence); `_apply_normalization_plan` is the sole mutation path (raises on spurious ops/missing occurrences); `_check_conservation` independently diffs and verifies a BIJECTION (every diff consumes exactly one op; every non-noop op consumed). Negative tests added: duplicate occurrences, explicit-null stray, already-canonical stray (allowed no-op, telemetered), missing op, unused op, spurious op |
| 2 (High) | Blueprint amended after the v0.3 Proceed gate without re-versioning — load-bearing, not editorial | **Accurate** — my process error. Fixed: blueprint versioned **v0.4** (ops-plan conservation authority + §3.3 bounded wording + §3.4 aggregate bound), header marked **PENDING Joseph's explicit re-ratification; implementation blocked until then** |
| 3 (Medium) | Phase-3 `git add` omits `compiler/resp_summary.py`, `compiler/validate_source_response.py`, `orchestrator/tests/test_kdb_orchestrate.py` | **Accurate** — fixed: all three added + `git status --short` clean check before the commit gate |
| 4 (Medium) | Retiring `repair.py` drops token-parity coverage for authority-valid rewrites (escaped/fenced/inline/duplicates/unclosed/heading-display) | **Accurate** — fixed: Step 4 now migrates the corpus to a bridge projection (`response_pages` + `expected_body_bridge`); body-only cases assert verbatim preservation; authority-valid variants keep per-shape mapped coverage; the obsolete `expected_body_coerce` column removed only after equivalent coverage exists |
| 5 (Medium) | Matrix contains a vacuous `assert … or True`; compile_source test uses undefined `_conn`/`kdb_graph.testing` and claims zero-write without asserting it | **Accurate** — fixed: exact `expected_summary_slug(source_id)` assertion + `cs is not None`; test passes `conn=None` + prebuilt `ContextSnapshot` (skips the only graph read, `compiler.py:642-652`); explicit no-wiki/no-compile_result/no-manifest assertions; helpers defined locally |
| 6 (Medium) | "Bounded telemetry" bounded per field, not in aggregate (repeated occurrences emit unbounded decisions) | **Accurate** — fixed: `_cap_decisions` (≤50 located samples + total count + overflow sha256) wired into both the success and terminal-reject persist paths; state/record carry the three fields; blueprint §3.4 v0.4 records the bound |

## Codex plan review v5 (2026-07-23) — verification + absorption record

Verdict: REVISE BEFORE EXECUTION — "correctly restores the v0.4 re-ratification gate and substantially improves the plan; two load-bearing operation-model defects and several verification gaps remain" (`…-review-codex-v5.md` beside this plan). All findings verified against the plan text before absorption. **Blueprint v0.4 remains PENDING Joseph's explicit re-ratification; implementation blocked until then.**

| Finding | Claim | Verification → fix |
|---|---|---|
| 1 (High) | Duplicate body rewrites fail at apply time: ops are occurrence-indexed against the ORIGINAL body but applied sequentially to the MUTATING body — op 0 consumes the first occurrence, renumbering the rest, so op 1 can't find its occurrence and raises. Only an end-to-end test would catch it | **Accurate** — traced: two `[[foo--bar]]` → after op 0, one raw occurrence remains at index 0; op 1 (occurrence 1) raises `CanonicalInvariantError`. Fixed: `_apply_body_ops` applies ALL of a page's body ops in ONE scan against the original body (occurrence counts taken on the original); sequential `_rewrite_nth_occurrence` deleted; end-to-end `normalize_proposal` duplicate-token test added |
| 2 (High) | Bijection holes: no-op ops removed before comparison (a missing already-canonical resolution passes silently, telemetry lost); unused no-ops pass; kind/authority excluded; apply dispatches on `field` only (wrong kind/field combos accepted) | **Accurate** — all four real. Fixed: `_validate_plan` runs before apply — kind/field/authority matrix enforced, index/occurrence ranges checked, no-op discipline (only summary resolution may be a no-op), EXACTLY ONE summary resolution required even when no-op. Apply raises on unknown fields. Five negative tests added |
| 3 (Medium) | `_cap_decisions` counts decisions; blueprint says ops (a resolution op derives 2 decisions — they differ); Phase 4 would project from the truncated list and undercount | **Accurate** — resolved by decision: the field counts **total derived decisions, pre-truncation** (blueprint §3.4 v0.4 wording amended). Measurement projects the persisted count with `len(list)` fallback for old records. >50-decision tests on success AND terminal-reject paths (sample length 50, true total, stable digest) |
| 4 (Medium) | Atomic commit still omits `compiler/validate_source_response.py` (docstring sweep assigned to Phase 3) | **Accurate** — added to the `git add` list |
| 5 (Medium) | `compile_source` test asserts `tmp_path/state/...` while passing `state_root=tmp_path` (a regression writing directly under state_root passes unnoticed); "ZERO writes" too broad — resp telemetry is legitimate | **Accurate** — fixed: realistic `state_root = tmp_path/"KDB"/"state"`; no-wiki/no-compile_result/no-manifest asserted at the right paths; resp-stats under `runs/*/pass2/` explicitly allowed and asserted to be the only write |
| 6 (Low) | Blueprint title still says v0.3 while status says v0.4 | **Accurate** — title updated to v0.4 |
