# Task #145 Phase 2 — Extraction Architecture Decision Record

> **Status**: v0.3 — review absorbed, all decisions resolved (2026-08-21).
> **Parent**: [`2026-08-16-task145-kdb-fts-blueprint-v0.1.md`](2026-08-16-task145-kdb-fts-blueprint-v0.1.md) (§7.3 extraction, §9 Phase-2 gate).
> **Review**: [`2026-08-21-task145-phase2-extraction-architecture-review-kimi.md`](2026-08-21-task145-phase2-extraction-architecture-review-kimi.md).
> **Scope**: the Phase-2 extraction pass only (`extract.py` + `spans.py` + JSON schema + per-record salvage). This record resolves the five open questions surfaced by the architecture pass, plus the extraction-model default.

---

## 1. Objective (one paragraph)

Extraction is the **one expensive LLM read** that turns a gate-accepted article's prose into
structured, source-grounded records — the durable artifacts everything downstream consumes. It emits
**0..N `idea_mentions`** (perishable theses: company + stance + thesis) and **0..N `lesson_cards`**
(compounding frameworks: principle + context), each grounded in a **validated evidence span**. The
governing principle is D1/D14 (**extract once, score many**): extraction is the only LLM-heavy read;
clustering, ranking, and review are deterministic or cheap afterward. The record must therefore carry
enough structure for deterministic scoring, never re-reading prose.

## 2. Scope

**In this pass:**

- `extract.py` — prompt + JSON schema + per-record salvage + the extraction runner.
- `spans.py` — evidence-span proof (deterministic).
- The `idea_mentions` / `lesson_cards` / `evidence_spans` / `extraction_runs` schema (migration 3).

**Out of this pass (deferred to the end of Phase 2, with extraction output in hand):**

- `cluster.py` — mentions→ideas, cards→frameworks. *Rejected alternative*: folding canonicalize into
  this pass (risk lives in the LLM contract, not in deterministic clustering; designing merge rules
  before seeing one extracted batch is speculative generality; the Phase-2 exit gate can't test it).
  **Binding constraint retained:** the extraction schema stays *cluster-aware* — `normalized_company`,
  `stance` enum, `ticker`-nullability, and `thesis` are design inputs now (D12).

**Never in scope:** ranker, decay, queues, feedback/outcome loops (Phase 3+), gate-model change.

---

## 3. Grounding (live ledger, verified 2026-08-21)

- Corpus: **623** articles (`ok` 607 · `media` 14 · `short` 2). Quarantined: `_promo/` 1,872 + `_blacklist/` 1,694.
- Gate verdicts: **607** (one per `ok` article). Topic mix: investment 195 · other 154 · geopolitics 93 · ai-tech 64 · finance-econ 62 · china-econ 39.
- **Gate-accepted (accept rule): 293** = 257 topic-clause (195 investment + 62 finance-econ) + 36 signal-clause (`signal ≥ 0.75`, non-relevant topic).
- **Exploration sample: 33** not-accepted articles already carry `exploration=1` → the full extraction
  denominator is **~326** (293 + 33; +11% cost), per blueprint §7.2.
- **Flag cross-tab** (why the trigger decision matters):
  - Accepted (293): `extract_ideas` 134 · `extract_lessons` 223 · **neither 41**.
  - Not-accepted (314): **95 carry flags** (94 lessons, 1 both).
- Word counts (accepted set, n=293; nearest-rank interpolation): avg 3,029 · p50 1,830 · p90 7,160 · p95 9,590 · p99 18,423 · **max 45,152** · **22 articles >8,000 words**.
- Accepted backlog: 887,555 words ≈ 1.55M input + 0.23M output tokens ≈ **~$1** at `deepseek-v4-flash` prices; the 100-file audit is ~35% of that. Full two-stage pilot (§5) stays < $2.

---

## 4. Decisions (binding — changing one is a new architecture turn)

| ID | Decision | Rejected alternatives |
|---|---|---|
| D-P2-1 | **Trigger set:** the calibrated accept rule ∪ §7.2 exploration sample; gate flags are advisory | flag-driven; rule∪flags hybrid |
| D-P2-2 | **Call structure:** one combined call (ideas + lessons) | split idea/lesson passes; coarse-then-refine staging |
| D-P2-3 | **Span:** model *points* (`paragraph_id` + head/tail anchors), Python *cuts* | model-transcribed full quote; character offsets |
| D-P2-4 | **Window:** full body ≤8k; chunked tail (>8k); never silently truncate | single 4k cap; full-body single call; LLM chunk-merge |
| D-P2-5 | **Schema:** rich records, slim required core; rest optional-nullable | fully-required rich schema; two-stage refine |
| D-P2-6 | **Model:** pilot bake-off over 7 candidates decides the default | single pre-declared default; no comparison |

### D-P2-1 — Trigger set: accept rule ∪ exploration sample; gate flags are advisory

The **ratified accept rule** (`topic ∈ {investment, finance-econ} ∪ signal ≥ 0.75`) is the **primary**
trigger, **joined by the blueprint §7.2 exploration sample** — the 33 ineligible articles currently
marked `exploration=1` are extracted regardless, so the denominator is ~326, not 293. The gate's
`extract_ideas` / `extract_lessons` flags are **advisory** — recorded on `extraction_runs` as
*expectations* for the audit, never a trigger.

- **Rejected:** *(a)* flag-driven triggering — would silently skip the **41** accepted-but-neither-flagged
  articles and extract the **95** rejected-but-flagged ones; *(b)* a hybrid that lets flags widen the rule.
- **Rationale:** the accept rule was calibrated against Joseph's 150 labels; the flags have **no precision/recall**
  (the calibration batch measured *usefulness buckets*, not idea/lesson eligibility). An uncalibrated signal
  must not override a calibrated one. The extractor's downgrade-right (→ `neither`, logged) is what converts
  an accept into "nothing to extract" — a rule-precision signal, not an error.
- **Constraints:** D5 (gate-then-extract), D20 (`promote` covers the false-negative; the exploration sample
  measures it), §7.2 (exploration sample is binding, not amended).
- **Pilot metric:** **flag-divergence** — lessons-flagged → zero cards (flag-precision); neither-flagged → ideas
  emitted (rule-recall). The 41 and the 95 are the two audit subsets; the pilot **oversamples the 95**
  (highest-information false-negative candidates) *additively on top of* the §7.2 exploration sample — it
  supplements, not substitutes for, that sample (see §5).

### D-P2-2 — Call structure: one combined call

One structured call per triggered article, emitting both `idea_mentions` and `lesson_cards` in a single response.

- **Rejected:** split idea-pass + lesson-pass (≈2× input, ~$0.50 extra on the backlog, no demonstrated quality gain);
  coarse-then-refine staging (extra cost + complexity for a task D11 already makes over-asking safe).
- **Rationale:** body tokens dominate cost and are paid per call (avg 3,029 words); D11 (zero-is-success) +
  per-record salvage make "ask for everything, keep what's grounded" the cheap posture. *Empirically falsifiable*,
  not debated in the abstract.
- **Pilot metric:** per-type emission vs. the gate's flag expectation (does a combined call under-emit ideas
  relative to `extract_ideas`?).

### D-P2-3 — Span representation: the model points, Python cuts

The model emits `paragraph_id` + **short verbatim head/tail anchors** (~3–8 words each, unique within the
paragraph). `spans.py` locates the anchors and **slices the span from the source** — the substring proof holds
**by construction**, because the stored `exact_quote` *is* source text. This is squarely the repo's controller
philosophy (model emits structure, Python owns the bytes).

- **Rejected:** model-transcribed full quote (long exact quotes are unreliable — models paraphrase); character
  offsets (models do not reproduce byte/char offsets reliably).
- **Why anchors beat quotes:** a 3–8 word verbatim anchor is dramatically more reproducible than a 40-word
  verbatim quote, so dropout is far lower for the same D10 guarantee.
- **Validation spec (binding):** each anchor must match **exactly once** in the stated paragraph; the head anchor
  must precede the tail anchor; span boundaries (anchor-inclusive vs exclusive) are fixed in the schema. Anchor
  failure on a **required-core span** (0 or >1 matches) → the *record* is dropped (per-record salvage); anchor
  failure on an **optional-field span** → null that field only (see D-P2-5). **Fallback ladder** (only if anchors
  prove flaky in the pilot): model-written quote + salvage `exact → whitespace/unicode-folded → fuzzy-snap-within-
  paragraph → drop`. The fuzzy rung may relax the *anchor*, never the *proof* — the landed text is always a
  verbatim substring.
- **Pilot metric:** **anchor-dropout rate** (the #1 residual risk: non-unique/common anchors) + span-validity 100%.

### D-P2-4 — Input window: full body ≤8k; chunked tail; never silently truncate

Full body up to **8,000 words** (covers ~92.5% of the accepted set); the **22-article >8k tail** is
**chunked at paragraph boundaries** into **≤6,000-word chunks with no overlap** (map-only implies no overlap;
paragraph boundaries guarantee no span is ever split) and extracted map-only (concatenate chunk outputs;
**byte/field-identical dedupe only**; no LLM merge). **Never silently truncate.**

- **Rejected:** the gate's 4k cap (silently loses the back half of long articles — and the 45k tail is plausibly
  the highest-value deep-dives); one full-body call for 45k (fits context, but quality degrades and cost spikes);
  an LLM chunk-merge pass (complexity that belongs to `cluster.py`, D12).
- **Why paragraph-boundary chunking is clean:** paragraphs are the atomic evidence unit, so a chunk boundary can
  never split a span; `paragraph_id`s are global and stable, so spans validate identically per chunk.
- **Known limitation (on record):** no cross-chunk synthesis — a thesis built in §1 and argued in §4 may
  under-merge. Acceptable for v1; merging is `cluster.py`'s later problem.
- **Pilot metric:** long-tail extraction coverage + span-validity across chunk boundaries.

### D-P2-5 — Schema granularity: rich records, slim required core

Keep blueprint §6's record shape, but the **required core is tiny** per record — idea: `company` + `stance` +
`thesis` + span; lesson: `principle` + span. Everything else (`valuation_premise`, `catalyst`, `risks`,
`horizon`, `expires_on`, `extraction_uncertainty`, `context`, `reusable_application`, `failure_mode`,
`lesson_type`) is **optional-nullable**; `schema_version` stamped (D14).

- **Rejected:** fully-required rich schema (JSON-mode reliability degrades with deep nesting and large required
  sets); two-stage coarse-then-refine (extra cost, no demonstrated gain).
- **Salvage rule (binding):** an *optional* field emitted with an invalid span is **nulled, not record-fatal** —
  the record's required core stands. Record-drop (D-P2-3) applies **only** to required-core span failure; optional
  span failure nulls the field. Each required-core field carries its own span (D10). The ranker treats missing
  features as zero contribution, so nulls are structurally safe.
- **Pilot metric:** **field-fill rates** — tells us which optional fields to tighten into required later, and
  only when the data justifies it.

### D-P2-6 — Extraction model: pilot bake-off over 7 candidates

The extraction default is **not pre-declared** — it is the winner of a pilot bake-off. The **gate stays locked
to `deepseek-v4-flash`** (the accept rule is calibrated against its verdicts; re-gating would force re-calibration).

| Candidate | ctx / max out | $ in / out (1M) | Reasoning | Note |
|---|---|---|---|---|
| `deepseek-v4-flash` | 1M / 65,536 | 0.44 / 1.32 | off | standing default |
| `gpt-5.4-mini` | 400k / 128,000 | 0.75 / 4.5 | `low` | in pool |
| `gpt-5.6-luna` ⚠️ | 1.05M / 128,000 | 0.20 / 1.20 | none/low/med | **add to pool**; cheapest |
| `qwen3.8-max` ⚠️ | 1M / 65,536 | 2.0 / 6.0 | xhigh/med/low | **add to pool**; the Qwen upgrade seat |
| `glm-5.3` ⚠️ | 1M / 128,000 | 1.4 / 4.4 | always on | **add to pool**; availability unconfirmed |
| `deepseek-v4-pro` | 1M / 384,000 | 1.32 / 3.96 | off | same-provider "does paying more help" probe |
| `qwen3.7-flash` | 1M / 65,536 | 0.03 / 0.13 | off | in pool; **last chance** — dropped from the extraction seat if it underperforms |

⚠️ = register in `common/models.json` before the pilot (IDs confirmed 2026-08-21: `gpt-5.6-luna`, `qwen3.8-max`,
`glm-5.3`; keys already set: `OPENAI_API_KEY` / `QWEN_SGP_API_KEY` / `ZAI_API_KEY`; keep the confirmation
receipt with the pilot journal — the new IDs could not be independently re-verified in review). The pool today is
exactly five — `gpt-5.4-mini`, `gemini-3.6-flash`, `deepseek-v4-flash`, `deepseek-v4-pro`, `qwen3.7-flash` — so
the three ⚠️ entries are genuine additions. Excluded from the bake-off (present in pool, not requested):
`gemini-3.6-flash`. `gpt-5.6-sol`/`gpt-5.6-terra` are not in the pool and out of scope per Joseph.

- **Reasoning policy (binding):** run every candidate at its **minimum reasoning** — `gpt-5.6-luna` at
  `none`/`low`, `qwen3.8-max` at `low`, `glm-5.3` at `low` (forced on). Extraction is a structuring + faithfulness
  task, not a reasoning task, and **reasoning tokens bill as output** — so sticker output prices understate the
  real cost of the reasoning-first models.
- **Bake-off design:** a fixed **20-file probe** (idea-only / lesson-only / both / long-tail, frozen) run through
  every candidate with the *same* prompt + schema + span-validator. Metrics: span-validity (hard gate, 100% on
  landed records), landed-record rate (anchor-dropout), field-fill, flag-divergence, **cost-per-landed-record**
  (not per-call — a cheap model that drops 30% is pricier per landed record than a dearer one that lands 95%),
  and Joseph's qualitative audit of a handful of records per model. Cost of the bake-off is < $1.
- **Decision rule:** default = the model that clears the span gate and wins on coverage + quality at acceptable
  cost; D19's "overrideable per run" is retained.
- **Rejected:** single fixed default with no comparison (D19's `deepseek-v4-flash` is the *provisional* default,
  not the verdict); declaring a default before measuring extraction quality.

---

## 5. Pilot gate — two stages

The pilot is **staged**, and the §3 cost lines assume single-model runs:

1. **Bake-off (20-file probe × 7 candidates)** → pick the extraction default (D-P2-6).
2. **100-file eligible-set audit — on the winner only** → the Phase-2 exit gate (blueprint §9).

The 95-disagreement oversample (D-P2-1) is an **amendment to §9's "eligible-set audit"** — those 95 are not
eligible-set members by construction — and is **additive**: a stated count *on top of* the 100. Full two-stage
pilot cost < $2.

Metrics:

1. **Span-validity 100%** on landed records (D10).
2. **Zero-idea rate on a political holdout** reported (D11).
3. **Anchor-dropout rate** per model (D-P2-3).
4. **Field-fill rates** per model (D-P2-5).
5. **Flag-divergence** (rule-recall / flag-precision) — with the 95 disagreement articles oversampled (D-P2-1).
6. **Cost-per-landed-record** per model (D-P2-6).
7. **Model bake-off decision** produced (D-P2-6).

## 6. Follow-ups (not blocking)

1. **Workflow doc §11** — tag `cluster.py` as a post-Phase-2 decision; drop it from the "planned modules" list.
2. **Blueprint §14** — correct the stale 922-mix line to the post-#152 truth (607 verdicts, investment 195).
3. **Register the three models** in `common/models.json` — confirm GLM-5.3 base URL (`https://api.z.ai/api/paas/v4`)
   **and API availability** (launched ~Aug 14–17; sources disagree on whether the public API is live — ping the
   endpoint before the bake-off and be prepared to run with 5 candidates).
4. **`prompts/extract.j2`** versioning convention to be fixed in the blueprint (mirrors `gate_v1`).

## 7. References

- Blueprint v0.1 — `docs/superpowers/specs/2026-08-16-task145-kdb-fts-blueprint-v0.1.md` (§2 D1–D22, §6 data model, §7.3, §9).
- Problem statement — `docs/superpowers/specs/2026-08-16-gmail-info-search-rank-problem-statement.md`.
- Workflow reference — `docs/reference/kdb-fts-workflow.html` (§11 Phase 2).
- Live ledger — `~/Obsidian/KDB/fts/ledger.sqlite` (verified 2026-08-21).
- Model pricing — z.ai, OpenAI, Alibaba Model Studio docs (fetched 2026-08-21).

## 8. Review amendments (v0.2 → v0.3, 2026-08-21 — Kimi review)

Absorbed from the Kimi review:

1. **Trigger restated** as *accept rule ∪ §7.2 exploration sample* (33 ineligible already `exploration=1`; denominator ~326, +11% cost).
2. **Salvage collision resolved** — record-drop applies only to required-core spans; optional-field span failure nulls the field.
3. **Pilot staged** — 20-file probe × N candidates → winner → 100-file audit on the winner; the 95-oversample is an additive amendment to §9's gate.
4. **Pool list corrected** — exactly five today; `gpt-5.6-sol`/`terra` were never in the pool.
5. **Chunk target pinned** (≤6,000 words, no overlap); percentile method noted.
6. **`glm-5.3` availability flagged** — ping before the bake-off; 5-candidate fallback.

**Open decision — RESOLVED (Joseph, 2026-08-21):** include `qwen3.7-flash` as a **7th candidate, fully audited**.
It is the cheapest pool model by >10× ($0.03/$0.13) and the decision metric is cost-per-landed-record, so it earns
a measured shot — but this is its **last chance**: it was already "on the cusp of getting dropped" for
underperforming, and a weak probe result removes it from the extraction seat permanently.
