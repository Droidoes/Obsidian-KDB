# Grok blueprint v0.1 — Relevance-gated info ledger

**Status:** Grok seat proposal for Option C (Joseph selected this family
2026-08-16). This is a deliberation blueprint, **not** filed in `docs/TASKS.md`
or `docs/CODEBASE_OVERVIEW.md`, and **not** ratified for implementation until
Joseph says **Proceed**.

**Brief:** [`2026-08-16-gmail-info-search-rank-problem-statement.md`](2026-08-16-gmail-info-search-rank-problem-statement.md)
**Selection:** [`2026-08-16-gmail-info-search-rank-response-grok.md`](2026-08-16-gmail-info-search-rank-response-grok.md)

---

## 1. Problem (one paragraph)

Joseph cannot read 2,659 residual gmail-substack files plus the weekly inflow.
The files are information, not knowledge, and the residual set is majority
politics/geopolitics by author, not investment letters. The knowledge pipeline
(classify-and-connect, 3 LLM calls/source, a compounding graph) is the wrong
tool. He needs (1) a ranked research queue of investment ideas, (2) author
utility that informs that queue without taking it over, and (3) compounding
lessons — all calibrated to *his* judgment, not to predicted market returns.

---

## 2. Decisions

These are binding for this blueprint. Changing one is a new architecture turn.

| ID | Decision |
|---|---|
| **D1** | **Option C.** Index every residual file. Extract structured idea/lesson records only from files that pass a cheap relevance gate. Info-only and residual-noise stay searchable and are not forced through the idea schema. |
| **D2** | **Parallel system, sibling package.** Working name `info_rank/` in this repo. Reuse `common/call_model` and the model pool. A later split into a separate equity-research repo remains open and is not v1 work. |
| **D3** | **Hard write boundary.** The package may *read* `KDB/raw/joseph-ft-public-gmail/` (and later other raw trees). It must not write `KDB/wiki/`, `manifest.json`, the Kuzu graph, or the gmail-substack pipeline config. Its state lives under `KDB/state/info_rank/` (SQLite + journals + exports). |
| **D4** | **Ranking objective.** Scores are **expected value of Joseph's next research hour**. Schema field: `research_priority`. The system does not predict investment performance. |
| **D5** | **Joseph's labels** are ground truth for personal usefulness and research priority only. Faithfulness, factual correctness, and track record are separate axes. |
| **D6** | **Author quality is three variables.** (a) personal utility — learnable now; (b) analytical traits — from extraction features; (c) track record — empty until post-horizon outcome checks exist. Author utility's weight on idea ranking is **capped and small** in v1. |
| **D7** | **Extract once, score many times.** Changing ranker weights never re-extracts. Re-extraction is a new `extraction_run` keyed by schema version + model + source hash. |
| **D8** | **Faithfulness is a gate.** Every substantive extracted field carries a source span. A deterministic checker must find that exact span in the article body. Failure fails the record, not the whole article (other valid records still land). Zero unvalidated spans in the ledger. |
| **D9** | **Zero ideas / zero lessons is success.** The extractor must be allowed to emit nothing. Forcing at least one idea is a defect. |
| **D10** | **Never merge by ticker alone.** A bullish valuation thesis and a bearish accounting thesis on the same company are different `ideas`. Corroboration raises salience, not merit. |
| **D11** | **No embeddings in v1.** FTS5 over articles + extracted text. A vector adapter is allowed only after an evaluation shows FTS + structured fields missing queries Joseph actually asks. |
| **D12** | **Skip by rule, no LLM:** `content_kind` in `{video, podcast}`; body word count `<50`; the 3 known frontmatter-bleed files until intake repairs them. |
| **D13** | **Default model** for gate and extraction: `deepseek-v4-flash` via the existing pool. Overrideable per run. |
| **D14** | **Dry-run / audit / reversible.** Every write is journaled. `--dry-run` performs intake + optional LLM calls but commits nothing. A run can be rolled back by run id. |
| **D15** | **Working package name `info_rank` is provisional.** Joseph may rename before the first commit. Rename is mechanical and does not reopen D1–D14. |

---

## 3. System shape

```text
KDB/raw/joseph-ft-public-gmail/*.md     (immutable source)
        │
        ▼
info_rank intake  (deterministic)
  paragraph IDs, word count, author-map, frontmatter repair
  FTS5 over full residual corpus
        │
        ▼
relevance gate    (cheap LLM or rules+LLM)
  investment-bearing | lesson-bearing | mixed | info-only | residual-noise
        │
        ├─ info-only / noise / skip-by-rule ──► searchable only
        │                                      (exploration sample may still extract)
        └─ investment / lesson / mixed
                │
                ▼
        structured extraction (one call / article)
          idea_mentions 0..N
          lesson_cards  0..N
          evidence spans (validated)
                │
                ▼
        canonicalize mentions → ideas / cards → frameworks
                │
                ▼
        versioned ranker
          research queue     (ideas, decay toward horizon)
          lesson library     (no decay; long-interval re-surface)
          reading queue      (articles Joseph has not triaged)
                │
                ▼
        feedback events + later outcome checks
                │
                ▼
        next ranker version (hand-tuned, then small pointwise model)
```

State root: `<vault>/KDB/state/info_rank/`

| Path | Role |
|---|---|
| `ledger.sqlite` | system of record |
| `runs/<run_id>/journal.jsonl` | append-only events |
| `runs/<run_id>/extractions/<hash>.json` | raw + salvaged model output |
| `exports/<date>/` | versioned JSONL/CSV snapshots |
| `author_map.yaml` | raw author string → canonical author + publication |

---

## 4. Data model

SQLite. Raw Markdown remains the source of truth; the DB stores derived
records and never a second copy of the full body (FTS stores its own searchable
copy of title + body + extracted text, rebuilt from sources on intake).

### 4.1 Tables

**`articles`**
`article_id` (stable hash of vault-relative path + content sha256 at first
seen), `path`, `content_sha256`, `title`, `raw_author`, `published_date`,
`source_url`, `gmail_message_id`, `content_kind`, `word_count`,
`cleanliness` (`ok` / `short` / `media` / `bleed` / `repaired`),
`first_seen_run`, `last_seen_run`.

**`authors`** / **`publications`**
Canonical ids. `author_aliases` maps each raw string onto one author and
optionally one publication. 117 raw strings in, far fewer canonicals out.
Joseph can edit `author_map.yaml`; intake reapplies.

**`relevance_verdicts`**
`article_id`, `run_id`, `label`, `confidence`, `model`, `prompt_version`,
`rationale_span` (optional). Latest verdict wins for routing; history is kept.

**`extraction_runs`**
`run_id`, `article_id`, `schema_version`, `model`, token/cost/latency,
`status` (`ok` / `empty` / `failed` / `skipped`).

**`idea_mentions`**
What *one* article claims: `company`, `ticker` (nullable), `stance`
(`long` / `short` / `pass` / `unclear`), `thesis`, `valuation_premise`,
`catalyst`, `risks`, `horizon`, `expires_on` (date or null),
`extraction_uncertainty`, `idea_id` (nullable until clustered).

**`ideas`**
Clusters of compatible mentions. Created by a deterministic first pass
(same normalized company + same stance + token-overlap on thesis) plus a
manual merge/split command. Never auto-merge opposite stances.

**`lesson_cards`** / **`frameworks`**
Principle, context, reusable application, failure mode. Cards cluster into
frameworks the same way mentions cluster into ideas.

**`evidence_spans`**
`record_type` + `record_id` + `field`, `paragraph_id`, `exact_quote`.
Insert is refused if `exact_quote` is not a substring of that paragraph.

**`feedback_events`**
Immutable: `action` (`research` / `save` / `skip` / `wrong-extraction` /
`promote-to-extract`), optional `usefulness` 1–5, `reason_tags`, optional
pairwise other id, `ranker_version`, `score_shown`, `position_shown`,
`batch_id`, `ts`.

**`outcome_checks`**
v1 stores `due_on` from `expires_on`. The hit/miss UI may land after the
500-file gate. Until then the column may be null.

**`rankers`** / **`score_snapshots`**
A ranker is a named, versioned JSON object of weights + feature list.
A snapshot is `ranker_version × record_id → scores` so a past queue is
replayable.

### 4.2 Scores (never a single "quality")

- `idea_research_priority`
- `lesson_learning_value`
- `article_reading_priority`
- `author_personal_utility`

v1 idea features (all 0–1 except as noted): thesis specificity, evidence
quality, valuation discipline, falsifiability, risk treatment, horizon
clarity, freshness vs horizon (decays), independent-source corroboration
(salience only), novelty, extraction uncertainty (penalty), capped author
utility (v1 cap: 0.15 of the weighted sum).

---

## 5. Processing contracts

### 5.1 Intake (no LLM)

- Walk the pipeline root; honor the existing `_promo/` exclude.
- Compute word count from the body (the field is not in frontmatter).
- Assign paragraph IDs: split on blank lines, stable `p0001…`.
- Repair the 3 bleed files into a repaired view (original bytes untouched).
- Apply `author_map.yaml`. Unmapped strings stay raw and are listed for
  Joseph; they do not block intake.
- Rebuild FTS5 from current bodies.

Idempotent. Re-running intake on an unchanged tree is a no-op except FTS
rebuild if requested.

### 5.2 Relevance gate

Closed label set:

`investment-bearing` | `lesson-bearing` | `mixed` | `info-only` | `residual-noise`

Routing:

| Label | Extract ideas? | Extract lessons? |
|---|---|---|
| investment-bearing | yes | if present |
| lesson-bearing | no, unless extractor finds one (may upgrade) | yes |
| mixed | yes | yes |
| info-only | no | no |
| residual-noise | no | no |

The extractor may *downgrade* a file to `info-only` (logged). It may not
silently upgrade `residual-noise`. Upgrade of `info-only` happens only via
Joseph's `promote-to-extract` or the exploration sample.

Exploration sample: each full-corpus gate pass extracts a fixed 5% (min 10)
of current `info-only` files, stratified by author, so false negatives are
measured. Those extractions are tagged `exploration=true` and do not enter
the default research queue until Joseph accepts them.

### 5.3 Extraction

One structured JSON response per article. Schema version stamped.
Salvage is per-record (R1 posture from #123): a parseable document is never
discarded whole; bad mentions drop; good ones land.

Required per mention/card: at least one validated evidence span.
`ticker` is omitted unless the exact ticker string appears in the source.

Prompt must say: emit zero mentions if the article is not an investment
thesis. Do not invent a company so the schema looks filled.

### 5.4 Ranker

Deterministic function of features + weights. No LLM in the scoring path.
`expires_on` past today → idea leaves the research queue and appears on the
outcome due-list. Lessons never expire; a `last_surfaced_at` drives a 90-day
re-surface.

v1 weights are hand-set in `rankers`. Changing weights writes a new
`ranker_version` and a new `score_snapshots` set.

### 5.5 Feedback

CLI + a later static HTML review surface (same pattern as the #123
adjudication reviewer: no backend, reads a JSON snapshot, writes a JSONL
Joseph drops back in). v1 can be CLI-only.

Every review batch reserves 20% of slots for exploration / uncertain /
random, recorded on the event.

After 200 events with `action` in `{research, save, skip}` and representative
author mix, a separate command fits a regularized pointwise model and
proposes a new ranker version. Joseph accepts or rejects the proposal.
No automatic swap.

---

## 6. CLI (v1)

Working command name `kdb-info-rank` (matches existing `kdb-*` entry points).

| Command | Purpose |
|---|---|
| `intake` | Walk sources, repair view, FTS, author map |
| `gate [--max N] [--dry-run]` | Relevance verdicts |
| `extract [--max N] [--dry-run]` | Extraction on files the gate admits |
| `rank` | Recompute scores for the active ranker |
| `queue [--kind research\|lessons\|reading] [--n 20]` | Print the current queue |
| `feedback <id> <action>` | Append an event |
| `promote <article_id>` | Force extract |
| `export` | JSONL/CSV snapshot |
| `status` | Counts by verdict, run, cost |

`--dry-run` is valid on `gate` and `extract`. Non-interactive `--yes` is
**not** provided for destructive rollback; rollback is a named
`runs/<id>/rollback` that requires typing the run id.

---

## 7. Phased delivery and TDD gates

Implementation does not start until Proceed. After Proceed, phases are
sequential. Each gate is a failing-test-first block.

### Phase 0 — Package + intake + FTS (no LLM)

- Package `info_rank/` with the same boundary-guard pattern as `kdb_search`
  (imports `common` only, plus stdlib). `call_model` is used from Phase 1.
- SQLite schema + migrations.
- Intake over a fixture tree (promo excluded, bleed repaired, word counts).
- FTS query returns known fixture hits.
- **Gate:** intake on the real 2,659-file tree is idempotent; counts match
  the 2026-08-16 audit (2,659 / 1,530 promo / 77 video / 12 podcast / 25
  short); no write outside `KDB/state/info_rank/`.

### Phase 1 — Relevance gate

- Label schema + prompt version + salvage.
- Fixture articles covering all five labels.
- **Gate:** hand-label 150 stratified real files (Joseph). Gate precision
  and recall on `investment-bearing ∪ mixed` both recorded; **do not
  proceed to full extraction** until Joseph accepts the confusion matrix.
  No numeric threshold is invented here — he sets it after seeing the 150.

### Phase 2 — Extraction schema

- Prompt + JSON schema + span validator + per-record salvage.
- Fixtures: a real Burry/TSOH-style thesis, a Reich-style political essay
  (must emit zero ideas), a lesson-only post-mortem, a short stub (skip).
- **Gate:** 100-file relevant-set audit. Span-validity 100% on landed
  records. Zero-idea rate on a political holdout is reported, not hoped.

### Phase 3 — Ranker + queues

- Feature computation, hand-tuned weights, decay, `queue` CLI.
- Baselines implemented: recency, author-only, BM25 title.
- **Gate:** on the 100-file audit set, the hand-tuned research queue is
  compared to the three baselines using Joseph's labels. Ship only if it
  is not worse than all three on nDCG@10. Ties go to the simpler baseline
  until more labels exist.

### Phase 4 — Feedback + 500-file extract

- Event log, exploration quota, `promote`.
- Extract remaining relevant files after Joseph accepts the 100-file gate.
- **Gate:** 500-file extract. Span-validity ≥95% on a 50-file re-audit.
  Top-10 of the research queue is not majority one author and not majority
  politics. Joseph uses the queue for one real weekly triage.

### Phase 5 — Steady state

- Incremental intake/gate/extract on new feeder files.
- `export` for a future GraphDB comparison harness.
- Outcome due-list (hit/miss) may start here; it is not a Phase 0–4
  blocker.

---

## 8. Test plan (TDD-first)

Prefer system tests that run the CLI against fixture trees over isolated
mocks of SQLite.

| Area | Must fail before the code exists |
|---|---|
| Boundary | importing `info_rank` from `kdb_graph` / `compiler` / `orchestrator` is rejected; `info_rank` does not import those |
| Intake | promo files absent; video/podcast flagged `media`; word_count matches body; bleed repaired in the view only |
| FTS | known title query returns the fixture article and not a promo path |
| Gate | each label has a fixture; unknown label fails closed |
| Extract | political fixture → 0 idea_mentions; thesis fixture → ≥1 mention with a span that is a real substring |
| Span | quote not in source → insert refused |
| Merge | opposite stances on same ticker → two `ideas` |
| Ranker | weight-only change produces a new version and does not call the model |
| Dry-run | `extract --dry-run` leaves `idea_mentions` count unchanged |
| Feedback | event is append-only; update of an old event is impossible |

Live smoke (Joseph-fired, after Phase 1): 150-file gate labels. Not part of
`pytest` CI.

---

## 9. Cost and attention

Registry prices (`common/models.json`, `deepseek-v4-flash`): $0.14/M in,
$0.28/M out. A full extract of 2,659 files would be low-single-digit
dollars. Option C extracts the relevant subset plus a 5% exploration
sample, so less.

The binding budget is Joseph minutes:

- Phase 1: ~150 gate labels
- Phase 2: ~100 extraction audits
- Phase 4: ~50 re-audit + one weekly triage

The 100-file extract run must print tokens, retries, dollars, span-validity,
and review minutes, then extrapolate before Phase 4.

---

## 10. Out of scope (v1)

- Writing into the knowledge graph or wiki
- Compiling gmail-substack through `kdb-orchestrate`
- Embeddings / vector DB (#141 remains a separate discussion)
- Automatic market-data track record
- Learning-to-rank (LambdaMART etc.)
- A new git repository
- Reopening the promo filter
- Renaming authors in the source Markdown

---

## 11. Open items that need Joseph before Proceed

These do not reopen Option C. They do need a word before code:

1. **Package name.** Keep `info_rank`, or pick something else now.
2. **Phase 1 gate threshold.** Set after the 150-file confusion matrix,
   not before.
3. **Who labels the 150?** Joseph only, or a first-pass by the agent with
   his review.

---

## 12. Implementation plan (post-Proceed only)

See §7. No code until Proceed. After Proceed, invoke the writing-plans
skill to explode §7 into a checkboxed plan under `docs/superpowers/plans/`.
