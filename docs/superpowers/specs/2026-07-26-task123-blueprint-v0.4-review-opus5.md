# #123 Blueprint v0.4 + spec v0.6 — opus5 confirmation review

Date: 2026-07-26 · Respondent: **opus5** · Reviewing: `…-blueprint-v0.3-to-v0.4-confirmation.diff` (spec v0.5→v0.6, blueprint v0.3→v0.4, 313 lines)
Prior: round-1 · synthesis · vision · spec v0.1–v0.3 · blueprint v0.1 (F1–F8) · v0.2 concurrence (G1–G8) · v0.3 review + removal audit (H1–H9)

## Verdict: **CONCUR — ratification-ready**

**All nine H-items are absorbed, and three are absorbed better than I wrote them.** H1's remedy is stronger than my
proposal (the ceiling lands on the *rendered block*, so the bound is `150 × 2,500 B` exactly rather than
`2,000 + overhead`); D5 solves the H3/codex-#1 collision by making the calibration call an explicit narrow
amendment with a hard ceiling rather than by hand-waving the D1 line; and codex #4's sibling calibration artifact
fixes a mutation of the checksummed manifest that **I proposed and neither noticed** — my G4 said "persist into the
fixture manifest," which would have broken the fixture's own integrity contract. That correction is on him.

Four items below. **J1** is the one I'd fold before P1 (a §7 clause plus one constant); **J2** before P4. J3/J4 are
one-liners. None of them blocks ratification, and none is an operational risk against the configured pool.

---

## 1. H1–H9 absorption

| H | v0.4 disposition | Verdict |
|---|---|---|
| **H1** stage-2 bound | Excerpt **policy v2**: rendered per-entity fat block hard-capped at 2,500 UTF-8 B, projector-truncating at a character boundary; `150 × 2,500 B = 375 kB ≈ 94k < 102.4k` *by construction*; the falsifying data (102/163 over the implied density; 10.53 B/word ⇒ 113k) recorded in §7; fixture v1 untouched (max 2,209 B) | **Closed, and better than my version.** Capping the *rendered block* rather than the excerpt makes the bound arithmetic exact. Residual: the bound covers the evidence block only — **J1**. |
| **H2** enum out of contract | Spec v0.6 adds `fat_after_thin_failure` at **both** sites (§1.1 `spec:51`, §5.1 `spec:200`), plus the R4 body, the R4 decision row, and §9's contract-test line | **Closed at every site I named, plus two I didn't** (the R4 row and §9). |
| **H3** P1 vs calibration | **D5** (Joseph): one non-comparative call per candidate, hard 3-call ceiling, Joseph fires at end of P2, recorded as a narrow D1 amendment; P1 budget tests **structural-only** against synthetic windows | **Closed.** Making it an owner amendment rather than an interpretation is the same discipline D1 applied to codex's closing line. Minor narrowing side effect — **J3**. |
| **H4** diagnostic population | New §11 bullet: `retry_load`, `token_overrun_rate`, `repair_rung_rate` stay pass1+pass2; pass-1.5 surfaces in its own columns | **Closed verbatim**, with my `processing.py:91-106` citation carried in. |
| **H5** reconciliation invariant | Restated as a **mis-partitioning check**, with the independent side named: `len(glob("search/*.json")) == searches_attempted` | **Closed.** The envelope-count side is exactly the right independent anchor. |
| **H6** provenance read owner | §3.1 gains step **5.5**: batched `entity_first_run_ids` over validated hits, ≤`max_results`, post-validation, **adapter-side — the adapter imports `kdb_graph`, the core never does** | **Closed.** |
| **H7** V2 kept-field list | Restored as an explicit **Kept** bullet (`run_id`, `source_id`, `status`, `t1/t2/t3`, `candidate_universe_size`, `domain_scope`, `cold_start`, `max_hops`, `page_cap`, `keys_emitted`) | **Closed.** |
| **H8** #119 interaction | §9 regains the byte-pinning parenthetical; §3.2 regains the `search_summary` caller-supplied-snapshot qualifier | **Closed at both sites.** |
| **H9** never-surfaced enumeration | §4 restores "never surfaced as search results, fallback, annotation, comparator, or telemetry" and labels it *R1's enforcement clause* | **Closed.** |
| minors | SD-5's survivor series restored (§3.3 counts); fail-hard propagation posture restored as a §2.1 bullet **with the pinning test named**; T3's `T1∪T2` seed clause restored with the 0-cold→22-warm citation; `delimiter_collision_guard` back in §12's `test_projection.py` | **All four closed.** |

**Spec v0.6's normative-body sync** goes past what H2 asked: §7.1's sizing figures are refreshed to fixture
measurements, §8.1 step 4 carries D1 inline, §9's "exactly two calls" becomes the branch contract, §10's
blueprint-routed items are retired as resolved, and the withdrawn v0.5 cell ("~290k expected / ~1M safety-bound —
does not fit") is explicitly labeled as having described an **uncapped single-stage projection the two-stage path
never renders**. That withdrawal is correct and I should have caught it a round earlier — it was in the ratified
spec while R4 had already dissolved single-stage.

I checked v0.6's refreshed arithmetic: 691 B ⇒ ~173 tok, 2,500 B ⇒ 625 tok, 88 B ⇒ ~22 tok, 150 × 719 B ⇒ ~27k,
3,000 × 88 B ⇒ ~66k, 66k + 27k ⇒ ~93k, 66k + 94k ⇒ ~160k, 1,706 × 93k ⇒ ~159M — all consistent. The dollar
figures also reconcile against `common/models.json` (`price_in` 0.14 / 0.75 / 1.5 per 1M): 160M ⇒ $22 / $120 /
$240 ≈ the stated $25 / $115 / $230. I had drafted an objection that the dollar figures were derived from the
today-scale token count and were ~9× low; checking the pricing showed they track the 160M vault figure. Withdrawn
before filing.

---

## 2. Findings

### J1 — policy v2 bounds the evidence block; the stage-2 *request* is still unbounded, and the unbounded part is the query (load-bearing for §9's test)

§7's bound is `150 × 2,500 B = 375 kB ≈ 94k tokens < 102.4k`, and §9 asserts it. But a stage-2 request is
evidence **plus** the system template, the query block, and an output allowance — and:

1. **There is no `OUTPUT_ALLOWANCE_FAT`.** §7 declares `OUTPUT_ALLOWANCE_THIN` (2,000, reserved via
   `ModelRequest.max_tokens = 2000`) and nothing for the fat call, whose response can carry up to
   `max_results = 50` entries with slugs and expression attributions.
2. **The query block is schema-unbounded on two of its five SD-1 fields.** Verified in
   `ingestion/enrich/pass1_schema.py:77-89`: `summary` is `{"type": "string"}` with **no `maxLength`**, and
   `key_themes` is an array of strings with **no `maxItems`** — only `entity_search_keys` is capped (10). The
   prompt asks for "1-3 sentences" (`pass1_prompt.j2:62`), which is discipline, not a constraint, and R1's
   coerce-don't-reject posture means an over-long summary is kept, not rejected.

So the evidence side is now a code property while the query side has exactly the unbounded-bytes property that
policy v2 was introduced to remove. The asymmetry is sharper than it looks: **stage 1 estimates the query block at
runtime** (§7's estimator covers "rendered thin block + system template + user wrapper + query block"), so query
bloat there is counted and can fire `budget_exceeded` honestly. **Stage 2 has no runtime estimate at all** — its
only guard is the static bound, and the static bound omits the query.

Arithmetically: against a 128k window's 102.4k budget, evidence alone is 91.6%, leaving ~8.6k for system + query +
output. That is probably sufficient (system ~0.5–1k, a well-behaved query ~0.3–0.8k, a 50-hit JSON response
~1.5–3k), but "probably sufficient" is the register policy v2 just retired.

**Fix (two clauses and one constant):** state the stage-2 accounting as
`150 × 2,500 B + system + query + OUTPUT_ALLOWANCE_FAT ≤ 0.8 × window`; declare `OUTPUT_ALLOWANCE_FAT` and reserve
it as `max_tokens` on the fat request exactly as thin does; and give the rendered query block a byte ceiling in the
projector (the same mechanism, applied to the block that is actually unbounded). Then §9's assertion covers the
request rather than one of its three parts.

**Not urgent operationally:** the configured pool is 400k/1M/1M ⇒ 320k/800k/800k budgets, so even a 10k-token query
block is inert. This is about the asserted bound and about the 128k-window claim, which §7 states twice.

### J2 — the fixture manifest still declares `excerpt_policy_version: "1"` (minor, breaks a §8.1 check)

§5 and §7 say policy v2 "binds on nothing in fixture v1 (largest rendered block 2,209 B) — no regeneration,
checksums unchanged." The **bytes** claim is correct (verified: 2,209 B < 2,500 B, and the two capped entries are
the manifest's own `capped` list). But `benchmark/truth/task123_search_snapshot_v1/manifest.json` carries
`"excerpt_policy_version": "1"`, and the projector will stamp `"2"` — while spec §8.1 lists **"policy versions"**
among what the fixture restoration smoke test verifies, and P4's harness loads the fixture checksum-verified.

So either the smoke test compares the manifest's `1` against the projector's `2` and fails, or it doesn't compare
them and the "policy versions" clause is decorative. Neither is what's intended.

**Fix:** bump the manifest field to `"2"` with a one-line note that v2 is byte-identical on this corpus (checksums
genuinely unchanged, so this is a metadata-only edit and the checksum file needs no regeneration) — or state
explicitly that the fixture remains policy-v1 evidence and the harness accepts `1 | 2` under a recorded
equivalence claim. The first is cleaner.

### J3 — D5's 3-call ceiling silently drops the adversarial calibration input (minor)

v0.3's calibration read the fixture thin block **"+ adversarial high-token-density case"**. D5's "exactly one
non-comparative call per candidate (hard 3-call ceiling)" leaves only the fixture block, so `bytes ÷ 4` is
calibrated at a single density point — and the guardrail exists for vault-scale thin blocks whose slug/title
density is unmeasured. Concatenating both into one prompt doesn't help: usage is reported per request, so the two
segments can't be decomposed.

**Fix:** either raise the ceiling to two calls per candidate (6 total — still trivial spend, still
non-comparative), or state explicitly that the 0.8 headroom is accepted as the sole margin for density variance.
The second is defensible; it just shouldn't be silent, since it was an explicit input one version ago.

### J4 — spec §7.2 wasn't synced with §7.1's refreshed figures (minor)

§7.1 (v0.6) now measures vault largest-domain thin at **~66k** and whole-graph at **~211k**. §7.2's paragraph
immediately below still reads *"pass-1.5's largest domain space thin-projects to ~40k–70k tokens and whole-graph
human queries to ~127k–222k (§7.1)"* — the pre-fixture estimates, cross-referencing the section that now says
something else. One sentence.

(The SD-5 row in the same section survives the refresh: at the measured 22 tokens/entity, an 800k budget admits
~36k entities and a 102.4k budget ~4.6k — inside the stated "~35k–60k" and "~4k–8k" ranges.)

### For the record, not a finding

§7.1's "~160M input tokens **upper bound**" is the expected-rate total (1,706 × ~93k). It is an upper bound in the
*domain-size* sense the parenthetical gives ("most domains are far smaller"), but the policy-ceiling worst case is
1,706 × ~160k ≈ **273M ≈ $38 / $205 / $410**. Worth having on the "any expense" record alongside the expected
figure, since both are now derivable.

---

## 3. Verified against the repo

- **`summary` unbounded, `key_themes` unbounded, `entity_search_keys` capped at 10** —
  `ingestion/enrich/pass1_schema.py:77-89`; prompt-level "1-3 sentences" at `pass1_prompt.j2:62` (J1).
- **Fixture manifest `excerpt_policy_version: "1"`**, `capped` = the two 251w/262w entries (J2).
- **Fixture max rendered fat block = 2,209 B < 2,500 B** — policy v2 binds on nothing in fixture v1, as claimed;
  checksums genuinely unchanged.
- **Pricing reconciles** — `common/models.json` `price_in` = 0.14 / 0.75 / 1.5 per 1M ⇒ 160M tokens ≈
  $22 / $120 / $240 ≈ the stated $25 / $115 / $230.
- **Spec enum now four-valued at both sites** — §1.1 and §5.1 (H2 closed).
- **`entity_first_run_ids` still needed** — `active_entities()` returns `{title, page_type}` only
  (`kdb_graph/queries.py:247-257`); `first_run_id` is an Entity property (`intake.py:316`).
- **Diagnostic series populations** — `retry_load` / `token_overrun_rate` / `repair_rung_rate` computed over the
  whole `calls` list (`compiler/kpi/processing.py:91-106`), as H4's new bullet states.
- **All v0.6 sizing arithmetic and the 39-probe / fixture / model-pool claims** re-checked and consistent.

## 4. Recommendation

**Ratify.** J1 is a §7 clause plus one declared constant — cheapest before P1 writes `test_budget.py`; J2 is a
one-field metadata edit needed before P4 loads the fixture; J3 and J4 are single sentences. Nothing here reopens
the architecture, contradicts D1–D5, or changes a phase boundary.
