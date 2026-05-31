# Ontology Blueprint V1 — External Panel Review Prompt

**Purpose:** Fire `docs/ontology-blueprint-V1.md` at the external panel for
independent takes on its three open decisions (D1 domain model · D2 Claim layer ·
D3 T2/T3 domain-scoping). This is a **foundational, full-panel** review (the doc
becomes one of the project's two foundational documents) — not a fast-pass.

**Dispatch mode:** **chat apps, not CLIs.** Each reviewer is the chat interface
of its model (no repo access). Paste the **Prompt body** below, then attach or
paste the full contents of `docs/ontology-blueprint-V1.md` (it is self-contained
— schema DDL and source excerpts are inlined in its appendices).

**Suggested panel (full, 5):** Codex/GPT (chat) · DeepSeek (chat) · Qwen (chat) ·
Gemini (3.1 Pro / Deep Research, chat) · Grok (chat). Per
`docs/external-review-panel.md` this fork is #88/#89-scale → full panel.

**Save each reply to its own file** (for synthesis + convergence tally):
- `docs/ontology-blueprint-V1-review-codex.md`
- `docs/ontology-blueprint-V1-review-deepseek.md`
- `docs/ontology-blueprint-V1-review-qwen.md`
- `docs/ontology-blueprint-V1-review-gemini.md`
- `docs/ontology-blueprint-V1-review-grok.md`

---

## ─── Prompt body (paste to each chat app; attach `ontology-blueprint-V1.md`) ───

You are one of several **independent** reviewers on a multi-model panel. The
document attached (`ontology-blueprint-V1.md`) is the **meaning layer** of a
personal knowledge-graph system (KDB): it defines what each node and edge in the
graph *means* and surfaces three open architectural decisions. We want your
honest, independent judgment on those three decisions — reviewers do not see each
other's takes; convergence across independent reviewers is the signal we synthesize.

### 0. Rules of engagement

- **You have no repo or filesystem access, and need none.** Everything required
  is in the attached document, including the current schema DDL (Appendix A) and
  the load-bearing excerpts from the project's foundational "why" doc
  (Appendix B). **Do not ask for repo access, file contents, or code.** This is a
  reasoning task; produce your review as text only.
- **The settled frame (§1 of the doc) is ground truth — do not re-open it.**
  Philosophy B (broad ingestion, LLM extraction, query-time partitioning), the
  five-rung objective ladder (Remember → Relate → Learn → Discover → Create), and
  "domain = coordinate, not gate" are decided. Reason *within* them. You may flag
  if you believe a proposed *decision* violates the frame — but do not argue the
  frame itself.
- **Challenge the assistant's leans.** Each decision states a lean (D1→A, D2→C,
  D3→C). Agree or disagree, but show your reasoning; don't rubber-stamp.

### 1. Context (brief)

KDB compiles raw markdown (a personal Obsidian vault — value investing, AI/ML,
health, history, geopolitics, etc.) into a Kuzu knowledge graph. A first clean
end-to-end run produced 178 entities / 29 sources, but exposed two problems the
blueprint addresses: (1) domain labels are badly under-covered and collapse to 4
values; (2) the graph is 100% generic edges — traversable but not "reasoned
over." Read the attached doc §2 for the evidence, §3–4 for the node/edge
inventory, §5–7 for the three decisions.

### 2. What we want — the three decisions

For **each** decision, give us:

- **Your pick** — which option (A/B/C/D, or a new option you name).
- **Confidence** — high / medium / low.
- **Reasoning** — why, in terms of the five-rung objectives and the tradeoffs.
- **What we missed** — an option, consequence, or failure mode our framing
  under-weights.
- **The sub-question(s)** for that decision (listed below).

**D1 — Domain model** (doc §5). How should `Entity BELONGS_TO Domain` edges be
created? Lean: **A** (derive from `Source.domain` + `SUPPORTS`; drop the Pass-2
per-page LLM domain). Sub-questions: (1) should the derived edge record the
conferring source(s) (`via_source`), or recover provenance by joining through
`SUPPORTS`? (2) retire the `sub_domain` attribute, or keep it?

**D2 — Claim layer** (doc §6) — the deepest call. Wire the typed `Claim` layer
into the live pipeline, or keep it deferred? Lean: **C** (wire `Claim` +
`EVIDENCES` + `ABOUT` now for typed/grounded assertions → "reason"; defer the
belief-revision edges `SUPERSEDES`/`CONTRADICTS`/`QUALIFIES` to the gated #83/#84
arc). The empirical sub-question we most want your judgment on: *at personal
corpus scale (~30 sources, ~180 entities), does typed-claim extraction deliver
enough reasoning value to justify the Pass-2 complexity — or does it degrade to
noisy, low-yield assertions?* Also assess the Claim↔`LINKS_TO` division of labor
argued in §6: is it coherent, or does adding Claims just bolt a parallel
structure onto the generic-edge problem?

**D3 — T2/T3 domain-scoping** (doc §7). When building per-compile context, should
retrieval be scoped to the source's domain? Lean: **C** (domain as a
ranking/budget *coordinate*, not a hard gate). Central tradeoff: a hard gate
sharpens Relate precision but suppresses cross-domain **Discover** (Swanson-style
links are inherently cross-domain). Sub-questions: if soft, how aggressive should
same-domain weighting be? And: gate the T2 seeds but leave T3 neighbor-expansion
open (variant D), or treat both uniformly?

### 3. Cross-cutting check

Beyond the three decisions: is the **node/edge inventory** (§3–4) right? Any node
or edge whose stated *rationale* or *objective-served* is wrong, or any
missing/redundant element? Flag anything where a decision, as framed, would
quietly violate the settled frame.

### 4. Output format

```markdown
# Ontology Blueprint V1 — [Your model] Review

## Summary
[2-4 sentences: overall assessment + your one-line verdict per decision]

## D1 — Domain model
- Pick: [A/B/C/D/new] · Confidence: [high/med/low]
- Reasoning: ...
- What we missed: ...
- Sub-questions: [via_source?] [sub_domain?]

## D2 — Claim layer
- Pick / Confidence / Reasoning / What we missed
- Personal-scale value of claim extraction: [your judgment]
- Claim↔LINKS_TO division of labor: [coherent? / concern]

## D3 — T2/T3 domain-scoping
- Pick / Confidence / Reasoning / What we missed
- Sub-questions: [weighting aggressiveness] [gate-seeds-open-neighbors?]

## Cross-cutting (inventory + frame)
[Anything wrong/missing in §3–4; any frame violation]

## Convergence note
[If you suspect another reviewer will raise (or contest) any point, say so —
it helps the synthesizer weight load-bearing vs unique catches.]
```

### 5. Logistics

- **Length:** ~1500–3500 words. Depth over breadth; don't pad.
- **Tone:** direct, technical, honest. Don't underclaim a load-bearing concern to
  seem agreeable; don't inflate minor polish to look thorough.
- **Stay decision-focused:** the three decisions are the point. The inventory and
  frame checks are secondary.

---

**Reminder:** text-only review; no repo access needed or assumed; the attached
`ontology-blueprint-V1.md` is everything. Thank you for the review.
