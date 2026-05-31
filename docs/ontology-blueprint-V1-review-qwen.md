# Ontology Blueprint V1 — Qwen Review

## Summary

The blueprint is architecturally sound and the evidence from run-3 is compelling. The three decisions are well-framed and the assistant's leans (D1→A, D2→C, D3→C) are correct. **D1-A** is the clear winner given the empirical evidence (29/29 sources classified vs 16% page coverage). **D2-C** is the right pragmatic split — prove claim extraction before building belief revision on a hypothetical substrate. **D3-C** honors coordinate-not-gate, though I lean toward **variant D** (gate T2, open T3) as the sharper implementation. My one load-bearing concern: the Claim schema's 16-field extraction from personal notes is the make-or-break for D2; if the LLM can't reliably populate it, the layer degrades to noise.

---

## D1 — Domain model

**Pick: A** (derive from `Source.domain` + `SUPPORTS`) · **Confidence: high**

**Reasoning:**

The evidence is decisive. Pass-1 classification is reliable and complete (29/29 sources, 11 domains, including the 9-source `value-investing` cluster). Pass-2 page-level domain is broken (16% coverage, 4 domains, `value-investing` never emitted). Option A is:

- **Deterministic** — no LLM cost, fully recomputable from authority
- **Backfillable** — run-3 can be validated before run-4 with zero additional extraction
- **Correct semantics** — an entity *belongs to* the domains of the sources that evidence it. This is not a bug; it's the right model for a coordinate system. A value-investing source mentioning an AI tool *should* confer `value-investing` on that entity unless an ai-ml source also supports it (and then it gets both).
- **B-aligned** — a coordinate computed from structure, not a gate imposed by judgment

Option B re-introduces the LLM at entity level, which just failed. Option C (query-time only) breaks the viewer, domain analytics, and D3's per-compile reads. A is the clear choice.

**What we missed:**

The inheritance model is correct, but the blueprint should explicitly state the **multi-domain semantics**: an entity with sources from multiple domains gets multiple `BELONGS_TO` edges. This is implied but not foregrounded. At scale, entities will accumulate domains as more sources are ingested — this is a feature (the coordinate system gets richer), not a problem.

**Sub-questions:**

1. **`via_source` on BELONGS_TO?** Yes, record it. The cost is trivial (an array attribute or a count), and the value is high: answers "why is this entity in value-investing?" for user inspection, and feeds D3's domain-weighting logic (you can weight by number of conferring sources). Provenance by joining through `SUPPORTS` works, but materializing it on the edge is cheap and ergonomic.

2. **`sub_domain` retirement?** Retire it. Pass-1 emits one domain per source, no sub-domain. There's no data source to populate it, and keeping it invites confusion about what it means. If a future Pass-1 or entity-level classifier emits sub-domains, reintroduce it then — not before.

---

## D2 — Claim layer

**Pick: C** (wire Claim + EVIDENCES + ABOUT now; defer SUPERSEDES/CONTRADICTS/QUALIFIES) · **Confidence: medium-high**

**Reasoning:**

The split is pragmatic and correct. The five-rung ladder distinguishes **Relate** (traverse typed edges) from **Learn** (belief revision over time). Option C honors this: land the typed assertion layer first (Relate-as-reasoning), prove extraction works at personal scale, *then* build belief revision (Learn) on a working substrate.

The division of labor with `LINKS_TO` is coherent:
- `LINKS_TO` = cheap, untyped **associative adjacency** (the wiki graph; fuels PPR recall and proximity traversal — *Relate-by-association*)
- `Claim` = typed, grounded, polarized **assertion** (*Relate-by-reasoning* + Learn substrate)

Adding Claims is not bolting a parallel structure onto the generic-edge problem. It adds the reasoning layer the generic layer structurally cannot provide, while `LINKS_TO` keeps doing the cheap-traversal job it's good at. The two coexist with distinct jobs.

**What we missed — the empirical heart of D2:**

The make-or-break is **prompt design for claim extraction from personal notes**. The 16-field Claim schema is heavy:

```
claim_id, claim_family_id, subject_slug, predicate_class_canonical,
predicate_class_raw, predicate_scope_slugs[], object_slugs[], polarity,
modality, condition_text, assertion_text, confidence, confidence_spread,
state, version, created_at, last_revised_at
```

Personal notes are not structured claims. They're messy markdown — half-formed ideas, tangents, quotes, personal reflections. The LLM must extract:
- A canonical subject (which entity?)
- A typed predicate (from the controlled vocabulary: `supplies`, `competes_with`, `is_bottleneck_for`, etc.)
- Object entities
- Polarity (positive/negative/neutral)
- Modality (factual/hypothetical/normative)
- Condition text (when does this hold?)
- Assertion text (natural-language summary)

This is hard. At ~30 sources, the yield may be modest. The risk is noisy, low-yield extraction — the LLM hallucinates claims, misidentifies subjects, or emits vague predicates (`relates_to` — the very degeneration ¶419 warns against).

**Personal-scale value of claim extraction:**

At 30 sources, 180 entities, I expect:
- **Modest yield** — maybe 50-150 claims across the corpus (rough guess: 2-5 claims per source that discusses relationships)
- **High variance** — value-investing sources (structured arguments about moats, margins, management) will yield rich claims; dev logs and personal notes will yield few
- **Infrastructure value > immediate query value** — the point is not "what does this source assert about Buffett?" on day one, but building the substrate for Learn (belief revision) and Discover (contradiction detection) over time

The honest question: is the Pass-2 prompt expansion worth the complexity if the immediate yield is modest? **Yes, because:**
1. The schema is already defined (v2.2) — the cost is prompt engineering, not schema design
2. You need the substrate before you can build Learn on it — Round 6's belief revision (#83/#84) requires Claims to exist
3. The extraction quality will improve as the prompt is tuned — you can't tune what you haven't built

**Claim↔LINKS_TO division of labor:**

Coherent. `LINKS_TO` is the cheap wiki graph; `Claim` is the typed assertion layer. They serve different purposes. The only risk is if claim extraction proves so low-yield that the Claim layer is sparse (say, 50 claims across 180 entities) — then the reasoning layer is thin, and `LINKS_TO` remains the dominant structure. But that's an empirical outcome, not an architectural flaw.

**Recommendation:** wire Claim + EVIDENCES + ABOUT now (C), but **invest heavily in prompt engineering and extraction-quality tests** before run-4. Define pass criteria: what fraction of sources should yield at least one claim? What's the minimum predicate-class diversity? If extraction proves noisy, you can defer the full layer — but you need the data to make that call.

---

## D3 — T2/T3 domain-scoping

**Pick: C** (domain as ranking/budget coordinate) with **strong preference for variant D** (gate T2 seeds, open T3 neighbors) · **Confidence: medium**

**Reasoning:**

The tension is real: a hard domain gate (A) sharpens **Relate** precision but suppresses **Discover** (Swanson-style cross-domain links). No scoping (B) preserves Discover but floods context at scale. Option C (soft weighting) is the right stance — domain shapes order and share, not membership.

But the implementation matters. **Variant D** (gate T2, open T3) is sharper than pure C:

- **T2 (seed entities):** gate to same-domain. These are the entities the LLM uses to *anchor* its understanding of the source's context. If the source is about value-investing, the seeds should be value-investing entities. Cross-domain seeds introduce noise at the anchor layer.
- **T3 (1-hop neighbors):** leave open. This is where Discover happens. A value-investing seed (Buffett) has a neighbor (psychology: behavioral bias) — that cross-domain link is exactly what the graph should surface. Gating T3 suppresses the very links that make Discover valuable.

Variant D is a **hybrid**: precision on anchors, discovery on expansion. It honors coordinate-not-gate (the T3 expansion is open), while sharpening the T2 anchor layer where precision matters most.

**What we missed:**

The weighting policy. If soft (pure C), how aggressive should same-domain weighting be? 2x? 5x? 10x? This is empirical and corpus-dependent. The blueprint should state the **stance** (gate vs coordinate) but leave the **algorithm** (weighting factor, budget split) to the consumer sub-project, where it can be tuned against real data.

If variant D, the question is simpler: gate T2 to same-domain (binary), leave T3 open (no weighting needed). This is easier to implement and reason about.

**Sub-questions:**

1. **Weighting aggressiveness (if C):** I'd start with 3-5x same-domain weighting in the context budget, then tune based on observed cross-domain link quality. But I prefer variant D's binary gate on T2.

2. **Gate-seeds-open-neighbors (variant D)?** Yes. T2 seeds anchor the compile; T3 neighbors expand for discovery. Gating T2 sharpens precision where it matters; opening T3 preserves the cross-domain links that make Discover valuable.

**Recommendation:** go with **variant D** — gate T2 seeds to same-domain, leave T3 neighbor-expansion open. This is the sharpest implementation of the coordinate-not-gate stance.

---

## Cross-cutting (inventory + frame)

**Node inventory (§3):** correct. Each node has a clear rationale and objective. No missing elements.

**Edge inventory (§4):** correct. The Claim edges (EVIDENCES, ABOUT, SUPERSEDES, CONTRADICTS, QUALIFIES) are all justified by Learn (belief revision). The generic edges (LINKS_TO, SUPPORTS, ALIAS_OF, BELONGS_TO) are all kept for good reasons.

**Frame violations:** none that I can see. The three decisions all honor:
- Philosophy B (broad ingestion, LLM extraction, query-time partitioning)
- The five-rung ladder (Remember → Relate → Learn → Discover → Create)
- Coordinate-not-gate (C2)

**One load-bearing concern:**

The Claim schema's 16-field extraction from personal notes is the make-or-break for D2. The blueprint acknowledges this implicitly (the empirical question in §6), but I'd make it explicit: **run-4's success criterion should include claim-extraction quality metrics** (yield, predicate diversity, subject/object accuracy). If extraction proves noisy, you can defer the full Claim layer — but you need the data to make that call, not a priori judgment.

**One minor concern:**

The blueprint mentions "the broken Pass-2 page-`domain` is dropped regardless of D1's outcome" (§8). This is correct, but the implementation path should be explicit: does Pass-2 stop emitting `domain` entirely, or does it emit but the graph_sync ignores it? I'd recommend **Pass-2 stops emitting** — remove it from the prompt, don't just ignore the output. Cleaner, less confusing.

---

## Convergence note

I expect the other reviewers to:

- **Agree on D1-A** — the evidence is overwhelming. High convergence likely.
- **Split on D2** — some may lean B (defer entirely) if they're skeptical of claim extraction at personal scale. The empirical question (does extraction deliver enough value?) is the load-bearing judgment call. I expect Codex/GPT and Gemini to lean C (wire now), DeepSeek to be cautious (maybe B), Grok to lean A (full layer). My medium-high confidence on C is a pragmatic middle.
- **Vary on D3** — some may prefer A (hard gate) for simplicity, others C (soft weighting). Variant D (gate T2, open T3) is a hybrid that may or may not be on other reviewers' radar. I expect moderate divergence here.

The synthesis should weight **D2's empirical question** heavily — that's where independent judgment matters most. D1-A is near-certain; D3 is a stance call with implementation flexibility.
