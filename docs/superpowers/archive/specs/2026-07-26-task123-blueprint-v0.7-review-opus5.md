# #123 Blueprint v0.7 + spec v0.9 — opus5 confirmation review

Date: 2026-07-26 · Respondent: **opus5** · Reviewing: `…-blueprint-v0.6-to-v0.7-confirmation.diff` (spec v0.8→v0.9, blueprint v0.6→v0.7, 258 lines)
Prior rounds: F1–F8 · G1–G8 · H1–H9 + removal audit · J1–J4 · L1–L3 · M1–M4

## Verdict: **CONCUR — ratify**

**All four M-items landed verbatim:**

| M | landed as |
|---|---|
| **M1** | `budget_estimation_miss` re-typed **`status: budget_exceeded`, `detected: post_call`** (preflight = `pre_call`), **excluded from the §8.4 selector-failure gate**, watched series kept — and the reasoning I gave carried into the normative text at §3.4, §8.4, §8, and the telemetry record (`detected` is now a per-stage budget-record field). |
| **M2** | §8.5 gains the retention-pressure confound note with the 39%-vs-8% figures, reports the whole-graph arm's stage-1 recall alongside, and records the M ≥ 163 variant; §8.3 metric 2 gains **M≈5/163 (~3%)** with the reason stated — the earlier 12–40% points never reached the regime the gate approves. |
| **M3** | All three synced: R4's trailing clause, SD-4's last `recall@150`, blueprint §7's 381 kB. |
| **M4** | `keys_emitted` = original expressions, audit = rendered forms, affected indices flagged — with the "#122 series keeps its meaning" rationale. |

**D8 is a good ruling and the `evidence` drop is the right instinct** — it was the only free-prose field on the
wire, unbounded and unverifiable, and *take the content, not the semantics* applies to the selector's output as
much as its input. Index-based `matched` is strictly better than repeated strings, and out-of-range ⇒ coerce-drop
keeps R1 intact. Two items on D8's mechanics below.

---

## Findings

### N1 — the ≤ 96 B slug wire bound is **below the project's canonical slug cap**, and it is load-bearing in the allowance arithmetic (load-bearing)

D8 declares a **slug wire bound ≤ 96 B** with a render-time controller assertion, and derives
`OUTPUT_ALLOWANCE_THIN = 4,000` from it (100 × ≤ 96 B ≈ 9,600 B ⇒ ~3.2k tokens at 3 B/token).

The project's canonical slug cap is **120**: `common/paths.py:27` `MAX_SLUG_LEN = 120`, enforced at `:58-59`
(kebab truncation) and `:67-68` (`PathError` above it). A 97–120 byte slug is therefore **valid canonical data**,
and the compiler already generates against that budget (`compiler/summary_slug.py:18` computes the summary stem as
`120 − len("summary-")`). So:

1. **The assertion fires on legitimate slugs.** A typed failure is better than silent truncation, but the trigger
   is valid data, and it would abort a search for a reason that isn't a defect. Fixture max is 64
   (`summary-relative-ranking-methods-borda-condorcet-and-aggregation`) so nothing binds today — but that's a
   *64-byte slug from a moderate title*, and vault-scale titles will reach further.
2. **The allowance has margin only because the bound is too low.** At the real cap: `100 × 120 B = 12,000 B ⇒
   4,000 tokens at 3 B/token` — **exactly the entire THIN allowance, zero margin.** That is precisely the
   truncation ⇒ `unparseable` ⇒ retry ⇒ identical-overflow ⇒ hard-gate chain L1 closed, reintroduced through a
   constant chosen independently of the one the repo already enforces.

**Fix:** set the wire bound to `MAX_SLUG_LEN` — **imported from `common.paths`, not re-declared** (`kdb_search`
imports `common`, so this is a direct import, and a second slug-length constant is exactly the kind of drift the
boundary test exists to prevent) — then re-derive: `100 × 120 B = 12,000 B` ⇒ THIN ≈ **6,000** to keep the ~1.5–2×
margin the allowances were deliberately sized for. Keep the render-time assertion as a defence against
*non-canonical* input (it would then only fire on data that already violates `paths.py`, i.e. a real defect).

FAT is unaffected — its ~170 B/entry estimate is dominated by the fixed JSON structure, and at 120 B slugs it rises
to ~190 B ⇒ ~3.2k of 4,000, still inside margin.

### N2 — the `evidence` drop is justified on *consumption* grounds, but it is a change to the selector's *task*, and the whole cohort runs with thinking disabled (load-bearing for the D7 experiment, not for implementation)

The stated case is that nothing downstream consumed `evidence` — verified as far as I can tell, and I'm not arguing
to keep it. But "nobody reads it" answers whether it is *useful output*; it does not answer whether **producing**
it changes the selection. Those are different questions, and one repo fact makes the second non-trivial:

**every model in the cohort runs with thinking disabled** — `gpt-5.4-mini` and `gemini-3.6-flash` take the
`thinking` default (`common/model_pool.py`: `entry.get("thinking", "disabled")`), `deepseek-v4-flash` sets it
explicitly. So there is no reasoning channel anywhere in this pipeline, and a per-hit prose field was the only
place the selector could reason in-band before committing to a hit. Removing it may improve the selection (less
room to rationalize a weak pick) or degrade it (no room to work). We have zero evidence either way, and the change
is landing *before* any baseline exists.

**Fix — one line in the D7 program, no implementation cost:** carry the with-/without-`evidence` prompt as a
**variant in the selector A/B** (the harness is already parameterized for three candidates and reduced-M points;
this is one more axis on the same runs). If it makes no difference, the drop is confirmed on evidence rather than
on the absence of a consumer — and that is the same standard R3's truth-set-before-tuning gate applies to
everything else in this design.

### N3 — `tokens_lte_bytes` cannot be "asserted at route resolution" (minor, and the fix makes it stronger)

§7 says the invariant is "asserted at route resolution." Nothing local can verify a claim about a provider's
tokenizer — the absence of a local tokenizer is the premise the entire D5 calibration mechanism rests on, and D5
measures a *ratio*, not a bound.

But the invariant doesn't need verifying, because it is a **theorem for byte-level BPE**: every token maps to at
least one byte, so content tokens ≤ content bytes, and all four pool providers use byte-level BPE. State it that
way — a **declared per-route premise with its reason**, presence-checked at resolution — rather than as something
the code verifies. The existing qualifier "*content* token count" is already doing real work and should keep its
footnote: chat-template and special tokens add tokens with no content bytes, immaterial here given 59k of slack
(261k vs 320k).

---

## Verified

- **`MAX_SLUG_LEN = 120`** at `common/paths.py:27`, raising `PathError` above it (`:67-68`); the summary-stem
  budget derives from it (`compiler/summary_slug.py:18`). Fixture longest slug = 64 B (N1).
- **Thinking disabled across the cohort** — `gpt-5.4-mini` and `gemini-3.6-flash` by default,
  `deepseek-v4-flash` explicitly (`common/models.json` + `model_pool.resolve_models_json`) (N2).
- **D8's allowance arithmetic** reproduces at its own premises: 100 × 96 B = 9,600 B ⇒ 3,200 tokens at 3 B/token
  (stated ~3.3k); 50 × ~170 B = 8,500 B ⇒ ~2,833 (stated ~2.8k). Both inside 4,000 — the issue is the 96, not the
  arithmetic.
- **M=100 static guarantee unchanged and still holds** — 257 kB ⇒ 257k + 4k output = 261k < 320k.
- **`matched: [int]` indexing is consistent with M4** — truncation preserves expression count and order, so index
  *i* maps to rendered expression *i* maps to original *i*; State C (`expressions: []`) yields an empty index
  space and wholly unattributed hits, already a handled case.

## Recommendation

**Ratify.** N1 is one constant (imported rather than re-declared) plus a re-derived allowance — worth fixing before
P1 pins `test_budget.py`, since it currently encodes a bound that contradicts `paths.py`. N2 is one line in the D7
program. N3 is a rewording that strengthens the claim. Nothing reopens the architecture or contradicts D1–D8.
