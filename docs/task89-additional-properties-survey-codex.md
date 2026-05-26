# Additional Properties Survey — Codex

## Summary

I propose five additions. Two are high-value source-level classification axes (`knowledge_intent`, `evidence_basis`), two are strong optional navigation / Pass-2 aids (`temporal_frame`, `abstraction_level`), and one is a stretch field that may be worth testing in NW-5 (`central_question`).

## Proposals

## knowledge_intent

**Type:** enum string (`explain`, `argue`, `instruct`, `evaluate`, `report`, `reflect`, `reference`, `mixed`, `unclear`)
**Required / Optional:** Required
**One-line purpose:** Captures what the source is trying to do intellectually, independent of its file/source form.
**Why the LLM is the right tool:** `source_type` can say "article" or "transcript", but it cannot reliably distinguish explanation, argument, practical instruction, analysis, or reference material. That distinction is semantic and rhetorical, not structural.
**Downstream consumer:** Pass-2 can calibrate worth-verdict expectations; compile can tune extraction posture; query layer and Obsidian UX can filter for "instructional" versus "argumentative" sources within the same domain.
**Cost concern:** Low. This is a compact enum that the LLM can infer while already reading for `summary`, `kdb_signal`, and `domain`.
**Tier (your call):** ★★★ (must)

## evidence_basis

**Type:** list of enum strings (`data`, `primary-source`, `expert-analysis`, `first-hand-experience`, `case-study`, `theoretical-argument`, `literary-text`, `speculation`, `mixed`, `unclear`)
**Required / Optional:** Required, with `unclear` allowed
**One-line purpose:** Records what kind of support the source relies on for its claims or exposition.
**Why the LLM is the right tool:** Evidence basis usually depends on reading the source's argumentative texture: whether it cites data, narrates experience, reasons from theory, analyzes primary documents, or speculates. Regex over citations or numbers would be brittle and would miss implicit support.
**Downstream consumer:** Pass-2 can treat speculative material differently from data-backed or primary-source material; human queries can ask for "data-backed investing notes" or "first-hand experience sources"; NW-5 can spot models that over-credit thin material.
**Cost concern:** Moderate but bounded. A short enum list adds some judgment load, but it should not compete directly with entity/theme extraction because it is a source-level classification.
**Tier (your call):** ★★★ (must)

## temporal_frame

**Type:** object

```yaml
temporal_frame:
  class: evergreen | current | historical | forward-looking | mixed | unclear
  stated_period: <string or null>
```

**Required / Optional:** Optional in v0.2; required only if NW-5 shows reliable extraction
**One-line purpose:** Identifies whether the source is evergreen, time-bound/current, historical, forward-looking, or mixed, plus any explicitly stated period.
**Why the LLM is the right tool:** The dropped `time_period` field was too broad, but a tighter temporal durability field is useful and hard to derive mechanically. A source can mention many dates while being evergreen, or mention no dates while being about current market conditions.
**Downstream consumer:** Pass-2 can discount stale current-events material; query layer can filter historical versus current market/geopolitical sources; human UX can surface sources likely to need later review.
**Cost concern:** Moderate. The `class` is cheap; `stated_period` risks over-extraction if the prompt asks for too much date detail. Keep it to explicit periods only, not inferred chronology.
**Tier (your call):** ★★ (strong)

## abstraction_level

**Type:** enum string (`concrete-case`, `applied-method`, `general-principle`, `theory-foundation`, `meta-methodology`, `mixed`, `unclear`)
**Required / Optional:** Optional
**One-line purpose:** Classifies the source's level of generality: specific case, applied method, broad principle, foundation, or method-about-method.
**Why the LLM is the right tool:** This is a semantic reading of the source's operating level, not something file metadata or keyword matching can infer. It also complements NW-4's boundary-axis thinking without encoding domain edges or cross-cut hints.
**Downstream consumer:** Pass-2 can decide whether a source is likely to promote new reusable concepts versus merely support an existing case; query layer can filter for "general principles" or "concrete cases"; human navigation can separate playbooks from examples.
**Cost concern:** Low to moderate. It is another enum, but it may overlap cognitively with `domain` boundary classification. If domain accuracy drops in NW-5, this should be one of the first optional fields to remove.
**Tier (your call):** ★★ (strong)

## central_question

**Type:** string or null
**Required / Optional:** Optional
**One-line purpose:** States the main question or problem the source is trying to answer in one sentence.
**Why the LLM is the right tool:** A source's driving question is often implicit. It is not equivalent to `summary`: the summary says what the source says; this field says what problem the source is organized around.
**Downstream consumer:** Human Obsidian UX gets a quick "why read this?" affordance; Pass-2 can use it to compare source intent against existing ontology coverage; query layer can support problem-oriented retrieval.
**Cost concern:** Highest of these proposals. It adds a generative prose field and could blur with `summary` if not tightly prompted. Keep optional and evaluate whether it improves human scanability enough to justify the attention cost.
**Tier (your call):** ★ (stretch)

## Considerations

The clean pattern is to add source-level semantic axes, not mini-compile outputs. I would avoid Pass-1 fields like extracted claims, proposed edges, related domains, canonical entity IDs, or graph mutations; those belong to compile / Pass-2 / GraphDB authority. The safest v0.2 candidate set is probably `knowledge_intent` + `evidence_basis`, with `temporal_frame` and `abstraction_level` behind NW-5 quality checks.
