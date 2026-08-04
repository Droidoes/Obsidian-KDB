# Task #125 — Formal response: keep the stage, re-derive the interface

Date: 2026-07-26 · Task: **#125** · Status: **position paper for deliberation — nothing here is ratified**

Responds to: `2026-07-26-task125-two-pass-boundary-question.md` (the problem statement), section by
section. Where the two documents disagree, this one is the opinionated party; the problem statement
remains the neutral panel brief.

---

## 0. Position, stated first

**The pass boundary is sound; the interface crossing it is stale.** The question doc's own §5
already showed the merged alternative eliminates no call (`domain` circularity) and §6 showed it
spends the entire envelope margin at the *median* real source. What survives of Q1 is a narrower,
measurable question: **how much selection-relevant signal does the ≤4 kB projection lose relative
to the full body — and is the cheapest fix a better prompt (Q2), a bigger projection budget, or
moving the computation (the merge)?** Those three fixes are totally ordered by cost and disruption,
so the rational procedure is not a one-shot pick but an **escalation ladder walked on evidence**:
run the §6.1 experiment, and only climb a rung when measurement says the rung below is
insufficient.

Concretely recommended, in order:

1. **Run §6.1 round 1** (current projection vs. full body, paired, same session) under the
   predeclared decision rule in §3 below. Joseph fires it.
2. **Do the Q2/Q2b prompt review regardless of outcome** — it pays under every branch (§4).
3. **Panel only if the ladder reaches the merge rung.** If round 1 shows no material gap, there is
   no fork left to panel.

---

## 1. Does the metadata stage earn its keep? Yes — but on new grounds, not inherited ones

Full concession to the question doc's §1: the split's *original* justification is gone. Pass-1's
key field was built for a PK-lookup consumer (D-89-20) that #123 retires, and §2.1 established
there is no write-side justification either. If the stage stands, it must re-earn its keep from
scratch. It does, three times over — and none of the three depends on the retired consumer.

### 1.1 The merged call is the one call the envelope cannot hold

Pass-1 is **source-complete and graph-blind** (`{{ source_text }}` in full, no candidates).
The selector is **graph-aware and source-projected** (~257 kB of evidence, ≤4 kB of query).
A merged selection call must be *both* — graph-aware **and** source-complete — and that is
precisely the call the arithmetic rejects: median real source 34,029 B against ~37 kB spare
consumes the entire margin, and a third of probe sources plus every `benchmark/sources/` file
break the 320k static guarantee outright (question doc §6).

So the two-pass design is best understood as a **factorization**: one infeasible
(graph-aware × source-complete) call split into two feasible ones, with the projection as the
compression interface between them. The §3 jab — *"read in full, discarded, judged from a ≤4 kB
summary"* — describes not an artifact but the compression any within-envelope design must perform
*somewhere*. The only real choices are where the compression happens and how good it is.

One reframe matters for the experiment: the projection is **not a truncation**. It is a
full-attention compression — the model that wrote `summary`/`key_themes`/`entity_search_keys` had
all 34 kB in front of it. The body's information already reaches the selector, via distillation.
What the experiment measures is the *loss of that distillation* — with the caveat (§3 below) that
today's distillation was optimized for the old consumers, so measured loss indicts the current
prompt before it indicts the boundary.

### 1.2 The boundary is the intrinsic/relational line, already ratified as data model

Every Pass-1 output is **intrinsic to the source** and is frontmatter-embedded (question doc §2).
T2 selection is **relational** — a function of *(source, graph state at this moment)*. The ratified
frontmatter principle says exactly this line: intrinsic → frontmatter; relational/dynamic → GraphDB
(`docs/archive/tasks/task89-deliberation-wikilinks-frontmatter.md:135`, sectionalized as D-89-16).
The pass boundary is that data-model line expressed in call structure. A merged call would emit one
envelope straddling it — half destined for frontmatter, half categorically barred from it. The
split is therefore not an accident of how the passes grew; it is the call-level image of a decision
Joseph already made about the data.

### 1.3 Cadence asymmetry — Joseph's own Call-3 argument, applied one level up

Enrichment is **compute-once**: intrinsic fields cannot change unless the source does. Selection is
**compute-per-graph-state**: the Call-3 decision (stage 1 always runs) was taken precisely because
the graph will grow past M and results must track it — Joseph's reason [1], 2026-07-26. The
question doc's §5 cost 4 already noted the coupling; the price deserves stating: merged, every
re-selection against a grown graph re-pays a median 34 kB of body tokens to recompute fields that
cannot have changed. Post-development, re-selection is the *normal* case, so the merged design pays
its worst-case cost at steady state.

**Distinction this yields — the position in one line:** the *stage* earns its keep (three standing
grounds above); the *field* does not automatically. `entity_search_keys`' contract was written for
"imperfect slugs simply miss, no harm" (`pass1_schema.py:79-84`) and is consumed by something with
opposite failure semantics. Keep the stage; re-derive the field's contract (§4).

---

## 2. The answer space, priced

Three genuinely distinct responses to Q1, ordered by cost and disruption — they form a ladder, not
a menu:

| | Option | What changes | Cost | Reversibility |
|---|---|---|---|---|
| **A** | Keep boundary, keep ≤4 kB interface; fix quality in the prompt | `pass1_prompt.j2` only (Q2/Q2b) | Prompt-review effort; zero bytes, zero contract change | Total |
| **B** | Keep boundary, **widen** the interface | Query cap 4,096 B → up to ~16–20 kB carved from the ~37 kB spare; §7.0a re-derived; projection content redesigned (richer distillation and/or salient excerpts) | Spare-envelope bytes; one spec/blueprint amendment; test_budget re-derivation | High — a constant and a template |
| **C** | Move selection into a body-carrying call (the honest merge: classifier call **+** body-carrying selector) | Two-call staging in spec §5.1, the adapter boundary, parts of the 13-terminal matrix; D1–D9 re-ratification | See exchange rate below, plus failure coupling (§5 cost 1) and cadence coupling (§1.3) | Low — restructures ratified P1 work |

**C's exchange rate, made concrete.** Evidence is budgeted at 2,500 B per hydrated candidate
(blueprint §7.0a). Carrying the body instead of the projection therefore costs, in candidates:
median source 34,029 B ≈ **14 candidates**; max probe source 96,311 B ≈ **39 candidates** — up to
two-fifths of M=100. That is the real trade: **query fidelity purchased with candidate coverage**,
i.e. spending recall ceiling to buy precision input. At today's largest domain (51 eligible) it
would not bite; at the N > M steady state Joseph designed Call-3 around, it bites exactly when it
matters. On sunk work (§5 cost 5): sunk cost is not an argument, but *forward rework* is — C
re-opens ratified decisions and a green 2,498-test P1, a real price payable only for a benefit A
and B measurably cannot deliver.

**Why a ladder, not a menu.** A ⊂ B ⊂ C in disruption, and each rung's fix is a superset of the
previous rung's. So the cheapest sufficient rung wins, and sufficiency is measurable per rung —
which is what the experiment is for.

---

## 3. The predeclared decision rule (set before any data is seen)

Per the #87 discipline (criteria before probes) and the data-before-principle rule, the rule is
declared here, before round 1 fires. Joseph may amend it — but before firing, not after reading
results.

**Design.** Paired arms, same session (per the apples-to-apples rule), on the 25 source-resolvable
probes, scored on the normative precision@5 and recall (spec §8.3 metric 3):

- **Arm P** — projection, current Pass-1 output, as-is (the baseline; also prices Q2's headroom).
- **Arm F** — full body substituted for the projection. Experiment-only envelope relaxation (or a
  reduced-M variant) — this arm is a measurement instrument, not a production candidate.
- **Arm P−k** *(optional, cheap)* — projection **without** `entity_search_keys`. This is the
  consumer-purpose test applied to the field itself: it prices what the keys contribute now that
  their original consumer is retired. If P−k ≈ P, Q2 is redesigning a field that earns nothing.

**Rule.**

1. **F − P not material** → the current 4 kB compression already suffices. **A** is ratified;
   #25 unblocks with §7.0a intact; Q2 proceeds as hygiene, not rescue. *No panel — no fork left.*
2. **F − P material** → do the Q2 prompt revision, re-run the pair (P′ vs F, same session).
   - **F − P′ closed** → **A** (prompt was the culprit, boundary vindicated).
   - **Gap remains** → widen the projection within spare (**B**), re-run once more.
3. **Gap survives B at its widest affordable budget** → only now is **C**'s exchange rate a live
   fork → **external panel**, with the question doc as brief and this document as the position to
   attack.

**Materiality, proposed:** aggregate delta ≥ **0.10** on either normative metric, corroborated by
the paired per-probe view (F must win the pairs, not one outlier probe). Proposed, not sacred —
but fixed before firing.

**What the experiment cannot decide, stated honestly:** it prices signal loss only. The §1.2
intrinsic/relational argument and the §1.3 cadence argument stand or fall on architecture, not
data; even a large F − P gap argues for climbing to B, and only past B does it argue against the
boundary itself.

---

## 4. Q2 / Q2b — unconditional under every branch

The field's contract must be re-derived for its new consumer regardless of where the ladder stops
(even C renders keys — relocated, not removed). Review scope for `pass1_prompt.j2:68-80`:

1. **Failure semantics flipped.** The instructions were written under "imperfect slugs simply miss,
   no harm." As selector query expressions, a bad key is now a *false query* the model is asked to
   match on and abstention is scored against. The prompt must be rewritten for the consumer that
   punishes wrong keys, not the one that ignored them.
2. **Form question.** Canonical-slug guessing was correct for a PK lookup. Whether hyphenated
   slug-form is the right *query expression* form for an LLM selector is genuinely open — to be
   resolved in the prompt review, **within** the graph-blind constraint: no graph vocabulary, no
   candidate hints in Pass-1 (D-NW4-5 / no-hints principle). The field stays a pure function of the
   source under every option.
3. **Template compliance.** Definition + illustrative-only examples, per the ratified prompt
   template; examples ground form, never relationships.
4. **Q2b (`author`).** Replace the prose *"null otherwise"* (`pass1_prompt.j2:60-61`) with an
   explicit "emit JSON `null`, never the string `\"null\"`" instruction. The projector-side
   normalization already decided (task #30) stays as the coerce-don't-reject backstop; this is the
   upstream fix.

Sequencing note: item 1's revision is exactly the P′ of §3 rule 2 — so if round 1 shows a material
gap, the Q2 work is not parallel hygiene but the next measured rung.

---

## 5. Sequencing and ledger effects

1. Prepare the §6.1 harness delta (alternate query-block builder + experiment-only envelope flag;
   to be sized before asking Joseph to fire — expected small, since only the query side changes and
   the fixture's evidence pool is untouched per question doc §6.1).
2. Joseph fires round 1 (arms P, F, optionally P−k). Decision by §3's rule.
3. **#25 stays held** until the ladder's stopping rung is known — A leaves §7.0a intact, B rewrites
   it, so the byte-table re-derivation waits (unchanged from the question doc §8).
4. **#123 P2 selector implementation is not blocked** (unchanged).
5. Q2/Q2b prompt revision lands with the #25 amendment batch — both touch prompt/spec text; one
   re-derivation, one review cycle.
6. External panel convenes only on §3 rule 3, with the question doc + this response as the packet.

## 6. What this response does not claim

- **Not** that the original justification for the split survives. It doesn't; §1 rebuilds the case
  on grounds independent of the retired consumer, which is what "re-justify rather than inherit"
  demanded.
- **Not** that C is impossible. It is *priced* — ~14 candidates at the median, ~39 at the max, plus
  failure and cadence coupling and forward rework — and dominated unless measurements exhaust A
  and B first.
- **Not** that the current projection is good. §1.1's own caveat: it was distilled for retired
  consumers. The boundary being sound and the interface being stale are compatible claims — they
  are the position.
