# #131 — T1 Exemption from the Context `page_cap`: Blueprint v0.1

Date: 2026-08-05 · Task: **#131 t1 pages must be exempt from the context `page_cap`** · Status: **v0.1 — RATIFIED (Joseph: "proceed", 2026-08-05) — SHIPPED + CLOSED 2026-08-05**

Ledger row: `docs/TASKS.md` #131 (open). Sequenced after #129 (tier-structured
context, CLOSED) and #130 (deprecated lifecycle, CLOSED) — both landed 2026-08-05.

---

## 1. What #131 is

The fix for the system silently amputating a source's own pages from the model's
view on warm recompiles.

**Verified problem statement.** In sandbox run 7 (`2026-08-05T00-25-04_EDT`,
deepseek warm): `Pabrai interview - August 2025 - 3.md` had **65 t1 candidates,
50 delivered**. The 15 cap-cut pages were never shown to the model, could not be
re-emitted, lost SUPPORTS, and were retracted — 14 became zombie files (pre-#130
semantics; post-#130 they would flip to `deprecated`). This is a system-caused
drop the model gets blamed for: any source that accumulates >50 of its own pages
sheds its tail on **every** recompile, silently. Deepseek's dense minting (305
cold pages vs qwen's 167) is what first pushed a source past the cap.

**Root cause.** `compiler/context_loader.py:160` —
`selected_slugs = [s[0] for s in scored[:page_cap]]` applies the merged cap
across tiers, t1 included. T1 sorts first under strict tier order, so t1 is cut
only when `|t1| > page_cap` — a regime that did not exist until deepseek.

**Fix.** T1 is must-see by contract: **exempt t1 from the cap; the cap governs
t2+t3 only** — flood control was always the cap's purpose (the original design
note: "Token budget for context shouldn't dominate the prompt",
`docs/archive/early/system-prompt.context-pages.md:147` — a t2/t3 concern).
Selection, scoring, strict tier order otherwise untouched.

**Success measure.** A warm recompile of a >50-t1 source delivers every t1 page
(`t1.delivered == t1.candidates`) and loses zero unshown pages (§8).

## 2. Scope and non-goals

**In scope:**

- `context_loader` selection split: t1 delivered in full; t2∪t3 ranked and
  capped at `page_cap` (§4).
- Telemetry + record-parser invariant realignment: the `sum(delivered) ≤
  page_cap` invariant becomes `t2.delivered + t3.delivered ≤ page_cap`, t1
  unbounded (§5) — both parser generations (V1 replay-era, V2 live).
- Test rewrites (4 cap-accounting tests) + new regression pins (§6).
- Sandbox verification: warm audit + faithful 65-page repro (§8).
- Doc closure: TASKS #131 row, North Star §line + Milestone Changelog.

**Non-goals (explicitly deferred):**

- **Per-tier caps on t2/t3** — rejected in #129 (R-129-5), stays rejected.
- **The `page_cap=50` value itself** and pass-1.5 `max_results=50`
  (`kdb_search/constants.py:27`) — selector-side t2 flood control, intact.
- **Prompt changes** — the prompt never mentions the cap (`prompt_builder.py`
  checked); no `PASS2_PROMPT_VERSION` bump.
- **Healing the 14 already-deprecated Pabrai pages.** Deprecated pages are
  excluded from t1 (`context_loader.py:119` builds from active entities) — this
  fix prevents *future* cap-caused deprecations; the existing 14 rely on
  organic re-minting (#130's ratified one-way-door property, revival via
  `intake.py:735`) or the §8 repro's forced re-emit. Not this task's scope to
  change revival semantics.
- **#134-style GC** for accumulating deprecated pages — measure-first, parked.

## 3. Binding rulings and the one design decision

- **R-131-1 — Exemption, owner-filed direction.** Ledger row: "t1 is must-see
  by contract — exempt t1 from the global cap (the cap's purpose is t2/t3
  flood control); selection/scoring otherwise untouched."
- **R-131-2 — t2+t3 keep the full budget.** With t1 out of the cap, the t2∪t3
  budget stays `page_cap` (option A). The alternative considered and rejected:
  budget = `max(0, page_cap − |t1|)` (option C) — it preserves a total bound
  but a >50-page source would **never see t2/t3 again**: no link-don't-duplicate
  inputs, degraded compile quality for exactly the richest sources. Rejected.
- **R-131-3 — Token bound accepted.** ~20 tokens/entry (slug/title/type/links);
  a 200-page source ≈ 4K + 1K context tokens — ledger-accepted. No request-byte
  ceiling interacts (the 3,072 B reserve is the pass-1.5 selector prompt, not
  the pass-2 context block; the context block has no byte ceiling).
- **R-131-4 — Success measure:** warm recompile of a >50-t1 source loses zero
  unshown pages (ledger).

## 4. Design — selection split (`compiler/context_loader.py`)

One region changes (:146-160): build two scored lists instead of one, sort each
with the **same existing key** `(-tier, rank_index, -pagerank, slug)`, then:

```python
t1_sorted   = sorted(t1_scored,  key=...)            # tier 3 — all delivered
rest_sorted = sorted(rest_scored, key=...)           # tiers 2/1 — flood-capped
selected_slugs = [s[0] for s in t1_sorted] + [s[0] for s in rest_sorted[:page_cap]]
```

Consequences, all intended:

- The flat sequence stays strict tier order (t1 first — it sorts first anyway).
- `snapshot.pages` (the #129 derived flat view) can now exceed `page_cap`
  entries: bound becomes `len(pages) ≤ |t1| + page_cap`.
- Projection, `_VALID_PAGE_TYPES` filtering, tier assignment, T3 seeding — all
  untouched.
- Module docstring (:8-11, :19-23) and the ranking-tiers block (:25-34) gain a
  #131 line: cap governs t2/t3 only; t1 is must-see, exempt.
- The TierRecord comment (:177-180) is restated: `t2.delivered + t3.delivered ≤
  page_cap`; `t1.delivered == |valid t1|` (cap-exempt); `sum(delivered) ==
  len(pages) ≤ |t1| + page_cap`.

## 5. Design — telemetry + record parsers

- `common/types.py:362-368` (`TierRecord`): docstring "post-cap" becomes
  per-tier — t1 delivered = full valid set (cap-exempt); t2/t3 delivered =
  post-cap. `ContextTelemetry.page_cap` (:391): field kept, shape unchanged;
  semantics = the budget governing t2+t3.
- `compiler/context_record.py` — both parsers loosen the same invariant:
  - V1 (:239-242) and V2 (:794-797): `sum(delivered) > page_cap` →
    `(t2.delivered + t3.delivered) > page_cap`.
  - **Replay-safe loosening:** every historical record satisfies the old
    invariant (`sum ≤ cap` ⇒ `t2+t3 ≤ cap`), so all stored records still parse.
  - **No schema-version bump** — record shape unchanged; the parser only
    *loosens*. One-way note: a post-#131 record with `|t1| > cap` would be
    rejected by a pre-#131 parser — the repo never replays new records through
    old code (era dispatch is by prompt version), so this is documentation only.
- KPI surface (`compiler/kpi/graph.py:196-200`): `context_t{1,2,3}_delivered_mean`
  read per-tier delivered — no cap-sum assumption; `context_t1_delivered_mean`
  may now exceed 50. Informational series; noted in the changelog, no
  re-baseline machinery.
- `compiler/compiler.py:741` (`page_cap=_DEFAULT_PAGE_CAP` pass-through) and
  the orchestrator call path — untouched.

## 6. Test plan (TDD — define first, then implement)

**Rewrites (cap accounting moved — 4 tests, all in
`compiler/tests/test_context_loader.py` unless noted):**

1. `test_page_cap_truncates` (:168) — today: cap=3, 3 t1 + 2 t2 ⇒ 3 pages.
   New: 3 t1 delivered in full despite cap=3 (the exemption pin) + t2/t3 capped
   at 3 ⇒ assert `t1 == 3`, `t2+t3 delivered ≤ 3`, total ≤ 3+3.
2. `test_binding_cap_selector_rank_decides_t2_survivors` (:178) — the §3.2
   lesson (selector rank, not PageRank, decides under a binding cap) currently
   uses cap=4 = 3 t1 + 1 t2 slot. Under exemption, cap=4 leaves 4 t2 slots (no
   cut). Re-pin with **cap=1** — one t2 slot, first selector hit survives.
3. `test_tier_lists_match_telemetry` (:264) — same cap=4 setup ⇒ cap=1.
4. `test_telemetry_tier_records_pre_and_post_cap` (:672) — cap=4, 3 t1 + 2 t2:
   t2 delivered 1 ⇒ now 2. Rewrite assertions: `t1.delivered == 3` (exempt,
   full), `t2+t3 ≤ cap`; the `total ≤ page_cap` assertion becomes
   `total ≤ |t1| + page_cap`.

**New regression pins:**

5. `test_t1_exceeding_cap_is_fully_delivered` — the defect in miniature
   (Pabrai 65/50): fixture source SUPPORTS 8 active entities, cap=3 ⇒ all 8
   t1 delivered, `t1.delivered == t1.candidates == 8`, t2+t3 ≤ 3,
   telemetry consistent. (Build via extra fixture entities, not a 65-page
   monster — the mechanics are size-independent.)
6. `test_context_record.py::test_parse_rejects_sum_delivered_over_page_cap`
   (:249) — rewritten: **t1 alone over cap ACCEPTS** (60 t1, 0 t2/t3, cap=50
   parses); **t2+t3 over cap REJECTS**. Mirror the same pair for the V2 parser
   in `test_context_record_v2.py` (no cap test exists there today).

**Pass criteria:** full `pytest` suite green (3111 + net-new pins).

## 7. Implementation plan — single phase

| Step | Change | Files |
|---|---|---|
| 131.1 | Selection split + docstring/comment realignment | `compiler/context_loader.py` |
| 131.2 | Parser invariant loosening (V1+V2) + type docstrings | `compiler/context_record.py`, `common/types.py` |
| 131.3 | Test rewrites (4) + new pins (2 sites) | `compiler/tests/test_context_loader.py`, `test_context_record.py`, `test_context_record_v2.py` |
| 131.4 | Full suite; doc closure (TASKS row, North Star + changelog) | `docs/TASKS.md`, `docs/CODEBASE_OVERVIEW.md` |

Order 131.3-first per TDD: write the failing pins, then 131.1/131.2 to green.

## 8. Verification and success measure

1. **Suite gate (must):** `pytest` green, exit 0.
2. **Sandbox warm audit (must):** warm run over `Vault-in-place-test-run`
   (deepseek-v4-flash, single model all passes) — for **every** source,
   `t1.delivered == t1.candidates` in the run's context records; zero pages
   dropped-unshown.
3. **Faithful 65-page repro (recommended):** the Pabrai source currently has 50
   active t1 (14 cap-cut pages sit `deprecated` post-#130). Force re-emit the
   14 slugs through the real `apply_compile_result` path (the #130 revival-probe
   method — revives node + restores SUPPORTS), recreating the 65-active-t1
   condition; warm recompile ⇒ 65 delivered, zero drops of unshown pages.
   This also heals the 14 deprecated pages as a side effect.

## 9. Risks and edge cases

- **Prompt growth** — worst case `|t1| + 50` entries; bounded by source size;
  R-131-3 accepts the token cost.
- **`cold_start` semantics** — unchanged (`len(t1) == 0`); a >cap t1 source is
  warm by definition.
- **Empty/degenerate tiers** — t1 empty ⇒ behavior identical to today (cap
  governs everything present); t2/t3 empty ⇒ t1-only snapshot, valid per the
  2026-08-03 owner ruling (empty tiers compile cold).
- **KPI series drift** — `context_t1_delivered_mean` may exceed 50 from here
  on; flagged in the changelog (§5).

*End of blueprint v0.1.*
