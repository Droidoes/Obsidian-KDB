# Task #115 — Phase 4 Gate-4 code review: resolution of Codex findings (round 1 → round 2)

> Response to `docs/superpowers/plans/2026-07-22-task115-phase4-gate4-code-review-codex.md` (verdict: GO-WITH-CHANGES).
> All 4 findings folded into the same uncommitted Gate-4 diff on branch `feat/115-pass2-contract` (base `15f16ff`, the Gate-3 commit).
> **Verification after fixes:** full suite **1450 passed / 1 live-skip / 1 deselected** via `.venv/bin/python -m pytest` (pre-review: 1436; +14 tests).
>
> **For the round-2 reviewer:** re-review the working-tree diff (`git diff HEAD`) with focus on the files cited per finding. Confirm each resolution, and re-run the deterministic suite (`.venv/bin/python -m pytest -q -m 'not bench and not live'`). Write the round-2 verdict to `docs/superpowers/plans/2026-07-22-task115-phase4-gate4-code-review-codex-v2.md`.

---

## F1 [Medium] — corpus protected cases now force real renames; pre-fix coerce provably fails

**What was wrong:** the `escaped` / `fenced-code` / `inline-code` cases used the already-valid target `aapl`, so the coercion rewriter built no rename — the pre-fix and post-fix implementations behaved identically on those cases, and reverting the production fix would have kept the corpus green (Codex verified by simulation).

**Resolution (`tests/fixtures/wikilink_parity/cases.json`):**
- `escaped`, `fenced-code`, `inline-code` reworked: the malformed target `[[Foo--Bar]]` now appears BOTH inside the protected region AND in ordinary prose. Pinned: prose token becomes `[[foo-bar]]` (coerce) / `[[canonical-foo]]` (canonicalize); the escaped/code token is byte-identical.
- New `malformed-heading-display` case: `[[Foo--Bar#Sec|the alias]]` → `[[foo-bar#Sec|the alias]]` (coerce) / `[[canonical-foo#Sec|the alias]]` (canonicalize) — heading+display preservation during a REAL coerce rewrite.
- New `code-only-uncoercible-does-not-block-repair` case: uncoercible `[[Foo Bar]]` only inside inline code; the malformed page slug `Good--Slug` IS repaired to `good-slug` (changed=True), body untouched.
- New `code-only-collision-does-not-refuse` case: `[[foo-bar]]` + `[[foo--bar]]` colliding ONLY inside inline code; the page-slug repair proceeds (changed=True), body untouched.
- Cases now carry `page_slug` / `expected_page_slug` / `expect_coerce_changed`; the driver (`compiler/tests/test_wikilink_parity.py`) asserts all three plus both bodies.

**Acceptance evidence (Codex's own criterion):** a local simulation of the PRE-FIX implementation (old regex, no lookbehind, no code segmentation, code-inclusive value scan) fails exactly the 5 designed cases — `escaped`, `fenced-code`, `inline-code`, `code-only-uncoercible-does-not-block-repair`, `code-only-collision-does-not-refuse`. The corpus now guards the behavior Phase 4 changed.

## F2 [Medium] — system test moved to the production orchestration boundary

**What was wrong:** the three-way equality test used direct `apply_compile_result` (immediate wiring), never persisted wiki pages, and fed rebuild two hand-written journals — bypassing page_writer, the deferred `wire_links` finalizer, and `_combine_crs`.

**Resolution (`kdb_graph/tests/test_rebuilder.py`):** new `test_system_wiki_body_equals_live_and_rebuilt_links` runs the REAL production sequence:
1. `page_writer.apply(..., write=True)` per source (pages persisted to a temp vault).
2. `apply_compile_result(..., detect_orphans=False, wire_links=False)` per source (deferred wiring, as the orchestrator does).
3. **Zero LINKS_TO asserted at this point** — the deferred finalizer is load-bearing, and the FORWARD cross-source link (`concept-a → concept-b`, target introduced by the SECOND source) could not have been wired per-source anyway.
4. `_combine_crs([cr1, cr2], run_id)` → `wire_links(combined, ...)` batch finalizer → live edges asserted (4 expected; inline-code and escaped non-edges pinned).
5. **Persisted wiki-body equality:** bodies are read back from the on-disk `.md` files via `common.wiki_io.get_body` (frontmatter stripped — the real serialization boundary) and their extracted wikilinks asserted equal to live LINKS_TO.
6. The **combined** compile_result + combined scan are written as ONE journal (the production finalize payload) and replayed through `ObsidianRunsAdapter` — rebuilt LINKS_TO == live LINKS_TO.

The pre-existing direct-intake test remains as parser-level coverage with a corrected docstring (`test_live_vs_rebuild_links_to_equality_new_shape`). A numeric `current_mtime` was added to the test's scan entries — `page_writer` requires it and the factory omits it.

## F3 [Low] — legacy-negative classification pins the stated cause

**Resolution (`tools/tests/test_response_replay.py`):** `test_replay_case04_legacy_negative_rejects_at_schema` now additionally asserts `"Additional properties are not allowed"` and a representative removed key (`summary_slug` or `source_name`) appear in the first schema detail — the test can no longer pass on an unrelated schema regression.

## F4 [Medium] — identical old/new sidecars proven through BOTH kdb-validate and rebuild

**What was wrong:** the mixed-pair coverage validated altered copies (`compile_meta` stripped) but rebuilt the unmodified, schema-invalid originals; the nominal "new" payload also carried the deprecated `warnings` key via the factory. Rebuild-compat and validator-compat were each covered, but never for the same artifacts.

**Resolution (`kdb_graph/tests/test_rebuilder.py::test_d115_14_identical_sidecars_through_validate_and_rebuild`):** hand-built legacy + new compile_results that are schema-valid EXACTLY AS WRITTEN — full production `compile_meta` (provider/model/tokens/latency/attempts/ok), legacy source with `summary_slug` + 7-field pages (status/confidence/outgoing_links), new source with 4-field pages + `compilation_notes` and NO deprecated keys anywhere. Both are written as journal sidecars; the test then (1) reads the sidecar bytes from disk and asserts `vcr.validate(...).is_valid` for both, and (2) rebuilds the same files and asserts legacy stored-list edges (`summary-old→a`, `a→b`) and new body-derived edges (`summary-new→c`, `c→d`).

---

## Suite evidence

- Full suite after all fixes: **1450 passed, 1 skipped (env-gated live smoke), 1 deselected (bench), 39 warnings** in ~60s — `.venv/bin/python -m pytest`.
- Delta vs pre-review (1436): +12 parity-corpus tests (3 new cases × 4 consumers... plus driver fields), +1 system test, +1 D-115-14 test.
- Production code unchanged by these resolutions — all fixes are fixtures/tests; `compiler/repair.py` (the Phase-4 production change) is untouched since the review.
