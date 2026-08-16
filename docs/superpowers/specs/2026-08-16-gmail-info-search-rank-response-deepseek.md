# Gmail/Substack search-and-rank — formal architecture response (DeepSeek)

**Date:** 2026-08-16
**Reviewer:** DeepSeek (`deepseek-v4-pro`)
**Review basis:** `2026-08-16-gmail-info-search-rank-problem-statement.md`
**Companion artifact:** `2026-08-16-gmail-info-search-rank-review-and-solution.md` (read; this response is independent)

---

## 0. Verdict

**CONCUR-WITH-CORRECTIONS.** The brief names the right problem and the right
two-value split, but three claims must be corrected before panel synthesis, and one
first-class requirement is missing. Recommended direction: an **extraction-first
Signal Ledger** (extract once → store structured, source-grounded records → rank
repeatedly with versioned, feedback-calibrated weights), with retrieval as a read
surface and — uniquely — a **post-horizon outcome loop** that turns perishable ideas
into author-track-record data over time.

---

## 1. Review of the problem statement

### 1.1 The corpus is not investment-dominated (measured, not inferred)

The brief asserts *"the corpus is dominated by investment newsletters (plus a minority
of AI/tech and other letters)."* This is materially wrong and it matters, because the
whole system is framed as an investment-idea engine. I measured the residual corpus:

- **2,659 files** (not "2,659 full articles" — see §1.2).
- **4.21M body words**; median 1,000/article, p95 4,311, max 45,152.
- **117 distinct raw author strings**; **212 files** attributed only to `Substack`.
- The **largest author cohorts are political/geopolitical**, not investment:
  `Julian Vigo / Savage Minds` (224), `Robert Reich` (221), `Glenn Diesen` (196),
  `The New Republic` (126), `The Bulwark` (84), `Project Syndicate` (70),
  `Mearsheimer` (60), `Chris Hedges` (55). Investment voices — `Compounding Quality`
  (86), `The Coal Trader` (122), `Rebound Capital` (31) — are a **minority**.
- `content_kind`: **2,570 article / 77 video / 12 podcast**.

Consequence: **corpus relevance is a first-class, non-trivial gate**, not a small
cleanup step. A meaningful fraction of these files will never produce a value-investing
idea *or* a value-investing lesson, and the system must say so explicitly per file
rather than force every file through an idea/lesson mold. This is the difference
between "classify" and "extract what exists."

### 1.2 "2,659 full articles" overstates the extractable corpus

Of the 2,659 files, **89 are video/podcast** (their bodies are show notes or empty)
and **25 have <50 body words**. Three files additionally carry **corrupted
frontmatter** (body text leaking into frontmatter keys). The extractable-text corpus
is closer to ~2,540 articles. None of this invalidates the task; it tightens the
cold-start accounting and the extraction contract's relevance gate.

### 1.3 The two-value split is right — and it should be a three-output split

The brief's Ideas vs Lessons distinction is the strongest part of the framing and
should be preserved. Add a third output the brief names but never operationalizes:

> **Outcomes.** Every idea has a horizon. When that horizon passes, the system
> should record *what actually happened* (hit / miss / expired / still-running, plus
> an optional one-line note). This is the **only** way "author track record" (§1.4)
> can be learned without plumbing external market data on day one — and it is
> essentially free, because Joseph is already the human in the loop.

Outcome checking converts the *liability* of perishability (ideas go stale) into the
system's highest-leverage *asset* (a growing, author-attributed track-record dataset).
No other single addition pays off this much over a year.

### 1.4 "Author quality" is three concepts; only one is cold-start learnable

The brief says author quality should be "learned and tracked." Split it:

1. **Personal utility to Joseph** — learnable immediately from feedback events.
2. **Analytical/writing characteristics** — partially learnable from extraction
   features (thesis specificity, evidence discipline, falsifiability).
3. **Real investment track record** — **not** learnable from usefulness labels; it
   requires outcomes (§1.3) plus time. Until ~6–12 months of outcomes accumulate,
   this dimension is empty and must be treated as empty (no hallucinated prior).

Keep author reputation's influence on idea ranking **small and capped** at the start,
and let it grow only as outcome data justifies it. A rich-get-richer loop that
amplifies the loudest author before any track record exists is the main self-inflicted
failure mode to avoid.

### 1.5 The ranking objective needs one word of precision

"Strongest current investment ideas" could be read as predicted return. The
achievable, honest objective is:

> **Rank ideas by expected value of further research**, not by predicted investment
> performance.

The system predicts "worth Joseph's research hour," never "will this stock go up."
That distinction must be written into the schema (the `research_priority` field should
be labeled exactly that) so the ranker is never asked to predict markets.

### 1.6 Missing: success criteria and a decision rule

The brief header promises success criteria but delivers goals, not pass/fail gates.
§6 below supplies concrete ones.

---

## 2. Proposed architecture

### 2.1 Guiding principles

1. **Extract once, preserve evidence, score many times.** One structured extraction
   per article; ranking is deterministic and re-runnable without re-extraction.
2. **Faithfulness is a safety requirement, not a quality nicety.** A hallucinated
   ticker or thesis is actively dangerous (Joseph may research a fake company). Every
   substantive field must carry a validated source span; unsupported output fails the
   gate.
3. **Joseph's attention is the scarce resource, not LLM tokens.** (See §2.6 — the full
   extraction pass is ~$1–3.) Optimize the design for *signal per review minute*.
4. **Independence = independent state and lifecycle, not reinvented infra.** The
   system must not write into the KDB wiki/manifest/graph, but it should reuse
   `common/call_model` + `common/model_pool` (retry, telemetry, routing). Reinventing
   those would forfeit the cost telemetry the brief itself demands.

### 2.2 Pipeline

```text
Raw Markdown (2,659, durable)
    ↓
Deterministic intake: identity/author cleanup, frontmatter repair, paragraph IDs
    ↓
One structured LLM extraction per article
    ├── relevance verdict (investment / lesson / mixed / off-topic / noise)
    ├── 0..N idea_mentions   (company, ticker?, stance, thesis, premise,
    │                          catalyst, risks, horizon, expiry)
    ├── 0..N lesson_cards    (principle, context, reuse, counterexample)
    └── validated evidence_spans (paragraph id + exact source span)
    ↓
SQLite ledger (single file) + FTS5
    ↓
Canonicalization: idea_mentions → ideas (clusters); lesson_cards → frameworks
    ↓
Versioned deterministic ranker → two surfaces
    ├── Research queue   (ideas, decaying by horizon, corroboration-aware, diverse)
    └── Lesson library   (compounding frameworks, cross-linked, spaced retrieval)
    ↓
Feedback events (immutable) + Outcome checks (post-horizon)
    ↓
Weight calibration (pointwise) → next ranker version
```

**Two surfaces, not one.** Ideas and lessons have different mechanics and must not
share a single queue:

- **Ideas** are *perishable*: a decaying research queue. `research_priority` decays
  exponentially toward the extracted horizon; when the horizon passes, the idea
  graduates into an `outcome_check` record instead of lingering at the top.
- **Lessons** are *compounding*: a framework library, not a queue. Lesson cards should
  be cross-linked (this mistake ↔ that framework ↔ that author), cluster into durable
  frameworks, and support *spaced retrieval* ("re-surface the framework Joseph hasn't
  seen in 90 days"). Ranking lessons by a single score is the wrong primitive.

### 2.3 Data model

One local SQLite file is the system of record; raw Markdown stays the immutable source.
FTS5 for keyword search across articles, ideas, lessons, and evidence (BM25 for free;
defer embeddings until an evaluation proves FTS + structured fields miss real queries).

Core records:

| Record | Purpose |
|---|---|
| `articles` | source identity + cleanliness flags (promo/noise/off-topic) |
| `authors` / `publications` | modeled separately; identity-cluster map (117 raw strings → canonical) |
| `extraction_runs` | per-article run provenance, model, telemetry, schema version |
| `article_assessments` | relevance verdict, summary, one-line takeaway |
| `idea_mentions` | what **one** article claims (never merged at this layer) |
| `ideas` | cross-article clusters; a bullish and a bearish thesis on the same ticker are **different ideas** |
| `lesson_cards` | atomic lesson; `frameworks` cluster related cards |
| `evidence_spans` | paragraph id + exact quoted span, deterministically validated |
| `feedback_events` | immutable (see §2.4) |
| `outcome_checks` | post-horizon: hit / miss / expired / still-running + note |
| `score_snapshots` | ranker version × record id → score, for audit/replay |
| `rankers` | human-readable, versioned weights |

Never merge by ticker alone. Corroboration (same thesis in N independent authors)
raises *salience and extraction confidence* — but note the domain subtlety: **consensus
is not value.** In investing, everyone already holding an idea is often a crowding
signal, not a buy signal. Corroboration must feed confidence/salience, never the
thesis's intrinsic merit score.

### 2.4 The learning loop (minimal viable version)

Store feedback as **immutable events**, not mutable ratings:

- Action: `research` / `save` / `skip` / `wrong-extraction`.
- Optional usefulness score + reason tags.
- Optional **pairwise comparison** ("which of these two deserves research first?").
- The ranker version, score, and display position **shown to Joseph at collection time**.

Two disciplines make the loop actually learn instead of drift:

1. **Selection-bias control.** Feedback only on top-ranked items is a biased training
   set. Reserve a fixed exploration quota of every review queue for uncertain,
   diverse, and randomly sampled records, and record exposure in the event.
2. **Start hand-tuned, then pointwise.** Begin with transparent hand-set weights.
   Once ~200–300 representative labels exist, fit a small regularized pointwise model
   (e.g., logistic regression over the feature vector). Defer learning-to-rank
   (LambdaMART-style) until there are genuine query groups and graded labels — it is
   not a v1 tool.

The **outcome loop** runs in parallel and is equally a first-class citizen: a
"what happened?" queue of ideas whose horizon has passed, answered in one click.

### 2.5 Cold start vs steady state

- **Cold start (2,659):** full extraction is cheap (§2.6), so do **not** build a
  triage-that-suppresses gate (that is the "active-learning prioritizer" failure mode
  — it can permanently miss lessons in articles it declines). Instead: **extract
  everything**, then gate *quality* in three tiers (100-audit → 500-audit → full),
  not *coverage*.
- **Steady state (~tens/week):** new file → extract once → canonicalize into existing
  `ideas`/`frameworks` (new mention updates the cluster and its corroboration count) →
  recompute scores → append to the appropriate surface. Incremental and deterministic.

### 2.6 Cost envelope

Using the standing `deepseek-v4-flash` ($0.14/M in, $0.28/M out; 1M ctx):

- ~4.21M source words ≈ **5.5M input tokens ≈ $0.77**; extraction output ≈ 700
  tokens/article × 2,659 ≈ **1.9M tokens ≈ $0.52**. Full pass ≈ **~$1.3**, plus
  retry/validation overhead — a **low-single-digit-dollar** job.
- The "cost conversation" that deferred compilation is therefore **moot in dollars**;
  the binding constraints are extraction *quality* and Joseph's *review time*.

The 100-article pilot must capture token/retry/latency/cost telemetry (already
available via `common/call_model` + `llm_telemetry`) and extrapolate before the
500-article gate. Deterministic work (identity cleanup, FTS, decay, clustering by
exact ticker/company) should never be sent to an LLM; embeddings stay out of v1
unless evaluation (§2.7) proves a need.

### 2.7 Evaluation and head-to-head vs GraphDB

Predeclare metrics before building, so the system is judgeable:

- **Ranking quality:** `nDCG@10` against Joseph's labeled priorities; top-10
  `research`/`save` rate; **exploration-diverse** coverage (not 10 ideas in one sector).
- **Faithfulness:** extraction span-validity rate; `wrong-extraction` feedback rate;
  zero unvalidated spans in the ledger.
- **Recall:** against the stratified pilot's hand-audited idea/lesson count.
- **Cost/attention:** LLM $ per surfaced signal; Joseph review-minutes per accepted idea.
- **Head-to-head:** keep a stable, versioned JSONL/CSV export from the ledger and a
  small shared probe set. Comparing to the GraphDB pipeline means running the *same
  probe set* through both and comparing the same metrics above — which is only
  possible because the brief preserves both paths (raw sources durable; exports stable).

---

## 3. Direct answers to the six open questions

| # | Question | Answer |
|---|---|---|
| 1 | Core architecture | Extraction-first Signal Ledger: one structured, source-grounded extraction per article → SQLite + FTS5 → versioned deterministic ranker → **two surfaces** (decaying research queue + compounding lesson library). Retrieval is a read surface, not the core. |
| 2 | Learning loop | Immutable feedback events (with exposure context) + pairwise comparisons + a post-horizon **outcome loop**; start hand-tuned weights, move to small pointwise model at ~200–300 labels; reserve exploration quota against selection bias. |
| 3 | Data model | Single SQLite file (articles, authors/publications, idea_mentions→ideas, lesson_cards→frameworks, evidence_spans, feedback_events, outcome_checks, score_snapshots, rankers) + FTS5; vectors deferred. |
| 4 | Cold start vs steady state | Backlog: extract everything (cheap), gate *quality* in tiers, never gate *coverage*; steady state: incremental extract→cluster→recompute per file. |
| 5 | Cost discipline | ~$1–3 full backlog pass on `deepseek-v4-flash`; keep deterministic work deterministic; pilot captures telemetry and extrapolates before scaling. |
| 6 | Evaluation | `nDCG@10`, top-10 accept rate, faithfulness/span-validity, recall, diversity, $/signal, review-minutes/idea; head-to-head via stable exports + a shared probe set. |

---

## 4. Delivery sequence

1. **Corpus audit + label protocol** — confirm §1 measurements; define exactly what
   Joseph labels at article/idea/lesson level and the pairwise prompt.
2. **Stratified pilot (~120 articles)** — ratify the extraction schema across authors,
   dates, lengths, topics, and content_kind.
3. **Extraction gate** — 100-audit → 500-audit → full corpus; each tier has a
   predeclared pass condition on faithfulness + relevance.
4. **Ranking baseline** — hand-tuned weights vs recency-only, author-only, BM25.
5. **Steady state + outcome loop** — incremental ingestion and the "what happened?"
   queue; author track record begins accruing.

---

## 5. Decision gate

Recommend **extraction-first Signal Ledger** with the two-surface split and the
outcome loop added to the ranker's feedback sources. This response is not ratified.
If Joseph selects the direction, the next actions are: (1) fold this + the companion
review into a synthesis; (2) file a unique task ID in `docs/TASKS.md`; (3) record the
system boundary in `docs/CODEBASE_OVERVIEW.md`; (4) produce the detailed blueprint,
implementation plan, and TDD gates; (5) request explicit **Proceed** before
implementation.
