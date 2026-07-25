# Task #115 Phase 4 — Gate-4 code review, round 2 (Codex)

## Verdict: GO

All four round-1 findings are resolved, and the fixes introduce no new correctness, regression, boundary, or scope issue. The working-tree diff is safe to commit as Gate 4 and use as the clean Phase-5 comparison-cohort anchor, subject to Joseph's commit approval.

## Resolution audit

### F1 — corpus did not guard the coerce fix: CLOSED

`tests/fixtures/wikilink_parity/cases.json:41-65` now forces actual rewrites outside escaped/fenced/inline-code regions while requiring the protected malformed tokens to remain byte-identical. The added cases at `:113-141` also pin heading+display preservation during a real rename, code-only uncoercible-value exclusion, and code-only collision exclusion. `compiler/tests/test_wikilink_parity.py:39-51` now checks body, changed flag, and the repaired page slug where applicable.

I reran the round-1 acceptance probe using the exact pre-fix scanner/rewriter. It now fails exactly the five intended cases: `escaped`, `fenced-code`, `inline-code`, `code-only-uncoercible-does-not-block-repair`, and `code-only-collision-does-not-refuse`. The ten control cases still pass. A reversion of the production fix can no longer leave the corpus green.

### F2 — three-way system test bypassed persistence/finalization: CLOSED

`kdb_graph/tests/test_rebuilder.py:1106-1220` now crosses every load-bearing D-115-10 boundary relevant to this phase:

- wiki pages are persisted through `page_writer.apply`;
- per-source graph intake runs with `wire_links=False`;
- zero pre-finalizer edges are asserted;
- `_combine_crs` plus batch `wire_links` creates the live edge set;
- a forward cross-source link makes deferred wiring necessary;
- persisted Markdown bodies are read back through `common.wiki_io.get_body`;
- escaped and inline-code non-edges have existing targets and are independently pinned by the explicit expected set;
- the one combined journal is rebuilt through `ObsidianRunsAdapter`, and rebuilt edges must equal the live graph.

The earlier direct-intake test remains correctly relabeled as parser-level coverage. The production-boundary test would fail if page persistence, deferred finalization, combined payload construction, protected-token extraction, or rebuild parity regressed.

### F3 — replay asserted only a generic schema failure: CLOSED

`tools/tests/test_response_replay.py:100-116` now pins the `additionalProperties` cause and a representative removed top-level key in addition to the extract/parse/schema/semantic flags. The assertion matches the observed first schema error and cannot pass on an unrelated rejection.

### F4 — validation and rebuild used different payloads: CLOSED

`kdb_graph/tests/test_rebuilder.py:1024-1103` writes one schema-valid historical sidecar and one clean new sidecar, reads those exact bytes back for aggregate validation, then rebuilds the same files. The legacy record includes the deprecated stored-link fields and full production-shaped `compile_meta`; the new record contains four-field pages, `compilation_notes`, and no deprecated contract keys. The edge assertions distinguish legacy stored-list derivation from new body derivation. No copied or normalized substitute is validated.

## New findings

None.

The cross-package imports added for the system test are test-only; the enforced production dependency graph deliberately excludes `tests/`, and the package-boundary guard remains green. Production changes remain confined to the already-reviewed `compiler/repair.py`; no Phase-5 cohort logic, #116 lifecycle work, or Gate-2/Gate-3 surface change entered the diff.

## Verification

- Focused resolution bundle, including both parity suites, the two new cross-boundary tests, replay classification, and package boundaries: **72 passed**.
- Exact pre-fix coerce simulation: **5 intended failures, 10 controls passed**.
- Requested deterministic suite (`.venv/bin/python -m pytest -q -m 'not bench and not live'`, with cache/bytecode writes disabled): **1449 passed, 1 skipped, 2 deselected**; exit 0.
- Deterministic collection count: **1450 selected tests** (the one selected live-API smoke skips by its own explicit opt-in guard).
- `git diff --check HEAD`: clean.

## Bottom line

Gate 4 now supplies the evidence the ratified blueprint requires: shared parser/rewriter semantics are mutation-sensitive, persisted wiki links equal production-finalized live graph links and rebuilt links, new-response replay and legacy rejection are classified correctly, and the identical historical/new sidecars pass both validation and rebuild. No change is required before the Gate-4 commit.
