# #123 Blueprint v0.8 + spec v0.10 — opus5 confirmation review

Date: 2026-07-26 · Respondent: **opus5** · Reviewing: `…-blueprint-v0.7-to-v0.8-confirmation.diff` (spec v0.9→v0.10, blueprint v0.7→v0.8, 187 lines)
Prior rounds: F1–F8 · G1–G8 · H1–H9 + removal audit · J1–J4 · L1–L3 · M1–M4 · N1–N3

## Verdict: **CONCUR — ratify**

**N1–N3 all landed, and N1's resolution improved on my fix.** I proposed importing `MAX_SLUG_LEN` and bumping THIN
to ~6,000 to restore the density margin; codex N2 removed the density step entirely instead — allowances now equal
the **exact max serialization of the fully-bounded wire**, covered by `tokens_lte_bytes` (tokens ≤ bytes), so
THIN 13,000 / FAT 10,000 are proofs rather than estimates. That is strictly better: no 3 B/token guess survives
anywhere in the output path.

Verified both: THIN exact max = **12,315 B** ≤ 13,000 ✓. FAT exact max = **8,404 B** ≤ 10,000 ✓.

**codex N1 caught a real D8 miss neither of us saw last round:** `Hit.evidence` survived in the *public result
contract* (spec §1.1) after D8 dropped it from the wire. My N2 argued about whether dropping it changes behavior and
I never checked whether the type still declared it.

N3 landed as a validated `models.json` boolean carried by `ModelSpec`, presence-checked at selector route
resolution, with the byte-level-BPE theorem as its stated reason — and correctly scoped: pass-1/pass-2 routes don't
require the field, which fits Gate 1's existing structure (it can't know which models are selectors). N2 became
§8.6 as a variant axis on the existing runs.

One load-bearing item, two minors.

---

## Findings

### O1 — the wire's index caps and the FAT allowance rest on an undeclared "≤ 10 expressions" assumption imported from pass-1.5 (load-bearing)

v0.10 states every numeric maximum (codex N2's point, and the right move): `selections` ≤ `max_results` (≤ 50),
`slug` ≤ `MAX_SLUG_LEN`, **`matched` ≤ 10 unique indices**, **`unresolved` ≤ 10 indices**. The two index caps come
from `entity_search_keys`' `maxItems: 10` (`ingestion/enrich/pass1_schema.py:88`) — a **pass-1.5 schema
constraint**, stated here as a property of the consumer-neutral wire.

But `graph_search` is consumer-neutral by ratified design: `QueryPayload.expressions` is whatever the caller
passed, and the P5b CLI/MCP surface is an explicitly planned second consumer. Nothing in the *contract* bounds
`len(expressions)` — the 4,096 B query ceiling bounds *bytes*, and its per-field allocation (`entity_search_keys`
≤ 10 × 128 B) is again SD-1-specific.

The consequence is arithmetic, not stylistic. Rendering the exact schema maximum at varying expression counts:

| expressions passed | FAT exact max wire bytes | vs `OUTPUT_ALLOWANCE_FAT = 10,000` |
|---:|---:|---|
| 10 (pass-1.5) | 8,404 B | fits |
| 20 | 10,414 B | **exceeded** |
| 40 | 13,414 B | **exceeded** |
| 50 | 14,914 B | **exceeded** |

The break-even is ~15 expressions. So the allowance — the thing v0.10 just promoted from estimate to proof — is a
proof only under a premise the contract never states, and a CLI caller passing 20 expressions reopens exactly the
truncation ⇒ `unparseable` ⇒ retry ⇒ identical-overflow ⇒ hard-gate chain that L1 and N1 closed. This is also the
species of error R2 rules against directly: *no per-consumer distinctions in the contract*.

**Fix (one field, one derivation):** declare `MAX_EXPRESSIONS` in `QueryPayload` — the consumer-neutral core's own
bound, which pass-1.5 satisfies by construction — then derive both index caps and the FAT allowance **from that
constant** rather than from pass-1's schema. A caller exceeding it gets the same treatment as any other bounded
input: typed outcome with telemetry, never silent truncation. If the chosen bound is 10, nothing changes
numerically and the premise becomes explicit; if a larger bound is wanted for the human surface, the allowance
follows from the same formula instead of needing rediscovery at P5b.

### O2 — the 4k→10k output-allowance sweep missed one instance (minor)

Blueprint §7's vault-scale-projections bullet still reads *"≤ ~257k absolute-worst tokens **+ 4k output** < 320k"*
while §7's static-guarantee bullet, the R2 body and the R2 decision row all now say 10k. Same figure, adjacent
bullets.

**Worth more than the one-line fix:** this is the third consecutive round where a constants sweep left one instance
behind (M3 caught three, N-round caught the `Hit.evidence` survivor, this round catches the 4k). The pattern is
structural — M, the excerpt ceiling, the query ceiling, both allowances and the derived totals now appear in five
or more places across two documents. A single **constants table** in §7 that every other mention cites, rather than
restates, would end the recurrence before P1 starts encoding these values in tests.

### O3 — `unresolved` as indices loses the ability to report an expression the selector *invented* (minor, and probably correct)

Under the old string form, a selector could return an `unresolved_expressions` entry that wasn't in the request —
detectable, and counted via `selector_accounting_delta`. Indexed, an invented expression is unrepresentable: an
out-of-range index is coerce-dropped, and the delta then records only a count mismatch, not that the selector
hallucinated a query term. That is a small loss of signal about selector conformance.

I think the trade is right — the bounded wire is worth more than the diagnostic, and out-of-range indices are
themselves the signal — but it should be recorded as a *consequence* of D8 rather than left implicit, since
`selector_accounting_delta` is a watched per-model series and its meaning just narrowed.

---

## Verified

- **Allowance arithmetic** — THIN `{"retained": [100 × 120 B]}` = 12,315 B exact max (v0.10 says 12.3k ✓);
  FAT `{"selections": [50 × {slug 120 B, matched 10 × 1-digit}], "unresolved": [10]}` = 8,404 B (v0.10's 9.6k is
  conservative — fits either way). Both under their allowances via `tokens_lte_bytes`.
- **`matched`/`unresolved` ≤ 10 traces to `pass1_schema.py:88`** `maxItems: 10` on `entity_search_keys` — pass-1.5
  specific (O1).
- **`MAX_SLUG_LEN` import** — `common/paths.py:27`; `kdb_search` imports `common`, so the boundary contract permits
  it and the second constant is gone. N1 closed as specified.
- **`Hit.evidence` removal** — the field is gone from spec §1.1's `Hit`; the fat-stage *evidence pool* (excerpts)
  is untouched, as the diff notes.
- **`tokens_lte_bytes` scoping** — selector-route-only check is consistent with `load_pool()`'s Gate 1, which
  validates every entry but cannot know which model is a selector.
- **§8.6** exists and states the thinking-disabled rationale; **M=100 guarantee** re-checked at the new allowance:
  257 kB + 10k = 267k < 320k ✓.

## Recommendation

**Ratify.** O1 is one declared constant plus a derivation, best fixed before P1 pins `test_budget.py` — it is the
last place a hidden per-consumer premise carries a numeric guarantee. O2 is a line, plus a suggestion worth taking
on its own merits. O3 is a sentence of record-keeping.
