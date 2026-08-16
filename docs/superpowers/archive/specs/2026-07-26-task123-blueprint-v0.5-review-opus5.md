# #123 Blueprint v0.5 + spec v0.7 — opus5 confirmation review

Date: 2026-07-26 · Respondent: **opus5** · Reviewing: `…-blueprint-v0.4-to-v0.5-confirmation.diff` (spec v0.6→v0.7, blueprint v0.4→v0.5, 252 lines)
Prior: round-1 · synthesis · vision · spec v0.1–v0.3 · blueprint v0.1 (F1–F8) · v0.2 (G1–G8) · v0.3 (H1–H9 + removal audit) · v0.4 (J1–J4)

## Verdict: **CONCUR — ratify** (verify-the-fold pass; my v0.4 verdict was already CONCUR)

**All four folds confirmed landed:** J1 as **D6** — query ceiling 4,096 B, `OUTPUT_ALLOWANCE_FAT` declared, and the
both-stage asymmetry closed by giving fat the *same* calibrated preflight rather than a bespoke static claim
(stronger than what I asked for); J2 as codex K3's compat artifact; J3 with D5 held at 3 calls and the
headroom-carries-density-variance statement now explicit in two places; J4 with §7.2 synced to the measured
66k/211k. Per-fold evidence in §1.

Two corrections in this round land on **me**, and both are right — recorded in §1.

Three items below are things the *fold itself* introduced (a constant D6 declared, and the new terminal D6
created), not reopened design.

Three items below. **L1** is the one worth folding before P2 writes the prompt contracts (a constant, sized from a
schema that doesn't exist yet — cheap now, a deterministic hard-gate failure later). **L2** is a result-contract
row that the D3 precedent says should be spelled out. **L3** is a stale phrase. None blocks ratification.

---

## 1. J1–J4, and two corrections against me

| J | v0.5 / v0.7 disposition | Verdict |
|---|---|---|
| **J1** stage-2 request unbounded | **D6 (Joseph): one budget calculation method for both stages.** Fat gets the same calibrated estimate over the fully rendered request + 80% guard; typed `budget_exceeded`, stage recorded, zero spend, never retried; branch table gains the fat-budget row; §2.2 gains the check in the right position (after D3's terminal, before the fat call); rendered-query ceiling **4,096 B** with `query_truncated` telemetry; **`OUTPUT_ALLOWANCE_FAT = 2,000`** declared | **Closed beyond what I proposed.** I asked for the accounting to be *stated*; D6 makes it *enforced*, which retires the whole class of objection. See **L1** on the constant's value and **L2** on the new terminal's contract. |
| **J2** fixture policy version | **codex K3 option b:** fixture v1 manifest stays **immutable at `"1"`**; a checked sibling `…_policy_v2_compat.json` records the equivalence with its proof (2,209 B < 2,500 B ⇒ ceiling binds on nothing ⇒ bytes identical); harness records effective policy `"2"` | **Closed — and codex's option beats mine.** I proposed bumping the manifest field; his preserves the immutability principle he established in confirmation #4 (never mutate a checksummed artifact), and the equivalence proof is checked in rather than asserted in prose. |
| **J3** single-density calibration | §7.2 + D6: "conservative" / "provably fits ≥128k" relabeled **calibrated-with-headroom**, with the 0.8 factor explicitly carrying density variance; D5 unchanged at 3 calls | **Closed as option b**, which is what I said was defensible — the point was that it shouldn't be silent, and now it's normative text in two places. |
| **J4** §7.2 stale figures | Synced to the measured 66k / 211k | **Closed.** |

**Two corrections against me, both correct:**

1. **codex K1's relabeling.** My H1 fix made the *byte* accounting a projector property; v0.4 then wrote that
   `150 × 2,500 B ≈ 94k tokens < 102.4k` "holds **by construction** for any window ≥ 128k." That inference is
   invalid — bytes ÷ 4 is a calibrated ratio, not a bound, so a byte ceiling cannot yield a token guarantee. The
   overclaim originates in my H1 language ("a property of the code"), which was true of the byte side only and got
   carried across. v0.7's split — byte accounting = projector property, token fit = calibrated estimate + runtime
   preflight — is the honest statement, and it is the third time this bound has been tightened by someone catching
   the previous framing.
2. **codex K3 over my J2**, as above.

**Also correct and unprompted:** the byte-ceiling/sentence-rule precedence clause (when the 2,500 B ceiling binds,
truncation wins over "no mid-sentence cut" — otherwise policy v2 is self-contradictory on exactly the pages it
binds on), the envelope-count invariant qualified as a **successful-write** condition with
`search_artifact_write_failures` (warn-only persistence means my "independent side" could otherwise read as a
violation when it's a known write failure), and K2's R3-row sync.

I re-verified v0.7's new arithmetic: the ~96–98k full-fat-request figure reconciles (93.75k evidence + 1.02k query
+ ~0.75k system/template + 2k output ≈ 97.5k, ~4.9k under the 102.4k budget), and the ≤ ~381 kB worst-case byte
accounting is consistent with the three ceilings.

---

## 2. Findings

### L1 — the output allowance is a *hard truncation ceiling* on exactly the two responses the design asks to be large, and 2,000 is likely undersized for fat (load-bearing for P2)

`OUTPUT_ALLOWANCE_THIN = OUTPUT_ALLOWANCE_FAT = 2,000`, reserved via `ModelRequest.max_tokens = 2000`. That
constant does two jobs: it reserves budget in the estimate, **and it truncates the provider's response**. The
second job is the problem, because the two responses it caps are the ones the contract asks to be maximal:

- **thin** returns up to **M = 150** retained slugs under a prompt that says "when in doubt, retain";
- **fat** returns up to **`max_results` = 50** entries, each a slug *plus* a `matched_expression`.

Measured against the fixture's real slugs (mean 24.9 chars, max 64), rendered as JSON:

| response | bytes | ÷4 | at a pessimistic 3 B/token |
|---|---:|---:|---:|
| thin, 150 retained slugs | 4,577 B | 1,144 | 1,526 |
| fat, 50 × `{slug, matched_expression}` | 5,709 B | 1,427 | **1,903 (95% of the allowance)** |
| fat, same + one extra field (e.g. `rank`) | 6,300 B | 1,575 | **2,100 — over** |

At the ÷4 ratio both fit; at a plausible slug-dense ratio the fat response sits at 95% of its own reserved
ceiling, and one additional field, longer `matched_expression` strings, or longer vault-scale slugs put it over.

**Why this failure mode is worse than a normal overflow:** `max_tokens` truncation cuts the response mid-JSON ⇒
`unparseable_response` ⇒ the §8 retry class fires ⇒ **the retry hits the identical deterministic overflow** ⇒
`selector_failure`. Two calls burned, no possible recovery, landing on a **hard gate** (`selector_failure` rate),
and under R1 there is no fallback — the source gets an honest empty T2. A cap-shaped defect would present as a
model-quality problem in exactly the metric that is supposed to detect model-quality problems.

**Fix (cheap, and the right moment is before P2 writes the prompt contracts):** size each allowance from its own
response schema rather than sharing one constant — thin from `M × per-slug budget`, fat from
`max_results × per-entry budget` — with real margin, and have P1's `test_budget.py` assert each allowance against
a **worst-case rendered response** (150 longest slugs / 50 max-length entries) instead of asserting nothing about
it. My rough sizing: thin ~3,000, fat ~4,000.

**One coupling to note, since it cuts the other way.** The allowance is *added to the input estimate*, so raising
fat's to 4,000 spends 2k of the ~5k ceiling-case headroom at a 128k window: 93.75k + 1.02k + 0.75k + 4k ≈ 99.5k of
102.4k, i.e. ~3% slack. The three D6 constants (2,500 B × 150 evidence, 4,096 B query, output allowance) are now
**jointly** calibrated against a 128k window with only a few percent of total slack in the all-ceilings case. That
is fine — the configured pool is 400k/1M/1M, and the preflight fails closed and visibly if it ever binds — but it
is worth stating in §7 that the 128k claim is a *joint* property of three constants, so a future change to any one
of them is a budget change, not a local tweak.

### L2 — the new fat-`budget_exceeded` terminal has no complete result contract (minor, but the D3 precedent says spell it out)

§2.2's new branch reads: `→ budget_exceeded, execution=thin_attempted, stage=fat recorded`. codex c-1 required the
**D3** terminal to carry its full result shape (hits `[]`, all expressions unresolved, concordance null,
`evidence_status: not_applicable`, `body_coverage: None`, fat-side yields null), and §12's contract-test matrix
consumes exactly that. The fat-`budget_exceeded` terminal is structurally the same object — thin ran, fat never
did — and gets one clause.

Everything is derivable (concordance null by codex #12's rule since no fat stage ran; `not_applicable` since there
is no fat evidence pool), but "derivable" is what c-1 declined to accept for D3, and the matrix row has to be
written either way. Two additional specifics worth naming while you're there:

1. **`status: budget_exceeded` now pairs with two different `execution` values** (`not_executed` for the thin
   preflight, `thin_attempted` for the fat preflight). §9's contract test names the new pair, so this is
   consistent — just make sure the matrix is stated as a two-row entry rather than a single `budget_exceeded` row.
2. **The F1 interaction is unspecified.** On the thin-failed/N≤M path, stage-2 input is all-eligible and
   `execution` was going to be `fat_after_thin_failure`; if the fat preflight then fires, the result carries
   `budget_exceeded` + `thin_failed_nonbinding` + (presumably) `execution: thin_attempted`. That combination is
   coherent but unnamed, and it is the only path where thin failed *and* a fat preflight runs.

### L3 — one stale phrase (minor)

Spec §7.2's SD-5 bullet still describes the guard as "the pre-flight `budget_exceeded` check (80% of the
configured window, runtime estimated **serialized thin tokens**)". After D6 it is per-stage. Same for the §11 SD-5
decision row. One word each.

---

## 3. Verified against the repo

- **Slug distribution used in L1** — fixture v1: 163 slugs, mean 24.9 chars, median 23, max 64
  (`identities.json`); the JSON renderings above are computed from those actual slugs.
- **`summary` / `key_themes` schema-unbounded** — `ingestion/enrich/pass1_schema.py:77-78`; `entity_search_keys`
  capped at 10 (`:85-89`). D6's citation is exact, and the 4,096 B query ceiling targets the right field.
- **Fixture manifest still `excerpt_policy_version: "1"`** — consistent with K3 option b's immutability choice.
- **Fixture max rendered fat block 2,209 B < 2,500 B** — the compat artifact's proof holds.
- **Pool windows / output caps** — `gpt-5.4-mini` 400k ctx / 128k max_output; `gemini-3.6-flash` 1,048,576 / 65,536;
  `deepseek-v4-flash` 1,000,000 / 384,000. Raising either output allowance is unconstrained by the pool — the only
  cost is the budget arithmetic in L1's coupling note.
- **Full-fat-request ~96–98k and ≤ ~381 kB worst-case byte accounting** — both reproduce from the three ceilings.
- **Branch table** now has six rows including the fat-budget row; call counts consistent with §2.2's flow.

## 4. Recommendation

**Ratify.** L1 is a constant plus a test assertion, best fixed before P2 pins the prompt contracts; L2 is one
clause and two matrix rows; L3 is a word. Nothing reopens the architecture, contradicts D1–D6, or moves a phase
boundary. This is the round where the remaining items stopped being about the design and started being about
constants — which is the right place for a blueprint to land.
