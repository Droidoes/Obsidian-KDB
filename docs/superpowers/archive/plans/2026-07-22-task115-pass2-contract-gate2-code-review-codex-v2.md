# Task #115 — Pass-2 contract revision — Gate-2 code review, round 2

**Reviewed:** 2026-07-22  
**Base:** `e9ca323` on `feat/115-pass2-contract`  
**Scope:** the complete uncommitted Gate-2 working-tree diff, with focused verification of the resolutions documented in `2026-07-22-task115-pass2-contract-gate2-review-response.md`  
**Verdict:** **GO-WITH-CHANGES** — all round-1 High and Medium findings are correctly resolved. Add the two missing schema annotations below, rerun the schema/focused validation tests, and Gate 2 is safe to commit.

The implementation now matches the ratified architecture on every load-bearing runtime path. Terminal semantic rejection is classified as validation on both telemetry surfaces; canonical body rewriting agrees with the compiler/graph token contract for headings, escapes, and code spans; underivable stems fail closed in aggregate validation and replay; the mixed-shape tests exercise per-source mode selection and a valid NEW journal; the prompt teaches the executable slug algorithm; and guard/production failure equivalence is pinned. No architectural rework is needed.

## Round-1 resolution audit

| Prior finding | Round-2 result |
|---|---|
| F1 — prompt/executable summary-slug contradiction | **Resolved.** The prompt now states normalization, the 112-character budget, trailing-hyphen removal, and prefixing in the executable order. Accented and prompt-example cases are tested. |
| F2 — stale contract documentation/schema annotations | **Mostly resolved.** Runtime-facing docstrings and the six page/source property annotations are corrected. One machine-readable annotation gap remains below. |
| F3 — semantic failure routed as generic compile failure | **Resolved.** `compile_one` records `validate`/`SemanticCheckError`; `compile_source` maps it to outer `validate`; the persisted-record regression test covers both surfaces. |
| F4 — canonical wikilink grammar mismatch | **Resolved.** Plain, display, heading, escaped, inline-code, and fenced-code behavior is aligned and tested; compiler and graph extraction agree on the remapped results. |
| F5 — aggregate/replay `PathError` escapes | **Resolved.** Both consumers catch the underivable-stem boundary and return stable fail-closed results; API, CLI, and replay tests cover it. |
| F6 — invalid NEW half of mixed-journal fixture | **Resolved.** The actual NEW journal now has its derived summary page; mixed aggregate validation proves per-source LEGACY/NEW selection. The graph test retains both stored-list and body-derived edge assertions. |
| F7 — missing guard/helper exception equivalence | **Resolved.** Non-ASCII-only and punctuation-only failure cases now require identical `PathError` behavior. |

## (a) Contract coherence (schema / prompt / builder)

### F8

**[Severity: Low] · `compiler/schemas/compile_result.schema.json:20` and `:29` · two removed top-level fields lack the ratified machine-readable compatibility annotations.**

The retained historical `log_entries` and `warnings` properties describe themselves as deprecated, but neither has `"deprecated": true` nor `"readOnly": true`. The six retained page/source properties now carry both annotations. D-115-14 and blueprint Task 2.2 require removed aggregate fields to remain optional, deprecated-annotated, and read-only; `log_entries` was dropped and `warnings` was replaced by `compilation_notes`, so both fall under that rule.

This does not alter JSON-Schema validation behavior—both keywords are annotations—and historical payloads still validate. It does leave the published machine-readable contract internally inconsistent and means schema-aware consumers cannot distinguish these two retired fields from ordinary writable optional properties.

**Suggested change:** add `"deprecated": true, "readOnly": true` to both top-level properties and add a schema-contract test that walks the complete retained-legacy field list, rather than asserting only selected page/source fields.

## (b) Correctness of new gates (derive / semantic / canonicalize)

None. The round-1 F3–F5 defects are resolved, including both observable failure-stage surfaces and the canonicalizer/extractor boundary.

## (c) Dual-mode and backward compatibility

None. Mode selection remains per source; ordinary historical aggregate validation is covered by the retained old-shape fixture, while the mixed test now proves a LEGACY and a NEW source coexist correctly.

The rebuild test validates a fixture-backed copy of the synthetic legacy journal because `kdb_graph.testing.make_compiled_source` carries an intake-only `compile_meta` stub that is not aggregate-schema-shaped. That limitation is explicitly documented in the test and does not reopen F6: the actual NEW journal is schema-valid, the exact graph replay payloads exercise both edge paths, and separate historical fixtures cover `kdb-validate` read compatibility.

## (d) Layering and cross-package behavior

None.

Verified that production `kdb_graph` code has no compiler/common sibling import, the package-boundary suite passes, compiler and graph wikilink extraction agree on the remediated forms, and no removed repair/reconcile caller survives.

## (e) Scope and test coverage

None.

The diff remains confined to Gate-2 Phases 1–2. `scripts/cohort_slug_collision_guard.py`, `common/measurement.py`, graph confidence/snapshot work, and MCP Phase-3 surfaces remain outside the diff.

## Verification performed

- Focused round-2 remediation set: **35 passed**.
- Complete deterministic suite: `.venv/bin/python -m pytest -q -m 'not bench and not live'` — **green (exit 0)**; the separately environment-gated compiler live smoke was skipped.
- `tools/tests/test_package_boundaries.py` — **9 passed**.
- Both modified JSON Schemas pass `Draft202012Validator.check_schema`.
- Manual canonicalization probes covered plain, display, heading, heading+display, escaped, inline-code, fenced-code, uppercase, and non-kebab alias surfaces; compiler and graph extractors returned identical post-remap edge sets.
- `git diff --check HEAD` — clean.
- Scope searches found no dangling deleted repair API, forbidden production sibling import, Phase-3 leakage, or changes to the baseline collision guard / merged measurement module.

## Bottom line

The round-1 functional blockers are closed and the Gate-2 implementation is operationally sound. The only remaining issue is a low-risk but explicit D-115-14 schema-contract omission: annotate top-level `log_entries` and `warnings` as deprecated/read-only and pin the complete legacy-property set in a test. After that small correction and focused verification, the diff is safe for Gate-2 commit approval.
