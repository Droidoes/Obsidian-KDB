# Task #106 — JSON-escape + slug-coercion robustness ladder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Pass-2 compiler deterministically recover from the two confirmed recoverable LLM-emission malformations (unescaped JSON backslashes; malformed slugs) instead of relying on a lucky retry — via a re-validation-gated repair ladder.

**Architecture:** Two deterministic, content-preserving repair rungs inside `compile_one`'s existing attempt loop, each gated on re-validation: **rung 1** = targeted backslash-escaping at the parse step; **rung 2** = slug coercion (lowercase + collapse `-{2,}` + edge-strip) with full reference propagation + collision guard at the schema step. The loop is first restructured so `semantic_check` runs *inside* it (so a post-repair semantic failure can retry), with per-attempt state reset and candidate-copy discipline. New helpers are leaf-safe (`common/util/json_escape_fix`, `common/paths.collapse_slug`); the propagation orchestration lives with the existing reconcilers (`compiler/repair`). Compositional telemetry flags record which rung resolved each source.

**Tech Stack:** Python 3, pytest, the existing `compiler/compiler.py` `compile_one` flow. **No new pip dependency** (`json-repair` was dropped by the design panel in favor of targeted escaping).

**Spec:** `docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md` (v0.2, panel-ratified). Synthesis: `…task106-review-synthesis.md`.

---

## Standing rules

- **Tests:** `python3 -m pytest -q -m "not live" <paths>`. `.env` auto-loads real API keys, so a bare `pytest` fires `$`-cost live tests — **NEVER run live as the assistant**; Joseph fires run-8.
- **Branch:** execute on `feat/task106-repair-ladder`, off `main` (v0.5.2). Not `main`.
- **TDD:** write the failing test first, watch it fail, implement minimally, watch it pass, commit. After each task: full non-live suite green.
- **Baseline:** the suite is green at the start (post-v0.5.2). The count grows as tasks add tests; it must never drop.

### Integration-test harness (REAL fixtures in `compiler/tests/test_compiler.py` — Tasks 5–7 use these verbatim)
The shorthand in the Task 5–7 snippets (`_good_payload`, `_as_model_response`, `_job(tmp_path)`) maps to these **actual** helpers — use the real ones:
- `vault = _write_vault(tmp_path)` → then `_write_raw(vault, source_id)` (writes the raw source the prompt reads).
- `job = _job(vault, source_id)` — **two args** (vault, source_id), returns a `CompileJob`.
- payload dict: `_good_response(source_id) -> dict` (the valid per-source response shape).
- model response wrapper: `from common.call_model import ModelResponse`; construct `ModelResponse(text=json.dumps(payload), stop_reason="stop", input_tokens=…, output_tokens=…, …)` — copy the exact kwargs from `_good_model_response()` / `test_compile_one_happy_path_returns_compiled_source` (lines ~97–101, ~150–176).
- the fake: `def fake(req): return ModelResponse(text=…, …)` then `monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)`. To count calls, increment a dict in the closure (see `test_compile_one_retries_on_bad_json_then_succeeds`, ~line 192).
- call: `cs, logs, warns, err = compiler.compile_one(job, provider="…", model="…", …)` — copy the exact call kwargs from `test_compile_one_happy_path` (~line 163).
- result shape: `cs.summary_slug`, `cs.pages[i].body`, `cs.pages[i].slug` (a `CompiledSource`); `err` is `None` on success, a string on failure.
- resp-stats inspection (telemetry asserts): `_resp_stats_files(state_root, run_id)` (~line 116) + read the written JSON; `_ctx(vault)` gives a `RunContext`.

**Before writing any Task 5–7 test, read `compiler/tests/test_compiler.py:43–148` to copy the exact fixture/`ModelResponse`/`compile_one` signatures.** Do not invent helper names.

---

## File-structure map

| File | Change | Responsibility |
|---|---|---|
| `common/util/__init__.py` | **create** (empty) | make `common/util` a package |
| `common/util/json_escape_fix.py` | **create** | rung-1: targeted backslash-escaping (pure string→string) |
| `common/paths.py` | modify (add `collapse_slug`) | rung-2 transform: lowercase+collapse+strip, validity-gated |
| `compiler/repair.py` | modify (add `coerce_slugs_and_propagate` + a wikilink regex) | rung-2 orchestration: rename map, propagation across 7 fields, collision guard |
| `common/types.py` | modify (`RespStatsRecord` +4 fields) | compositional telemetry |
| `common/llm_telemetry.py` | modify (`build_resp_stats` +4 params) | thread telemetry |
| `compiler/compiler.py` | modify (`compile_one` loop) | LB2 restructure + rung-1/rung-2 insertion + telemetry flags |
| Tests | create/extend `common/tests/test_json_escape_fix.py`, `common/tests/test_paths.py`, `compiler/tests/test_coerce_slugs.py`, `compiler/tests/test_compiler.py` | unit + integration |

**Key signatures (consistent across tasks):**
- `common/util/json_escape_fix.py`: `def escape_stray_backslashes(text: str) -> str` — returns text with invalid `\` escapes doubled; valid JSON escapes untouched.
- `common/paths.py`: `def collapse_slug(slug: str) -> str | None` — returns the lowercased/collapsed/stripped slug **iff** the result passes `validate_slug` (non-empty, pattern-valid, not reserved, ≤120); else `None`. Idempotent on already-valid input (returns it unchanged).
- `compiler/repair.py`: `def coerce_slugs_and_propagate(parsed_json: dict) -> bool` — mutates `parsed_json` in place applying a collision-free rename map across all 7 slug-bearing fields; returns `True` iff it changed anything; refuses (no mutation, returns `False`) on any collision or un-coercible value.

---

## Task 1: Rung-1 helper — `escape_stray_backslashes`

**Files:** Create `common/util/__init__.py`, `common/util/json_escape_fix.py`, `common/tests/test_json_escape_fix.py`.

- [ ] **Step 1: Create the package marker.** `common/util/__init__.py` with one line: `"""common.util — generic, stage-agnostic stateless helpers (util is common)."""`

- [ ] **Step 2: Write the failing test.** Create `common/tests/test_json_escape_fix.py`:
```python
import json
from common.util.json_escape_fix import escape_stray_backslashes


def test_latex_backslash_is_escaped_and_content_survives():
    # An unescaped LaTeX \( inside a JSON string value — the run-6 Borda class.
    bad = r'{"body": "the term \(n-1\) matters"}'
    fixed = escape_stray_backslashes(bad)
    obj = json.loads(fixed)                      # must now parse
    assert obj["body"] == r"the term \(n-1\) matters"   # backslash PRESERVED (content fidelity)


def test_valid_json_escapes_are_untouched():
    good = r'{"a": "line1\nline2", "b": "a\\b", "c": "quote\"", "d": "é"}'
    fixed = escape_stray_backslashes(good)
    assert json.loads(fixed) == json.loads(good)    # unchanged semantics
    assert fixed == good                            # byte-identical: no spurious doubling


def test_irreparable_still_fails_to_parse():
    # Escaping fixes backslashes only — a missing-comma stays broken (falls to retry).
    bad = r'{"a": 1 "b": 2}'
    fixed = escape_stray_backslashes(bad)
    try:
        json.loads(fixed)
        assert False, "should still be invalid JSON"
    except json.JSONDecodeError:
        pass
```

- [ ] **Step 3: Run — expect failure.** Run: `python3 -m pytest -q common/tests/test_json_escape_fix.py` — Expected: FAIL (module not found).

- [ ] **Step 4: Implement.** `common/util/json_escape_fix.py`:
```python
"""Rung-1 of the #106 repair ladder: targeted, content-preserving escaping of
stray backslashes that are not valid JSON escapes (e.g. unescaped LaTeX `\\(`).

This is NOT a general JSON-repair tool. It only doubles a `\\` that JSON would
reject, so the backslash survives in the parsed string exactly as emitted —
preserving body content (math/markdown). Anything else stays broken and falls
to retry/quarantine. See spec §3."""
from __future__ import annotations

import re

# A backslash that is NOT the start of a valid JSON escape:
#   valid escapes are \" \\ \/ \b \f \n \r \t  and  \uXXXX (4 hex)
# Negative lookahead for those; match the lone backslash so we can double it.
_STRAY_BACKSLASH = re.compile(r'\\(?![\"\\/bfnrt]|u[0-9a-fA-F]{4})')


def escape_stray_backslashes(text: str) -> str:
    """Double every backslash in `text` that is not a valid JSON escape lead.

    Content-preserving: valid escapes (`\\n`, `\\\\`, `\\"`, `\\uXXXX`, …) are
    left untouched; a stray `\\(` becomes `\\\\(` so `json.loads` decodes it
    back to a literal backslash. Idempotent on already-valid JSON text.
    """
    return _STRAY_BACKSLASH.sub(r"\\\\", text)
```

- [ ] **Step 5: Run — expect pass.** Run: `python3 -m pytest -q common/tests/test_json_escape_fix.py` — Expected: PASS (3 tests).

- [ ] **Step 6: Leaf check + commit.** Confirm `common` stays a leaf: `python3 -m pytest -q tools/tests/test_package_boundaries.py::test_common_is_a_leaf`. Then:
```bash
git add common/util/__init__.py common/util/json_escape_fix.py common/tests/test_json_escape_fix.py
git commit -m "feat(#106): rung-1 targeted backslash-escaping (common/util/json_escape_fix); content-preserving"
```

---

## Task 2: Rung-2 transform — `collapse_slug`

**Files:** Modify `common/paths.py` (add `collapse_slug` after `validate_slug`, ~line 72); extend `common/tests/test_paths.py`.

- [ ] **Step 1: Write the failing test.** Append to `common/tests/test_paths.py`:
```python
from common.paths import collapse_slug


def test_collapse_slug_lowercases_collapses_strips():
    # The Sleep-and-Aging run-6 class + decision-B lowercase.
    assert collapse_slug("summary-Sleep-and-Aging---Research") == "summary-sleep-and-aging-research"


def test_collapse_slug_noop_on_already_valid():
    assert collapse_slug("value-investing") == "value-investing"


def test_collapse_slug_refuses_empty_result():
    assert collapse_slug("---") is None          # collapses+strips to "" → refuse


def test_collapse_slug_refuses_reserved():
    assert collapse_slug("index--") is None      # → "index" is reserved → refuse


def test_collapse_slug_refuses_space_or_invalid_chars():
    # Spaces / non-[a-z0-9-] are structural extraction failures, NOT coerced.
    assert collapse_slug("Bayes Theorem") is None
    assert collapse_slug("foo_bar") is None
```

- [ ] **Step 2: Run — expect failure.** Run: `python3 -m pytest -q common/tests/test_paths.py -k collapse_slug` — Expected: FAIL (`collapse_slug` undefined).

- [ ] **Step 3: Implement.** Add to `common/paths.py` after `validate_slug` (after line 71):
```python
def collapse_slug(slug: str) -> str | None:
    """Rung-2 transform (#106 spec §4a): enforce, post-LLM, the deterministic
    non-semantic subset of `slugify` — lowercase, collapse hyphen runs, strip
    edge hyphens. Returns the coerced slug iff it is a valid slug; otherwise
    None (un-coercible: empty, reserved, over-length, or still pattern-invalid
    e.g. it contained spaces / underscores / other non-[a-z0-9-] content).

    Idempotent on already-valid input (returns it unchanged). Deliberately does
    NOT strip spaces or other characters — those are structural failures that
    must fall to retry/quarantine, not be silently rewritten.
    """
    if not isinstance(slug, str):
        return None
    coerced = re.sub(r"-{2,}", "-", slug.lower()).strip("-")
    try:
        return validate_slug(coerced)            # gates empty/reserved/over-len/pattern
    except PathError:
        return None
```

- [ ] **Step 4: Run — expect pass.** Run: `python3 -m pytest -q common/tests/test_paths.py -k collapse_slug` — Expected: PASS (5 tests).

- [ ] **Step 5: Full slug-policy file green + commit.** Run: `python3 -m pytest -q common/tests/test_paths.py`. Then:
```bash
git add common/paths.py common/tests/test_paths.py
git commit -m "feat(#106): rung-2 slug transform common/paths.collapse_slug (lowercase+collapse+strip, validity-gated)"
```

---

## Task 3: Rung-2 orchestration — `coerce_slugs_and_propagate`

**Files:** Modify `compiler/repair.py` (add a wikilink regex + `coerce_slugs_and_propagate`); create `compiler/tests/test_coerce_slugs.py`.

The 7 slug-bearing fields (verified against `compiler/schemas/compiled_source_response.schema.json`): `summary_slug`, `concept_slugs[]`, `article_slugs[]`, `pages[].slug`, `pages[].outgoing_links[]`, `[[…]]` tokens in `pages[].body`, `log_entries[].related_slugs[]`. (No `warnings[].related_slugs` — `warnings` is `array<string>`.)

- [ ] **Step 1: Write the failing tests.** Create `compiler/tests/test_coerce_slugs.py`:
```python
from compiler.repair import coerce_slugs_and_propagate


def _payload(summary_slug, pages, concept_slugs=None, article_slugs=None, log_entries=None):
    return {
        "source_name": "x.md",
        "summary_slug": summary_slug,
        "concept_slugs": concept_slugs or [],
        "article_slugs": article_slugs or [],
        "pages": pages,
        "log_entries": log_entries or [],
        "warnings": [],
    }


def test_propagates_rename_across_all_fields():
    p = _payload(
        summary_slug="summary-Foo---Bar",
        concept_slugs=["Foo---Bar"],
        pages=[
            {"slug": "summary-Foo---Bar", "page_type": "summary",
             "body": "see [[Foo---Bar]] and [[Foo---Bar|the alias]] and [[Foo---Bar#sec]]",
             "outgoing_links": ["Foo---Bar"]},
            {"slug": "Foo---Bar", "page_type": "concept", "body": "x", "outgoing_links": []},
        ],
        log_entries=[{"level": "info", "message": "m", "related_slugs": ["Foo---Bar"]}],
    )
    changed = coerce_slugs_and_propagate(p)
    assert changed is True
    assert p["summary_slug"] == "summary-foo-bar"
    assert p["concept_slugs"] == ["foo-bar"]
    assert p["pages"][0]["slug"] == "summary-foo-bar"
    assert p["pages"][1]["slug"] == "foo-bar"
    assert p["pages"][0]["outgoing_links"] == ["foo-bar"]
    # whole-token rewrite preserves |display and #anchor:
    assert "[[foo-bar]]" in p["pages"][0]["body"]
    assert "[[foo-bar|the alias]]" in p["pages"][0]["body"]
    assert "[[foo-bar#sec]]" in p["pages"][0]["body"]
    assert p["log_entries"][0]["related_slugs"] == ["foo-bar"]


def test_noop_returns_false_when_all_valid():
    p = _payload("summary-foo", [{"slug": "summary-foo", "page_type": "summary",
                                   "body": "ok", "outgoing_links": []}])
    assert coerce_slugs_and_propagate(p) is False
    assert p["summary_slug"] == "summary-foo"


def test_refuses_collision_malformed_vs_valid():
    # valid 'foo-bar' (concept) + malformed 'foo--bar' (another concept) → collapse collides → refuse
    p = _payload(
        summary_slug="summary-x",
        pages=[
            {"slug": "summary-x", "page_type": "summary", "body": "b", "outgoing_links": []},
            {"slug": "foo-bar", "page_type": "concept", "body": "b", "outgoing_links": []},
            {"slug": "foo--bar", "page_type": "concept", "body": "b", "outgoing_links": []},
        ],
    )
    before = _payload(p["summary_slug"], [dict(pg) for pg in p["pages"]])
    assert coerce_slugs_and_propagate(p) is False
    assert p["pages"][2]["slug"] == "foo--bar"        # unchanged — refused


def test_refuses_uncoercible_value_unchanged():
    # An empty-collapse slug ('---') cannot be coerced → refuse the whole thing.
    p = _payload("summary-x", [
        {"slug": "summary-x", "page_type": "summary", "body": "b", "outgoing_links": []},
        {"slug": "---", "page_type": "concept", "body": "b", "outgoing_links": []},
    ])
    assert coerce_slugs_and_propagate(p) is False
    assert p["pages"][1]["slug"] == "---"
```

- [ ] **Step 2: Run — expect failure.** Run: `python3 -m pytest -q compiler/tests/test_coerce_slugs.py` — Expected: FAIL (`coerce_slugs_and_propagate` undefined).

- [ ] **Step 3: Implement.** Add to `compiler/repair.py` (near the other reconcilers; import `collapse_slug`):
```python
import re
from common.paths import collapse_slug

# Whole-token wikilink matcher for the coercion rewrite. PERMISSIVE target group
# (must see malformed slugs like `Foo---Bar` that the strict extractor ignores),
# capturing #anchor and |display separately so they survive the rewrite.
_COERCE_WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+?)(#[^\[\]|]*)?(\|[^\[\]]*)?\]\]")


def _all_slug_values(pj: dict) -> set[str]:
    """Every distinct slug string present across the 7 bearing fields."""
    vals: set[str] = set()
    if isinstance(pj.get("summary_slug"), str):
        vals.add(pj["summary_slug"])
    for key in ("concept_slugs", "article_slugs"):
        vals.update(s for s in (pj.get(key) or []) if isinstance(s, str))
    for pg in (pj.get("pages") or []):
        if not isinstance(pg, dict):
            continue
        if isinstance(pg.get("slug"), str):
            vals.add(pg["slug"])
        vals.update(s for s in (pg.get("outgoing_links") or []) if isinstance(s, str))
        body = pg.get("body")
        if isinstance(body, str):
            vals.update(m.group(1) for m in _COERCE_WIKILINK_RE.finditer(body))
    for le in (pj.get("log_entries") or []):
        if isinstance(le, dict):
            vals.update(s for s in (le.get("related_slugs") or []) if isinstance(s, str))
    return vals


def coerce_slugs_and_propagate(parsed_json: dict) -> bool:
    """Rung-2 (#106 spec §4): build a collision-free rename map from
    `collapse_slug` over ALL present slug values, then apply it across every
    slug-bearing field (incl. whole `[[token]]` rewrite preserving |display /
    #anchor). Mutates `parsed_json` in place. Returns True iff anything changed.

    Refuses (no mutation, returns False) if any present slug is un-coercible
    (collapse_slug -> None for a value that is itself invalid) or if two
    distinct slugs would collapse to the same value / a collapse collides with
    an already-valid slug. The re-validation gate in compile_one is the final
    arbiter; this just keeps the payload internally consistent or untouched.
    """
    values = _all_slug_values(parsed_json)
    rename: dict[str, str] = {}
    for v in values:
        c = collapse_slug(v)
        if c is None:
            # v cannot be coerced. If v is already valid, collapse_slug returns
            # v unchanged (not None); None here means v is genuinely invalid and
            # unfixable by collapse → cannot guarantee consistency → refuse.
            return False
        if c != v:
            rename[v] = c
    if not rename:
        return False
    # Collision guard: targets must be unique AND not clash with any slug that
    # stays unchanged (already-valid or un-renamed).
    targets = list(rename.values())
    unchanged = values - set(rename.keys())
    if len(set(targets)) != len(targets) or (set(targets) & unchanged):
        return False

    def _swap(s):
        return rename.get(s, s) if isinstance(s, str) else s

    def _swap_list(lst):
        return [_swap(s) for s in lst] if isinstance(lst, list) else lst

    parsed_json["summary_slug"] = _swap(parsed_json.get("summary_slug"))
    for key in ("concept_slugs", "article_slugs"):
        if key in parsed_json:
            parsed_json[key] = _swap_list(parsed_json.get(key))
    for pg in (parsed_json.get("pages") or []):
        if not isinstance(pg, dict):
            continue
        pg["slug"] = _swap(pg.get("slug"))
        if "outgoing_links" in pg:
            pg["outgoing_links"] = _swap_list(pg.get("outgoing_links"))
        body = pg.get("body")
        if isinstance(body, str):
            def _rw(m):
                tgt, anchor, disp = m.group(1), m.group(2) or "", m.group(3) or ""
                return f"[[{rename.get(tgt, tgt)}{anchor}{disp}]]"
            pg["body"] = _COERCE_WIKILINK_RE.sub(_rw, body)
    for le in (parsed_json.get("log_entries") or []):
        if isinstance(le, dict) and "related_slugs" in le:
            le["related_slugs"] = _swap_list(le.get("related_slugs"))
    return True
```

- [ ] **Step 4: Run — expect pass.** Run: `python3 -m pytest -q compiler/tests/test_coerce_slugs.py` — Expected: PASS (4 tests).

- [ ] **Step 5: Stale/leaf sanity + commit.** Run the full repair test file: `python3 -m pytest -q compiler/tests/test_repair.py compiler/tests/test_coerce_slugs.py`. Then:
```bash
git add compiler/repair.py compiler/tests/test_coerce_slugs.py
git commit -m "feat(#106): rung-2 coerce_slugs_and_propagate (rename map across 7 fields, regex wikilink rewrite, all-values collision guard)"
```

---

## Task 4: Compositional telemetry fields

**Files:** Modify `common/types.py` (`RespStatsRecord` +4 fields); `common/llm_telemetry.py` (`build_resp_stats` +4 params); extend `compiler/tests/test_resp_stats_writer.py` (or `common/tests/`).

- [ ] **Step 1: Write the failing test.** Append to `compiler/tests/test_resp_stats_writer.py` (it already imports `common.llm_telemetry as resp_stats_writer`):
```python
def test_resp_stats_carries_compositional_repair_flags(tmp_path):
    from common.run_context import RunContext
    ctx = RunContext.new(state_root=tmp_path, run_id="r1")
    rec = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="s", prompt=None, raw_response_text="{}",
        model_response=None, extract_ok=True, parse_ok=True, parsed_json={},
        schema_ok=True, schema_errors=[], semantic_ok=True, semantic_errors=[],
        compile_attempts=1, syntax_repaired=True, slug_coerced=False,
        final_status="repaired",
    )
    assert rec.compile_attempts == 1
    assert rec.syntax_repaired is True
    assert rec.slug_coerced is False
    assert rec.final_status == "repaired"
    # SDK-level attempts stays a SEPARATE field:
    assert hasattr(rec, "attempts")


def test_resp_stats_repair_flags_default_off():
    from common.run_context import RunContext
    ctx = RunContext.new(state_root=__import__("pathlib").Path("/tmp"), run_id="r2")
    rec = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="s", prompt=None, raw_response_text="{}",
        model_response=None, extract_ok=True, parse_ok=True, parsed_json={},
        schema_ok=True, schema_errors=[], semantic_ok=True, semantic_errors=[],
    )
    assert rec.syntax_repaired is False
    assert rec.slug_coerced is False
    assert rec.compile_attempts is None or isinstance(rec.compile_attempts, int)
    assert rec.final_status is None
```
(Adjust `RunContext.new(...)` to its real constructor if the signature differs — check `common/run_context.py`.)

- [ ] **Step 2: Run — expect failure.** Run: `python3 -m pytest -q compiler/tests/test_resp_stats_writer.py -k compositional` — Expected: FAIL (`build_resp_stats` rejects the new kwargs / fields absent).

- [ ] **Step 3: Implement — add fields to `RespStatsRecord`.** In `common/types.py`, after `failure_exception_message: Optional[str] = None` (end of the dataclass, ~line 428):
```python
    # #106 repair-ladder telemetry (compositional — NOT mutually exclusive).
    # `attempts` above is SDK-level retry count; these describe the Pass-2 ladder.
    compile_attempts: Optional[int] = None      # loop attempt (1 or 2) that produced final parsed_json
    syntax_repaired: bool = False               # rung-1 escaping rescued a parse
    slug_coerced: bool = False                  # rung-2 coercion rescued schema/semantic
    final_status: Optional[str] = None          # clean | repaired | retried-and-repaired | quarantined
```

- [ ] **Step 4: Implement — thread through `build_resp_stats`.** In `common/llm_telemetry.py`, add params (after `failure=None,`, ~line 88):
```python
    compile_attempts: int | None = None,
    syntax_repaired: bool = False,
    slug_coerced: bool = False,
    final_status: str | None = None,
```
and pass them into the `return RespStatsRecord(...)` construction (add the four keyword args).

- [ ] **Step 5: Run — expect pass.** Run: `python3 -m pytest -q compiler/tests/test_resp_stats_writer.py` — Expected: PASS (existing + 2 new).

- [ ] **Step 6: Commit.**
```bash
git add common/types.py common/llm_telemetry.py compiler/tests/test_resp_stats_writer.py
git commit -m "feat(#106): compositional repair telemetry on RespStatsRecord (compile_attempts/syntax_repaired/slug_coerced/final_status)"
```

---

## Task 5: Restructure `compile_one`'s loop (LB2: semantic in-loop + state reset + candidate) — NO rungs yet

**Files:** Modify `compiler/compiler.py` (`compile_one`, lines ~242–352); update any existing test whose semantic-failure path changes (see Step 4).

This is a **behavior-preserving-where-possible refactor** that enables the rungs. **One intended behavior change:** a semantic failure on a non-final attempt now *retries* (today it errors immediately, because semantic runs once after the loop). That is the point of LB2 (the re-validation gate must be inside the loop). Existing tests that assert "semantic failure → error" must feed the bad response on **both** attempts (the fake model already returns the same response each call unless told otherwise — verify).

- [ ] **Step 1: Write/adjust the guard test.** Add to `compiler/tests/test_compiler.py` a test that a semantic failure now consumes both attempts before erroring (using the file's existing fake-model fixture; mirror its style):
```python
def test_semantic_failure_retries_then_errors(monkeypatch, tmp_path):
    # A response whose summary_slug is NOT among pages[].slug → semantic rule 2 fails.
    bad = _good_response()          # reuse the file's helper
    bad_json = json.loads(_extract(bad))   # adapt to the file's helpers
    bad_json["summary_slug"] = "summary-nonexistent"
    calls = {"n": 0}
    def fake(req):
        calls["n"] += 1
        return _as_model_response(json.dumps(bad_json))   # adapt to the file's helper
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)
    cr, logs, warns, err = compile_one(_job(tmp_path), provider="x", model="m")
    assert cr is None and "semantic" in (err or "")
    assert calls["n"] == 2          # LB2: retried before erroring (was 1 pre-LB2)
```
(Adapt helper names to the real fixtures in `test_compiler.py` — `_good_response`, the model-response wrapper, `_job`. If a similar semantic test already exists, modify its call-count expectation instead of adding a new one.)

- [ ] **Step 2: Run — expect failure.** Run: `python3 -m pytest -q compiler/tests/test_compiler.py -k semantic_failure_retries` — Expected: FAIL (currently `calls["n"] == 1`).

- [ ] **Step 3: Restructure the loop.** In `compiler/compiler.py`, replace the attempt-loop body (lines ~242–352) so that **per iteration**: reset the gate fields, run model→extract→parse→schema→**semantic**, and `break` only when `schema_ok and semantic_ok`; otherwise `continue` (non-final) or fall to the terminal error (final). Move the `semantic_check` block (currently 341–352) to *inside* the loop, right after the schema block, before `break`. Concretely:
  - At the top of the `for attempt …` body, reset: `state["extract_ok"]=False; state["parse_ok"]=False; state["parsed_json"]=None; state["schema_ok"]=False; state["schema_errors"]=[]; state["semantic_ok"]=False; state["semantic_errors"]=[]`.
  - Keep model-call / truncation / extract / parse / schema exactly as today, but on the **schema-OK** path do NOT `break` yet — fall into a new semantic block:
```python
            # --- semantic (now INSIDE the loop; LB2) ---
            state["semantic_errors"] = validate_source_response.semantic_check(
                state["parsed_json"], source_name=source_name
            )
            state["semantic_ok"] = state["semantic_errors"] == []
            if not state["semantic_ok"]:
                if not last_attempt:
                    log.warning(
                        f"{source_id}: Pass-2 attempt {attempt}/"
                        f"{_MAX_COMPILE_ATTEMPTS} semantic invalid, retrying: "
                        f"{state['semantic_errors'][0]}"
                    )
                    continue
                state["error"] = (
                    f"{source_id}: semantic check failed: {state['semantic_errors'][0]}"
                )
                return (None, [], [], state["error"])

            break  # parse_ok + schema_ok + semantic_ok → proceed
```
  - Delete the old post-loop semantic block (old 341–352). The `reconcile_body_links` / `reconcile_slug_lists` calls stay where they are (after the loop).
  - **Candidate discipline:** parse into a local `candidate = json.loads(...)` and only assign `state["parsed_json"] = candidate` after parse succeeds (it already effectively does this; ensure no half-failed assignment persists across attempts — the per-iteration reset in the first bullet covers the stale-state class).

- [ ] **Step 4: Fix any other semantic/attempt tests.** Run: `python3 -m pytest -q compiler/tests/test_compiler.py compiler/tests/test_compile_source.py` — some tests may now expect 2 calls instead of 1 on semantic failure, or rely on post-loop semantic. Update their call-count / structure expectations to match the in-loop gate (do NOT weaken what they assert about the *outcome* — only the retry count). List each test you change.

- [ ] **Step 5: Run — expect pass.** Run: `python3 -m pytest -q -m "not live" common/ ingestion/ compiler/ kdb_graph/ orchestrator/ tools/` — Expected: all pass (the restructure preserves outcomes; only semantic-failure retry-count changed).

- [ ] **Step 6: Commit.**
```bash
git add compiler/compiler.py compiler/tests/test_compiler.py compiler/tests/test_compile_source.py
git commit -m "refactor(#106): move semantic_check inside compile_one attempt loop (LB2) + reset per-attempt state; semantic failures now retry"
```

---

## Task 6: Insert rung-1 (escape) at parse-fail + rung-2 (coerce) at schema-fail + telemetry flags

**Files:** Modify `compiler/compiler.py` (`compile_one`); extend `compiler/tests/test_compiler.py`.

- [ ] **Step 1: Write the failing integration tests.** Add to `compiler/tests/test_compiler.py` (adapt helpers to the file's fixtures):
```python
def test_rung1_escape_recovers_latex_on_attempt_1(monkeypatch, tmp_path):
    # Emit a body with an unescaped LaTeX backslash → invalid JSON → rung-1 fixes it.
    payload = _good_payload()                     # dict helper
    payload["pages"][0]["body"] = r"the term \(n-1\) matters"
    raw = json.dumps(payload).replace(r"\\(", r"\(").replace(r"\\)", r"\)")  # re-introduce stray \
    calls = {"n": 0}
    def fake(req):
        calls["n"] += 1
        return _as_model_response(raw)
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)
    cr, logs, warns, err = compile_one(_job(tmp_path), provider="x", model="m")
    assert err is None and cr is not None         # recovered
    assert calls["n"] == 1                         # deterministic — no retry needed
    # content fidelity: the backslash survived into the compiled page body
    assert r"\(n-1\)" in cr.pages[0].body          # adapt to CompiledSource shape


def test_rung2_coerce_recovers_bad_slug_on_attempt_1(monkeypatch, tmp_path):
    payload = _good_payload()
    payload["summary_slug"] = "summary-Sleep-and-Aging---Research"
    payload["pages"][0]["slug"] = "summary-Sleep-and-Aging---Research"
    calls = {"n": 0}
    def fake(req):
        calls["n"] += 1
        return _as_model_response(json.dumps(payload))
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)
    cr, logs, warns, err = compile_one(_job(tmp_path), provider="x", model="m")
    assert err is None and cr is not None
    assert calls["n"] == 1
    assert cr.summary_slug == "summary-sleep-and-aging-research"   # adapt to shape
```

- [ ] **Step 2: Run — expect failure.** Run: `python3 -m pytest -q compiler/tests/test_compiler.py -k "rung1_escape or rung2_coerce"` — Expected: FAIL (no repair yet → either retries to quarantine or errors).

- [ ] **Step 3: Implement rung-1 at the parse step.** In `compile_one`, import `from common.util.json_escape_fix import escape_stray_backslashes`. In the parse block (today ~303–319), on `json.JSONDecodeError`, **before** deciding retry/fail, try the escape once:
```python
            # --- parse (+ rung-1: targeted backslash-escape on failure) ---
            try:
                state["parsed_json"] = json.loads(json_text)
                state["parse_ok"] = True
            except json.JSONDecodeError:
                fixed = escape_stray_backslashes(json_text)
                if fixed != json_text:
                    try:
                        state["parsed_json"] = json.loads(fixed)
                        state["parse_ok"] = True
                        state["syntax_repaired"] = True   # telemetry (see Step 5)
                        log.info(f"{source_id}: Pass-2 attempt {attempt} syntax-repaired, proceeding")
                    except json.JSONDecodeError:
                        pass
                if not state["parse_ok"]:
                    # (existing retry/terminal handling, unchanged)
                    ...
```
(Preserve the existing `if not last_attempt: log.warning(...); continue` / terminal `_set_failure(...); return` logic for the still-unparseable case — wrap it under `if not state["parse_ok"]:`.)

- [ ] **Step 4: Implement rung-2 at the schema step.** Import `from compiler.repair import coerce_slugs_and_propagate`. In the schema block (today ~321–337), on schema failure, attempt coercion + re-validate before retry/fail:
```python
            # --- schema (+ rung-2: slug coercion on failure) ---
            state["schema_errors"] = validate_source_response.validate(state["parsed_json"])
            state["schema_ok"] = state["schema_errors"] == []
            if not state["schema_ok"]:
                if coerce_slugs_and_propagate(state["parsed_json"]):
                    state["schema_errors"] = validate_source_response.validate(state["parsed_json"])
                    state["schema_ok"] = state["schema_errors"] == []
                    if state["schema_ok"]:
                        state["slug_coerced"] = True   # telemetry
                        log.info(f"{source_id}: Pass-2 attempt {attempt} slug-coerced, proceeding")
            if not state["schema_ok"]:
                # (existing retry/terminal handling, unchanged)
                ...
```
(The semantic block from Task 5 already follows and re-checks; a coercion that fixes schema but breaks semantic will retry per LB2.)

- [ ] **Step 5: Thread telemetry flags.** Add `"syntax_repaired": False, "slug_coerced": False` to the initial `state` dict (~line 174). Track `compile_attempts = attempt` on the successful `break`. Where `build_resp_stats(...)` is called for this source (the `finally`/success path), pass `compile_attempts=state.get("compile_attempts")`, `syntax_repaired=state["syntax_repaired"]`, `slug_coerced=state["slug_coerced"]`, and derive `final_status` (`clean` if neither flag and attempts==1; `repaired` if a flag set and attempts==1; `retried-and-repaired` if attempts==2 and a flag set; `quarantined` on failure). Keep `attempts=` (SDK) as-is.

- [ ] **Step 6: Run — expect pass.** Run: `python3 -m pytest -q compiler/tests/test_compiler.py -k "rung1_escape or rung2_coerce"` then the full suite `python3 -m pytest -q -m "not live" common/ ingestion/ compiler/ kdb_graph/ orchestrator/ tools/` — Expected: all pass.

- [ ] **Step 7: Commit.**
```bash
git add compiler/compiler.py compiler/tests/test_compiler.py
git commit -m "feat(#106): wire rung-1 (escape@parse) + rung-2 (coerce@schema) into compile_one + compositional telemetry flags"
```

---

## Task 7: Ladder integration + edge tests

**Files:** Extend `compiler/tests/test_compiler.py`.

- [ ] **Step 1: Write the tests** (adapt helpers): both-rungs-on-one-emission (a body with stray `\` AND a `---` summary_slug → recovers, both flags set); a collision case (two concepts collapse to the same slug) → falls through to quarantine, `slug_coerced` False; a non-slug schema error (e.g. a page missing a required field) → coercion no-ops, behaves exactly as pre-#106 (retry→quarantine); the irreparable JSON (missing comma) → rung-1 no-op → retry→quarantine. Assert `compile_attempts` / `syntax_repaired` / `slug_coerced` / `final_status` telemetry on each.
```python
def test_both_rungs_one_emission(monkeypatch, tmp_path):
    payload = _good_payload()
    payload["summary_slug"] = "summary-Foo---Bar"
    payload["pages"][0]["slug"] = "summary-Foo---Bar"
    payload["pages"][0]["body"] = r"math \(x\) and [[summary-Foo---Bar]]"
    payload["pages"][0]["outgoing_links"] = ["summary-Foo---Bar"]
    raw = json.dumps(payload).replace(r"\\(", r"\(").replace(r"\\)", r"\)")
    monkeypatch.setattr("compiler.compiler.call_model_with_retry",
                        lambda req: _as_model_response(raw))
    cr, logs, warns, err = compile_one(_job(tmp_path), provider="x", model="m")
    assert err is None and cr is not None
    assert cr.summary_slug == "summary-foo-bar"
    assert r"\(x\)" in cr.pages[0].body
```

- [ ] **Step 2: Run — expect pass** (the implementation from Tasks 5–6 should already satisfy these; if one fails it reveals a real gap). Run: `python3 -m pytest -q compiler/tests/test_compiler.py`.

- [ ] **Step 3: Commit.**
```bash
git add compiler/tests/test_compiler.py
git commit -m "test(#106): ladder integration — both-rungs, collision-falls-through, non-slug-error unchanged, irreparable quarantines"
```

---

## Task 8: Gate — non-live green, then live run-8

**Files:** none (verification).

- [ ] **Step 1: Full non-live suite green.** Run: `python3 -m pytest -q -m "not live" common/ ingestion/ compiler/ kdb_graph/ orchestrator/ tools/` — Expected: all pass; count ≥ baseline + the new #106 tests.
- [ ] **Step 2: Boundary contract intact.** Run: `python3 -m pytest -q tools/tests/test_package_boundaries.py` — Expected: pass (`common` still a leaf; `compiler → common` only).
- [ ] **Step 3: Editable install resolves.** Run: `pip install -e . -q --break-system-packages && kdb-orchestrate --help` — Expected: succeeds (no new dependency was added).
- [ ] **Step 4: Hand off the live gate to Joseph.** Present run-8 (reset + `kdb-orchestrate` on `~/Obsidian/Vault-in-place-test-run`; runbook `docs/reference/test-run-procedure.md`). **Joseph fires it.** Pass criteria: `exit_reason=ok`, 0 quarantined, the two recurring cases (LaTeX / `---` slug) resolve via repair (telemetry: `syntax_repaired` / `slug_coerced` true, `compile_attempts == 1`, not `retried`), links wired, 0 orphans.
- [ ] **Step 5: On clean run-8 — #106 DONE.** Record the gate + the repair-rate telemetry in `docs/RELEASES.md`/daily note; merge `feat/task106-repair-ladder`; tag (e.g. `v0.6.0-rc` or per the versioning scheme).

---

## Self-review notes

- **Spec coverage:** §3 rung-1 (Task 1, wired Task 6) · §4a transform (Task 2) · §4b/§4c propagation+collision (Task 3) · §5 placement + LB2 semantic-in-loop + candidate/reset (Task 5, rungs Task 6) · §7 telemetry (Task 4, threaded Task 6) · §8 homes (all) · §9 test plan (Tasks 1–3, 6, 7; run-8 Task 8). All covered.
- **No new dependency** — `json-repair` dropped; rung-1 is a ~3-line regex helper.
- **Riskiest task is 5** (the loop restructure with its one intended behavior change — semantic failures now retry). It is isolated from the rung logic and gated by the existing suite; Task 6 layers the rungs on top of a green restructure.
- **Helper contracts are fixed up front** (`escape_stray_backslashes`, `collapse_slug -> str|None`, `coerce_slugs_and_propagate -> bool`) and reused consistently in Tasks 5–7.
- **Adapt-to-fixtures flagged:** Tasks 5–7 integration tests must use `test_compiler.py`'s real fake-model/`_job` helpers (the model seam is `compiler.compiler.call_model_with_retry`) and the real `CompiledSource` attribute names — the implementer reads those before writing the asserts.
