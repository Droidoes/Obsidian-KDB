# Task #122 — Pass-1 Search-Key Decomposition (options v1.3 — context-load capture)

**Date:** 2026-07-24 · **Status:** v1.3 — absorbs Codex R3 (5 Important + 1 Moderate + 1 Minor; "architecture converged"). Event-time **direction selected by Joseph**; detailed contract awaiting his ratification → P0 docs gate → blueprint
**Filed:** `docs/TASKS.md` #122 (carved from #118/#120)
**Reviews:** R1 → `…-options-review-codex.md` · R2 → `…-options-review-codex-v2.md` · R3 → `…-options-review-codex-v3.md`
**Supersedes:** v1.0 (post-run decomposition — rejected by Joseph: *"you recalculate T2/T3 after the run and you always get the hit — it becomes meaningless."*); v1.2's incomplete completeness/denominator contracts.

## The defect, precisely

`entity_search_key_resolution` (#109, `compiler/kpi/graph.py:174-187`) resolves Pass-1's keys against the **final post-run graph** at emit time — self-fulfilling, because the run has already poured its own output into the graph. It measures what the graph *became*, not what the keys *did*.

**The design (event-time capture):** measure at the moment of identification — context-load, before the Pass-2 call. Persist the outcome; aggregate the *recordings* at emit time. The final graph is re-read for exactly two declared purposes (§4), never to claim a hit.

## 1. Two products from the context builder (R2 F2 — no prompt contamination)

Today `prompt_builder.py:193` serializes `context_snapshot.to_dict()` directly into `## EXISTING CONTEXT`. Telemetry must be structurally incapable of reaching the prompt:

```python
@dataclass
class ContextBuildResult:
    snapshot: ContextSnapshot    # prompt-facing — unchanged: source_id + pages only
    telemetry: ContextTelemetry  # persistence/KPI-facing — never serialized into the prompt
```

`build_context_snapshot` returns `ContextBuildResult`; `ContextSnapshot`/`to_dict()` stay byte-identical. **Pins:** prompt JSON contains only the existing `source_id`+`pages` contract; the same graph+source produces **byte-identical prompt text and prompt-hash** before and after #122. The caller-supplied `context_snapshot=` path in `compile_source` (replay/tooling) supplies no telemetry and writes no record.

## 2. The per-source record (R2 F1 + R3 F4 — dedicated namespace, frozen tier shape)

One record per Pass-1 **signal** source, written **atomically, once, immediately after context build** (before the model call; retries inside `compile_one` do not rebuild context):

```
state/runs/<run_id>/context/<safe_source_id>.json
```

**Not** `pass2/` — `common/measurement.py:346-356` projects *every* `pass2/*.json` as a `RespStatsRecord`. Filenames use `safe_source_id` (`common/llm_telemetry.py:55-67`); the real `source_id` lives inside.

```json
{
  "run_id": "...", "source_id": "...", "status": "complete | context_failed",
  "configured_t2_mode": "structured | layered | legacy",
  "effective_t2_strategy": "structured_keys | explicit_empty | legacy_regex | layered_union",
  "keys_emitted": ["charlie-munger", ...],
  "key_outcomes": [
    {"key": "charlie-munger", "disposition": "resolved_t2_seed",
     "resolved": "charlie-munger", "target_first_run_id": "2026-05-30T..."},
    {"key": "garcia", "disposition": "unresolved", "resolved": null}
  ],
  "t1": {"candidates": 0, "delivered": 0, "slugs": []},
  "t2": {"candidates": 4, "delivered": 4, "slugs": ["charlie-munger", "..."]},
  "t3": {"candidates": 11, "delivered": 9, "slugs": ["..."]},
  "candidate_universe_size": 87, "domain_scope": "value-investing",
  "cold_start": false, "max_hops": 1, "page_cap": 50
}
```

- **Tier shape frozen (R3 F4):** per tier, `candidates` (pre-cap set size), `delivered` (post-cap, post-projection prompt pages), `slugs` = **all delivered slugs, in prompt rank order** — collectively bounded by the shared `page_cap`, so no overflow fields. **Pinned invariant:** `sum(delivered per tier) == len(snapshot.pages) ≤ page_cap`.
- **`status`** — `context_failed` when the build raises (source quarantines at `failure_stage="context"`). `compile_source` **synthesizes** this record in the builder-exception path — no `ContextTelemetry` object can be returned by a function that raised.
- **Empty-graph early return** (`context_loader.py:78-80`) still produces a full telemetry result: emitted keys as `unresolved`, zero tiers. `cold_start` (`:93`) and the 2-hop widening (`:108-109`) recorded, not recomputed.

## 3. Per-key dispositions (R2 F3 — resolver hit ≠ T2 contribution; R3 F3 — seed ≠ delivered)

Post-resolver gates: the candidate pool is `(domain_pool ∩ active) − t1_slugs` (`context_loader.py:89-98`), dedup applies, **and the shared page cap ranks T1 above T2** (`:106-125`). Frozen enum per emitted key:

```
unresolved                — no active canonical at load
resolved_t2_seed          — resolved AND entered the pre-cap T2 seed set
resolved_already_t1       — resolved, but the canonical was already a T1 entity
resolved_out_of_scope     — resolved, but outside the domain-scoped pool
resolved_duplicate_seed   — resolved, but another key already seeded that canonical
```

Rates (R3 F3 naming — say exactly what was observed):

- `search_key_resolved_at_load_rate` — dispositions 2–5 / emitted;
- `search_key_t2_seed_rate` — `resolved_t2_seed` / emitted (**pre-cap seeding**; a seed can still be capped out by T1 pressure — `context_t2_delivered_mean` is what the prompt actually received);
- age partition of resolver hits (dispositions 2–5), `first_run_id` vs current run, **equality only**: `search_key_resolved_pre_run_rate` / `search_key_resolved_cohort_rate` / `search_key_resolved_age_unknown_rate` (invalid stamp → honest residual).

**Late/never classification operates only on `unresolved` keys** — a filtered-out key is not a miss.

## 4. Emit-time aggregation (recordings; final graph for two declared reads)

`emit_run_kpis` gathers `context/*.json`; `compute_graph` gains the recordings + `run_id`. Watched fields (frozen):

- **Headline:** `context_t1_delivered_mean` / `context_t2_delivered_mean` / `context_t3_delivered_mean` (post-cap prompt pages per tier — Joseph's T1/T2/T3 counts); diagnostics `context_t{1,2,3}_candidates_mean`.
- Keys: `search_key_resolved_at_load_rate`, `search_key_t2_seed_rate`, `search_key_resolved_pre_run_rate`, `search_key_resolved_cohort_rate`, `search_key_resolved_age_unknown_rate`, `search_key_late_resolution_rate`, `search_key_never_resolved_rate`.
- Completeness: `context_record_coverage`, `context_build_success_rate` (§5), `context_explicit_empty_count`.
- Legacy `entity_search_key_resolution` **retained unchanged** (leaderboard continuity).

**Final-graph reads — exactly two, declared:** (a) the legacy metric's existing read; (b) re-resolving **`unresolved`-at-load keys only** to split `late_resolution` (materialized during intake, too late to help) from `never_resolved`. One shared batched query permitted; **neither read may redefine a load-time outcome**.

**Arithmetic:** count identities exact (`n_pre+n_cohort+n_unknown == n_resolved_hits`; `n_resolved+n_late+n_never == n_emissions`); rate identities `pytest.approx`. None-on-zero means **zero denominator** (emitted keys, zero hits → `0.0`).

## 5. Completeness — identity reconciliation, and two populations (R3 F1/F2)

**Expected set:** `expected_ids` = source_ids whose final Pass-1 envelope is signal (Pass-1 sidecars are authoritative); `header.p2_attempted` is a **count cross-check**, not a substitute for identity reconciliation.

```
matched_ids := valid context-record source_ids ∩ expected_ids
context_record_coverage := len(matched_ids) / len(expected_ids)   (None when expected_ids is empty)
complete :=
    matched_ids == expected_ids
    AND no duplicate ids  AND no unexpected ids
    AND no malformed records  AND no wrong-run records
```

**Zero-expected case frozen:** `expected_ids == ∅` ⇒ coverage `None`, all substantive aggregates `None` — never a vacuous `1.0`.

**Two populations (R3 F2):**

- **Record-coverage population** — every expected source, *including* `context_failed` records (auditable evidence set).
- **Substantive-metric population** — `status == "complete"` only. `context_build_success_rate = complete_records / expected_records` (published). Tier means and key rates compute over complete records **only** — a context-build failure is a Pass-2 quarantine signal, never a legitimate zero-context observation. Expected-but-zero-complete ⇒ substantive aggregates `None`.
- A later model/validation/canonicalization/commit failure does **not** exclude a record: the context build completed; the event-time evidence is valid.

**Partial-evidence policy:** record-write failure is warn-only (source unaffected), but if `complete` (above) fails, all new substantive aggregates emit as `None` — incomplete evidence never masquerades as complete; the coverage diagnostic makes the reason visible.

## 6. Resolver enrichment (R1 F5 + R2 F7)

One shared enriched core in `kdb_graph/queries.py` returning `(canonical_slug, first_run_id)` per key — same precedence/active rules as `resolve_to_canonical_slugs` (`:459-517`), which remains as the slug-only projection. **Both** paths enriched: `simple` and the `batch` escape hatch (`context_loader.py:432-435`); simple ≡ batch parity pinned for outcomes **and** stamps.

## 7. Surfacing (R2 F8)

All Task-122 watched fields ride one explicit path: CLI extracts per model → `build_pass_board(..., pass1_watched_by_model=...)` → `_build_row` merges into Pass-1 `raw_values` for ranked, partial, **and** fallback/unranked rows → JSON + Markdown from the same values. `measurements.json` → `report.md` → main leaderboard data-driven/free. Tests for a ranked row and a fallback row.

## 8. Phases (R3 F5 — docs gate ahead of blueprint)

- **P0 — post-ratification docs gate:** `TASKS.md` #122 row updated from the v1.0 post-run language to the event-time contract; `CODEBASE_OVERVIEW.md` gains the event-time capture decision + metric meanings. **Before any blueprint work.**
- **Blueprint:** technical design (dataclasses, record schema, gather/reconcile logic, test plan) → Codex review → Proceed.
- **P1 — capture:** `ContextBuildResult` split (prompt byte/hash pins); enriched resolver core (both paths); record writer (atomic, `context/` namespace, statuses incl. synthesized `context_failed`); record-level tests.
- **P2 — aggregation + surfacing:** gather + reconciliation + coverage policy; watched fields; late/never split; Pass-1 board plumbing; reference docs; North Star milestone + `TASKS.md` closure.

## Acceptance

- **Coexistence:** run with response records + context records loads strictly; original `pass2_records` count; `pass2_malformed == 0`; measurements + both boards built.
- **Prompt identity:** byte-identical prompt text + hash pre/post #122; no telemetry key in prompt JSON.
- **Event-time truth table:** pre-seeded old target → `resolved_t2_seed` + pre-run; target created by an earlier source under the same run_id → hit + cohort; empty-graph miss later created → late; miss absent post-run → never; missing stamp → `age_unknown`; off-domain → `resolved_out_of_scope`; already-T1 → `resolved_already_t1`; two keys one canonical → second is `resolved_duplicate_seed`.
- **Cap pressure (R3 F3):** T1 fills the cap; a key is a valid `resolved_t2_seed` with `t2.delivered == 0` — never described as prompt-delivered; `t2_seed_rate` > 0 while `context_t2_delivered_mean == 0`.
- **Completeness:** missing / substituted / duplicate / unexpected / malformed / wrong-run records each fail the `complete` predicate (aggregates `None`) even at numerical coverage 1.0; zero-expected ⇒ coverage `None`; warn-only record-write failure preserves the source AND forces aggregates `None`; `context_failed` counts toward coverage but never toward tier means/key rates; 0-hit run ⇒ hit rates `0.0`.
- **Tier arithmetic:** `sum(delivered) == len(snapshot.pages) ≤ page_cap`.
- **Parity:** simple ≡ batch resolver outcomes+stamps; legacy metric byte-identical on the existing fixture.
- No change to scored KPIs, Borda, or production write paths beyond the `context/` sidecar; full suite green.
