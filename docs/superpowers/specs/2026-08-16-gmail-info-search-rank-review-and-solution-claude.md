# Gmail/Substack search-and-rank — review and solution (Claude)

> **Status:** architecture review and proposed solution (2026-08-16). Deliberation
> artifact, not a ratified architecture. Reviews
> [`2026-08-16-gmail-info-search-rank-problem-statement.md`](2026-08-16-gmail-info-search-rank-problem-statement.md)
> and proposes one architecture with reasoning, for Joseph's decision.
> Phase-1 (Architecture) output only — no implementation blueprint.

## Executive conclusion

The brief's core diagnosis is correct: this corpus is information, not knowledge, and
the classify-and-connect knowledge pipeline is the wrong tool for it. Two premises
underneath the brief need correcting, though — the corpus is not investment-dominated,
and LLM cost is not a real constraint at this scale. Both corrections push in the same
direction: **rank everything, extract deeply only where depth pays.**

The proposed architecture is a **single-pass extraction → structured SQLite ledger →
deterministic two-tier scoring → static HTML review UI**. One LLM call per article
classifies it and scores its signal; investment-bucket articles additionally yield idea
and lesson records. Scoring is computed post-LLM, deterministically. Joseph's ratings
are captured at both article and author level and are the ground truth the ranker is
tuned against.

## 1. Review of the problem statement

### 1.1 Corpus composition — the "investment corpus" premise is wrong

§1 of the brief already carries the corrected measurements (2026-08-16 audit); this
review confirms and elaborates them rather than restating them. The load-bearing fact:
**political/geopolitical commentary is the largest bucket, not investment.** Roughly
half the corpus is political/geopolitical writing — Julian Vigo/Savage Minds 224,
Robert Reich 221, Glenn Diesen 196, The New Republic 126, Democracy At Work 94, the
Bulwark family ~215 combined across ten distinct bylines, Project Syndicate 70,
John Mearsheimer 60, Chris Hedges 55, Alexander Dugin 30, Glenn Greenwald 20.

Investment-specific writing is roughly a sixth of the corpus (§1 measures 16.7% by
author name, ~440 articles): The Coal Trader 122, Compounding Quality 86, Rebound
Capital 31, TSOH/Alex Morris 25, Michael Burry 23, Mr Deep-Value 17, Watchlist
Investing 16, Doomberg 10, Tavi Costa 6, Ray Dalio 6, plus a long tail. China
geopolitics-economics is a small but distinct cluster (~3%: Pekingnology-CCG,
ChinaTalk, Hello China Tech, Baiguan), and AI/tech plus self-help/misc accounts for
another tenth or so (Dwarkesh Patel, Naval's Archive, Dan Koe, Nietzsche Wisdoms).
117 distinct author strings in total.

One framing note to avoid a false conflict later: §1's percentages are **author-name**
buckets, while the topic taxonomy proposed in §2 below is **content-based**. The two
cuts will not produce identical numbers, and they don't need to — the author-name cut
is the cheap measurement available today, the content cut is what the system will
actually produce.

The consequence for architecture is direct: a system that only serves the investment
slice leaves ~80% of the corpus unranked and Joseph's actual reading problem unsolved.

### 1.2 Digest contamination is real and must be excluded at intake

34 of the 2,659 residual files are Substack "Weekly Stack" recommendation digests
(`author: Substack`, title pattern `"<title>" and N more`) — stub-link roundups with no
body of their own. They are unrankable by construction and, left in, would corrupt both
the `author: Substack` bucket and any author-level rollup. They belong in the same
excluded class as the promo filter. **Rankable corpus: 2,625 articles**, ~4.2M body
words (§1 measures 4,207,609 across 2,659; the 34 stubs carry essentially no body, so
the rankable figure is marginally lower).

### 1.3 Cost is not a constraint here — correct the cost-anxiety framing

The brief inherits a cost worry from the 2026-08-15 compile decision ("a real cost
conversation") and from the knowledge pipeline's 3-calls-per-source profile. Applied to
this system, that worry is misplaced.

At `deepseek-v4-flash` registry pricing ($0.14/M input, $0.28/M output per
[`docs/reference/model-provider-api-calls.md`](../../reference/model-provider-api-calls.md)),
one extraction call per article over the full backlog:

- Input: ~4.2M words ≈ ~5.6M tokens × $0.14/M ≈ **$0.78**
- Output: ~2,625 structured records × ~400 tokens ≈ ~1.05M tokens × $0.28/M ≈ **$0.29**
- **Backlog total: roughly $1.** Ongoing inflow of tens of articles a week: pennies.

State it plainly: the objection to running this corpus through the GraphDB pipeline was
never dollars. It was **architectural mismatch** — that pipeline builds a compounding
graph structure over interrelated sources, and these articles are largely unrelated to
each other. Cost discipline should not shape this design; fit-for-purpose should. Any
architecture that trades coverage for LLM-call savings is optimizing a non-problem.

### 1.4 Author identity is dirty — a known wrinkle, not v1 work

`Julian Vigo, Editor-in-chief of Savage Minds` (224) and `Editor at Savage Minds` (97)
are almost certainly the same writer under two strings. The Bulwark's ten bylines are
the opposite case — genuinely distinct writers sharing a publication. Normalization is
worth a future pass; it is not v1 scope, and v1 should not be blocked on it. Flagging it
here so the derived author rollups are read with the right caveat.

## 2. Scope resolution (settled)

These are Joseph's directives, recorded as settled rather than proposed:

- **Rank everything in the corpus, not just investment content.** Every article gets a
  topic classification (`investment` / `geopolitics` / `china-econ` / `ai-tech` /
  `other`) and a quality/insight score.
- **Investment gets depth; everything else gets triage.** Investment-bucket articles
  additionally yield *idea* records (ticker/company + thesis — perishable, weeks-to-
  months shelf life) and *lesson* records (frameworks, mental models — compounding, long
  shelf life). Non-investment buckets get topic + quality score only, which is enough to
  serve reading triage.
- **Two-tier ranking: author → that author's individual articles.** Confirmed
  explicitly. Not publication-then-writer grouping, even though cases like the Bulwark's
  ten bylines could suggest that reading. The author-string duplication noted in §1.4 is
  the known data-quality wrinkle on this tier.
- **Rating capture at both levels** — article and author — via an HTML review UI, in the
  pattern of the project's existing `KDB/graph-view.html` static viewer: precomputed data
  baked into the HTML, no live backend.
- **Derived author rating.** Where Joseph has not set an explicit author rating, it is a
  recency-weighted rollup (mean/median) of that author's article scores. An explicit
  manual author rating, when set, takes precedence over the derived value.

## 3. Proposed solution

Single-pass extraction → structured SQLite ledger → deterministic two-tier scoring →
static HTML review UI.

```text
Raw Markdown (durable, unmodified)
    ↓  deterministic intake: exclude _promo/ + the 34 digests
One structured LLM call per article
    ├── topic bucket
    ├── quality/insight signal
    └── if investment: 0..N idea records, 0..N lesson records
    ↓
SQLite ledger  (articles / ideas / lessons / authors / ratings)
    ↓  deterministic, post-LLM
Two-tier scoring: article_score, author_score
    ↓
Static HTML review UI  → Joseph's ratings → back into the ledger
```

### 3.1 Extraction — one LLM call per article

A single structured-JSON call returns:

- **(a) Topic bucket** — one of investment / geopolitics / china-econ / ai-tech / other.
- **(b) Quality/insight signal** — a scalar the ranker consumes. The dimensions it
  reads are specificity, argument density, and conviction-language markers. The exact
  rubric and its calibration are deliberately left to implementation time: it is the
  part most likely to change under Joseph's first hundred ratings, and pinning it now
  would fix the wrong thing before there is any feedback to fix it against.
- **(c) Investment articles only** — zero or more **idea** records (ticker/company,
  thesis, conviction cues) and zero or more **lesson** records (framework/principle,
  summary). Non-investment articles skip this branch entirely; the call still runs, it
  just returns no idea/lesson payload.

One call per article, once per article. Re-scoring never requires re-extraction.

### 3.2 Storage — SQLite

SQLite, not GraphDB and not vector embeddings. This is a deliberately separate, parallel
system per the brief's own scope decisions, architecturally independent of the knowledge
pipeline — the graph substrate is the knowledge pipeline's, and the whole premise here is
that these articles don't interrelate. (The embeddings rejection is argued in §4.2.)

Table sketch:

| Table | Columns (sketch) |
|---|---|
| `articles` | id, path, author, published_date, topic_bucket, quality_signal, article_score, metadata |
| `ideas` | id, article_id (FK), ticker/company, thesis, conviction_cues |
| `lessons` | id, article_id (FK), framework/principle, summary |
| `authors` | id, name, explicit_rating (nullable), derived_score |
| `ratings` | id, target_type (`article`\|`author`), target_id, joseph_rating, rated_at |

`ratings` is the durable substrate for the human-in-the-loop requirement: Joseph's
evaluations accumulate as records attached to specific targets, and both the article
scorer and the author rollup read from them.

### 3.3 Scoring — deterministic, computed post-LLM

Scoring never lives in the prompt. This is the project's established convention for
provenance and scoring decisions, and it earns its keep here specifically: weights will
be retuned repeatedly against Joseph's accumulating ratings, and retuning must never
mean re-running the corpus.

- **`article_score`** = the LLM quality signal, recency-decayed **for investment ideas
  specifically** (they perish on a weeks-to-months clock), boosted or overridden by
  Joseph's direct rating where one exists. Geopolitics commentary and lesson content do
  not carry the same decay — a good framework doesn't expire in six weeks.
- **`author_score`** = explicit manual rating if set; otherwise the recency-weighted
  rollup of that author's article scores.
- **Ranking** folds `author_score` in as a prior alongside the article's own signal, so
  a strong writer's new piece surfaces before an unknown writer's, without the author
  prior alone deciding the order.

### 3.4 Review surface

A static HTML page in the `KDB/graph-view.html` pattern — precomputed ranking data baked
into the file, no backend, no server. It presents the two-tier view (authors, and each
author's articles) and captures ratings at both levels. Captured ratings flow back into
`ratings`, which changes `article_score` and `author_score` on the next scoring run.

### 3.5 Cost

~$1 one-time for the 2,625-article backlog; negligible ongoing. See §1.3.

## 4. Alternatives considered and rejected

### 4.1 Author-first, attention-gated extraction

Bootstrap author tiers from a small hand-rated sample. Rank the remaining corpus by
author tier plus cheap deterministic signals — recency, word count, title — with no LLM
call. Deep-extract ideas and lessons **only** from articles Joseph actually opens in the
review UI. Event-driven rather than batch.

Genuinely distinct: attention gates the LLM calls instead of an upfront batch pass, and
it is cheaper still — a few hundred calls instead of 2,625.

**Rejected** on two grounds. First, the savings buy nothing: §1.3 shows the full batch
costs about a dollar, so trading coverage for cost here is trading something real for
something that rounds to zero. Second, it conflicts directly with "rank everything" —
ideas and lessons only ever surface for content Joseph has already opened, which means
the system can't tell him what he's missing. That inverts the entire point.

### 4.2 Retrieval/embeddings-first with query-time LLM synthesis

Embed the corpus, index it, and run LLM extraction and ranking on demand per query. No
persistent extraction ledger; rankings synthesized fresh each time.

**Rejected** because the two-tier author/article rating requirement needs durable,
accumulating per-item records — something for a rating to attach *to*, and something to
roll up *over*. Pure query-time synthesis has nowhere to persist Joseph's judgment and
would recompute rankings from scratch on every query, discarding exactly the signal the
system is supposed to be accumulating.

Worth stating explicitly: this is **not** an application of the project's graph-over-
vector preference. That preference is scoped to the main KDB pipeline being an
ontology-builder, where vector retrieval is the anti-thesis of what's being built. This
system is explicitly separate and explicitly not an ontology, so that argument doesn't
transfer. The rejection stands on its own ground: no durable substrate for ratings.

## 5. Carried-forward scope decisions

Restated briefly from the brief's §3; not relitigated here.

- **Separate, parallel system** — own codebase and components, architecturally
  independent of the knowledge pipeline.
- **A deliberate competing architectural experiment** — an alternative way to extract
  value from a text corpus. If it proves more efficient or effective, it may later be
  applied to the vault-in-place corpus.
- **Optionality preserved** — the raw markdown sources stay durable and could still be
  run through the GraphDB pipeline later; a future harness may combine both systems'
  outputs (e.g. ranking × graph structure). Nothing proposed above forecloses either.
- **Human-in-the-loop is satisfied structurally** — the `ratings` table plus the derived
  author rollup make Joseph's manual evaluations the ground truth against which ranking
  behavior is developed, tested, and improved as evaluations accumulate. It is a first-
  class part of the data model, not an add-on.

## 6. Closing note

This is Phase-1 (Architecture) output: a review of the problem statement and one
proposed solution architecture with its reasoning and its rejected alternatives. A
phased implementation blueprint — technical detail, phase boundaries, TDD gates, task
breakdown — is a separate and later step, and should not be written without Joseph's
explicit go-ahead.
