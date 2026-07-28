# Task #125 — The Pass-1 / Pass-1.5 boundary: does the metadata stage earn its keep?

Date: 2026-07-26 · Task: **#125 (OPEN QUESTION)** · Status: **problem statement only — no options, no recommendation**

Raised by Joseph, 2026-07-26, mid-#123 P2 planning: *"why go through the trouble of Pass-1, if
the only purpose of Pass-1 is to produce metadata, in order to produce T1/T2/T3 using Pass-1.5 for
Pass-2 — why not just use Pass-1 with the source doc to produce T1/T2/T3?"*

His own framing of the timing: **"this is a question we should have asked earlier before Pass-1.5,
but better late than never."** §1 explains why it only became askable now.

This document is written to be self-contained, so it can serve as an external-panel brief without
further context. Every factual claim carries a `file:line`.

> **Amended 2026-07-26, after the response round.** As first written this document deliberately
> contained **no preferred option**, per the Phase-1 rule that framing must not pre-commit. It has
> since been corrected in place for verified factual errors (§6, §6.1) and has absorbed two verified
> **structural blockers** to the merged alternative (§5 costs 4–5). Those costs therefore now carry
> **verdicts** rather than being unargued, and §5 is no longer option-neutral: the merge is closed. The
> live question is narrower and stated in §6 — projection vs body *representation*, not the boundary.
> Read alongside `2026-07-26-task125-two-pass-boundary-synthesis.md`, which is the disposition.

---

## 1. Why the question only became askable now

`entity_search_keys` was introduced by **D-89-20** with a single documented purpose:

> `ingestion/enrich/pass1_schema.py:34-35`
> `# NB v0.2.2 (D-89-20): key_entities dropped; entity_search_keys added`
> `# (≤10 slugs; sole consumer = Task #90 context-loader T2-rewrite).`

So the field has exactly **one stated consumer**: the Task #90 T2-rewrite in
`compiler/context_loader.py:505-537`, which does exact-match PK lookup of those slugs to seed the
T2 context tier.

**#123 retires that consumer.** The Pass-1.5 adapter replaces `_t2_from_search_keys`' exact-match
seeds with selector hits (spec §1.2 / §5.1). At the same time, #123 repurposes `entity_search_keys`
as the *query expressions* handed to the selector — a different job with different quality
requirements — without anyone re-deriving whether the field, or the separate call that produces it,
should still exist in that form.

That is the answer to "why didn't we ask earlier": while the field fed a deterministic PK lookup,
imperfect keys were harmless (see §3, the `see's-candies` note). The moment they became an LLM's
query input, their quality became load-bearing, and the case for producing them in a separate
metadata-only call became a live question rather than a settled one.

---

## 2. What Pass-1 actually produces, and who consumes it

Pass-1 emits an 11-field LLM-owned envelope (`pass1_schema.py:63-64`) plus 4 code-stamped fields.
Consumers, verified:

| Pass-1 output | Consumer | Evidence |
|---|---|---|
| `kdb_signal` (signal/noise) | ingestion admission gate — decides whether the source is compiled at all | `pass1_schema.py:36`, `overrides.py` |
| `domain` (1 of 23 NW-4 IDs) | **#123 search scope** — defines the domain subtree that *is* the eligible space | `pass1_schema.py:37` for the field; the *consumer* is **spec §5.1 / §1.2, not yet code** — `kdb_search/types.py:83` only proves `ScopeKind="domain_subtree"` exists, and the adapter that fills it is P3a work |
| `summary` | (a) persisted as the GraphDB **`Source.summary`** property; (b) one field in Pass-2's **PASS-1 SOURCE METADATA** block, labelled trusted — *"do NOT re-derive … no need to rewrite or merge"*. **Not** Pass-2's principal input: Pass-2 also receives the **entire source body** and the **T1/T2/T3 snapshot** (`prompt_builder.py:190-207`). An earlier row here said "Pass-2, authoritatively" — corrected 2026-07-26 (Joseph) | `compiler/compiler.py:129-141`, `:273-275`; `compiler/prompt_builder.py:132-145`, `:190-207` |
| `key_themes` | (a) appended into `Source.summary`; (b) rendered into the #123 query block. **Not** threaded to Pass-2 separately (D-89-20) | `compiler/compiler.py:273-275`; `compiler/prompt_builder.py:154-156` |
| `entity_search_keys` | (a) T2-rewrite PK lookup — **being retired by #123**; (b) #123 query expressions; (c) a KPI (final-graph realization rate) | `context_loader.py:82-92`, `:505-537`, `:573`; `compiler/kpi/graph.py:219`, `:284`; `orchestrator/emit_kpis.py:59`, `:80` |
| `author` | #123 query block only (retained on codex's SD-1 revision as a person-signal) | spec §2.x |
| `source_type`, `confidence`, `uncertainty_reason`, `reject_reason`, `other_reason` | audit section — **Pass-2 ignores** (D-89-16) | `pass1_schema.py:44-58` |

All of it is serialized to YAML frontmatter and atomically written onto the source file
(`frontmatter_embedder.py`, per `pass1_schema.py:4-8`).

### 2.1 Correction of record — Pass-1 does *not* make a source findable

An earlier verbal claim in this discussion — that Pass-1's output is "committed to the graph as the
source's own enrichment," making it findable by every later source's search — is **false**, and the
question changes shape without it.

- `compile_source` is **produce-don't-write** (Task #91): "apply-pages, provenance, manifest commit,
  and graph-sync [happen] at the commit boundary" — `compiler/compiler.py:688`.
- Graph intake is `apply_compile_result` — it takes the **compile result**, i.e. Pass-2 output, and
  derives edges from produced page bodies — `kdb_graph/intake.py:1-7`, `:25-45`.

So a source becomes a graph citizen only after **Pass-2** compiles it and the result is synced.
Pass-1's contribution to the graph is *indirect*, via `Source.summary` and via Pass-2's pages.
There is no "write side" served by Pass-1 that would independently justify the separate call.

---

## 3. Pass-1 already reads the full source; Pass-1.5 reads a lossy projection of it

Pass-1's prompt receives the entire source body:

> `ingestion/enrich/pass1_prompt.j2:141` — `{{ source_text }}`

Pass-1.5's selector never sees the source. It sees a rendered query block bounded to **4,096 UTF-8
bytes**, built from five Pass-1 fields (`domain`, `summary`, `key_themes`, `entity_search_keys`,
`author`) under deterministic per-field byte allocations (spec §2.x / D6, codex L2).

Stated plainly: **the document is read in full by one LLM call, discarded, and a second LLM call is
then asked to judge that document's relevance to 51–163 candidates using a ≤4 kB summary of it.**
Whether that is a sound division of labour or an artifact of how the passes grew is the question.

Relevant history on key quality — the shape-only validation was a deliberate retreat:

> `pass1_schema.py:79-84` — "Shape validation only (string array, ≤10); content-format quality is a
> prompt-discipline concern. Downstream T2-rewrite (Task #90) does `Entity.slug` PK lookup —
> imperfect slugs simply miss, no harm. A strict regex caused real LLM emissions like
> `see's-candies` to reject the whole envelope (2026-05-26 night live fire)."

"Imperfect slugs simply miss, no harm" was true of a PK lookup. It is **not** true of selector query
expressions, which are what the LLM is asked to match against and what abstention is scored on.

---

## 4. The question, restated so it is answerable

Joseph's phrasing asks why Pass-1 doesn't "produce T1/T2/T3." That is not answerable as posed, and
the narrowing should be explicit rather than silently applied:

- **T1** (SUPPORTS edges) and **T3** (structural BFS) are **deterministic graph traversals**, not LLM
  outputs. No prompt can produce them from a source body; they are computed from graph state
  (spec §5.1 — "T1 (SUPPORTS) and T3 (structural BFS) are untouched").
- **T2** is the only tier that comes from search, and therefore the only tier in scope.

**Q1 (answerable form):** should T2 selection happen in a *second* LLM call over a ≤4 kB metadata
projection, or in the *same* call that already has the full source body in front of it?

**Q2:** if the two-call split stands, the Pass-1 prompt's `entity_search_keys` instructions
(`pass1_prompt.j2:68-80`) need review, because Pass-1.5's quality is entirely downstream of them.

**Q2b** (folded in from the Call-2 decision, 2026-07-26): the same prompt review covers `author`.
Root cause of the sentinel defect is prose, not code —

> `pass1_prompt.j2:60-61` — "`author`: string or null. Extract the source's primary author from the
> content if attributable; **null otherwise**."

The model reads "null otherwise" and emits the 4-character **string** `"null"`, which
`{"type": ["string","null"]}` (`pass1_schema.py:76`) accepts as valid. Measured across the 39 #123
truth probes: **19** a real author, **9** the string `"null"`, **5** genuine JSON `null`, **6** no
`pass1_fields` at all. Sentinels are **absent** from `key_themes` and `entity_search_keys`
(verified), so no sentinel can become a key label. Pass-1.5-side normalization is already decided
(task #30); the upstream prompt fix belongs here.

---

## 5. The concrete merged alternative, so the question isn't abstract

Stated only to give the options round something real to attack — not as a proposal:

> **One call per source.** It receives the source body **plus** a candidate identity list, and emits
> both the enrichment fields (`kdb_signal`, `domain`, `summary`, `key_themes`, `author`, audit) and
> the T2 selection with per-candidate attribution.

Costs 1–2 and 6–7 are stated unargued, as first written. **Costs 3, 4 and 5 were added or completed
after the response round and do carry verdicts** — all three are verified, and costs 3 and 4 each close
the merge on their own:

1. **Coupling of failures.** A malformed response loses enrichment *and* selection. Today a Pass-1.5
   failure leaves a correctly enriched source; the 13-terminal contract matrix
   (`kdb_search/contracts.py`) exists to make those partial outcomes typed and recoverable.
2. **Envelope.** Body bytes and evidence bytes now share one context. **Measured and largely
   dismissed** — see §6: at the pre-flight gate that actually runs, every probe document fits with
   M=100 intact. This cost is a proof obligation, not a feasibility limit, and it should **not** be
   used as an argument against the merge.
3. **`domain` circularity — and it is fatal to the "one call" framing.** The eligible space is
   scoped *by* `domain` (spec §1.2 / §5.1), which is itself a Pass-1 output. A merged call cannot
   use its own not-yet-emitted `domain` to scope the candidate list it is handed. Both branches
   have already been followed, and neither yields "one call":
   - **Whole-graph candidates instead.** This silently retracts a ratified owner decision: the
     #123 ledger row records *"domain gate always on for context-build (**Joseph's 3/3 override,
     on record**)"* — he overrode a unanimous panel to keep the gate. The cost is precision and a
     reversal of that override, **not** bytes: M=100 caps the hydrated set either way, so the
     envelope is indifferent to this branch.
   - **Keep classification separate.** Then the merge **eliminates no call**. It relocates
     `summary` / `key_themes` / `entity_search_keys` generation into the selector call and leaves a
     classifier call standing.

   **Consequence for the framing:** the "one call per source" statement above does not survive its
   own third cost. The honest merged alternative is *at best* "a classifier call plus a
   body-carrying selector call" — a materially more modest change than "why have Pass-1 at all."
   Any options round should start from that, not from the one-call sketch.
4. **Thin→fat staging — a second independent invalidation** (codex, 2026-07-26; verified). Final T2
   selection *is* the fat stage, and it is **"always preceded by the thin call, R4"**
   (`2026-07-25-task123-semantic-graph-search-spec.md:105`). Above M=100 it is thin's output that
   decides which bodies get hydrated for fat. So a merged call handed only candidate *identities* is
   performing **thin** selection, not final T2 selection; handed every candidate *body* it defeats the
   M=100 bound outright. Like cost 3 this holds regardless of bytes.
5. **`summary` has consumers outside search — but this is call *accounting*, not a blocker**
   (verified; **downgraded 2026-07-26** after Joseph corrected an overstatement). Pass-1's `summary` +
   mechanically appended `key_themes` **is** `Source.summary`, persisted as a GraphDB property
   (`compiler/compiler.py:129-141`), and it also appears as one trusted field in Pass-2's metadata
   block. **What it is not:** Pass-2's principal input. Pass-2 receives the **entire source body**
   plus the **T1/T2/T3 snapshot** (`prompt_builder.py:190-207`), and "authoritative" means only *"do
   NOT re-derive … no need to rewrite or merge it"* (`:132-145`) — a trust instruction. A merged call
   could emit `summary` itself, so nothing breaks. The surviving point is arithmetic: combined with
   costs 3 and 4, the merge **saves no call at all** — a classifier call still stands, a thin call
   still stands, and the descriptive fields must still be produced by someone. **Costs 3 and 4 are
   the blockers; this one is bookkeeping.**
6. **Re-selection.** Pass-1.5 can be re-run against a grown graph without re-enriching. Merged, the
   two cadences become one.
7. **Sunk work.** #123 P1 is complete (suite 2498) and D1–D9 are ratified against the split.

---

## 6. Coupling to queue item [2] — is the query cap forced by the envelope?

Item [2] asks whether the token/context-headroom concern is overweighted. It bears directly on Q1,
because if the 4,096 B query cap is *required* by the envelope, then Q1's answer is partly forced.
Measured, not asserted:

- Static guarantee, from the executable contract: 100 × 2,500 B evidence + 4,096 B query + 3,072 B
  system/template = **257,168 B** (`test_budget.py:316`), plus **26,000** reserved output (10k
  visible + 16k hidden) = **283,168** (`test_budget.py:323`) against `SMALLEST_POOL_BUDGET_TOKENS`
  = **320,000**. Spare: **36,832**. Note 320,000 is *already* gpt-5.4-mini's 400,000 window at
  `BUDGET_HEADROOM = 0.8` (`constants.py:137-139`), so the spare is post-headroom, not
  double-discounted.
- **Two different ceilings, and they must not be conflated** (codex, 2026-07-26): *appending* a body
  beside the 4,096 B projection permits ≤ **36,832 B** of body; *replacing* the projection frees its
  4,096 B and permits ≤ **40,928 B**.
- Source sizes — **and the population matters**. All `~/Obsidian` `.md` (n=1,909): median
  **2,398 B**, p90 **13,326 B**, p99 **83,496 B**. But that population is mostly *generated pages*,
  not ingestion sources. The probe sources are the population that matters, counted by **unique
  document** rather than per-probe (25 probes cover only 14 documents — §6.1): for the **13
  documents behind the scorable A/B/C probes**, median **31,214 B**, mean **38,995 B**, max
  **96,311 B**.

- **Two different *gates*, and this is the larger distinction.** `budget.py`'s module docstring keeps
  them apart and warns that conflating them *"would turn a by-construction argument into a
  measurement"*:
  - `worst_case_input_tokens` = `tokens == bytes` — the **pathological bound the static guarantee
    rests on**. This is what produces the 36,832 / 40,928 figures above.
  - `estimate_input_tokens` = `ceil(bytes / 4)` — the **calibrated estimate the pre-flight guard
    actually runs on** (`preflight`: `fits = estimated + reserved <= floor(ctx_window × 0.8)`).

  Maximum body under each, replacing the query block with M=100 held: **proof bound 40,928 B** vs
  **runtime gate 922,928 B** — a **22.5× spread**, the latter exceeding the largest file in the vault
  (199,092 B).

Measured with the shipped functions: **all 13 scorable documents pass pre-flight with M=100 and no
truncation**, the largest (96,311 B) consuming **113,346 of 320,000** tokens. Against the *proof
bound*, 8 of 13 fit and the other 5 would require freeing 8, 9, 17, 18 and 23 candidates.

**Corrected finding (three times over).** First: an earlier reading — that the cap is unforced because
vault notes are median 2.4 kB — was wrong, because it measured *pages* rather than sources. Second: the
follow-up claim that a full body would *"consume ~34 kB of the ~37 kB spare at the median and break the
guarantee above ~37 kB"* was **also** wrong — it used per-probe medians (double-counting 25 probes over
14 documents) and the *append* ceiling for a *replace* operation. Third, subsuming both: the correction
itself quoted the **wrong gate**. At the gate that actually executes, a full-body query costs **zero
candidates on every document in the probe set**. What the largest 5 documents forfeit is the
**by-construction static guarantee**, not the request.

So the 4,096 B projection is **not** envelope-forced, and the envelope constrains a **proof
obligation** rather than feasibility. This narrows Q1 rather than settling it: a body-informed query is
affordable, so the question becomes whether it is *worth* it — a measurement — plus a separate design
question about whether the query block must remain covered by a by-construction proof or may rest on
the estimator-plus-headroom guard that every other request in the system already uses.

### 6.1 The experiment that would settle Q1 on evidence — and it is runnable

Q1 is a question about real behavior, so it should be decided on data rather than argued. The direct
test exists: run the same probes **projection-vs-body** and compare on the normative precision@5 and
recall (spec §8.3 metric 3).

Verified runnable. Each probe records its origin, e.g.
`payload_origin: "sandbox-frontmatter:Value Investing/Accounting/Buffet style ROE discussion with
Gemini 3.md"`, and those paths resolve in `~/Obsidian`:

- **25 of 39** probes resolve to a real source document — classes **A=18, B=3, C=2, F=2**. These 25
  probes cover only **14 unique documents**, so per-probe size statistics double-count; quote
  unique-document figures (§6).
- **14 do not, by construction** — **D=3** (`kimi-drafted human query`), **E=5**
  (`kimi-drafted (abstention probe)`), **G=3**, and **H=3** (adversarial — omitted from an earlier
  enumeration here, caught by codex). These are synthetic queries with no originating source, so a
  body variant is undefined for them, not missing.
- **F01/F02 resolve but cannot exercise selector quality.** Both carry
  `space.kind = "empty_override"` with `abstention_reason = "domain_empty at compile time"`, so
  abstention is structurally forced no matter what the query says — and spec §283 confirms
  *"domain-empty/domain-missing abstentions are **not** selector failures."*

So the scorable denominator is the **23 A/B/C probes** (13 unique documents), not 25. One
methodological constraint: **M must be held constant** in the initial arm, since reducing it would
confound query quality with candidate retention (codex). No exclusion or truncation is needed — every
one of the 13 documents clears pre-flight whole at M=100 (§6); the 5 largest simply sit outside the
by-construction guarantee, which is a proof caveat to record rather than a reason to alter the arm.
Excluding or truncating them would bias the result toward "the projection suffices," since the largest
documents are exactly where a 4 kB projection should lose the most.

Caveat to state plainly: the fixture's `excerpts/` are truncated to 2,500 B and describe the
**evidence** side (163 *pages*, i.e. Pass-2 output). The body arm changes the **query** side only.
Nothing about the evidence pool changes, so the fixture stays valid for both arms.

---

## 7. Out of scope for this question

- The **existence** of Pass-2. Not in question.
- **T1 / T3** derivation. Deterministic; untouched (§4).
- The **selector's** own prompt and wire contract. Settled: Call-1 letter labels, **landed as D11 in
  spec v0.16 / blueprint v0.14 on 2026-07-27** (task #25), alongside D10's prompt ordering.
- Whether Pass-1.5 should **gate** on its outputs. That is queue item [4] / task #29.

## 8. What resolving this unblocks or invalidates

- **Blocks:** the batched spec v0.16 / blueprint v0.14 amendment (task #25) was deliberately held
  until Q1 was settled — no point re-deriving §7.0a's byte table if the answer restructured the
  passes. **RELEASED and LANDED 2026-07-27**, once Joseph closed Q1: spec v0.16 / blueprint v0.14
  carry D10 (prompt ordering) and D11 (letter key-labels, §7.0a re-derived to 9,271 B / break-even 14).
- **Does not block:** #123 P2 implementation of the selector itself, whose contract is settled.
- **Would invalidate if Q1 chooses the merged call:** the two-call staging in spec §5.1, the
  Pass-1.5 adapter boundary, and parts of the 13-terminal matrix.
