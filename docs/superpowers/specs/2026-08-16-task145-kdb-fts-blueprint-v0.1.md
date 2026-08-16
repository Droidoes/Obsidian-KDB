# kdb_fts blueprint v0.1 — the parallel extraction/ranking system (#145)

> **Status**: v0.1 draft for external panel review (2026-08-16). **Not ratified;
> no implementation until Joseph says Proceed.** Open items 1–2 from the first
> cut are resolved (D21/D22 below, Joseph 2026-08-16).
>
> **Briefs** (options-free, panel-reviewed):
> [`2026-08-16-gmail-info-search-rank-problem-statement.md`](2026-08-16-gmail-info-search-rank-problem-statement.md),
> [`2026-08-16-repo-placement-problem-statement.md`](2026-08-16-repo-placement-problem-statement.md).
> **Panel record**: round-1 responses (Grok / DeepSeek / Qwen / Codex / Claude)
> and round-2 repo-placement responses live beside this file.
> **Scaffold credit**: Grok's uncommissioned
> [`…-task145-info-rank-blueprint-v0.1-grok.md`](2026-08-16-task145-info-rank-blueprint-v0.1-grok.md)
> — used as reference; every decision below is re-derived from the synthesis,
> not inherited.

---

## 1. Problem (one paragraph)

Joseph cannot read the 2,625 rankable gmail-substack articles (plus ~tens/week
inflow). The corpus is **information, not knowledge** — mostly unrelated to
itself, majority politics/geopolitics by volume (~55%), investment-named ~17%.
He needs (1) a ranked research queue of investment ideas, (2) ranked authors
whose style and utility are learned, (3) compounding lessons distilled from the
flow, and (4) a reading queue over *everything* — all calibrated to **his**
judgment, developed iteratively from his manual evaluations. The system is a
deliberate architectural competitor to the GraphDB pipeline: same raw sources,
different extraction philosophy, head-to-head comparison planned.

## 2. Decisions (binding; changing one is a new architecture turn)

| ID | Decision | Source |
|---|---|---|
| **D1** | **Extraction-ledger family.** Extract once into structured, source-grounded records; rank deterministically many times. Retrieval (FTS5) is a read surface, never the core. | Round-1 panel 5/5 |
| **D2** | **Monorepo.** New top-level package `kdb_fts/` in Obsidian-KDB; imports `common` **only**; enforced by extending the AST boundary guard. Peer-repo split stays available via the extraction-roadmap triggers (a real second consumer). | Joseph 2026-08-16; round-2 panel 3/4 + roadmap precedent |
| **D3** | **Hard write boundary.** kdb_fts *reads* `KDB/raw/joseph-ft-public-gmail/` (and future raw trees); it never writes the wiki, manifest, graph, pipeline configs, or feeder state. Its writes are confined to its own state root — enforced by a **new mechanical write-boundary guard test**, not by convention. | Round-2 panel n/n |
| **D4** | **State root `<vault>/KDB/fts/`** — parallels `<vault>/KDB/graph`. One self-contained subtree: `ledger.sqlite`, `runs/`, `exports/`, `feedback/`, `review/`. Clean to `rm` if the experiment dies. | Joseph 2026-08-16 |
| **D5** | **Coverage = gate-then-extract.** One cheap gate call per article (topic + signal + eligibility); deep extraction only for eligible buckets. The idea/lesson ledger is never polluted by the politics majority. | Joseph 2026-08-16 |
| **D6** | **Per-topic decay.** Reading-priority decays on a topic-dependent half-life (geopolitics fast, finance/econ/investment slow); idea research-priority decays toward its extracted horizon; lessons never decay. Decay governs **unlabeled** items only — Joseph's status labels override it (D21). | Joseph's refinement (no seat proposed it) |
| **D7** | **Ranking objective** = expected value of Joseph's next research hour. Schema field is named `research_priority`; the system never predicts investment performance. | Round-1 panel n/n |
| **D8** | **Joseph's labels are ground truth for personal usefulness only.** Faithfulness (span validation), factual correctness (evidence/outcomes), and track record (post-horizon outcomes) are separate axes — never collapsed into one "quality" score. | Round-1 panel n/n |
| **D9** | **Author quality = three variables**: (a) personal utility — learnable now; (b) analytical traits — from extraction features; (c) track record — **empty until outcome data exists**; no hallucinated prior. Author weight in idea ranking is capped (v1 cap: 0.15 of the weighted sum). | Round-1 panel n/n |
| **D10** | **Faithfulness is a hard gate.** Every substantive extracted field carries an evidence span; a deterministic checker proves the span is a substring of the source paragraph. Unsupported spans fail the *record*, not the article. Zero unvalidated spans in the ledger. | Round-1 panel n/n |
| **D11** | **Zero ideas / zero lessons is a successful extraction.** The prompt must say so; forcing a filled schema is a defect. | Round-1 panel (Grok/DeepSeek) |
| **D12** | **Never merge by ticker alone.** Bull and bear theses on one company are different `ideas`. Corroboration raises *salience*, never *merit* (consensus is often crowding). | Round-1 panel n/n |
| **D13** | **Feedback = immutable events**, captured with exposure context (ranker version, score shown, position shown — the frozen batch JSON, D22, *is* the exposure record). Form = **D-hybrid**: fast bucket sort (strong / interesting / weak / noise) for everything reviewed, plus free-text reasons at the extremes — the extremes teach the rubric the most. Fixed exploration quota in every review batch against selection bias. | Joseph (D-hybrid) + round-1 panel n/n (events/exploration) |
| **D14** | **Extract once, score many.** Ranker weights are human-readable, versioned JSON; changing weights never re-extracts. Re-extraction = new `extraction_run` keyed by schema version + model + content hash. | Round-1 panel n/n |
| **D15** | **No embeddings in v1.** FTS5 over articles + extracted text. A vector adapter is allowed only after an evaluation shows FTS + structured fields missing queries Joseph actually asks. | Round-1 panel 4/5 (Qwen dissent recorded) |
| **D16** | **Skip-by-rule, no LLM**: `content_kind` in `{video, podcast}` (89 files); body < 50 words (25); the 34 "Weekly Stack" digest stubs; the 3 frontmatter-bleed files until intake repairs their *view* (original bytes untouched). | 2026-08-16 corpus audit |
| **D17** | **Source identity is stable across moves**: primary key from `gmail_message_id` (falling back to content sha256), never from the file path. Path is a mutable attribute. | Codex round-2 |
| **D18** | **State taxonomy**: (a) rebuildable — SQLite indexes, scores; (b) replayable — extraction journals (costly, but re-runnable); (c) **irreplaceable — Joseph's feedback events** (never treated as derived state; backed up with the vault; excluded from any wipe/rollback). | Codex round-2 |
| **D19** | **Default model** for gate + extraction: `deepseek-v4-flash` via `common/model_pool`. Overrideable per run. Full backlog ≈ $1–3; Joseph's review minutes are the binding budget. | Round-1 panel n/n |
| **D20** | **Dry-run / audit / reversible** per project standard: every write journaled; `--dry-run` performs intake + LLM calls but commits nothing. | Project standard |
| **D21** | **Status labels override decay.** Human vocabulary, numeric translation behind the scenes in the ranker JSON — Joseph never enters numbers. Ideas: `pending` (default; decays per D6) / `accepted` ("researched" — pinned out of the research queue, enters outcome tracking (§7.6), strong positive calibration signal) / `rejected` (score floored, strong negative signal). Lessons: `helpful` / `not-so-much` (unrated default). Labels are feedback events like everything else (D13) plus a materialized `status` column for fast queue filtering. | Joseph 2026-08-16 |
| **D22** | **Review surface v1 = local web app in the browser.** `kdb-fts review` freezes a review batch to `review/<batch_id>.json`, serves it via a stdlib-only local server with a single static page (no JS framework, no build step, no new dependency), and writes Joseph's clicks back as immutable feedback events. The Phase-1 calibration set (150 articles) is just batch `calibration-p1` in the same app. CLI `feedback` remains for scripting; markdown export is a fallback, not the primary surface. | Joseph 2026-08-16 |

## 3. System shape

```text
KDB/raw/joseph-ft-public-gmail/*.md        (immutable to kdb_fts; feeder is sole writer)
        │
        ▼
intake  (deterministic, no LLM)
  stable identity (gmail id / content hash), paragraph IDs, word count,
  digest-stub + skip-by-rule exclusion, author_map.yaml, frontmatter-bleed repair view,
  FTS5 index over the full residual corpus
        │
        ▼
gate  (one cheap LLM call per article)
  topic bucket (investment | finance-econ | geopolitics | china-econ | ai-tech | other)
  signal score 0..1 (specificity · argument density · conviction markers)
  extraction eligibility (ideas? lessons? neither)
        │
        ├─ ineligible / skip-by-rule ──► searchable + reading queue only
        │      (5% exploration sample still extracted, tagged exploration=true)
        ▼
extraction  (one structured call per eligible article)
  0..N idea_mentions + 0..N lesson_cards + validated evidence spans
        │
        ▼
canonicalize  (deterministic first pass + manual merge/split command)
  idea_mentions → ideas (clusters);  lesson_cards → frameworks
        │
        ▼
ranker  (deterministic, versioned weights; no LLM in the scoring path)
  research queue   (ideas; decay toward horizon → outcome due-list;
                    accepted → outcome track, rejected → floored (D21))
  lesson library   (no decay; 90-day re-surface; helpful/not-so-much adjust)
  reading queue    (all articles; per-topic decay on unlabeled items)
  author board     (explicit rating, else recency-weighted derived rollup)
        │
        ▼
review  (local web app: frozen batch JSON → browser page → immutable events)
  Joseph's feedback events (buckets + status labels + extreme reasons)
  + outcome checks (hit/miss/expired/running)
        │
        ▼
calibration  (hand-tuned weights → small pointwise model after ~200 events;
              never auto-swapped — Joseph accepts or rejects each ranker version)
```

## 4. Package layout & boundaries

```text
kdb_fts/
  __init__.py
  cli.py               # kdb-fts entry point (argparse subcommands)
  intake.py            # deterministic walk, identity, paragraph IDs, exclusions
  author_map.py        # raw author string → canonical author/publication (yaml)
  schema.py            # SQLite DDL + migrations
  ledger.py            # typed DB access layer (the only module that writes sqlite)
  gate.py              # relevance/topic gate (prompt, parse, salvage)
  extract.py           # idea/lesson extraction (prompt, schema, salvage)
  spans.py             # evidence-span validation (deterministic substring proof)
  cluster.py           # mentions→ideas, cards→frameworks (deterministic + manual ops)
  rank.py              # feature computation + versioned weighted scoring
  decay.py             # per-topic half-lives + horizon decay (pure functions)
  feedback.py          # immutable event append + exploration quota sampling
  review.py            # batch freezer + local web app (stdlib http.server,
                       # single static page; writes events back via feedback.py)
  assets/review.html   # the one static page (no framework, no build step)
  outcomes.py          # due-list + hit/miss recording
  export.py            # versioned JSONL/CSV snapshots (the only coupling)
  prompts/             # gate.j2 / extract.j2 (versioned)
  tests/
```

Boundary guards (both in `tools/tests/test_package_boundaries.py`):

1. **Import contract**: `ALLOWED["kdb_fts"] = {"common"}` — nothing internal else,
   and nothing else imports `kdb_fts` in v1 (the comparison harness, when built,
   reads *exports*, not the package).
2. **Write-boundary guard (new)**: walk `kdb_fts/` and assert every filesystem-write
   call site resolves under the configured state root (or a test tmp dir) — the
   "never writes wiki/manifest/graph" rule drifts silently if left to convention.

`common/` reuse: `call_model` + retry + telemetry + `model_pool` + `atomic_io`.
The infra/domain seam inside `common/` (~1,150 infra lines vs ~1,800 domain
lines — DeepSeek's measurement) is documented here as the future extraction
path; **no split while single-repo**.

## 5. State layout (`<vault>/KDB/fts/`)

| Path | Contents | Taxonomy (D18) |
|---|---|---|
| `ledger.sqlite` | system of record (all tables, FTS5 index) | rebuildable from sources + journals + feedback |
| `runs/<run_id>/journal.jsonl` | append-only run events | replayable |
| `runs/<run_id>/extractions/<id>.json` | raw + salvaged model output per article | replayable |
| `feedback/events.jsonl` | **Joseph's judgments — the irreplaceable asset** | irreplaceable; excluded from rollback/wipe |
| `review/<batch_id>.json` | frozen queue payload exactly as rendered (exposure context for D13) | rebuildable |
| `exports/<date>/` | versioned JSONL/CSV snapshots for the future harness | regenerable |
| `author_map.yaml` | raw string → canonical author/publication; Joseph-editable | config (git-backup-worthy) |

The ledger is declared **rebuildable** from (raw sources + extraction journals +
feedback events); a `kdb-fts rebuild` command is the proof, but is post-v1.
Rollback of a run = delete its `runs/<id>` subtree and replay-forward; feedback
events are never rolled back.

## 6. Data model (SQLite; raw markdown stays the source of truth)

**`articles`** — `article_id` (D17: `gmail_message_id` else content sha256),
`path` (mutable), `content_sha256`, `title`, `raw_author`, `author_id`,
`published_date`, `source_url`, `content_kind`, `word_count`,
`cleanliness` (`ok`/`short`/`media`/`digest-stub`/`bleed`/`repaired`),
`first_seen_run`, `last_seen_run`.

**`authors`** / **`publications`** — canonical ids; `author_aliases` maps each
of the 117 raw strings onto one canonical (+ optional publication). Unmapped
strings stay raw and are listed for Joseph; they never block intake. Alias rows
are re-resolved from the **current** `author_map.yaml` on every intake
(upserted, not early-returned) — Joseph's edits take effect on the next run;
repointing may orphan the old default-canonical author row (author GC is a
Phase-1 decision, not an accident).
`explicit_rating` (nullable; wins when set), `derived_score` (recency-weighted
rollup of the author's article signals).

**`gate_verdicts`** — `article_id`, `run_id`, `topic`, `signal` (0..1),
`extract_ideas` / `extract_lessons` (booleans), `model`, `prompt_version`,
`confidence`. Latest verdict routes; history kept.

**`extraction_runs`** — `run_id`, `article_id`, `schema_version`, `model`,
tokens/cost/latency, `status` (`ok`/`empty`/`failed`/`skipped`/`exploration`).

**`idea_mentions`** — what *one* article claims: `company`, `ticker` (nullable;
only if the exact string appears in the source), `stance`
(`long`/`short`/`pass`/`watch`/`unclear`), `thesis`, `valuation_premise`,
`catalyst`, `risks`, `horizon`, `expires_on`, `extraction_uncertainty`,
`idea_id` (nullable until clustered).

**`ideas`** — clusters of compatible mentions (deterministic first pass:
same normalized company + same stance + thesis token-overlap; manual
merge/split via CLI; never auto-merge opposite stances). `salience` from
independent-author corroboration; merit never inferred from consensus.
`status`: `pending` (default) / `accepted` / `rejected` (D21) — materialized
from feedback events for fast queue filtering.

**`lesson_cards`** / **`frameworks`** — `principle`, `context`,
`reusable_application`, `failure_mode`, `lesson_type`
(`framework`/`mental-model`/`mistake-postmortem`/`process`/`risk`/`behavioral`).
Cards cluster into frameworks the same way mentions cluster into ideas.
`last_surfaced_at` drives the 90-day re-surface. `rating`: `helpful` /
`not-so-much` / null (D21).

**`evidence_spans`** — `record_type` + `record_id` + `field`, `paragraph_id`,
`exact_quote`. **Insert is refused** unless `exact_quote` is a substring of
that paragraph in the source (D10).

**`feedback_events`** (immutable, append-only) — `action`
(`strong`/`interesting`/`weak`/`noise` bucket ≙ 3/2/1/0 usefulness,
`accept`/`reject` (ideas), `helpful`/`not-helpful` (lessons),
`save`/`skip`/`wrong-extraction`/`promote-to-extract`),
`target_type` (`article`/`idea`/`lesson`/`author`), `reason_text` (optional;
expected at the extremes per D13), `reason_tags`, `ranker_version`,
`score_shown`, `position_shown`, `batch_id`, `exploration` (bool), `ts`.

**`outcome_checks`** — `idea_id`, `due_on` (from `expires_on`; `accepted` ideas
get a due date even without an extracted horizon — default 90d, D21), `result`
(`hit`/`miss`/`expired`/`still-running`, null until answered), `note`.

**`rankers`** / **`score_snapshots`** — a ranker is a named, versioned JSON
object (weights + feature list + per-topic half-lives + **status-label numeric
overrides** (D21)). A snapshot is `ranker_version × record_id → scores`, so any
past queue is replayable and auditable ("why was this ranked #3 last
Tuesday?").

### Scores (four, never one "quality")

| Score | Decays? | Primary inputs |
|---|---|---|
| `idea_research_priority` | toward extracted horizon, **while `pending`** | thesis specificity, evidence quality, valuation discipline, falsifiability, risk treatment, horizon clarity, freshness-vs-horizon, corroboration (salience only), novelty, extraction uncertainty (penalty), capped author utility |
| `lesson_learning_value` | never (90-day re-surface) | principle generality, evidence, framework cluster size, Joseph's helpful/not-so-much ratings |
| `article_reading_priority` | **per-topic half-life** (D6), unlabeled only | gate signal, topic bucket, author utility, novelty |
| `author_personal_utility` | recency-weighted rollup | explicit rating (wins) else derived from article signals + acceptance rate |

Status-label overrides (D21): an `accepted` idea leaves the research queue and
moves to the outcome track; a `rejected` idea's score floors at zero (and the
reject is a strong calibration signal); a `helpful` lesson boosts its
framework; `not-so-much` suppresses re-surface. The exact magnitudes are
ranker-JSON tunables — the labels are Joseph's vocabulary, never numbers he
types.

v1 per-topic half-lives (hand-set, Joseph-tunable, in the ranker JSON):
`geopolitics` 21d · `china-econ` 45d · `ai-tech` 45d · `finance-econ` 90d ·
`investment` 90d · `other` 30d. Ideas with an extracted `horizon` use the
horizon, not the topic default. These numbers govern the **unlabeled
majority** — anything Joseph has labeled obeys D21 instead.

## 7. Processing contracts

### 7.1 Intake (no LLM)

Walk the pipeline root; honor the existing `_promo/` exclude; classify the 34
digest stubs (`and N more` title pattern on the **parsed** frontmatter field,
filename as secondary signal) and skip-by-rule classes (D16); compute word
count from the body (no such frontmatter field exists); assign stable
paragraph IDs (`p0001…`, split on blank lines); repair the 3 bleed files into
a repaired *view* (original bytes untouched); apply `author_map.yaml`; rebuild
FTS5. Idempotent — re-running on an unchanged tree is a no-op.

### 7.2 Gate (one cheap LLM call per article)

Input: title + author + published_date + body (truncated at ~4,000 words —
p95 is 4,245). Output: topic bucket (6 closed labels), `signal` 0..1,
extraction eligibility (`ideas`/`lessons`/`neither`), one-line rationale.
Unknown label fails closed to `other` + `neither`. The gate is **reversible
and logged**: Joseph can `promote` any article into extraction; each gate pass
also extracts a fixed **5% exploration sample (min 10)** of ineligible files,
stratified by author, so the gate's false-negative rate is *measured*, not
hoped (Grok's mitigation for the permanent-suppression failure mode DeepSeek
warned about — this is how D5 answers the extract-all camp's strongest point).

### 7.3 Extraction (one structured call per eligible article)

JSON-schema-gated response; schema version stamped. Per mention/card: at least
one validated evidence span or the record is dropped (other valid records from
the same article still land — per-record salvage, the #123 R1 posture). The
prompt states: emit zero mentions/lessons when none exist (D11); `ticker` only
when the exact string appears in the source. The extractor may *downgrade* an
article (`neither`), logged; it may not silently upgrade a skip-by-rule file.

### 7.4 Ranker

Deterministic function of features + ranker JSON. No LLM in the scoring path.
Expired ideas (`expires_on` < today) leave the research queue and appear on the
outcome due-list; `accepted`/`rejected` labels override decay per D21. Weight
change → new `ranker_version` + new `score_snapshots` set; no re-extraction
(D14).

### 7.5 Feedback & calibration

v1 surface is the **local web app** (D22): `kdb-fts review` freezes a review
batch to `review/<batch_id>.json` — the frozen payload doubles as the exposure
context stamped on every event from that batch (D13) — starts a stdlib-only
server, and serves one static page. In the browser Joseph gets: one-click
buckets (strong/interesting/weak/noise) per article, `accept`/`reject` per
idea (pending is the default), `helpful`/`not-so-much` per lesson, and
free-text reason boxes that surface at the extremes. Every click writes back
through `feedback.py` as an immutable event; the app writes nothing else.
The Phase-1 calibration set is batch `calibration-p1` — 150 stratified
articles rendered in the same app, no special tooling. `kdb-fts feedback`
(CLI) and markdown export remain for scripting and offline review.

Every review batch reserves **20% of slots** for exploration/uncertain/random
items, recorded on the event (D13). After **~200 events** with representative
author mix, a separate command fits a regularized pointwise model over the
feature vector and *proposes* a new ranker version; Joseph accepts or rejects —
no automatic swap. Learning-to-rank (LambdaMART etc.) is out of v1. Validation
when the time comes is **time-based** (train on older ratings, validate on
newer — Qwen's point), never random shuffle.

### 7.6 Outcome loop

The due-list (`outcome_checks` where `due_on` <= today, result null) is the
one-click "what happened?" queue, rendered as a queue kind in the review app.
`accepted` ideas enter this track immediately (default 90d due date when no
horizon was extracted, D21). This is the only channel by which author
**track record** (D9c) ever becomes non-empty — cheap because Joseph is
already the human in the loop (DeepSeek's highest-leverage addition).

## 8. CLI (v1)

| Command | Purpose |
|---|---|
| `kdb-fts intake` | Walk sources, exclusions, FTS rebuild, author map |
| `kdb-fts gate [--max N] [--dry-run]` | Topic + signal + eligibility verdicts |
| `kdb-fts extract [--max N] [--dry-run]` | Extraction on gate-admitted files |
| `kdb-fts cluster` | Rebuild idea/framework clusters |
| `kdb-fts rank [--ranker V]` | Recompute scores + snapshots |
| `kdb-fts review [--batch B] [--kind research\|lessons\|reading\|outcomes\|calibration] [--n 20]` | Freeze a batch JSON and serve the review web app |
| `kdb-fts queue [--kind …] [--n 20]` | Print/export a queue without serving (fallback surface) |
| `kdb-fts feedback <target> <action> [--reason txt] [--tags a,b]` | Append an immutable event (scripting path) |
| `kdb-fts promote <article_id>` | Force extraction past the gate |
| `kdb-fts authors` | Author board (explicit vs derived) |
| `kdb-fts export` | Versioned JSONL/CSV snapshot |
| `kdb-fts status` | Counts by verdict/run/topic, cost to date |

`--dry-run` valid on `gate`/`extract`. No silent destructive flags.

## 9. Phased delivery & TDD gates

Phases are sequential; each gate is failing-tests-first. Live-LLM gates are
Joseph-fired, never CI.

**Phase 0 — package + intake + FTS (no LLM, no cost).**
Package skeleton, boundary-guard rows, write-boundary guard, SQLite schema +
migrations, intake over a fixture tree, FTS queries.
*Gate:* intake on the real tree is idempotent and reproduces the 2026-08-16
audit exactly (2,659 intake-tree / 2,625 rankable / 34 digest stubs / 77 video /
12 podcast / 25 short / 3 bleed / 117 raw author strings); zero writes outside
`KDB/fts/`.

**Phase 1 — gate + labeling web app.**
Prompt + label schema + salvage; fixtures covering all 6 topics × eligibility
combinations. Review-app v0 (D22): batch freezer, stdlib server, static page
with bucket buttons, event write-back.
*Gate:* Joseph hand-labels **150 stratified real files** (stratified by author,
date, length, topic guess) **in the app** as batch `calibration-p1`; gate
precision/recall on `investment ∪ finance-econ` computed; **Joseph sets the
accept threshold after seeing the confusion matrix** (no invented number).
Fallback if the gate underperforms: extract-all is a ~$1 switch (D5 is a
policy, not a structural commitment).

**Phase 2 — extraction schema.**
Prompt + JSON schema + span validator + per-record salvage. Fixtures: a real
thesis article (≥1 mention with real spans), a political essay (must emit zero
ideas), a lesson-only post-mortem, a skip-by-rule stub.
*Gate:* 100-file eligible-set audit — **span-validity 100% on landed records**,
zero-idea rate on a political holdout *reported*.

**Phase 3 — ranker + queues.**
Feature computation, decay (per-topic + horizon), D21 status-label overrides,
hand-tuned v1 weights, queue CLI, three baselines (recency-only, author-only,
BM25-title).
*Gate:* on the labeled set, the hand-tuned research queue is **not worse than
all three baselines** on nDCG@10; ties go to the simpler baseline until more
labels exist.

**Phase 4 — feedback + 500-file extract + full review app.**
Event log hardening, exploration quota, promote, outcome due-list; the review
app gains idea/lesson labels and the outcome queue (D21 queues rendered).
*Gate:* extract the remaining eligible backlog; **span-validity ≥95%** on a
50-file re-audit; top-10 research queue is neither majority-one-author nor
majority-politics; Joseph completes one real weekly triage **in the app**.

**Phase 5 — steady state.**
Incremental intake/gate/extract on new feeder files; `export`; outcome
hit/miss flow in the app; calibration proposal command (post-~200 events);
review-app polish (filters, author board view) as usage dictates.

## 10. Test plan (TDD-first; system tests over mocks)

| Area | Must fail before code exists |
|---|---|
| Boundary | importing `kdb_fts` from `kdb_graph*`/`ingestion` rejected; `kdb_fts` imports only `common` |
| Write guard | a test-only write outside the state root is caught by the new guard |
| Intake | promo excluded; digests/short/media/bleed classified; word count from body; idempotent re-run |
| Identity | same file at two paths → one `article_id` (gmail id / hash, D17) |
| Gate | each topic label has a fixture; unknown label fails closed |
| Extract | political fixture → 0 idea_mentions (D11); thesis fixture → mention with span that is a real substring |
| Spans | quote not in source → insert refused |
| Cluster | opposite stances on same company → two `ideas` (D12) |
| Ranker | weight-only change → new version, zero model calls (D14); per-topic half-lives applied per bucket (D6) |
| Decay | expired idea leaves research queue, appears on outcome due-list |
| Status labels | `accept` event → idea leaves research queue, lands on outcome track (default 90d due); `reject` → score floored; magnitudes come from the ranker JSON, not code (D21) |
| Feedback | append-only; update/delete impossible; exploration quota honored in batch sampling |
| Review app | batch JSON frozen at serve time; a click round-trips into `events.jsonl` with the batch's exposure context; the app writes nothing but events (write-guard covered) |
| Dry-run | `extract --dry-run` leaves `idea_mentions` unchanged |

## 11. Cost & attention budget

- Gate over 2,625: ~4.2M words in → **< $0.5** at registry prices.
- Extraction over the eligible subset (est. 20–40% + 5% exploration):
  **< $1**. Full backlog end-to-end: **low single-digit dollars**.
- The pilot prints tokens/retries/dollars/span-validity/**review minutes**
  and extrapolates before the 500-file gate.
- Joseph's budget (the binding one): ~150 gate labels + ~100 extraction audits
  + ~50 re-audit + one weekly triage — all inside the review app, spread
  across Phases 1–4.

## 12. Out of scope (v1)

- Writing into the graph/wiki/manifest; compiling gmail-substack through
  `kdb-orchestrate`; embeddings/vectors (#141 track); automatic market-data
  track record; learning-to-rank; a second repo; reopening the promo filter;
  renaming authors in source markdown; `kdb-fts rebuild` (declared, post-v1);
  JS framework / build tooling for the review app (single static page by
  design, D22).

## 13. Open items for Joseph

1. ~~Who labels the 150?~~ **Resolved 2026-08-16** — Joseph, in the web app
   (D22).
2. ~~Review surface v1~~ **Resolved 2026-08-16** — local web app (D22);
   markdown export demoted to fallback.
3. **Per-topic half-life table** (§6) — sanity-check the six numbers; they are
   ranker-JSON tunables, not code. Note they only govern the *unlabeled*
   majority — labeled items follow D21 overrides.
