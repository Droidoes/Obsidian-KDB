# Review — Task #145 Phase 2 Extraction Architecture ADR (Kimi, 2026-08-21)

> **Subject**: [`2026-08-21-task145-phase2-extraction-architecture.md`](2026-08-21-task145-phase2-extraction-architecture.md)
> **Method**: every verifiable number checked against the live ledger (`~/Obsidian/KDB/fts/ledger.sqlite`) and the repo (`common/models.json`, blueprint v0.1).

## Verdict

Solid ADR — the grounding is real (§3 matches independent ledger queries, including the 293 = 257+36 split and the 134/223/41 · 95 cross-tab), the decisions match the architecture-pass discussion, and each one is falsifiable via the pilot. Found: **one material contradiction, two internal conflicts, one factual error, and one exclusion worth pushing back on**.

## Material findings

### 1. D-P2-1's "sole trigger" contradicts blueprint §7.2's exploration sample

The blueprint binds extraction to *two* triggers: the eligibility verdict **and** "a fixed 5% exploration sample (min 10) of ineligible files… still extracted, tagged exploration=true" (§3 diagram, §7.2, §11 cost line). The ledger shows 33 not-accepted articles already carry `exploration=1`. D-P2-1 as written ("the ratified accept rule is the **sole** trigger") either silently amends §7.2 or misstates the production denominator — the real extraction set is ~293 + 33 ≈ **326**, +11% cost. Fix: restate the trigger as *accept rule ∪ exploration sample* (and note the pilot's oversample of the 95 is additive, not a substitute for it).

### 2. D-P2-3 and D-P2-5 salvage rules collide

D-P2-3: anchor matches 0 or >1 times → "**the record is dropped**." D-P2-5: an optional field emitted with an invalid span is "**nulled, not record-fatal**." If an *optional* field's anchors fail, both binding rules fire. One sentence fixes it: record-drop applies only to required-core spans; optional-field span failure → null the field.

### 3. §5 pilot-gate per-model scope is ambiguous

Metrics 3/4/6 are "per model," but D-P2-6's bake-off is a 20-file probe. Is the 100-file audit run ×6 models, or is it 20×6 probe → winner → 100-file audit on the winner? The cost lines assume different things (§3 prices the audit at ~35% of $1 = single-model). Also: blueprint §9's gate is a "100-file **eligible-set** audit" — the 95 disagreement articles are *not* in the eligible set, so oversampling them is an amendment to §9's gate definition and should be recorded as such, with the count stated (inside the 100 or on top).

## Factual error

### 4. Pool contents misstated (D-P2-6)

"Excluded from the bake-off (**present in pool**): `gpt-5.6-sol`, `gpt-5.6-terra`" — neither is in `common/models.json`. The actual pool is exactly 5: `gpt-5.4-mini`, `gemini-3.6-flash`, `deepseek-v4-flash`, `deepseek-v4-pro`, `qwen3.7-flash`. The ⚠️ "add to pool" flags on the three new candidates are correct.

## Pushback

### 5. Excluding `qwen3.7-flash` undercuts the ADR's own metric

It's the cheapest model in the pool by >10× ($0.03/$0.13 vs flash's $0.44/$1.32). "Underperforming" is asserted with no evidence cited — and under *cost-per-landed-record* (D-P2-6's decision metric), a 15× cheaper model can drop a large share of records and still win. Either cite the underperformance evidence or put it in the 20-file probe; a bake-off that excludes the cheapest candidate on an unmeasured claim isn't a bake-off.

## Nits

- §3 percentiles: p95/p99 (9,590 / 18,423) differ slightly from a nearest-rank read (9,922 / 19,492) — interpolation method; immaterial, but "verified" claims should note the method.
- D-P2-4 pins everything except the chunk target size and overlap policy — since map-only implies no overlap, say so explicitly and pin a target (e.g., ≤6k words/chunk) for the blueprint.
- `glm-5.3` availability is genuinely shaky: launched ~Aug 14–17, and as of Aug 17–19 sources disagree on whether the public API is live — [datanorth.ai](https://datanorth.ai/news/z-ai-releases-glm-5-3) says no public API yet (pricing page still lists GLM-5.2), while [OpenRouter](https://openrouter.ai/z-ai/glm-5.3) lists `z-ai/glm-5.3` at $1.40/$4.40. Follow-up #3 checks the base URL, but the real risk is API availability itself — ping the endpoint before the bake-off and be prepared to run it with 5 candidates.
- The new-model IDs (`gpt-5.6-luna`, `qwen3.8-max`) could not be independently verified in this review — the doc says confirmed 2026-08-21; keep that confirmation receipt with the pilot journal.

## Bottom line

Nothing here blocks the architecture — findings 1–3 are one-paragraph fixes, 4 is a line edit, 5 is a decision for Joseph.
