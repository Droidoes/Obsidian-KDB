# Task #125 — Synthesis of the two formal responses

Date: 2026-07-26 · Task: **#125** · Status: **synthesized position — awaiting owner decision on one number and one option**

Synthesizes:
- `2026-07-26-task125-two-pass-boundary-response-fable.md` (fable — position paper)
- `2026-07-26-task125-two-pass-boundary-response-codex.md` (codex — `CONCUR-WITH-ITEMS`)

against the problem statement `2026-07-26-task125-two-pass-boundary-question.md`.

Per the convergence discipline: **2/2** findings are load-bearing, **1/2** catches are surfaced
individually, and the three genuine disagreements are resolved with a stated winner. Every codex
figure was independently verified before folding; the verification also **falsified one of fable's
own numbers** (§4.3) and **narrowed one of its arguments** (§4.2).

---

## 0. Synthesized position

**The boundary question is closed. The representation question is open and cheap to settle.**

- **Closed — do not merge the passes.** Option C is closed **independently by two grounds, neither
  requiring measurement**: `domain` circularity (question doc §5) and thin→fat staging (codex,
  verified §2.1). A third consideration — that `summary` must still be produced for GraphDB's
  `Source.summary` and for Pass-2's metadata block — is **not** a structural blocker at all
  (§4.4, corrected): a merged call would simply emit it. It belongs to the *call accounting*, not
  the blocker list. Together: C is not "dominated pending evidence" — it is **empty**, with a large
  cost set and a benefit set that contains nothing.
- **Open — the ≤4,096 B projection has never been tested** and is the only live question. It was
  distilled for consumers #123 retires, and its quality is now load-bearing.
- **Newly established, and it cuts against fable's own framing twice over:** carrying body content
  into the selector query is not merely cheaper than fable priced it — **at the gate that actually
  runs it is free for every document in the probe set.** The 40,928 B ceiling belongs to the *static
  guarantee's pathological `tokens == bytes` bound*, not to the runtime pre-flight, which estimates
  at `ceil(bytes / 4)`. Measured with the shipped functions (§4.3): **all 13** unique source
  documents pass pre-flight with **M=100 intact and no truncation**, the largest at **113,346 of
  320,000** tokens. There is no exclude-or-truncate fork and no candidate sacrifice.

**Consequence:** the escalation ladder in fable §3 collapses from A ⊂ B ⊂ C to **A vs B**, and the
external panel rung disappears with C. What remains is one experiment and one owner-set number.

**What Joseph must decide (only two things):**

1. **The materiality threshold** — how much precision@5 / recall gain justifies adopting B. Codex is
   right that this is an owner exchange rate, not a technical fact (§4.1). Proposal in §6.
2. **Confirm C stays closed.** Codex's phrasing is the correct standard: do not pursue C *unless
   Joseph explicitly reopens* the affected #123 decisions. Nothing here asks him to.

---

## 1. Convergent findings (2/2 — load-bearing)

Both reviewers reached these independently. Treated as settled.

| # | Finding |
|---|---|
| 1 | **Ratify the Pass-1 boundary; do not ratify the current projection.** The stage earns its keep; the ≤4 kB interface has not been tested. (fable §0; codex "Recommended disposition") |
| 2 | **Q1 conflates two independent decisions** — *boundary* (should enrichment stay separately persisted?) vs *representation* (should search consume metadata, body, or both?). A body-informed selector does **not** require merging. Codex states this more crisply and it is adopted as the synthesis frame. |
| 3 | **The merge (C) is not viable under D1–D9** and should not be pursued without the owner reopening ratified decisions. |
| 4 | **The experiment needs a decision rule predeclared before firing** — D7's thresholds are deliberately diagnostic, so results cannot auto-settle Q1. |
| 5 | **Keep A as the production baseline while running B as an experiment** — the arms differ only in query representation. |
| 6 | **Fix the Pass-1 prompt regardless of outcome** — redefine `entity_search_keys` for semantic selection rather than PK lookup; require literal JSON `null` for absent authors. Unconditional under every branch. |

---

## 2. Codex's unique catches (1/2) — all four verified, all folded

I verified each before accepting it. Evidence below is mine, not restated from codex.

### 2.1 Thin→fat staging independently invalidates "one call" — **CONFIRMED**

`spec:105` reads: *"Fat selection prompt (stage 2 — the final selection; always preceded by the thin
call, R4)."* Above M=100, thin output determines which bodies are hydrated for fat selection.

A merged call handed only candidate *identities* is therefore performing **thin** selection, not
final T2 selection; handed every candidate *body* it defeats the M=100 bound outright. This is a
third invalidation of the one-call framing, independent of the domain circularity the question doc
found and of any byte argument. **This is the strongest single item in either response** — it kills C
structurally rather than by pricing.

### 2.2 Append vs replace ceiling — **CONFIRMED, and it corrects the question doc**

Verified against the executable contract, not prose:
- `test_budget.py:316` — `fat_worst_case_request_bytes() == 257_168` (= 100 × 2,500 + 4,096 + 3,072)
- `test_budget.py:323` — `fat_static_guarantee_tokens() == 283_168` (+26,000 reserved output)
- `constants.py:139` — `SMALLEST_POOL_BUDGET_TOKENS = 320_000`
- Spare = **36,832**

So: **appending** a body beside the 4,096 B projection permits ≤ **36,832** body bytes;
**replacing** the projection frees its 4,096 B and permits ≤ **40,928**. The question doc §6 said
"substituting" while using the append threshold. Codex's correction stands and its consequences are
larger than he claimed — see §4.3.

**Guardrail check (neither response raised it, worth pinning):** `BUDGET_HEADROOM = 0.8` is **already
inside** the 320,000 figure — `constants.py:137-139` documents it as *"gpt-5.4-mini's 400,000 window
at `BUDGET_HEADROOM`."* The 36,832 spare is therefore post-headroom and is **not** double-discounted.
Both responses' arithmetic is safe on this point.

### 2.3 Probe denominators — **CONFIRMED exactly, including an omission in the question doc**

Measured over `benchmark/truth/task123_search_probes_v1.json` against `~/Obsidian`:

- Class distribution: **A=18, B=3, C=2, D=3, E=5, F=2, G=3, H=3** = 39.
- **Resolvable: 25** — A=18, B=3, C=2, **F=2**. **Unresolvable: 14** — D=3, E=5, G=3, **H=3**.
- The question doc §6.1 enumerated only D01–D03, E01–E05, G01–G03 (11) against a stated 14. **The
  missing 3 are the adversarial H probes** — codex caught an enumeration gap, confirmed.
- **F01/F02 cannot exercise selector quality**: both carry `space.kind = "empty_override"` and
  `abstention_reason = "domain_empty at compile time"`, so abstention is structurally forced
  regardless of query representation. Spec §283 agrees — *"Domain-empty/domain-missing abstentions
  are **not** selector failures."* → **the scorable denominator is 23, not 25.**
- **The 25 probes cover only 14 unique documents** (13 for the 23 A/B/C probes). Per-probe medians
  therefore double-count. Corrected figures in §5.

### 2.4 Do not reduce M in the initial arm — **CORRECT, and it fixes a flaw in fable's design**

Fable's Arm F offered "envelope relaxation *(or a reduced-M variant)*." Reducing M would confound
query quality with candidate retention — two variables, one measurement. **Adopted:** hold model,
scope, candidates, evidence, M, and result cap identical; change **only** `QueryPayload.text`.

---

## 3. Fable's unique catches (1/2) — retained

Codex's response is sharper on mechanism; these are the architectural grounds it does not contain.
They matter because they hold **independently of what the experiment measures**.

1. **The intrinsic/relational line (fable §1.2).** Every Pass-1 output is intrinsic to the source and
   frontmatter-embedded; T2 selection is relational — a function of *(source, graph state now)*. The
   ratified frontmatter principle draws exactly this line (`task89-deliberation-wikilinks-frontmatter.md:135`,
   sectionalized as D-89-16). The pass boundary is that data-model decision expressed in call
   structure, so a merged call would emit one envelope straddling it.
2. **Cadence asymmetry (fable §1.3).** Enrichment is compute-once; selection is
   compute-per-graph-state. Merged, every re-selection against a grown graph re-pays body tokens to
   recompute fields that cannot have changed — and post-development, re-selection is the *normal*
   case. Codex names "independent re-selection" as a virtue but does not price its loss.
3. **The projection is compression, not truncation (fable §1.1).** The model that wrote
   `summary`/`key_themes`/`entity_search_keys` had the whole body in front of it, so the body's
   information reaches the selector *via distillation*. **Load-bearing for the experiment:** a poor
   Arm P result indicts the current *prompt* before it indicts the *boundary*, which is why Q2 must
   be a measured rung and not merely parallel hygiene.
4. **The `P−k` ablation arm (fable §3).** Score a third arm with `entity_search_keys` removed from
   the projection. This applies the consumer-purpose test to the field itself now that its original
   consumer is retired: if `P−k ≈ P`, Q2 is redesigning a field that earns nothing. Cheap, and it
   answers a question neither response otherwise asks.

---

## 4. Disagreements resolved

### 4.1 Who sets the materiality threshold — **codex wins**

Fable predeclared ≥0.10 aggregate delta. Codex holds that D7's thresholds are intentionally
diagnostic *by owner policy*, so the projection-vs-body result informs Q1 but cannot settle it until
Joseph specifies what quality gain justifies the cost.

**Resolution:** keep fable's *structure* (a rule fixed before firing, per the #87 criteria-before-probes
discipline), hand the *number* to Joseph. The quality/cost exchange rate is an owner decision — and
D7's diagnostic status was itself his ruling, so inventing a binding threshold here would quietly
overturn it. §6 proposes a concrete number to accept or amend, which is the "don't over-ask" form:
he adjusts a number rather than authoring one.

### 4.2 Does the envelope argument kill the merge? — **narrowed against fable**

Fable §1.1 argued the merged call is "the one call the envelope cannot hold." Verified: **false at the
gate that runs.** Every probe document fits pre-flight with M=100 (§4.3); what fails for the largest 5
is the *by-construction guarantee*, not the request. The envelope constrains a **proof obligation**,
not feasibility.

**Resolution:** the envelope is withdrawn as a killing ground entirely. C still dies — on §2.1
thin→fat and domain circularity — but **not** on bytes, at either gate. Fable's §1.1 is retracted on
this point. Two follow-ons: the envelope objection **cannot** be recycled against option B (§4.3), and
"source-complete × graph-aware is infeasible" — fable's central architectural claim — is **not**
established by arithmetic. The boundary's defence rests on §3's intrinsic/relational and cadence
grounds plus §2.1's staging, none of which are byte arguments.

### 4.3 Fable mispriced option C's exchange rate — **falsified by measurement**

Fable §2 claimed C costs "median source 34,029 B ≈ **14 candidates**; max 96,311 B ≈ **39
candidates** — up to two-fifths of M=100." That arithmetic divided body bytes by 2,500 B/candidate,
**ignoring both the 36,832 B spare and the 4,096 B freed by replacing the query block**. It is wrong
in the same class as the population error already corrected once in this task: an unverified division.

**But correcting the division was not enough — the ceiling itself was the wrong gate.** `budget.py`'s
own module docstring keeps two quantities apart and warns that conflating them *"would turn a
by-construction argument into a measurement"*:

- `worst_case_input_tokens` = `tokens == bytes` — **the pathological bound the static guarantee rests
  on**, valid only under the route's `tokens_lte_bytes` premise. This is where 40,928 B comes from.
- `estimate_input_tokens` = `ceil(bytes / 4)` — **the calibrated estimate the pre-flight guard
  actually runs on** (`preflight`: `fits = estimated + reserved <= floor(ctx_window × 0.8)`).

Recomputed with the shipped functions, body **replacing** the query block, `M` held at 100:

| Unique A/B/C doc | rendered B | est. tokens + reserve | **runtime gate** | worst-case bound | proof |
|---|---|---|---|---|---|
| 1,939 → 34,029 (8 docs) | 255,011–287,101 | 89,753–97,776 | **FITS** | 281,011–313,101 | holds |
| 58,610 | 311,682 | 103,921 | **FITS** | 337,682 | **breaks** |
| 63,417 | 316,489 | 105,123 | **FITS** | 342,489 | **breaks** |
| 82,083 | 335,155 | 109,789 | **FITS** | 361,155 | **breaks** |
| 85,358 | 338,430 | 110,608 | **FITS** | 364,430 | **breaks** |
| 96,311 (max) | 349,383 | **113,346** | **FITS** | 375,383 | **breaks** |

Maximum body under each gate: **runtime 922,928 B** vs **proof 40,928 B** — a **22.5× spread**. The
runtime ceiling exceeds the largest file in the entire vault (199,092 B).

**So the corrected picture is not "cheap at the median, costly in the tail" — it is free everywhere in
the probe set.** All 13 documents pre-flight with M=100 and no truncation, the largest consuming
113,346 of 320,000 tokens (35%). Fable's "≈14 candidates at the median / ≈39 at max / two-fifths of
M" was wrong on the divisor *and* on the gate; the true candidate cost at the running gate is **zero,
for every document**.

**Three consequences, all material:**
- **The exclude-or-truncate fork dissolves.** An earlier draft of §6 offered to drop or truncate the 5
  oversized documents. Both choices bias toward A — those 5 are precisely where a 4 kB projection
  should lose the most — so the experiment would have run on the 8 documents least likely to show a
  gap. **Run all 13 whole.**
- **Arm F is a production-viable configuration, not an instrument.** Fable called it "a measurement
  instrument, not a production candidate." At the runtime gate it is simply a valid request.
- **What arm F costs is the *proof*, not the *call*.** For 5 of 13 documents the by-construction
  static guarantee no longer holds — the request still passes pre-flight, but its sufficiency rests on
  the estimator plus the 0.8 headroom rather than on a sizing argument. That is a real distinction and
  it is the actual design question inside option B (§5, §6).

### 4.4 Codex's B and fable's C are the same architecture — and that closes C

Neither document notices this. Codex's B is *"preserve Pass-1; let Pass-1.5 consume a body-informed
query."* Fable's C is *"classifier call + body-carrying selector."* The only difference is whether
Pass-1 keeps producing the descriptive fields.

It must — though **weakly, and an earlier draft of this section overstated why.**

> **Correction of record (Joseph, 2026-07-26).** This section first claimed
> *"`Source.summary` is Pass-2's authoritative input"* and that relocating its generation would
> *"break Pass-2's authoritative input."* **Both are wrong**, and Joseph caught it. Verified against
> `compiler/prompt_builder.py:190-207`, Pass-2's user prompt is:
> `source_name` + a small **PASS-1 SOURCE METADATA** block + `## SOURCE CONTENT {source_text}`
> (**the entire source body**) + `## EXISTING CONTEXT (graph snapshot)` (**the T1/T2/T3
> ContextSnapshot**) + schema + exemplar. So Pass-2's primary inputs are **the full body and the
> graph context**; `summary` is one line inside a four-field metadata block. And "authoritative"
> means only *"do NOT re-derive them from the source body … you do not need to rewrite or merge it"*
> (`prompt_builder.py:132-145`) — a **trust instruction**, not a statement of primacy. Pass-2 holds
> the body and could re-derive a summary; it is told not to, for consistency.

What survives is narrow: **something must still produce `summary`**, because it is persisted as the
GraphDB `Source.summary` property (`compiler.py:129-141`) independently of any prompt. A merged call
could emit it perfectly well. So this is **not** a structural blocker — it is a line in the call
accounting.

**The accounting is still what matters.** Fable's C reduces to codex's B plus relocating fields that
someone has to produce anyway — and since the classifier call still stands (domain circularity) and
the thin call still stands (§2.1), the merge **saves no call at all**. That is why §0 calls C empty
rather than merely dominated, and why the panel rung in fable §3 is retired. **But note the load is
carried entirely by §2.1 and domain circularity**; anyone reopening C should be answered with those
two, never with `Source.summary` and never with bytes (§4.2).

**One thing this correction opens up, and it matters for the live question.** Pass-2 is a working
precedent for presenting an LLM **both** the full body **and** a distillation side by side, with
explicit instructions about which to trust for what. So the stage-2 representation question is not
the binary *projection XOR body* that both responses assumed — **projection AND body** is a third
configuration, already proven in this codebase. See §6.

---

## 5. Corrected figures — single source of truth for the experiment

Supersedes the question doc §6/§6.1, fable §2/§3, and codex finding #4 wherever they differ.

| Quantity | Value | Source |
|---|---|---|
| Fat worst-case request | **257,168 B** | `test_budget.py:316` |
| Static guarantee total | **283,168 tokens** | `test_budget.py:323` |
| Smallest pool budget (400k × 0.8 headroom) | **320,000** | `constants.py:137-139` |
| Spare (post-headroom) | **36,832** | derived |
| Body ceiling, **append** — *proof bound* (`tokens == bytes`) | **≤ 36,832 B** | codex, verified |
| Body ceiling, **replace** — *proof bound* | **≤ 40,928 B** | codex, verified |
| Body ceiling, **replace** — ***runtime pre-flight*** (`ceil(bytes/4)`) | **≤ 922,928 B** | measured, `budget.preflight` |
| Candidate cost at the **runtime** gate, any probe document | **0** (M=100 holds for all 13) | §4.3 |
| Candidate cost at the **proof** bound | 0 for 8 docs; up to 23 for the largest | §4.3 |
| Fat worst case as shipped, at the **runtime** gate | 90,292 / 320,000 = **28%** | derived |
| Fat worst case as shipped, at the **proof** bound | 283,168 / 320,000 = **88.5%** | `test_budget.py:323` |
| Probes total / resolvable / unresolvable | **39 / 25 / 14** | measured |
| **Scorable** for selector quality | **23** (A=18, B=3, C=2) | F01/F02 forced-empty |
| Unique documents behind the 23 | **13** | measured |
| Unique-doc sizes (13, A/B/C) | median **31,214 B**, mean **38,995 B**, max **96,311 B** | measured |
| Unique-doc sizes (14, incl. F) | median **29,336 B**, mean **36,753 B**, max **96,311 B** | codex, verified |
| Docs fitting the replace ceiling | **8 of 13** | measured |
| Worst-case candidate cost at M=100 | **23 candidates**, one document | derived (§4.3) |

**Retired figures — do not cite:** per-probe median 34,029 B (double-counts 25 probes over 14 docs);
"25 probes measure selector quality" (23); "C costs ~14 candidates at the median" (zero at either
gate); "M 100 → 77 worst case" (a proof-bound artifact — the runtime gate sacrifices nothing);
"the envelope is a policy constraint on the tail" (it is a constraint on the *proof*, not the call).

**Which gate to quote.** Rows above are labelled because the two differ by 22.5× and the distinction
is load-bearing: `budget.py` warns that conflating them *"would turn a by-construction argument into a
measurement."* Quote the **proof bound** when arguing that a configuration is safe *by construction*;
quote the **runtime gate** when asking whether a request will actually execute. Arm F needs only the
second.

**Direct answer to queue item [2] — the strongest form the data supports.** The headroom concern is
**almost entirely a property of the proof discipline, not of the calls.** The shipped fat worst case
consumes **28%** of the usable window at the calibrated estimator but **88.5%** at the pathological
bound — and the usable window is itself already discounted 20% by `BUDGET_HEADROOM`. That ~3.1× gap is
the entire source of the tightness that has shaped several #123 decisions. This does **not** make the
proof wasteful: it is by-construction, immune to density variance, and it is what killed codex's 381 kB
counterexample "by sizing, not by measurement." But it does mean the operative question for B — and
for [2] generally — is narrower than it has been treated: **must the by-construction guarantee cover
the query block, or does the estimator-plus-0.8-headroom guard suffice there, as it does for every
other request in the system?** That is a design decision about proof obligations, not an arithmetic
constraint.

**Caveat neither response raised — part of the spare is unbanked.**
`SYSTEM_TEMPLATE_BUDGET_BYTES = 3,072` is explicitly *"a declared reserve, not a measurement"*, with
a stated **P2 obligation**: *"the real rendered templates must be asserted against this, and this
figure raised (with the guarantee recomputed) if they exceed it"* (`constants.py:128-135`). If real
templates exceed 3,072 B, the 36,832 spare shrinks and the **proof-bound** 40,928 ceiling drops with
it — 4 B of ceiling per byte of overrun. **If B elects to preserve the by-construction guarantee, its
byte policy must be set after P2 measures the templates**, alongside #25's byte-table re-derivation.
If B rests on the runtime guard instead, template overrun is immaterial at a 22.5× margin. Either way
this is a direct input to queue item **[2]**, and it does not affect **arm F**, which needs only
pre-flight.

---

## 6. The experiment, as synthesized

**Denominator:** the **23** A/B/C probes (13 unique documents). F01/F02 excluded — forced-empty space.
Scored on the normative precision@5 and recall (spec §8.3 metric 3).

**Controls (codex §2.4):** identical model, scope, candidates, evidence, **M**, and result cap. Change
**only** `QueryPayload.text`. No M reduction in the initial round.

**Arms:**
- **P** — current projection, as-is. Baseline.
- **F** — full body replacing the projection. **All 13 documents run whole, M=100 held, no
  truncation, no exclusions** — every one passes pre-flight (§4.3). Record per-probe that arm F sits
  outside the by-construction static guarantee for the 5 documents over 40,928 B; that is a proof
  caveat on the arm, not a reason to alter it.
  > **Deliberately rejected:** excluding or truncating those 5. Both bias toward A, because the
  > largest documents are exactly where a 4 kB projection should lose the most — the experiment would
  > have measured F−P on the 8 documents least likely to show a gap and then concluded "A suffices."
- **PF** — projection **and** body together, the projection kept as a trust-labelled header above the
  body. **Added after the §4.4 correction**, which established that both responses framed this as a
  binary when it is not: Pass-2 already runs exactly this configuration
  (`prompt_builder.py:190-207`) and it is the arrangement most likely to win, since it strictly adds
  information to P. Cost is the sum of both, still inside pre-flight for every probe document.
  Without this arm a P-vs-F result cannot distinguish *"the body helps"* from *"the projection
  hurts."*
- **P−k** *(optional, cheap — fable §3)* — projection minus `entity_search_keys`. Prices the field.

**Decision rule (structure fixed now; threshold Joseph's):**

1. **F − P below threshold** → the 4 kB compression suffices. **A ratified**; #25 unblocks with §7.0a
   intact; Q2 proceeds as hygiene.
2. **F − P at or above threshold** → run the Q2 prompt revision, re-run the pair (**P′ vs F**, same
   session per the apples-to-apples rule).
   - **Gap closes** → **A** — the prompt was the culprit and the interface is vindicated.
   - **Gap persists** → **B**. Its one real design question is the proof obligation (§5): keep the
     by-construction guarantee over the query block — capping body content at 40,928 B less any P2
     template overrun — or rest the query block on the estimator-plus-headroom guard that every other
     request already relies on, which is effectively unbounded for real sources.
3. **C is not on this ladder.** It reopens only if Joseph explicitly reopens the #123 decisions.

**Proposed threshold — Joseph's to set or amend before firing:** **≥ 0.10** aggregate delta on either
normative metric, corroborated by the paired per-probe view (F must win the pairs, not one outlier).
Rationale for a modest number: with C closed, the only cost on the table is B's — one spec/blueprint
amendment, a proof-obligation decision, and **zero** candidate loss on every probe document at the
running gate (§4.3). The threshold is guarding a cheap change, not an expensive one.

**What the experiment cannot decide:** it prices signal loss only. §3's intrinsic/relational and
cadence arguments are architectural; even a large gap argues for **B**, never for the merge.

---

## 7. Unconditional work — Q2 / Q2b (2/2 convergent)

Independent of the experiment's outcome:

1. **Redefine `entity_search_keys` for its actual consumer.** Written under *"imperfect slugs simply
   miss, no harm"* (`pass1_schema.py:79-84`) — a PK lookup that ignored bad keys. As selector query
   expressions a bad key is a **false query** the model matches on and abstention is scored against.
   Rewrite for the consumer that punishes wrong keys.
2. **Revisit the slug form.** Canonical-slug guessing was right for PK lookup; whether hyphenated
   slug-form is right for an LLM selector is open — resolved **within** the graph-blind constraint (no
   graph vocabulary, no candidate hints in Pass-1 — D-NW4-5). The field stays a pure function of the
   source under every option.
3. **Template compliance** — definition + illustrative-only examples; examples ground form, never
   relationships.
4. **Q2b (`author`)** — replace *"null otherwise"* (`pass1_prompt.j2:60-61`) with an explicit "emit
   JSON `null`, never the string `\"null\"`". Task #30's projector-side normalization stays as the
   coerce-don't-reject backstop; this is the upstream fix.

Item 1 **is** the P′ of §6 rule 2, so if round 1 shows a gap this work is the next measured rung
rather than parallel cleanup.

---

## 8. Sequencing

1. **Question doc corrected in place** (done 2026-07-26) — append/replace conflation, per-probe median,
   25-vs-23 denominator, H-probe enumeration gap, and the two verified structural blockers added to §5.
2. Size the harness delta: alternate query-block builder, plus a way to run arm F outside the
   by-construction guarantee while still honouring pre-flight. Query side only — the evidence pool is
   untouched, so the fixture stays valid for both arms.
3. **Joseph sets the threshold**, then fires round 1 (P, F, optionally P−k) — all 13 documents whole,
   M=100 held.
4. **#25 stays held** until A vs B resolves — A leaves §7.0a intact, B rewrites it.
5. **#123 P2 is not blocked** (unchanged from the question doc §8). P2 additionally supplies the
   template measurement, which matters to B **only if** B elects to preserve the static guarantee.
6. Q2/Q2b land with the #25 amendment batch — one re-derivation, one review cycle.
7. **No external panel.** It was contingent on the C fork, and C is closed independently by domain
   circularity and thin→fat staging — neither of which needs measurement.

## 9. What this synthesis does not claim

- **Not** that the split's original justification survives — it does not (question doc §1, §2.1). The
  boundary is re-earned on §3's grounds, none of which depend on the retired consumer.
- **Not** that the current projection is adequate. It is **untested**, which is the whole point of §6.
- **Not** that C is impossible in principle — only that it is **empty in this codebase**: no call
  saved, two independent structural blockers (plus a third that forecloses the classifier-plus-selector
  variant), and its one real benefit (body reaching the selector) fully available inside option B.
- **Not** that C fails on bytes. It does not, at either gate (§4.2). Anyone reopening C should be
  answered with thin→fat staging and domain circularity, never with the envelope.
- **Not** that the static guarantee was a mistake. It is a by-construction proof and it did its job.
  The finding is only that it must not be **quoted as a feasibility limit** on requests that the
  runtime gate clears with a 22.5× margin.
