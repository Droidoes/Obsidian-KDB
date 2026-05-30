# Task #59 — M5 Replacement: `body_emit_set_coverage` — Implementation Plan

> **Execution constraints (project-specific, override generic harness defaults):**
> 1. **Docs-first.** CODEBASE_OVERVIEW.md and TASKS.md updates land before code (Task 1).
> 2. **TDD.** Write failing tests first; minimal implementation; verify pass before commit.
> 3. **User-confirmed commits.** Don't auto-commit unless user has approved; ask first.
> 4. **User-fired API runs.** Don't auto-run `kdb-benchmark` (or any model-cost CLI). Surface the command and wait — per memory `feedback_user_fires_api_cost_runs`.
> 5. **Steps use checkbox (`- [ ]`) syntax** so the executor can track progress.

**Goal:** Replace the retired-by-construction M5 (`body_link_jaccard`, weight 5%) with a meaningful body-content discriminator (`body_emit_set_coverage`) computed in the benchmark scorer from captured `parsed_json`.

**Architecture:** All measurement logic lives in `kdb_benchmark/scorer.py`; no `RespStatsRecord` field changes (preserves D25 one-way boundary). Body-text wikilink helper `_body_wikilink_slugs` is promoted to public `body_wikilink_slugs` so the scorer can import it across the boundary. Per-page self-links are subtracted before union; emit-set is the union of declared `concept_slugs` and `article_slugs`.

**Tech Stack:** Python 3, pytest, Anthropic / OpenAI / xAI / DashScope / Ollama SDKs (already wired). No new dependencies.

**Spec:** [`docs/task59-m5-replacement-design.md`](task59-m5-replacement-design.md) — design v2 + Codex-approved §10 plan-stage clarifications.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `docs/CODEBASE_OVERVIEW.md` | Modify | Update §7.3 M5 row (line 168); add D29 to decisions ledger |
| `docs/TASKS.md` | Modify | Add #59 to Open/In-Progress; close at end |
| `kdb_compiler/validate_compiled_source_response.py` | Modify | Promote `_body_wikilink_slugs` → public `body_wikilink_slugs` |
| `kdb_compiler/reconcile.py` | Modify | Update import + call site for the promoted name |
| `kdb_benchmark/scorer.py` | Modify | New `_compute_body_emit_set_coverage` helper; rewrite `m5()`; update `_MEASURE_LABELS`; replace verbose-trace block |
| `kdb_benchmark/tests/test_scorer.py` | Modify | Replace `TestM5` and `TestVerboseTraceM5Asymmetry` test classes; add helper-level tests |

**Files NOT touched (per spec D29.6, D29.8):**
- `kdb_compiler/types.py` (RespStatsRecord unchanged — one-way boundary)
- `kdb_compiler/resp_stats_writer.py` (still calls orphaned `body_link_check`; orphan removal is a future task)
- `kdb_compiler/tests/test_validate_compiled_source_response.py` (no test currently uses `_body_wikilink_slugs` by underscore name; confirm in Task 2)

---

## Task 1: Docs-first — North Star + ledger

**Files:**
- Modify: `docs/CODEBASE_OVERVIEW.md` (line 168 M5 row; decisions ledger after D28)
- Modify: `docs/TASKS.md` (Open/In-Progress section)

- [ ] **Step 1: Update M5 row in §7.3 measure table**

In `docs/CODEBASE_OVERVIEW.md`, replace the M5 row at line 168:

```markdown
| **M5** | `body_emit_set_coverage` | fraction of declared `concept_slugs ∪ article_slugs` appearing as `[[slug]]` wikilinks in *other* pages' bodies (self-links excluded) | Output integrity |
```

(Replaces the old row: `| **M5** | `body_link_jaccard` | symmetric Jaccard of declared outgoing_links vs body `[[slug]]` tokens | Output integrity |`)

- [ ] **Step 2: Add D29 to decisions ledger**

In `docs/CODEBASE_OVERVIEW.md`, append D29 after D28 in the decisions ledger:

```markdown
| D29 | 2026-05-10 | M5 retired body_link_jaccard (=1.000-by-construction post-#57) is replaced by `body_emit_set_coverage`: per-source `\|((⋃_p (body_wikilink_slugs(p.body) − {p.slug})) ∩ (concept_slugs ∪ article_slugs))\| / \|concept_slugs ∪ article_slugs\|`, micro-aggregated across the run. Computed in `kdb_benchmark/scorer.py` from captured `parsed_json` — no new RespStatsRecord fields (preserves one-way boundary D25). Self-links excluded to reward cross-page integration. Weight stays 5%. See `docs/task59-m5-replacement-design.md` for full design (D29.1–D29.9 sub-decisions). |
```

- [ ] **Step 3: Add Task #59 row to TASKS.md Open/In-Progress**

In `docs/TASKS.md`, add a row to the Open/In-Progress table (after the #33 row, before the trailing `Open-1..Open-8` entry):

```markdown
| 59 | in-progress   | M5 replacement: `body_emit_set_coverage`                       | Retired body_link_jaccard (=1.000-by-construction post-#57) replaced. See `docs/task59-m5-replacement-design.md` (design) and `docs/task59-m5-replacement-plan.md` (plan) |
```

- [ ] **Step 4: Verify the docs render and references resolve**

```bash
grep -n "body_emit_set_coverage" docs/CODEBASE_OVERVIEW.md docs/TASKS.md
```
Expected: at least 2 hits — one in the §7.3 table, one in D29 ledger entry, one in TASKS.md row. No stale `body_link_jaccard` mention in those locations (other mentions stay in `task19-kpi-design.md` per spec — historical record).

- [ ] **Step 5: Commit**

```bash
git add docs/CODEBASE_OVERVIEW.md docs/TASKS.md
git commit -m "docs(task59): North Star M5 swap + ledger entry

CODEBASE_OVERVIEW.md §7.3 table row updated; D29 added to decisions
ledger. TASKS.md gains #59 row in Open/In-Progress.

Docs-first per Codex review of design v2: docs reflect intended state
before code follows."
```

---

## Task 2: Promote `_body_wikilink_slugs` → `body_wikilink_slugs`

**Files:**
- Modify: `kdb_compiler/validate_compiled_source_response.py:124, 156, 186`
- Modify: `kdb_compiler/reconcile.py:35, 136`

- [ ] **Step 1: Verify no test currently imports the underscore name**

```bash
grep -rn "_body_wikilink_slugs" /home/ftu/Droidoes/Obsidian-KDB/ 2>/dev/null | grep -v __pycache__ | grep -v "\.git/"
```
Expected: 5 hits, all in non-test source files: `validate_compiled_source_response.py:124` (def), `:156`, `:186` (same-file calls), `reconcile.py:35` (import), `:136` (call site). If a test references it, surface that and update accordingly in Step 3.

- [ ] **Step 2: Rename the function definition**

In `kdb_compiler/validate_compiled_source_response.py:124`, change:

```python
def _body_wikilink_slugs(body: str) -> set[str]:
    """Slug set extracted from [[slug]] / [[slug|alias]] / [[slug#h]]
    tokens in `body`, after stripping code spans. Strict kebab-case
    match — out-of-pattern brackets (e.g. [[Foo Bar]]) are silently
    ignored."""
    return set(_WIKILINK_RE.findall(_strip_code(body)))
```

to:

```python
def body_wikilink_slugs(body: str) -> set[str]:
    """Slug set extracted from [[slug]] / [[slug|alias]] / [[slug#h]]
    tokens in `body`, after stripping code spans. Strict kebab-case
    match — out-of-pattern brackets (e.g. [[Foo Bar]]) are silently
    ignored.

    Public utility — also used by `kdb_benchmark.scorer` for M5
    (`body_emit_set_coverage`) computation across the one-way boundary.
    """
    return set(_WIKILINK_RE.findall(_strip_code(body)))
```

- [ ] **Step 3: Update same-file callers**

In `kdb_compiler/validate_compiled_source_response.py`, update lines 156 and 186:

Line 156 (inside `body_link_check`):
```python
        body_links = body_wikilink_slugs(body) if isinstance(body, str) else set()
```
(was: `_body_wikilink_slugs(body)`)

Line 186 (inside `body_link_per_page_asymmetry`):
```python
        body_links = body_wikilink_slugs(body) if isinstance(body, str) else set()
```
(was: `_body_wikilink_slugs(body)`)

- [ ] **Step 4: Update `reconcile.py` import + call**

In `kdb_compiler/reconcile.py:35`, change:
```python
from .validate_compiled_source_response import _body_wikilink_slugs
```
to:
```python
from .validate_compiled_source_response import body_wikilink_slugs
```

And in `kdb_compiler/reconcile.py:136`, change:
```python
        new_links = sorted(_body_wikilink_slugs(body)) if isinstance(body, str) else []
```
to:
```python
        new_links = sorted(body_wikilink_slugs(body)) if isinstance(body, str) else []
```

- [ ] **Step 5: Run the full kdb_compiler test suite**

```bash
cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest kdb_compiler/tests/ -q
```
Expected: all tests pass. Existing `test_body_link_check_*` tests exercise `body_link_check`, which still works (it now calls the renamed `body_wikilink_slugs` internally). `test_reconcile.py` tests for `reconcile_body_links` still pass.

- [ ] **Step 6: Verify no `_body_wikilink_slugs` references remain**

```bash
grep -rn "_body_wikilink_slugs" /home/ftu/Droidoes/Obsidian-KDB/ 2>/dev/null | grep -v __pycache__ | grep -v "\.git/"
```
Expected: zero hits.

- [ ] **Step 7: Commit**

```bash
git add kdb_compiler/validate_compiled_source_response.py kdb_compiler/reconcile.py
git commit -m "refactor(kdb_compiler): promote _body_wikilink_slugs → body_wikilink_slugs

Drops the leading underscore so kdb_benchmark.scorer can import it
across the one-way boundary for the new M5 computation. Internal
callers in validate_compiled_source_response.py and reconcile.py
updated; no behavior change."
```

---

## Task 3: Add `_compute_body_emit_set_coverage` helper in scorer.py

**Files:**
- Modify: `kdb_benchmark/scorer.py` (new helper near other measure helpers, ~line 245)
- Modify: `kdb_benchmark/tests/test_scorer.py` (new `TestComputeBodyEmitSetCoverage` test class)

- [ ] **Step 1: Write the failing test class**

In `kdb_benchmark/tests/test_scorer.py`, before the `TestM5` class (currently at ~line 515), add a new test class:

```python
# ---------------------------------------------------------------------------
# §6a — _compute_body_emit_set_coverage helper (per-source numerator/denominator)
# ---------------------------------------------------------------------------


class TestComputeBodyEmitSetCoverage:
    """The pure helper that computes (num, denom) for one source's parsed_json.
    Per spec §2.2 + §10.2: micro-aggregated, self-links excluded, malformed
    inputs coerced silently (never raises)."""

    def test_happy_path_three_of_four_concepts_in_other_bodies(self):
        # 4 declared concepts + 0 articles; 3 appear in other-page bodies.
        # Self-links (alpha referenced in alpha's own body) excluded.
        parsed = {
            "concept_slugs": ["alpha", "beta", "gamma", "delta"],
            "article_slugs": [],
            "pages": [
                {"slug": "alpha", "page_type": "concept", "body": "see [[alpha]] and [[beta]]"},
                {"slug": "beta", "page_type": "concept", "body": "[[gamma]]"},
                {"slug": "gamma", "page_type": "concept", "body": "no links"},
                {"slug": "summary-foo", "page_type": "summary", "body": "[[delta]]"},
            ],
        }
        num, denom = scorer._compute_body_emit_set_coverage(parsed)
        # body_emit_links across other-pages: {beta} from alpha-body (self-link [[alpha]] excluded),
        # {gamma} from beta-body, {} from gamma-body, {delta} from summary-foo-body.
        # Union: {beta, gamma, delta}. Intersected with declared {alpha, beta, gamma, delta} = 3.
        assert (num, denom) == (3, 4)

    def test_emit_set_unions_concept_and_article_slugs(self):
        parsed = {
            "concept_slugs": ["c1"],
            "article_slugs": ["a1"],
            "pages": [
                {"slug": "summary-x", "page_type": "summary", "body": "[[c1]] and [[a1]]"},
                {"slug": "c1", "page_type": "concept", "body": ""},
                {"slug": "a1", "page_type": "article", "body": ""},
            ],
        }
        num, denom = scorer._compute_body_emit_set_coverage(parsed)
        assert (num, denom) == (2, 2)

    def test_self_link_excluded(self):
        # Single concept; only reference is in its own body → self-link excluded → num=0.
        parsed = {
            "concept_slugs": ["alpha"],
            "article_slugs": [],
            "pages": [
                {"slug": "alpha", "page_type": "concept", "body": "I am [[alpha]]"},
            ],
        }
        num, denom = scorer._compute_body_emit_set_coverage(parsed)
        assert (num, denom) == (0, 1)

    def test_spurious_wikilink_outside_emit_set_does_not_count(self):
        parsed = {
            "concept_slugs": ["alpha"],
            "article_slugs": [],
            "pages": [
                {"slug": "summary-x", "page_type": "summary", "body": "[[alpha]] [[unknown]]"},
            ],
        }
        num, denom = scorer._compute_body_emit_set_coverage(parsed)
        # [[unknown]] is not in declared emit-set, doesn't count toward numerator.
        assert (num, denom) == (1, 1)

    def test_empty_emit_set_returns_zero_zero(self):
        parsed = {
            "concept_slugs": [],
            "article_slugs": [],
            "pages": [
                {"slug": "summary-x", "page_type": "summary", "body": "[[anything]]"},
            ],
        }
        num, denom = scorer._compute_body_emit_set_coverage(parsed)
        assert (num, denom) == (0, 0)

    def test_missing_concept_and_article_keys_returns_zero_zero(self):
        parsed = {"pages": [{"slug": "x", "page_type": "summary", "body": "[[anything]]"}]}
        num, denom = scorer._compute_body_emit_set_coverage(parsed)
        assert (num, denom) == (0, 0)

    def test_non_list_concept_slugs_coerced_to_empty(self):
        # Round 4 CW2 convention: non-list slug fields coerce to empty
        # (avoid set("foo") char-slug trap).
        parsed = {
            "concept_slugs": "alpha",  # string, not list
            "article_slugs": [],
            "pages": [{"slug": "x", "page_type": "summary", "body": "[[alpha]]"}],
        }
        num, denom = scorer._compute_body_emit_set_coverage(parsed)
        assert (num, denom) == (0, 0)

    def test_non_string_slug_member_dropped(self):
        parsed = {
            "concept_slugs": ["alpha", 42, None, "beta"],
            "article_slugs": [],
            "pages": [{"slug": "x", "page_type": "summary", "body": "[[alpha]] [[beta]]"}],
        }
        num, denom = scorer._compute_body_emit_set_coverage(parsed)
        # Emit set = {alpha, beta} after dropping non-strings.
        assert (num, denom) == (2, 2)

    def test_non_string_body_yields_no_links(self):
        parsed = {
            "concept_slugs": ["alpha"],
            "article_slugs": [],
            "pages": [{"slug": "x", "page_type": "summary", "body": None}],
        }
        num, denom = scorer._compute_body_emit_set_coverage(parsed)
        assert (num, denom) == (0, 1)

    def test_non_string_page_slug_skips_self_link_subtraction(self):
        # Page with non-string slug → no self-link subtraction for that page,
        # but body wikilinks still contribute to the union.
        parsed = {
            "concept_slugs": ["alpha"],
            "article_slugs": [],
            "pages": [{"slug": 42, "page_type": "concept", "body": "[[alpha]]"}],
        }
        num, denom = scorer._compute_body_emit_set_coverage(parsed)
        # No self-link subtraction (slug isn't a string), so [[alpha]] counts.
        assert (num, denom) == (1, 1)

    def test_pages_not_a_list_returns_zero_emit_set_size(self):
        parsed = {
            "concept_slugs": ["alpha"],
            "article_slugs": ["beta"],
            "pages": "not-a-list",
        }
        num, denom = scorer._compute_body_emit_set_coverage(parsed)
        # Emit set still has size 2 (declared); no pages → no body links → num=0.
        assert (num, denom) == (0, 2)

    def test_same_slug_in_multiple_bodies_counted_once_set_semantics(self):
        parsed = {
            "concept_slugs": ["alpha", "beta"],
            "article_slugs": [],
            "pages": [
                {"slug": "x", "page_type": "summary", "body": "[[alpha]]"},
                {"slug": "y", "page_type": "summary", "body": "[[alpha]] [[beta]]"},
            ],
        }
        num, denom = scorer._compute_body_emit_set_coverage(parsed)
        # Union of body-emit-links across pages: {alpha, beta}.
        assert (num, denom) == (2, 2)

    def test_helper_never_raises_on_garbage(self):
        # Garbage at every layer.
        for parsed in [{}, {"pages": None}, {"concept_slugs": None, "article_slugs": None}]:
            num, denom = scorer._compute_body_emit_set_coverage(parsed)
            assert isinstance(num, int) and isinstance(denom, int)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest kdb_benchmark/tests/test_scorer.py::TestComputeBodyEmitSetCoverage -v
```
Expected: all 12 tests fail with `ImportError` or `AttributeError` — `_compute_body_emit_set_coverage` does not yet exist.

- [ ] **Step 3: Implement the helper in scorer.py**

In `kdb_benchmark/scorer.py`, after the `_slug_jaccard` helper (around line 295, before `m4()`), add:

```python
def _compute_body_emit_set_coverage(parsed_json: dict) -> tuple[int, int]:
    """Per-source `(numerator, denominator)` for M5 body_emit_set_coverage.

    numerator   = |⋃_p (body_wikilink_slugs(p.body) − {p.slug})| ∩ declared_emit_set
    denominator = |declared_emit_set|

    where declared_emit_set = set(concept_slugs) ∪ set(article_slugs).

    Self-links excluded per page (Codex 2026-05-10 review): a page that
    references its own slug isn't "integrating" the concept — it's a
    tautology. Subtraction rewards cross-page integration only.

    Tolerant — never raises (per §10.2 plan-stage clarifications):
      * concept_slugs / article_slugs non-list → empty set
      * non-string slug members → dropped
      * pages non-list → no body links contribute
      * non-string body → page contributes zero links
      * non-string page slug → no self-link subtraction for that page
      * any malformed nested value → silently absorbed
    """
    from kdb_compiler.validate_compiled_source_response import body_wikilink_slugs

    def _slugs(field) -> set[str]:
        if not isinstance(field, list):
            return set()
        return {s for s in field if isinstance(s, str)}

    declared = _slugs(parsed_json.get("concept_slugs")) | _slugs(parsed_json.get("article_slugs"))
    denom = len(declared)

    pages = parsed_json.get("pages")
    if not isinstance(pages, list):
        return (0, denom)

    body_emit_links: set[str] = set()
    for p in pages:
        if not isinstance(p, dict):
            continue
        body = p.get("body")
        if not isinstance(body, str):
            continue
        page_slug = p.get("slug")
        page_links = body_wikilink_slugs(body)
        if isinstance(page_slug, str):
            page_links = page_links - {page_slug}
        body_emit_links |= page_links

    num = len(body_emit_links & declared)
    return (num, denom)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest kdb_benchmark/tests/test_scorer.py::TestComputeBodyEmitSetCoverage -v
```
Expected: all 12 tests pass.

- [ ] **Step 5: Run the full scorer test suite to confirm no regression**

```bash
cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest kdb_benchmark/tests/test_scorer.py -q
```
Expected: existing `TestM5` and `TestVerboseTraceM5Asymmetry` still pass (they test the OLD `m5()` and trace, which haven't changed yet). New 12 tests pass. Total green.

- [ ] **Step 6: Commit**

```bash
git add kdb_benchmark/scorer.py kdb_benchmark/tests/test_scorer.py
git commit -m "feat(task59): add _compute_body_emit_set_coverage helper

Pure helper that computes (numerator, denominator) for a single source's
parsed_json. Self-links excluded per page (Codex review); malformed
inputs coerced silently per §10.2 conventions.

12 unit tests covering happy path, self-link exclusion, emit-set
intersection, malformed-input coercion, set-semantics dedup, and
zero-denom edges. Helper not yet wired into m5() — that's Task 4."
```

---

## Task 4: Rewrite `m5()` and update `_MEASURE_LABELS`

**Files:**
- Modify: `kdb_benchmark/scorer.py:320-330` (m5() function)
- Modify: `kdb_benchmark/scorer.py:521` (_MEASURE_LABELS dict)
- Modify: `kdb_benchmark/tests/test_scorer.py` (replace `TestM5` class)

- [ ] **Step 1: Replace `TestM5` with new tests reading from parsed_json**

In `kdb_benchmark/tests/test_scorer.py`, find the existing `TestM5` class (around line 515) and replace it entirely with:

```python
# ---------------------------------------------------------------------------
# §6 — M5 body_emit_set_coverage (weight 5%)
# ---------------------------------------------------------------------------


class TestM5:
    """M5 reads parsed_json from each parse-pass record (per §10.1: matches
    M2/M3 _is_parse_pass gate; schema_ok not required) and aggregates
    Σnum / Σdenom across sources."""

    def _record_with_parsed(self, source_id: str, parsed_json: dict, parse_ok: bool = True):
        """Build a fake record with parsed_json. Schema_ok left True;
        parse-pass gate is what matters per §10.1."""
        return fake_record(
            source_id=source_id,
            parse_ok=parse_ok,
            schema_ok=True,
            parsed_json=parsed_json,
        )

    def test_m5_aggregates_coverage_across_sources(self):
        # Source 1: 3 of 4 declared concepts integrated → (3, 4)
        # Source 2: 1 of 2 declared concepts integrated → (1, 2)
        # Aggregate: (4, 6) → 0.6667
        records = [
            self._record_with_parsed("s1", {
                "concept_slugs": ["a", "b", "c", "d"],
                "article_slugs": [],
                "pages": [
                    {"slug": "summary-1", "page_type": "summary", "body": "[[a]] [[b]] [[c]]"},
                ],
            }),
            self._record_with_parsed("s2", {
                "concept_slugs": ["x", "y"],
                "article_slugs": [],
                "pages": [
                    {"slug": "summary-2", "page_type": "summary", "body": "[[x]]"},
                ],
            }),
        ]
        score = scorer.m5(records)
        assert score.name == "M5"
        assert (score.numerator, score.denominator) == (4, 6)
        assert abs(score.rate - (4 / 6)) < 1e-9
        assert score.weight == 0.05

    def test_m5_zero_denom_scores_zero(self):
        """MF6: model emits empty emit-set → denominator 0 → rate = 0.0
        (model-controlled penalty)."""
        records = [
            self._record_with_parsed("s1", {
                "concept_slugs": [],
                "article_slugs": [],
                "pages": [{"slug": "summary-1", "page_type": "summary", "body": ""}],
            }),
        ]
        score = scorer.m5(records)
        assert score.numerator == 0
        assert score.denominator == 0
        assert score.rate == 0.0

    def test_m5_skips_parse_fail_records(self):
        """§10.1: only parse-pass records contribute (matches _is_parse_pass)."""
        records = [
            self._record_with_parsed("s1", {
                "concept_slugs": ["a"],
                "article_slugs": [],
                "pages": [{"slug": "summary-1", "page_type": "summary", "body": "[[a]]"}],
            }),
            # Parse-fail record: contributes nothing, regardless of parsed_json.
            fake_record(source_id="s2", parse_ok=False, schema_ok=False, parsed_json={
                "concept_slugs": ["spurious"],
                "article_slugs": [],
                "pages": [],
            }),
        ]
        score = scorer.m5(records)
        # Only s1's (1, 1) contributes.
        assert (score.numerator, score.denominator) == (1, 1)

    def test_m5_includes_parse_pass_schema_fail_records(self):
        """§10.1: schema_ok NOT required. A parse-pass / schema-fail record
        is still scored (matches M2/M3 behavior at scorer.py:256)."""
        records = [
            self._record_with_parsed("s1", {
                "concept_slugs": ["a"],
                "article_slugs": [],
                "pages": [{"slug": "summary-1", "page_type": "summary", "body": "[[a]]"}],
            }, parse_ok=True),
        ]
        # Override schema_ok to False on the second record.
        bad_schema = fake_record(
            source_id="s2",
            parse_ok=True,
            schema_ok=False,
            parsed_json={
                "concept_slugs": ["b"],
                "article_slugs": [],
                "pages": [{"slug": "summary-2", "page_type": "summary", "body": "[[b]]"}],
            },
        )
        records.append(bad_schema)
        score = scorer.m5(records)
        # Both contribute: (1+1, 1+1) = (2, 2).
        assert (score.numerator, score.denominator) == (2, 2)
```

- [ ] **Step 2: Confirm `fake_record` already supports `parsed_json` kwarg**

The existing `fake_record(...)` helper at `kdb_benchmark/tests/test_scorer.py:78` already accepts `parsed_json: dict | None = None` and passes it through into the returned dict (line 126). No edits needed — just verify:

```bash
grep -n "parsed_json" /home/ftu/Droidoes/Obsidian-KDB/kdb_benchmark/tests/test_scorer.py | head -5
```
Expected: hits at the function signature (line ~78) and inside the returned dict (line ~126). Test code in this task can pass `parsed_json={...}` directly into `fake_record(...)`.

- [ ] **Step 3: Run new TestM5 tests to verify they fail**

```bash
cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest kdb_benchmark/tests/test_scorer.py::TestM5 -v
```
Expected: tests fail because the existing `m5()` reads `body_link_intersection` / `body_link_union` (which we're not setting) and gets 0/0 → 0.0 instead of the expected coverage values.

- [ ] **Step 4: Rewrite `m5()` in scorer.py**

In `kdb_benchmark/scorer.py:320-330`, replace the existing `m5()`:

```python
def m5(records: list[dict]) -> MeasureScore:
    """M5 — body_emit_set_coverage (weight 5%, Output Integrity).

    Per §7.3 + Task #59 design: per-source coverage of declared
    `concept_slugs ∪ article_slugs` by body wikilinks across other pages
    (self-links excluded). Micro-aggregated:

      Σ |⋃_p (body_wikilink_slugs(p.body) − {p.slug})| ∩ declared_emit_set
      ────────────────────────────────────────────────────────────────────
      Σ |declared_emit_set|

    over parse-pass records (matches M2/M3 `_is_parse_pass` gate; §10.1).
    Round 4 MF6: zero-denom → 0.0 (model-controlled penalty).
    """
    num_total = 0
    denom_total = 0
    for r in records:
        if not _is_parse_pass(r):
            continue
        pj = r.get("parsed_json")
        if not isinstance(pj, dict):
            continue
        n, d = _compute_body_emit_set_coverage(pj)
        num_total += n
        denom_total += d
    rate = (num_total / denom_total) if denom_total else 0.0
    return MeasureScore(name="M5", numerator=num_total, denominator=denom_total, rate=rate, weight=0.05)
```

- [ ] **Step 5: Update `_MEASURE_LABELS` dict**

In `kdb_benchmark/scorer.py:521`, change line 530:

```python
    "M5": "body_emit_set_coverage",
```
(was: `"M5": "body_link_jaccard",`)

- [ ] **Step 6: Run TestM5 tests to verify they pass**

```bash
cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest kdb_benchmark/tests/test_scorer.py::TestM5 -v
```
Expected: all 4 new TestM5 tests pass.

- [ ] **Step 7: Run full scorer test suite — `TestVerboseTraceM5Asymmetry` will fail**

```bash
cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest kdb_benchmark/tests/test_scorer.py -q
```
Expected: `TestVerboseTraceM5Asymmetry` tests fail (they assume the old per-page-asymmetry trace format and feed `body_link_intersection`/`body_link_union` — these tests are replaced in Task 5). All other tests green.

This intermediate failure is expected and is fixed in Task 5. Do **not** commit yet — the trace block is still in an inconsistent state. Continue to Task 5 immediately and commit Tasks 4 + 5 together.

---

## Task 5: Replace verbose-trace M5 block

**Files:**
- Modify: `kdb_benchmark/scorer.py:591-613` (replace `_m5_per_page_asymmetry_lines` helper)
- Modify: `kdb_benchmark/scorer.py:642-643` (update wiring inside `_emit_verbose_trace`)
- Modify: `kdb_benchmark/tests/test_scorer.py:967-1033` (replace `TestVerboseTraceM5Asymmetry` class)

**Architecture context** (verified pre-task): `_emit_verbose_trace` has signature `(records: list[dict], rs: RunScore, sink: list[str]) -> None` at `scorer.py:616` — `records` is already passed in directly, so the new helper can mirror the existing `_m5_per_page_asymmetry_lines(records) -> list[str]` pattern at `scorer.py:591`. No `RunScore` structural change needed. Existing tests use `score_run(tmp_path, run_id, model_id, trace_sink=sink)` (the canonical disk-backed entry point at `scorer.py:443`), with records written via `_write_records(tmp_path, run_id, [rec])`.

- [ ] **Step 1: Replace `TestVerboseTraceM5Asymmetry` with new coverage trace tests**

In `kdb_benchmark/tests/test_scorer.py`, find the `TestVerboseTraceM5Asymmetry` class (around line 967) and replace it entirely (and remove the now-unused `_record_with_pages(...)` helper at ~line 950 that took `body_link_intersection` / `body_link_union` kwargs — verify it's not used elsewhere first):

```python
# ---------------------------------------------------------------------------
# §9b — verbose trace M5 coverage detail (Task #59)
# ---------------------------------------------------------------------------


class TestVerboseTraceM5Coverage:
    """Per-source coverage detail under the M5 line (replaces the retired
    per-page asymmetry block). When M5 < 1.0, the trace lists which sources
    had un-integrated declared slugs and which slugs are missing from bodies.
    Tests use the canonical score_run(tmp_path, ..., trace_sink=...) entry
    point with records written to disk via _write_records()."""

    def _record_with_parsed(
        self,
        source_id: str,
        *,
        concept_slugs: list[str],
        article_slugs: list[str],
        pages: list[dict],
    ) -> dict:
        return fake_record(
            source_id=source_id,
            parse_ok=True,
            schema_ok=True,
            parsed_json={
                "concept_slugs": concept_slugs,
                "article_slugs": article_slugs,
                "pages": pages,
            },
        )

    def test_trace_omits_m5_block_when_perfect(self, tmp_path):
        """M5 = 1.0 → no per-source coverage block in the trace."""
        rec = self._record_with_parsed(
            "s1",
            concept_slugs=["a"],
            article_slugs=[],
            pages=[{"slug": "summary-1", "page_type": "summary", "body": "[[a]]"}],
        )
        _write_records(tmp_path, "haiku-test", [rec])
        sink: list[str] = []
        run = scorer.score_run(
            tmp_path, "haiku-test", "haiku-4.5", trace_sink=sink,
        )
        assert run.measures["M5"].rate == 1.0
        joined = "\n".join(sink)
        assert "per-source M5 coverage" not in joined

    def test_trace_emits_m5_block_when_partial_coverage(self, tmp_path):
        """M5 < 1.0 → block names each below-100%-coverage source with its
        missing (declared but un-integrated) slugs in sorted order."""
        rec = self._record_with_parsed(
            "src-foo",
            concept_slugs=["alpha", "beta", "gamma"],
            article_slugs=[],
            pages=[{"slug": "summary-1", "page_type": "summary", "body": "[[alpha]]"}],
        )
        _write_records(tmp_path, "haiku-test", [rec])
        sink: list[str] = []
        run = scorer.score_run(
            tmp_path, "haiku-test", "haiku-4.5", trace_sink=sink,
        )
        assert run.measures["M5"].rate == pytest.approx(1 / 3)
        joined = "\n".join(sink)
        assert "per-source M5 coverage:" in joined
        assert "src-foo" in joined
        # Missing slugs sorted: beta, gamma.
        assert "['beta', 'gamma']" in joined

    def test_trace_reflects_self_link_exclusion(self, tmp_path):
        """A page linking to its own slug doesn't count; trace lists that
        slug as missing."""
        rec = self._record_with_parsed(
            "src-bar",
            concept_slugs=["alpha", "beta"],
            article_slugs=[],
            pages=[
                {"slug": "alpha", "page_type": "concept", "body": "I am [[alpha]]"},
                {"slug": "summary-1", "page_type": "summary", "body": "[[beta]]"},
            ],
        )
        _write_records(tmp_path, "haiku-test", [rec])
        sink: list[str] = []
        run = scorer.score_run(
            tmp_path, "haiku-test", "haiku-4.5", trace_sink=sink,
        )
        # Self-link excluded: only beta integrated → 1/2.
        assert run.measures["M5"].numerator == 1
        assert run.measures["M5"].denominator == 2
        joined = "\n".join(sink)
        assert "per-source M5 coverage:" in joined
        assert "src-bar" in joined
        # alpha is missing because its only reference was a self-link.
        assert "['alpha']" in joined

    def test_trace_omits_block_when_zero_denom(self, tmp_path):
        """Empty emit-set → rate=0.0 (MF6) but every source has d=0; the
        helper finds nothing to report → no header, no body."""
        rec = self._record_with_parsed(
            "s1",
            concept_slugs=[],
            article_slugs=[],
            pages=[{"slug": "summary-1", "page_type": "summary", "body": "no links"}],
        )
        _write_records(tmp_path, "haiku-test", [rec])
        sink: list[str] = []
        run = scorer.score_run(
            tmp_path, "haiku-test", "haiku-4.5", trace_sink=sink,
        )
        assert run.measures["M5"].rate == 0.0
        joined = "\n".join(sink)
        assert "per-source M5 coverage" not in joined
```

**Important:** the deleted `_record_with_pages(...)` helper at ~line 950 (with `body_link_intersection` / `body_link_union` kwargs) is no longer needed. Before removing it, grep for other callers:

```bash
grep -n "_record_with_pages" /home/ftu/Droidoes/Obsidian-KDB/kdb_benchmark/tests/test_scorer.py
```
If only the old `TestVerboseTraceM5Asymmetry` used it, delete it. If other tests use it, keep it (it's only a test fixture; orphaning is fine).

- [ ] **Step 2: Replace the helper in scorer.py**

In `kdb_benchmark/scorer.py:591-613`, replace the existing `_m5_per_page_asymmetry_lines(records)` function with the new coverage helper:

```python
def _m5_per_source_coverage_lines(records: list[dict]) -> list[str]:
    """Per-source coverage detail under the M5 line, emitted only when M5
    rate < 1.0 (Task #59, replaces the retired per-page asymmetry helper).

    For each parse-pass record with denom > 0 and num < denom, list the
    source_id, the integrated count vs declared count, and the sorted set
    of declared emit-set slugs that did NOT appear as body wikilinks in
    any other page. Self-links are already excluded inside
    _compute_body_emit_set_coverage. Returns empty list (caller emits
    nothing — not even a header) when no source falls below 100%.
    """
    body: list[str] = []
    for r in records:
        if not _is_parse_pass(r):
            continue
        parsed = r.get("parsed_json")
        if not isinstance(parsed, dict):
            continue
        n, d = _compute_body_emit_set_coverage(parsed)
        if d == 0 or n == d:
            continue

        def _slugs(field) -> set[str]:
            if not isinstance(field, list):
                return set()
            return {s for s in field if isinstance(s, str)}

        declared = _slugs(parsed.get("concept_slugs")) | _slugs(parsed.get("article_slugs"))
        body_emit_links: set[str] = set()
        pages = parsed.get("pages")
        if isinstance(pages, list):
            for p in pages:
                if not isinstance(p, dict):
                    continue
                page_body = p.get("body")
                if not isinstance(page_body, str):
                    continue
                page_links = body_wikilink_slugs(page_body)
                page_slug = p.get("slug")
                if isinstance(page_slug, str):
                    page_links = page_links - {page_slug}
                body_emit_links |= page_links
        missing = sorted(declared - body_emit_links)
        sid = r.get("source_id", "<unknown>")
        body.append(f"[verbose]     {sid}: {n}/{d} integrated, missing: {missing}")

    if not body:
        return []
    return ["[verbose]   per-source M5 coverage:"] + body
```

- [ ] **Step 2a: Update the import block at the top of scorer.py**

Open `kdb_benchmark/scorer.py` and inspect the imports near the top. Two explicit edits:

```bash
grep -n "from kdb_compiler" /home/ftu/Droidoes/Obsidian-KDB/kdb_benchmark/scorer.py
```

1. **Remove `body_link_per_page_asymmetry`** from the import line if present — the new helper does not call it (the per-page asymmetry helper is now orphaned in `kdb_compiler` per D29.8).
2. **Add `body_wikilink_slugs`** to the import line so the new `_m5_per_source_coverage_lines` helper can use it without re-importing locally. The expected resulting line:

```python
from kdb_compiler.validate_compiled_source_response import body_wikilink_slugs, check_compiled_source
```

(Adjust the rest of the imported names — `check_compiled_source` is already used by `s0()` at line 165 — to match what's currently imported. The point is `body_wikilink_slugs` is now imported at module top, and `body_link_per_page_asymmetry` is removed.)

- [ ] **Step 3: Update the wiring in `_emit_verbose_trace`**

In `kdb_benchmark/scorer.py:642-643`, change:

```python
        elif key == "M5" and ms.rate is not None and ms.rate < 1.0:
            sink.extend(_m5_per_page_asymmetry_lines(records))
```

to:

```python
        elif key == "M5" and ms.rate is not None and ms.rate < 1.0:
            sink.extend(_m5_per_source_coverage_lines(records))
```

- [ ] **Step 4: Run the trace tests + full scorer suite**

```bash
cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest kdb_benchmark/tests/test_scorer.py -q
```
Expected: all tests pass — new `TestM5`, new `TestVerboseTraceM5Coverage`, new `TestComputeBodyEmitSetCoverage`, plus all unrelated tests.

- [ ] **Step 5: Verify no `body_link_jaccard` references remain in scorer + scorer tests**

```bash
grep -n "body_link_jaccard\|_m5_per_page_asymmetry_lines\|body_link_per_page_asymmetry" /home/ftu/Droidoes/Obsidian-KDB/kdb_benchmark/scorer.py /home/ftu/Droidoes/Obsidian-KDB/kdb_benchmark/tests/test_scorer.py
```
Expected: zero hits in scorer.py / test_scorer.py. The `body_link_per_page_asymmetry` helper is **still defined** in `kdb_compiler/validate_compiled_source_response.py:162` (orphaned per D29.8 — preserved for future cleanup); that grep is scoped to scorer files only and should pass.

- [ ] **Step 6: Commit Tasks 4 + 5 together**

```bash
git add kdb_benchmark/scorer.py kdb_benchmark/tests/test_scorer.py
git commit -m "feat(task59): rewrite m5() as body_emit_set_coverage; replace verbose trace

m5() now reads parsed_json from each parse-pass record (matches M2/M3
_is_parse_pass gate) and aggregates Σnum / Σdenom via the
_compute_body_emit_set_coverage helper. _MEASURE_LABELS reflects new
name. Verbose trace replaces the retired per-page asymmetry block with
per-source coverage detail (which sources fell short of 100%, which
declared slugs are missing from bodies).

TestM5 + TestVerboseTraceM5Coverage rewritten for parsed_json-driven
fixtures; TestComputeBodyEmitSetCoverage from prior commit unchanged.

Closes the M5 swap. body_link_check / body_link_intersection /
body_link_union remain in kdb_compiler as orphans per D29.8 (future
cleanup task)."
```

---

## Task 6: Live verification fire (user-fired per `feedback_user_fires_api_cost_runs`)

**Files:** None modified — verification only.

- [ ] **Step 1: Surface the verification command for the user to run**

Recommend: `haiku-4.5` (cheapest API tier; well-characterized; consistent baseline). Estimated cost ~$0.10 across 5 sources.

Present this command to the user and **wait for them to run it themselves**:

```bash
cd /home/ftu/Droidoes/Obsidian-KDB && kdb-benchmark --models haiku-4.5 --sources benchmark/sources --no-merge
```

(The `--no-merge` flag isolates the new-M5 fire from the historical scorecard chain so the comparison is clean.)

- [ ] **Step 2: User runs the command; we read the output**

When the user reports completion, read the latest run's scorecard:

```bash
ls -1t /home/ftu/Droidoes/Obsidian-KDB/benchmark/scores/runs/ | head -1
```
Then read the `.txt` sidecar of that scorecard:

```bash
cat /home/ftu/Droidoes/Obsidian-KDB/benchmark/scores/runs/<scorecard_id>.txt
```

- [ ] **Step 3: Sanity-check the new M5 reading**

Confirm (per Codex 2026-05-10 plan review — closure criterion is structural, not a specific numeric value):

- `M5` appears as `body_emit_set_coverage` in the trace (label and name swap landed).
- M5 numerator and denominator are plausible: denominator equals total `|concept_slugs ∪ article_slugs|` summed across sources; numerator ≤ denominator; both are integers.
- If M5 rate < 1.0, the verbose-trace per-source coverage detail lists the under-100% sources with their missing slugs in sorted order.
- Self-link exclusion behavior is reflected: per-source coverage detail does NOT credit a page's own slug as "integrated."
- The scorecard headline `final_score` is in a sane range (haiku-4.5 has historically scored ~0.85–0.997).

**M5 = 1.000 is NOT necessarily a bug.** With this metric, a model can legitimately hit 1.0 if every declared concept and article appears as a wikilink in some other page's body. Don't chase a non-1.000 result — chase structural correctness:
- If you see M5 = 1.000, sanity-check by reading at least one per-source coverage trace line if any partial-coverage source exists. If all 5 sources have d > 0 and n == d, the model genuinely covered everything — that's a clean reading.
- If you see M5 = 1.000 AND `M5 numerator / denominator = 0/0`, something IS wrong (capture-full not on, or `parsed_json` not flowing through). That's a debug case.
- A non-1.000 result is *useful for confidence* but not *required* for closure.

---

## Task 7: Close #59 in TASKS.md

**Files:**
- Modify: `docs/TASKS.md`

- [ ] **Step 1: Collect implementation commit SHAs**

```bash
git log --oneline -10
```
Note the commit SHAs from Tasks 1, 2, 3, 4+5. Format: `cdea367` (spec — already landed); Task 1 (`<sha-1>`), Task 2 (`<sha-2>`), Task 3 (`<sha-3>`), Tasks 4+5 (`<sha-45>`).

- [ ] **Step 2: Move #59 row to Closed**

In `docs/TASKS.md`, remove the #59 row from Open/In-Progress (added in Task 1) and add a row to the Closed table:

```markdown
| 59 | M5 replacement: `body_emit_set_coverage`                       | `<sha-1>` (docs-first) → `<sha-2>` (helper promotion) → `<sha-3>` (new helper) → `<sha-45>` (m5 rewrite + trace). Retired body_link_jaccard (M5=1.000-by-construction post-#57) replaced by per-source coverage of declared emit-set in body wikilinks (self-links excluded), computed in scorer from parsed_json. See `docs/task59-m5-replacement-design.md` (D29.1–D29.9) and `docs/task59-m5-replacement-plan.md`. Live-verified on haiku-4.5 / canonical 5-source corpus. |
```

(Use the actual SHAs from Step 1.)

- [ ] **Step 3: Commit close-out**

```bash
git add docs/TASKS.md
git commit -m "docs(TASKS): close #59 — M5 replacement landed

body_link_jaccard → body_emit_set_coverage swap complete. Live-verified
on haiku-4.5 / canonical 5-source corpus."
```

- [ ] **Step 4: Verify branch state**

```bash
git status --short --branch
git log --oneline -8
```
Expected: working tree clean; 5+ new commits on top of `cdea367` (the spec commit).

---

## Self-Review (post-plan)

Done. Notes for execution:

- **Task ordering rationale**: docs-first (1) sets the documented expectation; rename (2) before scorer work (3-5) so scorer can import the public name; helper before m5() rewrite so m5() can call it; m5() before trace because trace depends on m5() output. Verification (6) before close-out (7) because the live fire can surface defects.
- **Tasks 4 and 5 commit together** because Task 4 leaves the verbose trace block in a transitionally-broken state. Don't commit between them.
- **Task 6 is user-driven** per memory `feedback_user_fires_api_cost_runs`. Do NOT auto-fire the benchmark.
- **Task 7's commit message** carries the multi-commit lineage — important for the ledger's "closure proof" convention.
- **Verification criteria** (spec §9) are checked organically across Tasks 5 (no `body_link_jaccard` in scorer/tests), 6 (live fire produces non-1.000 M5), and 7 (TASKS.md closure with SHAs).

---

**Plan complete and committed-ready.** Save location: `docs/task59-m5-replacement-plan.md` (project convention).

**Two execution options:**

1. **Subagent-Driven (recommended)** — dispatch fresh subagent per task; review between tasks; fast iteration; clean context per task.
2. **Inline Execution** — execute tasks in this session; batch with checkpoints for review.

**Which approach?**
