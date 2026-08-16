# Session handoff — 2026-08-02

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime.

## ⏩ END OF SESSION — #123 P2 closed out; the road to a Pass-1 → Pass-1.5 → Pass-2 end-to-end run is now the whole remaining question

Nine commits, all pushed to `origin/feat/123-semantic-graph-search`. Suite **3,037 passed, 32 skipped**,
working tree clean. **No PR opened.**

The theme of the session, in Joseph's words: *"the chief objective is to simplify, simplify and
simplify — by removing complexity, we are making our architecture/design/code stronger"* and
*"simplicity is power"*. Four mechanisms were **deleted** rather than fixed, each on measured
evidence rather than argument.

```
3b086eb  docs   D5 calibration gate + the v0.16 review record
9a8d497  feat   v0.16 D-123-A..E — truncation machinery deleted, fill to budget
126ec78  feat   v0.16 D-123-F + selector_fat _v3 — advisory `unresolved` off the wire
0bcb6f5  feat   record the real bytes-per-token from every live call
634d25a  feat   #126 — entity_search_keys re-specified as the search's query terms
2779f1c  refac  D-123-G — remove small_space; thin fails, no fat
d853c65  feat   D5 gate DISCHARGED — all candidates measured
56d2bb0  feat   split alibaba by region; qwen3.7-flash as a fourth D5 family
751a7d7  feat   D-123-H — deliver the audit payload on the result
```

---

## 1. THE GOAL — what "end-to-end" actually means

One source document, all the way through:

| pass | what it does | state |
|---|---|---|
| **Pass-1** — `ingestion/enrich/` | reads a raw source, emits frontmatter: `domain`, `summary`, `key_themes`, `entity_search_keys`, `author` | **works.** Prompt just moved to **1.3.0** (#126) and has **not** been fired live under the new contract |
| **Pass-1.5** — `kdb_search/` | given that frontmatter, picks which existing wiki pages are relevant, using two LLM calls (thin → fat) | **the machine exists and is tested to 3,037 tests. NOTHING CALLS IT.** |
| **Pass-2** — `compiler/` | writes/updates wiki pages, using context pages supplied to it | **works**, fed today by `compiler/context_loader.py` |

**The gap is the wiring, not the machinery.** `graph_search` has no caller anywhere outside its own
tests — verified by grep. Pass-2 is fed instead by `context_loader.build_context_snapshot()`, whose
**T2 tier** does a *deterministic PK/regex lookup* on `entity_search_keys`. #123 exists to replace
that T2 seeding with semantic selection. **P3a is that wiring.**

Read `compiler/context_loader.py`'s module docstring before touching this: it defines the T1/T2/T3
tiering, the cold-start widening, and the ranking tie-break that P3a has to slot into without
disturbing T1 or T3.

---

## 2. #7 — BLUEPRINT P3a (unblocked as of this session)

**This is a Phase-2 Blueprint exercise, not a coding task.** Logic flows, data schemas, integration
boundaries, phased plan, TDD test plan; panel review before ratification, per project default.

Scope, per blueprint §11:

- the **pass-1.5 adapter** (+ §3.1 plumbing) — the piece that turns pass-1 frontmatter into a
  `GraphSearchRequest` and hands the result to the context build
- `t2_selection` / `search_summary`
- **ContextRecordV2** + the dispatching loader (`emit_kpis`)
- the **envelope sink** (the running log — see the ruling below)
- **KPI readers V1+V2**
- the **measurement contract** (§11)
- `query_kind: state_c`

### Two rulings the blueprint must carry — both already made, do not re-open

**(a) The audit log (D-123-H, this session).** `GraphSearchResult.audit` now reaches the caller
whole. The adapter writes the running log: **a one-line summary per document, full bytes retained
only on failure.** Each receipt is ~80 kB, so full retention costs **~125 MB per 1,586-note vault
ingest**, and a successful search's evidence is reconstructable from the graph plus the snapshot
hash. Failures are what the log gets opened for.

**(b) The live bytes-per-token series (#10, this session).** The envelope sink **must** persist
`StageRecord.provider_input_tokens`, and a KPI reader **must** aggregate `measured_bytes_per_token`
**per stage and per model — never blended.** Thin sends slug-heavy identity lines; fat sends whole
prose bodies; they tokenize at genuinely different densities and one figure hides the spread the
series exists to show. **Without this, every live run measures the real ratio and throws it away,**
and Joseph's Fork C ruling stays notional rather than operative.

Baseline for that series — D5, **four independent tokenizer families**, 3.2% spread:

| model | B/token | under-estimate |
|---|---:|---:|
| gemini-3.6-flash | 3.7127 | 1.077× |
| deepseek-v4-flash | 3.7632 | 1.063× |
| qwen3.7-flash | 3.7911 | 1.055× |
| gpt-5.4-mini | 3.8308 | 1.044× |

Failure threshold **3.20**; headroom 1.25×. `ESTIMATOR_BYTES_PER_TOKEN = 4` stands, **no longer
provisional**.

---

## 3. #8 — THE STRATEGIC FORK (answer this first)

**Finish #123 through P3a, or stop and ingest the 1,586-note vault?**

The 2026-07-07 pivot put the binding constraint at **corpus scale** and named vault ingestion as the
next move. #123 is now a large, carefully built machine that has still only ever run against **163
entities**.

**This session is itself evidence for the pivot.** Three safety mechanisms were deleted because
measurement showed they never fire at this corpus size (byte ceiling 0/163 fixture and 0/83 live;
word cap 2/163, 0/83; `truncated` read nowhere). A fourth — the query-block ceiling — was measured
at **0/39** and left standing *only* because n=39 is too thin to conclude on. **The vault answers
that one for free with 1,586 real pass-1 records.**

Against that: P3a is what makes any of #123 observable at all. Until the adapter exists, no live run
happens, no bytes-per-token series accumulates, and the audit log has no writer.

Measured input to the decision — domain sizes today, scaled 9.7× by the vault:

| domain | now | projected | vs M=150 |
|---|---:|---:|---|
| value-investing | 51 | ~495 | large |
| software | 35 | ~340 | large |
| ai-ml | 27 | ~262 | large |
| health-wellbeing | 22 | ~213 | large |
| geopolitics / quotes | 6 | ~58 | small |
| math / psychology | 5 | ~48 | small |
| history / personal-finance | 3 | ~29 | small |

≈83% of searches become large-space; 6 of 10 domains stay small.

---

## 4. WHAT ELSE STANDS BETWEEN HERE AND AN END-TO-END RUN

Ordered. Items 1–2 are decisions; 3–5 are work.

1. **#8 — the strategic fork above.** Everything below assumes "continue #123".
2. **Does semantic search REPLACE T2 seeding, or supplement it?** Not yet decided and P3a can't be
   blueprinted without it. `context_loader`'s T2 has three modes today (`STRUCTURED` /
   `LAYERED` / `LEGACY`) and cold-start widening. Whether `graph_search` becomes a fourth mode, or
   replaces `STRUCTURED`, or sits above the tiering entirely, changes the adapter's shape.
3. **#7 — blueprint P3a**, then build it.
4. **Re-fire Pass-1 under prompt 1.3.0.** #126 changed what `entity_search_keys` contains, and no
   live pass-1 has run since. Until it does, the only pass-1 output in the repo is the 39 probes'
   `query_payload`, captured under 1.2.0. **Joseph accepted that fixture drift** — the probes keep
   their old queries — but production output will differ, and nobody has seen it yet.
5. **A live smoke over a handful of sources** before anything vault-scale. Prior qwen and
   gemini cohort runs quarantined sources at rates that only showed up live.

### Watch-fors for the first live run

- **Zero-key sources are now possible** (#126). A source engaging nothing beyond its `key_themes`
  may emit an empty `entity_search_keys`. Verified valid end-to-end — no `minItems`, accounting
  returns empty tuples, the query block omits the field line — **but §8.3 metric 6 reads *unresolved
  expressions*, so a zero-key source makes that metric degenerate.** Future-probe concern; the
  frozen 39 keep their expressions.
- **`thin fails ⇒ no fat` (D-123-G).** There is no longer any fallback. Two bad thin responses end
  the search. At today's scale *every* space is small, so this path used to be masked by the F1
  route and no longer is. Expect it to become visible.
- **DashScope content-filter false positives** (`data_inspection_failed`) — flagged twice as the
  durable provider-level risk for vault-scale ingest, on the Li Lu lecture both times.

---

## 5. OPEN ITEMS OUTSIDE THE E2E PATH

- **Query-block ceiling** — measured 0/39, max 26% of the 4,096 B ceiling. Kept, deliberately, only
  because n=39 is thin. Re-measure after ingestion and decide on evidence, exactly as the body
  ceiling was decided. *Correction on record:* the original justification ("pass-1 metadata is
  genuinely unbounded, unlike compiled bodies") **does not hold** — both are model-authored under a
  KDB-written prompt. The honest reason to keep it is sample size.
- **`gpt-5.6-luna`** — registered, fired, removed. Exhausted the entire 36,000-token thin envelope
  without finishing (a 400). Recorded under *"Rejected routes — measured, not assumed"* in
  `docs/reference/model-provider-api-calls.md`. **Re-adding requires first confirming what reasoning
  control it actually accepts** — `reasoning_effort` was *mirrored* from `gpt-5.4-mini`, not
  verified, so the failure may say nothing about the model.
- **`qwen3.7-flash`** — newly registered (`alibaba-sgp`, $0.03/$0.13 per M, cheapest viable route in
  the pool). Route-admissible and D5-measured. **Not a selector verdict:** four qwen generations
  were dropped on link/graph quality. Its compile-seat failure mode (fabricated slugs) is
  *structurally impossible* in the closed-world selector, which is why a fresh trial is defensible —
  but that is P5a's question.
- **`worst_case_input_tokens`** — now used only by its own tests. Kept as the executable form of the
  `tokens_lte_bytes` premise, which still proves the output allowances. Flagged because two other
  "computed, read nowhere" fields were deleted this session on exactly that test.
- **`types.py:99` `evidence_excerpt`** — pre-existing orphan, referenced nowhere. Flagged, not
  deleted (not ours to clean).
- **Promoting `qwen3.7-flash` into `D4_COHORT`** (or retiring `gpt-5.4-mini` from it) is a **D4
  amendment** — owner call, deliberately not slipped in.

---

## 6. DECISIONS RATIFIED THIS SESSION

`D-123-A…E` (v0.16) · `D-123-F` · `D-123-G` · `D-123-H`, plus the Fork C ruling and #126.

- **A** — `M` 100 → **150**, narrowed to thin's retention ceiling.
- **B** — stage-2 pool is **dynamic, 1–150**, filled by thin's rank to the 0.8 budget, presented in
  manifest order. **Rank decides membership; §3.4 governs presentation** — the distinction that was
  misread twice before checking `search.py`.
- **C** — **no body truncation anywhere.** Bodies reach fat whole.
- **D** — D7's static guarantee **withdrawn**; replaced by *a request that does not fit is never
  constructed*.
- **E** — fat prose `_v3` (owner-read and approved).
- **F** — the advisory `unresolved` list **off the wire**. It fed `selector_accounting_delta`, which
  was computed and **read nowhere**. It should have gone out with `evidence` on D8(ii)'s own
  consumer test.
- **G** — **`small_space` removed entirely.** Retain-all and the F1 path both go, with three
  `FAT_*_ON_F1` terminals, the `thin_failed_nonbinding` watched class and the
  `fat_after_thin_failure` execution value. The contract matrix now **adds nothing** beyond §8's
  branch table. *Trade accepted:* an entity thin omits by judgment in a space that would have fit is
  lost.
- **H** — the audit payload is **delivered on the result** (8th field). `search_artifact_write_
  failures` deleted with the sink design it belonged to.
- **Fork C** — empty-slot calibration **satisfies D5**; no re-fire. The #126 prerequisite is retained
  for **P5a**, where key *content* is load-bearing, and was over-applied to D5, where only byte
  density matters.

Two consequences the amendment did **not** anticipate, recorded rather than absorbed:

1. `VISIBLE_OUTPUT_ALLOWANCE_THIN` **13,000 → 20,000**. Thin's wire is `M × MAX_SLUG_LEN` bounded, so
   M=150 carries its exact max 12,314 → 18,464 B, straight through the old allowance. "No longer an
   input to any guarantee" is true of the *input* budget and false of the *output* wire.
2. `FAT_PREFLIGHT_BUDGET` **changed shape** — now unreachable by window size, because thin's 36,000
   reserve exceeds fat's 26,000. Only a single oversized body reaches it.

---

## 7. VERIFICATION STATE

- Suite **3,037 passed, 32 skipped, 1 deselected**. Every commit verified green individually, not
  only at the tip.
- Working tree clean; branch pushed; **no PR**.
- The D5 artifact is `benchmark/truth/task123_search_calibration_v1.json`, four rows.
  `write_artifact` now **merges** behind a full-fingerprint guard — it earned that on its first real
  firing, preserving two paid rows through a run in which every call 429'd.
- Panel: codex and kimi both returned **CONCUR** on v0.16. kimi reproduced the figures independently
  and caught a live staging trap (`git mv` had staged two contentless renames while the assistant
  was asserting nothing was staged).
