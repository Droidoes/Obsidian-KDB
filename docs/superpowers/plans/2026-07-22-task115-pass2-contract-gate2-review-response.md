# Task #115 — Gate-2 code review: resolution of Codex findings (round 1 → round 2)

> Response to `docs/superpowers/plans/2026-07-22-task115-pass2-contract-gate2-code-review-codex.md` (verdict: GO-WITH-CHANGES).
> All 7 findings folded into the same uncommitted Gate-2 diff on branch `feat/115-pass2-contract` (base `e9ca323`).
> **Verification after fixes:** full suite **1376 passed / 1 live-skip / 1 deselected** via `.venv/bin/python -m pytest` (pre-review: 1360; +16 new regression tests, net of edits).
>
> **For the round-2 reviewer:** re-review the working-tree diff (`git diff HEAD`) with focus on the files cited per finding. Confirm each resolution is correct and complete, and re-run the deterministic suite (`.venv/bin/python -m pytest -q -m 'not bench and not live'`). Write the round-2 verdict to `docs/superpowers/plans/2026-07-22-task115-pass2-contract-gate2-code-review-codex-v2.md`.

---

## F3 [High] — terminal post-call semantic rejection now classified `validate` on BOTH surfaces

**What was wrong:** `compile_one`'s terminal semantic-failure branch set `state["error"]` and returned without `_set_failure`, so the persisted record carried `failure_stage=None` and `compile_source` mapped the outer result to generic `"compile"`.

**Resolution:**
- `compiler/compiler.py` (terminal semantic branch, ~line 446): now calls `_set_failure(state, "validate", "SemanticCheckError", state["semantic_errors"][0])` before returning. `"SemanticCheckError"` is a synthetic exception_type, mirroring the `"TokenOverrun"` precedent for truncation. `semantic_errors` remains the structured detail surface; `compile_source`'s existing `inner == "validate" → outer "validate"` mapping (compiler.py:~668) now engages for this path.
- Docstrings updated where the old "semantic failures are always outside the triplet" claim lived:
  - `compiler/compiler.py` — `FailureTelemetry` class docstring: schema failures stay out of the triplet; validation-stage rejections (pre-call `PathError` route + terminal semantic rejection) populate it with stage `"validate"`.
  - `common/types.py` — `RespStatsRecord` docstring: same scope clarification.

**Tests:** `compiler/tests/test_compile_source.py::test_postcall_semantic_failure_inner_and_outer_validate` — schema-valid payload with a wrong derived summary slug; asserts outer `failure_stage == "validate"` + `exception_type == "SemanticCheckError"`, and on the persisted record: `failure_stage == "validate"`, `failure_exception_type == "SemanticCheckError"`, non-empty `failure_exception_message`, `schema_ok is True`, `semantic_ok is False`, non-empty `semantic_errors`. (Record field name is `failure_exception_message`, per `common/llm_telemetry.py:206-208`.)

## F4 [High] — canonical body rewriting aligned with the extraction token contract

**What was wrong:** `_remap_body_wikilinks` did not match `[[slug#heading]]` at all, and rewrote escaped `\[[...]]` and fenced/inline-code occurrences — while the compiler/graph extractors treat heading forms as links and ignore escaped/code occurrences.

**Resolution (`compiler/canonicalize.py`):**
- New `_WIKILINK_RE`: `(?<!\\)\[\[([^\[\]|#]+?)(#[^|\]]*)?(?:\|([^\]]*))?\]\]` — negative lookbehind for the escape backslash, optional heading group, optional display group. The target class deliberately stays broader than the extractor's strict kebab `_SLUG_RE` (remap normalizes arbitrary alias surface forms; comment says so).
- `_FENCED_CODE_RE` / `_INLINE_CODE_RE` added (same pair as `validate_source_response._strip_code`, applied in the same order: fenced first, then inline within non-fenced segments).
- `_remap_body_wikilinks` now segments the body on code spans and remaps ONLY outside them; code spans pass through byte-identical. Rebuild emits `[[canonical#heading|display]]` preserving heading suffix and display text verbatim.
- Verified against Codex's repro cases: `[[aapl#Revenue]]` → `[[apple-inc#Revenue]]`; `\[[aapl]]` and `` `[[aapl]]` `` untouched.

**Tests (6 new, `compiler/tests/test_canonicalize_algorithm.py::TestBodyWikilinkRemap`):** heading suffix remapped+preserved, heading+display preserved, escaped link not remapped, inline code not remapped, fenced block not remapped, and `test_heading_form_edge_consistent_with_extractor` (post-remap body yields exactly `{canonical}` from `body_wikilink_slugs`).

## F5 [Medium] — underivable stems fail CLOSED in aggregate validation + replay (no more `PathError` escapes)

**Resolution:**
- `compiler/validate_compile_result.py`: NEW-mode branch wraps `expected_summary_slug(source_id)` in `try/except PathError` and appends a gate finding of the NEW dedicated type **`summary_slug_underivable`**, added to `HARD_ZERO_FINDING_TYPES` (and to the `check_compiled_source` docstring listing). The mode check remains per-source.
- `tools/replay.py`: same catch — returns `semantic_ok=False` with stable detail `"semantic: cannot derive expected summary slug: ..."` and the run continues.
- `compiler/tests/test_validate_compile_result.py::test_hard_zero_finding_types_set` updated for the new set member.

**Tests:** API — `test_new_mode_underivable_stem_fails_closed` (`KDB/raw/日本語.md` → exactly one `summary_slug_underivable` gate finding; no raise). CLI — `test_cli_underivable_stem_exits_one_not_traceback` (kdb-validate exits 1, finding in stdout, no `Traceback` in stderr). Replay — `tools/tests/test_response_replay.py::test_replay_underivable_stem_fails_closed` (flags extract/parse/schema True, semantic False, `matches_expected` True).

## F6 [Medium] — mixed-journal rebuild test now uses a VALID new-contract record

**Resolution (`kdb_graph/tests/test_rebuilder.py::test_rebuilder_mixed_shape_journal_pair`):**
- NEW journal's pages now include the derived summary page: `{"slug": "summary-new", "page_type": "summary", ...}` alongside concepts `c`/`d`. LEGACY journal now also carries a proper `summary-old` summary page + top-level `summary_slug` key (legacy referential shape).
- Both journal payloads are validated through `compiler.validate_compile_result` before the rebuild. Note: they're validated as *fixture-backed* payloads (`compile_meta` stripped, which the aggregate schema explicitly allows) because the synthetic factory's `run_state`/`hash` stub is intake-only and never schema-valid (`additionalProperties: false`); a comment in the test says so. Original edge assertions kept (`a→b` stored-list, `c→d` body-derived).
- **New mixed aggregate test:** `compiler/tests/test_validate_compile_result.py::test_mixed_legacy_and_new_sources_validate_per_source` — one payload containing a LEGACY source and a NEW source validates clean; a second case with only the NEW source broken flags exactly one `summary_slug_mismatch` attributed to the NEW source (per-source mode selection, not global).

## F1 [Medium] — prompt summary-slug rule now states the executable algorithm

**Resolution (`compiler/prompts/KDB-Compiler-System-Prompt.md`, §3 summary bullet):** replaced "copied verbatim — preserve every character of the stem" with the exact rule: kebab-case (lowercase, accents folded to ASCII, non-alphanumeric runs collapse to one `-`, edge `-` stripped) → first 112 characters (drop trailing `-`) → `summary-` prefix; "preserve meaningful numeric or identifier prefixes" retained. The three examples are unchanged (they already matched the derivation). The only other "verbatim" in the prompt (§4 EXISTING CONTEXT slug reuse) is correct usage and stays.

**Tests (`compiler/tests/test_summary_slug.py`):** `test_accented_stem_folds_to_ascii` (`Café déjà vu.md` → `summary-cafe-deja-vu`) and `test_prompt_example_stems_match_derivation` (all three prompt examples equal the executable derivation).

## F2 [Low] — stale docstrings / schema descriptions brought in line

- `compiler/validate_source_response.py`: module docstring — 4 page fields (not 7), CLI flag `--source-id` (not `--source-name`); `_validator` docstring — "pages + optional compilation_notes" (not "path-free source_name").
- `compiler/canonicalize.py` `_merge_page_intents` docstring: no `outgoing_links` union (field left the contract; winner's body authoritative) — matches the code's existing behavior.
- `compiler/schemas/compile_result.schema.json`: `outgoing_link_remaps` description now body-only; formal `"deprecated": true, "readOnly": true` annotations added to the six retained historical properties (`status`, `outgoing_links`, `confidence` on pages; `summary_slug`, `concept_slugs`, `article_slugs` on sources). Both validators re-checked with `Draft202012Validator.check_schema`.

## F7 [Low] — guard/production equivalence pinned for the failure path

**Resolution (`compiler/tests/test_summary_slug.py`):** new `test_guard_exception_identical` parametrized over a non-ASCII-only stem (`日本語.md`) and a punctuation-only stem (`---.md`) — asserts BOTH `compiler.summary_slug.expected_summary_slug` and the guard script's copy raise `PathError`. The success-path parametrization also gained the accented stem. (An initially included `KDB/raw/.md` case was dropped: `Path(".md").stem` is `".md"` by dotfile semantics, which slugifies to `md` — not an underivable stem.)

---

## Suite evidence

- Full suite after all fixes: **1376 passed, 1 skipped (env-gated live smoke), 1 deselected (bench), 39 warnings** in ~58s — `.venv/bin/python -m pytest`.
- No production file outside the cited ones was touched; `scripts/cohort_slug_collision_guard.py` and `common/measurement.py` remain absent from the Gate-2 diff (re-verified).
