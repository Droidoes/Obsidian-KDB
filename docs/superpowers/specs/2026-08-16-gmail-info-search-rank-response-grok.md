# Gmail/Substack search-and-rank — formal architecture response (Grok)

**Date:** 2026-08-16
**Reviewer:** Grok
**Review basis:** `2026-08-16-gmail-info-search-rank-problem-statement.md`
**Independence:** this response was written after an independent corpus audit. It
read, but does not adopt, `2026-08-16-gmail-info-search-rank-review-and-solution.md`
and `2026-08-16-gmail-info-search-rank-response-deepseek.md`.

## 0. Verdict

**CONCUR-WITH-CORRECTIONS.** The brief names the right job and the right
ideas-versus-lessons split. It is not yet a fair panel brief, because its
description of the corpus is wrong in a way that changes the architecture.

Recommended direction: a **relevance-gated structured extraction ledger**.
Index every residual file for search. Extract idea and lesson records only from
files that pass a cheap relevance gate. Rank those records with a versioned,
feedback-calibrated scorer whose objective is expected value of Joseph's next
research hour — never predicted investment return.

This is not ratification. Joseph chooses among the three families in §3.

---

## 1. Review of the problem statement

### 1.1 What the brief gets right

- Ideas are perishable; lessons compound. That split should survive every option.
- Joseph's evaluations are the only legitimate ground truth for *personal
  usefulness and research priority*. Making the feedback loop first-class is
  correct.
- A parallel system, with raw Markdown left durable, preserves GraphDB
  optionality. Do not reopen that.
- The six open questions are the right six.

### 1.2 Load-bearing error: the corpus is not investment-dominated

The brief says the residual corpus is "dominated by investment newsletters
(plus a minority of AI/tech and other letters)." That is false.

Independent audit of `/home/ftu/Obsidian/KDB/raw/joseph-ft-public-gmail`
(excluding `_promo/`), 2026-08-16:

| Fact | Measurement |
|---|---|
| Residual files | **2,659** (promo 1,530; tree total 4,189) |
| `content_kind` | 2,570 article / 77 video / 12 podcast |
| Body words | **4,207,609**; median 1,000; p95 4,245; max 45,152 |
| Distinct raw `author` strings | **117** |
| Author = `Substack` only | **212** (8.0%) |
| Files with `<50` body words | 25 |
| Frontmatter-bleed files | 3 |
| Date span | 2025-11-24 → 2026-08-15 |
| `word_count` frontmatter field | **does not exist** |

Author-name buckets (heuristic, conservative):

| Bucket | Files | Share |
|---|---|---|
| Politics / geopolitics named | 1,477 | **55.5%** |
| Investment named | 443 | **16.7%** |
| Other (mixed: some investors, some culture/tech) | 437 | 16.4% |
| Generic `Substack` | 212 | 8.0% |
| AI / tech named | 90 | 3.4% |

Largest cohorts are `Julian Vigo / Savage Minds` (224), `Robert Reich` (221),
`Glenn Diesen` (196), `The New Republic` (126), then `The Coal Trader` (122).
Investment voices such as `Compounding Quality` (86), `Rebound Capital` (31),
`TSOH` (25), `Michael Burry` (23), `Mr Deep-Value` (17) are real and
valuable — they are not the mass of the inbox.

Consequence: a system that treats every residual file as an investment-idea
source will spend most of its extraction and audit budget on political
commentary. **Corpus relevance is a first-class gate**, not a cleanup footnote.
The brief must be corrected before any implementation plan.

`4,189` also needs a one-line fix: it is 33 pre-existing files plus 4,156 newly
converted messages, not 4,156 files. The residual 2,659 are candidate sources,
not "full articles."

### 1.3 "Strongest idea" is the wrong objective as written

"Rank the strongest current investment ideas" can be read as predicted return.
That is not a job this system can honestly do, and it is not what Joseph asked
for. The achievable objective is:

> Rank records by **expected value of Joseph's next research hour**.

The system predicts "worth a closer look," never "this security will outperform."
That wording belongs in the schema name (`research_priority`) so later rankers
cannot quietly become market-forecasting models.

### 1.4 Joseph's labels are ground truth for one thing only

They establish personal usefulness and research priority. They do **not**
establish:

- extraction faithfulness (needs span validation + audit)
- factual correctness of a thesis (needs evidence, later outcomes)
- investment performance (needs time and a market series)

Any architecture that collapses those four into one "quality" score will learn
the wrong function.

### 1.5 "Author quality" is three variables

1. **Personal utility to Joseph** — learnable now from feedback.
2. **Analytical traits** — partly observable from extraction features
   (specificity, falsifiability, risk treatment).
3. **Track record** — not learnable from usefulness labels. It needs
   post-horizon outcome checks and time. Until those exist, this variable
   is empty and must stay empty.

Author reputation may inform ranking only with a **small, capped** weight at
the start. Otherwise the loudest political list will dominate the research
queue.

### 1.6 Success criteria are missing

The header promises success criteria. The body has goals. The brief needs
pass/fail gates before a blueprint. Proposed gates are in §5.

### 1.7 A useful addition the brief almost makes

Perishability is framed as a liability. It is also the cheapest path to
track record: when an idea's extracted horizon passes, ask Joseph
`hit / miss / expired / still-running`. That loop should be in scope for the
architecture even if v1 only logs the due date.

---

## 2. What "useful" requires of any architecture

A candidate that cannot do all four of these is the wrong family:

1. **Enumerate** current research-worthy ideas across the corpus (not merely
   retrieve some of them for a query).
2. **Separate** perishable ideas from compounding lessons.
3. **Learn** Joseph's priorities from a small labeled subset without
   pretending the labels are market truth.
4. **Leave** the unrelated majority searchable, without forcing it into an
   idea schema.

Retrieval can do (4) and a weak form of (3). It cannot do (1).
GraphDB classify-and-connect can do a distorted (2) at three LLM calls per
file, and will invent connections among unrelated letters — the 434
PendingLink invented slugs from the vault compile are the preview of that
failure mode on this corpus.

---

## 3. Three distinct architectures

These differ in primitive, not in library choice.

### Option A — Retrieval library

**Primitive:** index the Markdown; answer questions at query time.

- Deterministic FTS5 (and, only if measured later, embeddings).
- Optional query-time LLM synthesis over the top-k hits.
- Author ranking = folder/author facets + Joseph's pin list.
- No durable idea or lesson records.

| | |
|---|---|
| Serves | Open-ended Q&A: "what did Burry write about China?" |
| Cannot serve | A standing ranked idea list; a lesson library; a calibrated author model |
| Cost | Near-zero LLM for the backlog; pay per question |
| Reversibility | Highest. Index can be deleted. |
| Failure mode | Feels useful in demo, never produces "here are this week's ideas." |

Use later as a **read surface**. Do not use as the core.

### Option B — Extract-everything ledger

**Primitive:** one structured LLM extraction per residual file; store idea
mentions, lesson cards, and evidence; rank offline.

This is the companion draft's "Signal Ledger" and the DeepSeek response's
extract-all variant.

| | |
|---|---|
| Serves | Enumeration, lessons, feedback calibration, audit |
| Cost in dollars | Low. ~4.21M words on `deepseek-v4-flash` (`price_in` 0.14 / `price_out` 0.28 in `common/models.json`) is a low-single-digit-dollar pass |
| Cost in attention | High. The 100- and 500-file audit gates will be majority politics if the sample is representative |
| Failure mode | The ledger fills with forced "ideas" from Reich/Diesen/Mearsheimer. Ranking then fights its own inventory |

Dollars are not the scarce resource. Joseph's audit minutes are. Extracting
everything because inference is cheap contradicts the brief's own
human-in-the-loop requirement.

### Option C — Relevance-gated ledger (recommended)

**Primitive:** same ledger and ranker as B, with a cheap relevance gate
**before** idea/lesson extraction.

```text
Every residual Markdown file
        │
        ▼
Deterministic intake
  • repair 3 bleed files, normalize 117 author strings
  • paragraph IDs, content_kind, word count
  • FTS5 over the full residual corpus
        │
        ▼
Cheap relevance verdict (small model or rules+model)
  investment-bearing | lesson-bearing | mixed | info-only | residual-noise
        │
        ├─ info-only / noise ──► searchable, not extracted
        │
        └─ investment / lesson / mixed
                │
                ▼
        One structured extraction
          idea_mentions (0..N)
          lesson_cards  (0..N)
          validated evidence spans
                │
                ▼
        SQLite ledger
                │
                ▼
        Versioned deterministic ranker
          research queue   (ideas, decay by horizon)
          lesson library   (frameworks, spaced re-surface)
                │
                ▼
        Joseph feedback events + later outcome checks
                │
                ▼
        Weight calibration (hand-tuned → small pointwise model)
```

| | |
|---|---|
| Serves | Enumeration where it can exist; lessons where they exist; full-corpus search for the rest |
| Cost in dollars | Lower than B (extract ~20–40% of files if the gate is honest) |
| Cost in attention | Audit sample can be stratified on *relevant* files, so the schema is ratified against the actual job |
| Failure mode | A bad gate permanently suppresses a file. Mitigation: gate is reversible, logged, and overridable; FTS remains; Joseph can promote any file into extraction; a fixed exploration slice of "info-only" is extracted anyway |

Option C is not "Option B plus a flag." The gate changes what the ledger
*is*: a research instrument over a mixed inbox, not a forced ontology over
every email.

### Why not GraphDB-as-is

Already decided as a competing later experiment, not the v1 core. Three
calls per file, a compounding graph, and LINKS_TO among unrelated newsletters
optimize for the wrong structure. Keep the raw files. Do not spend the
compile budget to learn that.

### Why not author-first-only

A fourth family — rank new mail by author reputation and recency, extract
nothing — would triage the inbox cheaply and would not produce ideas. It is
a good **v0 slice of C's intake** (author normalization + reading order) and
a bad destination.

---

## 4. Recommended design (Option C)

### 4.1 Boundary

Parallel system. Input adapter reads the durable gmail-substack Markdown.
Owns its own SQLite file and journals. **Does not write** the KDB wiki,
manifest, or graph.

Place it as a **sibling package in this repo** (working directory name
`info_rank/` — replace when Joseph names it). Reuse `common/call_model` and
the model pool so cost telemetry is real. A later split into the previously
mentioned equity-research repo remains open; do not start there. Independence
is independent *state*, not a second copy of the LLM stack.

Export versioned JSONL/CSV so a future GraphDB comparison harness can consume
outputs without coupling.

### 4.2 Records

One SQLite file. Raw Markdown stays the source of truth.

- `articles` — path, hash, dates, `content_kind`, word count, cleanliness
- `authors` / `publications` — separate; 117 raw strings map into canonicals
- `relevance_verdicts` — gate output + model + prompt version
- `extraction_runs` — provenance, tokens, schema version
- `idea_mentions` — what **one** article claims
- `ideas` — clusters of compatible mentions; **never merge by ticker alone**
- `lesson_cards` / `frameworks`
- `evidence_spans` — paragraph id + exact quote; deterministic exists-in-source check
- `feedback_events` — immutable
- `outcome_checks` — post-horizon; may be empty in v1 except for due dates
- `score_snapshots` / `rankers` — versioned weights

An article may emit zero ideas and zero lessons. That is a valid, successful
extraction. Forcing at least one idea is a defect.

Corroboration (same thesis, independent authors) raises **salience**, not
merit. In investing, consensus is often crowding.

### 4.3 Extraction contract

For files that pass the gate:

- Relevance confirmation (the gate can be wrong; extraction may downgrade)
- Summary
- 0..N idea mentions: company/security, ticker if supported, stance, thesis,
  valuation premise, catalyst, risks / disconfirming evidence, horizon,
  perishability
- 0..N lesson cards: principle, context, reusable application, failure mode
- Evidence span for every substantive field

Unsupported spans fail the gate. They do not enter the ledger.

Video/podcast (89 files) and `<50`-word stubs (25) skip extraction by rule
and stay in FTS. No LLM.

### 4.4 Ranker

Separate scores, never one "quality":

- `idea_research_priority`
- `lesson_learning_value`
- `article_reading_priority`
- `author_personal_utility`

Initial idea features: specificity, evidence, valuation discipline,
falsifiability, risk treatment, horizon clarity, freshness vs horizon,
independent corroboration, novelty, extraction uncertainty, capped author
utility.

Weights are human-readable and versioned. Changing them never re-extracts.

Ideas decay toward their horizon, then leave the research queue for the
outcome list. Lessons do not decay; they re-surface on a long interval.

### 4.5 Feedback loop (minimal)

Immutable events, not editable stars:

- `research` / `save` / `skip` / `wrong-extraction` / `promote-to-extract`
- optional 1–5 usefulness and reason tags
- optional pairwise "which of these two first?"
- ranker version, score, and display position at collection time

Reserve a fixed slice of every review batch for uncertain, diverse, and
random items. Top-only labels are a biased training set.

Start with hand-tuned weights. After ~200 representative labels, fit a small
regularized pointwise model. Do not start with learning-to-rank.

### 4.6 Cold start vs steady state

**Backlog.** Do not extract 2,659 files on day one.

1. Intake + FTS + author normalization over all 2,659 (deterministic).
2. Relevance gate over all 2,659 (cheap).
3. Stratified **relevant** pilot, ~100–150 files, to ratify the extraction
   schema.
4. Extract 100 → audit faithfulness → extract 500 → audit → remaining
   relevant files.
5. Hold a small labeled "info-only" sample so the gate's false-negative rate
   is measured, not hoped.

**Weekly inflow.** Same path, incremental. Tens of files. Joseph reviews the
new research queue, not the raw inbox.

### 4.7 Cost envelope

Full extract-all (Option B) is ~$1–3 at registry prices. Option C is less.
Neither number is the decision. The binding costs are:

- Joseph minutes per accepted idea
- schema-revision cycles after a bad audit
- false ideas that consume research time

The 100-file pilot must record tokens, retries, latency, dollars, span-validity,
and review minutes, then extrapolate before the 500-file gate.

Keep deterministic work deterministic: identity cleanup, FTS, decay,
ticker-level clustering. No embeddings in v1 unless a later evaluation shows
FTS plus structured fields missing queries Joseph actually asks.

---

## 5. Evaluation and comparison to GraphDB

Predeclare before building:

| Axis | Metric |
|---|---|
| Ranking | nDCG@10 on Joseph's labeled priorities; top-10 `research`/`save` rate |
| Diversity | sector / author concentration in the top 10 |
| Faithfulness | span-validity rate; `wrong-extraction` rate; zero unvalidated spans |
| Gate quality | precision/recall of relevance vs a hand-labeled 150-file set |
| Recall | extracted ideas/lessons vs the pilot's hand audit |
| Attention | review minutes per accepted idea; $ per accepted idea |
| Head-to-head | same probe set, same metrics, GraphDB compile vs this ledger, via stable exports |

Baselines the ranker must beat: recency-only, author-only, BM25 over titles.

v1 is a success if, after the 500-file gate, Joseph will use the research
queue instead of the raw folder for weekly triage, and span-validity is
≥95% on audit. It is a failure if the top 10 is dominated by political
essays or by one author's house style.

---

## 6. Direct answers to the six open questions

| # | Answer |
|---|---|
| 1 Core architecture | Relevance-gated extraction ledger. Retrieval is a read surface over all files. Active learning later calibrates the ranker and the gate; it does not choose what exists. |
| 2 Learning loop | Immutable events with exposure context + pairwise comparisons + a later outcome queue. Hand-tuned weights until ~200 labels, then a small pointwise model. Exploration quota against selection bias. |
| 3 Data model | One SQLite file + FTS5. Records in §4.2. Vectors deferred. Raw Markdown remains immutable. |
| 4 Cold start vs steady state | Index everyone; extract only the relevant subset, quality-gated 100 → 500 → rest. Weekly: incremental extract → cluster → recompute. |
| 5 Cost discipline | Dollars are small either way. Spend LLM on relevant files. Spend Joseph on audited relevant files. Deterministic everywhere else. |
| 6 Evaluation | §5. Compare to GraphDB only through a shared probe set and stable exports. |

---

## 7. Where this diverges from the DeepSeek seat

Agreed: ideas vs lessons; research-EV objective; three-way author quality;
extract-once / score-many; evidence spans; immutable feedback; FTS before
vectors; sibling reuse of `call_model`; outcome loop as a high-leverage
addition.

**Disagreed: extract the whole residual corpus.** DeepSeek treats ~$1–3 as
reason to extract 2,659 files and only gate *quality*. That ignores the
measured mix: the majority of files are not investment letters. Extracting
them pollutes the ledger and wastes the only scarce input — Joseph's audit.
The gate is the architecture, not an optimization.

---

## 8. Decision gate

Recommend **Option C**. Next Architecture-phase actions if Joseph selects it:

1. Patch the problem statement with the corpus corrections in §1.2–1.6.
2. File a unique task ID in `docs/TASKS.md`.
3. Record the parallel-system boundary in `docs/CODEBASE_OVERVIEW.md`.
4. Write the technical blueprint, implementation plan, and TDD gates.
5. Wait for explicit **Proceed** before any code.

If Joseph prefers Option B (extract all), the same ledger design stands and
only the coverage policy changes. If he prefers Option A, stop after FTS and
do not pretend ranking exists.
