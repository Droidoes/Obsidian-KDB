# 1. Review of the problem statement

The brief correctly identifies the core tension:

> The Gmail-Substack corpus is not primarily a knowledge-compounding corpus.  
> It is a large, growing stream of perishable investment signals plus a smaller set of compounding lessons.

That makes the existing Obsidian-KDB classify-and-connect pipeline a poor default fit for this corpus, because that pipeline is optimized for durable, interrelated knowledge, not for ranking noisy, time-sensitive investment ideas.

The most important requirements are:

1. **Rank ideas**  
    Surface the strongest current investment ideas from thousands of letters.
2. **Rank authors**  
    Learn which writers consistently produce useful signal.
3. **Extract lessons**  
    Preserve durable frameworks, mistakes, mental models, and process insights.
4. **Human-in-the-loop learning**  
    Joseph’s judgments must become the ground truth that improves the system.
5. **Cost discipline**  
    The system must not require expensive full LLM treatment for every article.
6. **Separate but option-preserving**  
    It should be independent from the Obsidian-KDB pipeline, but not foreclose future integration.

I would slightly sharpen the problem statement by adding three explicit artifacts:

- **Evaluation schema**: what exactly Joseph rates.
- **Ranking snapshots**: what the system recommended at what time, and why.
- **Cost ledger**: how much each pipeline run cost.

With that in mind, the recommended solution is below.

---

# 2. Proposed solution: “Signal Ledger”

Working name: **Signal Ledger**  
Alternative names: LetterRank, Idea Ledger, Substack Triage Engine.

## Core idea

Build a separate **rank-and-learn** system, not a knowledge-graph-first system.

The system should act as a filter:

> It turns a firehose of newsletter articles into a ranked queue of investment ideas, author reputations, and durable lessons.

It should have two speeds:

1. **Fast layer: Ideas**
    - Perishable
    - Ticker/company-centric
    - Ranked by strength, recency, author quality, novelty, and Joseph’s learned preferences
2. **Slow layer: Lessons**
    - Compounding
    - Frameworks, mistakes, mental models, process insights
    - Periodically distilled into durable “playbook” notes

Author quality sits between the two as a learned prior.

---

# 3. Recommended architecture

The system should be a lightweight local pipeline, preferably Python + SQLite, with optional local or API embeddings.

## High-level pipeline

Raw markdown articles
        |
        v
Ingest / Normalize
        |
        v
Deterministic Feature Extraction
        |
        v
Chunking / Embedding / Search Index
        |
        v
Triage Classifier
        |
        +--> likely idea? --> Idea Extraction
        |
        +--> likely lesson? --> Lesson Extraction
        |
        +--> noise / weak? --> suppress
        |
        v
Idea Ledger + Author Profiles + Lesson Library
        |
        v
Ranking Engine
        |
        v
Review Queue / Weekly Digest
        |
        v
Joseph’s evaluations
        |
        v
Model update / ranking improvement

The system should be built around three planes:

---

## A. Evidence plane

This preserves the raw evidence and makes it searchable.

Artifacts:

- Original markdown files
- Article metadata
- Chunks
- Embeddings
- Detected tickers/companies
- Deduplication fingerprints

Substrate:

- SQLite for metadata
- Vector index for embeddings, e.g. `sqlite-vec`, LanceDB, or a simple local embedding store
- Markdown remains the durable source of truth

---

## B. Signal plane

This extracts structured signals from articles.

Three primary record types:

### 1. Idea

An investment idea is not an article. An article can contain zero, one, or several ideas.

An idea record should contain:

- Ticker/company
- Long/short/neutral stance
- Thesis summary
- Supporting argument
- Catalysts
- Risks
- Valuation angle
- Time horizon
- Evidence quotes from the article
- Author
- Publication
- Date
- Expiry/decay status
- Model score
- Joseph rating, if any

Example JSON-like structure:

```
{
  "idea_id": "idea_000123",
  "source_file": "KDB/raw/joseph-ft-public-gmail/...",
  "author": "Author Name",
  "publication": "Newsletter Name",
  "date": "2026-07-14",
  "company": {
    "ticker": "XYZ",
    "name": "XYZ Corp"
  },
  "stance": "long",
  "thesis": "Company is mispriced because market underestimates recurring revenue durability.",
  "argument": [
    "High retention",
    "Conservative accounting",
    "Insider buying"
  ],
  "catalysts": [
    "Margin inflection",
    "Divestiture",
    "Guidance change"
  ],
  "risks": [
    "Customer concentration",
    "Competition"
  ],
  "timeframe": "6-18 months",
  "evidence_quotes": [
    "The company has retained 95% of revenue for three years..."
  ],
  "confidence": 0.72
}
```

### 2. Lesson

A lesson is durable knowledge.

Examples:

- “Avoid turnarounds unless management has skin in the game.”
- “High ROIC is fragile without switching costs.”
- “Most value traps are caused by deteriorating unit economics, not bad multiples.”
- “The author’s best ideas came from boredom, not novelty.”

A lesson record should contain:

- Lesson type: framework, mistake, mental model, process, psychology
- Principle
- Evidence quotes
- Author
- Source article
- Tags
- Related lessons
- Joseph usefulness rating

### 3. Author profile

Author profiles should track:

- Canonical author name
- Aliases
- Publication
- Style tags
- Sector focus
- Historical usefulness
- Explicit Joseph ratings
- Implicit acceptance rate
- Idea frequency
- Idea quality
- Lesson quality
- Consistency
- Credibility score

Author quality should be a learned prior, not a static label.

---

## C. Judgment plane

This is the most important part.

The judgment plane stores:

- Joseph’s ratings
- Ranking snapshots
- Model versions
- Feature values
- Prompt versions
- Cost estimates
- Evaluation metrics

This is what makes the system improve over time.

---

# 4. Data model

Primary substrate: **SQLite**.

SQLite is sufficient, auditable, portable, and local. Graph and vector stores can be added later, but should not be required for the MVP.

Recommended tables:

---

## `sources`

One row per markdown article.

Fields:

- `source_id`
- `file_path`
- `sha256`
- `gmail_id`
- `title`
- `author_raw`
- `author_id`
- `publication`
- `date`
- `source_url`
- `content_kind`
- `word_count`
- `processed_at`
- `processing_status`
- `triage_class`
- `triage_score`

---

## `authors`

Fields:

- `author_id`
- `canonical_name`
- `aliases`
- `publication`
- `style_tags`
- `sector_focus`
- `author_prior_score`
- `explicit_rating_mean`
- `implicit_acceptance_rate`
- `idea_count`
- `lesson_count`
- `last_updated`

---

## `chunks`

Fields:

- `chunk_id`
- `source_id`
- `chunk_index`
- `text`
- `token_count`
- `embedding_id`

---

## `embeddings`

Fields:

- `embedding_id`
- `chunk_id`
- `model`
- `vector`
- `created_at`

If using `sqlite-vec`, vectors can live in a virtual table.

---

## `ideas`

Fields:

- `idea_id`
- `source_id`
- `author_id`
- `company_name`
- `ticker`
- `stance`
- `thesis_summary`
- `argument`
- `catalysts`
- `risks`
- `valuation_angle`
- `timeframe`
- `evidence_quotes`
- `confidence_raw`
- `score`
- `status`
- `expires_at`
- `created_at`
- `updated_at`

Status examples:

- `candidate`
- `ranked`
- `reviewed`
- `researched`
- `watched`
- `expired`
- `dismissed`

---

## `lessons`

Fields:

- `lesson_id`
- `source_id`
- `author_id`
- `lesson_type`
- `principle`
- `explanation`
- `evidence_quotes`
- `tags`
- `score`
- `created_at`
- `updated_at`

---

## `evaluations`

This is the ground-truth table.

Fields:

- `evaluation_id`
- `target_type`: `article`, `idea`, `author`, `lesson`
- `target_id`
- `rating`
- `labels`
- `note`
- `context`
- `created_at`
- `model_version`
- `rank_position`

Suggested rating scale:

0 = Noise / irrelevant
1 = Weak / not worth research
2 = Interesting but not actionable
3 = Strong / deserves research time

Optional labels:

- `idea`
- `lesson`
- `author_insight`
- `macro`
- `company_specific`
- `process`
- `mistake_postmortem`
- `too_speculative`
- `too_obvious`
- `already_known`
- `high_quality_writing`

---

## `rank_runs`

Fields:

- `run_id`
- `run_date`
- `model_version`
- `prompt_version`
- `cost_estimate`
- `notes`

---

## `rank_entries`

Fields:

- `run_id`
- `target_type`
- `target_id`
- `score`
- `rank`
- `features_json`

This table is essential for auditing why the system ranked something highly.

---

## `author_metrics`

Fields:

- `author_id`
- `as_of_date`
- `explicit_rating_mean`
- `bayesian_author_score`
- `idea_acceptance_rate`
- `lesson_usefulness`
- `volume`
- `recent_quality`
- `style_tags`

---

# 5. Processing model

The system should not treat every article equally.

Use a tiered processing model.

---

## Tier 0: Deterministic ingest

For every article:

- Parse markdown/frontmatter
- Extract title, date, author, URL, Gmail ID
- Normalize author/publication
- Deduplicate by Gmail ID, URL, hash, title/date
- Compute word count
- Detect tickers/company mentions
- Detect boilerplate/unsubscribe/promo patterns
- Detect truncation/paywall markers
- Tag obvious noise

This tier should be free or nearly free.

---

## Tier 1: Embedding and retrieval

For every article:

- Chunk article into 500–1,000 token chunks
- Generate embeddings
- Store vectors
- Detect near-duplicates
- Detect topic clusters
- Compute similarity to known high-quality articles
- Support semantic search

This tier should be cheap and used broadly.

Embeddings are useful for:

- Finding similar ideas
- Detecting repeated pitches
- Clustering lessons
- Searching by concept, not just ticker
- Computing novelty scores

---

## Tier 2: Cheap triage

For every article or most articles:

Use a low-cost LLM or local classifier to answer:

Is this article primarily:
- investment idea
- company analysis
- lesson/process/framework
- market commentary
- macro
- noise
- promotional
- truncated/paywalled

Also estimate:

- Likely usefulness
- Presence of actionable thesis
- Presence of durable lesson
- Author style hints

This can be one compact structured call, not three calls per source.

Output:

{
  "content_class": "investment_idea",
  "idea_probability": 0.82,
  "lesson_probability": 0.15,
  "noise_probability": 0.03,
  "likely_tickers": ["XYZ"],
  "summary": "Bull case for XYZ based on...",
  "quality_heuristic": 0.68
}

## Tier 3: Structured extraction

Only for articles above a threshold, or for sampled articles used for evaluation.

This is where the system extracts full idea or lesson structure.

Use the standing low-cost production model first, e.g. `deepseek-v4-flash`.

Extraction requirements:

- Must return structured JSON
- Must include evidence quotes
- Must not invent tickers
- Must distinguish mention from thesis
- Must identify stance: long, short, neutral, watchlist
- Must identify whether the article contains a durable lesson

The extractor should be conservative:

> Better to mark uncertain than to fabricate.

---

## Tier 4: Deep synthesis

Only for top-ranked or strategically important items.

Examples:

- Top 50 ideas across the backlog
- Top authors
- Recurring lessons
- Cross-author comparisons
- Weekly digest generation
- Playbook compilation

This tier can use a stronger model, but should be capped.

---

# 6. Idea ranking

The system should rank ideas, not merely articles.

## Initial heuristic score

Start with an explainable weighted score:

idea_score =
    0.30 * author_prior
  + 0.25 * thesis_quality
  + 0.15 * recency_decay
  + 0.10 * novelty
  + 0.10 * evidence_strength
  + 0.05 * consensus_signal
  + 0.05 * actionability

This is only the cold-start formula. It should later be replaced or calibrated by Joseph’s evaluations.

---

## Feature definitions

### `author_prior`

A Bayesian author-quality score.

Formula concept:

author_prior =
  (C * global_mean_rating + sum(author_ratings)) / (C + n_ratings)

Where:

- `C` is shrinkage strength
- `global_mean_rating` is the average rating across all evaluated articles
- `n_ratings` is the number of Joseph ratings for that author

This prevents low-sample authors from dominating or being unfairly punished.

---

### `thesis_quality`

LLM-assessed or learned from Joseph ratings.

Signals:

- Specificity
- Falsifiability
- Clear business understanding
- Valuation awareness
- Catalyst awareness
- Risk awareness
- Asymmetry
- Evidence quality
- Absence of hype

---

### `recency_decay`

Ideas are perishable.

Use exponential decay:

recency_decay = exp(-age_days / half_life_days)

Suggested half-life:

- 30 days for event-driven ideas
- 60–90 days for fundamental ideas
- Longer for watchlist/quality-compounder ideas

The half-life can vary by idea type.

---

### `novelty`

If the same thesis has appeared many times recently, reduce marginal score.

But do not eliminate consensus completely.

Use embedding similarity to previous ideas:

- Highly duplicate: penalty
- Similar but with new evidence: mild penalty
- Contrarian or differentiated: bonus

---

### `evidence_strength`

Based on:

- Number of supporting quotes
- Specificity of facts
- Quantitative support
- Management/insider/financial evidence
- Logical coherence

---

### `consensus_signal`

If multiple independent high-quality authors pitch the same idea, that may increase confidence.

But avoid creating a consensus bubble.

Use author-weighted consensus:

consensus_signal = weighted_count_of_independent_high_quality_mentions

### `actionability`

Signals:

- Is ticker clear?
- Is the company investable?
- Is the thesis researchable?
- Is there a clear entry point for further work?
- Is it too late or too event-driven?

---

# 7. Author ranking

Author ranking should not be a simple average rating.

It should combine:

1. **Explicit Joseph ratings**
2. **Idea acceptance rate**
3. **Lesson usefulness**
4. **Consistency over time**
5. **Originality**
6. **Calibration**
7. **Style fit**

## Author score components

author_score =
    explicit_rating_score
  + idea_acceptance_rate
  + lesson_usefulness
  + consistency_score
  + originality_score
  - hype_penalty

Use Bayesian shrinkage to handle small samples.

## Author style tags

Examples:

- Deep value
- Quality compounders
- Special situations
- Activism
- Macro
- Tech
- Healthcare
- Energy
- Behavioral/process
- Post-mortem
- Short-selling
- Quantitative
- Narrative-driven

Style tags help with reading triage.

For example:

> “Show me high-quality process lessons from authors I rate highly.”

or:

> “Show me current special-situation ideas from authors with high calibration.”

---

# 8. Lesson extraction and compounding

Lessons should not be forced from every article.

The system should identify likely lesson articles using signals such as:

- Post-mortem language
- Mistake language
- Framework language
- Process language
- “What I learned”
- “What I missed”
- “Mental model”
- “Risk management”
- “Portfolio construction”
- “Checklist”

Lesson record types:

1. **Framework**
    - A reusable analytic method
2. **Mental model**
    - A general principle for thinking
3. **Mistake post-mortem**
    - What went wrong and why
4. **Process insight**
    - How the writer works
5. **Risk lesson**
    - What to avoid
6. **Behavioral lesson**
    - Psychology, discipline, bias

## Lesson distillation cycle

Do not synthesize lessons immediately from the whole backlog.

Instead:

1. Extract candidate lessons
2. Embed and cluster them
3. Let Joseph rate useful ones
4. Periodically distill clusters into durable notes
5. Store distilled notes in a “Playbook” or “Lessons Library”

Example lesson cluster:

Theme: Value traps
- Lesson 1: Cheap multiples are not enough if unit economics are declining.
- Lesson 2: High dividend yield can mask capital allocation failure.
- Lesson 3: Cyclical peak earnings often look cheap.

Distilled output:

# Value Trap Checklist

1. Check whether margins are structurally impaired.
2. Check whether capital allocation is value-destructive.
3. Check whether earnings are cyclically inflated.
4. Check whether the business has pricing power.
5. Check whether management is rational capital allocators.

Sources:
- Author A, 2025-03-14
- Author B, 2025-08-02
- Author C, 2026-01-21

This is where the corpus compounds.

---

# 9. Human-in-the-loop learning loop

This must be a first-class citizen.

The minimal viable loop is:

System ranks items
        |
        v
Joseph reviews a small queue
        |
        v
Joseph gives explicit ratings
        |
        v
Ratings are stored with context
        |
        v
Ranking model is retrained/calibrated
        |
        v
System improves

## Step 1: Create evaluation schema

Use a simple scale:

0 = Noise
1 = Weak
2 = Interesting
3 = Strong / research-worthy

Optional idea-level labels:

- `too_late`
- `too_obvious`
- `too_speculative`
- `not_investable`
- `already_known`
- `good_but_not_for_me`
- `strong_thesis`
- `worth_research`
- `author_insightful`

Optional lesson-level labels:

- `durable`
- `useful_checklist`
- `good_postmortem`
- `too_generic`
- `already_internalized`

---

## Step 2: Seed evaluations

Before trying to optimize the system, Joseph should rate a stratified sample.

Suggested seed sample:

- 100–200 articles total
- Sample across:
    - Authors
    - Dates
    - Lengths
    - Ticker density
    - Content types
    - Triage scores

Do not rate only top-ranked articles. That creates feedback bias.

Suggested seed composition:

- 50 articles chosen randomly
- 50 articles chosen by heuristic score
- 50 articles from known high-prior authors
- 50 articles from uncertain or low-author-signal sources

This gives the system both positive and negative examples.

---

## Step 3: Build a review queue

The review queue should show:

- Article title
- Author
- Date
- Model score
- Why it was ranked highly
- Detected tickers
- Extracted thesis, if available
- Evidence snippet
- Quick rating controls

The queue can be:

- CLI
- Local web UI
- Markdown export
- Simple TUI

For MVP, even a generated Markdown file with rating commands is acceptable.

Example:

## 2026-08-16 Review Queue

### 1. XYZ Corp — Author Name — 2026-08-10
Score: 0.83
Why: High author prior, clear catalyst, novel thesis
Ticker: XYZ
Thesis: Market misses recurring revenue durability.
Evidence: "Retention has remained above 95%..."

Rating: [ ] 0 [ ] 1 [ ] 2 [ ] 3
Notes:

## Step 4: Active learning

After the seed set, do not ask Joseph to rate randomly.

Use active learning to choose the next items.

Sample from:

1. **High uncertainty**
    - Model is unsure whether article is strong
2. **High score**
    - Validate that top-ranked items are actually good
3. **Underrepresented authors**
    - Avoid author bias
4. **New inflow**
    - Ensure production relevance
5. **Diverse clusters**
    - Avoid duplicate ratings of the same thesis

Suggested weekly review volume:

- 20–40 items per week
- 5–10 minutes per day
- Mix:
    - 70% high-ranked/uncertain
    - 20% random exploration
    - 10% author-quality checks

---

## Step 5: Train the ranking model

Start simple.

### MVP model

Use logistic regression or ordinal regression to predict Joseph rating from features.

Features:

- Author prior
- Article length
- Ticker density
- Presence of quantified thesis
- Embedding similarity to previously strong articles
- Embedding distance to noise articles
- Recency
- Content class probabilities
- LLM thesis-quality estimate
- Author historical rating
- Cluster novelty

Later, if enough data accumulates:

- Pairwise ranking model
- Gradient-boosted ranker
- Learned weights
- LLM-as-judge calibrated on Joseph ratings

But do not start with complex learning-to-rank.

Start with explainable weights and manual calibration.

---

## Step 6: Validate

Use time-based validation, not random shuffling.

Why?

Because the system will be used in production over time.

Example:

- Train on ratings from articles before date X
- Validate on articles after date X

Metrics:

- Precision@10
- Precision@20
- NDCG@10
- NDCG@20
- Calibration error
- Fraction of top-20 items rated 2 or 3
- Cost per useful item
- Author diversity
- Idea diversity

Success criterion:

> The system should beat simple baselines such as “newest first”, “author prior only”, and “ticker density only”.

---

# 10. Cold start vs steady state

## Cold start: 2,659 backlog articles

Do not process the entire backlog with full LLM extraction immediately.

Use a phased backlog plan.

### Phase 1: Inventory

For all 2,659 articles:

- Parse metadata
- Normalize authors
- Detect tickers
- Compute embeddings
- Cluster articles
- Build source table
- Build author table

Cost: low.

### Phase 2: Seed evaluation

Select 100–200 stratified articles for Joseph to rate.

Cost: minimal LLM, mostly human time.

### Phase 3: Triage all articles

Run cheap triage on all articles.

Output:

- likely idea
- likely lesson
- likely commentary
- likely noise
- likely weak

Cost: moderate.

### Phase 4: Extract high-value subset

Extract structured ideas only from:

- Articles with high triage score
- Articles from promising authors
- Recent articles, because ideas are perishable
- Articles in dense idea clusters
- Articles Joseph has marked useful
- Articles similar to marked-useful articles

Likely extraction subset:

- 300–800 articles initially

Cost: controlled.

### Phase 5: Build first leaderboard

Generate:

- Top 20 ideas
- Top 20 lessons
- Top 20 authors
- Top 10 clusters

Joseph reviews and rates.

### Phase 6: Iterate

Retrain or recalibrate ranking.

---

## Steady state: weekly inflow

For each new batch of articles:

1. Ingest new markdown files
2. Deduplicate
3. Compute deterministic features
4. Embed
5. Triage
6. Extract if above threshold
7. Update idea ledger
8. Update author profiles
9. Update rankings
10. Generate weekly digest

Weekly digest should include:

# Weekly Signal Digest

## Top New Ideas
1. Ticker — Author — one-line thesis — score
2. ...

## Rising Authors
- Author: reason

## Persistent Lessons
- Lesson: source

## Duplicate/Overhyped Themes
- Theme: why suppressed

## Review Queue
- 20 items for evaluation


# 11. Cost discipline

Cost should be controlled by tiering.

## Cost principles

1. **Do not run full LLM extraction on every article by default.**
2. **Use deterministic rules for metadata, tickers, dedupe, and promo/noise.**
3. **Use embeddings for search, clustering, and novelty.**
4. **Use low-cost LLM for triage.**
5. **Use extraction only for likely valuable articles.**
6. **Use stronger models only for synthesis or difficult cases.**
7. **Cache everything.**
8. **Never reprocess unchanged files.**
9. **Every run should estimate token cost before applying.**

---

## Suggested cost tiers

### Tier 0: Deterministic

Applies to: 100% of articles  
Cost: near zero

### Tier 1: Embeddings

Applies to: 100% of articles  
Cost: low

### Tier 2: Cheap triage

Applies to: 100% of articles, or 80–90% after deterministic filters  
Cost: low to moderate

### Tier 3: Structured extraction

Applies to: top 10–30% of articles  
Cost: moderate

### Tier 4: Deep synthesis

Applies to: top 1–5% of articles  
Cost: higher but capped

---

## Example backlog budget

Assuming use of a low-cost production model for most LLM calls:

- Backlog triage: all 2,659 articles
- Structured extraction: 400–800 articles
- Deep synthesis: 50–100 items

Target envelope:

- **Lean run**: under $20–$50 if using cheap models and tight truncation
- **Balanced run**: $50–$150
- **High-quality review run**: $150–$400 if using stronger models selectively

Exact cost depends on token pricing, article length, and prompt design.

The system should maintain a cost ledger:

run_id, stage, model, sources_processed, input_tokens, output_tokens, estimated_cost


## Ongoing budget

Weekly inflow may be tens of articles.

Target:

- Cheap triage for all new articles
- Extraction only for high-signal articles
- One weekly digest
- One weekly review queue

Reasonable ongoing target:

- **$1–$10 per week** with cheap models
- **$10–$30 per week** if using stronger models selectively

---

# 12. Evaluation: how to know whether the system is good

The system should be measured on usefulness, not completeness.

## Primary metrics

### 1. Precision@K

Of the top K ideas/articles, how many does Joseph rate 2 or 3?

Example:

Precision@10 = number of top 10 rated useful / 10

### 2. NDCG@K

Measures whether the best items appear earliest.

### 3. Calibration

If the system predicts an item is 80% likely useful, is it useful roughly 80% of the time?

### 4. Research conversion rate

How many top ideas lead to actual research notes, watchlist entries, or deeper investigation?

### 5. Author ranking correlation

Do higher-ranked authors produce higher-rated future articles?

### 6. Cost per useful item

cost_per_useful_item = total_run_cost / number_of_useful_items_found

### 7. Time saved

Approximate:

- Number of articles Joseph no longer needs to read
- Number of strong ideas surfaced per week
- Time spent reviewing queue

### 8. Diversity

Avoid collapse into one author or one theme.

Measure:

- Author concentration
- Topic concentration
- Ticker concentration
- Idea novelty

---

# 13. Head-to-head comparison with GraphDB pipeline

The comparison should be done on a frozen snapshot.

## Benchmark setup

1. Freeze a subset of the corpus.
    - Example: 500 articles or a date range.
2. Run both systems:
    - Signal Ledger
    - Existing classify-and-connect GraphDB pipeline
3. Use the same human ground truth.
    - Joseph rates the same sampled outputs.
4. Compare outputs across:
    - Top ideas
    - Top authors
    - Lessons
    - Cost
    - Latency
    - Auditability
    - Reading burden reduction

## Comparison metrics

- Precision@10/20
- NDCG@10/20
- Cost per useful item
- Fraction of durable lessons found
- Quality of author ranking
- Ability to answer queries like:
    - “What are the strongest recent energy ideas?”
    - “Which authors have good post-mortems?”
    - “What is the consensus on XYZ?”
    - “What mistakes keep repeating?”

## Expected outcome

I would expect:

- **Signal Ledger** to win on:
    - Idea ranking
    - Author triage
    - Cost-controlled backlog processing
    - Perishable signal handling
- **GraphDB pipeline** to win on:
    - Durable knowledge compounding
    - Cross-source conceptual connections
    - Long-term wiki-like synthesis

Therefore the best long-term architecture may be:

> Signal Ledger for ranking and filtering; GraphDB/KDB for durable knowledge integration.

Signal Ledger could later export high-quality lessons and validated ideas into the knowledge graph.

---

# 14. Minimal viable version

The MVP should be small and useful within days, not weeks.

## MVP scope

Build:

1. SQLite database
2. Ingest parser for markdown/frontmatter
3. Author normalization table
4. Ticker/company detection
5. Simple heuristic article score
6. Review queue generator
7. Evaluation capture
8. Weekly ranking export

Do not initially build:

- Full graph
- Complex learning-to-rank
- Fancy UI
- Automatic investment recommendations
- Full lesson synthesis
- Multi-user features

---

## MVP heuristic score

For article-level ranking:

article_score =
    0.30 * author_prior
  + 0.20 * recency
  + 0.15 * ticker_signal
  + 0.15 * idea_probability
  + 0.10 * embedding_similarity_to_good_articles
  + 0.10 * length_quality_signal

Where:

- `ticker_signal` is not just ticker presence, but ticker density and context
- `idea_probability` can come from cheap LLM triage
- `author_prior` starts neutral and updates with ratings

---

## MVP review flow

Command example:

signal-ledger ingest
signal-ledger triage --dry-run
signal-ledger rank --limit 20
signal-ledger review --queue daily
signal-ledger evaluate --source-id abc123 --rating 3 --note "Strong thesis"
signal-ledger report --weekly

For the first version, even this is acceptable:

signal-ledger export-review --format markdown --limit 20

Joseph edits ratings in a generated markdown or JSON file, then:

signal-ledger import-evaluations ratings.jsonl

# 15. Recommended implementation phases

## Phase 0: Foundation

Deliverables:

- SQLite schema
- Markdown ingestion
- Author normalization
- Deduplication
- Source table
- Dry-run mode
- Cost estimator

Exit criterion:

> All 2,659 articles can be ingested into SQLite without mutating raw files.

---

## Phase 1: Baseline ranking

Deliverables:

- Deterministic features
- Simple heuristic score
- Top-N leaderboard
- Review queue
- Evaluation table

Exit criterion:

> Joseph can rate 20 articles per day and ratings are stored with ranking context.

---

## Phase 2: Embeddings and triage

Deliverables:

- Chunking
- Embedding index
- Similarity search
- Duplicate detection
- Cheap triage classification

Exit criterion:

> The system can find similar articles, detect repeated ideas, and classify articles into idea/lesson/commentary/noise.

---

## Phase 3: Structured idea extraction

Deliverables:

- Idea extractor
- Evidence quotes
- Ticker normalization
- Idea ledger
- Idea ranking

Exit criterion:

> The system produces a ranked idea ledger with thesis, author, date, evidence, and score.

---

## Phase 4: Learned ranking

Deliverables:

- Logistic/pairwise ranker
- Feature snapshots
- Model versioning
- Validation report
- Active learning queue

Exit criterion:

> The learned ranker beats the heuristic baseline on held-out Joseph ratings.

---

## Phase 5: Lesson library

Deliverables:

- Lesson extraction
- Lesson clustering
- Distilled playbooks
- Lesson ratings

Exit criterion:

> The system produces a small set of durable lesson notes with citations.

---

# 16. Risks and mitigations

## Risk 1: LLM hallucinates tickers or thesis

Mitigation:

- Require evidence quotes
- Validate tickers against detected text
- Mark low-confidence extractions
- Store source spans
- Use conservative prompts

---

## Risk 2: Author normalization errors

Mitigation:

- Maintain alias table
- Manual review of uncertain author merges
- Store raw author string alongside canonical author

---

## Risk 3: Feedback loop becomes biased

Mitigation:

- Always include random/exploration items in review queue
- Track author diversity
- Track topic diversity
- Do not train only on top-ranked items

---

## Risk 4: Ideas go stale

Mitigation:

- Recency decay
- Expiry status
- Catalyst tracking
- Periodic stale-idea review

---

## Risk 5: Overfitting to Joseph’s current preferences

Mitigation:

- Holdout evaluation
- Diversity quotas
- Periodic “challenge queue” from contrarian or low-prior authors
- Separate “fit” score from “exploration” score

---

## Risk 6: Cost creep

Mitigation:

- Token budget per run
- Cost ledger
- Dry-run cost estimate
- Cache hashes
- No re-extraction of unchanged articles
- Cap strong-model calls

---

# 17. Final recommendation

Build **Signal Ledger** as a separate, lightweight, local rank-and-learn system.

It should be:

- **SQLite-first**
- **Markdown-compatible**
- **Dry-run capable**
- **Cost-tiered**
- **Evaluation-driven**
- **Independent from the main KDB pipeline**
- **Able to export durable lessons later into the knowledge graph**

The most important first step is not full LLM extraction.

The first step is:

> Build the evaluation loop.

Concretely:

1. Ingest the 2,659 articles into SQLite.
2. Normalize authors and detect tickers.
3. Generate a stratified review queue of 100–200 articles.
4. Have Joseph rate them using a simple 0–3 scale.
5. Use those ratings to calibrate the first ranking model.
6. Then expand into idea extraction, author scoring, and lesson distillation.

That creates the foundation for a system that does not merely summarize newsletters, but progressively learns Joseph’s judgment and reduces his reading burden while improving investment insight.