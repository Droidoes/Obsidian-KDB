# #123 Semantic Graph Search — Spec v0.1 Review Synthesis

**Date:** 2026-07-25
**Synthesizer:** Kimi
**Inputs:** [`…-spec-review-codex.md`](2026-07-25-task123-semantic-graph-search-spec-review-codex.md) (REVISE) · [`…-spec-review-opus5.md`](2026-07-25-task123-spec-review-opus5.md) (APPROVE SD-1/2/3/5, SD-4 w/ corrected rationale, SD-6 substrate blocked)
**Artifact under review:** [`…-semantic-graph-search-spec.md`](2026-07-25-task123-semantic-graph-search-spec.md) v0.1

## 0. Verification record (Kimi, before absorbing anything)

| Panel claim | Check | Result |
|---|---|---|
| `benchmark/runs/` untracked → snapshot not durable (codex F2, opus5 §B) | `.gitignore:42`, `git ls-files benchmark/runs/` | **Confirmed** — zero tracked files |
| Snapshot = 163 entities, not ~62 (codex F1, opus5 §A) | page count of `benchmark/runs/gemini-3.6-flash-2026-07-25T09-41-46_EDT/wiki/` | **Confirmed** — 116 concepts + 18 articles + 29 summaries = 163 |
| `teledyne` has a relevant entity; invalid abstention probe (codex F3, opus5 §D.3) | `grep -ci teledyne wiki/concepts/henry-singleton.md` | **Confirmed** — 3 mentions |
| Rebuild path does not exist for this snapshot (codex F2, opus5 §B) | `ls ~/Obsidian/Vault-in-place-test-run/KDB/state/runs/` | **Confirmed** — no `<run_id>.json` journals, no `compile_result.json`/`last_scan.json` sidecars; adapter (`kdb_graph/adapters/obsidian_runs.py:5-7`) requires all three |
| 250-word excerpt bound is inert (opus5 §A) | `wc -w` over all 163 pages | **Confirmed** — exactly 2/163 pages >250 words; median 107w whole-file (opus5's 62–73w body-only figures consistent) |

## 1. Convergences (2/2 — load-bearing, absorb)

### C1 — Sizing constants are wrong; headline conclusion survives (codex F1 ≡ opus5 §A)
- v0.1 §7.1 inherited "~62 entities, 1.7/source" (opus5's own earlier figure — he owns the error) and assumed ~333 tokens/entity.
- Measured: **163 entities / 29 compiled sources = 5.6 per source**; ~97–150 tokens/entity (250w bound binds only 2/163 pages).
- Vault projection: ~1,706 notes × 5.6 ≈ **~9,600 entities**; largest domain subtree **~2,700**; fat largest-subtree ≈ **~262k tokens — still does not fit**. The "single fat call breaks at vault scale" conclusion stands.
- Fold into v0.2: corrected §7.1 table with explicit denominators; SD-3 reframed as an inert safety bound (kept at 250, never a sizing lever); SD-5 threshold keyed on **space entity count** as primary series with serialized-token estimate at the measured per-entity cost + prompt/output margins.
- opus5's cost note for the record: stage-1 thin (~2,700 × 5 tok) + stage-2 fat (150 × 97) ≈ **28k input tokens/source at vault scale ⇒ ~48M for a full 1,706-source ingest — tens of dollars**, not hundreds. Joseph's "any expense" ruling should be on record against this figure.

### C2 — SD-6 snapshot substrate is not durable; rebuild claim is false (codex F2 ≡ opus5 §B)
- Gitignored + no journals + live sandbox already drifted past it (warm run added pages) ⇒ the only clean copy is one `git clean` away from loss, and Joseph's labeling effort pins to exactly this state.
- Fold into v0.2: **promote the snapshot to a tracked, checksummed fixture** (identity manifest + exact projected excerpt bytes + checksums + manifest) **before any labeling begins**; automated restoration smoke test (materialize → verify identity count, excerpt hash, representative entities); §8.1 drops the `graphdb-kdb rebuild` claim and names the fixture as the storage/retention authority.

### C3 — `teledyne` is not an abstention probe (codex F3 ≡ opus5 §D.3)
- `henry-singleton` discusses Teledyne (verified ×3); under the ratified relevance criterion a Singleton composite **is** a relevant return, so "correctly empty" would punish the capability for succeeding.
- Fold into v0.2: move `teledyne` to the person/semantic class with an adjudicated relevant set; every class-E (abstention) probe must be **verified against the frozen evidence bytes** before labeling.

### C4 — Fail-closed semantics were internally contradictory (codex F6 ≡ opus5 §D.1)
- v0.1 called foreign slugs a typed contract failure yet §2.3/§3.4 discarded invalid entries and kept the rest as "honest partial" — a systematically hallucinating selector would report as healthy.
- Fold into v0.2: **any contract violation invalidates the whole selector response and activates the deterministic fallback** — foreign slug, unknown expression, duplicate slug, over-cap result, invalid JSON, inconsistent matched/unresolved accounting. "Honest partial" = a fully valid response that returned fewer hits or explicitly left expressions unresolved. Controller additionally validates: unresolved expressions are valid, deduplicated, disjoint from matched, and every request expression is accounted for.

## 2. The one divergence: SD-4 scale path (codex F4 vs opus5 §C)

| | codex | opus5 |
|---|---|---|
| Vote | **DISAPPROVE as written** — two LLM relevance calls change ratified vision P1 ("one batched call on the happy path"); needs explicit option comparison + vision re-ratification | **APPROVE the design, fix the rationale** — "stage 1 has no recall cap" overclaims: M=150 **is** a cap, imposed by LLM judgment over thin titles instead of BM25 |
| Shared premise | A cap on **unmeasured** recall is unacceptable as a load-bearing filter | Same — and FTS recall over thin slug/title text would need separate instrumentation to measure |

The two positions reconcile: both reviewers accept the two-stage design **iff** (a) it wins an explicit comparison and (b) its stage-1 cap is predeclared and measured. v0.2 will carry the three-option comparison and Joseph ratifies the pick (with a vision P1 amendment if a two-call path wins):

1. **FTS/exact candidate generation → one fat LLM selector.** Matches vision P1's single LLM call; lowest recurring cost. But candidate generation runs over thin slug/title text — vision Q3 already judged thin text near-zero-signal for lexical/embedding methods — and FTS recall would need separate instrumentation before its cap is load-bearing. FTS-over-bodies = RAG-on-graph, rejected in round 1.
2. **All-title LLM pre-selection → fat LLM selection (v0.1's recommendation).** Both calls do relevance; the stage-1 cap (M=150) is **measurable inside the existing truth-set harness** (predeclared stage-1 recall@150, run before vault ingestion — this becomes the dated revisit trigger, replacing "if stage-1 underperforms"). Costs 2 calls/source at scale (~28k input tokens — see C1).
3. **Sharded fat LLM → deterministic/LLM merge.** Every body excerpt semantically evaluated; no thin-text stage. Highest cost (~3× calls/source), hardest ordering/merge/replay semantics. Held as the fallback if option 2's stage-1 gate fails.

**Kimi recommendation: option 2**, with opus5's corrected rationale ("which cap is measured", not "cap vs no cap") and codex's demanded comparison on record. Note the amendment is narrower than it reads: P1's single batched call remains literally true for every space under the measured threshold — which includes today's entire 163-entity graph (whole-graph fat ≈ 16k tokens). Two-stage only activates at scale.

## 3. Unique catches (1/2 — verified, absorb)

- **codex F5 — stage-aware artifacts.** `SearchArtifactV1` must represent two stages: `graph_ref` + eligible-space manifest; per-stage evidence bytes, prompt bytes (archived, not just hashed — a hash preserves nothing), output, validation, model route, latency, cost; retained identities; final result + fallback state. `complete | partial` applies to the evidence pool **presented to the fat selector**; eligible-space and stage-1 coverage reported as separate counts.
- **codex F7 — metric separation.** Report separately: scope coverage; stage-1 candidate recall@M (if a candidate stage exists); final selector P@5 / R@5 / MRR; **attempted** contract-violation rate from raw output (post-validation foreign-slug rate is zero by construction and measures nothing); **escaped** foreign-identity rate (hard gate 0); semantic abstention accuracy on non-empty spaces; domain-empty/domain-missing as availability, not relevance quality.
- **codex F8 — truth set as a checked-in artifact before tuning.** Per probe: stable ID + class, exact `QueryPayload`, frozen eligible-space reference, relevant slug set, acceptable alternatives + notes, explicit abstention reason, exact/alias-matchable annotation, adjudicator + version. Joseph ratifies labels **and** numerical gates before any experiment runs. (This is D7 made concrete.)
- **opus5 §D.2 — resolver runs on the happy path.** `identity_match_annotations` requires exact/alias resolution per hit on every request, not just in fallback. v0.2 states: the deterministic resolver is always invoked (annotation) and **additionally** supplies results when the selector fails — which also makes the A1 fallback cheaper: the code path is live regardless.
- **opus5 §D.4 — class-A labeling is the operative success definition.** Person-class recall depends entirely on which composites Joseph marks relevant. §8.2 must say so explicitly so labeling gets proportionate attention.

## 4. SD vote tally

| SD | codex | opus5 | Disposition for v0.2 |
|---|---|---|---|
| **SD-1** fields | approve w/ revision — do not drop `author` without evidence; authorship is a person signal for the motivating class | approve as written | **Joseph rules.** Kimi recommendation: include `author` (5 fields) — trivial cost, directly on-class for `warren-buffett`; truth set can A/B its exclusion later |
| **SD-2** T2 candidates/delivered | approve | approve | **Ratified** — selector-valid hits pre/post merged cap; candidate-stage pool (if SD-4 adopts one) recorded separately, never overloaded into T2 |
| **SD-3** 250-word bound | hold — conditional on corrected arithmetic | approve — inert safety bound, keep generous | **Ratified as safety bound** — arithmetic now corrected (C1); 250 stays, explicitly not a sizing lever |
| **SD-4** scale path | disapprove as written → explicit comparison + vision re-ratification | approve design w/ corrected rationale + predeclared stage-1 recall@150 | **Joseph rules option 1/2/3** (§2); vision P1 amendment follows the pick |
| **SD-5** measured threshold | hold — define in serialized input tokens w/ margins | approve — entity count as primary series | **Ratified as principle** — threshold = f(space entity count, measured tokens/entity, prompt/output margins); value set after measurement |
| **SD-6** snapshot | approve choice, packaging fix required | approve choice, substrate blocked | **Ratified choice + blocked labeling** until C2's tracked fixture + restoration smoke test land |

## 5. v0.2 disposition list

1. §7.1 corrected constants + denominators (C1); cost figure on record.
2. §8.1 snapshot → tracked checksummed fixture + restoration smoke test; rebuild claim removed (C2).
3. §8.2 probe classes: `teledyne` moved; abstention probes verified against frozen bytes; class-A labeling flagged as the operative success definition (C3, opus5 §D.4).
4. §2.3/§3.4 strict fail-closed: any contract violation ⇒ whole-response invalid ⇒ fallback; "honest partial" redefined (C4).
5. §2/§5 stage-aware artifacts: graph_ref, per-stage evidence/prompt bytes/output/model/cost/hashes; `complete|partial` scoped to the fat-selector evidence pool (codex F5).
6. §6 metrics separated per codex F7, incl. attempted-vs-escaped violation rates.
7. §8 truth-set artifact schema + Joseph-ratifies-labels-and-gates gate (codex F8).
8. Resolver-always-on for annotation (opus5 §D.2).
9. SD-4 three-option comparison with recorded decision + vision P1 amendment (§2 above).
10. SD-1 field list per Joseph's ruling.

## 6. Incidental (not #123 scope)

opus5 §B flags: the live sandbox wiki drifted +2 summaries/+1 concept from the two warm-probe sources deleted after the #122 analysis — those pages are now source-less orphans (`kdb-clean orphans` territory). Noted for the next sandbox touch; no action in this task.

## 7. Next gates

1. **Joseph rules:** SD-4 option (1/2/3) · SD-1 (author in/out) · confirm the §5 disposition list.
2. Kimi folds into **spec v0.2** (+ vision v1.3 P1 amendment if SD-4 picks a two-call path).
3. v0.2 returns to codex (re-review explicitly requested — 7 conditions listed in his gate) and opus5 for concurrence.
4. Ratification → commit (spec v0.1's commit gate stays open until then; the panel reviews + this synthesis commit with v0.2).
