# #123 Blueprint v0.6 + spec v0.8 — opus5 confirmation review

Date: 2026-07-26 · Respondent: **opus5** · Reviewing: `…-blueprint-v0.5-to-v0.6-confirmation.diff` (spec v0.7→v0.8, blueprint v0.5→v0.6, 261 lines)
Prior rounds: F1–F8 · G1–G8 · H1–H9 + removal audit · J1–J4 · L1–L3

## Verdict: **CONCUR — ratify**

L1–L3 absorbed; my L1 numbers used verbatim (THIN 3,000 / FAT 4,000). **D7's M=100 is the best move of the
round** and it isn't mine or codex's — it dissolves the whole budget argument by sizing instead of measuring:
`100 × 2,500 B + 4,096 B + ~3 kB ≈ 257 kB ⇒ ≤ 257k tokens even at the pathological 1-token/byte extreme, + 4k
output < 320k`, the pool's smallest budget. Verified, and it holds for any window ≥ ~330k. Three rounds of us
tightening a token estimate are retired by one constant, at zero behavioral cost today (largest domain 51 < 100).
It also makes §8.3 metric 2 binding on the whole-graph fixture space, which is a real gain.

Three items. **M1** is a hard-gate contamination and the one to fix before P1. **M2** is an experiment-design
consequence of M=100 in a section D7 didn't touch. **M3** is a live contradiction about the production constant.

---

## 1. L1–L3 absorption

| L | v0.6 / v0.8 disposition | Verdict |
|---|---|---|
| **L1** output allowance | **THIN = 3,000 / FAT = 4,000**, sized from the response schemas, with the truncation ⇒ `unparseable` ⇒ retry ⇒ identical-overflow ⇒ hard-gate chain recorded as the reason, and §12 asserting each allowance against a worst-case rendered response (100 longest slugs / 50 max-length entries) | **Closed exactly**, my numbers carried through (100 slugs ≈ ≤1,017 tok; 50 entries ≈ ≤1,903 tok at 3 B/token — both now ~2× under their allowance). My coupling caveat is moot: M=100 freed the headroom the larger allowances spend. |
| **L2** fat-budget terminal | Complete contract in §2.2 (hits `[]`, all expressions unresolved, concordance null, `not_applicable`/`None`, **no fat StageRecord**), the two-row `budget_exceeded` matrix, and the F1 interaction named | **Closed, with one addition I didn't ask for** — "no fat StageRecord" is the right call and keeps `logical_call_count == StageRecords` intact on this path. |
| **L3** SD-5 stale phrase | Per-stage | **Closed.** |

**codex L2 corrects me, and is right:** my J1 called `summary` "the only realistically unbounded SD-1 field."
`author` is `{"type": ["string","null"]}` and `key_themes` is an unbounded array — both verified at
`pass1_schema.py:77-89`, only `entity_search_keys` is capped (10). v0.7 encoded my characterization as
summary-only truncation, which was an observed-input assumption, not a projector property. The per-field
allocation (author ≤ 256 B / keys ≤ 10 × 128 B / themes ≤ 1,024 B / summary ≤ remainder) is the correct
generalization. That's the third correction against me in two rounds; all three were mine to make and I didn't.

---

## 2. Findings

### M1 — `budget_estimation_miss` is typed `selector_failure`, which contaminates a hard gate (load-bearing)

D7 types the thin-side residual as `status: selector_failure`, `failure_class: budget_estimation_miss`
(spec §3.4). §8.4's hard gate is **"selector-failure rate ≤ ceiling — the 'is #123 delivering' measure."** So an
estimator under-call — *our* `bytes ÷ 4` mis-calibrating against a dense corpus — lands in the metric that is
supposed to measure the selector's behavior, and:

- it counts against the **model's** per-model selector-failure series on the leaderboard, for a failure the model
  did not commit;
- it penalizes **smaller-window models systematically** — they reach the guard sooner on identical inputs — so the
  gate acquires a window-size preference unrelated to selection quality;
- it contaminates the single hard gate that answers whether #123 works, which is R1's whole compensating control.

The spec already has the precedent, twice: **`budget_exceeded` is its own `status`**, deliberately not a
`selector_failure` — and `budget_estimation_miss` is the same event detected one step later. And §8.3 already
excludes `cap_exhausted_possible` / `unattributed_possible` from abstention scoring for exactly this reason: don't
score our own mechanics as model behavior.

**Fix:** give it its own status — or `status: budget_exceeded` with `detected: post_call` (which reads truer: it
*is* a budget outcome, just caught by the provider instead of the preflight) — and exclude it from the
selector-failure-rate gate. Keep the per-model watched series; it is genuinely informative about corpus density
and estimator calibration, which is what it measures.

### M2 — M=100 changes the §8.5 cross-domain A/B's confound profile, and §8.5 wasn't touched (load-bearing for the D7 experiment)

§8.5 runs the selector twice per source — domain-scoped space vs whole graph — to answer whether whole-graph scope
beats domain scope. Retention pressure across that pair has just moved:

| | domain arm (51) | whole-graph arm (163) |
|---|---|---|
| at M=150 | retain-all | 150/163 = **92%** retained |
| at M=100 | retain-all | 100/163 = **61%** retained |

The domain arm is retain-all by controller enforcement; the whole-graph arm must now discard 39%. A whole-graph
loss can therefore be attributed to *scope* when it is *retention pressure* — and §8.3 metric 2 celebrates the same
binding as a gain (correctly, for its own purpose). Both readings are right; §8.5 needs the note.

**Fix:** state in §8.5 that the arms differ in retention pressure as well as scope, and either report the
whole-graph arm's stage-1 recall alongside its result, or run the scope comparison at M ≥ 163 (non-binding on both
arms) while keeping M=100 for the production-path measurement.

**Related, and it is my own protocol I'm questioning:** the reduced-M gate points (M=10/20 over 51; M=20/40 over
163) test retention ratios of 12–40%. Production at vault scale will be **100 / ~3,000 ≈ 3.3%**. The gate points
do not bracket the regime the gate authorizes — true at M=150 (5%) too, so D7 only mildly worsens it, but the fix
is one more point: add M≈5 over the 163-entity space (~3%) so the curve reaches production's ratio before the gate
approves vault ingestion.

### M3 — R4's body still declares **M=150** the production constant (load-bearing, documentation)

Spec §7.2's R4 bullet was updated to "largest domain 51 < M=100" but its own trailing clause still reads
*"(predeclared per SD-4; **M=150 stays the production constant** — naming corrected per codex K2: recall@150 is
non-binding on this fixture …)"*. The SD-4 row, the R4 decision row, §8.3 metric 2, and §8.4 all now say M=100. So
the normative body contradicts itself inside one bullet, on the production constant.

Two more stale figures in the same family:

1. **spec §7.2, SD-4 option comparison:** *"Predeclared measurement: stage-1 **recall@150** on the fixed truth
   set"* — the last surviving `recall@150`, which outlived both codex K2's sweep and D7's renumbering.
2. **blueprint §7:** the "Both stages guarded (D6)" bullet still says fat is *"byte-capped by construction
   (≤ ~381 kB full request)"* — the M=150 figure, sitting directly below the bullet that now says ≤ ~257 kB.

### M4 — which form of a truncated expression goes into `keys_emitted`? (minor)

Per-field truncation can shorten an `entity_search_keys` item (≤ 128 B/item), and D7 says accounting runs over the
**rendered** expressions with both forms archived. `ContextRecordV2.keys_emitted` — 1:1 with `key_outcomes` — isn't
specified as original or rendered. If rendered, the #122 emitted-key series silently changes meaning when
truncation fires; if original, the record and the accounting describe different strings at the same index. One
clause (I'd carry the original in `keys_emitted`, the rendered form in the audit, and flag the affected index).
Near-zero incidence — keys are short — hence minor.

---

## 3. Verified

- **M=100 static guarantee** — 100 × 2,500 = 250,000 B + 4,096 + ~3 kB ≈ 257 kB ⇒ 257k tokens at 1 B/token, + 4k
  output = 261k < 320k (gpt-5.4-mini 400k × 0.8); the "≥ ~330k window" threshold follows (261/0.8 = 326k). Holds.
- **Cost figures all reconcile** at `price_in` 0.14 / 0.75 / 1.5 per 1M: fat 100 × 719 B ≈ 18k; 66k + 18k = 84k;
  1,706 × 84k ≈ 143M ⇒ $20 / $107 / $215; ceiling case 66k + 62.5k = 128.5k ⇒ 219M ⇒ $31 / $164 / $329.
- **Output-allowance headroom** — recomputed from the fixture's real slugs (mean 24.9 chars, max 64): 100 retained
  slugs ≈ 3,050 B (1,017 tok at 3 B/token) against 3,000; 50 fat entries ≈ 5,709 B (1,903) against 4,000.
- **All four SD-1 text fields' schema status** — `pass1_schema.py:77-89`: `summary` unbounded, `key_themes`
  unbounded, `author` unbounded, `entity_search_keys` `maxItems: 10`. codex L2's generalization is correct.
- **§8.3 metric 2's new claim** — largest fixture domain 51 < 100 (non-binding), whole graph 163 > 100 (binding).
  Correct, and it is a genuine measurement gain.
- **Fixture invariants unchanged** — max rendered fat block 2,209 B < 2,500 B; manifest still policy `"1"` per K3.

## 4. Recommendation

**Ratify.** M1 is a status value plus one gate-definition clause — worth fixing before P1 pins the contract matrix,
since it changes what a hard gate counts. M2 is a paragraph in §8.5 plus one reduced-M point. M3 is three stale
figures, one of which is a self-contradiction on the production constant. M4 is a clause. Nothing reopens the
architecture, contradicts D1–D7, or moves a phase boundary.
