# #123 Semantic Graph Search Spec v0.1 — opus5 review

Date: 2026-07-25 · Respondent: **opus5** · Reviewing: `2026-07-25-task123-semantic-graph-search-spec.md` (v0.1)
Prior records: `…-round1-panel-discussion-opus5.md` · `…-round1-synthesis-review-opus5.md` · `…-task123-vision-review-opus5.md`

## Verdict

**APPROVE SD-1, SD-2, SD-3, SD-5. APPROVE SD-4 with a corrected rationale (§C). APPROVE SD-6's *choice* but
NOT its current substrate (§B) — that one needs fixing before Joseph spends labeling effort on it.**

All five of my vision-review items landed correctly: A1 fallback (§3.4), A2 T2Mode disposition (§3.4), B1 frozen
artifact + `intra_run_order` (§5.1/5.3), B2 sizing gate (§7), C3 cross-domain A/B (§8.5). The three-mode naming
in §5.2 is cleaner than what I asked for.

**§A below corrects an error of mine that the spec inherited.** I supplied "~62 entities, ratio 1.7/source" in
my vision review; the measured corpus is 163 entities at 5.6/source. I also assumed 250-word excerpts cost
~333 tokens each; the measured mean is 97. Both constants in §7.1 are wrong, in opposite directions.

---

## A. Corrected sizing constants (replaces my B2 arithmetic — measure, don't infer)

Measured directly from the SD-6 snapshot's own wiki (`benchmark/runs/gemini-3.6-flash-2026-07-25T09-41-46_EDT/wiki/`):

| page type | count | median words | p90 | max | over 250w |
|---|---|---|---|---|---|
| concepts | 116 | 62 | 94 | 151 | 0 |
| articles | 18 | 135 | 271 | 299 | 2 |
| summaries | 29 | 57 | 91 | 93 | 0 |
| **all** | **163** | — | — | — | **2 (1.2%)** |

**Mean 73 words/entity when capped at 250 ⇒ ~97 tokens/entity.** Whole-graph fat payload today, all 163
entities: **15.9k tokens.**

Two corrections follow, and they cut in opposite directions:

- **Entity count: 163 from 29 compiled sources = 5.6 entities/source**, not 1.7. My "62 pages" came from the
  packet's §2 (and the underlying memory note), which reflects a much older corpus state. Vault projection
  moves from ~2,900 entities to **~9,600**.
- **Per-entity cost: ~97 tokens, not ~333.** Because 161 of 163 bodies are already under the bound.

### Corrected §7.1

| | entities | largest domain subtree | thin, whole graph | fat, largest subtree |
|---|---|---|---|---|
| today (29 sources compiled) | **163** | 46+ | ~0.8k tokens | **~4.5k tokens** |
| vault (~1,706 notes) | **~9,600** | **~2,700**¹ | **~48k tokens** | **~262k tokens — does not fit** |

¹ floor: value-investing's pool reached 46 of 163 mid-run (≥28% share); the end-of-run share is higher.

**The spec's headline conclusion survives** — the largest subtree at vault scale does not fit a 100k budget —
but it survives by coincidence, the two errors nearly cancelling (3.3× ÷ 3.4×). The decisions underneath it
change:

1. **SD-3's excerpt bound is inert today and is not the sizing lever.** 250 words binds exactly **2 of 163
   pages**. Cutting it to 100 would save essentially nothing (median body is 62 words). **Entity count is the
   only variable that matters**, which makes SD-4 the sole effective lever and means SD-3 can stay generous at
   no cost. Keep 250; just stop treating it as a knob.
2. **The two-stage threshold is crossed by *count*, not by *length*** — so SD-5's measured distribution should
   track space **entity count** as the primary series, with token estimate derived from the measured
   ~97 tokens/entity rather than from the excerpt bound.
3. **Good news on cost.** Per source at vault: stage-1 thin (~2,700 × 5 ≈ 13.5k) + stage-2 fat (150 × 97 ≈
   14.5k) ≈ **28k input tokens**. Across 1,706 sources ≈ **~48M input tokens** for a full ingest — tens of
   dollars at current flash-tier pricing, not hundreds. The "any expense" ruling is being made against a much
   smaller number than §7.1 implies. Worth stating explicitly so the ruling is on record with a figure.

---

## B. SD-6 — right snapshot, unsafe substrate (fix before labeling)

The choice of the 2026-07-25 gemini cold-run end state is correct: real corpus messiness, Buffett-rich, 116
concept pages (verified accurate). Three problems with it as a durable evaluation base:

1. **The substrate is untracked.** `benchmark/runs/` is git-ignored (`.gitignore:42`); `git ls-files
   benchmark/runs/` returns nothing. The only clean copy of the snapshot is one `git clean -xdf` or one disk
   loss from gone — and Joseph's relevance labeling, the most expensive artifact in the D7 program, is pinned
   to exactly this state.
2. **The stated re-materialization path does not exist.** §8.1 says "re-materializable via `graphdb-kdb
   rebuild` from the run journals." There is no `state/journals/` in the sandbox (`~/Obsidian/Vault-in-place-test-run/KDB/state/`
   holds `compile_result.json`, `last_orchestrate.json`, `manifest.json`, `pipelines.json`, `runs/` — no
   journals), and the run directory carries no `.jsonl` journals either. The rebuild path needs to be verified
   before it is relied on, or the claim dropped.
3. **The live state has already drifted past it.** The warm run (deepseek `09-48-25`) ran without a wipe, so the
   sandbox wiki is now 31 summaries / 117 concepts / 18 articles vs the snapshot's 29 / 116 / 18. The snapshot
   exists *only* as the copy in `benchmark/runs/`.

**Fix:** promote the snapshot to a tracked, checksummed fixture (or an explicitly archived export with a
manifest) *before* labeling begins. This is cheap now and unrecoverable later.

**Incidental hygiene finding:** the +2 summaries / +1 concept in the live sandbox came from the two warm-probe
sources Joseph deleted after the #122 analysis. Those wiki pages are now orphans whose sources no longer exist —
`kdb-clean orphans` territory, unrelated to #123, flagged so it isn't rediscovered as news.

---

## C. SD-4 — approve the design, correct the rationale

Two-stage all-LLM with no FTS in v1 is the right v1 call, and the codex F4 point (a cap on unmeasured recall is
unacceptable as a load-bearing filter) is sound. But the stated justification overclaims in a way that will
mislead whoever revisits this:

> "the two-stage path shows the LLM **every** title (no recall cap at all in stage 1)"

Stage 1 shows every title but returns only M=150. **That is a recall cap** — imposed by LLM judgment over
three-word titles rather than by BM25 score. So the real distinction is not "cap vs no cap"; it is **which cap
is measured**. And the vision's own Q3 reasoning (which I supplied) says three-word titles carry near-zero
signal for lexical *and* embedding methods alike — that argument applies to a thin-title LLM pre-selection too.
Stage 1 asks the selector to do, on thin text, the task the document elsewhere argues thin text cannot support.

With the corrected §A numbers this matters more: stage 1 picks 150 from **~9,600** titles, not 2,900.

**Fix:** restate the rationale as "both stage-1 candidates cap recall; the two-stage path is preferred because
its cap is measurable inside the existing truth-set harness, while FTS recall would require separate
instrumentation" — and **predeclare the measurement**: stage-1 recall@150 on the truth set, run **before** vault
ingestion rather than after. That converts SD-4's revisit trigger from a vague "if stage-1 underperforms" into
a gate with a date.

---

## D. Contract gaps worth closing in v0.2

1. **"Wholesale-invalid" is undefined (§2.3 ↔ §3.4).** Per-entry violations are discarded as honest partials;
   wholesale-invalid output triggers the fallback. The boundary is unspecified. If 9 of 10 selections are
   foreign slugs, is that a partial (keep 1) or a failure (fall back)? As written, a systematically
   hallucinating selector reports as a healthy partial. Needs a rule — a discard-ratio threshold, or "any
   foreign slug ⇒ failure" (defensible under D9's fail-closed posture).
2. **`identity_match_annotations` implies exact/alias runs on the happy path.** Computing `exact_matchable` /
   `alias_matchable` per hit requires the deterministic resolver on every request, not just on fallback. §3.4
   describes that resolver as "survival-scoped" to the fallback. Both are fine, but they should agree: the
   resolver is *always* invoked (for annotation) and *additionally* supplies results when the selector fails.
   This also makes A1's fallback cheaper than it sounds — the code path is live regardless.
3. **Probe classes E and D contradict each other (§8.2).** Class E lists `teledyne` as an abstention probe
   ("no relevant entity exists; correct answer is empty"), while class D includes "the guy who bought back
   Teledyne stock" as a query expecting a hit, and class A includes `henry-singleton`. Under the ratified
   relevance criterion — composites are legitimate returns — a Singleton/capital-allocation page *is* relevant
   to `teledyne`. Verify against the snapshot before labeling; as written, one of these two probes will be
   labeled wrong, and class E is exactly where a wrong label teaches the selector to abstain when it shouldn't.
4. **Class A labeling is the operative definition of success.** If the snapshot lacks standalone person
   entities (#122 finding 4), person-class recall depends entirely on which composites Joseph marks relevant.
   That labeling *is* the project's success criterion, more than any threshold in §8.4. Worth flagging in §8.2
   so it gets proportionate attention.

---

## E. Votes on SD-1..SD-6

| | vote | note |
|---|---|---|
| **SD-1** field list | **approve** | domain/summary/key_themes/entity_search_keys; exclusions correct. |
| **SD-2** candidates/delivered | **approve** | preserves #122 field meaning; no metric break. |
| **SD-3** 250-word bound | **approve** | but see §A1 — inert today (binds 2/163), a safety bound not a lever. Keep it generous. |
| **SD-4** two-stage, no FTS v1 | **approve w/ §C** | design right, rationale overclaims, predeclare stage-1 recall@150. |
| **SD-5** measured threshold | **approve** | track entity **count** as primary series; seed from corrected §A constants. |
| **SD-6** snapshot choice | **approve, substrate blocked** | fix §B durability before labeling starts. |

---

## F. Affirmations

- **§5.2's three named modes** (live search / record replay / historical selector re-call, the last validated
  against the *archived* manifest and never presented as current) is a better resolution than the escape hatch
  I asked for — it closes the "re-call silently becomes a live answer" failure I hadn't named.
- **§3.3's zero-spend abstention** on empty space, with typed reasons, is exactly right: it makes
  correct-by-design abstention free rather than merely unpenalized.
- **§6.2's two denominators**, kept explicitly non-substitutable, is the cleanest expression of the D3
  reconciliation anywhere in the round.
- **§2.1's P10 mechanics** — data-only evidence encoding, explicit instruction precedence, adversarial class-H
  fixtures as must-pass — treat prompt-injection as a contract property rather than a hope.
- **§8.4 fixing gate *shapes* now and *values* after labeling** is the #75 pattern applied correctly, and is
  what keeps the "objective cannot fail" risk from §Q5 of round 1 contained.

Nothing here blocks the blueprint once §B's substrate is secured and §A's constants are folded into §7.
