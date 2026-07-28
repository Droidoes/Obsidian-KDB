# Task #125 — Stage-2 representation: predictions registered before firing

Date: 2026-07-27 · Task: **#125** · Status: **pre-registration — written before any arm is run**

Registers falsifiable expectations for the stage-2 query-representation experiment, at Joseph's
request, *before* any API spend. Nothing here is a decision. If a prediction is wrong, that is the
useful outcome; the point is to make "we expected that" checkable rather than reconstructable.

**Scope, after the 2026-07-27 walkthrough.** The architecture question is **closed** — Joseph ratified
Pass-1 ↔ Pass-1.5 ↔ Pass-2 as final. What remains is a **capacity/performance** question localized to
Pass-1.5 stage-2, settled by trial:

> **Does giving the stage-2 selector the source body, in addition to what it already gets, improve
> selection?**

---

## 0. Why this document exists, stated plainly

Two reasons, and the second is about me.

1. **A null result is only informative if the prediction preceded it.** If the two arms come out
   equal, that should be on record as *predicted* or *surprising* — not narrated afterwards.
2. **My error record in this task points one way.** Across #125 I made four substantive errors — the
   findability claim, the source-population measurement, option C's candidate pricing, and
   "`Source.summary` is Pass-2's authoritative input" — and **every one favoured keeping the current
   architecture.** That is a direction, not bad luck. The central prediction below (§4, Prediction 1)
   favours the status quo, and is registered at barely better than a coin flip for that reason.

---

## 1. The two arms

Joseph's scoping, 2026-07-27: *"since we currently have P, the experiment should be between P and
PF."* Correct, and tighter than the 2×2 lattice this document first proposed.

| Arm | What the query block carries | Note |
|---|---|---|
| **`keys+summary`** | `entity_search_keys` (lettered) + `domain` + `author` + `key_themes` + `summary` | **Production today.** The baseline |
| **`keys+summary+document`** | all of the above **plus the full source `.md`** | The candidate |

Everything else is identical: same model, scope, candidates, evidence, **M=100**, result cap, and all
13 source documents run whole (no truncation, no exclusions — every one clears pre-flight).

**Why two arms and not four.** An earlier draft proposed a 2×2 adding `keys-only` (does the
descriptive projection earn its bytes?) and `keys+document` (should the body *replace* the summary?).
Both were dropped: the confound the lattice existed to avoid — "did the body help or did the summary
hurt?" — **only arises if you replace**, and nobody is proposing replacement. The candidate arm
strictly *adds* to the baseline, so the comparison is already clean. The extra arms buy knowledge,
not decisions.

> **Retracted: the `P−k` arm.** A "projection minus `entity_search_keys`" arm was proposed and **is
> not runnable.** `projection.py:303-306` renders the keys as the labelled, indexed list that
> stage-2's wire attributes every hit against; remove them and `matched` has nothing to reference.
> **The keys are not an ablatable field — they are the query being asked.** This sharpens Q2: bad
> keys are not degraded metadata, they are *the wrong question asked*, under every arm.

**Both arms run on the D10-corrected prompt order.** Evidence first, query last (spec §2.1, ratified
2026-07-27). This is a **fix, not an arm** — Joseph: *"reordering should not be part of the
experiment, it should be the official fix… after that done, we can experiment."* It removes a real
confound: with ~250 kB of evidence ahead of it, a query that grows to ~38 kB in the candidate arm
would sit far from the generation point, and a null result could have meant "too far away" rather
than "didn't help."

---

## 2. What the metrics can and cannot resolve — read this before choosing a threshold

The most consequential section, and it **retracts the threshold I proposed earlier**.

**Precision@5 has a high floor and is probably insensitive.** The label policy has three tiers, and
`acceptable_alternative` is explicitly *"recall-neutral and **precision-acceptable**"* — it does not
cost precision. For A01 that means **6 relevant + 21 acceptable = 27 of the 51 eligible entities are
precision-safe.** A blind draw of 5 scores ~0.53. It cannot cleanly separate good from mediocre on the
alternative-rich probes.

**Class-A micro recall over relevant slugs is the discriminating metric**, with a smaller denominator
than the probe count suggests:

- 18 class-A probes − **A10** (`class_a_abstention_probe_excluded`) − **A09/A12**
  (`class_a_precision_only_probes`, zero relevant slugs) = **15 probes** carry class-A recall.
- Aggregation is `micro_relevant_slug`, so resolution comes from slug-level trials, not 15 — A01
  alone contributes 6. Order tens of judgments. Detectable, but noisy: **paired per-probe comparison
  is essential**, not just means.

**Abstention is effectively unmeasurable here.** Its denominator is `[E01–E05, A10]`, and E01–E05 are
kimi-drafted with **no source document**, so the candidate arm is undefined for them. That leaves
**A10 alone, n=1.** If the body's real benefit is better abstention judgment, this experiment cannot
see it.

**Class difficulty runs opposite to my earlier assumption.** From the probes' own notes: **B** is
*"exact-named concept — the LLM's own sanity baseline"* (trivial); **C** is near-named singular/plural
surface variance (easy); **A** is the genuine semantic-judgment class — A01 poses it directly: *"do
Buffett-concept pages count as relevant to the person key?"* So 18 of 23 probes are the discriminating
ones, which is **good for power**, and corrects what I told Joseph in the walkthrough.

**Therefore, retracted:** my *"≥0.10 aggregate delta on either normative metric."* It pooled a
high-floor insensitive metric with the discriminating one, and pooled classes of wildly different
difficulty, letting 5 trivial probes dilute a real class-A effect. **Instead:** **class-A micro
relevant-slug recall is primary**, reported per class and never pooled, paired per probe, with
precision@5 as a **guardrail** (did it get worse?) rather than the signal. Any threshold Joseph sets
belongs on class-A recall alone.

---

## 3. The mechanisms in tension

Both directions have a specific mechanism. Neither is clearly stronger — which is the honest reason to
spend money here rather than argue.

**Why the body should help — the projection carries no proportion.** `key_themes` and
`entity_search_keys` are *unordered lists*; `summary` is one sentence. Nothing in the projection
conveys **emphasis, centrality, or how much of the document is about what.** But class A's labelling
question *is* a centrality judgment — of 16 excerpt-visible Buffett mentions, which 6 are *required*
versus merely defensible. A 34 kB body conveys proportion; a flat 10-item list plus one sentence
cannot.

**Why the body should hurt — tangent inflation.** The real sources are long discursive documents
(lecture transcripts, recorded model discussions; median 31 kB), which mention many entities in
passing. A selector reading the body sees every tangent as a candidate, surfacing false positives. The
projection is a *deliberate abstraction of aboutness* and suppresses exactly that.

**A third possibility worth naming: dilution.** The candidate arm's query grows ~9×. Even with D10
placing it last, a 34 kB block may simply attract less focused attention per byte than a 4 kB one. If
so the result reads as "no effect" while the real finding is about presentation — see Prediction 4.

---

## 4. Predictions

**Prediction 1 — `keys+summary+document` − `keys+summary` on class-A micro recall will be small:
< 0.10.** *Confidence: 55% — deliberately barely above a coin flip, per §0.* Mechanism: the projection
was distilled by a model that read the whole body, so at the granularity of ranking ~50 candidates it
may already carry enough. **Counter-mechanism I take seriously:** §3's proportion argument is specific,
and class A is precisely a tiering task. *Falsified if* the delta ≥ 0.10.

**Prediction 2 — the candidate arm will not be *worse* on class-A recall (delta ≥ −0.02).**
*Confidence: 75%.* It strictly adds information. **If it comes out materially worse, that is a
presentation defect, not a representation finding** — most likely dilution — and the response is to
fix presentation and re-run, not to conclude the body is useless.

**Prediction 3 — the pooled 23-probe aggregate will show no material difference even if class A
alone does.** *Confidence: 70%.* B and C are near-lookup classes where both arms should saturate. **This
is the procedurally important one:** had we fired under the aggregate rule I originally proposed, the
likely outcome was "baseline suffices, ratified" — reached by dilution rather than by evidence.

**Prediction 4 — precision@5 will move less than recall in either direction, possibly not at all.**
*Confidence: 65%.* Mechanism: the high floor in §2. **Registered so a flat precision reading is not
later cited as evidence of "no effect"** — it is weak evidence either way by construction.

**Prediction 5 — per-probe variance will be higher in the candidate arm.** *Confidence: 60%.*
Mechanism: body sizes span 1.9 kB to 96 kB while the projection is uniformly ≤4 kB. Practical
consequence: **read paired per-probe deltas.** A mean can hide the body winning big on 3 documents and
losing on 8 — and if it correlates with document size, that is itself the finding (a length threshold,
not a yes/no).

---

## 5. Pre-committed interpretation

| Outcome on class-A micro recall | Reading | Action |
|---|---|---|
| Delta < threshold, precision flat | The distillation already carries what stage-2 needs at this corpus scale | **Keep production as-is.** Redirect to Q2 — key quality is then the whole game |
| Delta ≥ threshold | The body adds what the projection structurally cannot (proportion) | **Adopt `keys+summary+document`.** Size the byte policy; decide the proof obligation (§6 of the synthesis) |
| Delta materially negative | Presentation defect, not a representation finding | Fix presentation, re-run before concluding |
| Delta correlates with document size | Not a yes/no — a **length threshold** | Adopt conditionally: body included below the crossover, projection alone above |
| Any escaped foreign identity | Contract violation; overrides every quality reading | Stop. That is the one non-diagnostic gate (`escaped_foreign_identity_rate_max: 0`) |

---

## 6. Cost

- **2 arms × 23 probes = 46 stage-2 calls.** Under D3 every fat call is a thin→fat call, so the naive
  run is **~92 calls**.
- **Halvable to ~46.** The experiment measures stage-2 only, and at eligible-space 51 ≤ M the
  controller enforces retain-all *regardless of thin's response* (`spec:123`), so thin cannot affect
  the stage-2 input. Bypassing it in the harness changes nothing measured; it forgoes only the
  thin/fat concordance metric.

Joseph fires this.

---

## 7. Correction carried in from the walkthrough — stage-1 *is* measurable

I told Joseph stage-1's representation question is unmeasurable today because retain-all masks it.
**Half right.** It is masked at *production* M — but the truth artifact ships a purpose-built protocol:
`stage_1_reduced_m_recall_min`, with `stage_1_hard_points: {value_investing_51: [10, 20],
whole_graph_163: [20, 40]}` and `stage_1_watched_points: {whole_graph_163: [5]}`.

So stage-1 recall is measurable **today** by reducing M to 10/20 over the 51-entity space. Two
consequences: it is answerable as a **separate run**, not deferred to N>100; and it must **not** be
folded into the stage-2 arms, where reducing M is exactly the confound codex warned about.
