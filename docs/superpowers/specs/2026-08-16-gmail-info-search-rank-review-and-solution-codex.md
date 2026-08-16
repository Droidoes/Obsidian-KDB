# Gmail/Substack search-and-rank — review and solution proposal

> **Status:** architecture review and proposed solution (2026-08-16). This is a
> deliberation artifact, not a ratified architecture. It reviews
> [`2026-08-16-gmail-info-search-rank-problem-statement.md`](2026-08-16-gmail-info-search-rank-problem-statement.md)
> and recommends a direction for Joseph's decision.

## Executive conclusion

The brief identifies the right problem, but it is not yet panel-ready. Its biggest
gap is that "strongest investment idea" and "author quality" are undefined. The
recommended architecture is an extraction-first, SQLite-backed **Signal Ledger**:
extract durable idea and lesson records once, then rank them repeatedly using
transparent, feedback-calibrated scoring.

## 1. Review findings

The problem framing is strong in four places:

- It correctly separates perishable ideas from compounding lessons.
- It makes Joseph's feedback a first-class requirement.
- It keeps the new system independent from Obsidian-KDB.
- It preserves raw sources and future GraphDB optionality.

Before panel review, correct the following issues.

### 1.1 Change the ranking objective

"Strongest current investment ideas" could mean predicted investment return. The
achievable objective is:

> Rank ideas by expected value of further research—not by predicted investment
> performance.

### 1.2 Bound what Joseph's judgment establishes

Joseph's labels are ground truth for personal usefulness and research priority. They
cannot establish factual truth, extraction faithfulness, or investment outcomes.
Those require separate evaluation axes.

### 1.3 Split "author quality" into three concepts

- Usefulness to Joseph
- Analytical/writing characteristics
- Real investment track record

Only the first can initially be learned from Joseph's feedback. Track record requires
market data, time horizons, and outcome measurement.

### 1.4 Correct the corpus description

- `4,189` means 33 pre-existing files plus 4,156 newly converted messages.
- The residual files are "candidate articles," not necessarily "full articles."
- The claimed `word_count` frontmatter field does not exist in the inspected files.
- The remaining corpus contains about **4.28 million words**: median 1,028/article,
  p95 4,334, maximum 45,177.
- Author identity is not clean: 117 distinct raw author strings and 212 articles
  attributed only to `Substack`.
- The claim that investment letters dominate should be measured. Several of the
  largest author cohorts are political or geopolitical.

### 1.5 Add measurable success criteria

The problem-statement header says the document includes success criteria, but it
currently contains goals rather than pass/fail gates.

## 2. Architectural options

| Option | Core design | Strength | Structural weakness |
|---|---|---|---|
| **A. Retrieval-first library** | Full-text/vector index; answer questions with query-time LLM synthesis | Cheapest and fastest; excellent open-ended search | Cannot reliably enumerate all ideas or maintain a durable ranking/author model |
| **B. Structured extraction ledger** | One LLM extraction per article into durable idea, lesson, evidence, and feature records; deterministic ranking afterward | Directly satisfies idea ranking, author learning, lessons, auditability, and corpus-wide enumeration | Requires an extraction schema and backlog processing |
| **C. Active-learning prioritizer** | Human labels train a classifier/ranker that decides which articles deserve processing | Strong personalization and potentially low steady-state cost | Cold-start problem; can permanently miss lessons and ideas in articles it suppresses |

Option C becomes valuable later, but it should learn over the records produced by
Option B—not replace them. Option A should also exist as a read surface over the
ledger, not as the core architecture.

## 3. Recommended solution: Structured Signal Ledger

The governing principle is:

> Extract once, preserve evidence, score many times.

```text
Raw Markdown
    ↓
Deterministic intake + identity cleanup
    ↓
One structured LLM extraction
    ├── Article assessment
    ├── 0..N idea mentions
    ├── 0..N lesson cards
    └── source-grounded evidence spans
    ↓
SQLite ledger + full-text index
    ↓
Versioned deterministic ranker
    ↓
Research queue / learning queue / author profiles
    ↓
Joseph feedback events
    ↓
Weight calibration + active-learning selection
```

### 3.1 System boundary

Build the Signal Ledger as the already-decided separate, parallel system. Its input
adapter reads the durable Gmail/Substack Markdown sources. It owns its own SQLite
database and processing journals and does not write into the Obsidian-KDB wiki,
manifest, or graph.

Expose versioned JSONL/CSV exports so a future comparison harness or GraphDB consumer
can use its outputs without coupling either system internally.

### 3.2 Storage

Use one local SQLite database as the system of record, with raw Markdown remaining
the immutable source corpus.

Core records:

- `articles`
- `authors` and `publications`, modeled separately
- `processing_runs`
- `article_assessments`
- `idea_mentions`
- `idea_clusters`
- `lesson_cards`
- `evidence_spans`
- `feedback_events`
- `score_snapshots`

An article can emit multiple ideas and lessons. An `idea_mention` is what one article
claims; an `idea_cluster` groups compatible mentions across articles. Never merge by
ticker alone—a bullish valuation thesis and bearish accounting thesis about the same
company are different ideas.

Use SQLite FTS5 for keyword search across articles, ideas, lessons, and evidence. At
this corpus size, duplicating searchable text is simpler and safer than
external-content synchronization. FTS5 provides BM25 ranking and supports external or
contentless designs if scale later warrants them. See the
[SQLite FTS5 documentation](https://www.sqlite.org/fts5.html).

Do not add embeddings to v1. Add a vector-index adapter only if an evaluation proves
that FTS plus structured fields misses semantic queries that matter.

### 3.3 Extraction contract

Each article should produce:

- Corpus relevance: investment, learning, mixed, unrelated, or residual noise
- Author and publication normalization candidates
- Article summary
- Zero or more idea mentions:
  - company/security
  - ticker when supported
  - stance
  - thesis
  - valuation premise
  - catalyst
  - risks and disconfirming evidence
  - time horizon
  - perishability/expiry estimate
- Zero or more lesson cards:
  - principle
  - context
  - reusable application
  - failure mode or counterexample
- Evidence references for every substantive extraction

Evidence should use paragraph IDs plus exact source spans. A deterministic validator
must prove each quoted span exists in the source. Unsupported output fails the
extraction gate rather than quietly entering the ledger.

### 3.4 Ranking model

Maintain separate scores rather than one opaque "quality" number:

- `idea_research_priority`
- `lesson_learning_value`
- `article_reading_priority`
- `author_personal_utility`

Initial idea features should include:

- Thesis specificity
- Evidence quality
- Valuation discipline
- Falsifiability
- Risk treatment
- Catalyst and horizon clarity
- Freshness relative to the extracted horizon
- Independent-source corroboration
- Novelty and fit for Joseph
- Extraction uncertainty

Author reputation should initially have a small, capped influence to avoid a
rich-get-richer loop.

Weights remain human-readable and versioned. Changing ranking weights must never
require re-extracting the articles.

### 3.5 Feedback loop

Store feedback as immutable events, not mutable ratings:

- `research`, `save`, `skip`, or `wrong extraction`
- usefulness score
- reason tags
- optional comparison: "Which of these two deserves research first?"
- score and display position shown when feedback was collected

Logging exposure and position matters because feedback only on top-ranked items
creates selection bias. Reserve part of the review queue for uncertain, diverse, and
randomly sampled records.

Start with transparent hand-tuned weights. Once enough representative labels exist,
fit a small regularized model. A sophisticated learning-to-rank model such as
LambdaMART should be deferred until there are meaningful query groups and graded
labels; its own documentation notes that learning-to-rank is nontrivial. See the
[XGBoost learning-to-rank documentation](https://xgboost.readthedocs.io/en/release_3.2.0/tutorials/learning_to_rank.html).

## 4. Delivery sequence

### Phase 1 — Corpus audit and labeling protocol

- Measure source mix, author identity quality, residual noise, and content lengths.
- Define exactly what Joseph labels at article, idea, and lesson level.

### Phase 2 — Stratified pilot

- Select roughly 100–150 articles across authors, dates, lengths, and apparent
  topics.
- Ratify the extraction schema against this sample before processing the backlog.

### Phase 3 — Extraction gate

- Run 100 articles, manually audit outputs, and revise the schema.
- Then process 500 articles.
- Process the remaining backlog only after the 500-record gate passes.

### Phase 4 — Ranking baseline

- Compare against simple baselines: recency-only, author-only, and FTS/BM25.
- Evaluate `nDCG@10`, top-10 research/save rate, extraction recall, evidence
  faithfulness, diversity, cost, and human review time.

### Phase 5 — Steady state

- New article → extract once → update clusters → compute scores.
- Produce separate "research now," "lessons worth learning," and "exploration"
  queues.

## 5. Cost assessment

At approximately 4.28 million source words, a one-call extraction pass is likely a
low-single-digit-dollar job using the current local `deepseek-v4-flash` registry price
of $0.14/M input and $0.28/M output tokens. The real risk is extraction quality and
human validation time, not raw inference cost.

The 100-article pilot should capture actual token, retry, latency, and cost telemetry
and extrapolate the backlog total before the 500-article and full-corpus gates.

## 6. Recommendation and decision gate

Recommend **Option B: Structured Signal Ledger**, with retrieval as a read interface
and active learning added later to its ranker.

This recommendation is not ratified by this document. If Joseph selects it, the next
Architecture-phase actions are:

1. Revise the problem statement with the review corrections.
2. File the work in `docs/TASKS.md` with a unique task ID.
3. Record the selected system boundary in `docs/CODEBASE_OVERVIEW.md`.
4. Produce the detailed technical blueprint, implementation plan, and TDD gates.
5. Request explicit **Proceed** confirmation before implementation.
