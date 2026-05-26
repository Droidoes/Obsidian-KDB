# Additional Properties Survey — Grok Build

## Summary

I propose four additions. Three are compact source-level semantic/rhetorical classification axes that are LLM-native and high-reuse downstream (`rhetorical_purpose`, `audience_level`, `durability_class`). One is a lightweight generative signal for high-value reusable content patterns common in this vault (`primary_artifact`). All respect the single-call discipline, the post-LLM deterministic boundary, and D-NW4-5 constraints.

## Proposals

## rhetorical_purpose

**Type:** enum string (`explain`, `argue`, `instruct`, `analyze`, `report`, `reflect`, `reference`, `narrate`, `mixed`, `unclear`)

**Required / Optional:** Required

**One-line purpose:** Captures the primary intellectual move the source is making, independent of its `source_type` or `domain`.

**Why the LLM is the right tool:** `source_type` tells you the container (article, letter, transcript); rhetorical purpose tells you the *action* (is this source trying to persuade, teach a method, dissect a decision, narrate experience, or simply record data?). Heuristics on sentence structure or keyword lists are brittle across domains and writing styles.

**Downstream consumer:** Pass-2 can modulate worth-verdict strictness (an "instruct" source in `value-investing` may be higher value than a reflective one); query layer supports intent-based retrieval ("show me instructional notes on capital allocation"); human UX can surface "playbooks and models" vs "analysis and critique" within the same domain.

**Cost concern:** Low. A single compact enum inferred alongside `domain`, `summary`, and `key_themes`. Minimal additional attention load once the model is already doing deep semantic reading for signal/domain.

**Tier (your call):** ★★★ (must)

## audience_level

**Type:** enum string (`practitioner`, `advanced_practitioner`, `academic`, `generalist`, `beginner_friendly`, `mixed`, `unclear`)

**Required / Optional:** Optional (default `unclear` if ambiguous)

**One-line purpose:** The intended or natural audience sophistication level of the source.

**Why the LLM is the right tool:** This is a holistic judgment of assumed background knowledge, jargon density, and explanatory posture. A source can be "advanced practitioner" even if written for a generalist audience (e.g., Buffett letters); regex or readability scores miss the actual expertise threshold.

**Downstream consumer:** Query filtering ("practitioner-level notes on personal-finance"); Pass-2 can apply different extraction density expectations; Obsidian UX can offer "beginner on-ramps" vs "deep practitioner dives" within a domain; useful for future "progressive disclosure" features in compiled wiki output.

**Cost concern:** Low. Another single-enum judgment that rides along with existing classification work (`domain` + `key_themes`).

**Tier (your call):** ★★ (strong)

## durability_class

**Type:** enum string (`evergreen`, `slowly_drift`, `event_driven`, `time_sensitive`, `mixed`, `unclear`)

**Required / Optional:** Optional

**One-line purpose:** How quickly the source's core value is expected to decay or require refresh.

**Why the LLM is the right tool:** A source can mention many dates while being evergreen in its mental models (classic Buffett letters); another can have almost no dates while being tightly bound to a specific market regime or geopolitical moment. This is semantic durability, not mechanical date extraction (the dropped `time_period` was the latter).

**Downstream consumer:** Pass-2 can deprioritize or flag time-sensitive material for re-evaluation; query layer can support "evergreen principles" filters; human UX can surface "review candidates" (high `event_driven` or `time_sensitive` sources that have aged); feeds future maintenance/orphan logic in Component #3.

**Cost concern:** Low. Coarse enum + optional short `stated_period` string if the source explicitly names one. Can be prompted as a quick side judgment after the main substance work.

**Tier (your call):** ★★ (strong)

## primary_artifact

**Type:** enum string or null (`framework`, `checklist`, `mental_model`, `decision_record`, `prompt_template`, `table_or_matrix`, `case_study`, `none`, `mixed`, `unclear`)

**Required / Optional:** Optional (null / `none` when no primary reusable artifact stands out)

**One-line purpose:** Flags when the source's main payload is a concrete, reusable cognitive artifact rather than (or in addition to) prose exposition.

**Why the LLM is the right tool:** Detecting "this page contains a decision framework / capital allocation checklist / prompt template / 2x2 matrix that the author intends for reuse" requires understanding authorial intent and structure. Simple presence of lists or tables is noisy; the LLM can distinguish throwaway tables from load-bearing reusable ones.

**Downstream consumer:** Extremely high UX value in Obsidian ("show me all the frameworks in personal-finance"); Pass-2 can treat artifact-bearing sources as higher-yield for concept extraction; compile can give them special rendering treatment (callouts, index entries); query layer supports artifact-type search. This is one of the highest-leverage cheap signals for making the KDB feel like a living toolkit rather than just a library.

**Cost concern:** Moderate but bounded. Requires the model to surface the *main* artifact if one exists; not an exhaustive inventory. Can be prompted after summary/domain work with a "if the source's primary gift is a reusable artifact, name its kind" instruction.

**Tier (your call):** ★★ (strong)

## Considerations

The locked v0.1 set already does an excellent job on the "what is this about?" and "is it worth reading?" axes. The highest-ROI additions are therefore **second-order classification axes** (rhetorical move, audience posture, durability) that multiply the utility of the existing fields without duplicating them.

I deliberately avoided anything that looks like pre-emptive compile work:
- No claim extraction, polarity, or evidence linking (Pass-2 / GraphDB territory).
- No entity canonicalization or grounding beyond the already-locked `key_entities` (that's #74 + compile).
- No proposed edges, related domains, or cross-cuts (D-NW4-5).
- No file-level or provenance reasoning (post-LLM deterministic layer per the feedback memory).

The `primary_artifact` proposal is the one that feels most distinctive to *this* vault's content culture (heavy on models, checklists, and decision records). If NW-5 shows it adds attention cost without clear downstream payoff, it is the easiest to demote to stretch or drop.

Overall stance: ship the three ★★/★★★ classification axes in v0.2; gate `primary_artifact` behind a small NW-5 probe set. This keeps the single Pass-1 call high-signal while staying ruthlessly concrete-first.