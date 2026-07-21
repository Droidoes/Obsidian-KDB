# Task #114 — Recovery-Oriented Pass-2 Parse Stage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Pass-2 parse stage recover the JSON payload from any carrier noise (select, never edit; fail only when no complete document exists) — spec v0.3.6 at `docs/superpowers/specs/2026-07-21-recovery-oriented-parse-stage-design.md`.

**Architecture:** One shared recovery function (`compiler/response_recovery.recover_json_response`) owns loose unwrap + strict-shape eval + a 5-step selection-first ladder, used by both `compile_one` and `tools/replay.py`. A leaf util (`common/util/json_tail_fix.parse_document_prefix`) does root-preserving boundary-decode via `json.JSONDecoder().raw_decode`. Truncation is declared only after recovery fails. Recovery becomes telemetry (`boundary_recovered`, prefix/tail counts) threaded to the KPI counters.

**Tech Stack:** Python 3.10+, pytest, stdlib `json` only (no new deps).

**Revision history:**
- **v1.0** — initial plan.
- **v1.1** — Codex plan review round 1 (`REVISE`, 6 findings + process note,
  `...-review-codex.md`): winning-attempt reset semantics; corrected
  `extract_ok` truth values; compiler-level fixture tests; pytest direct;
  replay test file; any-value recovery; pre-authorized commit boundaries.
- **v1.2** — Codex plan review round 2 (`REVISE`, 6 findings,
  `...-v1.1-review-codex.md`), all verified + folded in:
  1. **[High] `recovered: bool` on `RecoveryResult`** — JSON `null` decodes
     to Python `None`, colliding with the failure sentinel. `recovered` is
     now the success signal; `parsed` may be `None` WITH `recovered=True`.
  2. **[High] Root-preserving boundary-decode** — the util decodes at the
     first non-whitespace character when it begins a JSON value; on a
     `[`/scalar root that fails to decode it returns `None` and NEVER
     scans into a nested `{` (no lifting an object out of a top-level
     array — the root document is never carved). Leading-prose case still
     falls back to the first `{`.
  3. **[High] Slug-coercion guarded to dicts** — `compile_one` only calls
     `coerce_slugs_and_propagate` when `isinstance(parsed_json, dict)`;
     list/scalar/`null` payloads go schema-retry → quarantine without
     `AttributeError`.
  4. **[Medium] Task 2 updates the architectural assertion** —
     `test_no_semantic_functions_present` (`test_response_normalizer.py:142-151`)
     gains `unwrap_response` in the allowed public API.
  5. **[Medium] All 19 fixtures go through `compile_one`** — full
     parameterization (not 3 representatives), satisfying the spec §5
     acceptance criterion.
  6. **[Low] spec `extract_ok` wording** — "non-brace trailing junk"
     (spec v0.3.3).
- **v1.3** — Codex plan review round 3 (`REVISE`, 6 findings,
  `...-v1.2-review-codex.md`), all verified + folded in:
  1. **[High] Value-start classification by lexical prefix** — `t`/`f`/`n`
     are matched as the actual `true`/`false`/`null` prefixes, not by
     first character, so prose like `note:` falls through to the
     first-`{` fallback instead of failing as a root candidate (v1.2's
     impl contradicted its own prose test).
  2. **[Medium] Spec passages rewritten** around "root value first,
     prose-only first-`{` fallback" (§3.1 multi-doc rule, §3.2 step 2,
     §5 util contract) — spec v0.3.4.
  3. **[Medium] Incomplete fixture tested through `compile_one`** — two
     calls, quarantine, `parse_ok=False`, zero boundary telemetry (Task 6
     test 9).
  4. **[Medium] `parsed_json` annotations widened to `object | None`** in
     `build_resp_stats` and `RespStatsRecord` + serialization test (Task 4).
  5. **[Medium] `boundary_recovered` appended AFTER `semantic_ok`** in
     `PassCallMeasurement` (all earlier fields are required — a defaulted
     field earlier breaks the dataclass) (Task 7).
  6. **[Low] Vacuous `... is None or True` assertion removed** (Task 1).
- **v1.4** — Codex plan review round 4 (`REVISE`, 5 findings,
  `...-v1.3-review-codex.md`), all verified + folded in:
  1. **[High] Truncated-literal roots no longer bypassable** — a proper
     PREFIX of `true`/`false`/`null` (e.g. `nul`, `tru`, `fals`) is an
     attempted root: decode fails → `None`, never a scan into a later
     `{` (strict root preservation, consistent with the array-root rule).
     Regression tests for `nul/tru/fals {"a": 1}`.
  2. **[Medium] Spec + plan interface wording** pinned to lexical-prefix
     classification (spec §3.2, plan Task 1 interface) — spec v0.3.5.
  3. **[Low] Plan goal references spec v0.3.5.**
  4. **[Low] Task 1 expected count corrected** (19 tests).
  5. **[Low] Task 6 bookkeeping** — tests 3-9 (two places).
- **v1.5** — Codex plan review round 5 (`REVISE`, 4 findings,
  `...-v1.4-review-codex.md`), all verified + folded in:
  1. **[High] Both-direction literal classification** — a token that
     STARTS WITH a complete literal (`nulljunk`, `trueTAIL`, `falsehood`)
     is a root candidate too (raw_decode decodes the root at its own
     offset, adjacent noise becomes tail) — not just proper prefixes
     (`nul`). "The root value wins" now holds in both directions;
     `note:` still falls through to prose.
  2. **[Medium] Stale test comment** — the `'nul'`-alone test no longer
     claims the prose branch (it is an attempted root).
  3. **[Low] Spec §5 wording** — "`nul` is an attempted truncated root
     and never triggers prose fallback" (spec v0.3.6).
  4. **[Low] Prefix-telemetry wording** — "characters before the selected
     root boundary" (spec §3.4 + plan Task 4).

## Global Constraints

- Python 3.10+ modern type hints (`list[str]`, `str | None`); 4-space indent.
- **Layering**: `common` imports nothing internal; `compiler` may import `common`. The new util goes in `common/util/`; the recovery function in `compiler/`.
- Never guess structure: no bracket completion, no string trimming, no fragment merging, **no carving a nested object out of its root** (spec §3.6 + v0.3.6).
- `extract_ok` keeps meaning *strict carrier-shape conformance* (starts `{`, ends `}`, or single fenced block) but is **non-gating**; `failure_stage="extract"` is retired from new records.
- **Repair flags describe the winning attempt**: `syntax_repaired`, `slug_coerced`, `boundary_recovered`, and both discard counts are reset in the per-attempt reset block and assigned from the winning `RecoveryResult` only (existing semantics — regression guard at `compiler/tests/test_compiler.py:1394-1465`).
- `final_status` precedence (existing, `compiler/compiler.py:548-560`): quarantined always wins; attempt-1+repair = `"repaired"`; attempt-2+repair = `"retried-and-repaired"`; attempt-2 clean = `"retried"`; else `"clean"`. `boundary_recovered` joins `syntax_repaired`/`slug_coerced` in the "repair" condition.
- New record fields always serialize (`False`/`0`); readers use `.get(..., False/0)` for historical records.
- Test runner: `.venv/bin/python -m pytest` (no system `python`).
- Fixtures: copy the 20 captured responses from `benchmark/runs/gemini-3.5-flash-2026-07-21T01-{09-32,46-20}_EDT/run_state/pass2/` into a **tracked** `compiler/tests/fixtures/pass2_recovery/` — tests must not read `benchmark/`.
- Commits: pre-authorized per-task boundaries (Joseph's 2026-07-21 instruction "task A first, test runs, commit"); the executor still shows each commit before making it.

---

### Task 1: `common/util/json_tail_fix.py` — root-preserving boundary-decode util

**Files:**
- Create: `common/util/json_tail_fix.py`
- Test: `common/tests/test_json_tail_fix.py`

**Interfaces:**
- Produces: `parse_document_prefix(text: str) -> tuple[object, int, int] | None`
  Returns `(value, prefix_chars, tail_chars)` — the decoded ROOT JSON value
  (any type), chars skipped before it, chars after its decoder boundary.
  `None` if no complete root value decodes. Root-preserving: when the first
  non-whitespace character begins a JSON value (`{`, `[`, `"`, digit, `-`,
  or a letter-run that is a `true`/`false`/`null` literal, a proper
  prefix of one (`nul`/`tru`/`fals` = attempted root), or starts with one
  (`nulljunk`/`trueTAIL` = root + adjacent noise tail)), decode exactly
  there; if it fails, return `None` — never scan into a nested `{`
  (strict root preservation). Only when the text leads with prose (the
  leading word is neither a literal prefix nor literal-led) does it fall
  back to the first `{`, first-`{` only, no scanning. Selection only —
  no bytes altered.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest common/tests/test_json_tail_fix.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'common.util.json_tail_fix'`

- [ ] **Step 3: Implement the util**

```python
"""Root-preserving boundary-decode (#114): decode the ROOT JSON value of a
text, tolerating carrier noise before/after it.

Selection only — the accepted value is decoded exactly as written; no byte
is altered, and a nested value is NEVER carved out of its root (an array
root that fails to decode yields None, not its first element).

Rule: when the first non-whitespace character begins a JSON value
('{', '[', '"', digit, '-', or a letter-run matching a 'true'/'false'/
'null' literal in EITHER direction — prefix-of-literal ('nul' = attempted
root) or literal-led ('nulljunk' = root + noise tail); 'note:' is
prose), decode exactly there; on failure return None, never scan into a
nested '{'. Only when the text leads with prose does the search fall
back to the first '{' — first-'{' only, no scanning.
"""
from __future__ import annotations

import json


def _is_value_start(text: str, i: int) -> bool:
    c = text[i]
    if c in '{["-0123456789':
        return True
    if not c.isalpha():
        return False
    # A leading letter-run counts as a root candidate in BOTH directions:
    # it is a prefix of a literal ('nul' → attempted root) or starts with
    # one ('nulljunk' → root 'null' + adjacent-noise tail). Anything else
    # ('note:', 'nonsense') is prose → first-'{' fallback.
    j = i
    while j < len(text) and text[j].isalpha():
        j += 1
    tok = text[i:j]
    return any(
        text.startswith(lit, i) or lit.startswith(tok)
        for lit in ("true", "false", "null")
    )


def _decode_at(text: str, start: int) -> tuple[object, int, int] | None:
    try:
        value, end = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError:
        return None
    return value, start, len(text) - end


def parse_document_prefix(text: str) -> tuple[object, int, int] | None:
    """Return (value, prefix_chars, tail_chars) or None."""
    i = 0
    while i < len(text) and text[i].isspace():
        i += 1
    if i == len(text):
        return None
    if _is_value_start(text, i):
        # Root candidate at the first non-whitespace char — decode there or
        # fail. Never scan into a nested '{' on failure.
        return _decode_at(text, i)
    # Leading prose: the document is expected to start at the first '{'.
    start = text.find("{")
    if start == -1:
        return None
    return _decode_at(text, start)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest common/tests/test_json_tail_fix.py -q`
Expected: 22 passed

- [ ] **Step 5: Commit (pre-authorized boundary)**

```bash
git add common/util/json_tail_fix.py common/tests/test_json_tail_fix.py
git commit -m "feat(common): #114 — parse_document_prefix root-preserving boundary-decode util"
```

---

### Task 2: `unwrap_response` in `compiler/response_normalizer.py`

**Files:**
- Modify: `compiler/response_normalizer.py` (add function; existing strict
  `extract_json_text`/`parse_json_object` untouched)
- Test: `compiler/tests/test_response_normalizer.py` (append tests AND
  update the architectural assertion at lines 142-151)

**Interfaces:**
- Produces: `unwrap_response(raw_text: str) -> str` — loose unwrap: strips a
  single clearly-present fenced block; otherwise returns the stripped text.
  Never raises.

- [ ] **Step 1: Write the failing tests + update the architectural assertion**

New tests (with `from compiler.response_normalizer import unwrap_response`):

```python
def test_unwrap_bare_object_passthrough():
    assert unwrap_response('{"a": 1}') == '{"a": 1}'


def test_unwrap_strips_json_fence():
    assert unwrap_response('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_unwrap_strips_unlabelled_fence():
    assert unwrap_response('```\n{"a": 1}\n```') == '{"a": 1}'


def test_unwrap_trailing_junk_after_fence_is_kept_for_recovery():
    assert unwrap_response('```json\n{"a": 1}\njunk') == '{"a": 1}\njunk'


def test_unwrap_prose_passthrough():
    assert unwrap_response('note: {"a": 1}') == 'note: {"a": 1}'


def test_unwrap_non_json_fence_passthrough():
    assert unwrap_response('```python\n{"a": 1}\n```') == '```python\n{"a": 1}\n```'
```

Update the architectural assertion (`test_no_semantic_functions_present`,
line 148) — the allowed public API becomes:

```python
    assert sorted(public_names) == [
        "extract_json_text", "parse_json_object", "unwrap_response"], (
        f"response_normalizer must expose only extract_json_text, "
        f"parse_json_object and unwrap_response; found: {public_names}"
    )
```

(The module's shrink contract — extract/unwrap/parse, never coerce — is
unchanged; `unwrap_response` never rejects, so it fits the invariant.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest compiler/tests/test_response_normalizer.py -q`
Expected: FAIL — `ImportError: cannot import name 'unwrap_response'`

- [ ] **Step 3: Implement**

Append to `compiler/response_normalizer.py`:

```python
def unwrap_response(raw_text: str) -> str:
    """Loose unwrap (#114): strip a single clearly-present fenced block;
    otherwise return the stripped text unchanged. Never rejects — carrier
    noise is the recovery stage's problem, not the unwrap stage's.
    """
    text = raw_text.strip()
    if not text.startswith("```"):
        return text
    first_newline = text.find("\n")
    if first_newline == -1:
        return text
    lang = text[3:first_newline].strip().lower()
    if lang not in ("", "json"):
        return text
    body_and_rest = text[first_newline + 1:]
    if body_and_rest.endswith("```"):
        return body_and_rest[:-3].strip()
    return body_and_rest.strip()
```

- [ ] **Step 4: Run to verify pass** — same command; Expected: all passed (new + existing strict tests + updated assertion)

- [ ] **Step 5: Commit (pre-authorized boundary)**

```bash
git add compiler/response_normalizer.py compiler/tests/test_response_normalizer.py
git commit -m "feat(compiler): #114 — unwrap_response loose unwrap (never rejects)"
```

---

### Task 3: `compiler/response_recovery.py` — the shared recovery function

**Files:**
- Create: `compiler/response_recovery.py`
- Test: `compiler/tests/test_response_recovery.py`

**Interfaces:**
- Consumes: `parse_document_prefix` (Task 1), `unwrap_response` (Task 2),
  `escape_stray_backslashes` (`common/util/json_escape_fix.py`),
  `extract_json_text` (strict, for the `extract_ok` telemetry verdict).
- Produces:
  ```python
  @dataclass(frozen=True)
  class RecoveryResult:
      recovered: bool          # THE success signal (a complete JSON value decoded)
      extract_ok: bool         # strict shape conformance — telemetry, NON-GATING
      parsed: object | None = None   # ANY complete JSON value; None w/ recovered=True = JSON null
      syntax_repaired: bool = False
      boundary_recovered: bool = False
      prefix_discarded_chars: int = 0
      tail_discarded_chars: int = 0
      error: str | None = None

  def recover_json_response(raw_text: str) -> RecoveryResult
  ```
  Ladder: (1) clean-decode original → (2) boundary-decode original →
  (3) escape-normalize → (4) clean-decode normalized →
  (5) boundary-decode normalized. ANY decoded value is returned (the
  schema gate judges content — spec v0.3.2/0.3.3). Failure →
  `recovered=False` with `error` set. Callers branch on
  `result.recovered`, NEVER on `parsed is None`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for response_recovery — the #114 shared recovery contract."""
from compiler.response_recovery import recover_json_response


def test_clean_json_parses_no_flags():
    r = recover_json_response('{"pages": []}')
    assert r.recovered and r.parsed == {"pages": []}
    assert r.extract_ok and not r.boundary_recovered and not r.syntax_repaired
    assert (r.prefix_discarded_chars, r.tail_discarded_chars) == (0, 0)
    assert r.error is None


def test_lone_brace_tail_boundary_recovered_strict_conformant():
    r = recover_json_response('{"pages": []}\n}')
    assert r.recovered and r.parsed == {"pages": []}
    assert r.boundary_recovered and not r.syntax_repaired
    assert r.tail_discarded_chars == 2
    assert r.extract_ok is True


def test_prose_tail_boundary_recovered_strict_nonconformant():
    r = recover_json_response('{"pages": []}\n  "warnings": []')
    assert r.recovered and r.parsed == {"pages": []}
    assert r.boundary_recovered and not r.syntax_repaired
    assert r.tail_discarded_chars == 17
    assert r.extract_ok is False


def test_leading_prose_boundary_recovered_with_prefix():
    r = recover_json_response('Here is JSON:\n{"pages": []}')
    assert r.recovered and r.parsed == {"pages": []}
    assert r.boundary_recovered
    assert r.prefix_discarded_chars == 14 and r.tail_discarded_chars == 0
    assert r.extract_ok is False


def test_fenced_json_parses_clean():
    r = recover_json_response('```json\n{"pages": []}\n```')
    assert r.recovered and r.parsed == {"pages": []}
    assert r.extract_ok and not r.boundary_recovered


def test_fenced_plus_tail_boundary_recovered():
    r = recover_json_response('```json\n{"pages": []}\n```\n}')
    assert r.recovered and r.parsed == {"pages": []} and r.boundary_recovered


def test_escape_fix_still_works_step4():
    r = recover_json_response('{"body": "math \\(x\\) here"}')
    assert r.recovered and r.parsed == {"body": "math \\(x\\) here"}
    assert r.syntax_repaired and not r.boundary_recovered


def test_escape_plus_tail_composed_step5():
    r = recover_json_response('{"body": "math \\(x\\)"}\n}')
    assert r.recovered and r.parsed == {"body": "math \\(x\\)"}
    assert r.syntax_repaired and r.boundary_recovered
    assert r.tail_discarded_chars == 2


def test_unterminated_returns_not_recovered_with_error():
    r = recover_json_response('{"pages": [1, 2')
    assert not r.recovered and r.parsed is None and r.error
    assert not r.boundary_recovered and not r.syntax_repaired


def test_json_null_is_recovered_not_failure():
    # json.loads("null") is None — must NOT collide with the failure sentinel
    r = recover_json_response('null')
    assert r.recovered and r.parsed is None and r.error is None


def test_non_dict_top_level_returned_for_schema_gate():
    r = recover_json_response('[1, 2, 3]')
    assert r.recovered and r.parsed == [1, 2, 3]
    assert r.error is None and not r.boundary_recovered


def test_truncated_array_never_lifts_nested_object():
    r = recover_json_response('[{"pages": []}')
    assert not r.recovered


def test_first_brace_only_no_scanning():
    r = recover_json_response('{bad} {"pages": []}')
    assert not r.recovered


def test_selection_first_no_unneeded_edit():
    r = recover_json_response('{"a": "no backslashes"}\n}')
    assert r.recovered and r.boundary_recovered and not r.syntax_repaired
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest compiler/tests/test_response_recovery.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""response_recovery — the Pass-2 recovery contract (#114).

One shared operation for the whole raw-response surface: loose unwrap,
strict-shape evaluation, and the 5-step selection-first ladder. Used by
both compile_one and tools/replay.py so a captured response yields ONE
verdict.

The principle: the LLM response is a carrier; the JSON document is the
payload. Recover the payload with maximum tolerance for carrier noise;
select, never edit (the one sanctioned byte normalization is
escape_stray_backslashes — content-preserving through decode). Failure is
declared only when no complete decodable document exists. ANY decoded
value is returned — including JSON null (recovered=True, parsed=None);
the schema gate judges content (spec v0.3.2/0.3.3). Callers branch on
`result.recovered`, never on `parsed is None`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from common.util.json_escape_fix import escape_stray_backslashes
from common.util.json_tail_fix import parse_document_prefix
from compiler import response_normalizer


@dataclass(frozen=True)
class RecoveryResult:
    recovered: bool
    extract_ok: bool
    parsed: object | None = None
    syntax_repaired: bool = False
    boundary_recovered: bool = False
    prefix_discarded_chars: int = 0
    tail_discarded_chars: int = 0
    error: str | None = None


def recover_json_response(raw_text: str) -> RecoveryResult:
    # Strict-shape verdict first — telemetry only, never gates.
    try:
        response_normalizer.extract_json_text(raw_text)
        extract_ok = True
    except ValueError:
        extract_ok = False

    candidate = response_normalizer.unwrap_response(raw_text)

    # 1. clean-decode original
    try:
        return RecoveryResult(recovered=True, extract_ok=extract_ok,
                              parsed=json.loads(candidate))
    except json.JSONDecodeError:
        pass

    # 2. boundary-decode original (root-preserving)
    hit = parse_document_prefix(candidate)
    if hit is not None:
        return RecoveryResult(
            recovered=True, extract_ok=extract_ok, parsed=hit[0],
            boundary_recovered=True,
            prefix_discarded_chars=hit[1], tail_discarded_chars=hit[2])

    # 3-5. escape-normalize, then clean-decode / boundary-decode normalized
    escaped = escape_stray_backslashes(candidate)
    if escaped != candidate:
        try:
            return RecoveryResult(recovered=True, extract_ok=extract_ok,
                                  parsed=json.loads(escaped),
                                  syntax_repaired=True)
        except json.JSONDecodeError:
            pass
        hit = parse_document_prefix(escaped)
        if hit is not None:
            return RecoveryResult(
                recovered=True, extract_ok=extract_ok, parsed=hit[0],
                syntax_repaired=True, boundary_recovered=True,
                prefix_discarded_chars=hit[1], tail_discarded_chars=hit[2])

    return RecoveryResult(
        recovered=False, extract_ok=extract_ok,
        error="no complete JSON document recoverable from response")
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest compiler/tests/test_response_recovery.py -q`
Expected: 14 passed

- [ ] **Step 5: Commit (pre-authorized boundary)**

```bash
git add compiler/response_recovery.py compiler/tests/test_response_recovery.py
git commit -m "feat(compiler): #114 — shared recover_json_response (5-step selection-first ladder)"
```

---

### Task 4: Telemetry fields — RespStatsRecord + build_resp_stats

**Files:**
- Modify: `common/types.py:439-447` (RespStatsRecord, after `slug_coerced`)
- Modify: `common/llm_telemetry.py` (`build_resp_stats` signature + record assembly)
- Test: `common/tests/test_llm_telemetry.py`, `common/tests/test_types.py`

**Interfaces:**
- Produces (record fields, always serialized): `boundary_recovered: bool = False`,
  `prefix_discarded_chars: int = 0`, `tail_discarded_chars: int = 0`.
- `build_resp_stats(..., boundary_recovered: bool = False,
  prefix_discarded_chars: int = 0, tail_discarded_chars: int = 0)` — appended
  keyword params with defaults (no caller breakage).

- [ ] **Step 1: Write the failing tests**

In `common/tests/test_types.py`:

```python
def test_resp_stats_record_boundary_fields_default_and_serialize():
    rec = RespStatsRecord(
        run_id="r", source_id="s", provider="p", model="m",
        attempts=1, latency_ms=1, input_tokens=1, output_tokens=1,
        prompt_hash="h", response_hash="h",
        extract_ok=False, parse_ok=True, schema_ok=True, semantic_ok=True,
        boundary_recovered=True, prefix_discarded_chars=3, tail_discarded_chars=2,
    )
    d = rec.to_dict()
    assert d["boundary_recovered"] is True
    assert d["prefix_discarded_chars"] == 3 and d["tail_discarded_chars"] == 2


def test_resp_stats_record_boundary_defaults():
    rec = RespStatsRecord(
        run_id="r", source_id="s", provider="p", model="m",
        attempts=1, latency_ms=1, input_tokens=1, output_tokens=1,
        prompt_hash="h", response_hash="h",
        extract_ok=True, parse_ok=True, schema_ok=True, semantic_ok=True,
    )
    d = rec.to_dict()
    assert d["boundary_recovered"] is False
    assert d["prefix_discarded_chars"] == 0 and d["tail_discarded_chars"] == 0
```

In `common/tests/test_llm_telemetry.py`: mirror the nearest existing
`build_resp_stats` test — pass `boundary_recovered=True,
prefix_discarded_chars=2, tail_discarded_chars=20` and assert the fields
land on the returned record.

- [ ] **Step 2: Run to verify failure** — constructor/kwarg errors.

- [ ] **Step 3: Implement**

`common/types.py` — after the `slug_coerced` line in `RespStatsRecord`:

```python
    # #114 recovery telemetry (Pass-2 only; always serialized, False/0 default).
    boundary_recovered: bool = False            # selection recovered a document amid carrier noise
    prefix_discarded_chars: int = 0             # carrier noise before the selected root boundary
    tail_discarded_chars: int = 0               # carrier noise after the decoder boundary
```

`common/llm_telemetry.py` — add the three keyword params (defaults
`False`/`0`/`0`) to `build_resp_stats` and pass them into the
`RespStatsRecord(...)` constructor.

**Also widen the `parsed_json` annotations** (Codex round-3 F4 — any-value
recovery means a list/scalar payload flows through this surface on the
schema-failure path): `build_resp_stats`'s `parsed_json` param
(`common/llm_telemetry.py:81`) and `RespStatsRecord.parsed_json`
(`common/types.py:419`) become `object | None`. Add a serialization test:
a record whose `parsed_json` is a list round-trips through `to_dict()`.

- [ ] **Step 4: Run to verify pass** — both test files.

- [ ] **Step 5: Commit (pre-authorized boundary)**

```bash
git add common/types.py common/llm_telemetry.py common/tests/test_types.py common/tests/test_llm_telemetry.py
git commit -m "feat(common): #114 — boundary_recovered + prefix/tail discard telemetry fields"
```

---

### Task 5: Fixtures — copy the 20 captured responses into tracked fixtures

**Files:**
- Create: `compiler/tests/fixtures/pass2_recovery/*.txt` (20 files)
- Create: `compiler/tests/fixtures/pass2_recovery/manifest.json`

**Interfaces:**
- Produces: `manifest.json` — list of
  `{"file": str, "source_id": str, "source_name": str, "recoverable": bool,
    "extract_ok": bool, "tail_discarded_chars": int,
    "prefix_discarded_chars": int}`
  consumed by the Task 6 fixture tests. `source_name` is the payload's own
  `source_name` field (needed for the semantic check to match).

- [ ] **Step 1: Generate fixtures from the captured records**

Run (repo root):

```bash
.venv/bin/python << 'EOF'
import json, glob, os

from common.util.json_tail_fix import parse_document_prefix
from compiler import response_normalizer

OUT = 'compiler/tests/fixtures/pass2_recovery'
os.makedirs(OUT, exist_ok=True)

manifest = []
i = 0
for run in ['gemini-3.5-flash-2026-07-21T01-09-32_EDT',
            'gemini-3.5-flash-2026-07-21T01-46-20_EDT']:
    for f in sorted(glob.glob(f'benchmark/runs/{run}/run_state/pass2/*.json')):
        d = json.load(open(f))
        msg = d.get('failure_exception_message') or ''
        is_extra = 'Extra data' in msg
        is_extract = d.get('failure_stage') == 'extract'
        if not (is_extra or is_extract):
            continue
        raw = d.get('raw_response_text')
        assert raw, f'no raw text in {f}'
        i += 1
        fname = f'{i:02d}.txt'
        with open(f'{OUT}/{fname}', 'w') as fh:
            fh.write(raw)
        try:
            response_normalizer.extract_json_text(raw)
            extract_ok = True
        except ValueError:
            extract_ok = False
        hit = parse_document_prefix(response_normalizer.unwrap_response(raw))
        payload = hit[0] if (hit and isinstance(hit[0], dict)) else {}
        manifest.append({
            'file': fname,
            'source_id': d['source_id'],
            'source_name': payload.get('source_name', ''),
            'recoverable': hit is not None,
            'extract_ok': extract_ok,
            'prefix_discarded_chars': hit[1] if hit else 0,
            'tail_discarded_chars': hit[2] if hit else 0,
        })

with open(f'{OUT}/manifest.json', 'w') as fh:
    json.dump(manifest, fh, indent=2)

n_rec = sum(1 for e in manifest if e['recoverable'])
print(f'{len(manifest)} fixtures, {n_rec} recoverable, '
      f'{len(manifest) - n_rec} incomplete')
for e in manifest:
    print(e['file'], e['source_id'][:50], e['recoverable'],
          'strict-ok' if e['extract_ok'] else 'strict-fail',
          f"prefix={e['prefix_discarded_chars']} tail={e['tail_discarded_chars']}")
EOF
```

Expected output — **eyeball against this before proceeding (ground-truth
pinning):** 20 fixtures, **19 recoverable, 1 incomplete**
(`Negative cash-conversion cycle.md`). `extract_ok` is **True for 18**
(all tails end in `}` — the strict check is shape-only) and **False for 2**
(`Callouts.md`, `Negative cash-conversion cycle.md`). Lone-brace tails = 2;
fragment tails ∈ {19, 20, 22}; every entry has `prefix_discarded_chars=0`.

- [ ] **Step 2: Commit (pre-authorized boundary)**

```bash
git add compiler/tests/fixtures/pass2_recovery/
git commit -m "test(compiler): #114 — 20 curated carrier-noise fixtures (19 recoverable + 1 incomplete)"
```

---

### Task 6: `compile_one` rewiring — recovery + post-recovery truncation

**Files:**
- Modify: `compiler/compiler.py` (~184 state init; ~296-308 per-attempt
  reset; ~344-406 truncation/extract/parse block; ~408-425 schema/coercion;
  ~543-560 final_status; ~574-603 record call)
- Test: `compiler/tests/test_compiler_recovery.py` (new); updates to
  `compiler/tests/test_compiler.py` where old strict behavior is encoded

**Interfaces:**
- Consumes: `recover_json_response`, `RecoveryResult` (Task 3). Callers
  branch on `result.recovered`, NEVER on `parsed is None` (JSON null).
- Behavior contract (spec §3.3): recovery FIRST; `stop_reason in
  ("max_tokens", "length")` terminal ONLY after recovery fails (no retry);
  recovery failure with normal stop → existing retry path
  (`_MAX_COMPILE_ATTEMPTS = 2`) → `failure_stage="parse"`.
- `extract_ok` recorded from `RecoveryResult.extract_ok` (non-gating);
  `failure_stage="extract"` never emitted by new code.
- **Winning-attempt semantics**: `boundary_recovered`,
  `prefix_discarded_chars`, `tail_discarded_chars` reset per attempt and
  assigned directly (`=`, never `|=`) from the attempt's `RecoveryResult`.
- **Coercion guarded**: `coerce_slugs_and_propagate` only called when
  `isinstance(state["parsed_json"], dict)` — list/scalar/`null` payloads
  go schema-retry → quarantine, no `AttributeError`.
- final_status: repair condition becomes
  `_syntax_repaired or _slug_coerced or _boundary_recovered`.

- [ ] **Step 1: Write the failing tests** (`compiler/tests/test_compiler_recovery.py`)

Read `compiler/tests/test_compiler.py` first and mirror its harness
(`_write_vault`, `_write_raw`, `_ctx`, `_job`, `_good_response`,
`_resp_stats_files`, `fake` model with `ModelResponse`).

```python
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / 'fixtures' / 'pass2_recovery'
MANIFEST = json.loads((FIXTURES / 'manifest.json').read_text())
RECOVERABLE = [e for e in MANIFEST if e['recoverable']]
INCOMPLETE = [e for e in MANIFEST if not e['recoverable']]


def test_manifest_shape():
    assert len(MANIFEST) == 20
    assert len(RECOVERABLE) == 19
    assert len(INCOMPLETE) == 1
    assert 'Negative cash-conversion' in INCOMPLETE[0]['source_id']
    assert sum(1 for e in MANIFEST if not e['extract_ok']) == 2


# 1. All 19 positives: schema-clean AND semantic-clean payloads.
def test_all_19_fixtures_decode_schema_and_semantic_clean():
    from compiler import validate_source_response
    from compiler.response_recovery import recover_json_response
    for e in RECOVERABLE:
        r = recover_json_response((FIXTURES / e['file']).read_text())
        assert r.recovered, e['source_id']
        errs = validate_source_response.validate(r.parsed)
        assert errs == [], f'{e["source_id"]}: {errs[:1]}'
        sem = validate_source_response.semantic_check(
            r.parsed, source_name=e['source_name'])
        assert sem == [], f'{e["source_id"]}: {sem[:1]}'
        assert r.boundary_recovered, e['source_id']
        assert r.tail_discarded_chars == e['tail_discarded_chars']
        assert r.extract_ok == e['extract_ok']


# 2. The incomplete fixture fails recovery.
def test_incomplete_fixture_unrecoverable():
    from compiler.response_recovery import recover_json_response
    e = INCOMPLETE[0]
    r = recover_json_response((FIXTURES / e['file']).read_text())
    assert not r.recovered and r.error


# 3. compile_one e2e over ALL 19 positives (spec §5 acceptance criterion):
#    parameterize by manifest entry. For each: fabricate the source at the
#    manifest source_id (name MATCHES the payload source_name), fake model
#    returns the fixture text, compile succeeds (cs is not None), and the
#    persisted record carries final_status="repaired",
#    boundary_recovered=True, prefix/tail counts + extract_ok matching the
#    manifest.
# (one pytest.mark.parametrize test over RECOVERABLE; body = harness pattern)


# 4. Truncation composition: complete doc + stop_reason "length" → compiles,
#    stop_reason persisted on the record.


# 5. Truncation terminal: truncated doc + "length" → failure_stage
#    "truncation", NO retry (call_count == 1).


# 6. Two-attempt reset regression (Codex round-1 F1): attempt 1 =
#    boundary-recovered but schema-invalid (tail-junk response whose payload
#    is missing a required field) → retry; attempt 2 = fully clean → success.
#    Record: boundary_recovered False, counts 0, final_status == "retried"
#    (NOT "retried-and-repaired"). Modeled on test_compiler.py:1394-1465.


# 7. Negative: schema-wrong decodable prefix (complete small object, then
#    the real document) → recovery accepts the prefix, SCHEMA gate rejects
#    → retry → quarantine. Selection does not bypass content gates.


# 8. Non-object payloads never crash (Codex round-2 F1+F3): three cases —
#    a top-level list, a scalar string, and JSON null. Each recovers
#    (recovered=True), fails the schema gate, coercion is SKIPPED (no
#    AttributeError), and the source retries → quarantines. Assert the
#    quarantined record exists and failure is schema-class.


# 9. Incomplete fixture through compile_one (Codex round-3 F3): fake model
#    returns the INCOMPLETE[0] fixture text on both attempts. Assert: 2
#    model calls, quarantined, parse_ok=False, boundary_recovered=False,
#    prefix/tail counts 0, final_status="quarantined".
```

(Tests 3-8 use the existing harness; test 6 is modeled directly on
`test_final_status_retried_when_attempt1_repaired_but_attempt2_is_clean`
at `test_compiler.py:1394-1465`.)

- [ ] **Step 2: Run to verify failure** — tests 3-9 fail on current code
  (1-2 pass after Task 3; that is fine).

- [ ] **Step 3: Implement the rewiring**

In `compiler/compiler.py`:

(a) Per-attempt state reset (~line 296-308) — append to the existing
reset block (repair flags describe the winning attempt):

```python
            state["boundary_recovered"] = False
            state["prefix_discarded_chars"] = 0
            state["tail_discarded_chars"] = 0
```

(b) Replace the truncation guard + extract + parse block (current lines
344-406) with:

```python
            # --- recovery (#114): unwrap + strict-eval + 5-step ladder ---
            result = recover_json_response(state["raw_response_text"])
            state["extract_ok"] = result.extract_ok
            if not result.recovered:
                # truncation guard — terminal only AFTER recovery fails
                # (a truncated-flagged response may still carry a complete
                # document; stop_reason is carrier metadata, not proof of
                # absence). A re-call won't fit a bigger output → no retry.
                sr = state["model_response"].stop_reason
                if sr in ("max_tokens", "length"):
                    _set_failure(
                        state, "truncation", "TokenOverrun",
                        f"stop_reason={sr!r}; max_tokens={max_tokens}",
                    )
                    state["error"] = (
                        f"{source_id}: truncated at max_tokens={max_tokens} "
                        f"(stop_reason={sr!r}); raise --max-tokens or shorten source"
                    )
                    return (None, [], [], state["error"])
                if not last_attempt:
                    log.warning(
                        f"{source_id}: Pass-2 attempt {attempt}/"
                        f"{_MAX_COMPILE_ATTEMPTS} unrecoverable JSON, retrying: "
                        f"{result.error}"
                    )
                    continue
                _set_failure(state, "parse", "JSONDecodeError",
                             result.error or "unrecoverable")
                state["error"] = f"{source_id}: invalid JSON: {result.error}"
                return (None, [], [], state["error"])

            state["parsed_json"] = result.parsed
            state["parse_ok"] = True
            state["syntax_repaired"] = result.syntax_repaired
            state["boundary_recovered"] = result.boundary_recovered
            state["prefix_discarded_chars"] = result.prefix_discarded_chars
            state["tail_discarded_chars"] = result.tail_discarded_chars
```

Add the import at top: `from compiler.response_recovery import recover_json_response`.
Remove the now-unused `escape_stray_backslashes` import if nothing else in
the file uses it (check first).

(c) State init (~line 184 region): add `"boundary_recovered": False`,
`"prefix_discarded_chars": 0`, `"tail_discarded_chars": 0` to the `state`
dict.

(d) Slug-coercion guard (~line 414) — non-dict payloads skip coercion:

```python
            if not state["schema_ok"]:
                if isinstance(state["parsed_json"], dict) and \
                        coerce_slugs_and_propagate(state["parsed_json"]):
                    ...existing re-validate block unchanged...
```

(e) final_status derivation (~line 544-551): add
`_boundary_recovered = state["boundary_recovered"]` alongside the other
two flags; repair condition becomes

```python
        elif _syntax_repaired or _slug_coerced or _boundary_recovered:
```

(f) `build_resp_stats(...)` call (~line 574-603): add

```python
            boundary_recovered=_boundary_recovered,
            prefix_discarded_chars=state["prefix_discarded_chars"],
            tail_discarded_chars=state["tail_discarded_chars"],
```

- [ ] **Step 4: Run new + full compiler tests DIRECTLY (no pipe)**

Run: `.venv/bin/python -m pytest compiler/tests/ -q`
Expected: all passed. **Watch for existing tests encoding the old strict
behavior** (early-truncation guard, extract-failure expectations in
`test_compiler.py` ~580-613/1042-1067): update them to the new contract —
recovery-first truncation, no `failure_stage="extract"`, `extract_ok`
non-gating. Each such update is part of this task's diff; list each one in
the commit message.

- [ ] **Step 5: Commit (pre-authorized boundary)**

```bash
git add compiler/compiler.py compiler/tests/test_compiler_recovery.py compiler/tests/test_compiler.py
git commit -m "feat(compiler): #114 — compile_one recovery-first parse stage (truncation after recovery)"
```

---

### Task 7: Measurement + KPI threading

**Files:**
- Modify: `common/measurement.py` (PassCallMeasurement field + both projections)
- Modify: `compiler/kpi/processing.py:60-68,93-94` (counters)
- Test: `common/tests/test_measurement.py`, `compiler/tests/test_kpi_processing.py`

**Interfaces:**
- `PassCallMeasurement.boundary_recovered: bool = False`
- `from_pass2`: `boundary_recovered=rec.get("boundary_recovered", False)`
- `from_pass1`: `boundary_recovered=False` (Pass-1 has no recovery)
- `recovery_rate` and `repair_rung_rate` count `… or c.boundary_recovered`.

- [ ] **Step 1: Write the failing tests**

In `common/tests/test_measurement.py`:

```python
def test_from_pass2_reads_boundary_recovered():
    rec = {
        "run_id": "r", "source_id": "s", "provider": "p", "model": "m",
        "final_status": "repaired", "boundary_recovered": True,
    }
    m = PassCallMeasurement.from_pass2(rec)
    assert m.boundary_recovered is True


def test_from_pass2_old_record_defaults_false():
    rec = {"run_id": "r", "source_id": "s", "provider": "p", "model": "m",
           "final_status": "clean"}  # pre-#114 record: key absent
    assert PassCallMeasurement.from_pass2(rec).boundary_recovered is False
```

Plus a Pass-1 projection test (mirror the file's existing pass1 sidecar
fixture): `boundary_recovered is False`.

In `compiler/tests/test_kpi_processing.py` (mirror existing counter tests):

```python
def test_boundary_recovered_counts_in_recovery_and_repair_rung():
    # one call: final_status="repaired", boundary_recovered=True,
    # syntax_repaired=False, slug_coerced=False, attempts=1
    # → counted in BOTH recovery_rate and repair_rung_rate numerators
    ...
```

- [ ] **Step 2: Run to verify failure** — field/counter errors.

- [ ] **Step 3: Implement**

`common/measurement.py`: add `boundary_recovered: bool = False` to
`PassCallMeasurement` — **appended AFTER `semantic_ok`** (the last field;
every earlier field is required, so a defaulted field anywhere else breaks
the dataclass); `from_pass2` gains
`boundary_recovered=rec.get("boundary_recovered", False)`; `from_pass1`
gains `boundary_recovered=False`.

`compiler/kpi/processing.py`:

```python
    n_recovery = sum(
        1 for c in calls
        if c.final_status != "quarantined"
        and (c.syntax_repaired or c.slug_coerced or c.boundary_recovered or c.attempts > 1)
    )
    ...
    # repair_rung_rate: syntax_repaired OR slug_coerced OR boundary_recovered;
    # quarantined NOT excluded.
    n_repair_rung = sum(
        1 for c in calls
        if c.syntax_repaired or c.slug_coerced or c.boundary_recovered
    )
```

(Update the two comments to match.)

- [ ] **Step 4: Run** — both test files + full suite so far, run directly.

- [ ] **Step 5: Commit (pre-authorized boundary)**

```bash
git add common/measurement.py compiler/kpi/processing.py common/tests/test_measurement.py compiler/tests/test_kpi_processing.py
git commit -m "feat(kpi): #114 — boundary_recovered threaded into recovery_rate + repair_rung_rate"
```

---

### Task 8: `tools/replay.py` parity

**Files:**
- Modify: `tools/replay.py:88-117` (`replay_case`)
- Test: `tools/tests/test_response_replay.py` (the existing suite — NOT
  `test_replay.py`, which does not exist)

**Interfaces:**
- Consumes: `recover_json_response` (Task 3). Layering: `tools` may import
  `compiler` (verify against `tools/tests/test_package_boundaries.py` —
  if `tools→compiler` is disallowed, the recovery module's home moves;
  decide at implementation and keep the boundary guard green).

- [ ] **Step 1: Write the failing test**

```python
def test_replay_recovers_trailing_junk_like_compile_one():
    # fixture: stored response text = '{"…valid minimal compile payload…"}\n}'
    # replay_case → parse_ok True, extract_ok True (shape conforms: ends '}'),
    # schema/semantic proceed. Pre-#114 replay would have failed at parse.
    ...
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** — `replay_case` calls
  `recover_json_response(fixture.stored_response_text)` once:
  `extract_ok = result.extract_ok`; success branch on `result.recovered`
  (NOT `parsed is None`); on failure `error_detail = f"parse: {result.error}"`;
  schema/semantic stages unchanged. Run the existing replay tests — any
  fixture whose expected verdict changes under the new contract is updated
  in this diff and listed in the commit message.

- [ ] **Step 4: Run** — `tools/tests/` + full suite green, run directly.

- [ ] **Step 5: Commit (pre-authorized boundary)**

```bash
git add tools/replay.py tools/tests/test_response_replay.py
git commit -m "feat(tools): #114 — replay uses shared recovery (parity with compile_one)"
```

---

### Task 9: Closure — full suite + docs

- [ ] **Step 1: Full non-live suite — run pytest DIRECTLY (no pipe; a
  pipe to `tail` masks pytest's exit status)**

Run: `.venv/bin/python -m pytest -q`
Expected: all passed (baseline was 1298 before #114; new tests on top).

- [ ] **Step 2: Docs**

- `docs/TASKS.md` #114 row → move to Closed table with commit SHAs + summary.
- `docs/CODEBASE_OVERVIEW.md` Milestone Changelog entry (closure rule).
- Spec §8 satisfied.

- [ ] **Step 3: Commit (pre-authorized boundary)**

```bash
git add docs/TASKS.md docs/CODEBASE_OVERVIEW.md
git commit -m "docs: #114 closure — ledger + milestone changelog"
```

---

## Self-Review Notes (plan author)

- **Spec coverage:** §3.1 (Tasks 2, 3, 6), §3.2 ladder + shared API +
  any-value recovery + root preservation (Tasks 1, 3, 6, 8), §3.3
  truncation (Task 6), §3.4 telemetry + defaults + precedence (Tasks 4,
  6, 7), §3.5/§3.6 (Task 3 semantics + tests), §5 fixtures/tests (Tasks
  1, 3, 5, 6, 7, 8), §6 validation (Task 9). All spec sections map.
- **Winning-attempt semantics** are enforced in two places: the per-attempt
  reset block and direct assignment (no OR) — with a dedicated regression
  test (Task 6 test 6) mirroring `test_compiler.py:1394-1465`.
- **Sentinel discipline:** `RecoveryResult.recovered` is the ONLY success
  signal; `parsed=None` with `recovered=True` is JSON null. Callers never
  branch on `parsed is None` (Task 6 test 8 covers null end-to-end).
- **Root preservation:** boundary-decode never carves a nested object out
  of a failed array root (Task 1 + Task 3 regression tests).
- **Known soft spot:** Task 6 tests 3-9 are described, not fully written —
  the implementer must mirror `compiler/tests/test_compiler.py`'s harness
  (read it first). Everything else is complete code.
- **Type consistency:** `parse_document_prefix` returns `tuple[object, int,
  int] | None`; `RecoveryResult.parsed` is `object | None`. Field names
  identical across Tasks 3/4/6/7/8.
