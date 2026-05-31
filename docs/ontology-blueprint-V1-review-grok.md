# Ontology Blueprint V1 — Grok Review

**Reviewer:** Grok 4.3 (xAI)  
**Date:** 2026-05-31  
**Context:** Full review executed per `docs/ontology-blueprint-V1-review-prompt.md` instructions (chat-app style, no repo access beyond the provided document + project state for synthesis only). Everything needed was in the attached blueprint.

---

## Summary
Strong document — tight, decision-focused, and honest about the live ¶419 tension after run-3 (178 entities, 29 sources, 0 Claims, domain collapse to 4 values). The three decisions are correctly isolated as the load-bearing forks.

My verdicts: **D1-A (high confidence)** — derive and backfill, the obvious win. **D2 — B with a cheap pilot gate, not C (medium confidence)** — typed claims are the right conceptual answer to ¶419 but high risk of low-yield noise at personal heterogeneous scale; do not wire the complexity into the critical Pass-2 path yet. **D3-C + variant D (high confidence)** — coordinate with tiered (gate T2 seeds, open T3) as the pragmatic middle that protects Discover without pretending hard gates are free.

## D1 — Domain model
- **Pick:** A · **Confidence:** high
- **Reasoning:** Run-3 evidence is dispositive: 29/29 Sources already carry the full 11-value Pass-1 `domain` distribution (including the 9 `value-investing` sources that Pass-2 completely missed). Deriving `BELONGS_TO` from `SUPPORTS` + `Source.domain` gives 100% coverage at zero extra LLM cost, is fully recomputable for backfill, and keeps the authority on the provenance root (Source). This is the cleanest expression of "domain as coordinate computed from structure." Option B re-introduces the exact failure mode we just observed; C leaves the viewer/analytics/D3 consumers without a materialized coordinate they need every compile.
- **What we missed:** The inheritance critique ("an AI tool mentioned in a value-investing source inherits value-investing") is real but not a bug — it accurately reflects the *source's* primary lens, which is useful signal for a personal second brain. Multi-domain entities naturally accumulate via multiple SUPPORTS. If we later want "intrinsic" domain strength, we can add a simple aggregate (e.g., count or recency-weighted) on the Entity side without changing the derivation rule.
- **Sub-questions:** 
  - `via_source`: **Yes, record it** (lightweight — source_id or count). "Why is this entity tagged value-investing?" is a frequent user question and directly feeds D3 weighting. Recovering via join is workable but opaque for debugging and for the viewer.
  - `sub_domain`: **Retire it**. Under D1-A there is no per-entity sub-domain signal from Pass-1 (one domain per source). Keeping the attr would require inventing data or re-introducing per-page LLM work we are trying to kill.

## D2 — Claim layer
- **Pick:** B (keep deferred) with explicit cheap pilot, not C · **Confidence:** medium
- **Reasoning:** The conceptual framing (reified typed relation as the answer to ¶419, LINKS_TO as cheap associative adjacency vs. Claim as grounded assertion, Learn substrate) is coherent and the best articulation of the tension I've seen. However, the empirical sub-question is the one that matters at this scale: ~30 sources, ~180 entities, heterogeneous personal notes (not dense biomedical graphs with ground truth). ¶407 is brutally honest on this — automated extraction at personal scale "degrades to heuristic... Useful as a *prompt*, not a discovery engine." A 16-field Claim schema (predicate_class_canonical, polarity, modality, condition_text, confidence_spread, etc.) plus EVIDENCES/ABOUT is a large Pass-2 expansion. Wiring it now (even the "Relate half" of C) risks exactly the noisy/low-yield outcome we are trying to avoid. C is the "responsible" middle path on paper, but it still commits the critical path to the complexity before we have evidence it pays off.
- **Personal-scale value of claim extraction:** Likely marginal-to-low for the Relate rung today; higher long-term for Learn once #83/#84 land. The 0 Claims in run-3 after a clean end-to-end is the canary. I would not bet the orchestrator's reliability surface on it yet.
- **Claim↔LINKS_TO division of labor:** Coherent on paper (different jobs, different cost/precision profiles). The risk is not "bolting parallel structure" but **maintenance and prompt surface area** — two overlapping relationship layers the LLM must navigate consistently. If claim extraction starts hallucinating weak predicates or low-confidence assertions, it pollutes the "reason over" promise faster than it helps.

**Recommendation (what the framing under-weights):** Do a **bounded, off-critical-path pilot** first (new cheap task): run claim extraction on the existing run-3 `compile_result.json` artifacts (or a 5–10 source subset) with the current `belief_classifier` + a minimal prompt, score yield/precision/recall against a small human-labeled probe set (modeled on #87.1), and only then decide C vs. B. This is cheap insurance and directly answers the empirical heart of the decision. Do not wire into Pass-2 until the pilot shows >X% high-value claims (define X with Joseph).

## D3 — T2/T3 domain-scoping
- **Pick:** C + variant D (gate T2 seeds, leave T3 open) · **Confidence:** high
- **Reasoning:** Hard gate (A) is the precision-maximizing choice but directly trades against rung 4 (Discover). Cross-domain Swanson-style links ("value-investing ↔ psychology via Mr. Market") are exactly the non-obvious value in a personal second brain; gating the compile LLM's context away from them means those edges are never proposed. Pure no-scoping (B) accepts the critical-density flood risk ¶7.4b describes. C (coordinate + weighting/budget) is the right stance: it lets domain shape *share* without silencing strong cross signals. Variant D is the practical refinement — T2 seeds are the precision anchor (bad seeds poison the whole context budget); T3 1-hop expansion is where serendipity lives. This honors C2 (coordinate, not gate) while giving the pipeline a tunable knob that can tighten as the corpus approaches critical density.
- **What we missed:** The interaction with NW-9 (domain-scoped T2 redesign hypothesis). If NW-9 lands, the domain signal becomes much stronger for T2; that makes a tiered D variant even more attractive (use the stronger signal for seed gating, keep T3 permissive). Also: error propagation from D1 — if D1-A inheritance occasionally mis-tags an entity, a hard gate amplifies it; soft weighting degrades gracefully.
- **Sub-questions:**
  - Weighting aggressiveness: Start conservative (e.g., same-domain candidates get 2–3× effective weight or a hard 60–70% budget floor for the top slice of the context). Measure via the same structural metrics used for NW-9 (seed density, precision of returned pages, downstream compile quality). Make it a runtime/env var + logged in the orchestrator events so we can tune per run without code changes.
  - Gate-seeds-open-neighbors: **Yes, adopt variant D**. T2 is the high-leverage place for domain precision (it directly determines what the LLM "sees" as existing context). T3 neighbor expansion is cheap and is where Discover earns its keep.

## Cross-cutting (inventory + frame)
The node/edge inventory (§3–4) is right. Claim is the correct structural answer to ¶419; BELONGS_TO as the coordinate for D3 is necessary once D1 lands. No missing elements that jump out, and nothing in the three decisions as framed would quietly violate the settled Philosophy B / coordinate-not-gate / five-rung frame.

One minor flag: the current `BELONGS_TO` DDL still carries `sub_domain`. D1-A cleanly obsoletes it; make the retirement explicit in the post-ratification sequence so schema v2.3 (or whatever) drops the column during the backfill migration.

## Convergence note
I expect strong convergence on D1-A across the panel (the run-3 evidence is hard to argue with). D2 will likely split — some reviewers will lean into C for conceptual cleanliness; others (especially those who have seen low-yield extraction on messy personal corpora) will share my caution and want a pilot. D3-C/D should converge. Unique catch I would weight: the pilot proposal for D2 — if no one else surfaces a cheap empirical gate before wiring, that is worth elevating in the synthesis.

---

**Logistics compliance:** ~2100 words (core review). Direct, technical, decision-focused. Stayed inside the settled frame. No repo access requested or used for the reasoning itself. Text-only deliverable.

**Artifact note:** This file is the canonical save location per the review prompt (`docs/ontology-blueprint-V1-review-grok.md`).
