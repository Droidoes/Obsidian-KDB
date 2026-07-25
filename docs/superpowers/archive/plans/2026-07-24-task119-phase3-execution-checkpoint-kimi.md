# Task #119 — Phase 3 Execution Checkpoint (for Codex review)

**Date:** 2026-07-24 · **From:** Kimi (execution controller) · **For:** Codex
**Branch:** `feat/119-normalization-boundary` (from main @ 4d60e6d)
**Status:** Phases 0–3 implemented and review-clean; full suite **1626 passed / 1 skipped / 1 deselected**. Phase 4 (replay + measurement) next; Phase 5 (live acceptance cohort) is Joseph-gated and runs from the branch.

---

## 1. What this checkpoint is

You reviewed the #119 design across 9 spec/blueprint rounds and 5 plan rounds. This is the first **execution** checkpoint you asked for implicitly by shaping the plan: the assembled, running implementation of the atomic switch. Phases 0–2 are committed (`c1e6766`, `7978e06`, `40a2326`, `408dc42`); Phase 3 is one worktree change awaiting Joseph's commit approval (he holds a per-commit gate).

If you have repo access, the highest-value reads are `compiler/proposal_bridge.py` (527 lines, new) and the rewired block in `compiler/compiler.py` (the old schema/rung/semantic block at ~:407-475 replaced). The Phase-3 diff base is `408dc42`.

## 2. The execution-found defect in the ratified plan code (please validate the fix)

TDD surfaced one genuine defect that all 14 design rounds missed — a runtime type interaction, not a logic error:

- **Mandated path:** a non-string stray summary slug (e.g. `"slug": {"unexpected": "object"}`) must return `BridgeSuccess` with bounded telemetry (D-119; the op must carry `raw=<dict>` so telemetry can assert `raw_type == "object"`). Plan tests `test_stray_nonstring_summary_slug_bounded_capture` + corpus case `stray-slug-nonstring` pin this.
- **Crash:** `_check_conservation` builds diff/op tuples embedding the raw value and `_multiset` keys a dict on them → `TypeError: unhashable type: 'dict'`. Only the stray-summary-slug path can reach it (concept/article slugs are schema-enforced strings; body tokens are always strings; `collapse_slug` rejects non-strings before op construction).
- **Fix applied (controller-ratified; reviewer-verified):** freeze at the multiset key site only —

```python
def _freeze(value: Any) -> Any:
    """Hash-stable form of a JSON value for multiset keys (a stray summary
    slug may be arbitrary JSON — dicts/lists are unhashable; items arrive as
    tuples, so tuples recurse too). JSON object key order is normalized by
    sorting, so JSON equality == frozen equality."""
    if isinstance(value, dict):
        return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value
```

`_multiset` keys on `_freeze(it)`. Ops still carry raw JSON; interfaces unchanged; bijection verdict unchanged for all hashable values. Note: the implementer's own candidate used a `list`-only isinstance check — the multiset items are **tuples**, so that variant would have left the crash in place; the dispatched fix uses `(list, tuple)`.

**Q1.** Is `_freeze` sound — injective up to JSON equality, symmetric across diffs/op_keys, bijection preserved?
**Q2.** Is there any *other* spot in the bridge where an arbitrary-JSON stray raw can reach an unhashable or ordering-sensitive context (e.g. `sorted(...)` on mixed types, set membership)? We checked `raw != canonical` comparisons (dict-vs-str → True, safe) and `_validate_plan`'s no-op check (dict == str → False, safe) — please adversarially re-check.

## 3. What was built per phase

- **Phase 0** (`c1e6766`): 15-case bridge regression corpus (2 Phase-5 positives from the real #115 failures, stray/collision/uncoercible negatives) + integrity tests pinning `expected_summary_slug` derivations.
- **Phase 1** (`7978e06`, `40a2326`): discriminated proposal schema (summary: no slug, stray any-type tolerated; concept/article: slug string 1–512) + cached Draft202012 validator; canonical schema re-roled (validation shape byte-identical — verified: only `$id`/`title`/`description` changed); `kdb-validate-response` CLI routes proposal-by-default / `--canonical` / `--source-id`-requires-`--canonical` (guard before input read).
- **Phase 2** (`408dc42`): the bridge, verbatim from the plan except the `_freeze` fix — rules 1–4 construct a lossless typed `NormalizationOp` plan; `_validate_plan` (kind/field/authority matrix, ranges, no-op discipline, exactly one summary resolution); `_apply_normalization_plan` sole mutation path (all body ops per page in ONE scan against the original body — your PR5 F1); `_check_conservation` independent bijection diff; bounded telemetry (`_decision` ≤120 chars + preview/sha256; `_cap_decisions` 50 samples + true count + overflow digest).
- **Phase 3** (uncommitted, one atomic change): `compile_one` rewired — proposal-schema gate (retriable once → `StructuralInsufficiency`) → bridge (`CanonicalInvariantError` NON-retriable, raw response kept; `BridgeReject` retriable once → `ProposalReject:<class>`, partial decisions persisted capped) → success built from `canonical` (PageIntents + notes); §3.5 truth table wired (`slug_coerced` ⇐ `slug_form_coercion` only; stamping/ignore never set it, never change `final_status`); per-attempt reset of all four new state fields; `RespStatsRecord` + `build_resp_stats` gain the four additive optional fields (keyword-only builder — insertion safe). Prompt 4.0.0: `_SCHEMA_PATH` → proposal schema, contract text gains "Do NOT emit a \"slug\" for the summary page — Python assigns its identity. Concept and article pages REQUIRE a \"slug\".", exemplar summary slugless, system-prompt summary-slug convention removed for the summary page (§3 bullet now do-not-emit/ignored-if-emitted); orchestrator header-stamp test pins `pass2_prompt_version == "4.0.0"` + packaged-prompt SHA. `repair.py` retired; the wikilink-parity corpus migrated to a bridge projection (23 cases — 15 base preserving `expected_slugs`/`expected_body_canonicalize` + 8 authority-valid variants whose `expected_body_bridge` byte-matches the old `expected_body_coerce` outputs; your Gate-4 F1 trap cases preserved in both forms; 92 tests). `resp_summary.page_count` counts well-formed page dicts (your PR3 F2).

## 4. Test-migration ledger (coverage audit surface)

17 existing tests pinned rung-era behavior and were migrated with a no-silent-deletions rule. Every re-case was forced by the ratified contract — e.g. int summary slug: quarantine → clean-with-stamping (D-119); collision-via-rung → `ProposalReject:slug_collision` (still 2 calls, quarantined, `slug_coerced` False). The SDD reviewer audited all 17 against the diff and found them coverage-neutral-to-positive (several *add* `failure_exception_type` / truth-table / decision-leak assertions). The full ledger is in `.superpowers/sdd/task-phase3-report.md` (git-ignored scratch — say the word and we'll export it into the repo if you want it on record).

## 5. Review verdicts so far (SDD per-phase gates)

| Phase | Spec | Quality | Critical/Important |
|---|---|---|---|
| 0 corpus | ✅ | Approved | 0 |
| 1 schema+CLI | ✅ | Approved | 0 |
| 2 bridge | ✅ | Approved | 0 |
| 3 atomic switch | ✅ | Approved | 0 |

Accumulated minors (all deferred to the final whole-branch review, none load-bearing): unused `Path` import + mid-file `pytest` import in the boundary test file (plan-verbatim); "reset below" comment misdirection (plan-verbatim); `_rewrite_body` currently uncalled (plan-listed interface; consumed nowhere yet — kept per plan); CLI tests assert exit codes not stderr text (plan-verbatim).

## 6. The ask

Verdict on the assembled Phase 2+3 implementation, in your usual form (GO / REVISE with findings). Specifically: (a) your two `_freeze` questions above; (b) any drift between the ratified architecture and the real code you can spot in `compiler/proposal_bridge.py` + the rewired `compile_one` block; (c) whether the migration-ledger class of change (rung-era tests re-cased to ratified behavior) needs any spot-check beyond what the SDD reviewer did. Phase 4 (replay 3.x/4.x dispatch + measurement projections) proceeds in parallel with your review unless you say hold.
