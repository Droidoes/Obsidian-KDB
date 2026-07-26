# #123 Blueprint v0.2 → v0.3 confirmation diff — opus5 removal audit

Date: 2026-07-26 · Respondent: **opus5** · Reviewing: `2026-07-26-task123-blueprint-v0.2-to-v0.3-confirmation.diff`
Companion: `2026-07-26-task123-blueprint-v0.3-review-opus5.md` (findings H1–H6 on the diff's *additions*)

## Provenance

The confirmation diff is **byte-identical** to `51a16f2`'s diff for the two files it covers (spec v0.4→v0.5,
blueprint v0.2→v0.3) — verified by regenerating `git diff 51a16f2^ 51a16f2 --` over both paths and comparing.
So the additions are already reviewed in the companion doc: **H1** (stage-2 bound still corpus-estimated rather
than enforced), **H2** (`fat_after_thin_failure` out of contract with the ratified three-value `execution` enum),
**H3** (P1's budget test asserts against calibration measurements that don't exist until end of P2), plus H4–H6.

This doc covers the half a confirmation pass shouldn't skip: **what the diff removed.** v0.3 is 58 lines shorter
than v0.2 (296 → 238). Eight commitments disappeared in that compression, and **no panel item asked for any of
them.** Three are load-bearing.

## H7 — the V2 retained-field list is gone (load-bearing)

v0.2 §3.3 carried an explicit bullet:

> **Kept:** `run_id`, `source_id`, `status`, `t1/t2/t3`, `candidate_universe_size`, `domain_scope`, `cold_start`,
> `max_hops`, `page_cap`, `keys_emitted` (= expressions).

v0.3 §3.3 lists loader dispatch, hit-level provenance, per-expression outcomes, the KPI resolver removal,
**retired** fields, and the new `search` section — and nowhere states what V2 carries forward.

Why it matters: `candidate_universe_size` / `domain_scope` / `cold_start` are the fields the round-1 domain-gate
starvation evidence was computed from (zero-pool on 34–36% of records across three cold runs), and `t1/t2/t3` +
`page_cap` are what `context_t{1,2,3}_delivered_mean` reads — the #122 headline series this task is measured by.
An implementer building V2 from v0.3 alone has no list to preserve, and `test_context_record_v2.py`'s "factory
invariants / strict parser" cannot catch the omission of a field nobody wrote down.

**Fix:** restore the bullet, or state "V1's fields except the two retired ones."

*Same class, weaker:* v0.2 enumerated the `search` section's counts (`eligible_space_size`, `stage1_retained`,
`stage2_hydrated`, `stage2_title_only`, `returned_entries`, `valid_entries`, `valid_entry_yield`, per-class
`attempted_violations`, `all_entries_dropped`, `unattributed_hit_count`, `retry_attempts`); v0.3 replaces them with
"the §2.3 + flow counts". That is incorporation by reference and still traceable — acceptable, but the record's
field list now exists only as a derivation, not a specification.

## H8 — the #119 interaction is now unstated in both places it appeared (load-bearing)

v0.2 §9:

> `artifact_integrity_hash` validated on load. **#119 byte-pinning survives (caller-supplied `context_snapshot=`
> writes no record — existing behavior).**

v0.2 §3.2 also qualified `search_summary` as *"`None` on the caller-supplied-snapshot path."* **v0.3 drops both.**

So the one ratified invariant this feature could most easily break — #119 prompt-byte pinning, which #122 shipped
golden fixtures specifically to protect — no longer appears in the blueprint at all, and the mechanism that
protects it (caller-supplied snapshots write no record) is unstated.

**Fix:** restore the parenthetical in §9 and the `search_summary` qualifier in §3.2. Two clauses.

## H9 — the retained resolvers' never-surfaced enumeration is gone (load-bearing)

v0.2 §4:

> their output is **never surfaced as search results, fallback, annotation, comparator, or telemetry**.

v0.3 §4: *"identity, not retrieval."*

The short form names the *category*. The long form names the *five ways the category gets violated* — and four of
those five (fallback, annotation, comparator, telemetry) are exactly the forms Joseph's post-concurrence ruling
struck out one version earlier: "no fallback, no annotations, no `exact_matchable` delta, no
`foregone_deterministic_hits`." This is the enforcement clause for R1's no-deterministic-machinery ruling — the
sentence that stops the retained resolver reappearing as "just a watched series."

**Fix:** restore the enumeration.

## Minors in the same sweep

| dropped | where it was | disposition |
|---|---|---|
| **SD-5's survivor telemetry** — "space entity count per search recorded as the tracked trend series; no threshold tuned" | v0.2 §7 last bullet | SD-5 was *dissolved into* that series by a ratified spec decision; with the line gone, nothing in v0.3 records it. One bullet. |
| **Fail-hard propagation posture** — "an *unexpected* exception is a defect and **propagates** — for pass-1.5 it lands in the existing `context_failed` channel" | v0.2 §2.1 | v0.3 keeps fail-hard at *resolution* only. §12's P3a test ("adapter defect ⇒ `context_failed`") still pins the behavior, so this is documentation only. |
| **T3's seed set** — "T3 expands from T1∪T2 seeds" | v0.2 §3.2 | v0.3's "T1/T3/cap/ordering unchanged" is true, but that clause is *why* better T2 pays off downstream (#122 measured T3 0 cold → 22 warm) — the mechanism behind #123's headline benefit. Half a line. |
| **`delimiter_collision_guard`'s test hook** | v0.2 §12 `test_projection.py` | Still specified in §5; the §12 line now reads "§5 grammar incl. both G7 clauses" without the guard counter. |
| **`atomic_write_json` / `_write_context_record` precedent** | v0.2 §3.1 step 5 | Harmless — project convention covers it. |

## Why this is a finding rather than a shrug

v0.3 is a better document *because* it is terser, and compression is the right instinct for a blueprint heading
into ratification. But a ratification artifact is the thing an implementer builds from, and these eight lines were
commitments rather than prose. Four of them (H7, H8, H9, SD-5) are now traceable only to a superseded version of
the same file — which is exactly where a commitment goes to die.

Restoring them costs roughly six lines. Combined with H1–H3 from the companion doc, that is the full set I would
fold before ratification.
