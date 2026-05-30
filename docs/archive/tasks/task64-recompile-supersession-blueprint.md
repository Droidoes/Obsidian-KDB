# Task #64 — Recompile Page Supersession + #37 Summary-Prefix Data Repair

Status: **open** — awaiting Proceed gate.
Blueprint owner: two-person team. Codex-reviewed (3 rounds, 2026-05-15).

---

## 1. Why this exists

Recompiling a source that was first compiled **before Task #37** (2026-05-07,
commit `a21c2a8d`, the `summary-` slug-prefix reservation) produces a
**duplicate summary page** and leaves stale pages stranded.

Observed on the 2026-05-15 Buffett recompile:

- April compile → summary slug `buffett-yahoo-interview-march-2020-covid`
- May recompile → summary slug `summary-buffett-yahoo-interview-march-2020-covid`
- Both pages now `status: active`. `tombstones: 0`.

The same duplication already happened silently during the #63.7 validation arc
(2026-05-14) for EP1 and Howard-Marks. **3 of the 4 pre-#37 sources are
affected; CODEBASE_OVERVIEW.md is a latent 4th.**

## 2. Root cause

Three layers — only the middle one is the bug.

**Not a bug — the `summary-` convention (Task #37).** #37 deliberately reserved
the `summary-` prefix for summary slugs to eliminate the duplicate_slug /
pairing_type_mismatch defect class (summary vs concept slug collisions in a flat
namespace). It is schema-enforced (`summarySlug` pattern
`^summary-[a-z0-9]+(?:-[a-z0-9]+)*$`). The convention is correct and stays.

**The bug — the manifest path never removes support.**
`manifest_update._ensure_page()` (`manifest_update.py:383-386`) only ever
*unions* the current source into a page's `supports_page_existence`. When a
recompile emits a different page set than the source's prior run, the pages it
no longer emits keep their stale support entry. They are never re-pointed, never
orphaned. Because the post-#37 summary has a *different slug* (= different
`page_key`), the recompile cannot update the old summary in place — and the old
slug is now **schema-invalid**, so no future compile can ever touch it. It
becomes a permanently-orphaned page unless explicitly retired.

**Not a bug — the graph path already supersedes.** `manifest.json` and
`graphdb_kdb` are D34-independent siblings, each consuming `compile_result`
separately. The graph ingestor `graphdb_kdb/ingestor.py:_replace_supports_for_source`
(lines 308-350) does an **atomic per-source SUPPORTS replacement** — drops all
of a source's SUPPORTS edges, recreates one per currently-emitted page; Phase 4
`_detect_and_mark_orphans` flags pages left with zero SUPPORTS. This was Codex
CRITICAL #2 ("stale SUPPORTS edges") during the #63 blueprint review and was
fixed there. **The graph path is the reference design. #64 brings the older
manifest path into parity with it.**

This bug is not specific to #37. Any recompile that emits fewer pages (model
output volume is model-dependent — see 2026-05-14 daily note) strands the
omitted pages in the manifest. #37 is just the trigger that made it visible and
unavoidable.

## 3. The fix — two parts

### Part A — Code fix (manifest path only)

Bring `manifest_update.apply_compile_result()` to parity with the graph
ingestor's per-source replacement. After a source's pages are upserted:

1. `emitted_page_keys` = the page_keys this run emitted for the source — already
   computed as `touched_keys` in the per-source loop (`manifest_update.py:438`
   appends every emitted page; `touched_keys` is the complete emitted set,
   `created_keys ⊆ touched_keys`, verified).
2. Find prior pages where `source_id ∈ supports_page_existence`.
3. For each such page **not** in `emitted_page_keys`: remove `source_id` from
   `supports_page_existence` **and** `source_refs` — the diff-form equivalent of
   the graph's drop-all-then-recreate.
4. The existing orphan pass (`manifest_update.py:489-508`) then flags any page
   whose `supports_page_existence` went empty as `orphan_candidate` and records
   it in `manifest["orphans"]`.

The removal primitive already exists — `_purge_source_from_pages()`
(`manifest_update.py:225-232`) does exactly this filter, currently only invoked
on the DELETED-source path. Part A reuses it on the recompile path, scoped to
omitted pages.

**Invariant fix.** `assert_manifest_invariants()` (`manifest_update.py:565-568`)
rejects empty `source_refs` for *all* pages with no status filter. Supersession
can legitimately empty a page's `source_refs`. The invariant must become
status-aware (D43). This also fixes a **pre-existing latent bug**: the DELETED
path can already empty `source_refs`, which would crash the invariant — never
hit only because no source has been deleted in practice.

**Provenance preservation.** The `orphans` entry already carries a
`previous_supporting_sources` field (`manifest_update.py:499`), currently always
`[]`. Supersession populates it with the removed source ref(s).

**No `graphdb_kdb` change.** The graph ingestor is already correct.

### Part B — One-time data repair (the 3 already-crossed sources)

The 3 affected sources are already `recompiled` with unchanged hashes, so a
normal `kdb-compile` run classifies them `to_skip` and will not re-fire.
Recompiling would cost 3 API calls and is unnecessary. Part B is two
**D34-independent** repairs sharing one upstream (the run sidecars):

**B1 — manifest migration** (`scripts/migrate_task64_supersession.py`, no API):
1. For each of the 3 recompiled sources, derive the emitted page set from the
   archived Stage 9 sidecar `state/runs/<run_id>/compile_result.json`
   (first-principles authority), and **assert it equals** the manifest's
   `sources[source_id].outputs_touched`. On divergence → stop, print the diff
   (guard against stale bookkeeping — Q1).
2. Pages still listing the source in `supports_page_existence` but not in the
   emitted set → remove the source from `supports_page_existence` + `source_refs`.
3. Orphan pages whose support is now empty; populate `previous_supporting_sources`.
4. Re-run `assert_manifest_invariants()` (status-aware, post-D43) as a self-check.

**B2 — graph repair**: `graphdb-kdb rebuild`, then `graphdb-kdb verify`.
Rebuild replays the run sidecars through `graphdb_kdb`'s **already-correct**
ingestor — `_replace_supports_for_source` reproduces a correctly-superseded
graph at replay time. Rebuild does not depend on the migrated manifest (D34);
`verify` then cross-checks that the repaired graph and repaired manifest agree.
(April pre-#37 runs have no sidecars, so a rebuild simply cannot reintroduce
their stale pages.)

CODEBASE_OVERVIEW.md needs **nothing** from Part B — no duplicate exists yet;
once Part A lands, its next recompile self-heals.

**Affected data (confirm during implementation):** 3 orphaned pre-#37 summaries
(`buffett-yahoo-interview-march-2020-covid`, `ep1-the-journey-of-china`,
`howard-marks-oil-rational-investor`), plus any pre-#37 articles/concepts a
recompile no longer emits — e.g. the 2 Buffett articles
`buffett-on-fang-stocks-and-market-concentration` and
`buffett-on-political-division-and-american-progress`. Shared concepts still
supported by another source must **stay active** — orphan only on empty support.

## 4. Locked decisions (proposed — D41–D44)

| ID  | Decision |
|-----|----------|
| **D41** | **Recompile supersession.** A source's recompile removes that source's support from prior pages the new run no longer emits. The graph ingestor already implements this; D41 binds the manifest path to parity. |
| **D42** | **`source_refs` is current-state provenance, not an eternal log.** Stripped on supersession alongside `supports_page_existence`. History lives in run journals, `sources[].previous_versions`, and `orphans[].previous_supporting_sources`. |
| **D43** | **Status-aware `source_refs` invariant.** `active` page → `source_refs` non-empty. `orphan_candidate` page → may be empty (provenance preserved in `orphans[].previous_supporting_sources`). Also fixes the pre-existing DELETED-path invariant crash. |
| **D44** | **D12 preserved.** Supersession flags pages `orphan_candidate`; never deletes page records or files. `delete_policy` stays `mark_orphan_candidate`. |

## 5. Implementation surface

### 5.1 Part A — files touched
- `kdb_compiler/manifest_update.py` — supersession step in `apply_compile_result()`; status-aware `assert_manifest_invariants()`; `previous_supporting_sources` population.
- `kdb_compiler/tests/test_manifest_update.py` — test surface §6.
- No `graphdb_kdb` change.

### 5.2 Part B — files touched
- `scripts/migrate_task64_supersession.py` (new) — `--dry-run` is the **default**; `--apply` required to mutate. Prints exact affected page_keys per source; writes a reconstructible audit JSON under `state/` (or `state/runs/`). Committed for audit trail (Q3).
- Graph repair via existing `graphdb-kdb rebuild` + `verify` — operational, no new code.

### 5.3 Sequencing
1. Part A code fix + tests; full suite green.
2. Commit Part A + CODEBASE_OVERVIEW.md D41–D44 ledger entries.
3. Part B1 migration script; run with default `--dry-run`; review the proposed diff.
4. Part B1 `--apply` against the live vault; then Part B2 `graphdb-kdb rebuild` + `verify`.
5. Verify (§7); commit Part B (script + audit JSON).

## 6. Test surface (provisional — finalize in plan)
- pre-#37 summary slug replaced by `summary-*` on recompile → old summary becomes `orphan_candidate`.
- omitted article/concept supported only by that source → becomes `orphan_candidate`.
- omitted **shared** concept still supported by another source → stays `active`.
- supersession is idempotent — re-applying the same compile result does not re-orphan or thrash.
- invariant: `orphan_candidate` page with empty `source_refs` passes; `active` page with empty `source_refs` still fails.
- orphan entry carries non-empty `previous_supporting_sources` after supersession.

## 7. Verification criteria for closure
- Recompiling any source no longer leaves a stale prior-generation page `active`.
- After Part B: the 3 pre-#37 summaries are `orphan_candidate`; the fresh `summary-*` pages are the only `active` summaries for their sources; shared concepts unaffected.
- `graphdb-kdb verify` reports no divergence between the repaired graph and repaired manifest.
- Full kdb_compiler suite green.

## 8. Resolved review questions (Codex round 3, 2026-05-15)
- **Q1 — migration emitted-set source → RESOLVED.** Sidecar `compile_result.json` is the authority; the migration **asserts** it equals manifest `outputs_touched` before mutating and stops on divergence. First-principles authority + a guard against stale bookkeeping.
- **Q2 — graph repair → RESOLVED.** The graph ingestor already supersedes correctly (`_replace_supports_for_source`), so plain `graphdb-kdb rebuild` replaying sidecars produces a correct graph — no repair-sidecar, no manifest-driven rebuild, no targeted patch needed. `verify` cross-checks convergence afterward.
- **Q3 — migration packaging → RESOLVED.** Throwaway script under `scripts/`, committed for audit trail; `--dry-run` default, `--apply` to mutate; emits affected page_keys + an audit JSON. A reusable subcommand would overfit a one-time #37 migration.

## 9. Known limitations
- Part B repairs only the 3 known crossed sources. CODEBASE_OVERVIEW.md self-heals on its own next recompile under Part A — intentional, not a gap.
- Supersession is per-run: it reflects the latest compile's emitted set. A page omitted by a buggy/under-producing model run will be orphaned even if the omission was a model defect rather than intent. This is correct behaviour (the orphan flag is reviewable, D12), but worth noting alongside the model-output-volume variance flagged 2026-05-14.
