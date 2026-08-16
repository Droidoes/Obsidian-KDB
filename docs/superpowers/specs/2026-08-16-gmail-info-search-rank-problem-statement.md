# Problem statement — learning from the gmail-substack corpus

> **Status**: draft for external panel review (2026-08-16). Options-free by design (#125
> precedent): this document states the problem, the corpus, the constraints, and the
> success criteria — it deliberately does **not** propose or pre-select a solution.
> The panel is asked to propose their own architectures. Corpus measurements in §1
> were corrected 2026-08-16 after an independent audit.
> Panel artifacts: [`…-response-grok.md`](2026-08-16-gmail-info-search-rank-response-grok.md),
> [`…-response-deepseek.md`](2026-08-16-gmail-info-search-rank-response-deepseek.md),
> [`…-review-and-solution-codex.md`](2026-08-16-gmail-info-search-rank-review-and-solution-codex.md),
> [`…-review-and-solution-claude.md`](2026-08-16-gmail-info-search-rank-review-and-solution-claude.md),
> [`…-Solution-Qwen-3.8-max.md`](2026-08-16-gmail-info-rank-problem-statement-Solution-Qwen-3.8-max.md),
> [`…-task145-info-rank-blueprint-v0.1-grok.md`](2026-08-16-task145-info-rank-blueprint-v0.1-grok.md) (uncommissioned; reference only).

## 1. Context

The Obsidian-KDB project maintains a knowledge pipeline: sources in an Obsidian vault
are enriched (Pass-1), searched (Pass-1.5), compiled (Pass-2) into wiki pages and a
Kuzu-backed knowledge graph — a classify-and-connect architecture designed for a
curated, interrelated personal knowledge base.

Separately, the `#143` gmail-substack feeder (shipped 2026-08-15) converted the
backlog of a Gmail `Substack_raw` label into local markdown sources:

- **4,156 messages converted** → 4,189 md files under `KDB/raw/joseph-ft-public-gmail/`
- A deterministic promo pre-filter then moved **1,530 promotional/truncated files
  (36.5%) to `_promo/`**, leaving **2,659 full articles**
- The corpus **keeps growing**: every subscribed Substack letter lands in Gmail and is
  converted on each feeder run (with the promo battery now applied at fetch time)

**Corpus measurement (2026-08-16 audit, residual tree excluding `_promo/`):**
2,659 files (2,570 article / 77 video / 12 podcast); 4,207,609 body words
(median 1,000, p95 4,245, max 45,152); 117 distinct raw `author` strings;
212 files attributed only to `Substack`; 25 files with <50 body words; 3 files
with frontmatter bleed. Date span 2025-11-24 → 2026-08-15. The claimed
`word_count` frontmatter field does **not** exist (`published_date` does).
`4,189` total md files = 33 pre-existing + 4,156 newly converted.

**Digest contamination (found 2026-08-16, after the audit above):** **34** of the
2,659 residual files are Substack "Weekly Stack" recommendation digests, not
articles — each is a stub-link roundup pointing at five other posts, with no body
of its own. All 34 carry `author: Substack` (i.e. 34 of the 212 files under that
generic string) and match the title pattern `"<title>" and N more`. Detection
note: only 21 match `^title:.*and N more` on a single line; the other 13 have the
marker on a YAML-wrapped continuation line, so the pattern must be matched
against the *parsed* `title` field, not a raw line grep. Filenames are a reliable
secondary signal (`…-and-4-more.md`).

Consequence: **2,659 remains the correct intake-tree count**, but the **rankable
corpus is 2,625**. These 34 are unrankable by construction and, if left in, would
corrupt both the `author: Substack` bucket and any author-level rollup. They
belong in the same excluded class as the existing promo filter.

The residual corpus is **not** investment-dominated. Author-name buckets:
politics/geopolitics ~55.5% (largest: Savage Minds 224, Robert Reich 221,
Glenn Diesen 196, The New Republic 126), investment-named ~16.7% (Coal Trader
122, Compounding Quality 86, then a long tail including Rebound Capital,
TSOH, Michael Burry, Mr Deep-Value), other ~16.4%, generic `Substack` 8.0%,
AI/tech-named 3.4%. Corpus relevance is therefore a first-class gate, not a
cleanup footnote. Each letter still has an identifiable author/publication
string; those strings are dirty and must be normalized.

## 2. The problem

Joseph cannot read 2,659 backlog articles plus the continuous inflow. The corpus is
**information, not knowledge** — articles are mostly *unrelated to each other*,
unlike the vault-in-place sources the knowledge pipeline was built for. Running this
corpus through the existing classify-and-connect pipeline unchanged is believed to be
the wrong tool (3 LLM calls/source, graph structure built for knowledge compounding),
but this belief is itself open to challenge.

**The intent, in Joseph's words: extract investment ideas and improve value
investing skill.** Two distinct values live in the corpus:

1. **Ideas** — actionable investment theses (ticker/company + argument), which are
   **perishable**: a pitch has a window of weeks to months.
2. **Lessons** — frameworks, mental models, dissected mistakes, writer process —
   which **compound**: a great post-mortem teaches for years.

A useful system must serve both, and must serve them from a corpus that is large,
growing, uneven in quality, and authored by writers of very different styles and
track records.

### 2.1 What "useful" concretely means

- **Rank ideas**: surface the ideas with the highest **expected value of Joseph's
  next research hour** (not predicted investment return), with the supporting
  thesis, so he can decide what deserves research time.
- **Rank authors**: not all letters are equal; author quality (and style) should be
  learned and tracked, so author reputation informs idea ranking and reading triage.
- **Learn**: the corpus should make Joseph a better value investor — patterns,
  frameworks, and mistakes across writers should be extractable, not just tickers.

### 2.2 Human-in-the-loop development requirement

The system's judgment must converge toward **Joseph's** judgment. The development
process itself is required to be iterative: Joseph will manually evaluate a subset of
articles, and those evaluations are the ground truth from which the system's ranking
behavior is developed, tested, and improved over time. Any proposed architecture must
make this feedback loop a first-class citizen (how evaluations are captured, how the
system's rankings are validated against them, how the system improves as more
evaluations accumulate).

## 3. Scope decisions (already made — not up for debate)

- **A separate, parallel system.** This corpus is handled by a *different* system —
  its own codebase/components and tool calls, architecturally independent of the
  Obsidian-KDB knowledge pipeline. It needs a name (working name TBD).
- **It is a deliberate competing approach.** The parallel system is an architectural
  experiment: an alternative way to extract value from text corpora. If it proves
  more efficient/effective, it may later be applied to the vault-in-place corpus too.
- **Optionality is preserved.** (a) The gmail-substack corpus can still be run
  through the GraphDB pipeline later (the raw md sources are durable); (b) a future
  harness may combine both systems' outputs (e.g., ranking × graph structure).
  Nothing built now should foreclose those paths.
- **Promo/truncated noise is already filtered** (1,530 files in `_promo/`); the
  residual 2,659 articles are the working corpus. A handful of transactional emails
  and ~15 borderline items remain as acceptable noise.

## 4. Open questions the panel should address

1. **Core architecture**: given 2,659 articles + continuous inflow, what is the right
   processing model to rank ideas, rank authors, and distill lessons? (Extraction
   pass? Retrieval? Aggregation? Some combination? Something else?)
2. **The learning loop**: how exactly should Joseph's manual evaluations on a subset
   be captured and converted into improved system ranking? What is the minimal
   viable version of this loop?
3. **Data model**: what records/artifacts should the system maintain (idea ledger?
   author profiles? evaluation history?), and in what substrate (files, SQLite,
   graph, vectors, …)?
4. **Cold start vs steady state**: what does the backlog (2,659) demand vs each new
   week's inflow (~tens of articles)?
5. **Cost discipline**: what is a reasonable LLM-cost envelope for the backlog and
   for ongoing operation? Where can deterministic/embedding methods replace LLM calls?
6. **Evaluation**: how do we measure whether the system is any good — and how would
   we later compare it head-to-head against the GraphDB pipeline approach?

## 5. Constraints and practical notes

- Single operator (Joseph), local machine (WSL), existing multi-provider LLM
  infrastructure available (`deepseek-v4-flash` is the standing production model;
  OpenAI/Gemini/Qwen/xAI keys optional).
- LLM cost is a real consideration: the 2026-08-15 compile decision over 2,659
  sources was explicitly deferred as "a real cost conversation."
- The corpus lives as plain md files with metadata-only frontmatter (`title`,
  `author`, `published_date`, `source_url`, `gmail_message_id`, `content_kind`,
  `feeder`, `ingested_at`). There is no `word_count` field; length is computed
  from the body.
- New articles arrive continuously; promo filtering happens at fetch time.
- Anything built should be dry-run-capable, auditable, and reversible — the project
  standard.

## 6. Explicitly out of scope (for this brief)

- Changing the existing Obsidian-KDB knowledge pipeline (vault-in-place) itself.
- Re-opening the promo-filter decisions (settled 2026-08-15).
- Choosing among solution families — that is the panel's job, and then Joseph's.
